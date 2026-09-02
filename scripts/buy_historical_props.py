#!/usr/bin/env python3
"""Buy historical prop prices so the model can be measured against them.

**This spends credits, and it is the most expensive thing in the repository.**
The provider's documentation is ambiguous about what the per-event
historical endpoint costs: it documents ten credits per market for the bulk
historical endpoint, and either one-per-market-returned or nothing at all for
the per-event one, depending on which part of the guide you read. So the real
cost is read from `x-requests-last` on every response, and the cap is enforced
against the pessimistic ten-per-market reading — a cap that can only be
over-respected.

So it does nothing without `--live`, it takes a mandatory `--credit-cap`, and
the cap is enforced before each request rather than checked afterwards. A
probe that quietly became a full-season purchase is exactly the accident these
two flags exist to make impossible.

    # Free: print what a purchase would cost and stop.
    PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
        --from 2025-01-05 --to 2025-01-05

    # One event, one snapshot: does the provider retain these markets at all?
    PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
        --probe --live --credit-cap 60

    # A real purchase, capped.
    PYTHONPATH=src .venv/bin/python scripts/buy_historical_props.py \
        --from 2025-01-05 --to 2025-01-12 --live --credit-cap 2000

## Which snapshot to buy

`--hours-before` picks how long before puck drop to price at, defaulting to
four hours — roughly when the Gameday Refresh card is built. Buying a closing
snapshot would measure the model against a line it could never have bet, which
would make every number optimistic in a way no caveat can undo.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.stores import dedupe_prices, read_store

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.historical_props import list_historical_events
from nhl_betting_lab.season import game_date
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


HISTORICAL_PRICES_FILENAME = "historical_prop_prices.csv"
RETENTION_FILENAME = "historical_props_retention.json"


def _events_in_window(
    provider: OddsApiProvider,
    start: date,
    end: date,
    *,
    hours_before: float,
    raw_dir: Path,
    every_n_days: int = 1,
) -> tuple[list[dict[str, str]], int]:
    """Event ids and per-event snapshots for a past window.

    This walks the **historical** events endpoint, one listing per day. The
    live events endpoint only knows about upcoming games, so pointing it at a
    past window returns nothing — which looks exactly like "the provider has
    no data for that window" and is not. That bug would have made a purchase
    run buy zero events and report success.

    One listing per day at 12:00 UTC, and everything on the board for the
    following twenty-four hours is that day's slate.

    That window is the fix for a real and badly-shaped bug. Keeping only games
    whose `commence_time` fell on the *same UTC date* discarded most of every
    slate, because a North American evening is the next day in UTC: on
    2026-01-10 the provider listed fourteen games and the filter kept four —
    and the four it kept were the afternoon games. Sampling would have been
    restricted to matinees and national-TV windows, which is a systematically
    different set of fixtures, silently.

    `every_n_days` thins the window into a stratified sample rather than
    buying consecutive days. Consecutive days share injuries, road trips and
    goalie rotations, so a hundred consecutive events carry a good deal less
    independent information than a hundred spread across a season.
    """
    events: list[dict[str, str]] = []
    listing_cost = 0
    seen: set[str] = set()
    cursor = start
    while cursor <= end:
        snapshot = f"{cursor.isoformat()}T12:00:00Z"
        window_start = datetime.fromisoformat(f"{cursor.isoformat()}T12:00:00+00:00")
        window_end = window_start + timedelta(days=1)
        try:
            found, cost, _ = list_historical_events(
                provider, snapshot=snapshot, raw_dir=raw_dir
            )
        except ProviderError as exc:
            print(f"  {cursor}: {exc}", file=sys.stderr)
            cursor += timedelta(days=every_n_days)
            continue
        listing_cost += cost
        for raw in found:
            commence = str(raw.get("commence_time", "")).strip()
            event_id = str(raw.get("id", "")).strip()
            if not event_id or event_id in seen:
                continue
            try:
                when = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            except ValueError:
                continue
            if not (window_start <= when.astimezone(timezone.utc) < window_end):
                # The listing can carry games beyond this slate. Bounding it
                # to the twenty-four hours after the snapshot keeps exactly
                # one night's fixtures, so `every_n_days` means what it says.
                continue
            seen.add(event_id)
            when_utc = when.astimezone(timezone.utc)
            events.append(
                {
                    "event_id": event_id,
                    "game_date": game_date(commence),
                    "snapshot": (
                        when_utc - timedelta(hours=hours_before)
                    ).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "commence_time": commence,
                    "home_team": str(raw.get("home_team", "")),
                    "away_team": str(raw.get("away_team", "")),
                }
            )
        cursor += timedelta(days=every_n_days)
    return events, listing_cost


def _write_retention_from_cache(
    *, raw_dir: Path, output_dir: Path, markets: list[str]
) -> int:
    """Rebuild the retention record from the responses already on disk.

    `historical_props_retention.json` was written once by a paid probe and
    then never refreshed, so a verdict reached over 256 events under one
    region outlived the purchases that contradicted it: `player_hits` stood
    as "cannot be measured against past prices" while the store held 16,048
    hits rows and the backtest settled 5,021 wagers on them. The retention
    record is derived data, like the price CSVs, and this is the door that
    derives it.
    """
    probes = hist.retention_from_cache(raw_dir=raw_dir, markets=markets)
    if not probes:
        print(
            f"No cached response in {raw_dir} asked for exactly these "
            f"{len(markets)} market(s), so retention cannot be rebuilt from "
            "the cache. The file is left as it is rather than replaced with "
            "an emptier answer than the one it holds.",
            file=sys.stderr,
        )
        return 2
    table = hist.retention_table(probes)
    print(table)
    provider_to_key = {market.provider_key: market.key for market in PROP_MARKETS}
    unmeasurable = {
        provider_to_key.get(provider_key, provider_key): reason
        for provider_key, reason in hist.unmeasurable_markets(probes).items()
    }
    snapshots = sorted({probe.snapshot for probe in probes if probe.snapshot})
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / RETENTION_FILENAME).write_text(
        json.dumps(
            {
                "events_probed": len(probes),
                "source": (
                    "Derived from the raw response cache, not from a paid "
                    "probe. Every response that requested exactly this market "
                    "list was read."
                ),
                "note": (
                    f"{len(probes)} cached response(s) covering "
                    f"{len({probe.event_id for probe in probes})} event(s). "
                    "This replaces a 256-event probe whose verdict of "
                    "'player_hits not offered in any of 256 events' was true "
                    "of what it saw and false about the provider: it asked "
                    "one region, and both books that quote hits are in the "
                    "second."
                ),
                "snapshot_range": [snapshots[0], snapshots[-1]] if snapshots else [],
                "markets_seen": sorted(
                    {market for probe in probes for market in probe.markets_returned}
                ),
                "credits_spent": 0,
                "table": table,
                "unmeasurable": unmeasurable,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"Retention rebuilt from {len(probes):,} cached response(s) for 0 "
        f"credits, written to {output_dir / RETENTION_FILENAME}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", default="", help="ISO start date.")
    parser.add_argument("--to", dest="end", default="", help="ISO end date.")
    parser.add_argument(
        "--events-file",
        default="",
        help=(
            "JSON list of {event_id, snapshot} to buy, for a window the live "
            "events endpoint can no longer describe."
        ),
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "Sample a few events to find out which markets are retained. "
            "Deliberately more than one: a single event is a book's night, "
            "not the provider's retention policy."
        ),
    )
    parser.add_argument(
        "--probe-events",
        type=int,
        default=hist.MINIMUM_PROBES_FOR_ABSENCE,
        help=(
            "How many events to probe. Below the floor, a market that does "
            "not appear is reported as unseen rather than as unmeasurable."
        ),
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help=(
            "Rebuild the retention record from responses already bought, "
            "instead of paying for a fresh probe. Reads files, touches no "
            "network, spends nothing — and sees every event ever bought "
            "rather than the handful a probe can afford."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually spend credits. Without this, nothing is bought.",
    )
    parser.add_argument(
        "--credit-cap",
        type=int,
        default=0,
        help="Hard cap. Required with --live; the run stops rather than exceed it.",
    )
    parser.add_argument(
        "--markets",
        nargs="*",
        default=None,
        help=(
            "Provider market keys to buy. Defaults to every prop this lab "
            "prices. Naming a subset is how a market added later is filled in "
            "without re-buying the ones already on disk — at ten credits per "
            "market per event, re-buying six to add a seventh costs seven "
            "times what it needs to."
        ),
    )
    parser.add_argument("--hours-before", type=float, default=4.0)
    parser.add_argument(
        "--every-n-days",
        type=int,
        default=1,
        help=(
            "Sample every Nth day rather than every day. Consecutive days "
            "share injuries, road trips and goalie rotations, so a spread "
            "sample carries more independent information per credit."
        ),
    )
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error(
            "--live requires a positive --credit-cap. Historical prices bill "
            "up to ten credits per market per event; an uncapped purchase is not a "
            "thing this script will do."
        )

    load_provider_env()
    markets = (
        list(args.markets)
        if args.markets
        else [market.provider_key for market in PROP_MARKETS]
    )
    known = {market.provider_key for market in PROP_MARKETS}
    unknown = sorted(set(markets) - known)
    if unknown:
        parser.error(
            f"{unknown} are not markets this lab prices, so nothing could "
            "settle them. Add them to markets.py first."
        )

    if args.from_cache:
        # Deliberately before the provider exists, so this path cannot reach
        # the network even by accident. A retention verdict is only as wide as
        # the query behind it, and the widest query this lab has already paid
        # for is everything in the cache.
        return _write_retention_from_cache(
            raw_dir=Path(args.raw_dir),
            output_dir=Path(args.output_dir),
            markets=markets,
        )

    events: list[dict[str, str]] = []
    # Built once, up front, and keyless: constructing it sends nothing. The
    # dry-run cost quote needs its region count, and the region count is
    # exactly what the old quote left out.
    provider = OddsApiProvider()
    listing_cost = 0
    if args.events_file:
        events = json.loads(Path(args.events_file).read_text(encoding="utf-8"))
    elif args.start and args.end:
        if not args.live:
            print(
                "Listing past events is itself a paid call (one credit a day, "
                "free when it finds nothing), so a dry run does not make it. "
                "Re-run with --live and a --credit-cap to see the real slate."
            )
            return 0
        try:
            events, listing_cost = _events_in_window(
                provider,
                date.fromisoformat(args.start),
                date.fromisoformat(args.end),
                hours_before=args.hours_before,
                raw_dir=Path(args.raw_dir),
                every_n_days=max(1, args.every_n_days),
            )
        except ProviderError as exc:
            print(f"Could not list events: {exc}", file=sys.stderr)
            return 2
        print(
            f"{len(events)} event(s) found in the window; the listings cost "
            f"{listing_cost} credit(s)."
        )
    elif not args.probe:
        parser.error("Give --from/--to, or --events-file, or --probe.")

    if args.probe:
        if not events:
            print(
                "A probe needs events to look at. Give --from/--to over days "
                "the season was being played.",
                file=sys.stderr,
            )
            return 2
        # Spread across the window rather than taking the first few, so the
        # probe does not describe one night's book coverage.
        step = max(1, len(events) // max(1, args.probe_events))
        events = events[::step][: args.probe_events]

    print(
        hist.cost_note(
            events=len(events),
            markets=len(markets),
            regions=provider.region_count,
        )
        if events
        else "No events in scope."
    )
    if not args.live:
        print(
            "Dry run: nothing was bought and no credit was spent. Re-run with "
            "--live and a --credit-cap to buy."
        )
        return 0
    if not events:
        return 0

    outputs = Path(args.output_dir)
    outputs.mkdir(parents=True, exist_ok=True)

    if args.probe:
        probes = []
        for event in events:
            probe = hist.probe_retention(
                provider,
                event_id=event["event_id"],
                snapshot=event["snapshot"],
                markets=markets,
                raw_dir=Path(args.raw_dir),
            )
            print(probe.summary_line())
            probes.append(probe)
        table = hist.retention_table(probes)
        print(table)
        provider_to_key = {
            market.provider_key: market.key for market in PROP_MARKETS
        }
        unmeasurable = {
            provider_to_key.get(provider_key, provider_key): reason
            for provider_key, reason in hist.unmeasurable_markets(probes).items()
        }
        spent = sum(probe.credits_spent for probe in probes) + listing_cost
        (outputs / RETENTION_FILENAME).write_text(
            json.dumps(
                {
                    "events_probed": len(probes),
                    "snapshots": [probe.snapshot for probe in probes],
                    "markets_seen": sorted(
                        {
                            market
                            for probe in probes
                            for market in probe.markets_returned
                        }
                    ),
                    "credits_spent": spent,
                    "table": table,
                    "unmeasurable": unmeasurable,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Total spend this run: {spent} credit(s).")
        print(f"Retention written to {outputs / RETENTION_FILENAME}.")
        return 0

    buy = hist.buy_historical_props(
        provider,
        events=events,
        markets=markets,
        credit_cap=max(0, args.credit_cap - listing_cost),
        raw_dir=Path(args.raw_dir),
    )
    print(buy.summary_line())
    print(
        f"Total spend this run: {buy.credits_spent + listing_cost} credit(s), "
        f"against a cap of {args.credit_cap}."
    )
    for error in buy.errors[:10]:
        print(f"  {error}", file=sys.stderr)

    processed = Path(args.processed_dir)
    processed.mkdir(parents=True, exist_ok=True)
    target = processed / HISTORICAL_PRICES_FILENAME
    frame = pd.DataFrame(buy.rows)
    if target.is_file() and not frame.empty:
        # Historical prices never change, so an existing file is evidence to
        # add to rather than replace. Deduplicated on the quote AND the
        # snapshot window, so a re-run of the same window is idempotent and a
        # purchase of a second window is added rather than substituted. The
        # window used to be left out: buying 9.5 hours into a store already
        # holding 4.0 overwrote 1,126,739 of its 1,259,312 rows in silence.
        existing = read_store(target, for_append=True)
        frame = dedupe_prices(
            pd.concat([existing, frame], ignore_index=True)
        )
    if frame.empty and target.is_file():
        # A run that bought nothing must never replace a file that holds
        # something. This exact write once emptied eleven thousand credits of
        # accumulated prices; the raw cache made it recoverable, and this
        # guard makes it not happen.
        print(
            f"Nothing was bought, so {target.name} is left as it was "
            f"({sum(1 for _ in open(target)) - 1:,} rows)."
        )
    else:
        frame.to_csv(target, index=False, lineterminator="\n")
    print(f"{len(frame):,} historical price rows now in {target}.")
    print(
        "Bought prices only. No bet was placed, no policy was edited, and no "
        "market was allowlisted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
