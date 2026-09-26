"""A GitHub API error read as "no purchase carries bought prices", and the buy went ahead.

Historical Props Purchase's "Restore the cached boxscores and samples" step
restores two artifacts that carry prices the lab paid for. `gameday-state`
went through `scripts/restore_state.py` without `--require-newest`, where a
failed listing prints and returns no runs and a failed download moves on to
the next run. `historical-props` went through an inline listing:

    bought=$(gh run list --workflow historical-props-purchase.yml ... \\
      | while read -r id; do gh run download "$id" ... 2>/dev/null ...; done)

whose status nothing read. So an HTTP 502 on `gh run list` came out as an
empty `$bought`, and the step printed "No purchase run on main carries
bought prices. Anything bought this run is bought fresh." GitHub runs a step
that names no `shell:` under `bash -e`, without pipefail, so the step exited
0; under pipefail it exited 1, and it was `continue-on-error` either way.
Then:

* `rebuild_price_files.py` found no cache and left no file to guard;
* the buy found no cached event, so it bought the window again, up to the cap;
* `buy_historical_props.py` wrote `historical_prop_prices.csv` holding this
  run's rows alone, because there was no file to add them to;
* both uploads (`if: always()`) carried only those rows, and the next main
  purchase, and then Experiment Refresh, took this run as the newest carrier.

Found by the failure-shape audit; confirmed by all three refuters. The
reproduce refuter ran the step's own run block with the real
restore_state.py and a `gh` answering HTTP 502 to every call: under `bash -e`
the step exited 0 and printed both absence lines. The real
`hist.buy_historical_props`, driven by a stub provider replaying 12 real
cached responses, served 12 from the cache and made 0 requests after a
working restore, and after the 502 restore bought all 12 again: 12
requests, 1,284 credits. The run's two uploads carried 12 responses and
7,961 rows where the carrier before it held 60 and 40,942. The next purchase
rebuilt 7,961 rows with exit 0, and Experiment Refresh restored the thin copy
over a Gameday Refresh state holding 40,942 and passed its `-s` check.

The reachability refuter found that a failed download alone does it too:
with every listing answering and every download failing, the result was the
same. The chain's newest main carrier on 2026-09-26 is run 33450963332
(`gameday-state` 86,454,131 bytes, `historical-props` 51,374,400 bytes,
both expiring 2026-11-29). It holds 6,252 raw prop responses, and the home
checkout's store holds 3,804,233 rows. Full-window buys have cost 157,870 to
289,984 credits.

There was a second route to the same thin carrier, and these tests model it
because a real checkout has it. Both uploads were `if: always()`, and the
checkout tracks `data/processed/current_corrections.json` and several
reports under `data/outputs`. A run that restored nothing therefore still
uploaded a `historical-props` holding the committed reports and not one
bought response, and a `gameday-state` holding the tracked processed file.
The next purchase would download those without error and take them as the
chain.

These tests run the whole purchase job as GitHub would. Every step comes
from the workflow file in order, with each `if:` evaluated under GitHub's
rules (an `if:` with no status function gets `success() &&` in front),
`continue-on-error` honoured, and each `upload-artifact` modelled from the
paths the YAML names, rooted at their common ancestor. The work directory
holds the checkout's tracked `data/outputs` and `data/processed` files. An
offline `gh` injects HTTP 502s and tells a run holding no artifact from a
failed call in gh 2.97.0's own words. Each run block that can run offline
does run: the restore step, under GitHub's `bash -e` and under
`bash --noprofile --norc -eo pipefail`, and the price rebuild, through the
real `rebuild_price_files.py` `main()` on the work directory.

Three kinds of step are replaced and never executed: those that read the
credential, those that fetch from the NHL, and the measurement steps. The
buy is replaced too. It is recorded as a step that would spend credits, and
it models the one thing the real buy does that matters here: it pays for
every event of the window whose response is not already cached, at the path
`_cache_path` gives. No buy script is ever run. `scripts/restore_state.py
--refuse-unreachable` is also driven directly.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers.historical_props import _cache_path

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "historical-props-purchase.yml"
SCRIPTS = PROJECT_ROOT / "scripts"
PURCHASE = "historical-props-purchase.yml"
GAMEDAY = "gameday-refresh.yml"
RESTORE_STEP = "Restore the cached boxscores and samples"
BOUGHT_FRESH = "No purchase run on main carries bought prices."

SNAPSHOT = "2026-04-02T16:30:00Z"
#: What an earlier window bought: owned by the chain, outside today's window.
#: Not in the provider's 32-hex shape, which the secrets guard would read as a
#: possible API key.
OLDER = tuple(f"evt-older-{n}" for n in range(4))
#: The window every buy here asks for; the chain already owns its first two.
WINDOW = tuple(f"evt-window-{n}" for n in range(4))
OWNED = OLDER + WINDOW[:2]
#: A raw team response: only `gameday-state` carries the raw team cache.
TEAM_FILE = "slate_20260402T163000Z.json"

MAIN_RUN = 7001
GAMEDAY_RUN = 6001

#: The run block's shell. GitHub runs a step that names no `shell:` under
#: `bash -e {0}`; `shell: bash` is `bash --noprofile --norc -eo pipefail {0}`.
SHELLS = {
    "github-default": ["bash", "-e", "-c"],
    "pipefail": ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"],
}

#: Scripts that run offline and are run for real, in the work directory.
RUN_FOR_REAL = {"restore_state.py"}
#: Replaced, never executed: they read the credential, fetch from the NHL or
#: rebuild a measurement. None of them decides what the chain holds.
NEVER_RUN = {
    "check_provider_credential.py", "check_provider_quota.py",
    "fetch_nhl_data.py", "build_datasets.py", "run_props_calibration.py",
    "run_team_markets_measurement.py", "run_player_props_backtest.py",
    "run_what_we_can_claim.py",
}
#: Replaced by `Purchase._buy`, never executed.
BUYS = {"buy_historical_props.py", "buy_historical_team_prices.py"}

FAKE_GH = r'''#!{python}
import json, os, shutil, subprocess, sys
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

def injected(keys, message):
    for key in keys:
        if failures.get(key, 0) > 0:
            failures[key] -= 1
            failures_path.write_text(json.dumps(failures))
            print(message, file=sys.stderr)
            sys.exit(1)

if args[:2] == ["run", "list"]:
    workflow = value("--workflow")
    injected(["list:" + workflow, "list:*"],
             "HTTP 502: Bad Gateway (https://api.github.com/repos/owner/"
             "nhl-betting-lab/actions/workflows/" + workflow + "/runs)")
    runs = [r for r in registry if r["workflow"] == workflow]
    branch = value("--branch")
    if branch is not None:
        runs = [r for r in runs if r["headBranch"] == branch]
    status = value("--status")
    if status:
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    fields = [f for f in value("--json", "").split(",") if f]
    rows = [{{k: r[k] for k in fields}} for r in runs]
    expression = value("--jq")
    if expression is None:
        print(json.dumps(rows))
        sys.exit(0)
    # gh embeds jq and prints strings raw, which is `jq -r`.
    done = subprocess.run([{jq!r}, "-r", expression], input=json.dumps(rows),
                          capture_output=True, text=True)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    sys.exit(done.returncode)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    injected(["download:" + run_id + ":" + name, "download:*"],
             "error downloading " + name + ": HTTP 502: Bad Gateway")
    run = next((r for r in registry if str(r["databaseId"]) == run_id), {{}})
    held = run.get("artifacts") or {{}}
    # gh 2.97.0's two answers for a run that holds no such artifact: none
    # valid at all (never uploaded, or expired), or none of that name.
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


# --------------------------------------------------------------------------
# Artifacts, as the purchase lays them out.
# --------------------------------------------------------------------------

def _response(event_id: str) -> dict:
    """One cached event-odds response, in the provider's shape."""
    return {
        "timestamp": SNAPSHOT,
        "data": {
            "id": event_id,
            "commence_time": "2026-04-02T23:00:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [{
                "key": "draftkings", "title": "DraftKings",
                "markets": [{
                    "key": "player_shots_on_goal",
                    "outcomes": [{"name": "Over", "description": "Auston Matthews",
                                  "price": -115, "point": 3.5}],
                }],
            }],
        },
    }


def _pay_for(raw: Path, event_id: str) -> None:
    path = _cache_path(event_id, SNAPSHOT, raw_dir=raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_response(event_id)), encoding="utf-8")


def _carrier(root: Path, *, events: tuple[str, ...], boxscores: int = 0,
             team: bool = False) -> Path:
    """An artifact rooted where the upload roots it (`data/`): the raw
    responses, and the price file the real rebuild makes of them."""
    raw = root / "raw"
    for event_id in events:
        _pay_for(raw, event_id)
    box = raw / "nhl" / "boxscore"
    for game in range(boxscores):
        box.mkdir(parents=True, exist_ok=True)
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    if team:
        (raw / "historical_team_prices").mkdir(parents=True)
        (raw / "historical_team_prices" / TEAM_FILE).write_text(
            json.dumps({"timestamp": SNAPSHOT, "data": []}), encoding="utf-8")
    (root / "processed").mkdir(parents=True, exist_ok=True)
    if events:
        code = load_script("rebuild_price_files.py").main(
            ["--raw-dir", str(raw), "--processed-dir", str(root / "processed")])
        assert code == 0
    return root


def _responses(artifact: str | Path | None) -> set[str]:
    """Which events an artifact (or a data directory) holds a response for."""
    if artifact is None:
        return set()
    return {path.name.split("_")[0]
            for path in (Path(artifact) / "raw" / "historical_props").glob("*.json")}


def _team(artifact: str | Path) -> bool:
    """Whether an artifact holds the raw team response only `gameday-state` carries."""
    return (Path(artifact) / "raw" / "historical_team_prices" / TEAM_FILE).is_file()


def _checkout_files() -> list[str]:
    """The tracked files a fresh checkout has under the uploads' paths."""
    listed = subprocess.run(
        ["git", "ls-files", "data/outputs", "data/processed"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "data/processed/current_corrections.json" in listed, listed
    assert "data/outputs/player_props_backtest.md" in listed, listed
    return listed


# --------------------------------------------------------------------------
# The job, as GitHub runs it.
# --------------------------------------------------------------------------

def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _job() -> dict:
    jobs = _workflow()["jobs"]
    assert list(jobs) == ["purchase"], "the purchase is expected to be one job"
    return jobs["purchase"]


def _dispatch_defaults() -> dict[str, str]:
    document = _workflow()
    on = document.get("on", document.get(True))  # PyYAML reads `on` as True
    inputs = on["workflow_dispatch"]["inputs"]
    return {name: str(spec.get("default", "")) for name, spec in inputs.items()}


_TOKEN = re.compile(
    r"\s*('[^']*'|&&|\|\||==|!=|!|\(|\)|[A-Za-z_][\w-]*\(\)|[A-Za-z_][\w.-]*)"
)


def _holds(condition: object, *, inputs: dict, steps: dict, failed: bool) -> bool:
    """A step's `if:` as GitHub evaluates it, for the shapes this job uses."""
    text = str(condition).strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    if not re.search(r"\b(success|always|failure|cancelled)\(\)", text):
        text = f"success() && ({text})"
    python, position = [], 0
    while position < len(text.rstrip()):
        match = _TOKEN.match(text, position)
        assert match, f"the harness does not model `if: {condition}`"
        token, position = match.group(1), match.end()
        if token.startswith("'"):
            python.append(repr(token[1:-1]))
        elif token in {"&&", "||", "!"}:
            python.append({"&&": " and ", "||": " or ", "!": " not "}[token])
        elif token in {"==", "!=", "(", ")"}:
            python.append(token)
        elif token.endswith("()"):
            known = {"success()": not failed, "always()": True,
                     "failure()": failed, "cancelled()": False}
            assert token in known, f"the harness does not model {token}"
            python.append(repr(known[token]))
        elif token.startswith("inputs."):
            python.append(repr(inputs[token.split(".", 1)[1]]))
        elif token.startswith("steps."):
            _, step_id, field_name = token.split(".")
            assert field_name in {"outcome", "conclusion"}, token
            python.append(repr(steps.get(step_id, {}).get(field_name, "")))
        else:
            raise AssertionError(f"the harness does not model `{token}` in an `if:`")
    return bool(eval("".join(python), {"__builtins__": {}}))  # noqa: S307


@dataclass
class Outcome:
    run_id: int
    conclusion: str = "success"
    #: The step whose failure failed the job, if one did.
    failed_at: str | None = None
    log: str = ""
    #: Steps whose run block could spend credits (`--live`) that ran.
    paid: list[str] = field(default_factory=list)
    #: Events the buy paid for.
    spent: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


class Purchase:
    """Historical Props Purchase's runs, one after another, as GitHub runs them."""

    def __init__(self, tmp_path: Path, shell: str) -> None:
        jq = shutil.which("jq")
        assert jq, "the unfixed step's `--jq` is evaluated with a real jq, as gh does"
        self.tmp = tmp_path
        self.shell = shell
        self.registry: list[dict] = []  # newest first, as `gh run list` lists
        self.next_id = 7101
        self.uploads: list[tuple[int, str, Path]] = []
        self.state = tmp_path / "gh"
        self.state.mkdir(parents=True)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable, jq=jq), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.path = f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
        self.checkout = _checkout_files()

    def carrier(self, run_id: int, *, workflow: str = PURCHASE,
                conclusion: str = "success", artifacts: dict[str, Path]) -> None:
        """An older completed run on main, appended below the newer ones."""
        self.registry.append({
            "databaseId": run_id, "workflow": workflow, "status": "completed",
            "conclusion": conclusion, "headBranch": "main",
            "artifacts": {name: str(path) for name, path in artifacts.items()},
        })

    def run(self, mode: str, *, fail: dict[str, int] | None = None) -> Outcome:
        run_id = self.next_id
        self.next_id += 1
        work = self.tmp / f"run{run_id}"
        (work / "scripts").mkdir(parents=True)
        for relative in self.checkout:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"committed {relative}\n", encoding="utf-8")
        runner_temp = self.tmp / f"runner-temp-{run_id}"
        runner_temp.mkdir()
        running = {"databaseId": run_id, "workflow": PURCHASE, "status": "in_progress",
                   "conclusion": "", "headBranch": "main", "artifacts": {}}
        (self.state / "registry.json").write_text(
            json.dumps([running, *self.registry]), encoding="utf-8")
        (self.state / "failures.json").write_text(json.dumps(fail or {}), encoding="utf-8")
        inputs = {**_dispatch_defaults(), "mode": mode}
        env = {
            **os.environ,
            "PATH": self.path,
            "FAKE_GH_STATE": str(self.state),
            # A runner's /tmp is its own; this machine's is shared.
            "TMPDIR": str(runner_temp),
            "RESTORE_STATE_RETRY_SECONDS": "0",
            "GITHUB_STEP_SUMMARY": str(runner_temp / "summary.md"),
        }

        outcome = Outcome(run_id=run_id)
        steps: dict[str, dict[str, str]] = {}
        failed = False
        for step in _job()["steps"]:
            if not _holds(step.get("if", "success()"), inputs=inputs, steps=steps,
                          failed=failed):
                if step.get("id"):
                    steps[step["id"]] = {"outcome": "skipped", "conclusion": "skipped"}
                continue
            ok = self._step(step, work, env, inputs, outcome, runner_temp)
            result = "success" if ok else "failure"
            conclusion = "success" if step.get("continue-on-error") else result
            if step.get("id"):
                steps[step["id"]] = {"outcome": result, "conclusion": conclusion}
            if conclusion == "failure" and not failed:
                failed = True
                outcome.failed_at = step["name"]
        outcome.conclusion = "failure" if failed else "success"
        self.registry.insert(0, {**running, "status": "completed",
                                 "conclusion": outcome.conclusion,
                                 "artifacts": dict(outcome.artifacts)})
        return outcome

    # -- one step -------------------------------------------------------------

    def _step(self, step: dict, work: Path, env: dict, inputs: dict,
              outcome: Outcome, runner_temp: Path) -> bool:
        uses = str(step.get("uses", ""))
        if uses.startswith(("actions/checkout", "actions/setup-python")):
            return True
        if uses.startswith("actions/upload-artifact"):
            self._upload(step["with"], work, outcome)
            return True  # if-no-files-found: warn
        assert not uses, f"the harness does not model `uses: {uses}`"

        text = re.sub(r"\$\{\{\s*inputs\.(\w+)\s*\}\}",
                      lambda m: inputs[m.group(1)], str(step["run"]))
        assert "${{" not in text, f"an unmodelled expression in {step['name']!r}"
        if "--live" in text:
            outcome.paid.append(step["name"])
        scripts = set(re.findall(r"scripts/(\w+\.py)", text))
        if "pip install" in text:
            return True
        if scripts & BUYS:
            return self._buy(text, work, outcome)
        if scripts & NEVER_RUN:
            assert scripts <= NEVER_RUN, scripts
            return True
        if "rebuild_price_files.py" in scripts:
            assert scripts == {"rebuild_price_files.py"}, scripts
            # In-process, pointed at the work directory: run as a script it
            # would read the package's own data/ tree.
            code = load_script("rebuild_price_files.py").main(
                ["--raw-dir", str(work / "data" / "raw"),
                 "--processed-dir", str(work / "data" / "processed")])
            return code == 0
        assert scripts <= RUN_FOR_REAL, f"{step['name']!r} would run {scripts}"
        for name in scripts:
            shutil.copy(SCRIPTS / name, work / "scripts" / name)
        # The unfixed step downloaded into a fixed /tmp/probe; moved into
        # this run's scratch, and nothing else under /tmp is allowed. Checked
        # on the step as written, before the move: on a Linux runner pytest's
        # own tmp_path is under /tmp, so the moved text always holds "/tmp/".
        assert "/tmp/" not in text.replace("/tmp/probe", ""), (
            f"{step['name']!r} writes to a fixed path under /tmp"
        )
        text = text.replace("/tmp/probe", str(runner_temp / "probe"))
        step_env = dict(env)
        for key, raw in (step.get("env") or {}).items():
            raw = str(raw)
            if raw == "${{ github.token }}":
                raw = "not-a-token"
            assert "${{" not in raw, f"an unmodelled expression in {key}: {raw}"
            step_env[key] = raw
        result = subprocess.run(
            [*self._shell_for(step), text], cwd=work, env=step_env,
            capture_output=True, text=True, timeout=120,
        )
        outcome.log += result.stdout + result.stderr
        return result.returncode == 0

    def _shell_for(self, step: dict) -> list[str]:
        if self.shell != "github-default":
            return SHELLS[self.shell]
        assert "defaults" not in _workflow() and "defaults" not in _job()
        named = step.get("shell")
        assert named in (None, "bash"), named
        return SHELLS["pipefail" if named == "bash" else "github-default"]

    def _buy(self, text: str, work: Path, outcome: Outcome) -> bool:
        """What a buy does that matters to the chain: it pays for every event
        of the window whose response is not already cached. Never the real
        script; nothing here reaches a provider."""
        if "buy_historical_props.py" in text and "--probe" not in text:
            raw = work / "data" / "raw"
            for event_id in WINDOW:
                if not _cache_path(event_id, SNAPSHOT, raw_dir=raw).is_file():
                    _pay_for(raw, event_id)
                    outcome.spent.append(event_id)
        return True

    def _upload(self, given: dict, work: Path, outcome: Outcome) -> None:
        paths = [line.strip() for line in str(given["path"]).splitlines() if line.strip()]
        root = Path(os.path.commonpath(paths))
        kept = self.tmp / "artifacts" / str(outcome.run_id) / given["name"]
        found = False
        for relative in paths:
            source = work / relative
            files = [source] if source.is_file() else (
                [p for p in source.rglob("*") if p.is_file()] if source.is_dir() else [])
            for path in files:
                target = kept / path.relative_to(work / root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                found = True
        if found:
            outcome.artifacts[given["name"]] = str(kept)
            self.uploads.append((outcome.run_id, given["name"], kept))


def _seeded(tmp_path: Path, shell: str) -> Purchase:
    """The chain as it stands: main's last purchase carries both artifacts,
    with the older window, two events of today's and the raw team cache; a
    Gameday Refresh run carries boxscores and no bought prices."""
    chain = Purchase(tmp_path, shell)
    chain.carrier(MAIN_RUN, artifacts={
        "historical-props": _carrier(tmp_path / "a-props", events=OWNED),
        "gameday-state": _carrier(tmp_path / "a-state", events=OWNED,
                                  boxscores=3, team=True),
    })
    chain.carrier(GAMEDAY_RUN, workflow=GAMEDAY, artifacts={
        "gameday-state": _carrier(tmp_path / "a-gameday", events=(), boxscores=3),
    })
    return chain


def assert_refused(run: Outcome) -> None:
    """Stopped at the restore, before the first paid request, uploading nothing."""
    assert run.conclusion == "failure", run.log
    assert run.failed_at == RESTORE_STEP, (run.failed_at, run.log)
    assert run.paid == [], f"{run.paid} ran after a restore that could not ask GitHub"
    assert run.spent == []
    assert run.artifacts == {}, (
        f"run {run.run_id} uploaded {sorted(run.artifacts)} after a restore that "
        "could not ask GitHub; the next purchase would take it as the chain"
    )
    assert BOUGHT_FRESH not in run.log, run.log
    assert "HTTP 502" in run.log and "::error::" in run.log, run.log


def assert_the_chain_only_grows(chain: Purchase) -> None:
    """No upload of either artifact holds fewer bought responses than the one
    before it."""
    for name in ("historical-props", "gameday-state"):
        held: set[str] = set()
        for run_id, uploaded, kept in chain.uploads:
            if uploaded != name:
                continue
            now = _responses(kept)
            assert held <= now, f"run {run_id}'s {name} lost {sorted(held - now)}"
            held = now


# --------------------------------------------------------------------------
# GitHub could not be asked: the run stops before it spends.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("mode", "shell"), [
    ("buy", "github-default"), ("buy_team", "github-default"),
    ("probe", "github-default"), ("buy", "pipefail"),
])
def test_a_failed_listing_stops_the_purchase_before_it_spends_or_uploads(
    tmp_path: Path, mode: str, shell: str,
) -> None:
    """The finding's scenario: every `gh run list` answers HTTP 502."""
    chain = _seeded(tmp_path, shell)

    run = chain.run(mode, fail={"list:*": 99})

    assert_refused(run)


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("artifact", ["historical-props", "gameday-state"])
def test_a_failed_download_of_the_newest_carrier_stops_the_purchase(
    tmp_path: Path, artifact: str, shell: str,
) -> None:
    """Every listing answers, and the newest carrier's download fails. An
    older carrier cannot stand in: whatever the newest added would be lost.
    `gameday-state` matters as much as `historical-props`, because it
    alone carries the raw team responses."""
    chain = _seeded(tmp_path, shell)

    run = chain.run("buy", fail={f"download:{MAIN_RUN}:{artifact}": 99})

    assert_refused(run)


@pytest.mark.parametrize("fail", [
    {f"list:{PURCHASE}": 1},
    {f"download:{MAIN_RUN}:gameday-state": 1},
    {f"download:{MAIN_RUN}:historical-props": 1},
], ids=["one-failed-listing", "one-failed-state-download", "one-failed-props-download"])
def test_one_transient_failure_is_retried_and_the_purchase_goes_on(
    tmp_path: Path, fail: dict[str, int],
) -> None:
    """A single 502 is not an outage: each call is tried again, and the run
    starts from everything the chain holds."""
    chain = _seeded(tmp_path, "github-default")

    run = chain.run("buy", fail=fail)

    assert run.conclusion == "success", run.log
    assert f"Bought-price cache restored from run {MAIN_RUN} on main" in run.log, run.log
    assert run.spent == list(WINDOW[2:]), "it re-bought an event the chain owns"
    assert _responses(run.artifacts["historical-props"]) == set(OWNED + WINDOW)
    assert _team(run.artifacts["gameday-state"]), "the raw team cache fell out of the chain"


# --------------------------------------------------------------------------
# GitHub answered that nothing carries them: the run buys fresh.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("history", ["bare", "carriers-hold-none"])
def test_a_listing_that_holds_no_carrier_still_buys_fresh(
    tmp_path: Path, history: str, shell: str,
) -> None:
    """Only an answer starts the run without bought prices. On a bare
    repository, or where every purchase run holds none (refused before it
    uploaded, or expired), the run buys the window and keeps what it bought."""
    chain = Purchase(tmp_path, shell)
    if history == "carriers-hold-none":
        chain.carrier(7003, conclusion="failure", artifacts={})
        chain.carrier(7002, artifacts={
            "gameday-state-old": _carrier(tmp_path / "a-other", events=())})
        chain.carrier(GAMEDAY_RUN, workflow=GAMEDAY, artifacts={
            "gameday-state": _carrier(tmp_path / "a-gameday", events=(), boxscores=3)})

    run = chain.run("buy")

    assert run.conclusion == "success", run.log
    assert f"{BOUGHT_FRESH} Anything bought this run is bought fresh." in run.log, run.log
    assert run.paid == ["Buy a window"], run.paid
    assert run.spent == list(WINDOW)
    assert sorted(run.artifacts) == ["gameday-state", "historical-props"]


# --------------------------------------------------------------------------
# Over several runs: an outage leaves the chain as it was.
# --------------------------------------------------------------------------

def test_an_outage_never_shrinks_the_chain_or_rebuys_what_it_owns(tmp_path: Path) -> None:
    """A healthy purchase, one during an outage, then a healthy one. The
    outage run spends nothing and keeps nothing, so the run after it restores
    everything the chain held, from the run before it."""
    chain = _seeded(tmp_path, "github-default")

    first = chain.run("buy")
    outage = chain.run("buy", fail={"list:*": 99, "download:*": 99})
    after = chain.run("buy")

    assert first.conclusion == "success", first.log
    assert first.spent == list(WINDOW[2:])
    assert outage.spent == [], "the outage re-bought events the chain owns"
    assert after.conclusion == "success", after.log
    assert f"Bought-price cache restored from run {first.run_id} on main" in after.log
    assert after.spent == []
    for name in ("historical-props", "gameday-state"):
        assert _responses(after.artifacts[name]) == set(OWNED + WINDOW), name
    assert _team(after.artifacts["gameday-state"])
    assert_the_chain_only_grows(chain)


# --------------------------------------------------------------------------
# restore_state.py --refuse-unreachable, driven directly.
# --------------------------------------------------------------------------

def _restore(tmp_path: Path, registry: list[dict], *args: str,
             fail: dict[str, int] | None = None) -> tuple[subprocess.CompletedProcess, Path]:
    chain = Purchase(tmp_path, "github-default")
    (chain.state / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (chain.state / "failures.json").write_text(json.dumps(fail or {}), encoding="utf-8")
    dest = tmp_path / "dest"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "restore_state.py"), "--dest", str(dest), *args],
        env={**os.environ, "PATH": chain.path, "FAKE_GH_STATE": str(chain.state),
             "TMPDIR": str(tmp_path), "RESTORE_STATE_RETRY_SECONDS": "0"},
        capture_output=True, text=True, timeout=60,
    )
    return result, dest


def _listed(run_id: int, conclusion: str = "success", **artifacts: Path) -> dict:
    return {"databaseId": run_id, "workflow": PURCHASE, "status": "completed",
            "conclusion": conclusion, "headBranch": "main",
            "artifacts": {name.replace("_", "-"): str(path)
                          for name, path in artifacts.items()}}


def _downloads(tmp_path: Path, run_id: int) -> int:
    log = (tmp_path / "gh" / "gh.log").read_text(encoding="utf-8").splitlines()
    return sum(1 for line in log if line.startswith(f"run download {run_id} "))


STRICT = ("--artifact", "historical-props", "--workflow", PURCHASE,
          "--refuse-unreachable", "--attempts", "3")


@pytest.mark.parametrize("held", ["nothing", "another-artifact"])
def test_a_run_that_holds_none_is_passed_over_once_not_refused(
    tmp_path: Path, held: str,
) -> None:
    """gh's two answers for "not here" are answers: the older carrier is
    restored, and the run that holds none is asked once, not retried."""
    older = _carrier(tmp_path / "older", events=OLDER)
    newest = (_listed(7005) if held == "nothing"
              else _listed(7005, gameday_state=_carrier(tmp_path / "other", events=())))
    record = tmp_path / "run.txt"

    result, dest = _restore(tmp_path, [newest, _listed(7004, historical_props=older)],
                            *STRICT, "--record-run", str(record))

    assert result.returncode == 0, result.stdout + result.stderr
    assert _responses(dest) == set(OLDER)
    assert record.read_text(encoding="utf-8").strip() == "7004"
    assert _downloads(tmp_path, 7005) == 1


def test_a_listing_with_no_carrier_records_no_run(tmp_path: Path) -> None:
    record = tmp_path / "run.txt"

    result, dest = _restore(tmp_path, [_listed(7005)], *STRICT, "--record-run", str(record))

    assert result.returncode == 0, result.stdout + result.stderr
    assert record.read_text(encoding="utf-8").strip() == ""
    assert _responses(dest) == set()


def test_a_refused_restore_leaves_no_earlier_run_on_record(tmp_path: Path) -> None:
    """The record is emptied before GitHub is asked. A step that read it
    after a refusal it failed to act on would otherwise name a restore that
    never happened, and its own `exit 1` would be the only thing proven to
    stop the run (a missing file happened to stop it too)."""
    record = tmp_path / "run.txt"
    record.write_text("7004\n", encoding="utf-8")
    newest = _carrier(tmp_path / "newest", events=OWNED)

    result, _ = _restore(tmp_path, [_listed(7005, historical_props=newest)], *STRICT,
                         "--record-run", str(record), fail={"list:*": 99})

    assert result.returncode == 1, result.stdout + result.stderr
    assert record.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize("fail", [{"list:*": 99}, {"download:7005:historical-props": 99}],
                         ids=["listing", "download"])
def test_a_failure_to_ask_exits_1_and_restores_nothing_older(
    tmp_path: Path, fail: dict[str, int],
) -> None:
    newest = _carrier(tmp_path / "newest", events=OWNED)
    older = _carrier(tmp_path / "older", events=OLDER)
    registry = [_listed(7005, historical_props=newest), _listed(7004, historical_props=older)]

    result, dest = _restore(tmp_path, registry, *STRICT, fail=fail)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "::error::" in result.stdout and "3 attempt(s)" in result.stdout, result.stdout
    assert _responses(dest) == set(), "an older carrier stood in for the newest"


@pytest.mark.parametrize("merge", ["fill", "union"])
def test_a_failed_download_underneath_is_not_read_as_absence_either(
    tmp_path: Path, merge: str,
) -> None:
    """The newest carrier is red, so the last success is laid underneath it
    (or, with --union, older carriers are unioned in). A failed download of
    that one is a failure too, not a run holding none."""
    red = _carrier(tmp_path / "red", events=WINDOW)
    good = _carrier(tmp_path / "good", events=OLDER)
    registry = [_listed(7005, "failure", historical_props=red),
                _listed(7004, historical_props=good)]
    extra = ("--union", "2") if merge == "union" else ()

    failed, _ = _restore(tmp_path / "a", registry, *STRICT, *extra,
                         fail={"download:7004:historical-props": 99})
    healthy, dest = _restore(tmp_path / "b", registry, *STRICT, *extra)

    assert failed.returncode == 1, failed.stdout + failed.stderr
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert _responses(dest) == set(WINDOW + OLDER)


def test_refuse_unreachable_and_require_newest_are_two_contracts_not_one(
    tmp_path: Path,
) -> None:
    """--require-newest refuses a newest run that holds none; this flag
    passes over it. Asked for both, the script refuses to guess."""
    result, _ = _restore(tmp_path, [], *STRICT, "--require-newest")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "not allowed with" in result.stderr
