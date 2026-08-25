#!/usr/bin/env python3
"""Buy historical prop prices so the model can be measured against them.

**This spends credits, and it is the most expensive thing in the repository.**
The historical endpoints bill ten credits per market per event — an order of
magnitude above the live per-event rate. Six markets across one twelve-game
night is 720 credits.

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
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


HISTORICAL_PRICES_FILENAME = "historical_prop_prices.csv"
RETENTION_FILENAME = "historical_props_retention.json"


def _events_in_window(
    provider: OddsApiProvider, start: date, end: date, *, hours_before: float
) -> list[dict[str, str]]:
    """Historical event ids for a date window, from the free events endpoint.

    The historical events list is itself a paid endpoint on some plans, so this
    uses the live events list where it can and otherwise expects the caller to
    supply ids. When the window is in the past and the live list cannot answer,
    the run says so rather than silently buying nothing.
    """
    events: list[dict[str, str]] = []
    for raw in provider.list_events():
        commence = str(raw.get("commence_time", "")).strip()
        try:
            when = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except ValueError:
            continue
        if not (start <= when.date() <= end):
            continue
        snapshot = (when - timedelta(hours=hours_before)).astimezone(timezone.utc)
        events.append(
            {
                "event_id": str(raw.get("id", "")),
                "snapshot": snapshot.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "commence_time": commence,
                "home_team": str(raw.get("home_team", "")),
                "away_team": str(raw.get("away_team", "")),
            }
        )
    return events


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
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error(
            "--live requires a positive --credit-cap. Historical prices bill "
            "ten credits per market per event; an uncapped purchase is not a "
            "thing this script will do."
        )

    load_provider_env()
    markets = [market.provider_key for market in PROP_MARKETS]

    events: list[dict[str, str]] = []
    if args.events_file:
        events = json.loads(Path(args.events_file).read_text(encoding="utf-8"))
    elif args.start and args.end:
        try:
            provider = OddsApiProvider()
            events = _events_in_window(
                provider,
                date.fromisoformat(args.start),
                date.fromisoformat(args.end),
                hours_before=args.hours_before,
            )
        except ProviderError as exc:
            print(f"Could not list events: {exc}", file=sys.stderr)
            return 2
    elif not args.probe:
        parser.error("Give --from/--to, or --events-file, or --probe.")

    if args.probe:
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
        credit_cap=args.credit_cap,
        raw_dir=Path(args.raw_dir),
    )
    print(buy.summary_line())
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
