"""The puck-drop guard.

Every selection is checked against the provider's `commence_time` before a
card is rendered. A selection is quarantined when either of these is true:

1. The game's start time is at or before the moment the card is generated.
2. The game's start time **cannot be confirmed** — missing, blank,
   unparseable, or carrying no timezone.

Its stake is removed with it.

## Why ambiguity falls on the not-a-play side

The two failure directions are not symmetric.

Letting a started game through produces a card recommending a bet nobody can
place, at a price that no longer exists, and whose result may already be
partly known. That is the failure that destroys trust in every other line.

Pulling a game that had not actually started costs one bet on a card listing
dozens, and the card says exactly why it was pulled, so the loss is visible
and recoverable in seconds.

So a missing or unparseable start time is treated as **started**. It is not
treated as "probably fine".

## What it deliberately does not do

It does not consult the NHL API's `gameState`. That would be a second source
of truth about whether a bet is placeable and the two could disagree. The
provider's `commence_time` is the one that matters, because the provider is
the one selling the price.

It applies no grace period. A game that started sixty seconds ago is started.

It compares in UTC, always. A naive datetime is a bug, not a fallback.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


#: The exact heading quarantined selections appear under. Contract text: the
#: card renderer, the issue comment, and the tests all use this one string.
QUARANTINE_SECTION = "Already started — no longer plays"

QUARANTINE_NOTE = (
    "These selections were removed because their game has already started, or "
    "because its start time could not be confirmed. Their stakes were removed "
    "with them. They are not passes, avoids, or no-value calls — they are bets "
    "that are no longer available."
)

PLAYABLE = "playable"
STARTED = "started"
UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True)
class PuckDropVerdict:
    """Whether one selection may still be played, and why."""

    state: str
    reason: str
    commence_time: str = ""

    @property
    def playable(self) -> bool:
        return self.state == PLAYABLE


def parse_commence_time(value: object) -> datetime | None:
    """Parse a provider commence time into an aware UTC datetime, or None.

    Accepts the ISO-8601 the provider emits, including the `Z` suffix that
    `datetime.fromisoformat` rejected before Python 3.11. A naive timestamp
    returns None rather than being assumed to be UTC: assuming would silently
    shift a start time by up to a day, in whichever direction, and the guard
    would then be confidently wrong.
    """
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else None
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def check_commence_time(
    value: object, *, now: datetime | None = None
) -> PuckDropVerdict:
    """The verdict for one start time."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError(
            "The puck-drop guard compares aware instants. A naive `now` is a "
            "bug, not a fallback."
        )
    moment = moment.astimezone(timezone.utc)

    raw = value.isoformat() if isinstance(value, datetime) else str(value or "").strip()
    start = parse_commence_time(value)
    if start is None:
        return PuckDropVerdict(
            state=UNCONFIRMED,
            reason=(
                "The start time could not be confirmed"
                + (f" from {raw!r}" if raw else " (it is missing)")
                + ". Ambiguity falls on the not-a-play side."
            ),
            commence_time=raw,
        )
    if start <= moment:
        minutes = (moment - start).total_seconds() / 60.0
        return PuckDropVerdict(
            state=STARTED,
            reason=(
                f"The game started {minutes:.0f} minute(s) ago "
                f"({start.isoformat(timespec='minutes')})."
            ),
            commence_time=start.isoformat(timespec="seconds"),
        )
    hours = (start - moment).total_seconds() / 3600.0
    return PuckDropVerdict(
        state=PLAYABLE,
        reason=f"Puck drop is in {hours:.1f} hour(s).",
        commence_time=start.isoformat(timespec="seconds"),
    )


@dataclass
class QuarantineResult:
    """Selections split into what still plays and what no longer does."""

    playable: list[dict[str, Any]]
    quarantined: list[dict[str, Any]]

    @property
    def stake_removed(self) -> float:
        """Total staked units taken off the card by the guard."""
        return sum(
            float(row.get("_removed_units", 0.0) or 0.0)
            for row in self.quarantined
        )

    def summary_line(self) -> str:
        if not self.quarantined:
            return "Puck-drop guard: every selection is still playable."
        return (
            f"Puck-drop guard: {len(self.quarantined)} selection(s) removed "
            f"({self.stake_removed:g} unit(s) of stake removed with them); "
            f"{len(self.playable)} still playable."
        )


#: Fields whose presence would let a quarantined row keep looking stakeable.
_STAKE_FIELDS = ("suggested_units", "stake_units", "units")


def apply_puck_drop_guard(
    selections: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    commence_field: str = "commence_time",
) -> QuarantineResult:
    """Split selections into playable and quarantined, stripping stakes.

    A quarantined row keeps every field that explains it and loses every field
    that would let it be staked. Zeroing the stake is not enough — a renderer
    that reads `suggested_units` and finds 0.0 shows a zero-unit bet, which
    still reads as a recommendation.
    """
    moment = now or datetime.now(timezone.utc)
    playable: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []

    for selection in selections:
        row = dict(selection)
        verdict = check_commence_time(row.get(commence_field), now=moment)
        row["puck_drop_state"] = verdict.state
        row["puck_drop_reason"] = verdict.reason
        if verdict.playable:
            playable.append(row)
            continue
        removed = 0.0
        for field in _STAKE_FIELDS:
            if field in row:
                try:
                    removed = max(removed, float(row[field] or 0.0))
                except (TypeError, ValueError):
                    removed = removed
                row.pop(field)
        row["_removed_units"] = removed
        row["section"] = QUARANTINE_SECTION
        quarantined.append(row)

    return QuarantineResult(playable=playable, quarantined=quarantined)


def render_quarantine_section(result: QuarantineResult) -> list[str]:
    """Markdown lines for the quarantine section, or nothing when it is empty."""
    if not result.quarantined:
        return []
    lines = [f"## {QUARANTINE_SECTION}", "", QUARANTINE_NOTE, ""]
    lines.extend(
        [
            "| Game | Market | Selection | Why |",
            "|:-----|:-------|:----------|:----|",
        ]
    )
    for row in result.quarantined:
        away = str(row.get("away_team", "")).strip()
        home = str(row.get("home_team", "")).strip()
        game = f"{away} @ {home}".strip(" @")
        lines.append(
            f"| {game or '-'} | `{row.get('market', '-')}` "
            f"| {row.get('selection', '-')} | {row.get('puck_drop_reason', '-')} |"
        )
    lines.append("")
    lines.append(
        f"Stake removed with these selections: **{result.stake_removed:g} unit(s)**."
    )
    lines.append("")
    return lines


def any_selection_is_stakeable(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Whether any row still carries a stake. Used as a post-render assertion."""
    return any(
        any(field in row for field in _STAKE_FIELDS) for row in rows
    )
