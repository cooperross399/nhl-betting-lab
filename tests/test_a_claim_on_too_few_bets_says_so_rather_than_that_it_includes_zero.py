"""A claim on under thirty bets says it is too few, not that it spans zero.

`RoiInterval.survives_correction` is False below thirty bets whatever the
interval, and `MarketClaim.sentence` rendered every False as "Correcting for
the family, it does not exclude zero." On 22 wins and 3 losses at even money,
seven looks, the corrected interval is about +40% to +112% -- it excludes
zero by a distance -- and the claims document said it did not. It now says
what `RoiInterval.verdict()` says: far too few bets to measure anything. The
verdict is unchanged; no demonstrated edge either way.
"""

from __future__ import annotations

from nhl_betting_lab.reports.what_we_can_claim import MarketClaim
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, roi_interval


def _claim(returns: list[float], *, looks: int = 7) -> tuple[MarketClaim, object]:
    measured = roi_interval(returns, looks=looks, family="6 markets and the overall figure")
    return (
        MarketClaim(
            market="goals",
            measured=True,
            bets=measured.bets,
            roi=measured.roi,
            low=measured.low,
            high=measured.high,
            includes_zero=measured.includes_zero,
            survives_correction=measured.survives_correction,
            looks=looks,
            family=measured.family,
        ),
        measured,
    )


def test_the_repro_corrected_interval_excludes_zero_and_does_not_survive() -> None:
    _, measured = _claim([1.0] * 22 + [-1.0] * 3)
    assert measured.bets == 25
    assert measured.adjusted_low > 0
    assert measured.survives_correction is False


def test_twenty_five_bets_is_called_too_few_not_an_interval_spanning_zero() -> None:
    claim, _ = _claim([1.0] * 22 + [-1.0] * 3)
    sentence = claim.sentence()
    assert "does not exclude zero" not in sentence
    assert "far too few" in sentence
    assert "25 bets" in sentence
    assert NO_DEMONSTRATED_EDGE.capitalize() in sentence


def test_twenty_nine_is_too_few_and_thirty_is_not() -> None:
    few, _ = _claim([1.0] * 25 + [-1.0] * 4)
    assert "far too few" in few.sentence()
    # At thirty the interval governs again; this one survives.
    enough, measured = _claim([1.0] * 27 + [-1.0] * 3)
    assert measured.bets == 30 and measured.survives_correction
    assert "far too few" not in enough.sentence()
    assert "excludes zero even after correcting" in enough.sentence()


def test_a_real_failure_to_survive_still_says_so() -> None:
    # 60 bets, naive interval excludes zero, corrected one does not.
    claim, measured = _claim([1.0] * 39 + [-1.0] * 21)
    assert not measured.includes_zero and not measured.survives_correction
    assert "it does not exclude zero" in claim.sentence()
    assert "far too few" not in claim.sentence()
