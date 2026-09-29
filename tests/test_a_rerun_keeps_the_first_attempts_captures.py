"""Re-running a Line Movement run never throws away the first attempt's captures.

A Line Movement run goes red on purpose when the line units or the scratch
list were not captured, and the error says that data "cannot be collected
later", which invites a click on Re-run. Before this fix the re-run lost
the data it was meant to rescue:

* "Restore today's captures" lists only COMPLETED runs, and while attempt 2
  runs GitHub lists its own run as in progress. So attempt 2 restored the run
  before it, and `--union 3` only walks older carriers: attempt 1's round
  never reached disk.
* "Keep the captures" then uploaded `line-movement` with `overwrite: true`.
  An upload-artifact v4 artifact belongs to the run, not the attempt, so that
  deleted attempt 1's artifact, the only copy of its prices, scratch list and
  line units. If attempt 2 went green nothing reported the loss.

Now, on any attempt after the first, the run's own `line-movement` artifact
is downloaded and unioned, row by row, into data/processed before it is
uploaded again (`restore_state.py --fold-run`, the same `union_csv` the
restore uses). A run that holds none is not a fault. A download that fails
for any other reason must not be followed by the overwrite: this attempt's
captures are kept beside the earlier ones under their own name, and the run
goes red saying so.

These tests run the fold step itself, taken from the workflow file, under
`bash --noprofile --norc -eo pipefail` with an offline `gh`. Nothing reaches
the network, and no provider credit is spent.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
RESTORE_SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"
ARTIFACT = "line-movement"
KEEP = "Keep the captures"
RUN_ID = "4242"
DAY = "2026-10-15"

HEADER = "captured_at,market,player,american_odds\n"
#: What "Restore today's captures" brought back from the run before: 14:00.
BASE = HEADER + "2026-10-15T14:00:00+00:00,shots_on_goal,Auston Matthews,-110\n"
#: Attempt 1 of this run captured the 18:00 round, and a scratch list.
ROUND_1 = "2026-10-15T18:00:00+00:00,shots_on_goal,Auston Matthews,-125\n"
DEPLOYMENT = "captured_at,game_id,player,status\n2026-10-15T18:00:00+00:00,1,A,scratched\n"
#: Attempt 2 (this one) captured the 21:00 round on top of the restored base.
ROUND_2 = "2026-10-15T21:00:00+00:00,shots_on_goal,Auston Matthews,-130\n"

FAKE_GH = r'''#!{python}
import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if args[:2] == ["run", "download"]:
    mode = os.environ["FAKE_GH_MODE"]
    if mode == "down":
        print("HTTP 502: Bad Gateway", file=sys.stderr)
        sys.exit(1)
    if mode == "absent" or args[2] != os.environ["FAKE_GH_RUN"]:
        print("no artifact matches any of the names or patterns provided", file=sys.stderr)
        sys.exit(1)
    dest = Path(args[args.index("--dir") + 1])
    shutil.copytree(os.environ["FAKE_GH_ARTIFACT"], dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["capture"]["steps"]


def _fold_step() -> tuple[int, dict]:
    """The step that runs `restore_state.py --fold-run`."""
    matches = [
        (index, step) for index, step in enumerate(_steps())
        if "--fold-run" in str(step.get("run", ""))
    ]
    assert len(matches) == 1, "exactly one step folds in this run's earlier attempts"
    return matches[0]


def _uploads(name_contains: str) -> list[tuple[int, dict]]:
    return [
        (index, step) for index, step in enumerate(_steps())
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
        and name_contains in str((step.get("with") or {}).get("name", ""))
    ]


def _paths(step: dict) -> list[str]:
    return [line.strip() for line in str(step["with"]["path"]).splitlines() if line.strip()]


def _run_fold(tmp_path: Path, mode: str) -> tuple[subprocess.CompletedProcess, Path, Path]:
    """Attempt 2's data/processed, the fold step run over it, and gh's log."""
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    shutil.copy(RESTORE_SCRIPT, work / "scripts" / "restore_state.py")
    processed = work / "data" / "processed"
    (processed / "line_movement").mkdir(parents=True)
    (processed / "line_movement" / f"{DAY}.csv").write_text(BASE + ROUND_2, encoding="utf-8")

    # Attempt 1's artifact, rooted at data/processed as "Keep the captures"
    # roots it: the restored base, its own round, and a scratch list.
    earlier = tmp_path / "attempt1"
    (earlier / "line_movement").mkdir(parents=True)
    (earlier / "line_movement" / f"{DAY}.csv").write_text(BASE + ROUND_1, encoding="utf-8")
    (earlier / "deployment").mkdir()
    (earlier / "deployment" / f"{DAY}.csv").write_text(DEPLOYMENT, encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "gh.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        "GH_TOKEN": "not-a-token",
        "GITHUB_RUN_ID": RUN_ID,
        "RESTORE_STATE_RETRY_SECONDS": "0",
        "FAKE_GH_LOG": str(log),
        "FAKE_GH_MODE": mode,
        "FAKE_GH_RUN": RUN_ID,
        "FAKE_GH_ARTIFACT": str(earlier),
    }
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _fold_step()[1]["run"]],
        cwd=work, env=env, capture_output=True, text=True, timeout=120,
    )
    return result, processed, log


# --------------------------------------------------------------------------
# The step itself, run over a re-run's data/processed.
# --------------------------------------------------------------------------

def test_a_rerun_uploads_the_first_attempt_s_round_as_well_as_its_own(tmp_path: Path) -> None:
    result, processed, log = _run_fold(tmp_path, "present")
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    # The run's OWN artifact, not the run before's.
    assert f"run download {RUN_ID} --name {ARTIFACT}" in log.read_text(encoding="utf-8")
    # Every row of both attempts, once each, in capture order.
    day_file = (processed / "line_movement" / f"{DAY}.csv").read_text(encoding="utf-8")
    assert day_file == BASE + ROUND_1 + ROUND_2
    # A store attempt 2 did not write at all comes back whole.
    assert (processed / "deployment" / f"{DAY}.csv").read_text(encoding="utf-8") == DEPLOYMENT


def test_a_run_whose_earlier_attempt_uploaded_nothing_is_not_a_fault(tmp_path: Path) -> None:
    result, processed, _ = _run_fold(tmp_path, "absent")
    assert result.returncode == 0, result.stdout + result.stderr
    day_file = (processed / "line_movement" / f"{DAY}.csv").read_text(encoding="utf-8")
    assert day_file == BASE + ROUND_2
    assert not (processed / "deployment").exists()


def test_an_earlier_attempt_that_cannot_be_downloaded_fails_the_step(tmp_path: Path) -> None:
    """Could not ask is not nothing there: the step goes red, so the upload
    that would delete the earlier attempt's copy does not run."""
    result, processed, log = _run_fold(tmp_path, "down")
    out = result.stdout + result.stderr
    assert result.returncode != 0, out
    assert "502" in out
    # Retried, not taken at the first failure.
    assert log.read_text(encoding="utf-8").count("run download") > 1
    day_file = (processed / "line_movement" / f"{DAY}.csv").read_text(encoding="utf-8")
    assert day_file == BASE + ROUND_2


def test_folding_a_run_reads_no_other_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--fold-run` lists nothing and downloads only the run it names."""
    module = load_script("restore_state.py")
    asked: list[tuple[str, ...]] = []

    def gh(*args: str) -> subprocess.CompletedProcess:
        asked.append(args)
        return subprocess.CompletedProcess(args, 1, "", module.NO_SUCH_ARTIFACT)

    monkeypatch.setattr(module, "_gh", gh)
    code = module.main(["--fold-run", "77", "--artifact", ARTIFACT,
                        "--dest", str(tmp_path)])
    assert code == 0
    assert [a[:3] for a in asked] == [("run", "download", "77")]


# --------------------------------------------------------------------------
# The workflow: the fold runs where it must, and a failed fold never overwrites.
# --------------------------------------------------------------------------

def test_the_fold_runs_on_every_re_run_before_the_captures_are_kept() -> None:
    fold_index, fold = _fold_step()
    [(keep_index, _)] = [(i, s) for i, s in _uploads(ARTIFACT) if s.get("name") == KEEP]
    assert fold_index < keep_index
    condition = str(fold.get("if", ""))
    # Whatever the captures did, as the upload itself runs `if: always()`.
    assert "always()" in condition
    # Only a re-run has an earlier attempt; the first attempt asks nothing.
    assert "github.run_attempt" in condition
    # It never makes the job stop before the uploads and the gates.
    assert fold.get("continue-on-error") is True
    assert "--artifact line-movement" in fold["run"]
    assert "--dest data/processed" in fold["run"]
    assert "GITHUB_RUN_ID" in fold["run"]
    assert "NHL_ODDS_API_KEY" not in json.dumps(fold)


def test_a_failed_fold_never_overwrites_the_earlier_attempt() -> None:
    fold_id = _fold_step()[1].get("id")
    assert fold_id, "the fold step needs an id for the uploads to read"
    failed = f"steps.{fold_id}.outcome == 'failure'"
    not_failed = f"steps.{fold_id}.outcome != 'failure'"
    [keep] = [step for _, step in _uploads(ARTIFACT) if step.get("name") == KEEP]
    assert keep["with"].get("overwrite") is True
    assert not_failed in str(keep.get("if", ""))
    # This attempt's captures are still kept, under their own name and
    # without overwriting anything, from the same paths.
    beside = [step for _, step in _uploads("run_attempt") if step is not keep]
    assert len(beside) == 1
    assert failed in str(beside[0].get("if", ""))
    assert not beside[0]["with"].get("overwrite")
    assert _paths(beside[0]) == _paths(keep)
    # And the run goes red, saying so.
    gates = [
        step for step in _steps()
        if failed in str(step.get("if", "")) and "exit 1" in str(step.get("run", ""))
    ]
    assert len(gates) == 1
    assert "::error::" in gates[0]["run"]
