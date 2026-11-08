"""The award races read what the voters reward, and say it in plain English.

Cooper (2026-11-08): "How can we improve the award section of the website to
display the award rankings in a presentable manner and also have accurate
projections like PostHockey.com does for all the awards". Its published method
(the award race's changelog, 2026-11-06 and 11-07) fits each race to the
ballots since 2010-11 on the box score, the club's record and how much a club
leans on a player: whether he leads it in points and by how much, his share of
last season's vote, a Selke that counts scoring in full only up to first-line
level, and no feature past three standard deviations. These tests hold those
pieces, the back-filled ballots, the new Lady Byng race and the page's
one-line reasons.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from test_the_season_page_is_a_projection import _synthetic_model

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

from season_sim import award_fit as af  # noqa: E402
from season_sim import awards as aw  # noqa: E402
from season_sim.awards import award_stats  # noqa: E402
from season_sim.model import is_rookie  # noqa: E402


def test_every_race_reads_the_new_features_and_starts_where_the_old_model_did() -> None:
    assert {"team_lead", "team_pct", "prior_vote"} <= set(af.FEATURES["hart"])
    assert {"team_pct", "prior_vote"} <= set(af.FEATURES["norris"]) and {"team_pct", "prior_vote"} <= set(af.FEATURES["vezina"])
    assert "offence" in af.FEATURES["selke"] and "points_pg" not in af.FEATURES["selke"]
    assert set(af.FEATURES["lady_byng"]) >= {"points_pg", "pim"}
    for award, feats in af.FEATURES.items():
        assert len(af.DEFAULTS[award]) == len(feats), award
    # The new features start at zero weight: the fit, not a guess, moves them.
    for f in ("team_lead", "team_pct", "prior_vote"):
        assert af.DEFAULTS["hart"][af.FEATURES["hart"].index(f)] == 0.0
    assert set(aw.AWARDS) == set(af.FEATURES)


def test_no_feature_counts_past_three_standard_deviations() -> None:
    x = np.array([0.0] * 50 + [100.0])
    assert af._z(x).max() == pytest.approx(af.Z_CAP)


def test_the_selke_counts_scoring_in_full_only_up_to_first_line_level() -> None:
    pts = np.array([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 1.5])
    X = af.design("selke", dict(points_pg=pts, defence=np.zeros(7), faceoffs=np.zeros(7), pk=np.zeros(7),
                                puck=np.zeros(7), games=np.ones(7)))
    off = X[0, :, af.FEATURES["selke"].index("offence")]
    z = af._z(pts)
    assert off[-1] == pytest.approx(af.OFFENCE_KNEE + af.OFFENCE_SLOPE * (z[-1] - af.OFFENCE_KNEE))
    assert off[0] == pytest.approx(z[0])  # below the knee, in full


def test_leading_your_own_team_and_last_seasons_vote_are_read() -> None:
    assert af.team_lead(100, 80) == pytest.approx(np.log(100 / 80))
    assert af.team_lead(60, 90) < 0 and af.team_lead(200, 10) == af.TEAM_LEAD_CLIP
    shares = af.vote_shares([dict(player="Connor McDavid", votes=300), dict(player="Leon Draisaitl", votes=100)])
    assert shares == {"connor mcdavid": 0.75, "leon draisaitl": 0.25}
    assert af.previous_season("20262027") == "20252026"
    # A history season's skaters carry their club lead and record.
    sk = [dict(playerId=i, skaterFullName=f"P {i}", teamAbbrevs="AAA" if i < 3 else "BBB", positionCode="C",
               gamesPlayed=80, points=[90, 60, 40, 70, 70, 10][i], penaltyMinutes=8, timeOnIcePerGame=1000) for i in range(6)]
    hist = dict(season="20242025", skaters=sk, goalies=[], born={}, prior_gp={}, berths={"AAA": True, "BBB": False},
                games=82, team_pct={"AAA": 0.62, "BBB": 0.45}, moneypuck=None, goalie_mp=None)
    rows = {r["id"]: r for r in af.season_fields(hist, award_stats, is_rookie)["_all"]}
    assert rows[0]["team_lead"] == pytest.approx(np.log(90 / 60)) and rows[1]["team_lead"] < 0
    assert rows[3]["team_lead"] == pytest.approx(0.0)  # tied for his club's lead
    assert rows[0]["team_pct"] == 0.62 and rows[0]["pim"] == pytest.approx(0.1)


def test_last_seasons_vote_lifts_a_candidate_in_the_fit_data() -> None:
    sk = [dict(playerId=i, skaterFullName=f"P {i}", teamAbbrevs=f"T{i}", positionCode="C", gamesPlayed=82,
               points=100, penaltyMinutes=0, timeOnIcePerGame=1000) for i in range(4)]
    hist = dict(season="20242025", skaters=sk, goalies=[], born={}, prior_gp={}, berths={}, games=82,
                moneypuck=None, goalie_mp=None)
    fields = af.season_fields(hist, award_stats, is_rookie)
    (X, v), missed = af.fit_data("hart", [dict(player="P 0", team="T0", pos="C", votes=10)], fields, {"p 1": 0.6})
    col = af.FEATURES["hart"].index("prior_vote")
    keys = [r["key"] for r in fields["hart"]]
    assert missed == 0 and X[0, keys.index("p 1"), col] == pytest.approx(0.6) and X[0, keys.index("p 0"), col] == 0.0


def test_the_lady_byng_is_simulated_and_ranked_without_any_odds() -> None:
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=2)
    result = simulate(model, sims=150, seed=7)
    stats = {}
    for i, (t, q) in enumerate((t, q) for t, qs in model["players"].items() for q in qs if not q.get("filler")):
        q.setdefault("id", 10_000 + i)
        stats[q["id"]] = dict(gp=20, gp_now=10, points=q["proj_p"] / 84, pim=(3.0 if i % 2 else 0.1), toi=18.0)
    sim = aw.simulated_shares(model, result, stats, prior_votes={"hart": {}})
    assert "lady_byng" in sim and sum(sim["lady_byng"]["share"].values()) == pytest.approx(1.0, abs=1e-6)
    players = [dict(name=q["name"], pos=q["pos"], team=t, p=q["proj_p"], stats=stats[q["id"]])
               for t, qs in model["players"].items() for q in qs if not q.get("filler")]
    from datetime import date  # noqa: PLC0415
    tr = aw.tracker("lady_byng", {}, players, {}, today=date(2026, 11, 8), sim=sim)
    assert len(tr["rows"]) == aw.ROWS and tr["weights"]["model"] == 1.0 and not tr["stale"]
    assert tr["about"] == "Sportsmanship with skill"


def test_each_row_says_why_in_plain_english() -> None:
    def sk(name, team, p, gp=20, **st):
        return dict(name=name, team=team, stats=dict(now=dict(gp=gp, g=p // 3, a=p - p // 3, p=p, pim=4, toi=24.5, fo=0.55), **st))

    mcd, drai = sk("Connor McDavid", "EDM", 34), sk("Leon Draisaitl", "EDM", 27)
    line = aw.why_line("hart", mcd, None, mates=[mcd, drai], playoff=0.81, games=84)
    assert line == "34 points in 20 games, on pace for 143, leads his team by 7, team 81% to make the playoffs"
    line = aw.why_line("hart", drai, None, mates=[mcd, drai], playoff=0.81, games=84)
    assert "7 behind McDavid on his own team" in line
    assert aw.why_line("norris", sk("Quinn Hughes", "MIN", 20, defence=0.1), None, mates=[], playoff=None, games=84) \
        == "20 points in 20 games, 24.5 minutes a night, fewer chances against than his teammates"
    assert "55% on faceoffs" in aw.why_line("selke", sk("Nick Suzuki", "MTL", 15, pk=1.8), None, mates=[], playoff=None, games=84)
    g = dict(name="Igor Shesterkin", now=dict(gs=14, w=10, sv=0.927), gsax60=0.4)
    assert aw.why_line("vezina", None, g, mates=[], playoff=None, games=84) == \
        "10 wins in 14 starts, .927 save percentage, rated 0.40 goals a game better than an average goalie"
    assert aw.why_line("lady_byng", sk("Jack Hughes", "NJD", 22), None, mates=[], playoff=None, games=84) == \
        "22 points and 4 penalty minutes in 20 games"
    assert aw.why_line("hart", dict(name="X", stats={}), None, mates=[], playoff=None, games=84) == ""


def test_an_aging_poll_fades_instead_of_flagging_the_race_stale() -> None:
    from datetime import date as _date

    assert aw.poll_fade(0) == 1.0 and aw.poll_fade(aw.POLL_FULL_DAYS) == 1.0
    assert 0 < aw.poll_fade(28) < 1
    assert aw.poll_fade(aw.POLL_GONE_DAYS) == 0.0 and aw.poll_fade(None) == 0.0
    spec = {"hart": {
        "odds": [{"book": "B", "date": "2026-11-07", "lines": [{"name": "Connor McDavid", "team": "EDM", "odds": -150},
                                                              {"name": "Nathan MacKinnon", "team": "COL", "odds": 400}]}],
        "poll": {"outlet": "P", "date": "2026-09-01", "entries": [{"name": "Nathan MacKinnon", "team": "COL", "points": 50}]},
    }}
    tr = aw.tracker("hart", spec, [], {}, today=_date(2026, 11, 8))
    poll = [s for s in tr["sources"] if s["kind"] == "poll"][0]
    assert not tr["stale"] and poll["used"] is False and tr["weights"]["poll"] == 0.0
