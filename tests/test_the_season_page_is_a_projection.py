"""The Season page publishes a projection of the standings, and only that.

`web/build_season_json.py` plays the remaining schedule ten thousand times
and writes `data/season.json` for the site. These tests hold its arithmetic
to the league's own bookkeeping on a synthetic season, with no network:

* every simulated season awards two points a win and one an overtime loss,
  every team plays exactly its schedule, and the goals scored league-wide are
  the goals allowed;
* sixteen teams make the playoffs, four win a division, one wins the
  Presidents' Trophy, in every simulated season;
* a season under way starts from the table to date and never loses a point
  already banked;
* the file writer refuses a season it cannot vouch for (a missing team, odds
  that do not sum to sixteen);
* the availability list refuses an entry it could not apply.

The model's fit to real inputs is not tested here: it needs the network, and
its output is a projection whose quality only the season can judge.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"

DIVISIONS = {
    "E": ("Atlantic", "Metropolitan"),
    "W": ("Central", "Pacific"),
}


def _load_builder():
    if str(WEB) not in sys.path:
        sys.path.insert(0, str(WEB))
    spec = importlib.util.spec_from_file_location("_season_builder", WEB / "build_season_json.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_model(*, played_rounds: int, rounds: int = 6, seed: int = 7) -> dict:
    """32 teams in the league's alignment, a round-robin schedule of
    ``rounds`` games per opponent-slot, the first ``played_rounds`` already
    final with scores drawn at random."""
    rng = np.random.default_rng(seed)
    teams = []
    for conf, divs in DIVISIONS.items():
        for div in divs:
            for k in range(8):
                teams.append((f"{div[:2].upper()}{k}", conf, div))
    abbrs = [t[0] for t in teams]
    # pair every team with the next `rounds` teams round the circle: each team
    # plays `rounds` home games and `rounds` away games.
    games = []
    n = len(abbrs)
    for r in range(1, rounds + 1):
        for i, home in enumerate(abbrs):
            games.append(dict(home=home, away=abbrs[(i + r) % n], round=r))
    per_team = {a: 0 for a in abbrs}
    for g in games:
        per_team[g["home"]] += 1
        per_team[g["away"]] += 1
    assert len(set(per_team.values())) == 1
    games_per_team = per_team[abbrs[0]]

    now = {a: dict(gp=0, w=0, l=0, otl=0, pts=0, gf=0, ga=0, rw=0, row=0) for a in abbrs}
    remaining = []
    for j, g in enumerate(games):
        if g["round"] <= played_rounds:
            hg, ag = int(rng.poisson(3)), int(rng.poisson(3))
            if hg == ag:
                hg += 1  # overtime, home wins
                loser, winner, ot = g["away"], g["home"], True
            else:
                winner, loser = (g["home"], g["away"]) if hg > ag else (g["away"], g["home"])
                ot = False
            for a, gf, ga in ((g["home"], hg, ag), (g["away"], ag, hg)):
                now[a]["gp"] += 1; now[a]["gf"] += gf; now[a]["ga"] += ga
            now[winner]["w"] += 1; now[winner]["pts"] += 2; now[winner]["row"] += 1
            if not ot:
                now[winner]["rw"] += 1
                now[loser]["l"] += 1
            else:
                now[loser]["otl"] += 1; now[loser]["pts"] += 1
        else:
            remaining.append(dict(id=j, date=f"2026-11-{(j % 28) + 1:02d}", home=g["home"], away=g["away"], neutral=False))

    model_teams, info, players, goalies = {}, {}, {}, {}
    for a, conf, div in teams:
        strength = rng.normal(0, 0.15)
        model_teams[a] = dict(off=3.08 + strength, ga=3.08 - strength, td_off=3.0, bu_off=3.1, d_xgf=0.0, td_xga=3.0,
                              d_xga=0.0, goalie_gsax=0.0, gp=now[a]["gp"])
        info[a] = dict(abbrev=a, name=f"{a} Club", conf=conf, div=div, now=now[a],
                       last=dict(gp=82, pts=90, w=40, l=32, otl=10, gf=250, ga=250))
        players[a] = [dict(id=1, name=f"{a} Star", pos="C", age=27.0, toi=20.0, proj_gp=70, proj_g=30.0, proj_a=40.0,
                           proj_p=70.0, now=dict(gp=now[a]["gp"], g=1, a=2, p=3), last=None)]
        goalies[a] = [dict(name=f"{a} Starter", age=28.0, share=0.65, gsax60=0.05, sv=0.91,
                           now=dict(gs=int(now[a]["gp"] * 0.65), w=int(now[a]["w"] * 0.65), sv=None), last=None),
                      dict(name=f"{a} Backup", age=30.0, share=0.35, gsax60=-0.05, sv=0.9,
                           now=dict(gs=now[a]["gp"] - int(now[a]["gp"] * 0.65), w=now[a]["w"] - int(now[a]["w"] * 0.65), sv=None),
                           last=None)]
    return dict(asof="2026-11-01", season="20262027", games_per_team=games_per_team,
                state=dict(games_per_team=games_per_team, played=[], remaining=remaining),
                teams=model_teams, team_info=info, players=players, goalies=goalies, unknown=[], league_gpg=3.08)


@pytest.mark.parametrize("played_rounds", [0, 3])
def test_every_simulated_season_keeps_the_leagues_books(played_rounds: int) -> None:
    builder = _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415 - loaded off web/ above

    model = _synthetic_model(played_rounds=played_rounds)
    G = model["games_per_team"]
    result = simulate(model, sims=400, seed=1)
    teams = result["teams"]
    assert len(teams) == 32

    for t in teams:
        assert abs(t["w"] + t["l"] + t["otl"] - G) < 0.2, t  # each is rounded to a tenth
        assert abs(t["pts"] - (2 * t["w"] + t["otl"])) < 0.15, t
        assert t["pts_p10"] <= t["pts"] <= t["pts_p90"], t
        now = model["team_info"][t["abbrev"]]["now"]
        assert t["pts"] >= now["pts"] - 1e-9
        assert t["w"] >= now["w"] - 1e-9
    # goals scored are goals allowed, once every game is played
    assert abs(sum(t["gf"] for t in teams) - sum(t["ga_sim"] for t in teams)) <= 32
    # sixteen playoff places, four division titles, one Presidents' Trophy
    assert abs(sum(t["p_playoff"] for t in teams) - 16) < 0.02
    assert abs(sum(t["p_div"] for t in teams) - 4) < 0.02
    assert abs(sum(t["p_pres"] for t in teams) - 1) < 0.02
    assert abs(sum(t["p_last"] for t in teams) - 1) < 0.02
    # the file writer accepts what the simulation vouches for
    site = builder.compose(model, result, {"asOf": "2026-11-01"}, {}, generated_at="2026-11-01T14:00:00+00:00")
    builder.check(site)
    assert site["phase"] == ("preseason" if played_rounds == 0 else "regular")
    assert site["remainingGames"] == len(model["state"]["remaining"])
    assert len(site["teams"]) == 32 and site["teams"][0]["proj"]["pts"] >= site["teams"][-1]["proj"]["pts"]


def test_a_season_already_over_is_reported_not_simulated() -> None:
    _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=6)
    assert not model["state"]["remaining"]
    result = simulate(model, sims=50, seed=2)
    for t in result["teams"]:
        now = model["team_info"][t["abbrev"]]["now"]
        assert t["pts"] == now["pts"] and t["pts_p10"] == t["pts_p90"] == t["pts"]
    assert result["meta"]["remaining_games"] == 0


def test_the_writer_refuses_a_season_it_cannot_vouch_for() -> None:
    builder = _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=0)
    result = simulate(model, sims=50, seed=3)
    site = builder.compose(model, result, {}, {}, generated_at="2026-10-01T14:00:00+00:00")
    builder.check(site)

    short = json.loads(json.dumps(site))
    short["teams"] = short["teams"][:31]
    with pytest.raises(SystemExit, match="31 teams"):
        builder.check(short)

    skewed = json.loads(json.dumps(site))
    skewed["teams"][0]["odds"]["playoff"] += 0.5
    with pytest.raises(SystemExit, match="sum to"):
        builder.check(skewed)


def test_the_availability_list_refuses_an_entry_it_cannot_apply(tmp_path: Path) -> None:
    _load_builder()
    from season_sim.model import ModelError, load_injuries  # noqa: PLC0415

    good = tmp_path / "good.json"
    good.write_text(json.dumps({"returning": [{"name": "A Player", "team": "CHI", "born": "2000-01-01", "return": "2026-11-15"}],
                                "out": [{"name": "B Player", "team": "FLA", "return": "season"}]}), encoding="utf-8")
    assert load_injuries(good)["returning"][0]["return"] == "2026-11-15"

    no_birthday = tmp_path / "bad.json"
    no_birthday.write_text(json.dumps({"returning": [{"name": "A Player", "team": "CHI", "return": "2026-11-15"}]}), encoding="utf-8")
    with pytest.raises(ModelError, match="born"):
        load_injuries(no_birthday)

    bad_date = tmp_path / "date.json"
    bad_date.write_text(json.dumps({"out": [{"name": "B Player", "team": "FLA", "return": "next month"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_injuries(bad_date)


def test_the_committed_baseline_is_a_season_the_page_can_read() -> None:
    """`web/data/season.json` ships with the site as the fallback Publish Site
    keeps when no Season Sim run can be restored, so it must pass the same
    check a fresh build does."""
    builder = _load_builder()
    site = json.loads((WEB / "data" / "season.json").read_text(encoding="utf-8"))
    builder.check(site)
    assert site["games"] == 84 and site["sims"] >= 1000
    assert {t["div"] for t in site["teams"]} == {"Atlantic", "Metropolitan", "Central", "Pacific"}


def test_the_roster_notes_on_disk_parse() -> None:
    _load_builder()
    from season_sim.model import load_injuries  # noqa: PLC0415

    notes = load_injuries(PROJECT_ROOT / "data" / "season_sim" / "roster_notes.json")
    shares = notes["goalieShares"]
    assert len(shares) == 32
    for team, split in shares.items():
        assert abs(sum(split.values()) - 1) < 1e-6, team
