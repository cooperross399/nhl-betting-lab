#!/usr/bin/env python3
"""Backtest the period, extra-prop and scorer shadow models against bought prices.

    PYTHONPATH=src .venv/bin/python scripts/run_new_market_backtest.py \\
        [--prices-dir DIR] [--hours-before 9.5] [--fetch]

Reads the historical responses `buy_new_market_prices.py` cached (by default
`data/raw/new_market_prices/historical`, which in CI is pulled from the
PRIVATE repository into the runner's temp directory), `team_games.csv`,
`player_logs.csv`, the team-name map and the cached NHL play-by-play
(`--fetch` downloads what is missing, free). With `shadow_team_games.csv`
beside the tables the period markets are priced on the xG ratings too.

Every price is joined to the shadow model's walk-forward opinion; the model
bets a selection when its edge clears the card's measurement bar (3.5% for
the period markets, 6% for the player markets), one bet per wager at the
best price, flat stake, and every interval is clustered on the game and
corrected across every figure measured (`nhl_betting_lab.new_markets.backtest`).

Writes `data/outputs/new_market_backtest.md` and `.json`: **aggregates only**
(counts, rates, intervals). No price, line, book or player of any wager is
written, because the bought prices are The Odds API's data and this
repository is public. Nothing on the card's path reads either file, and the
lab places no bet.

Exit codes: 0 measured; 1 nothing to measure (no prices in the window, no
tables, no play-by-play); 2 the team-name map resolves no event's two teams.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.config import MIN_EDGE, MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError, game_is_final
from nhl_betting_lab.new_markets import backtest, periods, player_extras, prices, scorers
from nhl_betting_lab.providers.team_names import load_team_name_map

REPORT_STEM = "new_market_backtest"
SHADOW_TEAM_TABLE = "shadow_team_games.csv"


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _pct(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{100 * value:+.1f}%"


def _interval(low: float | None, high: float | None) -> str:
    if low is None or high is None or not math.isfinite(low) or not math.isfinite(high):
        return "unbounded"
    return f"{100 * low:+.1f}% .. {100 * high:+.1f}%"


def render(payload: dict[str, Any]) -> str:
    w = payload["window"]
    j = payload["join"]
    lines = [
        "# New markets against bought prices",
        "",
        "Period markets, power-play points, faceoffs won, `player_shots`, and first and last "
        "goalscorer, each priced by its shadow model walk-forward "
        "(`nhl_betting_lab.new_markets`) and bet against the prices that were actually for "
        "sale. **Nothing here reaches the card**, the snapshot or the forward ledger; moving "
        "any market onto the card is Cooper's call, after this report.",
        "",
        "**How to read it.** One bet per wager at the best price any book quoted (best-of-N, "
        "which leans optimistic: the best price is the likeliest to be stale). Flat stake. A "
        f"selection is bet when the model's edge clears the card's measurement bar: "
        f"{100 * MIN_EDGE:.1f}% for the period markets, {100 * MIN_PROP_EDGE:.0f}% for the "
        "player markets. Intervals are 95%, clustered on the game, and corrected across "
        f"every figure in the table ({payload['looks']} figures). An interval that includes "
        "zero is **no demonstrated edge**.",
        "",
        "This page prints aggregates only. No price, line, book or player of any wager is "
        "written here: the prices are the provider's data and this repository is public.",
        "",
        "## Prices",
        "",
        f"- Window: {payload['hours_before']:g} hours before face-off, within "
        f"{backtest.WINDOW_TOLERANCE_HOURS:g} hour, strictly before it (median lead "
        f"{'n/a' if w['median_lead_hours'] is None else format(w['median_lead_hours'], '.2f')} h).",
        f"- Price rows on disk: {w['rows']:,}; in the window: {w['kept']:,}, over {w['events']:,} events.",
        f"- Events joined to an NHL game: {j['events'] - j['unresolved_teams'] - j['no_game']:,} of "
        f"{j['events']:,} ({j['unresolved_teams']:,} with a team the map does not resolve, "
        f"{j['no_game']:,} with no game in the tables).",
        f"- Wagers after the best-price collapse: {payload['wagers']:,}.",
        f"- Wagers with no opinion: {payload['no_opinion']:,} (a player the game's logs do not "
        f"name: {payload['no_player']:,}; before the model's minimum history: "
        f"{payload['not_priced']:,}; period games without a walk-forward rate or play-by-play: "
        f"{payload['period_unpriced']:,}). Never bet, never guessed.",
        "",
        "Wagers by market family (each family is every period or line it carries):",
        "",
        "| Family | Wagers | Priced |",
        "|:--|--:|--:|",
    ]
    for row in payload["by_family"]:
        lines.append(f"| {row['family']} | {row['wagers']:,} | {row['priced']:,} |")
    lines += [
        "",
        "## Result",
        "",
        "| Figure | Bar | Bets | Games | Wins | Pushes | Profit (u) | ROI | 95% interval | "
        "Corrected | Verdict | Every priced wager, no bar |",
        "|:--|--:|--:|--:|--:|--:|--:|--:|:--|:--|:--|:--|",
    ]
    for f in payload["figures"]:
        bar = "" if f["bar"] is None or not math.isfinite(f["bar"]) else f"{100 * f['bar']:.1f}%"
        lines.append(
            f"| {f['label']} | {bar} | {f['bets']:,} | {f['games']:,} | {f['wins']:,} | "
            f"{f['pushes']:,} | {f['profit'] if f['profit'] is not None else 0:+.1f} | {_pct(f['roi'] if f['bets'] else None)} | "
            f"{_interval(f['low'], f['high'])} | {_interval(f['adjusted_low'], f['adjusted_high'])} | "
            f"{f['verdict']} | {_pct(f['priced_roi'])} over {f['priced_wagers']:,} |"
        )
    if not payload["figures"]:
        lines.append("| nothing priced | | 0 | 0 | 0 | 0 | | | | | no bets | |")
    lines += [
        "",
        "The last column is every priced wager bet blind at its best price, the toll the "
        "market charges before any model opinion; it is context, not a figure tested.",
        "",
        "## What `player_shots` means",
        "",
    ]
    shots = payload["shots_definition"]
    if shots.get("wagers"):
        lines += [
            "Settled two ways above, because the key's definition is not confirmed. Over the "
            f"{shots['wagers']:,} `player_shots` wagers matched to a player-game: mean posted line "
            f"{shots['mean_line']:.2f} (median {shots['median_line']:.1f}); those players' mean "
            f"shot attempts {shots['mean_shot_attempts']:.2f}, unblocked attempts "
            f"{'n/a' if shots['mean_unblocked_attempts'] is None else format(shots['mean_unblocked_attempts'], '.2f')}, "
            f"shots on goal {shots['mean_shots_on_goal']:.2f}. A posted line sits near the median "
            "of the count it settles on; a line nearest shots on goal would mean neither reading "
            "here is the right one.",
        ]
    else:
        lines.append("No `player_shots` price was matched to a player-game.")
    lines += [
        "",
        "## What this cannot say",
        "",
        "- Settlement is this lab's reading of each market (a tied period pushes the two-way, "
        "a whole line that lands exactly pushes, scorer markets count overtime and never the "
        "shootout). A book's own rule can differ; check it before reading any figure as that "
        "book's market.",
        "- The scorer models list every dressed skater, known at warm-ups; the price was taken "
        "hours earlier. A book voids a player who does not dress, which the join honours by "
        "not betting a player the game's logs do not name.",
        "- Only the bought window is measured. Nothing here is the closing price.",
        "",
    ]
    return "\n".join(lines)


def _payloads(ids: list[int], raw_dir: Path, fetch: bool, failures: list[int]) -> Iterator[dict]:
    for number, gid in enumerate(ids, 1):
        payload = None
        if fetch:
            try:
                payload = player_extras.fetch_play_by_play(gid, raw_dir=raw_dir).payload
            except NhlApiError as exc:
                failures.append(gid)
                print(f"Play-by-play {gid}: {exc}", file=sys.stderr)
        else:
            payload = player_extras.read_cached_play_by_play(gid, raw_dir=raw_dir)
        if isinstance(payload, dict) and game_is_final(payload):
            yield payload
        if number % 500 == 0:
            print(f"Play-by-play: {number} of {len(ids)} games")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prices-dir", type=Path, default=prices.DEFAULT_PRICES_DIR,
                        help="The bought responses (the folder holding historical/).")
    parser.add_argument("--hours-before", type=float, default=9.5,
                        help="The window measured, in hours before face-off (default 9.5, the card's).")
    parser.add_argument("--fetch", action="store_true", help="Fetch uncached play-by-play (free NHL API).")
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    args = parser.parse_args(argv)

    raw_prices = prices.rows_from_cache(args.prices_dir, source="historical")
    windowed, window = backtest.select_window(raw_prices, args.hours_before)
    if windowed.empty:
        print(
            f"No bought price sits {args.hours_before:g} hours before face-off under "
            f"{args.prices_dir} ({window['rows']:,} row(s) on disk). Nothing measured.",
            file=sys.stderr,
        )
        return 1
    team_games = load_team_games(args.processed_dir)
    logs = load_player_logs(args.processed_dir)
    if team_games.empty or logs.empty:
        print("No team games or player logs on disk; build the datasets first.", file=sys.stderr)
        return 1
    team_map = load_team_name_map(processed_dir=args.processed_dir, raw_dir=args.raw_dir)
    joined, join = backtest.attach_games(windowed, team_games, team_map)
    if joined.empty and join["unresolved_teams"] == join["events"]:
        print(
            "::error::The team-name map resolves the two teams of none of the "
            f"{join['events']:,} priced events; refusing to measure on it.",
            file=sys.stderr,
        )
        return 2
    if joined.empty:
        print("No priced event matched a game in the tables. Nothing measured.", file=sys.stderr)
        return 1
    bets = backtest.wagers(joined)

    final = team_games.dropna(subset=["home_goals", "away_goals"])
    ids = sorted({int(g) for g in pd.to_numeric(final["game_id"], errors="coerce").dropna() if int(g) > 0})
    failures: list[int] = []
    goal_rows: list[dict] = []
    orders: dict[int, scorers.GoalOrder] = {}

    def stream() -> Iterator[dict]:
        for payload in _payloads(ids, args.raw_dir, args.fetch, failures):
            goals = periods.period_goals(payload)
            if goals is not None:
                goal_rows.append(goals.row())
            order = scorers.parse_goal_order(payload)
            gid = int(payload.get("id", 0) or 0)
            if gid:
                orders[gid] = order
            yield payload

    counts, _ = player_extras.build_counts(stream())
    if not goal_rows:
        print("No play-by-play on disk; run with --fetch.", file=sys.stderr)
        return 1
    period_table = pd.DataFrame(goal_rows)
    xg_path = args.processed_dir / SHADOW_TEAM_TABLE
    xg_metrics = pd.read_csv(xg_path) if xg_path.is_file() else None
    rates = periods.walk_forward_rates(team_games, period_table, xg_metrics=xg_metrics)
    period_priced = backtest.price_periods(bets, rates, period_table)

    table, _ = player_extras.attach_ice_time(counts, logs) if not counts.empty else (pd.DataFrame(), {})
    predictions = player_extras.walk_forward(table) if not table.empty else pd.DataFrame()
    count_priced, count_misses = backtest.price_counts(bets, predictions, logs)

    selections = scorers.measure(team_games, logs, orders, selections=True).selections
    scorer_priced, scorer_misses = backtest.price_scorers(bets, selections, logs)

    priced = pd.concat([f for f in (period_priced, count_priced, scorer_priced) if not f.empty], ignore_index=True) \
        if any(not f.empty for f in (period_priced, count_priced, scorer_priced)) else pd.DataFrame()
    scored = backtest.score(priced) if not priced.empty else priced
    figures = backtest.measure(scored) if not scored.empty else []

    period_bets = bets[bets["family"].isin(backtest.PERIOD_FAMILIES)]
    period_seen = (
        set(zip(period_priced["game_id"], period_priced["family"], period_priced["period"],
                period_priced["selection"], period_priced["line_key"]))
        if not period_priced.empty else set()
    )
    period_unpriced = sum(
        1 for row in period_bets.itertuples()
        if (row.game_id, row.family, row.period, row.selection, row.line_key) not in period_seen
    )
    by_family = []
    for family, frame in bets.groupby("family", sort=True):
        priced_n = 0
        if not scored.empty:
            priced_n = int(
                scored[scored["family"] == family].drop_duplicates(backtest.WAGER_KEY).shape[0]
            )
        by_family.append({"family": str(family), "wagers": int(len(frame)), "priced": priced_n})
    no_player = count_misses["no_player"] + scorer_misses["no_player"]
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hours_before": args.hours_before,
        "window": window,
        "join": join,
        "wagers": int(len(bets)),
        "no_player": int(no_player),
        "not_priced": int(count_misses["not_priced"]),
        "period_unpriced": int(period_unpriced),
        "no_opinion": int(no_player + count_misses["not_priced"] + period_unpriced),
        "by_family": by_family,
        "looks": len(figures),
        "bars": {"period": MIN_EDGE, "player": MIN_PROP_EDGE},
        "figures": [f.as_dict() for f in figures],
        "shots_definition": backtest.shots_definition_check(count_priced),
        "play_by_play_failures": len(failures),
        "period_models": [m for m in backtest.PERIOD_MODELS if m != "xg" or xg_metrics is not None],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{REPORT_STEM}.json").write_text(
        json.dumps(_clean(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / f"{REPORT_STEM}.md").write_text(render(_clean(payload)), encoding="utf-8")
    for f in figures:
        print(f"  {f.label}: {f.bets} bet(s), ROI {_pct(f.roi if f.bets else None)}, {f.verdict}")
    print(f"Wrote {args.output_dir / (REPORT_STEM + '.md')}")
    return 0 if figures else 1


if __name__ == "__main__":
    raise SystemExit(main())
