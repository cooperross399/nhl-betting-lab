"""A published pick carries the side and line the page's live status reads.

`web/lib/live.js::pickStatus` judges a team pick against the live score from
`pick.side` (home, away, over, under) and, for a total, `pick.line`. The
builder published only `kind`, `market`, `label`, `price` and `edgePct`, so
every pick's live status read "unavailable" on a real board while the sample
fixtures, which carry both fields, looked fine.

Driven through the builder's own `main()` with the fixtures of
tests/test_a_lean_is_never_published_as_a_best_bet.py.
"""

from __future__ import annotations

from pathlib import Path

from nhl_betting_lab.reports.gameday_card import BEST_BETS_SECTION, GamedayCard, save_card

from test_site_never_calls_an_unpriced_game_a_pass import BOARD_DAY, SLATE, _candidate, build, make_lab


def _lab(tmp_path: Path, monkeypatch) -> Path:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    card = GamedayCard(
        generated_at=f"{BOARD_DAY.isoformat()}T13:30:00+00:00", card_generated=True,
        slate_games=len(SLATE), included_markets=("moneyline", "puck_line", "total_goals"),
        best_bets=[
            _candidate("MTL", "TOR", market="moneyline", selection="away",
                       odds=140, edge=0.11, section=BEST_BETS_SECTION),
            _candidate("BOS", "NYI", market="total_goals", selection="under",
                       odds=-105, edge=0.12, section=BEST_BETS_SECTION, line=6.5),
        ],
    )
    save_card(card, output_dir=lab / "data" / "outputs")
    return lab


def _pick(board: dict, home: str) -> dict:
    return next(g for g in board["games"] if g["home"]["abbr"] == home)["pick"]


def test_a_moneyline_pick_names_its_side_and_no_line(tmp_path: Path, monkeypatch) -> None:
    board, _ = build(_lab(tmp_path, monkeypatch), tmp_path / "out", monkeypatch)
    pick = _pick(board, "TOR")
    assert pick["market"] == "Moneyline", pick
    assert pick["side"] == "away" and pick["line"] is None, pick


def test_a_total_pick_names_its_side_and_its_line(tmp_path: Path, monkeypatch) -> None:
    board, _ = build(_lab(tmp_path, monkeypatch), tmp_path / "out", monkeypatch)
    pick = _pick(board, "NYI")
    assert pick["market"] == "Total", pick
    assert pick["side"] == "under" and pick["line"] == 6.5, pick
