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
``not_requested``
    The fetch behind the prices never asked the provider for this market, so
    there is nothing to judge. Only a caller that knows what it asked can say
    this (a live shadow run); the card never passes a requested set and never
    sees the state. It exists because "never asked" and "asked, nobody
    quotes it" read identically as `unavailable`, and the scheduled discovery
    probe — bulk markets only — published nine markets as the provider's
    absence that it had never asked about.
``fetch_failed``
    Asked for, and the per-event request that asks for it failed for every
    game in the slate (an HTTP error, a timeout, an unreadable answer), so
    there are no rows and nothing to judge. Not an absence at the provider:
    retry the fetch. Only a caller that knows which requests failed can say
    this — a live shadow run, and the card reading that run's staging
    provenance. It exists because a run whose every per-event request
    answered HTTP 503 read, row for row, like a run whose books posted
    nothing: nine markets `unavailable`, "The provider returned no rows".
    A market that is missing only SOME games for this reason keeps its
    `unavailable` or `incomplete` state and names those games in its reason.
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
NOT_REQUESTED = "not_requested"
FETCH_FAILED = "fetch_failed"
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


@dataclass(frozen=True)
class FailedRequest:
    """One per-event request that got no usable answer, keyed to its game."""

    game: str
    #: The project markets it asked for that no answered request covered.
    markets: tuple[str, ...]
    error: str


def failed_requests(
    failed_events: Iterable[Mapping[str, object]] | None,
    prices: pd.DataFrame | None = None,
) -> tuple[FailedRequest, ...]:
    """The per-event requests a fetch recorded as failed, each keyed to the
    game exactly as the slate keys it.

    `failed_events` is `FetchResult.failed_events` as `run_provider_shadow.py`
    passes it on and the staging provenance keeps it. A failure is tied to
    its game through the staged rows carrying its `provider_event_id` — the
    bulk rows, which the slate is built from — and, where no row does, from
    the date and teams it recorded. So a failure lands on the very game the
    coverage is measured against, however the events listing spelled it.
    """
    if not failed_events:
        return ()
    games_by_event: dict[str, str] = {}
    if (
        prices is not None
        and not prices.empty
        and "provider_event_id" in prices.columns
    ):
        for row in prices.drop_duplicates("provider_event_id").to_dict("records"):
            event_id = str(row.get("provider_event_id", "") or "").strip()
            if event_id and event_id.lower() != "nan":
                games_by_event.setdefault(event_id, _game_key(row))
    found: list[FailedRequest] = []
    for entry in failed_events:
        if not isinstance(entry, Mapping):
            continue
        event_id = str(entry.get("provider_event_id", "") or "").strip()
        if event_id in games_by_event:
            game = games_by_event[event_id]
        elif str(entry.get("home_team", "") or "").strip() and str(
            entry.get("away_team", "") or ""
        ).strip():
            game = _game_key(entry)
        else:
            game = f"event {event_id or 'unknown'}"
        markets = entry.get("markets") or ()
        if isinstance(markets, str):
            markets = (markets,)
        found.append(
            FailedRequest(
                game=game,
                markets=tuple(
                    sorted({str(item).strip() for item in markets if str(item).strip()})
                ),
                error=str(entry.get("error", "") or "").strip(),
            )
        )
    return tuple(found)


def unanswered_games(
    requests: Sequence[FailedRequest],
) -> dict[str, dict[str, str]]:
    """{project market: {game: why its request failed}}."""
    found: dict[str, dict[str, str]] = {}
    for request in requests:
        for market in request.markets:
            found.setdefault(market, {})[request.game] = request.error
    return found


def name_games(games: Sequence[str], *, limit: int = 4) -> str:
    """A short list of game keys for a reason a person reads."""
    shown = ", ".join(games[:limit])
    return shown + (f" and {len(games) - limit} more" if len(games) > limit else "")


def assess_markets(
    prices: pd.DataFrame,
    *,
    slate_games: Sequence[str],
    policy: StagingProviderPolicy,
    provider_name: str,
    markets: Iterable[str] | None = None,
    disabled: Iterable[str] = (),
    require_full_slate: bool = True,
    requested: Iterable[str] | None = None,
    failed_events: Iterable[Mapping[str, object]] | None = None,
) -> EligibilityReport:
    """Decide each market's state for one slate.

    `prices` is the long-form staged price table with at least `market`,
    `date`, `home_team` and `away_team`. `slate_games` is the set of game keys
    the card would cover, so a market can be judged against the whole slate
    rather than against whatever the provider happened to return.

    `requested` is the set of project markets the fetch behind `prices`
    actually asked the provider for, when the caller knows it. A market
    outside it with no rows is `not_requested`, not `unavailable`: until
    2026-09-25 the scheduled discovery run, which asks for the three bulk
    markets only, reported the other nine as "The provider returned no rows
    for this market" — a claim about a provider nobody had asked. None (the
    card, and any offline assessment of staged files) means "unknown", and
    every market is judged exactly as before. A market with rows is judged
    on its rows whatever this says; rows are never hidden behind a label.

    `failed_events` is the fetch's record of per-event requests that got no
    usable answer (`FetchResult.failed_events`). A market that has no rows
    because its request failed for every game in the slate is
    `fetch_failed`; one missing only some games for that reason keeps its
    state and names them. Until 2026-09-26 nothing here could see a failed
    request: a run whose three per-event requests all answered HTTP 503
    exited 4 and still published nine markets as "The provider returned no
    rows ... check per-bookmaker coverage including alternate lines", word
    for word what a run whose books posted nothing publishes, and the card's
    excluded markets said the same under a note that the fetch had failed.
    None means no failure is known, and every market is judged as before.
    """
    keys = tuple(str(market) for market in (markets or MARKETS_BY_KEY))
    turned_off = {str(item).strip() for item in disabled}
    asked = (
        None if requested is None else {str(item).strip() for item in requested}
    )
    unanswered = unanswered_games(failed_requests(failed_events, prices))
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

        if not covered and asked is not None and key not in asked:
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=NOT_REQUESTED,
                    reason=(
                        "Not requested in this run: the fetch behind these "
                        "prices never asked the provider for this market, "
                        "so there is nothing to judge. That says nothing "
                        "about whether any book quotes it — it is not an "
                        "absence at the provider, not a price of zero and "
                        "not a no-value call."
                    ),
                    games_in_slate=len(slate),
                    rows=0,
                    missing_games=missing,
                )
            )
            continue

        failed_here = unanswered.get(key, {})
        # The slate's games whose request for this market failed. With no
        # slate at all (no market has a row), every failed game counts.
        failed_games = (
            tuple(game for game in slate if game in failed_here)
            if slate
            else tuple(sorted(failed_here))
        )
        failed_missing = tuple(game for game in missing if game in failed_here)

        if not covered and failed_games and len(failed_missing) == len(missing):
            scope = (
                f"all {len(slate)} game(s) in the slate"
                if slate
                else f"{len(failed_games)} game(s)"
            )
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=FETCH_FAILED,
                    reason=(
                        "No rows, because the per-event request that asks "
                        f"for this market failed for {scope}: the provider "
                        "refused it or did not answer. That is a failed "
                        "fetch — not an absence at the provider, not a price "
                        "of zero and not a no-value call — and it says "
                        "nothing about whether any book quotes this market. "
                        "Retry the fetch before concluding anything; the "
                        "alternate lines were asked in the same request, and "
                        "a wider region would not answer it."
                    ),
                    games_in_slate=len(slate),
                    rows=0,
                    missing_games=missing,
                )
            )
            continue

        if not covered:
            if failed_missing:
                absence = (
                    f"For {len(failed_missing)} of the {len(slate)} game(s) "
                    f"({name_games(failed_missing)}) that is because the "
                    "per-event request failed, not because no book quotes "
                    "it: retry those before reading them either way. The "
                    "rest is an absence, not a price of zero and not a "
                    "no-value call."
                )
            else:
                absence = (
                    "That is an absence, not a price of zero and not a "
                    "no-value call."
                )
            report.markets.append(
                MarketEligibility(
                    market=key,
                    state=UNAVAILABLE,
                    reason=(
                        "The provider returned no rows for this market. "
                        f"{absence} Check per-bookmaker coverage "
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
                        + (
                            f" Of the {len(missing)} missing game(s), "
                            f"{len(failed_missing)} "
                            f"({name_games(failed_missing)}) are missing "
                            "because the per-event request failed, not "
                            "because no book priced them."
                            if failed_missing
                            else ""
                        )
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
