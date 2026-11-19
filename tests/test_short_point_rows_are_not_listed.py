"""Cooper, 2026-11-19: "dont show me 1+ point if its for more than -150".

A 1+ point row on the Due List or the Hot List priced shorter than -150 is
not listed; -150 itself, a longer price, an unpriced row and other
categories are.
"""
from nhl_betting_lab import drought_rule, hot_list


def test_a_one_point_row_shorter_than_minus_150_is_not_listed() -> None:
    rows = [
        {"player": "Short", "market": "points", "american_odds": -151},
        {"player": "Edge", "market": "points", "american_odds": -150},
        {"player": "Plus", "market": "points", "american_odds": 120},
        {"player": "Unpriced", "market": "points", "american_odds": None},
        {"player": "Assist", "market": "assists", "american_odds": -190},
        {"player": "TwoPoints", "market": "two_points", "american_odds": -200},
    ]
    notes: list[str] = []
    kept = drought_rule.drop_short_points(rows, notes)
    assert [r["player"] for r in kept] == ["Edge", "Plus", "Unpriced", "Assist", "TwoPoints"]
    assert notes == ["1 1+ point row(s) priced shorter than -150 are not listed."]


def test_both_lists_apply_it() -> None:
    assert drought_rule.POINT_MAX_JUICE == -150
    assert hot_list.drop_short_points is drought_rule.drop_short_points
    import inspect
    assert "drop_short_points(rows, result.notes)" in inspect.getsource(drought_rule.build_drought_list)
    assert "drop_short_points(rows, result.notes)" in inspect.getsource(hot_list.build_hot_list)
