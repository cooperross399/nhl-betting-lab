"""The Season page's playoff bracket and trophy odds follow the league's rules.

Cooper asked (2026-10-26) for the season simulation to predict trophy
winners and playoff matchups, and for its team strengths to come from the
same PostHockey-style ratings the card prices on. These tests hold, on
synthetic seasons with no network:

* the bracket is seeded in the NHL's format: three per division, two wild
  cards per conference, the better division winner against the second wild
  card, second against third, home ice to the better record;
* a best-of-seven is won by a coin-flip team half the time, more often by
  the better team, and more often with home ice;
* every simulated season crowns exactly eight first-round winners, four
  conference finalists, two finalists and one champion, and a team's odds
  shrink round by round;
* each award's odds over every candidate sum to one, ties split;
* the Calder list follows the NHL's eligibility rule;
* the card's ratings are blended in only when they are current, with their
  five-game form taken out;
* the page renders the new sections through its own code, and still renders
  a file written before they existed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from test_the_season_page_is_a_projection import WEB, _load_builder, _synthetic_model


def _sim():
    _load_builder()
    from season_sim import simulate as sim  # noqa: PLC0415 - loaded off web/ above

    return sim


# -- seeding ----------------------------------------------------------------


def test_the_bracket_is_seeded_in_the_nhl_format() -> None:
    sim = _sim()
    # one conference, two divisions of eight, one simulated season; the key
    # is the standings order (higher is better)
    div = np.array(["A"] * 8 + ["B"] * 8)
    points = np.array([110, 100, 95, 94, 93, 60, 50, 40,     # A: A0 A1 A2, then A3 A4 chase
                       105, 99, 90, 92.5, 70, 65, 55, 45]).astype(float)
    # B3 (92.5) is below B2 (90)? no: order inside B is by key, so B's top
    # three are B0 105, B1 99, B3 92.5; B2 90 falls to the wild-card race.
    key = points[None, :]
    cols = np.arange(16)
    seeded = sim.seed_conference(key, div, cols)
    series = [(int(a[0]), int(b[0])) for a, b in seeded["series"]]
    wc1, wc2 = int(seeded["wildcards"][0][0]), int(seeded["wildcards"][1][0])
    assert (wc1, wc2) == (3, 4)  # A3 94 and A4 93, ahead of B2 90
    # A0 (110) is the better division winner, so it meets the second wild card
    assert series[0] == (0, wc2)
    assert series[1] == (1, 2)
    assert series[2] == (8, wc1)
    assert series[3] == (9, 11)


def test_the_weaker_division_winner_meets_the_first_wild_card() -> None:
    sim = _sim()
    div = np.array(["A"] * 8 + ["B"] * 8)
    points = np.array([100, 98, 97, 96, 95, 50, 49, 48, 112, 90, 80, 70, 60, 50, 40, 30], float)
    seeded = sim.seed_conference(points[None, :], div, np.arange(16))
    (b_win, b_opp) = seeded["series"][2]
    (a_win, a_opp) = seeded["series"][0]
    assert int(b_win[0]) == 8 and int(b_opp[0]) == int(seeded["wildcards"][1][0])  # B0 is better: WC2
    assert int(a_win[0]) == 0 and int(a_opp[0]) == int(seeded["wildcards"][0][0])  # A0 gets WC1


# -- series -----------------------------------------------------------------


def test_series_probabilities_are_sane() -> None:
    sim = _sim()
    assert sim.series_win_probability(0.5, 0.5) == pytest.approx(0.5)
    # 0.6 a game, home or away: the textbook 0.710
    assert sim.series_win_probability(0.6, 0.6) == pytest.approx(0.71021, abs=1e-4)
    assert sim.series_win_probability(1.0, 1.0) == pytest.approx(1.0)
    # home ice in a coin-flip series is worth something, and only a little
    edge = float(sim.series_win_probability(0.55, 0.45))
    assert 0.5 < edge < 0.53
    grid = np.linspace(0.05, 0.95, 19)
    assert np.all(np.diff(sim.series_win_probability(grid, grid)) > 0)
    # a game between equals is a coin flip; a better side wins more
    assert sim.game_win_probability(np.array(3.0), np.array(3.0)) == pytest.approx(0.5)
    assert sim.game_win_probability(np.array(3.4), np.array(2.8)) > 0.55


def test_every_simulated_postseason_crowns_one_champion() -> None:
    sim = _sim()
    model = _synthetic_model(played_rounds=2)
    result = sim.simulate(model, sims=600, seed=4)
    teams = result["teams"]
    for field, want in (("p_r1", 8), ("p_r2", 4), ("p_final", 2), ("p_cup", 1)):
        assert sum(t[field] for t in teams) == pytest.approx(want, abs=2e-3), field
    for t in teams:
        assert t["p_cup"] <= t["p_final"] <= t["p_r2"] <= t["p_r1"] <= t["p_playoff"] + 1e-9, t
    for c in ("E", "W"):
        conf = {a for a, i in model["team_info"].items() if i["conf"] == c}
        assert sum(t["p_final"] for t in teams if t["abbrev"] in conf) == pytest.approx(1.0, abs=2e-3)
    slots = result["playoffs"]["slots"]
    assert len(slots) == 8 and all(s["matchups"] for s in slots)
    for s in slots:
        assert sum(m["p"] for m in s["matchups"]) <= 1 + 1e-9
        div = s["label"].split(" ")[0]
        if "wild card" not in s["label"]:
            # second v third: both from the slot's own division
            for m in s["matchups"]:
                assert model["team_info"][m["a"]]["div"] == div == model["team_info"][m["b"]]["div"]
        else:
            for m in s["matchups"]:
                assert model["team_info"][m["a"]]["div"] == div
    for m in result["playoffs"]["finals"]:
        assert model["team_info"][m["a"]]["conf"] != model["team_info"][m["b"]]["conf"]


def test_a_better_team_wins_the_cup_more_often() -> None:
    sim = _sim()
    model = _synthetic_model(played_rounds=0)
    best = max(model["teams"], key=lambda a: model["teams"][a]["off"] - model["teams"][a]["ga"])
    worst = min(model["teams"], key=lambda a: model["teams"][a]["off"] - model["teams"][a]["ga"])
    result = sim.simulate(model, sims=800, seed=5)
    by = {t["abbrev"]: t for t in result["teams"]}
    assert by[best]["p_cup"] > by[worst]["p_cup"]


# -- trophies ---------------------------------------------------------------


def test_award_odds_over_every_candidate_sum_to_one(monkeypatch) -> None:
    sim = _sim()
    monkeypatch.setattr(sim, "TROPHY_ROWS", 10_000)
    model = _synthetic_model(played_rounds=2)
    # make one team's star a clear favourite, and two players rookies
    # rest-of-season shares a twelve-game schedule can carry: about a tenth
    # of his team's goals for everyone, a quarter for the star
    first = sorted(model["players"])[0]
    for ab in sorted(model["players"]):
        q = model["players"][ab][0]
        g, a = (6.0, 7.0) if ab == first else (2.0, 3.0)
        q.update(proj_g=q["now"]["g"] + g, proj_a=q["now"]["a"] + a, proj_p=q["now"]["p"] + g + a, rookie=False)
    for ab in sorted(model["players"])[1:3]:
        model["players"][ab][0]["rookie"] = True
    tro = sim.simulate(model, sims=500, seed=6)["trophies"]
    for name in ("art_ross", "rocket", "wins", "calder"):
        assert sum(r["p"] for r in tro[name]) == pytest.approx(1.0, abs=2e-3), name
        assert all(0 <= r["p"] <= 1 for r in tro[name])
    assert tro["art_ross"][0]["name"] == f"{first} Star" and tro["art_ross"][0]["p"] > 0.5
    assert {r["team"] for r in tro["calder"]} == set(sorted(model["players"])[1:3])


def test_ties_split_the_credit() -> None:
    sim = _sim()
    shares = sim._split_credit(np.array([[5, 5, 1], [2, 7, 7], [9, 1, 1]]))
    assert shares.tolist() == [[0.5, 0.5, 0.0], [0.0, 0.5, 0.5], [1.0, 0.0, 0.0]]


def test_no_calder_table_when_rookies_are_unknown() -> None:
    sim = _sim()
    tro = sim.simulate(_synthetic_model(played_rounds=1), sims=100, seed=7)["trophies"]
    assert tro["calder"] is None


def test_calder_eligibility_follows_the_rule() -> None:
    _load_builder()
    from season_sim.model import is_rookie  # noqa: PLC0415

    season = "20262027"
    assert is_rookie([], "2006-03-01", season) is True
    assert is_rookie([12, 3], "2004-01-01", season) is True         # one season of six-plus
    assert is_rookie([26], "2004-01-01", season) is False           # more than 25 in a season
    assert is_rookie([8, 7], "2004-01-01", season) is False         # six-plus in two seasons
    assert is_rookie([], "2000-09-15", season) is False             # 26 on September 15
    assert is_rookie([], "2000-09-16", season) is True              # still 25 that day
    assert is_rookie([], None, season) is None


# -- the card's ratings -----------------------------------------------------


def _teams() -> dict:
    return {f"T{i:02d}": dict(off=3.0 + 0.02 * i, ga=3.2 - 0.02 * i) for i in range(32)}


def _ph(through: str) -> dict:
    return dict(
        last_game_date=through,
        teams={f"T{i:02d}": dict(attack=1.2 if i == 0 else 1.0, defence=1.0) for i in range(32)},
        form={"T00": dict(attack=1.2, defence=1.0)},
        home_ice={"T01": 0.05},
    )


def test_the_cards_ratings_are_blended_in_when_current() -> None:
    _load_builder()
    from season_sim.model import _blend_ph  # noqa: PLC0415

    teams = _teams()
    state = dict(played=[dict(date="2026-10-25")])
    status, home_ice = _blend_ph(teams, _ph("2026-10-25"), 0.5, state)
    assert status.startswith("blended") and home_ice == {"T01": 0.05}
    # T00's 1.2 attack is all five-game form: taken out, it is average
    assert teams["T00"]["ph_off"] == pytest.approx(sum(t["own_off"] for t in teams.values()) / 32)
    t5 = teams["T05"]
    assert t5["off"] == pytest.approx(0.5 * t5["own_off"] + 0.5 * t5["ph_off"])


def test_stale_or_missing_ratings_are_not_blended() -> None:
    _load_builder()
    from season_sim.model import _blend_ph, load_ph_ratings  # noqa: PLC0415

    teams = _teams()
    status, home_ice = _blend_ph(teams, _ph("2026-10-10"), 0.5, dict(played=[dict(date="2026-10-25")]))
    assert home_ice is None and "2026-10-10" in status
    assert all(t["off"] == t["own_off"] for t in teams.values())
    assert load_ph_ratings(Path("/nonexistent/shadow_team_ratings.json"))[0] is None


def test_team_home_ice_moves_home_results() -> None:
    sim = _sim()
    model = _synthetic_model(played_rounds=0)
    first = sorted(model["teams"])[0]
    # put every one of its games at home: the card's home ice is a home-road
    # spread, so it helps at home and costs on the road
    for g in model["state"]["remaining"]:
        if g["away"] == first:
            g["home"], g["away"] = first, g["home"]
    plain = {t["abbrev"]: t for t in sim.simulate(model, sims=400, seed=8)["teams"]}
    model["home_ice"] = {first: 0.25}
    boosted = {t["abbrev"]: t for t in sim.simulate(model, sims=400, seed=8)["teams"]}
    assert boosted[first]["pts"] > plain[first]["pts"]


# -- the page ---------------------------------------------------------------

_DRIVER = r"""
import { readFileSync } from "node:fs";
const [dataPath, pagePath] = process.argv.slice(2);
const data = JSON.parse(readFileSync(dataPath, "utf8"));
const html = readFileSync(pagePath, "utf8");
const m = html.match(/<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/);
if (!m) throw new Error("Season.dc.html carries no component script");
class DCLogic { constructor() { this.props = {}; this.state = {}; } setState(s) { this.state = { ...this.state, ...s }; } }
const Component = new Function("DCLogic", m[1] + "\nreturn Component;")(DCLogic);
const page = new Component();
page.state = { vm: page.build(data, {}), otherSports: [] };
process.stdout.write(JSON.stringify(page.renderVals()));
"""


def _render(site: dict, tmp_path: Path) -> dict:
    node = shutil.which("node")
    assert node, "node is not on PATH; the Season page is rendered through its own code"
    (tmp_path / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    data = tmp_path / "season.json"
    data.write_text(json.dumps(site), encoding="utf-8")
    result = subprocess.run([node, str(tmp_path / "render.mjs"), str(data), str(WEB / "Season.dc.html")],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, f"the Season page threw on this file:\n{result.stderr}"
    return json.loads(result.stdout)


def test_the_page_renders_the_trophy_and_playoff_sections(tmp_path: Path) -> None:
    builder = _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=2)
    for ab in sorted(model["players"]):
        model["players"][ab][0]["rookie"] = ab.endswith("0")
    result = simulate(model, sims=300, seed=9)
    site = builder.compose(model, result, {"asOf": "2026-11-01"}, {}, generated_at="2026-11-01T14:00:00+00:00")
    builder.check(site)
    vals = _render(site, tmp_path)
    assert vals["hasRounds"] and vals["hasTrophies"]
    assert [c["name"] for c in vals["roundConfs"]] == ["Eastern", "Western"]
    assert all(len(c["rows"]) == 16 for c in vals["roundConfs"])
    assert len(vals["slots"]) == 8 and vals["finals"]
    assert [b["title"] for b in vals["trophies"]] == ["Art Ross", "Rocket Richard", "Most wins", "Calder"]
    assert all(r["value"].endswith("%") for b in vals["trophies"] for r in b["rows"])
    assert any(c["label"] == "Stanley Cup" for c in vals["strip"])
    # labelled as projections, on the page itself
    assert "projection" in vals["roundsNote"] and "projection" in vals["trophiesNote"]
    heads = [m["head"] for m in vals["method"]]
    assert "Playoffs." in heads and "Trophies." in heads
    page = (WEB / "Season.dc.html").read_text(encoding="utf-8")
    for binding in ("{{ roundConfs }}", "{{ slots }}", "{{ finals }}", "{{ trophies }}", "{{ hasTrophies }}", "{{ hasRounds }}"):
        assert binding in page, binding


def test_a_file_written_before_the_new_sections_still_renders(tmp_path: Path) -> None:
    site = json.loads((WEB / "data" / "season.json").read_text(encoding="utf-8"))
    for key in ("playoffs", "trophies"):
        site.pop(key, None)
    vals = _render(site, tmp_path)
    assert vals["hasRounds"] is False and vals["hasTrophies"] is False
    assert vals["divisions"] and vals["strip"]


# -- the backtest's bookkeeping ---------------------------------------------


def _backtest():
    from test_scripts import load_script  # noqa: PLC0415

    return load_script("backtest_season_sim.py")


def _schedule_game(gid: int, day: str, home: str, away: str, hs: int, as_: int, last: str = "REG") -> dict:
    return dict(id=gid, gameType=2, gameDate=day, gameState="OFF", homeTeam=dict(abbrev=home, score=hs),
                awayTeam=dict(abbrev=away, score=as_), gameOutcome=dict(lastPeriodType=last))


def test_the_backtest_tallies_the_table_from_games_before_the_cutoff_only() -> None:
    bt = _backtest()
    games = [
        _schedule_game(1, "2024-10-10", "AAA", "BBB", 3, 2),
        _schedule_game(2, "2024-10-11", "BBB", "AAA", 2, 1, "OT"),
        _schedule_game(3, "2024-10-12", "AAA", "BBB", 4, 3, "SO"),
        _schedule_game(4, "2024-10-13", "BBB", "AAA", 9, 0),
    ]
    final = {"standings": [dict(teamAbbrev={"default": ab}, teamName={"default": ab}, conferenceAbbrev="E",
                                divisionName="Atlantic") for ab in ("AAA", "BBB")]}
    table = {r["teamAbbrev"]["default"]: r for r in bt.standings_to_date(final, games, "2024-10-13")["standings"]}
    a, b = table["AAA"], table["BBB"]
    assert (a["gamesPlayed"], a["wins"], a["losses"], a["otLosses"], a["points"]) == (3, 2, 0, 1, 5)
    assert (b["gamesPlayed"], b["wins"], b["losses"], b["otLosses"], b["points"]) == (3, 1, 1, 1, 3)
    assert (a["regulationWins"], a["regulationPlusOtWins"]) == (1, 1)   # the shootout win counts in neither
    assert (b["regulationWins"], b["regulationPlusOtWins"]) == (0, 1)
    assert a["goalFor"] == 3 + 1 + 4 and b["goalFor"] == 2 + 2 + 3     # the 9-0 is after the cutoff
    # the checkpoint is the morning after the league's average team reached it
    sched = {"AAA": {"games": games}, "BBB": {"games": games}}
    assert bt.cutoff_dates(sched, (1, 2)) == {1: "2024-10-11", 2: "2024-10-12"}


def test_the_backtest_scores_a_perfect_and_a_wrong_projection() -> None:
    bt = _backtest()
    teams = ["A", "B"]
    actual = {"A": dict(pts=100.0, playoff=True), "B": dict(pts=80.0, playoff=False)}
    pts = np.array([[100.0, 80.0]] * 10)
    good = bt.score(teams, pts, np.array([[True, False]] * 10), actual)
    bad = bt.score(teams, pts + 10, np.array([[False, True]] * 10), actual)
    assert good["rmse"] == 0 and good["brier"] < 1e-5 and good["coverage"] == 1.0
    assert bad["rmse"] == pytest.approx(10.0) and bad["logloss"] > good["logloss"] and bad["coverage"] == 0.0
