from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.market_eligibility import (
    ELIGIBLE,
    EligibilityReport,
    MarketEligibility,
    NOT_ALLOWLISTED,
)
from nhl_betting_lab.puck_drop import QUARANTINE_SECTION
from nhl_betting_lab.reports import gameday_card as card_module


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _price_row(
    *,
    market: str = "shots_on_goal",
    player: str = "Auston Matthews",
    selection: str = "over",
    line: float | None = 3.5,
    price: float = 120,
    hours: float = 4,
    home: str = "TOR",
    away: str = "BOS",
    book: str = "DraftKings",
) -> dict:
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


def _prices(rows: list[dict] | None = None) -> pd.DataFrame:
    return pd.DataFrame(rows if rows is not None else [_price_row()])


def _key(row: dict) -> tuple:
    """Built by the real key function, not a hand copy of it.

    A hand-built fixture key is how the production drift went unseen: the
    tests agreed with themselves while the two production copies disagreed
    with each other."""
    from types import SimpleNamespace

    from nhl_betting_lab.reports.card_pricing import selection_key

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


def _blocked_eligibility(markets: list[str]) -> EligibilityReport:
    return EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=1,
        markets=[
            MarketEligibility(
                market=market,
                state=NOT_ALLOWLISTED,
                reason="No reviewed human approval covers this market.",
            )
            for market in markets
        ],
    )


# -- the default state -------------------------------------------------


def test_with_nothing_allowlisted_there_is_no_card_and_no_selections() -> None:
    rows = [_price_row()]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.75},
        eligibility=_blocked_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.card_generated is False
    assert card.best_bets == []
    assert card.leans == []
    assert card.passes == []


def test_a_blocked_card_explains_itself_rather_than_inventing_content() -> None:
    card = card_module.build_card(
        _prices(),
        {},
        eligibility=_blocked_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    rendered = card_module.render_card(card)

    assert "No best bet, lean, pass, or stake was produced" in rendered
    assert "worse than no card" in rendered


def test_a_blocked_card_still_lists_every_excluded_market_with_a_reason() -> None:
    card = card_module.build_card(
        _prices(),
        {},
        eligibility=_blocked_eligibility(["shots_on_goal", "points"]),
        now=NOW,
    )

    assert set(card.excluded_markets) == {"shots_on_goal", "points"}
    assert all(card.excluded_markets.values())


def test_an_excluded_market_is_never_described_as_a_pass() -> None:
    card = card_module.build_card(
        _prices(),
        {},
        eligibility=_blocked_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    rendered = card_module.render_card(card)

    assert "not** a pass, an avoid, or a no-value call" in rendered
    assert card.safety["excluded_market_shown_as_a_pass"] is False


# -- selection ---------------------------------------------------------


def test_a_clear_edge_becomes_a_best_bet_with_a_stake() -> None:
    rows = [_price_row(price=150)]  # implied 40%

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.card_generated is True
    assert len(card.best_bets) == 1
    assert card.best_bets[0]["suggested_units"] > 0
    assert card.total_units > 0


def test_a_small_edge_becomes_a_lean_and_is_not_staked() -> None:
    """The smallest edges are mostly estimation error; in EPL they lost."""
    rows = [_price_row(price=100)]  # implied 50%

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.57},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert len(card.leans) == 1
    assert card.leans[0].get("suggested_units", 0.0) == 0.0
    assert card.total_units == 0.0


def test_a_row_the_model_agrees_with_becomes_a_pass() -> None:
    rows = [_price_row(price=100)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.50},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.passes and card.passes[0]["market"] == "shots_on_goal"
    assert card.best_bets == []


def test_a_row_with_no_model_opinion_appears_nowhere() -> None:
    """Not a pass: a pass is a judgement about something that was modelled."""
    card = card_module.build_card(
        _prices(),
        {},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert card.leans == []
    assert card.passes == []


def test_heavy_juice_is_passed_rather_than_selected() -> None:
    rows = [_price_row(price=-200)]  # implied 66.7%, worse than -160

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.90},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert card.passes and card.passes[0]["american_odds"] == -200


def test_a_longshot_beyond_the_price_cap_is_passed() -> None:
    """Independent-count tails and favourite-longshot bias compound."""
    rows = [_price_row(price=900)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.40},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert card.leans == []


def test_a_prop_must_clear_a_higher_bar_than_a_team_market() -> None:
    prop = _price_row(market="shots_on_goal", price=100)
    team = _price_row(market="moneyline", player="", line=None, price=100)
    prices = pd.DataFrame([prop, team])
    edge_of_four_points = 0.54

    card = card_module.build_card(
        prices,
        {_key(prop): edge_of_four_points, _key(team): edge_of_four_points},
        eligibility=_eligibility(["shots_on_goal", "moneyline"]),
        now=NOW,
    )
    selected = {row["market"] for row in card.best_bets + card.leans}

    assert "moneyline" in selected
    assert "shots_on_goal" not in selected


def test_the_best_available_price_is_used_and_the_book_named() -> None:
    rows = [
        _price_row(price=110, book="DraftKings"),
        _price_row(price=135, book="FanDuel"),
    ]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets[0]["american_odds"] == 135
    assert card.best_bets[0]["book"] == "FanDuel"


# -- hard gates --------------------------------------------------------


def test_goalie_saves_cannot_produce_a_selection_even_when_allowlisted() -> None:
    """Starters are confirmed after the card is built; this lab has no feed."""
    rows = [_price_row(market="goalie_saves", player="Joseph Woll", line=27.5)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.80},
        eligibility=_eligibility(["goalie_saves"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert "goalie_saves" in card.excluded_markets


def test_the_goalie_gate_says_it_is_not_a_no_value_judgement() -> None:
    card = card_module.build_card(
        _prices([_price_row(market="goalie_saves", line=27.5)]),
        {},
        eligibility=_eligibility(["goalie_saves"]),
        now=NOW,
    )

    assert "not a judgement that the market has no value" in (
        card.excluded_markets["goalie_saves"]
    )
    assert "confirmed_starter" in card.excluded_markets["goalie_saves"]


# -- the puck-drop guard -----------------------------------------------


def test_a_started_game_is_quarantined_and_its_stake_removed() -> None:
    rows = [_price_row(price=150, hours=-1)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert len(card.quarantined) == 1
    assert card.stake_removed_by_guard > 0
    assert card.total_units == 0.0


def test_an_unconfirmable_start_is_quarantined_too() -> None:
    rows = [_price_row(price=150)]
    rows[0]["commence_time"] = ""

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert len(card.quarantined) == 1


def test_the_quarantine_section_appears_with_its_exact_heading() -> None:
    rows = [_price_row(price=150, hours=-2)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )
    rendered = card_module.render_card(card)

    assert QUARANTINE_SECTION in rendered
    assert "no longer available" in rendered


def test_a_pass_on_a_started_game_is_dropped_too() -> None:
    """Otherwise the guard's coverage depends on which section a row lands in."""
    rows = [_price_row(price=100, hours=-1)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.50},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.passes == []


def test_no_started_game_is_ever_offered_as_a_play() -> None:
    rows = [
        _price_row(price=150, hours=-1, player="Started Guy"),
        _price_row(price=150, hours=3, player="Later Guy"),
    ]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60, _key(rows[1]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )
    playable = card.best_bets + card.leans + card.passes

    assert all(row["puck_drop_state"] == "playable" for row in playable)
    assert card.safety["started_game_offered_as_a_play"] is False


# -- fingerprint and output --------------------------------------------


def test_the_fingerprint_ignores_a_price_move() -> None:
    """A card whose only change is half a cent has not changed its selections."""
    rows_a = [_price_row(price=150)]
    rows_b = [_price_row(price=155)]

    card_a = card_module.build_card(
        _prices(rows_a),
        {_key(rows_a[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )
    card_b = card_module.build_card(
        _prices(rows_b),
        {_key(rows_b[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card_a.selection_fingerprint() == card_b.selection_fingerprint()


def test_the_fingerprint_changes_when_a_selection_does() -> None:
    rows_a = [_price_row(price=150, line=3.5)]
    rows_b = [_price_row(price=150, line=2.5)]

    card_a = card_module.build_card(
        _prices(rows_a),
        {_key(rows_a[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )
    card_b = card_module.build_card(
        _prices(rows_b),
        {_key(rows_b[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card_a.selection_fingerprint() != card_b.selection_fingerprint()


def test_saving_writes_both_files_and_the_fingerprint(tmp_path: Path) -> None:
    rows = [_price_row(price=150)]
    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    paths = card_module.save_card(card, output_dir=tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    assert Path(paths["markdown"]).is_file()
    assert payload["selection_fingerprint"] == card.selection_fingerprint()
    assert payload["total_units"] == card.total_units


def test_the_card_never_claims_a_demonstrated_edge() -> None:
    rows = [_price_row(price=150)]
    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    rendered = card_module.render_card(card)

    assert "No edge here is a demonstrated edge" in rendered
    assert "what_we_can_claim.md" in rendered
    assert "Bets placed: **No**" in rendered


def test_unmatched_names_are_recorded_on_the_card() -> None:
    """"Why is my player not here" is the first question a reader asks."""
    rows = [_price_row(price=150)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
        unresolved_names=["Hartford Whalers", "Elias Pettersson"],
    )

    assert card.unresolved_names == ["Elias Pettersson", "Hartford Whalers"]


def test_the_card_explains_that_an_unmatched_name_is_not_a_judgement() -> None:
    rows = [_price_row(price=150)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
        unresolved_names=["Elias Pettersson"],
    )
    rendered = card_module.render_card(card)

    assert "Names that could not be matched" in rendered
    assert "not a judgement about them" in rendered
    assert "a join that did not land" in rendered


def test_the_unmatched_section_is_absent_when_everything_matched() -> None:
    rows = [_price_row(price=150)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert "Names that could not be matched" not in card_module.render_card(card)


def test_a_long_unmatched_list_is_truncated_with_a_count() -> None:
    rows = [_price_row(price=150)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
        unresolved_names=[f"Player {index}" for index in range(30)],
    )
    rendered = card_module.render_card(card)

    assert "10 further" in rendered


def test_edges_are_computed_against_the_price_as_sold() -> None:
    """Devigging only where possible would put team and prop thresholds on
    different scales, and the card ranks them against each other."""
    from nhl_betting_lab.models.value import american_to_implied

    rows = [_price_row(price=-130)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.70},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )
    selection = (card.best_bets + card.leans)[0]

    assert selection["implied_probability"] == pytest.approx(
        american_to_implied(-130)
    )
    assert selection["edge"] == pytest.approx(0.70 - american_to_implied(-130))


def test_the_module_states_why_it_does_not_devig() -> None:
    text = " ".join(card_module.__doc__.split())

    assert "deliberately not used here" in text
    assert "understated" in text


# -- defence in depth ---------------------------------------------------


def test_a_leaked_excluded_market_blocks_the_whole_card(monkeypatch) -> None:
    """The input is already filtered to eligible markets, so this branch only
    fires if a future change upstream lets one through. Simulating that change
    is the only way to know the net is there."""
    rows = [_price_row(price=150)]
    real = card_module.build_candidates

    def leak(prices, probabilities, **kwargs):
        selections, passes = real(prices, probabilities, **kwargs)
        for candidate in selections:
            candidate.market = "points"  # never eligible in this card
        return selections, passes

    monkeypatch.setattr(card_module, "build_candidates", leak)

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.card_generated is False
    assert card.best_bets == []
    assert card.leans == []
    assert card.passes == []
    assert any("reached the selections" in item for item in card.blockers)


def test_an_unusable_price_produces_no_candidate_at_all() -> None:
    rows = [_price_row(price=150)]
    prices = _prices(rows)
    prices["american_odds"] = prices["american_odds"].astype(object)
    prices.loc[0, "american_odds"] = "not a price"

    card = card_module.build_card(
        prices,
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert card.passes == []


def test_an_unparseable_line_is_treated_as_no_line() -> None:
    rows = [_price_row(price=150, line=None)]
    prices = _prices(rows)
    prices["line"] = prices["line"].astype(object)
    prices.loc[0, "line"] = "two and a half"

    card = card_module.build_card(
        prices,
        {("shots_on_goal", "auston matthews", "TOR", "BOS", "over", None): 0.60},
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.card_generated is True


def test_a_market_key_the_lab_does_not_know_produces_no_candidate() -> None:
    rows = [_price_row(market="corner_kicks", price=150)]

    card = card_module.build_card(
        _prices(rows),
        {_key(rows[0]): 0.60},
        eligibility=_eligibility(["corner_kicks"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert card.leans == []


def test_a_tier_is_assigned_by_edge_size() -> None:
    """Staking follows the tier, so the boundary is worth pinning down."""
    assert card_module._tier_for(0.30, is_prop=False) == "A"
    assert card_module._tier_for(0.10, is_prop=False) == "B"
    assert card_module._tier_for(0.05, is_prop=False) == "C"
    # A prop must clear a higher bar for the same tier.
    assert card_module._tier_for(0.10, is_prop=True) == "C"


def test_every_tier_has_a_stake_and_none_is_large() -> None:
    """These are positions whose expected value is genuinely uncertain."""
    assert set(card_module.TIER_UNITS) == {"A", "B", "C"}
    assert all(0 < units <= 0.5 for units in card_module.TIER_UNITS.values())
