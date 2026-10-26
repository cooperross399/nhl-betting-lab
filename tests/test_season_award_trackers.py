"""The Hart, Norris and Selke trackers read published odds and polls honestly.

Cooper asked (2026-10-26) for Selke, Norris and Hart trackers built from the
available odds and the media polls on each award. These tests hold, with no
network:

* the hand-kept inputs file names a source URL and a date on every block,
  and every price and poll entry is a real number, not a placeholder;
* a book's odds become probabilities with the margin taken out (they sum to
  one over the field, and the order of the prices is kept);
* the tracker share blends the market, the poll and the model with the
  documented weights, renormalised over the signals that exist, and sums to
  at most one;
* the Norris model counts defensemen only, the Selke has no model signal,
  the Hart weighs a player's club's playoff odds;
* an award with no poll says so, and an input older than 14 days is stale;
* the Season page renders the trackers through its own code.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from test_season_playoffs_and_trophies import _render
from test_the_season_page_is_a_projection import WEB, _load_builder, _synthetic_model

INPUTS = WEB.parent / "data" / "season_sim" / "award_inputs.json"


def _awards():
    _load_builder()
    from season_sim import awards  # noqa: PLC0415 - loaded off web/ above

    return awards


def _inputs(poll: bool = True, day: str = "2026-10-20") -> dict:
    odds = dict(book="Book", date=day, url="https://example.org/odds", lines=[
        dict(name="Ann Alpha", team="AAA", american=150),
        dict(name="Bo Beta", team="BBB", american=300),
        dict(name="Cy Gamma", team="CCC", american=-120),
    ])
    block = dict(odds=odds)
    if poll:
        block["poll"] = dict(outlet="Poll", date=day, url="https://example.org/poll", entries=[
            dict(name="Bo Beta", team="BBB", points=40), dict(name="Ann Alpha", team="AAA", points=20),
            dict(name="Dee Delta", team="DDD", points=20),
        ])
    return {"hart": block, "norris": block, "selke": block}


PLAYERS = [
    dict(name="Ann Alpha", pos="C", team="AAA", p=100.0),
    dict(name="Bo Beta", pos="D", team="BBB", p=60.0),
    dict(name="Cy Gamma", pos="D", team="CCC", p=70.0),
    dict(name="Dee Delta", pos="L", team="DDD", p=90.0),
]
PLAYOFF = {"AAA": 0.9, "BBB": 0.5, "CCC": 0.5, "DDD": 0.1}


def test_the_committed_inputs_name_a_source_and_a_date_for_every_number() -> None:
    awards = _awards()
    data = json.loads(INPUTS.read_text(encoding="utf-8"))
    for award in awards.AWARDS:
        block = data[award]
        odds = block["odds"]
        assert odds["url"].startswith("https://") and date.fromisoformat(odds["date"]) and odds["book"]
        assert odds["lines"] and all(isinstance(x["american"], int) and abs(x["american"]) >= 100 for x in odds["lines"])
        poll = block.get("poll")
        if poll is not None:
            assert poll["url"].startswith("https://") and date.fromisoformat(poll["date"]) and poll["outlet"]
            assert poll["entries"] and all(isinstance(e["points"], int) and e["points"] > 0 for e in poll["entries"])
        for x in odds["lines"] + (poll or {}).get("entries", []):
            assert x["name"].strip() and len(x["team"]) == 3


def test_a_books_odds_lose_their_margin_and_keep_their_order() -> None:
    awards = _awards()
    assert awards.implied(100) == pytest.approx(0.5)
    assert awards.implied(-200) == pytest.approx(2 / 3)
    assert awards.implied(300) == pytest.approx(0.25)
    market = awards._market(_inputs()["hart"]["odds"])
    assert sum(market.values()) == pytest.approx(1.0)
    assert market["cy gamma"] > market["ann alpha"] > market["bo beta"]
    assert awards.name_key("David Pastrňák") == awards.name_key("david pastrnak")


def test_the_tracker_blends_the_three_signals_with_the_documented_weights() -> None:
    awards = _awards()
    tr = awards.tracker("hart", _inputs(), PLAYERS, PLAYOFF, today=date(2026, 10, 26))
    assert tr["weights"] == awards.WEIGHTS
    rows = {r["name"]: r for r in tr["rows"]}
    assert set(rows) == {"Ann Alpha", "Bo Beta", "Cy Gamma", "Dee Delta"}
    for r in rows.values():
        want = 0.5 * (r["market"] or 0) + 0.3 * (r["poll"] or 0) + 0.2 * (r["model"] or 0)
        assert r["tracker"] == pytest.approx(want, abs=2e-4)
    assert sum(r["tracker"] for r in tr["rows"]) == pytest.approx(1.0, abs=1e-3)
    assert sum(r["model"] for r in tr["rows"]) == pytest.approx(1.0, abs=1e-3)
    # Dee Delta is in the poll only: no price, a poll rank, shares with Ann
    assert rows["Dee Delta"]["odds"] is None and rows["Dee Delta"]["market"] == 0
    assert rows["Dee Delta"]["pollRank"] == rows["Ann Alpha"]["pollRank"] == 2
    # the Hart weighs the club's playoff odds: Ann (100 pts, 90%) far above Dee (90 pts, 10%)
    assert rows["Ann Alpha"]["model"] > 3 * rows["Dee Delta"]["model"]
    assert [r["name"] for r in tr["rows"]] == sorted(rows, key=lambda n: -rows[n]["tracker"])


def test_the_norris_model_counts_defensemen_and_the_selke_has_none() -> None:
    awards = _awards()
    norris = {r["name"]: r for r in awards.tracker("norris", _inputs(), PLAYERS, PLAYOFF, today=date(2026, 10, 26))["rows"]}
    assert norris["Ann Alpha"]["model"] == 0 and norris["Dee Delta"]["model"] == 0
    assert norris["Cy Gamma"]["model"] > norris["Bo Beta"]["model"] > 0
    selke = awards.tracker("selke", _inputs(), PLAYERS, PLAYOFF, today=date(2026, 10, 26))
    assert selke["weights"] == {"market": pytest.approx(0.625), "poll": pytest.approx(0.375), "model": 0.0}
    assert all(r["model"] is None for r in selke["rows"])
    assert "no defensive stats" in selke["modelNote"]


def test_an_award_without_a_poll_says_so_and_old_inputs_are_stale() -> None:
    awards = _awards()
    tr = awards.tracker("hart", _inputs(poll=False), PLAYERS, PLAYOFF, today=date(2026, 10, 26))
    assert tr["noPoll"] and tr["weights"]["poll"] == 0
    assert tr["weights"]["market"] == pytest.approx(0.5 / 0.7, abs=1e-4)
    assert all(r["poll"] is None and r["pollRank"] is None for r in tr["rows"])
    assert not tr["stale"]
    fresh = awards.tracker("hart", _inputs(day="2026-10-12"), PLAYERS, PLAYOFF, today=date(2026, 10, 26))
    old = awards.tracker("hart", _inputs(day="2026-10-11"), PLAYERS, PLAYOFF, today=date(2026, 10, 26))
    assert not fresh["stale"] and old["stale"]
    assert all(s["ageDays"] == 15 and s["stale"] for s in old["sources"])
    assert awards.trackers(None, PLAYERS, PLAYOFF, today=date(2026, 10, 26)) is None


def test_the_page_renders_the_award_trackers(tmp_path: Path) -> None:
    builder = _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=2)
    teams = sorted(model["players"])
    star = {"name": f"{teams[0]} Star", "team": teams[0], "american": 200}
    inputs = _inputs(day="2026-10-01")
    inputs["hart"]["odds"] = dict(inputs["hart"]["odds"], lines=inputs["hart"]["odds"]["lines"] + [star])
    inputs["norris"] = dict(odds=inputs["norris"]["odds"])  # no poll
    result = simulate(model, sims=200, seed=4)
    site = builder.compose(model, result, {"asOf": "2026-11-01"}, {}, generated_at="2026-11-01T14:00:00+00:00",
                           award_inputs=inputs)
    builder.check(site)
    voted = site["trophies"]["voted"]
    assert set(voted) == {"hart", "norris", "selke"}
    hart = {r["name"]: r for r in voted["hart"]["rows"]}
    assert hart[star["name"]]["projP"] is not None and hart[star["name"]]["model"] > 0
    vals = _render(site, tmp_path)
    assert vals["hasVoted"] and vals["hasTrophySection"]
    assert [v["title"] for v in vals["voted"]] == ["Hart Trophy", "Norris Trophy", "Selke Trophy"]
    norris = vals["voted"][1]
    assert any(s["label"] == "Poll: no poll yet." for s in norris["sources"])
    assert all(v["staleLabel"] for v in vals["voted"])  # inputs dated Oct 1, built Nov 1
    assert all(r["share"].endswith("%") for v in vals["voted"] for r in v["rows"])
    assert "projection" in vals["votedNote"] and all("projection" in v["sub"] for v in vals["voted"])
    page = (WEB / "Season.dc.html").read_text(encoding="utf-8")
    assert "{{ voted }}" in page and "{{ hasTrophySection }}" in page


def test_a_build_without_award_inputs_publishes_no_trackers(tmp_path: Path) -> None:
    builder = _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=2)
    site = builder.compose(model, simulate(model, sims=100, seed=1), {"asOf": "2026-11-01"}, {},
                           generated_at="2026-11-01T14:00:00+00:00")
    builder.check(site)
    assert site["trophies"]["voted"] is None
    vals = _render(site, tmp_path)
    assert vals["hasVoted"] is False and vals["voted"] == []


# ---------------------------------------------------------------- the season so far
# Cooper (2026-10-26): "How do we make the Hart/Norris/Selke trophy trackers
# accurate and up to date". The model signal reads this season's stats.


def _stat(gp=12, gp_now=12, **kw) -> dict:
    row = dict(gp=gp, gp_now=gp_now, points=0.5, toi=17.0, faceoffs=0.0, pk=1.0, puck=0.0, defence=0.0)
    row.update(kw)
    return row


def test_the_selke_model_rewards_a_two_way_centre_once_stats_arrive() -> None:
    awards = _awards()
    players = [
        dict(name="Ann Alpha", pos="C", team="AAA", p=70.0,
             stats=_stat(points=0.8, faceoffs=4.0, pk=2.5, defence=0.15, puck=0.5, toi=20.0)),
        dict(name="Bo Beta", pos="C", team="BBB", p=90.0,
             stats=_stat(points=1.3, faceoffs=-3.0, pk=0.0, defence=-0.10, puck=-0.5, toi=21.0)),
        dict(name="Cy Gamma", pos="L", team="CCC", p=40.0, stats=_stat(points=0.4, toi=15.0)),
        dict(name="Dee Delta", pos="D", team="DDD", p=50.0, stats=_stat(points=0.6, defence=0.3, toi=24.0)),
    ]
    selke = awards.tracker("selke", _inputs(), players, PLAYOFF, today=date(2026, 10, 26))
    rows = {r["name"]: r for r in selke["rows"]}
    assert selke["weights"] == awards.WEIGHTS
    assert rows["Ann Alpha"]["model"] > rows["Bo Beta"]["model"]
    assert rows["Dee Delta"]["model"] == 0  # a defenseman is not a Selke candidate
    assert "faceoffs" in selke["modelNote"]
    assert sum(r["tracker"] for r in selke["rows"]) == pytest.approx(1.0, abs=1e-3)


def test_the_norris_model_weighs_minutes_and_defence_beside_points() -> None:
    awards = _awards()
    players = [
        dict(name="Bo Beta", pos="D", team="BBB", p=60.0, stats=_stat(points=0.9, toi=25.0, defence=0.12)),
        dict(name="Cy Gamma", pos="D", team="CCC", p=70.0, stats=_stat(points=1.0, toi=19.0, defence=-0.15)),
        dict(name="Eve Echo", pos="D", team="EEE", p=30.0, stats=_stat(points=0.3, toi=18.0, defence=0.0)),
        dict(name="Ann Alpha", pos="C", team="AAA", p=100.0, stats=_stat(points=1.5, toi=21.0)),
    ]
    rows = {r["name"]: r for r in awards.tracker("norris", _inputs(), players, PLAYOFF, today=date(2026, 10, 26))["rows"]}
    assert rows["Bo Beta"]["model"] > rows["Cy Gamma"]["model"]
    assert rows["Ann Alpha"]["model"] == 0


def test_a_player_under_the_games_floor_is_not_rated_and_early_rates_lean_on_last_season() -> None:
    awards = _awards()
    assert awards._blend(2.0, 0, 1.0) == 1.0
    assert awards._blend(2.0, awards.PRIOR_GAMES, 1.0) == pytest.approx(1.5)
    assert awards._blend(None, 0, None) is None and awards._blend(0.7, 3, None) == 0.7
    players = [dict(name="Bo Beta", pos="D", team="BBB", p=60.0, stats=_stat(gp=2, gp_now=2)),
               dict(name="Cy Gamma", pos="D", team="CCC", p=70.0, stats=_stat(gp=10, gp_now=10))]
    model = awards._model("norris", players, PLAYOFF)
    assert set(model) == {"cy gamma"}


def test_the_hart_model_follows_a_hot_scoring_pace_and_the_model_names_an_unpriced_leader() -> None:
    awards = _awards()
    players = [
        dict(name="Ann Alpha", pos="C", team="AAA", p=100.0, stats=_stat(gp_now=12, points=0.9)),
        dict(name="Fay Foxtrot", pos="C", team="AAA", p=95.0, stats=_stat(gp_now=12, points=2.0)),
        dict(name="Bo Beta", pos="D", team="BBB", p=40.0, stats=_stat()),
    ]
    rows = {r["name"]: r for r in awards.tracker("hart", _inputs(), players, PLAYOFF, today=date(2026, 10, 26))["rows"]}
    assert "Fay Foxtrot" in rows  # in no book and no poll, but leading the model
    assert rows["Fay Foxtrot"]["model"] > rows["Ann Alpha"]["model"]
    assert rows["Fay Foxtrot"]["market"] == 0 and rows["Fay Foxtrot"]["odds"] is None


def test_award_stats_reads_the_nhl_and_moneypuck_tables(tmp_path: Path) -> None:
    awards = _awards()
    import csv  # noqa: PLC0415

    def write(path: Path, rows: list[dict]) -> Path:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            w = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}))
            w.writeheader()
            w.writerows(rows)
        return path

    sk = [dict(playerId=7, season=2026, team="AAA", situation="all", games_played=10, icetime=12000,
               faceoffsWon=120, faceoffsLost=80, I_F_takeaways=9, I_F_giveaways=4),
          dict(playerId=7, season=2026, team="AAA", situation="4on5", games_played=10, icetime=1500),
          dict(playerId=7, season=2026, team="AAA", situation="5on5", games_played=10, icetime=9000,
               OnIce_A_xGoals=4.0, OffIce_A_xGoals=12.0)]
    teams = [dict(team="AAA", situation="5on5", games_played=10, iceTime=30000)]
    bundle = dict(
        season="20262027",
        skaters={"20262027": [dict(playerId=7, gamesPlayed=10, points=12, timeOnIcePerGame=1200)],
                 "20252026": [dict(playerId=7, gamesPlayed=80, points=60, timeOnIcePerGame=1140)]},
        moneypuck={"20262027": dict(skaters=write(tmp_path / "sk.csv", sk), teams=write(tmp_path / "t.csv", teams)),
                   "20252026": dict(skaters=None, teams=None)},
    )
    st = awards.award_stats(bundle)[7]
    w = 10 / (10 + awards.PRIOR_GAMES)
    assert st["gp"] == 10 and st["gp_now"] == 10
    assert st["points"] == pytest.approx(w * 1.2 + (1 - w) * 0.75)
    assert st["faceoffs"] == pytest.approx(4.0) and st["puck"] == pytest.approx(0.5)
    assert st["pk"] == pytest.approx(2.5)
    # on ice 4 xGA in 9000 s against the team's 12 in 21000 s off: he allows fewer
    assert st["defence"] > 0
    shifted = awards.award_stats(bundle, defence={"7": -0.05})[7]
    assert shifted["defence"] == -0.05
