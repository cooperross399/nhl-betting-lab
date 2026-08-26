"""`data/outputs/player_props_backtest.md` — does the model beat a real price?

This is the report that decides. Calibration can rule a model out; only a
measurement against prices that were actually for sale can say anything about
whether disagreeing with the market pays.

## What a bet is here

For each historically-priced outcome the model holds an opinion on, compare
the model's probability to the price's implied probability. When the edge
clears the threshold, stake one flat unit. Settlement comes from the NHL
boxscore, never from the provider — so a provider outage can never change what
a bet did.

A player who did not dress produces no bet. That matches how books void a prop
on a player who never enters, and it keeps the absence out of the measurement
rather than scoring it as a loss.

## Three things the numbers cannot show, so they are printed

**The prices are one-sided.** Books quote the Over and the Yes; there is often
no quoted Under to devig against. Implied probability from a single quoted
side includes the vig, which overstates the true probability and therefore
**understates** every model edge here. The measurement is conservative in that
one direction.

**Not every market can be measured.** The provider retains some markets
historically and not others. A market that cannot be bought cannot be
measured, and this report names it as unmeasurable rather than substituting a
calibration number and letting it read like a backtest. The retention table is
measured by probe, not assumed.

**Sample size rules everything.** Separating a true +8% edge from zero takes
about six hundred bets. A report on two hundred is calibration-grade evidence
at best, and its verdict says so in the words this repository uses for it:
*no demonstrated edge*.

## The rule this report enforces

A change that improves calibration and loses here does not ship. Where a
price-based number exists, it is the one that decides.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.backtest.walk_forward import distribution_from
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY, PROP_MARKETS
from nhl_betting_lab.models.player_props import normalize_player_name
from nhl_betting_lab.season import game_date
from nhl_betting_lab.models.value import (
    OddsError,
    american_to_implied,
    profit_on_win,
)
from nhl_betting_lab.stats import (
    NO_DEMONSTRATED_EDGE,
    ROI_TABLE_HEADER,
    RoiInterval,
    detection_table,
    roi_interval,
)


BACKTEST_MARKDOWN_FILENAME = "player_props_backtest.md"
BACKTEST_JSON_FILENAME = "player_props_backtest.json"
BACKTEST_CSV_FILENAME = "player_props_backtest_bets.csv"


@dataclass
class PlacedBet:
    """One flat-stake bet the measurement would have made."""

    date: str
    market: str
    player: str
    line: float
    selection: str
    american_odds: float
    model_probability: float
    implied_probability: float
    edge: float
    actual: float
    won: bool
    push: bool
    profit: float
    book: str = ""


@dataclass
class BacktestReport:
    generated_at: str
    edge_threshold: float
    bets: list[PlacedBet] = field(default_factory=list)
    by_market: dict[str, RoiInterval] = field(default_factory=dict)
    overall: RoiInterval | None = None
    by_side: dict[str, RoiInterval] = field(default_factory=dict)
    looks: int = 1
    priced_outcomes: int = 0
    outcomes_without_a_model_opinion: int = 0
    outcomes_below_threshold: int = 0
    unmatched_players: list[str] = field(default_factory=list)
    retention_note: str = ""
    unmeasurable_markets: dict[str, str] = field(default_factory=dict)
    #: Which slice of history this measured. Empty means everything on disk.
    window_label: str = ""
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        if self.overall is None or not self.overall.bets:
            return (
                "No bets were placed, so nothing is measured. That is a "
                "statement about the evidence, not about the model."
            )
        return self.overall.verdict()


def settle(actual: float, line: float, selection: str) -> tuple[bool, bool]:
    """`(won, push)` for one prop outcome.

    A whole-number line pushes on an exact hit — a book refunds "over 2.0" on
    a 2. Rounding that to a half-point line would silently convert refunds
    into wins or losses, which is a systematic error, not a rounding one.
    """
    value = float(actual)
    threshold = float(line)
    side = str(selection).strip().lower()
    if value == threshold and float(threshold).is_integer():
        return False, True
    if side.startswith("o") or side in {"yes", "over"}:
        return value > threshold, False
    if side.startswith("u") or side in {"no", "under"}:
        return value < threshold, False
    raise ValueError(f"Unknown prop selection {selection!r}.")


def run_backtest(
    prices: pd.DataFrame,
    samples: pd.DataFrame,
    *,
    edge_threshold: float = MIN_PROP_EDGE,
    now: datetime | None = None,
    retention_note: str = "",
    unmeasurable_markets: Mapping[str, str] | None = None,
    window_label: str = "",
) -> BacktestReport:
    """Measure the props model against historically-bought prices.

    `prices` needs `date`, `market`, `player`, `selection`, `line`,
    `american_odds` and optionally `book`. `samples` is the walk-forward
    output: model probabilities for player-games the model could not see.
    """
    moment = now or datetime.now(timezone.utc)
    report = BacktestReport(
        generated_at=moment.isoformat(timespec="seconds"),
        edge_threshold=float(edge_threshold),
        retention_note=retention_note,
        unmeasurable_markets=dict(unmeasurable_markets or {}),
        window_label=window_label,
    )
    report.notes = _standing_notes()

    if prices.empty or samples.empty:
        return report

    # One entry per player-game-market, carrying the fitted distribution. Any
    # line the provider offers can be priced from it exactly, including
    # alternate ladders the calibration sweep never named.
    model_by_key: dict[tuple[str, str, str], tuple[Any, float]] = {}
    for row in samples.itertuples():
        key = (
            str(row.date)[:10],
            str(row.market),
            normalize_player_name(row.player),
        )
        model_by_key[key] = (
            distribution_from(row.mean, getattr(row, "dispersion_r", None)),
            float(row.actual),
        )

    unmatched: set[str] = set()
    for row in prices.itertuples():
        report.priced_outcomes += 1
        market = str(getattr(row, "market", "")).strip()
        player = str(getattr(row, "player", "")).strip()
        selection = str(getattr(row, "selection", "")).strip().lower()
        try:
            line = float(getattr(row, "line"))
        except (TypeError, ValueError):
            continue
        # The game date, not the UTC date of puck drop. An evening North
        # American game commences on the *next* UTC day, so joining on the raw
        # commence date silently discarded roughly seven prices in ten — and
        # the survivors were disproportionately matinees, which is a
        # systematically different set of fixtures.
        date_text = game_date(
            getattr(row, "commence_time", "") or getattr(row, "date", "")
        )
        key = (date_text, market, normalize_player_name(player))

        model = model_by_key.get(key)
        if model is None:
            unmatched.add(player)
            report.outcomes_without_a_model_opinion += 1
            continue
        distribution, actual = model
        over_probability = distribution.over_probability(line)

        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            continue

        # The model prices the Over. The Under's model probability is its
        # complement; the price's is its own, which is why the two sides can
        # both look like edges on a vigged market and neither is.
        side_probability = (
            over_probability
            if selection in {"over", "yes"}
            else 1.0 - over_probability
        )
        edge = side_probability - implied
        if edge < report.edge_threshold:
            report.outcomes_below_threshold += 1
            continue

        won, push = settle(actual, line, selection)
        profit = 0.0 if push else (profit_on_win(price) if won else -1.0)
        report.bets.append(
            PlacedBet(
                date=date_text,
                market=market,
                player=player,
                line=line,
                selection=selection,
                american_odds=price,
                model_probability=side_probability,
                implied_probability=implied,
                edge=edge,
                actual=actual,
                won=won,
                push=push,
                profit=profit,
                book=str(getattr(row, "book", "")),
            )
        )

    report.unmatched_players = sorted(unmatched)[:50]
    if report.bets:
        markets = sorted({bet.market for bet in report.bets})
        # Every market measured on the same data is one look in one family.
        # Reporting the market that cleared 95% without counting the rest is
        # not a finding, it is a search.
        looks = len(markets) + 1  # the markets, plus the overall figure
        report.looks = looks
        report.overall = roi_interval(
            [bet.profit for bet in report.bets],
            wins=sum(1 for bet in report.bets if bet.won),
            pushes=sum(1 for bet in report.bets if bet.push),
            looks=looks,
        )
        for market in markets:
            subset = [bet for bet in report.bets if bet.market == market]
            report.by_market[market] = roi_interval(
                [bet.profit for bet in subset],
                wins=sum(1 for bet in subset if bet.won),
                pushes=sum(1 for bet in subset if bet.push),
                looks=looks,
            )
        report.by_side = {
            side: roi_interval(
                [bet.profit for bet in report.bets if _side_of(bet) == side],
                wins=sum(
                    1 for bet in report.bets if _side_of(bet) == side and bet.won
                ),
            )
            for side in ("over", "under")
            if any(_side_of(bet) == side for bet in report.bets)
        }
    return report


def _side_of(bet: PlacedBet) -> str:
    """Which way a bet points, normalising `yes`/`no` onto over/under."""
    side = str(bet.selection).strip().lower()
    return "over" if side in {"over", "yes"} else "under"


def _standing_notes() -> list[str]:
    return [
        "Settlement comes from the NHL boxscore, never from the odds "
        "provider. A provider outage can change what was measured; it can "
        "never change what a bet did.",
        "Prop prices are one-sided at most books, so the implied probability "
        "used here includes the vig. That overstates the true probability and "
        "therefore **understates** every edge below — the measurement is "
        "conservative in that one direction.",
        "A player who did not dress produces no bet, matching how a book "
        "voids a prop on a player who never enters.",
        "A market the provider does not retain historically cannot be "
        "measured historically. Those markets are named below as "
        "unmeasurable. A calibration number is not offered in their place.",
        "This report decides. A change that improves calibration and loses "
        "here does not ship.",
    ]


def render_backtest(report: BacktestReport) -> str:
    lines = [
        "# Player props backtest",
        "",
        (
            "Does the model beat a price that was actually for sale? "
            "Calibration cannot answer that; this can, to the extent the "
            "sample allows."
        ),
        "",
        f"- Generated: {report.generated_at}",
        *(
            [f"- Window measured: **{report.window_label}**"]
            if report.window_label
            else []
        ),
        f"- Edge threshold: **{report.edge_threshold:.1%}**",
        f"- {report.summary_line()}",
        "",
    ]

    if report.overall is None or not report.overall.bets:
        lines.extend(
            [
                "## Not measured",
                "",
                (
                    "No historically-priced outcome cleared the edge "
                    "threshold with a model opinion behind it, so no bet was "
                    "placed and **nothing is measured**."
                ),
                "",
                (
                    f"- Priced outcomes seen: {report.priced_outcomes:,}"
                ),
                (
                    "- Without a model opinion: "
                    f"{report.outcomes_without_a_model_opinion:,}"
                ),
                (
                    "- Below the edge threshold: "
                    f"{report.outcomes_below_threshold:,}"
                ),
                "",
                (
                    "This is a statement about the evidence, not about the "
                    f"model. It means **{NO_DEMONSTRATED_EDGE}** — and equally, "
                    "no demonstrated absence of one."
                ),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Result",
                "",
                ROI_TABLE_HEADER,
                report.overall.as_row("**All props**"),
            ]
        )
        for market, interval in report.by_market.items():
            label = (
                MARKETS_BY_KEY[market].label if market in MARKETS_BY_KEY else market
            )
            lines.append(interval.as_row(f"`{market}` ({label})"))
        lines.extend(["", "### What each row means", ""])
        for market, interval in report.by_market.items():
            lines.append(f"- `{market}`: {interval.verdict()}")

        if report.looks > 1:
            lines.extend(
                [
                    "",
                    "### Why there are two intervals",
                    "",
                    (
                        f"{report.looks} figures were computed from one body "
                        "of data. Under the null, the chance that at least one "
                        f"of {report.looks} independent 95% tests clears is "
                        f"about {1 - 0.95 ** report.looks:.0%} — so reporting "
                        "the market that cleared, at its uncorrected interval, "
                        "would be reporting a search and calling it a finding."
                    ),
                    "",
                    (
                        "The corrected column is Bonferroni, which is crude "
                        "and conservative. That is the right trade here: a "
                        "sharper correction needs assumptions about how these "
                        "markets covary, and nothing in this repository has "
                        "measured that."
                    ),
                    "",
                ]
            )

        if report.by_side:
            lines.extend(
                [
                    "### Which way the bets point",
                    "",
                    (
                        "This is the most important structural fact in the "
                        "report, and it is not visible in the table above."
                    ),
                    "",
                    "| Side | Bets | Profit | ROI | 95% interval |",
                    "|:-----|-----:|-------:|----:|:-------------|",
                ]
            )
            for side, interval in report.by_side.items():
                lines.append(
                    f"| {side} | {interval.bets} | {interval.profit:+.1f}u "
                    f"| {interval.roi:+.1%} "
                    f"| {interval.low:+.1%} .. {interval.high:+.1%} |"
                )
            total = sum(item.bets for item in report.by_side.values())
            dominant = max(report.by_side.items(), key=lambda item: item[1].bets)
            share = dominant[1].bets / total if total else 0.0
            lines.extend(
                [
                    "",
                    (
                        f"**{share:.0%} of every bet is on the {dominant[0]}.** "
                        "That is one directional disagreement with the market, "
                        "not many independent ones: the model thinks these "
                        f"counts land {'above' if dominant[0] == 'over' else 'below'} "
                        "where the line sits, across the board. Per-market "
                        "results that point in opposite directions are "
                        "therefore harder to read as separate findings than "
                        "the table suggests, because they rest on the same "
                        "underlying bias."
                    ),
                    "",
                ]
            )
        lines.extend(
            [
                "",
                (
                    "Every number above is a point estimate from a finite "
                    "sample. An interval that includes zero means "
                    f"**{NO_DEMONSTRATED_EDGE}** — not 'promising', not "
                    "'trending positive'."
                ),
                "",
                "### How much data would settle it",
                "",
                detection_table(),
                "",
                (
                    "Order-of-magnitude guidance rather than a precise power "
                    "calculation. Its job is to make 'we cannot know this "
                    "yet' concrete."
                ),
                "",
                "## Where the bets came from",
                "",
                f"- Priced outcomes seen: {report.priced_outcomes:,}",
                (
                    "- Without a model opinion: "
                    f"{report.outcomes_without_a_model_opinion:,}"
                ),
                (
                    "- Below the edge threshold: "
                    f"{report.outcomes_below_threshold:,}"
                ),
                f"- Bets placed: {len(report.bets):,}",
                "",
            ]
        )
        if report.unmatched_players:
            lines.extend(
                [
                    (
                        "Players whose prices could not be matched to a model "
                        "opinion (first 50). A name here is a bet that was "
                        "not measured, not a bet that lost:"
                    ),
                    "",
                    *[f"- {name}" for name in report.unmatched_players],
                    "",
                ]
            )

    lines.extend(["## Which markets can be measured at all", ""])
    lines.append(
        report.retention_note
        or (
            "No retention probe has been run, so which prop markets the "
            "provider retains historically is **unknown**. It is not assumed "
            "to be all of them and it is not assumed to be none."
        )
    )
    lines.append("")
    if report.unmeasurable_markets:
        lines.extend(
            [
                "### Named as unmeasurable",
                "",
                *[
                    f"- `{market}`: {reason}"
                    for market, reason in sorted(report.unmeasurable_markets.items())
                ],
                "",
                (
                    "These markets have **no price-based evidence at all**. "
                    "Whatever their calibration says, it cannot substitute for "
                    "this, and no report in this repository will present it "
                    "as though it does."
                ),
                "",
            ]
        )
    else:
        priced = ", ".join(f"`{market.key}`" for market in PROP_MARKETS)
        lines.extend(
            [
                (
                    f"Markets this lab prices: {priced}. Until a retention "
                    "probe has run, none of them is established as measurable "
                    "or unmeasurable."
                ),
                "",
            ]
        )

    lines.extend(["## Standing notes", "", *[f"- {note}" for note in report.notes], ""])
    return "\n".join(lines)


def save_backtest(
    report: BacktestReport,
    *,
    output_dir: Path | None = None,
    label: str = "",
) -> dict[str, str]:
    """Write the report. A label writes a second, window-specific copy.

    The contract filename always gets the report as run, so a scheduled job
    that reads it never has to know about labels. A labelled copy sits beside
    it, which is what makes two windows comparable side by side.
    """
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / BACKTEST_MARKDOWN_FILENAME
    markdown.write_text(render_backtest(report), encoding="utf-8")

    payload: dict[str, Any] = {
        "generated_at": report.generated_at,
        "edge_threshold": report.edge_threshold,
        "priced_outcomes": report.priced_outcomes,
        "outcomes_without_a_model_opinion": report.outcomes_without_a_model_opinion,
        "outcomes_below_threshold": report.outcomes_below_threshold,
        "bets": len(report.bets),
        "unmeasurable_markets": report.unmeasurable_markets,
        "notes": report.notes,
        "overall": _interval_payload(report.overall),
        "looks": report.looks,
        "by_market": {
            market: _interval_payload(interval)
            for market, interval in report.by_market.items()
        },
        "by_side": {
            side: _interval_payload(interval)
            for side, interval in report.by_side.items()
        },
    }
    json_path = directory / BACKTEST_JSON_FILENAME
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    csv_path = directory / BACKTEST_CSV_FILENAME
    pd.DataFrame([bet.__dict__ for bet in report.bets]).to_csv(
        csv_path, index=False, lineterminator="\n"
    )
    written = {
        "markdown": str(markdown),
        "json": str(json_path),
        "csv": str(csv_path),
    }
    if label:
        safe = "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in label
        )
        labelled = directory / f"player_props_backtest_{safe}.md"
        labelled.write_text(render_backtest(report), encoding="utf-8")
        labelled_json = directory / f"player_props_backtest_{safe}.json"
        labelled_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        written["labelled_markdown"] = str(labelled)
        written["labelled_json"] = str(labelled_json)
    return written


def _interval_payload(interval: RoiInterval | None) -> dict[str, Any] | None:
    if interval is None:
        return None
    return {
        "bets": interval.bets,
        "profit": interval.profit,
        "roi": interval.roi,
        "low": interval.low,
        "high": interval.high,
        "includes_zero": interval.includes_zero,
        "looks": interval.looks,
        "adjusted_low": interval.adjusted_low,
        "adjusted_high": interval.adjusted_high,
        "survives_correction": interval.survives_correction,
        "verdict": interval.verdict(),
    }
