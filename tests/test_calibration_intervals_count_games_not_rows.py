"""Both calibration reports printed a "95%" interval that counted rows as trials.

`props_calibration.md` prices every player-game at every line of a fixed grid
(2 lines for goals and assists, 5 for hits and goalie saves), and all of a
player-game's lines land in one ice-time bucket and share one stat line. The
"95% on observed" column was `wilson_interval(hits, rows)`, the ⚠ floor was
`rows >= 100`, and the headline said "2,508,315 walk-forward samples": the
goalie "pulled or partial" row printed 830 samples, 8.5% .. 12.6%, from 166
goalie-games, and a 20-goalie bucket would have cleared the 100-sample floor
with 100 rows. `team_markets_measurement.md` did the same on its reliability
table: every selection at every grid line of a game shares one scoreline,
total_goals holds 160,446 held-out rows over 3,658 games, and up to 13 rows
of one game sit in one bucket — so the 0-10% and 90-100% intervals were
about 1.9x too narrow and covered about 71%, not 95%. Found by the
failure-shape audit (findings 26 and 27, confirmed 3/3 and 2/3).

What these tests hold: the interval counts each game once — every line of a
player-game, every player in one game, every selection of one game — through
the real report paths; duplicating a player-game's lines moves neither the
interval nor the floor; the ⚠ floor and the market floor count player-games;
the tables print the player-games and games behind each row; and where rows
are independent, or anti-correlated, the interval is exactly today's Wilson
interval on rows, never narrower.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from nhl_betting_lab import stats
from nhl_betting_lab.backtest.walk_forward import DEFAULT_LINES
from nhl_betting_lab.reports import props_calibration as props
from nhl_betting_lab.reports import team_markets_measurement as tmm


PULLED = "goalie, pulled or partial (under 50 min)"
FULL = "goalie, full game (50 min+)"


def _day(index: int) -> str:
    return (date(2025, 10, 1) + timedelta(days=index)).isoformat()


# --------------------------------------------------------------------------
# Props: the stored-distribution shape the cached samples CSV really has, so
# every goalie-game goes through `expand_to_lines` onto the 5-line grid.
# --------------------------------------------------------------------------


def _goalie_samples(
    *, pulled: int, scored_days: int = 25, warmup_days: int = 7
) -> pd.DataFrame:
    """Six starters a day through the warm-up, then five full games a day plus
    one pulled goalie on each of the first `pulled` scored days."""
    rows = []
    saves = (18.0, 23.0, 26.0, 28.0, 30.0, 33.0)
    for day_index in range(warmup_days + scored_days):
        scored = day_index - warmup_days
        slots = [3600] * 6 if scored < 0 else [3600] * 5
        if 0 <= scored < pulled:
            slots.append(1800)
        for slot, seconds in enumerate(slots):
            rows.append(
                {
                    "date": _day(day_index),
                    "game_id": 2025020000 + 3 * day_index + slot // 2,
                    "player_id": 8470000 + slot,
                    "market": "goalie_saves",
                    "mean": 27.0,
                    "dispersion_r": float("nan"),
                    "actual": (
                        (12.0, 21.0)[day_index % 2]
                        if seconds < 3000
                        else saves[(day_index + slot) % 6]
                    ),
                    "toi_seconds": seconds,
                }
            )
    return pd.DataFrame(rows)


def _volume_row(item: props.MarketCalibration, bucket: str) -> dict:
    return next(row for row in item.volume_rows if row["bucket"] == bucket)


def _ice_time_line(rendered: str, bucket: str) -> str:
    section = rendered.split("### By ice time", 1)[1].split("###", 1)[0]
    return next(line for line in section.splitlines() if line.startswith(f"| {bucket}"))


def test_twenty_pulled_goalies_do_not_clear_the_bucket_floor_as_a_hundred_lines() -> None:
    report = props.build_calibration_report(
        _goalie_samples(pulled=20), minimum_fit_samples=200
    )
    goalies = report.markets[0]
    pulled = _volume_row(goalies, PULLED)
    rendered = props.render_calibration(report)

    assert DEFAULT_LINES["goalie_saves"] and len(DEFAULT_LINES["goalie_saves"]) == 5
    # 100 line samples are 20 goalie-games: below the floor, and flagged.
    assert pulled["enough"] is False
    assert "⚠" in _ice_time_line(rendered, PULLED)
    assert (pulled["samples"], pulled["player_games"]) == (100, 20)
    # The control: 125 full-game goalies clear it, unflagged.
    full = _volume_row(goalies, FULL)
    assert (full["samples"], full["player_games"], full["enough"]) == (625, 125, True)
    assert "⚠" not in _ice_time_line(rendered, FULL)
    assert "below 100 player-games" in rendered


def test_the_headline_counts_player_games_beside_line_samples() -> None:
    frame = _goalie_samples(pulled=20)
    report = props.build_calibration_report(frame, minimum_fit_samples=200)
    rendered = props.render_calibration(report)

    # 7 warm-up days of 6, 20 days of 6, 5 days of 5.
    assert len(frame) == 187
    assert report.total_samples == 935
    assert report.total_player_games == 187
    assert report.summary_line().startswith(
        "935 walk-forward line samples from 187 player-game predictions"
    )
    assert report.markets[0].player_games == 145
    header = next(line for line in rendered.splitlines() if line.startswith("| Market |"))
    assert "| Player-games |" in header
    assert "| `goalie_saves` (Goalie saves) | 725 | 145 |" in rendered


def test_a_market_of_few_player_games_shows_no_reliability_table() -> None:
    """25 scored goalie-games are 125 line samples, which cleared the old
    100-sample market floor and printed a reliability table."""
    report = props.build_calibration_report(
        _goalie_samples(pulled=0, scored_days=5), minimum_fit_samples=200
    )
    goalies = report.markets[0]
    rendered = props.render_calibration(report)

    assert (goalies.samples, goalies.player_games) == (125, 25)
    assert "too few for a reliability table" in rendered
    assert "### Reliability" not in rendered


def _skater_lines(
    *, copies: int = 1, players_per_game: int = 1, days: int = 20
) -> pd.DataFrame:
    """Four games a day in one ice-time bucket, already on the line grid.

    Each player-game carries `copies` identical lines, and every player of a
    game shares that game's outcome — the two ways rows stop being trials.
    """
    rows = []
    for day_index in range(days):
        for slot in range(4):
            game = 4 * day_index + slot
            won = (game * 7) % 10 < 3
            for player in range(players_per_game):
                for _ in range(copies):
                    rows.append(
                        {
                            "date": _day(day_index),
                            "game_id": 2025020000 + game,
                            "player_id": 8480000 + 50 * game + player,
                            "market": "shots_on_goal",
                            "line": 2.5,
                            "model_probability": 0.3,
                            "outcome": won,
                            "toi_seconds": 1000,
                        }
                    )
    return pd.DataFrame(rows)


def _only_bucket(frame: pd.DataFrame) -> dict:
    report = props.build_calibration_report(frame, minimum_fit_samples=1)
    (row,) = report.markets[0].volume_rows
    assert row["bucket"] == "16-20 min"
    return row


def _scored_hits(frame: pd.DataFrame) -> tuple[int, int]:
    """Hits and rows after the first date, which is the warm-up here."""
    scored = frame[frame["date"] > frame["date"].min()]
    return int(scored["outcome"].sum()), len(scored)


def test_repeating_a_player_games_lines_moves_neither_the_interval_nor_the_floor() -> None:
    single = _only_bucket(_skater_lines(copies=1))
    quadruple = _only_bucket(_skater_lines(copies=4))

    assert quadruple["samples"] == 4 * single["samples"] == 4 * 76
    assert (quadruple["observed_low"], quadruple["observed_high"]) == pytest.approx(
        (single["observed_low"], single["observed_high"]), abs=1e-12
    )
    assert quadruple["enough"] is single["enough"] is False
    assert quadruple["player_games"] == single["player_games"] == 76


def test_one_line_per_player_game_keeps_todays_wilson_interval() -> None:
    frame = _skater_lines(copies=1)
    row = _only_bucket(frame)
    hits, count = _scored_hits(frame)

    assert (row["samples"], row["games"]) == (count, count)
    assert (row["observed_low"], row["observed_high"]) == stats.wilson_interval(
        hits, count
    )


def test_the_players_of_one_game_are_one_trial_between_them() -> None:
    """Five players sharing one game's outcome are one game, not five trials.

    Clustering on the player-game alone would treat them as five."""
    frame = _skater_lines(players_per_game=5)
    row = _only_bucket(frame)
    hits, count = _scored_hits(frame)

    assert (row["samples"], row["player_games"], row["games"]) == (count, 380, 76)
    assert (row["observed_low"], row["observed_high"]) == pytest.approx(
        stats.wilson_interval(hits // 5, 76), abs=1e-12
    )


# --------------------------------------------------------------------------
# Team markets: every selection at every line of one game shares its score.
# --------------------------------------------------------------------------


def _team_rows(games_per_day: int = 10, days: int = 21) -> pd.DataFrame:
    """Ten `over` rows per game in the 90-100% bucket and, on even games,
    three `under` rows in the 0-10% bucket — each game's rows share one
    outcome, as rows at neighbouring lines of one scoreline do."""
    rows = []
    for day_index in range(days):
        for slot in range(games_per_day):
            game = games_per_day * day_index + slot
            over_won = game % 13 != 0
            base = {
                "date": _day(day_index),
                "game_id": 2025020000 + game,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "total_goals",
                "push": False,
            }
            for line in range(10):
                rows.append(
                    {**base, "selection": "over", "line": line + 0.5,
                     "model_probability": 0.95, "outcome": over_won}
                )
            if game % 2 == 0:
                for line in range(3):
                    rows.append(
                        {**base, "selection": "under", "line": line + 7.5,
                         "model_probability": 0.05, "outcome": not over_won}
                    )
    return pd.DataFrame(rows)


def _reliability_lines(rendered: str, market: str) -> dict[str, list[str]]:
    section = rendered.split(f"### `{market}`", 1)[1].split("\n## ", 1)[0]
    cells = {}
    for line in section.splitlines():
        if line.startswith("| ") and "%-" in line.split("|")[1]:
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            cells[parts[0]] = parts
    return cells


def _scored_games(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["date"] > frame["date"].min()]


def test_ten_rows_of_one_game_are_one_trial_in_the_team_reliability_table() -> None:
    frame = _team_rows()
    report = tmm.build_team_measurement(frame, minimum_fit_samples=10)
    rendered = tmm.render_team_measurement(report)
    scored = _scored_games(frame)
    over = scored[scored["selection"] == "over"]
    hit_games = int(over.groupby("game_id")["outcome"].first().sum())

    low, high = stats.wilson_interval(hit_games, 200)
    row = _reliability_lines(rendered, "total_goals")["90%-100%"]
    assert row[-1] == f"{low:.1%} .. {high:.1%}"
    (bucket,) = [b for b in report.markets[0].reliability if b.label == "90%-100%"]
    assert (bucket.observed_low, bucket.observed_high) == pytest.approx(
        (low, high), abs=1e-12
    )


def test_the_team_reliability_table_prints_the_games_behind_each_row() -> None:
    report = tmm.build_team_measurement(_team_rows(), minimum_fit_samples=10)
    rendered = tmm.render_team_measurement(report)
    rows = _reliability_lines(rendered, "total_goals")

    header = next(
        line for line in rendered.splitlines() if line.startswith("| Bucket |")
    )
    assert header.split("|")[3].strip() == "Games"
    assert rows["90%-100%"][1:3] == ["2,000", "200"]
    assert rows["0%-10%"][1:3] == ["300", "100"]


def _moneyline(count: int = 3000) -> pd.DataFrame:
    """One row per game: nothing is shared, so nothing should change."""
    return pd.DataFrame(
        [
            {
                "date": f"2025-{1 + index // 700:02d}-{1 + index % 27:02d}",
                "game_id": index,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "model_probability": (0.35, 0.55, 0.62)[index % 3],
                "outcome": index % 20 < 11,
                "push": False,
            }
            for index in range(count)
        ]
    )


def test_one_row_per_game_keeps_todays_wilson_interval() -> None:
    report = tmm.build_team_measurement(_moneyline(), minimum_fit_samples=300)
    rendered = tmm.render_team_measurement(report)
    rows = _reliability_lines(rendered, "moneyline")

    assert len(report.markets[0].reliability) == 3
    for bucket in report.markets[0].reliability:
        expected = stats.wilson_interval(
            int(round(bucket.observed * bucket.count)), bucket.count
        )
        assert bucket.clusters == bucket.count
        assert (bucket.observed_low, bucket.observed_high) == expected
        assert rows[bucket.label][-1] == f"{expected[0]:.1%} .. {expected[1]:.1%}"


def test_an_anti_correlated_pair_from_one_game_is_never_narrower_than_rows() -> None:
    """Over 5.5 and under 6.5 of one game both sit in 40-50% and rarely both
    win. The game-clustered variance is below the binomial one there; the
    interval keeps the Wilson interval on rows rather than narrowing."""
    rows = []
    for index in range(600):
        total = (3, 4, 5, 6, 7, 8)[index % 6]
        base = {
            "date": f"2025-{1 + index // 300:02d}-{1 + index % 25:02d}",
            "game_id": index, "home_team": "TOR", "away_team": "BOS",
            "market": "total_goals", "push": False, "model_probability": 0.45,
        }
        rows.append({**base, "selection": "over", "line": 5.5, "outcome": total >= 6})
        rows.append({**base, "selection": "under", "line": 6.5, "outcome": total <= 6})
    report = tmm.build_team_measurement(pd.DataFrame(rows), minimum_fit_samples=100)
    (bucket,) = report.markets[0].reliability
    hits = int(round(bucket.observed * bucket.count))

    assert bucket.clusters * 2 == bucket.count
    assert (bucket.observed_low, bucket.observed_high) == stats.wilson_interval(
        hits, bucket.count
    )


# --------------------------------------------------------------------------
# The interval itself.
# --------------------------------------------------------------------------


def test_clusters_of_one_are_exactly_the_wilson_interval() -> None:
    clusters = [(1, 1)] * 37 + [(0, 1)] * 163

    assert stats.clustered_wilson_interval(clusters) == stats.wilson_interval(37, 200)


def test_identical_rows_inside_a_cluster_count_once() -> None:
    clusters = [(5, 5)] * 30 + [(0, 5)] * 70

    assert stats.clustered_wilson_interval(clusters) == pytest.approx(
        stats.wilson_interval(30, 100), abs=1e-12
    )


def test_a_rate_of_zero_or_one_counts_each_cluster_once() -> None:
    """With no outcome varying, no design effect can be measured, so the
    interval does not assume the rows inside a cluster are independent."""
    assert stats.clustered_wilson_interval([(0, 5)] * 20) == stats.wilson_interval(0, 20)
    assert stats.clustered_wilson_interval([(4, 4)] * 20) == stats.wilson_interval(20, 20)


def test_a_single_cluster_is_one_trial() -> None:
    assert stats.clustered_wilson_interval([(2, 5)]) == stats.wilson_interval_on_rate(
        0.4, 1.0
    )
    assert stats.clustered_wilson_interval([]) == (0.0, 1.0)


def test_negative_correlation_inside_clusters_never_narrows_below_rows() -> None:
    clusters = [(1, 2)] * 150 + [(2, 2)] * 50

    assert stats.clustered_wilson_interval(clusters) == stats.wilson_interval(250, 400)


def test_the_effective_trials_arithmetic_is_wilsons_own() -> None:
    """`wilson_interval` is the fractional-trials helper at a whole number,
    bit for bit, so no existing caller's interval moved."""
    for hits, trials in ((0, 5), (1, 3), (5, 5), (37, 200), (12_345, 67_890)):
        assert stats.wilson_interval(hits, trials) == stats.wilson_interval_on_rate(
            hits / trials, trials
        )
