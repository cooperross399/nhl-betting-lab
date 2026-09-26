"""Publish Site published, and froze, projections fitted on a history the lab calls thin.

Since 17e4eac, Publish Site restores the newest Gameday Refresh run that
carries `gameday-state`, whatever its conclusion, with `--no-merge`, so that
an older run's card never fills in for today's. A Gameday run that starts
cold is always red: its restore found nothing (both run listings failing, or
every download failing, on its single attempt; or every artifact expired),
the fetch walks the game ids oldest first and stops at `--max-games 600`,
and "Record what went wrong" calls fewer than 1,000 cached games "fitted on
a thin history" and degrades the run. It still uploads its state. Publish
Site then took that state alone. Nothing was laid underneath, and nothing
checked how thin it was. `web/build_site_json.py::load_model` refused only
an EMPTY `team_games.csv`, so the board fitted `TeamModel` on the 600 oldest
games (2023-10-10 to 2024-01-04). It published every projection from that
fit, and the first build of the day froze it as the day's published opinion
in `history/<day>.json`. The next morning's Results graded straight up
against it, and the frozen copy is kept for good (the history floor refuses
any change to it). `restore_state.py`'s own docstring names the hazard: "a
red run that itself started cold must not replace a full cache with a thin
one". It protected Gameday's own chain and left the public board exposed.

Found by the failure-shape audit and confirmed by two of three refuters
(reproduce, reachability). The intent refuter held the pairing to be
deliberate. It is: the state and the reports still come from one run, and
nothing here changes the restore. What changes is that the board does not
project from a history the lab itself calls thin. Measured on the real
tables, fitting the 600 oldest of the 3,936 games against all of them, for
opening-week games:

* VAN @ EDM, home win 0.447 against 0.623;
* LAK @ COL, 0.495 against 0.601;
* CAR @ PHI, 0.512 against 0.410;
* BOS @ MIN, 0.432 against 0.531.

The projected winner flips in all four. For PIT @ PHI the board's projected
total is 5.94 against 6.67 (regulation expected goals 5.72 against 6.45).

These tests run Publish Site's restore step itself, from the workflow file,
under `bash -eo pipefail`, with the fake `gh` of
tests/test_state_restores_from_the_run_that_carries_it.py replaying a cold
red run over an older full success. They then run the real `main()` of
`web/build_site_json.py` and `web/site_history.py`, loaded by path as the
build step runs them, with only the NHL schedule stubbed. They also run
Gameday Refresh's health step from its workflow file, because the board's
floor and Gameday's are one number. `config.THIN_HISTORY_GAMES` holds it,
and the workflow's literal is held to it here by running that step. The
thin and full fixtures project opposite winners in both games, so a board
that fitted the thin table cannot pass by coincidence.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import config
from nhl_betting_lab.data.build_datasets import TEAM_GAME_COLUMNS
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import team_names

from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_state_restores_from_the_run_that_carries_it import SCRIPT, _env, _run

PROJECT_ROOT = config.PROJECT_ROOT
WEB = PROJECT_ROOT / "web"
PUBLISH_SITE = PROJECT_ROOT / ".github" / "workflows" / "publish-site.yml"
GAMEDAY = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"

#: What a cold Gameday run caches: `fetch_nhl_data.py --max-games 600` over
#: the ids sorted oldest first.
COLD_GAMES = 600
#: What the older successful run carries: comfortably past the floor.
FULL_GAMES = 1400

BOARD_DAY = date(2026, 10, 8)
#: abbrev -> (placeName, commonName), as the NHL API spells them.
CLUBS = {
    "TOR": ("Toronto", "Maple Leafs"),
    "MTL": ("Montréal", "Canadiens"),
    "BOS": ("Boston", "Bruins"),
    "NYI": ("New York", "Islanders"),
}
#: (away, home, NHL game id)
SLATE = (("MTL", "TOR", "2026020101"), ("NYI", "BOS", "2026020102"))


def floor() -> int:
    return config.THIN_HISTORY_GAMES


# -- the history -------------------------------------------------------------


def _history(count: int) -> list[list]:
    """`count` team-game rows, oldest first, one game a day, each club every
    other day (so no side is ever on a back-to-back). In the oldest
    COLD_GAMES the visitors of the slate, Montreal and the Islanders, are
    the stronger clubs; after that Toronto and Boston are, by more, so the
    full history and its oldest 600 games project opposite winners. Scores
    vary with the game, so no fit rests on a constant."""
    start = BOARD_DAY - timedelta(days=count + 150)
    rows: list[list] = []
    for index in range(count):
        day = start + timedelta(days=index)
        strong, weak = (("MTL", "TOR"), ("NYI", "BOS"))[index % 2]
        if index >= COLD_GAMES:
            strong, weak = weak, strong
        home, away = (strong, weak) if (index // 2) % 2 else (weak, strong)
        strong_goals = (4 + index % 2) if index < COLD_GAMES else (5 + index % 3)
        weak_goals = 1 + (index // 3) % 2
        home_goals, away_goals = (
            (strong_goals, weak_goals) if home == strong else (weak_goals, strong_goals)
        )
        rows.append([2023020001 + index, 20232024, 2, day.isoformat(),
                     f"{day.isoformat()}T23:00:00Z", home, away, home_goals,
                     away_goals, 30, 28, index % 5 != 0])
    return rows


def _write_table(path: Path, rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(TEAM_GAME_COLUMNS)
        writer.writerows(rows)


def _side(abbrev: str) -> dict:
    place, common = CLUBS[abbrev]
    return {"abbrev": abbrev, "placeName": {"default": place},
            "commonName": {"default": common}}


def _state(root: Path, rows: list[list]) -> Path:
    """A gameday-state artifact as Gameday uploads it, relative to data/: a
    boxscore per game and the team table built from them."""
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for row in rows:
        game_id, home, away = row[0], row[5], row[6]
        (box / f"{game_id}.json").write_text(
            json.dumps({"id": game_id, "homeTeam": _side(home), "awayTeam": _side(away)}),
            encoding="utf-8",
        )
    _write_table(root / "processed" / "team_games.csv", rows)
    return root


def _fit(rows: list[list]) -> TeamModel:
    return TeamModel().fit(pd.DataFrame(rows, columns=list(TEAM_GAME_COLUMNS)))


def _winners(model: TeamModel) -> dict[str, str]:
    """home abbrev -> the projected winner, as `settle` picks it."""
    winners = {}
    for away, home, _ in SLATE:
        eh, ea = model.expected_goals(home, away)
        winners[home] = home if eh >= ea else away
    return winners


# -- Publish Site, as its runner holds it --------------------------------------


def _publish_restore_step() -> str:
    workflow = yaml.safe_load(PUBLISH_SITE.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["publish"]["steps"]:
        if step.get("name") == "Restore the lab's latest state":
            return step["run"]
    raise AssertionError("publish-site.yml has no step named \"Restore the lab's latest state\"")


def _restore(tmp_path: Path, work: Path, scenario: dict) -> str:
    """Publish Site's restore step, verbatim, in the runner's checkout."""
    (work / "scripts").mkdir(parents=True, exist_ok=True)
    (work / "scripts" / "restore_state.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    env = _env(tmp_path, scenario)
    env["PATH"] = f"{tmp_path / 'bin'}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
    env["GH_TOKEN"] = "not-a-token"
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _publish_restore_step()],
        cwd=work, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schedule(day: date, *, final: bool) -> list[dict]:
    if day != BOARD_DAY:
        return []
    games = []
    for away, home, game_id in SLATE:
        game = {"id": int(game_id), "gameType": 2, "startTimeUTC": f"{day.isoformat()}T23:00:00Z",
                "venue": {"default": "Arena"}, "venueLocation": {"default": "City"},
                "tvBroadcasts": [],
                "awayTeam": {**_side(away), "record": "1-0-0"},
                "homeTeam": {**_side(home), "record": "1-0-0"}}
        if final:
            # The visitor wins both, so a straight-up grade is never a tie.
            game["awayTeam"]["score"], game["homeTeam"]["score"] = 4, 1
            game.update(gameState="OFF", gameOutcome={"lastPeriodType": "REG"})
        games.append(game)
    return games


def _build(work: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
           day: date = BOARD_DAY) -> tuple[dict, dict, str]:
    """The build step: build_site_json, then site_history, over what the
    restore left in the checkout. Returns the board, the results and the log."""
    site = _load(WEB / "build_site_json.py", "_site_build_thin_history")
    monkeypatch.setattr(site, "schedule_for", lambda d: _schedule(d, final=d < day))
    monkeypatch.setattr(site, "allowlisted_markets", lambda _lab: ["moneyline"])
    history = _load(WEB / "site_history.py", "_site_history_thin_history")
    out = work / "dist" / "data"
    capsys.readouterr()
    assert site.main(["--lab", str(work), "--out", str(out), "--date", day.isoformat()]) == 0
    assert history.main(["--data", str(out)]) == 0
    printed = capsys.readouterr().out
    board = json.loads((out / "board.json").read_text(encoding="utf-8"))
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return board, results, printed


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A Publish Site runner: a checkout whose data/ the restore fills, with
    every default data directory pointed there as it is on the runner, and
    the recorded verdicts pointed at an empty directory (the rest adjustment
    is off, so the oracle below is the plain fit)."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(team_names, "RAW_DIR", work / "data" / "raw")
    monkeypatch.setattr(team_names, "PROCESSED_DIR", work / "data" / "processed")
    full_rows = _history(FULL_GAMES)
    cold_rows = full_rows[:COLD_GAMES]
    return {
        "work": work,
        "full_rows": full_rows,
        "cold_rows": cold_rows,
        "full": _state(tmp_path / "state-full", full_rows),
        "cold": _state(tmp_path / "state-cold", cold_rows),
    }


def _projected(board: dict) -> list[dict]:
    return [g for g in board["games"] if "projGoals" in g["home"] or "winProb" in g["home"]]


def test_the_fixture_can_tell_a_thin_fit_from_a_full_one(runner: dict) -> None:
    """Both games' projected winners differ between the two fits, and the
    cold state is below the floor while the full one clears it."""
    thin, full = _winners(_fit(runner["cold_rows"])), _winners(_fit(runner["full_rows"]))

    assert all(thin[home] != full[home] for _, home, _ in SLATE), (thin, full)
    assert COLD_GAMES < floor() <= FULL_GAMES


def test_after_a_cold_red_run_the_board_publishes_no_thin_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, runner: dict
) -> None:
    """The workflow_run publish after a cold 13:30 run: the newest carrier
    is red and thin, the older success is full, and the step takes the red
    one alone. The board must not project from it, and the day's frozen
    board must carry no projection from it either."""
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(7002, "failure"), _run(7001, "success")]},
        "artifacts": {"7002": {"gameday-state": str(runner["cold"])},
                      "7001": {"gameday-state": str(runner["full"])}},
    }
    work = runner["work"]

    log = _restore(tmp_path, work, scenario)
    restored = pd.read_csv(work / "data" / "processed" / "team_games.csv")
    # The premise: the restore took the cold run alone. What is tested below
    # is what the build does with that.
    assert "run 7002 (failure)" in log, log
    assert len(restored) == COLD_GAMES

    board, _, printed = _build(work, monkeypatch, capsys)
    frozen = json.loads(
        (work / "dist" / "data" / "history" / f"{BOARD_DAY.isoformat()}.json").read_text(encoding="utf-8")
    )

    assert board["phase"] == "regular" and len(board["games"]) == len(SLATE)
    assert _projected(board) == [], (
        f"the board published projections fitted on {COLD_GAMES} games, "
        f"below the {floor()} the lab calls thin: {_projected(board)}"
    )
    assert all(g["priced"] is False and g["pick"] is None for g in board["games"])
    assert _projected(frozen) == [], "the day's frozen board carries the thin fit"
    notice = (board["notice"] or "").lower()
    assert "thin" in notice, board["notice"]
    assert "not available" not in notice, (
        "the history WAS available; the notice must say it was too thin"
    )
    assert f"{COLD_GAMES} games" in printed and str(floor()) in printed, printed


def test_the_next_morning_grades_nothing_from_the_thin_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, runner: dict
) -> None:
    """The same day, then the 15:00 backup finishes clean with the full
    state and Publish Site runs again, then the next morning's build settles
    the day. The live board projects the full fit, and nothing graded, and
    nothing frozen, is the thin fit's."""
    work = runner["work"]
    artifacts = {"7002": {"gameday-state": str(runner["cold"])},
                 "7001": {"gameday-state": str(runner["full"])},
                 "7003": {"gameday-state": str(runner["full"])}}
    _restore(tmp_path, work, {
        "runs": {"gameday-refresh.yml": [_run(7002, "failure"), _run(7001, "success")]},
        "artifacts": artifacts,
    })
    _build(work, monkeypatch, capsys)

    later = [_run(7003, "success"), _run(7002, "failure"), _run(7001, "success")]
    log = _restore(tmp_path, work, {"runs": {"gameday-refresh.yml": later}, "artifacts": artifacts})
    board, _, _ = _build(work, monkeypatch, capsys)
    _, results, _ = _build(work, monkeypatch, capsys, day=BOARD_DAY + timedelta(days=1))

    full, thin = _fit(runner["full_rows"]), _fit(runner["cold_rows"])
    full_winners, thin_winners = _winners(full), _winners(thin)
    assert "run 7003 (success)" in log, log
    # A full history is projected: the refusal is the table's, not the day's.
    for game in board["games"]:
        away, home = game["away"]["abbr"], game["home"]["abbr"]
        assert game["home"]["winProb"] == round(full.moneyline_probabilities(home, away)["home"], 4)
    frozen = json.loads(
        (work / "dist" / "data" / "history" / f"{BOARD_DAY.isoformat()}.json").read_text(encoding="utf-8")
    )
    for game in _projected(frozen):
        away, home = game["away"]["abbr"], game["home"]["abbr"]
        assert game["home"]["winProb"] == round(full.moneyline_probabilities(home, away)["home"], 4), (
            "the frozen board carries a projection that is not the full fit's"
        )
    for row in results["games"]:
        home = row["home"]["abbr"]
        assert row["projWinner"] == full_winners[home] != thin_winners[home], (
            f"the morning after graded {row['projWinner']} straight up, the thin fit's winner"
        )


@pytest.mark.parametrize("offset", [0, -1], ids=["at-the-floor", "one-below"])
def test_the_board_projects_from_exactly_the_floor_and_not_one_game_fewer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, runner: dict, offset: int
) -> None:
    work = runner["work"]
    count = floor() + offset
    rows = _history(count)
    _write_table(work / "data" / "processed" / "team_games.csv", rows)
    (work / "data" / "outputs").mkdir(parents=True)

    board, _, printed = _build(work, monkeypatch, capsys)

    if offset == 0:
        model = _fit(rows)
        assert len(_projected(board)) == len(SLATE), board["notice"]
        for game in board["games"]:
            away, home = game["away"]["abbr"], game["home"]["abbr"]
            assert game["home"]["winProb"] == round(model.moneyline_probabilities(home, away)["home"], 4)
        assert "thin" not in (board["notice"] or "").lower(), board["notice"]
    else:
        assert _projected(board) == [], f"{count} games were projected from"
        assert "thin" in (board["notice"] or "").lower(), board["notice"]
        assert f"{count} games" in printed, printed


# -- the floor is Gameday's --------------------------------------------------


def _health_step() -> str:
    workflow = yaml.safe_load(GAMEDAY.read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "health":
                block = step["run"]
                for expression, value in (
                    ("${{ steps.results.outcome }}", "success"),
                    ("${{ steps.prices.outputs.empty_slate }}", "false"),
                    ("${{ steps.prices.outcome }}", "success"),
                ):
                    block = block.replace(expression, value)
                assert "${{" not in block, block
                return block
    raise AssertionError("gameday-refresh.yml has no step with id: health")


@pytest.mark.parametrize("offset", [0, -1], ids=["at-the-floor", "one-below"])
def test_gameday_calls_the_same_history_thin(tmp_path: Path, offset: int) -> None:
    """Gameday Refresh's health step, run from its workflow file, with
    exactly the floor's number of cached games and one fewer: the board and
    the run that built its tables draw the line in the same place."""
    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "data" / "processed" / "player_game_logs.csv").write_text("player_id\n1\n", encoding="utf-8")
    box = work / "data" / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(floor() + offset):
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _health_step()],
        cwd=work, env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    notes = (work / "run_degraded.txt").read_text(encoding="utf-8")
    degraded = dict(line.partition("=")[::2] for line in output.read_text().splitlines())["degraded"]

    if offset == 0:
        assert degraded == "false" and notes == "", notes
    else:
        assert degraded == "true" and "thin history" in notes, notes
