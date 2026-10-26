#!/usr/bin/env python3
"""Backtest the season simulation on completed seasons.

    python scripts/backtest_season_sim.py --cache data/raw/season_sim_backtest \\
        --out data/outputs/season_sim_backtest.md

For each completed season (2024-25 and 2025-26 by default) and each
checkpoint (after about 10, 20 and 41 games a team), the engine is rebuilt as
it would have stood that morning and the rest of the season played: the
standings to date are tallied from the clubs' own schedules (games before the
cutoff only), the current season's skater and goalie lines come from the stats
API with a game-date filter, and every earlier season is read whole. Each
projection is scored against how the season actually ended:

* points RMSE (projected mean against the final table),
* Brier score and log loss of the playoff odds against the sixteen who made it,
* 10th-90th range coverage (the share of teams that finished inside it; 0.80
  is calibrated).

A grid over the jitter (SIGMA, fixed or shrinking with games played) and the
in-season update's prior weight (K_TEAM_UPDATE) is tuned on one season and
checked on the other, and a pace projection (points to date plus the same
points percentage for the rest) is scored beside it for scale. With
``--ph-dir`` holding the card's ratings rebuilt as of each cutoff
(``scripts/run_shadow_stats.py --tables-only --ratings-as-of DATE``), the
blend toward them is scored from weight 0 to 1.

What the rebuild cannot hold as of the date, and so reads whole: each
season's rosters (``roster/{team}/{season}``, which lists everyone who
dressed, deadline arrivals included) and nothing else; the current season's
MoneyPuck expected goals are left out entirely (the in-season update then
uses goals only, as it does whenever that table is missing), and so is the
hand-kept availability list. The report says so. It reads no price and
spends no credit; every request is to the NHL's and MoneyPuck's free
endpoints and is cached under ``--cache``.

``--print-cutoffs`` prints the checkpoint dates only (for the workflow,
which rebuilds the card's ratings as of those dates before the backtest).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "web") not in sys.path:
    sys.path.insert(0, str(ROOT / "web"))

from season_sim import fetch as F  # noqa: E402
from season_sim.model import K_TEAM_UPDATE, build_model, load_ph_ratings  # noqa: E402
from season_sim.simulate import SIGMA, SIGMA_MODE, simulate  # noqa: E402

SEASONS = ("20242025", "20252026")
CHECKPOINTS = (10, 20, 41)
K_GRID = (15.0, 30.0, 45.0, 60.0)
SIGMA_GRID = (0.03, 0.05, 0.07, 0.09)
MODES = ("fixed", "shrink")
PH_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
EPS = 1e-3


def season_label(season: str) -> str:
    return f"{season[:4]}-{season[6:]}"


def prior_seasons(season: str) -> tuple[str, ...]:
    y = int(season[:4])
    return tuple(f"{y - k}{y - k + 1}" for k in (1, 2, 3))


# ----------------------------------------------------------------------
# inputs
# ----------------------------------------------------------------------
def fetch_season(cache: Path, season: str) -> dict:
    """Everything about a completed season that does not depend on the
    cutoff, cached for good (the season is closed)."""
    c = Path(cache) / season
    F._get(f"{F.NHL}/standings-season", c / "standings_season.json", required=True, ttl_hours=None)
    meta = {str(s["id"]): s for s in json.loads((c / "standings_season.json").read_text())["seasons"]}
    priors = prior_seasons(season)
    end = meta.get(season, {}).get("standingsEnd")
    prior_end = meta.get(priors[0], {}).get("standingsEnd")
    if not end or not prior_end:
        raise F.FetchError(f"standings-season does not state when {season} or {priors[0]} ended")
    F._get(f"{F.NHL}/standings/{end}", c / "standings_final.json", required=True, ttl_hours=None)
    F._get(f"{F.NHL}/standings/{prior_end}", c / "standings_prior.json", required=True, ttl_hours=None)
    final = json.loads((c / "standings_final.json").read_text())
    prior = json.loads((c / "standings_prior.json").read_text())
    teams = sorted(t["teamAbbrev"]["default"] for t in final["standings"])
    if len(teams) != 32:
        raise F.FetchError(f"{season} final standings list {len(teams)} teams")
    rosters, schedules = {}, {}
    for ab in teams:
        F._get(f"{F.NHL}/roster/{ab}/{season}", c / "roster" / f"{ab}.json", required=True, ttl_hours=None)
        F._get(f"{F.NHL}/club-schedule-season/{ab}/{season}", c / "sched" / f"{ab}.json", required=True, ttl_hours=None)
        rosters[ab] = json.loads((c / "roster" / f"{ab}.json").read_text())
        schedules[ab] = json.loads((c / "sched" / f"{ab}.json").read_text())
    skaters, goalies, moneypuck = {}, {}, {}
    for s in priors:
        F._get(F._stats_url("skater", s, "points"), c / f"skaters_{s}.json", required=True, ttl_hours=None)
        F._get(F._stats_url("goalie", s, "wins"), c / f"goalies_{s}.json", required=True, ttl_hours=None)
        skaters[s] = json.loads((c / f"skaters_{s}.json").read_text()).get("data", [])
        goalies[s] = json.loads((c / f"goalies_{s}.json").read_text()).get("data", [])
        year = int(s[:4])
        got = {}
        for kind in ("teams", "skaters", "goalies"):
            path = c / f"mp_{kind}_{year}.csv"
            ok = F._get(f"{F.MONEYPUCK}/{year}/regular/{kind}.csv", path, required=True, ttl_hours=None)
            got[kind] = path if ok else None
        moneypuck[s] = got
    return dict(season=season, cache=c, final=final, prior=prior, teams=teams, rosters=rosters,
                schedules=schedules, skaters=skaters, goalies=goalies, moneypuck=moneypuck)


def regular_games(schedules: dict) -> list[dict]:
    games = {}
    for sched in schedules.values():
        for g in sched.get("games", []):
            if g.get("gameType") == 2:
                games[g["id"]] = g
    return sorted(games.values(), key=lambda g: (g["gameDate"], g["id"]))


def cutoff_dates(schedules: dict, checkpoints=CHECKPOINTS) -> dict[int, str]:
    """The morning after the day the league's average team reached each
    checkpoint's games played."""
    games = regular_games(schedules)
    out, done = {}, 0
    teams = {t for g in games for t in (g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"])}
    for g in games:
        done += 2
        for n in checkpoints:
            if n not in out and done >= n * len(teams):
                out[n] = (date.fromisoformat(g["gameDate"]) + timedelta(days=1)).isoformat()
    return out


def standings_to_date(final: dict, games: list[dict], cutoff: str) -> dict:
    """The table as of the cutoff morning, tallied from final scores."""
    rows = {}
    for t in final["standings"]:
        ab = t["teamAbbrev"]["default"]
        rows[ab] = dict(teamAbbrev={"default": ab}, teamName=t["teamName"], conferenceAbbrev=t["conferenceAbbrev"],
                        divisionName=t["divisionName"], gamesPlayed=0, wins=0, losses=0, otLosses=0, points=0,
                        goalFor=0, goalAgainst=0, regulationWins=0, regulationPlusOtWins=0)
    for g in games:
        if g["gameDate"] >= cutoff:
            continue
        h, a = g["homeTeam"], g["awayTeam"]
        if "score" not in h or "score" not in a:
            continue
        last = (g.get("gameOutcome") or {}).get("lastPeriodType", "REG")
        hs, as_ = int(h["score"]), int(a["score"])
        win, lose = (h["abbrev"], a["abbrev"]) if hs > as_ else (a["abbrev"], h["abbrev"])
        for ab, gf, ga in ((h["abbrev"], hs, as_), (a["abbrev"], as_, hs)):
            rows[ab]["gamesPlayed"] += 1; rows[ab]["goalFor"] += gf; rows[ab]["goalAgainst"] += ga
        rows[win]["wins"] += 1; rows[win]["points"] += 2
        if last == "REG":
            rows[win]["regulationWins"] += 1
        if last != "SO":
            rows[win]["regulationPlusOtWins"] += 1
        if last == "REG":
            rows[lose]["losses"] += 1
        else:
            rows[lose]["otLosses"] += 1; rows[lose]["points"] += 1
    return {"standings": list(rows.values())}


def _stats_to_date(kind: str, season: str, sort: str, first: str, last: str) -> str:
    extra = quote(f' and gameDate<="{last} 23:59:59" and gameDate>="{first}"')
    return F._stats_url(kind, season, sort) + extra


def bundle_as_of(base: dict, cutoff: str) -> dict:
    season = base["season"]
    games = regular_games(base["schedules"])
    first = games[0]["gameDate"]
    last = (date.fromisoformat(cutoff) - timedelta(days=1)).isoformat()
    c = base["cache"]
    F._get(_stats_to_date("skater", season, "points", first, last), c / f"skaters_{season}_to_{last}.json",
           required=True, ttl_hours=None)
    F._get(_stats_to_date("goalie", season, "wins", first, last), c / f"goalies_{season}_to_{last}.json",
           required=True, ttl_hours=None)
    skaters = {season: json.loads((c / f"skaters_{season}_to_{last}.json").read_text()).get("data", [])}
    goalies = {season: json.loads((c / f"goalies_{season}_to_{last}.json").read_text()).get("data", [])}
    skaters.update(base["skaters"]); goalies.update(base["goalies"])
    schedules = {}
    for ab, sched in base["schedules"].items():
        schedules[ab] = dict(sched, games=[g if g["gameDate"] < cutoff else dict(g, gameState="FUT")
                                           for g in sched.get("games", [])])
    moneypuck = {season: dict(teams=None, skaters=None, goalies=None), **base["moneypuck"]}
    return dict(today=date.fromisoformat(cutoff), season=season, teams=base["teams"],
                standings_now=standings_to_date(base["final"], games, cutoff), standings_prior=base["prior"],
                rosters=base["rosters"], schedules=schedules, skaters=skaters, goalies=goalies, moneypuck=moneypuck)


def actual_outcome(final: dict) -> dict:
    out = {}
    for t in final["standings"]:
        made = t.get("divisionSequence", 9) <= 3 or t.get("wildcardSequence", 0) in (1, 2)
        out[t["teamAbbrev"]["default"]] = dict(pts=float(t["points"]), playoff=bool(made))
    if sum(v["playoff"] for v in out.values()) != 16:
        raise ValueError("the final standings do not mark sixteen playoff teams")
    return out


# ----------------------------------------------------------------------
# scoring
# ----------------------------------------------------------------------
def score(teams: list[str], pts: np.ndarray, playoff: np.ndarray, actual: dict) -> dict:
    """Points RMSE, playoff Brier and log loss, 10-90 coverage."""
    want = np.array([actual[t]["pts"] for t in teams])
    made = np.array([actual[t]["playoff"] for t in teams], float)
    mean = pts.mean(axis=0)
    p10, p90 = np.percentile(pts, 10, axis=0), np.percentile(pts, 90, axis=0)
    p = np.clip(playoff.mean(axis=0), EPS, 1 - EPS)
    return dict(
        rmse=float(np.sqrt(np.mean((mean - want) ** 2))),
        brier=float(np.mean((p - made) ** 2)),
        logloss=float(-np.mean(made * np.log(p) + (1 - made) * np.log(1 - p))),
        coverage=float(np.mean((want >= p10) & (want <= p90))),
    )


def pace_rmse(bundle: dict, games_per_team: int, actual: dict) -> float:
    errs = []
    for row in bundle["standings_now"]["standings"]:
        gp = row["gamesPlayed"]
        pace = row["points"] + (row["points"] / (2 * gp) if gp else 0.5) * 2 * (games_per_team - gp)
        errs.append(pace - actual[row["teamAbbrev"]["default"]]["pts"])
    return float(math.sqrt(sum(e * e for e in errs) / len(errs)))


def run_cell(bundle, actual, *, k, sigma, mode, ph=None, ph_weight=0.0, sims, seed):
    model = build_model(bundle, {}, starter_shares={}, ph_ratings=ph, ph_weight=ph_weight, k_team_update=k)
    res = simulate(model, sims=sims, seed=seed, sigma=sigma, sigma_mode=mode)
    a = res["_arrays"]
    return score(a["teams"], a["pts"], a["playoff"], actual), model


def mean_metrics(cells: list[dict]) -> dict:
    return {m: float(np.mean([c[m] for c in cells])) for m in ("rmse", "brier", "logloss", "coverage")}


# ----------------------------------------------------------------------
# report
# ----------------------------------------------------------------------
def _row(label: str, m: dict) -> str:
    return f"| {label} | {m['rmse']:.2f} | {m['brier']:.4f} | {m['logloss']:.4f} | {m['coverage']:.2f} |"


HEAD = "| | Points RMSE | Playoff Brier | Playoff log loss | 10-90 coverage |\n|:--|--:|--:|--:|--:|"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "raw" / "season_sim_backtest")
    parser.add_argument("--seasons", nargs="+", default=list(SEASONS))
    parser.add_argument("--checkpoints", nargs="+", type=int, default=list(CHECKPOINTS))
    parser.add_argument("--tune-season", default=SEASONS[0], help="Season the grid is tuned on; the others check it.")
    parser.add_argument("--sims", type=int, default=2000)
    parser.add_argument("--ph-dir", type=Path, default=None,
                        help="Directory of shadow_team_ratings_asof_<cutoff>.json files (the card's ratings as of each cutoff).")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "outputs" / "season_sim_backtest.md")
    parser.add_argument("--json", type=Path, default=None, help="Also write every cell's metrics here.")
    parser.add_argument("--print-cutoffs", action="store_true", help="Print the checkpoint dates and stop.")
    args = parser.parse_args(argv)

    bases = {s: fetch_season(args.cache, s) for s in args.seasons}
    cutoffs = {s: cutoff_dates(b["schedules"], args.checkpoints) for s, b in bases.items()}
    if args.print_cutoffs:
        print(" ".join(sorted({d for c in cutoffs.values() for d in c.values()})))
        return 0

    before = dict(k=K_TEAM_UPDATE, sigma=SIGMA, mode=SIGMA_MODE)
    grid = [dict(k=k, sigma=sg, mode=md) for k in K_GRID for sg in SIGMA_GRID for md in MODES]
    cells: list[dict] = []
    ph_cells: list[dict] = []
    pace: dict[tuple[str, int], float] = {}
    for s, base in bases.items():
        actual = actual_outcome(base["final"])
        for n, cutoff in sorted(cutoffs[s].items()):
            bundle = bundle_as_of(base, cutoff)
            games_per_team = len(regular_games(base["schedules"])) * 2 // 32
            pace[(s, n)] = pace_rmse(bundle, games_per_team, actual)
            for j, cfg in enumerate(grid):
                m, _ = run_cell(bundle, actual, sims=args.sims, seed=1000 + n, **cfg)
                cells.append(dict(season=s, n=n, cutoff=cutoff, **cfg, **m))
            if args.ph_dir:
                ph, why = load_ph_ratings(args.ph_dir / f"shadow_team_ratings_asof_{cutoff}.json")
                if ph is None:
                    print(f"{season_label(s)} after {n}: no card ratings as of {cutoff} ({why})")
                    continue
                for w in PH_WEIGHTS:
                    m, model = run_cell(bundle, actual, sims=args.sims, seed=1000 + n, ph=ph, ph_weight=w, **before)
                    ph_cells.append(dict(season=s, n=n, cutoff=cutoff, weight=w, status=model["ratings"]["ph_status"], **m))
            print(f"{season_label(s)} after {n} games ({cutoff}): scored {len(grid)} settings")

    def pick(rows, **want):
        return [r for r in rows if all(r[k] == v for k, v in want.items())]

    tune = args.tune_season
    checks = [s for s in args.seasons if s != tune]
    ranked = sorted(grid, key=lambda cfg: (mean_metrics(pick(cells, season=tune, **cfg))["logloss"],
                                           mean_metrics(pick(cells, season=tune, **cfg))["rmse"]))
    tuned = ranked[0]

    def label(cfg):
        return f"K {cfg['k']:.0f}, SIGMA {cfg['sigma']:.2f} {cfg['mode']}"

    lines = [
        "# Season simulation backtest",
        "",
        f"Written by `scripts/backtest_season_sim.py` ({args.sims:,} simulated seasons a cell). Each season is "
        "projected from the standings the morning after the league's average team reached each checkpoint, and "
        "scored against the final table. Coverage is the share of teams that finished inside the 10th-90th range "
        "(0.80 is calibrated). The rebuild reads each season's rosters whole and leaves out the current season's "
        "MoneyPuck expected goals and the availability list.",
        "",
        f"**Before** is the shipped engine ({label(before)}). **Tuned** is the grid's best on {season_label(tune)} "
        f"by playoff log loss ({label(tuned)}), checked on {', '.join(season_label(s) for s in checks) or 'nothing'}.",
        "",
    ]
    for s in args.seasons:
        lines += [f"## {season_label(s)}{' (tuned on)' if s == tune else ' (check)'}", ""]
        for n, cutoff in sorted(cutoffs[s].items()):
            b = mean_metrics(pick(cells, season=s, n=n, **before))
            t = mean_metrics(pick(cells, season=s, n=n, **tuned))
            lines += [f"After {n} games ({cutoff}); pace projection points RMSE {pace[(s, n)]:.2f}", "", HEAD,
                      _row("Before", b), _row("Tuned", t), ""]
        b = mean_metrics(pick(cells, season=s, **before)); t = mean_metrics(pick(cells, season=s, **tuned))
        lines += ["All checkpoints", "", HEAD, _row("Before", b), _row("Tuned", t), ""]
    lines += [f"## The grid on {season_label(tune)}, best ten by log loss", "", HEAD]
    for cfg in ranked[:10]:
        lines.append(_row(label(cfg), mean_metrics(pick(cells, season=tune, **cfg))))
    lines.append("")
    if ph_cells:
        lines += ["## Toward the card's PostHockey-style ratings", "",
                  "The shipped settings, with each team's strength moved this far toward the card's ratings as of "
                  "the cutoff (0 is the model's own).", ""]
        for s in args.seasons:
            lines += [f"### {season_label(s)}", "", HEAD]
            for w in PH_WEIGHTS:
                rows = pick(ph_cells, season=s, weight=w)
                if rows:
                    lines.append(_row(f"weight {w:.2f}", mean_metrics(rows)))
            lines.append("")
        best_w = min(PH_WEIGHTS, key=lambda w: mean_metrics(pick(ph_cells, weight=w))["logloss"]
                     if pick(ph_cells, weight=w) else math.inf)
        lines += [f"Best weight over every season and checkpoint by log loss: **{best_w:.2f}**.", ""]
    else:
        lines += ["## Toward the card's PostHockey-style ratings", "",
                  "Not scored: no `--ph-dir` of ratings rebuilt as of each cutoff was given.", ""]
    verdict = []
    for s in checks:
        b = mean_metrics(pick(cells, season=s, **before)); t = mean_metrics(pick(cells, season=s, **tuned))
        better = t["logloss"] < b["logloss"] and t["rmse"] <= b["rmse"] + 0.25
        verdict.append(f"{season_label(s)}: tuned log loss {t['logloss']:.4f} against {b['logloss']:.4f}, "
                       f"RMSE {t['rmse']:.2f} against {b['rmse']:.2f}, coverage {t['coverage']:.2f} against "
                       f"{b['coverage']:.2f}: {'holds' if better else 'does not hold'}.")
    lines += ["## Verdict", "", *verdict, "",
              "A setting ships only when it holds on the season it was not tuned on.", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(dict(cells=cells, ph=ph_cells, cutoffs=cutoffs, tuned=tuned, before=before,
                                             pace={f"{s}:{n}": v for (s, n), v in pace.items()}), indent=1),
                             encoding="utf-8")
    print("\n".join(lines[-6:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
