"""A game day whose line units were not captured turns the run red.

The Daily Faceoff capture is `continue-on-error`, deliberately: a line-source
failure must never cost the prices captured in the same run. But that made a
lost night indistinguishable from a captured one — the run stayed green — and
the source keeps no archive, so a night not captured is gone for good. The
brief and the digest could only say "a green run proves the prices, not the
line units". A final step now fails the run when the capture step failed, after
every upload, so the red X reports the loss without causing any.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "line-movement.yml"


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _gate() -> tuple[int, dict]:
    matches = [
        (index, step) for index, step in enumerate(_steps())
        if "steps.lines.outcome == 'failure'" in str(step.get("if", ""))
    ]
    assert len(matches) == 1, "exactly one step must fail the run on a missed line capture"
    return matches[0]


def test_the_line_capture_can_still_never_cost_the_prices() -> None:
    capture = [s for s in _steps() if s.get("name") == "Capture line combinations"]
    assert len(capture) == 1
    step = capture[0]
    assert step.get("id") == "lines", "the gate reads this step by its id"
    assert step.get("continue-on-error") is True
    assert str(step.get("if", "")).startswith("always()")


def test_the_gate_runs_after_every_upload_and_is_not_itself_forgiven() -> None:
    index, gate = _gate()
    uploads = [
        i for i, step in enumerate(_steps())
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert uploads, "the workflow uploads its captures"
    assert index > max(uploads), "a red run must never stop a capture from being kept"
    assert "always()" in str(gate.get("if", ""))
    assert gate.get("continue-on-error") in (None, False)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_gate_fails_and_says_why(tmp_path) -> None:
    _, gate = _gate()
    result = subprocess.run(
        ["bash", "-e", "-c", gate["run"]], cwd=tmp_path,
        env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "no archive" in result.stdout
