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


# -- the stats' side decides which team bets are staked (Cooper, 2026-10-10) --

def _team_row(market: str, selection: str, price: float, line=None) -> dict:
    return {**ml(selection, price), "market": market, "line": line}


def _pkey(row: dict) -> tuple:
    return selection_key(SimpleNamespace(**row), market=row["market"], selection=row["selection"], line=row["line"])


def _built(rows: list[dict], p: dict) -> card_module.GamedayCard:
    markets = sorted({r["market"] for r in rows})
    eligibility = EligibilityReport(provider_name="the_odds_api", games_in_slate=1, markets=[
        MarketEligibility(market=m, state=ELIGIBLE, reason="Allowlisted and complete.") for m in markets])
    return card_module.build_card(pd.DataFrame(rows), p, eligibility=eligibility, now=NOW)


def test_an_underdog_the_stats_give_a_real_chance_is_still_staked() -> None:
    # Home 42% at +200: an 8.7-point edge, under the best-bet bar; at +225, 11.2 points.
    rows = [ml("home", 225), ml("away", -270)]
    card = _built(rows, probs(rows, 0.42))
    assert [r["selection"] for r in card.best_bets] == ["home"], "42% is a real chance: still a bet"


def test_a_longshot_the_stats_do_not_back_is_a_lean_not_a_stake() -> None:
    # Home 30% at +400 is a 10-point edge by price; the stats give it under 40%.
    rows = [ml("home", 400), ml("away", -550)]
    card = _built(rows, probs(rows, 0.30))
    assert card.best_bets == []
    lean = next(r for r in card.leans if r["selection"] == "home")
    assert lean["demotion_reason"].startswith(card_module.STAT_SIDE_PREFIX)
    assert "30.0% chance to win, under the 40%" in lean["demotion_reason"]
    assert lean["suggested_units"] == 0.0
    assert "a team bet is staked only when the model gives that team at least a 40% chance" in card_module.render_card(card)


def test_the_favourite_with_an_edge_is_still_staked() -> None:
    rows = [ml("home", -110), ml("away", -110)]
    card = _built(rows, probs(rows, 0.62))
    assert [r["selection"] for r in card.best_bets] == ["home"]


def test_a_puck_line_on_a_team_the_stats_do_not_back_is_not_staked() -> None:
    mls = [ml("home", 260), ml("away", -320)]
    pl = [_team_row("puck_line", "home", 120, 1.5), _team_row("puck_line", "away", -140, -1.5)]
    p = {**probs(mls, 0.33), _pkey(pl[0]): 0.62, _pkey(pl[1]): 0.38}
    card = _built(mls + pl, p)
    assert ("puck_line", "home") not in {(r["market"], r["selection"]) for r in card.best_bets}
    assert any(r["market"] == "puck_line" and r["selection"] == "home" for r in card.leans)


def test_totals_are_not_sides_and_are_untouched() -> None:
    mls = [ml("home", -110), ml("away", -110)]
    tot = [_team_row("total_goals", "over", 120, 6.5), _team_row("total_goals", "under", -140, 6.5)]
    p = {**probs(mls, 0.5), _pkey(tot[0]): 0.60, _pkey(tot[1]): 0.40}
    card = _built(mls + tot, p)
    assert ("total_goals", "over") in {(r["market"], r["selection"]) for r in card.best_bets}


def test_a_side_with_no_moneyline_opinion_is_not_staked() -> None:
    pl = [_team_row("puck_line", "home", 120, 1.5)]
    card = _built(pl, {_pkey(pl[0]): 0.62})
    assert card.best_bets == []
    assert "cannot confirm" in card.leans[0]["demotion_reason"]
