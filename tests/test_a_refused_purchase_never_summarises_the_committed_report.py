"""A purchase refused at the restore wrote the committed report into its summary.

Historical Props Purchase's "Restore the cached boxscores and samples" step
(`id: restore`) stops the job, under `--refuse-unreachable`, when GitHub
cannot be asked which run carries the bought prices. Every step after it
that is not `always()` is skipped, and both uploads are gated on
`steps.restore.outcome == 'success'`. Two steps were not:

* "Rebuild the backtest with whatever was bought" was `if: always()`. On a
  refused run it rebuilt the reports from whatever the checkout held, with
  none of the bought prices restored.
* "Write the result to the run summary" was `if: always()` and `cat`ted
  `data/outputs/player_props_backtest.md`. The checkout TRACKS that file, so
  on a refused run the job summary showed the last committed report under
  "## What can be measured", as though this run had measured it. The same
  happened after a restore that worked and a rebuild that failed
  (`continue-on-error`): the file was still the committed one, or the
  `--phase card` report the rebuild writes to the same name before `late`.

Now the rebuild runs only after a restore that succeeded (still `always()`,
so a buy that spent credits and then failed is still measured), the report
is summarised only after a rebuild that succeeded, and otherwise the summary
says in one line that no measurement was produced, and why.

These tests run the whole job as GitHub would, through the harness in
`test_an_unreachable_github_never_reads_as_no_bought_prices`: every step
from the workflow in order, each `if:` evaluated under GitHub's rules, the
restore step's real run block and `restore_state.py` against an offline `gh`
answering HTTP 502, and the summary steps' real run blocks writing to
`$GITHUB_STEP_SUMMARY`. The work directory holds the checkout's tracked
files, each reading "committed <path>". No measurement script and no buy is
ever run.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from test_an_unreachable_github_never_reads_as_no_bought_prices import (
    Outcome,
    Purchase,
    _holds,
    _job,
    _seeded,
)


BACKTEST_STEP = "Rebuild the backtest with whatever was bought"
COMMITTED_REPORT = "committed data/outputs/player_props_backtest.md"
REFUSED = "This run was refused before it measured anything"
NOT_REBUILT = "The backtest rebuild did not complete"


class _Recorded(Purchase):
    """The harness, recording which steps ran and failing the named ones."""

    def __init__(self, *args, failing: tuple[str, ...] = (), **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.ran: list[str] = []
        self.failing = set(failing)

    def _step(self, step: dict, *args) -> bool:
        self.ran.append(step["name"])
        if step["name"] in self.failing:
            return False
        return super()._step(step, *args)


def _chain(tmp_path: Path, *, failing: tuple[str, ...] = ()) -> _Recorded:
    seeded = _seeded(tmp_path, "github-default")
    chain = _Recorded(tmp_path / "recorded", "github-default", failing=failing)
    chain.registry = seeded.registry
    return chain


def _summary(chain: Purchase, run: Outcome) -> str:
    path = chain.tmp / f"runner-temp-{run.run_id}" / "summary.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.mark.parametrize("mode", ["buy", "buy_team", "probe"])
@pytest.mark.parametrize("fail", [
    {"list:*": 99},
    {"download:*": 99},
], ids=["listing-502", "download-502"])
def test_a_refused_run_says_so_and_never_shows_the_committed_report(
    tmp_path: Path, mode: str, fail: dict[str, int],
) -> None:
    chain = _chain(tmp_path)

    run = chain.run(mode, fail=fail)
    summary = _summary(chain, run)

    assert run.failed_at == "Restore the cached boxscores and samples", run.log
    assert COMMITTED_REPORT not in summary, (
        "a refused run summarised the checkout's committed report as its own "
        f"measurement:\n{summary}"
    )
    assert "## What can be measured" not in summary, summary
    assert REFUSED in summary, summary
    assert "no measurement was produced" in summary, summary
    assert BACKTEST_STEP not in chain.ran, (
        "the backtest was rebuilt after a restore that could not ask GitHub"
    )


def test_a_healthy_run_summarises_the_report_its_rebuild_wrote(tmp_path: Path) -> None:
    """The measurement scripts are never run here, so the file is the
    checkout's; what matters is that a restore and a rebuild that both
    succeeded lead to the report being shown, and nothing else."""
    chain = _chain(tmp_path)

    run = chain.run("buy")
    summary = _summary(chain, run)

    assert run.conclusion == "success", run.log
    assert BACKTEST_STEP in chain.ran
    assert summary.startswith("## What can be measured"), summary
    assert COMMITTED_REPORT in summary, summary
    assert REFUSED not in summary and NOT_REBUILT not in summary, summary


def test_a_buy_that_failed_after_spending_is_still_measured(tmp_path: Path) -> None:
    """The reason the rebuild is `always()`: credits already spent are
    measured even when the buy then fails."""
    chain = _chain(tmp_path, failing=("Buy a window",))

    run = chain.run("buy")
    summary = _summary(chain, run)

    assert run.failed_at == "Buy a window", run.log
    assert BACKTEST_STEP in chain.ran
    assert summary.startswith("## What can be measured"), summary
    assert sorted(run.artifacts) == ["gameday-state", "historical-props"]


def test_a_failed_rebuild_never_shows_the_report_it_left_behind(tmp_path: Path) -> None:
    """`continue-on-error`, so the job goes on; the file under the contract
    name is the committed one (or the card window's), not this run's."""
    chain = _chain(tmp_path, failing=(BACKTEST_STEP,))

    run = chain.run("buy")
    summary = _summary(chain, run)

    assert run.conclusion == "success", run.log
    assert COMMITTED_REPORT not in summary, summary
    assert NOT_REBUILT in summary and "no measurement was produced" in summary, summary
    assert REFUSED not in summary, summary


# --------------------------------------------------------------------------
# The gating, read off the YAML.
# --------------------------------------------------------------------------

def _steps() -> list[dict]:
    return _job()["steps"]


def _named(name: str) -> dict:
    found = [step for step in _steps() if step["name"] == name]
    assert len(found) == 1, name
    return found[0]


def _condition(step: dict) -> str:
    text = str(step.get("if", "")).strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    return " ".join(text.split())


def test_the_rebuild_is_gated_on_the_restore() -> None:
    step = _named(BACKTEST_STEP)

    assert _condition(step) == "always() && steps.restore.outcome == 'success'"
    assert step.get("id") == "backtest"


def test_every_summary_step_is_gated_and_exactly_one_can_run() -> None:
    """Whatever the restore and the rebuild came to, one summary step runs,
    and only the one after a successful rebuild reads the report."""
    writers = [step for step in _steps()
               if "GITHUB_STEP_SUMMARY" in str(step.get("run", ""))]
    readers = [step for step in writers
               if "player_props_backtest.md" in str(step["run"])]
    assert len(readers) == 1, [step["name"] for step in readers]
    for step in writers:
        assert "always()" in _condition(step), step["name"]

    outcomes = ("success", "failure", "skipped", "cancelled")
    for restore, backtest in itertools.product(outcomes, repeat=2):
        if restore != "success" and backtest != "skipped":
            continue  # the rebuild never runs after a restore that did not succeed
        steps = {"restore": {"outcome": restore}, "backtest": {"outcome": backtest}}
        running = [step["name"] for step in writers
                   if _holds(step["if"], inputs={}, steps=steps, failed=True)]
        assert len(running) == 1, (restore, backtest, running)
        reads = readers[0]["name"] in running
        assert reads == (restore == "success" and backtest == "success"), (
            restore, backtest, running)


def test_every_step_an_if_names_exists_earlier_in_the_job() -> None:
    """`steps.<id>` of an id that does not exist reads as '' and never
    'success', so a typo would silently skip a step or silently run one."""
    seen: set[str] = set()
    for step in _steps():
        for step_id in re.findall(r"steps\.([\w-]+)\.", str(step.get("if", ""))):
            assert step_id in seen, (step["name"], step_id)
        if step.get("id"):
            seen.add(step["id"])
