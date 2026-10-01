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
  read, and not a fault. The report falls back to Line Movement's captures;
* the store could not be reached, or is damaged: a fault, written to
  `run_degraded.txt` like every other fault the run records, and the report
  still falls back rather than score nothing;
* the store was read: the report scores exactly the store's rows.

These run the step's own `run:` block under `bash -eo pipefail`, with real git
and the real pull script against a local bare repository standing in for the
private store (the rig in `test_closing_prices_never_reach_the_public_repo.py`).
"""

from __future__ import annotations

import shutil

import pytest

from nhl_betting_lab.closing_lines import CAPTURES_FILENAME
from test_closing_prices_never_reach_the_public_repo import (  # noqa: F401
    _capture_row,
    _day_file,
    _seed_private,
    clv_rig,
    run_clv_step,
)

NOT_READ = "<no store>\n"


@pytest.fixture
def rig(clv_rig):  # noqa: F811
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


def _unreachable(rig) -> None:
    shutil.rmtree(rig["bare"])


def _damaged(rig) -> None:
    good = _day_file([_capture_row(book="Today")])
    _seed_private(rig["bare"], rig["root"], rig["env"],
                  {"captures/2026-10-08.csv": good + 'x,"unterminated\n'})


@pytest.mark.parametrize(
    "fault",
    [pytest.param(_unreachable, id="store-unreachable"),
     pytest.param(_damaged, id="store-damaged")],
)
def test_a_failed_read_is_a_degraded_run_that_scores_no_store(rig, fault) -> None:
    """The finding: a read that fails is not "no store yet". The report must
    not score the restored store, and the run says what went wrong."""
    fault(rig)

    done, read, degraded = run_clv_step(rig)

    assert done.returncode == 0, done.stderr
    assert read == NOT_READ, "the report scored a store this run did not fetch"
    assert "private closing-line store" in degraded
    assert len(degraded.splitlines()) == 1, degraded
    assert "No private capture store is configured" not in done.stdout
    assert not rig["stale"].exists()
