"""Stat sides: each priced game's model-favoured side on the card, as a list.

Cooper, 2026-10-10: "I want to make sure were not only looking for edges but
looking for sides that the stats say should win." The section shows who the
model expects to win every priced game, its win chance and how that chance
compares with the best price. It is a list beside the card: nothing in it is a
best bet, lean, pass or stake, and the probability map the snapshot freezes is
not touched.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

from nhl_betting_lab.market_eligibility import ELIGIBLE, EligibilityReport, MarketEligibility
from nhl_betting_lab.reports import gameday_card as card_module
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.stat_sides import SECTION_TITLE, build_stat_sides

NOW = datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def ml(selection: str, price: float, *, home="Toronto Maple Leafs", away="Boston Bruins", hours=7.0, book="DraftKings") -> dict:
    return {"date": "2026-10-10", "commence_time": _at(hours), "home_team": home, "away_team": away,
            "market": "moneyline", "player": "", "selection": selection, "line": None,
            "american_odds": price, "book": book}


def key(row: dict) -> tuple:
    return selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=None)


def probs(rows: list[dict], home: float) -> dict:
    out = {}
    for r in rows:
        out[key(r)] = home if r["selection"] == "home" else 1 - home
    return out


def test_the_side_with_the_larger_win_chance_is_listed_at_its_best_price() -> None:
    rows = [ml("home", -150), ml("home", -140, book="FanDuel"), ml("away", 125)]
    sides = build_stat_sides(pd.DataFrame(rows), probs(rows, 0.62), now=NOW)
    assert len(sides.rows) == 1
    row = sides.rows[0]
    assert (row["team"], row["opponent"], row["side"]) == ("Toronto Maple Leafs", "Boston Bruins", "home")
    assert row["win_probability"] == 0.62
    assert (row["american_odds"], row["book"]) == (-140.0, "FanDuel"), "the best price staged, and its book"
    assert row["edge"] == round(0.62 - 140 / 240, 4)
    assert row["best_bet"] is False


def test_an_away_favourite_is_named_as_such() -> None:
    rows = [ml("home", 130), ml("away", -155)]
    row = build_stat_sides(pd.DataFrame(rows), probs(rows, 0.41), now=NOW).rows[0]
    assert (row["team"], row["side"], row["win_probability"]) == ("Boston Bruins", "away", 0.59)


def test_a_game_without_an_opinion_on_both_sides_is_counted_not_guessed() -> None:
    rows = [ml("home", -150), ml("away", 125)]
    only_home = {key(rows[0]): 0.6}
    sides = build_stat_sides(pd.DataFrame(rows), only_home, now=NOW)
    assert sides.rows == [] and sides.without_opinion == 1


def test_a_started_or_unconfirmed_game_is_not_listed() -> None:
    started = [ml("home", -150, hours=-0.5), ml("away", 125, hours=-0.5)]
    unknown = [dict(ml("home", -110, home="A", away="B"), commence_time=""), dict(ml("away", -110, home="A", away="B"), commence_time="")]
    rows = started + unknown
    p = {**probs(started, 0.6), **probs(unknown, 0.55)}
    sides = build_stat_sides(pd.DataFrame(rows), p, now=NOW)
    assert sides.rows == []
    assert sides.removed_by_guard == 2, "the started game and the one whose start cannot be confirmed"


def test_another_nights_game_is_left_off_when_a_day_is_named() -> None:
    tonight = [ml("home", -150), ml("away", 125)]
    tomorrow = [ml("home", -120, hours=31), ml("away", 100, hours=31)]
    rows = tonight + tomorrow
    sides = build_stat_sides(pd.DataFrame(rows), {**probs(tonight, 0.6), **probs(tomorrow, 0.55)}, now=NOW, day="2026-10-10")
    assert len(sides.rows) == 1 and sides.rows[0]["american_odds"] == -150.0


def test_a_side_the_card_staked_is_marked_as_its_best_bet() -> None:
    rows = [ml("home", 140), ml("away", -165)]
    staked = [{"market": "moneyline", "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins", "selection": "home"}]
    row = build_stat_sides(pd.DataFrame(rows), probs(rows, 0.52), now=NOW, best_bets=staked).rows[0]
    assert row["best_bet"] is True


def test_listing_the_sides_touches_neither_the_prices_nor_the_probabilities() -> None:
    rows = [ml("home", -150), ml("away", 125)]
    prices, p = pd.DataFrame(rows), probs(rows, 0.6)
    before_prices, before_p = prices.copy(), copy.deepcopy(p)
    build_stat_sides(prices, p, now=NOW)
    pd.testing.assert_frame_equal(prices, before_prices)
    assert p == before_p


def _card(*, built: bool) -> card_module.GamedayCard:
    rows = [ml("home", -150), ml("away", 125)]
    eligibility = EligibilityReport(provider_name="the_odds_api", games_in_slate=1, markets=[
        MarketEligibility(market="moneyline", state=ELIGIBLE, reason="Allowlisted and complete.")])
    p = probs(rows, 0.6)
    card = card_module.build_card(pd.DataFrame(rows), p, eligibility=eligibility, now=NOW)
    if built:
        sides = build_stat_sides(pd.DataFrame(rows), p, now=NOW, best_bets=card.best_bets)
        card.stat_sides_built, card.stat_sides = True, sides.rows
    return card


def test_the_card_renders_the_section_and_keeps_it_out_of_the_selections() -> None:
    plain, listed = _card(built=False), _card(built=True)
    text = card_module.render_card(listed)
    assert f"## {SECTION_TITLE}" in text
    assert "| Boston Bruins @ Toronto Maple Leafs |" in text and "**Toronto Maple Leafs** | 60.0%" in text
    assert f"## {SECTION_TITLE}" not in card_module.render_card(plain)
    assert listed.selection_fingerprint() == plain.selection_fingerprint()
    assert listed.total_units == plain.total_units
    assert (listed.best_bets, listed.leans, listed.passes) == (plain.best_bets, plain.leans, plain.passes)


def test_the_section_survives_the_cards_json(tmp_path) -> None:
    import json

    paths = card_module.save_card(_card(built=True), output_dir=tmp_path)
    payload = json.loads(open(paths["json"], encoding="utf-8").read())
    assert payload["stat_sides_built"] is True
    assert payload["stat_sides"][0]["team"] == "Toronto Maple Leafs"
