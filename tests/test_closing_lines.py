"""Closing-line value, and the ways it could quietly lie.

Every test here is a way this measurement could flatter the model without
raising anything: a live price used as a close, a pulled selection dropped
instead of counted, a de-vig applied to a market that cannot take one.
"""

from __future__ import annotations

import pandas as pd

from nhl_betting_lab import closing_lines as cl


GAME = {
    "commence_time": "2026-10-08T23:00:00Z",
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
}


def _opinion(**overrides) -> pd.DataFrame:
    row = {
        **GAME,
        "snapshot_date": "2026-10-08",
        "market": "moneyline",
        "player": "",
        "selection": "away",
        "line": None,
        "american_odds": 150.0,
        "book": "DraftKings",
        "model_probability": 0.45,
        "edge": 0.05,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _capture(**overrides) -> dict:
    row = {
        **GAME,
        "captured_at": "2026-10-08T22:30:00Z",
        "market": "moneyline",
        "player": "",
        "selection": "away",
        "line": None,
        "american_odds": 120.0,
        "book": "BetMGM",
    }
    row.update(overrides)
    return row


def test_a_price_captured_after_the_start_is_never_the_close() -> None:
    """It is a live price. Scoring a 09:30 opinion against an in-game number
    would flatter or damn the model with information it could not have had."""
    captures = pd.DataFrame(
        [
            _capture(),
            _capture(captured_at="2026-10-08T23:30:00Z", american_odds=-500.0),
        ]
    )

    rows, counts = cl.clv_rows(_opinion(), captures)

    assert counts["matched"] == 1
    assert rows.iloc[0]["closing_odds"] == 120.0


def test_the_latest_price_before_the_start_wins() -> None:
    captures = pd.DataFrame(
        [
            _capture(captured_at="2026-10-08T20:00:00Z", american_odds=200.0),
            _capture(captured_at="2026-10-08T22:45:00Z", american_odds=110.0),
        ]
    )

    rows, _ = cl.clv_rows(_opinion(), captures)

    assert rows.iloc[0]["closing_odds"] == 110.0


def test_an_opinion_with_no_close_is_counted_not_dropped() -> None:
    """A selection the books pulled is the one most likely to have been
    wrong. Dropping it silently would flatter the model exactly there."""
    rows, counts = cl.clv_rows(
        _opinion(), pd.DataFrame(columns=list(cl.CAPTURE_COLUMNS))
    )

    assert rows.empty
    assert counts == {"opinions": 1, "matched": 0, "no_close": 1}


def test_clv_is_positive_when_the_price_shortened_after_we_took_it() -> None:
    rows, _ = cl.clv_rows(_opinion(), pd.DataFrame([_capture()]))
    row = rows.iloc[0]

    # +150 is 2.50 decimal; +120 is 2.20. 2.50/2.20 - 1 = +13.6%.
    assert bool(row["beat_close"])
    assert abs(float(row["clv_pct"]) - (2.5 / 2.2 - 1.0)) < 1e-9


def test_clv_is_negative_when_the_market_moved_against_us() -> None:
    rows, _ = cl.clv_rows(
        _opinion(), pd.DataFrame([_capture(american_odds=200.0)])
    )

    assert not bool(rows.iloc[0]["beat_close"])
    assert rows.iloc[0]["clv_pct"] < 0


def test_expected_value_needs_the_other_side_to_have_closed() -> None:
    """Without a pair there is no de-vig, and a guessed fair price is worse
    than none."""
    unpaired, _ = cl.clv_rows(_opinion(), pd.DataFrame([_capture()]))
    assert pd.isna(unpaired.iloc[0]["ev_at_close"])

    paired, _ = cl.clv_rows(
        _opinion(),
        pd.DataFrame([_capture(), _capture(selection="home", american_odds=-140.0)]),
    )
    ev = paired.iloc[0]["ev_at_close"]
    # De-vigged fair probability of the +120 side is about 0.438; taking it
    # at +150 is worth about +9.5 cents per unit.
    assert 0.08 < ev < 0.11


def test_the_three_way_is_never_devigged_as_a_pair() -> None:
    """Three outcomes cannot be de-vigged in twos, and a fair probability
    that is simply wrong is worse than an absent one."""
    assert cl.opposite_selection("regulation_3_way", "home", None) is None
    assert cl.opposite_selection("regulation_3_way", "draw", None) is None


def test_the_puck_line_pairs_against_the_mirrored_number() -> None:
    """home -1.5 and away +1.5 are the same wager from the two sides. Pairing
    them at the same signed line would de-vig against a different bet."""
    assert cl.opposite_selection("puck_line", "home", -1.5) == ("away", 1.5)
    assert cl.opposite_selection("puck_line", "away", 1.5) == ("home", -1.5)


def test_team_totals_pair_within_a_side() -> None:
    assert cl.opposite_selection("team_total", "home_over", 3.5) == (
        "home_under",
        3.5,
    )


def test_only_the_best_price_of_a_capture_is_kept() -> None:
    """The card quotes the best reachable price, so the close has to use the
    same basis or the comparison measures the book, not the model."""
    prices = pd.DataFrame(
        [
            {**GAME, "market": "moneyline", "player": "", "selection": "away",
             "line": None, "american_odds": 120.0, "book": "Worse"},
            {**GAME, "market": "moneyline", "player": "", "selection": "away",
             "line": None, "american_odds": 145.0, "book": "Better"},
        ]
    )

    best = cl.best_prices(prices, captured_at="2026-10-08T22:30:00Z")

    assert len(best) == 1
    assert best.iloc[0]["american_odds"] == 145.0
    assert best.iloc[0]["book"] == "Better"


def test_the_report_says_no_demonstrated_value_when_the_interval_spans_zero() -> None:
    """The house sentence, in the house words."""
    captures = pd.DataFrame([_capture(), _capture(american_odds=200.0,
                                                  captured_at="2026-10-08T21:00:00Z")])
    report = cl.build_clv_report(_opinion(), captures)
    rendered = cl.render_clv(report, generated="test")

    assert "Closing-line value" in rendered
    assert "no demonstrated" in rendered or "Nothing to measure yet" in rendered
    assert "it is not profit" in rendered


def test_the_store_refuses_to_shrink(tmp_path) -> None:
    frame = cl.best_prices(
        pd.DataFrame([{**GAME, "market": "moneyline", "player": "",
                       "selection": "away", "line": None,
                       "american_odds": 120.0, "book": "BetMGM"}]),
        captured_at="2026-10-08T22:30:00Z",
    )
    assert cl.append_captures(frame, processed_dir=tmp_path) == 1
    assert cl.append_captures(frame, processed_dir=tmp_path) == 1
    assert len(cl.load_captures(tmp_path)) == 2


# -- defects the first version shipped with, each reproduced then fixed ----


def _rendered(opinions: pd.DataFrame, captures: pd.DataFrame) -> str:
    return cl.render_clv(cl.build_clv_report(opinions, captures), generated="t")


def test_every_table_row_has_exactly_as_many_cells_as_its_header() -> None:
    """The by-market table shipped one cell short, so every number rendered
    under the heading to its left and the sample size was swallowed by the
    View cell. Nothing in the suite looked at a table row, which is exactly
    why it shipped."""
    opinions = pd.concat(
        [
            _opinion(),
            _opinion(market="total_goals", selection="over", line=6.5,
                     american_odds=-110.0),
        ],
        ignore_index=True,
    )
    captures = pd.DataFrame(
        [
            _capture(),
            _capture(market="total_goals", selection="over", line=6.5,
                     american_odds=-130.0),
        ]
    )

    rendered = _rendered(opinions, captures)

    header_cells = None
    for line in rendered.splitlines():
        if not line.startswith("|"):
            header_cells = None
            continue
        cells = len(line.split("|"))
        if header_cells is None:
            header_cells = cells
            continue
        assert cells == header_cells, f"ragged table row: {line}"


def test_the_expected_value_column_carries_its_interval() -> None:
    """EV at close is the money figure. It was published as a bare point
    estimate while its interval was computed and thrown away."""
    opinions = pd.concat([_opinion()] * 4, ignore_index=True)
    captures = pd.DataFrame(
        [_capture(), _capture(selection="home", american_odds=-140.0)]
    )

    rendered = _rendered(opinions, captures)

    assert "EV at close [95%] (n)" in rendered
    assert "money figure" in rendered


def test_opinions_are_scored_at_the_best_price_not_an_arbitrary_book() -> None:
    """The snapshot holds one row per book. Scoring whichever row survived a
    de-duplication measured luck — and because the surviving price decides
    whether the selection clears the staking bar, it moved bets in and out
    of the table exactly where the price was worst."""
    opinions = pd.DataFrame(
        [
            {**GAME, "snapshot_date": "2026-10-08", "market": "moneyline",
             "player": "", "selection": "away", "line": None,
             "american_odds": 110.0, "book": "Worse", "edge": 0.01},
            {**GAME, "snapshot_date": "2026-10-08", "market": "moneyline",
             "player": "", "selection": "away", "line": None,
             "american_odds": 150.0, "book": "Best", "edge": 0.09},
        ]
    )

    rows, counts = cl.clv_rows(opinions, pd.DataFrame([_capture()]))

    assert counts["opinions"] == 1, "two books, one selection"
    assert rows.iloc[0]["taken_odds"] == 150.0


def test_a_capture_at_the_puck_drop_second_is_not_a_close() -> None:
    """Compared as strings, `...+00:00` sorts before `...Z`, so a capture at
    the exact start could pass a guard written to exclude it."""
    captures = pd.DataFrame(
        [_capture(captured_at="2026-10-08T23:00:00+00:00", american_odds=-300.0)]
    )

    rows, counts = cl.clv_rows(_opinion(), captures)

    assert rows.empty
    assert counts["no_close"] == 1


def test_an_unparseable_stamp_is_refused_rather_than_ordered_by_luck() -> None:
    captures = pd.DataFrame([_capture(captured_at="not a timestamp")])

    _, counts = cl.clv_rows(_opinion(), captures)

    assert counts["no_close"] == 1


def test_a_price_that_did_not_move_is_neither_a_win_nor_a_loss() -> None:
    """Ties dragged the beat rate down on exactly the markets that move
    least."""
    captures = pd.DataFrame([_capture(american_odds=150.0)])

    report = cl.build_clv_report(_opinion(), captures)
    summary = report["overall"]["opinions"]

    assert summary["tied"] == 1
    assert summary["decided"] == 0
    assert summary["beat_close"] == 0


def test_the_devig_refuses_legs_from_different_capture_rounds() -> None:
    """Two prices taken hours apart are not a market's two sides at one
    moment, and the drift between them is not vig."""
    captures = pd.DataFrame(
        [
            _capture(),
            _capture(
                selection="home",
                american_odds=-140.0,
                captured_at="2026-10-08T19:00:00Z",
            ),
        ]
    )

    rows, _ = cl.clv_rows(_opinion(), captures)

    assert pd.isna(rows.iloc[0]["ev_at_close"])


def test_bets_that_never_got_a_close_are_reconciled_too() -> None:
    """Counting only opinions would let a bet whose price the books pulled
    vanish from every number on the page."""
    opinions = _opinion(edge=0.99)

    report = cl.build_clv_report(
        opinions, pd.DataFrame(columns=list(cl.CAPTURE_COLUMNS))
    )

    assert report["counts"]["bets"] == 1
    assert report["counts"]["bets_no_close"] == 1


def test_a_truncated_store_reads_as_absent_rather_than_crashing(tmp_path) -> None:
    (tmp_path / "closing_line_captures.csv").write_text("", encoding="utf-8")

    assert cl.load_captures(tmp_path).empty


def test_the_house_phrase_is_used_verbatim() -> None:
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE

    opinions = pd.concat([_opinion(), _opinion(american_odds=140.0)],
                         ignore_index=True)
    rendered = _rendered(opinions, pd.DataFrame([_capture()]))

    assert NO_DEMONSTRATED_EDGE in rendered


def test_the_capture_merge_never_loses_a_remote_row() -> None:
    """A push that collides must merge, not re-offer what it hashed before it
    fetched. Once a game has started, a dropped capture cannot be retaken."""
    import sys

    sys.path.insert(0, str(cl.Path(__file__).resolve().parents[1] / "scripts"))
    from merge_capture_store import merge

    theirs = pd.DataFrame([_capture(), _capture(selection="home")])
    mine = pd.DataFrame([_capture(), _capture(market="total_goals", line=6.5)])

    merged = merge(mine, theirs)

    assert len(merged) == 3, "the shared row collapses, both uniques survive"
    for frame in (theirs, mine):
        for row in frame.itertuples():
            assert (merged["selection"] == row.selection).any()


def test_the_capture_merge_refuses_to_shrink_the_remote_store() -> None:
    import sys

    sys.path.insert(0, str(cl.Path(__file__).resolve().parents[1] / "scripts"))
    from merge_capture_store import merge
    import pytest

    theirs = pd.DataFrame([_capture(), _capture(selection="home")])
    # A remote holding duplicate rows must never come back shorter.
    with pytest.raises(ValueError, match="Refusing a merge"):
        merge(pd.DataFrame(columns=list(cl.CAPTURE_COLUMNS)),
              pd.concat([theirs, theirs], ignore_index=True))
