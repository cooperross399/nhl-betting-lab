"""The purchase restored its bought prices from a feature-branch dispatch.

Historical Props Purchase's "Restore the cached boxscores and samples" step
restores two artifacts. `gameday-state` goes through
`scripts/restore_state.py`. The bought prices, `historical-props`, were
chosen by an inline listing of the step's own:

    gh run list --workflow historical-props-purchase.yml --limit 20 \\
      --json databaseId --jq '.[].databaseId'

It passed no `--branch` and never looked at a run's `headBranch`, so the
newest run on ANY branch that carried the artifact was the one restored, and
its raw responses were copied into `data/raw/historical_props`. That is the
cache `rebuild_price_files.py` treats as the evidence and rebuilds the price
CSVs from, and both of the run's uploads (`historical-props` and
`gameday-state`) then carry it forward under a main run's id, past every
main-only filter downstream. It was the one run listing that #178, which
taught restore_state.py to read main only, left outside it ("No workflow file
changed"). The purchase is dispatch-only, so running it on a branch is one
click — and a probe, the mode meant to be run "repeatedly while exploring
retention", takes minutes.

Found by the failure-shape audit; confirmed by all three refuters. One ran
the step's own text against realistic history: the 11 real purchase runs, all
on main, newest 33450963332, plus one hypothetical newer dispatch on
`probe-new-market-key` that had bought two responses for one other event.
The step restored that branch run's 14 responses, and the rebuilt
`historical_prop_prices.csv` held 9,391 rows, 1,430 of them from the
branch-bought event; with `--branch main` added it restored main's 12 and
rebuilt 7,961 rows, none from the branch. Another planted a doctored price of
777 in the branch run's copy of a response main also held, and the 777
reached the CSV. Latent on 2026-09-25: every Historical Props Purchase run
(11 of 11) is on main, so the filtered and unfiltered listings are identical
and no published number moves.

These tests run that step's own run block, taken from the workflow file,
under `bash --noprofile --norc -eo pipefail`, against an offline `gh` that
honours `--branch`, `--status`, `--limit` and `--json` as `gh run list
--help` documents them and evaluates `--jq` with a real jq (`gh` embeds one
and prints strings raw, which is `jq -r`). Then the real
`rebuild_price_files.py` rebuilds the price file from whatever was restored.
One variant runs a `gh` that ignores `--branch`, so the per-run `headBranch`
check is exercised on its own; another crowds the listing window with branch
runs, so the server-side filter is exercised on its own. Checks in series
mask each other; each is given a scenario where it alone stands.

No purchase run in these scenarios carries `gameday-state`. That half of the
step goes through restore_state.py, whose branch filter is #178's and is
tested with it; handing `gameday-state` to a main Gameday Refresh run instead
means every file under `data/raw/historical_props` can only have come through
the listing these tests are about.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers.historical_props import _cache_path


WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
RESTORE_SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"
PURCHASE = "historical-props-purchase.yml"
GAMEDAY = "gameday-refresh.yml"
STEP = "Restore the cached boxscores and samples"

FEATURE = "probe-new-market-key"
MAIN_RUN = 7001
#: The first branch dispatch after it; a burst of them counts up from here.
BRANCH_RUN = 7002
#: The run doing the restore: listed by `gh`, still in progress, carries nothing.
THIS_RUN = 7100

SNAPSHOT = "2026-04-02T16:30:00Z"
#: One event both copies hold. The branch's copy was written by code nobody
#: reviewed; 777 is the refuter's doctored price.
#: Not in the provider's 32-hex shape, which the secrets guard reads as a
#: possible API key unless a tracked fixture records it as an event id.
SHARED_EVENT = "evt-both-copies"
PRICE = {"main": -115, FEATURE: 777}
MAIN_ONLY_EVENT = "evt-main-only"
BRANCH_ONLY_EVENT = "evt-branch-only"

FAKE_GH = r'''#!{python}
import json, os, shutil, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
registry = json.loads(Path(os.environ["FAKE_GH_REGISTRY"]).read_text())

def value(flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default

if args[:2] == ["run", "list"]:
    runs = [r for r in registry if r["workflow"] == value("--workflow")]
    branch = value("--branch")
    if branch is not None and os.environ.get("FAKE_GH_IGNORES_BRANCH") != "1":
        runs = [r for r in runs if r["headBranch"] == branch]
    status = value("--status")
    if status:
        # As `gh run list --help` documents it: a status or a conclusion.
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    # Only the fields asked for, as gh returns them: a filter on a field
    # the listing never requested sees null, exactly as it would for real.
    fields = [f for f in value("--json", "").split(",") if f]
    rows = [{{k: r[k] for k in fields}} for r in runs]
    expression = value("--jq")
    if expression is None:
        print(json.dumps(rows))
        sys.exit(0)
    done = subprocess.run([{jq!r}, "-r", expression], input=json.dumps(rows),
                          capture_output=True, text=True)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    sys.exit(done.returncode)
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


# --------------------------------------------------------------------------
# Scenario builders.
# --------------------------------------------------------------------------

def _run(run_id: int, *, workflow: str = PURCHASE, branch: str = "main",
         event: str = "workflow_dispatch", status: str = "completed",
         conclusion: str = "success",
         artifacts: dict[str, Path] | None = None) -> dict:
    """One row of `gh run list`, plus what `gh run download` can fetch."""
    return {
        "databaseId": run_id, "workflow": workflow, "status": status,
        "conclusion": conclusion, "headBranch": branch, "event": event,
        "artifacts": {name: str(path) for name, path in (artifacts or {}).items()},
    }


def _response(event_id: str, price: int) -> dict:
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
                                  "price": price, "point": 3.5}],
                }],
            }],
        },
    }


def _bought(root: Path, *, built_on: str, events: tuple[str, ...]) -> Path:
    """A `historical-props` artifact as `Upload what was bought` lays it out,
    each response at the path the purchase itself caches it under."""
    for event_id in events:
        path = _cache_path(event_id, SNAPSHOT, raw_dir=root / "raw")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_response(event_id, PRICE[built_on])),
                        encoding="utf-8")
    (root / "processed").mkdir(parents=True)
    (root / "processed" / "historical_prop_prices.csv").write_text(
        "provider_event_id,built_on\n"
        + "".join(f"{event_id},{built_on}\n" for event_id in events),
        encoding="utf-8",
    )
    (root / "outputs").mkdir(parents=True)
    (root / "outputs" / "player_props_backtest.md").write_text(
        f"backtest built on {built_on}", encoding="utf-8"
    )
    return root


def _gameday_state(root: Path) -> Path:
    """What a main Gameday Refresh uploads: here, three cached boxscores and
    no bought prices, so none can arrive by this route."""
    box = root / "raw" / "nhl" / "boxscore"
    box.mkdir(parents=True)
    for game in range(3):
        (box / f"{game}.json").write_text("{}", encoding="utf-8")
    return root


def _history(tmp_path: Path, *, branch_runs: int = 1,
             main_conclusion: str = "success") -> list[dict]:
    """Newest first: this run, the branch dispatch(es), main's last purchase,
    and the Gameday Refresh run the boxscores come from."""
    branch = _bought(tmp_path / "a-branch", built_on=FEATURE,
                     events=(SHARED_EVENT, BRANCH_ONLY_EVENT))
    main = _bought(tmp_path / "a-main", built_on="main",
                   events=(SHARED_EVENT, MAIN_ONLY_EVENT))
    return [
        _run(THIS_RUN, status="in_progress", conclusion=""),
        *(_run(BRANCH_RUN + n, branch=FEATURE,
               artifacts={"historical-props": branch})
          for n in reversed(range(branch_runs))),
        _run(MAIN_RUN, conclusion=main_conclusion,
             artifacts={"historical-props": main}),
        _run(6001, workflow=GAMEDAY, event="schedule",
             artifacts={"gameday-state": _gameday_state(tmp_path / "a-gameday")}),
    ]


# --------------------------------------------------------------------------
# Running the step as the runner runs it.
# --------------------------------------------------------------------------

def _step(scratch: Path) -> str:
    """The step's run block, its scratch download moved into `scratch`.

    A runner's /tmp is its own, fresh each job; this machine's is shared by
    every suite run on it, so the step's fixed `/tmp/probe` is the one thing
    rewritten. Anything else under /tmp is refused rather than written.
    """
    document = yaml.safe_load((WORKFLOWS / PURCHASE).read_text(encoding="utf-8"))
    found = [
        step["run"] for job in document["jobs"].values()
        for step in job.get("steps", []) if step.get("name") == STEP
    ]
    assert len(found) == 1, f"exactly one step named {STEP!r} in {PURCHASE}"
    assert "${{" not in found[0], f"an unstubbed expression is left in {STEP!r}"
    assert "/tmp/" not in found[0].replace("/tmp/probe", ""), (
        f"{STEP!r} writes to another fixed path under /tmp"
    )
    return found[0].replace("/tmp/probe", str(scratch / "probe"))


def _run_step(tmp_path: Path, registry: list[dict], *,
              ignores_branch: bool = False) -> tuple[Path, str]:
    """The step's own run block, in a fresh checkout, against the offline gh."""
    jq = shutil.which("jq")
    assert jq, (
        "these tests evaluate the step's `--jq` with a real jq, as gh does; "
        "every GitHub runner has one"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable, jq=jq), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    scratch = tmp_path / "runner-temp"
    scratch.mkdir()
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "restore_state.py").write_text(
        RESTORE_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        "GH_TOKEN": "not-a-token",
        "TMPDIR": str(scratch),
        "FAKE_GH_REGISTRY": str(tmp_path / "registry.json"),
        "FAKE_GH_LOG": str(tmp_path / "gh.log"),
        "FAKE_GH_IGNORES_BRANCH": "1" if ignores_branch else "0",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _step(scratch)],
        cwd=work, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return work / "data", result.stdout


def _bought_downloads(tmp_path: Path) -> list[str]:
    """Every run the step tried to take `historical-props` from, in order."""
    log = (tmp_path / "gh.log").read_text(encoding="utf-8").splitlines()
    return [line.split()[2] for line in log
            if line.startswith("run download ") and "--name historical-props" in line]


def _cached(data: Path) -> dict[str, int]:
    """Each restored response file, by name, with the price it holds."""
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))["data"]["bookmakers"]
        [0]["markets"][0]["outcomes"][0]["price"]
        for path in sorted((data / "raw" / "historical_props").glob("*.json"))
    }


def _main_files(tmp_path: Path) -> dict[str, int]:
    return {
        _cache_path(event_id, SNAPSHOT, raw_dir=tmp_path).name: PRICE["main"]
        for event_id in (SHARED_EVENT, MAIN_ONLY_EVENT)
    }


def load_script(name: str) -> ModuleType:
    """Import a script by path. They are entry points, not a package."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rebuilt(data: Path) -> pd.DataFrame:
    """What `Rebuild the price files from the raw cache` makes of it."""
    module = load_script("rebuild_price_files.py")
    code = module.main(["--raw-dir", str(data / "raw"),
                        "--processed-dir", str(data / "processed")])
    assert code == 0
    return pd.read_csv(data / "processed" / "historical_prop_prices.csv",
                       dtype={"provider_event_id": str})


# --------------------------------------------------------------------------
# The finding's scenario, with each half of the filter standing alone.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ignores_branch", [False, True],
                         ids=["gh-filters", "gh-ignores"])
def test_the_next_main_purchase_does_not_restore_a_branch_runs_bought_prices(
    tmp_path: Path, ignores_branch: bool,
) -> None:
    """The branch dispatch is the newest carrier; main's purchase is next.
    Main's responses are restored and nothing the branch wrote reaches the
    cache or the price file rebuilt from it — whether the branch is dropped
    by gh's filter or, when gh returns it anyway, by the run's own branch."""
    data, out = _run_step(tmp_path, _history(tmp_path),
                          ignores_branch=ignores_branch)

    assert str(BRANCH_RUN) not in _bought_downloads(tmp_path), out
    assert f"Bought-price cache restored from run {MAIN_RUN}" in out, out
    assert _cached(data) == _main_files(tmp_path), (
        "a response the branch run wrote is in main's raw cache"
    )
    assert (data / "processed" / "historical_prop_prices.csv").read_text(
        encoding="utf-8"
    ) == (tmp_path / "a-main" / "processed" / "historical_prop_prices.csv").read_text(
        encoding="utf-8"
    )

    rebuilt = _rebuilt(data)

    assert sorted(rebuilt["provider_event_id"]) == sorted([SHARED_EVENT, MAIN_ONLY_EVENT])
    assert set(rebuilt["american_odds"]) == {PRICE["main"]}


def test_branch_probes_cannot_crowd_mains_purchase_out_of_the_listing(
    tmp_path: Path,
) -> None:
    """The listing reads 20 runs. Filtered only after listing, twenty probes
    on a branch fill that window and main's purchase falls out of it: the run
    starts with no bought prices and re-buys what main already owns. Filtered
    by gh, the window is main's."""
    registry = _history(tmp_path, branch_runs=20)

    data, out = _run_step(tmp_path, registry)

    assert f"Bought-price cache restored from run {MAIN_RUN}" in out, out
    assert _cached(data) == _main_files(tmp_path)


def test_a_red_main_purchase_is_still_the_source_of_what_it_bought(
    tmp_path: Path,
) -> None:
    """Main-only is a filter on the branch, never on the conclusion: the run
    that spends the credits and the run that finishes green are not always
    the same run (the purchase behind the original restore bought 2,710
    events and died writing the CSV). An older green main run sits under it
    and must not be preferred."""
    registry = _history(tmp_path, main_conclusion="failure")
    older = _bought(tmp_path / "a-older-main", built_on="main", events=(SHARED_EVENT,))
    registry.insert(-1, _run(7000, artifacts={"historical-props": older}))

    data, out = _run_step(tmp_path, registry)

    assert f"Bought-price cache restored from run {MAIN_RUN}" in out, out
    assert _cached(data) == _main_files(tmp_path)
