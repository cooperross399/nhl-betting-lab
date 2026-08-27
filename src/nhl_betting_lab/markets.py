"""Every market this lab knows how to name, price, and settle.

One table, in one place. The provider adapter, the eligibility gate, the
models, the card and the backtest all read from here, so a market cannot mean
one thing in the fetch and another in the report.

The lab's priority order is in the `is_prop` flag: props are the product and
team markets exist so an edge anywhere can be found.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    """One market: what it is called here, at the provider, and how it settles."""

    #: The name used everywhere inside this repository.
    key: str
    #: The Odds API market key that supplies it.
    provider_key: str
    #: Human label for reports.
    label: str
    #: True for a player prop, False for a team market.
    is_prop: bool
    #: The player-game-log column a settled result is read from. Empty for
    #: team markets, which settle from `team_games.csv` instead.
    settles_on: str = ""
    #: The selections a complete market must quote. A prop quotes one side at
    #: most books, which is why props list only `over`; a market that is
    #: genuinely two-sided lists both, and an incomplete one is excluded
    #: rather than half-used.
    selections: tuple[str, ...] = ("over",)
    #: Whether the provider serves it from the per-event endpoint (costing one
    #: credit per market per event) rather than the bulk endpoint.
    per_event: bool = False


#: Player props. These are the point of the lab.
PROP_MARKETS: tuple[Market, ...] = (
    Market(
        key="shots_on_goal",
        provider_key="player_shots_on_goal",
        label="Shots on goal",
        is_prop=True,
        settles_on="shots_on_goal",
        per_event=True,
    ),
    Market(
        key="points",
        provider_key="player_points",
        label="Points",
        is_prop=True,
        settles_on="points",
        per_event=True,
    ),
    Market(
        key="goals",
        provider_key="player_goals",
        label="Goals (incl. anytime scorer)",
        is_prop=True,
        settles_on="goals",
        per_event=True,
    ),
    Market(
        key="assists",
        provider_key="player_assists",
        label="Assists",
        is_prop=True,
        settles_on="assists",
        per_event=True,
    ),
    Market(
        key="goalie_saves",
        provider_key="player_total_saves",
        label="Goalie saves",
        is_prop=True,
        settles_on="saves",
        per_event=True,
    ),
    Market(
        key="blocked_shots",
        provider_key="player_blocked_shots",
        label="Blocked shots",
        is_prop=True,
        settles_on="blocked_shots",
        per_event=True,
    ),
    # Added after a market probe showed the provider serves it and this lab
    # had simply never asked. The boxscore carries hits, so it settles like
    # any other count.
    Market(
        key="hits",
        provider_key="player_hits",
        label="Hits",
        is_prop=True,
        settles_on="hits",
        per_event=True,
    ),
)

#: Team markets. Priced and modelled so an edge anywhere can be found.
TEAM_MARKETS: tuple[Market, ...] = (
    Market(
        key="moneyline",
        provider_key="h2h",
        label="Moneyline",
        is_prop=False,
        selections=("home", "away"),
    ),
    Market(
        key="puck_line",
        provider_key="spreads",
        label="Puck line (-1.5 / +1.5)",
        is_prop=False,
        selections=("home", "away"),
    ),
    Market(
        key="total_goals",
        provider_key="totals",
        label="Total goals",
        is_prop=False,
        selections=("over", "under"),
    ),
    # The result after sixty minutes, with the draw as a real outcome. The
    # team model already computes this distribution exactly — it is the
    # quantity the moneyline is derived *from* — so pricing it needs no new
    # model, and it settles from the regulation flag the boxscore supplies.
    Market(
        key="regulation_3_way",
        provider_key="h2h_3_way",
        label="Regulation result (3-way)",
        is_prop=False,
        selections=("home", "draw", "away"),
        # Served on the per-event endpoint only (probed 2026-08-26: four
        # books answered there; the bulk endpoint refuses it). Without this
        # flag the market was fully wired and never fetched — dead code on
        # every production path, with the operating docs promising evidence
        # that could never accumulate.
        per_event=True,
    ),
)

ALL_MARKETS: tuple[Market, ...] = PROP_MARKETS + TEAM_MARKETS

MARKETS_BY_KEY: dict[str, Market] = {market.key: market for market in ALL_MARKETS}

#: Several provider keys can feed one project market and vice versa, so this
#: maps the provider's vocabulary to ours rather than assuming a 1:1 name.
PROVIDER_KEY_TO_MARKET: dict[str, str] = {
    market.provider_key: market.key for market in ALL_MARKETS
}

#: Alternate-line markets carry the same project market on a different line.
#: They are listed separately because the bulk market and the alternate ladder
#: are different endpoints with different coverage — the EPL lab excluded a
#: market for a whole season because only the bulk one was checked.
ALTERNATE_PROVIDER_KEYS: dict[str, str] = {
    "alternate_spreads": "puck_line",
    "alternate_totals": "total_goals",
}

#: Where the provider's headline NHL total sits almost every night. Used for
#: reporting only — the line a price is judged against always comes from the
#: response, never from here.
#:
#: This market key is `total_goals` and not `total_5_5`. It carries whatever
#: line the response holds, including the 6.5 and 7.5 rungs of the alternate
#: ladder, and a key naming a line it does not always hold is the same lie as
#: a column called `power_play_points` holding a count of goals. Renamed
#: before any approval receipt could cite the old name.
TYPICAL_TOTAL_LINE = 5.5

#: Anytime goal scorer is goals over 0.5. There is one name for this in the
#: repository, not two, so the two cannot disagree on the same card.
ANYTIME_SCORER_LINE = 0.5


def market_for(key: str) -> Market:
    """Look up a market by its project key, or say which keys exist."""
    text = str(key or "").strip().lower()
    try:
        return MARKETS_BY_KEY[text]
    except KeyError as exc:
        raise KeyError(
            f"Unknown market {key!r}. Known markets: "
            f"{sorted(MARKETS_BY_KEY)}"
        ) from exc


def market_for_provider_key(provider_key: str) -> Market | None:
    """The project market a provider key supplies, or None if we ignore it.

    Returning None rather than raising is deliberate: a provider response
    carries markets this lab does not price, and every one of them being an
    error would make an ordinary response unparseable.
    """
    text = str(provider_key or "").strip().lower()
    project_key = PROVIDER_KEY_TO_MARKET.get(text) or ALTERNATE_PROVIDER_KEYS.get(text)
    return MARKETS_BY_KEY.get(project_key) if project_key else None


def prop_market_keys() -> tuple[str, ...]:
    return tuple(market.key for market in PROP_MARKETS)


def team_market_keys() -> tuple[str, ...]:
    return tuple(market.key for market in TEAM_MARKETS)


def per_event_provider_keys() -> tuple[str, ...]:
    """Provider market keys that cost one credit per market per event."""
    return tuple(market.provider_key for market in ALL_MARKETS if market.per_event)
