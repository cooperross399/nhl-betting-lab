"""Cooper, 2026-11-19: "dont show me 1+ point if its for more than -150",
then 2026-11-21 (the lists' re-evaluation): no Due or Hot List row of any
category priced shorter than -130 is listed. -130 itself, a longer price and
an unpriced row are.
"""
from nhl_betting_lab import drought_rule, hot_list


def test_a_row_shorter_than_minus_130_is_not_listed() -> None:
    rows = [
        {"player": "Short", "market": "points", "american_odds": -151},
        {"player": "PointsMid", "market": "points", "american_odds": -140},
        {"player": "Edge", "market": "points", "american_odds": -130},
        {"player": "Plus", "market": "points", "american_odds": 120},
        {"player": "Unpriced", "market": "points", "american_odds": None},
        {"player": "Assist", "market": "assists", "american_odds": -190},
        {"player": "AssistEdge", "market": "assists", "american_odds": -130},
        {"player": "TwoPoints", "market": "two_points", "american_odds": -200},
    ]
    notes: list[str] = []
    kept = drought_rule.drop_short_points(rows, notes)
    assert [r["player"] for r in kept] == ["Edge", "Plus", "Unpriced", "AssistEdge"]
    assert notes == ["4 row(s) priced shorter than -130 are not listed."]


def test_both_lists_apply_it() -> None:
    assert drought_rule.POINT_MAX_JUICE == -150
    assert drought_rule.LIST_MAX_JUICE == -130
    assert hot_list.drop_short_points is drought_rule.drop_short_points
    import inspect
    assert "drop_short_points(rows, result.notes)" in inspect.getsource(drought_rule.build_drought_list)
    assert "drop_short_points(rows, result.notes)" in inspect.getsource(hot_list.build_hot_list)
