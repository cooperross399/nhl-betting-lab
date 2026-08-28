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
