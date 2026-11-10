"""The Monday layer scorecard: what each model layer did on settled picks.

Cooper, 2026-11-10 ("All"): re-score the layers every Monday and show him
the result. The Layer Scoring workflow runs `scripts/run_layer_scoring.py`
early every Monday and keeps `layer_scoring.md` / `.json` in its
`layer-scoring` artifact; Gameday Refresh restores the newest one into
`data/outputs`, the Monday card carries this section, and card-feed carries
the full report as `latest_layer_scoring.md`.

It reports and decides nothing. A "cut" here is the rule's verdict, fixed
before any result was read; taking a layer off the card stays Cooper's call.
Aggregate only: wagers, units, ROI and intervals, never a price, line or book.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPORT_JSON = "layer_scoring.json"
REPORT_MD = "layer_scoring.md"
SECTION_TITLE = "Layer scorecard"
#: A report older than this on a Monday is last week's run, or older: the
#: section says so rather than presenting it as this week's.
FRESH_DAYS = 8

#: What each layer is called on the card and in the report.
LAYER_LABELS = {
    "home_ice": "Each team's own home ice (#344)",
    "form": "Last-five team form, team markets (#345)",
    "rest": "Rest and travel (#346)",
    "lineup": "Posted lineup: player ratings, aging, skater defence (#346, #353, #354, #356)",
    "goalies": "Tonight's starting goalies, team markets (#351)",
    "referees": "Referee crews (#346, #348)",
    "posthockey": "PostHockey pre-game blend, 50/50 (#350)",
    "team_form_props": "Last-five team form, props (#345)",
    "position_matchup": "Matchup by position, props (#346)",
    "self_learning": "Self-learning, by side (#383, #427)",
}


def load_scorecard(output_dir: Path) -> dict[str, Any] | None:
    """The saved layer scoring, or None when there is none or it cannot be read."""
    path = Path(output_dir) / REPORT_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), dict):
        return None
    return payload


def _generated_day(payload: Mapping[str, Any]) -> date | None:
    stamp = str((payload.get("notes") or {}).get("generated_at") or "")
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.date()


def _units(value: Any) -> str:
    try:
        return f"{float(value):+.1f}u"
    except (TypeError, ValueError):
        return "-"


def _with(entry: Mapping[str, Any]) -> str:
    side = entry.get("with") or {}
    bets = int(side.get("bets") or 0)
    if not bets:
        return "0 bets"
    return (f"{float(side.get('units') or 0):+.1f}u over {bets:,}, "
            f"{float(side.get('roi') or 0):+.1%} [{float(side.get('low') or 0):+.1%}, "
            f"{float(side.get('high') or 0):+.1%}]")


def render_scorecard(payload: Mapping[str, Any] | None, day: str) -> list[str]:
    """Markdown lines for the Monday card. Always says something: a missing
    or stale report is named, never silently skipped."""
    lines = [f"## {SECTION_TITLE}", ""]
    if payload is None:
        return lines + [
            "_No layer scoring is on hand this run: the weekly Layer Scoring "
            "workflow has not produced a report this run could restore._", "",
        ]
    try:
        today = datetime.fromisoformat(day).date()
    except ValueError:
        today = None
    made = _generated_day(payload)
    notes = payload.get("notes") or {}
    if made is None or today is None or (today - made).days > FRESH_DAYS:
        when = made.isoformat() if made else "an unknown date"
        return lines + [
            f"_The newest layer scoring on hand is from {when}, more than "
            f"{FRESH_DAYS} days old, so it is not shown as this week's. The "
            "Layer Scoring workflow did not finish this week._", "",
        ]
    lines += [
        f"Each layer added since {notes.get('window_from', '2026-10-22')}, taken out alone and the "
        f"same settled picks repriced (through {notes.get('last_night') or 'the last settled night'}, "
        f"{int(notes.get('settled_wagers') or 0):,} settled wagers; run {made.isoformat()}). "
        "**Contribution** is units with the layer minus units without it, flat 1u, "
        "over the wagers either version bets.",
        "",
        "| Layer | Pop. B with it | Contribution (B) | Changed | Staked contribution | Rule says |",
        "|:--|:--|--:|--:|--:|:--|",
    ]
    for key, result in (payload.get("results") or {}).items():
        b = result.get("population_b") or {}
        staked = result.get("staked") or {}
        lines.append(
            f"| {LAYER_LABELS.get(key, key)} | {_with(b)} | {_units(b.get('contribution_units'))} "
            f"| {int(b.get('changed_wagers') or 0):,} | {_units(staked.get('contribution_units'))} "
            f"| {result.get('verdict', '-')} |"
        )
    lines += [
        "",
        "Intervals are clustered on the game; every one spanning zero is **no demonstrated "
        "edge** either way. \"Cut\" is the rule fixed before any result was read; it changes "
        "nothing on the card, and taking a layer off stays Cooper's call. The full report is "
        "`latest_layer_scoring.md` on card-feed.",
        "",
    ]
    return lines
