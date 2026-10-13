#!/usr/bin/env python3
"""Buy historical prices for the new markets, so their shadow models can be
backtested against real odds. Dry-run by default; the lab places no bet.

    # Free: what would a window cost? (no network, no credential)
    PYTHONPATH=src .venv/bin/python scripts/buy_new_market_prices.py \\
        --from 2024-10-08 --to 2026-04-16

    # Measure the real per-event charge on a spread-out sample, and project
    # the full window from it (spends up to the cap)
    PYTHONPATH=src .venv/bin/python scripts/buy_new_market_prices.py \\
        --from 2024-10-08 --to 2026-04-16 --probe-events 20 --live --credit-cap 4000

    # Buy the window (spends up to the cap)
    PYTHONPATH=src .venv/bin/python scripts/buy_new_market_prices.py \\
        --from 2024-10-08 --to 2026-04-16 --live --credit-cap 500000

Markets: the period markets (`h2h_p1..p3`, `h2h_3_way_p1..p3`,
`spreads_p1..p3`, `totals_p1..p3`), `player_power_play_points`,
`player_faceoffs_won`, `player_shots`, `player_goal_scorer_first` and
`player_goal_scorer_last` (`nhl_betting_lab.new_markets.prices.CORE_KEYS`).
`--with-alternates` also asks the alternate-ladder spellings, which have not
been seen served for NHL; a 422 for the list falls back once to the core
keys.

**What it costs.** The historical endpoint bills ten credits per market
RETURNED per region per event. The gate is the pessimistic estimate,
`10 x markets asked x regions` per event (340 at 17 keys and `us,us2`), and
the dry run quotes `10 x markets x regions x events`. The real charge is
lower whenever a market is not served, which is why `--probe-events` exists:
it buys a sample spread across the window and projects the full buy from the
MEASURED charges. Each day's listing is one more credit unless it is already
cached (the props buy's listings are shared, under `data/raw/historical_props`).

**The cap holds on measured spend** (#234): an event is asked only when the
worst case of everything asked fits, and when the measured spend plus the
dearest charge seen (never below the estimate) fits. A refused event is a
counted budget skip, not a stop, and any overspend is named and exits 2.
`--live` without a positive `--credit-cap` is refused.

**Where the prices go.** Every response is cached raw under `--prices-dir`
(default `data/raw/new_market_prices/historical`, never committed: `data/raw`
is ignored), and a cached response is never bought again. In CI the cache is
pulled from, and pushed to, the PRIVATE repository
(`scripts/private_new_market_store.py`) and lives on the runner only in its
temp directory. The provider's terms forbid redistributing their data as
files, and this repository is public, so no step uploads it.

Writes nothing the card, the snapshot or the forward ledger reads. A probe
writes `data/outputs/new_market_probe.md` and `.json`: counts and credits
only, no price.

Exit codes: 0 done (or a dry run); 1 nothing in scope; 2 a fault (a day that
could not be listed, an event that could not be bought, an overspend).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buy_historical_props import _events_in_window  # noqa: E402

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR, REGULAR_SEASON_GAME_TYPE  # noqa: E402
from nhl_betting_lab.data.build_datasets import load_team_games  # noqa: E402
from nhl_betting_lab.new_markets import prices  # noqa: E402
from nhl_betting_lab.providers.env_file import load_provider_env  # noqa: E402
from nhl_betting_lab.providers.odds_api import OddsApiProvider  # noqa: E402

PROBE_STEM = "new_market_probe"


def _parse_day(text: str) -> date:
    return date.fromisoformat(str(text))


def regular_season_games(team_games: pd.DataFrame, start: date, end: date) -> int:
    """Regular-season games in [start, end] per the local tables. Free."""
    if team_games.empty:
        return 0
    days = pd.to_datetime(team_games["date"], errors="coerce").dt.date
    keep = (days >= start) & (days <= end)
    if "game_type" in team_games:
        keep &= pd.to_numeric(team_games["game_type"], errors="coerce") == REGULAR_SEASON_GAME_TYPE
    return int(team_games.loc[keep, "game_id"].nunique())


def spread_sample(events: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """`count` events spread evenly across the window, first to last."""
    if count <= 0 or not events:
        return []
    ordered = sorted(events, key=lambda e: (e.get("commence_time", ""), e.get("event_id", "")))
    if count >= len(ordered):
        return ordered
    step = (len(ordered) - 1) / (count - 1) if count > 1 else 0
    picks = sorted({round(i * step) for i in range(count)})
    return [ordered[i] for i in picks]


def historical_request(provider: OddsApiProvider):
    def request(event, markets):
        return provider._get(  # noqa: SLF001 -- one adapter, one door
            f"{provider.base_url}/v4/historical/sports/{provider.sport_key}/events/{event['event_id']}/odds",
            provider._params(  # noqa: SLF001
                regions=provider.regions, markets=",".join(markets), date=str(event["snapshot"])
            ),
        )

    return request


def _wrap(event, payload, asked):
    out = dict(payload) if isinstance(payload, dict) else {"data": payload}
    out["requested"] = str(event["snapshot"])
    out["markets_asked"] = list(asked)
    return out


def render_probe(payload: dict[str, Any]) -> str:
    p = payload["projection"]
    lines = [
        "# New markets: what a historical buy costs",
        "",
        f"A probe of {payload['sampled']:,} events spread across {payload['from']} to "
        f"{payload['to']} ({payload['events_in_window']:,} events listed), "
        f"{payload['hours_before']:g} hours before face-off, asking {payload['markets_asked']} "
        f"markets in {payload['regions']} region(s). Credits are MEASURED "
        "(`x-requests-last`), not estimated. This page holds counts and credits only, never "
        "a price.",
        "",
        f"- Gate per event (the pessimistic estimate, 10 x markets x regions): "
        f"{payload['estimate_per_event']:,}.",
        f"- Listings charged: {payload['listing_cost']:,}; events charged: "
        f"{payload['credits_spent']:,} over {payload['bought']:,} bought "
        f"({payload['from_cache']:,} already cached, {payload['skipped_for_budget']:,} skipped for budget).",
    ]
    if p:
        lines += [
            f"- Measured per event: mean {p['mean_per_event']:.1f}, across the sample "
            f"{p['low'] / max(payload['events_in_window'], 1):.0f} to "
            f"{p['high'] / max(payload['events_in_window'], 1):.0f}.",
            f"- **Projected full buy of {payload['events_in_window']:,} events: about "
            f"{p['projected']:,.0f} credits** (sample range {p['low']:,.0f} to {p['high']:,.0f}), "
            f"against a worst case of {payload['worst_case']:,}. A forecast, not a bound: "
            "retention varies across a season, and the buy enforces its own cap as it spends.",
        ]
    else:
        lines.append("- Nothing was bought, so nothing is projected.")
    lines += [
        "",
        "## Which markets the provider kept",
        "",
        "Per key, over every response in the cache (the sample, and anything bought before): "
        "how many events asked for it, how many carried it, and how many books quoted it. A key asked and never seen cost nothing (billed per market returned).",
        "",
        "| Market | Events asked | Events seen | Books |",
        "|:--|--:|--:|--:|",
    ]
    for key, row in sorted(payload["markets_seen"].items()):
        lines.append(f"| `{key}` | {row['events_asked']:,} | {row['events_seen']:,} | {row['books']:,} |")
    if payload["errors"]:
        lines += ["", "## Errors", ""] + [f"- {e}" for e in payload["errors"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", required=True, help="First league day, YYYY-MM-DD.")
    parser.add_argument("--to", dest="end", required=True, help="Last league day, YYYY-MM-DD.")
    parser.add_argument("--hours-before", type=float, default=9.5,
                        help="Buy prices this many hours before face-off (default 9.5, the card's window).")
    parser.add_argument("--probe-events", type=int, default=0,
                        help="Buy only N events spread across the window and project the full buy.")
    parser.add_argument("--with-alternates", action="store_true",
                        help="Also ask the alternate-ladder keys (unverified for NHL).")
    parser.add_argument("--live", action="store_true", help="Actually buy. Without it nothing is asked.")
    parser.add_argument("--credit-cap", type=int, default=0,
                        help="Required with --live: the most this run may spend, listings included.")
    parser.add_argument("--prices-dir", type=Path, default=prices.DEFAULT_PRICES_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR,
                        help="Where the historical event listings are cached (shared with the props buy).")
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error("--live requires a positive --credit-cap; an uncapped purchase is not a thing this script does.")
    start, end = _parse_day(args.start), _parse_day(args.end)
    if end < start:
        parser.error("--to is before --from.")
    markets = list(prices.CORE_KEYS) + (list(prices.ALTERNATE_KEYS) if args.with_alternates else [])

    # Keyless: constructing it sends nothing; it carries the region count.
    provider = OddsApiProvider()
    per_event = prices.historical_estimate(len(markets), provider.region_count)

    if not args.live:
        games = regular_season_games(load_team_games(args.processed_dir), start, end)
        if games == 0:
            # No tables on disk: a regular season is 1,312 games, so say what
            # the window's seasons would hold rather than quote nothing.
            seasons = max(1, round((end - start).days / 365.25 + 0.5))
            games = 1_312 * seasons
            print(f"No regular-season games in the local tables; assuming {seasons} season(s) of 1,312 games.")
        events = min(args.probe_events, games) if args.probe_events else games
        print(
            f"Dry run, nothing asked. {start} to {end}: {games:,} regular-season game(s) in "
            f"scope; {len(markets)} market(s) x {provider.region_count} region(s) x 10 "
            f"credits = {per_event:,} per event at worst."
        )
        print(
            f"Worst case for {events:,} event(s): 10 x {len(markets)} x {provider.region_count} x "
            f"{events:,} = {per_event * events:,} credits, plus up to one credit per uncached "
            "day's listing. The real charge is per market RETURNED; --probe-events measures it."
        )
        return 0

    load_provider_env()
    provider = OddsApiProvider()
    total_days = (end - start).days + 1
    every = max(1, total_days // args.probe_events) if args.probe_events else 1
    events, listing_cost, listing_held, failed_days = _events_in_window(
        provider, start, end, hours_before=args.hours_before, raw_dir=args.raw_dir,
        credit_cap=args.credit_cap, every_n_days=every,
    )
    events_in_window = len(events)
    if args.probe_events:
        # One listing per `every` days thins the walk; the full window's
        # event count is scaled back up for the projection.
        events_in_window = len(events) * every
        events = spread_sample(events, args.probe_events)
    if not events:
        print("No events in scope." + (" Days could not be listed." if failed_days else ""), file=sys.stderr)
        return 2 if failed_days else 1
    budget = args.credit_cap - listing_held
    if budget <= 0:
        print(f"::error::The listings hold {listing_held} of the {args.credit_cap}-credit cap; nothing left to buy.")
        return 2
    run = prices.gated_buy(
        events,
        request=historical_request(provider),
        path_for=lambda e, m: prices.historical_path(args.prices_dir, e["event_id"], e["snapshot"], m),
        wrap=_wrap,
        markets=markets,
        per_event_estimate=per_event,
        credit_cap=budget,
        core_markets=list(prices.CORE_KEYS) if args.with_alternates else None,
    )
    print(f"Listings: {listing_cost} credit(s). Events: {run.summary_line()}")
    for error in run.errors:
        print(f"  {error}", file=sys.stderr)
    for day, cause in failed_days:
        print(f"::error::{day} could not be listed: {cause}")

    if args.probe_events:
        seen = prices.markets_seen(args.prices_dir, source="historical")
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "from": start.isoformat(),
            "to": end.isoformat(),
            "hours_before": args.hours_before,
            "regions": provider.region_count,
            "markets_asked": len(run_markets(run, markets)),
            "sampled": len(events),
            "events_in_window": events_in_window,
            "estimate_per_event": per_event,
            "worst_case": per_event * events_in_window,
            "listing_cost": listing_cost,
            "credits_spent": run.credits_spent,
            "bought": run.events_bought,
            "from_cache": run.events_from_cache,
            "skipped_for_budget": run.events_skipped_for_budget,
            "projection": prices.project_cost(run.charges, events_in_window),
            "markets_seen": seen["markets"],
            "errors": [e for e in run.errors if not e.startswith("Event ")]
            + ([f"{len(run.failed)} event(s) could not be bought."] if run.failed else []),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / f"{PROBE_STEM}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (args.output_dir / f"{PROBE_STEM}.md").write_text(render_probe(payload), encoding="utf-8")
        projection = payload["projection"]
        if projection:
            print(
                f"Projected full buy of {events_in_window:,} events: about {projection['projected']:,.0f} "
                f"credits (mean {projection['mean_per_event']:.1f} per event, measured)."
            )

    overspent = any(e.startswith("OVERSPENT") for e in run.errors)
    if failed_days or run.failed or overspent:
        return 2
    return 0


def run_markets(run: prices.PaidRun, markets: list[str]) -> list[str]:
    """The list actually asked: the core keys once a 422 forced the fallback."""
    return list(prices.CORE_KEYS) if run.fell_back_to_core else list(markets)


if __name__ == "__main__":
    raise SystemExit(main())
