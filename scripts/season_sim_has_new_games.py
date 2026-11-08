"""Say whether a game has gone final since the last season projection.

Season Sim runs every hour so the Season page, its award races included,
moves after every game (Cooper, 2026-11-08: "this should update with every
game played ... for every award"). An hourly run with no new final would
rebuild the same projection and republish the site for nothing, so it asks
first: the NHL's current standings, summed over the 32 clubs, against the
``leagueGamesPlayed`` the last projection was built on.

Prints ``build=true`` or ``build=false`` (append it to ``$GITHUB_OUTPUT``).
Anything it cannot read means build: a missed update is worse than a spare
one.

    python scripts/season_sim_has_new_games.py --previous PATH
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

STANDINGS = "https://api-web.nhle.com/v1/standings/now"


def games_final(standings: dict) -> int:
    """Games played league-wide: each game is in two clubs' records."""
    return sum(int(row.get("gamesPlayed") or 0) for row in standings.get("standings") or []) // 2


def previous_games(path: Path | None) -> int | None:
    if path is None or not path.is_file():
        return None
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["leagueGamesPlayed"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def decide(previous: int | None, now: int | None) -> tuple[bool, str]:
    if previous is None:
        return True, "no earlier projection to compare with"
    if now is None:
        return True, "the standings could not be read"
    if now != previous:
        return True, f"{now - previous:+d} game(s) final since the last projection ({previous} -> {now})"
    return False, f"no game has gone final since the last projection ({now} played)"


def fetch_standings(url: str = STANDINGS) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nhl-betting-lab season sim"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any failure means build
        print(f"::warning::The standings could not be read ({exc}); building anyway.")
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--previous", type=Path, default=None, help="the last season.json")
    args = ap.parse_args(argv)
    standings = fetch_standings()
    now = games_final(standings) if standings is not None else None
    build, why = decide(previous_games(args.previous), now)
    print(f"Season Sim: {why}.")
    print(f"build={'true' if build else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
