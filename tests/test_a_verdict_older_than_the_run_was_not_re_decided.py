"""A verdict file older than the run was never behaviour-tested as stale.

`scripts/check_verdict_drift.py --since <run start>` treats a verdict file
whose mtime predates the run as "not re-decided": its experiment did not
write it this run, so "unchanged" would report a stale belief as a confirmed
one, and the script exits 2 — the broken refresh Experiment Refresh fails
on. That branch is the one the first firing of the workflow needed (every
experiment failed, the old files stayed on disk, and the run said "nothing
moved").

Nothing exercised it. The behaviour tests in
`test_an_unreadable_verdict_is_a_broken_refresh.py` write every file fresh,
and the only guard was `test_season_readiness.py` grepping the source for
"not re-decided" — text the summary message also contains. Deleting the
mtime branch left the whole suite green while the script went back to
exiting 0 ("Nothing moved") on a refresh that re-decided nothing, or 1
(open a pull request) when the stale file happened to differ from the
committed record.

What these tests hold, calling the real `main()` with only the git read of
the committed record replaced:

* a readable verdict file older than `--since` is "not re-decided": exit 2,
  its row says so, no "moved", no clean bill — whether its contents agree
  with the committed record or not;
* a file written at or after the run start is compared as usual: exit 0
  when it held.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.verdicts import VERDICT_FILES


SCRIPT = PROJECT_ROOT / "scripts" / "check_verdict_drift.py"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_script_check_verdict_drift_stale", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(
    tmp_path: Path, monkeypatch, team_b2b: str, team_b2b_age: float
) -> tuple[int, str]:
    """Every policy committed as in force and re-decided unchanged this run,
    except that `team_b2b`'s file holds `team_b2b` and has an mtime
    `team_b2b_age` seconds before the run started (0: exactly at the start,
    negative: after it)."""
    module = _script()
    monkeypatch.setattr(
        module, "committed",
        lambda rel: {"ships": [p for p, f in VERDICT_FILES.items() if f == rel.name]},
    )
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    # A whole second, as the workflow's `date +%s` marker is.
    started = float(int(time.time()) - 60)
    for policy, filename in VERDICT_FILES.items():
        path = outputs / filename
        if policy == "team_b2b":
            path.write_text(team_b2b, encoding="utf-8")
            stamp = started - team_b2b_age
            os.utime(path, (stamp, stamp))
        else:
            path.write_text(f'{{"ships": ["{policy}"]}}', encoding="utf-8")
    code = module.main(["--output-dir", str(outputs), "--since", str(int(started))])
    return code, (outputs / "verdict_drift.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "body",
    ['{"ships": ["team_b2b"]}', '{"ships": []}'],
    ids=["agrees-with-committed", "differs-from-committed"],
)
@pytest.mark.parametrize(
    "age", [1.0, 3600.0, 86400.0 * 30], ids=["a-second", "an-hour", "a-month"]
)
def test_a_verdict_older_than_the_run_is_a_broken_refresh(
    tmp_path, monkeypatch, body, age
):
    code, report = _run(tmp_path, monkeypatch, body, age)

    assert code == 2, report
    assert (
        "| `team_b2b` | in force | **not re-decided** (file predates this run) | no |"
        in report
    )
    assert "were not re-decided: `team_b2b`" in report
    assert "**yes**" not in report
    assert "moved:" not in report and "Nothing moved" not in report


@pytest.mark.parametrize(
    "age", [0.0, -0.5, -30.0], ids=["in-the-start-second", "just-after", "later"]
)
def test_a_verdict_written_during_the_run_is_compared(tmp_path, monkeypatch, age):
    code, report = _run(tmp_path, monkeypatch, '{"ships": ["team_b2b"]}', age)

    assert code == 0, report
    assert "| `team_b2b` | in force | in force | no |" in report
    assert "not re-decided" not in report
    assert "Nothing moved" in report
