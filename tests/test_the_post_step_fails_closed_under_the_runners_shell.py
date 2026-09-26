"""The post step failed open under the shell GitHub actually ran it with.

No workflow in this repository set `shell:` or `defaults.run.shell`, so GitHub
ran every `run:` block of Gameday Refresh as `bash -e {0}`: errexit, and no
pipefail. Run 33142173149 (main, 2026-08-28) printed `shell: /usr/bin/bash -e
{0}` 14 times, including under the post step, and pipefail not once. The workflow's own
comments said "the shell is `bash -eo pipefail`", and every test that replays
its steps ran them under `bash --noprofile --norc -eo pipefail`. So the suite
graded a shell production never ran. One refuter rewrote all 275 of the
suite's pipefail bash calls to `bash -e`, and 2504 of 2504 tests still passed.

Found by the failure-shape audit and confirmed by 3/3 refuters, who replayed
the real "Post the card to the operating home" block with only `gh` (and, for
B, the post script) stubbed. It had two consequences:

A. `NUMBER=$(gh issue list … | jq …)` took jq's exit status, and jq on empty
   input prints nothing and exits 0. One HTTP 502 from the listing therefore
   read as "no home issue exists". The step ran `gh issue create --title "NHL
   Betting Lab — Claude Operating Home"`, `gh issue pin 999` and `gh issue
   comment 999`, recorded decision=post and exited 0. gh lists newest first,
   so every later card followed the duplicate: the split that the step's own
   comment says the exact-title match exists to prevent. Under the tests'
   shell the same case exits 1 and records post_failed.
B. `DECISION=$(python scripts/post_card_to_issue.py … | tail -1)` took
   tail's exit status. A post script that crashed before printing a decision
   (TypeError, in the replay) left DECISION empty, and the step printed "Not
   posting: the run was clean and the selections did not change." and exited
   0. Final health added nothing, card-feed recorded decision 'none' with
   degraded=false, and the 15:00 backup's precheck stood down on it. This one
   is latent: it needs the script to crash.

What these tests hold, running the workflow's own blocks:

* every `run:` step of Gameday Refresh runs under the shell the replay tests
  use. The shell is read from the YAML the way GitHub resolves it (step, then
  job `defaults`, then workflow `defaults`, then the runner's `bash -e`), and
  a failure on the left of a pipe fails a block run under it;
* the post step fails closed under EITHER shell: the one the workflow now
  declares, and plain `bash -e`, should the declaration ever go. A failed
  listing is a failed post that creates, pins and comments on nothing. A post
  script that exits non-zero, or ends without `post` or `skip`, is a failed
  post, never "the run was clean";
* the final health turns each of those into a degraded run, so card-feed
  reads degraded=true and the backup runs;
* the ordinary paths still work. A found home is commented on, a missing one
  is created, pinned and commented on once, and a clean skip calls no `gh`.

Not fixed here: the other operational workflows declare no shell either, and
six of them (closing-lines, experiment-refresh, historical-props-purchase,
line-movement, provider-market-discovery, publish-site) have steps that tests
replay under `-eo pipefail` while GitHub runs them under `bash -e`, as of
1b8d58b. The mismatch runs the other way there too: `games=$(find … | wc -l)`
with no `|| true` passes under `bash -e` and would end the step under
pipefail. Each needs its own pipeline audit before it declares a shell.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
HOME_TITLE = "NHL Betting Lab — Claude Operating Home"

#: What GitHub runs a Linux `run:` block with, keyed on the `shell:` that
#: resolves for it (GitHub Actions docs, "jobs.<job_id>.steps[*].shell"). No
#: `shell:` anywhere is `bash -e {0}` — measured in run 33142173149's log —
#: and the bare keyword `bash` is `bash --noprofile --norc -eo pipefail {0}`.
#: A value outside this table is not guessed at; the test that reads it fails.
RUNNER_SHELLS: dict[str | None, tuple[str, ...]] = {
    None: ("bash", "-e"),
    "bash": ("bash", "--noprofile", "--norc", "-eo", "pipefail"),
    "sh": ("sh", "-e"),
}

#: The command line every test that replays a Gameday Refresh step runs it
#: under (tests/test_run_health_covers_the_card_and_the_post.py,
#: test_a_failed_per_event_fetch_is_a_degraded_run.py,
#: test_fetch_fails_loudly_when_the_api_is_down.py,
#: test_state_restores_from_the_run_that_carries_it.py, …).
REPLAY_SHELL = ("bash", "--noprofile", "--norc", "-eo", "pipefail")

#: GitHub's own shell for a block that declares none: the weakest shell the
#: post step could ever be handed.
BARE_RUNNER_SHELL = RUNNER_SHELLS[None]


def _document() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _declared_shell(document: dict, job: dict, step: dict) -> str | None:
    """The `shell:` GitHub resolves for a step: its own, else the job's
    `defaults.run.shell`, else the workflow's, else none."""
    if "shell" in step:
        return step["shell"]
    for scope in (job, document):
        run_defaults = (scope.get("defaults") or {}).get("run") or {}
        if "shell" in run_defaults:
            return run_defaults["shell"]
    return None


def runner_shell(document: dict, job: dict, step: dict) -> tuple[str, ...]:
    declared = _declared_shell(document, job, step)
    assert declared in RUNNER_SHELLS, (
        f"step {step.get('name') or step.get('id')!r} declares `shell: {declared!r}`, "
        "which this file does not know how GitHub runs"
    )
    return RUNNER_SHELLS[declared]


def _run_steps() -> list[tuple[str, dict, dict]]:
    document = _document()
    return [
        (job_id, job, step)
        for job_id, job in document["jobs"].items()
        for step in job.get("steps", [])
        if "run" in step
    ]


def _post_step() -> tuple[tuple[str, ...], str]:
    document = _document()
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "post":
                return runner_shell(document, job, step), step["run"]
    raise AssertionError("no step posts the card")


def _final_step() -> tuple[tuple[str, ...], str]:
    document = _document()
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "final":
                return runner_shell(document, job, step), step["run"]
    raise AssertionError("no step records the final health")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _outputs(path: Path) -> dict[str, str]:
    """GITHUB_OUTPUT as the runner reads it: the last value of a key wins."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        found[key] = value
    return found


def _executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


# --------------------------------------------------------------------------
# The shell production runs is the shell the replays run.
# --------------------------------------------------------------------------

def test_every_gameday_step_runs_under_the_shell_its_replays_use() -> None:
    steps = _run_steps()
    assert steps, "no `run:` step in Gameday Refresh"
    document = _document()
    resolved = {
        f"{job_id}: {step.get('name') or step.get('id')}": runner_shell(document, job, step)
        for job_id, job, step in steps
    }

    assert {name: argv for name, argv in resolved.items() if argv != REPLAY_SHELL} == {}


def test_a_failure_on_the_left_of_a_pipe_fails_a_gameday_step() -> None:
    """Executed, not read: each distinct shell the steps resolve to is handed
    `false | true` and must not reach the next line."""
    document = _document()
    shells = {runner_shell(document, job, step) for _, job, step in _run_steps()}
    assert shells

    for argv in shells:
        result = subprocess.run([*argv, "-c", "false | true; echo reached"],
                                capture_output=True, text=True)
        assert result.returncode != 0 and "reached" not in result.stdout, argv


# --------------------------------------------------------------------------
# The post step, replayed under the declared shell and under bare `bash -e`.
# --------------------------------------------------------------------------

def _shells() -> list[tuple[str, ...]]:
    declared, _ = _post_step()
    return [declared, BARE_RUNNER_SHELL]


SHELLS = pytest.mark.parametrize("which", ["declared", "bare-runner"])


def _shell(which: str) -> tuple[str, ...]:
    return dict(zip(["declared", "bare-runner"], _shells()))[which]


def _post(
    tmp_path: Path, which: str, *, python: str, gh_list: str,
    empty_slate: str = "false",
) -> tuple[subprocess.CompletedProcess, dict[str, str], list[str]]:
    """Run the post step's own block with `python` and `gh` standing in.
    Returns the result, the step's outputs and every `gh` call made."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "gh_calls.log"
    calls.write_text("", encoding="utf-8")
    _executable(bin_dir / "python", python)
    _executable(
        bin_dir / "gh",
        "#!/bin/sh\n"
        f'echo "gh $*" >> "{calls}"\n'
        'case "$1 $2" in\n'
        f"  \"issue list\") {gh_list};;\n"
        '  "issue create") echo "https://github.com/o/r/issues/999";;\n'
        '  "issue pin") exit 0;;\n'
        '  "issue comment") exit 0;;\n'
        "  *) exit 3;;\n"
        "esac\n",
    )
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    _, block = _post_step()
    block = _render(block, {
        "github.server_url": "https://github.com", "github.repository": "o/r",
        "github.run_id": "1", "steps.prices.outputs.empty_slate": empty_slate,
        "inputs.force_post == true && '--force' || ''": "",
    })
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "GITHUB_OUTPUT": str(output), "GH_TOKEN": "x"}

    result = subprocess.run([*_shell(which), "-c", block], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    made = calls.read_text(encoding="utf-8").splitlines()
    return result, _outputs(output), made


def _final_health(tmp_path: Path, post: subprocess.CompletedProcess,
                  earlier: str = "") -> tuple[str, str]:
    """The next step, fed the post step's outcome as the runner records it
    under `continue-on-error`. Returns `degraded` and the notes."""
    notes = tmp_path / "run_degraded.txt"
    notes.write_text(earlier, encoding="utf-8")
    output = tmp_path / "final_output"
    output.write_text("", encoding="utf-8")
    argv, block = _final_step()
    outcome = "success" if post.returncode == 0 else "failure"
    result = subprocess.run(
        [*argv, "-c", _render(block, {"steps.post.outcome": outcome})],
        cwd=tmp_path, env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return _outputs(output)["degraded"], notes.read_text(encoding="utf-8")


def _decides(*lines: str, code: int = 0) -> str:
    """A post script that writes the title, as the real one does, prints
    `lines` and exits `code`."""
    printed = "".join(f"echo {line!r}\n" for line in lines)
    return (
        "#!/bin/sh\n"
        f"printf '%s' '{HOME_TITLE}' > card_title.txt\n"
        f"{printed}"
        f"exit {code}\n"
    )


LISTS_HOME = f"echo '[{{\"number\": 7, \"title\": \"{HOME_TITLE}\"}}]'"
LISTS_NOTHING = "echo '[]'"
LIST_FAILS = "echo 'HTTP 502: Bad Gateway (https://api.github.com/graphql)' >&2; exit 1"


@SHELLS
def test_a_failed_listing_is_a_failed_post_that_opens_no_second_home(
    tmp_path: Path, which: str
) -> None:
    """A: one HTTP 502 from `gh issue list` on a run that has a card to post."""
    result, outputs, made = _post(
        tmp_path, which,
        python=_decides("The selections differ.", "post"), gh_list=LIST_FAILS,
    )

    assert result.returncode != 0, (result.stdout, made)
    assert outputs.get("decision") == "post_failed"
    assert made == ["gh issue list --state open --limit 200 --json number,title"], (
        "a listing that failed was read as 'no home issue exists'"
    )
    degraded, notes = _final_health(tmp_path, result)
    assert degraded == "true" and "could not be posted" in notes


@SHELLS
@pytest.mark.parametrize(
    ("printed", "code"),
    [((), 1), (("skip",), 1), (("post",), 1), ((), 0), (("The selections differ.",), 0)],
    ids=["crashed-before-deciding", "crashed-after-skip", "crashed-after-post",
         "exited-0-with-nothing", "exited-0-without-a-decision"],
)
def test_a_post_script_that_fails_or_decides_nothing_is_a_failed_post(
    tmp_path: Path, which: str, printed: tuple[str, ...], code: int
) -> None:
    """B: the decision is the script's last line only when the script
    succeeded, and only when that line is `post` or `skip`."""
    result, outputs, made = _post(
        tmp_path, which, python=_decides(*printed, code=code), gh_list=LISTS_HOME,
    )

    assert result.returncode != 0, result.stdout
    assert "the run was clean" not in result.stdout
    assert outputs.get("decision") not in {"post", "skip"}
    assert made == [], "a post script that failed or decided nothing was acted on"
    degraded, notes = _final_health(tmp_path, result)
    assert degraded == "true" and "could not be posted" in notes


# --------------------------------------------------------------------------
# The ordinary paths, so failing closed is not failing always.
# --------------------------------------------------------------------------

@SHELLS
def test_a_found_home_is_commented_on(tmp_path: Path, which: str) -> None:
    result, outputs, made = _post(
        tmp_path, which, python=_decides("The selections differ.", "post"),
        gh_list=LISTS_HOME,
    )

    assert result.returncode == 0, result.stderr
    assert outputs.get("decision") == "post"
    assert made[1:] == ["gh issue comment 7 --body-file card_comment.md"]
    degraded, _ = _final_health(tmp_path, result)
    assert degraded == "false"


@SHELLS
def test_a_missing_home_is_created_pinned_and_commented_on_once(
    tmp_path: Path, which: str
) -> None:
    result, outputs, made = _post(
        tmp_path, which, python=_decides("The selections differ.", "post"),
        gh_list=LISTS_NOTHING,
    )

    assert result.returncode == 0, result.stderr
    assert outputs.get("decision") == "post"
    assert made[1:] == [
        f"gh issue create --title {HOME_TITLE} --body-file issue_body.md",
        "gh issue pin 999",
        "gh issue comment 999 --body-file card_comment.md",
    ]


@SHELLS
def test_a_clean_skip_stays_quiet(tmp_path: Path, which: str) -> None:
    result, outputs, made = _post(
        tmp_path, which, python=_decides("Nothing changed.", "skip"), gh_list=LISTS_HOME,
    )

    assert result.returncode == 0, result.stderr
    assert outputs.get("decision") == "skip"
    assert "the run was clean" in result.stdout
    assert made == []
    degraded, _ = _final_health(tmp_path, result)
    assert degraded == "false"
