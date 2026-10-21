"""The Lineup's projections: DraftKings points from the lab's player model.

`nhl_betting_lab.dfs_projections` turns the props model into DraftKings
points, `scripts/publish_lineup_projections.py` sends tonight's to Cooper's
DFS app, and `scripts/run_dfs_projection_test.py` measures them against
DraftKings' own average. Pinned here: the scoring, the books' means replacing
the model's, nothing but derived numbers leaving the lab, and the workflow
step never able to fail or delay the card run.

Offline, like the rest of the suite.
"""

from __future__ import annotations

import importlib.util
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from nhl_betting_lab import dfs_projections as dfs
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel

ROOT = Path(__file__).resolve().parents[1]
NAN = math.nan


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


# -- scoring -----------------------------------------------------------------


def test_actual_points_follow_the_draftkings_table() -> None:
    # Hat trick (3 goals = 25.5 + 3), 1 assist (5), 5 shots (7.5 + 3), 3 blocks (3.9 + 3), 4 points (+3).
    got = dfs.actual_skater_points([3], [1], [5], [3])[0]
    assert got == pytest.approx(25.5 + 3 + 5 + 7.5 + 3 + 3.9 + 3 + 3)
    # 30 saves, 1 against, win: 6 + 21 - 3.5 ; 35 saves, 0 against, win: shutout and 35+.
    assert dfs.actual_goalie_points([30], [1], [True], [False])[0] == pytest.approx(23.5)
    assert dfs.actual_goalie_points([35], [0], [True], [False])[0] == pytest.approx(6 + 24.5 + 4 + 3)
    assert dfs.actual_goalie_points([25], [3], [False], [True])[0] == pytest.approx(17.5 - 10.5 + 2)


def test_expected_points_add_the_bonus_chances() -> None:
    r = {s: NAN for s in dfs.SKATER_STATS}
    out = dfs.skater_expected_points([0.4], [0.6], [3.0], [1.0], r=r)
    linear = 8.5 * 0.4 + 5 * 0.6 + 1.5 * 3.0 + 1.3 * 1.0
    bonus = 3 * (out["p_hat_trick"] + out["p_three_points"] + out["p_five_shots"] + out["p_three_blocks"])
    assert out["dk"][0] == pytest.approx(linear + bonus[0])
    assert 0 < out["p_five_shots"][0] < 0.3


def test_a_mean_is_recovered_from_its_own_over_chance() -> None:
    for r in (NAN, 3.0):
        for mean, line in ((3.4, 2.5), (0.6, 0.5), (27.0, 26.5), (2.0, 2.0)):
            p = dfs.over_probability(np.array([mean]), r, np.array([line]))
            assert dfs.implied_mean(p, np.array([line]), r)[0] == pytest.approx(mean, rel=1e-3)


def test_the_books_mean_replaces_the_models_and_points_can_set_assists() -> None:
    model = {"goals": 0.3, "assists": 0.4, "shots_on_goal": 2.5, "blocked_shots": 1.0, "points": 0.7}
    means, source = dfs.blend(model, {"shots_on_goal": 3.1, "points": 0.9})
    assert means["shots_on_goal"] == 3.1 and source["shots_on_goal"] == "market"
    assert means["assists"] == pytest.approx(0.6) and source["assists"].startswith("market")
    assert means["goals"] == 0.3 and source["goals"] == "model"


def test_a_lopsided_line_does_not_anchor() -> None:
    r = {"points": NAN}
    assert dfs.market_means([(1, "points", 0.5, 0.97)], r) == {}
    got = dfs.market_means([(1, "points", 0.5, 0.55), (1, "points", 0.5, 0.57)], r)
    assert got[(1, "points")][1] == 2


def test_devig_needs_two_real_prices() -> None:
    assert dfs.devig(-110, -110) == pytest.approx(0.5)
    assert dfs.devig(-110, 50) is None


# -- tonight's slate -------------------------------------------------------------


def synthetic(seed: int = 3, days: int = 330) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two short seasons, four teams, five skaters and one goalie a side."""
    rng = np.random.default_rng(seed)
    teams = ["TOR", "BOS", "MTL", "OTT"]
    logs, games = [], []
    game_id = 0
    start = pd.Timestamp("2023-10-10")
    for d in range(days):
        day = start + pd.Timedelta(days=d)
        if day.month in (5, 6, 7, 8, 9):
            continue
        pairs = [(teams[(d) % 4], teams[(d + 1) % 4]), (teams[(d + 2) % 4], teams[(d + 3) % 4])]
        for home, away in pairs:
            game_id += 1
            hg, ag = int(rng.poisson(3.1)), int(rng.poisson(2.8))
            if hg == ag:
                hg += 1
            games.append({"game_id": game_id, "season": 0, "game_type": 2, "date": day.date().isoformat(),
                          "start_time_utc": f"{day.date()}T23:00:00Z", "home_team": home, "away_team": away,
                          "home_goals": hg, "away_goals": ag, "home_shots": 30, "away_shots": 28,
                          "regulation": bool(rng.random() < 0.8)})
            for team, opp, venue, ga in ((home, away, "home", ag), (away, home, "away", hg)):
                base = teams.index(team) * 10
                for k in range(5):
                    g = int(rng.poisson(0.3 + 0.05 * k))
                    a = int(rng.poisson(0.4))
                    logs.append({"game_id": game_id, "season": 0, "game_type": 2, "date": day.date().isoformat(),
                                 "start_time_utc": "", "player_id": base + k, "player": f"{team} Skater {k}",
                                 "boxscore_name": "", "role": "skater", "position": "D" if k == 4 else "C",
                                 "team": team, "opponent": opp, "venue": venue, "toi_seconds": 1100 + 60 * k,
                                 "shots_on_goal": g + int(rng.poisson(2.2)), "goals": g, "assists": a, "points": g + a,
                                 "blocked_shots": int(rng.poisson(1.0)), "hits": 1, "power_play_goals": 0,
                                 "saves": 0, "shots_against": 0, "goals_against": 0})
                sa = int(rng.poisson(29))
                logs.append({"game_id": game_id, "season": 0, "game_type": 2, "date": day.date().isoformat(),
                             "start_time_utc": "", "player_id": base + 9, "player": f"{team} Goalie",
                             "boxscore_name": "", "role": "goalie", "position": "G", "team": team, "opponent": opp,
                             "venue": venue, "toi_seconds": 3600, "shots_on_goal": 0, "goals": 0, "assists": 0,
                             "points": 0, "blocked_shots": 0, "hits": 0, "power_play_goals": 0,
                             "saves": max(sa - ga, 0), "shots_against": sa, "goals_against": ga})
    return pd.DataFrame(logs), pd.DataFrame(games)


@pytest.fixture(scope="module")
def fitted():
    logs, games = synthetic(days=200)
    return PlayerPropsModel().fit(logs), TeamModel().fit(games)


def test_every_player_on_tonights_slate_is_projected(fitted) -> None:
    model, team_model = fitted
    rows = dfs.project_slate(model, team_model, {("TOR", "BOS"): "2026-10-11T23:00:00Z"})
    teams = {row["team"] for row in rows}
    assert teams == {"TOR", "BOS"}
    goalies = [row for row in rows if row["pos"] == "G"]
    assert len(goalies) == 2 and all(g["ifStarts"] for g in goalies)
    for row in rows:
        assert row["p10"] <= row["dk"] + 1 and row["dk"] <= row["p90"]
        assert row["source"] == "model"


def test_a_two_sided_quote_sets_that_stat(fitted) -> None:
    model, team_model = fitted
    player_id = next(pid for pid, rates in model.skaters.items() if rates.team == "TOR")
    quotes = [(player_id, "shots_on_goal", 4.5, 0.55)] * 3
    rows = dfs.project_slate(model, team_model, {("TOR", "BOS"): ""}, quotes=quotes)
    row = next(r for r in rows if r["name"] == model.skaters[player_id].player)
    assert row["source"] == "market" and row["marketStats"] == ["shots_on_goal"] and row["books"] == 3
    assert row["shots"] > 4.5


def test_a_roster_move_puts_the_player_on_his_new_club(fitted) -> None:
    model, team_model = fitted
    mover = next(pid for pid, rates in model.skaters.items() if rates.team == "MTL")
    rows = dfs.project_slate(model, team_model, {("TOR", "BOS"): ""}, rosters={mover: "TOR"})
    assert any(r["name"] == model.skaters[mover].player and r["team"] == "TOR" for r in rows)


def test_staged_quotes_pair_the_two_sides_of_one_book(fitted) -> None:
    model, _ = fitted
    name = next(rates.player for rates in model.skaters.values() if rates.team == "TOR")
    base = {"home_team": "TOR", "away_team": "BOS", "market": "points", "player": name, "line": 0.5}
    prices = pd.DataFrame([
        {**base, "selection": "Over", "american_odds": -120, "book": "a"},
        {**base, "selection": "Under", "american_odds": 100, "book": "a"},
        {**base, "selection": "Over", "american_odds": -110, "book": "b"},  # one-sided: left out
    ])
    quotes = dfs.staged_quotes(prices, model, {("TOR", "BOS")})
    assert len(quotes) == 1 and quotes[0][1:3] == ("points", 0.5)


# -- the send ------------------------------------------------------------------


def _processed(tmp_path: Path) -> Path:
    logs, games = synthetic(days=200)
    processed = tmp_path / "processed"
    processed.mkdir()
    logs.to_csv(processed / "player_game_logs.csv", index=False)
    games.to_csv(processed / "team_games.csv", index=False)
    return processed


@pytest.mark.parametrize("anchor", [False, True])
def test_the_send_carries_no_price_line_or_book(tmp_path, monkeypatch, anchor) -> None:
    pub = _load("publish_lineup_projections")
    processed = _processed(tmp_path)
    monkeypatch.setattr(pub, "scheduled_regular_season_starts",
                        lambda raw_dir=None: {("2026-10-11", "TOR", "BOS"): "2026-10-11T23:00:00Z"})
    monkeypatch.setattr(pub, "load_team_name_map", lambda **_k: {})
    staging = tmp_path / "staging"
    staging.mkdir()
    pd.DataFrame([
        {"home_team": "TOR", "away_team": "BOS", "market": "points", "player": "TOR Skater 1",
         "selection": s, "line": 0.5, "american_odds": o, "book": "SecretBook"}
        for s, o in (("over", -137), ("under", 113))
    ]).to_csv(staging / "player_props_staging.csv", index=False)
    monkeypatch.setenv(pub.TOKEN_ENV, "t")
    sent = []

    def accept(url, token, body):
        sent.append((url, body))
        return 200, '{"ok":true}'

    code = pub.main(["--processed-dir", str(processed), "--raw-dir", str(tmp_path / "raw"),
                     "--staging-dir", str(staging), "--output-dir", str(tmp_path / "out"),
                     "--date", "2026-10-11", "--url", "https://example.test",
                     *(["--anchor-on-books"] if anchor else [])], send=accept)
    assert code == 0
    (url, body), = sent
    assert url == "https://example.test/projections?sport=NHL&date=2026-10-11"
    text = json.dumps(body)
    for leaked in ("SecretBook", "-137", "113", "american_odds", "player_id", "playerId"):
        assert leaked not in text
    # The books' means are measured worse than the model's, so they ride only when asked for.
    assert any(row["source"] == "market" for row in body["rows"]) is anchor


def test_no_token_sends_nothing(tmp_path, monkeypatch) -> None:
    pub = _load("publish_lineup_projections")
    monkeypatch.delenv(pub.TOKEN_ENV, raising=False)
    sent = []
    assert pub.main(["--date", "2026-10-11"], send=lambda *a: sent.append(a)) == 0
    assert sent == []


def test_a_refused_send_exits_one(tmp_path, monkeypatch) -> None:
    pub = _load("publish_lineup_projections")
    processed = _processed(tmp_path)
    monkeypatch.setattr(pub, "scheduled_regular_season_starts",
                        lambda raw_dir=None: {("2026-10-11", "TOR", "BOS"): ""})
    monkeypatch.setattr(pub, "load_team_name_map", lambda **_k: {})
    monkeypatch.setenv(pub.TOKEN_ENV, "t")
    code = pub.main(["--processed-dir", str(processed), "--raw-dir", str(tmp_path / "raw"),
                     "--staging-dir", str(tmp_path), "--output-dir", str(tmp_path / "out"),
                     "--date", "2026-10-11"], send=lambda *a: (401, "no"))
    assert code == pub.EXIT_REFUSED


def test_the_send_can_never_fail_or_delay_the_card_run() -> None:
    document = yaml.safe_load((ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(encoding="utf-8"))
    steps = [s for job in document["jobs"].values() for s in job.get("steps", [])]
    found = [(i, s) for i, s in enumerate(steps) if "publish_lineup_projections.py" in str(s.get("run", ""))]
    assert len(found) == 1
    index, step = found[0]
    names = [s.get("name") for s in steps]
    assert names.index("Render the card") < index
    assert step.get("continue-on-error") is True and step.get("timeout-minutes", 99) <= 10
    assert "github.event.repository.default_branch" in str(step.get("if", ""))
    secrets = {k for k, v in step.get("env", {}).items() if "secrets." in str(v)}
    assert secrets == {"LINEUP_INGEST_TOKEN"}


# -- the measurement -------------------------------------------------------------


def test_the_measurement_runs_and_compares_three_projections(tmp_path) -> None:
    test = _load("run_dfs_projection_test")
    processed = _processed(tmp_path)
    out = tmp_path / "out"
    assert test.main(["--processed-dir", str(processed), "--output-dir", str(out)]) == 0
    payload = json.loads((out / "dfs_projection_test.json").read_text())
    overall = payload["results"]["overall"]
    assert set(overall) == {"dk_average", "app_today", "lab_model"}
    assert overall["lab_model"]["n"] == overall["dk_average"]["n"] > 0
    assert 0 <= payload["results"]["spread"]["above_p90"] <= 1


def test_the_measurement_reads_bought_prices_into_anchors() -> None:
    test = _load("run_dfs_projection_test")
    from nhl_betting_lab.providers.team_names import normalize_team_name

    frame = pd.DataFrame([
        {"date": "2025-01-10", "player": "Auston Matthews", "player_id": 8479318, "team": "TOR", "game_id": 7},
        {"date": "2025-01-10", "player": "Auston Matthews", "player_id": 8479318, "team": "TOR", "game_id": 7},
    ])
    base = {
        "player": "Auston Matthews", "market": "shots_on_goal", "line": 3.5,
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "commence_time": "2025-01-11T00:00:00Z", "snapshot": "2025-01-10T14:30:00Z",
    }
    prices = pd.DataFrame([
        {**base, "book": "a", "selection": "Over", "american_odds": -120},
        {**base, "book": "a", "selection": "Under", "american_odds": 100},
        {**base, "book": "b", "selection": "Over", "american_odds": 110},
    ])
    names = {normalize_team_name("Toronto Maple Leafs"): "TOR", normalize_team_name("Boston Bruins"): "BOS"}
    anchors = test.market_anchors(prices, frame, names, {"shots_on_goal": None})
    assert set(anchors) == {(7, 8479318)}
    assert 3.0 < anchors[(7, 8479318)]["shots_on_goal"] < 5.0


def test_goalie_saves_follow_the_cards_saves_model_when_given(fitted) -> None:
    """The Lineup's goalie saves come from the card's game-context model
    (2026-10-21) when its inputs are passed; skaters are untouched."""
    from nhl_betting_lab.models.saves_context import SHIPPED, SavesInputs

    model, team_model = fitted
    _, games = synthetic(days=200)
    games = games.copy()
    # BOS outshoots everyone: TOR's goalie should face more against BOS.
    games.loc[games["home_team"] == "BOS", "home_shots"] = 40
    games.loc[games["away_team"] == "BOS", "away_shots"] = 40
    inputs = SavesInputs.from_tables(games, pd.DataFrame())
    slate = {("TOR", "BOS"): ""}
    plain = {r["name"]: r for r in dfs.project_slate(model, team_model, slate)}
    ctx = {r["name"]: r for r in dfs.project_slate(model, team_model, slate, saves_inputs=inputs)}

    goalie = model.resolve_player("TOR Goalie")
    base = model.expected_saves(goalie, opponent="BOS", venue="home", own_b2b=False, opp_b2b=False)
    want = inputs.distribution(base, venue="home", team="TOR", opponent="BOS",
                               expected_toi_seconds=model.goalies[goalie].expected_toi_seconds).mean
    assert ctx["TOR Goalie"]["saves"] == pytest.approx(want, abs=0.01)
    assert ctx["TOR Goalie"]["saves"] > ctx["BOS Goalie"]["saves"]
    assert SHIPPED.dispersion_r
    for name, row in plain.items():
        if row["pos"] != "G":
            assert ctx[name]["dk"] == row["dk"]


def test_the_saves_walk_forward_only_fits_on_earlier_starts() -> None:
    from nhl_betting_lab.backtest.walk_forward import generate_prop_samples
    from nhl_betting_lab.models.saves_context import walk_forward_means

    logs, games = synthetic(days=330)
    samples, _ = generate_prop_samples(logs, use_rest=False)
    gs = samples[samples["market"] == "goalie_saves"]
    walked = walk_forward_means(gs, logs, games, min_training=200)
    assert walked.index.equals(gs.index)
    first = pd.to_datetime(gs["date"]).min()
    early = pd.to_datetime(gs["date"]) < first + pd.Timedelta(days=14)
    assert walked.loc[early, "mean"].isna().all()
    assert walked["mean"].notna().any()
    assert (walked["mean"].dropna() > 0).all()
