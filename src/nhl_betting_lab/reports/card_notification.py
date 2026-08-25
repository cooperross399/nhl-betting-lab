"""The issue comment that delivers the card, and the "Selections changed" marker.

Delivery is a comment on the pinned operating-home issue. GitHub emails
everyone watching it, so commenting *is* the whole mechanism: no SMTP server,
no credentials, no third party.

## The contract

Three strings here are hard-coded by Cooper's local scheduled tasks. Renaming
any of them silently breaks his automation, and the breakage looks exactly like
the lab going quiet — which is the one failure mode this design cannot
otherwise see.

* the issue title, `NHL Betting Lab — Claude Operating Home` (em dash);
* the marker `Selections changed`, which appears in the **first paragraph** of
  the comment when the selections differ from the previous card;
* the three measurement output paths, which the comment links to.

## When a comment is posted at all

Only when the selections changed, or the run was degraded.

Posting every run would put five emails a week in front of a reader and train
them to ignore all five. But silence is only safe to read as "nothing moved" if
anything going wrong breaks the silence — so a degraded run always posts, even
when the selections are identical.

A card that is *blocked* is a degraded run, not a quiet one. "No card, because
no market is allowlisted" is information, and the first time it appears it must
arrive.

## What "changed" means

The fingerprint compares selections — market, player, side, line — and not
prices. A card whose only difference is that a line moved a cent has not
changed its selections, and treating it as changed would send an email a day
until nobody read them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from nhl_betting_lab.reports.gameday_card import GamedayCard, render_card


#: Contract: matched literally by Cooper's local scheduled tasks.
OPERATING_HOME_TITLE = "NHL Betting Lab — Claude Operating Home"

#: Contract: appears in the first paragraph when selections differ.
SELECTIONS_CHANGED_MARKER = "Selections changed"

#: The three measurement outputs the contract names.
MEASUREMENT_PATHS = (
    "data/outputs/player_props_backtest.md",
    "data/outputs/props_calibration.md",
    "data/outputs/what_we_can_claim.md",
)

OPERATING_HOME_BODY = f"""This is the operating home for the NHL Betting Lab.

Every gameday card is posted here as a comment when the selections change, and
whenever a run is degraded. When the selections differ from the previous card,
the comment's first paragraph contains the phrase "{SELECTIONS_CHANGED_MARKER}".

**Recommendations only. No bet is ever placed by this repository.**

What the evidence actually supports:

{chr(10).join(f'- `{path}`' for path in MEASUREMENT_PATHS)}
"""


@dataclass(frozen=True)
class NotificationDecision:
    """Whether to post, and why."""

    post: bool
    reason: str
    selections_changed: bool
    degraded: bool

    def summary_line(self) -> str:
        return ("post" if self.post else "skip") + f": {self.reason}"


def decide(
    card: GamedayCard,
    *,
    previous_fingerprint: str | None,
    degraded_notes: Sequence[str] = (),
    force: bool = False,
) -> NotificationDecision:
    """Decide whether this card is worth an email."""
    degraded = bool(degraded_notes) or not card.card_generated
    current = card.selection_fingerprint()
    # A first run has no previous fingerprint. That is a change — there was
    # nothing and now there is something — and treating "no previous" as "no
    # change" would make the very first card the one that never arrives.
    changed = previous_fingerprint is None or current != previous_fingerprint

    if force:
        return NotificationDecision(
            post=True,
            reason="Forced by the caller.",
            selections_changed=changed,
            degraded=degraded,
        )
    if degraded:
        return NotificationDecision(
            post=True,
            reason=(
                "The run was degraded, and silence is only safe to read as "
                "'nothing moved' if anything going wrong breaks it."
            ),
            selections_changed=changed,
            degraded=True,
        )
    if changed:
        return NotificationDecision(
            post=True,
            reason="The selections differ from the previous card.",
            selections_changed=True,
            degraded=False,
        )
    return NotificationDecision(
        post=False,
        reason="Clean run and the selections did not change.",
        selections_changed=False,
        degraded=False,
    )


def render_comment(
    card: GamedayCard,
    decision: NotificationDecision,
    *,
    run_url: str = "",
    degraded_notes: Sequence[str] = (),
) -> str:
    """The comment body. The marker, when it applies, is in paragraph one."""
    opening: list[str] = []
    if decision.selections_changed:
        # Contract: this phrase, in this paragraph. Everything else in the
        # sentence is prose and may be reworded; the phrase may not.
        opening.append(
            f"**{SELECTIONS_CHANGED_MARKER}** since the previous card — "
            + (
                f"{len(card.best_bets)} best bet(s), "
                f"{card.total_units:g} unit(s) staked."
                if card.card_generated
                else "there is no card this run, and the previous run had one "
                "or this is the first run."
            )
        )
    else:
        opening.append(
            "Selections are unchanged since the previous card; this comment "
            "is here because the run was degraded."
        )

    lines = [opening[0], ""]
    if degraded_notes:
        lines.extend(
            [
                "### What went wrong",
                "",
                *[f"- {note}" for note in degraded_notes],
                "",
            ]
        )
    lines.append(render_card(card))
    lines.extend(
        [
            "",
            "---",
            "",
            "What the evidence actually supports:",
            "",
            *[f"- `{path}`" for path in MEASUREMENT_PATHS],
            "",
        ]
    )
    if run_url:
        lines.extend([f"Run: {run_url}", ""])
    lines.append(
        "Recommendations only. No bet was placed, no policy was edited, and "
        "no market was allowlisted by this run."
    )
    return "\n".join(lines)


def previous_fingerprint_from(payload: Any) -> str | None:
    """Read the previous card's fingerprint out of its saved JSON."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("selection_fingerprint")
    return str(value) if isinstance(value, str) else None
