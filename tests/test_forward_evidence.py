"""The forward-evidence organ: freeze, settle, accumulate, report.

The historical backtest re-prices the past with walk-forward fits. This
stream is the stronger thing: the opinion the live card actually held,
written down before puck drop and never revised. These tests protect the
three properties that make it evidence — a snapshot cannot be overwritten, a
day settles as a unit or not at all, and settlement only appends.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key


NOW = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
TEAM_NAMES = {
    "toronto maple leafs": "TOR",
    "boston bruins": "BOS",
    "carolina hurricanes": "CAR",
    "new york islanders": "NYI",
}


def _price_row(**overrides) -> dict:
    row = {
        "commence_time": "2026-10-09T00:10:00Z",  # league date 2026-10-08
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 3.5,
        "american_odds": 120,
        "book": "DraftKings",
    }
    row.update(overrides)
    return row


def _snapshot(tmp_path: Path, rows: list[dict], probabilities=None) -> Path:
    prices = pd.DataFrame(rows)
    if probabilities is None:
        probabilities = {}
        for raw in rows:
            row = SimpleNamespace(**raw)
            line = raw.get("line")
            probabilities[
                selection_key(
                    row,
                    market=raw["market"],
                    selection=raw["selection"],
                    line=None if line is None else float(line),
                )
            ] = 0.62
    path = fe.write_snapshot(
        prices,
        probabilities,
        key_for=selection_key,
        verdicts_line="props_b2b=in force",
        snapshot_date="2026-10-08",
        archive_dir=tmp_path,
    )
    assert path is not None
    return path


def _logs(shots: float = 5.0, dressed: bool = True) -> pd.DataFrame:
    if not dressed:
        return pd.DataFrame(columns=["date", "player_id", "player", "team",
                                     "shots_on_goal", "points", "goals",
                                     "assists", "blocked_shots", "hits",
                                     "saves"])
    return pd.DataFrame(
        [
            {
                "date": "2026-10-08",
                "player_id": 8479318,
                "player": "Auston Matthews",
                "team": "TOR",
                "shots_on_goal": shots,
                "points": 1.0,
                "goals": 1.0,
                "assists": 0.0,
                "blocked_shots": 0.0,
                "hits": 2.0,
                "saves": 0.0,
            }
        ]
    )


def _games(*, regulation: bool = True, home_goals: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": 1,
                "date": "2026-10-08",
                "home_team": "TOR",
                "away_team": "BOS",
                "home_goals": home_goals,
                "away_goals": 2,
                "regulation": regulation,
            }
        ]
    )


# -- freezing ----------------------------------------------------------


def test_a_snapshot_freezes_the_opinion_with_its_edge(tmp_path: Path) -> None:
    path = _snapshot(tmp_path, [_price_row()])
    frame = pd.read_csv(path)

    assert len(frame) == 1
    assert frame.iloc[0]["model_probability"] == pytest.approx(0.62)
    # +120 implies 45.45%; the frozen edge is against the price as sold.
    assert frame.iloc[0]["edge"] == pytest.approx(0.62 - 100 / 220, abs=1e-4)
    assert frame.iloc[0]["verdicts_in_force"] == "props_b2b=in force"


def test_the_first_opinion_of_the_day_stands(tmp_path: Path) -> None:
    """A repriced snapshot is not the card's opinion any more, and two
    snapshots for one day would let the flattering one settle."""
    _snapshot(tmp_path, [_price_row()])

    second = fe.write_snapshot(
        pd.DataFrame([_price_row(american_odds=200)]),
        {},
        key_for=selection_key,
        verdicts_line="x",
        snapshot_date="2026-10-08",
        archive_dir=tmp_path,
    )

    assert second is None
    frame = pd.read_csv(fe.snapshots_dir(tmp_path) / "2026-10-08.csv")
    assert frame.iloc[0]["american_odds"] == 120


def test_a_row_without_a_model_opinion_is_not_frozen(tmp_path: Path) -> None:
    """The snapshot is the card's opinions, not the provider's price list."""
    path = _snapshot(
        tmp_path,
        [_price_row(), _price_row(player="Nobody Priced")],
        probabilities={
            selection_key(
                SimpleNamespace(**_price_row()),
                market="shots_on_goal",
                selection="over",
                line=3.5,
            ): 0.62
        },
    )

    assert len(pd.read_csv(path)) == 1


# -- settling ----------------------------------------------------------


def _settle(tmp_path: Path, logs, games, now=NOW):
    return fe.settle_snapshots(
        logs,
        games,
        team_names=TEAM_NAMES,
        archive_dir=tmp_path,
        processed_dir=tmp_path / "processed",
        now=now,
    )


def test_a_winning_over_settles_from_the_boxscore(tmp_path: Path) -> None:
    _snapshot(tmp_path, [_price_row()])

    result = _settle(tmp_path, _logs(shots=5.0), _games())
    ledger = fe.load_ledger(tmp_path / "processed")

    assert result.rows_settled == 1
    assert ledger.iloc[0]["outcome"] == "won"
    assert ledger.iloc[0]["actual"] == 5.0
    assert ledger.iloc[0]["profit_units"] == pytest.approx(1.2)


def test_a_losing_over_costs_one_unit(tmp_path: Path) -> None:
    _snapshot(tmp_path, [_price_row()])

    _settle(tmp_path, _logs(shots=2.0), _games())
    ledger = fe.load_ledger(tmp_path / "processed")

    assert ledger.iloc[0]["outcome"] == "lost"
    assert ledger.iloc[0]["profit_units"] == pytest.approx(-1.0)


def test_a_player_who_never_entered_voids(tmp_path: Path) -> None:
    """Books return the stake; settling it as a loss would poison the
    ledger with lineup noise the model was never asked about."""
    _snapshot(tmp_path, [_price_row()])

    result = _settle(tmp_path, _logs(dressed=False), _games())
    ledger = fe.load_ledger(tmp_path / "processed")

    assert result.rows_void == 1
    assert ledger.iloc[0]["outcome"] == "void"
    assert ledger.iloc[0]["profit_units"] == 0.0


def test_a_team_market_row_settles_too(tmp_path: Path) -> None:
    _snapshot(
        tmp_path,
        [
            _price_row(
                market="moneyline", player="", selection="home", line=None,
                american_odds=-120,
            )
        ],
    )

    _settle(tmp_path, _logs(), _games(home_goals=4))
    ledger = fe.load_ledger(tmp_path / "processed")

    assert ledger.iloc[0]["outcome"] == "won"


def test_the_regulation_three_way_settles_a_late_winner_as_a_draw(
    tmp_path: Path,
) -> None:
    """The market this stream exists for, settled by the sport's own rule."""
    _snapshot(
        tmp_path,
        [
            _price_row(
                market="regulation_3_way", player="", selection="draw",
                line=None, american_odds=320,
            )
        ],
    )

    _settle(tmp_path, _logs(), _games(regulation=False, home_goals=3))
    ledger = fe.load_ledger(tmp_path / "processed")

    assert ledger.iloc[0]["outcome"] == "won"


def test_a_day_settles_as_a_unit_or_waits(tmp_path: Path) -> None:
    """Half a settled day would make the ledger's totals move twice for one
    day, and whichever half settled first would look like the whole."""
    _snapshot(
        tmp_path,
        [
            _price_row(),
            _price_row(
                home_team="Carolina Hurricanes",
                away_team="New York Islanders",
                player="Sebastian Aho",
            ),
        ],
    )

    # Only the Toronto game is final.
    result = _settle(tmp_path, _logs(), _games())

    assert result.snapshots_waiting == 1
    assert fe.load_ledger(tmp_path / "processed").empty


def test_patience_runs_out_and_the_missing_game_is_counted(
    tmp_path: Path,
) -> None:
    _snapshot(
        tmp_path,
        [
            _price_row(),
            _price_row(
                home_team="Carolina Hurricanes",
                away_team="New York Islanders",
                player="Sebastian Aho",
            ),
        ],
    )
    much_later = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)

    result = _settle(tmp_path, _logs(), _games(), now=much_later)
    ledger = fe.load_ledger(tmp_path / "processed")

    assert result.rows_unsettleable == 1
    assert set(ledger["outcome"]) == {"won", "unsettleable"}


def test_settlement_is_idempotent(tmp_path: Path) -> None:
    """A settled day never settles twice; the ledger only ever appends."""
    _snapshot(tmp_path, [_price_row()])
    _settle(tmp_path, _logs(), _games())

    again = _settle(tmp_path, _logs(), _games())

    assert again.snapshots_seen == 0
    assert len(fe.load_ledger(tmp_path / "processed")) == 1


# -- the report --------------------------------------------------------


def test_an_empty_ledger_reports_the_preseason_truth(tmp_path: Path) -> None:
    payload = fe.build_forward_report(fe.load_ledger(tmp_path), now=NOW)

    rendered = fe.render_forward_report(payload)

    assert "correct state, not a fault" in rendered


def test_the_report_separates_opinions_from_bets(tmp_path: Path) -> None:
    """Mixing the calibration stream with the bet stream would flatter
    whichever is worse."""
    _snapshot(tmp_path, [_price_row()])
    _settle(tmp_path, _logs(shots=5.0), _games())

    payload = fe.build_forward_report(
        fe.load_ledger(tmp_path / "processed"), now=NOW
    )
    entry = payload["markets"]["shots_on_goal"]

    # Edge 0.165 clears the prop bar, so this row is both an opinion and a bet.
    assert entry["opinions"] == 1
    assert entry["bets"] == 1


def test_the_report_speaks_the_house_vocabulary(tmp_path: Path) -> None:
    _snapshot(tmp_path, [_price_row()])
    _settle(tmp_path, _logs(shots=5.0), _games())

    rendered = fe.render_forward_report(
        fe.build_forward_report(fe.load_ledger(tmp_path / "processed"), now=NOW)
    )

    assert "written down before puck drop" in rendered
    assert "never revised" in rendered
    assert "no demonstrated edge" in rendered
    assert "hits and the regulation three-way" in rendered


def test_an_empty_snapshot_settles_exactly_once(tmp_path: Path) -> None:
    """An empty day leaves no ledger trace, so without its own marker it
    would re-settle on every run forever — noise that trains the reader to
    ignore the settlement log."""
    fe.write_snapshot(
        pd.DataFrame(columns=["market"]),
        {},
        key_for=selection_key,
        verdicts_line="x",
        snapshot_date="2026-10-08",
        archive_dir=tmp_path,
    )

    first = _settle(tmp_path, _logs(), _games())
    second = _settle(tmp_path, _logs(), _games())

    assert first.snapshots_settled == 1
    assert second.snapshots_seen == 0
