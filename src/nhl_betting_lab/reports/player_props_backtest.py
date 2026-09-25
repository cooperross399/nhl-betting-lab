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
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.backtest.walk_forward import distribution_from
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY, PROP_MARKETS
from nhl_betting_lab.models.player_props import player_key, player_name_aliases
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    build_team_name_map,
    resolve_team,
)
from nhl_betting_lab.stores import best_price_per_wager, label_phases
from nhl_betting_lab.season import clean_text, row_game_date
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

#: Window-labelled copies a summary may read for a market the contract report
#: has no bets in. The contract file holds whichever window ran last -- `late`
#: in both workflows -- and `hits` is quoted only by the two books in the
#: second region, which the `late` purchase never asked. Without this the
#: summaries reported hits as "no historical prices have been bought" while
#: this report printed its ROI over 5,021 wagers.
OTHER_WINDOW_JSON_FILENAMES: dict[str, str] = {
    "card": "player_props_backtest_card.json",
}


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
    #: Every price row handed in, and the two ways one leaves before it is a
    #: quote on a wager: priced in another window, or carrying no parseable
    #: snapshot or face-off time, so its window is unknown. The
    #: reconciliation starts here, not at `priced_outcomes`, because every
    #: row this measurement is known to have lost silently was lost before
    #: the loop that counts priced outcomes.
    rows_read: int = 0
    rows_other_window: int = 0
    rows_window_unknown: int = 0
    #: Book quotes seen, and the distinct wagers they collapse to. One
    #: selection quoted by eight books is one bet, not eight.
    quotes_seen: int = 0
    wagers: int = 0
    #: Which snapshot window was measured, and its median hours before
    #: face-off. A number without this is not comparable to another number.
    phase: str = ""
    phase_hours: float = 0.0
    priced_outcomes: int = 0
    outcomes_without_a_model_opinion: int = 0
    outcomes_below_threshold: int = 0
    #: Rows whose line, odds or selection could not be parsed. Zero on the
    #: shipped data, and counted anyway: an uncounted drop is invisible
    #: exactly when a provider format change makes it large, which is the
    #: shape of the UTC-join defect that once discarded seven prices in ten.
    outcomes_unparseable: int = 0
    #: Rows whose player name matched two different players that both dressed
    #: that night and could not be separated by team — the same-game Aho
    #: case. Settled against neither rather than against a coin flip.
    outcomes_ambiguous: int = 0
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


#: The sides a price row may name. Pricing reads the first two as the Over;
#: settlement reads them the same way. Anything else is unparseable: pricing
#: used to read every other string as an Under while `settle` read anything
#: beginning with "o" as an Over, so an "o" row was priced one way and
#: settled the other, and "maybe" raised in `settle` and ended the report.
OVER_SELECTIONS = frozenset({"over", "yes"})
UNDER_SELECTIONS = frozenset({"under", "no"})


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



def _expected_toi(row: Any) -> float:
    """A sample's expected ice time, and never its actual one."""
    value = getattr(row, "expected_toi_seconds", None)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if number != number else number


def _game_of(row) -> str:
    """One game: the provider's event id where there is one, else the
    league game date and the two teams — never the UTC commence date."""
    event = clean_text(getattr(row, "provider_event_id", ""))
    if event:
        return event
    return "|".join(
        (
            row_game_date(row),
            clean_text(getattr(row, "home_team", "")),
            clean_text(getattr(row, "away_team", "")),
        )
    )


def run_backtest(
    prices: pd.DataFrame,
    samples: pd.DataFrame,
    *,
    edge_threshold: float = MIN_PROP_EDGE,
    now: datetime | None = None,
    retention_note: str = "",
    unmeasurable_markets: Mapping[str, str] | None = None,
    window_label: str = "",
    correct: Any = None,
    team_names: Mapping[str, str] | None = None,
    phase: str = "auto",
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
    report.rows_read = len(prices)

    # A correction indexed on ice time needs the expected figure. Without the
    # column every sample would index at zero, which is a different
    # correction from the one that was fitted and nothing would say so.
    if (
        correct is not None
        and not samples.empty
        and "expected_toi_seconds" not in samples.columns
    ):
        raise ValueError(
            "A correction was supplied but the samples carry no "
            "`expected_toi_seconds`. Refusing rather than applying it on a "
            "missing index; regenerate the samples."
        )
    if prices.empty:
        return report
    # NO SAMPLES IS NOT NO PRICES. This returned here for either, before the
    # phase filter below, so prices with no model samples — a worktree, or a
    # purchase probe that never builds them — reported "No snapshot window
    # was filtered" with `--phase late` named and "Priced outcomes seen: 0"
    # over 20,000 price rows, skipped the team-map refusal below, and the
    # claims summary then said no prices had been bought for any market. The
    # prices still go through the same window, collapse and accounting; with
    # no opinion to compare, every priced outcome lands in "without a model
    # opinion", which is what happened. The runner refuses before this.
    if samples.empty:
        report.notes.append(
            "No walk-forward samples were supplied, so no priced outcome had "
            "a model opinion to compare with its price and nothing about the "
            "model is measured. Every priced outcome is counted as one "
            "without a model opinion."
        )

    # ONE WAGER IS ONE BET, AT THE BEST PRICE A CARD COULD HAVE TAKEN.
    #
    # The store holds every book's quote on the same selection — 2.8 of them
    # on average — and counting each as its own bet measured a strategy this
    # lab would never run: betting all eight books at their average price
    # rather than taking the one best price, which is exactly what
    # `gameday_card.build_candidates` does. It also made every interval about
    # sqrt(2.8) too narrow, because eight quotes on one outcome are eight
    # copies of one coin flip, not eight flips.
    #
    # Together those two errors published "-1.55% over 73,918 bets, interval
    # excluding zero" — a demonstrated loss — where the card's own policy over
    # the same data gives -0.34% over 26,091 bets, spanning zero. The sibling
    # football lab already collapses to distinct wagers and says so in its
    # own report; this lab did not.
    #
    # Best-of-N is optimistically biased in the other direction (the best
    # price is the likeliest to be stale), so the two numbers bracket the
    # truth rather than one replacing the other. The pessimistic bracket is
    # kept and reported beside this one.
    # One phase at a time. The store may hold the same wager priced at more
    # than one moment before face-off, and the best-price collapse below
    # would otherwise take the better of two moments — a price nobody could
    # have taken, which inflates the measured edge invisibly.
    if phase:
        labelled = label_phases(prices)
        present = [
            p for p in labelled["phase"].unique() if str(p) != "unknown"
        ]
        # Auto-detect rather than trust a default. A hardcoded window that
        # matches nothing falls through silently and measures the mixture it
        # was added to prevent — which is exactly what happened the first
        # time this guard was written.
        if phase == "auto":
            if len(present) > 1:
                raise ValueError(
                    "This store holds prices from more than one window "
                    f"({sorted(present)}). A wager priced at two distances "
                    "from face-off is two different questions and the better "
                    "of the two is a price nobody could have taken. Name the "
                    "window explicitly: --phase card (or late/early), or "
                    "--phase all to measure the mixture on purpose."
                )
            phase = str(present[0]) if present else ""
        # A NAMED WINDOW FILTERS WHETHER OR NOT IT MATCHED ANYTHING. The
        # filter used to be skipped when the named window came back empty,
        # which left the full mixture in `prices` and measured every window at
        # once under no label — the same silent fall-through the auto-detect
        # was added to remove, still live on the path where a window is named.
        # It fires only when the operator asks for a window the store does not
        # have, which is exactly when a wrong number is least likely to be
        # questioned. A named window that matches nothing now measures
        # nothing. `phase` empty is a different thing and keeps the old
        # behaviour: it means the store carries no window information at all,
        # not that a window was asked for and missed.
        if phase:
            in_window = labelled["phase"] == phase
            # A ROW WITH NO READABLE MOMENT IS NOT A ROW FROM ANOTHER MOMENT.
            # Both used to be one count, "outside the window", explained as
            # "a wager priced at two different moments" — which says nothing
            # true about a row whose snapshot or face-off could not be
            # parsed. On one real week (`card`), sending 30% of the quotes
            # with an unparseable time cut priced outcomes by 1,326 and grew
            # that count from 23,056 rows to 35,907, while the reconciliation
            # said "all of them" — and a provider format change is exactly
            # what produces such rows. Counted apart, and named.
            unknown = (labelled["phase"] == "unknown") & ~in_window
            kept = labelled[in_window]
            report.phase = str(phase)
            report.rows_window_unknown = int(unknown.sum())
            report.rows_other_window = int((~in_window & ~unknown).sum())
            prices = kept.drop(columns=["hours_before", "phase"])
            if kept.empty:
                report.notes.append(
                    f"No price row is in the `{phase}` window, so nothing was "
                    "measured against a real price. The window(s) this store "
                    f"does hold: {sorted(present) or 'none'}."
                )
            else:
                report.phase_hours = float(kept["hours_before"].median())
                if report.rows_other_window:
                    report.notes.append(
                        f"{report.rows_other_window:,} price row(s) outside "
                        f"the `{phase}` window were excluded. A wager priced "
                        "at two different moments is two different questions, "
                        "and the better of the two is a price nobody could "
                        "have taken."
                    )
            if report.rows_window_unknown:
                report.notes.append(
                    f"{report.rows_window_unknown:,} price row(s) have no "
                    "parseable snapshot or face-off time, so the window they "
                    "were priced in is unknown. They were excluded rather "
                    f"than guessed into the `{phase}` window or another one."
                )

    report.quotes_seen = len(prices)
    # THE WAGER IS A GAME AND A PLAYER, NOT A UTC DAY AND A SPELLING. This
    # keyed on the raw `date` column, which is the UTC commence date: a 7pm
    # ET face-off (00:00Z) and the next afternoon's game share one, so each
    # player's wager on a back-to-back collapsed to whichever game paid more
    # and the other vanished before `priced_outcomes` counted it — 4,196
    # late-window and 5,337 card-window wager keys on the bought store, with
    # the reconciliation still printing "Accounted for: all of them". It
    # also keyed the raw player string, so one player spelled two ways by
    # two books was two wagers. The card keys on the game and the player's
    # identity (`card_pricing.selection_key`), and this replays the card.
    prices = prices.assign(
        _wager_game=[_game_of(row) for row in prices.itertuples()],
        _wager_player=[player_key(p) for p in prices["player"]],
    )
    prices = best_price_per_wager(
        prices, ["_wager_game", "market", "_wager_player", "line", "selection"]
    ).drop(columns=["_wager_game", "_wager_player"])
    report.wagers = len(prices)

    # One entry per player-game-market, indexed under every legitimate
    # spelling (`player_name_aliases`), carrying the player's identity and
    # team so a shared name can be resolved rather than last-write-won. The
    # flat version of this index settled Carolina's Sebastian Aho prices
    # against the Islanders' Sebastian Aho's games on the 123 nights both
    # dressed, and dropped every "A.J." spelling of a registry "(AJ)" name.
    model_by_key: dict[
        tuple[str, str, str], dict[int, tuple[str, Any, float, float]]
    ] = {}
    for row in samples.itertuples():
        entry = (
            str(getattr(row, "team", "")).strip().upper(),
            distribution_from(row.mean, getattr(row, "dispersion_r", None)),
            float(row.actual),
            # Expected TOI only: the correction must be applied on what a live
            # card can have. `expected or actual` substituted ACTUAL ice time,
            # which is hindsight, wherever the expected value was 0 or absent,
            # and a correction fitted on one index was applied on another.
            _expected_toi(row),
        )
        player_id = int(getattr(row, "player_id", 0) or 0)
        for alias in player_name_aliases(row.player):
            model_by_key.setdefault(
                (str(row.date)[:10], str(row.market), alias), {}
            )[player_id] = entry
    # Supplied by the caller (the runner passes `team_names.csv` from its
    # --processed-dir), else built from the boxscore cache.
    #
    # This used to say a checkout with no boxscore cache "yields an empty
    # map, so resolution finds no teams and shared names resolve to neither:
    # the conservative direction". The map is never empty — the builder
    # always adds the Utah and Arizona aliases — and neither half held. With
    # no team resolved the filter below is skipped, so a lone same-named
    # candidate is accepted whatever team they play for; and in a Utah game
    # the aliases resolve Utah alone, so the filter keeps only Utah players
    # and voids every priced player on the other side. On the bought store
    # (3,804,233 rows) the full map resolves both teams of every row and the
    # alias-only map resolves both of none and one side of 229,388. So a
    # store with team labels that no game's two teams resolve in is refused.
    team_map: dict[str, str] | None = (
        dict(team_names) if team_names is not None else None
    )
    games = [
        (clean_text(home), clean_text(away))
        for home, away in prices.reindex(columns=["home_team", "away_team"])
        .drop_duplicates()
        .itertuples(index=False)
    ]
    games = [game for game in games if game[0] or game[1]]
    if games:
        if team_map is None:
            team_map = build_team_name_map()
        if not any(
            resolve_team(home, team_map) and resolve_team(away, team_map)
            for home, away in games
        ):
            missing = sorted(
                {
                    label
                    for game in games
                    for label in game
                    if label and resolve_team(label, team_map) is None
                }
            )
            preview = ", ".join(missing[:6]) + (
                f" and {len(missing) - 6} more" if len(missing) > 6 else ""
            )
            raise UnresolvedTeamsError(
                f"Not one of the {len(games):,} priced game(s) names two teams "
                f"the team-name map can resolve ({len(team_map)} spelling(s)). "
                f"Unresolved: {preview or '(none named)'}. Measured anyway, "
                "the check that a player's team is in the priced game would "
                "be skipped everywhere except Utah games, where it would void "
                "the other side. Point --processed-dir at a directory holding "
                "team_names.csv (scripts/run_gameday_card.py writes it), or "
                "run where data/raw/nhl/boxscore can rebuild it."
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
            report.outcomes_unparseable += 1
            continue
        # A blank line reads as NaN and `float(nan)` succeeds, so it used to
        # pass the parse above: with a model opinion `math.floor` raised in
        # `over_probability` and ended the whole report, and without one it
        # was filed as "without a model opinion". A side neither pricing nor
        # settlement names ended the report in `settle` once its edge
        # cleared. Both are unparseable rows, counted here with the rest.
        if not math.isfinite(line) or selection not in (
            OVER_SELECTIONS | UNDER_SELECTIONS
        ):
            report.outcomes_unparseable += 1
            continue
        # The game date, not the UTC date of puck drop. An evening North
        # American game commences on the *next* UTC day, so joining on the raw
        # commence date silently discarded roughly seven prices in ten — and
        # the survivors were disproportionately matinees, which is a
        # systematically different set of fixtures.
        date_text = row_game_date(row)
        candidates: dict[int, tuple[str, Any, float, float]] = {}
        for alias in player_name_aliases(player):
            candidates.update(
                model_by_key.get((date_text, market, alias), {})
            )
        if not candidates:
            unmatched.add(player)
            report.outcomes_without_a_model_opinion += 1
            continue
        # The price row names the game, so the side that plays in it wins the
        # join — and the check runs on a *single* candidate too, because a
        # lone candidate can still be the wrong same-named player when the
        # right one did not dress that night. A lone candidate whose team is
        # not in the priced game is an unmatched price (a void), not a match.
        home_label = clean_text(getattr(row, "home_team", ""))
        away_label = clean_text(getattr(row, "away_team", ""))
        if home_label or away_label:
            if team_map is None:
                team_map = build_team_name_map()
            game_teams = {
                resolve_team(home_label, team_map),
                resolve_team(away_label, team_map),
            }
            game_teams.discard(None)
            if game_teams:
                candidates = {
                    player_id: entry
                    for player_id, entry in candidates.items()
                    if entry[0] in game_teams
                }
        if len(candidates) > 1:
            report.outcomes_ambiguous += 1
            continue
        if not candidates:
            unmatched.add(player)
            report.outcomes_without_a_model_opinion += 1
            continue
        _, distribution, actual, toi_seconds = next(iter(candidates.values()))
        over_probability = distribution.over_probability(line)
        if correct is not None:
            # The hook receives the market, the game date, the player's ice
            # time and the raw P(over), and must be walk-forward on its own
            # account — the timeline it looks into is fitted only on strictly
            # earlier dates.
            over_probability = float(
                correct(market, date_text, toi_seconds, over_probability)
            )

        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            report.outcomes_unparseable += 1
            continue

        # The model prices the Over. The Under's model probability is its
        # complement; the price's is its own, which is why the two sides can
        # both look like edges on a vigged market and neither is.
        side_probability = (
            over_probability
            if selection in OVER_SELECTIONS
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

    # A market this run measured is not unmeasurable, whatever an older probe
    # concluded. `hits` was recorded as "not offered in any of 256 events" and
    # then settled 5,021 wagers in the 9.5-hour window, because the probe
    # asked one region and both books that quote it — ESPN BET and theScore
    # Bet — are in the second. Printing a market's measurement and calling it
    # unmeasurable four sections later is the report contradicting itself,
    # which is the exact failure this document exists to prevent. The stale
    # verdict is retired here, and the contradiction is stated rather than
    # quietly dropped.
    for market in sorted(set(report.unmeasurable_markets) & set(report.by_market)):
        report.unmeasurable_markets.pop(market, None)
        report.notes.append(
            f"`{market}` was named unmeasurable by an earlier retention probe "
            f"and this run measured {report.by_market[market].bets:,} bets on "
            "it. The probe is the stale side of that disagreement — it was "
            "run against a narrower set of books — so its verdict is retired "
            "here rather than printed beside the measurement refuting it."
        )
    return report


def _side_of(bet: PlacedBet) -> str:
    """Which way a bet points, normalising `yes`/`no` onto over/under."""
    side = str(bet.selection).strip().lower()
    return "over" if side in OVER_SELECTIONS else "under"


def _reconciliation_line(report: "BacktestReport") -> str:
    """Every price row read must land in exactly one bucket.

    Checked in two stages, because rows leave in two places: before the
    priced outcomes are counted (another window, an unknown window, another
    book's quote on a wager already counted) and inside the loop that prices
    them (no opinion, below threshold, unparseable, ambiguous, bet).

    This used to check only the second stage, against `priced_outcomes` —
    which is bumped at the top of the same loop that bumps every bucket, so
    "Accounted for: all of them." was printed by construction, including
    while the UTC-day collapse lost 4,196 late-window wager keys before the
    loop ever saw them. What the identity catches, said plainly: a code path
    that drops a row, or counts one twice, without a counter, anywhere from
    reading the store to placing a bet. What it cannot catch: a collapse
    keyed on the wrong columns, which merges wagers into a bucket that is
    counted correctly — the printed bucket sizes are what show that. A
    provider format change is not caught by the identity either; it lands in
    a named bucket (window unknown, unparseable), and the bucket is printed.
    """
    before_the_loop = (
        report.rows_other_window
        + report.rows_window_unknown
        + (report.quotes_seen - report.wagers)
    )
    in_the_loop = (
        report.outcomes_without_a_model_opinion
        + report.outcomes_below_threshold
        + report.outcomes_unparseable
        + report.outcomes_ambiguous
        + len(report.bets)
    )
    gaps = []
    if before_the_loop + report.priced_outcomes != report.rows_read:
        gaps.append(
            f"{report.rows_read:,} price rows read, "
            f"{before_the_loop + report.priced_outcomes:,} accounted for"
        )
    if in_the_loop != report.priced_outcomes:
        gaps.append(
            f"{report.priced_outcomes:,} outcomes seen, "
            f"{in_the_loop:,} accounted for"
        )
    if not gaps:
        return "- Accounted for: all of them."
    return (
        f"- **DOES NOT RECONCILE**: {'; '.join(gaps)}. The difference was "
        "dropped by a path with no counter, or counted twice, and whatever "
        "those rows have in common is missing from this measurement."
    )


def _accounting_lines(report: "BacktestReport") -> list[str]:
    """Where every price row went, from the store to the bets.

    Printed whether or not a bet was placed: a report that measured nothing
    is exactly the one whose reader needs to see where the rows went.
    """
    return [
        f"- Price rows read: {report.rows_read:,}",
        (
            "- Outside the measured window, excluded: "
            f"{report.rows_other_window:,}"
        ),
        (
            "- Window unknown (no parseable snapshot or face-off time), "
            f"excluded: {report.rows_window_unknown:,}"
        ),
        (
            "- Another book's quote on a wager already counted at its best "
            f"price: {report.quotes_seen - report.wagers:,}"
        ),
        f"- Priced outcomes seen: {report.priced_outcomes:,}",
        (
            "- Without a model opinion: "
            f"{report.outcomes_without_a_model_opinion:,}"
        ),
        (
            "- Below the edge threshold: "
            f"{report.outcomes_below_threshold:,}"
        ),
        (
            "- Unparseable line, odds or selection: "
            f"{report.outcomes_unparseable:,}"
        ),
        (
            "- Ambiguous player name, dropped: "
            f"{report.outcomes_ambiguous:,}"
        ),
        f"- Bets placed: {len(report.bets):,}",
        _reconciliation_line(report),
    ]


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
        "measured historically. Any such market is named below as "
        "unmeasurable, and a calibration number is not offered in its place; "
        "when no market is named there, none was found to be unmeasurable.",
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
        (
            f"- Priced **{report.phase_hours:.1f} hours before face-off** "
            f"(`{report.phase}` window). A return measured at one distance "
            "from the puck is not comparable to one measured at another: the "
            "lineup is known at four hours and guessed at nine."
            if report.phase else
            "- No snapshot window was filtered, so this number may mix prices "
            "taken at different distances from face-off."
        ),
        f"- {report.summary_line()}",
        "",
    ]

    if report.overall is None or not report.overall.bets:
        # When not one priced outcome had an opinion, the threshold never had
        # anything to clear, and saying it was not cleared blames it for what
        # a missing or mismatched model did.
        no_opinion_at_all = bool(report.priced_outcomes) and (
            report.outcomes_without_a_model_opinion == report.priced_outcomes
        )
        lines.extend(
            [
                "## Not measured",
                "",
                (
                    "Not one historically-priced outcome had a model opinion "
                    "behind it, so no bet was placed and **nothing is "
                    "measured**."
                    if no_opinion_at_all else
                    "No historically-priced outcome cleared the edge "
                    "threshold with a model opinion behind it, so no bet was "
                    "placed and **nothing is measured**."
                ),
                "",
                *_accounting_lines(report),
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

        if report.bets:
            claimed = sum(bet.edge for bet in report.bets) / len(report.bets)
            realised = report.overall.roi if report.overall else 0.0
            lines.extend(
                [
                    "### The claimed edge against the realised one",
                    "",
                    (
                        f"The average selected bet claimed a "
                        f"**{claimed:+.1%}** edge and the flat-stake return "
                        f"was **{realised:+.1%}**. That gap is not a mystery "
                        "and not a fault in the measurement: bets are "
                        "selected wherever the model most disagrees with the "
                        "price, which is exactly where the model's own "
                        "estimation error concentrates. A threshold on "
                        "estimated edge harvests real edge and estimation "
                        "error together, and the realised number is what is "
                        "left after the error washes out."
                    ),
                    "",
                    (
                        "The mean predictions themselves are close to "
                        "unbiased — the walk-forward means run within a few "
                        "percent of the actuals on every market — so the gap "
                        "lives in the tails and in selection, not in the "
                        "rates."
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
                *_accounting_lines(report),
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
    elif not report.retention_note:
        # Only while retention is genuinely unknown. This sentence used to
        # print unconditionally, so it appeared directly beneath a table
        # establishing all seven markets as measurable — the report saying
        # "none of them is established" under its own establishment of them.
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
        "outcomes_unparseable": report.outcomes_unparseable,
        "outcomes_ambiguous": report.outcomes_ambiguous,
        "outcomes_without_a_model_opinion": report.outcomes_without_a_model_opinion,
        "outcomes_below_threshold": report.outcomes_below_threshold,
        "bets": len(report.bets),
        "unmeasurable_markets": report.unmeasurable_markets,
        "notes": report.notes,
        "overall": _interval_payload(report.overall),
        "looks": report.looks,
        # Which window these numbers describe, so a summary reading only the
        # JSON can say so rather than assume.
        "phase": report.phase,
        "phase_hours": report.phase_hours,
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


def window_phrase(payload: Mapping[str, Any], default_phase: str = "") -> str:
    """"`late` window, 4.1 hours before face-off", from a saved payload."""
    phase = str(payload.get("phase") or default_phase or "").strip()
    if not phase:
        return ""
    hours = payload.get("phase_hours")
    if isinstance(hours, (int, float)) and hours > 0:
        return f"`{phase}` window, {float(hours):.1f} hours before face-off"
    return f"`{phase}` window"


def by_market_with_other_windows(
    directory: Path, contract: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """The contract report's markets, plus any it has no bets for.

    A market the contract window measured keeps that measurement, always.
    Only a market with no bets there is read from another window, and it
    carries `_window` naming that window. Choosing per market whichever window
    looked better would be the look-back max this lab keeps removing.
    """
    merged: dict[str, dict[str, Any]] = {
        str(market): dict(entry)
        for market, entry in (contract.get("by_market") or {}).items()
        if isinstance(entry, dict)
    }
    for phase, filename in OTHER_WINDOW_JSON_FILENAMES.items():
        path = Path(directory) / filename
        if not path.is_file():
            continue
        try:
            other = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(other, dict):
            continue
        phrase = window_phrase(other, default_phase=phase)
        for market, entry in (other.get("by_market") or {}).items():
            if not isinstance(entry, dict) or int(entry.get("bets", 0) or 0) <= 0:
                continue
            current = merged.get(str(market))
            if current and int(current.get("bets", 0) or 0) > 0:
                continue
            merged[str(market)] = {**entry, "_window": phrase}
    return merged
