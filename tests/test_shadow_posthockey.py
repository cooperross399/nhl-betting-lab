"""PostHockey's glossary in the shadow model: context xG and shot-by-shot talent.

Cooper asked on 2026-10-08 for the knowledge of posthockey.com/glossary to go
into the model. What is buildable from the free play-by-play went into the
shadow model, beside the card: an expected-goals model with prior-event
context, Bayesian shooter and goalie talent, shooter-adjusted xGF/xGA,
GSAx(sh), GSAx+ and the A-F goalie tiers. These tests pin what those pieces
do, and that none of them moves the ratings the site and the card read.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS, TEAM_GAME_COLUMNS
from nhl_betting_lab.shadow.play_by_play import game_events, prior_context
from nhl_betting_lab.shadow.talent import add_talent, goalie_tier, gsax_plus
from nhl_betting_lab.shadow.xg import XgModel, context_design_matrix, design_matrix

from test_shadow_stats import _payload, _play, _script, _synthetic_season


def test_an_attempt_right_after_a_neutral_zone_play_is_a_rush() -> None:
    before = (1, 100, "takeaway", "HOM", 0.0, 0.0, "N")
    context = prior_context(before, team="HOM", clock=103, x=60.0, y=0.0)
    assert context["prior_event"] == "takeaway"
    assert context["prior_same_team"] is True
    assert context["prior_seconds"] == 3.0
    assert context["prior_feet"] == 60.0
    assert context["rush"] is True
    # The same play, too long ago, is not a rush.
    assert prior_context(before, team="HOM", clock=110, x=60.0, y=0.0)["rush"] is False
    # An opponent's offensive-zone play is in the shooter's own end.
    away = (1, 100, "giveaway", "AWY", -70.0, 0.0, "O")
    assert prior_context(away, team="HOM", clock=102, x=60.0, y=0.0)["rush"] is True
    assert prior_context(None, team="HOM", clock=5, x=60.0, y=0.0)["prior_event"] == "none"


def test_the_feed_stamps_the_prior_play_and_the_score_on_every_attempt() -> None:
    plays = [
        _play("faceoff", 1, 0, xCoord=0, yCoord=0, zoneCode="N", eventOwnerTeamId=1),
        _play("goal", 1, 3, scoringPlayerId=11, xCoord=70, yCoord=0, shotType="wrist"),
        _play("hit", 1, 30, xCoord=60, yCoord=10, zoneCode="O", eventOwnerTeamId=1),
        _play("shot-on-goal", 1, 32, shootingPlayerId=11, xCoord=75, yCoord=5, shotType="wrist"),
        _play("shot-on-goal", 2, 10, shootingPlayerId=21, xCoord=-75, yCoord=5, shotType="wrist"),
    ]
    shots = game_events(_payload(2024020001, plays)).shots
    first, second, third = shots
    assert first["prior_event"] == "faceoff" and first["rush"] is True
    assert first["score_diff"] == 0
    assert second["prior_event"] == "hit" and second["prior_seconds"] == 2.0
    assert second["rush"] is False
    assert second["score_diff"] == 1
    # A new period starts with nothing before it, and the away side trails.
    assert third["prior_event"] == "none"
    assert third["score_diff"] == -1


def test_context_xg_learns_that_a_rush_scores_more_and_the_plain_model_is_untouched() -> None:
    rng = np.random.default_rng(4)
    n = 8000
    rush = rng.uniform(size=n) < 0.2
    distance = rng.uniform(5, 50, n)
    p = 1 / (1 + np.exp(-(0.2 - 0.1 * distance + 1.0 * rush)))
    shots = pd.DataFrame(
        {
            "game_id": 2023020001,
            "distance": distance,
            "angle": rng.uniform(0, 60, n),
            "rebound": False,
            "empty_net": False,
            "shot_type": "wrist",
            "strength": "5v5",
            "unblocked": True,
            "goal": rng.uniform(size=n) < p,
            "prior_event": np.where(rush, "takeaway", "faceoff"),
            "prior_same_team": True,
            "prior_seconds": np.where(rush, 2.0, 20.0),
            "prior_feet": 40.0,
            "rush": rush,
            "score_diff": 0,
            "period": 1,
        }
    )
    model = XgModel.fit(shots, design=context_design_matrix)
    on_rush = model.predict(shots[shots["rush"]]).mean()
    settled = model.predict(shots[~shots["rush"]]).mean()
    assert on_rush > 1.5 * settled
    # A frame with no context columns still scores, as no context.
    bare = shots.drop(columns=["prior_event", "prior_same_team", "prior_seconds",
                               "prior_feet", "rush", "score_diff", "period"])
    assert context_design_matrix(bare).shape[1] > design_matrix(bare).shape[1]


def _talent_frame(goals_by_shooter: dict[int, list[bool]], p: float = 0.1) -> pd.DataFrame:
    rows = []
    for shooter, outcomes in goals_by_shooter.items():
        for k, scored in enumerate(outcomes):
            rows.append(
                {"game_id": 2024020001 + k, "date": f"2024-10-{(k % 28) + 1:02d}",
                 "game_seconds": shooter, "season": 20242025, "shooter_id": shooter,
                 "goalie_id": 99, "unblocked": True, "empty_net": False,
                 "goal": scored, "xg_ctx": p}
            )
    return pd.DataFrame(rows)


def test_talent_moves_with_finishing_shrinks_small_samples_and_reads_only_earlier_shots() -> None:
    hot = [True, False, False] * 60  # one in three against a 10% expectation
    frame = _talent_frame({1: hot, 2: [True, False, False]})
    scored, shooters, goalies = add_talent(frame, base="xg_ctx", order="date")
    assert shooters[1].mean > 0.2
    # Three shots barely move a shooter off the prior.
    assert abs(shooters[2].mean) < shooters[1].mean / 3
    # The goalie who let all those in rates below average.
    assert goalies[99].mean < 0
    # Each shot carries the talent before it: the first is the prior, and
    # every later one is the posterior after the shot before it.
    mine = scored[scored["shooter_id"] == 1].sort_values(["date", "game_id"])
    assert mine["mu_shooter"].iat[0] == 0.0
    assert np.allclose(mine["mu_shooter"].to_numpy()[1:], mine["mu_shooter_after"].to_numpy()[:-1])
    # Shooter-adjusted xG on a positive talent is above the base.
    assert (mine["xg_sh"].iloc[1:] >= mine["xg_ctx"].iloc[1:]).all()


def test_talent_is_recentred_each_season_and_an_empty_net_teaches_nothing() -> None:
    frame = _talent_frame({1: [True, False] * 50, 2: [False] * 100})
    later = frame.copy()
    later["season"] = 20252026
    later["date"] = "2025-11-01"
    later["empty_net"] = True
    _, shooters, _ = add_talent(pd.concat([frame, later], ignore_index=True))
    # Both re-centred around zero, and the empty-net season changed nobody.
    assert math.isclose(shooters[1].mean + shooters[2].mean, 0.0, abs_tol=1e-9)
    assert shooters[1].mean > 0 > shooters[2].mean


def test_goalie_tiers_and_gsax_plus_follow_the_glossary() -> None:
    assert goalie_tier(0.10, 0.05) == "A"
    assert goalie_tier(-0.10, 0.05) == "F"
    assert goalie_tier(0.03, 0.05) == "B"
    assert goalie_tier(-0.03, 0.05) == "D"
    assert goalie_tier(0.01, 0.05) == "C"
    scaled = gsax_plus(pd.Series([-10.0, 0.0, 10.0]))
    assert math.isclose(scaled.mean(), 100.0)
    assert math.isclose(scaled.std(ddof=0), 15.0)


def _write_inputs(tmp_path: Path):
    rng = np.random.default_rng(7)
    teams = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
    payloads, team_rows, log_rows = [], [], []
    for year in (2023, 2024):
        p, t, logs = _synthetic_season(rng, year, 9, teams)
        payloads += p
        team_rows += t
        log_rows += logs
    raw = tmp_path / "raw"
    cache = raw / "nhl" / "play_by_play"
    cache.mkdir(parents=True)
    for payload in payloads:
        (cache / f"{payload['id']}.json").write_text(json.dumps(payload))
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(team_rows, columns=list(TEAM_GAME_COLUMNS)).to_csv(processed / "team_games.csv", index=False)
    pd.DataFrame(log_rows, columns=list(PLAYER_LOG_COLUMNS)).to_csv(processed / "player_game_logs.csv", index=False)
    return raw, processed


def test_the_full_run_measures_the_posthockey_variants_and_moves_no_rating(tmp_path) -> None:
    raw, processed = _write_inputs(tmp_path)
    script = _script()
    common = ["--processed-dir", str(processed), "--raw-dir", str(raw)]

    assert script.main(common + ["--output-dir", str(tmp_path / "a"), "--tables-only"]) == 0
    ratings = (processed / script.RATINGS_FILE).read_text()
    plain = pd.read_csv(processed / "shadow_team_games.csv")

    assert script.main(common + ["--output-dir", str(tmp_path / "b")]) == 0
    full = pd.read_csv(processed / "shadow_team_games.csv")
    result = json.loads((tmp_path / "b" / "shadow_stats.json").read_text())

    assert {e["variant"] for e in result["team"]} >= {"xg_context_luck", "xg_shooter_gsax"}
    assert {e["variant"] for e in result["props"]["goals"]} >= {"ixg_context_finishing", "ixg_talent"}
    assert result["context_xg_seasons"]
    # The plain columns, the shorthanded ones included, are what the
    # tables-only run (the site's and the card's) wrote.
    for column in ("xgf", "xga", "goalie_xga", "goalie_ga", "gf", "xga_sh", "ga_sh"):
        assert np.allclose(plain[column], full[column]), column
    assert plain["xgf_adj"].isna().all() and full["xgf_adj"].notna().all()
    # The site's ratings come only from the tables-only path, and it was not
    # rewritten by the full run.
    assert (processed / script.RATINGS_FILE).read_text() == ratings
    report = (tmp_path / "b" / "shadow_stats.md").read_text()
    assert "PostHockey" in report
