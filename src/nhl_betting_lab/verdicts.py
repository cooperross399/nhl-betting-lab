"""Recorded experiment verdicts, read by the things that obey them.

Nothing in this repository ships a modelling policy by assertion. An
experiment measures the policy against real prices, records its verdict as a
`ships` list in a JSON file under `data/outputs/`, and the card and the
sample generators read that list rather than hard-coding the decision — so
the shipped configuration is auditable against the measurement that made it,
and reverting a policy is re-running its experiment rather than editing code.

A run given its own output directory reads a verdict from there when that
directory records one — a what-if experiment re-run into a scratch directory
governs the card and the measurements pointed at the same directory — and
otherwise the recorded verdict in `data/outputs/`. A verdict file that is
missing from both, or that is present and unreadable, ships nothing. The
conservative reading of "no recorded decision" is "no policy in force".
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
    # The team back-to-back adjustment. Verdict: ships (+5.8u in the `late`
    # window, must-not-lose; the +19.4u it once recorded mixed windows).
    "team_b2b": "rest_experiment.json",
    # The props back-to-back adjustment. Verdict: ships (+18.7u in the `card`
    # window, all of it shots_on_goal; must-not-lose).
    "props_b2b": "props_rest_experiment.json",
}


def source(policy: str, *, output_dir: Path | None = None) -> Path:
    """The file the verdict for `policy` is read from.

    `output_dir`'s own file when it holds one, else the recorded one under
    `data/outputs/`. This used to be `output_dir`'s file whether or not it
    existed, and a missing file ships nothing — but the verdicts are tracked
    files that live only in `data/outputs/`, so every run given a scratch
    --output-dir priced with every shipped policy off. Reproducing the
    2025-03-02 card that way moved all six home moneylines (Pittsburgh,
    at home the night after playing, 0.4141 -> 0.4370) and cut the card from
    3 best bets and 1.25 units to 2 and 0.5, while its log and its frozen
    snapshot said "props_b2b=off, team_b2b=off" against a repository that
    ships both. A file that exists is the directory's own decision, and
    stands even when unreadable, so a broken what-if verdict ships nothing
    rather than being papered over by the recorded one.
    """
    filename = VERDICT_FILES.get(str(policy))
    if filename is None:
        raise KeyError(
            f"No experiment records a verdict for {policy!r}. Known: "
            f"{sorted(VERDICT_FILES)}"
        )
    recorded = Path(OUTPUTS_DIR) / filename
    if not output_dir:
        return recorded
    own = Path(output_dir) / filename
    return own if own.exists() else recorded


def ships(policy: str, *, output_dir: Path | None = None) -> bool:
    """Whether the recorded verdict for `policy` says it is in force."""
    path = source(policy, output_dir=output_dir)
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
