"""Line Movement's capture chain is kept in the private repository too.

Stage one of the move Cooper chose on 2026-10-02 (closing-line data is never
published publicly; the chain is moved in stages): every round folds the
private copy (branch `movement` of cooperross399/nhl-closing-lines) into what
it restored from the public artifact, pushes its three stores there, and
checks that the private tip holds every row of what it then uploads
publicly. `scripts/private_movement_chain.py` does all three.

What must hold, and is driven here against a local bare repository standing
in for the private one:

* a push never drops a row the tip holds, keeps exact duplicates (a multiset,
  as `restore_state.union_csv` does), and touches only the files that changed;
* a pull makes a thin restore whole and never overwrites what it cannot merge;
* the check fails when the tip is short of anything uploaded publicly;
* the chain lives on its own branch and never touches the closing-line
  store's `main`;
* the workflow runs the pull before the paid fetch, the push and the check
  before the public upload, only from the default branch, and a red gate
  after every upload.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import _bash, _render

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_closing_store as store  # noqa: E402
import private_movement_chain as chain  # noqa: E402

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
HEADER = "date,commence_time,provider_event_id,home_team,away_team,market,player,selection,line,american_odds,book,fetched_at,captured_at\n"


def _row(n: int, book: str = "BetMGM") -> str:
    return (f"2026-10-08,2026-10-08T23:00:00Z,ev1,Toronto Maple Leafs,Boston Bruins,"
            f"player_points,P{n},over,0.5,{100 + n},{book},2026-10-08T14:00:00Z,2026-10-08T14:00:00Z\n")


def _write(processed: Path, rel: str, body: str) -> Path:
    path = processed / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _git(args: list[str], **kw) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, **kw).stdout


@pytest.fixture
def bare(tmp_path, monkeypatch) -> Path:
    """A private store with a seeded `main` (the closing-line store) and no
    movement chain yet; the privacy answer is replaced, the rest is real."""
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    path = tmp_path / "store.git"
    _git(["init", "-q", "--bare", "-b", "main", str(path)])
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(["init", "-q", "-b", "main"], cwd=seed)
    (seed / "captures").mkdir()
    # A readable closing-line store on main, so a pull of main writes a file
    # whose contents a test can look into.
    (seed / "captures" / "2026-10-08.csv").write_text(
        "captured_at,commence_time,home_team,away_team,market,player,selection,line,american_odds,book\n"
        "2026-10-08T22:00:00Z,2026-10-08T23:00:00Z,Toronto Maple Leafs,Boston Bruins,moneyline,,away,,120.0,MainOnlyBook\n")
    _git(["add", "-A"], cwd=seed)
    _git(["commit", "-qm", "seed"], cwd=seed)
    _git(["push", "-q", str(path), "HEAD:refs/heads/main"], cwd=seed)
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: True)
    monkeypatch.setattr(chain, "sleep", lambda seconds: None)
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return path


def _run(command: str, bare: Path, folder: Path) -> int:
    flag = "--dest" if command == "pull" else "--processed-dir"
    return chain.main([command, flag, str(folder), "--remote", f"file://{bare}"])


def _tip(bare: Path, ref: str = "movement") -> str:
    return _git(["--git-dir", str(bare), "rev-parse", ref]).strip()


def _show(bare: Path, rel: str) -> str:
    return _git(["--git-dir", str(bare), "show", f"movement:{rel}"])


def _changed(bare: Path) -> list[str]:
    return _git(["--git-dir", str(bare), "diff-tree", "--no-commit-id", "--name-only",
                 "-r", "movement"]).split()


LM = "line_movement/2026-10-08.csv"
LC = "line_combinations/2026-10-08.csv"
DP = "deployment/2026-10-08.csv"


@pytest.fixture
def run(tmp_path) -> Path:
    processed = tmp_path / "processed"
    _write(processed, LM, HEADER + _row(1) + _row(2))
    _write(processed, LC, "team,line\nTOR,1\n")
    _write(processed, DP, "team,player\nTOR,X\n")
    return processed


# --- push --------------------------------------------------------------------


def test_the_first_push_establishes_the_chain_byte_for_byte(bare, run) -> None:
    main_before = _tip(bare, "main")
    assert _run("push", bare, run) == chain.EXIT_OK
    for rel in (LM, LC, DP):
        assert _show(bare, rel) == (run / rel).read_text()
    assert _tip(bare, "main") == main_before, "the chain must never touch the closing store's main"


def test_a_second_push_of_the_same_files_commits_nothing(bare, run) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    tip = _tip(bare)
    assert _run("push", bare, run) == chain.EXIT_OK
    assert _tip(bare) == tip


def test_a_round_touches_only_the_files_it_appended_to(bare, run, monkeypatch) -> None:
    """Only the changed file is read from the tip or written: by April the
    chain is about 3.7 GB, and reading every day file each round would not
    fit the job."""
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    read = []
    real = chain.blob_to
    monkeypatch.setattr(chain, "blob_to", lambda work, sha, target: (read.append(sha), real(work, sha, target)))
    assert _run("push", bare, run) == chain.EXIT_OK
    assert _changed(bare) == [LM]
    assert _show(bare, LM) == HEADER + _row(1) + _row(2) + _row(3)
    assert len(read) == 1, f"read {len(read)} tip file(s) for one changed file"


def test_a_thin_run_never_drops_a_row_the_tip_holds(bare, run, tmp_path) -> None:
    """A runner whose restore came back thin (09-30 18:00) appends its round
    to a short file; the tip keeps every earlier row and gains the new one."""
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    assert _run("push", bare, run) == chain.EXIT_OK
    thin = tmp_path / "thin"
    _write(thin, LM, HEADER + _row(4))
    assert _run("push", bare, thin) == chain.EXIT_OK
    assert _show(bare, LM) == HEADER + _row(1) + _row(2) + _row(3) + _row(4)


def test_a_thin_run_with_nothing_new_pushes_nothing(bare, run, tmp_path) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    tip = _tip(bare)
    thin = tmp_path / "thin"
    _write(thin, LM, HEADER + _row(1))
    assert _run("push", bare, thin) == chain.EXIT_OK
    assert _tip(bare) == tip


def test_exact_duplicate_rows_are_kept(bare, run) -> None:
    """3.7% of the movement rows on 2026-10-02 were exact duplicates; the
    chain's own union keeps them, and so must the private copy."""
    _write(run, LM, HEADER + _row(1) + _row(1) + _row(2))
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(1) + _row(2) + _row(2))
    assert _run("push", bare, run) == chain.EXIT_OK
    assert _show(bare, LM) == HEADER + _row(1) + _row(1) + _row(2) + _row(2)


def test_duplicates_survive_a_merge_of_two_diverged_copies(bare, run, tmp_path) -> None:
    """Where duplicates matter: a thin restore or a race, when the tip and
    this run's copy have diverged and union_csv really merges them. Each row
    is kept as many times as the copy holding it most often has it."""
    _write(run, LM, HEADER + _row(1) + _row(1) + _row(2))
    assert _run("push", bare, run) == chain.EXIT_OK
    thin = tmp_path / "thin"
    _write(thin, LM, HEADER + _row(1) + _row(3) + _row(3))
    assert _run("push", bare, thin) == chain.EXIT_OK
    assert _show(bare, LM) == HEADER + _row(1) + _row(1) + _row(2) + _row(3) + _row(3)


def _damage_tip(bare: Path, tmp_path: Path, rel: str, body: str) -> str:
    clone = tmp_path / "clone"
    _git(["clone", "-q", "-b", "movement", str(bare), str(clone)])
    (clone / rel).write_text(body)
    _git(["commit", "-qam", "damage"], cwd=clone)
    _git(["push", "-q", "origin", "HEAD:movement"], cwd=clone)
    return _tip(bare)


def test_a_damaged_tip_file_is_named_and_every_other_file_still_pushed(bare, run, tmp_path, capsys) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    folded = HEADER + _row(1).replace("P1", '"P1') + _row(2).replace("P2", 'P2"')
    _damage_tip(bare, tmp_path, LM, folded)
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    _write(run, LC, "team,line\nTOR,1\nTOR,2\n")
    capsys.readouterr()  # only what the damaged push says counts below

    assert _run("push", bare, run) == chain.EXIT_DAMAGED

    assert _show(bare, LM) == folded, "a file that could not be merged was overwritten"
    assert _show(bare, LC) == "team,line\nTOR,1\nTOR,2\n"
    assert f"{LM} could not be pushed" in capsys.readouterr().out


def test_a_rejected_push_refetches_and_keeps_both_rounds(bare, run, tmp_path, monkeypatch) -> None:
    """Another writer lands between this push's fetch and its push: the push
    is rejected, refetches, re-merges, and both writers' rows are kept."""
    assert _run("push", bare, run) == chain.EXIT_OK
    real = chain.fetch_chain
    calls = {"n": 0}

    def racing(work, remote, token):
        tip = real(work, remote, token)
        calls["n"] += 1
        if calls["n"] == 1:
            _damage_tip(bare, tmp_path, LM, HEADER + _row(1) + _row(2) + _row(9))
        return tip

    monkeypatch.setattr(chain, "fetch_chain", racing)
    waited = []
    monkeypatch.setattr(chain, "sleep", waited.append)
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    assert _run("push", bare, run) == chain.EXIT_OK
    assert calls["n"] == 2
    assert waited == [2], "a rejected push waits before it tries again"
    assert sorted(_show(bare, LM).splitlines()[1:]) == sorted(
        (_row(1) + _row(2) + _row(9) + _row(3)).splitlines())
    # The retry's commit is built on the refetched tip, not on this round's
    # files alone: every file it did not change is still there.
    assert _show(bare, LC) == (run / LC).read_text()
    assert _show(bare, DP) == (run / DP).read_text()


def test_the_public_lab_and_a_public_store_are_refused(bare, run, monkeypatch) -> None:
    assert chain.main(["push", "--processed-dir", str(run), "--repo", store.PUBLIC_REPO,
                       "--remote", f"file://{bare}"]) == chain.EXIT_REFUSED
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: False)
    assert _run("push", bare, run) == chain.EXIT_REFUSED
    with pytest.raises(subprocess.CalledProcessError):
        _tip(bare)


def test_no_token_pushes_nothing(bare, run, monkeypatch) -> None:
    monkeypatch.delenv(store.TOKEN_ENV)
    assert chain.main(["push", "--processed-dir", str(run)]) == chain.EXIT_NO_TOKEN


# --- pull --------------------------------------------------------------------


def test_a_pull_into_an_empty_folder_lays_down_the_chain(bare, run, tmp_path) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    empty = tmp_path / "empty"
    assert _run("pull", bare, empty) == chain.EXIT_OK
    for rel in (LM, LC, DP):
        assert (empty / rel).read_text() == (run / rel).read_text()


def test_a_pull_makes_a_thin_restore_whole(bare, run, tmp_path) -> None:
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    assert _run("push", bare, run) == chain.EXIT_OK
    thin = tmp_path / "thin"
    _write(thin, LM, HEADER + _row(1))
    assert _run("pull", bare, thin) == chain.EXIT_OK
    assert sorted((thin / LM).read_text().splitlines()) == sorted(
        (HEADER + _row(1) + _row(2) + _row(3)).splitlines())


def test_a_pull_never_overwrites_what_it_cannot_merge(bare, run, tmp_path) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    other = tmp_path / "other"
    _write(other, LM, "a,different,header\n1,2,3\n")
    assert _run("pull", bare, other) == chain.EXIT_DAMAGED
    assert (other / LM).read_text() == "a,different,header\n1,2,3\n"


def test_no_chain_yet_is_its_own_answer(bare, tmp_path) -> None:
    assert _run("pull", bare, tmp_path / "x") == chain.EXIT_EMPTY


# --- verify ------------------------------------------------------------------


def test_the_check_passes_when_the_tip_holds_every_row(bare, run, tmp_path, monkeypatch) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert _run("push", bare, run) == chain.EXIT_OK
    assert _run("verify", bare, run) == chain.EXIT_OK
    assert "Private chain check passed" in summary.read_text()


def test_the_check_fails_when_the_tip_is_short(bare, run, tmp_path, monkeypatch, capsys) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3) + _row(3))
    _write(run, "deployment/2026-10-09.csv", "team,player\nTOR,Y\n")

    assert _run("verify", bare, run) == chain.EXIT_DAMAGED

    out = capsys.readouterr().out
    assert f"{LM}: 2 row(s) missing" in out
    assert "deployment/2026-10-09.csv: 1 row(s) missing" in out
    assert "FAILED" in summary.read_text()


def test_the_check_counts_copies_not_distinct_rows(bare, run) -> None:
    """A tip holding a row once does not hold it twice."""
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(1) + _row(2))
    assert _run("verify", bare, run) == chain.EXIT_DAMAGED


def test_the_closing_store_pull_never_reads_the_chain(bare, run, tmp_path, monkeypatch) -> None:
    """The chain's files have the capture columns; on `main` they would be
    scored as closing prices. The store's pull reads `main` only."""
    assert _run("push", bare, run) == chain.EXIT_OK
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    out = tmp_path / "pulled" / "closing_line_captures.csv"
    assert store.main(["pull", "--out", str(out), "--remote", f"file://{bare}"]) == store.EXIT_OK
    text = out.read_text()
    assert "MainOnlyBook" in text, "the pull did not read main"
    assert "P1" not in text and "BetMGM" not in text, "the pull read the movement chain"


# --- the workflow --------------------------------------------------------------


def _steps() -> list[dict]:
    (job,) = [j for j in yaml.safe_load(WORKFLOW.read_text())["jobs"].values()
              if any(s.get("id") == "private_push" for s in j.get("steps", []))]
    return job["steps"]


def _index(name: str) -> int:
    return [s.get("name") for s in _steps()].index(name)


DEFAULT_BRANCH = ("github.event_name == 'schedule' || github.ref == "
                  "format('refs/heads/{0}', github.event.repository.default_branch)")


def test_the_private_steps_sit_where_they_must() -> None:
    """Restore before the paid fetch; the push straight after the captures
    (the round's only home now), the seal and its upload after the push, the
    check after both, and every gate after every upload."""
    assert _index("Restore today's captures") < _index("Capture prices")
    # The check comes before the seal, so a push that exited 0 but left the
    # tip short is sealed too.
    assert (_index("Capture line combinations") < _index("Keep the captures privately")
            < _index("Check the private chain holds this round")
            < _index("Seal this round when the private chain did not take it") < _index("Keep the sealed round")
            < _index("Scan the captured ladders"))
    gate = _index("Fail the run when the private chain was not kept")
    uploads = [i for i, s in enumerate(_steps()) if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert gate > max(uploads)


def test_no_step_uploads_the_chain_publicly() -> None:
    """Stage two: the only artifacts are the encrypted seal and the
    aggregate ladder scan."""
    names = {str(s["with"].get("name")) for s in _steps()
             if str(s.get("uses", "")).startswith("actions/upload-artifact")}
    assert names == {"line-movement-sealed-${{ github.run_attempt }}", "ladder-coherence"}
    sealed = _steps()[_index("Keep the sealed round")]
    assert sealed["with"]["path"] == "${{ runner.temp }}/sealed/round.enc"
    assert sealed["with"]["retention-days"] == 7
    assert sealed["if"] == "always() && steps.seal.outcome == 'success'"


def test_only_the_default_branch_writes_the_chain() -> None:
    for name in ("Keep the captures privately", "Check the private chain holds this round"):
        step = _steps()[_index(name)]
        assert step["if"] == f"always() && ({DEFAULT_BRANCH})", name
        assert step.get("continue-on-error") is True
    seal = _steps()[_index("Seal this round when the private chain did not take it")]
    assert seal["if"] == ("always() && (steps.private_push.outcome == 'failure' "
                          "|| steps.private_verify.outcome == 'failure')")


def test_the_secrets_reach_only_the_steps_that_need_them() -> None:
    token = {s.get("name") for s in _steps() if "secrets.NHL_CLOSING_LINES_TOKEN" in yaml.safe_dump(s)}
    assert token == {"Restore today's captures", "Keep the captures privately",
                     "Check the private chain holds this round"}
    key = {s.get("name") for s in _steps() if "secrets.NHL_CHAIN_FALLBACK_KEY" in yaml.safe_dump(s)}
    assert key == {"Restore today's captures", "Seal this round when the private chain did not take it"}


def _restore_block(tmp_path: Path, pull: int, unseal: int) -> tuple[subprocess.CompletedProcess, str]:
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "python").write_text(
        "#!/bin/sh\n"
        f'case "$2" in pull) exit {pull} ;; unseal) exit {unseal} ;; esac\nexit 0\n')
    (stub / "python").chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    step = _steps()[_index("Restore today's captures")]
    done = _bash(_render(step["run"], {}), work,
                 {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"})
    return done, (work / "restore_problem.txt").read_text()


@pytest.mark.parametrize(("pull", "unseal", "problem"), [
    (0, 0, False), (4, 0, False),
    (1, 0, True), (2, 0, True), (3, 0, True), (5, 0, True),
    (0, 1, True), (0, 2, True), (0, 3, True),
])
def test_the_restore_reports_everything_but_a_clean_read_or_no_chain(tmp_path, pull, unseal, problem) -> None:
    done, text = _restore_block(tmp_path, pull, unseal)
    assert done.returncode == 0, "the restore never stops the paid capture"
    assert bool(text.strip()) is problem


def _gate(outcomes: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess:
    step = _steps()[_index("Fail the run when the private chain was not kept")]
    values = {f"steps.{k}.outcome": v for k, v in outcomes.items()}
    values["github.run_attempt"] = "1"
    work = tmp_path / "gate"
    work.mkdir()
    return _bash(_render(step["run"], values), work, dict(os.environ))


OK = {"private_push": "success", "seal": "skipped", "sealed_upload": "skipped", "private_verify": "success"}


@pytest.mark.parametrize(("change", "red", "says"), [
    ({}, False, ""),
    ({"private_push": "skipped", "private_verify": "skipped"}, False, ""),
    ({"private_push": "failure", "seal": "success", "sealed_upload": "success"}, True, "It was sealed"),
    ({"private_push": "failure", "seal": "failure", "sealed_upload": "skipped"}, True, "on no copy"),
    ({"private_push": "failure", "seal": "success", "sealed_upload": "failure"}, True, "upload: failure"),
    ({"private_verify": "failure", "seal": "success", "sealed_upload": "success"}, True, "check: failure"),
    ({"private_verify": "failure", "seal": "failure", "sealed_upload": "skipped"}, True, "on no copy"),
])
def test_the_gate_is_red_for_every_fault_and_says_where_the_round_is(tmp_path, change, red, says) -> None:
    done = _gate({**OK, **change}, tmp_path)
    assert (done.returncode != 0) is red, done.stdout + done.stderr
    assert says in done.stdout


# --- the second review's findings ----------------------------------------------


def test_an_interrupted_copy_leaves_no_truncated_day_file(bare, run, tmp_path, monkeypatch) -> None:
    """A pull cut off mid-copy must not leave half a day file for the
    capture to append to: the copy is written whole or not at all."""
    assert _run("push", bare, run) == chain.EXIT_OK
    real = subprocess.run

    def cut_off(command, *a, **kw):
        if command[:3] == ["git", "cat-file", "blob"]:
            kw["stdout"].write(b"date,commence_time,half a ro")
            raise KeyboardInterrupt("the step was cancelled")
        return real(command, *a, **kw)

    monkeypatch.setattr(chain.subprocess, "run", cut_off)
    empty = tmp_path / "empty"
    with pytest.raises(KeyboardInterrupt):
        _run("pull", bare, empty)
    leftovers = [p for p in empty.rglob("*") if p.is_file()]
    assert leftovers == [], leftovers


def test_a_fetch_that_fails_once_is_tried_again(bare, run, monkeypatch) -> None:
    real = chain.fetch_chain_once
    calls = {"n": 0}

    def flaky(work, remote, token):
        calls["n"] += 1
        if calls["n"] == 1:
            raise store.Unreachable("Could not resolve host: github.com")
        return real(work, remote, token)

    waited = []
    monkeypatch.setattr(chain, "fetch_chain_once", flaky)
    monkeypatch.setattr(chain, "sleep", waited.append)
    assert _run("push", bare, run) == chain.EXIT_OK
    assert calls["n"] == 2 and waited == [5]


def test_a_fetch_that_never_answers_is_a_failure_not_an_empty_chain(bare, run, monkeypatch) -> None:
    def down(work, remote, token):
        raise store.Unreachable("Could not resolve host: github.com")

    monkeypatch.setattr(chain, "fetch_chain_once", down)
    assert _run("push", bare, run) == chain.EXIT_FAILED
    assert _run("pull", bare, run) == chain.EXIT_FAILED


def test_a_file_the_tip_holds_byte_for_byte_passes_the_check_whatever_it_holds(bare, run) -> None:
    """A day file whose own parse is ragged, but which the tip holds byte for
    byte, is held; it must not turn every later round red."""
    _write(run, DP, 'team,player\nTOR,"X\nTOR,Y\n')
    assert _run("push", bare, run) == chain.EXIT_OK
    assert _run("verify", bare, run) == chain.EXIT_OK


@pytest.mark.parametrize(("name", "command", "bound"), [
    ("Restore today's captures", "python scripts/private_movement_chain.py pull --dest data/processed", 4),
    ("Restore today's captures", "python scripts/private_movement_chain.py unseal --dest data/processed", 4),
    ("Keep the captures privately", "python scripts/private_movement_chain.py push --processed-dir data/processed", 6),
    ("Seal this round when the private chain did not take it",
     'python scripts/private_movement_chain.py seal --processed-dir data/processed --out "$RUNNER_TEMP/sealed/round.enc"', 2),
    ("Check the private chain holds this round", "python scripts/private_movement_chain.py verify --processed-dir data/processed", 4),
])
def test_each_private_step_is_bounded_soft_and_pointed_at_the_chain(name, command, bound) -> None:
    """Soft, so it never costs the capture or the upload; bounded, inside the
    20-minute job; and pointed at the folder the restore and the uploads use."""
    step = _steps()[_index(name)]
    assert step.get("continue-on-error") is True
    assert step["timeout-minutes"] <= bound
    assert command in step["run"]


def test_an_empty_folder_is_not_a_passing_check(bare, run, tmp_path) -> None:
    """A check pointed at the wrong folder sees no file; that is not a pass."""
    assert _run("push", bare, run) == chain.EXIT_OK
    empty = tmp_path / "nothing-here"
    empty.mkdir()
    assert _run("verify", bare, empty) == chain.EXIT_DAMAGED


# --- the third review's test holes ---------------------------------------------


def test_the_check_fails_on_a_tip_copy_it_cannot_read(bare, run, tmp_path) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    _damage_tip(bare, tmp_path, LM, HEADER + _row(1).replace("P1", '"P1') + _row(2).replace("P2", 'P2"'))
    assert _run("verify", bare, run) == chain.EXIT_DAMAGED


def test_the_check_fails_on_a_header_that_changed(bare, run, tmp_path) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    _damage_tip(bare, tmp_path, LM, HEADER.replace("captured_at", "captured") + _row(1) + _row(2))
    assert _run("verify", bare, run) == chain.EXIT_DAMAGED


def test_the_check_with_no_chain_is_not_a_pass(bare, run) -> None:
    assert _run("verify", bare, run) == chain.EXIT_EMPTY


def test_the_gate_reads_steps_that_exist() -> None:
    """GitHub reads an unknown step id as an empty outcome, and "" is not
    "failure": a renamed id would silence the gate."""
    ids = {s.get("id") for s in _steps()}
    gate = _steps()[_index("Fail the run when the private chain was not kept")]["run"]
    named = set(re.findall(r"steps\.(\w+)\.outcome", gate))
    assert named == {"private_push", "seal", "sealed_upload", "private_verify"}
    assert named <= ids


# --- stage two: the sealed fallback ----------------------------------------------


KEY = "a-test-key-that-is-not-the-real-one"


@pytest.fixture
def sealed_env(monkeypatch, tmp_path):
    monkeypatch.setenv(chain.KEY_ENV, KEY)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    return tmp_path / "runner_temp" / "sealed" / "round.enc"


def _offer(monkeypatch, sealed_files: list[Path]) -> None:
    """GitHub's listing and download, replaced by the sealed files given."""
    artifacts = [{"id": i, "name": f"{chain.SEALED_PREFIX}1", "expired": False,
                  "workflow_run": {"id": 100 + i, "head_branch": "main"},
                  "created_at": f"2026-10-0{i + 1}T00:00:00Z"} for i, _ in enumerate(sealed_files)]
    monkeypatch.setattr(chain, "list_sealed", lambda repo: artifacts)
    monkeypatch.setattr(chain, "download_sealed",
                        lambda repo, artifact, target: target.write_bytes(sealed_files[artifact["id"]].read_bytes()))


def _seal(run: Path, out: Path) -> int:
    return chain.main(["seal", "--processed-dir", str(run), "--out", str(out)])


def test_a_sealed_round_is_not_readable_without_the_key(sealed_env, run) -> None:
    assert _seal(run, sealed_env) == chain.EXIT_OK
    data = sealed_env.read_bytes()
    assert b"BetMGM" not in data and b"Toronto" not in data and b"line_movement" not in data


def test_a_sealed_round_comes_home_with_the_next_round(sealed_env, run, tmp_path, monkeypatch) -> None:
    """Seal, then a later round with a thin disk unseals it: every row is
    back, and the next push would carry it into the chain."""
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    later = tmp_path / "later"
    _write(later, LM, HEADER + _row(1))
    assert chain.main(["unseal", "--dest", str(later), "--github-repo", "o/r"]) == chain.EXIT_OK
    assert sorted((later / LM).read_text().splitlines()) == sorted(
        (HEADER + _row(1) + _row(2) + _row(3)).splitlines())
    assert (later / LC).read_text() == (run / LC).read_text()


def test_unsealing_twice_adds_nothing(sealed_env, run, tmp_path, monkeypatch) -> None:
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    later = tmp_path / "later"
    assert chain.main(["unseal", "--dest", str(later), "--github-repo", "o/r"]) == chain.EXIT_OK
    first = (later / LM).read_text()
    assert chain.main(["unseal", "--dest", str(later), "--github-repo", "o/r"]) == chain.EXIT_OK
    assert (later / LM).read_text() == first


def test_the_wrong_key_opens_nothing_and_says_so(sealed_env, run, tmp_path, monkeypatch, capsys) -> None:
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    monkeypatch.setenv(chain.KEY_ENV, "another-key")
    later = tmp_path / "later"
    _write(later, LM, HEADER + _row(1))
    assert chain.main(["unseal", "--dest", str(later), "--github-repo", "o/r"]) == chain.EXIT_DAMAGED
    assert (later / LM).read_text() == HEADER + _row(1)
    assert "could not be decrypted" in capsys.readouterr().out


def test_no_key_cannot_seal(run, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(chain.KEY_ENV, raising=False)
    out = tmp_path / "x" / "round.enc"
    assert _seal(run, out) == chain.EXIT_NO_TOKEN
    assert not out.exists()


def test_sealed_rounds_without_a_key_are_a_fault_and_none_are_not(sealed_env, run, tmp_path, monkeypatch) -> None:
    assert _seal(run, sealed_env) == chain.EXIT_OK
    monkeypatch.delenv(chain.KEY_ENV)
    _offer(monkeypatch, [sealed_env])
    assert chain.main(["unseal", "--dest", str(tmp_path / "d"), "--github-repo", "o/r"]) == chain.EXIT_NO_TOKEN
    _offer(monkeypatch, [])
    assert chain.main(["unseal", "--dest", str(tmp_path / "d"), "--github-repo", "o/r"]) == chain.EXIT_OK


def test_a_seal_inside_the_workspace_is_refused(run, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(chain.KEY_ENV, KEY)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    assert _seal(run, tmp_path / "data" / "round.enc") == chain.EXIT_REFUSED


def test_an_archive_with_a_member_outside_the_stores_is_refused(sealed_env, tmp_path, monkeypatch) -> None:
    """A sealed archive is opened only into the three stores' day files."""
    import tarfile
    evil = tmp_path / "evil"
    _write(evil, "line_movement/2026-10-08.csv", HEADER + _row(1))
    _write(evil, "notes.txt", "x")
    bundle = tmp_path / "round.tar"
    with tarfile.open(bundle, "w") as tar:
        tar.add(evil / "line_movement/2026-10-08.csv", arcname="line_movement/2026-10-08.csv")
        tar.add(evil / "notes.txt", arcname="../outside/notes.txt")
    sealed_env.parent.mkdir(parents=True, exist_ok=True)
    assert chain._openssl(["-e", "-salt"], bundle, sealed_env).returncode == 0
    _offer(monkeypatch, [sealed_env])
    dest = tmp_path / "dest"
    assert chain.main(["unseal", "--dest", str(dest), "--github-repo", "o/r"]) == chain.EXIT_DAMAGED
    assert not (tmp_path / "outside").exists()
    assert not dest.exists() or not any(dest.rglob("*.csv"))


def test_the_listing_keeps_only_unexpired_sealed_rounds_from_this_repos_default_branch(monkeypatch) -> None:
    """Fail closed: a fork's pull request runs in this repository's context
    and could upload the same name from a branch it calls main."""
    import json as _json
    run = {"head_branch": "main", "repository_id": 7, "head_repository_id": 7}
    rows = [
        {"name": "line-movement-sealed-1", "expired": False, "workflow_run": run, "created_at": "2"},
        {"name": "line-movement-sealed-2", "expired": True, "workflow_run": run, "created_at": "3"},
        {"name": "line-movement-sealed-1", "expired": False, "workflow_run": {**run, "head_branch": "feature"}, "created_at": "4"},
        {"name": "line-movement-sealed-1", "expired": False, "workflow_run": {**run, "head_repository_id": 99}, "created_at": "6"},
        {"name": "line-movement-sealed-1", "expired": False, "workflow_run": {"head_branch": "main"}, "created_at": "7"},
        {"name": "line-movement-sealed-1", "expired": False, "created_at": "8"},
        {"name": "ladder-coherence", "expired": False, "workflow_run": run, "created_at": "5"},
        {"name": "line-movement-sealed-3", "expired": False, "workflow_run": run, "created_at": "1"},
    ]

    class Done:
        returncode, stderr = 0, ""
        stdout = "\n".join(_json.dumps(r) for r in rows)

    monkeypatch.setattr(chain.subprocess, "run", lambda *a, **k: Done())
    monkeypatch.delenv("NHL_DEFAULT_BRANCH", raising=False)
    found = chain.list_sealed("o/r")
    assert [(f["name"], f["created_at"]) for f in found] == [
        ("line-movement-sealed-3", "1"), ("line-movement-sealed-1", "2")]
    monkeypatch.setenv("NHL_DEFAULT_BRANCH", "trunk")
    assert chain.list_sealed("o/r") == [], "NHL_DEFAULT_BRANCH overrides main"


def test_a_listing_that_fails_once_is_asked_again(monkeypatch) -> None:
    calls = {"n": 0}

    class Done:
        def __init__(self, code, stdout=""):
            self.returncode, self.stdout, self.stderr = code, stdout, "HTTP 502"

    def gh(command, *a, **k):
        calls["n"] += 1
        return Done(1) if calls["n"] == 1 else Done(0, "")

    waited = []
    monkeypatch.setattr(chain.subprocess, "run", gh)
    monkeypatch.setattr(chain, "sleep", waited.append)
    assert chain.list_sealed("o/r") == []
    assert waited == [5]
