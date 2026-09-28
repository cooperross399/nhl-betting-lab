"""The Results page graded every unpriced game as a model "No play", settled as a Push.

`web/build_site_json.py::settle` turns yesterday's frozen board into
results.json. Every game without a pick got a pick anyway:
`{"market": "—", "label": "No play", "price": 0, "result": "push"}`. It
never read the frozen board's `priced` flag. Publish Site restores no staged
prices (ledger item [33], left to the owner), so from opening night every
regular-season game is frozen `priced: false` with no pick. The board says
"Not priced" for those games (fixed in #154). The next morning, though,
`web/lib/sports.js::resultPick` rendered the placeholder under the "Model
pick" heading as "No play", "— · −0", "Push". So a game no price ever
reached was published as a model pass and then graded as a push. The page
also printed a price of "−0" that nobody quoted. CLAUDE.md's first hard rule
says an excluded market is never described as a pass. #154's own test
docstring names the symptom ("The next morning graded every game 'No
play'"), but no test asserted anything about the rendered pick.

Found by the failure-shape audit and confirmed by 3 of 3 refuters.
Reproduced on the unfixed code with this module's harness (the real `main()`
run twice, the Results adapter rendered under node):

* Unpriced board: 2 of 2 games published that placeholder and rendered as
  "No play" / "— · −0" / "Push".
* Staged board: the priced game with no pick (BOS @ NYI) rendered exactly
  the same way, so the page could not tell an unpriced game from a priced
  pass.
* Refuters, on the real lab data and the real 2026-09-29 opening-night
  slate: 5 of 5 games rendered as a graded "No play" Push.

`summary.picks` never counted the placeholder, so no tally was wrong. What
the page got wrong was the words, and it got them wrong every morning after
an unpriced board.

The fix: settle carries the frozen board's `priced` onto each results row
and publishes `pick: null` for a game that had no pick. The adapter labels
an unpriced game "Not priced" and a priced game with no pick "No play". It
grades neither and shows no price for either. Only a real pick gets a Win,
Loss or Push.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    CLUBS,
    SLATE,
    _price_rows,
    _write_csv,
    build,
    make_lab,
    render_results,
)

NEXT_DAY = BOARD_DAY + timedelta(days=1)

#: What resultPick prints in the result box for a graded pick. No game
#: without a pick may show any of them.
GRADES = {"Win", "Loss", "Push", "Void"}


def _settled(tmp_path: Path, monkeypatch, lab: Path) -> tuple[dict, dict, dict]:
    """The board night, then the next morning with finals, through main()."""
    out = tmp_path / "out"
    board, _ = build(lab, out, monkeypatch)
    _, results = build(lab, out, monkeypatch, day=NEXT_DAY, finals=True)
    assert len(results["games"]) == len(SLATE), results["games"]
    page = render_results(results, tmp_path)
    return board, results, page


def _by_home(games: list[dict], home) -> dict:
    return {home(g): g for g in games}


def _shown(game: dict) -> str:
    pick = game["pick"]
    return " | ".join(str(pick[key]) for key in ("label", "market", "result"))


def _assert_not_graded(game: dict) -> None:
    """A game with no pick gets no grade and no price on the page."""
    shown = _shown(game)
    assert game["pick"]["result"] not in GRADES, (
        f"a game with no pick was graded on the Results page: {shown}"
    )
    assert "−0" not in shown and "-0" not in shown, (
        f"the page printed a price nobody quoted: {shown}"
    )


def _partly_priced_lab(tmp_path: Path, monkeypatch) -> Path:
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    rows = [r for r in _price_rows() if r["home_team"] == CLUBS["TOR"][2]]
    _write_csv(lab / "data" / "staging" / "odds_api_prices_staging.csv", rows)
    return lab


def test_the_morning_after_an_unpriced_board_no_game_is_called_a_play(
    tmp_path: Path, monkeypatch
) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)

    board, results, page = _settled(tmp_path, monkeypatch, lab)

    assert [g["priced"] for g in board["games"]] == [False] * len(SLATE)
    for game in results["games"]:
        assert game["pick"] is None, (
            f"results.json gave an unpriced game a pick: {game['pick']}"
        )
        assert game["priced"] is False, game
    assert results["summary"]["picks"] == {"w": 0, "l": 0, "p": 0}
    for game in page["games"]:
        shown = _shown(game)
        assert game["hasPick"] is True, "the page must say why there is no pick"
        assert game["pick"]["label"] == "Not priced", shown
        assert "no market price" in game["pick"]["market"], shown
        assert "No play" not in shown, (
            f"a game no price reached was published as a model pass: {shown}"
        )
        _assert_not_graded(game)


def test_a_priced_game_with_no_pick_is_a_pass_and_a_pick_is_still_graded(
    tmp_path: Path, monkeypatch
) -> None:
    """The companion: prices staged, TOR carries the card's best bet and
    NYI carries a price and no pick. Keeps the unpriced test from passing on
    a page that never grades anything, or calls everything unpriced."""
    lab = make_lab(tmp_path, monkeypatch, staged=True)

    _, results, page = _settled(tmp_path, monkeypatch, lab)

    rows = _by_home(results["games"], lambda g: g["home"]["abbr"])
    assert rows["TOR"]["pick"] == {
        "kind": "bet", "market": "Moneyline", "label": "TOR +112", "price": 112, "edgePct": 11.0, "result": "win",
    }
    assert rows["NYI"]["pick"] is None and rows["NYI"]["priced"] is True, rows["NYI"]
    assert results["summary"]["picks"] == {"w": 1, "l": 0, "p": 0}

    shown = _by_home(page["games"], lambda g: g["sides"][1]["abbr"])
    tor = shown["TOR"]["pick"]
    assert (tor["label"], tor["market"], tor["result"]) == ("TOR +112", "Moneyline · +112", "Win")
    nyi = shown["NYI"]
    assert nyi["hasPick"] is True and nyi["pick"]["label"] == "No play", _shown(nyi)
    assert "Not priced" not in _shown(nyi), (
        "a game the board priced was published as unpriced"
    )
    _assert_not_graded(nyi)


def test_a_partly_priced_board_settles_each_game_on_its_own(
    tmp_path: Path, monkeypatch
) -> None:
    lab = _partly_priced_lab(tmp_path, monkeypatch)

    board, results, page = _settled(tmp_path, monkeypatch, lab)

    assert {g["home"]["abbr"]: g["priced"] for g in board["games"]} == {"TOR": True, "NYI": False}
    shown = _by_home(page["games"], lambda g: g["sides"][1]["abbr"])
    assert shown["TOR"]["pick"]["label"] == "TOR +112"
    assert shown["TOR"]["pick"]["result"] == "Win"
    assert shown["NYI"]["pick"]["label"] == "Not priced", _shown(shown["NYI"])
    _assert_not_graded(shown["NYI"])


@pytest.mark.parametrize(
    ("staged", "expected"),
    [(True, "No play"), (False, "Not priced")],
    ids=["legacy-priced-pass", "legacy-unpriced"],
)
def test_a_board_frozen_before_the_priced_flag_settles_by_its_lines(
    tmp_path: Path, monkeypatch, staged: bool, expected: str
) -> None:
    """A board frozen before #154 carries no `priced`. Every version of the
    builder attached `moneyline` under exactly the condition that now sets
    `priced`, so the line says whether the game was priced. Such a board
    must neither turn a real pass into "Not priced" nor an unpriced game
    into "No play"."""
    lab = make_lab(tmp_path, monkeypatch, staged=True) if staged else _partly_priced_lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)
    frozen = out / "history" / f"{BOARD_DAY.isoformat()}.json"
    legacy = json.loads(frozen.read_text(encoding="utf-8"))
    for game in legacy["games"]:
        del game["priced"]
    frozen.write_text(json.dumps(legacy), encoding="utf-8")

    _, results = build(lab, out, monkeypatch, day=NEXT_DAY, finals=True)

    rows = _by_home(results["games"], lambda g: g["home"]["abbr"])
    assert rows["NYI"]["pick"] is None
    assert rows["NYI"]["priced"] is staged, rows["NYI"]
    assert rows["TOR"]["priced"] is True and rows["TOR"]["pick"]["result"] == "win"
    nyi = _by_home(render_results(results, tmp_path)["games"], lambda g: g["sides"][1]["abbr"])["NYI"]
    assert nyi["pick"]["label"] == expected, _shown(nyi)
    _assert_not_graded(nyi)


def test_a_results_row_that_does_not_say_it_was_priced_is_never_a_pass(
    tmp_path: Path,
) -> None:
    """The page reads a pass only off `priced: true`. A row that does not
    say is not described as the model passing on it."""
    results = {
        "generatedAt": "2026-10-09T15:00:00Z", "season": "2026–27", "resultsDate": BOARD_DAY.isoformat(),
        "summary": {"straightUp": {"w": 1, "l": 0}, "picks": {"w": 0, "l": 0, "p": 0}, "totals": {"w": 0, "l": 0, "p": 0}},
        "teams": {},
        "games": [{"id": "1", "startUtc": f"{BOARD_DAY.isoformat()}T23:00:00Z", "finish": "REG", "projWinner": "TOR",
                   "away": {"abbr": "MTL", "projGoals": 2.5, "final": 2},
                   "home": {"abbr": "TOR", "projGoals": 3.1, "final": 5}, "pick": None}],
    }

    game = render_results(results, tmp_path)["games"][0]

    assert "No play" not in _shown(game), _shown(game)
    _assert_not_graded(game)
