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

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.historical_props import list_historical_events
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

    One listing per day at 12:00 UTC, which is before every NHL puck drop, so
    the day's whole slate is on it. Each listing is documented at one credit
    and is free when it finds nothing.

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
            if when.date() != cursor:
                # The listing covers a window, not a day. Keep only the games
                # actually played on the day being sampled, so `every_n_days`
                # means what it says.
                continue
            seen.add(event_id)
            when_utc = when.astimezone(timezone.utc)
            events.append(
                {
                    "event_id": event_id,
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
        help="Buy one event only, to find out which markets are retained.",
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
    markets = [market.provider_key for market in PROP_MARKETS]

    events: list[dict[str, str]] = []
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
            provider = OddsApiProvider()
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
                "A probe needs one event to look at. Give --from/--to over a "
                "day the season was being played.",
                file=sys.stderr,
            )
            return 2
        events = events[:1]

    print(
        hist.cost_note(events=len(events), markets=len(markets))
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

    provider = OddsApiProvider()
    outputs = Path(args.output_dir)
    outputs.mkdir(parents=True, exist_ok=True)

    if args.probe:
        probe = hist.probe_retention(
            provider,
            event_id=events[0]["event_id"],
            snapshot=events[0]["snapshot"],
            markets=markets,
            raw_dir=Path(args.raw_dir),
        )
        print(probe.summary_line())
        table = hist.retention_table([probe])
        print(table)
        unmeasurable = {
            market.key: (
                "The provider did not return this market in the historical "
                f"snapshot probed at {probe.snapshot}, so it cannot be "
                "measured against real prices."
            )
            for market in PROP_MARKETS
            if market.provider_key in probe.markets_missing
        }
        (outputs / RETENTION_FILENAME).write_text(
            json.dumps(
                {
                    "probed_at": probe.snapshot,
                    "event_id": probe.event_id,
                    "markets_returned": list(probe.markets_returned),
                    "markets_missing": list(probe.markets_missing),
                    "books_returned": list(probe.books_returned),
                    "credits_spent": probe.credits_spent,
                    "table": table,
                    "unmeasurable": unmeasurable,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
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
        # add to rather than replace. Deduplicated on the whole row so a
        # re-run is idempotent.
        existing = pd.read_csv(target)
        frame = pd.concat([existing, frame], ignore_index=True).drop_duplicates()
    frame.to_csv(target, index=False, lineterminator="\n")
    print(f"{len(frame):,} historical price rows now in {target}.")
    print(
        "Bought prices only. No bet was placed, no policy was edited, and no "
        "market was allowlisted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
