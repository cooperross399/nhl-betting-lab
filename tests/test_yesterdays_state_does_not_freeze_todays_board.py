"""A board built on yesterday's state became the day's permanent public record.

Publish Site builds on its own cron (14:45 UTC) and again whenever Gameday
Refresh completes. `web/build_site_json.py` froze `history/<day>.json` the
first time a day was built and never wrote it again, and
`web/site_history.py` did the same. The restore takes only COMPLETED Gameday
Refresh runs (`scripts/restore_state.py::completed_runs`). A cron build can
start while today's run is queued or running, or after GitHub dropped the
13:30 primary and before the 15:00 backup. That build restores YESTERDAY's
`gameday-state`, whose `team_games.csv` stops two league days back. Every
`played_previous_day` is then False, and TeamModel is fitted without last
night's games. That board froze first. The build that followed today's run
could not replace it: it restored the frozen file from the cron run's
`site-history` and skipped a file that already existed. The next morning
`settle()` graded the stale board on the Results page, though the live board
had moved on within the hour.

Found by the failure-shape audit and confirmed by all three refuters. One of
them ran the workflow's own restore step against the real scripts and
reproduced the finding's example exactly. The measurement below is re-derived
read-only from the real `team_games.csv`, on the 2025-26 regular season: 167
game days and 1,312 games. The fresh state is the games before the board's
day, the stale state the games before the day before it.

* 358 games had a back-to-back side (430 sides). A stale-state board carries
  0 of those flags.
* 40 projected winners flip, and 289 games move the home win probability by 2
  points or more (the largest move is 4.8 points).
* Graded straight up, the stale boards go 685 right, the fresh boards 697.
  Run through the builder and `settle()`, the refuter counted 41 flips and 685
  against 694.
* 2025-10-28 OTT @ CHI, with OTT on a back-to-back: fresh, OTT wins 0.5505
  and the projection is 3.18-2.86. Stale, 0.5879 and 3.29-2.74, with no flag.

Timing, measured read-only with `gh run list`: Publish Site's 14:45 cron fired
at 18:36:35Z, 18:39:16Z and 18:52:13Z on three days. One publish takes about
50 seconds, and a Gameday Refresh run takes 8 to 16 minutes.

The rule is now: a board built on LATER results (`resultsThrough`, the last
league date the model was fitted on) replaces the frozen board, but only
while no game on either board has started. From the first puck drop the
frozen board stands, whatever arrives later. A board built on the same or
older results never replaces it, so the day's first published opinion still
stands within one state.

The chain test runs Publish Site's restore and assemble steps from the
workflow file, under `bash --noprofile --norc -eo pipefail`, with an offline
`gh`. It runs the build step's two scripts through their own `main()`, with
only the NHL schedule and the clock stubbed, and uploads `site-history` from
the path the workflow names.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from nhl_betting_lab.providers import team_names

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-site.yml"
RESTORE_SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"
NEW_YORK = ZoneInfo("America/New_York")

DAY = date(2026, 10, 28)
LAST_NIGHT = DAY - timedelta(days=1)
TWO_NIGHTS_AGO = DAY - timedelta(days=2)
THREE_NIGHTS_AGO = DAY - timedelta(days=3)

#: The three times Publish Site's 14:45 cron was measured to fire: the first
#: two on the board's day (the cron build, then the build Gameday Refresh
#: triggers), the third on the next morning.
CRON = "2026-10-28T18:36:35+00:00"
AFTER_GAMEDAY = "2026-10-28T18:52:13+00:00"
NEXT_MORNING = "2026-10-29T18:39:16+00:00"

CLUBS = {
    "OTT": ("Ottawa", "Senators"),
    "CHI": ("Chicago", "Blackhawks"),
    "BOS": ("Boston", "Bruins"),
    "TOR": ("Toronto", "Maple Leafs"),
    "MTL": ("Montréal", "Canadiens"),
}
#: (away, home, NHL game id, start). OTT hosted MTL last night, so it is on
#: the road on a back-to-back. Nobody else on the slate played.
SLATE = (
    ("OTT", "CHI", "2026020150", "2026-10-29T00:30:00Z"),
    ("BOS", "TOR", "2026020151", "2026-10-28T23:00:00Z"),
)
FIRST_PUCK = "2026-10-28T23:00:00+00:00"
FINALS = {"2026020150": (3, 7), "2026020151": (2, 4)}  # (away, home)


# -- the league ----------------------------------------------------------------


def _results() -> list[tuple[str, str, str, int, int]]:
    """(date, home, away, home goals, away goals): four weeks of results,
    two games a night among five clubs, then last night's one game."""
    pairs = [("CHI", "OTT"), ("TOR", "BOS"), ("OTT", "MTL"), ("BOS", "CHI"),
             ("MTL", "TOR"), ("OTT", "BOS"), ("CHI", "MTL"), ("TOR", "OTT"),
             ("BOS", "MTL"), ("CHI", "TOR")]
    rows = []
    start = date(2026, 9, 30)
    for night in range((TWO_NIGHTS_AGO - start).days + 1):
        day = (start + timedelta(days=night)).isoformat()
        for slot in range(2):
            home, away = pairs[(2 * night + slot) % len(pairs)]
            home_goals = 1 + (night * 3 + slot * 5) % 5
            away_goals = 1 + (night * 7 + slot * 2) % 4
            if home_goals == away_goals:
                home_goals += 1
            rows.append((day, home, away, home_goals, away_goals))
    rows.append((LAST_NIGHT.isoformat(), "OTT", "MTL", 4, 2))
    return rows


def write_state(root: Path, through: date | None) -> Path:
    """A `gameday-state` artifact as `Upload the state for the next run`
    lays it out under data/: the boxscores, and the results up to `through`
    (none at all when `through` is None)."""
    boxscores = root / "raw" / "nhl" / "boxscore"
    boxscores.mkdir(parents=True, exist_ok=True)
    abbrevs = list(CLUBS)
    for index, home in enumerate(abbrevs):
        away = abbrevs[(index + 1) % len(abbrevs)]

        def side(abbrev: str) -> dict:
            place, common = CLUBS[abbrev]
            return {"abbrev": abbrev, "placeName": {"default": place},
                    "commonName": {"default": common}}

        (boxscores / f"{index}.json").write_text(
            json.dumps({"homeTeam": side(home), "awayTeam": side(away)}), encoding="utf-8")
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    if through is not None:
        with (processed / "team_games.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["game_id", "season", "game_type", "date", "start_time_utc",
                             "home_team", "away_team", "home_goals", "away_goals",
                             "home_shots", "away_shots", "regulation"])
            for index, (day, home, away, hg, ag) in enumerate(_results()):
                if day > through.isoformat():
                    continue
                writer.writerow([2026020001 + index, 20262027, 2, day, f"{day}T23:00:00Z",
                                 home, away, hg, ag, 30, 28, abs(hg - ag) > 1])
    return root


def nhl_schedule(*, finals: bool, starts: dict[str, str] | None = None):
    """The NHL schedule for the board's day; every other day is dark."""
    starts = starts or {}

    def schedule_for(day: date) -> list[dict]:
        if day != DAY:
            return []
        games = []
        for away, home, game_id, start in SLATE:
            def side(abbrev: str, score: int) -> dict:
                place, common = CLUBS[abbrev]
                entry = {"abbrev": abbrev, "placeName": {"default": place},
                         "commonName": {"default": common}, "record": "5-3-1"}
                if finals:
                    entry["score"] = score
                return entry

            away_goals, home_goals = FINALS[game_id]
            game = {"id": int(game_id), "gameType": 2,
                    "startTimeUTC": starts.get(game_id, start),
                    "venue": {"default": "Arena"}, "venueLocation": {"default": "City"},
                    "tvBroadcasts": [], "awayTeam": side(away, away_goals),
                    "homeTeam": side(home, home_goals)}
            if finals:
                game.update(gameState="OFF", gameOutcome={"lastPeriodType": "REG"})
            games.append(game)
        return games

    return schedule_for


def clock(instant: str) -> type:
    fixed = datetime.fromisoformat(instant)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 - the scripts' only use
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    return Frozen


def load_by_path(path: Path, name: str):
    """A web/ script, loaded by path as the workflow runs it."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arm_build(module, monkeypatch: pytest.MonkeyPatch, when: str,
              starts: dict[str, str] | None = None) -> None:
    """Stub the two things the builder cannot have in a test: the NHL API
    and the clock. Everything else is its own code."""
    finals = datetime.fromisoformat(when).astimezone(NEW_YORK).date() > DAY
    monkeypatch.setattr(module, "datetime", clock(when))
    monkeypatch.setattr(module, "schedule_for", nhl_schedule(finals=finals, starts=starts))
    monkeypatch.setattr(module, "allowlisted_markets",
                        lambda _lab: ["moneyline", "puck_line", "total_goals"])


def make_lab(root: Path, through: date | None) -> Path:
    write_state(root / "data", through)
    return root


def build(lab: Path, out: Path, monkeypatch: pytest.MonkeyPatch, when: str, *,
          starts: dict[str, str] | None = None) -> dict:
    """One build of `web/build_site_json.py` through its own `main()`, with
    the league date taken from the clock as the workflow takes it."""
    module = load_by_path(WEB / "build_site_json.py", "_site_build_stale_state")
    arm_build(module, monkeypatch, when, starts)
    monkeypatch.setattr(team_names, "RAW_DIR", lab / "data" / "raw")
    monkeypatch.setattr(team_names, "PROCESSED_DIR", lab / "processed-unused")
    assert module.main(["--lab", str(lab), "--out", str(out)]) == 0
    return json.loads((out / "board.json").read_text(encoding="utf-8"))


def frozen_path(out: Path) -> Path:
    return out / "history" / f"{DAY.isoformat()}.json"


def frozen(out: Path) -> dict:
    return json.loads(frozen_path(out).read_text(encoding="utf-8"))


def ott(board: dict) -> dict:
    """OTT's side of OTT @ CHI: the side on a back-to-back."""
    game = next(g for g in board["games"] if g["id"] == "2026020150")
    assert game["away"]["abbr"] == "OTT"
    return game["away"]


def back_to_back_sides(board: dict) -> list[str]:
    return [g[side]["abbr"] for g in board["games"] for side in ("away", "home")
            if g[side].get("b2b")]


@pytest.fixture
def labs(tmp_path: Path) -> dict[str, Path]:
    return {
        "stale": make_lab(tmp_path / "stale", TWO_NIGHTS_AGO),
        "fresh": make_lab(tmp_path / "fresh", LAST_NIGHT),
        "older": make_lab(tmp_path / "older", THREE_NIGHTS_AGO),
        "empty": make_lab(tmp_path / "empty", None),
    }


# -- Publish Site, run after run, as GitHub runs it ----------------------------

FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
registry = json.loads(Path(os.environ["FAKE_GH_REGISTRY"]).read_text())

def value(flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default

if args[:2] == ["run", "list"]:
    runs = [r for r in registry if r["workflow"] == value("--workflow")]
    status = value("--status")
    if status:
        # As `gh run list --help` documents it: a status or a conclusion.
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    fields = [f for f in value("--json", "").split(",") if f]
    rows = [{{k: r[k] for k in fields}} for r in runs]
    jq = value("--jq")
    if jq is None:
        print(json.dumps(rows))
    elif jq == ".[0].databaseId // empty":
        if rows:
            print(rows[0]["databaseId"])
    else:
        print("fake gh: unsupported --jq " + jq, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    run = next((r for r in registry if str(r["databaseId"]) == run_id), {{}})
    source = (run.get("artifacts") or {{}}).get(name)
    if source is None:
        print("no valid artifacts found to download", file=sys.stderr)
        sys.exit(1)
    shutil.copytree(source, dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _run_block(name: str) -> str:
    matches = [s for s in _steps() if s.get("name") == name]
    assert len(matches) == 1, f"publish-site.yml has exactly one step named {name!r}"
    return matches[0]["run"]


def _history_upload_path() -> str:
    for step in _steps():
        given = step.get("with") or {}
        if str(step.get("uses", "")).startswith("actions/upload-artifact") and (
            given.get("name") == "site-history"
        ):
            return str(given["path"]).strip()
    raise AssertionError("publish-site.yml uploads no 'site-history' artifact")


class Actions:
    """Gameday Refresh and Publish Site runs, newest first, as `gh` lists them."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.registry: list[dict] = []
        self.logs: dict[int, str] = {}
        self.next_publish = 2001
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.path = f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"

    def gameday(self, run_id: int, *, through: date | None, running: bool = False) -> None:
        """A Gameday Refresh run: in progress (no artifact yet), or completed
        with the state it uploaded."""
        self.registry = [r for r in self.registry if r["databaseId"] != run_id]
        artifacts = {}
        if not running:
            artifact = self.tmp / "artifacts" / str(run_id) / "gameday-state"
            artifacts["gameday-state"] = str(write_state(artifact, through))
        self.registry.insert(0, {
            "databaseId": run_id, "workflow": "gameday-refresh.yml",
            "status": "in_progress" if running else "completed",
            "conclusion": "" if running else "success", "artifacts": artifacts,
        })

    def _bash(self, script: str, work: Path, env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
            cwd=work, env=env, capture_output=True, text=True, timeout=120,
        )

    def publish(self, when: str) -> Path:
        """One Publish Site run at `when`. Returns its working tree."""
        run_id = self.next_publish
        self.next_publish += 1
        work = self.tmp / f"publish{run_id}"
        (work / "scripts").mkdir(parents=True)
        shutil.copy(RESTORE_SCRIPT, work / "scripts" / "restore_state.py")
        shutil.copytree(WEB, work / "web")
        registry = self.tmp / f"registry{run_id}.json"
        listed = [{"databaseId": run_id, "workflow": "publish-site.yml",
                   "status": "in_progress", "conclusion": "", "artifacts": {}}] + self.registry
        registry.write_text(json.dumps(listed), encoding="utf-8")
        env = {**os.environ, "PATH": self.path, "GH_TOKEN": "not-a-token",
               "FAKE_GH_REGISTRY": str(registry), "FAKE_GH_LOG": str(self.tmp / "gh.log")}

        # `continue-on-error: true`: the job goes on whatever the step returns.
        restored = self._bash(_run_block("Restore the lab's latest state and the site's history"),
                              work, env)
        self.logs[run_id] = restored.stdout + restored.stderr
        assembled = self._bash(_run_block("Assemble the site"), work, env)
        assert assembled.returncode == 0, assembled.stderr

        self.monkeypatch.chdir(work)
        self.monkeypatch.setattr(team_names, "RAW_DIR", work / "data" / "raw")
        self.monkeypatch.setattr(team_names, "PROCESSED_DIR", work / "processed-unused")
        for line in _run_block("Build today's board and yesterday's results").splitlines():
            tokens = shlex.split(line)
            if not tokens:
                continue
            if tokens[0] == "python":
                script = tokens[1]
                assert script in {"web/build_site_json.py", "web/site_history.py"}, (
                    f"the build step runs {script}, which this harness does not drive"
                )
                module = load_by_path(work / script, f"_publish_{Path(script).stem}_{run_id}")
                if script == "web/build_site_json.py":
                    arm_build(module, self.monkeypatch, when)
                else:
                    self.monkeypatch.setattr(module, "datetime", clock(when))
                assert module.main(tokens[2:]) == 0, line
            else:
                done = self._bash(line, work, env)
                assert done.returncode == 0, done.stderr

        history = work / _history_upload_path()
        artifacts = {}
        if history.is_dir() and any(history.iterdir()):
            kept = self.tmp / "artifacts" / str(run_id) / "site-history"
            shutil.copytree(history, kept)
            artifacts["site-history"] = str(kept)
        self.registry.insert(0, {"databaseId": run_id, "workflow": "publish-site.yml",
                                 "status": "completed", "conclusion": "success",
                                 "artifacts": artifacts})
        return work


def site(work: Path, name: str) -> dict:
    return json.loads((work / "dist" / "data" / name).read_text(encoding="utf-8"))


@pytest.fixture
def actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Actions:
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    return Actions(tmp_path, monkeypatch)


# -- the tests -------------------------------------------------------------------


@pytest.mark.parametrize("primary", ["running", "dropped"])
def test_the_results_page_grades_the_board_built_on_last_nights_results(
    actions: Actions, primary: str
) -> None:
    """The finding's sequence, through the workflow's own restore.

    `running`: the cron build starts while today's Gameday Refresh is in
    progress. `dropped`: GitHub dropped the 13:30 primary, and the 15:00
    backup completes after the 14:45 publish.
    """
    actions.gameday(1001, through=TWO_NIGHTS_AGO)  # yesterday morning's run
    if primary == "running":
        actions.gameday(1002, through=None, running=True)

    cron = actions.publish(CRON)

    # The premise: the cron build really did restore yesterday's state, and
    # yesterday's state really does lose the back-to-back.
    assert "gameday-refresh.yml run 1001" in actions.logs[2001], actions.logs[2001]
    assert back_to_back_sides(site(cron, f"history/{DAY.isoformat()}.json")) == []

    actions.gameday(1002, through=LAST_NIGHT)  # today's run completes
    after = actions.publish(AFTER_GAMEDAY)  # the workflow_run build it triggers

    assert "gameday-refresh.yml run 1002" in actions.logs[2002], actions.logs[2002]
    live = site(after, "board.json")
    assert back_to_back_sides(live) == ["OTT"], "the fresh state carries the flag"
    history = site(after, f"history/{DAY.isoformat()}.json")
    assert back_to_back_sides(history) == ["OTT"], (
        "the day's history still holds the board built on yesterday's state: "
        "no back-to-back, and TeamModel fitted without last night's game"
    )
    assert history["games"] == live["games"]
    assert history["resultsThrough"] == LAST_NIGHT.isoformat()

    actions.gameday(1003, through=DAY)  # the next morning's run
    morning = actions.publish(NEXT_MORNING)

    results = site(morning, "results.json")
    assert results["resultsDate"] == DAY.isoformat()
    graded = {g["id"]: g for g in results["games"]}
    shown = {g["id"]: g for g in live["games"]}
    assert set(graded) == set(shown) == {game_id for _, _, game_id, _ in SLATE}
    for game_id, row in graded.items():
        for side in ("away", "home"):
            assert row[side]["projGoals"] == shown[game_id][side]["projGoals"], (
                f"{game_id} {side}: the Results page graded a projection the "
                "board built on last night's results did not show"
            )


def test_a_board_built_on_newer_results_replaces_the_frozen_one_before_puck_drop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path]
) -> None:
    out = tmp_path / "out"
    stale = build(labs["stale"], out, monkeypatch, CRON)
    assert back_to_back_sides(stale) == []

    fresh = build(labs["fresh"], out, monkeypatch, AFTER_GAMEDAY)

    assert ott(fresh)["b2b"] is True
    assert frozen(out)["games"] == fresh["games"], (
        "a board built on later results, before any game started, did not "
        "replace the board built on yesterday's state"
    )
    assert frozen(out)["generatedAt"] == fresh["generatedAt"]
    assert stale["resultsThrough"] == TWO_NIGHTS_AGO.isoformat()
    assert frozen(out)["resultsThrough"] == LAST_NIGHT.isoformat()


@pytest.mark.parametrize("late", [FIRST_PUCK, "2026-10-28T23:05:00+00:00"],
                         ids=["at-the-first-puck-drop", "after-it"])
def test_once_a_game_has_started_the_frozen_board_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path], late: str
) -> None:
    out = tmp_path / "out"
    build(labs["stale"], out, monkeypatch, CRON)
    before = frozen_path(out).read_bytes()

    live = build(labs["fresh"], out, monkeypatch, late)

    assert ott(live)["b2b"] is True, "the live board still moves on"
    assert frozen_path(out).read_bytes() == before, (
        "a board built after the first puck drop rewrote the day's record"
    )


def test_a_matinee_that_has_started_holds_the_whole_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path]
) -> None:
    """BOS @ TOR at 13:00 New York has started; OTT @ CHI has not. A whole
    board is replaced or kept, and a game already under way is never
    re-projected, so it is kept."""
    matinee = {"2026020151": "2026-10-28T17:00:00Z"}
    out = tmp_path / "out"
    build(labs["stale"], out, monkeypatch, "2026-10-28T16:30:00+00:00", starts=matinee)
    before = frozen_path(out).read_bytes()

    build(labs["fresh"], out, monkeypatch, "2026-10-28T18:00:00+00:00", starts=matinee)

    assert frozen_path(out).read_bytes() == before


def test_an_older_or_equal_state_never_replaces_the_frozen_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path]
) -> None:
    """Within one state the day's first published opinion still stands."""
    out = tmp_path / "out"
    build(labs["fresh"], out, monkeypatch, CRON)
    before = frozen_path(out).read_bytes()

    build(labs["stale"], out, monkeypatch, AFTER_GAMEDAY)  # a restore that fell back
    assert frozen_path(out).read_bytes() == before, "an older state replaced a newer one"

    build(labs["fresh"], out, monkeypatch, "2026-10-28T19:30:00+00:00")  # same results, later
    assert frozen_path(out).read_bytes() == before, "a rebuild on the same results replaced it"

    build(labs["empty"], out, monkeypatch, "2026-10-28T20:00:00+00:00")  # a restore that found nothing
    assert frozen_path(out).read_bytes() == before, "a board with no model replaced one with it"


def test_a_board_built_without_the_model_is_replaced_by_one_built_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path]
) -> None:
    """A cron build whose restore found nothing publishes the schedule only.
    Frozen first, it graded nothing the next morning."""
    out = tmp_path / "out"
    bare = build(labs["empty"], out, monkeypatch, CRON)
    assert all("projGoals" not in g["home"] for g in bare["games"])
    before = frozen_path(out).read_bytes()
    build(labs["empty"], out, monkeypatch, "2026-10-28T18:45:00+00:00")
    assert frozen_path(out).read_bytes() == before, (
        "two boards with no results date: the later one is not newer, and the "
        "first stands exactly as it always did"
    )

    build(labs["fresh"], out, monkeypatch, AFTER_GAMEDAY)

    assert back_to_back_sides(frozen(out)) == ["OTT"]
    assert all("projGoals" in g["home"] for g in frozen(out)["games"])
    assert bare["resultsThrough"] is None


@pytest.mark.parametrize("unreadable_on", ["frozen-board", "new-board"])
def test_a_start_time_that_cannot_be_read_keeps_the_frozen_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path], unreadable_on: str
) -> None:
    """A start that cannot be confirmed as still to come is treated as
    started, on either board: the doubt falls on leaving the record alone."""
    tbd = {"2026020150": "TBD"}
    out = tmp_path / "out"
    build(labs["stale"], out, monkeypatch, CRON,
          starts=tbd if unreadable_on == "frozen-board" else None)
    before = frozen_path(out).read_bytes()

    build(labs["fresh"], out, monkeypatch, AFTER_GAMEDAY,
          starts=tbd if unreadable_on == "new-board" else None)

    assert frozen_path(out).read_bytes() == before


def test_a_frozen_board_whose_results_date_cannot_be_read_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path]
) -> None:
    """Unknown is not "earlier". A results date that is present and does not
    parse cannot be shown to be older, so the record is left alone."""
    out = tmp_path / "out"
    build(labs["stale"], out, monkeypatch, CRON)
    standing = frozen(out)
    standing["resultsThrough"] = "last Tuesday"
    frozen_path(out).write_text(json.dumps(standing), encoding="utf-8")
    before = frozen_path(out).read_bytes()

    build(labs["fresh"], out, monkeypatch, AFTER_GAMEDAY)

    assert frozen_path(out).read_bytes() == before


@pytest.mark.parametrize("contents", [b"\xff\xfe{not json", b"[]"], ids=["not-json", "not-an-object"])
def test_a_frozen_file_that_cannot_be_read_is_left_alone_and_the_build_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path], contents: bytes
) -> None:
    """The old freeze only asked whether the file existed. Reading it is new,
    and a file that does not parse must neither stop the site being built
    nor be overwritten as though it were stale."""
    out = tmp_path / "out"
    frozen_path(out).parent.mkdir(parents=True)
    frozen_path(out).write_bytes(contents)

    live = build(labs["fresh"], out, monkeypatch, AFTER_GAMEDAY)

    assert ott(live)["b2b"] is True
    assert frozen_path(out).read_bytes() == contents


@pytest.mark.parametrize(
    ("newer", "when", "replaced"),
    [
        ("fresh", AFTER_GAMEDAY, True),
        ("fresh", "2026-10-28T23:05:00+00:00", False),
        ("stale", AFTER_GAMEDAY, False),
        ("older", AFTER_GAMEDAY, False),
    ],
    ids=["later-results-before-puck-drop", "after-puck-drop", "same-results", "older-results"],
)
def test_site_history_on_its_own_follows_the_same_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, labs: dict[str, Path],
    newer: str, when: str, replaced: bool,
) -> None:
    """`web/site_history.py` freezes too. Built after the stale board froze,
    a board.json is handed to it alone, over the stale history."""
    stale_out, newer_out = tmp_path / "stale-out", tmp_path / "newer-out"
    build(labs["stale"], stale_out, monkeypatch, CRON)
    board = build(labs[newer], newer_out, monkeypatch, "2026-10-28T18:45:00+00:00")
    data = tmp_path / "data"
    (data / "history").mkdir(parents=True)
    shutil.copyfile(frozen_path(stale_out), frozen_path(data))
    (data / "board.json").write_text(json.dumps(board), encoding="utf-8")
    before = frozen_path(data).read_bytes()
    module = load_by_path(WEB / "site_history.py", "_site_history_stale_state")
    monkeypatch.setattr(module, "datetime", clock(when))

    assert module.main(["--data", str(data)]) == 0

    if replaced:
        assert frozen(data)["games"] == board["games"]
        assert frozen(data)["resultsThrough"] == LAST_NIGHT.isoformat()
    else:
        assert frozen_path(data).read_bytes() == before


def test_the_archive_page_does_not_promise_a_freeze_the_site_does_not_keep() -> None:
    """The Archive said each board is "frozen the moment it is first
    published and never edited". A board built before last night's results
    arrived is now replaced until the first game starts, so the page says
    that instead of the promise."""
    page = (WEB / "Archive.dc.html").read_text(encoding="utf-8")
    assert "first published and never edited" not in page
    assert "Until the first game starts" in page
