"""Of two listed unlaid runs that froze different snapshots for one day, the
older run's snapshot is the one that ends in place.

`restore_state._ask_again` lays the runs `processed/unlaid_runs.json` lists
newest first. Each lay puts back, over the state's copy, any snapshot the
laid run holds differently (`_first_opinions`), because runs are serialised
and an older run's copy of a day was frozen first. Laid newest first, the
last word goes to the oldest run, whose snapshot is the day's first opinion
and the one that must stand. Laid oldest first, the newer run's later
opinion would overwrite it, and the day would settle from the wrong one.
Nothing pinned the order: sorting the list oldest first passed every test,
since every existing case lists a single run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_a_red_runs_frozen_snapshot_is_laid_back import (
    REFRESH,
    SNAP,
    FakeGh,
    _run,
    _restore,
)

UNLAID = Path("processed") / "unlaid_runs.json"
DAY = SNAP / "2026-10-07.csv"


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setenv("RESTORE_STATE_RETRY_SECONDS", "0")


@pytest.mark.parametrize("listed_order", [[2, 3], [3, 2]])
@pytest.mark.parametrize("restored_holds_the_day", [True, False])
def test_the_oldest_listed_runs_first_frozen_snapshot_stands(
    tmp_path, monkeypatch, listed_order, restored_holds_the_day,
) -> None:
    # Run 2 froze the day first; run 3, whose restore missed it, froze its
    # own later; the restored green run 5 lists both as passed over.
    restored = {UNLAID.as_posix(): json.dumps({"runs": [
        {"run": run, "workflow": REFRESH, "tries": 1} for run in listed_order]})}
    if restored_holds_the_day:
        restored[DAY.as_posix()] = "run 5, latest\n"
    artifacts = {
        5: restored,
        3: {DAY.as_posix(): "run 3, second\n"},
        2: {DAY.as_posix(): "run 2, first\n"},
    }
    dest = tmp_path / "dest"
    gh = FakeGh([_run(5, "success")], artifacts)

    report = _restore(monkeypatch, dest, gh)

    assert sorted(gh.downloads) == [2, 3, 5]
    assert (dest / DAY).read_text(encoding="utf-8") == "run 2, first\n", (
        "a later opinion stands in place of the day's first frozen snapshot")
    assert report["unlaid"] == [] and not (dest / UNLAID).exists()
    assert report["unreached"] == []
