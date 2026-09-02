"""The role-to-minutes translator, and the guards that keep it honest.

Two of these tests exist because of how this lab has been burned before. One
asserts that a table fitted before a date cannot see a single game on or
after it -- walk-forward or it is not a result. The other asserts that the
realised-rank reader refuses to run unless the caller says the word `oracle`
out loud, because a rank read off a finished game is exactly the kind of
information that has manufactured findings here four times.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nhl_betting_lab.models import role_minutes as rm


def _game(game_id: int, date: str, team: str, forwards: list[int], defence: list[int]):
    rows = []
    for i, seconds in enumerate(forwards):
        rows.append({
            "game_id": game_id, "date": date, "team": team, "role": "skater",
            "position": "C" if i % 2 else "L", "player_id": 100 + i,
            "toi_seconds": seconds,
        })
    for i, seconds in enumerate(defence):
        rows.append({
            "game_id": game_id, "date": date, "team": team, "role": "skater",
            "position": "D", "player_id": 200 + i, "toi_seconds": seconds,
        })
    return rows


def _logs(dates=("2024-10-01", "2024-10-03"), scale: float = 1.0, games: int = 120):
    """A synthetic league with a clean usage ladder, twelve forwards and six
    defencemen a side."""
    forwards = [1200, 1180, 1160, 1000, 990, 980, 820, 810, 800, 620, 610, 600]
    defence = [1400, 1380, 1150, 1140, 900, 890]
    rows = []
    for g in range(games):
        date = dates[g % len(dates)]
        rows.extend(
            _game(
                1000 + g, date, "AAA",
                [int(v * scale) + (g % 5) for v in forwards],
                [int(v * scale) + (g % 5) for v in defence],
            )
        )
    return pd.DataFrame(rows)


# -- the ranking ---------------------------------------------------------


def test_band_for_rank_puts_forwards_in_threes_and_defence_in_pairs() -> None:
    assert [rm.band_for_rank("F", r) for r in (1, 3, 4, 6, 7, 10)] == [
        "f1", "f1", "f2", "f2", "f3", "f4"
    ]
    assert [rm.band_for_rank("D", r) for r in (1, 2, 3, 5, 7)] == [
        "d1", "d1", "d2", "d3", "d4"
    ]


def test_a_thirteenth_forward_does_not_invent_a_fifth_line() -> None:
    assert rm.band_for_rank("F", 13) == "f4"
    assert rm.band_for_rank("D", 99) == "d4"


def test_a_rank_must_be_one_based_and_a_goalie_has_no_line() -> None:
    with pytest.raises(ValueError):
        rm.band_for_rank("F", 0)
    with pytest.raises(ValueError):
        rm.band_for_rank("G", 1)


def test_bands_rank_within_team_and_position_group() -> None:
    banded = rm.with_usage_bands(_logs(games=1))
    top_forward = banded[banded["player_id"] == 100].iloc[0]
    fourth_forward = banded[banded["player_id"] == 103].iloc[0]
    top_pair = banded[banded["player_id"] == 200].iloc[0]

    assert top_forward["ev_band"] == "f1"
    assert fourth_forward["ev_band"] == "f2"
    assert top_pair["ev_band"] == "d1"
    # The top defenceman outplays every forward, so a position-blind ranking
    # would have called him a first-line forward.
    assert top_pair["band_group"] == "D"


def test_the_power_play_proxy_is_team_wide_and_five_deep() -> None:
    banded = rm.with_usage_bands(_logs(games=1))
    first_unit = set(banded.loc[banded["pp_band"] == "pp1", "player_id"])

    assert len(first_unit) == rm.PP_UNIT_SIZE
    # Two defencemen out-skate every forward here, so a first unit that
    # ignored position would be all forwards. It is not.
    assert {200, 201} <= first_unit


def test_ranking_refuses_a_frame_without_the_columns_it_needs() -> None:
    with pytest.raises(KeyError, match="usage"):
        rm.with_usage_bands(pd.DataFrame({"game_id": [1], "team": ["AAA"]}))


def test_scratched_and_goalie_rows_never_receive_a_band() -> None:
    frame = _logs(games=1)
    frame.loc[len(frame)] = {
        "game_id": 1000, "date": "2024-10-01", "team": "AAA", "role": "goalie",
        "position": "G", "player_id": 900, "toi_seconds": 3600,
    }
    frame.loc[len(frame)] = {
        "game_id": 1000, "date": "2024-10-01", "team": "AAA", "role": "skater",
        "position": "C", "player_id": 901, "toi_seconds": 0,
    }
    banded = rm.with_usage_bands(frame)

    assert 900 not in set(banded["player_id"])
    assert 901 not in set(banded["player_id"])


# -- the fit -------------------------------------------------------------


def test_the_ladder_survives_the_fit_in_the_right_order() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    means = [table.distribution(b).mean_seconds for b in ("f1", "f2", "f3", "f4")]

    assert means == sorted(means, reverse=True)
    assert table.distribution("d1").mean_seconds > table.distribution("d2").mean_seconds


def test_a_fit_cannot_see_a_single_game_on_or_after_its_cutoff() -> None:
    """Walk-forward, asserted rather than assumed."""
    early = _logs(dates=("2024-10-01",), games=120)
    late = _logs(dates=("2024-12-01",), scale=1.5, games=120)
    late["game_id"] = late["game_id"] + 5000
    both = pd.concat([early, late], ignore_index=True)

    fitted = rm.fit_role_minutes(both, before="2024-12-01")
    everything = rm.fit_role_minutes(both, before="2025-01-01")

    assert fitted.n_games == len(rm.with_usage_bands(early))
    assert fitted.distribution("f1").mean_seconds < everything.distribution(
        "f1"
    ).mean_seconds
    assert fitted.fitted_before == "2024-12-01"


def test_a_fit_with_no_history_refuses_rather_than_returning_a_flat_prior() -> None:
    with pytest.raises(ValueError, match="needs history"):
        rm.fit_role_minutes(_logs(), before="2024-09-01")
    with pytest.raises(ValueError, match="cutoff"):
        rm.fit_role_minutes(_logs(), before="not a date")


def test_a_thin_cell_falls_back_to_a_wider_one_and_says_so() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    # This synthetic league dresses six defencemen a night, so `d4` is empty.
    fallback = table.distribution("d4")

    assert fallback.n >= rm.MINIMUM_CELL
    assert fallback.basis != "d4"
    assert fallback.label == "d4"


def test_power_play_distributions_announce_that_they_are_a_proxy() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")

    assert table.distribution("pp1").is_proxy is True
    assert table.distribution("f1").is_proxy is False


def test_a_label_this_lab_does_not_know_is_refused() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    with pytest.raises(ValueError, match="line label"):
        table.distribution("f9")
    with pytest.raises(ValueError, match="at least one"):
        table.distribution()


def test_labels_are_read_the_way_daily_faceoff_writes_them() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")

    assert table.distribution("F1").label == "f1"
    assert table.distribution("pp-1").label == "pp1"


# -- the distribution ----------------------------------------------------


def test_a_distribution_is_a_distribution_and_not_a_point_estimate() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    band = table.distribution("f1")

    assert band.quantile(0.1) < band.median_seconds < band.quantile(0.9)
    assert band.spread_seconds() > 0
    assert band.n > 0


def test_integration_nodes_are_a_partition_of_the_probability() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    band = table.distribution("f2")
    nodes = band.nodes(20)

    assert len(nodes) == 20
    assert pytest.approx(1.0) == sum(weight for _, weight in nodes)
    assert band.expectation(lambda s: s, count=200) == pytest.approx(
        band.mean_seconds, rel=0.02
    )


def test_expectation_of_a_curve_is_not_the_curve_of_the_expectation() -> None:
    """Jensen, which is the whole reason a scalar plug-in is wrong."""
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    band = table.distribution("f1")

    curved = band.expectation(lambda s: (s / 60.0) ** 2, count=101)
    plugged = (band.mean_seconds / 60.0) ** 2

    assert curved > plugged


def test_total_variance_exceeds_the_scalar_plug_in_by_the_missing_term() -> None:
    """`E[Var] + Var[E]`: the second term is what a scalar ice time discards."""
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    band = table.distribution("f1")
    rate_per_second = 8.0 / 3600.0

    def mean_fn(seconds: float) -> float:
        return rate_per_second * seconds

    total = band.total_variance(mean_fn, mean_fn, count=101)
    scalar = mean_fn(band.mean_seconds)

    assert total > scalar
    assert total == pytest.approx(scalar + band.sd_seconds**2 * rate_per_second**2, rel=0.1)


def test_a_quantile_needs_a_probability() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    with pytest.raises(ValueError, match="probability"):
        table.distribution("f1").quantile(1.4)
    with pytest.raises(ValueError, match="at least one node"):
        table.distribution("f1").nodes(0)


def test_sampling_stays_inside_the_band_it_was_fitted_on() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    band = table.distribution("f3")
    draws = band.sample(500, np.random.default_rng(0))

    assert draws.min() >= band.quantile(0.0)
    assert draws.max() <= band.quantile(1.0)
    assert len(draws) == 500


def test_describe_names_the_sample_size_beside_the_number() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")

    assert f"n={table.distribution('f1').n}" in table.distribution("f1").describe()
    assert "f1" in table.table()
    assert "proxy" in table.distribution("pp1").describe()


# -- the blend -----------------------------------------------------------


def test_the_blend_moves_the_location_and_keeps_the_spread() -> None:
    logs = _logs()
    banded = rm.with_usage_bands(logs)
    banded["trailing"] = banded["toi_seconds"] + 60.0
    table = rm.fit_role_minutes(
        logs, before="2024-10-05", ranked=banded, trailing_column="trailing"
    )
    prior = table.distribution("f1")
    blended = table.blend("f1", trailing_toi_seconds=1500.0)

    assert 0.0 <= table.blend_weight <= 1.0
    assert blended.mean_seconds > prior.mean_seconds
    assert blended.spread_seconds() == pytest.approx(prior.spread_seconds())
    assert "trailing" in blended.basis


def test_a_missing_trailing_mean_falls_back_to_the_band_rather_than_guessing() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")

    assert table.blend("f1", trailing_toi_seconds=None) == table.distribution("f1")
    assert table.blend("f1", trailing_toi_seconds=float("nan")) == table.distribution("f1")


def test_without_a_trailing_column_the_blend_weight_is_all_trailing() -> None:
    """No fit, no claim: the weight defaults to the incumbent, not to the band."""
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")

    assert table.blend_weight == 1.0
    assert table.blend_n == 0


# -- the oracle ----------------------------------------------------------


def test_realised_rank_will_not_be_read_without_saying_the_word_oracle() -> None:
    with pytest.raises(ValueError, match="oracle"):
        rm.realised_band(_logs())

    read = rm.realised_band(_logs(games=1), oracle=True)
    assert set(read["ev_band"]) >= {"f1", "f2", "d1"}


def test_the_module_says_out_loud_what_it_is_not_wired_into() -> None:
    """A translator nobody has measured for money must not read as shipped."""
    assert "wired into nothing" in rm.__doc__
    assert "ORACLE" in rm.__doc__


def test_a_night_of_labels_maps_to_a_night_of_distributions() -> None:
    table = rm.fit_role_minutes(_logs(), before="2024-10-05")
    out = rm.distributions_for_labels(table, [("f1", "pp1"), ("d2",), ("f4",)])

    assert [d.label for d in out] == ["f1+pp1", "d2", "f4"]
    assert all(d.n > 0 for d in out)
