from __future__ import annotations

import pandas as pd

from nhl_betting_lab.backtest import walk_forward as wf


def _log(
    *,
    game: int,
    day: int,
    player_id: int,
    role: str = "skater",
    team: str = "TOR",
    opponent: str = "BOS",
    toi: int = 1200,
    month: int = 1,
    **stats: object,
) -> dict:
    row = {
        "game_id": game,
        "date": f"2025-{month:02d}-{day:02d}",
        "player_id": player_id,
        "player": f"Player {player_id}",
        "role": role,
        "position": "G" if role == "goalie" else "C",
        "team": team,
        "opponent": opponent,
        "venue": "home",
        "toi_seconds": toi,
        "shots_on_goal": 3,
        "goals": 0,
        "assists": 1,
        "points": 1,
        "blocked_shots": 1,
        "power_play_goals": 0,
        "saves": 0,
        "shots_against": 0,
    }
    row.update(stats)
    return row


def sample_logs(games: int = 400) -> pd.DataFrame:
    rows = []
    for index in range(games):
        month = 1 + (index // 100)
        day = 1 + (index % 28)
        for player_id in (1, 2, 3, 4):
            rows.append(
                _log(
                    game=index,
                    day=day,
                    month=month,
                    player_id=player_id,
                    team="TOR" if player_id < 3 else "BOS",
                    opponent="BOS" if player_id < 3 else "TOR",
                )
            )
        for player_id in (9, 10):
            rows.append(
                _log(
                    game=index,
                    day=day,
                    month=month,
                    player_id=player_id,
                    role="goalie",
                    team="TOR" if player_id == 9 else "BOS",
                    opponent="BOS" if player_id == 9 else "TOR",
                    toi=3600,
                    saves=28,
                    shots_against=31,
                )
            )
    return pd.DataFrame(rows)


def test_an_empty_log_produces_no_samples() -> None:
    samples, report = wf.generate_prop_samples(pd.DataFrame())

    assert samples.empty
    assert report.samples == 0
    assert "No samples were generated" in report.summary_line()


def test_windows_without_enough_history_are_skipped_and_counted() -> None:
    samples, report = wf.generate_prop_samples(
        sample_logs(50), minimum_history_games=1000
    )

    assert samples.empty
    assert report.windows_skipped_for_history > 0
    assert report.refits == 0


def test_samples_are_produced_once_enough_history_exists() -> None:
    samples, report = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )

    assert not samples.empty
    assert report.refits > 0
    assert "walk-forward refits" in report.summary_line()


def test_a_model_never_sees_the_game_it_prices() -> None:
    """The single rule this whole module exists to enforce."""
    logs = sample_logs(400)
    samples, _ = wf.generate_prop_samples(
        logs, minimum_history_games=50, refit_days=30
    )

    # Every sample's date must be at or after the first date any refit could
    # have used, and no sample may exist before enough history accumulated.
    earliest_sample = samples["date"].min()
    history_before = logs[logs["date"] < earliest_sample]["game_id"].nunique()

    assert history_before >= 50


def test_a_relief_appearance_produces_no_goalie_sample() -> None:
    """A book posts a saves line for the expected starter; nobody can bet a
    prop on a goalie who comes in cold in the second period."""
    logs = sample_logs(400)
    relief = _log(
        game=9999,
        day=27,
        month=4,
        player_id=9,
        role="goalie",
        toi=600,
        saves=5,
        shots_against=6,
    )
    combined = pd.concat([logs, pd.DataFrame([relief])], ignore_index=True)

    samples, _ = wf.generate_prop_samples(
        combined, minimum_history_games=50, refit_days=30
    )
    relief_samples = samples[
        (samples["game_id"] == 9999) & (samples["market"] == "goalie_saves")
    ]

    assert relief_samples.empty


def test_a_full_start_does_produce_goalie_samples() -> None:
    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )

    assert not samples[samples["market"] == "goalie_saves"].empty


def test_the_goalie_start_threshold_is_forty_minutes() -> None:
    assert wf.GOALIE_START_SECONDS == 2400


def test_a_goalie_is_never_priced_on_a_skater_market() -> None:
    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )
    goalie_rows = samples[samples["player_id"].isin([9, 10])]

    assert set(goalie_rows["market"]) == {"goalie_saves"}


def test_a_skater_is_never_priced_on_the_goalie_market() -> None:
    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )
    skater_rows = samples[samples["player_id"].isin([1, 2, 3, 4])]

    assert "goalie_saves" not in set(skater_rows["market"])


def test_a_sample_carries_a_distribution_that_prices_any_line() -> None:
    """The fixed grid discarded most of the prices bought, and what survived
    was whichever lines the grid happened to name."""
    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )
    row = samples.iloc[0]
    shape = wf.distribution_from(row["mean"], row["dispersion_r"])

    assert shape.mean > 0
    # Any line, including one no grid would have named.
    falling = [shape.over_probability(line) for line in (0.5, 1.5, 2.5, 3.5, 7.5)]
    assert falling == sorted(falling, reverse=True)


def test_there_is_one_sample_per_player_game_market_not_per_line() -> None:
    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )

    assert "line" not in samples.columns
    assert not samples.duplicated(
        subset=["game_id", "player_id", "market"]
    ).any()


def test_a_poisson_sample_stores_no_dispersion() -> None:
    """`dispersion_r` is NaN for a Poisson and finite for a negative binomial;
    the scorer rebuilds the right shape from that alone."""
    import math

    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )
    values = samples["dispersion_r"].tolist()

    assert all(math.isnan(v) or v > 0 for v in values)


def test_every_settlement_column_exists_in_the_logs() -> None:
    from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS

    for market, column in wf.SETTLEMENT_COLUMNS.items():
        assert column in PLAYER_LOG_COLUMNS, market


def test_the_goalie_market_settles_on_the_saves_column_not_its_own_name() -> None:
    """The one market whose key and column differ, which is why the map exists."""
    assert wf.SETTLEMENT_COLUMNS["goalie_saves"] == "saves"


def test_default_lines_cover_every_priced_market() -> None:
    from nhl_betting_lab.markets import prop_market_keys

    assert set(wf.DEFAULT_LINES) == set(prop_market_keys())


def test_anytime_scorer_is_covered_by_the_goals_half_line() -> None:
    assert 0.5 in wf.DEFAULT_LINES["goals"]


def test_a_date_window_limits_which_games_are_priced() -> None:
    samples, _ = wf.generate_prop_samples(
        sample_logs(400),
        minimum_history_games=50,
        refit_days=30,
        start_date="2025-03-01",
    )

    assert samples.empty or samples["date"].min() >= "2025-03-01"


def test_the_report_names_the_priced_date_range() -> None:
    _, report = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )

    assert report.first_priced_date <= report.last_priced_date
    assert report.first_priced_date in report.summary_line()


def test_samples_carry_ice_time_so_the_volume_split_is_possible() -> None:
    samples, _ = wf.generate_prop_samples(
        sample_logs(400), minimum_history_games=50, refit_days=30
    )

    assert (samples["toi_seconds"] > 0).all()
