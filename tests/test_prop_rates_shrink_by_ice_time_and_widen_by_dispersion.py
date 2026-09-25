"""The props model's shrinkage and its dispersion choice had tests that could not fail.

`PlayerPropsModel` has two levers that reach every skater price on the card
and every walk-forward prop sample, and both were guarded by tests whose
fixture made the right answer and a broken one the same number. Found by the
failure-shape audit and confirmed by three of three refuters each:

* **Shrinkage.** Each skater's per-60 rate is his group baseline plus
  `seconds / (seconds + SHRINKAGE_SECONDS)` of his measured deviation from it.
  The only test, `test_shrinkage_pulls_a_thin_record_toward_the_position_baseline`,
  asserted `min(baseline, raw) <= fitted <= max(baseline, raw)` — on a fixture
  whose two forwards have identical records, so the forward baseline IS the
  player's raw rate (11.0769 = 11.0769 = 11.0769) and the bound is an
  equality whatever the weight is. With no shrinkage (`weight = 1.0`, m20)
  and with total shrinkage (`weight = 0.0`, m21, every skater priced at his
  position baseline) the whole suite gave 1768 passed each. On the real logs
  (157,419 rows) m21 turns 646 distinct forward shot rates into one, 6.929 per
  60, and Brady Tkachuk (raw 13.5 SOG/60) and Lukas Rousek (raw 1.5) both
  price P(over 2.5 SOG) at 0.3575 where the real model says 0.6325 and 0.3126.
* **Dispersion.** `distribution` hands the stat's measured `Dispersion` to
  `distribution_for`, which picks a negative binomial where the data is
  overdispersed. The only test, `test_the_distribution_reflects_the_measured_dispersion`,
  asserted `isinstance(shape, (Poisson, NegativeBinomial))`, and every stat in
  its fixture is underdispersed (shots variance/mean 0.34 over 160 samples),
  so the right answer was itself a Poisson. With the dispersion dropped
  (`distribution_for(mean, None)`, m25, always Poisson) the whole suite gave
  1768 passed, and `test_a_poisson_sample_stores_no_dispersion` in the
  walk-forward tests (`isnan(v) or v > 0`) passed too. On the real logs
  shots_on_goal (r 4.37), blocked_shots (2.14), hits (1.63) and goalie_saves
  (29.1) all measure negative binomial, and every one of the 123,726 rows per
  skater market (6,759 for saves) in `prop_calibration_samples.csv` carries a
  finite r. Under m25 MacKinnon's SOG over 3.5 moves from 0.5386 to 0.6147
  and Saros's saves over 32.5 from 0.1927 to 0.1232, and every walk-forward
  sample would store NaN.

The production code was correct throughout; what was missing was a fixture
in which a broken version gives a different number. These tests build their
own leagues and assert their own premise first, so a later fixture edit
cannot quietly make them vacuous again:

* the shrinkage league has forwards and defencemen whose records differ from
  their group baseline on every stat, one forward with exactly the documented
  half-life of ice time, and forwards at four different ice times — so the
  fitted rate must sit strictly between baseline and raw, at an exact value
  computed here from the fixture's own totals;
* the dispersion league has an overdispersed shots column and an
  overdispersed starters' saves column beside underdispersed hits, plus a
  fourth-liner and a relief goalie that the documented filters exclude — so
  the model must choose a negative binomial with the measured r where the
  data is overdispersed, a Poisson where it is not, and the walk-forward must
  store exactly that r.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import pytest

from nhl_betting_lab.backtest import walk_forward as wf
from nhl_betting_lab.models import counts
from nhl_betting_lab.models.player_props import (
    GOALIE_STAT,
    SKATER_STATS,
    PlayerPropsModel,
)


#: The ice time at which a skater keeps exactly half of his measured deviation
#: from his position baseline, as `PlayerPropsModel.SHRINKAGE_SECONDS`
#: documents it ("about 65 games at 18 minutes"). Written out here rather than
#: read off the class: a changed half-life re-prices every skater in the
#: league, so it should arrive as a failing test to be justified.
DOCUMENTED_HALF_LIFE_SECONDS = 70_000

#: The counting stats a skater row carries; `points` is derived from two.
_COUNTED = ("shots_on_goal", "goals", "assists", "blocked_shots", "hits")


def _row(
    *,
    game: int,
    player_id: int,
    name: str,
    team: str,
    opponent: str,
    venue: str,
    position: str,
    toi: int,
    role: str = "skater",
    **stats: int,
) -> dict:
    row: dict = {
        "game_id": game,
        # Every other day, so no team is ever on a back-to-back and the rest
        # factors stay out of every price asserted here.
        "date": (date(2025, 1, 1) + timedelta(days=2 * game)).isoformat(),
        "player_id": player_id,
        "player": name,
        "role": role,
        "position": position,
        "team": team,
        "opponent": opponent,
        "venue": venue,
        "toi_seconds": toi,
        "power_play_goals": 0,
        "saves": 0,
        "shots_against": 0,
        **{stat: 0 for stat in _COUNTED},
    }
    row.update(stats)
    row["points"] = row["goals"] + row["assists"]
    return row


def _sides(game: int) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    home, away = ("TOR", "BOS") if game % 2 == 0 else ("BOS", "TOR")
    return (home, away, "home"), (away, home, "away")


# -- shrinkage -----------------------------------------------------------


@dataclass(frozen=True)
class Skater:
    """One skater of the shrinkage league: the same line every game he plays."""

    player_id: int
    name: str
    team: str
    position: str
    group: str
    games: int
    toi: int
    shots_on_goal: int
    goals: int
    assists: int
    blocked_shots: int
    hits: int

    @property
    def seconds(self) -> int:
        return self.games * self.toi

    def per_game(self, stat: str) -> int:
        if stat == "points":
            return self.goals + self.assists
        return int(getattr(self, stat))


SHRINKAGE_GAMES = 50

#: Four forwards at four different ice times and two defencemen, no two with
#: the same record. The Sniper plays exactly the documented half-life.
ROSTER: tuple[Skater, ...] = (
    Skater(1, "Sniper TOR", "TOR", "C", "F", 50, 1400, 6, 1, 1, 0, 1),
    Skater(2, "Grinder TOR", "TOR", "L", "F", 50, 900, 1, 0, 0, 1, 4),
    Skater(3, "Shutdown TOR", "TOR", "D", "D", 50, 1500, 1, 0, 0, 4, 3),
    Skater(101, "Winger BOS", "BOS", "R", "F", 50, 1200, 3, 0, 1, 1, 2),
    Skater(102, "Rover BOS", "BOS", "D", "D", 50, 1500, 3, 1, 1, 1, 1),
    Skater(103, "Callup BOS", "BOS", "C", "F", 16, 600, 3, 0, 0, 0, 3),
)

SKATERS = {skater.player_id: skater for skater in ROSTER}


def shrinkage_league() -> pd.DataFrame:
    rows: list[dict] = []
    for game in range(SHRINKAGE_GAMES):
        for team, opponent, venue in _sides(game):
            for skater in ROSTER:
                if skater.team != team or game >= skater.games:
                    continue
                rows.append(
                    _row(
                        game=game,
                        player_id=skater.player_id,
                        name=skater.name,
                        team=team,
                        opponent=opponent,
                        venue=venue,
                        position=skater.position,
                        toi=skater.toi,
                        **{stat: skater.per_game(stat) for stat in _COUNTED},
                    )
                )
            rows.append(
                _row(
                    game=game,
                    player_id=9 if team == "TOR" else 109,
                    name=f"Keeper {team}",
                    team=team,
                    opponent=opponent,
                    venue=venue,
                    position="G",
                    toi=3600,
                    role="goalie",
                    saves=27,
                    shots_against=30,
                )
            )
    return pd.DataFrame(rows)


def expected_rate(player_id: int, stat: str) -> tuple[float, float, float, float]:
    """(group baseline, raw rate, weight, shrunk rate), from the roster alone.

    Computed from the fixture's own totals with the documented half-life, not
    read off the fitted model, so the model has to arrive at it.
    """
    skater = SKATERS[player_id]
    group = [other for other in ROSTER if other.group == skater.group]
    baseline = (
        sum(other.games * other.per_game(stat) for other in group)
        / sum(other.seconds for other in group)
        * 3600.0
    )
    raw = skater.games * skater.per_game(stat) / skater.seconds * 3600.0
    weight = skater.seconds / (skater.seconds + DOCUMENTED_HALF_LIFE_SECONDS)
    return baseline, raw, weight, baseline + weight * (raw - baseline)


def _assert_fixture_separates_baseline_from_raw(player_ids: list[int]) -> None:
    """The premise the old test lacked: no raw rate equals its baseline."""
    for player_id in player_ids:
        for stat in SKATER_STATS:
            baseline, raw, _, _ = expected_rate(player_id, stat)
            assert abs(raw - baseline) > 0.05, (player_id, stat, baseline, raw)


def test_a_forward_with_the_documented_half_life_of_ice_time_keeps_exactly_half() -> None:
    """"Ice time at which a skater keeps half of his measured deviation from
    the position baseline": the Sniper plays exactly that much."""
    sniper = SKATERS[1]
    assert sniper.seconds == DOCUMENTED_HALF_LIFE_SECONDS
    _assert_fixture_separates_baseline_from_raw([1])

    model = PlayerPropsModel().fit(shrinkage_league())
    rates = model.skaters[1]

    # By hand: forwards shot 300 + 50 + 150 + 48 = 548 times in 70,000 +
    # 45,000 + 60,000 + 9,600 = 184,600 seconds, 10.6869 per 60; the Sniper
    # shot 300 in 70,000, 15.4286 per 60. Half of the gap is 13.0577.
    assert model.baselines["F"]["shots_on_goal"] == pytest.approx(
        548 / 184_600 * 3600, rel=1e-12
    )
    assert rates.per60["shots_on_goal"] == pytest.approx(
        (548 / 184_600 * 3600 + 300 / 70_000 * 3600) / 2, rel=1e-12
    )
    assert rates.per60["shots_on_goal"] == pytest.approx(13.0577310, abs=1e-6)

    for stat in SKATER_STATS:
        baseline, raw, weight, _ = expected_rate(1, stat)
        assert weight == 0.5
        fitted = rates.per60[stat]
        assert min(baseline, raw) < fitted < max(baseline, raw), stat
        assert fitted == pytest.approx((baseline + raw) / 2, rel=1e-12), stat


def test_every_forward_keeps_the_share_of_his_deviation_his_ice_time_earns() -> None:
    forwards = [skater.player_id for skater in ROSTER if skater.group == "F"]
    assert len({SKATERS[pid].seconds for pid in forwards}) == len(forwards)
    _assert_fixture_separates_baseline_from_raw(forwards)

    model = PlayerPropsModel().fit(shrinkage_league())

    for player_id in forwards:
        rates = model.skaters[player_id]
        assert rates.group == "F"
        for stat in SKATER_STATS:
            baseline, raw, _, shrunk = expected_rate(player_id, stat)
            assert model.baselines["F"][stat] == pytest.approx(baseline, rel=1e-12)
            fitted = rates.per60[stat]
            assert min(baseline, raw) < fitted < max(baseline, raw), (player_id, stat)
            assert fitted == pytest.approx(shrunk, rel=1e-12), (player_id, stat)


def test_more_ice_time_keeps_more_of_the_measured_deviation() -> None:
    """The documented shape, whatever the half-life: a player with more
    minutes behind his rate keeps more of it. The Callup's 9,600 seconds keep
    about an eighth; the Sniper's 70,000 keep half."""
    model = PlayerPropsModel().fit(shrinkage_league())
    forwards = sorted(
        (skater for skater in ROSTER if skater.group == "F"),
        key=lambda skater: skater.seconds,
    )

    kept = []
    for skater in forwards:
        baseline, raw, weight, _ = expected_rate(skater.player_id, "shots_on_goal")
        share = (model.skaters[skater.player_id].per60["shots_on_goal"] - baseline) / (
            raw - baseline
        )
        assert share == pytest.approx(weight, rel=1e-9), skater.name
        kept.append(share)

    assert [skater.name for skater in forwards] == [
        "Callup BOS",
        "Grinder TOR",
        "Winger BOS",
        "Sniper TOR",
    ]
    assert all(low < high for low, high in zip(kept, kept[1:])), kept
    assert 0.0 < kept[0] and kept[-1] < 1.0


def test_two_forwards_priced_for_the_same_minutes_get_their_own_shot_rates() -> None:
    """Through the pricing entry point: same team, same opponent, same venue,
    same minutes, so every factor but the player's own rate is common."""
    model = PlayerPropsModel().fit(shrinkage_league())

    def shots(player_id: int) -> float:
        value = model.expected_count(
            player_id,
            "shots_on_goal",
            opponent="BOS",
            venue="home",
            expected_toi_seconds=1080,
        )
        assert value is not None
        return value

    sniper, grinder = shots(1), shots(2)
    _, _, _, sniper_rate = expected_rate(1, "shots_on_goal")
    _, _, _, grinder_rate = expected_rate(2, "shots_on_goal")

    # 13.0577 against 8.0703 shots per 60: the Sniper is priced 1.618 times
    # the Grinder, not level with him and not at their raw 3.857 ratio.
    assert sniper / grinder == pytest.approx(sniper_rate / grinder_rate, rel=1e-12)
    assert sniper / grinder == pytest.approx(1.6180, abs=1e-4)
    assert (
        model.over_probability(
            1, "shots_on_goal", 2.5, opponent="BOS", venue="home",
            expected_toi_seconds=1080,
        )
        > model.over_probability(
            2, "shots_on_goal", 2.5, opponent="BOS", venue="home",
            expected_toi_seconds=1080,
        )
    )


def test_a_defenceman_shrinks_toward_the_defence_baseline_not_the_forwards() -> None:
    defencemen = [skater.player_id for skater in ROSTER if skater.group == "D"]
    _assert_fixture_separates_baseline_from_raw(defencemen)
    for stat in SKATER_STATS:
        forward_baseline, _, _, _ = expected_rate(1, stat)
        defence_baseline, _, _, _ = expected_rate(defencemen[0], stat)
        assert abs(forward_baseline - defence_baseline) > 0.05, stat

    model = PlayerPropsModel().fit(shrinkage_league())

    for player_id in defencemen:
        rates = model.skaters[player_id]
        assert rates.group == "D"
        for stat in SKATER_STATS:
            baseline, raw, _, shrunk = expected_rate(player_id, stat)
            assert model.baselines["D"][stat] == pytest.approx(baseline, rel=1e-12)
            fitted = rates.per60[stat]
            assert min(baseline, raw) < fitted < max(baseline, raw), (player_id, stat)
            assert fitted == pytest.approx(shrunk, rel=1e-12), (player_id, stat)


# -- dispersion ----------------------------------------------------------


DISPERSION_GAMES = 40


def _volume_shots(game: int) -> int:
    """Nothing one night, eight the next: variance far above the mean."""
    return 0 if game % 2 == 0 else 8


def _shooter_shots(game: int) -> int:
    return 1 if game % 2 == 0 else 5


def _starter_saves(game: int) -> tuple[int, int]:
    """(saves, shots against): a quiet night and a shooting gallery."""
    return (15, 17) if game % 2 == 0 else (40, 43)


def dispersion_league(games: int = DISPERSION_GAMES) -> pd.DataFrame:
    rows: list[dict] = []
    for game in range(games):
        for team, opponent, venue in _sides(game):
            side = {"game": game, "team": team, "opponent": opponent, "venue": venue}
            common = {"assists": 1, "blocked_shots": 1, "hits": 2}
            if team == "TOR":
                rows.append(_row(**side, player_id=1, name="Volume TOR", position="C",
                                 toi=1200, shots_on_goal=_volume_shots(game), **common))
                rows.append(_row(**side, player_id=2, name="Anchor TOR", position="D",
                                 toi=1300, shots_on_goal=2, **common))
                # Eight minutes a night: below the 600-second workload the
                # dispersion is measured on, so his zeros must not dilute it.
                rows.append(_row(**side, player_id=5, name="Fourth TOR", position="L",
                                 toi=480, shots_on_goal=0, **common))
                saves, against = _starter_saves(game)
                rows.append(_row(**side, player_id=9, name="Starter TOR", position="G",
                                 toi=3600, role="goalie", saves=saves,
                                 shots_against=against))
                if game % 4 == 0:
                    # A relief appearance: below the 1,800-second start the
                    # saves dispersion is measured on.
                    rows.append(_row(**side, player_id=19, name="Backup TOR",
                                     position="G", toi=1200, role="goalie",
                                     saves=5, shots_against=6))
            else:
                rows.append(_row(**side, player_id=101, name="Shooter BOS",
                                 position="R", toi=1200,
                                 shots_on_goal=_shooter_shots(game), **common))
                rows.append(_row(**side, player_id=102, name="Anchor BOS", position="D",
                                 toi=1300, shots_on_goal=2, **common))
                rows.append(_row(**side, player_id=109, name="Starter BOS",
                                 position="G", toi=3600, role="goalie", saves=28,
                                 shots_against=31))
    return pd.DataFrame(rows)


def _measured(values: list[int]) -> tuple[float, float, float]:
    """(mean, sample variance, negative binomial r), by the textbook."""
    mean = statistics.fmean(values)
    variance = statistics.variance(values)
    return mean, variance, mean * mean / (variance - mean)


def regular_shots(games: int = DISPERSION_GAMES) -> list[int]:
    """Every shots count from a skater night of 600 seconds or more."""
    return (
        [_volume_shots(game) for game in range(games)]
        + [_shooter_shots(game) for game in range(games)]
        + [2] * (2 * games)
    )


def starter_saves(games: int = DISPERSION_GAMES) -> list[int]:
    """Every saves count from a goalie night of 1,800 seconds or more."""
    return [_starter_saves(game)[0] for game in range(games)] + [28] * games


def _negative_binomial_over(mean: float, r: float, line: float) -> float:
    """P(X > line) on a half-point line, by the pmf's own recursion."""
    assert line % 1 == 0.5
    success = r / (r + mean)
    pmf = success**r
    below = pmf
    for k in range(1, int(math.floor(line)) + 1):
        pmf *= (k - 1 + r) / k * (1.0 - success)
        below += pmf
    return 1.0 - below


def _poisson_over(mean: float, line: float) -> float:
    assert line % 1 == 0.5
    pmf = math.exp(-mean)
    below = pmf
    for k in range(1, int(math.floor(line)) + 1):
        pmf *= mean / k
        below += pmf
    return 1.0 - below


def test_an_overdispersed_stat_is_priced_as_a_negative_binomial_with_the_measured_r() -> None:
    values = regular_shots()
    mean, variance, r = _measured(values)
    # The premise, by hand: 160 regular nights averaging 2.75 shots with
    # variance 910/159 = 5.72, twice the mean, so r = 2.75^2 / 2.97 = 2.54.
    assert len(values) == 160
    assert mean == 2.75
    assert variance == pytest.approx(910 / 159, rel=1e-12)
    assert variance / mean > 2.0
    assert r == pytest.approx(2.5435, abs=1e-4)
    # And the workload filter matters here: the fourth-liner's forty blanks
    # would measure a different r.
    assert abs(_measured(values + [0] * DISPERSION_GAMES)[2] - r) > 0.3

    model = PlayerPropsModel().fit(dispersion_league())

    measured = model.dispersion["shots_on_goal"]
    assert measured.samples == 160
    assert measured.mean == pytest.approx(mean, rel=1e-12)
    assert measured.variance == pytest.approx(variance, rel=1e-12)
    assert measured.overdispersed is True

    shape = model.distribution(1, "shots_on_goal", opponent="BOS", venue="home")
    assert type(shape) is counts.NegativeBinomial
    assert shape.r == pytest.approx(r, rel=1e-12)
    assert shape.mean == pytest.approx(
        model.expected_count(1, "shots_on_goal", opponent="BOS", venue="home"),
        rel=1e-12,
    )

    # The probability the card uses carries the negative binomial's tails:
    # at mean 2.87 it is 0.854 over 0.5 where a Poisson says 0.943, and 0.053
    # over 7.5 where a Poisson says 0.009. The separation margins are loose
    # enough to hold at any mean the shrinkage could land on (at the forward
    # baseline, 2.49, the gaps are 0.093 and 0.029), so this test answers only
    # to the dispersion.
    for line in (0.5, 2.5, 5.5, 7.5):
        over = model.over_probability(
            1, "shots_on_goal", line, opponent="BOS", venue="home"
        )
        assert over == pytest.approx(
            _negative_binomial_over(shape.mean, r, line), rel=1e-9
        ), line
    assert _poisson_over(shape.mean, 0.5) - _negative_binomial_over(
        shape.mean, r, 0.5
    ) > 0.05
    assert _negative_binomial_over(shape.mean, r, 7.5) - _poisson_over(
        shape.mean, 7.5
    ) > 0.02


def test_an_underdispersed_stat_in_the_same_fit_is_priced_as_a_poisson() -> None:
    """Two hits every night: variance zero, so a negative binomial here would
    be the model inventing a spread the data does not have."""
    model = PlayerPropsModel().fit(dispersion_league())
    assert model.dispersion["shots_on_goal"].overdispersed is True

    for stat in ("hits", "blocked_shots"):
        measured = model.dispersion[stat]
        assert measured.samples == 160
        assert measured.variance == 0.0
        assert measured.overdispersed is False

        shape = model.distribution(1, stat, opponent="BOS", venue="home")
        assert type(shape) is counts.Poisson, stat
        for line in (0.5, 1.5, 3.5):
            assert model.over_probability(
                1, stat, line, opponent="BOS", venue="home"
            ) == pytest.approx(_poisson_over(shape.mean, line), rel=1e-9), (stat, line)


def test_goalie_saves_are_priced_on_the_starters_measured_dispersion() -> None:
    values = starter_saves()
    mean, variance, r = _measured(values)
    # By hand: 80 starts averaging 27.75 saves with variance 6255/79 = 79.18,
    # so r = 27.75^2 / 51.43 = 14.97. The ten relief nights are not starts.
    assert len(values) == 80
    assert mean == 27.75
    assert variance == pytest.approx(6255 / 79, rel=1e-12)
    assert r == pytest.approx(14.9738, abs=1e-4)
    assert abs(_measured(values + [5] * 10)[2] - r) > 1.0

    model = PlayerPropsModel().fit(dispersion_league())

    measured = model.dispersion[GOALIE_STAT]
    assert measured.samples == 80
    assert measured.variance == pytest.approx(variance, rel=1e-12)

    shape = model.distribution(9, GOALIE_STAT, opponent="BOS", venue="home")
    assert type(shape) is counts.NegativeBinomial
    assert shape.r == pytest.approx(r, rel=1e-12)
    for line in (22.5, 26.5, 32.5):
        assert model.over_probability(
            9, GOALIE_STAT, line, opponent="BOS", venue="home"
        ) == pytest.approx(_negative_binomial_over(shape.mean, r, line), rel=1e-9)


def test_the_walk_forward_stores_the_measured_r_and_nan_only_for_a_poisson() -> None:
    """One refit on the forty games above, pricing the forty-first. The scorer
    rebuilds each shape from `mean` and `dispersion_r` alone, so a NaN where
    the fit was a negative binomial re-scores that market as a Poisson."""
    logs = dispersion_league(DISPERSION_GAMES + 1)
    last_day = str(logs["date"].max())
    shots_r = _measured(regular_shots())[2]
    saves_r = _measured(starter_saves())[2]

    samples, report = wf.generate_prop_samples(
        logs,
        minimum_history_games=DISPERSION_GAMES,
        refit_days=1,
        start_date=last_day,
    )

    assert report.refits == 1
    assert set(samples["date"]) == {last_day}

    by_market = {market: rows for market, rows in samples.groupby("market")}
    shots = by_market["shots_on_goal"]
    assert set(shots["player_id"]) == {1, 2, 5, 101, 102}
    assert shots["dispersion_r"].tolist() == pytest.approx(
        [shots_r] * len(shots), rel=1e-12
    )

    saves = by_market[GOALIE_STAT]
    assert set(saves["player_id"]) == {9, 109}
    assert saves["dispersion_r"].tolist() == pytest.approx(
        [saves_r] * len(saves), rel=1e-12
    )

    for market in ("hits", "blocked_shots", "points", "assists"):
        values = by_market[market]["dispersion_r"].tolist()
        assert len(values) == 5, market
        assert all(math.isnan(value) for value in values), market

    volume = shots[shots["player_id"] == 1].iloc[0]
    rebuilt = wf.distribution_from(volume["mean"], volume["dispersion_r"])
    assert type(rebuilt) is counts.NegativeBinomial
    assert rebuilt.over_probability(7.5) == pytest.approx(
        _negative_binomial_over(volume["mean"], shots_r, 7.5), rel=1e-9
    )
