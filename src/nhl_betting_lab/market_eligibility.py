"""Per-market eligibility for the card.

All-or-nothing eligibility is the wrong shape. A provider can be completely
trustworthy for moneylines and simply not offer blocked shots that night, and
one missing market must not block a whole card.

So eligibility is decided **per market**, and the states are kept distinct
because conflating them is how a card starts lying:

``eligible``
    Allowlisted, priced, and complete for every game in the slate. Usable.
``incomplete``
    Priced for some games and not others. The covered games are reported and
    the market is excluded — a market that covers half the slate would put
    picks only where the provider happened to have prices, which is a
    selection effect, not an edge.
``unavailable``
    The provider returned no rows at all. Not a price of zero, not a "no
    value" verdict — simply absent.
``not_allowlisted``
    Priced and complete, but no reviewed human approval covers it. This is the
    default state of every market in this repository.
``disabled``
    Deliberately excluded regardless of everything else.

**An excluded market is never a pass, a lean, or a no-value call.** Passes and
avoids are genuine model judgements about markets that were actually priced
and modelled. A market the provider could not supply is a different thing
entirely, and presenting one as the other misrepresents the card.

Nothing here invents a price. Absence stays absence.

## A tension worth naming rather than quietly resolving

`require_full_slate` treats a market priced for ten of twelve games as
incomplete, and excludes it. For team markets that is plainly right: a
provider that covers part of a slate is one whose coverage correlates with
something, and picking only where prices exist is a selection effect.

For props the argument is weaker. Books post player props for the games they
post them for, and the bettor is not choosing the subset — the book is. A
strict reading could keep every prop market permanently ineligible, which
would make the lab's primary product unreachable.

That tension is left strict on purpose. If props do turn out to be
systematically incomplete, the honest response is to **measure whether the
covered subset differs from the rest** — not to loosen the gate because the
gate is inconvenient. Loosening it without that measurement would be exactly
the move this repository exists to not make.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from nhl_betting_lab.markets import MARKETS_BY_KEY, market_for
from nhl_betting_lab.puck_drop import parse_commence_time
from nhl_betting_lab.season import row_game_date
from nhl_betting_lab.staging_provider_policy import StagingProviderPolicy


ELIGIBLE = "eligible"
INCOMPLETE = "incomplete"
UNAVAILABLE = "unavailable"
NOT_ALLOWLISTED = "not_allowlisted"
DISABLED = "disabled"

#: The only state that may produce a selection.
USABLE_STATES = frozenset({ELIGIBLE})


@dataclass(frozen=True)
class MarketEligibility:
    """One market's verdict, with the reason spelled out for the report."""

    market: str
    state: str
    reason: str
    games_in_slate: int = 0
    games_priced: int = 0
    rows: int = 0
    #: Games the provider priced this market for, when it covered only some.
    covered_games: tuple[str, ...] = ()
    #: Games it did not, which is the more useful half when diagnosing.
    missing_games: tuple[str, ...] = ()

    @property
    def usable_for_picks(self) -> bool:
        return self.state in USABLE_STATES

    @property
    def is_no_value_call(self) -> bool:
        """Always False. Exists so the answer is written down, not assumed.

        An excluded market is not a model opinion. Anything rendering this
        card can ask, get False, and put the market under "excluded" rather
        than under "passes".
        """
        return False

    def describe(self) -> str:
        return f"`{self.market}`: {self.state} — {self.reason}"


@dataclass
class EligibilityReport:
    """Every market's verdict for one slate."""

    provider_name: str
    games_in_slate: int
    markets: list[MarketEligibility] = field(default_factory=list)

    @property
    def eligible_markets(self) -> tuple[str, ...]:
        return tuple(
            item.market for item in self.markets if item.usable_for_picks
        )

    @property
    def excluded_markets(self) -> tuple[str, ...]:
        return tuple(
            item.market for item in self.markets if not item.usable_for_picks
        )

    def exclusion_reasons(self) -> dict[str, str]:
        return {
            item.market: item.reason
            for item in self.markets
            if not item.usable_for_picks
        }

    def summary_line(self) -> str:
        if not self.eligible_markets:
            return (
                f"No market is eligible for picks across "
                f"{self.games_in_slate} game(s). Every market is excluded with "
                "a stated reason; none is a pass or a no-value call."
            )
        return (
            f"{len(self.eligible_markets)} of {len(self.markets)} markets "
            f"eligible across {self.games_in_slate} game(s): "
            f"{', '.join(self.eligible_markets)}."
        )


def _game_key(row: Mapping[str, object]) -> str:
    return (
        f"{str(row.get('date', '')).strip()} "
        f"{str(row.get('away_team', '')).strip()}@"
        f"{str(row.get('home_team', '')).strip()}"
    ).strip()


def assess_markets(
    prices: pd.DataFrame,
    *,
    slate_games: Sequence[str],
    policy: StagingProviderPolicy,
    provider_name: str,
    markets: Iterable[str] | None = None,
    disabled: Iterable[str] = (),
    require_full_slate: bool = True,
) -> EligibilityReport:
    """Decide each market's state for one slate.

    `prices` is the long-form staged price table with at least `market`,
    `date`, `home_team` and `away_team`. `slate_games` is the set of game keys
    the card would cover, so a market can be judged against the whole slate
    rather than against whatever the provider happened to return.
    """
    keys = tuple(str(market) for market in (markets or MARKETS_BY_KEY))
    turned_off = {str(item).strip() for item in disabled}
    slate = tuple(dict.fromkeys(str(game) for game in slate_games))
    report = EligibilityReport(
        provider_name=str(provider_name), games_in_slate=len(slate)
    )

    if prices.empty or "market" not in prices.columns:
        priced: dict[str, set[str]] = {}
        counts: dict[str, int] = {}
    else:
        frame = prices.copy()
        frame["market"] = frame["market"].astype(str).str.strip()
        frame["_game"] = frame.apply(_game_key, axis=1)
        priced = {
            str(market): set(rows["_game"])
            for market, rows in frame.groupby("market")
        }
        counts = {
            str(market): len(rows) for market, rows in frame.groupby("market")
        }

    for key in keys:
        try:
            market_for(key)
        except KeyError:
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=DISABLED,
                    reason=(
                        "Not a market this lab knows how to price or settle."
                    ),
                )
            )
            continue

        covered = priced.get(key, set())
        rows = counts.get(key, 0)
        missing = tuple(game for game in slate if game not in covered)

        if key in turned_off:
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=DISABLED,
                    reason="Deliberately excluded from automated picks.",
                    games_in_slate=len(slate),
                    games_priced=len(covered),
                    rows=rows,
                )
            )
            continue

        if not covered:
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=UNAVAILABLE,
                    reason=(
                        "The provider returned no rows for this market. That "
                        "is an absence, not a price of zero and not a "
                        "no-value call. Check per-bookmaker coverage "
                        "including alternate lines before concluding it is "
                        "not offered."
                    ),
                    games_in_slate=len(slate),
                    rows=0,
                    missing_games=missing,
                )
            )
            continue

        if require_full_slate and missing:
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=INCOMPLETE,
                    reason=(
                        f"Priced for {len(covered)} of {len(slate)} games. "
                        "Picking only where prices happen to exist is a "
                        "selection effect, not an edge, so the market is "
                        "excluded rather than half-used."
                    ),
                    games_in_slate=len(slate),
                    games_priced=len(covered),
                    rows=rows,
                    covered_games=tuple(sorted(covered)),
                    missing_games=missing,
                )
            )
            continue

        if not policy.market_allowed(provider_name, key):
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=NOT_ALLOWLISTED,
                    reason=policy.refusal_reason(provider_name, key),
                    games_in_slate=len(slate),
                    games_priced=len(covered),
                    rows=rows,
                )
            )
            continue

        report.markets.append(
            MarketEligibility(
                market=key,
                state=ELIGIBLE,
                reason=(
                    f"Allowlisted, and priced for all {len(slate)} game(s) in "
                    "the slate."
                ),
                games_in_slate=len(slate),
                games_priced=len(covered),
                rows=rows,
                covered_games=tuple(sorted(covered)),
            )
        )

    report.markets.sort(key=lambda item: (not item.usable_for_picks, item.market))
    return report


def filter_to_eligible(
    prices: pd.DataFrame, report: EligibilityReport
) -> pd.DataFrame:
    """Drop every row whose market is not eligible.

    Applied before the card is assembled and again after, so a future change
    upstream cannot leak an excluded market into published picks.
    """
    if prices.empty or "market" not in prices.columns:
        return prices
    allowed = set(report.eligible_markets)
    return prices[prices["market"].astype(str).str.strip().isin(allowed)].copy()


def slate_games_from(prices: pd.DataFrame) -> tuple[str, ...]:
    """Every distinct game key present in a price table.

    The provider's view only: a game it priced in no market is not here.
    The card's slate is `slate_games_with_schedule`.
    """
    if prices.empty:
        return ()
    return tuple(
        dict.fromkeys(prices.apply(_game_key, axis=1).tolist())
    )


def slate_games_with_schedule(
    prices: pd.DataFrame,
    scheduled: Mapping[tuple[str, str, str], str],
    *,
    resolve: Callable[[object], str | None],
    now: datetime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The card's slate: every priced game, plus every scheduled game on the
    same league dates that no row prices. Returns (slate, unpriced).

    `scheduled` maps (league date, HOME, AWAY) to the scheduled face-off, as
    `season.scheduled_regular_season_starts` reads it; `resolve` turns a
    provider team name into the abbreviation the schedule uses. A priced row
    matches a scheduled game on (league date, HOME, AWAY) — the key the
    preseason screen already judges by — so the two cannot disagree about
    which game a row belongs to.

    `slate_games_from` alone describes only the games the provider returned,
    and a game it returned for NO market was then absent from the slate and
    could never make any market incomplete. That is the selection effect
    `require_full_slate` exists to block, reached one level up.

    Only the league dates the prices cover are filled in: they are the
    window the fetch asked about. A scheduled game already under way at
    `now` is not added — it cannot be played, and the provider need not
    still list it — but one whose face-off cannot be read is, because an
    unreadable start is not a started game and ambiguity falls on the
    excluded side. An unpriced game is keyed `DATE AWAY@HOME` in the
    league's abbreviations, not the provider's spelling a price key uses.
    A priced game whose team names do not resolve cannot be matched: where
    its rows survive to be judged it counts on both sides, overstating the
    slate by one game — an error toward excluding a market the card could
    not have fully priced anyway, never toward including one.
    """
    if now.tzinfo is None:
        raise ValueError("`now` must carry a timezone to tell a started game.")
    priced = slate_games_from(prices)
    if prices.empty:
        return priced, ()
    days: set[str] = set()
    matched: set[tuple[str, str, str]] = set()
    for row in prices.itertuples():
        day = row_game_date(row)
        days.add(day)
        matched.add(
            (
                day,
                resolve(getattr(row, "home_team", "")) or "",
                resolve(getattr(row, "away_team", "")) or "",
            )
        )
    unpriced: list[str] = []
    for (day, home, away), start in sorted(scheduled.items()):
        if day not in days or (day, home, away) in matched:
            continue
        begins = parse_commence_time(start)
        if begins is not None and begins <= now:
            continue
        unpriced.append(f"{day} {away}@{home}")
    return tuple(dict.fromkeys(priced + tuple(unpriced))), tuple(unpriced)
