#!/usr/bin/env python3
"""Score each model layer added from 2026-10-22 on the settled live picks.

Cooper, 2026-11-09 ("Yes do all 4"): keep what helps, cut what hurts. Every
layer is scored the same way: the frozen opinions of settled nights, priced
once with the layer as the card ran it and once with that layer alone taken
out, both against the SAME frozen best price and the SAME settled outcome.
Only the probability moves, so the difference is the layer.

Two populations, one bet per wager at the best frozen price, flat 1u:

* **Population B**: the registered statistic's population, the edge clearing
  the measurement bar (6% prop, 3.5% team).
* **Staked**: what the card would stake: 12% prop / 9% team, priced -160 to
  +600, a team side the model gives at least 40% to win, a prop clearing its
  odds-bracket floor, and no `points` stake.

Intervals are clustered on the game (`stats.clustered_mean_interval`).

## Where each counterfactual comes from

* **Team markets** (moneyline, and game totals through the goals): the card's
  own layer-by-layer breakdown, frozen into each night's site board as
  `games[].factors` (`factor_breakdown`, from 2026-10-26). Taking a layer out
  subtracts its step from the card's number: its win-chance delta for the
  moneyline, and for a total the change in the over's Poisson chance that its
  goals step made. First order: a layer's step is measured with the earlier
  layers on, as the card applies them. The base step (shooter-adjusted,
  score-adjusted xG ratings) has no "off" here, because without it there is
  no team model at all; the lineup step holds the player ratings, their aging
  and the skater defence together, as the card applies them as one.
* **Props**: the walk-forward props model (`generate_prop_samples`) priced
  over this season's nights with the card's layers on (last-five team form,
  matchup by position, the hits model), and again with one taken out; both
  joined to the ledger's frozen prices by `run_backtest`. That is the card's
  model family, not the card's exact model (it has no posted lines, referees
  or saves context), so its agreement with the frozen probability is printed.
* **Self-learning**: walk-forward on the ledger, each night with what had
  settled before it, as `run_self_learning_check.py` does.
* **Not scorable from settled data**: line movement and posted lines' ice
  time on props. The snapshot freezes the morning's first opinion, before any
  movement exists, and nothing kept re-prices props without tonight's lines.

## The rule, fixed before any result was read

A layer is CUT when taking it out improves BOTH populations, population B by
at least 2 points of ROI (its units difference over the wagers either
version bets), and population B improves in both halves of the window
(before 2026-11-01 and from it). With fewer than 30 wagers whose bet changes
it is too few to judge, and kept. Everything else is kept. Three weeks
cannot show an edge either way; the rule cuts only a layer that loses
plainly and consistently.

Reads the forward ledger, the player logs and the frozen site boards; writes
`data/outputs/layer_scoring.md` and `.json`. Spends nothing, prices nothing
live, reaches nothing the card reads.

    PYTHONPATH=src python scripts/run_layer_scoring.py --history-dir dist/data/history
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from nhl_betting_lab.config import MIN_EDGE, MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.stats import clustered_mean_interval

WINDOW_FROM = "2026-10-22"
HALF_SPLIT = "2026-11-01"
STAKE_TEAM = 0.09
STAKE_PROP = 0.12
MIN_WIN = 0.40
PRICE_LOW, PRICE_HIGH = -160.0, 600.0
CUT_ROI_POINTS = 0.02
TOO_FEW = 30
TEAM_LAYERS = ("home_ice", "form", "rest", "lineup", "goalies", "referees", "posthockey")
LAYER_LABELS = {
    "home_ice": "Each team's own home ice (#344)",
    "form": "Last-five team form, team markets (#345)",
    "rest": "Rest and travel (#346)",
    "lineup": "Posted lineup: player ratings, aging, skater defence (#346, #353, #354, #356)",
    "goalies": "Tonight's starting goalies, team markets (#351)",
    "referees": "Referee crews (#346, #348)",
    "posthockey": "PostHockey pre-game blend, 50/50 (#350)",
    "team_form_props": "Last-five team form, props (#345)",
    "position_matchup": "Matchup by position, props (#346)",
    "self_learning": "Self-learning, by side (#383, #427)",
}
REPORT_MD = "layer_scoring.md"
REPORT_JSON = "layer_scoring.json"


def implied(american: float) -> float:
    american = float(american)
    return 100.0 / (american + 100.0) if american > 0 else -american / (-american + 100.0)


def poisson_over(mean: float, line: float) -> float:
    """P(X > line) for a Poisson count, line a half-point."""
    if not mean or mean <= 0:
        return 0.0
    k_max = int(math.floor(line))
    term = math.exp(-mean)
    cdf = term
    for k in range(1, k_max + 1):
        term *= mean / k
        cdf += term
    return max(0.0, 1.0 - cdf)


@dataclass
class Scored:
    """One population of one variant: per-wager profit (0 when not bet)."""

    profit: pd.Series
    bet: pd.Series


def population(frame: pd.DataFrame, prob: pd.Series, *, staked: bool) -> pd.Series:
    """Which wagers a variant bets, given its probabilities. `frame` carries
    market, selection, american_odds, is_prop."""
    edge = prob - frame["implied"]
    is_prop = frame["is_prop"].astype(bool)
    if not staked:
        return edge >= np.where(is_prop, MIN_PROP_EDGE, MIN_EDGE) - 1e-12
    from nhl_betting_lab.reports.gameday_card import prop_confidence_reason

    odds = frame["american_odds"].astype(float)
    ok = (edge >= np.where(is_prop, STAKE_PROP, STAKE_TEAM) - 1e-12) & (odds >= PRICE_LOW) & (odds <= PRICE_HIGH)
    ok &= frame["market"].astype(str) != "points"
    moneyline_side = frame["market"].astype(str) == "moneyline"
    ok &= ~moneyline_side | (prob >= MIN_WIN)
    bracket = [
        (not p) or prop_confidence_reason(o, q) == ""
        for p, o, q in zip(is_prop, odds, prob)
    ]
    return ok & np.array(bracket, dtype=bool)


def compare(frame: pd.DataFrame, full: pd.Series, without: pd.Series, *, staked: bool) -> dict:
    """The layer's contribution: units with it minus units without it."""
    with_bet = population(frame, full, staked=staked)
    without_bet = population(frame, without, staked=staked)
    profit = frame["profit_units"].astype(float)
    games = list(frame["game"])
    out: dict = {}
    for name, mask in (("with", with_bet), ("without", without_bet)):
        rows = frame[mask]
        if len(rows) >= 1:
            iv = clustered_mean_interval(rows["profit_units"].astype(float).tolist(), list(rows["game"]))
            out[name] = {"bets": int(len(rows)), "units": float(rows["profit_units"].sum()),
                         "roi": iv.roi, "low": iv.low, "high": iv.high}
        else:
            out[name] = {"bets": 0, "units": 0.0, "roi": 0.0, "low": 0.0, "high": 0.0}
    union = with_bet | without_bet
    diff = (profit * with_bet.astype(float) - profit * without_bet.astype(float))[union]
    changed = int((with_bet != without_bet).sum())
    out["contribution_units"] = float(diff.sum())
    out["union_wagers"] = int(union.sum())
    out["changed_wagers"] = changed
    if union.sum() >= 2:
        iv = clustered_mean_interval(diff.tolist(), [g for g, u in zip(games, union) if u])
        out["contribution_per_wager"] = iv.roi
        out["contribution_low"] = iv.low
        out["contribution_high"] = iv.high
    halves = {}
    early = frame["snapshot_date"].astype(str) < HALF_SPLIT
    for label, part in (("before", early), ("after", ~early)):
        d = (profit * with_bet.astype(float) - profit * without_bet.astype(float))[union & part]
        halves[label] = float(d.sum())
    out["halves"] = halves
    return out


def verdict(pop_b: dict, staked: dict) -> str:
    """The rule fixed before any result was read (module docstring)."""
    if pop_b["changed_wagers"] < TOO_FEW:
        return "keep (too few changed wagers to judge)"
    union = max(pop_b["union_wagers"], 1)
    hurts_b = pop_b["contribution_units"] / union <= -CUT_ROI_POINTS
    hurts_staked = staked["contribution_units"] < 0
    consistent = pop_b["halves"]["before"] < 0 and pop_b["halves"]["after"] < 0
    if hurts_b and hurts_staked and consistent:
        return "cut"
    return "keep"


def load_ledger(paths: list[Path], processed: Path) -> pd.DataFrame:
    files: list[Path] = []
    for given in paths or [processed / "forward_evidence.csv"]:
        files += sorted(given.glob("*.csv")) if given.is_dir() else [given]
    frames = [pd.read_csv(p, dtype={"player": str}) for p in files if p.is_file()]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def settled_wagers(ledger: pd.DataFrame) -> pd.DataFrame:
    from nhl_betting_lab.closing_lines import collapse_to_best
    from nhl_betting_lab.markets import MARKETS_BY_KEY

    wagers = collapse_to_best(ledger)
    wagers = wagers[wagers["outcome"].isin(["won", "lost", "push"])].copy()
    wagers = wagers[wagers["snapshot_date"].astype(str) >= WINDOW_FROM]
    wagers["implied"] = wagers["american_odds"].map(implied)
    wagers["is_prop"] = wagers["market"].map(lambda m: bool(getattr(MARKETS_BY_KEY.get(m), "is_prop", False)))
    wagers["game"] = list(zip(wagers["home_team"].astype(str), wagers["away_team"].astype(str),
                              wagers["snapshot_date"].astype(str)))
    return wagers.reset_index(drop=True)


def team_counterfactuals(wagers: pd.DataFrame, history: Path, team_names: dict) -> tuple[pd.DataFrame, dict]:
    """Moneyline and total rows with one column per layer taken out."""
    from nhl_betting_lab.providers.team_names import resolve_team

    note = {"boards": 0, "games_with_factors": 0, "games_matched": 0, "games_mismatched": 0}
    team = wagers[wagers["market"].isin(["moneyline", "total_goals"])].copy()
    if team.empty or not history.is_dir():
        return team.iloc[0:0], note
    team["home_abbr"] = team["home_team"].map(lambda n: resolve_team(n, team_names))
    team["away_abbr"] = team["away_team"].map(lambda n: resolve_team(n, team_names))
    for layer in TEAM_LAYERS:
        team[layer] = np.nan
    keep = []
    for path in sorted(history.glob("20??-??-??.json")):
        day = path.stem
        if day < WINDOW_FROM:
            continue
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        note["boards"] += 1
        for game in board.get("games") or []:
            steps = game.get("factors") or []
            if not steps:
                continue
            note["games_with_factors"] += 1
            home, away = (game.get("home") or {}).get("abbr"), (game.get("away") or {}).get("abbr")
            rows = team[(team["snapshot_date"].astype(str) == day) & (team["home_abbr"] == home)
                        & (team["away_abbr"] == away)]
            final = float(steps[-1]["homeWin"])
            ml_home = rows[(rows["market"] == "moneyline") & (rows["selection"].astype(str) == "home")]
            if ml_home.empty or abs(float(ml_home["model_probability"].iloc[0]) - final) > 0.01:
                note["games_mismatched"] += 1
                continue
            note["games_matched"] += 1
            goals = [float(s.get("homeGoals") or 0) + float(s.get("awayGoals") or 0) for s in steps]
            mu_full = goals[-1]
            by_key = {str(s["key"]): i for i, s in enumerate(steps)}
            for idx in rows.index:
                row = team.loc[idx]
                prob = float(row["model_probability"])
                side = str(row["selection"])
                for layer in TEAM_LAYERS:
                    i = by_key.get(layer)
                    if i is None or i == 0:
                        team.at[idx, layer] = prob
                        continue
                    if row["market"] == "moneyline":
                        delta = float(steps[i].get("delta") or 0.0)
                        moved = prob - delta if side == "home" else prob + delta
                    else:
                        line = float(row["line"])
                        mu_without = mu_full - (goals[i] - goals[i - 1])
                        shift = poisson_over(mu_full, line) - poisson_over(mu_without, line)
                        moved = prob - shift if side == "over" else prob + shift
                    team.at[idx, layer] = min(max(moved, 0.001), 0.999)
                keep.append(idx)
    return team.loc[sorted(set(keep))], note


def props_counterfactuals(wagers: pd.DataFrame, ledger: pd.DataFrame, processed: Path, outputs: Path,
                          team_names: dict) -> tuple[pd.DataFrame, dict]:
    """Prop wagers with the walk-forward probability, full and with one layer out."""
    from nhl_betting_lab import verdicts
    from nhl_betting_lab.backtest.walk_forward import DEFAULT_LINES, generate_prop_samples
    from nhl_betting_lab.data.build_datasets import load_player_logs
    from nhl_betting_lab.models.player_props import HITS_OPTIONS
    from nhl_betting_lab.models.player_props import player_key
    from nhl_betting_lab.reports.player_props_backtest import run_backtest

    note: dict = {}
    logs = load_player_logs(processed)
    markets = ["shots_on_goal", "points", "goals", "assists", "blocked_shots", "hits"]
    rows = ledger[ledger["market"].isin(markets) & (ledger["snapshot_date"].astype(str) >= WINDOW_FROM)]
    settled_days = set(wagers["snapshot_date"].astype(str))
    rows = rows[rows["snapshot_date"].astype(str).isin(settled_days)]
    if logs.empty or rows.empty:
        note["skipped"] = "no player logs or no prop rows"
        return pd.DataFrame(), note
    lines = {m: tuple(sorted(set(DEFAULT_LINES.get(m, ())) | set(
        float(x) for x in rows.loc[rows["market"] == m, "line"].dropna().unique()))) for m in markets}
    prices = rows.assign(date=rows["snapshot_date"].astype(str))[
        ["date", "commence_time", "home_team", "away_team", "market", "player", "selection", "line",
         "american_odds", "book"]]
    use_rest = verdicts.ships("props_b2b", output_dir=outputs)
    variants = {
        "full": {"team_form": True, "position_matchup": True},
        "team_form_props": {"team_form": False, "position_matchup": True},
        "position_matchup": {"team_form": True, "position_matchup": False},
    }
    keyed: dict[str, pd.DataFrame] = {}
    for name, options in variants.items():
        print(f"Walk-forward props, {name} ...", flush=True)
        samples, walk = generate_prop_samples(
            logs, lines=lines, start_date=WINDOW_FROM, refit_days=7, use_rest=use_rest,
            hits_options=HITS_OPTIONS, **options,
        )
        print(f"  {walk.summary_line()}", flush=True)
        report = run_backtest(prices, samples, edge_threshold=-1.0, phase="", team_names=team_names)
        bets = pd.DataFrame([{
            "date": b.date, "market": b.market, "pkey": player_key(b.player), "line": float(b.line),
            "selection": b.selection, "prob": b.model_probability,
        } for b in report.bets])
        keyed[name] = bets.drop_duplicates(["date", "market", "pkey", "line", "selection"])
        note[name] = int(len(bets))
    props = wagers[wagers["market"].isin(markets)].copy()
    props["pkey"] = props["player"].map(player_key)
    props["line"] = props["line"].astype(float)
    props["date"] = props["snapshot_date"].astype(str)
    props["selection"] = props["selection"].astype(str)
    key = ["date", "market", "pkey", "line", "selection"]
    for name, bets in keyed.items():
        props = props.merge(bets.rename(columns={"prob": f"p_{name}"}), on=key, how="left")
    props = props.dropna(subset=[f"p_{n}" for n in variants])
    if not props.empty:
        gap = (props["p_full"] - props["model_probability"].astype(float)).abs()
        note["matched_wagers"] = int(len(props))
        note["mean_abs_gap_to_frozen"] = float(gap.mean())
        note["corr_to_frozen"] = float(np.corrcoef(props["p_full"], props["model_probability"].astype(float))[0, 1])
    return props, note


def self_learning_rows(wagers: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    from nhl_betting_lab.self_learning import Trust, adjusted, fit_trust, side_key, side_of

    out = []
    for day in sorted(wagers["snapshot_date"].astype(str).unique()):
        trust = fit_trust(ledger[ledger["snapshot_date"].astype(str) < day], by_side=True)
        today = wagers[wagers["snapshot_date"].astype(str) == day].copy()
        today["learned"] = [
            adjusted(r.model_probability, r.american_odds,
                     trust.get(side_key(r.market, side_of(r.market, r.selection, r.line))) or trust.get(r.market, Trust()))
            for r in today.itertuples()
        ]
        out.append(today)
    return pd.concat(out) if out else wagers.iloc[0:0]


def score(frame: pd.DataFrame, full: str, without: str) -> dict:
    pop_b = compare(frame, frame[full].astype(float), frame[without].astype(float), staked=False)
    staked = compare(frame, frame[full].astype(float), frame[without].astype(float), staked=True)
    return {"population_b": pop_b, "staked": staked, "verdict": verdict(pop_b, staked)}


def _cell(entry: dict) -> str:
    if not entry["bets"]:
        return "0 bets"
    return f"{entry['units']:+.1f}u / {entry['bets']:,}, {entry['roi']:+.1%} [{entry['low']:+.1%}, {entry['high']:+.1%}]"


def render(results: dict, notes: dict) -> str:
    lines = [
        "# Layer scoring on settled live picks",
        "",
        f"Settled forward-ledger wagers frozen from {WINDOW_FROM}, one bet per wager at the best "
        "frozen price, flat 1u, intervals clustered on the game. Each layer is taken out alone "
        "and the same wagers repriced against the same prices and outcomes. **Contribution** is "
        "units with the layer minus units without it, over the wagers either version bets.",
        "",
        "| Layer | Pop. B with | Pop. B without | Contribution (B) | Staked with | Staked without | "
        "Contribution (staked) | Verdict |",
        "|:--|:--|:--|--:|:--|:--|--:|:--|",
    ]
    for layer, r in results.items():
        b, s = r["population_b"], r["staked"]
        lines.append(
            f"| {LAYER_LABELS.get(layer, layer)} | {_cell(b['with'])} | {_cell(b['without'])} | "
            f"{b['contribution_units']:+.1f}u ({b['changed_wagers']} changed; halves "
            f"{b['halves']['before']:+.1f} / {b['halves']['after']:+.1f}) | {_cell(s['with'])} | "
            f"{_cell(s['without'])} | {s['contribution_units']:+.1f}u | **{r['verdict']}** |"
        )
    lines += ["", "## Notes", "", "```", json.dumps(notes, indent=2, sort_keys=True, default=str), "```", "",
              "Every interval spans zero unless it says otherwise: **no demonstrated edge** either way. "
              "The rule (fixed before the run) cuts a layer only when taking it out improves both "
              "populations, population B by 2+ points over the wagers either version bets, in both "
              "halves of the window.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    parser.add_argument("--history-dir", type=Path, default=Path("dist/data/history"))
    parser.add_argument("--ledger", type=Path, nargs="*", default=[])
    parser.add_argument("--skip-props", action="store_true")
    args = parser.parse_args(argv)
    from nhl_betting_lab.providers.team_names import load_team_name_map

    ledger = load_ledger(args.ledger, args.processed_dir)
    if ledger.empty:
        print("::error::No forward ledger to score.", file=sys.stderr)
        return 1
    wagers = settled_wagers(ledger)
    team_names = load_team_name_map(processed_dir=args.processed_dir)
    results: dict = {}
    notes: dict = {"settled_wagers": int(len(wagers)), "window_from": WINDOW_FROM,
                   "last_night": str(wagers["snapshot_date"].max()) if len(wagers) else ""}

    team, notes["team"] = team_counterfactuals(wagers, args.history_dir, team_names)
    if not team.empty:
        for layer in TEAM_LAYERS:
            results[layer] = score(team, "model_probability", layer)
    if not args.skip_props:
        props, notes["props"] = props_counterfactuals(wagers, ledger, args.processed_dir, args.output_dir, team_names)
        if not props.empty:
            for layer in ("team_form_props", "position_matchup"):
                results[layer] = score(props, "p_full", f"p_{layer}")
    learned = self_learning_rows(wagers, ledger)
    if not learned.empty:
        results["self_learning"] = score(learned, "learned", "model_probability")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / REPORT_JSON).write_text(
        json.dumps({"results": results, "notes": notes}, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8")
    text = render(results, notes)
    (args.output_dir / REPORT_MD).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
