#!/usr/bin/env python3
"""Capture tonight's prices for the new markets, under a cap. The lab places no bet.

    PYTHONPATH=src .venv/bin/python scripts/capture_new_market_prices.py --live --credit-cap 640

Asks the live per-event odds endpoint, once per game, for the period markets,
`player_power_play_points`, `player_faceoffs_won`, `player_shots` and first
and last goalscorer (`nhl_betting_lab.new_markets.prices.CORE_KEYS`), for
tonight's regular-season games that have not started. The board comes from
the free events listing; games on other league days, games already under way
(or whose start cannot be confirmed: the puck-drop rule) and exhibitions (the
card's preseason screen, with its abstentions) are dropped before the cap is
spent, so a cap never buys a game no model can use.

**Cost.** Live per-event markets bill one credit per market returned per
region, so the gate is `markets x regions` per event (34 at 17 keys and
`us,us2`); the cap is enforced on measured spend projected one event ahead
at the dearest charge seen (#234). `--live` without a positive
`--credit-cap` is refused. At 34 an event, the workflow's 640 buys a 16-game
night, the most the 2026-27 schedule holds.

Each response is cached raw under `--prices-dir`
(`live/<league day>/...`), never committed, and kept off any public upload:
in CI it is pushed to the PRIVATE repository
(`scripts/private_new_market_store.py`). Nothing the card, the snapshot or the
forward ledger reads is written.

Exit codes: 0 captured (or nothing to capture tonight, or a dry run); 2 a
request failed, the board could not be listed, or the cap was overspent.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.new_markets import prices
from nhl_betting_lab.preseason_screen import preseason_screen
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError, _drop_started
from nhl_betting_lab.season import LEAGUE_TIMEZONE, game_date


def tonight(events, *, league_day: str, now: datetime, screen) -> tuple[list[dict], dict[str, int]]:
    """Tonight's unstarted, screened events in face-off order, and what was dropped."""
    on_day = [e for e in events if isinstance(e, dict) and game_date(e.get("commence_time")) == league_day]
    unstarted, started = _drop_started(on_day, now)
    kept = [e for e in unstarted if screen is None or screen(e)]
    kept.sort(key=lambda e: (str(e.get("commence_time", "")), str(e.get("id", ""))))
    return kept, {
        "listed": len(events),
        "tonight": len(on_day),
        "started": started,
        "not_regular_season": len(unstarted) - len(kept),
    }


def live_request(provider: OddsApiProvider):
    def request(event, markets):
        return provider._get(  # noqa: SLF001 -- one adapter, one door
            f"{provider.base_url}/v4/sports/{provider.sport_key}/events/{event['event_id']}/odds",
            provider._params(regions=provider.regions, markets=",".join(markets)),  # noqa: SLF001
        )

    return request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Actually ask. Without it nothing is asked.")
    parser.add_argument("--credit-cap", type=int, default=0, help="Required with --live.")
    parser.add_argument("--with-alternates", action="store_true",
                        help="Also ask the alternate-ladder keys (unverified for NHL; a 422 falls back to the core).")
    parser.add_argument("--prices-dir", type=Path, default=prices.DEFAULT_PRICES_DIR)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error("--live requires a positive --credit-cap.")
    markets = list(prices.CORE_KEYS) + (list(prices.ALTERNATE_KEYS) if args.with_alternates else [])
    provider = OddsApiProvider()
    per_event = prices.live_estimate(len(markets), provider.region_count)
    if not args.live:
        print(
            f"Dry run: nothing was asked and no credit was spent. A live run gates each event at "
            f"{len(markets)} market(s) x {provider.region_count} region(s) = {per_event} credits."
        )
        return 0

    load_provider_env()
    provider = OddsApiProvider()
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    now = datetime.fromisoformat(captured_at)
    league_day = now.astimezone(LEAGUE_TIMEZONE).date().isoformat()
    try:
        screen, note = preseason_screen(league_day, processed_dir=args.processed_dir)
    except Exception as exc:  # noqa: BLE001 -- a screen that cannot be built screens nothing
        screen, note = None, f"WARNING: the preseason screen could not be built ({type(exc).__name__}: {exc})."
    print(note)
    try:
        board = provider.list_events()
    except ProviderError as exc:
        print(f"::error::The events listing failed: {exc}")
        return 2
    events, counts = tonight(board, league_day=league_day, now=now, screen=screen)
    print(
        f"{league_day}: {counts['listed']} listed, {counts['tonight']} tonight, {counts['started']} "
        f"started or unconfirmed, {counts['not_regular_season']} not on the regular-season schedule; "
        f"{len(events)} to capture at {captured_at}."
    )
    if not events:
        print("Nothing to capture tonight.")
        return 0
    wanted = [
        {
            "event_id": str(e.get("id", "")),
            "commence_time": str(e.get("commence_time", "")),
            "home_team": str(e.get("home_team", "")),
            "away_team": str(e.get("away_team", "")),
        }
        for e in events
    ]
    run = prices.gated_buy(
        wanted,
        request=live_request(provider),
        path_for=lambda e, m: prices.live_path(args.prices_dir, league_day, e["event_id"], captured_at, m),
        wrap=lambda e, payload, asked: {"captured_at": captured_at, "markets_asked": list(asked), "data": payload},
        markets=markets,
        per_event_estimate=per_event,
        credit_cap=args.credit_cap,
        core_markets=list(prices.CORE_KEYS) if args.with_alternates else None,
    )
    print(run.summary_line())
    for error in run.errors:
        print(f"  {error}", file=sys.stderr)
    rows = prices.rows_from_cache(args.prices_dir, source="live")
    tonight_rows = rows[rows["snapshot"] == captured_at] if not rows.empty else rows
    print(
        f"{len(tonight_rows):,} price row(s) over {tonight_rows['market'].nunique() if not tonight_rows.empty else 0} "
        "market(s) captured this round."
    )
    if run.failed or any(e.startswith("OVERSPENT") for e in run.errors):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
