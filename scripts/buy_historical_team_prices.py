#!/usr/bin/env python3
"""Buy historical team-market prices, so the team models can be measured.

Far cheaper than props. Props are per event — ten credits per market per event
— while team markets come from the bulk historical endpoint, which returns
every game on the board at one instant for `10 x markets x regions`. Thirty
credits buys a whole slate, whether that slate is four games or fourteen.

That difference is why the team markets went unmeasured while the props were
bought twice: the props were expensive enough to think about and the team
markets were cheap enough to forget.

    # Free: state the cost and stop.
    PYTHONPATH=src .venv/bin/python scripts/buy_historical_team_prices.py \
        --from 2024-10-08 --to 2026-04-15

    # Buy, capped.
    PYTHONPATH=src .venv/bin/python scripts/buy_historical_team_prices.py \
        --from 2024-10-08 --to 2026-04-15 --live --credit-cap 2000
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.providers import historical_team_prices as team
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


HISTORICAL_TEAM_PRICES_FILENAME = "historical_team_prices.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--every-n-days", type=int, default=14)
    parser.add_argument(
        "--snapshot-hour",
        type=int,
        default=23,
        help=(
            "UTC hour to price at. 23:00 UTC is about an hour before a 19:10 "
            "Eastern face-off, which is when a card would be built."
        ),
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credit-cap", type=int, default=0)
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error("--live requires a positive --credit-cap.")

    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    except ValueError:
        parser.error("--from and --to must be ISO dates.")

    snapshots: list[str] = []
    cursor = start
    step = max(1, args.every_n_days)
    while cursor <= end:
        snapshots.append(f"{cursor.isoformat()}T{args.snapshot_hour:02d}:00:00Z")
        cursor += timedelta(days=step)

    markets = list(team.BULK_MARKETS)
    print(team.cost_note(snapshots=len(snapshots), markets=len(markets)))
    if not args.live:
        print("Dry run: nothing was bought and no credit was spent.")
        return 0

    load_provider_env()
    try:
        provider = OddsApiProvider()
    except ProviderError as exc:
        print(f"Provider misconfigured: {exc}", file=sys.stderr)
        return 2

    buy = team.buy_team_prices(
        provider,
        snapshots=snapshots,
        markets=markets,
        credit_cap=args.credit_cap,
        raw_dir=args.raw_dir,
    )
    print(buy.summary_line())
    for error in buy.errors[:10]:
        print(f"  {error}", file=sys.stderr)

    from pathlib import Path

    processed = Path(args.processed_dir)
    processed.mkdir(parents=True, exist_ok=True)
    target = processed / HISTORICAL_TEAM_PRICES_FILENAME
    frame = pd.DataFrame(buy.rows)
    if target.is_file() and not frame.empty:
        existing = pd.read_csv(target)
        frame = pd.concat([existing, frame], ignore_index=True).drop_duplicates()
    frame.to_csv(target, index=False, lineterminator="\n")
    print(f"{len(frame):,} team price rows now in {target}.")
    print(
        "Bought prices only. No bet was placed, no policy was edited, and no "
        "market was allowlisted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
