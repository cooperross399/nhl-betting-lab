"""One failed site-history restore published "the history starts today", for good.

Publish Site restored the site's history with `gh run list --workflow
publish-site.yml --status success --limit 1` and `gh run download "$last"
--name site-history ... || echo "No site-history artifact on run $last."`,
inside a `continue-on-error` step. #131 moved the gameday-state restore onto
`scripts/restore_state.py` and left this one as it was. Either `gh` call can
fail on a transient API error (an HTTP 502 mid-run has been seen on this
account). A failed listing aborted the step under `bash -e` before the
"history starts today" line, and continue-on-error let the job carry on; a
failed download took the `|| echo` path and the step was green. Either way
`web/site_history.py` froze today's board alone and rewrote `index.json`
with one entry, the run concluded success, and "Keep the history for
tomorrow's settlement" uploaded that as `site-history` — which the next
run's `--status success --limit 1` then restored. Every earlier frozen board
(the published opinion Results settles against) and every line series fell
out of the chain for good, and nothing compared the new history with the
one before it.

Found by the failure-shape audit and confirmed 3/3 by the refuters
(reproduce, reachability, intent). Their replays of the real step under
`bash -e` with a fake `gh`: a three-board history (2026-03-10, -11, -12;
13, 2 and 14 games) became one board after one 502 on the listing, the next
healthy run restored two, and the boards for 03-10, 03-11 and 03-12 never
came back; the same on a 502 on the download; a six-board history became
one. Results for 2026-03-12 said "No board was published for this date, so
there is nothing to settle." about a board published with 14 games. And when
the failure hit the second publish of a day, that run froze the day again,
so the day's first published opinion was replaced by a later build and the
replacement was carried forward. The suite passed 2197 tests with no test
reading the Publish Site restore. The live chain held 4 boards on
2026-09-25 (run 36176147420).

These tests run Publish Site's steps in order, as GitHub would: every `run:`
block from the workflow file under `bash --noprofile --norc -eo pipefail`
with an offline `gh` on PATH (the one in
test_a_red_capture_run_stays_in_the_chain.py, plus injected HTTP 502s), the
build step through the real `web/build_site_json.py` and `web/site_history.py`
`main()`s with only the NHL schedule stubbed, `continue-on-error` and
`if: always()` honoured from the YAML, and each `upload-artifact` and Pages
deploy taken from the paths the YAML names. The floor check itself is also
driven directly, through `scripts/site_history_floor.py`'s `main()`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-site.yml"
WEB = PROJECT_ROOT / "web"
SCRIPTS = PROJECT_ROOT / "scripts"
NO_BOARD = "No board was published for this date, so there is nothing to settle."
#: A restore that cannot establish the history stops the job at this step,
#: before anything is built, and not only at the floor check further on.
HISTORY_STEP = "Restore the site's history"

D1, D2, D3, D4, D5 = (date(2026, 10, day) for day in range(5, 10))
#: Publish Site's live Archive, as its own step env names it.
LIVE_INDEX = "https://nhl.maverickhightower.com/data/history/index.json"

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
    # A listing that has not caught up (2026-10-05): these runs are missing
    # from it, so an older run comes first.
    stale = set(failures.get("stale-listing", []))
    runs = [r for r in runs if r["databaseId"] not in stale]
    # As `gh run list --branch` does. Every run here ran on main unless a
    # test says otherwise; restore_state.py asks for main and checks it.
    branch = value("--branch")
    if branch:
        runs = [r for r in runs if r.get("headBranch", "main") == branch]
    status = value("--status")
    if status:
        # As `gh run list --help` documents it: a status or a conclusion.
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    fields = [f for f in value("--json", "").split(",") if f]
    rows = [{{k: r.get(k, "main") if k == "headBranch" else r[k] for k in fields}}
            for r in runs]
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
if args[:1] == ["api"]:
    path = args[1]
    if "/actions/artifacts?" in path:
        injected("api:artifacts", "HTTP 502: Bad Gateway (https://api.github.com/" + path + ")")
        assert "--paginate" in args and "--slurp" in args, args
        name = path.split("name=")[1].split("&")[0]
        hidden = set(failures.get("stale-artifacts", []))
        found = []
        for r in registry:
            source = (r.get("artifacts") or {{}}).get(name)
            if source is None or r["databaseId"] in hidden:
                continue
            found.append({{"id": r["databaseId"] * 10, "name": name, "expired": False,
                          "created_at": r["created_at"],
                          "workflow_run": {{"id": r["databaseId"],
                                           "head_branch": r.get("headBranch", "main")}}}})
        # The API's own order is not relied on: oldest first here.
        found.sort(key=lambda a: a["created_at"])
        pages = [{{"total_count": len(found), "artifacts": found[i:i + 2]}}
                 for i in range(0, max(len(found), 1), 2)]
        print(json.dumps(pages))
        sys.exit(0)
    if "/actions/runs/" in path:
        run_id = path.rsplit("/", 1)[1]
        injected("api:run:" + run_id, "HTTP 502: Bad Gateway")
        run = next((r for r in registry if str(r["databaseId"]) == run_id), None)
        if run is None:
            print("HTTP 404: Not Found", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({{"id": run["databaseId"], "path": ".github/workflows/" + run["workflow"],
                          "status": run["status"], "conclusion": run["conclusion"] or None,
                          "head_branch": run.get("headBranch", "main")}}))
        sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    injected("download:" + run_id + ":" + name,
             "error downloading " + name + ": HTTP 502: Bad Gateway")
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


def _web_module(name: str):
    """A `web/` script, loaded by path as the workflow runs it."""
    path = WEB / name
    spec = importlib.util.spec_from_file_location(f"_publish_chain_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    jobs = _workflow()["jobs"]
    assert list(jobs) == ["publish"], "Publish Site is expected to be one job"
    return jobs["publish"]["steps"]


def _dispatch_inputs() -> dict:
    triggers = _workflow()
    # PyYAML reads the bare key `on` as the boolean True.
    on = triggers.get("on", triggers.get(True)) or {}
    return (on.get("workflow_dispatch") or {}).get("inputs") or {}


@dataclass
class Outcome:
    run_id: int
    conclusion: str
    log: str
    artifacts: dict = field(default_factory=dict)
    deployed: dict | None = None
    #: The step whose failure failed the job, if one did.
    failed_at: str | None = None

    @property
    def boards(self) -> list[str]:
        """The dates the deployed Archive lists, newest first."""
        assert self.deployed is not None, f"run {self.run_id} deployed nothing"
        return [entry["date"] for entry in self.deployed["index"]["dates"]]


class PublishSite:
    """Publish Site's runs, one after another, as GitHub would run them."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.registry: list[dict] = []  # newest first, as `gh run list` lists
        self.next_id = 1001
        self.deploys: list[Outcome] = []
        self.uploads: list[tuple[int, Path]] = []
        self.venue = "Arena"
        self.state = tmp_path / "gh"
        self.state.mkdir()
        # The public site: whatever the last deploy put there, nothing before.
        self.live = tmp_path / "live" / "index.json"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.path = f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
        self.build = _web_module("build_site_json.py")
        self.history = _web_module("site_history.py")
        monkeypatch.setattr(self.build, "schedule_for", self._schedule)
        # Nothing here may read the operator's data tree.
        monkeypatch.setattr(team_names, "RAW_DIR", tmp_path / "raw-unused")
        monkeypatch.setattr(team_names, "PROCESSED_DIR", tmp_path / "processed-unused")

    # -- the world outside ---------------------------------------------------

    def _schedule(self, day: date) -> list[dict]:
        """Two regular-season games a night; `venue` marks which build saw them."""
        games = []
        for n, (away, home) in enumerate((("MTL", "TOR"), ("BOS", "NYI"))):
            games.append({
                "id": int(f"{day:%Y%m%d}{n}"), "gameType": 2,
                "startTimeUTC": f"{day.isoformat()}T23:00:00Z",
                "venue": {"default": self.venue}, "venueLocation": {"default": "City"},
                "tvBroadcasts": [],
                "awayTeam": {"abbrev": away, "record": "1-0-0"},
                "homeTeam": {"abbrev": home, "record": "1-0-0"},
            })
        return games

    @staticmethod
    def created(run_id: int) -> str:
        """When the run (and so its artifact) was created: in id order."""
        return (datetime(2026, 10, 1) + timedelta(minutes=run_id)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def red(self, conclusion: str = "failure", *, artifacts: dict | None = None,
            branch: str = "main") -> int:
        """A completed run that uploaded nothing (cancelled, or failed early),
        or, with `artifacts`, one that uploaded them and then failed."""
        run_id = self.next_id
        self.next_id += 1
        self.registry.insert(0, {"databaseId": run_id, "workflow": "publish-site.yml",
                                 "status": "completed", "conclusion": conclusion,
                                 "headBranch": branch, "created_at": self.created(run_id),
                                 "artifacts": artifacts or {}})
        return run_id

    def expire(self, run_id: int) -> None:
        """The run's artifacts reached their retention and are gone."""
        for run in self.registry:
            if run["databaseId"] == run_id:
                run["artifacts"] = {}

    # -- one run --------------------------------------------------------------

    def run(
        self,
        day: date,
        *,
        fail: dict | None = None,
        afresh: bool = False,
        fold: str = "",
        venue: str = "Arena",
        after_build: Callable[[Path], None] | None = None,
    ) -> Outcome:
        run_id = self.next_id
        self.next_id += 1
        self.venue = venue
        work = self.tmp / f"run{run_id}"
        work.mkdir()
        shutil.copytree(WEB, work / "web")
        (work / "scripts").mkdir()
        for step in _steps():
            for name in re.findall(r"python scripts/(\S+\.py)", str(step.get("run", ""))):
                shutil.copy(SCRIPTS / name, work / "scripts" / name)
        runner_temp = self.tmp / f"runner-temp-{run_id}"
        runner_temp.mkdir()
        running = {"databaseId": run_id, "workflow": "publish-site.yml",
                   "status": "in_progress", "conclusion": "",
                   "created_at": self.created(run_id), "artifacts": {}}
        (self.state / "registry.json").write_text(
            json.dumps([running, *self.registry]), encoding="utf-8")
        (self.state / "failures.json").write_text(json.dumps(fail or {}), encoding="utf-8")
        env = {
            **os.environ,
            "PATH": self.path,
            "FAKE_GH_STATE": str(self.state),
            "RUNNER_TEMP": str(runner_temp),
            # restore_state.py pauses between attempts; not in a test.
            "RESTORE_STATE_RETRY_SECONDS": "0",
            "GITHUB_REPOSITORY": "owner/nhl-betting-lab",
        }
        # The live Archive the step reads is this chain's last deploy.
        # test_the_live_archive_the_step_reads_is_the_sites_own pins the
        # URL this stands in for to web/CNAME.
        self.world = {"DEPLOYED_INDEX": (LIVE_INDEX, self.live.as_uri())}
        expressions = {
            "${{ github.token }}": "not-a-token",
            "${{ inputs.start_history_afresh && 'true' || 'false' }}": "true" if afresh else "false",
            "${{ inputs.fold_history_from_run || '' }}": fold,
        }

        outcome = Outcome(run_id=run_id, conclusion="success", log="")
        failed = False
        for step in _steps():
            if failed and "always()" not in str(step.get("if", "")):
                continue
            ok = self._step(step, work, env, expressions, day, outcome, after_build)
            if not ok and not step.get("continue-on-error"):
                failed = True
                outcome.failed_at = outcome.failed_at or step.get("name")
        outcome.conclusion = "failure" if failed else "success"
        self.registry.insert(0, {"databaseId": run_id, "workflow": "publish-site.yml",
                                 "status": "completed", "conclusion": outcome.conclusion,
                                 "created_at": self.created(run_id),
                                 "artifacts": outcome.artifacts})
        if outcome.deployed is not None:
            self.deploys.append(outcome)
        return outcome

    def _step(self, step, work, env, expressions, day, outcome, after_build) -> bool:
        uses = str(step.get("uses", ""))
        given = step.get("with") or {}
        if uses.startswith(("actions/checkout", "actions/setup-python")):
            return True
        if uses.startswith(("actions/cache/restore", "actions/cache/save")):
            return True  # a cache miss and a save nothing reads: the play-by-play is not modelled
        if uses.startswith("actions/upload-artifact"):
            source = work / str(given["path"]).strip()
            if source.is_dir() and any(p.is_file() for p in source.rglob("*")):
                kept = self.tmp / "artifacts" / str(outcome.run_id) / given["name"]
                shutil.copytree(source, kept)
                outcome.artifacts[given["name"]] = str(kept)
                self.uploads.append((outcome.run_id, kept))
            return True  # if-no-files-found: warn
        if uses.startswith("actions/upload-pages-artifact"):
            site = work / str(given["path"]).strip()
            outcome.deployed = {"site": site}
            return True
        if uses.startswith("actions/deploy-pages"):
            site = outcome.deployed["site"]
            outcome.deployed = {
                "index": json.loads((site / "data" / "history" / "index.json").read_text()),
                "results": json.loads((site / "data" / "results.json").read_text()),
            }
            self.live.parent.mkdir(parents=True, exist_ok=True)
            self.live.write_text(json.dumps(outcome.deployed["index"]), encoding="utf-8")
            return True
        assert not uses, f"the chain does not model `uses: {uses}`"

        text = str(step["run"])
        assert "${{" not in text, "a run block carries an expression; model it"
        if "pip install" in text:
            return True  # installs nothing offline; the interpreter already has it
        step_env = dict(env)
        for key, raw in (step.get("env") or {}).items():
            raw = str(raw)
            if "${{" in raw:
                assert raw in expressions, f"the chain does not model {raw!r}"
                raw = expressions[raw]
            if key in self.world:
                published, here = self.world[key]
                assert raw == published, f"{key} is {raw!r}; the chain models {published!r}"
                raw = here
            step_env[key] = raw
        if "web/build_site_json.py" in text:
            return self._build(text, work, step_env, day, outcome, after_build)
        return self._bash(text, work, step_env, outcome)

    def _bash(self, text, work, env, outcome) -> bool:
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", text],
            cwd=work, env=env, capture_output=True, text=True, timeout=120,
        )
        outcome.log += result.stdout + result.stderr
        return result.returncode == 0

    def _build(self, text, work, env, day, outcome, after_build) -> bool:
        """The build step, line by line: the two generators in-process (the
        schedule needs the network), anything else through bash."""
        self.monkeypatch.chdir(work)
        for line in (raw.strip() for raw in text.splitlines()):
            if not line:
                continue
            assert not line.endswith("\\"), "a continued line in the build step; model it"
            argv = shlex.split(line)
            if argv[:2] == ["python", "web/build_site_json.py"]:
                code = self.build.main([*argv[2:], "--date", day.isoformat()])
            elif argv[:2] == ["python", "web/site_history.py"]:
                code = self.history.main(argv[2:])
            else:
                code = 0 if self._bash(line, work, env, outcome) else 1
            if code != 0:
                return False
        if after_build is not None:
            after_build(work)
        return True


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PublishSite:
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    return PublishSite(tmp_path, monkeypatch)


def _frozen(artifact: Path) -> list[str]:
    return sorted(p.name for p in artifact.glob("*.json") if p.name != "index.json")


def assert_the_history_only_grows(chain: PublishSite) -> None:
    """The invariant the chain exists for: no deploy drops a board an earlier
    deploy showed, Results never denies a board the site published, and no
    uploaded history holds fewer frozen boards than the one before it."""
    shown: set[str] = set()
    for deploy in chain.deploys:
        now = set(deploy.boards)
        assert shown <= now, (
            f"run {deploy.run_id} deployed an archive without {sorted(shown - now)}"
        )
        results = deploy.deployed["results"]
        if results["resultsDate"] in shown:
            assert results.get("notice") != NO_BOARD, (
                f"run {deploy.run_id} said no board was published for "
                f"{results['resultsDate']}, which the site had published"
            )
        shown |= now
    kept: set[str] = set()
    for run_id, artifact in chain.uploads:
        now = set(_frozen(artifact))
        assert kept <= now, f"run {run_id} uploaded a history without {sorted(kept - now)}"
        kept = now


def _dates(*days: date) -> list[str]:
    return [day.isoformat() for day in days]


# --------------------------------------------------------------------------
# The chain.
# --------------------------------------------------------------------------


def test_a_failed_listing_publishes_nothing_and_loses_nothing(chain: PublishSite) -> None:
    """The finding's scenario A: one 502 on `gh run list`, on every attempt."""
    chain.run(D1)
    chain.run(D2)
    healthy = chain.run(D3)
    assert healthy.boards == _dates(D3, D2, D1)

    refused = chain.run(D4, fail={"list:publish-site.yml": 99})

    assert refused.conclusion == "failure", refused.log
    assert refused.failed_at == HISTORY_STEP, refused.failed_at
    assert "site-history" not in refused.artifacts, "a truncated history was uploaded"
    assert refused.deployed is None, "a truncated archive was deployed"
    after = chain.run(D5)
    assert after.conclusion == "success", after.log
    # D4 published nothing, so the next morning truthfully has no D4 board.
    assert after.boards == _dates(D5, D3, D2, D1)
    assert_the_history_only_grows(chain)


def test_a_failed_download_publishes_nothing_and_loses_nothing(chain: PublishSite) -> None:
    """Scenario B: the listing works, the newest carrier's download does not.
    An older carrier cannot stand in for it: whatever the newest added —
    here the D3 board — would be lost with it."""
    chain.run(D1)
    chain.run(D2)
    newest = chain.run(D3)

    refused = chain.run(D4, fail={f"download:{newest.run_id}:site-history": 99})

    assert refused.conclusion == "failure", refused.log
    assert refused.failed_at == HISTORY_STEP, refused.failed_at
    assert "site-history" not in refused.artifacts
    assert refused.deployed is None
    after = chain.run(D5)
    assert after.boards == _dates(D5, D3, D2, D1)
    assert_the_history_only_grows(chain)


@pytest.mark.parametrize("call", ["list", "download"])
def test_one_transient_502_is_retried_and_the_run_stays_green(
    chain: PublishSite, call: str
) -> None:
    chain.run(D1)
    chain.run(D2)
    newest = chain.run(D3)
    key = {"list": "list:publish-site.yml",
           "download": f"download:{newest.run_id}:site-history"}[call]

    retried = chain.run(D4, fail={key: 1})

    assert retried.conclusion == "success", retried.log
    assert retried.boards == _dates(D4, D3, D2, D1)
    assert_the_history_only_grows(chain)


def test_the_days_first_published_opinion_stands_when_a_later_restore_fails(
    chain: PublishSite,
) -> None:
    """Scenario C: the second publish of D2 cannot restore. It used to freeze
    D2 again from its own build, and that replacement was carried forward."""
    chain.run(D1)
    chain.run(D2, venue="first build")
    second = chain.run(D2, venue="second build", fail={"list:publish-site.yml": 99})
    assert second.conclusion == "failure", second.log

    after = chain.run(D3)

    frozen = json.loads((Path(after.artifacts["site-history"]) / f"{D2}.json").read_text())
    assert {g["venue"] for g in frozen["games"]} == {"first build"}
    assert after.boards == _dates(D3, D2, D1)
    assert_the_history_only_grows(chain)


def test_the_first_publish_starts_the_history(chain: PublishSite) -> None:
    """The one case that may start from nothing: GitHub answered, and no
    Publish Site run has ever succeeded."""
    chain.red("cancelled")

    first = chain.run(D1)

    assert first.conclusion == "success", first.log
    assert first.boards == _dates(D1)
    second = chain.run(D2)
    assert second.boards == _dates(D2, D1)


def test_a_long_red_streak_does_not_hide_the_last_successful_publish(
    chain: PublishSite,
) -> None:
    """Thirty-one red runs since the last success: a source picked from the
    newest few completed runs would see no success at all and start the
    history afresh."""
    chain.run(D1)
    for _ in range(31):
        chain.red()

    after = chain.run(D2)

    assert after.conclusion == "success", after.log
    assert after.boards == _dates(D2, D1)


def test_starting_afresh_is_a_deliberate_dispatch_the_refusal_names(
    chain: PublishSite,
) -> None:
    """When the newest carrier's artifact is gone for good (expired), the
    history cannot come back from GitHub. That is refused rather than
    papered over, and the refusal names the one thing that can be done,
    which the workflow must actually offer."""
    chain.run(D1)
    newest = chain.run(D2)
    chain.expire(newest.run_id)

    refused = chain.run(D3)

    assert refused.conclusion == "failure", refused.log
    assert refused.failed_at == HISTORY_STEP, refused.failed_at
    assert refused.deployed is None and "site-history" not in refused.artifacts
    assert "start_history_afresh" in refused.log
    assert "start_history_afresh" in _dispatch_inputs(), (
        "the refusal tells the owner to dispatch with an input the workflow does not declare"
    )

    fresh = chain.run(D3, afresh=True)

    assert fresh.conclusion == "success", fresh.log
    assert fresh.boards == _dates(D3)


def test_a_build_that_loses_a_restored_board_is_not_uploaded(chain: PublishSite) -> None:
    """Whatever happens between the restore and the upload, a history that
    lost a restored board is neither kept for tomorrow nor deployed."""
    chain.run(D1)
    chain.run(D2)

    def lose_d1(work: Path) -> None:
        (work / "dist" / "data" / "history" / f"{D1}.json").unlink()

    refused = chain.run(D3, after_build=lose_d1)

    assert refused.conclusion == "failure", refused.log
    assert "site-history" not in refused.artifacts
    assert refused.deployed is None
    assert chain.run(D4).boards == _dates(D4, D2, D1)


def test_a_dropped_board_is_folded_back_from_the_run_that_held_it(chain: PublishSite) -> None:
    """2026-10-05 restored an older publish than the newest and dropped nine
    boards. Dispatching with fold_history_from_run brings back every board
    the named run held, and overwrites none that are already here."""
    chain.run(D1)
    held = chain.run(D2)
    dropped = chain.run(D3, afresh=True)  # the history shrank to one board
    assert dropped.boards == _dates(D3)
    kept = (Path(dropped.artifacts["site-history"]) / f"{D3}.json").read_bytes()

    folded = chain.run(D4, fold=str(held.run_id))

    assert folded.conclusion == "success", folded.log
    assert folded.boards == _dates(D4, D3, D2, D1)
    assert (Path(folded.artifacts["site-history"]) / f"{D3}.json").read_bytes() == kept


def test_a_fold_names_a_run_id_or_publishes_nothing(chain: PublishSite) -> None:
    chain.run(D1)
    refused = chain.run(D2, fold="1; rm -rf /")
    assert refused.conclusion == "failure", refused.log
    assert refused.deployed is None


# --------------------------------------------------------------------------
# The floor check, driven directly.
# --------------------------------------------------------------------------


def _floor_script():
    return load_script("site_history_floor.py")


def _history(root: Path, boards: dict[str, str], lines: tuple[str, ...] = ()) -> Path:
    """A history folder as site_history.py leaves it: frozen boards, line
    files, and an index listing every board."""
    root.mkdir(parents=True, exist_ok=True)
    for name, venue in boards.items():
        (root / name).write_text(json.dumps({"games": [{"venue": venue}]}), encoding="utf-8")
    for name in lines:
        (root / "lines").mkdir(exist_ok=True)
        (root / "lines" / name).write_text("{}", encoding="utf-8")
    index = [{"date": name[:10], "file": name, "games": 1, "bets": 0}
             for name in sorted(boards, reverse=True)]
    (root / "index.json").write_text(json.dumps({"dates": index}), encoding="utf-8")
    return root


def _record_then_check(tmp_path: Path, restored: dict, change: Callable[[Path], None]):
    history = _history(tmp_path / "history", restored,
                       lines=tuple(name for name in restored))
    floor = tmp_path / "temp" / "floor.json"
    module = _floor_script()
    assert module.main(["record", "--history", str(history), "--floor", str(floor)]) == 0
    change(history)
    return module.main(["check", "--history", str(history), "--floor", str(floor)])


RESTORED = {"2026-10-05.json": "a", "2026-10-06.json": "b", "2026-10-07.json": "c"}


def test_the_check_passes_a_history_that_kept_everything_and_grew(tmp_path: Path) -> None:
    def build_today(history: Path) -> None:
        _history(history, {**RESTORED, "2026-10-08.json": "d"},
                 lines=(*RESTORED, "2026-10-08.json"))

    assert _record_then_check(tmp_path, RESTORED, build_today) == 0


def test_the_check_refuses_a_history_that_lost_frozen_boards(tmp_path: Path, capsys) -> None:
    """The finding's shape: three boards restored, one board uploaded."""
    def truncate(history: Path) -> None:
        shutil.rmtree(history)
        _history(history, {"2026-10-08.json": "d"}, lines=("2026-10-08.json",))

    assert _record_then_check(tmp_path, RESTORED, truncate) == 1
    assert "2026-10-05.json" in capsys.readouterr().out


def test_the_check_refuses_a_lost_board_file_the_index_still_lists(tmp_path: Path) -> None:
    """The file and the index are checked apart: Results reads the file, the
    Archive reads the index, and either one going missing is a loss."""
    def lose_the_file(history: Path) -> None:
        (history / "2026-10-06.json").unlink()

    assert _record_then_check(tmp_path, RESTORED, lose_the_file) == 1


def test_the_check_refuses_a_rewritten_frozen_board(tmp_path: Path) -> None:
    """The day's first published opinion stands; a board is never re-frozen."""
    def refreeze(history: Path) -> None:
        (history / "2026-10-07.json").write_text(
            json.dumps({"games": [{"venue": "a later build"}]}), encoding="utf-8")

    assert _record_then_check(tmp_path, RESTORED, refreeze) == 1


def test_the_check_refuses_a_lost_line_series(tmp_path: Path) -> None:
    def drop_lines(history: Path) -> None:
        (history / "lines" / "2026-10-06.json").unlink()

    assert _record_then_check(tmp_path, RESTORED, drop_lines) == 1


def test_the_check_refuses_an_index_that_no_longer_lists_a_board(tmp_path: Path) -> None:
    """index.json is what the Archive page reads."""
    def reindex(history: Path) -> None:
        index = json.loads((history / "index.json").read_text())
        index["dates"] = [e for e in index["dates"] if e["file"] != "2026-10-05.json"]
        (history / "index.json").write_text(json.dumps(index), encoding="utf-8")

    assert _record_then_check(tmp_path, RESTORED, reindex) == 1


def test_the_check_refuses_when_nothing_recorded_what_was_restored(tmp_path: Path) -> None:
    """No record is not an empty floor: the restore may never have run."""
    history = _history(tmp_path / "history", {"2026-10-08.json": "d"})

    code = _floor_script().main(
        ["check", "--history", str(history), "--floor", str(tmp_path / "absent.json")])

    assert code == 1


def test_the_record_is_a_digest_of_every_frozen_board(tmp_path: Path) -> None:
    history = _history(tmp_path / "history", RESTORED, lines=("2026-10-05.json",))
    floor = tmp_path / "floor.json"

    assert _floor_script().main(["record", "--history", str(history), "--floor", str(floor)]) == 0

    record = json.loads(floor.read_text())
    assert record["boards"] == {
        name: hashlib.sha256((history / name).read_bytes()).hexdigest() for name in RESTORED
    }
    assert record["lines"] == ["lines/2026-10-05.json"]


# --------------------------------------------------------------------------
# Every other restore keeps its old contract.
# --------------------------------------------------------------------------


def test_without_require_newest_a_failed_listing_still_never_fails_the_step(
    tmp_path: Path, chain: PublishSite,
) -> None:
    """Gameday Refresh, Line Movement and the rest rely on restore_state.py
    never failing their restore step; only Publish Site's history asks for
    the strict contract, by flag."""
    (chain.state / "registry.json").write_text("[]", encoding="utf-8")
    (chain.state / "failures.json").write_text(
        json.dumps({"list:gameday-refresh.yml": 99}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "restore_state.py"), "--artifact", "gameday-state",
         "--dest", str(tmp_path / "data"), "--workflow", "gameday-refresh.yml"],
        env={**os.environ, "PATH": chain.path, "FAKE_GH_STATE": str(chain.state),
             "RESTORE_STATE_RETRY_SECONDS": "0"},
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Could not list gameday-refresh.yml runs" in result.stdout


# --------------------------------------------------------------------------
# A restore of the wrong run: the floor needs a source of its own.
#
# On 2026-10-05 run 37318279569 restored run 36176147420 (2026-09-25),
# because `gh run list --status success` listed it first, although run
# 37224089121 (2026-10-04, 14 frozen boards) was newer and successful. The
# floor was recorded from what was restored, every run stayed green, and the
# live Archive went from 13 boards to 5. Below, `stale-listing` makes the run
# listing leave out the newest runs, so an older publish comes first, as it
# did that morning.
# --------------------------------------------------------------------------


def test_a_listing_that_names_an_older_publish_publishes_nothing_and_loses_nothing(
    chain: PublishSite,
) -> None:
    """The 2026-10-05 shape. Without the guard this deploys D4 and D1 only."""
    first = chain.run(D1)
    second = chain.run(D2)
    newest = chain.run(D3)
    assert newest.boards == _dates(D3, D2, D1)

    refused = chain.run(D4, fail={"stale-listing": [newest.run_id, second.run_id]})

    assert f"from publish-site.yml run {first.run_id} (success)" in refused.log, (
        "the fixture did not reproduce the stale listing")
    assert refused.conclusion == "failure", refused.log
    assert refused.failed_at == HISTORY_STEP, refused.failed_at
    assert "site-history" not in refused.artifacts, "a history missing D2 and D3 was kept"
    assert refused.deployed is None, "an archive missing D2 and D3 was deployed"
    assert f"run {newest.run_id}" in refused.log, "the refusal does not name the newer run"
    after = chain.run(D5)
    assert after.conclusion == "success", after.log
    assert after.boards == _dates(D5, D3, D2, D1)
    assert_the_history_only_grows(chain)


def test_the_live_archive_catches_what_a_stale_artifacts_api_would_miss(
    chain: PublishSite,
) -> None:
    """Both GitHub listings behind together: the artifacts API agrees with
    the stale run listing, and only the live Archive still shows D3 and D2."""
    chain.run(D1)
    second = chain.run(D2)
    newest = chain.run(D3)
    stale = [newest.run_id, second.run_id]

    refused = chain.run(D4, fail={"stale-listing": stale, "stale-artifacts": stale})

    assert refused.failed_at == HISTORY_STEP, refused.log
    assert refused.deployed is None and "site-history" not in refused.artifacts
    assert f"history/{D3}.json is on the live Archive" in refused.log, refused.log
    assert f"history/{D2}.json is on the live Archive" in refused.log, refused.log
    assert_the_history_only_grows(chain)


def test_the_artifacts_api_catches_what_a_lagging_live_site_would_miss(
    chain: PublishSite,
) -> None:
    """The live index behind too (Pages caches it for ten minutes): only the
    artifacts API still knows the newest publish."""
    first = chain.run(D1)
    shown = chain.live.read_text(encoding="utf-8")
    second = chain.run(D2)
    newest = chain.run(D3)
    chain.live.write_text(shown, encoding="utf-8")

    refused = chain.run(D4, fail={"stale-listing": [newest.run_id, second.run_id]})

    assert refused.failed_at == HISTORY_STEP, refused.log
    assert refused.deployed is None and "site-history" not in refused.artifacts
    assert (f"took site-history from run {first.run_id}, but the artifacts API's "
            f"newest from a successful publish is run {newest.run_id}'s") in refused.log


@pytest.mark.parametrize("key", ["api:artifacts", "api:run"])
def test_an_artifacts_api_that_never_answers_is_a_refusal(
    chain: PublishSite, key: str,
) -> None:
    """Could not check is not checked."""
    chain.run(D1)
    newest = chain.run(D2)
    key = f"api:run:{newest.run_id}" if key == "api:run" else key

    refused = chain.run(D3, fail={key: 99})

    assert refused.failed_at == HISTORY_STEP, refused.log
    assert refused.deployed is None and "site-history" not in refused.artifacts
    assert "GitHub did not answer" in refused.log
    retried = chain.run(D3, fail={key: 1})
    assert retried.conclusion == "success", retried.log
    assert retried.boards == _dates(D3, D2, D1)


def test_a_live_site_without_an_archive_is_a_refusal_once_one_was_kept(
    chain: PublishSite,
) -> None:
    """A 404 is "nothing deployed" only before the first publish."""
    chain.run(D1)
    chain.run(D2)
    chain.live.unlink()

    refused = chain.run(D3)

    assert refused.failed_at == HISTORY_STEP, refused.log
    assert "The live site has no history/index.json" in refused.log


def test_a_newer_history_from_a_run_that_did_not_succeed_is_passed_over(
    chain: PublishSite,
) -> None:
    """The restore passes over a red run's upload, and any run off main, so
    the check must too, or one run that uploaded and then failed (or one
    dispatch on a branch) would refuse every publish after it."""
    chain.run(D1)
    newest = chain.run(D2)
    chain.red(artifacts=dict(newest.artifacts))
    # A branch dispatch that succeeded: only the branch keeps it out.
    chain.red("success", artifacts=dict(newest.artifacts), branch="rehearse-the-publish")

    after = chain.run(D3)

    assert after.conclusion == "success", after.log
    assert after.boards == _dates(D3, D2, D1)


def test_an_artifact_of_the_same_name_from_another_workflow_is_passed_over(
    chain: PublishSite,
) -> None:
    """The artifacts API is asked by name, which any workflow can upload."""
    chain.run(D1)
    newest = chain.run(D2)
    other = chain.red("success", artifacts=dict(newest.artifacts))
    chain.registry[0]["workflow"] = "season-sim.yml"
    assert chain.registry[0]["databaseId"] == other

    after = chain.run(D3)

    assert after.conclusion == "success", after.log
    assert after.boards == _dates(D3, D2, D1)


def test_the_live_archive_the_step_reads_is_the_sites_own() -> None:
    """The chain stands its own last deploy in for DEPLOYED_INDEX; that only
    tests anything while the URL is the site's."""
    step = next(s for s in _steps() if s.get("name") == HISTORY_STEP)
    host = (WEB / "CNAME").read_text(encoding="utf-8").strip()
    assert step["env"]["DEPLOYED_INDEX"] == f"https://{host}/data/history/index.json" == LIVE_INDEX
    assert '--record-run "$RUNNER_TEMP/site-history.run"' in step["run"]
    assert '--restored-run "$RUNNER_TEMP/site-history.run"' in step["run"]


def _record_with_source(tmp_path: Path, capsys, *, restored: str, newest: int | None,
                        deployed: set[str] | None, boards=RESTORED, monkeypatch=None) -> int:
    module = _floor_script()
    history = _history(tmp_path / "history", boards)
    run_file = tmp_path / "site-history.run"
    run_file.write_text(restored, encoding="utf-8")
    monkeypatch.setattr(module, "newest_artifact_run", lambda repo, attempts=3: newest)
    monkeypatch.setattr(module, "deployed_boards", lambda url, attempts=3: deployed)
    floor = tmp_path / "floor.json"
    code = module.main(["record", "--history", str(history), "--floor", str(floor),
                        "--restored-run", str(run_file), "--repo", "o/r",
                        "--deployed-index", "https://example.invalid/index.json"])
    assert floor.exists() == (code == 0), "a refused restore must not leave a floor behind"
    return code


def test_record_agrees_with_both_sources(tmp_path: Path, capsys, monkeypatch) -> None:
    assert _record_with_source(tmp_path, capsys, restored="7\n", newest=7,
                               deployed=set(RESTORED), monkeypatch=monkeypatch) == 0


@pytest.mark.parametrize("restored,newest,deployed", [
    ("6\n", 7, set(RESTORED)),                         # the listing named an older run
    ("", 7, set(RESTORED)),                            # it found none; the API holds one
    ("7\n", None, set(RESTORED)),                      # the API holds none
    ("7\n", 7, {*RESTORED, "2026-10-04.json"}),        # the Archive shows more
    ("7\n", 7, None),                                  # the Archive is gone
    ("not a run\n", 7, set(RESTORED)),                 # the record is unreadable
])
def test_record_refuses_when_a_source_disagrees(
    tmp_path: Path, capsys, monkeypatch, restored, newest, deployed,
) -> None:
    assert _record_with_source(tmp_path, capsys, restored=restored, newest=newest,
                               deployed=deployed, monkeypatch=monkeypatch) == 1
    assert "::error::" in capsys.readouterr().out


def test_the_first_publish_has_nothing_to_disagree_with(tmp_path: Path, capsys, monkeypatch) -> None:
    assert _record_with_source(tmp_path, capsys, restored="", newest=None, deployed=None,
                               boards={}, monkeypatch=monkeypatch) == 0


def test_record_refuses_without_the_restores_run_record(tmp_path: Path) -> None:
    module = _floor_script()
    history = _history(tmp_path / "history", RESTORED)
    code = module.main(["record", "--history", str(history), "--floor", str(tmp_path / "f.json"),
                        "--restored-run", str(tmp_path / "absent.run"), "--repo", "o/r",
                        "--deployed-index", "https://example.invalid/index.json"])
    assert code == 1


def test_the_source_flags_go_together(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _floor_script().main(["record", "--history", str(tmp_path), "--floor",
                              str(tmp_path / "f.json"), "--repo", "o/r"])


def test_a_deployed_index_that_cannot_be_read_is_unknown_not_empty(monkeypatch) -> None:
    import urllib.error
    module = _floor_script()
    monkeypatch.setenv("RESTORE_STATE_RETRY_SECONDS", "0")

    def unavailable(url):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)

    def missing(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    with pytest.raises(module.SourceUnknown):
        module.deployed_boards("https://x/index.json", 2, fetch=unavailable)
    with pytest.raises(module.SourceUnknown):
        module.deployed_boards("https://x/index.json", 2, fetch=lambda url: b"<html>")
    assert module.deployed_boards("https://x/index.json", 2, fetch=missing) is module.NOT_DEPLOYED
    body = json.dumps({"dates": [{"file": "2026-10-04.json"}]}).encode()
    assert module.deployed_boards("https://x/index.json", 2, fetch=lambda url: body) == {"2026-10-04.json"}
