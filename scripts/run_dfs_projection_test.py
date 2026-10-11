#!/usr/bin/env python3
"""Do the lab's DraftKings projections beat DraftKings' own average?

Cooper's DFS app, The Lineup, projected every player as DraftKings' season
average nudged by the website board's team numbers (`baseline` in the app's
core, weights 0.10 / 0.10 / 0.05, judgement). On 2026-10-11 he asked for the
lab's player model to feed it instead (`scripts/publish_lineup_projections.py`).
This measures, walk-forward on every player-game the props model could price,
how far each projection lands from the DraftKings points the player actually
scored:

* `dk_average`  -- his season-to-date average (last season's before his first
  game of this one), the number DraftKings shows as AvgPointsPerGame;
* `app_today`   -- that average times the app's team factor, on the team
  model's goals and win chance for the game;
* `lab_model`   -- `dfs_projections` on the props model's walk-forward means;
* `lab_market`  -- the same with the bought prop prices' de-vigged means in
  place of the model's wherever a two-sided quote exists (card window), on
  the player-games where one does. Needs the bought prices on disk.

Error is mean absolute error and root mean square error in DraftKings points,
and the mean, over game nights, of the rank correlation between projection and
result (what a lineup builder actually uses). The intervals are bootstrapped
over game nights. It also checks the spread: how often the result lands above
`p90` (should be about 10%) and below `p10`.

Scoring omits short-handed and shootout bonuses on both sides (the logs carry
neither). Goalies are measured on starts (40+ minutes), as projections are
"if he starts". Offline; spends nothing; records nothing the card reads.

    PYTHONPATH=src .venv/bin/python scripts/run_dfs_projection_test.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from nhl_betting_lab import verdicts
from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.dfs_projections import (
    GOALIE_STAT,
    SKATER_STATS,
    actual_goalie_points,
    actual_skater_points,
    blend,
    devig,
    goalie_expected_points,
    goalie_spread,
    market_means,
    skater_expected_points,
    skater_spread,
)
from nhl_betting_lab.models.player_props import player_name_aliases
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers.team_names import load_team_name_map, resolve_team
from nhl_betting_lab.stores import label_phases

REPORT_MARKDOWN = "dfs_projection_test.md"
REPORT_JSON = "dfs_projection_test.json"
APP_WEIGHTS = {"teamGoals": 0.10, "winProb": 0.10, "oppGoals": 0.05, "leagueAvgGoals": 3.0}
REFIT_DAYS = 14
SPREAD_SAMPLE = 20000
BOOTSTRAPS = 400


def _season_of(day: str) -> str:
    d = date.fromisoformat(day[:10])
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def team_context(games: pd.DataFrame, dates: list[str]) -> dict[int, dict]:
    """Per game id: each side's expected goals and win chance, from a team
    model fitted only on games before the game's 14-day block."""
    games = games.copy()
    games["_d"] = games["date"].astype(str).str[:10]
    regular = games[pd.to_numeric(games["game_type"], errors="coerce") == 2]
    if not dates:
        return {}
    first = date.fromisoformat(min(dates))
    last = date.fromisoformat(max(dates))
    out: dict[int, dict] = {}
    start = first
    while start <= last:
        end = start + timedelta(days=REFIT_DAYS - 1)
        history = regular[regular["_d"] < start.isoformat()]
        block = regular[(regular["_d"] >= start.isoformat()) & (regular["_d"] <= end.isoformat())]
        if len(history) >= 200 and not block.empty:
            model = TeamModel().fit(history.drop(columns=["_d"]))
            for row in block.itertuples():
                home, away = str(row.home_team), str(row.away_team)
                hg, ag = model.expected_goals(home, away)
                ph, tie, pa = model.regulation_probabilities(home, away)
                out[int(row.game_id)] = {
                    home: {"goals": hg, "opp": ag, "win": ph + tie / 2, "otl": tie / 2},
                    away: {"goals": ag, "opp": hg, "win": pa + tie / 2, "otl": tie / 2},
                }
        start = end + timedelta(days=1)
    return out


def actual_points(logs: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """DraftKings points scored in every appearance (goalies: starts only)."""
    frame = logs.copy()
    for column in ("toi_seconds", "goals", "assists", "shots_on_goal", "blocked_shots", "saves", "goals_against"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    frame = frame[frame["toi_seconds"] > 0]
    skaters = frame[frame["role"].astype(str) == "skater"].copy()
    skaters["dk_actual"] = actual_skater_points(
        skaters["goals"], skaters["assists"], skaters["shots_on_goal"], skaters["blocked_shots"]
    )
    goalies = frame[(frame["role"].astype(str) == "goalie") & (frame["toi_seconds"] >= 2400)].copy()
    result = games.set_index("game_id")[["home_team", "home_goals", "away_goals", "regulation"]]
    joined = goalies.join(result, on="game_id")
    home = joined["team"].astype(str) == joined["home_team"].astype(str)
    hg = pd.to_numeric(joined["home_goals"], errors="coerce")
    ag = pd.to_numeric(joined["away_goals"], errors="coerce")
    won = np.where(home, hg > ag, ag > hg)
    regulation = joined["regulation"].astype(str).str.lower().isin({"true", "1", "yes"})
    lost_ot = ~won & ~regulation & hg.notna()
    goalies["dk_actual"] = actual_goalie_points(goalies["saves"], goalies["goals_against"], won, lost_ot.to_numpy())
    out = pd.concat([skaters, goalies], ignore_index=True)
    out["date"] = out["date"].astype(str).str[:10]
    return out[["game_id", "player_id", "date", "role", "position", "dk_actual"]]


def dk_average(points: pd.DataFrame) -> pd.Series:
    """Season-to-date average before each appearance; last season's average
    before a player's first game of a season; NaN with neither."""
    points = points.sort_values(["player_id", "date", "game_id"]).copy()
    points["season"] = points["date"].map(_season_of)
    grouped = points.groupby(["player_id", "season"])["dk_actual"]
    before = grouped.cumsum() - points["dk_actual"]
    count = grouped.cumcount()
    to_date = before / count.replace(0, np.nan)
    season_mean = points.groupby(["player_id", "season"])["dk_actual"].mean()
    previous = {}
    for (player_id, season), value in season_mean.items():
        start = int(season[:4]) + 1
        previous[(player_id, f"{start}-{str(start + 1)[2:]}")] = value
    fallback = [previous.get((p, s), np.nan) for p, s in zip(points["player_id"], points["season"])]
    points["dk_average"] = to_date.fillna(pd.Series(fallback, index=points.index))
    return points.set_index(["game_id", "player_id"])["dk_average"]


def market_anchors(prices: pd.DataFrame, frame: pd.DataFrame, team_names, r: dict) -> dict:
    """{(game_id, player_id): {stat: mean}} from the bought card-window prices."""
    prices = label_phases(prices)
    prices = prices[(prices["phase"] == "card") & prices["market"].isin(set(SKATER_STATS) | {GOALIE_STAT})]
    prices = prices[prices["selection"].astype(str).str.lower().isin({"over", "under"})]
    if prices.empty:
        return {}
    commence = pd.to_datetime(prices["commence_time"], errors="coerce", utc=True)
    prices = prices.assign(_day=commence.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d"))
    labels = set(prices["home_team"].astype(str)) | set(prices["away_team"].astype(str))
    teams = {label: resolve_team(label, team_names) for label in labels}
    who: dict[tuple[str, str], dict[int, tuple[str, int]]] = {}
    for row in frame[["date", "player", "player_id", "team", "game_id"]].drop_duplicates().itertuples():
        for alias in player_name_aliases(row.player):
            who.setdefault((row.date, alias), {})[int(row.player_id)] = (str(row.team), int(row.game_id))
    alias_cache: dict[str, tuple[str, ...]] = {}
    sides: dict[tuple, dict[str, float]] = {}
    for row in prices.itertuples():
        name = str(row.player)
        aliases = alias_cache.setdefault(name, player_name_aliases(name))
        home, away = teams.get(str(row.home_team)), teams.get(str(row.away_team))
        found: dict[int, tuple[str, int]] = {}
        for alias in aliases:
            for pid, (team, game_id) in who.get((row._day, alias), {}).items():
                if team in (home, away):
                    found[pid] = (team, game_id)
        if len(found) != 1:
            continue
        (pid, (_team, game_id)), = found.items()
        key = (game_id, pid, str(row.market), float(row.line), str(row.book))
        sides.setdefault(key, {})[str(row.selection).lower()] = float(row.american_odds)
    quotes = []
    for (game_id, pid, market, line, _book), pair in sides.items():
        if "over" in pair and "under" in pair:
            p = devig(pair["over"], pair["under"])
            if p is not None:
                quotes.append(((game_id, pid), market, line, p))
    means = market_means(quotes, r)
    out: dict = {}
    for ((game_id, pid), market), (mean, _books) in means.items():
        out.setdefault((game_id, pid), {})[market] = mean
    return out


def _metrics(frame: pd.DataFrame, column: str, rng: np.random.Generator) -> dict:
    err = frame[column] - frame["dk_actual"]
    nights = frame["date"].to_numpy()
    by_night = pd.DataFrame({"night": nights, "abs": err.abs(), "sq": err**2})
    agg = by_night.groupby("night").agg(abs_sum=("abs", "sum"), sq_sum=("sq", "sum"), n=("abs", "size"))
    idx = np.arange(len(agg))
    boots = []
    for _ in range(BOOTSTRAPS):
        pick = agg.iloc[rng.choice(idx, size=len(idx))]
        boots.append(pick["abs_sum"].sum() / pick["n"].sum())
    rank = []
    for _night, rows in frame.groupby("date"):
        if len(rows) >= 10:
            rho = stats.spearmanr(rows[column], rows["dk_actual"]).statistic
            if np.isfinite(rho):
                rank.append(rho)
    return {
        "n": int(len(frame)),
        "mae": float(err.abs().mean()),
        "mae_low": float(np.percentile(boots, 2.5)),
        "mae_high": float(np.percentile(boots, 97.5)),
        "rmse": float(math.sqrt((err**2).mean())),
        "bias": float(err.mean()),
        "rank": float(np.mean(rank)) if rank else float("nan"),
    }


def _paired(frame: pd.DataFrame, a: str, b: str, rng: np.random.Generator) -> dict:
    """MAE of `a` minus MAE of `b`, bootstrapped over nights (negative: `a` better)."""
    diff = (frame[a] - frame["dk_actual"]).abs() - (frame[b] - frame["dk_actual"]).abs()
    agg = pd.DataFrame({"night": frame["date"], "d": diff}).groupby("night")["d"].agg(["sum", "size"])
    idx = np.arange(len(agg))
    boots = [
        (lambda pick: pick["sum"].sum() / pick["size"].sum())(agg.iloc[rng.choice(idx, size=len(idx))])
        for _ in range(BOOTSTRAPS)
    ]
    return {"delta": float(diff.mean()), "low": float(np.percentile(boots, 2.5)), "high": float(np.percentile(boots, 97.5))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)
    processed, outputs = Path(args.processed_dir), Path(args.output_dir)
    logs = load_player_logs(processed)
    games = load_team_games(processed)
    if logs.empty or games.empty:
        print("::error::Need player logs and team games on disk first.", file=sys.stderr)
        return 1
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)
    print("Generating walk-forward samples...")
    samples, walk = generate_prop_samples(logs, use_rest=use_rest)
    print(f"  {walk.summary_line()}")
    if samples.empty:
        print("::error::The walk-forward priced nothing.", file=sys.stderr)
        return 1

    r = {
        market: float(np.nanmedian(rows["dispersion_r"])) if rows["dispersion_r"].notna().any() else math.nan
        for market, rows in samples.groupby("market")
    }
    keys = ["date", "game_id", "player_id", "player", "team", "opponent", "venue"]
    wide = samples.pivot_table(index=keys, columns="market", values="mean", aggfunc="first").reset_index()
    context = team_context(games, sorted(wide["date"].unique()))
    points = actual_points(logs, games)
    average = dk_average(points)
    wide = wide.merge(points[["game_id", "player_id", "dk_actual", "position"]], on=["game_id", "player_id"], how="inner")
    wide["dk_average"] = [average.get((g, p), np.nan) for g, p in zip(wide["game_id"], wide["player_id"])]
    ctx = [context.get(int(g), {}).get(str(t)) for g, t in zip(wide["game_id"], wide["team"])]
    wide["team_goals"] = [c["goals"] if c else np.nan for c in ctx]
    wide["opp_goals"] = [c["opp"] if c else np.nan for c in ctx]
    wide["win"] = [c["win"] if c else np.nan for c in ctx]
    wide["otl"] = [c["otl"] if c else np.nan for c in ctx]
    wide = wide.dropna(subset=["dk_average", "team_goals"]).reset_index(drop=True)
    goalie = wide[GOALIE_STAT].notna() if GOALIE_STAT in wide else pd.Series(False, index=wide.index)
    wide["group"] = np.where(goalie, "G", np.where(wide["position"].astype(str).str.upper().str.startswith("D"), "D", "F"))

    w, L = APP_WEIGHTS, APP_WEIGHTS["leagueAvgGoals"]
    factor_skater = 1 + w["teamGoals"] * (wide["team_goals"] - L) + w["winProb"] * (wide["win"] - 0.5) + w["oppGoals"] * (L - wide["opp_goals"])
    factor_goalie = 1 + 2 * w["winProb"] * (wide["win"] - 0.5) + w["oppGoals"] * (L - wide["opp_goals"])
    wide["app_today"] = (wide["dk_average"] * np.where(goalie, factor_goalie, factor_skater)).clip(lower=0)

    sk = wide[~goalie]
    gk = wide[goalie]
    wide["lab_model"] = np.nan
    if not sk.empty:
        exp = skater_expected_points(sk["goals"], sk["assists"], sk["shots_on_goal"], sk["blocked_shots"], r=r)
        wide.loc[sk.index, "lab_model"] = exp["dk"]
    if not gk.empty:
        exp = goalie_expected_points(gk[GOALIE_STAT], gk["opp_goals"], gk["win"], gk["otl"], saves_r=r.get(GOALIE_STAT, math.nan))
        wide.loc[gk.index, "lab_model"] = exp["dk"]

    prices_path = processed / "historical_prop_prices.csv"
    anchored_note = "No bought prop prices on disk, so the market-anchored projection was not measured."
    wide["lab_market"] = np.nan
    if prices_path.is_file():
        print("Reading the bought prices...")
        prices = pd.read_csv(prices_path)
        anchors = market_anchors(prices, wide, load_team_name_map(processed_dir=processed), r)
        del prices
        has = [(int(g), int(p)) in anchors for g, p in zip(wide["game_id"], wide["player_id"])]
        rows = wide[has]
        for i, row in rows.iterrows():
            market = anchors[(int(row["game_id"]), int(row["player_id"]))]
            if row["group"] == "G":
                saves = market.get(GOALIE_STAT, row[GOALIE_STAT])
                wide.at[i, "lab_market"] = float(goalie_expected_points(
                    [saves], [row["opp_goals"]], [row["win"]], [row["otl"]], saves_r=r.get(GOALIE_STAT, math.nan)
                )["dk"][0])
            else:
                means, _ = blend({s: float(row[s]) for s in SKATER_STATS}, market)
                wide.at[i, "lab_market"] = float(skater_expected_points(
                    [means["goals"]], [means["assists"]], [means["shots_on_goal"]], [means["blocked_shots"]], r=r
                )["dk"][0])
        anchored_note = (
            f"{int(wide['lab_market'].notna().sum()):,} of {len(wide):,} player-games had a two-sided "
            "card-window quote on at least one stat."
        )

    rng = np.random.default_rng(7)
    wide["season"] = wide["date"].map(_season_of)
    columns = ["dk_average", "app_today", "lab_model"]
    results: dict = {"overall": {}, "by_group": {}, "by_season": {}}
    for c in columns:
        results["overall"][c] = _metrics(wide, c, rng)
    for group, rows in wide.groupby("group"):
        results["by_group"][group] = {c: _metrics(rows, c, rng) for c in columns}
    for season, rows in wide.groupby("season"):
        results["by_season"][season] = {c: _metrics(rows, c, rng) for c in columns}
    results["lab_vs_average"] = _paired(wide, "lab_model", "dk_average", rng)
    results["lab_vs_app"] = _paired(wide, "lab_model", "app_today", rng)
    anchored = wide[wide["lab_market"].notna()]
    if len(anchored) >= 500:
        results["anchored"] = {c: _metrics(anchored, c, rng) for c in columns + ["lab_market"]}
        results["market_vs_model"] = _paired(anchored, "lab_market", "lab_model", rng)

    # Spread: does the result land above p90 one time in ten?
    pick = wide.sample(n=min(SPREAD_SAMPLE, len(wide)), random_state=11)
    above = below = 0
    psk = pick[pick["group"] != "G"]
    pgk = pick[pick["group"] == "G"]
    if not psk.empty:
        sp = skater_spread(psk["goals"].to_numpy(), psk["assists"].to_numpy(), psk["shots_on_goal"].to_numpy(), psk["blocked_shots"].to_numpy(), r=r, draws=1500)
        above += int((psk["dk_actual"].to_numpy() > sp["p90"]).sum())
        below += int((psk["dk_actual"].to_numpy() < sp["p10"]).sum())
    if not pgk.empty:
        sp = goalie_spread(pgk[GOALIE_STAT].to_numpy(), pgk["opp_goals"].to_numpy(), pgk["win"].to_numpy(), pgk["otl"].to_numpy(), saves_r=r.get(GOALIE_STAT, math.nan), draws=1500)
        above += int((pgk["dk_actual"].to_numpy() > sp["p90"]).sum())
        below += int((pgk["dk_actual"].to_numpy() < sp["p10"]).sum())
    results["spread"] = {"n": int(len(pick)), "above_p90": above / len(pick), "below_p10": below / len(pick)}

    lab = results["lab_vs_average"]
    better = lab["high"] < 0
    verdict = (
        f"The lab's projection misses by {results['overall']['lab_model']['mae']:.2f} DraftKings points on average "
        f"against {results['overall']['dk_average']['mae']:.2f} for DraftKings' own average and "
        f"{results['overall']['app_today']['mae']:.2f} for the app's current formula, over "
        f"{len(wide):,} player-games. Paired against the average: {lab['delta']:+.3f} points "
        f"[{lab['low']:+.3f}, {lab['high']:+.3f}], "
        + ("so the lab's projection is measurably closer." if better else
           "an interval that does not show the lab's projection closer.")
    )
    payload = {"use_rest": use_rest, "player_games": len(wide), "dispersion_r": r, "anchored_note": anchored_note,
               "verdict": verdict, "results": results}
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(json.dumps(payload, indent=2, sort_keys=True, default=float) + "\n", encoding="utf-8")

    def line(name: str, m: dict) -> str:
        return (f"| {name} | {m['n']:,} | {m['mae']:.3f} [{m['mae_low']:.3f}, {m['mae_high']:.3f}] | "
                f"{m['rmse']:.3f} | {m['bias']:+.3f} | {m['rank']:.3f} |")

    names = {"dk_average": "DraftKings average", "app_today": "The Lineup today", "lab_model": "Lab model", "lab_market": "Lab, books' means"}
    head = ["| Projection | Player-games | MAE [95%] | RMSE | Bias | Rank corr. per night |", "|:--|--:|--:|--:|--:|--:|"]
    lines = ["# DraftKings projections: the lab against DraftKings' average", "",
             "Walk-forward over every player-game the props model could price (14-day refits). "
             "Error in DraftKings points; intervals bootstrapped over game nights. Short-handed and "
             "shootout bonuses are left out of every column. Goalies on starts only.", "", "## All players", "", *head]
    lines += [line(names[c], results["overall"][c]) for c in columns]
    lines += ["", f"Lab minus DraftKings average, MAE: {lab['delta']:+.3f} [{lab['low']:+.3f}, {lab['high']:+.3f}]. "
              f"Lab minus the app's formula: {results['lab_vs_app']['delta']:+.3f} "
              f"[{results['lab_vs_app']['low']:+.3f}, {results['lab_vs_app']['high']:+.3f}]. Negative is the lab closer.", ""]
    for group, label in (("F", "Forwards"), ("D", "Defence"), ("G", "Goalies (starts)")):
        if group in results["by_group"]:
            lines += [f"## {label}", "", *head, *[line(names[c], results["by_group"][group][c]) for c in columns], ""]
    for season, block in results["by_season"].items():
        lines += [f"## {season}", "", *head, *[line(names[c], block[c]) for c in columns], ""]
    lines += ["## With the books' numbers", "", anchored_note, ""]
    if "anchored" in results:
        mv = results["market_vs_model"]
        lines += [*head, *[line(names[c], results["anchored"][c]) for c in columns + ["lab_market"]], "",
                  f"Books' means minus the model's, MAE: {mv['delta']:+.3f} [{mv['low']:+.3f}, {mv['high']:+.3f}].", ""]
    sp = results["spread"]
    lines += ["## Spread", "", f"On {sp['n']:,} sampled player-games the result beat the projected p90 "
              f"{sp['above_p90']:.1%} of the time and fell under p10 {sp['below_p10']:.1%} (10% each if the range is right).",
              "", "## Verdict", "", verdict, ""]
    text = "\n".join(lines)
    (outputs / REPORT_MARKDOWN).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
