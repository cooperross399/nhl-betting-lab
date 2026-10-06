"""The Publish Site chain ran a live NHL fetch, and its time-out killed bash alone.

#299 added "Rate the teams on expected goals and goaltending" to Publish
Site: `timeout 10m python scripts/run_shadow_stats.py --fetch --tables-only`.
The chain in test_a_failed_history_restore_never_truncates_the_site.py runs
every `run:` block for real, so every chain run asked api-web.nhle.com for
the play-by-play of every final game in the checkout's own
data/processed/team_games.csv. The script reads its package's data tree,
not the chain's. Replayed with two games planted there and the network
refused through a dead proxy, one chain run spent 37.5 s in the fetch's
retries; the operator's checkout lists 3,936 final games and caches no
play-by-play. On a runner, with no team_games.csv, the script stops at once,
which is why CI never saw it. On 2026-10-06 the full suite twice sat for over
half an hour in test_the_skipped_backup_is_passed_over_and_asked_once, in
the chain's `subprocess.run(..., timeout=120)`.

That time-out kills bash and nothing else. `timeout` moves itself and its
command into a process group of their own (measured on macOS's
/usr/bin/timeout; GNU's does the same without --foreground), so a block that
outlived it left the fetch running, orphaned, still holding the block's
pipes, for up to its ten minutes.

Now the chain runs that step's real block against a stub, refuses any block
that would reach the network before running a line of it, and runs each
block in a session of its own that a time-out kills whole.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

from test_a_failed_history_restore_never_truncates_the_site import (
    SCRIPTS,
    STUB,
    Outcome,
    _network_fetches,
)
from test_a_failed_state_listing_never_freezes_the_days_board import (
    D1,
    PublishSiteBesideTheLab,
)


RATINGS = Path("data") / "processed" / "shadow_team_ratings.json"

#: The fetch step's shape: bash runs a command that moves itself into a
#: process group of its own, as `timeout` does, and starts the process that
#: does the work. The `if !` keeps bash from exec'ing into it, as it does
#: in the real step.
OUTLIVES_ITS_TIME = '''set -u
echo $$ > bash.pid
if ! python -c "
import os, subprocess, sys
os.setpgid(0, 0)
worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])
open('pids', 'w').write(f'{os.getpid()} {worker.pid} {os.getpgid(0)} {os.getsid(0)}')
worker.wait()
"; then
  echo "never reached"
fi
'''


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PublishSiteBesideTheLab:
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    return PublishSiteBesideTheLab(tmp_path, monkeypatch)


def _alive(pid: int) -> bool:
    """Running, as opposed to gone or a zombie, which has exited."""
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=30).stdout.strip()
    return bool(state) and not state.startswith("Z")


def test_the_play_by_play_step_takes_its_own_failure_path_against_a_stub(
    chain: PublishSiteBesideTheLab,
) -> None:
    """Gameday Refresh's state carries data/processed, its xG ratings with it,
    and Publish Site's step rebuilds them or removes them. Against the stub
    its real block removes them, as a failed fetch does on a runner, and the
    board is rated on goals."""
    carrier = chain.gameday()
    restored = chain.tmp / f"gameday-state-{carrier}" / "processed" / RATINGS.name
    restored.write_text("{}\n", encoding="utf-8")

    run = chain.run(D1)

    assert run.conclusion == "success", run.log
    work = chain.tmp / f"run{run.run_id}"
    assert (work / "scripts" / "run_shadow_stats.py").read_text(encoding="utf-8") == STUB
    assert "The chain does not run this script: it reaches the network." in run.log
    assert not (work / RATINGS).exists(), "the restored ratings outlived a failed fetch"


@pytest.mark.parametrize("line", [
    # The step's own line, with the real script where the stub should be.
    "timeout 10m python scripts/run_shadow_stats.py --fetch --tables-only",
    # A script nobody has said is offline.
    "python scripts/fetch_nhl_data.py",
    # An offline script asked to fetch.
    "python scripts/restore_state.py --artifact gameday-state --live",
    "curl -fsS https://api-web.nhle.com/v1/schedule/now",
    "wget -q https://api-web.nhle.com/v1/schedule/now",
])
def test_a_line_that_would_reach_the_network_is_named(tmp_path: Path, line: str) -> None:
    (tmp_path / "scripts").mkdir()
    for name in ("run_shadow_stats.py", "restore_state.py"):
        shutil.copy(SCRIPTS / name, tmp_path / "scripts" / name)

    assert _network_fetches(f"set -u\n{line}\necho done\n", tmp_path) == [line]


def test_the_chain_refuses_such_a_block_before_running_any_of_it(
    chain: PublishSiteBesideTheLab, tmp_path: Path,
) -> None:
    block = "touch started\npython scripts/fetch_nhl_data.py\n"

    with pytest.raises(AssertionError, match="would reach the network"):
        chain._bash(block, tmp_path, {**os.environ, "PATH": chain.path},
                    Outcome(run_id=0, conclusion="", log=""))

    assert not (tmp_path / "started").exists()


def test_the_chain_refuses_a_block_that_would_find_the_real_gh(
    chain: PublishSiteBesideTheLab, tmp_path: Path,
) -> None:
    with pytest.raises(AssertionError, match="real GitHub"):
        chain._bash("touch started\n", tmp_path, dict(os.environ),
                    Outcome(run_id=0, conclusion="", log=""))

    assert not (tmp_path / "started").exists()


def test_a_block_that_outlives_its_time_is_killed_with_everything_it_started(
    chain: PublishSiteBesideTheLab, tmp_path: Path,
) -> None:
    """The test fails within seconds of the limit, and neither the process
    that left bash's group nor the one it started is still running."""
    chain.block_seconds = 3
    listed = tmp_path / "pids"
    started = time.monotonic()
    try:
        with pytest.raises(pytest.fail.Exception, match="still running after 3s"):
            chain._bash(OUTLIVES_ITS_TIME, tmp_path, {**os.environ, "PATH": chain.path},
                        Outcome(run_id=0, conclusion="", log=""))
        elapsed = time.monotonic() - started

        bash = int((tmp_path / "bash.pid").read_text())
        middle, worker, group, session = (int(v) for v in listed.read_text().split())
        # The shape the fix is for: out of bash's group, still in its session.
        assert group == middle != bash
        assert session == bash
        assert elapsed < 30, elapsed
        deadline = time.monotonic() + 10
        while (_alive(middle) or _alive(worker)) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not [pid for pid in (middle, worker) if _alive(pid)], "the block's processes outlived it"
    finally:
        # Whatever went wrong above, nothing of this test's is left asleep.
        if listed.exists():
            for pid in (int(v) for v in listed.read_text().split()[:2]):
                if _alive(pid):
                    os.kill(pid, signal.SIGKILL)
