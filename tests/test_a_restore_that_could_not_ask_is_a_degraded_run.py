"""A restore that could not ask GitHub read as a restore that found nothing.

Gameday Refresh restores its state with `restore_state.py --artifact
gameday-state --workflow gameday-refresh.yml --workflow
historical-props-purchase.yml`, and made one attempt at every call. A listing
that failed was printed and then read exactly like an empty one, so the
script moved on to the next workflow; a download that failed for any reason
was read as a run without the artifact, so it moved on to the run before.
Nothing downstream knew: the health step counted boxscores, results and
prices, and no step read the restore's outcome.

Found by the failure-shape audit (restore_state.py:190) and confirmed by all
three refuters (reproduce, reachability, intent). Their replays of the real
step with an offline gh, over a mid-season week:

* One HTTP 502 on the gameday-refresh.yml listing printed "Restored
  gameday-state from historical-props-purchase.yml run 7 (success)" and
  exited 0. The purchase's gameday-state has never carried data/archive (the
  live one, run 33450963332, holds 3,936 boxscores and no archive, and is
  kept until 2026-11-29), so the six rows frozen on 2026-01-09 were not there
  to settle. The cache was full, so the run was green (degraded=false); its
  upload held only 2026-01-10.csv; the next day restored that green run, and
  the fill that lays the last success under a red run never ran. The control
  ledger held 01-06 to 01-10, the replay's 01-06, 07, 08 and 10: 2026-01-09's
  frozen opinions were gone for good.
* With an older ledger in the purchase's data/processed, the card-feed
  ledger fallback was skipped as well: 20 rows restored where card-feed held
  54, and the 20-row file was the one card-feed then published.
* Both listings failing printed the false "No completed run of
  gameday-refresh.yml, historical-props-purchase.yml on main carries
  gameday-state" and started cold.
* One 502 on the newest carrier's download, with the listing fine, restored
  the run before it and printed nothing about the one it passed over; green
  again, and 2026-01-09 lost the same way.

These tests run Gameday Refresh's own "Restore the previous state" step,
taken from the workflow file, under `bash --noprofile --norc -eo pipefail`,
with the real scripts/restore_state.py, an offline `gh` that replays a run
history and injects HTTP 502s (counted, so "once" and "on every attempt" are
different scenarios), and an offline `git` serving card-feed's ledger. Then
the real "Record what went wrong" step, for a run whose results and prices
were clean, so only the restore can make it degraded. The chain test goes on
to the next day's restore from what that run would have uploaded — the paths
"Upload the state for the next run" names — with the run's conclusion taken
from the health step's own output.

A restore that could not be asked at all still starts cold, and the card
still freezes that thin-history opinion; whether it should is a change to
which opinions the forward ledger holds, and is left to the owner.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"
REFRESH, PURCHASE, ARTIFACT = (
    "gameday-refresh.yml", "historical-props-purchase.yml", "gameday-state",
)

#: The health step's expressions for a run whose results and prices were
#: fetched cleanly: only the restore can make such a run degraded.
CLEAN = {
    "steps.results.outcome": "success",
    "steps.prices.outputs.empty_slate": "false",
    "steps.prices.outcome": "success",
}

#: Ledger rows each day's frozen snapshot settles into. 01-06..01-08 are the
#: 54 rows card-feed held in the reproduce refuter's replay; 01-09 is the day
#: whose six rows were lost.
ROWS = {"2026-01-06": 20, "2026-01-07": 18, "2026-01-08": 16, "2026-01-09": 6}

#: Every run on main, as `gh run list --branch main` would list them; an
#: artifact is a directory, and a run with none is a skipped backup.
FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["FAKE_GH_STATE"])
with open(state / "gh.log", "a") as log:
    log.write(" ".join(args) + "\n")
registry = json.loads((state / "registry.json").read_text())
failures_path = state / "failures.json"
failures = json.loads(failures_path.read_text()) if failures_path.exists() else {{}}

def value(flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default

def injected(key, message):
    if failures.get(key, 0) > 0:
        failures[key] -= 1
        failures_path.write_text(json.dumps(failures))
        print(message, file=sys.stderr)
        sys.exit(1)

if args[:2] == ["run", "list"]:
    workflow = value("--workflow")
    injected("list:" + workflow, "HTTP 502: Bad Gateway (https://api.github.com/"
             "repos/owner/nhl-betting-lab/actions/workflows/" + workflow + "/runs)")
    runs = [r for r in registry if r["workflow"] == workflow]
    branch = value("--branch")
    if branch:
        runs = [r for r in runs if r["headBranch"] == branch]
    status = value("--status")
    if status:
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    fields = [f for f in value("--json", "").split(",") if f]
    print(json.dumps([{{k: r[k] for k in fields}} for r in runs]))
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    injected("download:" + run_id + ":" + name,
             "error downloading " + name + ": HTTP 502: Bad Gateway")
    run = next((r for r in registry if str(r["databaseId"]) == run_id), {{}})
    held = run.get("artifacts") or {{}}
    # What gh 2.97.0 says for a run with no artifact at all, and for one
    # without the named artifact.
    if not held:
        print("no valid artifacts found to download", file=sys.stderr)
        sys.exit(1)
    if name not in held:
        print("no artifact matches any of the names or patterns provided",
              file=sys.stderr)
        sys.exit(1)
    shutil.copytree(held[name], dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''

#: card-feed holds the ledger run 101 published.
FAKE_GIT = """#!/bin/sh
case "$1" in
  fetch) exit 0;;
  cat-file) exit 0;;
  show) cat "$CARD_FEED_LEDGER"; exit 0;;
esac
exit 1
"""


def _ledger(days: tuple[str, ...]) -> str:
    return "snapshot_date,outcome\n" + "".join(
        f"{day},won\n" for day in days for _ in range(ROWS[day])
    )


def _state(root: Path, *, games: int, settled: tuple[str, ...] = (),
           pending: tuple[str, ...] = (), ledger: tuple[str, ...] | None = None,
           card: str = "") -> Path:
    """An artifact as `Upload the state for the next run` lays it out,
    relative to data/."""
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(games):
        (box / f"{2025020001 + game}.json").write_text("{}", encoding="utf-8")
    processed = root / "processed"
    processed.mkdir(parents=True)
    (processed / "player_game_logs.csv").write_text("game_id,player_id\n1,2\n",
                                                   encoding="utf-8")
    if ledger is not None:
        (processed / "forward_evidence.csv").write_text(_ledger(ledger),
                                                        encoding="utf-8")
    archive = root / "archive" / "priced_snapshots"
    for day in (*settled, *pending):
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"{day}.csv").write_text("snapshot_date\n", encoding="utf-8")
    for day in settled:
        (archive / f"{day}.settled").touch()
    if card:
        (root / "outputs").mkdir()
        (root / "outputs" / "gameday_card.json").write_text(
            json.dumps({"day": card}), encoding="utf-8")
    return root


def _run(run_id: int, conclusion: str, artifact: Path | None = None, *,
         workflow: str = REFRESH, status: str = "completed",
         name: str = ARTIFACT) -> dict:
    return {"databaseId": run_id, "workflow": workflow, "status": status,
            "conclusion": conclusion, "headBranch": "main",
            "artifacts": {name: str(artifact)} if artifact else {}}


@dataclass(frozen=True)
class World:
    """Run 100 froze 2026-01-08 and run 101 froze 2026-01-09, both green; a
    skipped backup followed each. The purchase's state has a full cache, an
    older ledger and no archive. card-feed holds run 101's ledger."""
    a100: Path
    a101: Path
    cold102: Path
    purchase: Path
    card_feed: Path

    def history(self, *newer: dict) -> list[dict]:
        """`gh run list` for a run on 2026-01-10, newest first, with any
        newer runs on top of it."""
        return [
            *newer,
            _run(1015, "success"),  # the 15:00 backup on 01-09: skipped
            _run(101, "success", self.a101),
            _run(1005, "success"),  # the 15:00 backup on 01-08: skipped
            _run(100, "success", self.a100),
            _run(7, "success", self.purchase, workflow=PURCHASE),
        ]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    root = tmp_path_factory.mktemp("artifacts")
    card_feed = root / "card_feed_ledger.csv"
    card_feed.write_text(_ledger(("2026-01-06", "2026-01-07", "2026-01-08")),
                         encoding="utf-8")
    return World(
        a100=_state(root / "a100", games=1000, settled=("2026-01-06", "2026-01-07"),
                    pending=("2026-01-08",), ledger=("2026-01-06", "2026-01-07"),
                    card="2026-01-08"),
        a101=_state(root / "a101", games=1000,
                    settled=("2026-01-06", "2026-01-07", "2026-01-08"),
                    pending=("2026-01-09",),
                    ledger=("2026-01-06", "2026-01-07", "2026-01-08"),
                    card="2026-01-09"),
        # A red run on 2026-01-10 whose own restore found nothing: 600 games
        # fetched cold, the ledger from card-feed, only its own snapshot.
        cold102=_state(root / "cold102", games=600, pending=("2026-01-10",),
                       ledger=("2026-01-06", "2026-01-07", "2026-01-08"),
                       card="2026-01-10"),
        purchase=_state(root / "a7", games=1000, ledger=("2026-01-06",)),
        card_feed=card_feed,
    )


# --------------------------------------------------------------------------
# The workflow's own steps.
# --------------------------------------------------------------------------

def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        steps = job.get("steps", [])
        if any(step.get("id") == "restore" for step in steps):
            return steps
    raise AssertionError("no job in gameday-refresh.yml restores the state")


def _block(*, id_: str = "", name: str = "") -> dict:
    for step in _steps():
        if (id_ and step.get("id") == id_) or (name and step.get("name") == name):
            return step
    raise AssertionError(f"no step {id_ or name} in gameday-refresh.yml")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions named; refuse any that is not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _upload_paths() -> list[str]:
    step = _block(name="Upload the state for the next run")
    return [line.strip() for line in str(step["with"]["path"]).splitlines()
            if line.strip()]


@dataclass
class Day:
    work: Path
    log: str
    gh: list[str]
    degraded: str
    notes: str

    @property
    def archive(self) -> Path:
        return self.work / "data" / "archive" / "priced_snapshots"

    def snapshots(self) -> list[str]:
        return sorted(p.name for p in self.archive.glob("*")) if self.archive.is_dir() else []

    def ledger(self) -> str:
        return (self.work / "data" / "processed" / "forward_evidence.csv").read_text(
            encoding="utf-8")

    def downloads(self, run_id: int) -> int:
        return sum(1 for call in self.gh if call.startswith(f"run download {run_id} "))

    def problems(self) -> str:
        path = self.work / "restore_problem.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def upload(self, dest: Path, *, freeze: str) -> Path:
        """What the run leaves for the next one: the card freezes `freeze`,
        then "Upload the state for the next run" keeps the paths it names
        (all under data/, the artifact's root)."""
        self.archive.mkdir(parents=True, exist_ok=True)
        (self.archive / f"{freeze}.csv").write_text("snapshot_date\n", encoding="utf-8")
        for name in _upload_paths():
            source = self.work / name
            target = dest / Path(name).relative_to("data")
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        return dest

    @property
    def conclusion(self) -> str:
        """As "Report the outcome" decides it: red unless the health said
        `degraded=false` (nothing after the health step fails in these runs)."""
        return "success" if self.degraded == "false" else "failure"


def _day(tmp_path: Path, world: World, registry: list[dict],
         failures: dict[str, int] | None = None, *, name: str = "run") -> Day:
    """One Gameday Refresh run's restore step and health step."""
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    state = tmp_path / f"{name}-gh"
    state.mkdir()
    (state / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (state / "failures.json").write_text(json.dumps(failures or {}), encoding="utf-8")
    bin_dir = tmp_path / f"{name}-bin"
    bin_dir.mkdir()
    for tool, text in (("gh", FAKE_GH.format(python=sys.executable)), ("git", FAKE_GIT)):
        path = bin_dir / tool
        path.write_text(text, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    work = tmp_path / name
    (work / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, work / "scripts" / "restore_state.py")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        "FAKE_GH_STATE": str(state),
        "CARD_FEED_LEDGER": str(world.card_feed),
        "GH_TOKEN": "not-a-token",
        # restore_state.py pauses 10s, then 20s, between attempts; not here.
        "RESTORE_STATE_RETRY_SECONDS": "0",
    }

    restore = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _render(_block(id_="restore")["run"],
                 {"github.repository": "owner/nhl-betting-lab"})],
        cwd=work, env=env, capture_output=True, text=True, timeout=120,
    )
    # The step is continue-on-error, but it has never failed on a restore
    # and must not start to: the ledger fallback below the call must run.
    assert restore.returncode == 0, restore.stdout + restore.stderr

    output = work / "health_output"
    output.write_text("", encoding="utf-8")
    health = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
         _render(_block(id_="health")["run"], CLEAN)],
        cwd=work, env={**env, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True, timeout=60,
    )
    assert health.returncode == 0, health.stdout + health.stderr
    outputs = dict(line.partition("=")[::2]
                   for line in output.read_text(encoding="utf-8").splitlines())
    return Day(
        work=work,
        log=restore.stdout + restore.stderr,
        gh=(state / "gh.log").read_text(encoding="utf-8").splitlines(),
        degraded=outputs.get("degraded", ""),
        notes=(work / "run_degraded.txt").read_text(encoding="utf-8"),
    )


def _today(world: World) -> list[dict]:
    """The run on 2026-01-10: its own run is listed, still in progress."""
    return world.history(_run(102, "", status="in_progress"))


# --------------------------------------------------------------------------
# One transient failure is retried, and the newest carrier is restored.
# --------------------------------------------------------------------------

def test_one_502_on_the_listing_is_retried_and_yesterdays_snapshot_settles(
    tmp_path: Path, world: World,
) -> None:
    """The finding's scenario (a): one 502 on the gameday-refresh.yml listing
    restored the purchase's state, which has no snapshot archive."""
    day = _day(tmp_path, world, _today(world), {f"list:{REFRESH}": 1})

    assert "2026-01-09.csv" in day.snapshots(), day.log
    assert "2026-01-09.settled" not in day.snapshots(), "so this run settles it"
    assert "2026-01-09" not in day.ledger()
    assert day.downloads(7) == 0, "the purchase's state stood in for the refresh's"
    assert day.degraded == "false", day.notes


def test_one_502_on_the_newest_download_is_retried_not_passed_over(
    tmp_path: Path, world: World,
) -> None:
    """One 502 on run 101's download restored run 100, which froze 01-08 and
    never saw 01-09, and said nothing about run 101."""
    day = _day(tmp_path, world, _today(world), {f"download:101:{ARTIFACT}": 1})

    assert "2026-01-09.csv" in day.snapshots(), day.log
    assert day.downloads(100) == 0, "an older run stood in for the newest carrier"
    assert day.degraded == "false", day.notes


# --------------------------------------------------------------------------
# A failure that outlasts the attempts is said, and makes the run degraded.
# --------------------------------------------------------------------------

def test_a_listing_that_never_answers_is_not_read_as_no_runs(
    tmp_path: Path, world: World,
) -> None:
    """GitHub did not answer, which is not "no refresh run carries the
    state": the purchase's state is the fallback for a first run, not for an
    outage, and here it would also have brought its older 20-row ledger in
    place of card-feed's 54."""
    day = _day(tmp_path, world, _today(world), {f"list:{REFRESH}": 99})

    assert day.downloads(7) == 0, "the purchase's state stood in for the refresh's"
    assert "No completed run" not in day.log, "a failed listing was reported as an empty one"
    assert day.ledger() == world.card_feed.read_text(encoding="utf-8"), (
        "the ledger did not come from card-feed"
    )
    problems = day.problems()
    assert f"GitHub did not answer when asked for the {REFRESH} runs" in problems
    assert f"{PURCHASE} was not consulted" in problems
    assert day.degraded == "true"
    assert f"GitHub did not answer when asked for the {REFRESH} runs" in day.notes, (
        "the health step never read what the restore could not ask"
    )


def test_a_download_that_never_succeeds_makes_the_run_degraded(
    tmp_path: Path, world: World,
) -> None:
    """The run before the newest carrier still stands in for it, as the
    restore has always done — but the run says so and is red, which is what
    makes tomorrow's restore lay run 101 underneath."""
    day = _day(tmp_path, world, _today(world), {f"download:101:{ARTIFACT}": 99})

    assert "Restored gameday-state from gameday-refresh.yml run 100" in day.log
    assert "2026-01-09.csv" not in day.snapshots()
    assert f"Could not download {ARTIFACT} from {REFRESH} run 101" in day.problems()
    # Everything else about this run is clean: a full cache, player logs,
    # results and prices. Only the restore can have made it degraded.
    assert day.degraded == "true", "a run that lost yesterday's snapshot was green"
    assert "run 101" in day.notes


def test_no_carrier_that_answers_does_not_fall_through_to_the_purchase(
    tmp_path: Path, world: World,
) -> None:
    """Both refresh carriers exist and neither could be downloaded: that is
    not "no refresh run carries the state" either."""
    day = _day(tmp_path, world, _today(world),
               {f"download:101:{ARTIFACT}": 99, f"download:100:{ARTIFACT}": 99})

    assert day.downloads(7) == 0, "the purchase's state stood in for the refresh's"
    assert "No completed run" not in day.log
    assert f"{PURCHASE} was not consulted" in day.log
    assert day.degraded == "true"
    assert "run 101" in day.problems() and "run 100" in day.problems()


def test_an_absent_artifact_is_an_answer_not_a_problem(
    tmp_path: Path, world: World,
) -> None:
    """Two absences before the carrier, in gh's two wordings: the skipped
    15:00 backup holds no artifact at all (every clean day), and a run that
    died between "Upload the reports" and "Upload the state" holds only
    gameday-reports. Neither is asked again, and neither is a fault — or
    every clean day would be a red one."""
    reports = tmp_path / "reports-only"
    reports.mkdir()
    (reports / "gameday_card.md").write_text("card", encoding="utf-8")
    registry = world.history(
        _run(102, "", status="in_progress"),
        _run(1016, "failure", reports, name="gameday-reports"),
    )

    day = _day(tmp_path, world, registry)

    assert "2026-01-09.csv" in day.snapshots(), day.log
    assert day.downloads(1016) == 1, "an absence was asked again"
    assert day.downloads(1015) == 1, "an absence was asked again"
    assert day.problems() == ""
    assert day.degraded == "false", day.notes


# --------------------------------------------------------------------------
# The success laid under a red run is retried and reported the same way.
# --------------------------------------------------------------------------

def _after_a_cold_red_run(world: World) -> list[dict]:
    """2026-01-11: the newest carrier is 01-10's red run, which started cold."""
    return world.history(_run(103, "", status="in_progress"),
                         _run(102, "failure", world.cold102))


def test_the_last_success_laid_under_a_red_run_is_retried(
    tmp_path: Path, world: World,
) -> None:
    day = _day(tmp_path, world, _after_a_cold_red_run(world),
               {f"download:101:{ARTIFACT}": 1})

    assert "run 101 (success) underneath" in day.log, day.log
    assert {"2026-01-09.csv", "2026-01-10.csv"} <= set(day.snapshots())
    assert day.downloads(100) == 0, "an older success was laid under the red run"
    assert day.degraded == "false", day.notes


def test_a_last_success_that_cannot_be_laid_underneath_makes_the_run_degraded(
    tmp_path: Path, world: World,
) -> None:
    day = _day(tmp_path, world, _after_a_cold_red_run(world),
               {f"download:101:{ARTIFACT}": 99})

    assert "2026-01-09.csv" not in day.snapshots()
    assert f"Could not download {ARTIFACT} from {REFRESH} run 101" in day.problems()
    assert day.degraded == "true", "the red run's gap was left open on a green run"


# --------------------------------------------------------------------------
# The chain: the snapshot a failed restore missed comes back the next day.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fault", [f"list:{REFRESH}", f"download:101:{ARTIFACT}"])
def test_the_snapshot_a_failed_restore_missed_settles_the_next_day(
    tmp_path: Path, world: World, fault: str,
) -> None:
    """The finding's end state: 2026-01-09 was frozen, a failed restore on
    01-10 left it out, and it never settled. It must come back on 01-11."""
    first = _day(tmp_path, world, _today(world), {fault: 99}, name="jan10")
    assert "2026-01-09.csv" not in first.snapshots()
    uploaded = first.upload(tmp_path / "a102", freeze="2026-01-10")

    second = _day(
        tmp_path, world,
        world.history(_run(103, "", status="in_progress"),
                      _run(102, first.conclusion, uploaded)),
        name="jan11",
    )

    assert "2026-01-09.csv" in second.snapshots(), (
        f"run 102 finished {first.conclusion} and 2026-01-09 was never restored "
        "again:\n" + second.log
    )
    assert "2026-01-10.csv" in second.snapshots()
    assert "2026-01-09.settled" not in second.snapshots(), "so this run settles it"
    assert "2026-01-09" not in second.ledger()


# --------------------------------------------------------------------------
# The strict path names an absence as one.
# --------------------------------------------------------------------------

def test_an_absent_newest_carrier_is_named_as_absent_under_require_newest(
    tmp_path: Path, world: World,
) -> None:
    """Publish Site's history restore refuses when the newest success holds
    no artifact (it expired). An absence is an answer and is not asked
    again; the refusal says it was an absence, not a failed download."""
    state = tmp_path / "gh"
    state.mkdir()
    (state / "registry.json").write_text(
        json.dumps([_run(9, "success", workflow="publish-site.yml")]), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--artifact", "site-history",
         "--dest", str(tmp_path / "history"), "--workflow", "publish-site.yml",
         "--success-only", "--require-newest", "--attempts", "3"],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
             "FAKE_GH_STATE": str(state), "RESTORE_STATE_RETRY_SECONDS": "0"},
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "holds no such artifact" in result.stdout, result.stdout
    downloads = [line for line in (state / "gh.log").read_text().splitlines()
                 if line.startswith("run download 9 ")]
    assert len(downloads) == 1, downloads


# --------------------------------------------------------------------------
# The union (Line Movement) reports a carrier it could not read too.
# --------------------------------------------------------------------------

def test_a_carrier_the_union_could_not_download_is_said(tmp_path: Path) -> None:
    """The union moved past an older carrier on any failure without a word;
    its rows then reached no copy of the store that run, and nothing said
    why. It still moves past it, and now says so — and a carrier that holds
    no artifact (run 25, cancelled before its upload) is still an answer."""
    carriers = {}
    for run_id, rows in ((3, "a\n1\n2\n"), (2, "a\n1\n"), (1, "a\n0\n")):
        root = tmp_path / f"lm{run_id}" / "line_movement"
        root.mkdir(parents=True)
        (root / "2026-10-15.csv").write_text(rows, encoding="utf-8")
        carriers[run_id] = root.parent
    state = tmp_path / "gh"
    state.mkdir()
    (state / "registry.json").write_text(json.dumps([
        _run(3, "success", carriers[3], workflow="line-movement.yml", name="line-movement"),
        _run(2, "success", carriers[2], workflow="line-movement.yml", name="line-movement"),
        _run(25, "cancelled", workflow="line-movement.yml"),
        _run(1, "success", carriers[1], workflow="line-movement.yml", name="line-movement"),
    ]), encoding="utf-8")
    (state / "failures.json").write_text(
        json.dumps({"download:2:line-movement": 99}), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    problems = tmp_path / "problems.txt"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--artifact", "line-movement",
         "--dest", str(tmp_path / "processed"), "--workflow", "line-movement.yml",
         "--union", "3", "--problem-file", str(problems)],
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
             "FAKE_GH_STATE": str(state), "RESTORE_STATE_RETRY_SECONDS": "0"},
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    said = "Could not download line-movement from line-movement.yml run 2"
    assert said in result.stdout, result.stdout
    assert said in problems.read_text(encoding="utf-8")
    assert "run 25" not in problems.read_text(encoding="utf-8"), "an absence was reported"
    assert "Unioned line-movement.yml run 1" in result.stdout, result.stdout
