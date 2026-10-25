#!/usr/bin/env python3
"""Record PostHockey's pre-game win probability for tonight's games.

    PYTHONPATH=src .venv/bin/python scripts/fetch_posthockey_pregame.py

Free (PostHockey's public live endpoint), and soft in Gameday Refresh: the
card blends what is here into its team markets and moves nothing for a game
with no row (`nhl_betting_lab.posthockey`). Each run appends what it read,
and the card takes the latest read of each game, so the pre-game update
picks up the lineups and goalies posted since the morning. Exit 0 unless the
endpoint could not be read at all.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from nhl_betting_lab import posthockey as ph
from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.data.nhl_api import _default_requester, _get_json
from nhl_betting_lab.season import LEAGUE_TIMEZONE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    args = parser.parse_args(argv)
    processed = Path(args.processed_dir)

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date().isoformat()
    try:
        payload = _get_json(ph.LIVE_URL, requester=_default_requester, params={"date": today})
        rows = ph.pregame_rows(payload, today, retrieved_at)
    except Exception as exc:  # a third party's site, on a bad day
        print(f"::warning::Could not read PostHockey's pre-game numbers: {exc}", file=sys.stderr)
        return 2
    ph.append_rows(processed / ph.TONIGHT_DIRNAME / f"{today}.csv", rows)
    for row in rows:
        print(
            f"{row['away_team']} at {row['home_team']}: home {row['p_home']:.1%} "
            f"(goalies {row['goalie_away_status'] or '?'} / {row['goalie_home_status'] or '?'})."
        )
    print(f"Tonight ({today}): PostHockey priced {len(rows)} game(s) not yet started.")
    print("This spent no provider credits.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
