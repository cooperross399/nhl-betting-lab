"""Cached walk-forward samples could not say which policy made them, or when.

`samples_are_current` checked emptiness, columns, market names and the line
grid — nothing else. Samples generated with the back-to-back adjustment on
and with it off have identical columns, so after a verdict flipped, `--reuse-
samples` kept the old policy's cache: the reproduction built a rest-ignored
prop cache while `props_b2b` shipped, and `run_props_calibration.py --reuse-
samples` printed "Reusing 749,115 cached samples" although 194,707 of those
rows carry a different fitted mean (32,165 per skater market, 1,717
goalie_saves), and wrote a calibration report and live corrections for the
policy that does not ship (159 numeric leaves differ from a fresh run). It was
blind to time as well: a cache cut at 2025-12-31 against logs reaching
2026-04-16 was reused, 605,218 of 749,115 samples, so no game played after a
cache was built ever reached the calibration. Gameday Refresh reuses the
restored cache on every run, and since #131 restores it every run. Found by the
failure-shape audit (finding 58; 2/3 refuters). No committed report is wrong
today: the cache on disk was built under the shipped policy and covers every
one of the 3,658 games on or after its first sampled date.

The correction experiment read the same cache with no check at all, so it
could decide `by_toi` on samples of a policy the card does not run.

What these tests hold:

* every prop and team sample row records the `use_rest` it was generated
  under, and the record survives the CSV;
* `samples_are_current` refuses a cache generated under another policy, one
  that records none, and one missing any game the logs hold on or after its
  first sampled date — and still accepts a cache that is current;
* the real `run_props_calibration.main(["--reuse-samples"])` regenerates, under
  the shipped verdict, a cache from the other policy and a cache the logs have
  outgrown, and reuses a current one untouched; the team runner does the same
  wherever its cache is otherwise reusable;
* the correction experiment refuses samples whose policy is not the one its
  output directory's verdict ships;
* Experiment Refresh sends restored samples through that check rather than
  trusting any file that restored.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.backtest import samples_are_current
from nhl_betting_lab.backtest import team_walk_forward as twf
from nhl_betting_lab.backtest import walk_forward as wf
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as tn


TEAMS = ("TOR", "BOS", "MTL")
SAMPLED_TEAM_MARKETS = ("moneyline", "puck_line", "regulation_3_way", "total_goals")


def _script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(tn, "RAW_DIR", tmp_path / "default_raw")


def _schedule(days: int) -> list[tuple[int, str, str, str]]:
    """One game a day among three clubs, so each plays two days running and
    then rests: back-to-backs that fall on one side of a game only."""
    pairs = [("TOR", "BOS"), ("BOS", "MTL"), ("MTL", "TOR")]
    start = pd.Timestamp("2025-01-01")
    return [
        (1000 + index, (start + pd.Timedelta(days=index)).strftime("%Y-%m-%d"), *pairs[index % 3])
        for index in range(days)
    ]


def _player_logs(days: int) -> pd.DataFrame:
    rows = []
    for game_id, day, home, away in _schedule(days):
        for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
            base = TEAMS.index(team) * 10
            for offset in (1, 2):
                rows.append({
                    "game_id": game_id, "date": day, "player_id": base + offset,
                    "player": f"Skater {base + offset}", "role": "skater",
                    "position": "C", "team": team, "opponent": opponent,
                    "venue": venue, "toi_seconds": 1100 + 60 * offset,
                    "shots_on_goal": (game_id + offset) % 5, "goals": game_id % 2,
                    "assists": (game_id + 1) % 2, "points": 1, "blocked_shots": offset,
                    "hits": (game_id + offset) % 4, "power_play_goals": 0,
                    "saves": 0, "shots_against": 0,
                })
            rows.append({
                "game_id": game_id, "date": day, "player_id": base + 9,
                "player": f"Goalie {base + 9}", "role": "goalie", "position": "G",
                "team": team, "opponent": opponent, "venue": venue,
                "toi_seconds": 3600, "shots_on_goal": 0, "goals": 0, "assists": 0,
                "points": 0, "blocked_shots": 0, "hits": 0, "power_play_goals": 0,
                "saves": 24 + game_id % 7, "shots_against": 27 + game_id % 7,
            })
    return pd.DataFrame(rows)


def _team_games(days: int) -> pd.DataFrame:
    """Never a level score: the generator cannot settle one and skips it."""
    return pd.DataFrame([
        {"game_id": game_id, "date": day, "home_team": home, "away_team": away,
         "home_goals": 4 if game_id % 2 else 1 + game_id % 3,
         "away_goals": 1 + game_id % 3 if game_id % 2 else 4,
         "regulation": game_id % 4 != 0}
        for game_id, day, home, away in _schedule(days)
    ])


def _reused(out: str) -> bool:
    """The runner's own line, not the word inside a refusal's reason."""
    return any(line.startswith("Reusing ") for line in out.splitlines())


PROP_ARGS = {"refit_days": 7, "minimum_history_games": 6}

#: Long enough that skaters pass the model's 15-game minimum and every prop
#: market is sampled, so the market check never decides a test here.
DAYS = 60


# --------------------------------------------------------------------------
# The generators record the policy.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("use_rest", [True, False])
def test_every_prop_sample_records_the_policy_that_made_it(use_rest):
    samples, _ = wf.generate_prop_samples(_player_logs(DAYS), use_rest=use_rest, **PROP_ARGS)

    assert not samples.empty
    assert "use_rest" in wf.SAMPLE_COLUMNS
    assert samples["use_rest"].tolist() == [use_rest] * len(samples)


@pytest.mark.parametrize("use_rest", [True, False])
def test_every_team_sample_records_the_policy_that_made_it(use_rest):
    samples, _ = twf.generate_team_samples(
        _team_games(DAYS), use_rest=use_rest, refit_days=7, minimum_history_games=6
    )

    assert not samples.empty
    assert "use_rest" in twf.SAMPLE_COLUMNS
    assert samples["use_rest"].tolist() == [use_rest] * len(samples)


# --------------------------------------------------------------------------
# The freshness check reads it, and the games.
# --------------------------------------------------------------------------

def _prop_cache(tmp_path: Path, *, use_rest: bool, days: int = DAYS) -> pd.DataFrame:
    """A cache as it comes back from disk, not as it was built in memory."""
    samples, _ = wf.generate_prop_samples(_player_logs(days), use_rest=use_rest, **PROP_ARGS)
    path = tmp_path / "cache.csv"
    samples.to_csv(path, index=False)
    return pd.read_csv(path)


def _markets(samples: pd.DataFrame) -> tuple[str, ...]:
    return tuple(sorted(samples["market"].unique()))


@pytest.mark.parametrize("use_rest", [True, False])
def test_a_cache_from_the_policy_in_force_is_current(tmp_path, use_rest):
    cached = _prop_cache(tmp_path, use_rest=use_rest)

    current, reason = samples_are_current(
        cached, known_markets=_markets(cached),
        required_policy={"use_rest": use_rest}, source_games=_player_logs(DAYS),
    )

    assert current is True, reason


@pytest.mark.parametrize("use_rest", [True, False])
def test_a_cache_from_the_other_policy_is_refused(tmp_path, use_rest):
    cached = _prop_cache(tmp_path, use_rest=not use_rest)

    current, reason = samples_are_current(
        cached, known_markets=_markets(cached), required_policy={"use_rest": use_rest}
    )

    assert current is False
    assert "use_rest" in reason and "generated under" in reason


def test_a_cache_that_records_no_policy_is_refused(tmp_path):
    cached = _prop_cache(tmp_path, use_rest=True).drop(columns=["use_rest"])

    current, reason = samples_are_current(
        cached, known_markets=_markets(cached), required_policy={"use_rest": True}
    )

    assert current is False
    assert "record no `use_rest`" in reason


def test_a_cache_with_one_row_from_the_other_policy_is_refused(tmp_path):
    cached = _prop_cache(tmp_path, use_rest=True)
    cached.loc[cached.index[-1], "use_rest"] = False

    current, _ = samples_are_current(
        cached, known_markets=_markets(cached), required_policy={"use_rest": True}
    )

    assert current is False


@pytest.mark.parametrize("extra", [1, 15])
def test_a_cache_the_logs_have_outgrown_is_refused(tmp_path, extra):
    cached = _prop_cache(tmp_path, use_rest=True, days=DAYS)
    days = DAYS + extra

    current, reason = samples_are_current(
        cached, known_markets=_markets(cached), source_games=_player_logs(days)
    )

    assert current is False
    assert f"{extra} game(s)" in reason
    assert f"latest {_schedule(days)[-1][1]}" in reason


def test_a_game_backfilled_mid_season_is_a_game_the_cache_lacks(tmp_path):
    """A cold cache fills 600 games a run, so games arrive in the middle of
    what a cache already covers, not only at its end."""
    logs = _player_logs(DAYS)
    missing = int(logs["game_id"].iloc[-60])
    samples, _ = wf.generate_prop_samples(
        logs[logs["game_id"] != missing], use_rest=True, **PROP_ARGS
    )

    current, reason = samples_are_current(
        samples, known_markets=_markets(samples), source_games=logs
    )

    assert current is False
    assert "1 game(s)" in reason


def test_games_before_the_first_sampled_date_are_not_required(tmp_path):
    """The warm-up window is never priced; its games are history, not gaps."""
    cached = _prop_cache(tmp_path, use_rest=True)
    assert cached["date"].min() > _player_logs(DAYS)["date"].min()

    current, reason = samples_are_current(
        cached, known_markets=_markets(cached), source_games=_player_logs(DAYS)
    )

    assert current is True, reason


def test_a_reach_that_cannot_be_checked_is_not_trusted(tmp_path):
    cached = _prop_cache(tmp_path, use_rest=True)

    current, reason = samples_are_current(
        cached, known_markets=_markets(cached), source_games=pd.DataFrame()
    )

    assert current is False
    assert "cannot be checked" in reason


# --------------------------------------------------------------------------
# The calibration runner, end to end.
# --------------------------------------------------------------------------

def _calibration(tmp_path, *, cache_policy: bool | None, verdict: list[str],
                 cache_days: int = DAYS, log_days: int = DAYS):
    module = _script("run_props_calibration.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    _player_logs(log_days).to_csv(processed / "player_game_logs.csv", index=False)
    (outputs / "props_rest_experiment.json").write_text(
        json.dumps({"ships": verdict}), encoding="utf-8"
    )
    cache = outputs / "prop_calibration_samples.csv"
    if cache_policy is not None:
        samples, _ = wf.generate_prop_samples(
            _player_logs(cache_days), use_rest=cache_policy, **PROP_ARGS
        )
        samples.to_csv(cache, index=False, lineterminator="\n")
    before = cache.read_bytes() if cache.is_file() else b""
    code = module.main([
        "--reuse-samples", "--processed-dir", str(processed),
        "--output-dir", str(outputs), "--refit-days", "7",
        "--minimum-history-games", "6",
    ])
    return code, before, cache


def _fresh(use_rest: bool, days: int = DAYS) -> pd.DataFrame:
    """A fresh generation, read back the way the runner's file is."""
    samples, _ = wf.generate_prop_samples(_player_logs(days), use_rest=use_rest, **PROP_ARGS)
    return pd.read_csv(StringIO(samples.to_csv(index=False, lineterminator="\n")))


@pytest.mark.parametrize(
    ("cache_policy", "verdict", "shipped"),
    [(False, ["props_b2b"], True), (True, [], False)],
    ids=["verdict-on-cache-off", "verdict-off-cache-on"],
)
def test_calibration_regenerates_a_cache_from_the_other_policy(
    tmp_path, capsys, cache_policy, verdict, shipped
):
    code, before, cache = _calibration(tmp_path, cache_policy=cache_policy, verdict=verdict)
    out = capsys.readouterr().out

    assert code == 0
    assert "Not reusing the cached samples" in out and "use_rest" in out
    assert not _reused(out)
    rebuilt = pd.read_csv(cache)
    pd.testing.assert_frame_equal(rebuilt, _fresh(shipped))
    # And the policy is visible in the numbers, not only in the new column:
    # these logs hold one-sided back-to-backs, so the two caches disagree.
    old = pd.read_csv(StringIO(before.decode()))
    assert len(old) == len(rebuilt)
    assert (old["mean"] != rebuilt["mean"]).sum() > 0


def test_calibration_regenerates_a_cache_the_logs_have_outgrown(tmp_path, capsys):
    code, before, cache = _calibration(
        tmp_path, cache_policy=True, verdict=["props_b2b"], cache_days=DAYS - 6,
        log_days=DAYS,
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "Not reusing the cached samples" in out and "6 game(s)" in out
    pd.testing.assert_frame_equal(pd.read_csv(cache), _fresh(True, days=DAYS))


def test_calibration_reuses_a_current_cache_untouched(tmp_path, capsys):
    code, before, cache = _calibration(tmp_path, cache_policy=True, verdict=["props_b2b"])
    out = capsys.readouterr().out

    assert code == 0
    assert _reused(out)
    assert cache.read_bytes() == before


# --------------------------------------------------------------------------
# The team runner, wherever its cache is otherwise reusable.
# --------------------------------------------------------------------------

def _team_measurement(tmp_path, monkeypatch, *, cache_policy: bool, verdict: list[str],
                      cache_days: int = 30, game_days: int = 30):
    module = _script("run_team_markets_measurement.py")
    # `team_market_keys()` names `team_total`, which the team generator never
    # emits, so today every team cache is refused on that alone. Narrowed to
    # what the generator produces, the policy and reach checks are what decide.
    monkeypatch.setattr(module, "team_market_keys", lambda: SAMPLED_TEAM_MARKETS)
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    _team_games(game_days).to_csv(processed / "team_games.csv", index=False)
    (outputs / "rest_experiment.json").write_text(json.dumps({"ships": verdict}), encoding="utf-8")
    cache = outputs / "team_market_samples.csv"
    samples, _ = twf.generate_team_samples(
        _team_games(cache_days), use_rest=cache_policy, refit_days=7,
        minimum_history_games=6,
    )
    samples.to_csv(cache, index=False, lineterminator="\n")
    before = cache.read_bytes()
    code = module.main([
        "--reuse-samples", "--processed-dir", str(processed),
        "--output-dir", str(outputs), "--refit-days", "7",
        "--minimum-history-games", "6", "--phase", "late",
    ])
    return code, before, cache


@pytest.mark.parametrize(
    ("cache_policy", "verdict", "cache_days", "reused"),
    [
        (True, ["team_b2b"], 30, True),
        (False, ["team_b2b"], 30, False),
        (True, [], 30, False),
        (True, ["team_b2b"], 27, False),
    ],
    ids=["current", "other-policy-on", "other-policy-off", "outgrown"],
)
def test_the_team_runner_checks_policy_and_reach(
    tmp_path, monkeypatch, capsys, cache_policy, verdict, cache_days, reused
):
    code, before, cache = _team_measurement(
        tmp_path, monkeypatch, cache_policy=cache_policy, verdict=verdict,
        cache_days=cache_days,
    )
    out = capsys.readouterr().out

    assert code == 0
    assert _reused(out) is reused
    assert (cache.read_bytes() == before) is reused
    if not reused:
        assert set(pd.read_csv(cache)["use_rest"]) == {bool(verdict)}


# --------------------------------------------------------------------------
# The correction experiment reads the cache directly.
# --------------------------------------------------------------------------

def _correction_on(tmp_path, monkeypatch, samples: pd.DataFrame, verdict: list[str]):
    module = _script("run_correction_experiment.py")
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"commence_time": "2025-01-10T00:00:00Z", "market": "shots_on_goal"}]).to_csv(
        processed / "historical_prop_prices.csv", index=False
    )
    (outputs / "props_rest_experiment.json").write_text(json.dumps({"ships": verdict}))
    samples.to_csv(outputs / "prop_calibration_samples.csv", index=False)
    reached: list[str] = []
    monkeypatch.setattr(module, "expand_to_lines", lambda s: reached.append("expanded") or s)
    code = module.main(["--processed-dir", str(processed), "--output-dir", str(outputs)])
    return code, reached, outputs


@pytest.mark.parametrize(
    ("cache_policy", "verdict"),
    [(False, ["props_b2b"]), (True, []), (None, ["props_b2b"]), (None, [])],
    ids=["verdict-on-cache-off", "verdict-off-cache-on", "no-record-on", "no-record-off"],
)
def test_the_correction_experiment_refuses_samples_of_another_policy(
    tmp_path, monkeypatch, capsys, cache_policy, verdict
):
    samples = _prop_cache(tmp_path, use_rest=bool(cache_policy))
    if cache_policy is None:
        samples = samples.drop(columns=["use_rest"])

    code, reached, outputs = _correction_on(tmp_path, monkeypatch, samples, verdict)
    err = capsys.readouterr().err

    assert code == 2
    assert reached == [], "it went on to fit the timeline"
    assert "::error::" in err and "use_rest" in err
    assert not list(outputs.glob("correction_experiment*"))


# --------------------------------------------------------------------------
# Experiment Refresh checks what it restored.
# --------------------------------------------------------------------------

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "experiment-refresh.yml"

FAKE_PYTHON = """#!/bin/bash
echo "$*" >> "$FAKE_PYTHON_LOG"
if [ "$1" = "scripts/run_props_calibration.py" ]; then
  mkdir -p data/outputs && echo built > data/outputs/prop_calibration_samples.csv
fi
exit 0
"""


def _restore_block() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "restore":
                return step["run"]
    raise AssertionError("no restore step")


@pytest.mark.parametrize("restored", [True, False], ids=["samples-restored", "samples-absent"])
def test_experiment_refresh_sends_restored_samples_through_the_check(tmp_path, restored):
    boxscores = tmp_path / "data" / "raw" / "nhl" / "boxscore"
    boxscores.mkdir(parents=True)
    for game in range(500):
        # Final: the restore counts final boxscores only.
        (boxscores / f"{game}.json").write_text('{"gameState": "OFF"}', encoding="utf-8")
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "data" / "processed" / "historical_prop_prices.csv").write_text("x\n")
    if restored:
        (tmp_path / "data" / "outputs").mkdir(parents=True)
        (tmp_path / "data" / "outputs" / "prop_calibration_samples.csv").write_text("x\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text(FAKE_PYTHON, encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "python.log"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
           "FAKE_PYTHON_LOG": str(log)}

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _restore_block()],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    calls = log.read_text(encoding="utf-8").splitlines()

    assert result.returncode == 0, result.stdout + result.stderr
    calibration = [c for c in calls if c.startswith("scripts/run_props_calibration.py")]
    assert calibration == ["scripts/run_props_calibration.py --reuse-samples"]
    assert calls.index("scripts/build_datasets.py") < calls.index(calibration[0]), (
        "the reach check needs the logs built first"
    )
