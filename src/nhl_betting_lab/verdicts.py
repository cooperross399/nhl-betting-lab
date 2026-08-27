"""Recorded experiment verdicts, read by the things that obey them.

Nothing in this repository ships a modelling policy by assertion. An
experiment measures the policy against real prices, records its verdict as a
`ships` list in a JSON file under `data/outputs/`, and the card and the
sample generators read that list rather than hard-coding the decision — so
the shipped configuration is auditable against the measurement that made it,
and reverting a policy is re-running its experiment rather than editing code.

A missing or unreadable verdict file ships nothing. The conservative reading
of "no recorded decision" is "no policy in force".
"""

from __future__ import annotations

import json
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR


#: Every verdict this repository records, and the file that records it.
VERDICT_FILES: dict[str, str] = {
    # The by-TOI calibration correction. Verdict: does not ship — indexed on
    # actual ice time it was hindsight, on expected ice time it loses.
    "by_toi": "correction_experiment.json",
    # The team back-to-back adjustment. Verdict: ships (+19.4u, must-not-lose).
    "team_b2b": "rest_experiment.json",
    # The props back-to-back adjustment. Verdict: ships (+11.4u, must-not-lose).
    "props_b2b": "props_rest_experiment.json",
}


def ships(policy: str, *, output_dir: Path | None = None) -> bool:
    """Whether the recorded verdict for `policy` says it is in force."""
    filename = VERDICT_FILES.get(str(policy))
    if filename is None:
        raise KeyError(
            f"No experiment records a verdict for {policy!r}. Known: "
            f"{sorted(VERDICT_FILES)}"
        )
    path = (Path(output_dir) if output_dir else Path(OUTPUTS_DIR)) / filename
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    listed = payload.get("ships")
    return isinstance(listed, list) and str(policy) in [
        str(item) for item in listed
    ]


def describe(*, output_dir: Path | None = None) -> str:
    """One line per policy, for run logs."""
    states = [
        f"{policy}={'in force' if ships(policy, output_dir=output_dir) else 'off'}"
        for policy in sorted(VERDICT_FILES)
    ]
    return ", ".join(states)
