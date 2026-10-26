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
    assert "no defensive rating" in selke["modelNote"]


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
