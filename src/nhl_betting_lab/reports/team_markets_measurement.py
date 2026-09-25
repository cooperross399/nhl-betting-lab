"""`data/outputs/team_markets_measurement.md` — the team model, measured.

Team markets are not the point of this lab. They exist so that an edge
anywhere can be found, and a market nobody prices is a market where nobody
can find one. But "not the point" is not a reason to measure them loosely, so
this report is built to the same rules as the props one:

* every number carries its sample size;
* calibration can rule the model out and never in;
* where historical prices exist the price-based backtest decides, and where
  they do not the report says **no price-based measurement** rather than
  offering a calibration figure in its place.

## What the split by market is for

Moneyline, puck line and totals fail differently, and pooling them would hide
which one is broken. In particular the puck line is the market most likely to
expose a modelling error, because covering -1.5 depends on the overtime rule
rather than on the scoring rate — so a model that has overtime wrong looks
fine on moneylines and totals and wrong only here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.backtest.team_walk_forward import DEFAULT_TOTAL_LINES, PUCK_LINES
from nhl_betting_lab.config import MIN_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.calibration import (
    PlattCalibration,
    brier_score,
    calibration_verdict,
    reliability_table,
    scored_keys,
    walk_forward_calibrate,
)
from nhl_betting_lab.providers.team_names import (
    TEAM_NAMES_FILENAME,
    UnresolvedTeamsError,
    load_team_name_map,
    resolve_team,
)
from nhl_betting_lab.models.value import (
    OddsError,
    american_to_implied,
    profit_on_win,
)
from nhl_betting_lab.stores import best_price_per_wager, label_phases
from nhl_betting_lab.season import row_game_date
from nhl_betting_lab.stats import (
    NO_DEMONSTRATED_EDGE,
    ROI_TABLE_HEADER,
    RoiInterval,
    detection_table,
    roi_interval,
)


MEASUREMENT_MARKDOWN_FILENAME = "team_markets_measurement.md"
MEASUREMENT_JSON_FILENAME = "team_markets_measurement.json"

#: Below this many samples a market gets its count and no verdict.
SAMPLE_FLOOR = 200


@dataclass
class MarketMeasurement:
    market: str
    samples: int = 0
    warmup_skipped: int = 0
    raw_brier: float | None = None
    corrected_brier: float | None = None
    correction: PlattCalibration = field(
        default_factory=PlattCalibration.identity
    )
    reliability: list[Any] = field(default_factory=list)
    verdict: str = ""
    priced: RoiInterval | None = None
    #: Where every WAGER of this market landed — seen, unresolved, unmatched,
    #: unparseable, below_threshold — counted after the best-price collapse,
    #: one per wager, as the bets on `priced` are. `quotes` is the unit before
    #: the collapse: the book quotes (price rows) those wagers were taken
    #: from. See `reconciliation_line` for why the two are printed together.
    accounting: dict[str, int] = field(default_factory=dict)
    #: The provider team names the team-name map could not resolve.
    unresolved_names: set[str] = field(default_factory=set)

    @property
    def has_price_evidence(self) -> bool:
        return self.priced is not None and self.priced.bets > 0

    def reconciliation_line(self) -> str:
        """Where this market's wagers went, and the book quotes behind them.

        Every count here is taken after `best_price_per_wager`, one per
        wager. It used to print as "`moneyline`: 4,200 prices seen", beside
        a standing note reading "Prices measured: 212,964 of 308,944 stored
        rows" — which does count rows. On the bought `late` window moneyline
        is 71,430 book quotes and 4,200 wagers, puck line 70,298 and 4,582,
        totals 71,236 and 7,926, so the three "prices seen" summed to 16,708
        against 212,964 "prices measured", in the same unit by their labels
        and 9x to 17x apart in fact. The counts were right and the unit was
        not. The line now says wagers, and prints the quotes they were
        collapsed from. Summed over the markets measured, the quotes are the
        "Prices measured" rows (212,964 = 71,430 + 70,298 + 71,236), so the
        two figures reconcile instead of reading as one unit.
        """
        seen = self.accounting.get("seen", 0)
        if not seen:
            return ""
        bets = (self.priced.bets if self.priced else 0)
        accounted = (
            self.accounting.get("unresolved", 0)
            + self.accounting.get("unmatched", 0)
            + self.accounting.get("unparseable", 0)
            + self.accounting.get("below_threshold", 0)
            + bets
        )
        matched = (
            seen
            - self.accounting.get("unresolved", 0)
            - self.accounting.get("unmatched", 0)
        )
        # A measurement built before `quotes` was counted names no quote
        # figure rather than guessing one.
        quotes = self.accounting.get("quotes")
        behind = (
            f", each at its best price among {quotes:,} book quote(s)"
            if quotes is not None
            else ", each at its best price"
        )
        base = (
            f"`{self.market}`: {seen:,} wager(s) seen{behind}, "
            f"{self.accounting.get('unresolved', 0):,} naming a team the map "
            "could not resolve, "
            f"{self.accounting.get('unmatched', 0):,} unmatched "
            f"({matched / seen:.0%} matched), "
            f"{self.accounting.get('below_threshold', 0):,} below threshold, "
            f"{bets:,} bets."
        )
        if accounted == seen:
            return base
        return base + (
            f" **DOES NOT RECONCILE**: {seen - accounted:,} wager(s) dropped "
            "by a path with no counter."
        )


@dataclass
class TeamMeasurementReport:
    generated_at: str
    total_samples: int = 0
    games: int = 0
    markets: list[MarketMeasurement] = field(default_factory=list)
    #: Rows left after the window was chosen: in the window, strictly before
    #: face-off. NOT the rows on disk — see `stored_rows`.
    priced_outcomes: int = 0
    #: Every price row handed to the measurement before any window was
    #: chosen, in total and by market. The report used to print
    #: `priced_outcomes` as the number "on disk", so `--phase card` against a
    #: store of 308,944 `late` and `early` rows read "0 historical team
    #: price(s) are on disk", and the zero reached `what_we_can_claim.md` as
    #: "no historical prices have been bought". Saved to the JSON so the
    #: claims document can say "stored, none in this window" instead.
    stored_rows: int = 0
    stored_by_market: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: The window every price in this report was captured in, and its median
    #: distance from face-off. Empty only when the prices carried no window
    #: information at all, which is not the same as a window asked for and
    #: missed. See `select_price_window`.
    phase: str = ""
    phase_hours: float = 0.0
    #: Rows held by the store before any window was chosen, by window, and the
    #: rows set aside because they were not captured strictly before face-off.
    windows_in_store: dict[str, int] = field(default_factory=dict)
    excluded_after_face_off: int = 0
    #: WAGERS (one per wager, at its best price) naming a team the team-name
    #: map could not resolve, summed over every market, and the names.
    #: Recorded when it is zero too, so a reader can tell "every team
    #: resolved" from "nobody checked". The name says rows and the count
    #: never was: it is taken after the best-price collapse, and the runner
    #: printed it as "N priced row(s)" — with "St Louis Blues" dropped from
    #: the real map that read 1,078 while 14,042 `late` rows named the team.
    #: The key is kept for its readers; `scored_wagers` beside it is its
    #: denominator, in the same unit.
    unresolved_team_rows: int = 0
    unresolved_team_names: list[str] = field(default_factory=list)
    #: Every wager scored against the model across all markets (the sum of
    #: `accounting["seen"]`): 16,708 on the bought `late` window, from
    #: 212,964 price rows.
    scored_wagers: int = 0

    def summary_line(self) -> str:
        if not self.total_samples:
            return (
                "No samples. The team model has not been measured, and that "
                "is the honest statement — not that it is fine."
            )
        measured = [item for item in self.markets if item.has_price_evidence]
        return (
            f"{self.total_samples:,} walk-forward samples across "
            f"{len(self.markets)} market(s) and {self.games:,} games; "
            f"{len(measured)} market(s) have any price-based evidence."
        )


def measure_calibration(
    samples: pd.DataFrame,
    *,
    market: str,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
    refit_every: int = 5,
) -> MarketMeasurement:
    """Walk-forward calibrate one team market."""
    subset = samples[samples["market"].astype(str) == market]
    # A push is not an outcome the model was asked about, so it is excluded
    # rather than scored as a loss. Scoring pushes as losses would make every
    # whole-number total look worse than it is.
    subset = subset[~subset["push"].astype(bool)]
    if subset.empty:
        return MarketMeasurement(market=market, verdict="No samples.")

    ordered = subset.sort_values(["date", "game_id", "selection", "line"])
    rows = [
        (str(row.date), float(row.model_probability), bool(row.outcome))
        for row in ordered.itertuples()
    ]
    result = walk_forward_calibrate(
        rows, minimum_fit_samples=minimum_fit_samples, refit_every=refit_every
    )
    correction = (
        result.corrections[-1][1]
        if result.corrections
        else PlattCalibration.identity()
    )
    # Every selection at every grid line of one game shares its scoreline:
    # total_goals holds 160,446 held-out rows over 3,658 games, up to 13 of
    # one game in one bucket. The reliability interval was a Wilson interval
    # on those rows. Measured on the real samples, the puck_line and
    # total_goals 0-10% and 90-100% buckets were 1.82-1.87x too narrow and
    # covered about 71%, not the 95% the header said; 10 of 36 rows move. It
    # is now clustered on the game (`clustered_wilson_interval`), and the
    # table prints the games beside the rows.
    games = scored_keys(rows, result, ordered["game_id"].tolist())
    return MarketMeasurement(
        market=market,
        samples=len(result.scored),
        warmup_skipped=result.warmup_skipped,
        raw_brier=brier_score(result.raw),
        corrected_brier=brier_score(result.corrected),
        correction=correction,
        reliability=reliability_table(result.raw, clusters=games),
        verdict=calibration_verdict(result),
    )


def _puck_line_selection(selection: str, line: float | None) -> tuple[str, float | None]:
    """Translate a price row's puck-line naming onto the samples' naming.

    The provider says `home` at line `-1.5`; the samples say `home_minus` at
    `-1.5`. The two describe one bet, and joining them on the raw strings
    silently measured the puck line as having no price evidence at all —
    the third join-vocabulary mismatch this repository has found, after team
    names and game dates.
    """
    side = str(selection).strip().lower()
    if line is None or side not in {"home", "away"}:
        return side, line
    suffix = "minus" if float(line) < 0 else "plus"
    return f"{side}_{suffix}", line


def _team_code(
    name: object, names: Mapping[str, str], codes: set[str]
) -> str | None:
    """The samples' abbreviation for one side of a price row, or None.

    The map turns "Toronto Maple Leafs" into "TOR". A row that already says
    "TOR" needs no map, and is accepted only because the samples use exactly
    that string. Anything else is unresolved: never guessed, and no longer
    passed through as the raw provider name, which could only miss the join
    and be counted as though the grid were at fault.
    """
    resolved = resolve_team(name, names)
    if resolved is not None:
        return resolved
    text = str(name or "").strip()
    return text if text in codes else None


def measure_prices(
    prices: pd.DataFrame,
    samples: pd.DataFrame,
    *,
    market: str,
    edge_threshold: float = MIN_EDGE,
    team_names: Mapping[str, str] | None = None,
    processed_dir: Path | None = None,
    looks: int = 1,
    accounting: dict[str, int] | None = None,
    unresolved_names: set[str] | None = None,
) -> RoiInterval | None:
    """Flat-stake ROI against historical team prices, or None if there are none.

    `accounting`, when given, receives per-bucket counts for every wager of
    this market — seen, unresolved, unmatched, unparseable, below threshold —
    taken after the best-price collapse, one per wager, and `quotes`: the
    price rows the wagers were collapsed from. An unmatched price that lands
    in no counter is invisible exactly when the sample grid drifts away from
    the lines the books hang, which is how a third of the bought totals
    silently left this measurement.
    `unresolved_names`, when given, receives every provider team name the map
    could not resolve.

    ## The team-name map is read from `processed_dir`

    With no `team_names`, the map is `team_names.csv` in `processed_dir`
    (rebuilt from the boxscore cache when absent). This used to call
    `load_team_name_map()` with no directory at all, so it read the default
    `data/processed` whatever `--processed-dir` the runner was given. In a
    worktree, where that gitignored file does not exist and no boxscores are
    cached, the fallback map holds only the Utah and Arizona aliases: on the
    bought `late` window it resolved one side of 14,514 of 212,964 rows and
    both sides of none, every price joined nothing, and the report printed
    "0 market(s) have any price-based evidence" — the words it prints when no
    price was ever bought. Copying the file in reproduced the committed
    report exactly (moneyline 954, puck line 1,117, totals 1,216 bets).

    So a market whose prices resolve both teams on **no** row raises
    `UnresolvedTeamsError` rather than measuring nothing. One resolvable side
    is not a resolved row: the aliases alone always supply one side of every
    Utah game.
    """
    if prices.empty or samples.empty:
        return None
    # A price captured at or after face-off is never a price a card could
    # take, in any window, so this refuses one rather than trusting every
    # caller to have filtered. Two callers did not: this report until
    # 2026-09-24, and the rest experiment after it, whose recorded "+19.4u"
    # included 1,070 bets priced once the game had started.
    if "commence_time" in prices.columns and "snapshot" in prices.columns:
        started = label_phases(prices)["hours_before"] <= 0
        if started.any():
            raise ValueError(
                f"{int(started.sum()):,} price row(s) were captured at or after "
                "face-off. Pass the prices through select_price_window first: "
                "a quote on a game already under way is not a price a card "
                "can take."
            )
    priced = prices[prices["market"].astype(str) == market]
    # Counted BEFORE the collapse: every count below is per wager, and this
    # is the only one in the unit the "Prices measured" note uses. Without
    # it the report printed wagers as "prices seen" beside rows and nothing
    # tied the two together (moneyline, `late`: 71,430 rows, 4,200 wagers).
    quotes = len(priced)
    if accounting is not None:
        accounting["quotes"] = quotes
    # One bet per wager, at the best price a card could have taken. The store
    # holds every book's quote on the same selection, and counting each as a
    # separate bet measures a strategy no card runs while narrowing every
    # interval by roughly the square root of the number of books. The props
    # backtest carried the identical defect and published a demonstrated loss
    # that was not one.
    priced = best_price_per_wager(
        priced,
        ["date", "home_team", "away_team", "market", "selection", "line"],
    )
    if priced.empty:
        return None
    # The provider says "Toronto Maple Leafs"; the samples say "TOR". An
    # explicit map is used as given, empty included: `team_names or ...`
    # treated a caller's `{}` as "none passed" and read the default directory.
    names = (
        dict(team_names)
        if team_names is not None
        else load_team_name_map(processed_dir=processed_dir)
    )
    codes = {
        str(team).strip()
        for column in ("home_team", "away_team")
        if column in samples.columns
        for team in samples[column].dropna().unique()
    }
    sides: dict[object, str | None] = {}
    rows: list[tuple[Any, str | None, str | None]] = []
    for row in priced.itertuples():
        home_name = getattr(row, "home_team", "")
        away_name = getattr(row, "away_team", "")
        for name in (home_name, away_name):
            if name not in sides:
                sides[name] = _team_code(name, names, codes)
        rows.append((row, sides[home_name], sides[away_name]))
    missing = sorted(
        {
            name.strip()
            for name, code in sides.items()
            if code is None and isinstance(name, str) and name.strip()
        }
    )
    if unresolved_names is not None:
        unresolved_names.update(missing)
    if not any(home is not None and away is not None for _, home, away in rows):
        source = (
            "the map passed in"
            if team_names is not None
            else (
                f"{TEAM_NAMES_FILENAME} in "
                f"{Path(processed_dir) if processed_dir else PROCESSED_DIR}, "
                "rebuilt from the boxscore cache when that file is absent"
            )
        )
        preview = ", ".join(missing[:6]) + (
            f" and {len(missing) - 6} more" if len(missing) > 6 else ""
        )
        # Rows as rows and wagers as wagers. This printed `len(rows)` — the
        # wagers left by the collapse — as "price row(s)". Every quote on one
        # wager names the same two teams (both are in the collapse key), so
        # "not one row" and "not one wager" are the same statement.
        raise UnresolvedTeamsError(
            f"Not one of the {quotes:,} `{market}` price row(s) "
            f"({len(rows):,} wager(s), one per wager at its best price) names "
            "two teams this measurement can identify: the team-name map "
            f"({len(names)} spelling(s), from {source}) resolved both sides "
            f"of no row. Unresolved: {preview or '(the rows name no team)'}. "
            "Measured anyway, every price would join no sample and the report "
            "would read '0 market(s) have any price-based evidence', the words "
            "it prints when no price was ever bought. Point --processed-dir at "
            f"a directory holding {TEAM_NAMES_FILENAME} "
            "(scripts/run_gameday_card.py writes it), or run where "
            "data/raw/nhl/boxscore can rebuild it."
        )
    if accounting is not None:
        accounting.setdefault("unresolved", 0)

    lookup: dict[tuple, tuple[float, bool, bool]] = {}
    for row in samples[samples["market"].astype(str) == market].itertuples():
        line = None if row.line is None or pd.isna(row.line) else float(row.line)
        lookup[
            (
                str(row.date)[:10],
                str(row.home_team),
                str(row.away_team),
                str(row.selection),
                line,
            )
        ] = (float(row.model_probability), bool(row.outcome), bool(row.push))

    returns: list[float] = []
    wins = pushes = 0
    for row, home, away in rows:
        try:
            line_value = getattr(row, "line", None)
            line = (
                None
                if line_value is None or pd.isna(line_value)
                else float(line_value)
            )
        except (TypeError, ValueError):
            line = None
        # The league game date, not the UTC commence date. An evening face-off
        # is the next day in UTC and joining on that discards most of a season.
        selection = str(getattr(row, "selection", ""))
        if market == "puck_line":
            selection, line = _puck_line_selection(selection, line)
        if accounting is not None:
            accounting["seen"] = accounting.get("seen", 0) + 1
        # Counted apart from `unmatched`, which means the grid or the warm-up
        # window could not score a price. An unresolved name says nothing
        # about the grid; it is the map that is missing.
        if home is None or away is None:
            if accounting is not None:
                accounting["unresolved"] = accounting.get("unresolved", 0) + 1
            continue
        key = (row_game_date(row), home, away, selection, line)
        found = lookup.get(key)
        if found is None:
            if accounting is not None:
                accounting["unmatched"] = accounting.get("unmatched", 0) + 1
            continue
        probability, won, push = found
        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            if accounting is not None:
                accounting["unparseable"] = accounting.get("unparseable", 0) + 1
            continue
        if probability - implied < edge_threshold:
            if accounting is not None:
                accounting["below_threshold"] = (
                    accounting.get("below_threshold", 0) + 1
                )
            continue
        if push:
            returns.append(0.0)
            pushes += 1
            continue
        returns.append(profit_on_win(price) if won else -1.0)
        wins += 1 if won else 0
    if not returns:
        return None
    return roi_interval(returns, wins=wins, pushes=pushes, looks=looks)


def lines_outside_the_grid(prices: pd.DataFrame) -> dict[str, list[float]]:
    """Every bought line the sample grid cannot score, by market.

    The grid is `DEFAULT_TOTAL_LINES` for totals and `PUCK_LINES` (either
    sign) for the puck line. A bought line off the grid joins nothing, lands
    in `unmatched`, and the measurement never sees the price — which is how a
    third of the bought totals silently left an earlier measurement. This
    is the runtime half of that lesson: the report NAMES the drift in its
    standing notes, so it is visible in the tracked measurement document
    rather than waiting on a test that can only run where the bought file is.
    """
    if prices is None or prices.empty or "market" not in prices or "line" not in prices:
        return {}
    grids = {
        "total_goals": {float(value) for value in DEFAULT_TOTAL_LINES},
        "puck_line": {float(value) for value in PUCK_LINES},
    }
    outside: dict[str, list[float]] = {}
    for market, grid in grids.items():
        lines = prices.loc[prices["market"].astype(str) == market, "line"].dropna()
        seen: set[float] = set()
        for value in lines:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            seen.add(abs(number) if market == "puck_line" else number)
        missing = sorted(seen - grid)
        if missing:
            outside[market] = missing
    return outside


class MixedWindowError(ValueError):
    """The store holds more than one window and none was named."""


def select_price_window(
    prices: pd.DataFrame, phase: str = "auto"
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Restrict team prices to one window, captured strictly before face-off.

    ## Why this exists

    This measurement took the best price per wager across **every** snapshot
    the store held, and the team store holds two windows — `late` (inside six
    hours) and `early` (fifteen hours or more). On 7,410 of 24,726 team wagers
    both windows quote the same selection, and the collapse took whichever
    paid more: a price nobody could have taken, because choosing it requires
    knowing at the early moment what the late one would offer.
    `stores.label_phases` says exactly this in its docstring, and the props
    backtest refuses a mixed store for exactly this reason. This path never
    called it.

    **It also took prices captured after the puck dropped.** 34,196 rows of the
    team store were snapshotted at or after face-off — 21,434 at exactly the
    start, 12,692 inside the first three hours, 70 later still. `label_phases`
    files them under `late`, because `late` means "six hours or fewer" and a
    negative number is fewer. A quote on a team that is losing mid-game has a
    low implied probability, clears the edge threshold easily against a
    pre-game model probability, and is then usually lost. That is neither a
    price a card can take nor a question this model answers. The closing rule
    this lab already uses for CLV is "the last price captured strictly before
    the face-off"; the same rule applies here, in every window including
    `all`.

    ## What it does

    * Rows at or after face-off, and rows whose timestamps cannot be read, are
      always excluded and counted.
    * `phase="auto"` raises `MixedWindowError` if more than one window remains,
      rather than choosing silently — the props backtest's first version of
      this guard hardcoded a window, matched nothing, and measured the mixture
      it was written to prevent.
    * A named window filters whether or not it matched anything, so asking for
      a window the store does not hold measures nothing rather than
      everything.
    * `phase="all"` measures the pre-face-off mixture on purpose. It exists for
      parity with the props backtest and for reproducing the old figure; it is
      not what any committed report should describe.
    """
    info: dict[str, Any] = {
        "phase": "",
        "phase_hours": 0.0,
        "windows_in_store": {},
        "excluded_after_face_off": 0,
        "excluded_unknown": 0,
        "excluded_other_windows": 0,
        "no_window_information": False,
    }
    if prices.empty or "market" not in prices.columns:
        return prices, info
    # A frame with no timestamps carries no window information AT ALL, which
    # is not the same as a window asked for and missed. There is nothing to
    # choose between and no face-off to be after, so it is measured as it is
    # and the report says it could not name its window — the props backtest's
    # rule for the same case, kept identical so the two cannot drift. The
    # bought team store always carries both columns.
    if "commence_time" not in prices.columns or "snapshot" not in prices.columns:
        info["no_window_information"] = True
        return prices, info
    labelled = label_phases(prices)
    info["windows_in_store"] = {
        str(k): int(v) for k, v in labelled["phase"].value_counts().items()
    }
    unknown = labelled["phase"] == "unknown"
    started = labelled["hours_before"] <= 0
    info["excluded_unknown"] = int(unknown.sum())
    info["excluded_after_face_off"] = int((started & ~unknown).sum())
    usable = labelled[~unknown & ~started]
    present = sorted(str(p) for p in usable["phase"].unique())

    chosen = str(phase or "").strip().lower()
    if chosen == "auto":
        if len(present) > 1:
            counts = usable["phase"].value_counts().to_dict()
            # Only the windows this store holds. The message used to say
            # "--phase late (or card/early)" to a store with no `card` row, and
            # following that advice wrote a report of 308,944 stored rows that
            # read "0 historical team price(s) are on disk".
            raise MixedWindowError(
                "The team price store holds prices from more than one window "
                f"({', '.join(f'{k}: {v:,}' for k, v in sorted(counts.items()))}). "
                "A wager priced at two distances from face-off is two different "
                "questions, and the better of the two is a price nobody could "
                "have taken. Name one of the windows it holds: "
                + " or ".join(f"--phase {name}" for name in present)
                + ", or --phase all to measure the mixture on purpose."
            )
        chosen = present[0] if present else ""
    if chosen in ("", "all"):
        kept = usable
        info["phase"] = "all" if chosen == "all" else ""
    else:
        kept = usable[usable["phase"] == chosen]
        info["phase"] = chosen
        info["excluded_other_windows"] = int(len(usable) - len(kept))
    if not kept.empty:
        info["phase_hours"] = float(kept["hours_before"].median())
    return kept.drop(columns=["hours_before", "phase"]), info


def held_windows(windows_in_store: Mapping[str, int]) -> str:
    """"`early` (61,784 rows), `late` (247,160 rows)", or "none"."""
    held = [
        f"`{name}` ({int(count):,} rows)"
        for name, count in sorted(windows_in_store.items())
        if str(name) != "unknown" and int(count or 0) > 0
    ]
    return ", ".join(held) or "none"


def missed_window_sentence(report: "TeamMeasurementReport") -> str:
    """What a named window that matched no stored row says about itself.

    The props backtest's wording for the same case, so the two reports read
    alike, plus the face-off filter the props backtest does not apply: a
    window whose every row was captured after the puck dropped measured
    nothing too. Until 2026-09-25 this report said nothing of the kind: asked
    for `card` over a store of 308,944 `late` and `early` rows, it printed
    "median **0.0 hours** before face-off" and "0 historical team price(s)
    are on disk", and exited 0.
    """
    return (
        f"No price row in the `{report.phase}` window was captured before "
        "face-off, so nothing was measured against a real price. The store's "
        "rows by window, before the face-off filter: "
        f"{held_windows(report.windows_in_store)}."
    )


def build_team_measurement(
    samples: pd.DataFrame,
    prices: pd.DataFrame | None = None,
    *,
    edge_threshold: float = MIN_EDGE,
    now: datetime | None = None,
    minimum_fit_samples: int = PlattCalibration.MINIMUM_SAMPLES,
    team_names: Mapping[str, str] | None = None,
    phase: str = "auto",
    processed_dir: Path | None = None,
) -> TeamMeasurementReport:
    """Calibrate and price every team market in `samples`.

    `processed_dir` is where the team-name map is read from when
    `team_names` is not given; pass the directory the prices came from. Raises
    `MixedWindowError` for an unnamed window over a mixed store, and
    `UnresolvedTeamsError` when prices exist and no row's teams resolve.
    """
    moment = now or datetime.now(timezone.utc)
    price_frame = (
        prices if prices is not None else pd.DataFrame(columns=["market"])
    )
    stored = len(price_frame)
    stored_by_market = (
        {
            str(market): int(count)
            for market, count in price_frame["market"]
            .astype(str)
            .value_counts()
            .sort_index()
            .items()
        }
        if stored and "market" in price_frame.columns
        else {}
    )
    # One window, strictly before face-off, BEFORE the best-price collapse in
    # `measure_prices`. See `select_price_window` for what this used to do.
    price_frame, window = select_price_window(price_frame, phase)
    report = TeamMeasurementReport(
        generated_at=moment.isoformat(timespec="seconds"),
        total_samples=len(samples),
        games=int(samples["game_id"].nunique()) if not samples.empty else 0,
        priced_outcomes=len(price_frame),
        stored_rows=stored,
        stored_by_market=stored_by_market,
        phase=window["phase"],
        phase_hours=window["phase_hours"],
        windows_in_store=window["windows_in_store"],
        excluded_after_face_off=window["excluded_after_face_off"],
    )
    markets = (
        sorted(set(samples["market"].astype(str))) if not samples.empty else []
    )
    # Every team market measured on the same games is one family of tests,
    # exactly as the props are.
    looks = max(1, len(markets))
    for market in markets:
        measurement = measure_calibration(
            samples, market=market, minimum_fit_samples=minimum_fit_samples
        )
        measurement.priced = measure_prices(
            price_frame,
            samples,
            market=market,
            edge_threshold=edge_threshold,
            team_names=team_names,
            processed_dir=processed_dir,
            looks=looks,
            accounting=measurement.accounting,
            unresolved_names=measurement.unresolved_names,
        )
        report.markets.append(measurement)

    scored = sum(item.accounting.get("seen", 0) for item in report.markets)
    report.scored_wagers = scored
    report.unresolved_team_rows = sum(
        item.accounting.get("unresolved", 0) for item in report.markets
    )
    report.unresolved_team_names = sorted(
        set().union(*(item.unresolved_names for item in report.markets))
    )

    drift = lines_outside_the_grid(price_frame)
    window_notes: list[str] = []
    if stored:
        if report.phase in ("", "all"):
            where = ", from every window before face-off, on purpose."
        elif len(price_frame):
            where = (
                f", from the `{report.phase}` window, median "
                f"{report.phase_hours:.1f} hours before face-off."
            )
        else:
            # A named window that matches nothing measures nothing AND SAYS
            # SO, as the props backtest does. This note used to read "median
            # 0.0 hours" — the field's default, a median of no rows.
            where = ". " + missed_window_sentence(report)
        window_notes.append(
            f"Prices measured: {len(price_frame):,} of {stored:,} stored rows"
            + where
        )
    if window["excluded_after_face_off"]:
        window_notes.append(
            f"{window['excluded_after_face_off']:,} price row(s) captured at or "
            "after face-off were excluded. A quote on a team already losing "
            "mid-game clears the edge threshold against a pre-game probability "
            "and is then usually lost; it is not a price a card can take."
        )
    if window["excluded_other_windows"]:
        window_notes.append(
            f"{window['excluded_other_windows']:,} price row(s) from other "
            "windows were excluded. The best-price collapse would otherwise "
            "take the better of two moments for one wager — a price nobody "
            "could have taken."
        )
    if window["no_window_information"]:
        window_notes.append(
            "These prices carry no snapshot or face-off time, so this report "
            "cannot say which window they describe or exclude any captured "
            "after the puck dropped. The bought team store always carries both."
        )
    if window["excluded_unknown"]:
        window_notes.append(
            f"{window['excluded_unknown']:,} price row(s) had no readable "
            "snapshot or face-off time and were excluded rather than guessed."
        )
    if scored:
        names = report.unresolved_team_names
        # Wagers, one per wager at its best price: the unit of `seen`. This
        # read "0 of the 16,708 prices scored" two lines below "Prices
        # measured: 212,964", which counts rows.
        window_notes.append(
            f"Team names: {report.unresolved_team_rows:,} of the {scored:,} "
            "wager(s) scored (each at its best price) named a team the "
            "team-name map could not resolve"
            + (
                f" ({', '.join(names[:8])}"
                f"{f' and {len(names) - 8} more' if len(names) > 8 else ''}). "
                "They are counted as unresolved, never guessed and never "
                f"scored; the map is `{TEAM_NAMES_FILENAME}` in the processed "
                "directory, rebuilt from the boxscore cache when absent."
                if report.unresolved_team_rows
                else "."
            )
        )
    report.notes = [
        *window_notes,
        *[
            f"{len(lines)} bought `{market}` line(s) sit outside the sample "
            f"grid and were scored by nothing: {', '.join(f'{line:g}' for line in lines)}. "
            "Widen the grid in `backtest/team_walk_forward.py`; an unmatched "
            "price is a price this measurement never saw."
            for market, lines in sorted(drift.items())
        ],
        "Team markets are not the point of this lab. They are measured to the "
        "same standard anyway, because a market nobody prices is a market "
        "where nobody can find an edge.",
        "The puck line is the market most likely to expose a modelling error: "
        "covering -1.5 depends on the overtime rule rather than on the "
        "scoring rate, so a model that has overtime wrong looks fine on "
        "moneylines and totals and wrong only here.",
        "A push is excluded rather than scored as a loss. Scoring pushes as "
        "losses would make every whole-number total look worse than it is.",
        "The 95% interval on each reliability row counts each game once, not "
        "each row: every selection at every line of one game shares its "
        "scoreline, so one bucket can hold many rows of one game. It is never "
        "narrower than a Wilson interval on the rows.",
        "Calibration can rule this model out; it cannot rule it in. Where "
        "historical prices exist the backtest decides, and where they do not "
        "this report says so rather than offering a calibration number in "
        "their place.",
    ]
    return report


def _fmt(value: float | None, spec: str = ".4f") -> str:
    return format(value, spec) if isinstance(value, (int, float)) else "-"


def render_team_measurement(report: TeamMeasurementReport) -> str:
    lines = [
        "# Team markets measurement",
        "",
        (
            "Moneyline, puck line and totals — calibrated walk-forward, and "
            "measured against real prices wherever any have been bought."
        ),
        "",
        f"- Generated: {report.generated_at}",
        f"- {report.summary_line()}",
        "",
    ]

    if not report.total_samples:
        lines.extend(
            [
                "## Not measured",
                "",
                (
                    "There are no samples, so nothing about the team model is "
                    "known. That is the honest statement — not that it is "
                    "fine."
                ),
                "",
                *["## Standing notes", ""],
                *[f"- {note}" for note in report.notes],
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Calibration",
            "",
            "| Market | Samples | Brier raw | Brier corrected | Correction |",
            "|:-------|--------:|----------:|----------------:|:-----------|",
        ]
    )
    for item in report.markets:
        label = (
            MARKETS_BY_KEY[item.market].label
            if item.market in MARKETS_BY_KEY
            else item.market
        )
        lines.append(
            f"| `{item.market}` ({label}) | {item.samples:,} "
            f"| {_fmt(item.raw_brier)} | {_fmt(item.corrected_brier)} "
            f"| {item.correction.describe()} |"
        )
    lines.append("")

    for item in report.markets:
        lines.extend([f"### `{item.market}`", "", f"- {item.verdict}", ""])
        if item.samples < SAMPLE_FLOOR or not item.reliability:
            lines.extend(
                [
                    f"Only {item.samples} samples; no reliability table is shown.",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                "| Bucket | Samples | Games | Predicted | Observed | 95% on observed |",
                "|:-------|--------:|------:|----------:|---------:|:----------------|",
            ]
        )
        for row in item.reliability:
            if (
                row.clusters is None
                or row.observed_low is None
                or row.observed_high is None
            ):
                raise ValueError(
                    f"`{item.market}` {row.label}: a reliability row with no "
                    "game-clustered interval. A Wilson interval on its rows "
                    "would count every line of one game as a trial."
                )
            lines.append(
                f"| {row.label} | {row.count:,} | {row.clusters:,} "
                f"| {row.predicted:.1%} | {row.observed:.1%} "
                f"| {row.observed_low:.1%} .. {row.observed_high:.1%} |"
            )
        lines.append("")

    lines.extend(["## Measured against real prices", ""])
    if report.phase and report.phase != "all" and not report.priced_outcomes:
        # Named, and matched nothing. This used to fall into the sentence
        # below and print "median **0.0 hours**" — a median of no rows.
        lines.extend([f"**{missed_window_sentence(report)}**", ""])
    elif report.phase and report.phase != "all":
        lines.extend([
            f"Every price below was captured in the `{report.phase}` window, "
            f"median **{report.phase_hours:.1f} hours** before face-off, and "
            "strictly before the puck dropped. A wager priced in two windows is "
            "two questions; this report answers one.",
            "",
        ])
    elif report.phase == "all":
        lines.extend([
            "**This run measures every pre-face-off window at once, on "
            "purpose.** The best-price collapse takes the better of the windows "
            "for each wager, which is a price nobody could have taken. It is "
            "here to reproduce and compare, not to be quoted.",
            "",
        ])
    measured = [item for item in report.markets if item.has_price_evidence]
    if measured:
        lines.append(ROI_TABLE_HEADER)
        for item in measured:
            lines.append(item.priced.as_row(f"`{item.market}`"))
        lines.append("")
        for item in measured:
            lines.append(f"- `{item.market}`: {item.priced.verdict()}")
        lines.append("")
    else:
        # The rows on disk, and how many of them the window left. This used to
        # print `priced_outcomes` — the rows AFTER the window filter — as the
        # number on disk, so 308,944 stored rows read as "0 ... on disk".
        if report.stored_rows:
            held = (
                f"{report.stored_rows:,} historical team price row(s) are on "
                f"disk and {report.priced_outcomes:,} of them "
                + (
                    f"are in the `{report.phase}` window before face-off"
                    if report.phase and report.phase != "all"
                    else "were measured"
                )
            )
        else:
            held = "No historical team price is on disk"
        lines.extend(
            [
                (
                    f"**No price-based measurement.** {held}, and no market "
                    "has enough matched, above-threshold outcomes to measure. "
                    f"This means **{NO_DEMONSTRATED_EDGE}** — and equally, no "
                    "demonstrated absence of one."
                ),
                "",
                (
                    "The calibration numbers above are **not** a substitute. "
                    "They say the model's probabilities are internally "
                    "sensible; they say nothing about whether the market "
                    "disagrees with them profitably."
                ),
                "",
            ]
        )

    # Whenever any price was scored, measured or not. This section sat inside
    # `if measured:`, so a store whose prices ALL went unmatched — the case it
    # was written to expose, after a third of the bought totals vanished that
    # way — rendered no reconciliation at all. On the real store, `late`
    # prices for games after the samples end went 100% unmatched (moneyline
    # 14/14, puck line 16/16, totals 32/32) and the report said only that no
    # market had enough matched outcomes.
    reconciled = [
        f"- {item.reconciliation_line()}"
        for item in report.markets
        if item.reconciliation_line()
    ]
    if reconciled:
        lines.extend(
            [
                "### Where every price landed",
                "",
                (
                    "An unmatched price is one the sample grid could not "
                    "score — a line the books hang that the grid does not "
                    "carry, or a warm-up-window game no sample covers. It is "
                    "counted, because a third of the bought totals once "
                    "vanished this way with nothing saying so. A price naming "
                    "a team the team-name map cannot resolve is counted "
                    "apart from those: it says nothing about the grid. "
                    "Everything here is counted one per wager, at the best "
                    "price any book quoted, as the bets are; the book quotes "
                    "each market's wagers were taken from are named beside "
                    "them."
                ),
                "",
                *reconciled,
                "",
            ]
        )
    if measured:
        lines.extend(
            [
                "### How much data would settle it",
                "",
                detection_table(),
                "",
            ]
        )

    lines.extend(["## Standing notes", "", *[f"- {note}" for note in report.notes], ""])
    return "\n".join(lines)


def save_team_measurement(
    report: TeamMeasurementReport, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / MEASUREMENT_MARKDOWN_FILENAME
    markdown.write_text(render_team_measurement(report), encoding="utf-8")
    payload = {
        "generated_at": report.generated_at,
        "total_samples": report.total_samples,
        "games": report.games,
        "priced_outcomes": report.priced_outcomes,
        # What was on disk, before any window was chosen. `priced_outcomes`
        # is only what the window kept, and a reader that took it for the
        # store called 308,944 bought rows "never bought".
        "stored_rows": report.stored_rows,
        "stored_by_market": report.stored_by_market,
        "phase": report.phase,
        "phase_hours": report.phase_hours,
        "windows_in_store": report.windows_in_store,
        "excluded_after_face_off": report.excluded_after_face_off,
        # Counted in wagers despite its name (see the field); `scored_wagers`
        # is the denominator in the same unit, so no reader has to set it
        # against `stored_rows`.
        "unresolved_team_rows": report.unresolved_team_rows,
        "unresolved_team_names": report.unresolved_team_names,
        "scored_wagers": report.scored_wagers,
        "notes": report.notes,
        "markets": [
            {
                "market": item.market,
                "samples": item.samples,
                "raw_brier": item.raw_brier,
                "corrected_brier": item.corrected_brier,
                "verdict": item.verdict,
                "has_price_evidence": item.has_price_evidence,
                "accounting": dict(item.accounting),
                "bets": item.priced.bets if item.priced else 0,
                "roi": item.priced.roi if item.priced else None,
                "low": item.priced.low if item.priced else None,
                "high": item.priced.high if item.priced else None,
                "includes_zero": (
                    item.priced.includes_zero if item.priced else True
                ),
                "looks": item.priced.looks if item.priced else 1,
                "survives_correction": (
                    item.priced.survives_correction if item.priced else False
                ),
            }
            for item in report.markets
        ],
    }
    json_path = directory / MEASUREMENT_JSON_FILENAME
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
