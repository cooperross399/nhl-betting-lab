"""A lean is never published as a best bet.

`web/build_site_json.py::build_board` chose each game's `pick` from every
card row outside "Passes / notable avoids", so the card's leans were
eligible alongside its best bets. It took the highest-edge row and set no
`kind`, and `web/lib/sports.js`'s NHL adapter defaults a pick without a kind
to "bet". A lean therefore reached the page headed "Best bet", was counted
in the board strip's "best bets", in `history/index.json`'s `bets` (which
`web/site_history.py` counts with the same default), and the next morning
was graded into the Results page's "Model picks" record.

A lean is not a small best bet. It is a row the card declined to stake:
below the best-bet bar, or in a market the stake gate withholds
(STAKE_EXCLUDED_MARKETS), or a rung one-stake-per-outcome demoted. Its edge
can be the largest on the game precisely because the thing that stopped it
is not the edge, so "highest edge wins" let the unstaked row outrank the
game's real best bet.

It could not fire while Publish Site stages no prices (no game is `priced`,
so no pick is attached at all). It fires on the first build that carries
prices. These tests stage them.

The builder is driven through its own `main()` with only the NHL schedule
stubbed, the card is written by the real `save_card`, the history index by
the real `web/site_history.py`, and the page is rendered through
`web/lib/sports.js` under node, all with the fixtures of
tests/test_site_never_calls_an_unpriced_game_a_pass.py.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    GamedayCard,
    LEANS_SECTION,
    save_card,
)

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    SLATE,
    WEB,
    _candidate,
    build,
    make_lab,
    page_games,
    render_board,
    render_results,
)


def _card_with_leans(outputs: Path) -> None:
    """MTL @ TOR holds a best bet AND a lean with a larger edge; BOS @ NYI
    holds only a lean. Both leans are what the stake gate leaves behind: a
    real edge on a row the card will not stake."""
    card = GamedayCard(
        generated_at=f"{BOARD_DAY.isoformat()}T13:30:00+00:00", card_generated=True,
        slate_games=len(SLATE), included_markets=("moneyline", "puck_line", "total_goals"),
        best_bets=[_candidate("MTL", "TOR", market="moneyline", selection="home",
                              odds=112, edge=0.050, section=BEST_BETS_SECTION)],
        leans=[
            _candidate("MTL", "TOR", market="total_goals", selection="over",
                       odds=-110, edge=0.200, section=LEANS_SECTION, line=6.0),
            _candidate("BOS", "NYI", market="puck_line", selection="home",
                       odds=210, edge=0.090, section=LEANS_SECTION, line=-1.5),
        ],
    )
    save_card(card, output_dir=outputs)


def _lab(tmp_path: Path, monkeypatch) -> Path:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    _card_with_leans(lab / "data" / "outputs")
    return lab


def _game(board: dict, home: str) -> dict:
    return next(g for g in board["games"] if g["home"]["abbr"] == home)


def test_a_best_bet_outranks_a_larger_edged_lean(tmp_path: Path, monkeypatch) -> None:
    board, _ = build(_lab(tmp_path, monkeypatch), tmp_path / "out", monkeypatch)

    tor = _game(board, "TOR")
    assert tor["priced"] is True
    assert tor["pick"] is not None and tor["pick"]["market"] == "Moneyline", (
        f"the game's pick was {tor['pick']!r}: a lean with a larger edge "
        "displaced the card's best bet on the same game"
    )
    assert tor["pick"]["kind"] == "bet", tor["pick"]


def test_a_game_with_only_a_lean_publishes_a_lean(tmp_path: Path, monkeypatch) -> None:
    board, _ = build(_lab(tmp_path, monkeypatch), tmp_path / "out", monkeypatch)

    nyi = _game(board, "NYI")
    assert nyi["pick"] is not None, "the lean is the model's recorded side; it is still published"
    assert nyi["pick"]["kind"] == "lean", (
        f"a lean was published as {nyi['pick']!r}, which the page reads as a best bet"
    )


def test_the_page_heads_a_lean_as_a_lean_and_counts_one_best_bet(tmp_path: Path, monkeypatch) -> None:
    board, _ = build(_lab(tmp_path, monkeypatch), tmp_path / "out", monkeypatch)

    rendered = render_board(board, tmp_path)

    by_home = {g["sides"][1]["abbr"]: g["pick"] for g in page_games(rendered)}
    assert by_home["TOR"]["heading"] == "Best bet" and by_home["TOR"]["label"] == "TOR +112"
    assert by_home["NYI"]["heading"] == "Lean", by_home["NYI"]
    assert "not staked" in by_home["NYI"]["extra"], by_home["NYI"]
    summary = rendered["board"]["summary"]
    assert "· 1 best bets ·" in summary and "· 1 leans ·" in summary, summary
    graphic = {row["pickLabel"]: row for row in rendered["graphic"]["rows"]}
    assert graphic["TOR +112"]["pickBg"] != graphic[by_home["NYI"]["label"]]["pickBg"], (
        "the Graphic page drew the lean in the best bet's colours"
    )


def test_the_history_index_counts_no_lean_as_a_best_bet(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    build(_lab(tmp_path, monkeypatch), out, monkeypatch)

    spec = importlib.util.spec_from_file_location("_site_history_leans", WEB / "site_history.py")
    assert spec and spec.loader
    history = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(history)
    assert history.main(["--data", str(out)]) == 0

    index = json.loads((out / "history" / "index.json").read_text(encoding="utf-8"))
    entry = next(e for e in index["dates"] if e["date"] == BOARD_DAY.isoformat())
    assert entry["bets"] == 1, (
        f"history indexed {entry['bets']} best bets for a board holding one best bet and one lean"
    )


def test_the_results_grade_no_lean_as_a_model_pick(tmp_path: Path, monkeypatch) -> None:
    lab = _lab(tmp_path, monkeypatch)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)

    _, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    picks = results["summary"]["picks"]
    assert picks["w"] + picks["l"] + picks["p"] == 1, (
        f"the Model picks record {picks} graded the lean as a best bet"
    )
    nyi = next(g for g in results["games"] if g["home"]["abbr"] == "NYI")
    assert nyi["pick"]["kind"] == "lean" and nyi["pick"]["result"] in {"win", "loss", "push"}, (
        "the lean is still recorded and judged on its own row; it is only kept out of the bets"
    )
    page = render_results(results, tmp_path)
    shown = next(g for g in page["games"] if g["sides"][1]["abbr"] == "NYI")
    assert "Lean" in shown["pick"]["market"], (
        f"the Results page showed the lean as {shown['pick']!r}, indistinguishable from a best bet"
    )
