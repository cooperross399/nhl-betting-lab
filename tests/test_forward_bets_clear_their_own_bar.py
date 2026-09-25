"""The forward report's opinion/bet split had a test that could not fail.

`build_forward_report` keeps two streams apart: **opinions**, every settled
wager the model held a view on, and **bets**, the subset whose frozen edge
clears its own market's bar — `MIN_PROP_EDGE` for a prop, `MIN_EDGE` for a
team market, `>=` as the card and the backtests apply it. The only test of
that split (`test_the_report_separates_opinions_from_bets`) froze one
`shots_on_goal` row at edge 0.165, which clears both bars, and asserted one
opinion and one bet — true whatever the filter does. Found by the
failure-shape audit and confirmed by three of three refuters: with every
settled opinion counted as a bet (`bets = subset`, m18) the whole suite gave
1768 passed, and with the two bars swapped (m19) it gave 1768 passed.

Neither mutant is harmless. In the audit's reproduction through the real
freeze, settle and report path on a four-row day, m18 turned a moneyline opinion with a 0.0095 edge
into a bet and published that market as 2 bets at +87.1%, interval +79.7% ..
+94.5%, "Includes zero: no", and made a 0.045 `points` opinion a bet too; m19
dropped the real 0.045 moneyline bet and made that `points` opinion a bet
instead. `forward_evidence.md` is published to card-feed every day of the
season, and this is the stream an allowlist decision will eventually rest on.

The production filter was correct throughout; what was missing was a test
that could tell it from a broken one. These tests freeze a slate as the card
does (`write_snapshot`), settle and publish it with the real runner
(`scripts/run_forward_evidence.py`), and read the JSON and Markdown it
writes. Every edge is placed relative to the bars read from config, and the
fixture asserts its own placement, so a later bar change cannot quietly make
these tests vacuous again:

* per market, the bets are exactly the rows that clear THAT market's bar — a
  prop between the bars is an opinion, a team row between them is a bet, a
  row below both is neither — and profit and ROI are summed over the bets
  alone;
* a frozen edge exactly at its bar is a bet and one a hair below it is not,
  in both market families.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import MIN_EDGE, MIN_PROP_EDGE, PROJECT_ROOT
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOG_COLUMNS,
    PLAYER_LOGS_FILENAME,
    TEAM_GAME_COLUMNS,
    TEAM_GAMES_FILENAME,
)
from nhl_betting_lab.models.value import american_to_implied, profit_on_win
from nhl_betting_lab.providers import team_names
from nhl_betting_lab.reports.card_pricing import selection_key


#: The card freezes the 2026-10-08 slate that morning, before either face-off.
FROZEN_AT = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
SNAPSHOT_DATE = "2026-10-08"

#: Keyed the way production keys it: normalized lowercase provider names.
TEAM_MAP = {
    "toronto maple leafs": "TOR",
    "boston bruins": "BOS",
    "carolina hurricanes": "CAR",
    "new york islanders": "NYI",
}

#: Between the two bars: clears the team bar, not the prop bar.
BETWEEN = (MIN_EDGE + MIN_PROP_EDGE) / 2
#: Below both bars.
BELOW_BOTH = MIN_EDGE / 3
#: Above both bars.
ABOVE_BOTH = MIN_PROP_EDGE + 0.04
#: Close enough to a bar that only an exact comparison separates them.
HAIR = 1e-9

TORONTO = {
    "commence_time": "2026-10-09T00:10:00Z",  # league date 2026-10-08
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
}
CAROLINA = {
    "commence_time": "2026-10-08T23:10:00Z",  # league date 2026-10-08
    "home_team": "Carolina Hurricanes",
    "away_team": "New York Islanders",
}


def _prop(game: dict, player: str, selection: str, line: float, odds: float,
          market: str = "shots_on_goal") -> dict:
    return {**game, "market": market, "player": player, "selection": selection,
            "line": line, "american_odds": odds, "book": "DraftKings"}


def _moneyline(game: dict, selection: str, odds: float) -> dict:
    return {**game, "market": "moneyline", "player": "", "selection": selection,
            "line": None, "american_odds": odds, "book": "FanDuel"}


def _key(row: dict) -> tuple:
    line = row["line"]
    return selection_key(
        SimpleNamespace(**row), market=row["market"],
        selection=row["selection"], line=None if line is None else float(line),
    )


def _exact_price(bar: float) -> float:
    """The first plus-money price whose frozen edge lands EXACTLY on `bar`.

    `write_snapshot` freezes `probability - implied`, so a probability of
    `implied + bar` returns `bar` only when the float arithmetic is exact,
    which depends on the price. Searched, not hard-coded, so this still finds
    one if a bar moves.
    """
    for odds in range(100, 1000):
        implied = american_to_implied(odds)
        if (implied + bar) - implied == bar:
            return float(odds)
    raise AssertionError(f"no price from +100 to +999 freezes an edge of exactly {bar}")


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_forward_evidence.py"
    spec = importlib.util.spec_from_file_location(
        "_script_run_forward_evidence_bars", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _log(player_id: int, player: str, team: str, *, shots: float = 0.0,
         points: float = 0.0) -> dict:
    row = {column: 0 for column in PLAYER_LOG_COLUMNS}
    row.update({"game_id": 1 if team in {"TOR", "BOS"} else 2,
                "season": 20262027, "game_type": 2, "date": SNAPSHOT_DATE,
                "player_id": player_id, "player": player, "team": team,
                "shots_on_goal": shots, "points": points, "goals": 0,
                "assists": points})
    return row


def _publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    slate: list[tuple[dict, float]],
    logs: list[dict],
) -> SimpleNamespace:
    """Freeze `slate` — (price row, frozen edge) — as the card does, settle
    and publish it with the real runner, and return what it wrote.

    Toronto beat Boston 4-2 and the Islanders won 3-1 at Carolina, both in
    regulation. Nothing reads or writes the real data tree.
    """
    home = tmp_path / "home"
    monkeypatch.setattr(fe, "DATA_DIR", home / "data")
    monkeypatch.setattr(team_names, "PROCESSED_DIR", home / "data" / "processed")
    monkeypatch.setattr(team_names, "RAW_DIR", home / "data" / "raw")
    module = load_script()
    monkeypatch.setattr(module, "PROCESSED_DIR", home / "data" / "processed")
    monkeypatch.setattr(module, "OUTPUTS_DIR", home / "data" / "outputs")

    scratch = tmp_path / "scratch"
    processed = scratch / "processed"
    outputs = scratch / "outputs"
    processed.mkdir(parents=True)
    games = []
    for game_id, (home_team, away_team, home_goals, away_goals) in enumerate(
        [("TOR", "BOS", 4, 2), ("CAR", "NYI", 1, 3)], start=1
    ):
        game = {column: 0 for column in TEAM_GAME_COLUMNS}
        game.update({"game_id": game_id, "season": 20262027, "game_type": 2,
                     "date": SNAPSHOT_DATE, "home_team": home_team,
                     "away_team": away_team, "home_goals": home_goals,
                     "away_goals": away_goals, "regulation": True})
        games.append(game)
    pd.DataFrame(games, columns=list(TEAM_GAME_COLUMNS)).to_csv(
        processed / TEAM_GAMES_FILENAME, index=False
    )
    pd.DataFrame(logs, columns=list(PLAYER_LOG_COLUMNS)).to_csv(
        processed / PLAYER_LOGS_FILENAME, index=False
    )
    team_names.save_team_name_map(TEAM_MAP, processed_dir=processed)

    rows = [row for row, _ in slate]
    probabilities = {
        _key(row): american_to_implied(row["american_odds"]) + edge
        for row, edge in slate
    }
    assert len(probabilities) == len(slate), "two fixture rows share a wager key"
    # The archive a scratch run reads: `<--output-dir>/archive`.
    frozen = fe.write_snapshot(
        pd.DataFrame(rows),
        probabilities,
        key_for=selection_key,
        verdicts_line="props_b2b=in force; team_b2b=in force",
        snapshot_date=SNAPSHOT_DATE,
        now=FROZEN_AT,
        archive_dir=outputs / "archive",
    )
    assert frozen is not None
    snapshot = pd.read_csv(frozen)
    assert len(snapshot) == len(slate), "every fixture row must be frozen"

    code = module.main(
        ["--processed-dir", str(processed), "--output-dir", str(outputs)]
    )
    assert code == 0
    ledger = fe.load_ledger(processed)
    assert len(ledger) == len(slate)
    assert set(ledger["outcome"]) <= {"won", "lost"}, ledger["outcome"].tolist()
    payload = json.loads(
        (outputs / fe.REPORT_JSON_FILENAME).read_text(encoding="utf-8")
    )
    markdown = (outputs / fe.REPORT_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    assert payload["rows"] == len(slate) and payload["wagers"] == len(slate), (
        "every fixture row is its own wager; the collapse must keep them all"
    )
    return SimpleNamespace(
        payload=payload, markdown=markdown, snapshot=snapshot, ledger=ledger
    )


def _frozen_edge(frame: pd.DataFrame, game: dict, market: str,
                 selection: str, player: str = "") -> float:
    """The edge `frame` holds for one fixture row, read back off disk."""
    players = frame["player"].fillna("").astype(str)
    match = frame[(frame["home_team"] == game["home_team"])
                  & (frame["market"] == market) & (players == player)
                  & (frame["selection"] == selection)]
    assert len(match) == 1, (game["home_team"], market, selection, player)
    return float(match.iloc[0]["edge"])


def test_each_markets_bets_are_the_rows_that_clear_its_own_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prop between the bars is an opinion; a team row between them is a
    bet; below both, neither. Profit and ROI come from the bets alone.

    Four of the six rows that do not clear their bar won, and the one bet
    in `shots_on_goal` lost, so a report that let them in would be both
    miscounted and flattered."""
    slate = [
        # shots_on_goal (prop bar): one bet, which lost.
        (_prop(TORONTO, "Auston Matthews", "over", 2.5, 120), ABOVE_BOTH),
        (_prop(TORONTO, "Mitch Marner", "over", 2.5, 110), BETWEEN),
        (_prop(TORONTO, "David Pastrnak", "under", 2.5, -125), BELOW_BOTH),
        # moneyline (team bar): both sides of both games; one bet, which won.
        (_moneyline(TORONTO, "home", -110), BETWEEN),
        (_moneyline(TORONTO, "away", 105), -0.08),
        (_moneyline(CAROLINA, "home", -130), BELOW_BOTH),
        (_moneyline(CAROLINA, "away", 115), MIN_EDGE - 0.005),
        # points (prop bar): an opinion between the bars and no bet at all.
        (_prop(TORONTO, "Auston Matthews", "over", 0.5, -150, market="points"),
         BETWEEN),
    ]
    logs = [
        _log(8479318, "Auston Matthews", "TOR", shots=1, points=1),
        _log(8478483, "Mitch Marner", "TOR", shots=4, points=0),
        _log(8477956, "David Pastrnak", "BOS", shots=1, points=0),
    ]
    # Every placement leans on this order. If the bars ever move so that it
    # fails, re-place the fixture; do not loosen the assertions below.
    assert 0 < BELOW_BOTH < MIN_EDGE < BETWEEN < MIN_PROP_EDGE < ABOVE_BOTH

    published = _publish(tmp_path, monkeypatch, slate, logs)
    markets = published.payload["markets"]

    # What the card froze sits where the fixture says, relative to the bars.
    snap = published.snapshot
    assert _frozen_edge(snap, TORONTO, "shots_on_goal", "over", "Mitch Marner") < MIN_PROP_EDGE
    assert _frozen_edge(snap, TORONTO, "shots_on_goal", "over", "Mitch Marner") > MIN_EDGE
    assert _frozen_edge(snap, TORONTO, "moneyline", "home") > MIN_EDGE
    assert _frozen_edge(snap, TORONTO, "points", "over", "Auston Matthews") < MIN_PROP_EDGE

    assert sorted(markets) == ["moneyline", "points", "shots_on_goal"]

    shots = markets["shots_on_goal"]
    assert (shots["opinions"], shots["bets"]) == (3, 1), (
        "shots_on_goal: only the row above the PROP bar is a bet; the row "
        "between the bars clears only the team bar"
    )
    assert shots["profit_units"] == pytest.approx(-1.0)
    assert shots["roi"] == pytest.approx(-1.0)

    moneyline = markets["moneyline"]
    assert (moneyline["opinions"], moneyline["bets"]) == (4, 1), (
        "moneyline: the row between the bars clears the TEAM bar and is a "
        "bet; the rows below it are opinions only"
    )
    assert moneyline["profit_units"] == pytest.approx(profit_on_win(-110))
    assert moneyline["roi"] == pytest.approx(profit_on_win(-110))

    points = markets["points"]
    assert (points["opinions"], points["bets"]) == (1, 0)
    assert "profit_units" not in points and "roi" not in points
    assert "No settled row has yet cleared the shipped edge bar" in points["verdict"]

    # And the page card-feed publishes says the same.
    assert "| `shots_on_goal` | 3 | 1 | -1.0u | -100.0% |" in published.markdown
    assert "| `moneyline` | 4 | 1 | +0.9u | +90.9% |" in published.markdown
    assert "| `points` | 1 | 0 | — | — | — | — |" in published.markdown


def test_an_edge_exactly_at_its_bar_is_a_bet_and_a_hair_below_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card stakes `edge >= bar` (`gameday_card.build_candidates` passes
    only `edge < bar`), and the backtests skip only `edge < threshold`, so
    the forward bets must use the same boundary in both market families."""
    prop_price = _exact_price(MIN_PROP_EDGE)
    team_price = _exact_price(MIN_EDGE)
    slate = [
        (_prop(TORONTO, "Auston Matthews", "over", 2.5, prop_price), MIN_PROP_EDGE),
        (_prop(TORONTO, "Mitch Marner", "over", 2.5, 110), MIN_PROP_EDGE - HAIR),
        (_moneyline(CAROLINA, "away", team_price), MIN_EDGE),
        (_moneyline(TORONTO, "home", -110), MIN_EDGE - HAIR),
    ]
    logs = [
        _log(8479318, "Auston Matthews", "TOR", shots=4),
        _log(8478483, "Mitch Marner", "TOR", shots=1),
    ]
    # HAIR must be tiny against both bars, or "a hair below" is not at the
    # boundary and this pins nothing a looser comparison would miss.
    assert 0 < HAIR < min(MIN_EDGE, MIN_PROP_EDGE) / 1000

    published = _publish(tmp_path, monkeypatch, slate, logs)

    # Exactly at the bar, as frozen and as settled — or this pins nothing.
    for frame in (published.snapshot, published.ledger):
        assert _frozen_edge(frame, TORONTO, "shots_on_goal", "over", "Auston Matthews") == MIN_PROP_EDGE
        assert _frozen_edge(frame, CAROLINA, "moneyline", "away") == MIN_EDGE
        assert _frozen_edge(frame, TORONTO, "shots_on_goal", "over", "Mitch Marner") < MIN_PROP_EDGE
        assert _frozen_edge(frame, TORONTO, "moneyline", "home") < MIN_EDGE

    markets = published.payload["markets"]
    shots = markets["shots_on_goal"]
    assert (shots["opinions"], shots["bets"]) == (2, 1), (
        f"a prop frozen at exactly {MIN_PROP_EDGE} clears the bar; "
        f"{MIN_PROP_EDGE} - {HAIR} does not"
    )
    assert shots["profit_units"] == pytest.approx(profit_on_win(prop_price))

    moneyline = markets["moneyline"]
    assert (moneyline["opinions"], moneyline["bets"]) == (2, 1), (
        f"a team row frozen at exactly {MIN_EDGE} clears the bar; "
        f"{MIN_EDGE} - {HAIR} does not"
    )
    assert moneyline["profit_units"] == pytest.approx(profit_on_win(team_price))
