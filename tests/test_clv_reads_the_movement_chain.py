"""The closing-line value report reads Line Movement's chain from the private repository.

Gameday Refresh never has Line Movement's captures on its runner, so from
2026-09-25 the "Report closing-line value" step restored the public
`line-movement` artifact into data/processed for the report (which
`load_captures` falls back to) and removed it afterwards; from 2026-10-01 it
scored that chain beside the private closing-line store.

Since stage two of the chain's move (2026-10-05) there is no public copy. The
chain's only home is branch `movement` of cooperross399/nhl-closing-lines, and
the step pulls it with `private_movement_chain.py pull --dest
"$RUNNER_TEMP/private-movement-chain"`: outside the workspace, so
gameday-state (which uploads data/processed whole) cannot carry it, and
removed when the report is done. These pin:

- the report is pointed at the folder the pull wrote, the pull gets the
  step's own token, and nothing reads a public copy (no `restore_state.py`,
  no `gh`);
- the chain is scored beside a store that was read, never instead of it;
- chain folders an older gameday-state left in data/processed are removed
  first, so they are neither scored nor uploaded again;
- the report's own exit is the step's, and the clean-up runs either way;
- a pull that exits 0 and wrote no day file is an ordinary night: the chain
  holds nothing for the report yet;
- a chain GitHub could not be reached for (exit 1) degrades the run, and says
  what was actually scored;
- a chain that is damaged (2), has no token to read with (3), has no
  `movement` branch (4), turns the token away (5) or exits with a code the
  step does not know fails the step (exit 2, `store_fault`) without degrading
  the run (the backup would read the same chain), a damaged chain's good days
  are still scored, and a chain fault beside a store that was read is still a
  fault. A missing branch is not "nothing yet": the chain has existed since
  2026-10-02, so a missing branch was deleted or renamed, and a quiet night
  would let the season drop off the tip unreported.

The no-token case stubs the chain alone to exit 3 (the real pull answers 3
only when the secret is missing, which also stops the store) so that the
chain's own `3)` arm is under test; the real pull with no token is replayed in
`test_clv_never_scores_a_restored_capture_store.py`. The public restore's
`--union 3` (a run's artifact could be partial) has no counterpart to replay:
the private branch accumulates every push, which
`test_the_movement_chain_is_kept_privately.py` covers. The store's own paths
are in `test_closing_prices_never_reach_the_public_repo.py`.

These run the workflow's own step block under `bash -eo pipefail`, with the
step's own `env:` (the secret rendered as a test value), a stub `python`, and
`git` and `gh` stubs that reach no network and log any call, as
`test_a_failed_settlement_fails_the_run.py` does.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import _bash, _outputs, _render

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
STEP = "Report closing-line value"
DAY_FILE = "2026-09-29.csv"
STALE_DAY_FILE = "2026-09-01.csv"
CHAIN_FOLDERS = ("line_movement", "deployment", "line_combinations")


def _step() -> dict:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["refresh"]["steps"]
    (step,) = [s for s in steps if s.get("name") == STEP]
    return step


def _block() -> str:
    return _render(_step()["run"], {})


def _step_env() -> dict[str, str]:
    """The step's own `env:`, with the secret as a test value. Any other
    expression is refused, so a token added back (`github.token`) is seen."""
    return {key: _render(str(value), {"secrets.NHL_CLOSING_LINES_TOKEN": "test-token"})
            for key, value in (_step().get("env") or {}).items()}


def _executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _stubs(tmp_path: Path, *, chain_exit: int, chain_writes: bool,
           store_exit: int, clv_exit: int) -> dict:
    """`chain_writes`: the pull leaves a day file (and a deployment file) in
    its --dest before exiting `chain_exit`. The store pull writes a store
    only when it exits 0. Every call is logged under `records/`."""
    bin_dir, records = tmp_path / "stubs", tmp_path / "records"
    bin_dir.mkdir()
    records.mkdir()
    chain_files = (
        'mkdir -p "$dest/line_movement" "$dest/deployment"; '
        f'echo x > "$dest/line_movement/{DAY_FILE}"; echo x > "$dest/deployment/{DAY_FILE}"; '
        if chain_writes else ""
    )
    store_file = 'echo x > "$out"; ' if store_exit == 0 else ""
    _executable(bin_dir / "python", (
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> "{records}/python.log"\n'
        'script=$1; shift\n'
        'case "$script" in\n'
        "  */private_closing_store.py)\n"
        '    [ "$1" = pull ] || exit 64\n'
        '    out=""; while [ $# -gt 0 ]; do [ "$1" = --out ] && out=$2; shift; done\n'
        f"    {store_file}exit {store_exit} ;;\n"
        "  */private_movement_chain.py)\n"
        '    [ "$1" = pull ] || exit 64\n'
        f'    echo "${{NHL_CLOSING_LINES_TOKEN:-<none>}}" > "{records}/chain_token.txt"\n'
        "    # What the real script answers when the token is not in its env.\n"
        '    [ -n "${NHL_CLOSING_LINES_TOKEN:-}" ] || exit 3\n'
        '    dest=""; while [ $# -gt 0 ]; do [ "$1" = --dest ] && dest=$2; shift; done\n'
        '    [ -n "$dest" ] || exit 64\n'
        f'    echo "$dest" > "{records}/chain_dest.txt"\n'
        f"    {chain_files}exit {chain_exit} ;;\n"
        "  */run_closing_line_value.py)\n"
        f'    printf "%s\\n" "$@" > "{records}/clv_args.txt"\n'
        f'    : > "{records}/clv_saw.txt"\n'
        "    # What load_captures reads from each folder it is given.\n"
        "    while [ $# -gt 0 ]; do\n"
        '      if [ "$1" = --captures-dir ]; then\n'
        f'        ls "$2/line_movement" 2>/dev/null >> "{records}/clv_saw.txt"\n'
        "      fi\n"
        "      shift\n"
        "    done\n"
        f"    exit {clv_exit} ;;\n"
        "esac\n"
        "exit 97\n"
    ))
    for tool in ("git", "gh"):
        _executable(bin_dir / tool, f'#!/bin/bash\necho "$*" >> "{records}/{tool}.log"\nexit 1\n')
    base = {k: v for k, v in os.environ.items()
            if k not in ("NHL_CLOSING_LINES_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")}
    (records / "github_output").write_text("", encoding="utf-8")
    return {**base, **_step_env(),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "RUNNER_TEMP": str(tmp_path / "runner_temp"),
            "GITHUB_OUTPUT": str(records / "github_output")}


def _run(tmp_path: Path, *, chain_exit: int = 0, chain_writes: bool = True,
         store_exit: int = 4, clv_exit: int = 0, stale: bool = False
         ) -> tuple[subprocess.CompletedProcess, Path]:
    """Store exit 4 by default: the private store holds nothing yet, so the
    chain is the only source."""
    work = tmp_path / "work"
    processed = work / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "kept.csv").write_text("keep\n", encoding="utf-8")
    if stale:
        for folder in CHAIN_FOLDERS:
            (processed / folder).mkdir()
            (processed / folder / STALE_DAY_FILE).write_text("old\n", encoding="utf-8")
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    env = _stubs(tmp_path, chain_exit=chain_exit, chain_writes=chain_writes,
                 store_exit=store_exit, clv_exit=clv_exit)
    return _bash(_block(), work, env), work


def _chain_dir(tmp_path: Path) -> Path:
    return tmp_path / "runner_temp" / "private-movement-chain"


def _read(tmp_path: Path, name: str) -> str:
    return (tmp_path / "records" / name).read_text(encoding="utf-8")


def test_the_report_reads_the_movement_captures(tmp_path: Path) -> None:
    result, work = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    # The pull gets the step's own token; without it the real pull answers 3,
    # which this step fails red as store_fault=no-token.
    assert _read(tmp_path, "chain_token.txt").strip() == "test-token"
    # Pointed at the folder the pull wrote, and nothing else: with no store
    # there is no second source.
    assert _read(tmp_path, "chain_dest.txt").strip() == str(_chain_dir(tmp_path))
    assert _read(tmp_path, "clv_args.txt").split() == ["--captures-dir", str(_chain_dir(tmp_path))]
    assert _read(tmp_path, "clv_saw.txt").split() == [DAY_FILE]
    assert "Read 1 line-movement day file(s) from the private chain." in result.stdout
    assert (work / "run_degraded.txt").read_text() == ""
    assert "store_fault" not in _outputs(tmp_path / "records" / "github_output")


def test_nothing_reads_a_public_copy(tmp_path: Path) -> None:
    result, _work = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    scripts = [line.split()[0] for line in _read(tmp_path, "python.log").splitlines()]
    assert scripts == ["scripts/private_closing_store.py", "scripts/private_movement_chain.py",
                       "scripts/run_closing_line_value.py"]
    assert not (tmp_path / "records" / "gh.log").exists()
    assert not (tmp_path / "records" / "git.log").exists()


def test_the_chain_is_scored_beside_a_store_not_instead_of_it(tmp_path: Path) -> None:
    result, _work = _run(tmp_path, store_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _read(tmp_path, "clv_args.txt").split() == [
        "--captures-dir", str(tmp_path / "runner_temp" / "private-closing-store"),
        "--captures-dir", str(_chain_dir(tmp_path)),
    ]
    assert _read(tmp_path, "clv_saw.txt").split() == [DAY_FILE]


def test_the_captures_do_not_ride_along_in_gameday_state(tmp_path: Path) -> None:
    result, work = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    # Pulled outside the workspace (a relative --dest is the workspace's),
    # and gone once the report is done.
    dest = (work / _read(tmp_path, "chain_dest.txt").strip()).resolve()
    assert not dest.is_relative_to(work.resolve())
    assert not _chain_dir(tmp_path).exists()
    # Everything else the runner had in data/processed is left alone.
    assert sorted(p.name for p in (work / "data" / "processed").iterdir()) == ["kept.csv"]
    assert (work / "data" / "processed" / "kept.csv").read_text() == "keep\n"


def test_chain_folders_from_an_older_state_are_removed_not_scored(tmp_path: Path) -> None:
    result, work = _run(tmp_path, stale=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _read(tmp_path, "clv_saw.txt").split() == [DAY_FILE]
    assert sorted(p.name for p in (work / "data" / "processed").iterdir()) == ["kept.csv"]


@pytest.mark.parametrize("code", [0, 2])
def test_the_reports_own_exit_is_the_steps_exit(tmp_path: Path, code: int) -> None:
    """Exit 2 (a damaged snapshot, store or movement day) is what "Report the
    outcome" reads; the clean-up must neither swallow it nor be skipped by it."""
    result, _work = _run(tmp_path, clv_exit=code)
    assert result.returncode == code, result.stdout + result.stderr
    assert not _chain_dir(tmp_path).exists()


def test_no_captures_yet_is_not_a_fault(tmp_path: Path) -> None:
    """A pull that exits 0 and wrote no day file: the chain exists and holds
    nothing for the report yet. Only a missing branch (exit 4) is a fault,
    in test_a_chain_that_could_not_be_used_fails_the_step."""
    result, work = _run(tmp_path, chain_exit=0, chain_writes=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Read 0 line-movement day file(s) from the private chain." in result.stdout
    assert "::error::" not in result.stdout
    # The report still runs, on the (empty) chain folder, and says so itself.
    assert _read(tmp_path, "clv_args.txt").split() == ["--captures-dir", str(_chain_dir(tmp_path))]
    assert _read(tmp_path, "clv_saw.txt").split() == []
    assert (work / "run_degraded.txt").read_text() == ""
    assert "store_fault" not in _outputs(tmp_path / "records" / "github_output")


@pytest.mark.parametrize(("store_exit", "unreached", "scored"), [
    (4, "the private movement chain", "no closing price"),
    (0, "the private movement chain", "the store alone"),
    (1, "the private closing-line store and the private movement chain", "no closing price"),
], ids=["chain-only", "store-read", "both-unreached"])
def test_a_chain_that_could_not_be_reached_is_recorded(
        tmp_path: Path, store_exit: int, unreached: str, scored: str) -> None:
    result, work = _run(tmp_path, chain_exit=1, chain_writes=False, store_exit=store_exit)
    assert result.returncode == 0, result.stdout + result.stderr  # the report runs on what it has
    assert (work / "run_degraded.txt").read_text() == (
        f"GitHub could not be reached for {unreached}, "
        f"so the closing-line value report scored {scored} today.\n"
    )
    assert (tmp_path / "records" / "clv_args.txt").exists()
    assert "store_fault" not in _outputs(tmp_path / "records" / "github_output")


DAMAGED_CHAIN = ("The private movement chain has damaged day file(s), named above; "
                 "its good days, if any, were still scored")
MISSING_CHAIN = ("The private repository has no movement branch; the chain has existed "
                 "since 2026-10-02, so it was deleted or renamed: restore it from its history")


@pytest.mark.parametrize(("chain_exit", "chain_writes", "tag", "fault", "scored"), [
    (2, True, "damaged-store", DAMAGED_CHAIN, "the movement chain alone"),
    (3, False, "no-token",
     "NHL_CLOSING_LINES_TOKEN is not set, so the private movement chain cannot be read; "
     "since stage two it is the only source of closing prices",
     "no closing price"),
    (4, False, "missing-chain", MISSING_CHAIN, "no closing price"),
    (5, False, "rejected-token",
     "The private movement chain turned NHL_CLOSING_LINES_TOKEN away (expired, revoked, "
     "or not granted cooperross399/nhl-closing-lines); replace the secret",
     "no closing price"),
    (7, False, "unexpected-exit-7",
     "The private movement chain read exited 7, which this step does not know",
     "no closing price"),
], ids=["damaged", "no-token", "missing-chain", "rejected-token", "unknown-exit"])
def test_a_chain_that_could_not_be_used_fails_the_step(
        tmp_path: Path, chain_exit: int, chain_writes: bool, tag: str, fault: str,
        scored: str) -> None:
    """Red (exit 2, which "Report the outcome" reads) even though the report
    itself exited 0, and not degraded: the backup would read the same chain.
    The store holds nothing (exit 4, not a fault), so the whole ::error:: line
    is the chain's own arm."""
    result, work = _run(tmp_path, chain_exit=chain_exit, chain_writes=chain_writes)
    assert result.returncode == 2, result.stdout + result.stderr
    (error,) = [line for line in result.stdout.splitlines() if line.startswith("::error::")]
    assert error == f"::error::{fault}; the closing-line value report scored {scored}."
    assert _outputs(tmp_path / "records" / "github_output")["store_fault"] == tag
    # The report still ran, on whatever the chain left.
    assert _read(tmp_path, "clv_saw.txt").split() == ([DAY_FILE] if chain_writes else [])
    assert (work / "run_degraded.txt").read_text() == ""
    assert not _chain_dir(tmp_path).exists()
    # A missing branch used to be "nothing yet"; it is never said quietly now.
    assert "No private movement chain to read." not in result.stdout


@pytest.mark.parametrize(("chain_exit", "chain_writes", "tag", "fault", "scored"), [
    (4, False, "missing-chain", MISSING_CHAIN, "the store alone"),
    (2, True, "damaged-store", DAMAGED_CHAIN, "the store and the movement chain"),
], ids=["missing-chain", "damaged"])
def test_a_chain_fault_beside_a_store_that_was_read_still_fails(
        tmp_path: Path, chain_exit: int, chain_writes: bool, tag: str, fault: str,
        scored: str) -> None:
    """A store that was read does not cover for the chain: a missing branch
    beside a good store is still red, and the line says the store was all that
    was scored; a damaged chain's good days are scored beside the store."""
    result, work = _run(tmp_path, chain_exit=chain_exit, chain_writes=chain_writes,
                        store_exit=0)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Read the capture store from the private repository." in result.stdout
    (error,) = [line for line in result.stdout.splitlines() if line.startswith("::error::")]
    assert error == f"::error::{fault}; the closing-line value report scored {scored}."
    assert _outputs(tmp_path / "records" / "github_output")["store_fault"] == tag
    assert _read(tmp_path, "clv_args.txt").split() == [
        "--captures-dir", str(tmp_path / "runner_temp" / "private-closing-store"),
        "--captures-dir", str(_chain_dir(tmp_path)),
    ]
    assert _read(tmp_path, "clv_saw.txt").split() == ([DAY_FILE] if chain_writes else [])
    assert (work / "run_degraded.txt").read_text() == ""
    assert not _chain_dir(tmp_path).exists()
