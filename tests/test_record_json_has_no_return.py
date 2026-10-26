"""record.json and ratings.json are accuracy and ratings, never a return.

The Track record and Methods pages (Claude Design's drop, 2026-10-26) read
these two files, and the hub's NHL card reads record.json from another
origin. Neither may carry a return, a unit, a profit or a stake: the forward
ledger's return stays sealed until 2027-04-25, and the season's betting
record lives on the Tracker page, which says what it counts. This scans every
key and every string in both documents, opening day included, so a field added
later cannot slip one in under another name's shelter.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from nhl_betting_lab.factor_breakdown import STEPS

from test_site_never_calls_an_unpriced_game_a_pass import site_module

FORBIDDEN = ("roi", "units", "profit", "return", "staked")


def _words(node) -> list[str]:
    if isinstance(node, dict):
        return [w for k, v in node.items() for w in [str(k), *_words(v)]]
    if isinstance(node, list):
        return [w for v in node for w in _words(v)]
    return [node] if isinstance(node, str) else []


def _clean(doc: dict) -> None:
    for word in _words(doc):
        assert not any(bad in word.lower() for bad in FORBIDDEN), word


def test_opening_day_writes_an_empty_record(tmp_path: Path) -> None:
    module = site_module()
    record = module.track_record(date(2026, 10, 26), tmp_path / "history")
    assert (record["nights"], record["games"], record["buckets"], record["brier"]) == (0, 0, [], None)
    _clean(record)


def test_ratings_without_shift_charts_carry_no_defence(tmp_path: Path) -> None:
    module = site_module()
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / module.SHADOW_RATINGS).write_text(json.dumps({
        "last_game_date": "2026-10-25",
        "teams": {"TOR": {"attack": 1.08, "defence": 0.94}, "MTL": {"attack": 0.96, "defence": 1.03}},
        "form": {"TOR": {"attack": 1.02, "defence": 0.99}},
        "home_ice": {"TOR": 0.021}, "team_goalie": {"TOR": 0.97},
    }), encoding="utf-8")
    ratings = module.ratings_page(tmp_path)
    assert ratings["through"] == "2026-10-25"
    assert {t["abbr"] for t in ratings["teams"]} == {"TOR", "MTL"}
    assert ratings["defence"] is None
    _clean(ratings)


def test_the_factor_keys_are_the_pages_eight_in_order() -> None:
    assert [k for k, _ in STEPS] == ["strength", "home_ice", "form", "rest", "lineup", "goalies",
                                     "referees", "posthockey"]
