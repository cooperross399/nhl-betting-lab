"""A card blocked for a reason that is not a fault is not posted as degraded.

The card records in `nothing_to_card` why a blocked card is NOT a fault.
There are two such reasons: the policy allowlists no market the card may pick
from (`NOTHING_ALLOWLISTED`), or no regular-season game is left to card today
(`NO_GAME_LEFT`). Gameday Refresh reads that field and leaves the run clean
for either of them (`tests/test_a_blocked_card_is_a_degraded_run.py`).
`card_notification.decide()` read only `card_generated`, so the same card went
out as `degraded=True`, with the comment "this comment is here because the
run was degraded", while the run published `degraded: false` and finished
green. The email and the run's health disagreed, in the direction of a false
alarm.

`decide()` now reads the same field the same way the workflow does: a blocked
card whose `nothing_to_card` is empty is a fault and stays degraded, and a
non-empty one is clean. A benign block still posts every run, as the module
docstring promises ("No card, because no market is allowlisted" is
information), and the comment's opening says why there is no card instead of
calling the run degraded.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nhl_betting_lab.reports import card_notification as note
from nhl_betting_lab.reports.gameday_card import (
    NO_GAME_LEFT,
    NOTHING_ALLOWLISTED,
    GamedayCard,
    save_card,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc).isoformat()
BLOCKER = (
    "No market is eligible for automated picks. Every market is listed under "
    "excluded markets with its reason. None of them is a pass, an avoid, or a "
    "no-value call."
)
BENIGN = pytest.mark.parametrize(
    "reason", [NOTHING_ALLOWLISTED, NO_GAME_LEFT], ids=["allowlist", "no-game"]
)


def _blocked(reason: str) -> GamedayCard:
    return GamedayCard(
        generated_at=NOW,
        card_generated=False,
        blockers=[BLOCKER],
        nothing_to_card=reason,
    )


def _first_paragraph(body: str) -> str:
    return body.split("\n\n", 1)[0]


@BENIGN
def test_a_benign_block_is_not_degraded_and_still_posts(reason: str) -> None:
    card = _blocked(reason)

    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint()
    )

    assert decision.post is True
    assert decision.degraded is False
    assert decision.selections_changed is False
    assert "degraded" not in decision.reason.lower()


@BENIGN
def test_a_benign_block_says_why_there_is_no_card(reason: str) -> None:
    card = _blocked(reason)
    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint()
    )

    body = note.render_comment(card, decision)
    opening = _first_paragraph(body)

    assert "because the run was degraded" not in body
    assert "on request" not in opening
    assert reason in opening
    assert note.SELECTIONS_CHANGED_MARKER not in opening


@BENIGN
def test_a_benign_block_that_is_a_change_carries_the_marker_and_the_reason(
    reason: str,
) -> None:
    card = _blocked(reason)
    decision = note.decide(card, previous_fingerprint="had selections before")
    assert decision.degraded is False

    opening = _first_paragraph(note.render_comment(card, decision))

    assert opening.startswith(f"**{note.SELECTIONS_CHANGED_MARKER}**")
    assert reason in opening


@BENIGN
def test_a_forced_benign_block_is_not_degraded(reason: str) -> None:
    card = _blocked(reason)
    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint(), force=True
    )

    body = note.render_comment(card, decision)

    assert decision.post is True
    assert decision.degraded is False
    assert "because the run was degraded" not in body
    assert reason in _first_paragraph(body)


def test_a_block_by_a_fault_stays_degraded() -> None:
    """A blocked card that does not say its block is benign is a fault, as the
    workflow reads it."""
    card = _blocked("")

    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint()
    )
    opening = _first_paragraph(note.render_comment(card, decision))

    assert decision.post is True
    assert decision.degraded is True
    assert "because the run was degraded" in opening


def test_a_forced_block_by_a_fault_stays_degraded() -> None:
    card = _blocked("")

    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint(), force=True
    )
    opening = _first_paragraph(note.render_comment(card, decision))

    assert decision.degraded is True
    assert "because the run was degraded" in opening


@BENIGN
@pytest.mark.parametrize("changed", [False, True], ids=["unchanged", "changed"])
def test_degraded_notes_still_degrade_a_benign_block(
    reason: str, changed: bool
) -> None:
    """The benign reason speaks for the block, never for the rest of the run,
    so a degraded run's comment never carries "does not degrade the run"."""
    card = _blocked(reason)
    notes = ["The price fetch failed."]

    decision = note.decide(
        card,
        previous_fingerprint="had selections before"
        if changed
        else card.selection_fingerprint(),
        degraded_notes=notes,
    )
    body = note.render_comment(card, decision, degraded_notes=notes)
    opening = _first_paragraph(body)

    assert decision.degraded is True
    assert reason not in body
    assert ("because the run was degraded" in opening) is not changed


@BENIGN
def test_the_post_script_posts_a_benign_block_as_clean(
    reason: str, tmp_path: Path
) -> None:
    """End to end through the script Gameday Refresh runs, with the empty
    `run_degraded.txt` the workflow leaves for a benign block."""
    card = _blocked(reason)
    paths = save_card(card, output_dir=tmp_path / "today")
    previous = save_card(card, output_dir=tmp_path / "yesterday")
    degraded_file = tmp_path / "run_degraded.txt"
    degraded_file.write_text("", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "post_card_to_issue.py"),
         "--card-json", paths["json"],
         "--previous-json", previous["json"],
         "--degraded-file", str(degraded_file),
         "--out", str(tmp_path / "comment.md"),
         "--title-out", str(tmp_path / "title.txt"),
         "--body-out", str(tmp_path / "body.md")],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True, text=True,
    )
    comment = (tmp_path / "comment.md").read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "post"
    assert "because the run was degraded" not in comment
    assert reason in _first_paragraph(comment)
    assert json.loads(Path(paths["json"]).read_text())["nothing_to_card"] == reason
