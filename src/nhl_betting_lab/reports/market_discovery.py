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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from nhl_betting_lab.market_eligibility import (
    failed_requests,
    name_games,
    unanswered_games,
)
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
    #: Whether the fetch behind this report asked the provider for the
    #: market. True when the caller cannot say (an offline assessment of
    #: staged files), which keeps the old wording rather than inventing a
    #: claim in either direction.
    requested: bool = True
    #: The slate's games whose per-event request for this market failed
    #: (every failed game when there is no slate). Until 2026-09-26 the
    #: report could not see a failed request, and a run whose three
    #: per-event requests all answered HTTP 503 wrote a report
    #: byte-identical to one whose books posted nothing: nine markets "No
    #: book returned this market ... re-run against the alternate ladders
    #: and a wider region", in the one file the discovery job puts in its
    #: summary.
    unanswered_games: tuple[str, ...] = ()

    @property
    def offered(self) -> bool:
        return self.rows > 0

    @property
    def not_asked(self) -> bool:
        """No rows because nobody asked — never because nobody quotes it.

        A market with rows is judged on its rows whatever `requested` says.
        """
        return not self.requested and not self.offered

    @property
    def fetch_failed(self) -> bool:
        """No rows because the request failed for every game in the slate.

        Neither an absence at the books nor a market nobody asked for.
        """
        return (
            self.requested
            and not self.offered
            and bool(self.unanswered_games)
            and len(self.unanswered_games) >= self.games_in_slate
        )

    @property
    def has_a_complete_line(self) -> bool:
        return bool(self.complete_book_lines)

    def _unanswered_clause(self) -> str:
        if not self.unanswered_games:
            return ""
        return (
            f" The per-event request failed for {len(self.unanswered_games)} "
            f"of the {self.games_in_slate} game(s) "
            f"({name_games(self.unanswered_games)}), so those games are "
            "missing from this market because of the fetch, not the books."
        )

    def verdict(self) -> str:
        if self.not_asked:
            # Until 2026-09-25 this read "No book returned this market". The
            # scheduled discovery run asks for the three bulk markets only,
            # so nine of twelve markets — every prop, the regulation
            # three-way and the team total — were published as unquoted on
            # the one unattended run built to tell a starved probe from an
            # unquoted market.
            return (
                "Not asked in this run. The fetch behind this report never "
                "requested this market (the per-event markets are asked "
                "only when `run_provider_shadow.py` runs with `--props`), so "
                "the absence of rows says nothing about whether any book "
                "quotes it. Ask for it before reading it either way."
            )
        if self.fetch_failed:
            scope = (
                f"all {self.games_in_slate} game(s) in the slate"
                if self.games_in_slate
                else f"{len(self.unanswered_games)} game(s)"
            )
            return (
                "Asked, but the per-event request that asks for this market "
                f"failed for {scope}, so no rows came back. That is a failed "
                "fetch, not a market no book quotes: it says nothing either "
                "way. Retry the fetch before recording anything; the "
                "alternate ladders were asked in the same failed request, "
                "and a wider region would not answer it."
            )
        if not self.offered:
            if self.unanswered_games:
                return (
                    "No book returned this market. For "
                    f"{len(self.unanswered_games)} of the "
                    f"{self.games_in_slate} game(s) "
                    f"({name_games(self.unanswered_games)}) that is because "
                    "the per-event request failed, not because no book "
                    "quotes it — retry those first. Before recording it as "
                    "not offered, re-run against the alternate ladders and a "
                    "wider region — that is the exact check the EPL lab "
                    "skipped."
                )
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
            ) + self._unanswered_clause()
        best = max(
            self.partial_book_lines, key=lambda item: item.games_priced, default=None
        )
        detail = (
            f" The widest is {best.book} at line {best.line}, "
            f"{best.games_priced} of {best.games_in_slate} games."
            if best
            else ""
        )
        # Until 2026-09-26 a game lost to a failed request was counted
        # against the books here: one 503 of three read "DraftKings at line
        # 2.5, 2 of 3 games" and nothing else.
        return (
            "Offered, but no single book covers the whole slate on one line, "
            "so it is incomplete rather than unavailable."
            + detail
            + self._unanswered_clause()
        )


@dataclass
class DiscoveryReport:
    slate_games: int
    markets: list[MarketCoverage] = field(default_factory=list)
    unmapped_provider_markets: tuple[str, ...] = ()
    #: (game, error) for every per-event request that got no usable answer.
    failed_requests: tuple[tuple[str, str], ...] = ()

    def summary_line(self) -> str:
        offered = [item.market for item in self.markets if item.offered]
        complete = [item.market for item in self.markets if item.has_a_complete_line]
        not_asked = [item.market for item in self.markets if item.not_asked]
        if not not_asked:
            line = (
                f"{len(offered)} of {len(self.markets)} markets returned prices "
                f"across {self.slate_games} game(s); {len(complete)} have at "
                "least one book covering the whole slate on a single line."
            )
        else:
            # "3 of 12 markets returned prices" read as nine markets no book
            # quotes, when nine were never asked. The count is of markets
            # asked.
            asked = len(self.markets) - len(not_asked)
            line = (
                f"{len(offered)} of {asked} markets asked returned prices "
                f"across {self.slate_games} game(s); {len(complete)} have at "
                "least one book covering the whole slate on a single line. "
                f"{len(not_asked)} of {len(self.markets)} were not asked in "
                f"this run ({', '.join(not_asked)}), so their absence says "
                "nothing about whether any book quotes them."
            )
        if not self.failed_requests:
            return line
        # The same count read nine markets no book quotes when every
        # per-event request had failed.
        games = list(dict.fromkeys(game for game, _ in self.failed_requests))
        failed = [item.market for item in self.markets if item.fetch_failed]
        return (
            f"{line} The per-event request failed for {len(games)} game(s), "
            "so for those games the per-event markets and the alternate "
            "ladders are missing because of the fetch, not the books"
            + (
                f"; {len(failed)} market(s) have no rows at all for that "
                f"reason ({', '.join(failed)})"
                if failed
                else ""
            )
            + ". Retry the fetch before reading any of them."
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
    requested: Iterable[str] | None = None,
    failed_events: Iterable[Mapping[str, Any]] | None = None,
) -> DiscoveryReport:
    """Build the coverage table from a staged price frame.

    `requested` is the set of project markets the fetch actually asked the
    provider for. A market outside it with no rows reads "not asked in this
    run" rather than "no book returned this market". None means the caller
    cannot say, and every market is treated as asked, as before.

    `failed_events` is the fetch's record of per-event requests that got no
    usable answer (`FetchResult.failed_events`). A market with no rows
    because its request failed for every game reads as a failed fetch, one
    missing some games for that reason names them, and the report lists
    every failed request. None means no failure is known.
    """
    keys = list(markets) if markets else [market.key for market in ALL_MARKETS]
    asked = (
        None if requested is None else {str(item).strip() for item in requested}
    )
    failures = failed_requests(failed_events, prices)
    unanswered = unanswered_games(failures)
    listed = tuple((item.game, item.error) for item in failures)

    def _asked(key: str) -> bool:
        return asked is None or key in asked

    def _unanswered(key: str, slate: Sequence[str]) -> tuple[str, ...]:
        # The slate's games whose request for this market failed. With no
        # slate at all (no market has a row), every failed game counts.
        failed = unanswered.get(key, {})
        if not slate:
            return tuple(sorted(failed))
        return tuple(game for game in slate if game in failed)

    if prices.empty:
        return DiscoveryReport(
            slate_games=0,
            markets=[
                MarketCoverage(
                    market=key,
                    games_in_slate=0,
                    requested=_asked(key),
                    unanswered_games=_unanswered(key, ()),
                )
                for key in keys
            ],
            unmapped_provider_markets=tuple(unmapped_provider_markets),
            failed_requests=listed,
        )

    frame = prices.copy()
    frame["_game"] = frame.apply(_game_key, axis=1)
    slate = sorted(set(frame["_game"]))
    report = DiscoveryReport(
        slate_games=len(slate),
        unmapped_provider_markets=tuple(unmapped_provider_markets),
        failed_requests=listed,
    )

    for key in keys:
        subset = frame[frame["market"].astype(str).str.strip() == key]
        coverage = MarketCoverage(
            market=key,
            games_in_slate=len(slate),
            requested=_asked(key),
            unanswered_games=_unanswered(key, slate),
        )
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
    ]
    if report.failed_requests:
        # This is the file the Provider Market Discovery job puts in its run
        # summary, and until 2026-09-26 it never named a failed request:
        # the errors were only in the verification report.
        lines.extend(
            [
                "## Per-event requests that failed",
                "",
                (
                    "The provider refused or did not answer these games' "
                    "per-event requests, so for these games every per-event "
                    "market (the props, the regulation three-way, the team "
                    "total) and every alternate ladder is missing because of "
                    "the fetch, not because no book quotes it. Retry the "
                    "fetch before reading any of those markets either way; a "
                    "wider region would not answer it."
                ),
                "",
                *[f"- {game}: {error}" for game, error in report.failed_requests],
                "",
            ]
        )
    lines.extend(
        [
            "## Coverage by market",
            "",
            "| Market | Rows | Books | Lines seen | Whole-slate book/line combos |",
            "|:-------|-----:|------:|:-----------|-----------------------------:|",
        ]
    )
    for coverage in report.markets:
        label = MARKETS_BY_KEY[coverage.market].label if coverage.market in MARKETS_BY_KEY else coverage.market
        seen = ", ".join(
            "n/a" if line is None else f"{line:g}" for line in coverage.lines[:8]
        ) or "-"
        if len(coverage.lines) > 8:
            seen += f", +{len(coverage.lines) - 8} more"
        # A 0 in the Rows column reads as "asked, and nothing came back".
        if coverage.not_asked:
            rows = "not asked"
        elif coverage.fetch_failed:
            rows = "request failed"
        else:
            rows = str(coverage.rows)
        lines.append(
            f"| `{coverage.market}` ({label}) | {rows} "
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
