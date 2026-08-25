"""Per-bookmaker market and line coverage.

This report exists because of one specific mistake, and it is worth naming.

In the EPL lab, `total_2_5` was excluded on the finding that a complete 2.5
line existed at only three books. That finding was true — of the bulk `totals`
market, which was the only one anybody looked at. It was never true of
`alternate_totals`, where two books already quoted on the card carried 2.5 on
every fixture. A market was written off for a season because the coverage
check asked the wrong question.

So this report asks the right one: **for each project market, which books
quote it, on which lines, for how many games — counting the alternate ladders
as well as the bulk markets.**

Read-only. It produces a table, not a decision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from nhl_betting_lab.markets import ALL_MARKETS, MARKETS_BY_KEY


@dataclass(frozen=True)
class LineCoverage:
    """One market/line/book combination and how much of the slate it covers."""

    market: str
    line: float | None
    book: str
    games_priced: int
    games_in_slate: int

    @property
    def complete(self) -> bool:
        return self.games_in_slate > 0 and self.games_priced >= self.games_in_slate

    @property
    def share(self) -> float:
        return self.games_priced / self.games_in_slate if self.games_in_slate else 0.0


@dataclass
class MarketCoverage:
    """Everything known about one market's availability."""

    market: str
    games_in_slate: int
    rows: int = 0
    books: tuple[str, ...] = ()
    lines: tuple[float | None, ...] = ()
    complete_book_lines: list[LineCoverage] = field(default_factory=list)
    partial_book_lines: list[LineCoverage] = field(default_factory=list)

    @property
    def offered(self) -> bool:
        return self.rows > 0

    @property
    def has_a_complete_line(self) -> bool:
        return bool(self.complete_book_lines)

    def verdict(self) -> str:
        if not self.offered:
            return (
                "No book returned this market. Before recording it as not "
                "offered, re-run against the alternate ladders and a wider "
                "region — that is the exact check the EPL lab skipped."
            )
        if self.has_a_complete_line:
            best = self.complete_book_lines[0]
            return (
                f"Offered. {len(self.complete_book_lines)} book/line "
                f"combination(s) cover the whole slate; the first is "
                f"{best.book} at line {best.line}."
            )
        best = max(
            self.partial_book_lines, key=lambda item: item.games_priced, default=None
        )
        detail = (
            f" The widest is {best.book} at line {best.line}, "
            f"{best.games_priced} of {best.games_in_slate} games."
            if best
            else ""
        )
        return (
            "Offered, but no single book covers the whole slate on one line, "
            "so it is incomplete rather than unavailable." + detail
        )


@dataclass
class DiscoveryReport:
    slate_games: int
    markets: list[MarketCoverage] = field(default_factory=list)
    unmapped_provider_markets: tuple[str, ...] = ()

    def summary_line(self) -> str:
        offered = [item.market for item in self.markets if item.offered]
        complete = [item.market for item in self.markets if item.has_a_complete_line]
        return (
            f"{len(offered)} of {len(self.markets)} markets returned prices "
            f"across {self.slate_games} game(s); {len(complete)} have at least "
            "one book covering the whole slate on a single line."
        )


def _game_key(row: Mapping[str, Any]) -> str:
    return (
        f"{str(row.get('date', '')).strip()} "
        f"{str(row.get('away_team', '')).strip()}@"
        f"{str(row.get('home_team', '')).strip()}"
    ).strip()


def discover_coverage(
    prices: pd.DataFrame,
    *,
    markets: Sequence[str] | None = None,
    unmapped_provider_markets: Sequence[str] = (),
) -> DiscoveryReport:
    """Build the coverage table from a staged price frame."""
    keys = list(markets) if markets else [market.key for market in ALL_MARKETS]
    if prices.empty:
        return DiscoveryReport(
            slate_games=0,
            markets=[MarketCoverage(market=key, games_in_slate=0) for key in keys],
            unmapped_provider_markets=tuple(unmapped_provider_markets),
        )

    frame = prices.copy()
    frame["_game"] = frame.apply(_game_key, axis=1)
    slate = sorted(set(frame["_game"]))
    report = DiscoveryReport(
        slate_games=len(slate),
        unmapped_provider_markets=tuple(unmapped_provider_markets),
    )

    for key in keys:
        subset = frame[frame["market"].astype(str).str.strip() == key]
        coverage = MarketCoverage(market=key, games_in_slate=len(slate))
        if subset.empty:
            report.markets.append(coverage)
            continue
        coverage.rows = len(subset)
        coverage.books = tuple(sorted({str(item) for item in subset["book"]}))
        coverage.lines = tuple(
            sorted(
                {
                    None if pd.isna(value) else float(value)
                    for value in subset.get("line", pd.Series(dtype=float))
                },
                key=lambda value: (value is None, value),
            )
        )
        grouped = subset.groupby(
            [subset["book"].astype(str), subset["line"].astype("object")],
            dropna=False,
        )
        for (book, line), rows in grouped:
            entry = LineCoverage(
                market=key,
                line=None if pd.isna(line) else float(line),
                book=str(book),
                games_priced=len(set(rows["_game"])),
                games_in_slate=len(slate),
            )
            if entry.complete:
                coverage.complete_book_lines.append(entry)
            else:
                coverage.partial_book_lines.append(entry)
        coverage.complete_book_lines.sort(key=lambda item: (item.book, item.line or 0))
        coverage.partial_book_lines.sort(
            key=lambda item: (-item.games_priced, item.book)
        )
        report.markets.append(coverage)
    return report


def render_discovery(report: DiscoveryReport) -> str:
    lines = [
        "# Provider market discovery",
        "",
        (
            "Which books quote which markets, on which lines, for how much of "
            "the slate — **including the alternate ladders**. This report "
            "decides nothing. It is evidence for a human decision."
        ),
        "",
        f"- {report.summary_line()}",
        "",
        "## Coverage by market",
        "",
        "| Market | Rows | Books | Lines seen | Whole-slate book/line combos |",
        "|:-------|-----:|------:|:-----------|-----------------------------:|",
    ]
    for coverage in report.markets:
        label = MARKETS_BY_KEY[coverage.market].label if coverage.market in MARKETS_BY_KEY else coverage.market
        seen = ", ".join(
            "n/a" if line is None else f"{line:g}" for line in coverage.lines[:8]
        ) or "-"
        if len(coverage.lines) > 8:
            seen += f", +{len(coverage.lines) - 8} more"
        lines.append(
            f"| `{coverage.market}` ({label}) | {coverage.rows} "
            f"| {len(coverage.books)} | {seen} "
            f"| {len(coverage.complete_book_lines)} |"
        )
    lines.append("")
    lines.append("## Verdict per market")
    lines.append("")
    for coverage in report.markets:
        lines.append(f"- `{coverage.market}`: {coverage.verdict()}")
    lines.append("")

    if report.unmapped_provider_markets:
        lines.extend(
            [
                "## Provider markets this lab does not map",
                "",
                (
                    "Present in the response and ignored. Listed so a market "
                    "worth adding is visible rather than silently discarded."
                ),
                "",
                *[
                    f"- `{item}`"
                    for item in sorted(report.unmapped_provider_markets)
                ],
                "",
            ]
        )

    lines.extend(
        [
            "## Before writing a market off",
            "",
            (
                "A market with no rows here is **not** established as "
                "unavailable. The EPL lab excluded a market for a season on a "
                "coverage check that examined only the bulk endpoint while the "
                "complete line sat in the alternate ladder the whole time. "
                "Re-check the alternates and a wider region first, and record "
                "the reason either way."
            ),
            "",
        ]
    )
    return "\n".join(lines)
