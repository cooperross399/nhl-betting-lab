"""CLV scored yesterday's capture store when today's fetch failed.

Gameday Refresh restores the `gameday-state` artifact before it does anything
else, and that artifact uploads `data/processed` whole. So a capture store an
earlier run left at `data/processed/closing_line_captures.csv` is already on
disk when "Report closing-line value" starts. That step used to fetch the
`closing-lines` branch and, when the fetch did not succeed, print "No capture
store yet" and run the report anyway: a fetch that FAILED took the same path
as a branch that did not exist, and the report scored the restored store as
if it were today's. Confirmed on main d0cc593.

Since 2026-10-01 the store is the private repository
cooperross399/nhl-closing-lines, pulled into the runner's temp directory
(never into `data/processed`, which is uploaded publicly). The step still
removes any restored store before it reads, so the report reads only what
this run fetched, and it still tells the states apart:

* no NHL_CLOSING_LINES_TOKEN, or a store with no captures yet: nothing to
  read, and not a fault. The report scores the movement chain alone;
* the store could not be reached: a fault that may pass, written to
  `run_degraded.txt` like every other such fault, so the backup is sent for;
* the store is damaged, or GitHub turns the token away: a fault the backup
  would hit again, so the step fails red (exit 2) WITHOUT degrading the run,
  as a damaged snapshot does;
* the store was read: the report scores the store's rows (and the chain's).

These run the step's own `run:` block under `bash -eo pipefail`, with real git
and the real pull script against a local bare repository standing in for the
private store (the rig in `test_closing_prices_never_reach_the_public_repo.py`).
"""

from __future__ import annotations

import os
import shutil

import pytest

import test_closing_prices_never_reach_the_public_repo as guard
from nhl_betting_lab.closing_lines import CAPTURES_FILENAME
from test_closing_prices_never_reach_the_public_repo import (
    _capture_row,
    _day_file,
    _seed_private,
    run_clv_step,
)

#: The guard module's rig, made a fixture of this module too. Assigned rather
#: than imported by name, which pyflakes would read as an unused import.
clv_rig = guard.clv_rig

NOT_READ = "<no store>\n"


@pytest.fixture
def rig(clv_rig):
    """With an earlier run's store restored into data/processed."""
    stale = clv_rig["work"] / "data" / "processed" / CAPTURES_FILENAME
    stale.write_text(_day_file([_capture_row(book="Yesterday")]), encoding="utf-8")
    clv_rig["stale"] = stale
    return clv_rig


def test_no_token_is_a_clean_run_that_reads_no_store(rig) -> None:
    del rig["env"]["NHL_CLOSING_LINES_TOKEN"]

    done, read, degraded = run_clv_step(rig)

    assert done.returncode == 0, done.stderr
    assert read == NOT_READ
    assert degraded == ""
    assert "No private capture store is configured" in done.stdout
    assert not rig["stale"].exists()


def test_a_store_with_no_captures_yet_is_a_clean_run(rig) -> None:
    _seed_private(rig["bare"], rig["root"], rig["env"], {"captures/.gitkeep": ""})

    done, read, degraded = run_clv_step(rig)

    assert done.returncode == 0, done.stderr
    assert read == NOT_READ
    assert degraded == ""
    assert "holds nothing yet" in done.stdout


def test_the_store_is_read_in_place_of_the_restored_one(rig) -> None:
    _seed_private(rig["bare"], rig["root"], rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row(book="Today")])})

    done, read, degraded = run_clv_step(rig)

    assert done.returncode == 0, done.stderr
    assert "Today" in read and "Yesterday" not in read
    assert degraded == ""


def test_an_unreachable_store_degrades_the_run_and_scores_no_store(rig) -> None:
    """The finding: a read that fails is not "no store yet". The report must
    not score the restored store, and the run says what went wrong."""
    shutil.rmtree(rig["bare"])

    done, read, degraded = run_clv_step(rig)

    assert done.returncode == 0, done.stderr
    assert read == NOT_READ, "the report scored a store this run did not fetch"
    assert "private closing-line store could not be reached" in degraded
    assert len(degraded.splitlines()) == 1, degraded
    assert not rig["stale"].exists()


def _damaged(rig) -> None:
    good = _day_file([_capture_row(book="Today")])
    _seed_private(rig["bare"], rig["root"], rig["env"],
                  {"captures/2026-10-08.csv": good + 'x,"unterminated\n'})


def _token_turned_away(rig) -> None:
    """GitHub answers, and refuses the token."""
    _seed_private(rig["bare"], rig["root"], rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row(book="Today")])})
    real = shutil.which("git", path=os.environ["PATH"])
    wrapper = rig["root"] / "bin" / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'case "$1" in ls-remote|fetch) echo "remote: Repository not found." >&2;'
        ' echo "fatal: Authentication failed" >&2; exit 128;; esac\n'
        f'exec "{real}" "$@"\n'
    )
    wrapper.chmod(0o755)


@pytest.mark.parametrize(
    "fault",
    [pytest.param(_damaged, id="store-damaged"),
     pytest.param(_token_turned_away, id="token-turned-away")],
)
def test_a_fault_a_backup_would_repeat_fails_red_without_degrading(rig, fault) -> None:
    """A degraded run sends for the backup, which buys prices again and would
    meet the same damaged file or the same rejected token. So the step exits
    2, which "Report the outcome" fails the run on, and degrades nothing."""
    fault(rig)

    done, read, degraded = run_clv_step(rig)

    assert done.returncode == 2, done.stdout + done.stderr
    assert read == NOT_READ, "the report scored a store this run did not fetch"
    assert degraded == ""
    assert "::error::The private closing-line store" in done.stdout
    assert not rig["stale"].exists()
