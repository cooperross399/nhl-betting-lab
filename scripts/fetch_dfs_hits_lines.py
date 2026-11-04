#!/usr/bin/env python3
"""Tonight's PrizePicks hits lines, for the card's unstaked "Hits lines" list.

From the 2026-10-27 morning card onward no sportsbook the lab can reach
quoted NHL hits (theScore Bet had been the only one). The Hits Source Probe
(run 41734366995, 2026-11-03) found one source still posting them: PrizePicks,
in the provider's `us_dfs` region. PrizePicks is a pick'em app, so what it
posts is a line, not sportsbook odds. Cooper chose "Add as lines only"
(2026-11-04): the card shows each PrizePicks hits line with the model's
chance of the over and the under, and stakes nothing, until a sportsbook
posts hits again.

This writes `data/staging/dfs_hits_lines.csv`. The card's priced inputs are
read from two named files only (`run_gameday_card._staged_prices`), so these
rows can never become a price the card stakes, freezes or records: PrizePicks
reaches no best bet, lean, snapshot, forward-ledger row or allowlist. Only
`nhl_betting_lab.dfs_hits_lines` reads this file.

**This spends credits**, one per event that returns hits (the live per-event
endpoint bills per market returned per region, and only `player_hits` in
`us_dfs` is asked). Nothing is asked without `--live`, and `--credit-cap` is
mandatory and enforced on the provider's measured running total.

    PYTHONPATH=src .venv/bin/python scripts/fetch_dfs_hits_lines.py --credit-cap 20
    PYTHONPATH=src .venv/bin/python scripts/fetch_dfs_hits_lines.py --live --credit-cap 20

Exit codes: 0 written (an empty file when nobody posted), 2 the fetch
failed, 3 no game on today's slate. It places no bet, edits no policy, writes
no receipt and adds no market to the allowlist.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from nhl_betting_lab.config import STAGING_DIR
from nhl_betting_lab.dfs_hits_lines import DFS_REGION, LINES_FILENAME, MARKET
from nhl_betting_lab.providers.env_file import load_provider_env, redact
from nhl_betting_lab.providers.odds_api import (
    EmptySlateError,
    OddsApiProvider,
    ProviderError,
    write_staging,
)
from nhl_betting_lab.season import LEAGUE_TIMEZONE

PROVIDER_MARKET = "player_hits"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credit-cap", type=int, required=True)
    parser.add_argument("--staging-dir", type=Path, default=STAGING_DIR)
    args = parser.parse_args(argv)
    if args.credit_cap <= 0:
        parser.error("--credit-cap must be a positive number of credits.")

    now = datetime.now(timezone.utc)
    day = now.astimezone(LEAGUE_TIMEZONE).date().isoformat()
    print(
        f"Plan: {PROVIDER_MARKET} in region {DFS_REGION} for {day}'s games, "
        f"one credit per game that returns it, cap {args.credit_cap}."
    )
    if not args.live:
        print("Not asked: pass --live to spend credits.")
        return 0

    load_provider_env()
    provider = OddsApiProvider(regions=DFS_REGION)
    try:
        result = provider.fetch_player_props(
            markets=[PROVIDER_MARKET],
            credit_cap=args.credit_cap,
            league_days=[day],
            now=now,
        )
    except EmptySlateError as exc:
        print(f"No game on today's slate: {exc}")
        return 3
    except ProviderError as exc:
        print(redact(f"::warning::The PrizePicks hits fetch failed: {exc}"))
        return 2

    rows = [row for row in result.rows if str(row.get("market")) == MARKET]
    target = write_staging(
        rows, filename=LINES_FILENAME, staging_dir=args.staging_dir, overwrite=True
    )
    games = {(r.get("home_team"), r.get("away_team")) for r in rows}
    print(
        f"PrizePicks hits: {len(rows)} row(s) over {len(games)} game(s), "
        f"{result.credits_spent} credit(s) spent, written to {target}."
    )
    for line in result.errors:
        print(redact(f"::warning::{line}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
