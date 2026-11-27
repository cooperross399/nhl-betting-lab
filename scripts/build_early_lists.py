"""Build today's Due List and Hot List before the card, for the 3 AM board.

Cooper, 2026-11-27: "We need the due list and hot list to be updated at 3am
like the college basketball portion of the site does now". The lists were
built only by the card (about 9:40 AM New York), so from midnight until then
the site showed none for the new day.

Publish Site runs this after it has refreshed the NHL results (free) and
before it builds the board. It writes `drought_list.json` and `hot_list.json`
into the outputs directory for TODAY's league day, from the player logs, the
current rosters and the schedule alone. Each row's price is whatever is staged
(the board's early fetch asks team markets only, so props read "not posted"),
never filled in. The card's own build replaces both files when it runs.

It writes no dated list, no ledger row, no snapshot and no card: nothing here
is recorded or graded. A list already built for today (the card's, priced) is
left as it is. `--check` exits 0 when today's lists are missing and 1 when
both are already for today, so the workflow can skip the results fetch.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, STAGING_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs
from nhl_betting_lab.data.nhl_api import current_rosters
from nhl_betting_lab.drought_rule import (
    SITE_LIST_FILENAME,
    DroughtList,
    backtest_headline,
    build_drought_list,
    cell_records,
    save_site_list,
    site_payload,
)
from nhl_betting_lab.hot_list import SITE_LIST_FILENAME as HOT_SITE_LIST_FILENAME
from nhl_betting_lab.hot_list import build_hot_list
from nhl_betting_lab.hot_list import save_site_list as save_hot_list
from nhl_betting_lab.hot_list import site_payload as hot_site_payload
from nhl_betting_lab.providers.team_names import build_team_name_map, saved_team_name_map
from nhl_betting_lab.season import LEAGUE_TIMEZONE, scheduled_regular_season_starts

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gameday_card import _staged_prices  # noqa: E402


def list_day(path: Path) -> str | None:
    """The day a saved list is for, or None when it cannot be read."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload.get("day") if isinstance(payload, dict) else None


def lists_needed(outputs: Path, day: str) -> list[str]:
    """The list files in `outputs` not already built for `day`."""
    return [
        name for name in (SITE_LIST_FILENAME, HOT_SITE_LIST_FILENAME)
        if list_day(outputs / name) != day
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--now", default=None, help="ISO time with a timezone (tests)")
    parser.add_argument("--check", action="store_true",
                        help="exit 0 when today's lists are missing, 1 when both are built")
    args = parser.parse_args(argv)

    moment = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        parser.error("--now must carry a timezone.")
    day = moment.astimezone(LEAGUE_TIMEZONE).date().isoformat()
    outputs = Path(args.output_dir)
    processed = Path(args.processed_dir)
    raw = Path(args.raw_dir) if args.raw_dir else None

    needed = lists_needed(outputs, day)
    if args.check:
        print(f"Lists for {day}: " + (f"to build ({', '.join(needed)})." if needed else "already built."))
        return 0 if needed else 1
    if not needed:
        print(f"The Due List and Hot List are already built for {day}; left as they are.")
        return 0

    starts = scheduled_regular_season_starts(raw)
    if not any(key[0] == day for key in starts):
        print(f"No regular-season game is scheduled for {day}; no list is built.")
        return 0
    logs = load_player_logs(processed)
    rosters = current_rosters(raw_dir=raw)
    team_names = {**saved_team_name_map(processed_dir=processed),
                  **(build_team_name_map(raw) if raw else build_team_name_map())}
    prices = _staged_prices(Path(args.staging_dir))
    generated_at = moment.isoformat()

    if SITE_LIST_FILENAME in needed:
        try:
            drought = build_drought_list(
                logs=logs, rosters=rosters, starts=starts, prices=prices,
                team_names=team_names, day=day, now=moment,
                records=cell_records(outputs, fallback=OUTPUTS_DIR),
            )
        except (KeyError, ValueError) as exc:
            drought = DroughtList(day=day, notes=[f"The Due List could not be built: {exc}"])
            print(f"::warning::The Due List could not be built: {exc}")
        drought.notes.append("Built before the card from last night's results; prices fill in when the card runs.")
        save_site_list(outputs / SITE_LIST_FILENAME,
                       site_payload(drought, backtest_headline(outputs, fallback=OUTPUTS_DIR), generated_at))
        print(f"Due List for {day}: {len(drought.rows)} row(s), "
              f"{sum(1 for r in drought.rows if r.get('american_odds') is None)} with no price posted.")

    if HOT_SITE_LIST_FILENAME in needed:
        try:
            hot = build_hot_list(logs=logs, rosters=rosters, starts=starts, prices=prices,
                                 team_names=team_names, day=day, now=moment)
        except (KeyError, ValueError) as exc:
            hot = DroughtList(day=day, notes=[f"The Hot List could not be built: {exc}"])
            print(f"::warning::The Hot List could not be built: {exc}")
        hot.notes.append("Built before the card from last night's results; prices fill in when the card runs.")
        save_hot_list(outputs / HOT_SITE_LIST_FILENAME, hot_site_payload(hot, generated_at))
        print(f"Hot List for {day}: {len(hot.rows)} row(s).")
    print("Nothing was recorded, staked or frozen: these lists are for the board only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
