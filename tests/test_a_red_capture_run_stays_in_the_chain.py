"""A red Line Movement run's captures stay in the chain.

Stage two of the move to the private repository (2026-10-05): the chain's
only home is branch `movement` of cooperross399/nhl-closing-lines.
"Restore today's captures" pulls it (`private_movement_chain.py pull`) and
then folds in every sealed fallback round (`unseal`). Straight after the
captures, "Keep the captures privately" merges this round's three stores
into the private tip (`push`), and "Check the private chain holds this
round" checks that the tip holds every row (`verify`). When either fails,
"Seal this round when the private chain did not take it" encrypts the round
(only the files the tip lacks, when it can list the tip) with
NHL_CHAIN_FALLBACK_KEY and "Keep the sealed round" keeps it as
`line-movement-sealed-<attempt>`, for the next restore to fold in. The
branch has existed since 2026-10-02 (seeded by hand with `push
--allow-new-chain`, which no workflow passes), so a missing branch is a
fault, never "no chain yet": the restore says so and the push refuses.

History, short. Until stage two the chain was the public `line-movement`
artifact, and its restore took `gh run list --status success --limit 1`. A
run gone red (the price capture's events list failed, or the line units were
not captured) still uploaded its free captures under `if: always()`, but the
next run restored the last GREEN run, so the red run's rows fell out of the
chain. The failure-shape audit's replay (14:00 green, 18:00 provider 503,
21:00 and 23:00 green) read the 18:00 scratch list and PP1 promotion as
first public at 21:00, three hours late, which is the one question these
captures exist to answer; neither source keeps an archive, and a missing
NHL_ODDS_API_KEY would have dropped every free capture the same way. A
second hole: a run whose own restore found nothing carried only its own rows
and became the next base. The public restore then read the newest carrier of
any conclusion and unioned the two before it. Stage two retired that restore,
so the same properties now rest on other lines, and these tests hold them
there:

* a red run's captures reach the chain because the private push runs under
  `always()`, after every capture step;
* a run whose restore could not read the chain loses nothing, however many
  come in a row, because its push MERGES into the private tip;
* a round whose push failed, or that the check found short after a push
  that exited 0, is sealed, and the next restore unseals it so the next
  push brings it home; a re-run's attempt 2 folds attempt 1's sealed round
  in, and seals under a name of its own. (A re-run whose first attempt DID
  push reads that round back from the chain, the ordinary restore every
  other test here replays; the re-run test covers the sealed path, the one
  that used to need `--fold-run`.)
* a round that finds the branch deleted does not start a thin chain in its
  place (every later restore, Closing Lines and the CLV step would read it
  as the season): its restore writes the fault, its push refuses, and the
  round is sealed until the branch is restored from its history.

They replay those steps, taken from the workflow file in its order, under
`bash --noprofile --norc -eo pipefail`, with the real scripts. Each step runs
only when its `if:` holds by GitHub's rules: after a red step, only the
steps that say `always()`. The private repository is a local bare repository:
git's `url.<base>.insteadOf` rewrites the real remote to it, and every other
transport is refused, so nothing leaves the machine. Before the first round
the fixture seeds its `movement` branch with a 2026-10-02 round, by the
manual seed's own command. Every round is a scheduled run on the default
branch. The GitHub API's privacy answer is stubbed in a `sitecustomize` the
steps' Python loads (it
also skips the retry pauses), and an offline `gh` serves the sealed
artifacts. Between restore and push they run the real
`capture_deployment.main` and `capture_line_combinations.main` with network
and clock stubbed, and append prices exactly as `capture_line_movement.main`
does. Not replayed here: a sealed artifact's 7-day expiry (every round here
is unexpired), and the gates that turn these runs red, which other tests run.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.season import LEAGUE_TIMEZONE

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
RESTORE_STEP = "Restore today's captures"
PRICES_STEP = "Capture prices"
DEPLOYMENT_STEP = "Capture deployment"
LINES_STEP = "Capture line combinations"
#: The private steps, by the ids their `if:`s and the gates read.
PUSH, SEAL, SEALED_UPLOAD, VERIFY = "private_push", "seal", "sealed_upload", "private_verify"
REPLAYED = {RESTORE_STEP, PRICES_STEP, DEPLOYMENT_STEP, LINES_STEP, PUSH, SEAL, SEALED_UPLOAD, VERIFY}

THIS_REPO = "cooperross399/nhl-betting-lab"
PRIVATE_REPO = "cooperross399/nhl-closing-lines"
TOKEN = "not-a-real-token"
#: Long enough for the seal and the unseal, which refuse a key shorter than
#: 32 characters (the recipe, `openssl rand -base64 48`, gives 64).
KEY = "not-a-real-fallback-key-but-as-long-as-a-real-one-is"
#: The remote the scripts build from the token; git is told it is the bare repository.
PRIVATE_REMOTE = f"https://x-access-token:{TOKEN}@github.com/{PRIVATE_REPO}.git"
SECRETS = {
    "secrets.NHL_CLOSING_LINES_TOKEN": TOKEN,
    "secrets.NHL_CHAIN_FALLBACK_KEY": KEY,
    "github.token": "not-a-github-token",
}
#: What a runner sets itself, or a step's `env:` must supply; never the caller's.
RUNNER_OWNED = {
    "NHL_CLOSING_LINES_TOKEN", "NHL_CHAIN_FALLBACK_KEY", "NHL_ODDS_API_KEY", "GH_TOKEN",
    "GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_WORKSPACE", "GITHUB_STEP_SUMMARY",
    "GITHUB_OUTPUT", "RUNNER_TEMP", "PYTHONPATH",
}
COLUMNS = {"line_movement": "captured_at", "deployment": "captured_at",
           "line_combinations": "retrieved_at"}

#: The in-season crons, in UTC, on one league day (2026-10-15 Eastern).
AT_14, AT_18 = "2026-10-15T14:00:00+00:00", "2026-10-15T18:00:00+00:00"
AT_21, AT_23 = "2026-10-15T21:00:00+00:00", "2026-10-15T23:00:00+00:00"
AT_01 = "2026-10-16T01:00:00+00:00"
#: A Re-run of the 18:00 round, forty minutes on.
AT_18_40 = "2026-10-15T18:40:00+00:00"
#: 21:00 Eastern the evening before.
YESTERDAY = "2026-10-15T01:00:00+00:00"
#: The round the chain was seeded with: it has existed since 2026-10-02.
SEEDED = "2026-10-02T23:00:00+00:00"
SEEDED_DAY = "2026-10-02"
#: The manual first seed. No workflow passes --allow-new-chain.
SEED_STEP = {
    "name": "Seed the chain by hand",
    "env": {"NHL_CLOSING_LINES_TOKEN": "${{ secrets.NHL_CLOSING_LINES_TOKEN }}", "PYTHONPATH": "src"},
    "run": "python scripts/private_movement_chain.py push --allow-new-chain --processed-dir data/processed",
}
BRANCH = "refs/heads/movement"

FAKE_GH = r'''
import json, os, re, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
    print("gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN "
          "environment variable.", file=sys.stderr)
    sys.exit(4)
if os.environ.get("FAKE_GITHUB_DOWN") == "1":
    print("HTTP 502: Bad Gateway", file=sys.stderr)
    sys.exit(1)
if args[:1] != ["api"]:
    print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
    sys.exit(2)
jq, endpoint, rest = None, None, args[1:]
while rest:
    flag = rest.pop(0)
    if flag == "--jq":
        jq = rest.pop(0)
    elif flag == "--paginate":
        continue
    elif flag.startswith("-") or endpoint is not None:
        print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
        sys.exit(2)
    else:
        endpoint = flag
artifacts = json.loads(Path(os.environ["FAKE_GH_ARTIFACTS"]).read_text())
# The artifacts are this repository's; any other is a 404, as GitHub answers.
listing = "repos/" + os.environ["FAKE_GH_REPOSITORY"] + "/actions/artifacts"
if (endpoint or "").split("?")[0] == listing:
    if jq != ".artifacts[]":
        print("fake gh: unsupported --jq " + str(jq), file=sys.stderr)
        sys.exit(2)
    for item in artifacts:
        print(json.dumps({k: v for k, v in item.items() if k != "zip"}))
    sys.exit(0)
match = re.fullmatch(re.escape(listing) + r"/(\d+)/zip", endpoint or "")
found = [a for a in artifacts if match and jq is None and str(a["id"]) == match.group(1)]
if not found:
    print("HTTP 404: Not Found (https://api.github.com/" + str(endpoint) + ")", file=sys.stderr)
    sys.exit(1)
sys.stdout.buffer.write(Path(found[0]["zip"]).read_bytes())
'''

SITECUSTOMIZE = r'''
"""The offline GitHub a replayed step's Python sees. Written by the test."""
import importlib.util, io, json, os, sys, time, urllib.error, urllib.request

time.sleep = lambda seconds: None  # the scripts' retry pauses: no test waits

def _urlopen(request, *args, **kwargs):
    url = getattr(request, "full_url", request)
    if os.environ.get("FAKE_GITHUB_DOWN") != "1" and url == "https://api.github.com/repos/PRIVATE_REPO":
        return io.BytesIO(json.dumps({"private": True}).encode())
    raise urllib.error.URLError("offline test: " + str(url))

urllib.request.urlopen = _urlopen

# The interpreter's own sitecustomize, which this one shadows, still runs.
_here = os.path.dirname(os.path.abspath(__file__))
for _entry in sys.path:
    _candidate = os.path.join(os.path.abspath(_entry or os.curdir), "sitecustomize.py")
    if os.path.dirname(_candidate) != _here and os.path.isfile(_candidate):
        _spec = importlib.util.spec_from_file_location("_shadowed_sitecustomize", _candidate)
        _spec.loader.exec_module(importlib.util.module_from_spec(_spec))
        break
'''.replace("PRIVATE_REPO", PRIVATE_REPO)


def _capture_steps() -> list[dict]:
    """The steps of the job that restores, in the order GitHub runs them."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = [job for job in document["jobs"].values()
            if any(s.get("name") == RESTORE_STEP for s in job["steps"])]
    assert len(jobs) == 1, f"exactly one job runs {RESTORE_STEP!r}"
    return jobs[0]["steps"]


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions this file names; refuse any other."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        assert expression in values, f"unfilled expression: {expression}"
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _git(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], capture_output=True, text=True, env=env, **kwargs)


def _day(instant: str) -> str:
    return datetime.fromisoformat(instant).astimezone(LEAGUE_TIMEZONE).date().isoformat()


def _clock(instant: str) -> type:
    fixed = datetime.fromisoformat(instant)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 - the scripts' only use
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    return Frozen


def _nhl_api(instant: str):
    """The schedule and right-rail payloads. The scratch goes public at 18:00."""
    day = _day(instant)
    scratched = instant >= f"{day}T18:00:00+00:00"

    def fetch(url, requester=None):
        if url.endswith("/v1/schedule/now"):
            return {"gameWeek": [{"games": [
                {"id": 2026020077, "startTimeUTC": f"{day}T23:00:00Z"},
            ]}]}
        return {"gameInfo": {
            "referees": [{"default": "Wes McCauley"}, {"default": "Chris Rooney"}],
            "linesmen": [{"default": "Ryan Gibbons"}],
            "homeTeam": {
                "headCoach": {"default": "Craig Berube"},
                "scratches": [{"id": 8471817, "firstName": {"default": "Ryan"},
                               "lastName": {"default": "Reaves"}}] if scratched else [],
            },
            "awayTeam": {"headCoach": {"default": "Marco Sturm"}, "scratches": []},
        }}

    return fetch


def _lines_page(instant: str) -> str:
    """The team page. Knies is promoted to the top power-play unit at 18:00."""
    players = [{
        "playerId": 8479318, "name": "Auston Matthews", "playerSlug": "auston-matthews",
        "groupIdentifier": "f1", "groupName": "F1", "categoryIdentifier": "ev",
        "positionIdentifier": "c",
    }]
    if instant >= f"{_day(instant)}T18:00:00+00:00":
        players.append({
            "playerId": 8482720, "name": "Matthew Knies", "playerSlug": "matthew-knies",
            "groupIdentifier": "pp1", "groupName": "PP1", "categoryIdentifier": "pp",
            "positionIdentifier": "sk1",
        })
    payload = {"props": {"pageProps": {
        "sortedTeams": [{"slug": "toronto-maple-leafs"}],
        "combinations": {
            "teamSlug": "toronto-maple-leafs", "teamAbbreviation": "TOR",
            "teamName": "Toronto Maple Leafs", "sourceName": "Morning Skate",
            "updatedAt": "2026-10-15T13:02:00.000Z", "players": players,
        },
    }}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload) + "</script></body></html>"
    )


@dataclass
class Round:
    """One attempt of one scheduled run, as it ended."""

    instant: str
    run_id: int
    attempt: int
    work: Path
    temp: Path
    red: bool = False
    outcomes: dict[str, str] = field(default_factory=dict)
    #: What was on disk for 2026-10-15 straight after the restore step.
    restored: dict[str, list[str]] = field(default_factory=dict)
    logs: dict[str, str] = field(default_factory=dict)

    @property
    def processed(self) -> Path:
        return self.work / "data" / "processed"

    @property
    def restore_problem(self) -> str:
        path = self.work / "restore_problem.txt"
        return path.read_text(encoding="utf-8") if path.is_file() else ""


class _Steps:
    """GitHub's `steps` context: a step that has not run has no outcome."""

    def __init__(self, outcomes: dict[str, str]) -> None:
        self._outcomes = outcomes

    def __getattr__(self, step_id: str) -> SimpleNamespace:
        return SimpleNamespace(outcome=self._outcomes.get(step_id, ""))


def _runs(step: dict, this: Round) -> bool:
    """Whether GitHub runs `step` at this point of the round: its `if:`, with
    `success()` implied when the expression names no status function."""
    expression = str(step.get("if", "")).strip()
    if expression.startswith("${{") and expression.endswith("}}"):
        expression = expression[3:-2].strip()
    if not expression:
        return not this.red
    python = re.sub(r"!(?!=)", " not ", expression.replace("&&", " and ").replace("||", " or "))
    names = {
        "always": lambda: True,
        "success": lambda: not this.red,
        "failure": lambda: this.red,
        "cancelled": lambda: False,
        "format": lambda text, *args: text.format(*args),
        # Scheduled, so on the default branch.
        "github": SimpleNamespace(
            event_name="schedule", ref="refs/heads/main", run_attempt=str(this.attempt),
            event=SimpleNamespace(repository=SimpleNamespace(default_branch="main")),
        ),
        "steps": _Steps(this.outcomes),
    }
    value = bool(eval(python, {"__builtins__": {}}, names))  # the workflow's own `if:`
    if re.search(r"\b(always|success|failure|cancelled)\(\)", expression):
        return value
    return value and not this.red


class Chain:
    """Line Movement's rounds, one after another, as GitHub would run them."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.next_id = 1000
        self.rounds: list[Round] = []
        self.artifacts: list[dict] = []  # what `gh api .../actions/artifacts` lists
        self.next_artifact = 5000
        #: What the seeded day holds, once `seed` has run.
        self.seeded: dict[str, list[str]] = {}
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}", encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.stubs = tmp_path / "stubs"
        self.stubs.mkdir()
        (self.stubs / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.path = f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
        self.store = tmp_path / "nhl-closing-lines.git"
        assert _git(["init", "-q", "--bare", "-b", "main", str(self.store)]).returncode == 0
        self.steps = _capture_steps()
        self.movement = load_script("capture_line_movement.py")
        self.deployment = load_script("capture_deployment.py")
        self.lines = load_script("capture_line_combinations.py")

    def _round(self, instant: str, run_id: int, attempt: int) -> Round:
        """A fresh checkout and runner temp for one attempt."""
        work = self.tmp / f"run{run_id}-{attempt}"
        work.mkdir()
        (work / "scripts").symlink_to(PROJECT_ROOT / "scripts", target_is_directory=True)
        (work / "src").symlink_to(PROJECT_ROOT / "src", target_is_directory=True)
        temp = self.tmp / f"runner-temp{run_id}-{attempt}"  # outside the workspace
        temp.mkdir()
        return Round(instant, run_id, attempt, work, temp)

    def seed(self) -> dict[str, list[str]]:
        """Branch `movement` as it has stood since 2026-10-02: one round's
        captures, pushed by the manual first seed's own command. What the
        seeded day holds, store by store."""
        assert self.branch() is None, "the bare repository starts with no chain"
        this = self._round(SEEDED, 1, 1)
        self._prices(this)
        self._deployment(this)
        self._lines(this, True)
        assert self._bash(SEED_STEP, this, down=False), this.logs
        assert self.branch(), "the manual seed made no movement branch"
        seeded = _instants(this.processed, SEEDED_DAY)
        assert all(seeded.values()) and self.tip(SEEDED_DAY) == seeded
        return seeded

    def branch(self) -> str | None:
        """The private branch's commit, or None when there is no branch."""
        shown = _git(["--git-dir", str(self.store), "rev-parse", "-q", "--verify", BRANCH])
        return shown.stdout.strip() if shown.returncode == 0 else None

    def set_branch(self, commit: str) -> None:
        """Point the private branch at `commit`, as a force-push would."""
        assert _git(["--git-dir", str(self.store), "update-ref", BRANCH, commit]).returncode == 0

    def delete_branch(self) -> None:
        assert _git(["--git-dir", str(self.store), "update-ref", "-d", BRANCH]).returncode == 0
        assert self.branch() is None

    def run(
        self, instant: str, *, prices: bool = True, lines: bool = True,
        pull_down: bool = False, push_down: bool = False, rerun: bool = False,
        after_push: Callable[[], None] | None = None,
    ) -> Round:
        """One round: every replayed step whose `if:` holds, in order.

        `pull_down`: GitHub could not be reached during the restore.
        `push_down`: nor during the push, the check and the seal's listing.
        `rerun`: a Re-run of the previous round (same run, next attempt).
        `after_push`: what happens to the private repository between the
        push and the check (another writer's).
        """
        if rerun:
            run_id, attempt = self.rounds[-1].run_id, self.rounds[-1].attempt + 1
        else:
            run_id, attempt = self.next_id, 1
            self.next_id += 1
        this = self._round(instant, run_id, attempt)
        found = set()
        for step in self.steps:
            key = next((k for k in (step.get("name"), step.get("id")) if k in REPLAYED), None)
            if key is None:
                continue
            found.add(key)
            if not _runs(step, this):
                if step.get("id"):
                    this.outcomes[step["id"]] = "skipped"
                continue
            if key == RESTORE_STEP:
                ok = self._bash(step, this, down=pull_down)
                this.restored = _instants(this.processed)
            elif key == PRICES_STEP:
                ok = self._prices(this) if prices else False  # exit 2: no round captured
            elif key == DEPLOYMENT_STEP:
                ok = self._deployment(this)
            elif key == LINES_STEP:
                ok = self._lines(this, lines)
            elif key == SEALED_UPLOAD:
                ok = self._upload(step, this)
            else:
                ok = self._bash(step, this, down=push_down)
            if step.get("id"):
                this.outcomes[step["id"]] = "success" if ok else "failure"
            if not ok and not step.get("continue-on-error"):
                this.red = True
            if key == PUSH and after_push is not None:
                after_push()
        assert found == REPLAYED, f"line-movement.yml has no step {sorted(REPLAYED - found)}"
        self.rounds.append(this)
        return this

    def _bash(self, step: dict, this: Round, *, down: bool) -> bool:
        """The step's `run:` block, with its `env:` as the workflow writes it."""
        given = {k: _render(str(v), SECRETS) for k, v in (step.get("env") or {}).items()}
        artifacts = self.tmp / "artifacts.json"
        artifacts.write_text(json.dumps(self.artifacts), encoding="utf-8")
        target = self.tmp / "unreachable.git" if down else self.store
        env = {k: v for k, v in os.environ.items()
               if k not in RUNNER_OWNED and not k.startswith("GIT_")}
        env.update({
            "PATH": self.path,
            "GITHUB_REPOSITORY": THIS_REPO,
            "GITHUB_WORKSPACE": str(this.work),
            "RUNNER_TEMP": str(this.temp),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_ALLOW_PROTOCOL": "file",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"url.{target.as_uri()}.insteadOf",
            "GIT_CONFIG_VALUE_0": PRIVATE_REMOTE,
            "FAKE_GH_LOG": str(self.tmp / "gh.log"),
            "FAKE_GH_ARTIFACTS": str(artifacts),
            "FAKE_GH_REPOSITORY": THIS_REPO,
            "FAKE_GITHUB_DOWN": "1" if down else "0",
            **given,
        })
        env["PYTHONPATH"] = os.pathsep.join(p for p in (given.get("PYTHONPATH"), str(self.stubs)) if p)
        done = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _render(step["run"], SECRETS)],
            cwd=this.work, env=env, capture_output=True, text=True, timeout=120,
        )
        this.logs[step.get("id") or step["name"]] = done.stdout + done.stderr
        return done.returncode == 0

    def _prices(self, this: Round) -> bool:
        # Exactly the append `capture_line_movement.main` makes; the script
        # itself needs --live, which no test may pass.
        day = _day(this.instant)
        frame = pd.DataFrame([{
            "provider_event_id": f"evt-{day}", "commence_time": f"{day}T23:00:00Z",
            "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
            "market": "shots_on_goal", "player": "Auston Matthews",
            "selection": "over", "line": 3.5,
            "american_odds": -110 - int(this.instant[11:13]), "book": "draftkings",
        }])
        frame["captured_at"] = this.instant
        path = self.movement.capture_path(day, processed_dir=this.processed)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                     lineterminator="\n")
        return True

    def _deployment(self, this: Round) -> bool:
        self.monkeypatch.setattr(self.deployment, "datetime", _clock(this.instant))
        self.monkeypatch.setattr(self.deployment, "_get_json", _nhl_api(this.instant))
        assert self.deployment.main(
            ["--processed-dir", str(this.processed), "--polite-seconds", "0"]
        ) == 0
        return True

    def _lines(self, this: Round, lines: bool) -> bool:
        self.monkeypatch.setattr(self.lines, "datetime", _clock(this.instant))
        self.monkeypatch.setattr(self.lines, "games_today", lambda *a, **k: 1)
        if lines:
            page = _lines_page(this.instant)
            self.monkeypatch.setattr(self.lines, "_fetch", lambda url, **k: page)
        else:
            def refused(url, **k):
                raise OSError("403 Forbidden")
            self.monkeypatch.setattr(self.lines, "_fetch", refused)
        code = self.lines.main(["--processed-dir", str(this.processed), "--polite-seconds", "0"])
        assert code == (0 if lines else 2)
        return code == 0

    def _upload(self, step: dict, this: Round) -> bool:
        """actions/upload-artifact@v4 as the step configures it."""
        assert str(step.get("uses", "")).startswith("actions/upload-artifact@"), step
        given = step.get("with") or {}
        name = _render(str(given["name"]), {"github.run_attempt": str(this.attempt)})
        paths = [p.strip() for p in str(given["path"]).splitlines() if p.strip()]
        assert len(paths) == 1, paths
        path = Path(_render(paths[0], {"runner.temp": str(this.temp)}))
        if not path.is_file():
            return given.get("if-no-files-found") != "error"
        same = [a for a in self.artifacts
                if a["name"] == name and a["workflow_run"]["id"] == this.run_id]
        if same:
            # An artifact belongs to the run, not the attempt: v4 refuses a
            # name the run already has unless told to overwrite it.
            if given.get("overwrite") is not True:
                return False
            self.artifacts = [a for a in self.artifacts if a not in same]
        self.next_artifact += 1
        archive = self.tmp / "uploads" / f"{self.next_artifact}.zip"
        archive.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.write(path, arcname=path.name)  # one file roots at its own folder
        self.artifacts.append({
            "id": self.next_artifact, "name": name, "expired": False,
            "created_at": this.instant, "zip": str(archive),
            "workflow_run": {"id": this.run_id, "head_branch": "main", "repository_id": 1, "head_repository_id": 1},
        })
        return True

    def tip(self, day: str = "2026-10-15") -> dict[str, list[str]]:
        """What the private chain holds now, store by store."""
        held = {}
        for store, column in COLUMNS.items():
            shown = _git(["--git-dir", str(self.store), "show", f"movement:{store}/{day}.csv"])
            held[store] = ([str(v) for v in pd.read_csv(io.StringIO(shown.stdout))[column]]
                           if shown.returncode == 0 else [])
        return held

    def sealed_files(self, this: Round) -> set[str]:
        """The files `this` round's kept seal holds, opened with the key."""
        name = f"line-movement-sealed-{this.attempt}"
        (artifact,) = [a for a in self.artifacts
                       if a["name"] == name and a["workflow_run"]["id"] == this.run_id]
        opened = self.tmp / f"opened{this.run_id}-{this.attempt}"
        opened.mkdir()
        with zipfile.ZipFile(artifact["zip"]) as zipped:
            zipped.extract("round.enc", opened)
        cipher = load_script("private_movement_chain.py").OPENSSL_CIPHER
        done = subprocess.run(
            ["openssl", "enc", "-d", *cipher, "-pass", "env:NHL_CHAIN_FALLBACK_KEY",
             "-in", str(opened / "round.enc"), "-out", str(opened / "round.tar")],
            env={**os.environ, "NHL_CHAIN_FALLBACK_KEY": KEY}, capture_output=True, text=True,
        )
        assert done.returncode == 0, done.stderr
        with tarfile.open(opened / "round.tar") as tar:
            return {m.name for m in tar.getmembers() if m.isfile()}


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    for tool in ("bash", "git", "openssl"):
        if shutil.which(tool) is None:
            pytest.fail(f"this test needs {tool}, which every runner here has")
    built = Chain(tmp_path, monkeypatch)
    built.seeded = built.seed()
    return built


def _column(processed: Path, store: str, column: str, day: str = "2026-10-15") -> list[str]:
    path = processed / store / f"{day}.csv"
    return [str(v) for v in pd.read_csv(path)[column]] if path.is_file() else []


def _instants(processed: Path, day: str = "2026-10-15") -> dict[str, list[str]]:
    return {store: _column(processed, store, column, day) for store, column in COLUMNS.items()}


NOTHING = {store: [] for store in COLUMNS}


def _went_home(*rounds: Round) -> None:
    """Each round's push reached the private chain, and the check agreed."""
    for this in rounds:
        assert this.outcomes[PUSH] == "success", f"{this.instant} push: {this.logs.get(PUSH)}"
        assert this.outcomes[VERIFY] == "success", f"{this.instant} check: {this.logs.get(VERIFY)}"


def test_a_red_price_runs_free_captures_reach_the_next_run(chain: Chain) -> None:
    """The finding's own replay: 14:00 green, 18:00 red, 21:00 and 23:00 green."""
    chain.run(AT_14)
    red = chain.run(AT_18, prices=False)  # the events list failed: exit 2, a red run
    assert red.red, "a failed price capture leaves only the `always()` steps to run"
    chain.run(AT_21)
    after = chain.run(AT_23).processed

    seen = _instants(after)
    assert AT_18 in seen["deployment"], "the 18:00 scratch list fell out of the chain"
    assert AT_18 in seen["line_combinations"], "the 18:00 line units fell out of the chain"
    assert AT_18 not in seen["line_movement"], "no price was captured at 18:00"

    deployment = pd.read_csv(after / "deployment" / "2026-10-15.csv")
    lines = pd.read_csv(after / "line_combinations" / "2026-10-15.csv")
    # The whole reason these exist: WHEN the news became public.
    assert deployment.loc[deployment["player"] == "Ryan Reaves", "captured_at"].min() == AT_18
    assert lines.loc[lines["player"] == "Matthew Knies", "retrieved_at"].min() == AT_18
    # Home, not carried in a sealed artifact: every round, the red one too,
    # pushed to the private chain, which holds what the last round saw.
    _went_home(*chain.rounds)
    assert chain.tip() == seen


def test_a_run_red_for_its_line_units_keeps_its_prices_in_the_chain(chain: Chain) -> None:
    """The gate that turns a missed line capture red says "the red X is the
    report, not the damage". So that run's prices, the ones that cost
    credits, must still reach the chain."""
    chain.run(AT_14)
    chain.run(AT_18, lines=False)
    after = chain.run(AT_21).processed

    seen = _instants(after)
    assert seen["line_movement"] == [AT_14, AT_18, AT_21]
    assert seen["deployment"].count(AT_18) >= 1
    _went_home(*chain.rounds)
    assert chain.tip()["line_movement"] == [AT_14, AT_18, AT_21]


def test_a_run_whose_restore_could_not_read_the_chain_loses_nothing(chain: Chain) -> None:
    """GitHub was down for its restore: the round starts its day files with
    its own rows alone. Its push MERGES into the private tip instead of
    replacing it, so every earlier capture, yesterday's included, is still
    in the chain the next run restores."""
    chain.run(YESTERDAY)
    chain.run(AT_14)
    thin = chain.run(AT_18, pull_down=True)
    assert thin.restored == NOTHING, "this restore was meant to come back empty"
    assert not (thin.processed / "line_movement" / "2026-10-14.csv").exists()
    # Said as a chain it could not read, not as one that is gone.
    assert "could not be restored" in thin.restore_problem, thin.logs.get("restore")
    assert "no movement branch" not in thin.restore_problem
    _went_home(thin)
    after = chain.run(AT_21).processed

    seen = _instants(after)
    assert chain.tip() == seen, "the next round did not restore what the chain holds"
    for store, instants in seen.items():
        assert instants == sorted(instants), f"{store} is not in capture order"
        assert {AT_14, AT_18, AT_21} <= set(instants), store
    yesterday = _instants(after, day="2026-10-14")
    assert chain.tip("2026-10-14") == yesterday
    for store, instants in yesterday.items():
        assert instants and set(instants) == {YESTERDAY}, f"yesterday's {store} was lost"
    assert chain.tip(SEEDED_DAY) == _instants(after, SEEDED_DAY) == chain.seeded


def test_three_thin_runs_in_a_row_lose_nothing(chain: Chain) -> None:
    """The public restore unioned the newest carrier with the two before it,
    so three thin runs in a row left every earlier capture outside its
    window. A merge into the private tip has no window."""
    chain.run(AT_14)
    for instant in (AT_18, AT_21, AT_23):
        thin = chain.run(instant, pull_down=True)
        assert thin.restored == NOTHING, instant
        _went_home(thin)
    after = chain.run(AT_01).processed

    seen = _instants(after)
    assert chain.tip() == seen, "the next round did not restore what the chain holds"
    for store, instants in seen.items():
        assert {AT_14, AT_18, AT_21, AT_23, AT_01} <= set(instants), store


def test_a_round_whose_push_failed_is_sealed_and_the_next_round_brings_it_home(
    chain: Chain,
) -> None:
    """The private repository is the round's only home, so a push that fails
    must not lose it: the round is sealed into a 7-day artifact, the next
    restore folds it in, and the next push carries it into the chain."""
    _went_home(chain.run(AT_14))
    stranded = chain.run(AT_21, push_down=True)
    assert stranded.outcomes[PUSH] == "failure"
    assert stranded.outcomes[SEAL] == "success", (stranded.outcomes[SEAL], stranded.logs.get(SEAL))
    assert stranded.outcomes[SEALED_UPLOAD] == "success"
    assert not any(AT_21 in held for held in chain.tip().values()), "the push was meant to fail"

    home = chain.run(AT_23)
    for store, instants in home.restored.items():
        assert AT_21 in instants, f"the restore did not fold the sealed {store} in"
    assert home.restore_problem == "", home.logs.get("restore")
    _went_home(home)
    for store, held in chain.tip().items():
        assert held == sorted(held), f"{store} is not in capture order"
        assert {AT_14, AT_21, AT_23} <= set(held), f"the chain lacks {store} rows"


def test_a_rerun_folds_in_its_first_attempts_sealed_round_and_seals_its_own(
    chain: Chain,
) -> None:
    """A red run invites a Re-run. With GitHub down for both attempts' pushes,
    attempt 2's restore folds attempt 1's sealed round in, and attempt 2
    seals under a name of its own: an artifact belongs to the run, not the
    attempt, and a second upload of one name is refused. The next round
    brings both attempts home."""
    chain.run(AT_14)
    first = chain.run(AT_18, prices=False, push_down=True)
    second = chain.run(AT_18_40, push_down=True, rerun=True)
    assert (second.run_id, second.attempt) == (first.run_id, 2)
    assert AT_18 in second.restored["deployment"], "attempt 2 did not fold attempt 1's round in"
    assert first.outcomes[SEALED_UPLOAD] == "success"
    assert second.outcomes[SEALED_UPLOAD] == "success", "attempt 2's round was sealed and not kept"
    _went_home(chain.run(AT_21))

    held = chain.tip()
    for store in ("deployment", "line_combinations"):
        assert AT_18 in held[store], f"attempt 1's {store} never reached the chain"
    for store, instants in held.items():
        assert AT_18_40 in instants, f"attempt 2's {store} never reached the chain"


def test_a_round_the_check_found_short_is_sealed_though_its_push_went_through(
    chain: Chain,
) -> None:
    """The push exited 0, and then the private branch was rewound before the
    check (another writer's force-push), so the tip lacks the round and the
    push's own exit says nothing of it. The check runs before the seal and
    the seal runs on its failure too. The seal lists the tip and holds only
    what it lacks: the seeded day, home already, stays out, so the seal does
    not grow to the chain's size. The next round brings the round home."""
    _went_home(chain.run(AT_14))
    before = chain.branch()
    short = chain.run(AT_18, after_push=lambda: chain.set_branch(before))
    assert short.outcomes[PUSH] == "success", short.logs.get(PUSH)
    assert short.outcomes[VERIFY] == "failure", short.logs.get(VERIFY)
    assert "row(s) missing from the private tip" in short.logs[VERIFY]
    assert short.outcomes[SEAL] == "success", short.logs.get(SEAL)
    assert short.outcomes[SEALED_UPLOAD] == "success"
    assert chain.sealed_files(short) == {f"{store}/2026-10-15.csv" for store in COLUMNS}
    assert not any(AT_18 in held for held in chain.tip().values()), "the branch was meant to be rewound"

    home = chain.run(AT_21)
    assert home.restore_problem == "", home.logs.get("restore")
    _went_home(home)
    for store, held in chain.tip().items():
        assert held == sorted(held), f"{store} is not in capture order"
        assert {AT_14, AT_18, AT_21} <= set(held), f"the chain lacks {store} rows"


def test_a_deleted_chain_is_a_fault_and_no_round_starts_a_thin_one(chain: Chain) -> None:
    """The chain has existed since 2026-10-02, so a missing `movement`
    branch was deleted or renamed; it is not "no chain yet". A round that
    finds it gone must not start a thin chain in its place, which every
    later restore, Closing Lines and the CLV step would read as the season.
    Its restore writes the fault for the restore gate, its push refuses, and
    the round is sealed; the next round folds that seal in and seals both.
    Once the branch is restored from its history, as the fault says to do,
    the next round brings every sealed round home.

    Row order is not pinned here, unlike the tests above: `unseal` folds a
    sealed copy in as the OLDER one, so rounds sealed while the branch was
    gone land ahead of the 14:00 rows the restored branch brings back, and
    the push keeps that order (reported with the stage-two review)."""
    _went_home(chain.run(AT_14))
    history = chain.branch()
    chain.delete_branch()
    gone = [chain.run(AT_18), chain.run(AT_21)]
    for this in gone:
        assert "The private repository has no movement branch" in this.restore_problem, (
            this.logs.get("restore"))
        assert "restore it from its history" in this.restore_problem
        assert this.outcomes[PUSH] == "failure"
        assert "has no `movement` branch" in this.logs[PUSH], this.logs[PUSH]
        assert chain.branch() is None, "a round started a thin chain in place of the deleted one"
        assert this.outcomes[VERIFY] == "failure"
        assert this.outcomes[SEAL] == "success", this.logs.get(SEAL)
        assert this.outcomes[SEALED_UPLOAD] == "success"
    assert AT_18 in gone[1].restored["deployment"], "the second round did not fold the first's seal in"
    assert chain.sealed_files(gone[1]) == {f"{store}/2026-10-15.csv" for store in COLUMNS}

    chain.set_branch(history)
    home = chain.run(AT_23)
    assert home.restore_problem == "", home.logs.get("restore")
    _went_home(home)
    for store, held in chain.tip().items():
        # Each round's own rows, as many times as it captured them: none
        # lost, none doubled by the two seals that both carry 18:00.
        captured = Counter(instant for this in chain.rounds
                           for instant in _instants(this.processed)[store] if instant == this.instant)
        assert set(captured) == {AT_14, AT_18, AT_21, AT_23}, store
        assert Counter(held) == captured, f"the chain does not hold each {store} row once"
    assert chain.tip(SEEDED_DAY) == chain.seeded


# --------------------------------------------------------------------------
# The union every fold of the chain makes: the pull, the push's merge into
# the tip, and the unseal, all through `restore_state.union_csv`, which
# `private_movement_chain` imports.
# --------------------------------------------------------------------------

def _union():
    return load_script("private_movement_chain.py").union_csv


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_the_union_keeps_a_repeated_row_as_often_as_it_was_captured(tmp_path: Path) -> None:
    older = _write(tmp_path / "old.csv", "a,b\n1,x\n1,x\n2,y\n")
    newer = _write(tmp_path / "new.csv", "a,b\n3,z\n")

    assert _union()(older, newer) == 3
    assert newer.read_text() == "a,b\n1,x\n1,x\n2,y\n3,z\n"


def test_a_row_the_newer_copy_repeats_is_kept_as_often_as_it_repeats(
    tmp_path: Path,
) -> None:
    """The multiset union from the other side: the newer copy holds a row
    twice that the older holds once, and the older holds a row the newer
    lacks. Each row is kept as often as the copy holding it most often has
    it, so nothing is lost and nothing is doubled. (A union that never
    counted down the older copy's matches read both newer rows as already
    known, recovered nothing and dropped the older row; the independent
    reviewer found that no test told the two apart.)"""
    older = _write(tmp_path / "old.csv", "a,b\n0,x\n1,a\n")
    newer = _write(tmp_path / "new.csv", "a,b\n1,a\n1,a\n")

    assert _union()(older, newer) == 1
    assert newer.read_text() == "a,b\n0,x\n1,a\n1,a\n"


def test_two_headers_are_not_merged_and_the_newer_file_is_untouched(tmp_path: Path) -> None:
    older = _write(tmp_path / "old.csv", "a,b\n1,x\n")
    newer = _write(tmp_path / "new.csv", "a,b,c\n3,z,q\n")

    assert _union()(older, newer) is None
    assert newer.read_text() == "a,b,c\n3,z,q\n"


def test_a_file_whose_parse_disagrees_with_its_lines_is_not_merged(tmp_path: Path) -> None:
    """A stray quote folds the rest of the file into one record; a union
    written from that read would drop rows and report success."""
    older = _write(tmp_path / "old.csv", 'a,b\n1,"x\n2,y\n3,z\n')
    newer = _write(tmp_path / "new.csv", "a,b\n4,w\n")

    assert _union()(older, newer) is None
    assert newer.read_text() == "a,b\n4,w\n"


def test_a_newer_copy_that_lost_rows_gets_them_back(tmp_path: Path) -> None:
    """The newer copy is a byte prefix of the older one: a round that could
    not read the chain, or a sealed round folded in after it."""
    older = _write(tmp_path / "old.csv", "a,b\n1,x\n2,y\n")
    newer = _write(tmp_path / "new.csv", "a,b\n1,x\n")

    assert _union()(older, newer) == 1
    assert newer.read_text() == "a,b\n1,x\n2,y\n"


def test_a_copy_that_does_not_parse_is_still_made_whole_by_one_that_extends_it(
    tmp_path: Path,
) -> None:
    """The same prefix case when the shared bytes do not parse (a stray quote
    in a row both copies hold). Each capture appended to the damaged copy, a
    byte extension the union passes unread, so the sealed copy extends the
    one the pull lays down; it is taken whole, unread. Parsed, neither copy
    could be merged, and the sealed round would never come home."""
    damaged = 'a,b\n1,"x\n'
    older = _write(tmp_path / "old.csv", damaged + "2,y\n3,z\n")
    newer = _write(tmp_path / "new.csv", damaged)

    assert _union()(older, newer) == 2
    assert newer.read_text() == damaged + "2,y\n3,z\n"
    assert not list(tmp_path.glob("*.union")), "the temp file was left behind"


def test_a_merged_file_is_byte_for_byte_what_the_capture_would_have_written(
    tmp_path: Path,
) -> None:
    """The deployment rows carry JSON lists, which the CSV has to quote. The
    next capture appends to this file and every reader parses it, so the
    union must write exactly what pandas writes for the same rows."""
    deployment = load_script("capture_deployment.py")
    early = deployment.rows_for_game(_nhl_api(AT_14)("right-rail"), game_id="77",
                                     captured_at=AT_14)
    late = deployment.rows_for_game(_nhl_api(AT_18)("right-rail"), game_id="77",
                                    captured_at=AT_18)
    older, newer, whole = (tmp_path / n for n in ("old.csv", "new.csv", "whole.csv"))
    pd.DataFrame(early).to_csv(older, index=False, lineterminator="\n")
    pd.DataFrame(late).to_csv(newer, index=False, lineterminator="\n")
    pd.DataFrame(early + late).to_csv(whole, index=False, lineterminator="\n")

    assert _union()(older, newer) == len(early)
    assert newer.read_bytes() == whole.read_bytes()
