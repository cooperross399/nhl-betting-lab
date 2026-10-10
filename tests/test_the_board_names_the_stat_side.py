"""The Board names each game's stat side on the game's row (Cooper, 2026-10-10).

"Not only looking for edges but looking for sides that the stats say should
win": every modelled game's collapsed row carries "Stats: <team> <chance>%",
the team with the larger `winProb`, so the side reads without opening the
game. Rendered through Board.dc.html's own component on the builder's output.
A game with no projection carries no tag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import test_the_site_board_carries_the_drought_list as drought_page
from test_site_never_calls_an_unpriced_game_a_pass import make_lab
from test_the_site_board_carries_the_drought_list import build


@pytest.fixture
def lab(tmp_path: Path, monkeypatch) -> Path:
    return make_lab(tmp_path, monkeypatch, staged=False)


def test_every_modelled_game_row_names_the_side_with_the_larger_win_chance(lab, tmp_path, monkeypatch) -> None:
    board = build(lab, tmp_path / "out", monkeypatch)
    modelled = [g for g in board["games"] if isinstance(g["home"].get("winProb"), (int, float))]
    assert modelled, "the fixture lab projects its games"
    expected = []
    for g in board["games"]:
        hp, ap = g["home"].get("winProb"), g["away"].get("winProb")
        if isinstance(hp, (int, float)) and isinstance(ap, (int, float)):
            side = g["home"] if hp >= ap else g["away"]
            expected.append(f"Stats: {side['abbr']} {round(max(hp, ap) * 100)}%")
        else:
            expected.append("")
    # An unmodelled game on the same board, to pin that it carries no tag.
    blank = {**board["games"][0], "id": "999", "home": {"abbr": board["games"][0]["home"]["abbr"]},
             "away": {"abbr": board["games"][0]["away"]["abbr"]}, "pick": None}
    board["games"].append(blank)
    expected.append("")

    driver = drought_page._PAGE_DRIVER.replace("label: g.sum.drought,", "label: g.sum.drought, side: g.sum.statSide,")
    assert driver != drought_page._PAGE_DRIVER
    monkeypatch.setattr(drought_page, "_PAGE_DRIVER", driver)
    shown = [g["side"] for g in drought_page.render_page(board, tmp_path)["tonight"]["games"]]
    assert sorted(shown) == sorted(expected)
    assert any(s for s in shown), "at least one game carries a stat side"
