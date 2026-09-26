"""An exhibition game is published as schedule only, whatever else is on the night.

`web/build_site_json.py::build_board` decided "preseason" once for the whole
day, `all(gameType == 1)`, and its per-game loop never read a game's own
`gameType`. So on a mixed night — one regular-season game and one exhibition,
the shape of 2026-09-29 — the board read `phase: regular`, gave BOTH games
`projGoals` and `winProb` (and, with staged prices, lines and the card's pick),
froze both into `history/<day>.json`, and `settle()` graded both the next
morning. The module's own docstring says preseason games are "published as
schedule only": the models are fitted on regular-season games, and the card
excludes exhibitions from the forward ledger. A projection the lab never made
on the card was being published, and scored, on the site.

These tests build a real mixed night through the builder's own `main()`
(only the NHL schedule is stubbed), then settle it the next morning, index it
through `web/site_history.py`, and render it through the page's own adapter.
Each exhibition is checked for what it must not carry, and the regular-season
game beside it for what it must still carry, so neither half passes
vacuously. The exhibition is taken both ways round: once as the game the
card holds a best bet for (so a pick would otherwise attach), once as the
other.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    SLATE,
    WEB,
    make_lab,
    page_games,
    render_board,
    render_results,
    schedule,
    site_module,
)

#: The figures only the model or the market can put on a game.
PROJECTED = ("projGoals", "winProb")
PRICED = ("moneyline", "puckLine", "total", "regulation")


def mixed_schedule(exhibition_id: str, *, final: bool, game_type: int = 1):
    """The shared slate with one game's gameType set to 1 (preseason)."""

    def schedule_for(day):
        games = schedule(day, final=final and day == BOARD_DAY)
        for game in games:
            if str(game["id"]) == exhibition_id:
                game["gameType"] = game_type
        return games

    return schedule_for


def build_mixed(lab: Path, out: Path, monkeypatch, exhibition_id: str):
    """Board for BOARD_DAY, then the next morning's build, which settles it."""
    module = site_module()
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline", "puck_line", "total_goals"])
    monkeypatch.setattr(module, "schedule_for", mixed_schedule(exhibition_id, final=False))
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", BOARD_DAY.isoformat()]) == 0
    board = json.loads((out / "board.json").read_text(encoding="utf-8"))
    frozen = json.loads((out / "history" / f"{BOARD_DAY.isoformat()}.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(module, "schedule_for", mixed_schedule(exhibition_id, final=True))
    next_day = BOARD_DAY + timedelta(days=1)
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", next_day.isoformat()]) == 0
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return board, frozen, results


def site_history():
    spec = importlib.util.spec_from_file_location("_site_history_exhibition", WEB / "site_history.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXHIBITION_IS = pytest.mark.parametrize(
    "exhibition_id",
    [SLATE[0][2], SLATE[1][2]],
    ids=["exhibition-is-the-carded-game", "exhibition-is-the-other-game"],
)


def _split(games: list[dict], exhibition_id: str) -> tuple[dict, dict]:
    exhibition = next(g for g in games if g["id"] == exhibition_id)
    regular = next(g for g in games if g["id"] != exhibition_id)
    return exhibition, regular


@EXHIBITION_IS
def test_the_exhibition_carries_no_projection_price_or_pick(tmp_path: Path, monkeypatch, exhibition_id: str) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)

    board, frozen, _ = build_mixed(lab, tmp_path / "out", monkeypatch, exhibition_id)

    assert board["phase"] == "regular" and len(board["games"]) == len(SLATE)
    for published in (board, frozen):
        exhibition, regular = _split(published["games"], exhibition_id)
        for side in ("home", "away"):
            leaked = [k for k in PROJECTED if k in exhibition[side]]
            assert not leaked, f"an exhibition game was published with {leaked} on the {side} side"
        leaked = [k for k in PRICED if k in exhibition]
        assert not leaked, f"an exhibition game was published with market figures {leaked}"
        assert exhibition["pick"] is None
        assert exhibition["priced"] is False
        assert exhibition["gameType"] == 1
        # The regular-season game beside it is projected and priced as before.
        assert all(k in regular[side] for k in PROJECTED for side in ("home", "away"))
        assert regular["priced"] is True and "moneyline" in regular
        assert regular["gameType"] == 2


def test_the_regular_game_keeps_its_pick_beside_an_exhibition(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)

    board, _, _ = build_mixed(lab, tmp_path / "out", monkeypatch, SLATE[1][2])

    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert tor["pick"] == {"market": "Moneyline", "label": "TOR +112", "price": 112, "edgePct": 11.0}


@EXHIBITION_IS
def test_settlement_grades_the_regular_game_and_not_the_exhibition(tmp_path: Path, monkeypatch, exhibition_id: str) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)

    _, _, results = build_mixed(lab, tmp_path / "out", monkeypatch, exhibition_id)

    settled = [g["id"] for g in results["games"]]
    regular_id = next(gid for _, _, gid in SLATE if gid != exhibition_id)
    assert settled == [regular_id], f"the morning after settled {settled}; only the regular-season game may be graded"
    su = results["summary"]["straightUp"]
    assert su["w"] + su["l"] == 1, f"straight up counted {su} over one regular-season game"
    picks = results["summary"]["picks"]
    expected_picks = 1 if regular_id == SLATE[0][2] else 0
    assert picks["w"] + picks["l"] + picks["p"] == expected_picks, picks
    rendered = render_results(results, tmp_path)
    assert rendered["count"] == 1


@EXHIBITION_IS
def test_the_archive_counts_no_bet_on_the_exhibition(tmp_path: Path, monkeypatch, exhibition_id: str) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    module = site_module()
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline", "puck_line", "total_goals"])
    monkeypatch.setattr(module, "schedule_for", mixed_schedule(exhibition_id, final=False))
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", BOARD_DAY.isoformat()]) == 0

    assert site_history().main(["--data", str(out)]) == 0

    index = json.loads((out / "history" / "index.json").read_text(encoding="utf-8"))
    entry = next(e for e in index["dates"] if e["date"] == BOARD_DAY.isoformat())
    # The card's one best bet is MTL @ TOR. It counts only while that game
    # is the regular-season one.
    assert entry["bets"] == (0 if exhibition_id == SLATE[0][2] else 1), entry
    lines = json.loads((out / "history" / "lines" / f"{BOARD_DAY.isoformat()}.json").read_text(encoding="utf-8"))
    assert not lines.get(exhibition_id), f"a line series was recorded for the exhibition: {lines.get(exhibition_id)}"


@EXHIBITION_IS
def test_the_page_says_the_model_abstains_on_the_exhibition(tmp_path: Path, monkeypatch, exhibition_id: str) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    board, _, _ = build_mixed(lab, tmp_path / "out", monkeypatch, exhibition_id)

    games = page_games(render_board(board, tmp_path))
    exhibition_abbr = next(home for _, home, gid in SLATE if gid == exhibition_id)
    shown = next(g for g in games if g["sides"][1]["abbr"] == exhibition_abbr)
    # "Not priced" would say a price failed to arrive; nobody looked for one.
    assert shown["pick"]["label"] == "Exhibition · model abstains", shown["pick"]
    other = next(g for g in games if g["sides"][1]["abbr"] != exhibition_abbr)
    assert other["pick"]["label"] != "Exhibition · model abstains"


def test_any_game_that_is_not_regular_season_is_schedule_only(tmp_path: Path, monkeypatch) -> None:
    """Not only gameType 1. The card prices regular-season games alone
    (`season.known_regular_season_games`), so a playoff game (3) beside a
    regular-season one is no more the model's than an exhibition, and the page
    does not call it one."""
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    out = tmp_path / "out"
    module = site_module()
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline"])
    monkeypatch.setattr(module, "schedule_for", mixed_schedule(SLATE[0][2], final=False, game_type=3))
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", BOARD_DAY.isoformat()]) == 0
    board = json.loads((out / "board.json").read_text(encoding="utf-8"))

    other, regular = _split(board["games"], SLATE[0][2])
    assert other["gameType"] == 3 and other["pick"] is None and "projGoals" not in other["home"]
    assert "moneyline" not in other and "projGoals" in regular["home"]
    shown = next(g for g in page_games(render_board(board, tmp_path)) if g["sides"][1]["abbr"] == "TOR")
    assert shown["pick"]["label"] == "Not a regular-season game · model abstains", shown["pick"]
