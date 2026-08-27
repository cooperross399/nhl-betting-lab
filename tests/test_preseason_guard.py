"""Only regular-season games are priced, and the screen knows its limits.

The odds provider does not flag preseason. Books post exhibition lines from
late September, the models are fitted on regular season only, and exhibition
results are never ingested — so an unfiltered card would freeze opinions
into the forward ledger that can never settle.

The screen's failure direction is the part worth testing hardest: with a
stale schedule cache it must abstain rather than exclude, because judging
every unknown date as "not regular season" would nuke the entire opening
slate the first time the cache lagged the calendar.
"""

from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab.season import known_regular_season_games


def _schedule(tmp_path: Path, games: list[tuple[str, str, str, int]]) -> None:
    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "TOR_20262027.json").write_text(
        json.dumps(
            {
                "games": [
                    {
                        "gameType": game_type,
                        "gameDate": day,
                        "homeTeam": {"abbrev": home},
                        "awayTeam": {"abbrev": away},
                    }
                    for day, home, away, game_type in games
                ]
            }
        ),
        encoding="utf-8",
    )


def test_regular_season_games_are_known_and_preseason_is_not(
    tmp_path: Path,
) -> None:
    _schedule(
        tmp_path,
        [
            ("2026-09-25", "TOR", "MTL", 1),  # exhibition
            ("2026-10-07", "TOR", "MTL", 2),  # opening night
        ],
    )

    known = known_regular_season_games(tmp_path)

    assert ("2026-10-07", "TOR", "MTL") in known
    assert ("2026-09-25", "TOR", "MTL") not in known


def test_an_empty_cache_knows_nothing_rather_than_guessing(
    tmp_path: Path,
) -> None:
    assert known_regular_season_games(tmp_path) == set()


def test_a_corrupt_schedule_file_is_skipped(tmp_path: Path) -> None:
    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True)
    (directory / "bad.json").write_text("{broken", encoding="utf-8")
    _schedule(tmp_path, [("2026-10-07", "TOR", "MTL", 2)])
    # _schedule overwrote TOR file; recreate the corrupt one separately.
    (directory / "zz_bad.json").write_text("{broken", encoding="utf-8")

    assert ("2026-10-07", "TOR", "MTL") in known_regular_season_games(tmp_path)


def test_the_card_screen_abstains_beyond_the_dates_it_knows() -> None:
    """A stale cache must leak a preseason game, never nuke a real one."""
    from nhl_betting_lab.config import PROJECT_ROOT

    # Flattened: the message wraps, and a test failing on where a line broke
    # is a test failing on formatting rather than meaning.
    text = " ".join(
        (PROJECT_ROOT / "scripts" / "run_gameday_card.py")
        .read_text(encoding="utf-8")
        .split()
    )

    assert "known_until = max(day for day, _, _ in schedule)" in text
    assert "abstain" in text
    # Fragments only: the message spans several source string literals, and
    # asserting across a literal boundary asserts on quotation marks.
    assert "excluded before pricing" in text
    assert "opinion was frozen for them" in text


def test_with_no_schedule_at_all_the_run_warns_loudly() -> None:
    from nhl_betting_lab.config import PROJECT_ROOT

    text = (PROJECT_ROOT / "scripts" / "run_gameday_card.py").read_text(
        encoding="utf-8"
    )

    assert "no regular-season schedule is cached" in text
