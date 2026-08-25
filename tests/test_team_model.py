from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.models.team_model import TeamModel


def _games(rows: list[tuple[str, str, int, int, bool]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "home_team": home,
                "away_team": away,
                "home_goals": hg,
                "away_goals": ag,
                "regulation": regulation,
            }
            for home, away, hg, ag, regulation in rows
        ]
    )


def balanced_league(rounds: int = 30) -> pd.DataFrame:
    """Four teams: STRONG scores more, WEAK concedes more, two average."""
    rows: list[tuple[str, str, int, int, bool]] = []
    for index in range(rounds):
        rows.append(("STR", "WEA", 5, 2, True))
        rows.append(("WEA", "STR", 2, 4, True))
        rows.append(("AVA", "AVB", 3, 3, index % 3 != 0))
        rows.append(("AVB", "AVA", 3, 2, True))
    return _games(rows)


def test_fitting_needs_the_result_columns() -> None:
    with pytest.raises(KeyError, match="missing columns"):
        TeamModel().fit(pd.DataFrame({"home_team": ["TOR"]}))


def test_fitting_on_no_completed_games_is_an_error() -> None:
    frame = balanced_league(1)
    frame["home_goals"] = None

    with pytest.raises(ValueError, match="No completed games"):
        TeamModel().fit(frame)


def test_a_fitted_model_knows_every_team() -> None:
    model = TeamModel().fit(balanced_league())

    assert set(model.teams) == {"STR", "WEA", "AVA", "AVB"}
    assert "goals per game" in model.report.summary_line()


def test_the_stronger_team_is_expected_to_score_more() -> None:
    model = TeamModel().fit(balanced_league())

    strong_home, weak_away = model.expected_goals("STR", "WEA")
    weak_home, strong_away = model.expected_goals("WEA", "STR")

    assert strong_home > weak_away
    assert strong_away > weak_home


def test_home_advantage_is_measured_not_assumed() -> None:
    model = TeamModel().fit(balanced_league())

    assert model.home_advantage > 0
    assert model.report.home_advantage == model.home_advantage


def test_the_overtime_rate_is_measured_from_the_regulation_flag() -> None:
    model = TeamModel().fit(balanced_league(30))

    # A quarter of the AVA/AVB home games are flagged non-regulation.
    assert 0.0 < model.overtime_rate < 0.5


def test_moneyline_probabilities_sum_to_one() -> None:
    """There is no draw in an NHL moneyline; the tie is resolved."""
    model = TeamModel().fit(balanced_league())

    probabilities = model.moneyline_probabilities("STR", "WEA")

    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert set(probabilities) == {"home", "away"}


def test_the_favourite_is_favoured_on_the_moneyline() -> None:
    model = TeamModel().fit(balanced_league())

    assert model.moneyline_probabilities("STR", "WEA")["home"] > 0.5
    assert model.moneyline_probabilities("WEA", "STR")["away"] > 0.5


def test_a_regulation_tie_is_split_evenly_and_the_assumption_is_stated() -> None:
    model = TeamModel().fit(balanced_league())
    home, tie, away = model.regulation_probabilities("AVA", "AVB")
    moneyline = model.moneyline_probabilities("AVA", "AVB")

    assert moneyline["home"] == pytest.approx(home + tie / 2)
    assert "coin flip" in " ".join(
        TeamModel.moneyline_probabilities.__doc__.split()
    )


def test_an_overtime_winner_can_never_cover_minus_one_and_a_half() -> None:
    """The single most important hockey-specific fact in this model."""
    model = TeamModel().fit(balanced_league())

    puck_line = model.puck_line_probabilities("STR", "WEA")
    moneyline = model.moneyline_probabilities("STR", "WEA")
    _, tie, _ = model.regulation_probabilities("STR", "WEA")

    # Covering -1.5 requires winning by two in regulation, so it must be
    # strictly less likely than winning at all by at least the tie mass.
    assert puck_line["home_minus"] < moneyline["home"] - tie / 2


def test_the_puck_line_sides_are_complements_of_each_other() -> None:
    model = TeamModel().fit(balanced_league())

    puck_line = model.puck_line_probabilities("STR", "WEA")

    assert puck_line["home_minus"] + puck_line["away_plus"] == pytest.approx(1.0)
    assert puck_line["away_minus"] + puck_line["home_plus"] == pytest.approx(1.0)


def test_a_one_goal_loss_covers_plus_one_and_a_half() -> None:
    model = TeamModel().fit(balanced_league())

    puck_line = model.puck_line_probabilities("WEA", "STR")

    # The underdog's +1.5 is far more likely than its moneyline.
    assert puck_line["home_plus"] > model.moneyline_probabilities("WEA", "STR")["home"]


def test_totals_include_the_overtime_goal() -> None:
    """A model stopping at regulation understates every Over."""
    model = TeamModel().fit(balanced_league())

    totals = model.total_probabilities("AVA", "AVB", line=5.5)
    matrix = model.scoreline_matrix("AVA", "AVB")
    regulation_over = sum(
        mass
        for i, row in enumerate(matrix)
        for j, mass in enumerate(row)
        if i + j > 5.5
    )

    assert totals["over"] > regulation_over


def test_totals_sum_to_one_across_over_under_and_push() -> None:
    model = TeamModel().fit(balanced_league())

    totals = model.total_probabilities("AVA", "AVB", line=5.5)

    assert totals["push"] == 0.0
    assert totals["over"] + totals["under"] == pytest.approx(1.0)


def test_a_whole_number_total_carries_a_push() -> None:
    model = TeamModel().fit(balanced_league())

    totals = model.total_probabilities("AVA", "AVB", line=6.0)

    assert totals["push"] > 0
    assert totals["over"] + totals["under"] == pytest.approx(1.0)


def test_a_higher_total_line_is_less_likely_to_go_over() -> None:
    model = TeamModel().fit(balanced_league())

    probabilities = [
        model.total_probabilities("AVA", "AVB", line=line)["over"]
        for line in (4.5, 5.5, 6.5, 7.5)
    ]

    assert probabilities == sorted(probabilities, reverse=True)


def test_an_unknown_team_is_priced_as_league_average() -> None:
    """A team the model has never seen is a real early-season state."""
    model = TeamModel().fit(balanced_league())

    home, away = model.expected_goals("NEW", "ALSO_NEW")

    assert home > away  # home advantage only
    assert home + away == pytest.approx(model.league_goals_per_game, rel=0.05)


def test_the_market_bundle_covers_every_team_market() -> None:
    model = TeamModel().fit(balanced_league())

    bundle = model.market_probabilities("STR", "WEA")

    assert set(bundle) == {"moneyline", "puck_line", "total_goals"}


def test_the_scoreline_matrix_holds_essentially_all_the_mass() -> None:
    """It is truncated at MAX_GOALS a side and renormalised downstream, so the
    residual must be small enough that the truncation cannot move a price."""
    model = TeamModel().fit(balanced_league())

    matrix = model.scoreline_matrix("STR", "WEA")
    total = sum(sum(row) for row in matrix)

    assert total > 0.99999


def test_every_market_probability_is_renormalised_to_sum_to_one() -> None:
    """The truncation must not leak into a published probability."""
    model = TeamModel().fit(balanced_league())

    moneyline = model.moneyline_probabilities("STR", "WEA")
    totals = model.total_probabilities("STR", "WEA", line=5.5)

    assert sum(moneyline.values()) == pytest.approx(1.0)
    assert totals["over"] + totals["under"] == pytest.approx(1.0)


def _docstring() -> str:
    """The module docstring with its line wrapping flattened.

    Asserting on wrapped prose otherwise fails on where the paragraph happened
    to break, which is a test failing on formatting rather than on meaning.
    """
    from nhl_betting_lab.models import team_model

    return " ".join(team_model.__doc__.split())


def test_the_empty_net_limitation_is_stated_rather_than_fudged() -> None:
    text = _docstring()

    assert "empty-net" in text.lower()
    assert "fitting the residual twice" in text


def test_the_docstring_records_that_its_own_prediction_was_wrong() -> None:
    """The measurement contradicted the reasoning, and the reasoning stays on
    the record rather than being quietly deleted."""
    text = _docstring()

    assert "says the opposite" in text
    assert "turned out backwards" in text
    assert "the measurement is what governs" in text
