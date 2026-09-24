"""Re-buying a team window doubled it, and a missing column undid a collapse.

Two defects in `stores`, both of the kind that make a store look significant
rather than wrong.

`dedupe_prices` compared `player` as pandas reconstructed it. A team row is
built with `player` "" and read back from CSV as NaN, so the copy already on
disk and the identical copy just bought were two quotes. Measured on the real
team store on 2026-09-24: re-buying the window it already holds took 308,944
rows to 586,068 under the old comparison, and leaves 293,034 under the new
one, exactly what deduplicating the store alone gives. The props store keeps
the identical 3,802,164 rows either way, so no published figure moves.

`best_price_per_wager` returned its input uncollapsed when a key column or
the odds were missing. That is the per-quote counting that published "-1.6%
over 73,918" as a demonstrated loss, restored without a word by a renamed
column.
"""

from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.stores import best_price_per_wager, dedupe_prices, read_store

TEAM_QUOTE = {
    "provider_event_id": "evt1",
    "commence_time": "2025-10-18T23:10:00Z",
    "snapshot": "2025-10-18T19:10:00Z",
    "market": "total_goals",
    "player": "",
    "selection": "over",
    "line": 5.5,
    "book": "DraftKings",
    "american_odds": -110.0,
}


def _bought(**changes) -> pd.DataFrame:
    """Rows as a purchase builds them, before any CSV round-trip."""
    return pd.DataFrame(
        [{**TEAM_QUOTE, **changes}, {**TEAM_QUOTE, "book": "FanDuel", **changes}]
    )


def test_rebuying_a_window_already_on_disk_adds_nothing(tmp_path) -> None:
    path = tmp_path / "historical_team_prices.csv"
    _bought().to_csv(path, index=False)
    on_disk = read_store(path, for_append=True)
    assert on_disk["player"].isna().all(), "the round-trip this test is about"

    merged = dedupe_prices(pd.concat([on_disk, _bought()], ignore_index=True))

    assert len(merged) == 2, "one window bought twice is still one window"


def test_a_line_written_as_text_is_the_same_line() -> None:
    frame = pd.concat([_bought(), _bought(line="5.50")], ignore_index=True)
    assert len(dedupe_prices(frame)) == 2


def test_the_rows_kept_are_the_rows_as_given(tmp_path) -> None:
    """Only the comparison is normalised; the stored values are not rewritten."""
    out = dedupe_prices(_bought())
    assert list(out["player"]) == ["", ""]
    assert list(out["line"]) == [5.5, 5.5]


def test_normalising_does_not_merge_genuinely_different_quotes() -> None:
    """The fold is only for absent values and number spellings."""
    frame = pd.concat(
        [_bought(), _bought(line=6.5), _bought(selection="under")],
        ignore_index=True,
    )
    assert len(dedupe_prices(frame)) == 6


KEY = ["provider_event_id", "market", "player", "selection", "line"]


def test_a_missing_key_column_is_refused_not_passed_through() -> None:
    frame = _bought().drop(columns=["selection"])
    with pytest.raises(ValueError, match="selection"):
        best_price_per_wager(frame, KEY)


def test_missing_odds_are_refused_not_passed_through() -> None:
    frame = _bought().drop(columns=["american_odds"])
    with pytest.raises(ValueError, match="american_odds"):
        best_price_per_wager(frame, KEY)


def test_an_empty_frame_is_still_an_empty_answer() -> None:
    """A night with no prices is not an error; it is nothing to collapse."""
    assert best_price_per_wager(pd.DataFrame(columns=["market"]), KEY).empty


def test_two_books_on_one_wager_are_one_bet_at_the_better_price() -> None:
    """What the refusal must not have broken."""
    frame = pd.concat(
        [_bought().iloc[[0]], _bought(book="FanDuel", american_odds=105.0).iloc[[0]]],
        ignore_index=True,
    )
    out = best_price_per_wager(frame, KEY)
    assert len(out) == 1
    assert out["american_odds"].iloc[0] == 105.0
