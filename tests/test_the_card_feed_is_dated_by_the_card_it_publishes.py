"""Card-feed's status was dated by the clock at publish, not by the card.

"Publish the card to the card-feed branch" worked out its date with
`TZ=America/New_York date +%F` when it ran. It runs last: after the card,
the settlement, the closing-line report, a state upload of about 30 MB and
the post. So a Gameday Refresh dispatched on main late on league day D could
build its card at 23:56 ET on D and publish it at 00:03 ET on D+1, stamped
`{date: D+1, degraded: false, ref: refs/heads/main}`. A card built that late
is usually a benign block (every game of D has faced off), so it is clean.

At 13:30 UTC on D+1 the scheduled precheck found "today's" status, clean,
from the default branch, printed "already published and clean. Skipping."
and stood the whole refresh down. The 15:00 backup read the same line and
skipped too. D+1 got no card, no post and no frozen snapshot, and that
day's opinions never reached the forward ledger. Both runs were green.
(Sweep 4, cardfeed-status-date-is-publish-wall-clock.)

What these tests hold:

* the status is dated by the league day the card on disk was built for,
  which is its `generated_at` in America/New_York, and records that day as
  `card_day`;
* with no card on disk, the date is the league day the run started on
  (written once, right after the checkout), never the clock at publish;
* the precheck stands a run down only for a status whose `card_day` is
  today, so a status published after midnight for the previous slate, a
  status with no card, and a status written before this fix (no
  `card_day`) all let the day's run go ahead. The last costs at most one
  duplicate run on the day this lands, as the ref check's did.

Every block is the workflow's own `run:`, under `bash -eo pipefail`, with
real git plumbing into a local bare remote and real jq. Only `date` is
stubbed: asked for "now" it answers the publish clock; asked to convert an
instant (`-d`) it is the real `date`.
"""
from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from test_a_blocked_card_is_a_degraded_run import (
    _bash,
    _git_env,
    _outputs,
    _render,
    _step,
)

MAIN = "refs/heads/main"
#: League day D and the next one.
CARD_DAY = "2026-10-14"
NEXT_DAY = "2026-10-15"
#: 23:56 ET on D: the card the late dispatch built.
LATE_CARD = "2026-10-15T03:56:00+00:00"
#: 09:40 ET on D+1: a card the morning run built.
MORNING_CARD = "2026-10-15T13:40:00+00:00"

REAL_DATE = shutil.which("date")


def _env(tmp_path: Path, clock: str) -> dict:
    """`_git_env`, with a `date` that converts instants for real and answers
    `clock` for "now"."""
    assert REAL_DATE, "the publish step converts the card's instant with date"
    env = _git_env(tmp_path, clock)
    stub = Path(env["PATH"].split(":", 1)[0]) / "date"
    stub.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in -d|--date|--date=*) exec ' + REAL_DATE + ' "$@";; esac\n'
        "done\n"
        f"echo {clock}\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return env


def _workspace(tmp_path: Path, generated_at: str | None) -> Path:
    work = tmp_path / "work"
    (work / "data" / "outputs").mkdir(parents=True)
    (work / "card_comment.md").write_text("card\n", encoding="utf-8")
    if generated_at is not None:
        (work / "data" / "outputs" / "gameday_card.json").write_text(
            json.dumps({
                "generated_at": generated_at,
                "card_generated": False,
                "nothing_to_card": "no regular-season game is left to card today",
            }),
            encoding="utf-8",
        )
    return work


def _publish(work: Path, tmp_path: Path, clock: str, degraded: str = "false") -> dict:
    env = _env(tmp_path, clock)
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    block = _render(_step(name="Publish the card to the card-feed branch")["run"], {
        "github.repository": "o/r",
        "github.server_url": "https://github.com",
        "github.run_id": "1",
        "github.ref": MAIN,
        "steps.post.outputs.decision || 'none'": "skip",
        "steps.final.outputs.degraded || 'unknown'": degraded,
        "steps.prices.outputs.empty_slate || 'false'": "false",
    })
    result = _bash(block, work, env)
    assert result.returncode == 0, result.stderr
    shown = subprocess.run(
        ["git", "--git-dir", str(tmp_path / "remote.git"), "show",
         "card-feed:latest_status.json"],
        env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(shown.stdout)


def _precheck(tmp_path: Path, clock: str) -> tuple[str, str]:
    env = _env(tmp_path, clock)
    checkout = tmp_path / f"precheck-{clock}"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=checkout, env=env, check=True)
    output = tmp_path / f"precheck-{clock}.out"
    output.write_text("", encoding="utf-8")
    block = _render(_step(id_="feed")["run"], {
        "github.event_name": "schedule", "github.repository": "o/r",
        "github.ref": MAIN,
    })
    result = _bash(block, checkout, {**env, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    return _outputs(output)["already"], result.stdout


def _push_status(tmp_path: Path, status: dict) -> None:
    """Write card-feed the way an older copy of the workflow would have."""
    env = _env(tmp_path, NEXT_DAY)
    work = tmp_path / "old"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    (work / "s.json").write_text(json.dumps(status), encoding="utf-8")
    block = (
        'BLOB=$(git hash-object -w s.json)\n'
        'TREE=$(printf "100644 blob %s\\tlatest_status.json\\n" "$BLOB" | git mktree)\n'
        'export GIT_AUTHOR_NAME=a GIT_AUTHOR_EMAIL=a@b GIT_COMMITTER_NAME=a GIT_COMMITTER_EMAIL=a@b\n'
        'COMMIT=$(git commit-tree "$TREE" -m old)\n'
        'git push "https://x-access-token:x@github.com/o/r" "$COMMIT:refs/heads/card-feed"\n'
    )
    result = _bash(block, work, env)
    assert result.returncode == 0, result.stderr


def _run_day_step() -> dict:
    return _step(name="Note the league day this run is for")


# --------------------------------------------------------------------------
# The defect: a card built before midnight, published after it.
# --------------------------------------------------------------------------

def test_a_card_published_after_midnight_is_dated_by_the_day_it_was_built_for(
    tmp_path: Path,
) -> None:
    status = _publish(_workspace(tmp_path, LATE_CARD), tmp_path, NEXT_DAY)

    assert status["date"] == CARD_DAY, status
    assert status["card_day"] == CARD_DAY, status
    assert status["degraded"] == "false" and status["ref"] == MAIN


def test_it_does_not_stand_the_next_day_down(tmp_path: Path) -> None:
    _publish(_workspace(tmp_path, LATE_CARD), tmp_path, NEXT_DAY)

    already, stdout = _precheck(tmp_path, NEXT_DAY)

    assert already == "false", stdout
    assert "Skipping" not in stdout


def test_a_clean_card_built_today_still_stands_the_backup_down(tmp_path: Path) -> None:
    """The control: the precheck exists to save the 15:00 backup's credits
    when the 13:30 run published a clean card for today."""
    status = _publish(_workspace(tmp_path, MORNING_CARD), tmp_path, NEXT_DAY)
    assert status["date"] == NEXT_DAY and status["card_day"] == NEXT_DAY

    already, stdout = _precheck(tmp_path, NEXT_DAY)

    assert already == "true", stdout
    assert f"Today's card ({NEXT_DAY}) is already published and clean." in stdout


# --------------------------------------------------------------------------
# No card on disk: the run's own day, and never a stand-down.
# --------------------------------------------------------------------------

def test_the_run_notes_its_league_day_when_it_starts(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    result = _bash(_run_day_step()["run"], work, _env(tmp_path, CARD_DAY))

    assert result.returncode == 0, result.stderr
    assert (work / "run_league_day.txt").read_text().strip() == CARD_DAY


def test_with_no_card_the_status_is_dated_by_the_day_the_run_started(
    tmp_path: Path,
) -> None:
    """The card step crashed, so nothing on disk says which day it was for.
    The run began on D; the publish clock has already rolled over."""
    work = _workspace(tmp_path, None)
    result = _bash(_run_day_step()["run"], work, _env(tmp_path, CARD_DAY))
    assert result.returncode == 0, result.stderr

    status = _publish(work, tmp_path, NEXT_DAY, degraded="true")

    assert status["date"] == CARD_DAY, status
    assert status["card_day"] == "", status


def test_a_status_with_no_card_never_stands_a_run_down(tmp_path: Path) -> None:
    """Even marked clean, a status that names no card is not a card for
    today."""
    _publish(_workspace(tmp_path, None), tmp_path, NEXT_DAY, degraded="false")

    already, stdout = _precheck(tmp_path, NEXT_DAY)

    assert already == "false", stdout


@pytest.mark.parametrize("status", [
    # Written before this fix: no card_day at all. It cannot say whether it
    # was published after midnight for the previous slate.
    {"date": NEXT_DAY, "degraded": "false", "ref": MAIN},
    # A card built for the previous day, however its date came to read today.
    {"date": NEXT_DAY, "card_day": CARD_DAY, "degraded": "false", "ref": MAIN},
], ids=["before-this-fix", "card-for-yesterday"])
def test_the_precheck_counts_only_a_card_built_for_today(
    tmp_path: Path, status: dict
) -> None:
    _push_status(tmp_path, status)

    already, stdout = _precheck(tmp_path, NEXT_DAY)

    assert already == "false", stdout


def test_the_precheck_reads_the_card_day_it_is_given(tmp_path: Path) -> None:
    """The control for the test above: the same hand-written line with
    today's card_day does stand the backup down, and the ref gate still
    holds beside it."""
    _push_status(tmp_path, {"date": NEXT_DAY, "card_day": NEXT_DAY,
                            "degraded": "false", "ref": MAIN})
    assert _precheck(tmp_path, NEXT_DAY)[0] == "true"


def test_the_ref_gate_still_holds_for_a_card_built_today(tmp_path: Path) -> None:
    _push_status(tmp_path, {"date": NEXT_DAY, "card_day": NEXT_DAY,
                            "degraded": "false",
                            "ref": "refs/heads/fix/some-unreviewed-change"})
    assert _precheck(tmp_path, NEXT_DAY)[0] == "false"
