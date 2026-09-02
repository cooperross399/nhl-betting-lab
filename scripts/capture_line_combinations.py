#!/usr/bin/env python3
"""Capture who has been PROMOTED, and when that became knowable.

    PYTHONPATH=src .venv/bin/python scripts/capture_line_combinations.py

`capture_deployment.py` records who is OUT, from the NHL's own API. That is
half the deployment signal. The other half is who moved UP: the winger
promoted to the first line, or onto the top power-play unit. That is exactly
the event `docs/where_the_remaining_error_lives.md` measures as the model's
largest residual error -- usage about to rise costs -6.44% over 5,661 bets,
and an oracle on future ice time is worth about five points -- and the
information is provably not in the box score.

Daily Faceoff publishes per-team line combinations and power-play units with
their own `updatedAt` stamp. Their robots.txt allows these pages (it
disallows only /api/ and /cms/). This fetches thirty-two team pages a few
times a day, on game days only, with a polite delay.

**This cannot be collected retroactively, and must never be faked.** The
source publishes only its CURRENT lines; there is no archive. Fetching
today's page and treating it as though it had been in hand this morning is
the leak that would manufacture an edge out of nothing, so every row carries
`retrieved_at` -- the instant this lab actually held the value -- and
`line_combinations.usable_before` gates on that and never on the source's own
timestamp. A night not captured is gone.

It runs beside the price capture so the two share an instant and are
joinable. It spends no provider credits, touches no card, and freezes no
opinion.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.line_combinations import (
    COLUMNS,
    TEAM_PAGE,
    rows_from_page,
    team_slugs,
)
from nhl_betting_lab.data.nhl_api import (
    API_BASE_URL,
    _default_requester,
    _get_json,
)
from nhl_betting_lab.season import LEAGUE_TIMEZONE, game_date


LINES_DIRNAME = "line_combinations"

#: Named so the site's operators can see who is asking and why.
USER_AGENT = (
    "nhl-betting-lab/1.0 (private betting-model research; "
    "low volume, game days only)"
)

#: One page that always exists, used to discover the other thirty-one rather
#: than hard-coding a list that would rot silently.
SEED_SLUG = "toronto-maple-leafs"


def capture_path(day: str, *, processed_dir: Path | None = None) -> Path:
    """One file per league game date, appended to through the day."""
    return (processed_dir or PROCESSED_DIR) / LINES_DIRNAME / f"{day}.csv"


def _fetch(url: str, *, timeout: float = 25.0) -> str:
    import requests

    response = requests.get(
        url, timeout=timeout, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return response.text


def games_today(fetch_json=None) -> int:
    """How many NHL games are on today, by league date."""
    fetch_json = fetch_json or (
        lambda path: _get_json(f"{API_BASE_URL}{path}", requester=_default_requester)
    )
    schedule = fetch_json("/v1/schedule/now")
    today = datetime.now(LEAGUE_TIMEZONE).date().isoformat()
    return sum(
        1
        for week in (schedule.get("gameWeek") or [])
        for game in (week.get("games") or [])
        if game_date(str(game.get("startTimeUTC", ""))) == today
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument(
        "--polite-seconds",
        type=float,
        default=1.5,
        help="Delay between team pages. Low volume is the whole licence here.",
    )
    parser.add_argument(
        "--ignore-schedule",
        action="store_true",
        help="Capture even with no games today. For rehearsals only.",
    )
    args = parser.parse_args(argv)

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date().isoformat()

    if not args.ignore_schedule:
        try:
            count = games_today()
        except Exception as exc:  # the public API, on a bad day
            print(f"Could not read the schedule: {exc}", file=sys.stderr)
            return 2
        if not count:
            print(f"No NHL games on {today}; nothing captured. Not a fault.")
            return 0

    try:
        seed = _fetch(TEAM_PAGE.format(slug=SEED_SLUG))
        slugs = team_slugs(seed)
    except Exception as exc:
        print(f"Could not read the team list: {exc}", file=sys.stderr)
        return 2
    if not slugs:
        print("The team list came back empty; nothing captured.", file=sys.stderr)
        return 2

    rows: list[dict] = []
    failed: list[str] = []
    for index, slug in enumerate(slugs):
        html = seed if slug == SEED_SLUG else None
        if html is None:
            time.sleep(max(0.0, args.polite_seconds))
            try:
                html = _fetch(TEAM_PAGE.format(slug=slug))
            except Exception as exc:
                failed.append(f"{slug}: {exc}")
                continue
        try:
            rows.extend(rows_from_page(html, retrieved_at=retrieved_at))
        except ValueError as exc:
            failed.append(f"{slug}: {exc}")

    if failed:
        print(f"{len(failed)} team page(s) could not be read:", file=sys.stderr)
        for line in failed[:5]:
            print(f"  {line}", file=sys.stderr)
    if not rows:
        # Loud, because silence here looks exactly like a quiet night.
        print("No line rows were parsed; nothing written.", file=sys.stderr)
        return 2

    frame = pd.DataFrame(rows)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[list(COLUMNS)]

    path = capture_path(today, processed_dir=Path(args.processed_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path, mode="a", header=not path.is_file(), index=False, lineterminator="\n"
    )

    teams = frame["team_slug"].nunique()
    sources = sorted(set(frame["source_name"]) - {""})
    print(
        f"{teams} team(s), {len(frame)} role row(s) at {retrieved_at} -> {path}"
    )
    if sources:
        # Provenance, not decoration: a projection and a confirmed
        # morning-skate line are different evidence and must not be pooled.
        print(f"  source(s): {', '.join(sources[:4])}")
    print(
        "This capture spent no provider credits, touched no card, and froze "
        "no opinion."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
