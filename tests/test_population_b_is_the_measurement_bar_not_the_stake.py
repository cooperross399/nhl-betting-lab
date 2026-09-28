"""Population B and the "Bets" streams were called the card's bets, and are not.

The forward report's population B (`population_clears_edge_bar`) and its
per-market Bets column were described on the page as "the opinions the card
would have bet", and `closing_lines.build_clv_report` said its Bets view
"cleared the staking bar: it measures what the bankroll would actually have
done". Both filters are `edge >= MIN_PROP_EDGE` (6%) for a prop and
`edge >= MIN_EDGE` (3.5%) for a team market — the backtest's shipped bar, a
MEASUREMENT bar. The card stakes something much narrower: only best bets
(12% prop, 9% team; a 6-12% prop edge is a lean, recorded and not staked),
nothing past the juice limit or the longest price, nothing in a
stake-excluded market (`points`) and nothing in a hard-gated one
(`goalie_saves`).

Found by sweep 3 (A1). Five settled opinions — a lean, a stake-excluded
`points` rung, a hard-gated `goalie_saves` rung, a +800 price and a -250
price — are all five in population B and all five in the Bets column, while
the card stakes none of them.

This is a WORDING fix. No number, population, bar or computation moves: which
population the 2027-04-25 decision reads is Cooper's decision, and the freeze
in docs/when_this_ends.md forbids changing what is measured. These tests pin
that the page, the definitions and the docstrings say what B is — opinions
clearing the measurement bar — and name how it differs from what the card
stakes, and that the counts themselves are unchanged (B still counts every
one of the five).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import (
    MAX_DEFAULT_JUICE,
    MAX_DEFAULT_PRICE,
    MIN_EDGE,
    MIN_PROP_EDGE,
)
from nhl_betting_lab.models.value import american_to_implied, profit_on_win
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    BEST_BET_EDGE,
    BEST_BET_PROP_EDGE,
    BEST_BETS_SECTION,
    HARD_GATED_MARKETS,
    STAKE_EXCLUDED_MARKETS,
    build_candidates,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)
CLEARS = "population_clears_edge_bar"
#: The claims this fix removes. Lower-cased, so a re-capitalised copy of
#: either still fails.
OLD_CLAIMS = (
    "would have bet",
    "bankroll would actually have done",
    "what the bankroll would",
)
NOT_STAKED = "not the card's staked bets"

#: (market, player, selection, line, American odds, model probability).
#: Every one clears the measurement bar; the card stakes none of them.
UNSTAKED = (
    ("shots_on_goal", "David Pastrnak", "over", 2.5, 100.0, 0.58),   # +8%: a lean
    ("points", "David Pastrnak", "over", 0.5, 100.0, 0.75),          # stake-excluded
    ("goalie_saves", "Jeremy Swayman", "over", 27.5, 100.0, 0.70),   # hard-gated
    ("shots_on_goal", "Brad Marchand", "over", 4.5, 800.0, 0.30),    # past the max price
    ("shots_on_goal", "Charlie McAvoy", "under", 2.5, -250.0, 0.85), # heavy juice
)


def _pct(value: float) -> str:
    return f"{value * 100:g}%"


def _ledger() -> pd.DataFrame:
    rows = []
    for market, player, selection, line, odds, p in UNSTAKED:
        rows.append({
            "snapshot_date": "2026-10-09",
            "commence_time": "2026-10-09T23:00:00Z",
            "home_team": "Boston Bruins", "away_team": "New York Rangers",
            "market": market, "player": player, "selection": selection,
            "line": line, "american_odds": odds, "book": "DK",
            "model_probability": p, "edge": p - american_to_implied(odds),
            "verdicts_in_force": "v", "settled_at": "2026-10-11T12:00:00Z",
            "outcome": "won", "actual": 4.0,
            "profit_units": profit_on_win(odds),
        })
    return pd.DataFrame(rows, columns=list(fe.LEDGER_COLUMNS))


def _page() -> tuple[dict, str]:
    payload = fe.build_forward_report(_ledger(), now=NOW)
    return payload, fe.render_forward_report(payload)


def _section(rendered: str, head: str) -> str:
    assert head in rendered, f"the page has no {head!r} section"
    return rendered.split(head, 1)[1].split("\n## ", 1)[0]


def _names_the_difference(text: str) -> None:
    """The text says B is the measurement bar, not the stake, and names the
    card's price gates (the best-bet bar, the juice and price limits, the
    stake-excluded and hard-gated markets) and the non-price reasons B holds
    opinions the card never staked (one stake per outcome, market
    eligibility, a blocked card, the puck-drop guard)."""
    assert "measurement bar" in text
    assert NOT_STAKED in text
    for bar in (MIN_PROP_EDGE, MIN_EDGE, BEST_BET_PROP_EDGE, BEST_BET_EDGE):
        assert _pct(bar) in text, f"{_pct(bar)} is not named"
    assert str(MAX_DEFAULT_JUICE) in text
    assert f"+{MAX_DEFAULT_PRICE}" in text
    for market in (*STAKE_EXCLUDED_MARKETS, *HARD_GATED_MARKETS):
        assert f"`{market}`" in text, f"{market} is not named"
    # The reasons that are not about the price. The snapshot is frozen from
    # the unfiltered prices before the card is built, so B holds every rung
    # of a ladder (only one takes the outcome's stake), markets the card
    # could not use that day, the opinions of a blocked card, and rows whose
    # stake the puck-drop guard pulled.
    for reason in (
        "one stake per outcome",
        "not allowlisted",
        "incomplete",
        "blocked",
        "puck-drop guard",
        "frozen from the unfiltered prices before the card is built",
    ):
        assert reason in text, f"{reason!r} is not named"


def test_every_unstaked_opinion_is_still_in_population_b() -> None:
    """The counts do not move: this is a wording fix. All five clear the
    measurement bar, so B and the Bets column count all five."""
    payload, _ = _page()
    assert payload["registered_statistic"][CLEARS]["settled_opinions"] == 5
    assert sum(entry["bets"] for entry in payload["markets"].values()) == 5


def test_the_page_no_longer_calls_b_the_cards_bets() -> None:
    _, rendered = _page()
    lowered = rendered.lower()
    for claim in OLD_CLAIMS:
        assert claim not in lowered, f"the page still says {claim!r}"


def test_the_registered_section_names_the_measurement_bar() -> None:
    _, rendered = _page()
    _names_the_difference(_section(rendered, "## Registered decision statistic"))


def test_the_bets_column_names_the_measurement_bar() -> None:
    _, rendered = _page()
    _names_the_difference(
        _section(rendered, "## Accumulated so far, at the shipped edge bars")
    )


def test_b_is_defined_as_the_measurement_bar() -> None:
    definition = fe.REGISTERED_POPULATIONS[CLEARS]
    assert "measurement bar" in definition
    assert NOT_STAKED in definition
    assert _pct(MIN_PROP_EDGE) in definition and _pct(MIN_EDGE) in definition


def test_the_clv_page_says_what_its_bets_are() -> None:
    opinions = pd.DataFrame([{
        "snapshot_date": "2026-10-08", "commence_time": "2026-10-08T23:00:00Z",
        "home_team": "Home", "away_team": "Away", "market": "shots_on_goal",
        "player": "Auston Matthews", "selection": "over", "line": 3.5,
        "american_odds": 110.0, "book": "Best", "edge": 0.08,
    }])
    captures = pd.DataFrame([
        {**opinions.iloc[0].to_dict(), "captured_at": "2026-10-08T22:30:00+00:00",
         "american_odds": price, "selection": side, "book": "Close"}
        for side, price in (("over", 100.0), ("under", -120.0))
    ])
    report = cl.build_clv_report(opinions, captures)
    assert report["overall"]["bets"]["bets"] == 1, "a lean is still a bet here"
    rendered = cl.render_clv(report, generated="t")
    lowered = rendered.lower()
    for claim in OLD_CLAIMS:
        assert claim not in lowered, f"the CLV page still says {claim!r}"
    _names_the_difference(_section(rendered, "## How to read this"))


def test_no_source_or_docstring_repeats_the_claim() -> None:
    """Comments and docstrings are where the next reader learns what B is,
    so the claim is held out of both source files, not just the pages."""
    for module in (fe, cl):
        text = Path(module.__file__).read_text(encoding="utf-8").lower()
        for claim in OLD_CLAIMS:
            assert claim not in text, (
                f"{Path(module.__file__).name} still says {claim!r}"
            )


def _staked_at(price: float, probability: float) -> bool:
    """Whether the card stakes one `shots_on_goal` over at this price, with
    an edge well past the best-bet bar so only the price limits can refuse
    it."""
    prices = pd.DataFrame([{
        "date": "2026-10-09", "commence_time": "2026-10-09T23:00:00Z",
        "home_team": "Boston Bruins", "away_team": "New York Rangers",
        "market": "shots_on_goal", "player": "David Pastrnak",
        "selection": "over", "line": 2.5, "american_odds": price,
        "book": "DK",
    }])
    (row,) = prices.to_dict("records")
    key = selection_key(SimpleNamespace(**row), market="shots_on_goal",
                        selection="over", line=2.5)
    edge = probability - american_to_implied(price)
    assert edge >= BEST_BET_PROP_EDGE, "the fixture must clear the best-bet bar"
    selections, passes = build_candidates(prices, {key: probability})
    staked = [c for c in selections
              if c.section == BEST_BETS_SECTION and c.suggested_units > 0]
    assert len(staked) + len(passes) == 1
    return bool(staked)


def test_the_price_limits_are_stated_at_their_real_boundaries() -> None:
    """-160 is staked and -161 is not; +600 is staked and +601 is not. The
    note says "shorter than -160" and "longer than +600" — so a note saying
    "at or shorter than -160" would call a staked price unstaked."""
    assert _staked_at(float(MAX_DEFAULT_JUICE), 0.85)
    assert not _staked_at(float(MAX_DEFAULT_JUICE - 1), 0.85)
    assert _staked_at(float(MAX_DEFAULT_PRICE), 0.35)
    assert not _staked_at(float(MAX_DEFAULT_PRICE + 1), 0.35)

    note = cl.measurement_bar_note()
    assert (
        f"nothing priced shorter than {MAX_DEFAULT_JUICE} or longer than "
        f"+{MAX_DEFAULT_PRICE}"
    ) in note
    assert "at or " not in note and "or more" not in note


def test_a_written_off_page_points_at_no_bets_column() -> None:
    """With nothing settled the page shows no Bets column, and B's
    definition must not send the reader to one "above"."""
    ledger = _ledger().assign(outcome="void", profit_units=0.0)
    rendered = fe.render_forward_report(
        fe.build_forward_report(ledger, now=NOW)
    )
    assert "| Bets |" not in rendered
    assert "Bets column above" not in rendered
    assert "## Registered decision statistic" in rendered
