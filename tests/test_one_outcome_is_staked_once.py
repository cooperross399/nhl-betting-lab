"""One player's points ladder was three staked bets on one outcome.

`selection_key` carries the line, and `markets.ALTERNATE_PROVIDER_KEYS` maps
every alternate ladder back onto the project market it is a ladder *of*. So
`points over 0.5`, `over 1.5` and `over 2.5` on one player arrived as three
keys, got three model opinions, cleared the bar three times, and
`build_candidates` staked all three — 0.25 or 0.5 units each, on an outcome
that settles once. Nothing on the staking path counted them: there is no
per-player, per-game, per-slate or bankroll cap anywhere on it.

It is the shape `selection_key`'s own docstring already records and already
fixed once — two book spellings of one player, "the card listed one outcome
twice" — and the reason anytime-scorer is collapsed into `goals` over 0.5
rather than carried as a second market.

What this module holds the fix to, and holds it *narrow* to:

* a same-side ladder collapses to one stake, the highest-edge rung;
* `home_over` and `away_over` on one game's `team_total` do not collapse into
  each other, and neither do the two sides of a puck line, a total, or a
  moneyline — the side rides in `selection`, which stays in the grouping;
* `over` is never collapsed against its own `under`; that is a contradiction
  for `ladder_coherence.py`, not a duplicate for this;
* two players in one game, and one player in two games, each keep their own
  stakes;
* a demoted rung is still on the card as a lean, at zero units, naming the
  rung that took the stake — it is demoted, never dropped;
* the forward snapshot still freezes every priced rung, because it is written
  off the unfiltered priced frame before the card is built.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.forward_evidence import write_snapshot
from nhl_betting_lab.market_eligibility import (
    ELIGIBLE,
    EligibilityReport,
    MarketEligibility,
)
from nhl_betting_lab.reports import gameday_card as card_module
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    LEANS_SECTION,
    build_candidates,
    build_card,
)


def outcome_group(key: tuple) -> tuple:
    """The production grouping, reached through the module at call time.

    A `from ... import outcome_group` at the top would make every test in
    this file fail at IMPORT against a tree without the fix, which says
    nothing about behaviour. Looked up here, the behaviour tests below run
    against such a tree and fail on what the card actually staked.
    """
    return card_module.outcome_group(key)


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _row(
    *,
    market: str = "points",
    player: str = "Auston Matthews",
    selection: str = "over",
    line: float | None = 0.5,
    price: float = 150,
    home: str = "TOR",
    away: str = "BOS",
    hours: float = 4,
    book: str = "DraftKings",
) -> dict:
    """One staged price row, in the shape the provider stages them."""
    return {
        "date": "2026-10-08",
        "commence_time": _at(hours),
        "home_team": home,
        "away_team": away,
        "market": market,
        "player": player,
        "selection": selection,
        "line": line,
        "american_odds": price,
        "book": book,
    }


def _key(row: dict) -> tuple:
    """Built by the real key function, never a hand copy of it.

    A hand-built fixture key is how the production drift this repository has
    already shipped went unseen: the tests agreed with themselves while the
    two copies in production disagreed with each other.
    """
    return selection_key(
        SimpleNamespace(**row),
        market=row["market"],
        selection=row["selection"],
        line=row["line"],
    )


def _eligibility(markets: list[str], *, games: int = 1) -> EligibilityReport:
    return EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=games,
        markets=[
            MarketEligibility(
                market=market, state=ELIGIBLE, reason="Allowlisted and complete."
            )
            for market in markets
        ],
    )


def _staked(rows: list[dict], probabilities: dict) -> list:
    selections, _passes = build_candidates(pd.DataFrame(rows), probabilities)
    return [item for item in selections if item.section == BEST_BETS_SECTION]


def _leans(rows: list[dict], probabilities: dict) -> list:
    selections, _passes = build_candidates(pd.DataFrame(rows), probabilities)
    return [item for item in selections if item.section == LEANS_SECTION]


#: A three-rung points ladder on one player, every rung over the best-bet
#: prop bar (0.12) at a price of +150 (implied 40%).
LADDER = [
    (_row(line=0.5), 0.60),   # edge +20.0%
    (_row(line=1.5), 0.56),   # edge +16.0%
    (_row(line=2.5), 0.54),   # edge +14.0%
]


# -- (a) a same-side ladder collapses to one stake ----------------------


def test_a_three_rung_ladder_on_one_outcome_is_one_stake() -> None:
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    staked = _staked(rows, probabilities)

    assert len(staked) == 1, [(c.line, c.edge) for c in staked]


def test_the_rung_that_keeps_the_stake_is_the_highest_edge_one() -> None:
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    selections, _passes = build_candidates(pd.DataFrame(rows), probabilities)
    (kept,) = [item for item in selections if item.section == BEST_BETS_SECTION]

    assert kept.line == 0.5
    assert kept.edge == max(item.edge for item in selections)


def test_the_ladder_no_longer_stakes_one_outcome_three_times_over() -> None:
    """The defect in units, which is what a bankroll actually feels.

    Three rungs at tier A/B were 0.5 + 0.25 + 0.25 = 1.0 unit on one outcome
    that settles once. One rung is 0.5.
    """
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    card = build_card(
        pd.DataFrame(rows),
        probabilities,
        eligibility=_eligibility(["points"]),
        now=NOW,
    )

    assert card.total_units == 0.5


# -- (b) the side rides in `selection`, so sides never collapse ---------


def test_home_over_and_away_over_on_one_team_total_are_two_stakes() -> None:
    """Both teams arrive under one provider key; the side is in `selection`.

    Collapsing these would be the fix eating a real second position: the home
    club going over 3.5 and the away club going over 3.5 are two outcomes
    that settle independently.
    """
    rows = [
        _row(market="team_total", player="", selection="home_over", line=3.5),
        _row(market="team_total", player="", selection="away_over", line=3.5),
    ]
    probabilities = {_key(row): 0.58 for row in rows}  # edge +18.0%

    staked = _staked(rows, probabilities)

    assert {item.selection for item in staked} == {"home_over", "away_over"}


def test_a_team_total_ladder_collapses_within_one_side_only() -> None:
    rows = [
        _row(market="team_total", player="", selection="home_over", line=3.5),
        _row(market="team_total", player="", selection="home_over", line=4.5),
        _row(market="team_total", player="", selection="away_over", line=3.5),
    ]
    probabilities = {
        _key(rows[0]): 0.58,  # edge +18.0%, the home rung that keeps it
        _key(rows[1]): 0.55,  # edge +15.0%
        _key(rows[2]): 0.58,
    }

    staked = _staked(rows, probabilities)

    assert sorted((item.selection, item.line) for item in staked) == [
        ("away_over", 3.5),
        ("home_over", 3.5),
    ]


def test_the_two_sides_of_a_puck_line_stay_two_outcomes() -> None:
    rows = [
        _row(market="puck_line", player="", selection="home", line=-1.5),
        _row(market="puck_line", player="", selection="away", line=1.5),
    ]
    probabilities = {_key(row): 0.58 for row in rows}

    assert len(_staked(rows, probabilities)) == 2


def test_an_over_is_never_collapsed_against_its_own_under() -> None:
    """A contradiction, not a duplication — `ladder_coherence.py` owns it.

    Collapsing these would silently delete one half of a disagreement the
    coherence tool exists to surface.
    """
    rows = [
        _row(line=1.5, selection="over"),
        _row(line=1.5, selection="under"),
    ]
    probabilities = {_key(row): 0.58 for row in rows}

    staked = _staked(rows, probabilities)

    assert {item.selection for item in staked} == {"over", "under"}
    assert outcome_group(_key(rows[0])) != outcome_group(_key(rows[1]))


def test_a_moneyline_keeps_both_sides_although_neither_carries_a_line() -> None:
    rows = [
        _row(market="moneyline", player="", selection="home", line=None),
        _row(market="moneyline", player="", selection="away", line=None),
    ]
    probabilities = {_key(row): 0.58 for row in rows}

    assert len(_staked(rows, probabilities)) == 2


# -- (c) and (d) the grouping is per player and per game ----------------


def test_two_players_in_one_game_each_keep_a_stake() -> None:
    rows = [
        _row(player="Auston Matthews", line=0.5),
        _row(player="William Nylander", line=0.5),
    ]
    probabilities = {_key(row): 0.60 for row in rows}

    staked = _staked(rows, probabilities)

    assert {item.player for item in staked} == {
        "Auston Matthews",
        "William Nylander",
    }


def test_two_players_in_one_game_each_keep_one_stake_off_their_own_ladder() -> None:
    rows = [
        _row(player="Auston Matthews", line=0.5),
        _row(player="Auston Matthews", line=1.5),
        _row(player="William Nylander", line=0.5),
        _row(player="William Nylander", line=1.5),
    ]
    probabilities = {
        _key(rows[0]): 0.60,
        _key(rows[1]): 0.56,
        _key(rows[2]): 0.60,
        _key(rows[3]): 0.56,
    }

    staked = _staked(rows, probabilities)

    assert sorted((item.player, item.line) for item in staked) == [
        ("Auston Matthews", 0.5),
        ("William Nylander", 0.5),
    ]


def test_one_player_in_two_games_keeps_a_stake_in_each() -> None:
    """Two fixtures are two bets, and the game date is in the grouping.

    The same clubs meeting twice in one staged file is the exact shape that
    already collapsed once, before the game date joined `selection_key`.
    """
    rows = [
        _row(line=0.5, home="TOR", away="BOS", hours=4),
        _row(line=0.5, home="TOR", away="BOS", hours=52),
    ]
    probabilities = {_key(row): 0.60 for row in rows}

    staked = _staked(rows, probabilities)

    assert len(staked) == 2
    assert len({item.commence_time for item in staked}) == 2


def test_one_player_against_two_opponents_keeps_a_stake_in_each() -> None:
    rows = [
        _row(line=0.5, home="TOR", away="BOS"),
        _row(line=0.5, home="MTL", away="TOR"),
    ]
    probabilities = {_key(row): 0.60 for row in rows}

    assert len(_staked(rows, probabilities)) == 2


# -- (e) a demoted rung is demoted, never dropped -----------------------


def test_every_demoted_rung_is_still_on_the_card_as_a_lean() -> None:
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    card = build_card(
        pd.DataFrame(rows),
        probabilities,
        eligibility=_eligibility(["points"]),
        now=NOW,
    )

    assert len(card.best_bets) == 1
    assert sorted(row["line"] for row in card.leans) == [1.5, 2.5]
    assert len(card.best_bets) + len(card.leans) == len(rows)


def test_a_demoted_rung_carries_zero_units_and_names_the_rung_that_kept_it() -> None:
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    card = build_card(
        pd.DataFrame(rows),
        probabilities,
        eligibility=_eligibility(["points"]),
        now=NOW,
    )

    # Asserted before the loop, so a card that demoted nothing cannot pass
    # this by having nothing to iterate over.
    assert len(card.leans) == 2
    for lean in card.leans:
        assert lean["suggested_units"] == 0.0
        assert "One stake per outcome" in lean["demotion_reason"]
        assert "Auston Matthews over 0.5" in lean["demotion_reason"]


def test_a_lean_that_was_always_a_lean_carries_no_demotion_reason() -> None:
    """The reason means one thing, so it is absent where nothing was demoted."""
    rows = [_row(line=0.5, price=100)]  # implied 50%
    probabilities = {_key(rows[0]): 0.57}  # edge +7%, under the best-bet bar

    card = build_card(
        pd.DataFrame(rows),
        probabilities,
        eligibility=_eligibility(["points"]),
        now=NOW,
    )

    assert len(card.leans) == 1
    assert card.leans[0]["demotion_reason"] == ""


def test_the_rendered_card_says_which_rung_took_the_stake() -> None:
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    card = build_card(
        pd.DataFrame(rows),
        probabilities,
        eligibility=_eligibility(["points"]),
        now=NOW,
    )
    rendered = card_module.render_card(card)

    assert "One stake per outcome" in rendered
    # Both demoted rungs are still visible in the leans table itself.
    assert "Auston Matthews over 1.5" in rendered
    assert "Auston Matthews over 2.5" in rendered


def test_the_card_states_that_this_is_not_a_per_game_or_bankroll_cap() -> None:
    card = build_card(
        pd.DataFrame([row for row, _ in LADDER]),
        {_key(row): p for row, p in LADDER},
        eligibility=_eligibility(["points"]),
        now=NOW,
    )

    assert any("bankroll cap" in note for note in card.notes)


def test_no_priced_opinion_is_lost_from_the_candidates() -> None:
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    selections, passes = build_candidates(pd.DataFrame(rows), probabilities)

    assert len(selections) + len(passes) == len(rows)
    assert sorted(item.line for item in selections) == [0.5, 1.5, 2.5]


def test_every_rung_still_freezes_into_the_forward_snapshot(tmp_path: Path) -> None:
    """The snapshot is written off the unfiltered priced frame, before the card.

    This fix reduces stakes. It must not reduce what is measured: all three
    rungs are opinions the model held, and the ledger settles opinions.
    """
    rows = [row for row, _ in LADDER]
    probabilities = {_key(row): p for row, p in LADDER}

    written = write_snapshot(
        pd.DataFrame(rows),
        probabilities,
        key_for=selection_key,
        verdicts_line="no verdict ships",
        snapshot_date="2026-10-08",
        now=NOW,
        archive_dir=tmp_path,
    )

    assert written is not None
    frozen = pd.read_csv(written)
    assert sorted(frozen["line"].tolist()) == [0.5, 1.5, 2.5]


# -- (f) a tie resolves the same way twice ------------------------------


def test_a_tie_in_edge_and_price_keeps_the_lower_rung_whatever_the_row_order() -> None:
    """Identical edges are real: the model and the ladder are both coarse.

    A card that staked whichever rung `dict` happened to yield first would
    change its selections between two runs over identical inputs, which reads
    as a live line move and is not one.
    """
    low = _row(line=1.5, price=100)
    high = _row(line=2.5, price=100)
    probabilities = {_key(low): 0.75, _key(high): 0.75}  # edge +25% exactly

    forwards = _staked([low, high], probabilities)
    backwards = _staked([high, low], probabilities)

    assert [item.line for item in forwards] == [1.5]
    assert [item.line for item in backwards] == [1.5]


def test_a_tie_in_edge_is_broken_by_the_better_price() -> None:
    """+300 and +100 at one edge are not one bet twice over at one price."""
    short = _row(line=1.5, price=100)   # implied 50%, model 75% -> +25%
    long = _row(line=2.5, price=300)    # implied 25%, model 50% -> +25%
    probabilities = {_key(short): 0.75, _key(long): 0.50}

    forwards = _staked([short, long], probabilities)
    backwards = _staked([long, short], probabilities)

    assert [item.american_odds for item in forwards] == [300]
    assert [item.american_odds for item in backwards] == [300]


def test_the_demoted_rung_of_a_tie_is_the_same_one_whatever_the_row_order() -> None:
    low = _row(line=1.5, price=100)
    high = _row(line=2.5, price=100)
    probabilities = {_key(low): 0.75, _key(high): 0.75}

    assert [item.line for item in _leans([low, high], probabilities)] == [2.5]
    assert [item.line for item in _leans([high, low], probabilities)] == [2.5]


# -- the grouping itself ------------------------------------------------


def test_the_group_is_the_selection_key_with_the_line_taken_out() -> None:
    """Stated against the real key, so the two cannot drift apart."""
    key = _key(_row(line=1.5))
    other_line = _key(_row(line=2.5))

    assert outcome_group(key) == outcome_group(other_line)
    assert key != other_line
    assert len(outcome_group(key)) == len(key) - 1


def test_the_group_keeps_the_market_the_player_the_game_and_the_side() -> None:
    base = _row(line=1.5)
    group = outcome_group(_key(base))

    assert group != outcome_group(_key(_row(line=1.5, market="goals")))
    assert group != outcome_group(_key(_row(line=1.5, player="Mitch Marner")))
    assert group != outcome_group(_key(_row(line=1.5, away="MTL")))
    assert group != outcome_group(_key(_row(line=1.5, selection="under")))
    assert group != outcome_group(_key(_row(line=1.5, hours=52)))
