"""Expired bought prices skip the experiments; they do not fail the refresh.

The bought prices exist in CI only in Historical Props Purchase's artifacts
(newest carrier run 33450963332, `historical-props` and `gameday-state`,
both expiring 2026-11-29). On 2026-09-25 the owner decided to let them
expire: the repository is public and the provider's terms forbid
redistributing bought prices as downloadable files. Experiment Refresh's
restore step then failed on "The bought prices did not restore" every week,
for a reason everyone already knew: permanent noise, which is how a real
failure of the same step would come to be ignored.

So the step tells two things apart, and these tests replay it (the real
restore_state.py, a fake `gh`, GitHub's `bash -e` and the pipefail form)
and then walk the job's later steps through their own `if:` conditions:

* (a) EXPIRED: every listing answered, and none of the three pairs that
  carry bought prices restored a run (their artifacts are gone, or there is
  no run at all). The step prints a `::notice::` naming the decision, sets
  `prices=expired`, still checks the boxscores and builds the samples, and
  exits 0; the experiments, the drift check, the "could not re-decide"
  failure and the evidence upload do not run, and the job is green.
* (b) BROKEN: a listing that fails, a carrier whose download fails, a
  carrier that restores and brings no price file, or a pair with no record
  of what its restore found. Each stays red, and never says "expired".

And with the prices present, nothing changes: no notice, every experiment
runs.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "experiment-refresh.yml"
RESTORE_STATE = PROJECT_ROOT / "scripts" / "restore_state.py"
GAMEDAY = "gameday-refresh.yml"
PURCHASE = "historical-props-purchase.yml"
PRICES = Path("processed") / "historical_prop_prices.csv"
BOUGHT = "event_id,price\nold,1.90\nnew,2.10\n"

EXPIRED_NOTICE = "::notice::The bought prices have expired from CI, as decided on 2026-09-25"
ABSENT_PRICES = "::error::The bought prices did not restore"
UNREACHABLE = "::error::GitHub could not be reached"

SHELLS = {
    "github-default": ["bash", "-e", "-c"],
    "pipefail": ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c"],
}

#: gh 2.97.0's two answers for "not here", as restore_state.py reads them: a
#: run whose every artifact has expired, and a run without that one.
FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["FAKE_GH_STATE"])
registry = json.loads((state / "registry.json").read_text())
failures_path = state / "failures.json"
failures = json.loads(failures_path.read_text())

def value(flag):
    return args[args.index(flag) + 1] if flag in args else None

def injected(key, message):
    if failures.get(key, 0) > 0:
        failures[key] -= 1
        failures_path.write_text(json.dumps(failures))
        print(message, file=sys.stderr)
        sys.exit(1)

if args[:2] == ["run", "list"]:
    workflow = value("--workflow")
    injected("list:" + workflow, "HTTP 502: Bad Gateway")
    runs = [r for r in registry if r["workflow"] == workflow
            and r["headBranch"] == value("--branch")][: int(value("--limit"))]
    fields = value("--json").split(",")
    print(json.dumps([{{k: r[k] for k in fields}} for r in runs]))
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    injected("download:" + run_id + ":" + name,
             "error downloading " + name + ": HTTP 502: Bad Gateway")
    run = next(r for r in registry if str(r["databaseId"]) == run_id)
    if not run["artifacts"]:
        print("no valid artifacts found to download", file=sys.stderr)
        sys.exit(1)
    if name not in run["artifacts"]:
        print("no artifact matches any of the names or patterns provided",
              file=sys.stderr)
        sys.exit(1)
    shutil.copytree(run["artifacts"][name], dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''

#: `python` on the step's PATH. restore_state.py runs for real; with
#: DROP_RECORD set its --record-run is withheld, as a restore that never
#: wrote its record. The dataset build is a no-op and the calibration writes
#: the samples file the step checks for.
FAKE_PYTHON = r'''#!{python}
import os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_PYTHON_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if args and args[0] == "scripts/restore_state.py":
    rest = args[1:]
    if os.environ.get("DROP_RECORD") and "--record-run" in rest:
        at = rest.index("--record-run")
        del rest[at:at + 2]
    sys.exit(subprocess.run([{python!r}, {restore!r}, *rest]).returncode)
if args and args[0] == "scripts/run_props_calibration.py":
    Path("data/outputs").mkdir(parents=True, exist_ok=True)
    Path("data/outputs/prop_calibration_samples.csv").write_text("built\n")
sys.exit(0)
'''


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    (job,) = document["jobs"].values()
    return job["steps"]


def _step(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"experiment-refresh.yml has no step named {name!r}")


def _artifact(root: Path, *, boxscores: int = 0, prices: str | None = None) -> str:
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    final = json.dumps({"gameState": "OFF"}, indent=2)
    for game in range(boxscores):
        (box / f"{game}.json").write_text(final, encoding="utf-8")
    if prices is not None:
        (root / PRICES).parent.mkdir(parents=True, exist_ok=True)
        (root / PRICES).write_text(prices, encoding="utf-8")
    return str(root)


def _run(workflow: str, run_id: int, **artifacts: str) -> dict:
    return {"databaseId": run_id, "workflow": workflow, "status": "completed",
            "conclusion": "success", "headBranch": "main",
            "artifacts": {name.replace("_", "-"): path for name, path in artifacts.items()}}


def _chain(tmp_path: Path, purchase: str) -> list[dict]:
    """Gameday Refresh carries the boxscores and no prices, as its real
    carriers do; the purchase runs are as `purchase` says."""
    arts = tmp_path / "artifacts"
    registry = [_run(GAMEDAY, 6001, gameday_state=_artifact(arts / "gameday", boxscores=500))]
    if purchase == "expired":
        # Both purchase runs listed, every artifact gone.
        registry += [_run(PURCHASE, 8002), _run(PURCHASE, 8001)]
    elif purchase == "no-runs":
        pass
    elif purchase == "carries":
        registry += [_run(PURCHASE, 8002,
                          historical_props=_artifact(arts / "p2", prices=BOUGHT),
                          gameday_state=_artifact(arts / "s2", prices=BOUGHT))]
    elif purchase == "carries-no-price-file":
        # A carrier that restores and brings no price file: broken, not expired.
        registry += [_run(PURCHASE, 8002, historical_props=_artifact(arts / "p2"))]
    else:
        raise AssertionError(purchase)
    return registry


def _restore(tmp_path: Path, shell: str, *, purchase: str, fail: dict | None = None,
             drop_record: bool = False) -> tuple[subprocess.CompletedProcess, dict, Path]:
    state = tmp_path / "gh"
    state.mkdir()
    (state / "registry.json").write_text(json.dumps(_chain(tmp_path, purchase)), encoding="utf-8")
    (state / "failures.json").write_text(json.dumps(fail or {}), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("gh", FAKE_GH.format(python=sys.executable)),
        ("python", FAKE_PYTHON.format(python=sys.executable, restore=str(RESTORE_STATE))),
    ):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    work = tmp_path / "work"
    work.mkdir()
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
           "FAKE_GH_STATE": str(state), "TMPDIR": str(tmp_path),
           "RESTORE_STATE_RETRY_SECONDS": "0", "GITHUB_OUTPUT": str(output),
           "FAKE_PYTHON_LOG": str(tmp_path / "python.log")}
    env.pop("DROP_RECORD", None)
    if drop_record:
        env["DROP_RECORD"] = "1"
    step = next(s for s in _steps() if s.get("id") == "restore")
    result = subprocess.run([*SHELLS[shell], step["run"]], cwd=work, capture_output=True,
                            text=True, timeout=120, env=env)
    outputs = dict(line.split("=", 1) for line in
                   output.read_text(encoding="utf-8").splitlines() if "=" in line)
    return result, outputs, work


# --------------------------------------------------------------------------
# The job after the restore, walked through its own `if:` conditions.
# --------------------------------------------------------------------------

_REF = re.compile(r"steps\.([A-Za-z_][\w-]*)\.outputs\.([A-Za-z_][\w-]*)")


def _condition(expression: str | None, outputs: dict[str, dict], failed: bool) -> bool:
    """GitHub's `if:` for the shapes this workflow uses: `always()`, `&&`,
    `||`, and `steps.X.outputs.Y` compared with `==` or `!=` to a quoted
    string. An unset output is ''. Without a status function, `success()`
    is implied. Any other shape fails the test rather than being guessed."""
    if expression is None:
        return not failed
    text = str(expression).strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    status = "always()" in text
    body = text.replace("always()", "True")
    body = _REF.sub(lambda m: repr(outputs.get(m.group(1), {}).get(m.group(2), "")), body)
    body = body.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    body = body.replace(" not =", " !=")
    assert re.fullmatch(r"[\s\w'\"=!()-]*", body) and "__" not in body, (
        f"an if: this simulator does not understand: {expression!r}"
    )
    value = bool(eval(body, {"__builtins__": {}}, {}))  # noqa: S307 - vetted above
    return value if status else (value and not failed)


def _job(restore: subprocess.CompletedProcess, restore_outputs: dict,
         *, moved: str = "0") -> tuple[bool, list[str], dict]:
    """Every step after the restore, in order: which ran, and whether the job
    ended red. The steps that do work are stood in for: the experiments ran
    and the drift check answered `moved`; the failure step fails."""
    failed = restore.returncode != 0
    outputs: dict[str, dict] = {"restore": restore_outputs}
    ran: list[str] = []
    after = False
    said = {}
    for step in _steps():
        if step.get("id") == "restore":
            after = True
            continue
        if not after:
            continue
        if not _condition(step.get("if"), outputs, failed):
            continue
        name = step["name"]
        ran.append(name)
        if step.get("id") == "started":
            outputs["started"] = {"at": "0"}
        elif step.get("id") == "drift":
            outputs["drift"] = {"moved": moved}
        elif name == "Fail if the refresh could not re-decide":
            failed = True
        elif name == "Say what this run did not do":
            env = {**os.environ, "PRICES": restore_outputs.get("prices", "")}
            said[name] = subprocess.run(["bash", "-e", "-c", step["run"]], env=env,
                                        capture_output=True, text=True).stdout
    return failed, ran, said


PRICE_DEPENDENT = [
    "Re-run every experiment",
    "Has anything changed its mind?",
    "Fail if the refresh could not re-decide",
    "Open a pull request when a verdict moved",
    "Keep the evidence",
]


# --------------------------------------------------------------------------
# (a) Expired: green, with the notice, the price-dependent steps skipped.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shell", sorted(SHELLS))
@pytest.mark.parametrize("purchase", ["expired", "no-runs"])
def test_expired_bought_prices_skip_the_experiments_and_the_run_is_green(
    tmp_path: Path, shell: str, purchase: str,
) -> None:
    result, outputs, work = _restore(tmp_path, shell, purchase=purchase)
    said = result.stdout + result.stderr

    assert result.returncode == 0, said
    assert EXPIRED_NOTICE in said, said
    assert "::error::" not in said, said
    assert outputs.get("prices") == "expired", outputs
    assert not (work / "data" / PRICES).exists()
    # Everything that needs no price still ran: the floor, the samples.
    # `\s*`: BSD wc pads its count, GNU wc does not.
    assert re.search(r"Boxscores restored:\s*500\n", said), said
    assert "samples: " in said, "the step stopped before building the samples"
    calls = (tmp_path / "python.log").read_text(encoding="utf-8")
    assert "scripts/build_datasets.py" in calls
    assert "scripts/run_props_calibration.py --reuse-samples" in calls

    failed, ran, spoken = _job(result, outputs, moved="2")
    assert not failed, f"the job ended red: {ran}"
    for name in PRICE_DEPENDENT:
        assert name not in ran, f"{name!r} ran on prices that expired"
    assert "Note when this run started" in ran
    assert "re-decided nothing" in spoken["Say what this run did not do"]
    assert "re-decided every experiment" not in spoken["Say what this run did not do"]


# --------------------------------------------------------------------------
# (b) Broken: red, and never called an expiry.
# --------------------------------------------------------------------------


BROKEN = {
    "purchase-listing-fails": dict(purchase="expired", fail={f"list:{PURCHASE}": 99}),
    "gameday-listing-fails": dict(purchase="expired", fail={f"list:{GAMEDAY}": 99}),
    "carrier-download-fails": dict(purchase="carries",
                                   fail={"download:8002:historical-props": 99}),
    "carrier-state-download-fails": dict(purchase="carries",
                                         fail={"download:8002:gameday-state": 99}),
    "carrier-brings-no-prices": dict(purchase="carries-no-price-file"),
    "no-record-of-the-restore": dict(purchase="expired", drop_record=True),
}


@pytest.mark.parametrize("shell", sorted(SHELLS))
@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_broken_restore_of_the_bought_prices_stays_red(
    tmp_path: Path, shell: str, case: str,
) -> None:
    result, outputs, _ = _restore(tmp_path, shell, **BROKEN[case])
    said = result.stdout + result.stderr

    assert result.returncode != 0, said
    assert EXPIRED_NOTICE not in said, "a breakage was reported as the decided expiry"
    assert outputs.get("prices") != "expired", outputs
    assert UNREACHABLE in said or ABSENT_PRICES in said, said
    failed, ran, spoken = _job(result, outputs)
    assert failed
    assert "Re-run every experiment" not in ran
    assert "Keep the evidence" in ran, "a red run still keeps what it has"
    assert "re-decided nothing" not in spoken["Say what this run did not do"]


def test_a_carrier_without_prices_is_named(tmp_path: Path) -> None:
    result, _, _ = _restore(tmp_path, "github-default", purchase="carries-no-price-file")
    said = result.stdout + result.stderr

    assert ABSENT_PRICES in said, said
    assert f"{PURCHASE}.historical-props (run 8002)" in said, said


# --------------------------------------------------------------------------
# With the prices present, nothing changes.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shell", sorted(SHELLS))
def test_restored_prices_run_every_experiment_as_before(tmp_path: Path, shell: str) -> None:
    result, outputs, work = _restore(tmp_path, shell, purchase="carries")
    said = result.stdout + result.stderr

    assert result.returncode == 0, said
    assert EXPIRED_NOTICE not in said
    assert "prices" not in outputs, outputs
    assert (work / "data" / PRICES).read_text(encoding="utf-8") == BOUGHT
    failed, ran, spoken = _job(result, outputs, moved="0")
    assert not failed
    for name in ("Re-run every experiment", "Has anything changed its mind?",
                 "Keep the evidence"):
        assert name in ran, f"{name!r} did not run with the prices present"
    assert "re-decided every experiment" in spoken["Say what this run did not do"]

    # A drift check that could not re-decide is still red.
    failed, ran, _ = _job(result, outputs, moved="2")
    assert failed and "Fail if the refresh could not re-decide" in ran


def test_the_simulator_reads_the_job_it_claims_to() -> None:
    """The walk above keys on these names; a renamed step would otherwise
    drop out of it silently and read as skipped."""
    names = {step.get("name") for step in _steps()}
    for name in [*PRICE_DEPENDENT, "Note when this run started", "Say what this run did not do"]:
        assert name in names, name
    assert _condition("always() && steps.restore.outputs.prices != 'expired'",
                      {"restore": {"prices": "expired"}}, True) is False
    assert _condition("always() && steps.restore.outputs.prices != 'expired'",
                      {"restore": {}}, True) is True
    assert _condition("steps.drift.outputs.moved == '2'",
                      {"drift": {"moved": "2"}}, False) is True
    assert _condition(None, {}, True) is False
