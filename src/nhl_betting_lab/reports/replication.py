"""Did a result found on one window hold on another?

This is the only question that separates a property of a strategy from a
property of a window, and no amount of extra precision on the first window can
answer it. A result measured more carefully on the data that produced it is
still that data.

So this report deliberately does **not** pool. Pooling two windows asks "what
is the edge across everything bought", which is a reasonable question and a
different one; it also launders a strong first window into a merged average
that looks like confirmation. The two windows are reported side by side and
the second one is treated as the test.

## What counts as replication

Three things, all required:

* the second window has enough bets to say anything at all;
* it points the **same direction** as the first;
* its interval excludes zero on its own, after correcting for the family of
  markets tested in that window.

The third is the strict one, and it is strict on purpose. A second window that
merely fails to contradict the first is not confirmation — most windows fail
to contradict most things.

## What a failure to replicate means

Not that the strategy is worthless. It means the first result is not yet
evidence of anything durable, and the honest description of a market in that
state is the same words this repository uses everywhere else: **no
demonstrated edge**.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, bets_needed_to_detect


REPLICATION_MARKDOWN_FILENAME = "replication.md"
REPLICATION_JSON_FILENAME = "replication.json"

#: Below this many bets in the test window, replication is untestable rather
#: than failed. Saying "did not replicate" from forty bets would be the same
#: over-reading in the other direction.
MINIMUM_TEST_BETS = 100

REPLICATED = "replicated"
CONTRADICTED = "contradicted"
NOT_CONFIRMED = "not confirmed"
UNTESTABLE = "untestable"


@dataclass(frozen=True)
class MarketReplication:
    market: str
    discovery_bets: int
    discovery_roi: float | None
    discovery_survived: bool
    test_bets: int
    test_roi: float | None
    test_survived: bool
    state: str
    reason: str

    @property
    def same_direction(self) -> bool:
        if self.discovery_roi is None or self.test_roi is None:
            return False
        return (self.discovery_roi > 0) == (self.test_roi > 0)


@dataclass
class ReplicationReport:
    generated_at: str
    discovery_label: str
    test_label: str
    markets: list[MarketReplication] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def replicated_markets(self) -> tuple[str, ...]:
        return tuple(
            item.market for item in self.markets if item.state == REPLICATED
        )

    def headline(self) -> str:
        discovered = [item for item in self.markets if item.discovery_survived]
        if not discovered:
            return (
                f"Nothing survived correction on **{self.discovery_label}**, "
                "so there is no result to replicate. That is not a failure of "
                "the test window."
            )
        if self.replicated_markets:
            names = ", ".join(f"`{m}`" for m in self.replicated_markets)
            return (
                f"{names} held on **{self.test_label}** as well as "
                f"**{self.discovery_label}**. Two windows agreeing is worth "
                "considerably more than one window measured precisely, and it "
                "is still two windows."
            )
        names = ", ".join(f"`{item.market}`" for item in discovered)
        return (
            f"{names} survived on **{self.discovery_label}** and did **not** "
            f"replicate on **{self.test_label}**. The first result is not yet "
            f"evidence of anything durable: {NO_DEMONSTRATED_EDGE}."
        )


def _interval(entry: Any) -> dict[str, Any]:
    return entry if isinstance(entry, Mapping) else {}


def compare(
    discovery: Mapping[str, Any],
    test: Mapping[str, Any],
    *,
    discovery_label: str,
    test_label: str,
    now: datetime | None = None,
) -> ReplicationReport:
    """Compare two backtest payloads market by market."""
    report = ReplicationReport(
        generated_at=(now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"
        ),
        discovery_label=discovery_label,
        test_label=test_label,
    )
    discovery_markets = discovery.get("by_market") or {}
    test_markets = test.get("by_market") or {}

    for market in sorted(set(discovery_markets) | set(test_markets)):
        first = _interval(discovery_markets.get(market))
        second = _interval(test_markets.get(market))
        discovery_bets = int(first.get("bets", 0) or 0)
        test_bets = int(second.get("bets", 0) or 0)
        discovery_roi = first.get("roi")
        test_roi = second.get("roi")
        discovery_survived = bool(first.get("survives_correction", False))
        test_survived = bool(second.get("survives_correction", False))

        entry = MarketReplication(
            market=market,
            discovery_bets=discovery_bets,
            discovery_roi=(
                float(discovery_roi)
                if isinstance(discovery_roi, (int, float))
                else None
            ),
            discovery_survived=discovery_survived,
            test_bets=test_bets,
            test_roi=float(test_roi) if isinstance(test_roi, (int, float)) else None,
            test_survived=test_survived,
            state=UNTESTABLE,
            reason="",
        )

        if not discovery_survived:
            entry = _with(
                entry,
                UNTESTABLE,
                "Nothing survived correction on the first window, so there is "
                "no result here to replicate.",
            )
        elif test_bets < MINIMUM_TEST_BETS:
            entry = _with(
                entry,
                UNTESTABLE,
                f"Only {test_bets} bet(s) in the test window, below the "
                f"{MINIMUM_TEST_BETS} needed to test anything. Calling this a "
                "failure would be the same over-reading in the other "
                "direction.",
            )
        elif not entry.same_direction:
            entry = _with(
                entry,
                CONTRADICTED,
                f"The test window points the other way "
                f"({entry.test_roi:+.1%} against {entry.discovery_roi:+.1%}). "
                f"{NO_DEMONSTRATED_EDGE.capitalize()}.",
            )
        elif not test_survived:
            entry = _with(
                entry,
                NOT_CONFIRMED,
                f"Same direction ({entry.test_roi:+.1%} over {test_bets} bets) "
                "but the interval does not exclude zero on its own. A window "
                "that merely fails to contradict is not confirmation — most "
                f"windows fail to contradict most things. "
                f"{NO_DEMONSTRATED_EDGE.capitalize()}.",
            )
        else:
            entry = _with(
                entry,
                REPLICATED,
                f"{entry.test_roi:+.1%} over {test_bets} bets, same direction, "
                "and the interval excludes zero on its own after correction.",
            )
        report.markets.append(entry)

    report.notes = [
        "The two windows are never pooled here. Pooling asks what the edge is "
        "across everything bought, which is a different question — and it "
        "launders a strong first window into a merged average that reads like "
        "confirmation.",
        "Replication requires the test window to exclude zero on its own, not "
        "merely to avoid contradicting the first. Most windows fail to "
        "contradict most things.",
        "A failure to replicate does not mean the strategy is worthless. It "
        "means the first result is not yet evidence of anything durable.",
        "Two windows agreeing is worth considerably more than one window "
        "measured precisely, and it is still two windows.",
    ]
    return report


def _with(entry: MarketReplication, state: str, reason: str) -> MarketReplication:
    return MarketReplication(
        market=entry.market,
        discovery_bets=entry.discovery_bets,
        discovery_roi=entry.discovery_roi,
        discovery_survived=entry.discovery_survived,
        test_bets=entry.test_bets,
        test_roi=entry.test_roi,
        test_survived=entry.test_survived,
        state=state,
        reason=reason,
    )


def _roi(value: float | None) -> str:
    return f"{value:+.1%}" if isinstance(value, float) else "-"


def render_replication(report: ReplicationReport) -> str:
    lines = [
        "# Replication",
        "",
        (
            "Did a result found on one window hold on another? No amount of "
            "extra precision on the first window can answer that — a result "
            "measured more carefully on the data that produced it is still "
            "that data."
        ),
        "",
        f"- Generated: {report.generated_at}",
        f"- Discovery window: **{report.discovery_label}**",
        f"- Test window: **{report.test_label}**",
        "",
        report.headline(),
        "",
        "| Market | Discovery | Test | Verdict |",
        "|:-------|:----------|:-----|:--------|",
    ]
    for item in report.markets:
        lines.append(
            f"| `{item.market}` "
            f"| {_roi(item.discovery_roi)} / {item.discovery_bets} bets"
            f"{' ✓' if item.discovery_survived else ''} "
            f"| {_roi(item.test_roi)} / {item.test_bets} bets"
            f"{' ✓' if item.test_survived else ''} "
            f"| **{item.state}** |"
        )
    lines.extend(
        [
            "",
            "✓ marks an interval that excludes zero after correcting for the "
            "markets tested in that window.",
            "",
            "## Market by market",
            "",
        ]
    )
    for item in report.markets:
        lines.append(f"- `{item.market}`: {item.reason}")
    lines.extend(
        [
            "",
            "## How much data would settle it",
            "",
            (
                f"Separating a +10% edge from zero takes about "
                f"{bets_needed_to_detect(0.10):,} bets; a +18% edge, about "
                f"{bets_needed_to_detect(0.18):,}. A window below "
                f"{MINIMUM_TEST_BETS} bets cannot test anything, which is why "
                "such markets are reported as untestable rather than failed."
            ),
            "",
            "## Standing notes",
            "",
            *[f"- {note}" for note in report.notes],
            "",
        ]
    )
    return "\n".join(lines)


def load_backtest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_replication(
    report: ReplicationReport, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / REPLICATION_MARKDOWN_FILENAME
    markdown.write_text(render_replication(report), encoding="utf-8")
    json_path = directory / REPLICATION_JSON_FILENAME
    json_path.write_text(
        json.dumps(
            {
                "generated_at": report.generated_at,
                "discovery_label": report.discovery_label,
                "test_label": report.test_label,
                "headline": report.headline(),
                "replicated_markets": list(report.replicated_markets),
                "markets": [item.__dict__ for item in report.markets],
                "notes": report.notes,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
