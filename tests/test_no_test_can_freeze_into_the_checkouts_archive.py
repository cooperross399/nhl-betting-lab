"""A card test could freeze into the checkout's own evidence archive, and the test named for that could not see it.

Two defects, both in this suite, around one guard in `run_gameday_card.py`:
a run given a scratch `--output-dir` freezes its snapshot under
`<output-dir>/archive`, not the real evidence archive.

* `test_a_scratch_run_cannot_freeze_into_the_real_evidence_archive` could not
  fail. It gave the card a staging directory that does not exist, so the
  card had no prices, froze nothing anywhere ("No snapshot was frozen for
  2026-10-08: there were no prices"), and its `after == before` held with the
  guard deleted. Measured on 68dcbb4 with the guard's two lines deleted: the
  whole suite went 14 failed, 2412 passed (2426 passed without the mutant),
  and that test was not among the 14.
* Four modules run the card's real `main()` with fixtures that point the raw
  cache, the team map and the recorded verdicts away from the checkout, and
  not `forward_evidence.DATA_DIR`, the root of the real evidence archive.
  Under the same mutant the suite went red and still left three snapshots of
  synthetic rows, under real team names, in the checkout's own
  `data/archive/priced_snapshots`:
  - 2026-03-12.csv, from test_a_scratch_output_dir_keeps_the_recorded_verdicts;
  - 2026-10-07.csv, from test_the_docs_state_the_cap_and_staging_truthfully;
  - 2026-10-15.csv, from test_a_club_schedule_that_is_not_an_object.
  test_the_card_reads_the_dirs_it_is_given aimed its freezes at the same
  archive and created the directory. It froze nothing only because
  2026-10-15 already stood when it ran. The operator's archive holds
  2026-08-27 and 2026-10-08, so none of the three would have collided, and
  all three would have landed. The first opinion of a day stands and is
  never replaced, so each would have become that night's forward evidence,
  read by settlement. A real card on 2026-10-07 or 2026-10-15 could not have
  frozen its own. #164 recorded the leak as not fixed; it counted 2 snapshots
  from 2 modules.

Found by the failure-shape audit (finding v5; the reproduce and
reachability refuters confirmed it, and the intent refuter agreed on the
facts and judged it hygiene). Each refuter ran the whole suite under the
mutant with an audit hook recording every write under `data/archive`.

What holds now:

* `tests/conftest.py` points `forward_evidence.DATA_DIR` at a scratch
  directory of each test's own before the test runs. That root holds the
  evidence archive's default and the forward ledger's. So no test can freeze
  or settle into the checkout, whichever guard regresses, including a test
  written later that forgets to point it away. The tests below check that
  first, before anything runs: a suite without the fixture fails here and
  writes nothing, where the defect it replaces wrote first and failed after;
* a card that takes the default archive route, as it would with the guard
  gone, freezes into that scratch directory, and each test gets its own;
* the named test now stages a slate the card prices, so it sees where the
  snapshot goes: under `<output-dir>/archive`, and nowhere in the default
  archive. It fails with the guard deleted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT

from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_scripts import load_script
from test_the_card_reads_the_dirs_it_is_given import PROVIDER, _saved_map, _slate, _tables


#: Toronto hosting Boston that evening, and the card run that morning.
DAY = "2026-10-15"
GAME = (DAY, f"{DAY}T23:00:00Z", "TOR", "BOS")
NOW = f"{DAY}T15:00:00+00:00"


def _inside(root: Path, path: Path) -> bool:
    return Path(root).resolve() in Path(path).resolve().parents


def test_the_default_evidence_root_is_scratch_before_the_test_body_runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Both append-only stores hang off this one root: the archive
    (`<root>/archive/priced_snapshots`) and the forward ledger's default
    (`<root>/processed/forward_evidence.csv`)."""
    root = fe.DATA_DIR

    assert not _inside(PROJECT_ROOT, root), (
        f"the default evidence root is the checkout's own: {root}"
    )
    assert _inside(tmp_path_factory.getbasetemp(), root), root
    assert fe.snapshots_dir().parent.parent == root


@pytest.mark.parametrize("run", ["first", "second"])
def test_a_card_that_takes_the_default_archive_route_freezes_into_this_tests_scratch(
    run: str,
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The card is told its scratch output directory is the default one, so
    it freezes where a card whose guard regressed would: the default archive.
    That must be this test's own scratch directory. Two runs freeze the same
    night, and the second must find no snapshot the first froze."""
    default_archive = fe.snapshots_dir()
    # Checked before anything runs: the defect this replaces wrote into the
    # checkout first and failed after.
    assert not _inside(PROJECT_ROOT, default_archive), (
        f"the default archive is the checkout's own: {default_archive}"
    )
    assert _inside(tmp_path_factory.getbasetemp(), default_archive), default_archive
    assert not default_archive.exists(), (
        f"{run}: another test's snapshots are in this test's default archive"
    )

    # Every other default the card reads is pointed away by the helper; the
    # archive root goes back where the suite put it, since that is what is
    # under test here.
    suite_root = fe.DATA_DIR
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    monkeypatch.setattr(fe, "DATA_DIR", suite_root)
    processed = tmp_path / "processed"
    _tables(processed)
    _saved_map(tmp_path, processed, ("TOR", "BOS", "MTL", "OTT"))
    _slate(tmp_path / "staging", GAME)
    outputs = tmp_path / "outputs"
    module = load_script("run_gameday_card.py")
    monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)

    code = module.main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(processed),
            "--output-dir", str(outputs),
            "--now", NOW,
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "not the real evidence archive" not in out, (
        "the card did not take the default archive route"
    )
    frozen = default_archive / f"{DAY}.csv"
    assert f"Priced snapshot frozen: {frozen}" in out, out
    assert sorted(pd.read_csv(frozen)["home_team"]) == [PROVIDER["TOR"]] * 2
    assert not (outputs / "archive").exists()
