"""The forward report called a written-off ledger the preseason state.

`render_forward_report` took one branch whenever no wager had settled won,
lost or push, and that branch read "## Nothing settled yet ... Before the
season starts this is the correct state, not a fault", whatever the ledger
held. An empty ledger is the preseason state. A ledger holding rows is not:
a row reaches it only once its game was found or its day waited out the
fourteen-day patience window, so every one of those rows is a game that was
played, or waited for, and produced no result here. The page is published
daily to card-feed as `latest_forward_evidence.md`.

Found by the failure-shape audit (finding 44, confirmed by two of three
refuters). Measured on the unfixed code, through the real settlement:

* the finder's ledger, two props for players who never dressed (void) and a
  total on a game with no final (unsettleable), rendered "Ledger rows: 3
  (2 void, 1 unsettleable)" and then "correct state, not a fault";
* the reachability refuter's ledger, the real 2026-27 opener (Boston v the
  Rangers, league date 2026-09-29) with its finals never fetched and the
  snapshot 16 days old, rendered "Ledger rows: 2 (0 void, 2 unsettleable)"
  and then the same reassurance. That is the quiet version of a broken
  results fetch: the runs stay green, settlement says "still waiting" for
  two weeks, writes the day off, and the report called the write-off normal.
  Card-feed reads "Ledger rows: 0" today, so this window opens for the first
  time with the opener.

What these tests hold, on ledgers written by the real `settle_snapshots` and
through the real runner:

* a ledger with rows and no won, lost or push is never "the correct state,
  not a fault" and never "Nothing settled yet": all-unsettleable, all-void,
  mixed, and rows that collapse to no wager at all;
* its section restates the void and unsettleable counts and says where to
  look;
* an empty ledger keeps the preseason text, word for word;
* one won row brings the table back, not either message.
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

from nhl_betting_lab import config
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOG_COLUMNS,
    PLAYER_LOGS_FILENAME,
    TEAM_GAME_COLUMNS,
    TEAM_GAMES_FILENAME,
)
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.providers.team_names import save_team_name_map
from nhl_betting_lab.reports.card_pricing import selection_key

#: Keyed exactly as `load_team_name_map` returns it: normalized name -> abbrev.
TEAM_MAP = {
    "boston bruins": "BOS",
    "new york rangers": "NYR",
    "toronto maple leafs": "TOR",
    "carolina hurricanes": "CAR",
    "new york islanders": "NYI",
}

#: The preseason paragraph, which an empty ledger must keep word for word.
PRESEASON = "correct state, not a fault"


@pytest.fixture(autouse=True)
def _no_real_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing here may read the real data/ tree, even by a default."""
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", tmp_path / "no-processed")
    monkeypatch.setattr(team_names_module, "RAW_DIR", tmp_path / "no-raw")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "no-raw")


def _row(home: str, away: str, commence: str, market: str, **fields) -> dict:
    row = {
        "commence_time": commence,
        "home_team": home,
        "away_team": away,
        "market": market,
        "player": "",
        "selection": "home",
        "line": None,
        "american_odds": -110,
        "book": "DraftKings",
    }
    row.update(fields)
    return row


def _opener(market: str, **fields) -> dict:
    """The real 2026-27 opener: Boston hosts the Rangers, league date
    2026-09-29, face-off 2026-09-30T00:00:00Z (the cached club schedule)."""
    return _row("Boston Bruins", "New York Rangers", "2026-09-30T00:00:00Z",
                market, **fields)


def _leafs(market: str, **fields) -> dict:
    """Toronto v Boston, league date 2026-10-08."""
    return _row("Toronto Maple Leafs", "Boston Bruins", "2026-10-09T00:10:00Z",
                market, **fields)


def _canes(market: str, **fields) -> dict:
    """Carolina v the Islanders, league date 2026-10-08."""
    return _row("Carolina Hurricanes", "New York Islanders",
                "2026-10-09T00:10:00Z", market, **fields)


def _freeze(archive: Path, rows: list[dict], *, day: str, frozen: datetime) -> None:
    """Freeze `rows` through the card's own snapshot writer."""
    probabilities = {}
    for raw in rows:
        line = raw.get("line")
        probabilities[
            selection_key(
                SimpleNamespace(**raw),
                market=raw["market"],
                selection=raw["selection"],
                line=None if line is None else float(line),
            )
        ] = 0.62
    path = fe.write_snapshot(
        pd.DataFrame(rows),
        probabilities,
        key_for=selection_key,
        verdicts_line="props_b2b=in force",
        snapshot_date=day,
        now=frozen,
        archive_dir=archive,
    )
    assert path is not None


def _games(*finals: tuple[str, str, str, int, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": index,
                "date": date,
                "home_team": home,
                "away_team": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "regulation": True,
            }
            for index, (date, home, away, home_goals, away_goals) in enumerate(
                finals, start=1
            )
        ],
        columns=["game_id", "date", "home_team", "away_team", "home_goals",
                 "away_goals", "regulation"],
    )


#: Nobody dressed: every prop on a found game voids, as books void it.
NO_LOGS = pd.DataFrame(
    columns=["date", "player_id", "player", "team", "shots_on_goal", "points",
             "goals", "assists", "blocked_shots", "hits", "saves"]
)


def _settle_and_render(
    tmp_path: Path, games: pd.DataFrame, *, now: datetime
) -> tuple[fe.SettlementResult, dict, str]:
    result = fe.settle_snapshots(
        NO_LOGS,
        games,
        team_names=TEAM_MAP,
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=now,
    )
    payload = fe.build_forward_report(fe.load_ledger(tmp_path / "processed"), now=now)
    return result, payload, fe.render_forward_report(payload)


def _after_the_ledger_line(text: str) -> str:
    """Everything the report says after its "- Ledger rows" line: the section
    that tells a reader what the counts mean."""
    lines = text.splitlines()
    (at,) = [i for i, line in enumerate(lines) if line.startswith("- Ledger rows:")]
    return "\n".join(lines[at + 1:])


def _assert_not_called_the_preseason_state(text: str, *, void: int, unsettleable: int) -> None:
    section = _after_the_ledger_line(text)
    assert "not a fault" not in text
    assert "correct state" not in text
    assert "## Nothing settled yet" not in text
    assert "not the empty state before a season" in section
    # The counts, restated where the reader is told what they mean.
    assert f"{void:,} void" in section
    assert f"{unsettleable:,} unsettleable" in section


# --------------------------------------------------------------------------
# Rows on the ledger, none settled won, lost or push.
# --------------------------------------------------------------------------

def test_the_opener_written_off_for_missing_finals_is_not_the_correct_state(
    tmp_path: Path,
) -> None:
    """The reachability refuter's route: every final missing, day 16."""
    _freeze(
        tmp_path / "archive",
        [_opener("moneyline"), _opener("total_goals", selection="over", line=5.5)],
        day="2026-09-29",
        frozen=datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc),
    )

    result, payload, text = _settle_and_render(
        tmp_path, _games(), now=datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    )

    assert result.rows_unsettleable == 2 and result.rows_settled == 0
    assert (payload["rows"], payload["void"], payload["unsettleable"]) == (2, 0, 2)
    assert payload["markets"] == {}
    _assert_not_called_the_preseason_state(text, void=0, unsettleable=2)
    section = _after_the_ledger_line(text)
    # Where to look: the results that never arrived, and the map that finds
    # each row's game.
    assert "results fetch" in section
    assert "team-name map" in section
    assert f"{fe.PATIENCE_DAYS}-day" in section


def test_the_finders_ledger_of_voids_and_a_missing_final(tmp_path: Path) -> None:
    """Two props on a found game for players who never dressed, and a total
    on a game with no final, past patience: 2 void, 1 unsettleable."""
    _freeze(
        tmp_path / "archive",
        [
            _leafs("shots_on_goal", player="Auston Matthews", selection="over",
                   line=3.5, american_odds=120),
            _leafs("shots_on_goal", player="Mitch Marner", selection="under",
                   line=2.5, american_odds=-120),
            _canes("total_goals", selection="over", line=6.5, american_odds=-105),
        ],
        day="2026-10-08",
        frozen=datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc),
    )

    result, payload, text = _settle_and_render(
        tmp_path,
        _games(("2026-10-08", "TOR", "BOS", 4, 2)),
        now=datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc),
    )

    assert (result.rows_void, result.rows_unsettleable) == (2, 1)
    assert payload["markets"] == {}
    _assert_not_called_the_preseason_state(text, void=2, unsettleable=1)


def test_an_all_void_ledger_is_not_the_preseason_state_either(tmp_path: Path) -> None:
    """A void needs a game that was found, so it can never be preseason."""
    _freeze(
        tmp_path / "archive",
        [_leafs("shots_on_goal", player="Auston Matthews", selection="over",
                line=3.5, american_odds=120)],
        day="2026-10-08",
        frozen=datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc),
    )

    result, payload, text = _settle_and_render(
        tmp_path,
        _games(("2026-10-08", "TOR", "BOS", 4, 2)),
        now=datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc),
    )

    assert (result.rows_void, result.rows_unsettleable) == (1, 0)
    _assert_not_called_the_preseason_state(text, void=1, unsettleable=0)


def test_rows_that_collapse_to_no_wager_are_still_rows(tmp_path: Path) -> None:
    """The split is on the ledger's rows, the figure the report prints first.

    A row whose price the best-price collapse cannot read is dropped from
    the wagers, but it is still on the ledger, and a ledger with rows on it
    is not empty.
    """
    ledger = pd.DataFrame(
        [
            {
                "snapshot_date": "2026-10-08", "commence_time": "2026-10-09T00:10:00Z",
                "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
                "market": "moneyline", "player": "", "selection": "home",
                "line": None, "american_odds": None, "book": "DraftKings",
                "model_probability": 0.62, "edge": 0.1, "verdicts_in_force": "x",
                "settled_at": "2026-10-09T15:00:00+00:00", "outcome": "unsettleable",
                "actual": None, "profit_units": 0.0,
            }
        ],
        columns=list(fe.LEDGER_COLUMNS),
    )

    payload = fe.build_forward_report(ledger)
    text = fe.render_forward_report(payload)

    assert payload["rows"] == 1 and payload["wagers"] == 0
    _assert_not_called_the_preseason_state(text, void=0, unsettleable=0)


# --------------------------------------------------------------------------
# What must not move.
# --------------------------------------------------------------------------

def test_an_empty_ledger_keeps_the_preseason_text_word_for_word(tmp_path: Path) -> None:
    payload = fe.build_forward_report(fe.load_ledger(tmp_path / "processed"))
    text = fe.render_forward_report(payload)

    assert payload["rows"] == 0
    assert _after_the_ledger_line(text).strip() == (
        "## Nothing settled yet\n\n"
        "The ledger is empty or nothing on it has settled. Before the season "
        f"starts this is the {PRESEASON}: forward evidence can only begin "
        "accumulating when books post prices and games produce results."
    )


def test_one_settled_row_brings_the_table_not_either_message(tmp_path: Path) -> None:
    """A void and a write-off beside a settled row are counted, not a
    reason to hide the table."""
    _freeze(
        tmp_path / "archive",
        [
            _leafs("moneyline", american_odds=-120),
            _leafs("shots_on_goal", player="Auston Matthews", selection="over",
                   line=3.5, american_odds=120),
            _canes("total_goals", selection="over", line=6.5, american_odds=-105),
        ],
        day="2026-10-08",
        frozen=datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc),
    )

    result, payload, text = _settle_and_render(
        tmp_path,
        _games(("2026-10-08", "TOR", "BOS", 4, 2)),
        now=datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc),
    )

    assert (result.rows_settled, result.rows_void, result.rows_unsettleable) == (1, 1, 1)
    assert list(payload["markets"]) == ["moneyline"]
    assert "## Accumulated so far, at the shipped edge bars" in text
    assert "| `moneyline` |" in text
    assert PRESEASON not in text
    assert "not the empty state before a season" not in text
    assert "## Nothing settled yet" not in text


# --------------------------------------------------------------------------
# Through the runner, the way Gameday Refresh's settlement step calls it.
# --------------------------------------------------------------------------

def _load_runner() -> ModuleType:
    """Import the script by path, as `tests/test_scripts.py` does."""
    path = config.PROJECT_ROOT / "scripts" / "run_forward_evidence.py"
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_runner_publishes_a_written_off_day_without_the_preseason_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The file card-feed publishes as `latest_forward_evidence.md`.

    The processed tables hold the map and the results fetched so far, which
    never include the opener's final; the runner settles at the wall clock,
    so the day is dated a season back to be past patience on any clock.
    """
    processed = tmp_path / "processed"
    save_team_name_map(TEAM_MAP, processed_dir=processed)
    pd.DataFrame(columns=list(PLAYER_LOG_COLUMNS)).to_csv(
        processed / PLAYER_LOGS_FILENAME, index=False
    )
    pd.DataFrame(columns=list(TEAM_GAME_COLUMNS)).to_csv(
        processed / TEAM_GAMES_FILENAME, index=False
    )
    _freeze(
        tmp_path / "archive",
        [
            _row("Boston Bruins", "New York Rangers", "2025-10-08T00:00:00Z",
                 "moneyline"),
            _row("Boston Bruins", "New York Rangers", "2025-10-08T00:00:00Z",
                 "total_goals", selection="over", line=5.5),
        ],
        day="2025-10-07",
        frozen=datetime(2025, 10, 7, 15, 0, tzinfo=timezone.utc),
    )

    code = _load_runner().main(
        [
            "--processed-dir", str(processed),
            "--output-dir", str(tmp_path / "outputs"),
            "--archive-dir", str(tmp_path / "archive"),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "0 row(s) settled, 0 void, 2 unsettleable" in out
    text = (tmp_path / "outputs" / fe.REPORT_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    _assert_not_called_the_preseason_state(text, void=0, unsettleable=2)
    assert "results fetch" in _after_the_ledger_line(text)
    # The JSON beside it is unchanged in shape: the site reads it, and this
    # fix adds no figure to anything published. `registered_statistic` was
    # added later (g23: the pooled number docs/when_this_ends.md decides on);
    # the site does not read it, and
    # tests/test_the_forward_report_computes_the_registered_statistic.py
    # holds that it publishes no return.
    published = json.loads(
        (tmp_path / "outputs" / fe.REPORT_JSON_FILENAME).read_text(encoding="utf-8")
    )
    assert set(published) == {
        "generated_at", "rows", "wagers", "markets", "unsettleable", "void",
        "registered_statistic",
    }
    assert (published["rows"], published["unsettleable"], published["markets"]) == (2, 2, {})
