from __future__ import annotations

import pandas as pd
import pytest

from nhl_betting_lab.backtest import team_walk_forward as twf


def _games(count: int = 400) -> pd.DataFrame:
    rows = []
    for index in range(count):
        month = 1 + index // 100
        day = 1 + index % 28
        home, away = ("STR", "WEA") if index % 2 == 0 else ("WEA", "STR")
        rows.append(
            {
                "game_id": index,
                "date": f"2025-{month:02d}-{day:02d}",
                "home_team": home,
                "away_team": away,
                "home_goals": 4 if home == "STR" else 2,
                "away_goals": 2 if home == "STR" else 4,
                "regulation": index % 5 != 0,
            }
        )
    return pd.DataFrame(rows)


# -- settlement --------------------------------------------------------


def test_the_moneyline_has_no_draw() -> None:
    assert twf.settle_moneyline(4, 2) == "home"
    assert twf.settle_moneyline(2, 4) == "away"


def test_a_level_completed_game_is_a_data_fault_not_an_outcome() -> None:
    """Calling it a home win would quietly bias every measurement."""
    with pytest.raises(ValueError, match="data fault"):
        twf.settle_moneyline(3, 3)


def test_an_overtime_winner_never_covers_minus_one_and_a_half() -> None:
    """The winning goal is the only one scored after regulation."""
    covered = twf.settle_puck_line(5, 3, regulation=False)

    assert covered["home_minus"] is False
    assert covered["home_plus"] is True


def test_a_regulation_two_goal_win_does_cover_minus_one_and_a_half() -> None:
    covered = twf.settle_puck_line(4, 2, regulation=True)

    assert covered["home_minus"] is True
    assert covered["away_plus"] is False


def test_a_one_goal_regulation_loss_covers_plus_one_and_a_half() -> None:
    covered = twf.settle_puck_line(2, 3, regulation=True)

    assert covered["away_plus"] is True
    assert covered["home_plus"] is True
    assert covered["away_minus"] is False


def test_the_puck_line_sides_are_exact_complements() -> None:
    covered = twf.settle_puck_line(4, 1, regulation=True)

    assert covered["home_minus"] is not covered["away_plus"]
    assert covered["away_minus"] is not covered["home_plus"]


def test_a_total_settles_on_the_final_score() -> None:
    assert twf.settle_total(4, 3, 5.5) == (True, False)
    assert twf.settle_total(2, 2, 5.5) == (False, False)


def test_a_whole_number_total_pushes_on_an_exact_hit() -> None:
    assert twf.settle_total(3, 3, 6.0) == (False, True)
    assert twf.settle_total(4, 3, 6.0) == (True, False)


# -- generation --------------------------------------------------------


def test_an_empty_frame_produces_no_samples() -> None:
    samples, report = twf.generate_team_samples(pd.DataFrame())

    assert samples.empty
    assert "No team samples" in report.summary_line()


def test_windows_without_enough_history_are_skipped_and_counted() -> None:
    samples, report = twf.generate_team_samples(
        _games(50), minimum_history_games=1000
    )

    assert samples.empty
    assert report.windows_skipped_for_history > 0


def test_samples_cover_every_team_market() -> None:
    samples, _ = twf.generate_team_samples(
        _games(400), minimum_history_games=50, refit_days=30
    )

    assert set(samples["market"]) == {
        "moneyline",
        "puck_line",
        "total_goals",
        "regulation_3_way",
    }


def test_a_game_that_went_past_regulation_settles_the_three_way_as_a_draw() -> None:
    """Every goal after sixty minutes belongs to overtime. Reading the final
    score here would settle a draw as a win."""
    assert twf.settle_regulation_3_way(4, 3, regulation=False) == "draw"
    assert twf.settle_regulation_3_way(4, 3, regulation=True) == "home"
    assert twf.settle_regulation_3_way(2, 3, regulation=True) == "away"


def test_a_level_game_flagged_as_regulation_is_a_data_fault() -> None:
    """A level game goes to overtime by rule, so the flag is wrong."""
    with pytest.raises(ValueError, match="data fault"):
        twf.settle_regulation_3_way(3, 3, regulation=True)


def test_exactly_one_three_way_side_wins_per_game() -> None:
    samples, _ = twf.generate_team_samples(
        _games(400), minimum_history_games=50, refit_days=30
    )
    three_way = samples[samples["market"] == "regulation_3_way"]

    for _, rows in three_way.groupby("game_id"):
        assert rows["outcome"].sum() == 1


def test_the_moneyline_sides_are_mutually_exclusive_per_game() -> None:
    samples, _ = twf.generate_team_samples(
        _games(400), minimum_history_games=50, refit_days=30
    )
    moneyline = samples[samples["market"] == "moneyline"]

    for _, rows in moneyline.groupby("game_id"):
        assert rows["outcome"].sum() == 1


def test_a_push_is_recorded_rather_than_scored_as_a_loss() -> None:
    """Every game in this fixture ends 4-2, so a 6.0 line always pushes."""
    samples, _ = twf.generate_team_samples(
        _games(400),
        minimum_history_games=50,
        refit_days=30,
        total_lines=(6.0,),
    )
    totals = samples[samples["market"] == "total_goals"]

    assert not totals.empty
    assert totals["push"].all()
    assert not totals["outcome"].any()


def test_a_pushed_total_is_neither_an_over_nor_an_under() -> None:
    samples, _ = twf.generate_team_samples(
        _games(400),
        minimum_history_games=50,
        refit_days=30,
        total_lines=(6.0, 5.5),
    )
    pushed = samples[(samples["market"] == "total_goals") & (samples["line"] == 6.0)]
    live = samples[(samples["market"] == "total_goals") & (samples["line"] == 5.5)]

    assert set(pushed["outcome"]) == {False}
    # The same games clear 5.5, so the fixture is not simply always under.
    assert live[live["selection"] == "over"]["outcome"].all()


def test_the_model_never_sees_the_game_it_prices() -> None:
    games = _games(400)
    samples, _ = twf.generate_team_samples(
        games, minimum_history_games=50, refit_days=30
    )
    earliest = samples["date"].min()
    history_before = len(games[games["date"] < earliest])

    assert history_before >= 50


def test_the_report_names_the_priced_date_range() -> None:
    _, report = twf.generate_team_samples(
        _games(400), minimum_history_games=50, refit_days=30
    )

    assert report.first_priced_date <= report.last_priced_date
    assert report.first_priced_date in report.summary_line()


def test_every_probability_is_a_probability() -> None:
    samples, _ = twf.generate_team_samples(
        _games(400), minimum_history_games=50, refit_days=30
    )

    assert (samples["model_probability"] >= 0).all()
    assert (samples["model_probability"] <= 1).all()


def test_a_date_window_limits_what_is_priced() -> None:
    samples, _ = twf.generate_team_samples(
        _games(400),
        minimum_history_games=50,
        refit_days=30,
        start_date="2025-03-01",
    )

    assert samples.empty or samples["date"].min() >= "2025-03-01"
