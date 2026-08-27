from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.reports import player_props_backtest as bt


def _sample(date: str, market: str, player: str, mean: float, actual: float) -> dict:
    """One player-game-market, carrying the fitted distribution."""
    return {
        "date": date,
        "game_id": abs(hash((date, player, market))) % 100000,
        "player_id": abs(hash(player)) % 10000,
        "market": market,
        "player": player,
        "mean": mean,
        "dispersion_r": float("nan"),
        "actual": actual,
        "toi_seconds": 1200,
    }


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Poisson(4.6) puts ~0.62 above 3.5.
            _sample("2025-01-05", "shots_on_goal", "Auston Matthews", 4.6, 5.0),
            # Poisson(3.3) puts ~0.58 above 2.5.
            _sample("2025-01-05", "shots_on_goal", "Mitch Marner", 3.3, 1.0),
            # Poisson(1.2) puts ~0.70 above 0.5.
            _sample("2025-01-06", "points", "Auston Matthews", 1.2, 2.0),
        ]
    )


def _prices(rows: list[dict] | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        rows
        if rows is not None
        else [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Auston Matthews",
                "selection": "over",
                "line": 3.5,
                "american_odds": 110,
                "book": "DraftKings",
            },
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Mitch Marner",
                "selection": "over",
                "line": 2.5,
                "american_odds": 105,
                "book": "FanDuel",
            },
            {
                "date": "2025-01-06",
                "commence_time": "2025-01-07T00:10:00Z",
                "market": "points",
                "player": "Auston Matthews",
                "selection": "over",
                "line": 0.5,
                "american_odds": -110,
                "book": "DraftKings",
            },
        ]
    )


# -- settlement --------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "line", "selection", "won", "push"),
    [
        (4.0, 3.5, "over", True, False),
        (3.0, 3.5, "over", False, False),
        (3.0, 3.5, "under", True, False),
        (1.0, 0.5, "yes", True, False),
        (0.0, 0.5, "yes", False, False),
    ],
)
def test_half_point_lines_settle_without_a_push(
    actual: float, line: float, selection: str, won: bool, push: bool
) -> None:
    assert bt.settle(actual, line, selection) == (won, push)


def test_a_whole_number_line_pushes_on_an_exact_hit() -> None:
    """A book refunds "over 2.0" on a 2; rounding that is a systematic error."""
    assert bt.settle(2.0, 2.0, "over") == (False, True)
    assert bt.settle(2.0, 2.0, "under") == (False, True)
    assert bt.settle(3.0, 2.0, "over") == (True, False)


def test_an_unknown_selection_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="Unknown prop selection"):
        bt.settle(3.0, 2.5, "maybe")


# -- the measurement ---------------------------------------------------


def test_no_prices_measures_nothing_and_says_so() -> None:
    report = bt.run_backtest(pd.DataFrame(columns=["market"]), _samples())

    assert report.bets == []
    assert "nothing is measured" in report.summary_line()
    rendered = bt.render_backtest(report)
    assert "statement about the evidence, not about the model" in rendered


def test_no_samples_measures_nothing() -> None:
    report = bt.run_backtest(_prices(), pd.DataFrame(columns=["market"]))

    assert report.bets == []


def test_a_clear_edge_produces_a_bet() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    assert report.bets
    assert report.overall is not None
    assert report.overall.bets == len(report.bets)


def test_an_outcome_below_the_threshold_is_counted_not_bet() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.95)

    assert report.bets == []
    assert report.outcomes_below_threshold == 3


def test_settlement_comes_from_the_sample_not_the_price() -> None:
    """A provider outage can change what was measured, never what a bet did."""
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)
    matthews = [bet for bet in report.bets if bet.player == "Auston Matthews"]

    assert all(bet.won for bet in matthews)  # 5 shots over 3.5, 2 points over 0.5


def test_a_losing_bet_costs_exactly_one_unit() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)
    marner = next(bet for bet in report.bets if bet.player == "Mitch Marner")

    assert marner.won is False
    assert marner.profit == pytest.approx(-1.0)


def test_a_winning_plus_money_bet_pays_its_price() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)
    matthews = next(
        bet
        for bet in report.bets
        if bet.player == "Auston Matthews" and bet.market == "shots_on_goal"
    )

    assert matthews.profit == pytest.approx(1.10)


def test_an_unmatched_player_is_reported_not_scored_as_a_loss() -> None:
    prices = _prices(
        [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Nobody At All",
                "selection": "over",
                "line": 2.5,
                "american_odds": 120,
                "book": "DraftKings",
            }
        ]
    )

    report = bt.run_backtest(prices, _samples(), edge_threshold=0.01)

    assert report.bets == []
    assert "Nobody At All" in report.unmatched_players
    assert report.outcomes_without_a_model_opinion == 1


def test_an_unusable_price_is_skipped_rather_than_guessed() -> None:
    prices = _prices()
    prices["american_odds"] = prices["american_odds"].astype(object)
    prices.loc[0, "american_odds"] = "n/a"

    report = bt.run_backtest(prices, _samples(), edge_threshold=0.05)

    assert all(bet.player != "Auston Matthews" or bet.market != "shots_on_goal"
               for bet in report.bets)


def test_the_under_side_uses_the_complement_of_the_model_probability() -> None:
    prices = _prices(
        [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Mitch Marner",
                "selection": "under",
                "line": 2.5,
                # +250 implies 28.6%; the model puts the Under at 35.9%.
                "american_odds": 250,
                "book": "FanDuel",
            }
        ]
    )

    report = bt.run_backtest(prices, _samples(), edge_threshold=0.01)

    from nhl_betting_lab.models.counts import Poisson

    assert len(report.bets) == 1
    assert report.bets[0].model_probability == pytest.approx(
        1 - Poisson(3.3).over_probability(2.5)
    )
    assert report.bets[0].won is True  # 1 shot is under 2.5


# -- the report --------------------------------------------------------


def test_a_result_that_includes_zero_says_the_exact_words() -> None:
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE

    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    rendered = bt.render_backtest(report)

    assert NO_DEMONSTRATED_EDGE in rendered


def test_the_report_states_that_one_sided_prices_understate_the_edge() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    rendered = bt.render_backtest(report)

    assert "understates" in rendered
    assert "conservative in that one direction" in rendered


def test_the_report_says_settlement_never_comes_from_the_provider() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    rendered = bt.render_backtest(report)

    assert "never from the odds" in rendered


def test_an_unprobed_retention_state_is_reported_as_unknown() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    rendered = bt.render_backtest(report)

    assert "is **unknown**" in rendered
    assert "not assumed to be all of them" in rendered


def test_an_unmeasurable_market_is_named_and_not_given_a_calibration_number() -> None:
    report = bt.run_backtest(
        _prices(),
        _samples(),
        edge_threshold=0.05,
        unmeasurable_markets={
            "blocked_shots": "the provider does not retain it historically"
        },
    )

    rendered = bt.render_backtest(report)

    assert "blocked_shots" in rendered
    assert "no price-based evidence at all" in rendered
    assert "cannot substitute for this" in rendered


def test_the_report_states_the_rule_it_enforces() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    rendered = bt.render_backtest(report)

    assert "improves calibration and loses here does not ship" in rendered


def test_saving_writes_the_contract_path(tmp_path: Path) -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    paths = bt.save_backtest(report, output_dir=tmp_path)

    assert Path(paths["markdown"]).name == "player_props_backtest.md"
    assert Path(paths["csv"]).is_file()
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert payload["bets"] == len(report.bets)


def test_the_saved_json_carries_the_interval_for_every_market(tmp_path: Path) -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    paths = bt.save_backtest(report, output_dir=tmp_path)
    payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))

    for entry in payload["by_market"].values():
        assert "includes_zero" in entry
        assert "verdict" in entry


# -- the search, and which way the bets point --------------------------


def _many(market: str, side: str, count: int, *, won: bool) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _sample(
                f"2025-01-{1 + index % 28:02d}",
                market,
                f"Player {index}",
                3.4,  # Poisson(3.4) puts ~0.70 above 2.5
                5.0 if won else 0.0,
            )
            for index in range(count)
        ]
    )


def test_measuring_several_markets_counts_them_as_a_family() -> None:
    samples = pd.concat(
        [_many("shots_on_goal", "over", 60, won=True),
         _many("points", "over", 60, won=False)],
        ignore_index=True,
    )
    prices = pd.DataFrame(
        [
            {
                "date": row.date,
                "commence_time": f"{row.date}T18:00:00Z",
                "market": row.market,
                "player": row.player,
                "selection": "over",
                "line": 2.5,
                "american_odds": 150,
            }
            for row in samples.itertuples()
        ]
    )

    report = bt.run_backtest(prices, samples, edge_threshold=0.05)

    assert report.looks > 1
    assert all(item.looks == report.looks for item in report.by_market.values())


def test_the_report_explains_why_there_are_two_intervals() -> None:
    samples = pd.concat(
        [_many("shots_on_goal", "over", 60, won=True),
         _many("points", "over", 60, won=False)],
        ignore_index=True,
    )
    prices = pd.DataFrame(
        [
            {
                "date": row.date,
                "commence_time": f"{row.date}T18:00:00Z",
                "market": row.market,
                "player": row.player,
                "selection": "over",
                "line": 2.5,
                "american_odds": 150,
            }
            for row in samples.itertuples()
        ]
    )

    rendered = bt.render_backtest(
        bt.run_backtest(prices, samples, edge_threshold=0.05)
    )

    assert "Why there are two intervals" in rendered
    assert "reporting a search and calling it a finding" in rendered
    assert "Bonferroni" in rendered


def test_the_report_shows_which_way_the_bets_point() -> None:
    """The most important structural fact, and invisible in the market table."""
    samples = _many("shots_on_goal", "under", 40, won=True)
    prices = pd.DataFrame(
        [
            {
                "date": row.date,
                "commence_time": f"{row.date}T18:00:00Z",
                "market": "shots_on_goal",
                "player": row.player,
                "selection": "under",
                "line": 2.5,
                "american_odds": 150,
            }
            for row in samples.itertuples()
        ]
    )
    # The model says 70% Over, so the Under side is 30% and never bet. A far
    # lower mean flips it: Poisson(1.0) puts only ~8% above 2.5.
    samples["mean"] = 1.0

    report = bt.run_backtest(prices, samples, edge_threshold=0.05)
    rendered = bt.render_backtest(report)

    assert "Which way the bets point" in rendered
    assert "of every bet is on the under" in rendered
    assert "one directional disagreement with the market" in rendered


def test_yes_and_no_are_normalised_onto_over_and_under() -> None:
    bet = bt.PlacedBet(
        date="2025-01-01", market="goals", player="X", line=0.5,
        selection="yes", american_odds=150, model_probability=0.6,
        implied_probability=0.4, edge=0.2, actual=1.0, won=True,
        push=False, profit=1.5,
    )

    assert bt._side_of(bet) == "over"


def test_a_window_label_is_recorded_in_the_report() -> None:
    report = bt.run_backtest(
        _prices(), _samples(), edge_threshold=0.05, window_label="2025-26"
    )

    assert "Window measured: **2025-26**" in bt.render_backtest(report)


def test_a_label_writes_a_second_copy_beside_the_contract_path(
    tmp_path: Path,
) -> None:
    """The contract filename always gets the report as run, so a scheduled job
    never has to know about labels; the labelled copy is what makes two
    windows comparable side by side."""
    report = bt.run_backtest(
        _prices(), _samples(), edge_threshold=0.05, window_label="2024-25"
    )

    paths = bt.save_backtest(report, output_dir=tmp_path, label="2024-25")

    assert Path(paths["markdown"]).name == "player_props_backtest.md"
    assert Path(paths["labelled_markdown"]).name == (
        "player_props_backtest_2024-25.md"
    )
    assert Path(paths["labelled_json"]).is_file()


def test_a_label_with_awkward_characters_is_made_safe(tmp_path: Path) -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    paths = bt.save_backtest(
        report, output_dir=tmp_path, label="../etc/passwd 2024"
    )

    assert "/" not in Path(paths["labelled_markdown"]).name
    assert Path(paths["labelled_markdown"]).parent == tmp_path


def test_no_label_writes_only_the_contract_path(tmp_path: Path) -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    paths = bt.save_backtest(report, output_dir=tmp_path)

    assert "labelled_markdown" not in paths


def test_the_report_explains_the_gap_between_claimed_and_realised_edge() -> None:
    """Bets are selected wherever the model most disagrees with the price,
    which is exactly where its estimation error concentrates."""
    samples = _many("shots_on_goal", "over", 60, won=True)
    prices = pd.DataFrame(
        [
            {
                "date": row.date,
                "commence_time": f"{row.date}T18:00:00Z",
                "market": row.market,
                "player": row.player,
                "selection": "over",
                "line": 2.5,
                "american_odds": 150,
            }
            for row in samples.itertuples()
        ]
    )

    rendered = bt.render_backtest(
        bt.run_backtest(prices, samples, edge_threshold=0.05)
    )

    assert "claimed edge against the realised one" in rendered
    assert "estimation error concentrates" in rendered
    assert "not a fault in the measurement" in rendered


# -- the join, done by identity rather than by string -------------------


def test_a_dotted_initials_price_matches_a_nickname_registry_name() -> None:
    """'A.J. Greer' bought, '(AJ) Greer' in the registry: twenty real priced
    outcomes went unmatched on exactly this shape."""
    samples = pd.DataFrame(
        [_sample("2025-01-05", "shots_on_goal", "Anthony-John (AJ) Greer", 3.0, 4.0)]
    )
    prices = _prices(
        [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "A.J. Greer",
                "selection": "over",
                "line": 2.5,
                "american_odds": 150,
                "book": "DraftKings",
            }
        ]
    )

    report = bt.run_backtest(prices, samples, edge_threshold=0.01)

    assert len(report.bets) == 1
    assert report.outcomes_without_a_model_opinion == 0


def test_a_dotless_initials_price_matches_a_dotted_registry_name() -> None:
    samples = pd.DataFrame(
        [_sample("2025-01-05", "shots_on_goal", "J.T. Miller", 3.4, 4.0)]
    )
    prices = _prices(
        [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "JT Miller",
                "selection": "over",
                "line": 2.5,
                "american_odds": 150,
                "book": "DraftKings",
            }
        ]
    )

    report = bt.run_backtest(prices, samples, edge_threshold=0.01)

    assert len(report.bets) == 1


def _aho_samples() -> pd.DataFrame:
    """Both Sebastian Ahos dressed on the same night."""
    frame = pd.DataFrame(
        [
            _sample("2025-01-05", "shots_on_goal", "Sebastian Aho", 4.5, 6.0),
            _sample("2025-01-05", "shots_on_goal", "Sebastian Aho", 1.2, 0.0),
        ]
    )
    frame.loc[0, "player_id"] = 8478427
    frame.loc[0, "team"] = "CAR"
    frame.loc[1, "player_id"] = 8480222
    frame.loc[1, "team"] = "NYI"
    return frame


def _aho_price(home: str, away: str) -> pd.DataFrame:
    return _prices(
        [
            {
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Sebastian Aho",
                "selection": "over",
                "line": 2.5,
                "american_odds": 150,
                "home_team": home,
                "away_team": away,
                "book": "DraftKings",
            }
        ]
    )


def test_a_shared_name_settles_against_the_player_in_the_priced_game() -> None:
    """The flat join settled Carolina's Aho prices against the Islanders'
    Aho's games on the 123 nights both dressed — a coin flip per night."""
    report = bt.run_backtest(
        _aho_price("Carolina Hurricanes", "Boston Bruins"),
        _aho_samples(),
        edge_threshold=0.01,
    )

    assert len(report.bets) == 1
    # The Carolina Aho's game: mean 4.5, actual 6 — the over wins.
    assert report.bets[0].won is True


def test_the_other_ahos_game_settles_against_the_other_aho() -> None:
    report = bt.run_backtest(
        _aho_price("New York Islanders", "Boston Bruins"),
        _aho_samples(),
        edge_threshold=0.01,
    )

    # NYI Aho: mean 1.2 — the model holds no over-2.5 edge, so no bet; what
    # matters is that it did NOT match the Carolina distribution.
    assert len(report.bets) == 0
    assert report.outcomes_ambiguous == 0


def test_both_ahos_in_one_game_resolves_to_neither() -> None:
    report = bt.run_backtest(
        _aho_price("Carolina Hurricanes", "New York Islanders"),
        _aho_samples(),
        edge_threshold=0.01,
    )

    assert len(report.bets) == 0
    assert report.outcomes_ambiguous == 1


# -- the accounting identity -------------------------------------------


def test_every_priced_outcome_lands_in_exactly_one_bucket() -> None:
    """priced = no_opinion + below_threshold + unparseable + ambiguous + bets.
    A drop that lands in no bucket is invisible exactly when a format change
    makes it large."""
    samples = _samples()
    prices = _prices()
    extra = pd.DataFrame(
        [
            {  # unparseable odds, after a successful model match
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Auston Matthews",
                "selection": "over",
                "line": 3.5,
                "american_odds": "EVEN",
                "book": "DraftKings",
            },
            {  # unparseable line
                "date": "2025-01-05",
                "commence_time": "2025-01-06T00:10:00Z",
                "market": "shots_on_goal",
                "player": "Auston Matthews",
                "selection": "over",
                "line": "no point",
                "american_odds": 120,
                "book": "DraftKings",
            },
        ]
    )
    prices = pd.concat([prices, extra], ignore_index=True)

    report = bt.run_backtest(prices, samples, edge_threshold=0.05)

    accounted = (
        report.outcomes_without_a_model_opinion
        + report.outcomes_below_threshold
        + report.outcomes_unparseable
        + report.outcomes_ambiguous
        + len(report.bets)
    )
    assert report.outcomes_unparseable == 2
    assert accounted == report.priced_outcomes


def test_the_report_prints_the_reconciliation() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)

    rendered = bt.render_backtest(report)

    assert "Accounted for: all of them." in rendered
    assert "DOES NOT RECONCILE" not in rendered


def test_a_gap_in_the_accounting_is_printed_loudly() -> None:
    report = bt.run_backtest(_prices(), _samples(), edge_threshold=0.05)
    report.priced_outcomes += 3  # simulate a counterless drop path

    rendered = bt.render_backtest(report)

    assert "DOES NOT RECONCILE" in rendered
    assert "no counter" in rendered


def test_a_lone_candidate_on_the_wrong_team_is_a_void_not_a_match() -> None:
    """A lone candidate can still be the wrong same-named player when the
    right one did not dress. The price names the game; a candidate outside
    it is an unmatched price."""
    samples = _aho_samples().iloc[[0]]  # only the Carolina Aho dressed

    report = bt.run_backtest(
        _aho_price("New York Islanders", "Boston Bruins"),  # the NYI game
        samples,
        edge_threshold=0.01,
    )

    assert len(report.bets) == 0
    assert report.outcomes_without_a_model_opinion == 1
    assert "Sebastian Aho" in report.unmatched_players


def test_a_disambiguated_price_never_binds_to_the_bare_name() -> None:
    samples = _aho_samples()
    samples.loc[:, "player"] = "Elias Pettersson"
    prices = _aho_price("Carolina Hurricanes", "Boston Bruins")
    prices.loc[:, "player"] = "Elias Pettersson (2004)"

    report = bt.run_backtest(prices, samples, edge_threshold=0.01)

    assert len(report.bets) == 0
    assert report.outcomes_without_a_model_opinion == 1
