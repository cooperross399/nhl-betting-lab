"""The new markets' prices: parsed honestly, bought under a cap, measured one
bet per wager, and kept only in the private repository.

2026-10-13. Cooper approved a daily capture and a historical buy for the
markets the shadow models cover (period markets, power-play points, faceoffs
won, player shots, first and last goalscorer). These tests hold the four
things that buy must never get wrong:

* the parser turns a response into this lab's selections and drops anything
  it cannot place, never guessing a side or a line;
* the cap holds on MEASURED spend, projected one event ahead at the dearest
  charge seen (#234), however far the provider's bill runs past the
  estimate;
* the backtest counts one bet per wager at the best price, as every
  measurement here does since the per-quote defect;
* the private store refuses the public lab, wants `"private": true`, and
  only ever adds files.
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.new_markets import backtest, prices
from nhl_betting_lab.new_markets.periods import period_matrix

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_new_market_store as store  # noqa: E402

HOME, AWAY = "Toronto Maple Leafs", "Boston Bruins"


def _event(markets: list[dict], *, event_id: str = "ev1") -> dict:
    return {
        "id": event_id,
        "commence_time": "2025-01-10T00:00:00Z",
        "home_team": HOME,
        "away_team": AWAY,
        "bookmakers": [{"key": "bookA", "title": "Book A", "markets": markets}],
    }


# -- the parser ---------------------------------------------------------------


def test_every_core_key_has_a_family_and_the_list_is_the_one_approved() -> None:
    assert len(prices.CORE_KEYS) == 17
    assert set(prices.CORE_KEYS) == {
        *(f"{kind}_p{p}" for kind in ("h2h", "h2h_3_way", "spreads", "totals") for p in (1, 2, 3)),
        "player_power_play_points", "player_faceoffs_won", "player_shots",
        "player_goal_scorer_first", "player_goal_scorer_last",
    }
    for key in prices.CORE_KEYS + prices.ALTERNATE_KEYS:
        assert prices.is_new_market_key(key)
    assert prices.market_family("alternate_totals_p2") == ("totals", 2)
    assert prices.market_family("player_shots_alternate") == ("shots", 0)
    assert not prices.is_new_market_key("player_shots_on_goal")


def test_the_new_keys_are_not_markets_the_card_prices() -> None:
    """Nothing here may reach the card: none of these keys is a market the
    card's market list or any production fetch asks for."""
    from nhl_betting_lab.markets import ALL_MARKETS
    from nhl_betting_lab.providers import odds_api

    card = {m.provider_key for m in ALL_MARKETS} | set(odds_api.PER_EVENT_PROVIDER_MARKETS) \
        | set(odds_api.ALTERNATE_PROVIDER_MARKETS) | set(odds_api.BULK_PROVIDER_MARKETS)
    assert not card & set(prices.CORE_KEYS + prices.ALTERNATE_KEYS)


def test_period_markets_parse_to_sides_lines_and_the_draw() -> None:
    rows = prices.parse_event(_event([
        {"key": "h2h_p1", "outcomes": [{"name": HOME, "price": -120}, {"name": AWAY, "price": 100}]},
        {"key": "h2h_3_way_p2", "outcomes": [
            {"name": HOME, "price": 200}, {"name": "Draw", "price": 120}, {"name": AWAY, "price": 250}]},
        {"key": "spreads_p3", "outcomes": [
            {"name": HOME, "price": 150, "point": -0.5}, {"name": AWAY, "price": -180, "point": 0.5},
            {"name": HOME, "price": 110}]},  # no line: dropped
        {"key": "totals_p1", "outcomes": [
            {"name": "Over", "price": -110, "point": 1.5}, {"name": "Under", "price": -110, "point": 1.5}]},
        {"key": "h2h_p2", "outcomes": [{"name": "Somebody Else", "price": 100}]},  # not a side: dropped
    ]), snapshot="2025-01-09T14:30:00Z", source="historical")
    got = {(r["family"], r["period"], r["selection"], r["line"]) for r in rows}
    assert got == {
        ("h2h", 1, "home", None), ("h2h", 1, "away", None),
        ("h2h_3_way", 2, "home", None), ("h2h_3_way", 2, "draw", None), ("h2h_3_way", 2, "away", None),
        ("spreads", 3, "home", -0.5), ("spreads", 3, "away", 0.5),
        ("totals", 1, "over", 1.5), ("totals", 1, "under", 1.5),
    }
    assert all(r["book"] == "Book A" and r["snapshot"] == "2025-01-09T14:30:00Z" for r in rows)


def test_player_counts_need_a_player_a_side_and_a_line() -> None:
    rows = prices.parse_event(_event([
        {"key": "player_shots", "outcomes": [
            {"name": "Over", "description": "Auston Matthews", "price": -130, "point": 6.5},
            {"name": "Under", "description": "Auston Matthews", "price": 100, "point": 6.5},
            {"name": "Over", "description": "Auston Matthews", "price": 100},  # no line
            {"name": "Over", "price": 100, "point": 2.5},  # no player
        ]},
        {"key": "player_faceoffs_won", "outcomes": [
            {"name": "Over", "description": "John Tavares", "price": -115, "point": 7.5}]},
        {"key": "player_power_play_points", "outcomes": [
            {"name": "Over", "description": "Mitch Marner", "price": 180, "point": 0.5}]},
    ]), snapshot="s", source="historical")
    got = {(r["family"], r["player"], r["selection"], r["line"]) for r in rows}
    assert got == {
        ("shots", "Auston Matthews", "over", 6.5), ("shots", "Auston Matthews", "under", 6.5),
        ("faceoffs_won", "John Tavares", "over", 7.5),
        ("power_play_points", "Mitch Marner", "over", 0.5),
    }


def test_scorer_outcomes_take_both_layouts_and_no_goalscorer() -> None:
    rows = prices.parse_event(_event([
        {"key": "player_goal_scorer_first", "outcomes": [
            {"name": "Yes", "description": "Auston Matthews", "price": 600},
            {"name": "No", "description": "Auston Matthews", "price": -1200},
            {"name": "Yes", "description": "No Goalscorer", "price": 2500},
            {"name": "No", "description": "No Goalscorer", "price": -10000},  # dropped
        ]},
        {"key": "player_goal_scorer_last", "outcomes": [
            {"name": "William Nylander", "price": 900},
            {"name": "No Goalscorer", "price": 2500},
        ]},
    ]), snapshot="s", source="historical")
    got = {(r["family"], r["player"], r["selection"]) for r in rows}
    assert got == {
        ("first_scorer", "Auston Matthews", "yes"), ("first_scorer", "Auston Matthews", "no"),
        ("first_scorer", "", prices.NO_SCORER),
        ("last_scorer", "William Nylander", "yes"), ("last_scorer", "", prices.NO_SCORER),
    }
    assert all(r["line"] is None for r in rows)


def test_a_price_that_is_not_american_odds_is_dropped_not_guessed() -> None:
    rows = prices.parse_event(_event([
        {"key": "h2h_p1", "outcomes": [
            {"name": HOME, "price": 1.91}, {"name": AWAY, "price": None}, {"name": HOME, "price": True}]},
    ]), snapshot="s", source="historical")
    assert rows == []


def test_the_cache_reads_back_through_the_wrapper(tmp_path: Path) -> None:
    event = _event([{"key": "totals_p2", "outcomes": [{"name": "Over", "price": -105, "point": 1.5}]}])
    path = prices.historical_path(tmp_path, "ev1", "2025-01-09T14:30:00Z", prices.CORE_KEYS)
    prices.write_json(path, {"timestamp": "2025-01-09T14:25:00Z", "data": event,
                             "requested": "2025-01-09T14:30:00Z", "markets_asked": list(prices.CORE_KEYS)})
    live = prices.live_path(tmp_path, "2025-01-09", "ev1", "2025-01-09T15:00:00+00:00", prices.CORE_KEYS)
    prices.write_json(live, {"captured_at": "2025-01-09T15:00:00+00:00", "data": event,
                             "markets_asked": list(prices.CORE_KEYS)})
    historical = prices.rows_from_cache(tmp_path, source="historical")
    assert list(historical["snapshot"]) == ["2025-01-09T14:25:00Z"]
    assert list(prices.rows_from_cache(tmp_path, source="live")["snapshot"]) == ["2025-01-09T15:00:00+00:00"]
    assert len(prices.rows_from_cache(tmp_path, source="all")) == 2
    seen = prices.markets_seen(tmp_path)["markets"]
    assert seen["totals_p2"] == {"events_asked": 1, "events_seen": 1, "books": 1}
    assert seen["player_shots"] == {"events_asked": 1, "events_seen": 0, "books": 0}


# -- the cap ------------------------------------------------------------------


def _events(n: int) -> list[dict]:
    return [{"event_id": f"e{i}", "snapshot": "2025-01-01T12:00:00Z"} for i in range(n)]


def _charging(charge: int, calls: list[str]):
    def request(event, markets):
        calls.append(event["event_id"])
        return {"data": {"id": event["event_id"]}}, {"x-requests-last": str(charge), "x-requests-remaining": "9"}
    return request


def _buy(tmp_path: Path, events, request, *, estimate: int, cap: int, **kw):
    return prices.gated_buy(
        events, request=request,
        path_for=lambda e, m: tmp_path / f"{e['event_id']}.json",
        wrap=lambda e, p, m: p, markets=["h2h_p1"], per_event_estimate=estimate, credit_cap=cap, **kw,
    )


def test_a_provider_charging_more_than_estimated_cannot_walk_past_the_cap(tmp_path: Path) -> None:
    """The #234 stub: 107 charged against 70 estimated, cap 200. The old
    reached-the-cap gate spent 214; projecting one event ahead at the dearest
    charge seen stops at 107."""
    calls: list[str] = []
    run = _buy(tmp_path, _events(5), _charging(107, calls), estimate=70, cap=200)
    assert run.credits_spent == 107 and calls == ["e0"]
    assert run.events_skipped_for_budget == 4
    assert not any(e.startswith("OVERSPENT") for e in run.errors)


def test_the_cap_is_spent_to_the_last_event_that_fits(tmp_path: Path) -> None:
    calls: list[str] = []
    run = _buy(tmp_path, _events(10), _charging(30, calls), estimate=34, cap=100)
    # Worst case 34 an event: two fit, a third would reach 102.
    assert run.credits_spent == 60 and len(calls) == 2


def test_a_rising_charge_is_the_only_way_past_the_cap_and_it_is_named(tmp_path: Path) -> None:
    charges = iter([40, 90])
    calls: list[str] = []

    def request(event, markets):
        calls.append(event["event_id"])
        return {"data": {}}, {"x-requests-last": str(next(charges))}

    run = _buy(tmp_path, _events(3), request, estimate=40, cap=100)
    assert run.credits_spent == 130
    assert any(e.startswith("OVERSPENT") for e in run.errors)


def test_a_cap_of_zero_is_refused_before_anything_is_asked(tmp_path: Path) -> None:
    calls: list[str] = []
    for cap in (0, -5, None):
        with pytest.raises(ValueError):
            _buy(tmp_path, _events(2), _charging(1, calls), estimate=34, cap=cap)
    assert calls == []


def test_a_cached_response_is_never_bought_again(tmp_path: Path) -> None:
    (tmp_path / "e0.json").write_text(json.dumps({"data": {"id": "e0"}}), encoding="utf-8")
    calls: list[str] = []
    run = _buy(tmp_path, _events(2), _charging(34, calls), estimate=34, cap=1000)
    assert calls == ["e1"] and run.events_from_cache == 1 and run.events_bought == 1


def test_a_failed_request_is_held_at_the_worst_case(tmp_path: Path) -> None:
    calls: list[str] = []

    def request(event, markets):
        calls.append(event["event_id"])
        raise RuntimeError("The odds provider returned HTTP 503.")

    run = _buy(tmp_path, _events(5), request, estimate=40, cap=100)
    assert calls == ["e0", "e1"] and len(run.failed) == 2 and run.credits_spent == 0


def test_a_422_for_the_list_falls_back_once_to_the_core_keys(tmp_path: Path) -> None:
    asked: list[list[str]] = []

    def request(event, markets):
        asked.append(list(markets))
        if "alternate_totals_p1" in markets:
            raise RuntimeError("The odds provider returned HTTP 422.")
        return {"data": {}}, {"x-requests-last": "20"}

    run = prices.gated_buy(
        _events(2), request=request, path_for=lambda e, m: tmp_path / f"{e['event_id']}-{len(m)}.json",
        wrap=lambda e, p, m: p, markets=["h2h_p1", "alternate_totals_p1"], per_event_estimate=40,
        credit_cap=1000, core_markets=["h2h_p1"],
    )
    assert asked == [["h2h_p1", "alternate_totals_p1"], ["h2h_p1"], ["h2h_p1"]]
    assert run.fell_back_to_core and run.events_bought == 2


def test_the_estimates_are_the_documented_rates() -> None:
    assert prices.historical_estimate(17, 2) == 340
    assert prices.live_estimate(17, 2) == 34
    projection = prices.project_cost([100, 120, 140], 2700)
    assert projection["projected"] == pytest.approx(324_000)
    assert projection["low"] == 270_000 and projection["high"] == 378_000


# -- the backtest ---------------------------------------------------------------


def _price_rows(**overrides) -> dict:
    row = {
        "provider_event_id": "ev1", "commence_time": "2025-01-10T00:00:00Z", "home_team": HOME,
        "away_team": AWAY, "market": "totals_p1", "family": "totals", "period": 1, "player": "",
        "selection": "over", "line": 1.5, "american_odds": -110.0, "book": "Book A",
        "snapshot": "2025-01-09T14:30:00Z", "source": "historical", "game_id": 1,
    }
    row.update(overrides)
    return row


def test_one_wager_is_one_bet_at_the_best_price() -> None:
    frame = pd.DataFrame([
        _price_rows(book="Book A", american_odds=-120.0),
        _price_rows(book="Book B", american_odds=105.0),
        _price_rows(book="Book C", american_odds=-105.0),
        _price_rows(selection="under", american_odds=-110.0),
    ])
    bets = backtest.wagers(frame)
    assert len(bets) == 2
    over = bets[bets["selection"] == "over"].iloc[0]
    assert over["american_odds"] == 105.0 and over["book"] == "Book B"


def test_player_shots_is_measured_under_both_readings() -> None:
    frame = pd.DataFrame([_price_rows(family="shots", market="player_shots", period=0,
                                      player="Auston Matthews", line=6.5)])
    assert sorted(backtest.wagers(frame)["family"]) == ["shots_as_attempts", "shots_as_unblocked"]


def test_a_tied_period_pushes_the_two_way_and_wins_the_draw() -> None:
    assert backtest._period_result(1, 1, "h2h", "home", None) == "push"
    assert backtest._period_result(1, 1, "h2h_3_way", "draw", None) == "win"
    assert backtest._period_result(2, 1, "spreads", "away", 1.0) == "push"
    assert backtest._period_result(2, 1, "totals", "over", 2.5) == "win"
    matrix = period_matrix(0.9, 0.7)
    win, push = backtest._period_outcome(matrix, "h2h", "home", None)
    draw, _ = backtest._period_outcome(matrix, "h2h_3_way", "draw", None)
    assert push == pytest.approx(draw) and 0 < win < 1
    over, _ = backtest._period_outcome(matrix, "totals", "over", 1.5)
    under, _ = backtest._period_outcome(matrix, "totals", "under", 1.5)
    assert over + under == pytest.approx(1.0, abs=1e-9)


def test_a_count_on_a_whole_line_can_push() -> None:
    over, push, under = backtest._count_outcome_probabilities(2.0, 0.0, 2.0)
    assert push > 0 and over + push + under == pytest.approx(1.0)
    over, push, under = backtest._count_outcome_probabilities(2.0, 0.2, 2.5)
    assert push == 0 and over + under == pytest.approx(1.0)


def test_the_edge_bar_is_the_cards_measurement_bar() -> None:
    from nhl_betting_lab.config import MIN_EDGE, MIN_PROP_EDGE

    assert backtest.edge_bar("totals") == MIN_EDGE
    for family in ("power_play_points", "faceoffs_won", "shots_as_attempts", "first_scorer"):
        assert backtest.edge_bar(family) == MIN_PROP_EDGE


def test_score_bets_only_past_the_bar_and_settles_flat() -> None:
    frame = pd.DataFrame([
        {**_price_rows(american_odds=100.0), "model": "goals", "p_win": 0.60, "p_push": 0.0, "result": "win",
         "line_key": "1.5", "player_key": ""},
        {**_price_rows(american_odds=100.0, selection="under"), "model": "goals", "p_win": 0.52, "p_push": 0.0,
         "result": "loss", "line_key": "1.5", "player_key": ""},
    ])
    scored = backtest.score(frame)
    assert list(scored["bet"]) == [True, False]
    assert list(scored["profit"]) == [1.0, -1.0]


def test_the_figures_are_clustered_and_corrected_and_say_no_demonstrated_edge() -> None:
    rng = np.random.default_rng(3)
    rows = []
    for game in range(60):
        for side in ("over", "under"):
            rows.append({"game_id": game, "family": "totals", "model": "goals", "bet": True,
                         "profit": 1.0 if rng.random() < 0.5 else -1.0, "result": "win",
                         "selection": side, "line_key": "1.5"})
    figures = backtest.measure(pd.DataFrame(rows))
    assert len(figures) == 1
    figure = figures[0]
    assert figure.bets == 120 and figure.games == 60
    assert figure.verdict == "no demonstrated edge"


def test_the_backtest_report_prints_no_price_line_or_book(tmp_path: Path) -> None:
    """The JSON and markdown carry aggregates only: render a payload built
    from sentinel prices and look for them."""
    import run_new_market_backtest as runner

    frame = pd.DataFrame([
        {**_price_rows(american_odds=1777.0, book="Zzsentinelbook", line=17.5), "model": "goals",
         "p_win": 0.9, "p_push": 0.0, "result": "win", "line_key": "17.5", "player_key": ""},
        # A second game, so the ROI is not the sentinel price itself.
        {**_price_rows(american_odds=1777.0, book="Zzsentinelbook", line=17.5, game_id=2), "model": "goals",
         "p_win": 0.9, "p_push": 0.0, "result": "loss", "line_key": "17.5", "player_key": ""},
    ])
    scored = backtest.score(frame)
    figures = backtest.measure(scored)
    payload = {
        "hours_before": 9.5, "window": {"rows": 1, "kept": 1, "events": 1, "median_lead_hours": 9.5},
        "join": {"events": 1, "unresolved_teams": 0, "no_game": 0}, "wagers": 1, "no_player": 0,
        "not_priced": 0, "period_unpriced": 0, "no_opinion": 0,
        "by_family": [{"family": "totals", "wagers": 1, "priced": 1}], "looks": len(figures),
        "figures": [f.as_dict() for f in figures], "shots_definition": {"wagers": 0},
    }
    text = runner.render(runner._clean(payload)) + json.dumps(runner._clean(payload))
    for sentinel in ("Zzsentinelbook", "1777", "17.5"):
        assert sentinel not in text


# -- the private store --------------------------------------------------------


@pytest.fixture
def private(monkeypatch) -> list[str]:
    asked: list[str] = []

    def answer(repo: str, token: str) -> bool:
        asked.append(repo)
        return True

    monkeypatch.setattr(store, "repo_is_private", answer)
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    return asked


def _cache(root: Path, name: str, body: dict) -> Path:
    path = root / "historical" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _bare(tmp_path: Path) -> Path:
    bare = tmp_path / "private.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    return bare


def _branch_files(bare: Path) -> list[str]:
    done = subprocess.run(["git", "--git-dir", str(bare), "ls-tree", "-r", "--name-only", store.BRANCH],
                          capture_output=True, text=True)
    return done.stdout.split() if done.returncode == 0 else []


def test_the_public_lab_is_refused_before_anything_is_asked(tmp_path, private, capsys) -> None:
    _cache(tmp_path / "prices", "a.json", {"data": {}})
    code = store.main(["push", "--prices-dir", str(tmp_path / "prices"), "--repo", "cooperross399/nhl-betting-lab"])
    assert code == store.EXIT_REFUSED and private == []
    assert "public lab" in capsys.readouterr().out


def test_a_local_remote_named_for_the_public_lab_is_refused(tmp_path, private) -> None:
    _cache(tmp_path / "prices", "a.json", {"data": {}})
    remote = tmp_path / "cooperross399" / "nhl-betting-lab"
    assert store.main(["push", "--prices-dir", str(tmp_path / "prices"),
                       "--remote", f"file://{remote}"]) == store.EXIT_REFUSED


def test_a_store_that_is_not_private_is_never_written(tmp_path, private, monkeypatch) -> None:
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: False)
    bare = _bare(tmp_path)
    _cache(tmp_path / "prices", "a.json", {"data": {}})
    assert store.main(["push", "--prices-dir", str(tmp_path / "prices"), "--remote", f"file://{bare}",
                       "--allow-new-branch"]) == store.EXIT_REFUSED
    assert _branch_files(bare) == []


def test_no_token_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(store.TOKEN_ENV, raising=False)
    assert store.main(["push", "--prices-dir", str(tmp_path)]) == store.EXIT_NO_TOKEN
    assert store.main(["pull", "--prices-dir", str(tmp_path)]) == store.EXIT_NO_TOKEN


def test_an_ordinary_push_never_creates_the_branch(tmp_path, private) -> None:
    bare = _bare(tmp_path)
    _cache(tmp_path / "prices", "a.json", {"data": {}})
    assert store.main(["push", "--prices-dir", str(tmp_path / "prices"),
                       "--remote", f"file://{bare}"]) == store.EXIT_REFUSED
    assert store.main(["pull", "--prices-dir", str(tmp_path / "out"),
                       "--remote", f"file://{bare}"]) == store.EXIT_EMPTY


def test_a_push_adds_gzip_files_and_a_pull_brings_them_back(tmp_path, private) -> None:
    bare = _bare(tmp_path)
    first = _cache(tmp_path / "prices", "a.json", {"data": {"id": "a"}})
    remote = f"file://{bare}"
    assert store.main(["push", "--prices-dir", str(tmp_path / "prices"), "--remote", remote,
                       "--allow-new-branch"]) == store.EXIT_OK
    assert _branch_files(bare) == ["raw/historical/a.json.gz"]
    blob = subprocess.run(["git", "--git-dir", str(bare), "cat-file", "blob",
                           f"{store.BRANCH}:raw/historical/a.json.gz"], capture_output=True, check=True).stdout
    assert json.loads(gzip.decompress(blob)) == {"data": {"id": "a"}}

    # A later push adds only what is new, and never rewrites a held file.
    first.write_text(json.dumps({"data": {"id": "changed"}}), encoding="utf-8")
    _cache(tmp_path / "prices", "b.json", {"data": {"id": "b"}})
    assert store.main(["push", "--prices-dir", str(tmp_path / "prices"), "--remote", remote]) == store.EXIT_OK
    assert _branch_files(bare) == ["raw/historical/a.json.gz", "raw/historical/b.json.gz"]
    log = subprocess.run(["git", "--git-dir", str(bare), "log", "--format=%H", store.BRANCH],
                         capture_output=True, text=True, check=True).stdout.split()
    assert len(log) == 2

    # Nothing new: nothing committed.
    assert store.main(["push", "--prices-dir", str(tmp_path / "prices"), "--remote", remote]) == store.EXIT_OK
    assert len(subprocess.run(["git", "--git-dir", str(bare), "log", "--format=%H", store.BRANCH],
                              capture_output=True, text=True, check=True).stdout.split()) == 2

    out = tmp_path / "out"
    assert store.main(["pull", "--prices-dir", str(out), "--remote", remote]) == store.EXIT_OK
    assert json.loads((out / "historical" / "a.json").read_text()) == {"data": {"id": "a"}}
    assert json.loads((out / "historical" / "b.json").read_text()) == {"data": {"id": "b"}}


def test_a_pull_into_the_workspace_is_refused(tmp_path, private, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    assert store.main(["pull", "--prices-dir", str(tmp_path / "data" / "x"),
                       "--remote", f"file://{_bare(tmp_path)}"]) == store.EXIT_REFUSED


# -- the workflow ---------------------------------------------------------------


def _workflow() -> dict:
    return yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "new-market-prices.yml").read_text())


def test_the_workflow_uploads_aggregates_only() -> None:
    uploads = [s for s in _workflow()["jobs"]["prices"]["steps"] if "upload-artifact" in str(s.get("uses", ""))]
    assert len(uploads) == 1
    paths = [line.strip() for line in uploads[0]["with"]["path"].splitlines() if line.strip()]
    assert paths and all(p.startswith("data/outputs/new_market_") for p in paths)


def test_the_prices_live_only_in_the_runners_temp_directory() -> None:
    text = (PROJECT_ROOT / ".github" / "workflows" / "new-market-prices.yml").read_text()
    for line in text.splitlines():
        if "--prices-dir" in line:
            assert '"$RUNNER_TEMP/private-new-markets"' in line or '"$prices"' in line, line
    assert 'prices="$RUNNER_TEMP/private-new-markets"' in text


def test_the_schedule_captures_from_the_default_branch_under_a_cap_that_covers_a_full_night() -> None:
    document = _workflow()
    on = document.get("on", document.get(True))
    assert [c["cron"] for c in on["schedule"]] == ["0 10 * 1-4,10-12 *"]
    job = document["jobs"]["prices"]
    assert "default_branch" in job["if"] and "schedule" in job["if"]
    plan = next(s for s in job["steps"] if s.get("id") == "plan")["run"]
    assert "cap=640" in plan and "mode=capture" in plan
    assert 640 >= 16 * prices.live_estimate(len(prices.CORE_KEYS), 2)
    assert on["workflow_dispatch"]["inputs"]["credit_cap"]["required"] is True


# -- the runner, end to end on a synthetic league ----------------------------------


def test_the_backtest_runs_end_to_end_and_writes_aggregates_only(tmp_path: Path) -> None:
    """A four-team league (the scorer tests' fixture), its play-by-play
    cached, and bought prices for every game after the models' history: the
    runner joins, prices and measures them, and its outputs carry no book."""
    import run_new_market_backtest as runner
    from test_scorer_markets import _league

    from nhl_betting_lab.new_markets import scorers
    from nhl_betting_lab.providers.team_names import TEAM_NAMES_FILENAME, normalize_team_name

    team_games, logs, payloads = _league(days=150)
    processed, raw, out = tmp_path / "processed", tmp_path / "raw", tmp_path / "outputs"
    processed.mkdir()
    team_games.to_csv(processed / "team_games.csv", index=False)
    logs.to_csv(processed / "player_game_logs.csv", index=False)
    names = {team: f"{team.title()} Sentinels" for team in ("AAA", "BBB", "CCC", "DDD")}
    (processed / TEAM_NAMES_FILENAME).write_text(
        "name,abbreviation\n" + "".join(f"{normalize_team_name(n)},{t}\n" for t, n in names.items()),
        encoding="utf-8",
    )
    for gid, payload in payloads.items():
        path = scorers.play_by_play_path(gid, raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    prices_dir = tmp_path / "prices"
    for game in team_games.itertuples():
        if game.date < "2025-01-15":
            continue
        commence = f"{game.date}T23:00:00Z"
        home_logs = logs[(logs["game_id"] == game.game_id) & (logs["team"] == game.home_team)]
        star = int(home_logs["player_id"].min())
        markets = [
            {"key": "totals_p1", "outcomes": [{"name": "Over", "price": -110, "point": 1.5},
                                              {"name": "Under", "price": -110, "point": 1.5}]},
            {"key": "h2h_p2", "outcomes": [{"name": names[game.home_team], "price": 120},
                                           {"name": names[game.away_team], "price": 120}]},
            {"key": "player_goal_scorer_first", "outcomes": [
                {"name": "Yes", "description": f"Player {star}", "price": 700},
                {"name": "Yes", "description": "No Goalscorer", "price": 1800}]},
        ]
        event = {"id": f"ev{game.game_id}", "commence_time": commence, "home_team": names[game.home_team],
                 "away_team": names[game.away_team],
                 "bookmakers": [{"key": "zz", "title": "Zzsentinelbook", "markets": markets}]}
        snapshot = f"{game.date}T13:30:00Z"
        prices.write_json(prices.historical_path(prices_dir, event["id"], snapshot, prices.CORE_KEYS),
                          {"timestamp": snapshot, "data": event, "markets_asked": list(prices.CORE_KEYS)})

    code = runner.main(["--prices-dir", str(prices_dir), "--processed-dir", str(processed),
                        "--raw-dir", str(raw), "--output-dir", str(out)])
    assert code == 0
    payload = json.loads((out / "new_market_backtest.json").read_text())
    assert payload["join"]["no_game"] == 0 and payload["join"]["unresolved_teams"] == 0
    families = {f["family"] for f in payload["figures"]}
    assert {"totals", "h2h", "first_scorer"} <= families
    assert payload["looks"] == len(payload["figures"])
    text = (out / "new_market_backtest.md").read_text() + json.dumps(payload)
    assert "Zzsentinelbook" not in text and "Sentinels" not in text


def test_a_window_holding_no_price_measures_nothing(tmp_path: Path) -> None:
    import run_new_market_backtest as runner

    assert runner.main(["--prices-dir", str(tmp_path / "none"), "--output-dir", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists()
