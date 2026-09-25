"""A run's health was decided before the card existed, and before it was posted.

"Record what went wrong" runs before "Render the card", and the card-feed
status and the run's exit read only it. So:

* A card step that crashed left yesterday's card on disk — the restore
  copied it rather than moving it — and the post and card-feed steps
  published that card as today's with `degraded: false`; the 15:00 backup
  then read a clean card for today and stood down.
* The post step wrote `decision=post` before `gh issue comment` ran, so a
  comment that failed still published "post" and a clean status, and the
  run finished green with no one told.

Found by the failure-shape audit (#7: 2/2 refuters; #11: 2/3). And the health
step itself counted boxscores with `$(find ... | wc -l)`, which under the
runner's `bash -eo pipefail` ends the step when the cache directory is
missing — before `degraded` is written at all.

These tests run the steps themselves, from the workflow file, under
`bash -eo pipefail` with stub commands, and the post script directly.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.reports.card_notification import SELECTIONS_CHANGED_MARKER


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in document["jobs"].values():
        steps = job.get("steps", [])
        if any(step.get("id") == "card" for step in steps):
            return steps
    raise AssertionError("no job renders the card")


def _step(*, name: str = "", id_: str = "") -> dict:
    for step in _steps():
        if (name and step.get("name") == name) or (id_ and step.get("id") == id_):
            return step
    raise AssertionError(f"no step {name or id_}")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _bash(block: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env or dict(os.environ), capture_output=True, text=True,
    )


def _outputs(path: Path) -> dict[str, str]:
    """GITHUB_OUTPUT as the runner reads it: the last value of a key wins."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        found[key] = value
    return found


# --------------------------------------------------------------------------
# The card's outcome and the delivery's reach the run's health.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(("outcome", "noted"), [("failure", True), ("success", False)])
def test_a_crashed_card_is_recorded(tmp_path: Path, outcome: str, noted: bool) -> None:
    (tmp_path / "run_degraded.txt").write_text("", encoding="utf-8")
    block = _render(_step(name="Record whether the card was built")["run"],
                    {"steps.card.outcome": outcome})

    result = _bash(block, tmp_path)
    notes = (tmp_path / "run_degraded.txt").read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert ("could not be rendered" in notes) is noted


@pytest.mark.parametrize(
    ("post", "earlier", "degraded"),
    [("failure", "", "true"), ("success", "", "false"),
     ("success", "The card could not be rendered.\n", "true")],
)
def test_the_final_health_covers_the_delivery(
    tmp_path: Path, post: str, earlier: str, degraded: str
) -> None:
    (tmp_path / "run_degraded.txt").write_text(earlier, encoding="utf-8")
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    block = _render(_step(id_="final")["run"], {"steps.post.outcome": post})

    result = _bash(block, tmp_path, {**os.environ, "GITHUB_OUTPUT": str(output)})

    assert result.returncode == 0, result.stderr
    assert _outputs(output)["degraded"] == degraded


def test_the_status_and_the_exit_read_the_final_health() -> None:
    names = [step.get("name") for step in _steps()]
    order = [
        "Render the card", "Record whether the card was built",
        "Post the card to the operating home", "Record whether the card was delivered",
        "Publish the card to the card-feed branch", "Report the outcome",
    ]
    assert [names.index(n) for n in order] == sorted(names.index(n) for n in order)
    publish = _step(name="Publish the card to the card-feed branch")["run"]
    report = _step(name="Report the outcome")["run"]
    assert "steps.final.outputs.degraded" in publish
    assert "steps.health.outputs.degraded" not in publish + report
    # A health that was never recorded fails the run, never passes it.
    assert '"${{ steps.final.outputs.degraded }}" != "false"' in report


# --------------------------------------------------------------------------
# Yesterday's card never stands in for today's.
# --------------------------------------------------------------------------

def test_the_restore_moves_yesterdays_card_aside(tmp_path: Path) -> None:
    state = tmp_path / "artifact" / "outputs"
    state.mkdir(parents=True)
    (state / "gameday_card.json").write_text('{"day": "yesterday"}', encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    helper = bin_dir / "python"
    # The restore step calls `python scripts/restore_state.py`; stand in for
    # it with a copy of what it would restore, so this test is the step's.
    helper.write_text(
        "#!/bin/sh\n"
        f'mkdir -p data && cp -R "{tmp_path / "artifact"}/." data/\n',
        encoding="utf-8",
    )
    git = bin_dir / "git"
    git.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    for tool in (helper, git):
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    work = tmp_path / "work"
    work.mkdir()
    block = _step(id_="restore")["run"].replace(
        "${{ github.repository }}", "owner/nhl-betting-lab"
    )
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "GH_TOKEN": "x"}

    result = _bash(block, work, env)

    assert result.returncode == 0, result.stderr
    assert (work / "previous_card.json").read_text() == '{"day": "yesterday"}'
    assert not (work / "data" / "outputs" / "gameday_card.json").exists(), (
        "yesterday's card was left where today's card is read from"
    )


def test_the_health_step_records_a_run_with_no_cache_at_all(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    block = _render(_step(id_="health")["run"], {
        "steps.results.outcome": "success", "steps.prices.outputs.empty_slate": "false",
        "steps.prices.outcome": "success",
    })

    result = _bash(block, tmp_path, {**os.environ, "GITHUB_OUTPUT": str(output)})

    assert result.returncode == 0, result.stderr
    assert _outputs(output)["degraded"] == "true"


# --------------------------------------------------------------------------
# The post script and the post step.
# --------------------------------------------------------------------------

def _post_script(tmp_path: Path, notes: str) -> tuple[str, Path]:
    degraded = tmp_path / "run_degraded.txt"
    degraded.write_text(notes, encoding="utf-8")
    comment = tmp_path / "comment.md"
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "post_card_to_issue.py"),
         "--card-json", str(tmp_path / "absent.json"),
         "--degraded-file", str(degraded), "--out", str(comment),
         "--title-out", str(tmp_path / "title.txt"),
         "--body-out", str(tmp_path / "body.md")],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1], comment


def test_a_degraded_run_with_no_card_posts_that(tmp_path: Path) -> None:
    decision, comment = _post_script(
        tmp_path, "The card could not be rendered, so there is no card for today.\n"
    )
    body = comment.read_text(encoding="utf-8")

    assert decision == "post"
    assert "No card could be built" in body and "could not be rendered" in body
    assert SELECTIONS_CHANGED_MARKER not in body, "no selections exist to have changed"


def test_a_clean_run_with_no_card_stays_quiet(tmp_path: Path) -> None:
    decision, comment = _post_script(tmp_path, "")

    assert decision == "skip" and not comment.exists()


@pytest.mark.parametrize(("comment_exit", "decision", "step_exit_ok"),
                         [(1, "post_failed", False), (0, "post", True)])
def test_post_is_recorded_only_once_the_comment_is_delivered(
    tmp_path: Path, comment_exit: int, decision: str, step_exit_ok: bool
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shims = {
        "python": "#!/bin/sh\n"
                  'printf "NHL Betting Lab — Claude Operating Home" > card_title.txt\n'
                  'echo "The selections differ." ; echo post\n',
        "gh": "#!/bin/sh\n"
              'case "$1 $2" in\n'
              f'  "issue list") echo \'[{{"number": 7, "title": "NHL Betting Lab — Claude Operating Home"}}]\';;\n'
              f'  "issue comment") exit {comment_exit};;\n'
              "  *) exit 3;;\n"
              "esac\n",
    }
    for name, text in shims.items():
        path = bin_dir / name
        path.write_text(text, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    output = tmp_path / "output"
    output.write_text("", encoding="utf-8")
    block = _render(_step(id_="post")["run"], {
        "github.server_url": "https://github.com", "github.repository": "o/r",
        "github.run_id": "1", "steps.prices.outputs.empty_slate": "false",
        "inputs.force_post == true && '--force' || ''": "",
    })
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "GITHUB_OUTPUT": str(output), "GH_TOKEN": "x"}

    result = _bash(block, tmp_path, env)

    assert (result.returncode == 0) is step_exit_ok, result.stderr
    assert _outputs(output)["decision"] == decision
