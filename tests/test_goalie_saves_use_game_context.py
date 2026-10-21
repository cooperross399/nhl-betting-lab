"""Goalie saves are priced on tonight's game, not the goalie's career.

Cooper, 2026-10-20: "Re-evaluate and fine-tune the goalie saves portion of
the model. Factor in the team that is favored to win and home ice
advantage." The Saves Model Study measured the change walk-forward before
it shipped (`docs/goalie_saves_context.md`).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.models import saves_context as sc
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.value import american_to_implied, profit_on_win
from nhl_betting_lab.reports import card_pricing
from test_player_props_model import sample_logs


def _games(rows: list[tuple[str, str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"game_id": i, "date": f"2025-01-{1 + i % 28:02d}", "home_team": h,
             "away_team": a, "home_shots": hs, "away_shots": aws}
            for i, (h, a, hs, aws) in enumerate(rows)
        ]
    )


def _saves_row(line: float = 26.5) -> pd.DataFrame:
    return pd.DataFrame([{
        "market": "goalie_saves", "player": "Netminder TOR", "home_team": "TOR",
        "away_team": "BOS", "selection": "over", "line": line, "american_odds": -110,
    }])


def test_a_team_that_outshoots_its_opponents_lowers_its_goalies_saves() -> None:
    # TOR outshoots BOS 38-22 every night: TOR's goalie should face fewer.
    games = _games([("TOR", "BOS", 38, 22) if i % 2 == 0 else ("BOS", "TOR", 22, 38) for i in range(40)])
    rates = sc.team_shot_rates(games)
    assert rates.team_sa("TOR") < 1.0 < rates.team_sa("BOS")
    assert rates.opp_sf("BOS") < 1.0 < rates.opp_sf("TOR")

    model = PlayerPropsModel().fit(sample_logs())
    plain, _ = card_pricing.price_props(_saves_row(), model)
    context, _ = card_pricing.price_props(
        _saves_row(), model, saves=sc.SavesInputs(rates, 3600.0)
    )
    key = next(iter(plain))
    assert set(context) == set(plain)
    assert context[key] < plain[key]


def test_the_card_uses_the_shipped_coefficients() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    rates = sc.team_shot_rates(_games([("TOR", "BOS", 30, 30)] * 20))
    inputs = sc.SavesInputs(rates, 3500.0)
    probabilities, _ = card_pricing.price_props(_saves_row(24.5), model, saves=inputs)
    goalie = model.resolve_player("Netminder TOR")
    base = model.expected_count(goalie, "goalie_saves", opponent="BOS", venue="home")
    expected = inputs.distribution(
        base, venue="home", team="TOR", opponent="BOS",
        expected_toi_seconds=model.goalies[goalie].expected_toi_seconds,
    )
    assert expected.r == pytest.approx(sc.SHIPPED.dispersion_r)
    assert next(iter(probabilities.values())) == pytest.approx(expected.over_probability(24.5))


def test_skater_props_are_untouched_by_the_saves_inputs() -> None:
    model = PlayerPropsModel().fit(sample_logs())
    row = pd.DataFrame([{
        "market": "shots_on_goal", "player": "Star TOR", "home_team": "TOR",
        "away_team": "BOS", "selection": "over", "line": 2.5, "american_odds": 120,
    }])
    inputs = sc.SavesInputs(sc.team_shot_rates(_games([("TOR", "BOS", 40, 20)] * 20)), 3600.0)
    assert card_pricing.price_props(row, model)[0] == card_pricing.price_props(row, model, saves=inputs)[0]


def test_a_rink_that_counts_generously_has_a_factor_above_one() -> None:
    rows = []
    for i in range(60):
        # Every game in AAA's building records 70 shots; elsewhere 56.
        rows.append(("AAA", "BBB", 35, 35) if i % 2 == 0 else ("BBB", "AAA", 28, 28))
    rates = sc.team_shot_rates(_games(rows))
    assert rates.arena_factor("AAA") > 1.0 > rates.arena_factor("BBB")


def test_the_market_win_chance_is_devigged_and_taken_before_face_off() -> None:
    def row(selection, odds, snapshot):
        return {"market": "moneyline", "selection": selection, "american_odds": odds,
                "book": "x", "snapshot": snapshot, "commence_time": "2025-01-11T00:00:00Z",
                "home_team": "Home", "away_team": "Away"}
    prices = pd.DataFrame([
        row("home", -150, "2025-01-10T15:00:00Z"), row("away", 130, "2025-01-10T15:00:00Z"),
        # At face-off: ignored.
        row("home", -400, "2025-01-11T00:00:00Z"), row("away", 300, "2025-01-11T00:00:00Z"),
    ])
    probs = sc.home_win_probabilities(prices)
    ih, ia = american_to_implied(-150), american_to_implied(130)
    assert probs == {("2025-01-10", "Home", "Away"): pytest.approx(ih / (ih + ia))}


def _ledger_row(market: str, day: str, index: int) -> dict:
    odds, p = 100.0, 0.6
    return {
        "snapshot_date": day, "commence_time": f"{day}T23:10:00Z",
        "home_team": f"Home {index}", "away_team": "Boston Bruins", "market": market,
        "player": f"Goalie {index}", "selection": "over", "line": 25.5,
        "american_odds": odds, "book": "DraftKings", "model_probability": p,
        "edge": p - american_to_implied(odds), "verdicts_in_force": "x",
        "settled_at": f"{day}T12:00:00+00:00", "outcome": "won", "actual": 28.0,
        "profit_units": profit_on_win(odds),
    }


def test_the_forward_report_sets_aside_saves_priced_before_the_change() -> None:
    rows = (
        [_ledger_row("goalie_saves", "2026-10-14", i) for i in range(3)]
        + [_ledger_row("goalie_saves", sc.SAVES_CONTEXT_FROM, i) for i in range(2)]
        + [_ledger_row("shots_on_goal", "2026-10-14", i) for i in range(4)]
    )
    payload = fe.build_forward_report(
        pd.DataFrame(rows), now=datetime(2026, 12, 1, tzinfo=timezone.utc)
    )
    assert payload["superseded_saves_rows"] == 3
    assert payload["markets"]["goalie_saves"]["opinions"] == 2
    assert payload["markets"]["shots_on_goal"]["opinions"] == 4
    text = fe.render_forward_report(payload)
    assert f"3 goalie-saves ledger row(s) frozen before {sc.SAVES_CONTEXT_FROM}" in text
