"""The voted award rankings: models fitted to past ballots, trend lines, live markets.

Cooper (2026-10-29), asked what would make the award rankings more accurate
and offered five steps (fit each award model to real voting history, read the
lab's defensive ratings, count injuries and games played, show a daily trend
line, add Kalshi and Polymarket automatically): "Yes do all that".
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from test_season_playoffs_and_trophies import _render
from test_the_season_page_is_a_projection import _load_builder, _synthetic_model

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

from season_sim import award_fit as af  # noqa: E402
from season_sim import live_markets as lm  # noqa: E402
from season_sim.awards import award_stats, name_key  # noqa: E402
from season_sim.model import is_rookie  # noqa: E402

VOTING = ROOT / "data" / "season_sim" / "award_voting.csv"


# ---------------------------------------------------------------- the ballots on file
def test_the_ballots_on_file_cover_every_award_with_a_clear_winner_each_season() -> None:
    rows = list(csv.DictReader(VOTING.open(encoding="utf-8")))
    seasons: dict[str, set[str]] = {}
    for r in rows:
        assert r["award"] in af.FEATURES
        assert len(r["season"]) == 8 and int(r["season"][4:]) == int(r["season"][:4]) + 1
        assert int(r["votes"]) > 0 and r["player"].strip()
        seasons.setdefault(r["award"], set()).add(r["season"])
    assert {a: len(s) for a, s in seasons.items()} == {"hart": 18, "norris": 9, "selke": 3, "vezina": 14, "calder": 12}
    winners = {}
    voting = af.load_voting(VOTING)
    for award, by in voting.items():
        for season, ballots in by.items():
            top = sorted(ballots, key=lambda b: -b["votes"])
            assert top[0]["votes"] > top[1]["votes"], f"{award} {season} has no single winner"
            winners[(award, season)] = top[0]["player"]
    # A few that anyone can check.
    assert winners[("hart", "20222023")] == "Connor McDavid"
    assert winners[("hart", "20242025")] == "Connor Hellebuyck"
    assert winners[("norris", "20232024")] == "Quinn Hughes"
    assert winners[("selke", "20222023")] == "Patrice Bergeron"
    assert winners[("vezina", "20212022")] == "Igor Shesterkin"
    assert winners[("calder", "20232024")] == "Connor Bedard"


# ---------------------------------------------------------------- the fit
def _history(rng, seasons: int, truth) -> tuple[dict, dict]:
    """Seasons of synthetic skaters whose Hart votes follow ``truth``."""
    hist, voting = {}, {"hart": {}}
    for y in range(2010, 2010 + seasons):
        s = f"{y}{y + 1}"
        sk = [dict(playerId=y * 1000 + i, skaterFullName=f"Pläyer {y} {i}", teamAbbrevs=f"T{i % 32}",
                   positionCode="C" if i % 4 else "D", gamesPlayed=int(rng.integers(40, 83)),
                   points=int(rng.gamma(2, 15)), timeOnIcePerGame=1000) for i in range(300)]
        hist[s] = dict(season=s, skaters=sk, goalies=[], born={}, prior_gp={},
                       berths={f"T{t}": t < 16 for t in range(32)}, games=82, moneypuck=None, goalie_mp=None)
        pool = af.season_fields(hist[s], award_stats, is_rookie)["hart"]
        X = af.design("hart", {k: [r[k] for r in pool] for k in ("points", "games", "berth", "d")})
        votes = rng.multinomial(150, af.shares(X, truth)[0]) * 10
        voting["hart"][s] = [dict(player=f"Player {y} {pool[j]['id'] - y * 1000}", team="TOT", pos="C", votes=int(v))
                             for j, v in enumerate(votes) if v]
    return hist, voting


def test_the_fit_learns_how_voters_vote_and_beats_the_old_weights_held_out() -> None:
    truth = (4.0, 2.5, 1.5, -1.0)
    hist, voting = _history(np.random.default_rng(1), 12, truth)
    report = af.fit_all(voting, hist, award_stats, is_rookie)["hart"]
    assert report["ballotNamesUnmatched"] == 0  # the accent-free name meets the ballot's
    assert report["used"] == "fitted"
    held = report["heldOut"]
    assert held["fittedLoss"] < held["defaultLoss"]
    beta = report["beta"]
    # Pulled from the old (6, log 4, 0, 0) toward what the voters did.
    assert beta[0] < 6.0 and beta[1] > np.log(4.0) and beta[2] > 0.5 and beta[3] < 0
    assert af.params({"hart": report})["hart"] == tuple(beta)


def test_a_fit_that_does_not_beat_the_old_weights_held_out_is_not_used() -> None:
    hist, voting = _history(np.random.default_rng(2), 6, af.DEFAULTS["hart"])
    report = af.fit_all(voting, hist, award_stats, is_rookie)["hart"]
    if report["used"] == "default":
        assert "did not predict" in report["reason"]
        assert af.params({"hart": report})["hart"] == af.DEFAULTS["hart"]
    one = af.fit_award("hart", {})
    assert one["used"] == "default" and af.params({"hart": one})["hart"] == af.DEFAULTS["hart"]


def test_the_old_hart_weights_are_the_old_hart_formula() -> None:
    pts = np.array([[100.0, 90.0, 60.0]])
    berth = np.array([[1.0, 0.0, 1.0]])
    X = af.design("hart", dict(points=pts, games=np.ones(3), berth=berth, d=np.zeros(3)))
    old = (pts / 100.0) ** 6 * (0.25 + 0.75 * berth)
    assert af.shares(X, af.DEFAULTS["hart"])[0] == pytest.approx((old / old.sum())[0])


def test_ballot_names_meet_the_right_player() -> None:
    rows = [dict(key=name_key("Sebastian Aho"), teams=["CAR"], pos="F"),
            dict(key=name_key("Sebastian Aho"), teams=["NYI"], pos="D"),
            dict(key=name_key("David Pastrnak"), teams=["BOS"], pos="F")]
    assert af._match(rows, "Sebastian Aho", "CAR", "C") is rows[0]
    assert af._match(rows, "Sebastian Aho", "TOT", "D") is rows[1]
    assert af._match(rows, "David Pastrňák", "BOS", "RW") is rows[2]
    assert af._match(rows, "Nobody Atall", "BOS", "C") is None


# ---------------------------------------------------------------- the fit reaches the simulated awards
def test_fitted_weights_and_games_played_reach_the_simulated_awards() -> None:
    from season_sim.awards import simulated_shares  # noqa: PLC0415
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=2)
    result = simulate(model, sims=200, seed=5)
    base = simulated_shares(model, result)["hart"]["share"]
    star_team, star = next((t, q) for t, qs in model["players"].items() for q in qs if q["name"].endswith("Star"))
    k = name_key(star["name"])
    # He misses most of the season: a fitted model that counts games played marks him down.
    star["proj_gp"] = model["games_per_team"] * 0.25
    fit = {"hart": dict(used="fitted", beta=[6.0, np.log(4.0), 2.0, 0.0], features=list(af.FEATURES["hart"]),
                        seasons=18, firstSeason="20082009", lastSeason="20252026",
                        heldOut=dict(fittedLoss=1.0, defaultLoss=1.2, fittedWinners=12, defaultWinners=10))}
    shares = simulated_shares(model, result, fit=fit)["hart"]
    assert shares["share"][k] < base[k]
    assert "fitted to how the voters actually voted" in shares["note"] and "2008-09 to 2025-26" in shares["note"]
    assert "12 of 18 winners" in shares["note"]


# ---------------------------------------------------------------- the trend lines
def test_each_ranked_name_carries_its_trend_and_weekly_move(tmp_path: Path) -> None:
    builder = _load_builder()
    voted = {"hart": {"rows": [dict(name="A", tracker=0.4), dict(name="B", tracker=0.2)]}}
    previous = {"trophies": {"votedHistory": {"hart": [
        dict(date="2026-10-20", chance={"A": 0.30, "B": 0.25}),
        dict(date="2026-10-25", chance={"A": 0.35}),
        dict(date="2026-10-29", chance={"A": 0.99}),  # today's earlier build is replaced
    ]}}}
    hist = builder.award_history(previous, voted, "2026-10-29")
    assert [e["date"] for e in hist["hart"]] == ["2026-10-20", "2026-10-25", "2026-10-29"]
    assert hist["hart"][-1]["chance"] == {"A": 0.4, "B": 0.2}
    a, b = voted["hart"]["rows"]
    assert a["trend"] == [0.30, 0.35, 0.4] and b["trend"] == [0.25, None, 0.2]
    assert a["change7"] == pytest.approx(0.10) and b["change7"] == pytest.approx(-0.05)
    first = builder.award_history(None, {"hart": {"rows": [dict(name="A", tracker=0.4)]}}, "2026-10-29")
    assert len(first["hart"]) == 1


def test_the_page_draws_the_trend_line(tmp_path: Path) -> None:
    from test_season_award_trackers import _inputs  # noqa: PLC0415

    builder = _load_builder()
    from season_sim.simulate import simulate  # noqa: PLC0415

    model = _synthetic_model(played_rounds=2)
    result = simulate(model, sims=200, seed=3)
    site = builder.compose(model, result, {"asOf": "2026-10-20"}, {}, generated_at="2026-10-20T14:00:00+00:00",
                           award_inputs=_inputs())
    first = site["trophies"]["voted"]["hart"]["rows"][0]
    later = builder.compose(model, result, {"asOf": "2026-10-28"}, {}, generated_at="2026-10-28T14:00:00+00:00",
                            award_inputs=_inputs(), previous=site)
    row = next(r for r in later["trophies"]["voted"]["hart"]["rows"] if r["name"] == first["name"])
    assert len(row["trend"]) == 2 and row["change7"] is not None
    vals = _render(later, tmp_path)
    card = next(v for v in vals["voted"] if v["title"] == "Hart Trophy")
    drawn = next(p for p in card["rows"] if p["name"] == first["name"])
    assert drawn["spark"].startswith("M0.0 ") and "L40.0" in drawn["spark"]


# ---------------------------------------------------------------- the live markets
def test_kalshi_and_polymarket_lines_are_read_and_a_field_far_past_100_is_left_out() -> None:
    ev = {"event_ticker": "KXNHLHART-27", "markets": [
        dict(yes_sub_title="Connor McDavid", yes_bid=20, yes_ask=24, status="active"),
        dict(yes_sub_title="Nathan MacKinnon", yes_bid_dollars="0.1500", yes_ask_dollars="0.1700", status="active"),
        dict(yes_sub_title="Nobody", yes_bid=0, yes_ask=0, last_price=0, status="active"),
        dict(yes_sub_title="Settled", yes_bid=50, yes_ask=52, status="settled"),
    ]}
    assert lm.kalshi_lines(ev) == [dict(name="Connor McDavid", chance=22.0), dict(name="Nathan MacKinnon", chance=16.0)]
    poly = {"markets": [dict(groupItemTitle="Connor McDavid", outcomePrices='["0.21", "0.79"]'),
                        dict(groupItemTitle="Closed Guy", outcomePrices='["0.5", "0.5"]', closed=True)]}
    assert lm.polymarket_lines(poly) == [dict(name="Connor McDavid", chance=21.0)]
    assert lm._usable([dict(name=str(i), chance=25.0) for i in range(4)])
    assert not lm._usable([dict(name=str(i), chance=60.0) for i in range(4)])  # 240%: separate bets
    assert not lm._usable([dict(name="a", chance=50.0), dict(name="b", chance=50.0)])  # too few players


def test_live_markets_join_the_odds_and_replace_the_hand_kept_copy(monkeypatch) -> None:
    class Resp:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self.data

    def fake_get(url, params=None, **kw):
        if "kalshi" in url:
            if params["series_ticker"] == "KXNHLHART":
                return Resp({"events": [{"event_ticker": "KXNHLHART-26", "markets": []},
                                        {"event_ticker": "KXNHLHART-27", "markets": [
                                            dict(yes_sub_title=n, yes_bid=c - 1, yes_ask=c + 1, status="active")
                                            for n, c in (("A", 40), ("B", 30), ("C", 20))]}]})
            raise lm.requests.ConnectionError("down")
        if params["q"].startswith("Norris"):
            return Resp({"events": [
                {"title": "Norris Trophy Winner 2025-26", "closed": True, "markets": []},
                {"title": "James Norris Trophy Winner 2026-27", "slug": "norris-2026-27", "markets": [
                    dict(groupItemTitle=n, outcomePrices=f'["{c}", "0"]') for n, c in (("D1", 0.5), ("D2", 0.3), ("D3", 0.2))]}]})
        return Resp({"events": []})

    monkeypatch.setattr(lm.requests, "get", fake_get)
    log: list[str] = []
    live = lm.live_blocks("20262027", date(2026, 10, 30), log=log.append)
    assert set(live) == {"hart", "norris"}
    assert live["hart"][0]["book"] == "Kalshi" and live["hart"][0]["date"] == "2026-10-30"
    assert [x["chance"] for x in live["hart"][0]["lines"]] == [40.0, 30.0, 20.0]
    assert live["norris"][0]["book"] == "Polymarket" and live["norris"][0]["url"].endswith("norris-2026-27")
    assert any("not read" in line for line in log)
    inputs = {"hart": {"odds": [dict(book="Kalshi", date="2026-10-17", lines=[dict(name="A", chance=10)]),
                                dict(book="DraftKings", date="2026-10-26", lines=[dict(name="A", american=200)])]},
              "norris": {"odds": dict(book="BET99", date="2026-10-29", lines=[dict(name="D1", american=150)])}}
    merged = lm.merge(inputs, live)
    assert [b["book"] for b in merged["hart"]["odds"]] == ["DraftKings", "Kalshi"]
    assert merged["hart"]["odds"][-1]["date"] == "2026-10-30"
    assert [b["book"] for b in merged["norris"]["odds"]] == ["BET99", "Polymarket"]
    assert inputs["hart"]["odds"][0]["date"] == "2026-10-17"  # the file read is not changed
