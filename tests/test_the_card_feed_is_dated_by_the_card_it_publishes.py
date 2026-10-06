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
* both of those are league days in America/New_York, under a clock that
  honours the time zone it is asked in: a run that starts at 23:50 ET, when
  the UTC date has already rolled over, notes the ET day, and with no card
  the status carries that day and not the publish clock's; with a card, the
  card's day wins over the run's;
* the precheck stands a run down only for a status whose `card_day` is
  today, so a status published after midnight for the previous slate, a
  status with no card, and a status written before this fix (no
  `card_day`) all let the day's run go ahead. The last costs at most one
  duplicate run on the day this lands, as the ref check's did.

Every block is the workflow's own `run:`, under `bash -eo pipefail`, with
real git plumbing into a local bare remote and real jq. Only `date` is
stubbed: asked for "now" it answers the publish clock; asked to convert an
instant (`-d`) it is the real `date`, where that is GNU's as on a runner.
macOS's has no `-d`, so there a stand-in answers the forms the steps use,
held to GNU's answers by test_the_stand_in_answers_as_gnu_date_does.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
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

#: GNU date, for a host whose own has no `-d` (macOS): `[-d INSTANT]
#: +FORMAT` in the TZ the step sets, INSTANT `@SECONDS` or ISO 8601, which
#: is every form the steps here ask for. Anything else is refused, not
#: guessed at.
GNU_DATE_STAND_IN = r'''#!{python}
import sys
from datetime import datetime, timezone

args = sys.argv[1:]
when = datetime.now(timezone.utc)
form = "%a %b %d %H:%M:%S %Z %Y"
while args:
    arg = args.pop(0)
    if arg in ("-d", "--date") or arg.startswith("--date="):
        text = arg.partition("=")[2] if arg.startswith("--date=") else args.pop(0)
        try:
            when = (datetime.fromtimestamp(int(text[1:]), timezone.utc) if text.startswith("@")
                    else datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            sys.exit(f"date: invalid date '{{text}}'")
    elif arg.startswith("+"):
        form = arg[1:]
    else:
        sys.exit(f"date stand-in: {{arg!r}} is not modelled")
# astimezone() reads the zone from TZ, as GNU date does, and takes an
# instant with no offset as local time there.
local = when.astimezone()
print(local.strftime(form.replace("%F", "%Y-%m-%d").replace("%s", str(int(local.timestamp())))))
'''


def _is_gnu(date: str | None) -> bool:
    if not date:
        return False
    probe = subprocess.run([date, "-u", "-d", "@0", "+%F"],
                           capture_output=True, text=True, timeout=30)
    return probe.returncode == 0 and probe.stdout.strip() == "1970-01-01"


GNU_DATE = _is_gnu(REAL_DATE)


def _stand_in(directory: Path) -> Path:
    path = directory / "gnu-date-stand-in"
    path.write_text(GNU_DATE_STAND_IN.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _converter(bin_dir: Path) -> str:
    """The `date` that converts instants: the real one where it is GNU's,
    the stand-in beside the stub where it is not."""
    return str(REAL_DATE) if GNU_DATE else str(_stand_in(bin_dir))


def _env(tmp_path: Path, clock: str) -> dict:
    """`_git_env`, with a `date` that converts instants for real and answers
    `clock` for "now"."""
    assert REAL_DATE, "the publish step converts the card's instant with date"
    env = _git_env(tmp_path, clock)
    stub = Path(env["PATH"].split(":", 1)[0]) / "date"
    converter = _converter(stub.parent)
    stub.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in -d|--date|--date=*) exec ' + converter + ' "$@";; esac\n'
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


# --------------------------------------------------------------------------
# The same, under a clock that honours TZ. The stub above answers one date
# whatever time zone it is asked in, so it cannot tell the league day from
# the UTC date, nor the run-day file from the publish clock when both would
# be read in the same zone.
# --------------------------------------------------------------------------

#: 23:50 ET on D, 03:50 UTC on D+1: a late dispatch starts.
RUN_STARTS = "2026-10-15T03:50:00Z"
#: 00:05 ET on D+1: the same run publishes.
RUN_PUBLISHES = "2026-10-15T04:05:00Z"


def _clock_env(tmp_path: Path, instant: str) -> dict:
    """`_git_env`, with a `date` whose "now" is `instant`, rendered by the
    real `date` in whatever TZ the caller sets. Asked to convert an instant
    (`-d`), it is the real `date` as it stands."""
    assert REAL_DATE, "the steps read the clock with date"
    epoch = int(datetime.fromisoformat(instant.replace("Z", "+00:00")).timestamp())
    env = _git_env(tmp_path, "unused")
    stub = Path(env["PATH"].split(":", 1)[0]) / "date"
    converter = _converter(stub.parent)
    stub.write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in -d|--date|--date=*) exec ' + converter + ' "$@";; esac\n'
        "done\n"
        f'exec {converter} -d @{epoch} "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return env


def _publish_at(work: Path, tmp_path: Path, instant: str, degraded: str) -> dict:
    env = _clock_env(tmp_path, instant)
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


def _note_run_day(work: Path, tmp_path: Path, instant: str) -> str:
    result = _bash(_run_day_step()["run"], work, _clock_env(tmp_path, instant))
    assert result.returncode == 0, result.stderr
    return (work / "run_league_day.txt").read_text(encoding="utf-8").strip()


def test_the_clock_stub_honours_the_time_zone(tmp_path: Path) -> None:
    """The control for the tests below: the same instant is D in New York
    and D+1 in UTC."""
    env = _clock_env(tmp_path, RUN_STARTS)
    new_york = _bash("TZ=America/New_York date +%F", tmp_path, env)
    utc = _bash("TZ=UTC date +%F", tmp_path, env)
    assert (new_york.stdout.strip(), utc.stdout.strip()) == (CARD_DAY, NEXT_DAY)


@pytest.mark.parametrize("command, answer", [
    (f"TZ=America/New_York date -d {LATE_CARD} +%F", CARD_DAY),
    (f"TZ=America/New_York date -d {MORNING_CARD} +%F", NEXT_DAY),
    (f"TZ=UTC date -d {LATE_CARD} +%F", NEXT_DAY),
    (f"TZ=America/New_York date -d {RUN_STARTS} +%F", CARD_DAY),
    (f"TZ=America/New_York date --date={RUN_PUBLISHES} +%F", NEXT_DAY),
    ("TZ=America/New_York date -d @1792036200 +%F", CARD_DAY),
    (f"TZ=UTC date -d {RUN_STARTS} +%s", "1792036200"),
])
def test_the_stand_in_answers_as_gnu_date_does(tmp_path: Path, command: str, answer: str) -> None:
    """Every form the steps ask `date` for, with the answer GNU date gives:
    the stand-in on every host, and the real date too where it is GNU's, so
    a runner holds the stand-in to it."""
    stand_in = tmp_path / "stand-in"
    stand_in.mkdir()
    _stand_in(stand_in).rename(stand_in / "date")
    dates = {"stand-in": f"{stand_in}:{os.environ['PATH']}"}
    if GNU_DATE:
        dates["real"] = os.environ["PATH"]
    for which, path in dates.items():
        ran = subprocess.run(["bash", "--noprofile", "--norc", "-c", command],
                             env={**os.environ, "PATH": path},
                             capture_output=True, text=True, timeout=30)
        assert (ran.returncode, ran.stdout.strip()) == (0, answer), (which, ran.stderr)


def test_a_run_starting_at_2350_et_notes_the_league_day_not_the_utc_date(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()

    assert _note_run_day(work, tmp_path, RUN_STARTS) == CARD_DAY


def test_with_no_card_a_run_that_started_before_midnight_keeps_its_start_day(
    tmp_path: Path,
) -> None:
    """The card step crashed on a run that started at 23:50 ET on D and
    publishes at 00:05 ET on D+1. The run's own day is D; the clock at
    publish says D+1, and a status dated D+1 would read as that day's."""
    work = _workspace(tmp_path, None)
    assert _note_run_day(work, tmp_path, RUN_STARTS) == CARD_DAY

    status = _publish_at(work, tmp_path, RUN_PUBLISHES, degraded="true")

    assert status["date"] == CARD_DAY, status
    assert status["card_day"] == "", status


def test_a_card_on_disk_outranks_the_day_the_run_started(tmp_path: Path) -> None:
    """The run started at 23:50 ET on D and its card was built at 00:02 ET
    on D+1, for D+1's slate. The status is the card's: the run-day file is
    the fallback for no card, never a rival to one."""
    work = _workspace(tmp_path, "2026-10-15T04:02:00+00:00")
    assert _note_run_day(work, tmp_path, RUN_STARTS) == CARD_DAY

    status = _publish_at(work, tmp_path, RUN_PUBLISHES, degraded="false")

    assert status["date"] == NEXT_DAY, status
    assert status["card_day"] == NEXT_DAY, status
