"""Line Movement's closing prices reach the store CLV is measured from.

History, short. Closing Lines lost its schedule on 2026-08-29 (Line
Movement's fetch already produced the same best price per selection), which
retired the store's only writer. Two hand-offs followed, and both were
downloadable odds files on a public repository, which the provider's terms
forbid: a `closing-line-captures` artifact (2026-09-24; Closing Lines was
disabled on 09-25, #126, before it published), then Line Movement's own
public `line-movement` artifact (2026-10-01).

Since stage two of the chain's move (2026-10-05) there is no public copy.
Line Movement keeps its chain only on branch `movement` of the private
repository cooperross399/nhl-closing-lines (`private_movement_chain.py
push`). A round whose push fails is sealed with NHL_CHAIN_FALLBACK_KEY into
a 7-day `line-movement-sealed-N` artifact, and the next round's restore
unseals it, so that round's push carries it home. Closing Lines runs when
Line Movement completes, pulls the chain from the private repository into
data/processed, derives the closing prices from it, and pushes them to the
same repository's `main`. It reads no artifact, holds no grant here beyond
`contents: read`, and spends no credit.

The structural half reads the YAML. The executed half runs the step blocks
exactly as written under the shell GitHub uses (Closing Lines' hand-off, and
Line Movement's restore and seal), with `python` the real interpreter and
the real scripts reaching a local bare repository through the very URL they
build (`url.<bare>.insteadOf`); `gh` is a tripwire, or a stub serving one
sealed artifact. Closing Lines' publish runs in-process with its step's
exact arguments, and Line Movement's chain push with its step's subcommand
and flag, because each asks GitHub's API that the target is private and
only that answer is replaced. The exits the real pull cannot be made to give
offline (unreachable, damaged, refused) come from a stub.

One test fails on 2026-10-05 and should until the script changes: Line
Movement's push, run exactly as written from its checkout, keeps nothing,
because its folder is relative and git reads it from a temporary repository
(`test_line_movements_push_keeps_the_round_from_its_own_checkout`). Every
other test runs that push with the folder made absolute, so each fails only
for its own property.

Not covered here: a re-run's second attempt recovering the first attempt's
round. It takes the same two paths (the private chain, or the first
attempt's sealed artifact, since unseal reads every unexpired
`line-movement-sealed-*`), but which attempt wrote an artifact is not
something this file models, and the red gates' wording is not tested.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab.config import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_closing_store as store  # noqa: E402
import private_movement_chain as chain  # noqa: E402

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
HANDOFF = "Take the chain from the private repository"
PUBLISH = "Publish to the private store"
RESTORE = "Restore today's captures"
KEEP = "Keep the captures privately"
SEAL = "Seal this round when the private chain did not take it"
SEALED_UPLOAD = "Keep the sealed round"
CHAIN = "private_movement_chain.py"
STORE = "private_closing_store.py"
REPO = "owner/lab"
TOKEN = "t"
KEY = "a-fallback-key"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(document: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    return document.get("on", document.get(True)) or {}


def _steps(document: dict) -> dict[str, dict]:
    (job,) = document["jobs"].values()
    return {step.get("name"): step for step in job["steps"]}


def _closing() -> dict[str, dict]:
    return _steps(_load("closing-lines.yml"))


def _movement() -> dict[str, dict]:
    """Line Movement's capture job (the other two jobs only wait)."""
    return {step.get("name"): step for step in _load("line-movement.yml")["jobs"]["capture"]["steps"]}


def _invocations(run: str, script: str) -> list[list[str]]:
    """The arguments of every `python scripts/<script>` command in a run
    block, read as the shell reads them (comments dropped)."""
    found = []
    for line in run.replace("\\\n", " ").splitlines():
        words = shlex.split(line, comments=True)
        for i in range(len(words) - 1):
            if words[i] == "python" and words[i + 1] == f"scripts/{script}":
                args = []
                for word in words[i + 2:]:
                    if word in {"||", "&&", "|", ";"}:
                        break
                    args.append(word)
                found.append(args)
    return found


def _exact(step: dict, script: str) -> list[str]:
    """The arguments of a one-command step, which must call `script`."""
    (args,) = _invocations(step["run"], script)
    return args


# -- structure ----------------------------------------------------------------


def test_closing_lines_pulls_the_chain_line_movement_pushes():
    """One writer, one reader, the same repository and branch: neither names
    a --repo or a --remote of its own, and the hand-off pulls into the
    folder the publish reads."""
    callers = {name: str(step["run"]) for name, step in _movement().items()
               if f"scripts/{CHAIN}" in str(step.get("run", ""))}
    pushes = [(name, args) for name, run in callers.items()
              for args in _invocations(run, CHAIN) if args[:1] == ["push"]]
    assert pushes == [(KEEP, ["push", "--processed-dir", "data/processed"])]
    steps = _closing()
    assert _invocations(steps[HANDOFF]["run"], CHAIN) == [["pull", "--dest", "data/processed"]]
    assert _exact(steps[PUBLISH], STORE) == ["push", "--processed-dir", "data/processed"]


def test_line_movement_no_longer_hands_over_a_closing_price_artifact():
    for job in _load("line-movement.yml")["jobs"].values():
        for step in job["steps"]:
            assert (step.get("with") or {}).get("name") != "closing-line-captures"


def test_line_movement_keeps_no_day_file_in_a_public_artifact():
    """The `line-movement` upload Closing Lines used to take is gone; the
    only upload left beside the ladder scan is the sealed round, which is
    written outside the workspace."""
    uploads = [step for job in _load("line-movement.yml")["jobs"].values()
               for step in job["steps"] if str(step.get("uses", "")).startswith("actions/upload-artifact")]
    assert any(step.get("name") == SEALED_UPLOAD for step in uploads)
    for step in uploads:
        for path in str(step["with"]["path"]).split():
            assert not path.startswith("data/processed"), (step["name"], path)
            assert cl.MOVEMENT_DIRNAME not in path, (step["name"], path)


def test_closing_lines_runs_when_line_movement_completes():
    source = _load("line-movement.yml")["name"]
    trigger = _triggers(_load("closing-lines.yml")).get("workflow_run") or {}
    assert trigger.get("workflows") == [source]
    assert "completed" in trigger.get("types", [])


def _secrets(step: dict) -> set[str]:
    return set(re.findall(r"secrets\.([A-Z0-9_]+)", yaml.safe_dump(step)))


def test_no_step_that_can_spend_runs_on_a_hand_off():
    """A step that reads the provider key is a step that can buy prices."""
    steps = _load("closing-lines.yml")["jobs"]["capture"]["steps"]
    spending = [s for s in steps if "NHL_ODDS_API_KEY" in yaml.safe_dump(s)]
    assert spending, "the dispatch path must still be able to capture"
    for step in spending:
        assert "github.event_name != 'workflow_run'" in str(step.get("if", "")), step["name"]
    # The hand-off reads the private repository and nothing else.
    assert _secrets(_closing()[HANDOFF]) == {store.TOKEN_ENV}


def test_the_store_token_reaches_only_the_private_repository_steps():
    """The hand-off reads the chain with it, the publish writes the store
    with it, and the step that holds the provider key never holds it."""
    holders = {name for name, step in _closing().items() if store.TOKEN_ENV in _secrets(step)}
    assert holders == {HANDOFF, PUBLISH}
    for name, step in _closing().items():
        assert not {store.TOKEN_ENV, "NHL_ODDS_API_KEY"} <= _secrets(step), name
    # The hand-off only reads: its one command is a pull.
    assert [args[0] for args in _invocations(_closing()[HANDOFF]["run"], CHAIN)] == ["pull"]
    assert _invocations(_closing()[HANDOFF]["run"], STORE) == []


def test_each_path_runs_the_steps_it_needs():
    steps = _steps(_load("closing-lines.yml"))
    assert steps[HANDOFF]["if"] == "github.event_name == 'workflow_run'"
    assert steps["Capture"]["if"] == "github.event_name != 'workflow_run'"
    assert "event_name" not in steps[PUBLISH]["if"], "both paths publish"
    assert "steps.handoff.outputs.empty != 'true'" in steps[PUBLISH]["if"]
    assert "steps.capture.outputs.empty_slate != 'true'" in steps[PUBLISH]["if"]


def test_a_hand_off_is_taken_only_from_the_default_branch():
    guard = str(_load("closing-lines.yml")["jobs"]["capture"]["if"])
    assert "github.event.workflow_run.head_branch" in guard
    assert "github.event.repository.default_branch" in guard


def test_closing_lines_holds_no_grant_here_beyond_reading_its_code():
    """It reads no other run's artifacts any more, so `actions: read` went
    with them, and it never held a write grant on this repository."""
    assert _load("closing-lines.yml")["permissions"] == {"contents": "read"}


# -- the steps, executed ------------------------------------------------------

TRIPWIRE = 'echo "$*" >> "$GH_LOG"\nexit 1\n'
#: What a step's own `env:` supplies, so a replay holds only what it names.
STEP_OWNED = ("NHL_CLOSING_LINES_TOKEN", "NHL_CHAIN_FALLBACK_KEY", "NHL_ODDS_API_KEY", "GH_TOKEN",
              "PYTHONPATH", "GITHUB_REPOSITORY", "GITHUB_OUTPUT", "GITHUB_WORKSPACE", "RUNNER_TEMP",
              "GITHUB_STEP_SUMMARY")


def _fill(text: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, text)


def _script(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _runner(tmp_path: Path, name: str, *, gh: str = TRIPWIRE, python: str | None = None) -> dict:
    """A fresh runner: a checkout holding the scripts and src the blocks
    call by relative path, a stub bin, and a RUNNER_TEMP outside the
    checkout."""
    root = tmp_path / name
    work, stubs, temp = root / "work", root / "bin", root / "temp"
    for folder in (work, stubs, temp):
        folder.mkdir(parents=True)
    (work / "scripts").symlink_to(PROJECT_ROOT / "scripts", target_is_directory=True)
    (work / "src").symlink_to(PROJECT_ROOT / "src", target_is_directory=True)
    _script(stubs / "gh", gh)
    _script(stubs / "python", python or f'exec "{sys.executable}" "$@"\n')
    output = root / "github_output.txt"
    output.write_text("")
    return {"work": work, "bin": stubs, "temp": temp, "output": output, "gh_log": root / "gh.log"}


def _run_step(runner: dict, step: dict, values: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """`step`'s run block as written, under the shell GitHub uses, with only
    the environment its own `env:` names plus what every runner sets."""
    values = {"secrets.NHL_CLOSING_LINES_TOKEN": TOKEN, "secrets.NHL_CHAIN_FALLBACK_KEY": KEY,
              "github.token": "x", **(values or {})}
    env = {key: value for key, value in os.environ.items() if key not in STEP_OWNED}
    env.update({"PATH": f"{runner['bin']}{os.pathsep}{os.environ['PATH']}",
                "GITHUB_OUTPUT": str(runner["output"]), "GITHUB_WORKSPACE": str(runner["work"]),
                "RUNNER_TEMP": str(runner["temp"]), "GITHUB_REPOSITORY": REPO,
                "GH_LOG": str(runner["gh_log"])})
    env.update({key: _fill(str(value), values) for key, value in (step.get("env") or {}).items()})
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _fill(step["run"], {})],
                          cwd=runner["work"], env=env, capture_output=True, text=True)


def _outputs(runner: dict) -> dict[str, str]:
    """GITHUB_OUTPUT as the runner reads it: the last value of a key wins."""
    found = {}
    for line in runner["output"].read_text().splitlines():
        key, _, value = line.partition("=")
        found[key] = value
    return found


def _in_process(step: dict, script: str, main, work: Path, monkeypatch) -> int:
    """A one-command step's exact arguments, run from its checkout."""
    monkeypatch.chdir(work)
    return main(_exact(step, script))


def _refs(bare: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "for-each-ref"],
                          capture_output=True, text=True, check=True).stdout


def _keep(work: Path, monkeypatch) -> int:
    """Line Movement's "Keep the captures privately": the step's own
    subcommand and flag, from its checkout, with the folder it names made
    absolute. As written, relative, it does not keep the round; that is
    `test_line_movements_push_keeps_the_round_from_its_own_checkout`, and
    the tests downstream of the push are not made to fail on it too."""
    args = _exact(_movement()[KEEP], CHAIN)
    at = args.index("--processed-dir") + 1
    args[at] = str(work / args[at])
    monkeypatch.chdir(work)
    return chain.main(args)


def _keep_round(tmp_path: Path, name: str, rounds: list[pd.DataFrame], monkeypatch,
                *, folder: str = cl.MOVEMENT_DIRNAME) -> None:
    """A Line Movement round whose "Keep the captures privately" landed."""
    work = _runner(tmp_path, name)["work"]
    processed = work / "data" / "processed"
    if folder == cl.MOVEMENT_DIRNAME:
        _day_file(processed, rounds)
    else:
        (processed / folder).mkdir(parents=True)
        pd.concat(rounds).to_csv(processed / folder / "2026-10-08.csv", index=False)
    assert _keep(work, monkeypatch) == chain.EXIT_OK


def test_line_movements_push_keeps_the_round_from_its_own_checkout(tmp_path, private, monkeypatch):
    """The step exactly as written, run from the checkout as GitHub runs it.

    Measured 2026-10-05: it returns 1 and keeps nothing, saying git "could
    not open 'data/processed/line_movement/2026-10-08.csv'". The folder is
    relative, and `blob_of` hands each path to git running in the push's own
    temporary repository. In stage two this push is the round's only home,
    so a round it does not keep lives only in its sealed artifact.
    """
    work = _runner(tmp_path, "movement")["work"]
    _day_file(work / "data" / "processed", [_round(14, 120.0)])

    assert _in_process(_movement()[KEEP], CHAIN, chain.main, work, monkeypatch) == chain.EXIT_OK

    kept = subprocess.run(["git", "--git-dir", str(private), "show",
                           f"{chain.CHAIN_BRANCH}:{cl.MOVEMENT_DIRNAME}/2026-10-08.csv"],
                          capture_output=True, text=True, check=True).stdout
    assert kept == (work / "data" / "processed" / cl.MOVEMENT_DIRNAME / "2026-10-08.csv").read_text()


def test_a_private_repository_with_no_chain_yet_publishes_nothing(tmp_path, private):
    runner = _runner(tmp_path, "closing")
    done = _run_step(runner, _closing()[HANDOFF])
    assert done.returncode == 0, done.stdout + done.stderr
    assert _outputs(runner).get("empty") == "true"


def test_a_chain_without_price_captures_publishes_nothing(tmp_path, private, monkeypatch):
    _keep_round(tmp_path, "movement", [_round(14, 120.0)], monkeypatch, folder="deployment")
    runner = _runner(tmp_path, "closing")
    done = _run_step(runner, _closing()[HANDOFF])
    assert done.returncode == 0, done.stdout + done.stderr
    assert (runner["work"] / "data" / "processed" / "deployment" / "2026-10-08.csv").is_file()
    assert _outputs(runner).get("empty") == "true"


@pytest.mark.parametrize("code", [chain.EXIT_FAILED, chain.EXIT_DAMAGED, chain.EXIT_REFUSED])
def test_a_chain_that_could_not_be_read_is_a_red_run_not_a_quiet_one(tmp_path, code):
    """GitHub unreachable, a file that would not merge, a token turned away:
    the rounds since the last push would be skipped quietly by a green run."""
    fake = (f'if [ "$1" = scripts/{CHAIN} ]; then\n'
            '  mkdir -p data/processed/line_movement && echo x > data/processed/line_movement/2026-10-08.csv\n'
            f'  exit {code}\nfi\nexit 97\n')
    runner = _runner(tmp_path, "closing", python=fake)
    done = _run_step(runner, _closing()[HANDOFF])
    assert done.returncode != 0
    assert "empty" not in _outputs(runner)


def test_a_hand_off_without_the_token_is_a_red_run(tmp_path, private):
    runner = _runner(tmp_path, "closing")
    done = _run_step(runner, _closing()[HANDOFF], {"secrets.NHL_CLOSING_LINES_TOKEN": ""})
    assert done.returncode != 0
    assert store.TOKEN_ENV in done.stdout
    assert "empty" not in _outputs(runner)


def test_what_line_movement_keeps_lands_where_the_publish_reads_it(tmp_path, private, monkeypatch):
    _keep_round(tmp_path, "movement", [_round(14, 120.0), _round(14, 125.0, "FanDuel")], monkeypatch)
    runner = _runner(tmp_path, "closing")

    done = _run_step(runner, _closing()[HANDOFF])
    assert done.returncode == 0, done.stdout + done.stderr
    assert "empty" not in _outputs(runner)
    assert (runner["work"] / "data" / "processed" / cl.MOVEMENT_DIRNAME / "2026-10-08.csv").is_file()
    assert _in_process(_closing()[PUBLISH], STORE, store.main, runner["work"], monkeypatch) == store.EXIT_OK

    stored = pd.read_csv(pd.io.common.StringIO(_stored(private)))
    assert stored[["american_odds", "book"]].values.tolist() == [[125.0, "FanDuel"]]


def test_the_hand_off_writes_nothing_and_asks_github_for_no_artifact(tmp_path, private, monkeypatch):
    _keep_round(tmp_path, "movement", [_round(14, 120.0)], monkeypatch)
    before = _refs(private)
    runner = _runner(tmp_path, "closing")

    done = _run_step(runner, _closing()[HANDOFF])

    assert done.returncode == 0, done.stdout + done.stderr
    assert _refs(private) == before
    assert not runner["gh_log"].exists(), runner["gh_log"].read_text()


def test_a_round_whose_private_push_failed_reaches_the_store_with_the_next_round(
        tmp_path, private, monkeypatch):
    lm, closing = _movement(), _closing()

    # Round one: its push failed, so the seal step ran and the upload kept
    # what the seal wrote, at the path the upload names.
    first = _runner(tmp_path, "round-1")
    _day_file(first["work"] / "data" / "processed", [_round(14, 120.0), _round(14, 125.0, "FanDuel")])
    done = _run_step(first, lm[SEAL])
    assert done.returncode == 0, done.stdout + done.stderr
    kept = Path(_fill(lm[SEALED_UPLOAD]["with"]["path"], {"runner.temp": str(first["temp"])}))
    artifact = tmp_path / "sealed.zip"
    with zipfile.ZipFile(artifact, "w") as zipped:
        # A single-file upload is rooted at the file's own folder.
        zipped.write(kept, arcname=kept.name)
    listing = json.dumps({
        "id": 11, "expired": False, "created_at": "2026-10-08T14:06:00Z",
        "name": _fill(lm[SEALED_UPLOAD]["with"]["name"], {"github.run_attempt": "1"}),
        "workflow_run": {"id": 7, "head_branch": "main", "repository_id": 1, "head_repository_id": 1},
    })

    # Closing Lines after round one: the private chain does not hold it.
    after_first = _runner(tmp_path, "closing-1")
    assert _run_step(after_first, closing[HANDOFF]).returncode == 0
    assert _outputs(after_first).get("empty") == "true"

    # Round two, on a fresh runner: its restore opens round one...
    gh = ('echo "$*" >> "$GH_LOG"\ncase "$*" in\n'
          f'  *"repos/{REPO}/actions/artifacts?per_page=100"*) echo {shlex.quote(listing)} ;;\n'
          f'  *"repos/{REPO}/actions/artifacts/11/zip"*) cat {shlex.quote(str(artifact))} ;;\n'
          '  *) exit 1 ;;\nesac\n')
    second = _runner(tmp_path, "round-2", gh=gh)
    done = _run_step(second, lm[RESTORE])
    assert done.returncode == 0, done.stdout + done.stderr
    assert (second["work"] / "restore_problem.txt").read_text() == ""
    # ...appends its own round to the day file as the capture does, and its
    # push lands.
    day = second["work"] / "data" / "processed" / cl.MOVEMENT_DIRNAME / "2026-10-08.csv"
    _round(21, 105.0).to_csv(day, mode="a", header=False, index=False)
    assert _keep(second["work"], monkeypatch) == chain.EXIT_OK

    # Closing Lines after round two publishes both rounds.
    after_second = _runner(tmp_path, "closing-2")
    done = _run_step(after_second, closing[HANDOFF])
    assert done.returncode == 0, done.stdout + done.stderr
    assert _in_process(closing[PUBLISH], STORE, store.main, after_second["work"], monkeypatch) == store.EXIT_OK
    stored = pd.read_csv(pd.io.common.StringIO(_stored(private))).sort_values("captured_at")
    assert stored[["captured_at", "american_odds", "book"]].values.tolist() == [
        ["2026-10-08T14:00:00Z", 125.0, "FanDuel"], ["2026-10-08T21:00:00Z", 105.0, "BetMGM"]]


# -- the push, executed -------------------------------------------------------


GAME = {
    "commence_time": "2026-10-08T23:00:00Z",
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
}


def _round(hour: int, odds: float, book: str = "BetMGM") -> pd.DataFrame:
    """One Line Movement round in its day file's columns."""
    return pd.DataFrame([{**GAME, "market": "moneyline", "player": "",
                          "selection": "away", "line": None,
                          "american_odds": odds, "book": book,
                          "captured_at": f"2026-10-08T{hour:02d}:00:00Z"}])


def _day_file(processed: Path, rounds: list[pd.DataFrame], day: str = "2026-10-08") -> None:
    folder = processed / cl.MOVEMENT_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    pd.concat(rounds, ignore_index=True).to_csv(folder / f"{day}.csv", index=False)


@pytest.fixture
def bare(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "store.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=seed, check=True)
    (seed / "README.md").write_text("private\n")
    subprocess.run(["git", "add", "-A"], cwd=seed, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=seed, check=True)
    subprocess.run(["git", "push", "-q", str(path), "HEAD:refs/heads/main"], cwd=seed, check=True)
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: True)
    monkeypatch.setattr(store, "utc_now", lambda: datetime(2026, 10, 9, tzinfo=timezone.utc))
    monkeypatch.setenv(store.TOKEN_ENV, TOKEN)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    return path


@pytest.fixture
def private(bare, monkeypatch) -> Path:
    """`bare` reached as production reaches the private repository: through
    the URL the scripts build from the token, redirected to the bare copy.
    Only the GitHub API's privacy answer is replaced, and only for it."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.file://{bare}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", store.remote_url(store.PRIVATE_REPO, TOKEN))
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: repo == store.PRIVATE_REPO)
    monkeypatch.setattr(chain, "sleep", lambda seconds: None)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    return bare


def _push(processed: Path, bare: Path) -> int:
    return store.main(["push", "--processed-dir", str(processed), "--remote", f"file://{bare}"])


def _stored(bare: Path, name: str = "2026-10-08.csv") -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "show", f"main:captures/{name}"],
                          capture_output=True, text=True, check=True).stdout


def test_the_first_push_establishes_the_day_file(tmp_path, bare):
    processed = tmp_path / "run1"
    _day_file(processed, [_round(14, 120.0), _round(14, 125.0, "FanDuel")])

    assert _push(processed, bare) == store.EXIT_OK

    stored = pd.read_csv(pd.io.common.StringIO(_stored(bare)))
    assert list(stored.columns) == list(cl.CAPTURE_COLUMNS)
    # One best-price row per selection per round: FanDuel's +125.
    assert stored[["american_odds", "book"]].values.tolist() == [[125.0, "FanDuel"]]


def test_later_rounds_merge_into_the_season_store(tmp_path, bare):
    first, second = tmp_path / "run1", tmp_path / "run2"
    _day_file(first, [_round(14, 120.0)])
    _day_file(second, [_round(14, 120.0), _round(21, 105.0)])

    assert _push(first, bare) == store.EXIT_OK
    assert _push(second, bare) == store.EXIT_OK

    stored = pd.read_csv(pd.io.common.StringIO(_stored(bare)))
    assert sorted(stored["captured_at"]) == ["2026-10-08T14:00:00Z", "2026-10-08T21:00:00Z"]


def test_a_push_never_drops_a_row_the_store_holds(tmp_path, bare):
    """A chain that has lost an earlier round must not erase it from the store."""
    full, short = tmp_path / "full", tmp_path / "short"
    _day_file(full, [_round(14, 120.0), _round(21, 105.0)])
    _day_file(short, [_round(23, 150.0)])

    assert _push(full, bare) == store.EXIT_OK
    assert _push(short, bare) == store.EXIT_OK

    stored = pd.read_csv(pd.io.common.StringIO(_stored(bare)))
    assert len(stored) == 3


def test_a_second_identical_push_commits_nothing(tmp_path, bare):
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0)])
    assert _push(processed, bare) == store.EXIT_OK
    tip = subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "main"],
                         capture_output=True, text=True, check=True).stdout
    assert _push(processed, bare) == store.EXIT_OK
    assert subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "main"],
                          capture_output=True, text=True, check=True).stdout == tip


def test_every_day_the_chain_carries_is_pushed_so_a_gap_heals(tmp_path, bare):
    """A league day weeks old that the store never received (a failed push,
    a week with no token) lands on the next push, for as long as the chain
    carries it."""
    processed = tmp_path / "run"
    days = ["2026-09-01", "2026-09-15", "2026-10-01", "2026-10-05", "2026-10-07"]
    for day in days:
        old = _round(14, 120.0)
        old["captured_at"] = f"{day}T14:00:00Z"
        _day_file(processed, [old], day=day)
    _day_file(processed, [_round(14, 120.0)])

    assert _push(processed, bare) == store.EXIT_OK

    for day in [*days, "2026-10-08"]:
        assert _stored(bare, f"{day}.csv"), f"{day} was skipped"


def _clone_and_edit(tmp_path: Path, bare: Path, name: str, edit) -> str:
    clone = tmp_path / f"clone-{len(list(tmp_path.glob('clone-*')))}"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    target = clone / name
    target.write_text(edit(target.read_text()))
    subprocess.run(["git", "commit", "-qam", "edit"], cwd=clone, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=clone, check=True)
    return _tip(bare)


def _tip(bare: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "main"],
                          capture_output=True, text=True, check=True).stdout


def test_a_damaged_remote_day_is_left_alone_and_every_other_day_is_pushed(tmp_path, bare, capsys):
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0)])
    assert _push(processed, bare) == store.EXIT_OK
    _clone_and_edit(tmp_path, bare, "captures/2026-10-08.csv",
                    lambda text: text + 'x,"unterminated\n' + "y,z\n")
    damaged_before = _stored(bare)

    other = _round(14, 110.0)
    other["captured_at"] = "2026-10-09T14:00:00Z"
    _day_file(processed, [_round(14, 120.0), _round(21, 105.0), other])
    assert _push(processed, bare) == store.EXIT_DAMAGED

    assert _stored(bare) == damaged_before, "the damaged day was overwritten"
    assert _stored(bare, "2026-10-09.csv"), "the good day was not pushed"
    assert "captures/2026-10-08.csv" in capsys.readouterr().out


def test_a_remote_day_that_parses_short_without_an_error_is_damage(tmp_path, bare, capsys):
    """A stray quote folds rows without pandas raising; the count off the
    file is what refuses the merge, so no remote row is lost."""
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0), _round(21, 105.0, "FanDuel")])
    assert _push(processed, bare) == store.EXIT_OK

    def fold(text: str) -> str:
        lines = text.splitlines()
        lines[1] = lines[1].replace("Toronto Maple Leafs", '"Toronto Maple Leafs')
        lines[2] = lines[2].replace("Toronto Maple Leafs", 'Toronto Maple Leafs"')
        return "\n".join(lines) + "\n"

    tip = _clone_and_edit(tmp_path, bare, "captures/2026-10-08.csv", fold)
    folded = pd.read_csv(pd.io.common.StringIO(_stored(bare)))
    assert len(folded) < 2, "the fixture must fold without an error"

    _day_file(processed, [_round(14, 120.0), _round(21, 105.0, "FanDuel"), _round(23, 150.0)])
    assert _push(processed, bare) == store.EXIT_DAMAGED
    assert _tip(bare) == tip
    # This damage carries no path of its own; the day is named by the key.
    assert "captures/2026-10-08.csv could not be used" in capsys.readouterr().out


def test_a_duplicated_remote_row_does_not_swallow_a_new_capture(tmp_path, bare):
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0)])
    assert _push(processed, bare) == store.EXIT_OK
    _clone_and_edit(tmp_path, bare, "captures/2026-10-08.csv",
                    lambda text: text + text.splitlines()[1] + "\n")

    _day_file(processed, [_round(14, 120.0), _round(21, 105.0)])
    assert _push(processed, bare) == store.EXIT_OK

    stored = pd.read_csv(pd.io.common.StringIO(_stored(bare)))
    assert sorted(stored["captured_at"]) == ["2026-10-08T14:00:00Z", "2026-10-08T21:00:00Z"]


def test_a_dispatched_capture_is_pushed_whole(tmp_path, bare):
    """The dispatch path: capture_closing_lines.py writes the dedicated
    store's file through append_captures, and the push takes all of it."""
    processed = tmp_path / "run"
    processed.mkdir()
    cl.append_captures(cl.best_prices(_round(22, 130.0, "Caesars"),
                                      captured_at="2026-10-08T22:00:00Z"), processed_dir=processed)
    cl.append_captures(cl.best_prices(_round(22, 125.0, "Bet365"),
                                      captured_at="2026-10-09T01:00:00Z"), processed_dir=processed)

    assert _push(processed, bare) == store.EXIT_OK

    first = pd.read_csv(pd.io.common.StringIO(_stored(bare, "2026-10-08.csv")))
    second = pd.read_csv(pd.io.common.StringIO(_stored(bare, "2026-10-09.csv")))
    assert first[["american_odds", "book"]].values.tolist() == [[130.0, "Caesars"]]
    assert second[["american_odds", "book"]].values.tolist() == [[125.0, "Bet365"]]


def test_a_damaged_dispatched_capture_is_named_and_pushes_nothing(tmp_path, bare, capsys):
    """A paid capture that parses short is damage, never a quiet no-op."""
    processed = tmp_path / "run"
    processed.mkdir()
    for hour, odds in ((21, 130.0), (22, 125.0)):
        cl.append_captures(cl.best_prices(_round(hour, odds), captured_at=f"2026-10-08T{hour}:00:00Z"),
                           processed_dir=processed)
    path = processed / cl.CAPTURES_FILENAME
    lines = path.read_text().splitlines()
    lines[1] = lines[1].replace("Toronto Maple Leafs", '"Toronto Maple Leafs')
    lines[2] = lines[2].replace("Toronto Maple Leafs", 'Toronto Maple Leafs"')
    path.write_text("\n".join(lines) + "\n")
    before = _tip(bare)

    assert _push(processed, bare) == store.EXIT_DAMAGED
    assert cl.CAPTURES_FILENAME in capsys.readouterr().out
    assert _tip(bare) == before


def test_a_store_without_main_is_refused_on_push_and_empty_on_pull(tmp_path, bare):
    empty = tmp_path / "empty.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(empty)], check=True)
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0)])

    assert store.main(["push", "--processed-dir", str(processed),
                       "--remote", f"file://{empty}"]) == store.EXIT_REFUSED
    out = tmp_path / "out" / cl.CAPTURES_FILENAME
    assert store.main(["pull", "--out", str(out), "--remote", f"file://{empty}"]) == store.EXIT_EMPTY
    assert not out.exists()


def test_a_damaged_movement_day_is_named_and_the_good_days_still_pushed(tmp_path, bare, capsys):
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0)])
    (processed / cl.MOVEMENT_DIRNAME / "2026-10-07.csv").write_text("")

    assert _push(processed, bare) == store.EXIT_DAMAGED
    assert "2026-10-07.csv" in capsys.readouterr().out
    assert _stored(bare)


def test_the_store_format_is_the_one_clv_reads(tmp_path, bare):
    """What the push writes and the pull joins is what `load_captures` reads."""
    processed = tmp_path / "run"
    _day_file(processed, [_round(14, 120.0), _round(21, 105.0)])
    assert _push(processed, bare) == store.EXIT_OK
    out = tmp_path / "pulled" / cl.CAPTURES_FILENAME
    assert store.main(["pull", "--out", str(out), "--remote", f"file://{bare}"]) == store.EXIT_OK
    loaded = cl.load_captures(out.parent)
    # What the dedicated store would hold for the same rounds: the movement
    # rows through `best_prices`, written to and read from a CSV, as every
    # store is (an empty player or line is NaN once read, in either).
    expected_path = tmp_path / "expected" / cl.CAPTURES_FILENAME
    expected_path.parent.mkdir()
    cl.load_movement_captures(processed).to_csv(expected_path, index=False)
    expected = cl.load_captures(expected_path.parent)
    assert list(loaded.columns) == list(cl.CAPTURE_COLUMNS)

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.sort_values("captured_at").reset_index(drop=True)

    pd.testing.assert_frame_equal(ordered(loaded), ordered(expected))
