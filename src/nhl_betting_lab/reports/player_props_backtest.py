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

from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY, PROP_MARKETS
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
    priced_outcomes: int = 0
    outcomes_without_a_model_opinion: int = 0
    outcomes_below_threshold: int = 0
    unmatched_players: list[str] = field(default_factory=list)
    retention_note: str = ""
    unmeasurable_markets: dict[str, str] = field(default_factory=dict)
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
    )
    report.notes = _standing_notes()

    if prices.empty or samples.empty:
        return report

    model_by_key: dict[tuple[str, str, str, float], tuple[float, float]] = {}
    for row in samples.itertuples():
        key = (
            str(row.date)[:10],
            str(row.market),
            str(row.player).strip().casefold(),
            float(row.line),
        )
        model_by_key[key] = (float(row.model_probability), float(row.actual))

    # Actuals keyed without the line, so an Over on a line the calibration
    # sweep did not price can still be settled from the same player-game.
    actual_by_player: dict[tuple[str, str, str], float] = {}
    for row in samples.itertuples():
        actual_by_player[
            (str(row.date)[:10], str(row.market), str(row.player).strip().casefold())
        ] = float(row.actual)

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
        date_text = str(getattr(row, "date", ""))[:10]
        key = (date_text, market, player.casefold(), line)

        model = model_by_key.get(key)
        if model is None:
            actual = actual_by_player.get((date_text, market, player.casefold()))
            if actual is None:
                unmatched.add(player)
                report.outcomes_without_a_model_opinion += 1
                continue
            # The model priced this player-game but not this exact line. It is
            # not scored: re-pricing the line here would use a model fitted
            # for a different sweep, and quietly mixing the two would make the
            # measurement unreproducible.
            report.outcomes_without_a_model_opinion += 1
            continue
        model_probability, actual = model

        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            continue

        # The model prices the Over. The Under's model probability is its
        # complement; the price's is its own, which is why the two sides can
        # both look like edges on a vigged market and neither is.
        side_probability = (
            model_probability
            if selection in {"over", "yes"}
            else 1.0 - model_probability
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
        report.overall = roi_interval(
            [bet.profit for bet in report.bets],
            wins=sum(1 for bet in report.bets if bet.won),
            pushes=sum(1 for bet in report.bets if bet.push),
        )
        for market in sorted({bet.market for bet in report.bets}):
            subset = [bet for bet in report.bets if bet.market == market]
            report.by_market[market] = roi_interval(
                [bet.profit for bet in subset],
                wins=sum(1 for bet in subset if bet.won),
                pushes=sum(1 for bet in subset if bet.push),
            )
    return report


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
    report: BacktestReport, *, output_dir: Path | None = None
) -> dict[str, str]:
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
        "by_market": {
            market: _interval_payload(interval)
            for market, interval in report.by_market.items()
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
    return {
        "markdown": str(markdown),
        "json": str(json_path),
        "csv": str(csv_path),
    }


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
        "verdict": interval.verdict(),
    }
