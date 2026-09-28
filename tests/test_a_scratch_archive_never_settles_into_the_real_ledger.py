"""A scratch archive settled into the REAL forward ledger.

`run_forward_evidence.py` moves the archive to `<--output-dir>/archive` when
it is given a non-default --output-dir, so a scratch card's snapshots are the
ones a scratch run settles. The ledger lives in --processed-dir, and that did
not move: `--output-dir /tmp/x` on its own paired the scratch archive with the
REAL processed directory. The scratch card's days settled into the real
forward ledger, as if Gameday Refresh had frozen them, and settlement only
ever appends — nothing takes them out again. `--archive-dir` on its own did
the same. This is the mirror of the split the script already refuses (a
scratch ledger with the real archive).

What these tests hold, with the default directories pointed at a scratch
"home" tree and a pending snapshot of a finished game frozen by a scratch
card:

* --output-dir alone, or --archive-dir alone, is refused before anything is
  read or written, naming both directories and the flag to pass;
* naming --processed-dir as well (even the real one) is an explicit choice,
  and it runs;
* naming the real archive or the real output directory is not a scratch
  run, and it runs as the flag-less one does.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers.team_names import save_team_name_map
from nhl_betting_lab.reports.card_pricing import selection_key


TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
ROW = {
    "commence_time": "2026-04-01T23:10:00Z",  # league date 2026-04-01
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
    "market": "moneyline",
    "player": "",
    "selection": "home",
    "line": None,
    "american_odds": -120,
    "book": "DraftKings",
}


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_forward_evidence.py"
    spec = importlib.util.spec_from_file_location(
        "_script_run_forward_evidence_scratch_archive", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _freeze(archive_dir: Path | None) -> None:
    """Freeze the Toronto moneyline as the card does, into `archive_dir`
    (None: the default archive)."""
    assert fe.write_snapshot(
        pd.DataFrame([ROW]),
        {selection_key(SimpleNamespace(**ROW), market="moneyline",
                       selection="home", line=None): 0.62},
        key_for=selection_key,
        verdicts_line="team_b2b=in force",
        snapshot_date="2026-04-01",
        now=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        archive_dir=archive_dir,
    ) is not None


def _processed(directory: Path) -> Path:
    """A processed directory that can settle the game: the final and a map."""
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"game_id": 1, "date": "2026-04-01", "home_team": "TOR",
          "away_team": "BOS", "home_goals": 4, "away_goals": 2,
          "regulation": True}]
    ).to_csv(directory / "team_games.csv", index=False)
    save_team_name_map(TEAM_MAP, processed_dir=directory)
    return directory


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path, with its bytes."""
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The 'real' data tree (default archive, processed and outputs) with an
    empty ledger, and a scratch card's snapshot frozen under scratch/archive,
    where run_gameday_card.py --output-dir scratch puts it."""
    root = tmp_path / "home" / "data"
    processed = _processed(root / "processed")
    outputs = root / "outputs"
    outputs.mkdir(parents=True)
    monkeypatch.setattr(fe, "DATA_DIR", root)
    module = load_script()
    monkeypatch.setattr(module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)
    scratch = tmp_path / "scratch"
    _freeze(scratch / "archive")
    return SimpleNamespace(root=root, processed=processed, outputs=outputs,
                           archive=root / "archive", scratch=scratch,
                           module=module)


def _assert_refused(home, code: int, err: str, before_home, before_scratch,
                    scratch_archive: Path) -> None:
    assert code == 2, "a scratch archive with the real ledger was not refused"
    errors = [line for line in err.splitlines() if line.startswith("::error::")]
    assert errors, err
    message = " ".join(errors)
    assert str(scratch_archive) in message, "the archive is not named"
    assert str(home.processed) in message, "the real processed dir is not named"
    assert "--processed-dir" in message, "the flag to pass is not named"
    assert not (home.processed / fe.LEDGER_FILENAME).exists(), (
        "the scratch card's day settled into the REAL forward ledger"
    )
    assert _tree(home.root) == before_home, "the real data tree changed"
    assert _tree(home.scratch) == before_scratch, (
        "the refused run still read-and-wrote the scratch tree"
    )


def test_output_dir_alone_is_refused(
    home, capsys: pytest.CaptureFixture[str]
) -> None:
    before_home, before_scratch = _tree(home.root), _tree(home.scratch)

    code = home.module.main(["--output-dir", str(home.scratch)])
    err = capsys.readouterr().err

    _assert_refused(home, code, err, before_home, before_scratch,
                    home.scratch / "archive")


def test_archive_dir_alone_is_refused(
    home, capsys: pytest.CaptureFixture[str]
) -> None:
    before_home, before_scratch = _tree(home.root), _tree(home.scratch)

    code = home.module.main(["--archive-dir", str(home.scratch / "archive")])
    err = capsys.readouterr().err

    _assert_refused(home, code, err, before_home, before_scratch,
                    home.scratch / "archive")


def test_naming_the_processed_dir_too_is_an_explicit_choice(
    home, capsys: pytest.CaptureFixture[str]
) -> None:
    # Even the real one: the flag says the pairing was meant.
    code = home.module.main(
        ["--output-dir", str(home.scratch),
         "--processed-dir", str(home.processed)]
    )
    capsys.readouterr()

    assert code == 0
    assert list(fe.load_ledger(home.processed)["outcome"]) == ["won"]
    assert (fe.snapshots_dir(home.scratch / "archive")
            / "2026-04-01.settled").exists()


@pytest.mark.parametrize("flag", ["--archive-dir", "--output-dir"])
def test_naming_the_real_directories_is_not_a_scratch_run(
    home, flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _freeze(None)
    target = home.archive if flag == "--archive-dir" else home.outputs

    code = home.module.main([flag, str(target)])
    capsys.readouterr()

    assert code == 0
    assert list(fe.load_ledger(home.processed)["outcome"]) == ["won"]
    assert (fe.snapshots_dir(None) / "2026-04-01.settled").exists()
    assert not (fe.snapshots_dir(home.scratch / "archive")
                / "2026-04-01.settled").exists()


def test_the_gameday_refresh_invocation_still_settles_home(
    home, capsys: pytest.CaptureFixture[str]
) -> None:
    # .github/workflows/gameday-refresh.yml runs the script with no flags.
    _freeze(None)

    code = home.module.main([])
    capsys.readouterr()

    assert code == 0
    assert list(fe.load_ledger(home.processed)["outcome"]) == ["won"]
    assert (fe.snapshots_dir(None) / "2026-04-01.settled").exists()
