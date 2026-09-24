"""Forward settlement wrote a whole day off when the team-name map was missing.

`settle_snapshots` finds each frozen row's game through the team-name map.
`scripts/run_forward_evidence.py` loads that map from `team_names.csv` in its
processed directory and rebuilds it from the boxscore cache when the file is
absent. With neither — a worktree, a broken state restore — the rebuilt map
holds only the six Utah and Arizona alias entries. It is never empty, so
nothing looked wrong; it resolves both teams of essentially no row, so every
game lookup missed; the day waited out the fourteen-day patience window; and
then every row was appended to the forward ledger as `unsettleable` and the
day marked settled. The ledger is append-only and the prices it settled
against are gone, so that was permanent. Nothing raised.

What these tests hold:

* a written-off day stays written off — the permanence the broken map reached;
* a map that resolves both teams of no row REFUSES instead, past patience and
  inside it, and one resolvable side (Utah) is not a resolved row;
* on refusal NO day is marked and NO row appended — including a good day
  that sorts first, because markers are touched inside the settlement loop
  and the ledger is written after it;
* the runner prints `::error::` and exits 2, leaves the ledger byte-identical,
  and still restates it as the forward report;
* the unresolved count is recorded when it is zero and when it is not.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
    resolve_team,
    save_team_name_map,
)
from nhl_betting_lab.reports.card_pricing import selection_key


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Keyed exactly as `load_team_name_map` returns it: normalized name -> abbrev.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}

#: One day after the 2026-10-08 slate, and twenty-two days after it — well
#: past `PATIENCE_DAYS`, where the old path wrote the day off.
NOW = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)


def _moneyline(
    home: str = "Toronto Maple Leafs",
    away: str = "Boston Bruins",
    commence: str = "2026-10-09T00:10:00Z",  # league date 2026-10-08
) -> dict:
    return {
        "commence_time": commence,
        "home_team": home,
        "away_team": away,
        "market": "moneyline",
        "player": "",
        "selection": "home",
        "line": None,
        "american_odds": -120,
        "book": "DraftKings",
    }


def _prop() -> dict:
    return {
        **_moneyline(),
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 3.5,
        "american_odds": 120,
    }


def _snapshot(archive: Path, rows: list[dict], day: str = "2026-10-08") -> Path:
    """Freeze rows the way the card does, each with a model opinion."""
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
        verdicts_line="team_b2b=in force",
        snapshot_date=day,
        archive_dir=archive,
    )
    assert path is not None
    return path


def _games(*rows: tuple[str, str, str]) -> pd.DataFrame:
    """Final games as (league date, HOME, AWAY), the home side winning 4-2."""
    return pd.DataFrame(
        [
            {
                "game_id": index,
                "date": day,
                "home_team": home,
                "away_team": away,
                "home_goals": 4,
                "away_goals": 2,
                "regulation": True,
            }
            for index, (day, home, away) in enumerate(rows)
        ],
        columns=["game_id", "date", "home_team", "away_team", "home_goals",
                 "away_goals", "regulation"],
    )


def _logs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-10-08", "player_id": 8479318,
                "player": "Auston Matthews", "team": "TOR",
                "shots_on_goal": 5.0, "points": 1.0, "goals": 1.0,
                "assists": 0.0, "blocked_shots": 0.0, "hits": 2.0,
                "saves": 0.0,
            }
        ]
    )


def _settle(tmp_path: Path, team_names, *, games=None, now=LATER):
    return fe.settle_snapshots(
        _logs(),
        _games(("2026-10-08", "TOR", "BOS")) if games is None else games,
        team_names=team_names,
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=now,
    )


def _markers(tmp_path: Path) -> list[str]:
    return sorted(
        p.name for p in fe.snapshots_dir(tmp_path / "archive").glob("*.settled")
    )


def _ledger(tmp_path: Path) -> Path:
    return tmp_path / "processed" / fe.LEDGER_FILENAME


@pytest.fixture
def broken_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """The map the runner loads with no `team_names.csv` and no boxscores.

    The default processed and raw directories point at empty scratch ones,
    so the real `data/processed/team_names.csv` and boxscore cache cannot
    rescue it — or make this pass or fail by checkout.
    """
    default_processed = tmp_path / "default_processed"
    default_raw = tmp_path / "default_raw"
    default_processed.mkdir()
    default_raw.mkdir()
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", default_processed)
    monkeypatch.setattr(team_names_module, "RAW_DIR", default_raw)
    mapping = load_team_name_map(processed_dir=tmp_path / "processed")
    # Six alias spellings, never empty: exactly what hid the failure.
    assert len(mapping) == 6
    return mapping


# --------------------------------------------------------------------------
# What the broken map used to reach.
# --------------------------------------------------------------------------

def test_a_written_off_day_stays_written_off(tmp_path: Path) -> None:
    """Past patience with no game found, every row is appended unsettleable
    and the day is marked; results arriving later change nothing. That is
    the legitimate path for a game that never happened — and the one a
    broken map sent every row down."""
    _snapshot(tmp_path / "archive", [_prop(), _moneyline()])

    first = _settle(tmp_path, TEAM_MAP, games=_games())
    second = _settle(tmp_path, TEAM_MAP)  # the result is in now
    ledger = fe.load_ledger(tmp_path / "processed")

    assert first.rows_unsettleable == 2
    assert first.rows_unresolved_teams == 0
    assert _markers(tmp_path) == ["2026-10-08.settled"]
    assert second.snapshots_seen == 0
    assert list(ledger["outcome"]) == ["unsettleable", "unsettleable"]


# --------------------------------------------------------------------------
# No row resolves both teams: refuse, and write nothing.
# --------------------------------------------------------------------------

def test_an_unresolvable_map_refuses_instead_of_writing_off_the_day(
    tmp_path: Path, broken_map: dict
) -> None:
    rows = [_prop(), _moneyline()]
    _snapshot(tmp_path / "archive", rows)
    assert not any(
        resolve_team(r["home_team"], broken_map)
        and resolve_team(r["away_team"], broken_map)
        for r in rows
    )

    try:
        result = _settle(tmp_path, broken_map)  # the game IS final
    except UnresolvedTeamsError as error:
        refused, message = True, str(error)
    else:
        refused, message = False, result.summary_line()

    ledger = fe.load_ledger(tmp_path / "processed")
    assert refused, (
        "settled instead of refusing — the day was written off: markers "
        f"{_markers(tmp_path)}, ledger outcomes {list(ledger['outcome'])}; "
        f"{message}"
    )
    assert _markers(tmp_path) == []
    assert not _ledger(tmp_path).exists()
    assert "2026-10-08: 2 row(s)" in message
    assert "Toronto Maple Leafs" in message and "Boston Bruins" in message


def test_the_refusal_does_not_wait_for_patience_to_run_out(
    tmp_path: Path, broken_map: dict
) -> None:
    """Resolution does not depend on results arriving, so waiting fixes
    nothing: a broken map is refused the first day it is seen."""
    _snapshot(tmp_path / "archive", [_moneyline()])

    with pytest.raises(UnresolvedTeamsError):
        _settle(tmp_path, broken_map, now=NOW)

    assert _markers(tmp_path) == []


def test_one_resolvable_side_is_not_a_resolved_row(
    tmp_path: Path, broken_map: dict
) -> None:
    """The alias map always resolves Utah, so a per-side guard never fires."""
    assert resolve_team("Utah Mammoth", broken_map) == "UTA"
    _snapshot(
        tmp_path / "archive", [_moneyline(home="Utah Mammoth")]
    )

    with pytest.raises(UnresolvedTeamsError):
        _settle(tmp_path, broken_map, games=_games(("2026-10-08", "UTA", "BOS")))

    assert _markers(tmp_path) == []


def test_a_refused_day_marks_and_appends_nothing_for_any_day(
    tmp_path: Path, broken_map: dict
) -> None:
    """A good day sorting first must not be marked either.

    Markers are touched inside the settlement loop and the ledger is written
    after it. Refusing mid-loop would leave 2026-10-07 marked settled with
    its row never written — the permanent loss this guard exists to stop.
    Utah at Arizona is chosen because the alias-only map resolves both.
    """
    _snapshot(
        tmp_path / "archive",
        [_moneyline(home="Utah Mammoth", away="Arizona Coyotes",
                    commence="2026-10-08T00:10:00Z")],
        day="2026-10-07",
    )
    _snapshot(tmp_path / "archive", [_moneyline()], day="2026-10-08")
    games = _games(("2026-10-07", "UTA", "ARI"), ("2026-10-08", "TOR", "BOS"))

    with pytest.raises(UnresolvedTeamsError) as caught:
        _settle(tmp_path, broken_map, games=games)

    assert _markers(tmp_path) == []
    assert not _ledger(tmp_path).exists()
    assert "2026-10-08" in str(caught.value)
    assert "2026-10-07" not in str(caught.value)


# --------------------------------------------------------------------------
# Through the runner, the way the Gameday Refresh step calls it.
# --------------------------------------------------------------------------

def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    module = load_script("run_forward_evidence.py")
    code = module.main(
        [
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
            "--archive-dir", str(tmp_path / "archive"),
        ]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_runner_refuses_leaves_the_ledger_and_still_restates_it(
    tmp_path: Path, broken_map: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    # A day already settled, honestly, with the map that worked then.
    _snapshot(
        tmp_path / "archive",
        [_moneyline(commence="2026-10-08T00:10:00Z")],
        day="2026-10-07",
    )
    _settle(tmp_path, TEAM_MAP, games=_games(("2026-10-07", "TOR", "BOS")))
    ledger = _ledger(tmp_path)
    before = ledger.read_bytes()
    assert list(fe.load_ledger(tmp_path / "processed")["outcome"]) == ["won"]
    # Today's run finds no team_names.csv and no boxscores.
    _snapshot(tmp_path / "archive", [_moneyline()])

    code, out, err = _run(tmp_path, capsys)

    assert code == 2
    assert any(line.startswith("::error::") for line in err.splitlines())
    assert ledger.read_bytes() == before
    assert _markers(tmp_path) == ["2026-10-07.settled"]
    assert (tmp_path / "outputs" / fe.REPORT_MARKDOWN_FILENAME).is_file()
    assert "Settlement refused" in out


def test_the_runner_settles_normally_with_the_map_in_its_processed_dir(
    tmp_path: Path, broken_map: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    save_team_name_map(TEAM_MAP, processed_dir=tmp_path / "processed")
    _snapshot(tmp_path / "archive", [_moneyline()])

    code, out, _ = _run(tmp_path, capsys)

    # No team games on disk, so the day waits; what matters is no refusal.
    assert code == 0
    assert "0 row(s) named a team the team-name map could not resolve" in out


def test_the_refusal_names_a_flag_the_runner_accepts(
    tmp_path: Path, broken_map: dict
) -> None:
    """An error instructing an impossible action reads as operator error."""
    _snapshot(tmp_path / "archive", [_moneyline()])
    with pytest.raises(UnresolvedTeamsError) as caught:
        _settle(tmp_path, broken_map)
    assert "--processed-dir" in str(caught.value)

    module = load_script("run_forward_evidence.py")
    buffer = io.StringIO()
    with pytest.raises(SystemExit) as exit_info, redirect_stdout(buffer):
        module.main(["--help"])

    assert exit_info.value.code == 0
    assert "--processed-dir" in buffer.getvalue()


# --------------------------------------------------------------------------
# The count is recorded either way.
# --------------------------------------------------------------------------

def test_a_partly_resolved_day_counts_and_names_what_did_not_resolve(
    tmp_path: Path,
) -> None:
    """One row resolves, so no refusal; the other is counted and named."""
    _snapshot(
        tmp_path / "archive",
        [_moneyline(), _moneyline(home="Seattle Kraken")],
    )

    result = _settle(tmp_path, TEAM_MAP, now=NOW)

    assert result.rows_unresolved_teams == 1
    assert result.unresolved_team_names == ["Seattle Kraken"]
    assert result.snapshots_waiting == 1
    assert "1 row(s) named a team the team-name map could not resolve" in (
        result.summary_line()
    )
