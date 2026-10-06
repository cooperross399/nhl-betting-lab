"""Line Movement's capture chain is kept in the private repository only.

The move Cooper chose on 2026-10-02 (closing-line data is never published
publicly; the chain is moved in stages). Since stage two, every round pulls
the chain (branch `movement` of cooperross399/nhl-closing-lines) and folds in
any sealed fallback round, pushes its three stores there, checks that the
private tip holds every row on its disk, and seals the round (encrypted,
7-day artifact) only when that check did not pass.
`scripts/private_movement_chain.py` does all of it.

What must hold, and is driven here against a local bare repository standing
in for the private one:

* a push never drops a row the tip holds, keeps exact duplicates (a multiset,
  as `restore_state.union_csv` does), and touches only the files that changed;
* a pull makes a thin restore whole and never overwrites what it cannot merge;
* the check fails when the tip is short of anything uploaded publicly;
* the chain lives on its own branch and never touches the closing-line
  store's `main`;
* the workflow runs the pull before the paid fetch, the push, the check and
  the seal after the captures, only from the default branch, and a red gate
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


def _run(command: str, bare: Path, folder: Path, *, seed: bool = True) -> int:
    """`seed` lets a push create the movement branch, as the one-off seed of
    2026-10-02 did; no workflow passes it, and a test of the refusal sets
    seed=False."""
    flag = "--dest" if command == "pull" else "--processed-dir"
    extra = ["--allow-new-chain"] if command == "push" and seed else []
    return chain.main([command, flag, str(folder), "--remote", f"file://{bare}", *extra])


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
    assert f"{LM} could not be merged into the private chain" in capsys.readouterr().out


def test_a_rejected_push_refetches_and_keeps_both_rounds(bare, run, tmp_path, monkeypatch) -> None:
    """Another writer lands between this push's fetch and its push: the push
    is rejected, refetches, re-merges, and both writers' rows are kept."""
    assert _run("push", bare, run) == chain.EXIT_OK
    real = chain.fetch_chain
    calls = {"n": 0}

    def racing(work, remote, token, **kw):
        tip = real(work, remote, token, **kw)
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
    # The check is the authority on whether the round is home: a push that
    # failed while the check passed (an earlier attempt landed, or a copy kept
    # as a sidecar) has nothing to seal, and a check that failed, timed out or
    # was cancelled is sealed whatever the push said.
    seal = _steps()[_index("Seal this round when the private chain did not take it")]
    assert seal["if"] == ("always() && steps.private_verify.outcome != 'success' "
                          "&& steps.private_verify.outcome != 'skipped'")


def test_the_push_step_is_the_one_command_the_tests_replay() -> None:
    push = _steps()[_index("Keep the captures privately")]["run"]
    assert push.strip() == "python scripts/private_movement_chain.py push --processed-dir data/processed"


@pytest.mark.parametrize("outcome", ["pushed", "sidecar", "crashed"])
def test_the_push_hands_its_exit_to_the_gate(bare, run, tmp_path, monkeypatch, outcome) -> None:
    """The gate words a sidecar (push exit 2) apart from any other failed
    push, so the push writes its exit to the step's outputs, whatever ends
    it; a crash is recorded as the 1 Python exits with."""
    output = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    if outcome == "pushed":
        assert _run("push", bare, run) == chain.EXIT_OK
        assert output.read_text() == "exit=0\n"
        return
    assert _run("push", bare, run) == chain.EXIT_OK
    output.unlink()
    if outcome == "sidecar":
        _damage_tip(bare, tmp_path, LM, HEADER.replace("captured_at", "captured") + _row(1))
        _write(run, LM, HEADER + _row(1) + _row(2))
        assert _run("push", bare, run) == chain.EXIT_DAMAGED
        assert output.read_text() == "exit=2\n"
        return

    def crash(*args, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(chain, "local_files", crash)
    with pytest.raises(RuntimeError):
        _run("push", bare, run)
    assert output.read_text() == "exit=1\n"


def test_the_secrets_reach_only_the_steps_that_need_them() -> None:
    token = {s.get("name") for s in _steps() if "secrets.NHL_CLOSING_LINES_TOKEN" in yaml.safe_dump(s)}
    assert token == {"Restore today's captures", "Keep the captures privately",
                     "Check the private chain holds this round",
                     "Seal this round when the private chain did not take it"}
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
    (0, 0, False),
    (4, 0, True), (1, 0, True), (2, 0, True), (3, 0, True), (5, 0, True),
    (0, 1, True), (0, 2, True), (0, 3, True),
])
def test_the_restore_reports_everything_but_a_clean_read_or_no_chain(tmp_path, pull, unseal, problem) -> None:
    done, text = _restore_block(tmp_path, pull, unseal)
    assert done.returncode == 0, "the restore never stops the paid capture"
    assert bool(text.strip()) is problem


def _gate(outcomes: dict[str, str], tmp_path: Path, *, on_disk: str | None = LM,
          push_exit: str = "") -> subprocess.CompletedProcess:
    """The gate as the runner renders it. `on_disk` is the one day file the
    round holds (None: none at all); `push_exit` is the push step's output."""
    step = _steps()[_index("Fail the run when the private chain was not kept")]
    values = {f"steps.{k}.outcome": v for k, v in outcomes.items()}
    values["github.run_attempt"] = "1"
    values["steps.private_push.outputs.exit"] = push_exit
    work = tmp_path / "gate"
    work.mkdir(parents=True)
    if on_disk:
        _write(work / "data" / "processed", on_disk, HEADER + _row(1))
    return _bash(_render(step["run"], values), work, dict(os.environ))


OK = {"private_push": "success", "seal": "skipped", "sealed_upload": "skipped", "private_verify": "success"}


BOTH_FAILED = {"private_push": "failure", "private_verify": "failure"}


@pytest.mark.parametrize(("change", "push_exit", "red", "says", "never"), [
    ({}, "0", False, "", "::error::"),
    ({"private_push": "skipped", "private_verify": "skipped"}, "", False, "", "::error::"),
    # The check passed: the round is home and nothing was sealed.
    ({"private_push": "failure"}, "1", True, "nothing was sealed and nothing is lost", "on no copy"),
    ({"private_push": "failure"}, "2", True, "Merging a sidecar", "It was sealed"),
    # Killed by its time limit before it could record an exit.
    ({"private_push": "failure"}, "", True, "not recorded", "Merging a sidecar"),
    # The check failed: sealed, or on no copy.
    ({**BOTH_FAILED, "seal": "success", "sealed_upload": "success"}, "1", True, "It was sealed", "on no copy"),
    ({**BOTH_FAILED, "seal": "failure", "sealed_upload": "skipped"}, "1", True, "on no copy", "It was sealed"),
    ({**BOTH_FAILED, "seal": "success", "sealed_upload": "failure"}, "1", True, "upload: failure", "It was sealed"),
    ({"private_verify": "failure", "seal": "success", "sealed_upload": "success"}, "0", True, "check: failure", "on no copy"),
    ({"private_verify": "failure", "seal": "failure", "sealed_upload": "skipped"}, "0", True, "on no copy", "It was sealed"),
])
def test_the_gate_is_red_for_every_fault_and_says_where_the_round_is(tmp_path, change, push_exit, red, says, never) -> None:
    done = _gate({**OK, **change}, tmp_path, push_exit=push_exit)
    assert (done.returncode != 0) is red, done.stdout + done.stderr
    assert says in done.stdout
    assert never not in done.stdout


@pytest.mark.parametrize("folder", chain.STORES)
def test_a_lone_day_file_in_any_store_is_never_called_safe(tmp_path, folder) -> None:
    """The gate tells "nothing captured" from "lost" by globbing the three
    stores; a day file in any one of them alone is a captured round."""
    rel = f"{folder}/2026-10-08.csv"
    lost = _gate({**OK, "private_verify": "failure", "seal": "failure", "sealed_upload": "skipped"},
                 tmp_path / "lost", on_disk=rel)
    assert "on no copy" in lost.stdout and "holds no day file" not in lost.stdout
    sealed = _gate({**OK, "private_verify": "failure", "seal": "success", "sealed_upload": "success"},
                   tmp_path / "sealed", on_disk=rel)
    assert "It was sealed" in sealed.stdout and "holds no day file" not in sealed.stdout


def test_the_gate_globs_exactly_the_chains_stores() -> None:
    gate = _steps()[_index("Fail the run when the private chain was not kept")]["run"]
    assert set(re.findall(r"data/processed/(\w+)/\*\.csv", gate)) == set(chain.STORES)


def test_a_round_with_nothing_on_disk_is_not_called_lost(tmp_path) -> None:
    """A failed restore on a night with no games leaves no day file: the
    check fails and there is nothing to seal, but no captured row is
    anywhere but the chain, and the gate says so instead of "on no copy"."""
    done = _gate({**OK, "private_verify": "failure", "seal": "failure", "sealed_upload": "skipped"},
                 tmp_path, on_disk=None)
    assert done.returncode != 0
    assert "holds no day file at all" in done.stdout
    assert "on no copy" not in done.stdout


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

    def flaky(work, remote, token, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise store.Unreachable("Could not resolve host: github.com")
        return real(work, remote, token, **kw)

    waited = []
    monkeypatch.setattr(chain, "fetch_chain_once", flaky)
    monkeypatch.setattr(chain, "sleep", waited.append)
    assert _run("push", bare, run) == chain.EXIT_OK
    assert calls["n"] == 2 and waited == [5]


def test_a_fetch_that_never_answers_is_a_failure_not_an_empty_chain(bare, run, monkeypatch) -> None:
    def down(work, remote, token, **kw):
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
    assert set(re.findall(r"steps\.(\w+)\.outputs\.exit", gate)) == {"private_push"}
    assert "private_push" in ids


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
    monkeypatch.setenv(chain.KEY_ENV, "another-key-that-is-long-enough-to-use-1234")
    later = tmp_path / "later"
    _write(later, LM, HEADER + _row(1))
    assert chain.main(["unseal", "--dest", str(later), "--github-repo", "o/r"]) == chain.EXIT_DAMAGED
    assert (later / LM).read_text() == HEADER + _row(1)
    assert "could not be decrypted" in capsys.readouterr().out


def test_a_wrong_key_that_slips_past_the_padding_check_is_still_named(sealed_env, run, tmp_path, monkeypatch, capsys) -> None:
    """CBC has no check of its own: about once in 256 a wrong key decrypts
    "successfully" into noise. That is still a wrong key, said as one."""
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    real = chain._openssl

    def noise(args, source, target):
        if args == ["-d"]:
            target.write_bytes(bytes(range(256)) * 4)
            return subprocess.CompletedProcess(args, 0, "", "")
        return real(args, source, target)

    monkeypatch.setattr(chain, "_openssl", noise)
    later = tmp_path / "later"
    _write(later, LM, HEADER + _row(1))
    capsys.readouterr()
    assert chain.main(["unseal", "--dest", str(later), "--github-repo", "o/r"]) == chain.EXIT_DAMAGED
    out = capsys.readouterr().out
    assert "could not be decrypted" in out and "a different key sealed it" in out
    assert (later / LM).read_text() == HEADER + _row(1)


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
        # Same repository, no branch at all: only the branch check refuses it.
        {"name": "line-movement-sealed-1", "expired": False,
         "workflow_run": {"repository_id": 7, "head_repository_id": 7}, "created_at": "9"},
        {"name": "line-movement-sealed-1", "expired": False,
         "workflow_run": {**run, "head_branch": None}, "created_at": "10"},
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


# --- the stage-two review's fixes -------------------------------------------------


def test_a_missing_chain_is_never_recreated_by_a_round(bare, run, capsys) -> None:
    """The chain has existed since 2026-10-02. A deleted branch must not
    come back as a thin chain holding one round, every gate green."""
    assert _run("push", bare, run, seed=False) == chain.EXIT_REFUSED
    with pytest.raises(subprocess.CalledProcessError):
        _tip(bare)
    assert "no `movement` branch" in capsys.readouterr().out


def test_an_older_copy_that_extends_the_newer_is_taken_whole(tmp_path) -> None:
    """The reverse of union_csv's fast path: a sealed copy that extends a
    disk copy byte for byte folds in without a parse, even when an earlier
    row is ragged (each append extends the bytes; only a parse refuses)."""
    from restore_state import union_csv
    ragged = HEADER + _row(1).replace("P1", '"P1')
    newer, older = tmp_path / "newer.csv", tmp_path / "older.csv"
    newer.write_text(ragged)
    older.write_text(ragged + _row(2))
    assert union_csv(older, newer) == 1
    assert newer.read_text() == ragged + _row(2)


def test_an_unmergeable_copy_is_kept_as_a_private_sidecar_and_counts_as_held(bare, run, tmp_path, capsys, monkeypatch) -> None:
    """Not stranded in a seal that expires: the push keeps this run's copy on
    the private branch beside the tip's, names it, and the check counts it
    as held, so the round is not sealed into an artifact no later round can
    fold."""
    assert _run("push", bare, run) == chain.EXIT_OK
    _damage_tip(bare, tmp_path, LM, HEADER.replace("captured_at", "captured") + _row(1))
    _write(run, LM, HEADER + _row(1) + _row(2))
    capsys.readouterr()

    assert _run("push", bare, run) == chain.EXIT_DAMAGED

    out = capsys.readouterr().out
    sidecars = _git(["--git-dir", str(bare), "ls-tree", "-r", "--name-only", "movement", "--", "unmerged"]).split()
    assert len(sidecars) == 1 and sidecars[0].startswith("unmerged/line_movement/2026-10-08/")
    assert _git(["--git-dir", str(bare), "show", f"movement:{sidecars[0]}"]) == HEADER + _row(1) + _row(2)
    assert sidecars[0] in out
    # Set only now, so only the check below writes to it.
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert _run("verify", bare, run) == chain.EXIT_OK
    # Every later check warns while the sidecar waits, in the log and in the
    # run summary, because only the round that kept it is red and its rows
    # reach no reader until merged.
    warned = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::warning::")]
    assert len(warned) == 1 and "1 sidecar(s) on the private chain await a hand merge" in warned[0]
    assert sidecars[0] in warned[0]
    written = summary.read_text()
    assert "Private chain check passed" in written
    assert "1 sidecar(s) on the private chain await a hand merge" in written and sidecars[0] in written
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    assert _run("push", bare, run) == chain.EXIT_OK, "the same copy is not damage twice"


def test_a_sealed_copy_already_home_is_skipped_and_one_that_cannot_merge_is_parked(
    sealed_env, bare, run, tmp_path, monkeypatch, capsys
) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    later = tmp_path / "later"
    _write(later, LM, "a,different,header\n1,2,3\n")
    unseal = ["unseal", "--dest", str(later), "--github-repo", "o/r", "--remote", f"file://{bare}"]

    # The tip holds every sealed file byte for byte: all skipped.
    assert chain.main(unseal) == chain.EXIT_OK
    assert (later / LM).read_text() == "a,different,header\n1,2,3\n"
    assert "already home" in capsys.readouterr().out

    # A sealed copy the tip does not hold, and that cannot merge with the
    # one on disk, is parked as a sidecar for the push, never dropped.
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(7))
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    assert chain.main(unseal) == chain.EXIT_DAMAGED
    parked = list((later / chain.UNMERGED).rglob("*.csv"))
    assert len(parked) == 1 and _row(7) in parked[0].read_text()
    assert _run("push", bare, later) in (chain.EXIT_OK, chain.EXIT_DAMAGED)
    on_branch = _git(["--git-dir", str(bare), "ls-tree", "-r", "--name-only", "movement", "--", "unmerged"]).split()
    assert parked[0].relative_to(later).as_posix() in on_branch
    # The parked sidecar, now on the tip as itself, is held: the check passes,
    # and a later seal from this folder carries only what is new, not the
    # parked copy that is already home.
    assert _run("verify", bare, later) == chain.EXIT_OK
    import tarfile
    _write(later, LC, "team,line\nTOR,1\nMTL,2\n")
    out = tmp_path / "again" / "round.enc"
    assert chain.main(["seal", "--processed-dir", str(later), "--out", str(out),
                       "--remote", f"file://{bare}"]) == chain.EXIT_OK
    opened = tmp_path / "again.tar"
    assert chain._openssl(["-d"], out, opened).returncode == 0
    with tarfile.open(opened) as tar:
        assert tar.getnames() == [LC]


def test_a_seal_holds_only_what_the_tip_lacks(sealed_env, bare, run, tmp_path, monkeypatch) -> None:
    import tarfile
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    out = tmp_path / "seal" / "round.enc"
    assert chain.main(["seal", "--processed-dir", str(run), "--out", str(out),
                       "--remote", f"file://{bare}"]) == chain.EXIT_OK
    opened = tmp_path / "opened.tar"
    assert chain._openssl(["-d"], out, opened).returncode == 0
    # Compressed: when the tip cannot be listed a seal is the whole season,
    # and every restore for a week downloads it.
    with tarfile.open(opened, "r:gz") as tar:
        assert tar.getnames() == [LM]


@pytest.mark.parametrize(("key", "code"), [
    ("", chain.EXIT_NO_TOKEN),
    ("short-key", chain.EXIT_REFUSED),
    (" " + "x" * 40, chain.EXIT_REFUSED),
    ("x" * 40 + "\n", chain.EXIT_REFUSED),
])
def test_a_weak_key_seals_nothing(run, tmp_path, monkeypatch, key, code) -> None:
    monkeypatch.setenv(chain.KEY_ENV, key)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    out = tmp_path / "x" / "round.enc"
    assert _seal(run, out) == code
    assert not out.exists()


@pytest.mark.parametrize("command", ["seal", "unseal"])
def test_a_blank_key_is_a_missing_secret_and_says_so(sealed_env, run, tmp_path, monkeypatch, capsys, command) -> None:
    """A secret saved as whitespace is not set, in the words and in the exit:
    the gate's "set the secret" answer, not "the key is weak"."""
    if command == "unseal":
        assert _seal(run, sealed_env) == chain.EXIT_OK
        _offer(monkeypatch, [sealed_env])
    capsys.readouterr()
    monkeypatch.setenv(chain.KEY_ENV, "   ")
    out = tmp_path / "x" / "round.enc"
    argv = (["seal", "--processed-dir", str(run), "--out", str(out)] if command == "seal"
            else ["unseal", "--dest", str(tmp_path / "d"), "--github-repo", "o/r"])
    assert chain.main(argv) == chain.EXIT_NO_TOKEN
    assert f"{chain.KEY_ENV} is not set" in capsys.readouterr().out
    assert not out.exists()


def test_a_tip_that_cannot_be_compared_seals_everything(sealed_env, bare, run, tmp_path, monkeypatch, capsys) -> None:
    """The comparison that trims a seal to the tip's gap is an economy, never
    a gate: when it fails locally, the whole round is sealed and the run says
    so, rather than the seal failing and the round being on no copy."""
    import tarfile
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))

    def unreadable(git_dir, path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(chain, "blob_of", unreadable)
    capsys.readouterr()
    out = tmp_path / "seal" / "round.enc"
    assert chain.main(["seal", "--processed-dir", str(run), "--out", str(out),
                       "--remote", f"file://{bare}"]) == chain.EXIT_OK
    assert "sealing everything" in capsys.readouterr().out
    opened = tmp_path / "opened.tar"
    assert chain._openssl(["-d"], out, opened).returncode == 0
    with tarfile.open(opened) as tar:
        assert sorted(tar.getnames()) == sorted(
            p.relative_to(run).as_posix() for p in run.rglob("*.csv"))


def _independent_decrypt(sealed: Path, *kdf: str) -> subprocess.CompletedProcess:
    """openssl with the parameters written out here, not read from the
    script, so a weaker setting in the script cannot pass by matching itself."""
    return subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", *kdf, "-pass", f"env:{chain.KEY_ENV}",
                           "-in", str(sealed), "-out", os.devnull], capture_output=True)


def test_the_seal_uses_pbkdf2_at_200k_iterations_with_sha256(sealed_env, run) -> None:
    assert _seal(run, sealed_env) == chain.EXIT_OK
    assert _independent_decrypt(sealed_env, "-pbkdf2", "-iter", "200000", "-md", "sha256").returncode == 0
    assert _independent_decrypt(sealed_env, "-md", "md5").returncode != 0, "legacy single-pass key derivation"
    assert _independent_decrypt(sealed_env, "-pbkdf2", "-iter", "1", "-md", "sha256").returncode != 0


def test_a_download_that_fails_once_is_asked_again(tmp_path, monkeypatch) -> None:
    import io
    import zipfile as zf
    payload = io.BytesIO()
    with zf.ZipFile(payload, "w") as archive:
        archive.writestr(chain.SEALED_FILE, b"SEALED")
    calls = []

    class Done:
        def __init__(self, code):
            self.returncode, self.stderr = code, b"HTTP 502"

    def gh(command, stdout=None, stderr=None, **k):
        calls.append(command)
        if len(calls) == 1:
            stdout.write(b"half a zi")
            return Done(1)
        stdout.write(payload.getvalue())
        return Done(0)

    waited = []
    monkeypatch.setattr(chain.subprocess, "run", gh)
    monkeypatch.setattr(chain, "sleep", waited.append)
    target = tmp_path / "round.enc"
    chain.download_sealed("o/r", {"id": 9}, target)
    assert target.read_bytes() == b"SEALED"
    assert len(calls) == 2 and waited == [5]


@pytest.mark.parametrize("bad", [
    "staging/2026-10-08.csv", "line_movement/notes.txt", "README.md",
    "line_movement/2026-10-08.csv.bak", "unmerged/line_movement/2026-10-08/not-a-sha.csv",
])
def test_an_archive_member_outside_the_allowlist_is_refused_inside_the_destination(
    sealed_env, tmp_path, monkeypatch, bad
) -> None:
    """Each bad member stays inside the destination, where tarfile's own
    filter lets it through: only the store/day-file allowlist refuses it."""
    import tarfile
    src = tmp_path / "src"
    _write(src, "line_movement/2026-10-08.csv", HEADER + _row(1))
    _write(src, bad, "x\n")
    bundle = tmp_path / "round.tar"
    with tarfile.open(bundle, "w") as tar:
        tar.add(src / "line_movement/2026-10-08.csv", arcname="line_movement/2026-10-08.csv")
        tar.add(src / bad, arcname=bad)
    sealed_env.parent.mkdir(parents=True, exist_ok=True)
    assert chain._openssl(["-e", "-salt"], bundle, sealed_env).returncode == 0
    _offer(monkeypatch, [sealed_env])
    dest = tmp_path / "dest"
    assert chain.main(["unseal", "--dest", str(dest), "--github-repo", "o/r"]) == chain.EXIT_DAMAGED
    assert not dest.exists() or not any(p.is_file() for p in dest.rglob("*"))


def test_line_movement_holds_the_grant_its_unseal_needs() -> None:
    """unseal lists and downloads sealed rounds with github.token; every
    replay's fake gh accepts any token, so this grant is what production
    relies on."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    assert workflow["permissions"].get("actions") == "read"
    restore = _steps()[_index("Restore today's captures")]
    assert restore["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_no_level_of_the_workflow_redirects_the_sealed_rounds_branch() -> None:
    """NHL_DEFAULT_BRANCH set anywhere in line-movement.yml would make every
    main round skip main's sealed rounds; the replays render step env only."""
    assert "NHL_DEFAULT_BRANCH" not in WORKFLOW.read_text()


# --- the pre-merge review's findings (2026-10-06) ------------------------------


def test_a_clean_check_warns_of_nothing(bare, run, tmp_path, capsys, monkeypatch) -> None:
    assert _run("push", bare, run) == chain.EXIT_OK
    capsys.readouterr()
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert _run("verify", bare, run) == chain.EXIT_OK
    assert "::warning::" not in capsys.readouterr().out
    assert "await a hand merge" not in summary.read_text()


def test_a_ragged_file_the_tip_lost_is_short_not_passed(bare, run, capsys) -> None:
    """A day file the tip does not hold, and whose own parse disagrees with
    its line count, cannot be counted row by row: it is short, not passed.
    The push exits 0 (a new file goes up whole); the branch is then set back,
    as a rewrite between push and check would, so the tip lacks it."""
    assert _run("push", bare, run) == chain.EXIT_OK
    before = _tip(bare)
    ragged = "line_movement/2026-10-09.csv"
    _write(run, ragged, HEADER + _row(1).replace("P1", '"P1') + _row(2))
    assert _run("push", bare, run) == chain.EXIT_OK
    _git(["--git-dir", str(bare), "update-ref", "refs/heads/movement", before])
    capsys.readouterr()
    assert _run("verify", bare, run) == chain.EXIT_DAMAGED
    assert f"{ragged}: differs from the private tip and could not be read on disk" in capsys.readouterr().out


def test_a_parked_sidecar_the_tip_lacks_fails_the_check(bare, run, tmp_path, monkeypatch, capsys) -> None:
    """unseal parks a sealed copy it could not merge; the check counts it
    like any day file, so a tip that lacks it is short and the round is
    sealed again rather than the parked rows living only in an artifact
    that expires."""
    assert _run("push", bare, run) == chain.EXIT_OK
    side = f"unmerged/line_movement/2026-10-08/{'ab' * 20}.csv"
    _write(run, side, HEADER + _row(5))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    capsys.readouterr()
    assert _run("verify", bare, run) == chain.EXIT_DAMAGED
    assert f"{side}: 1 row(s) missing from the private tip" in capsys.readouterr().out
    assert "FAILED" in summary.read_text()


@pytest.mark.parametrize(("stall_at", "cut"), [(1, "git ls-remote gave no answer"),
                                               (2, "git fetch gave no answer")])
def test_a_stalled_github_cannot_hold_the_seal_past_its_step(
    sealed_env, bare, run, tmp_path, monkeypatch, capsys, stall_at, cut
) -> None:
    """The listing that trims a seal is one attempt under a deadline on each
    git call: a remote that answers the listing and then stalls the pack (2),
    or never answers at all (1), costs seconds, and the whole round is still
    sealed. Unbounded, git would wait past the step's 2 minutes and the round
    would be on no copy, in exactly the case the seal is for."""
    import tarfile
    import time
    assert _run("push", bare, run) == chain.EXIT_OK  # a real tip, so the fetch is reached
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(3))
    count = tmp_path / "connections"
    proxy = tmp_path / "proxy.sh"
    proxy.write_text(
        "#!/bin/sh\n"
        f'n=$(( $(cat "{count}" 2>/dev/null || echo 0) + 1 )); echo "$n" > "{count}"\n'
        f'if [ "$n" -ge {stall_at} ]; then sleep 60; fi\n'
        f'exec git upload-pack "{bare}"\n')
    proxy.chmod(0o755)
    stalled = tmp_path / "stalled.git"
    for key, value in {"GIT_CONFIG_COUNT": "3",
                       "GIT_CONFIG_KEY_0": f"url.ext::{proxy}.insteadOf", "GIT_CONFIG_VALUE_0": f"file://{stalled}",
                       "GIT_CONFIG_KEY_1": "protocol.ext.allow", "GIT_CONFIG_VALUE_1": "always",
                       "GIT_CONFIG_KEY_2": "protocol.version", "GIT_CONFIG_VALUE_2": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(chain, "TIP_LISTING_SECONDS", 2)
    waited = []
    monkeypatch.setattr(chain, "sleep", waited.append)
    capsys.readouterr()
    started = time.monotonic()
    assert chain.main(["seal", "--processed-dir", str(run), "--out", str(sealed_env),
                       "--remote", f"file://{stalled}"]) == chain.EXIT_OK
    assert time.monotonic() - started < 15
    assert waited == [], "the listing is one attempt, never retried"
    out = capsys.readouterr().out
    assert "could not be listed" in out and cut in out, out
    assert count.read_text().strip() == str(stall_at), "the stall was not where this case puts it"
    opened = tmp_path / "opened.tar"
    assert chain._openssl(["-d"], sealed_env, opened).returncode == 0
    with tarfile.open(opened) as tar:
        assert sorted(tar.getnames()) == sorted(p.relative_to(run).as_posix() for p in run.rglob("*.csv"))


def test_the_tip_listing_deadline_fits_inside_the_steps_that_list() -> None:
    """The stall test sets its own short deadline, so the real one is pinned
    here: two timed git calls (ls-remote, then the fetch) plus room to tar,
    compress and encrypt must fit inside the seal step, and inside the
    restore step that unseals with the same listing."""
    per_call = chain.TIP_LISTING_SECONDS
    assert isinstance(per_call, (int, float)) and 0 < per_call
    for name, room in (("Seal this round when the private chain did not take it", 45),
                       ("Restore today's captures", 120)):
        limit = 60 * int(_steps()[_index(name)]["timeout-minutes"])
        assert 2 * per_call + room <= limit, (name, per_call, limit)


def test_a_sidecar_merged_by_hand_stays_home_while_its_seal_lives(sealed_env, bare, run, tmp_path, monkeypatch, capsys) -> None:
    """unseal parks a sealed copy that cannot merge; the push keeps it as a
    sidecar; someone merges it by hand and moves it to merged/. The seal
    still lives for up to 7 days, and every restore downloads it again: the
    merged mark is what tells it the copy is home, so it is not parked again
    and the next round is not red."""
    assert _run("push", bare, run) == chain.EXIT_OK
    _write(run, LM, HEADER + _row(1) + _row(2) + _row(7))
    assert _seal(run, sealed_env) == chain.EXIT_OK
    _offer(monkeypatch, [sealed_env])
    later = tmp_path / "later"
    _write(later, LM, "a,different,header\n1,2,3\n")
    unseal = ["unseal", "--dest", str(later), "--github-repo", "o/r", "--remote", f"file://{bare}"]
    assert chain.main(unseal) == chain.EXIT_DAMAGED
    (parked,) = list((later / chain.UNMERGED).rglob("*.csv"))
    side = parked.relative_to(later).as_posix()
    assert _run("push", bare, later) == chain.EXIT_DAMAGED  # the disk copy is a sidecar too
    # The hand merge, as CLAUDE.md says: fold the rows into the day file,
    # then move the sidecar to merged/.
    clone = tmp_path / "hand"
    _git(["clone", "-q", "-b", "movement", str(bare), str(clone)])
    (clone / LM).write_text(HEADER + _row(1) + _row(2) + _row(7))
    waiting = sorted(p.relative_to(clone).as_posix() for p in (clone / chain.UNMERGED).rglob("*.csv"))
    assert side in waiting and len(waiting) == 2  # the parked copy, and the disk copy the push kept
    for each in waiting:
        (clone / chain.merged_path(each)).parent.mkdir(parents=True, exist_ok=True)  # git mv needs the folder
        _git(["mv", each, chain.merged_path(each)], cwd=clone)
    _git(["add", "-A"], cwd=clone)
    _git(["commit", "-qm", "merge by hand"], cwd=clone)
    _git(["push", "-q", "origin", "HEAD:movement"], cwd=clone)

    # The folder that parked it still holds the parked copy: the next push
    # from it must not put the merged sidecar back.
    assert _run("push", bare, later) == chain.EXIT_OK
    assert not _git(["--git-dir", str(bare), "ls-tree", "-r", "--name-only", "movement", "--", "unmerged"]).split()

    fresh = tmp_path / "fresh"
    assert _run("pull", bare, fresh) == chain.EXIT_OK
    assert not (fresh / chain.MERGED).exists(), "a merged mark is not a day file"
    capsys.readouterr()
    assert chain.main(["unseal", "--dest", str(fresh), "--github-repo", "o/r",
                       "--remote", f"file://{bare}"]) == chain.EXIT_OK
    assert not (fresh / chain.UNMERGED).exists(), "the merged copy was parked again"
    assert _run("verify", bare, fresh) == chain.EXIT_OK
    assert "await a hand merge" not in capsys.readouterr().out
