"""Settlement given scratch directories settled the REAL archive into them.

`run_forward_evidence.py` took the real archive (`DATA_DIR/archive`) unless
--archive-dir was named, whatever --processed-dir and --output-dir it was
given. The archive's markers and the ledger's rows together decide which days
are settled, so a scratch run split the pair: it settled the real archive's
days into a scratch ledger and marked them settled in the real archive, and
the next real run printed "0 of 0 pending snapshot(s) settled" — the real
ledger never received those rows. It also never looked in the archive a
scratch card freezes into (`<--output-dir>/archive`, run_gameday_card.py).
Found by the failure-shape audit and reproduced three ways on the real code.

What these tests hold, with the default directories pointed at a scratch
"home" tree holding a pending snapshot of a finished game:

* a scratch run leaves the home archive and ledger exactly as they were;
* a scratch run settles the snapshot a scratch card froze under its
  --output-dir;
* a scratch ledger with the real archive is refused before anything is read
  or written;
* the flag-less run, the one Gameday Refresh makes, still settles home.
"""

from __future__ import annotations

import importlib.util
import sys
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
    spec = importlib.util.spec_from_file_location("_script_run_forward_evidence", path)
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
    """The 'real' data tree: default archive, processed and outputs."""
    root = tmp_path / "home" / "data"
    processed = _processed(root / "processed")
    outputs = root / "outputs"
    outputs.mkdir(parents=True)
    monkeypatch.setattr(fe, "DATA_DIR", root)
    module = load_script()
    monkeypatch.setattr(module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)
    _freeze(None)
    return SimpleNamespace(root=root, processed=processed, outputs=outputs,
                           archive=root / "archive", module=module)


def test_a_scratch_run_leaves_the_real_archive_and_ledger_alone(
    tmp_path: Path, home, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _tree(home.root)
    scratch = tmp_path / "scratch"

    code = home.module.main(
        ["--processed-dir", str(_processed(scratch / "processed")),
         "--output-dir", str(scratch)]
    )
    capsys.readouterr()

    assert code == 0
    assert _tree(home.root) == before, (
        "a scratch run changed the real data tree"
    )
    assert not (scratch / "processed" / fe.LEDGER_FILENAME).exists(), (
        "a scratch run settled the real archive's day into its own ledger"
    )


def test_a_scratch_run_settles_what_a_scratch_card_froze(
    tmp_path: Path, home, capsys: pytest.CaptureFixture[str]
) -> None:
    scratch = tmp_path / "scratch"
    _freeze(scratch / "archive")  # where run_gameday_card --output-dir puts it

    code = home.module.main(
        ["--processed-dir", str(_processed(scratch / "processed")),
         "--output-dir", str(scratch)]
    )
    out = capsys.readouterr().out
    ledger = fe.load_ledger(scratch / "processed")

    assert code == 0
    assert list(ledger["outcome"]) == ["won"]
    assert (fe.snapshots_dir(scratch / "archive") / "2026-04-01.settled").exists()
    assert str(scratch / "archive") in out


def test_a_scratch_ledger_with_the_real_archive_is_refused(
    tmp_path: Path, home, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _tree(home.root)
    scratch = _processed(tmp_path / "scratch" / "processed")

    code = home.module.main(["--processed-dir", str(scratch)])
    err = capsys.readouterr().err

    assert code == 2
    assert any(line.startswith("::error::") for line in err.splitlines())
    assert "--archive-dir" in err
    assert _tree(home.root) == before
    assert not (scratch / fe.LEDGER_FILENAME).exists()


def test_the_flag_less_run_still_settles_the_real_archive(
    home, capsys: pytest.CaptureFixture[str]
) -> None:
    code = home.module.main([])
    capsys.readouterr()

    assert code == 0
    assert list(fe.load_ledger(home.processed)["outcome"]) == ["won"]
    assert (fe.snapshots_dir(None) / "2026-04-01.settled").exists()
