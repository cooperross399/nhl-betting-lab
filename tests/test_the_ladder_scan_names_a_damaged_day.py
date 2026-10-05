"""A line-movement day the ladder scan cannot read is named, and the run says so.

`scripts/run_ladder_coherence.py` once read each `line_movement/<day>.csv`
with a bare `pd.read_csv` and `continue`d past an `OSError` or a
`ParserError`, so a damaged day fell out of the scan without a word ("Captures
read: 1" over two captured days, exit 0). An undecodable byte raised out of
the runner and the step's `|| true` turned it into "Ladder scan wrote no
report"; stray quotes parse short with no error; a day missing a ladder column
reached the detector with that column blank. The 2026-10-15 checkpoint in
`docs/pre_registered_ladder_coherence.md` reads the depth this report prints,
so each undercounted it with the step green.

STAGE TWO (2026-10-05). The chain's only home is branch `movement` of the
private repository: "Restore today's captures" pulls it whole (and unseals any
round whose push failed), and "Keep the captures privately" pushes this
round's files back before the scan runs. No public `line-movement` artifact
exists any more, so nothing here reads or names one. The scan and its step
did not change.

What these tests hold, through the real `run_ladder_coherence.main()` and the
Line Movement steps' own `run:` blocks:

* each damaged shape is named in the report, in the JSON and on stderr, and
  the runner exits non-zero; the good day beside it is still read and
  counted; a scan whose only day is damaged never says "Nothing has been
  captured yet";
* the step writes its summary, names the damaged file, and is red only when
  that file is the league day this round appended to; an earlier damaged day
  is a standing warning, every run;
* that split holds on what the restore really delivers: the restore step,
  pulling from a local bare repository that stands in for the private one
  (with an offline `gh` that lists no sealed round), brings a damaged day
  back whole every round, where the scan step reads it;
* the step stays `continue-on-error`, and one gate, placed after the round is
  pushed or sealed and after every upload, turns the run red; it points the
  repair at the repository and branch the push writes, and names no artifact
  the workflow does not upload.

Not held here: a re-run recovering its first attempt's round (from the
private chain, or from the sealed artifact unseal reads) is not a ladder-scan
property, and the push, seal and unseal mechanics are not driven here.

No test reads the real `data/` tree, and none reaches GitHub.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.season import LEAGUE_TIMEZONE

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
RUNNER = PROJECT_ROOT / "scripts" / "run_ladder_coherence.py"

GOOD_DAY = "2026-10-01"
BAD_DAY = "2026-10-02"
ROUNDS = 4
EMPTY_STATE = "Nothing has been captured yet"


def _event(event_id: str, day: str) -> dict:
    """One game, one book, one player with two de-viggable rungs: depth 1."""
    outcomes = [("Over", 2.5, -120), ("Under", 2.5, -110),
                ("Over", 3.5, +300), ("Under", 3.5, -400)]
    return {
        "id": event_id,
        "commence_time": f"{day}T23:00:00Z",
        "home_team": "Home Team",
        "away_team": "Away Team",
        "bookmakers": [{
            "key": "bookone", "title": "BookOne",
            "markets": [{
                "key": "player_shots_on_goal",
                "outcomes": [
                    {"name": side, "description": "A Player", "price": price,
                     "point": line}
                    for side, line, price in outcomes
                ],
            }],
        }],
    }


def _capture_day(processed: Path, day: str, rounds: int) -> Path:
    """Append `rounds` captures the way `capture_line_movement.main` does."""
    capture = load_script("capture_line_movement.py")
    path = capture.capture_path(day, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    for index in range(rounds):
        captured_at = f"{day}T{14 + index:02d}:00:00+00:00"
        rows = odds_api.normalize_event(_event(f"evt-{day}", day),
                                        fetched_at=captured_at)
        frame = pd.DataFrame(rows)
        frame["captured_at"] = captured_at
        frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                     lineterminator="\n")
    return path


# --------------------------------------------------------------------------
# Damage, each applied to the bad day's file. Line 0 is the header.
# --------------------------------------------------------------------------

def _stray_quote(path: Path) -> None:
    """Parses without an error, and short: the quotes swallow the rows between."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace(",BookOne", ',"BookOne')
    lines[9] = lines[9].replace(",BookOne", ',BookOne"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) < ROUNDS * 4, "the damage must shorten the parse"


def _one_row_short(path: Path) -> None:
    """The smallest short parse: two adjacent lines merge into one row."""
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[3] = lines[3].replace(",BookOne", ',"BookOne')
    lines[4] = lines[4].replace(",BookOne", ',BookOne"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(pd.read_csv(path)) == ROUNDS * 4 - 1


def _undecodable_byte(path: Path) -> None:
    raw = path.read_bytes()
    index = raw.index(b"Home Team", raw.index(b"\n"))
    path.write_bytes(raw[:index] + b"\xff" + raw[index + 1:])
    with pytest.raises(UnicodeDecodeError):
        pd.read_csv(path, low_memory=False)


def _missing_column(path: Path) -> None:
    """A ladder-identity column absent: concatenated, its rows lose their book."""
    pd.read_csv(path).drop(columns=["book"]).to_csv(path, index=False)


def _missing_moment(path: Path) -> None:
    """Neither `captured_at` nor `snapshot`: any moment would be a guess."""
    pd.read_csv(path).drop(columns=["captured_at", "fetched_at"]).to_csv(
        path, index=False
    )


def _ragged_row(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[5] += ",extra,extra,extra"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _unterminated_quote(path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write('"2026-10-02,2026-10-02T23:00:00Z\n')


def _zero_bytes(path: Path) -> None:
    path.write_bytes(b"")


DAMAGE = {
    "stray-quote": (_stray_quote, "parses to only"),
    "one-row-short": (_one_row_short, "parses to only"),
    "undecodable-byte": (_undecodable_byte, "UnicodeDecodeError"),
    "missing-column": (_missing_column, "book"),
    "missing-moment": (_missing_moment, "captured_at"),
    "ragged-row": (_ragged_row, "ParserError"),
    "unterminated-quote": (_unterminated_quote, "ParserError"),
    "zero-bytes": (_zero_bytes, "EmptyDataError"),
}


def _main(processed: Path, outputs: Path) -> tuple[int, str, dict]:
    module = load_script("run_ladder_coherence.py")
    code = module.main(
        ["--processed-dir", str(processed), "--output-dir", str(outputs)]
    )
    body = (outputs / "ladder_coherence.md").read_text(encoding="utf-8")
    record = json.loads(
        (outputs / "ladder_coherence.json").read_text(encoding="utf-8")
    )
    return code, body, record


@pytest.mark.parametrize("shape", list(DAMAGE))
def test_a_damaged_day_is_named_and_the_good_day_still_counted(
    tmp_path: Path, capsys, shape: str
) -> None:
    damage, reason = DAMAGE[shape]
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    damage(_capture_day(processed, BAD_DAY, ROUNDS))
    bad_name = f"{BAD_DAY}.csv"

    code, body, record = _main(processed, tmp_path / "outputs")
    stderr = capsys.readouterr().err

    assert code != 0, "a scan that could not read a captured day is not clean"
    # Named in the report, with its reason, and in the log.
    assert f"`{bad_name}`" in body, body
    assert reason in body, body
    assert bad_name in stderr and "::error::" in stderr, stderr
    assert [entry["name"] for entry in record["unreadable_captures"]] == [bad_name]
    assert reason in record["unreadable_captures"][0]["reason"]
    # The good day is still read and counted, and only it.
    assert "- Captures read: 1\n" in body, body
    assert record["captures"] == 1
    assert record["ladders_with_two_rungs"] == 1
    assert EMPTY_STATE not in body


@pytest.mark.parametrize("shape", ["undecodable-byte", "stray-quote", "missing-column"])
def test_a_scan_whose_only_day_is_damaged_is_never_the_empty_state(
    tmp_path: Path, capsys, shape: str
) -> None:
    damage, _ = DAMAGE[shape]
    processed = tmp_path / "processed"
    damage(_capture_day(processed, BAD_DAY, ROUNDS))

    code, body, record = _main(processed, tmp_path / "outputs")

    assert code != 0
    assert EMPTY_STATE not in body, body
    assert f"`{BAD_DAY}.csv`" in body, body
    assert record["captures"] == 0
    assert [entry["name"] for entry in record["unreadable_captures"]] == [
        f"{BAD_DAY}.csv"
    ]
    assert f"{BAD_DAY}.csv" in capsys.readouterr().err


def test_undamaged_days_are_all_counted_and_exit_zero(tmp_path: Path, capsys) -> None:
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    _capture_day(processed, BAD_DAY, ROUNDS)

    code, body, record = _main(processed, tmp_path / "outputs")

    assert code == 0
    assert "- Captures read: 2\n" in body
    assert record["captures"] == 2
    assert record["unreadable_captures"] == []
    # One ladder per capture moment: one on the first day, four on the second.
    assert record["ladders_with_two_rungs"] == 1 + ROUNDS
    assert "::error::" not in capsys.readouterr().err
    assert "could not be read" not in body


def test_a_header_only_day_is_empty_not_damaged(tmp_path: Path) -> None:
    """It holds no row to lose, so there is nothing to name."""
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    path = _capture_day(processed, BAD_DAY, 1)
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n",
                    encoding="utf-8")

    code, _, record = _main(processed, tmp_path / "outputs")

    assert code == 0
    assert record["unreadable_captures"] == []


# --------------------------------------------------------------------------
# The Line Movement step, and the gate that reads its outcome.
# --------------------------------------------------------------------------

#: The runner is pointed at this replay's own tree (its defaults are the real
#: data/ tree). The chain script's `pull` is pointed at the local bare
#: repository standing in for the private one; `unseal` runs as written,
#: against the offline `gh` below. Any other chain command is refused, so a
#: replay can never push anywhere.
STUB_PYTHON = """#!/bin/sh
if [ "$1" = "scripts/run_ladder_coherence.py" ]; then
  shift
  exec "$REAL_PYTHON" "$RUNNER" --processed-dir "$PWD/data/processed" \\
    --output-dir "$PWD/data/outputs" "$@"
fi
if [ "$1" = "scripts/private_movement_chain.py" ]; then
  shift
  case "$1" in
    pull) exec "$REAL_PYTHON" "$CHAIN" "$@" --remote "$CHAIN_REMOTE";;
    unseal) exec "$REAL_PYTHON" "$CHAIN" "$@";;
  esac
  echo "stub python: no stand-in for private_movement_chain.py $1" >&2
  exit 97
fi
exec "$REAL_PYTHON" "$@"
"""

#: Lists no artifact, so `unseal` finds no sealed round; records each call.
STUB_GH = """#!/bin/sh
echo "$*" >> "$GH_LOG"
exit 0
"""

#: Secrets and GitHub context a replay must never inherit from this shell.
SCRUBBED = ("NHL_CLOSING_LINES_TOKEN", "NHL_CHAIN_FALLBACK_KEY", "NHL_ODDS_API_KEY",
            "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_REPOSITORY")


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _step(name: str) -> dict:
    matches = [s for s in _steps() if s.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _scan_step() -> dict:
    return _step("Scan the captured ladders")


def _install(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / name
    stub.write_text(body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


def _replay(root: Path, step: dict, **extra: str) -> tuple[int, str, str]:
    """A step's own block, under the shell GitHub gives a `run:` (bash -e)."""
    bin_dir = root / "bin"
    _install(bin_dir, "python", STUB_PYTHON)
    summary = root / "summary.md"
    env = {
        **{k: v for k, v in os.environ.items() if k not in SCRUBBED},
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "REAL_PYTHON": sys.executable,
        "RUNNER": str(RUNNER),
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "GITHUB_STEP_SUMMARY": str(summary),
        **extra,
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=root, env=env, capture_output=True, text=True, timeout=120,
    )
    text = summary.read_text(encoding="utf-8") if summary.is_file() else ""
    return result.returncode, text, result.stdout + result.stderr


def _run_step(root: Path) -> tuple[int, str, str]:
    return _replay(root, _scan_step())


@pytest.mark.parametrize("shape", ["undecodable-byte", "stray-quote"])
def test_the_step_names_the_damaged_day_and_exits_non_zero(
    tmp_path: Path, shape: str
) -> None:
    damage, _ = DAMAGE[shape]
    processed = tmp_path / "data" / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    # The day this run captured into (the step's clock is pinned to TODAY).
    damage(_capture_day(processed, TODAY, ROUNDS))

    code, summary, log = _run_step_on_today(tmp_path)

    assert code != 0, log
    assert "wrote no report" not in summary, summary
    # The depth of the days that were read is still reported ...
    assert "### Ladder depth: 1\n" in summary, summary
    # ... under the name of the day that was not.
    assert f"{TODAY}.csv" in summary, summary
    assert f"{TODAY}.csv" in log, log


def test_the_step_exits_zero_on_undamaged_days(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    _capture_day(processed, GOOD_DAY, 1)

    code, summary, log = _run_step(tmp_path)

    assert code == 0, log
    assert "### Ladder depth: 1\n" in summary, summary
    assert "could not be read" not in summary, summary


def test_the_step_no_longer_swallows_its_own_exit() -> None:
    step = _scan_step()
    assert "|| true" not in step["run"]
    # A failed scan can never cost the round being kept (pushed privately,
    # or sealed): the step is still forgiven and still runs after a failed
    # capture.
    assert step.get("continue-on-error") is True
    assert str(step.get("if", "")).startswith("always()")
    assert step.get("id") == "ladder", "the gate reads this step by its id"


def _ladder_gate() -> tuple[int, dict]:
    gates = [
        (index, step) for index, step in enumerate(_steps())
        if "steps.ladder.outcome == 'failure'" in str(step.get("if", ""))
    ]
    assert len(gates) == 1, "exactly one step must fail the run on a failed scan"
    return gates[0]


def _replay_gate(root: Path) -> subprocess.CompletedProcess:
    _, gate = _ladder_gate()
    return subprocess.run(
        ["bash", "-e", "-c", gate["run"]], cwd=root,
        env={"PATH": os.environ["PATH"]}, capture_output=True, text=True,
        timeout=30,
    )


def _indices_running(steps: list[dict], command: str) -> list[int]:
    return [i for i, step in enumerate(steps) if command in str(step.get("run", ""))]


def test_a_failed_scan_turns_the_run_red_after_the_round_is_kept(
    tmp_path: Path,
) -> None:
    steps = _steps()
    index, gate = _ladder_gate()
    # What keeps the round in stage two: the private push, the seal that
    # stands in for a failed push, and every upload (the sealed round's and
    # the scan's own report). Found by what they run, not by their ids.
    pushes = _indices_running(steps, "private_movement_chain.py push")
    seals = _indices_running(steps, "private_movement_chain.py seal")
    uploads = [
        i for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert len(pushes) == 1 and len(seals) == 1 and uploads, (pushes, seals, uploads)
    keepers = pushes + seals + uploads
    assert index > max(keepers), (
        "a red run must never stop the round from being kept: "
        f"gate at {index}, keepers at {keepers}"
    )
    assert "always()" in str(gate.get("if", ""))
    assert gate.get("continue-on-error") in (None, False)

    result = _replay_gate(tmp_path)
    assert result.returncode == 1
    assert "::error::" in result.stdout


# --------------------------------------------------------------------------
# Red for the day this run wrote; a standing warning for every earlier day.
#
# The private chain carries every day file, each round's restore pulls a file
# it does not have whole (damaged or not), and the scan reads every day in it.
# So a day damaged in October is still damaged in March (the restore replay at
# the end of this file shows it). Were any damaged file to turn
# the run red, one bad day would red every later run of the season, and the
# line-unit and scratch-list gates, which report data that cannot be
# collected later, would sit under a red X nobody could clear. The run is red
# only when the day this run captured into (`--fail-on-day`) is damaged; an
# earlier damaged day is still named, every run, as a warning.
# --------------------------------------------------------------------------

TODAY = "2026-10-03"


def _main_for_day(processed: Path, outputs: Path, day: str) -> tuple[int, str, dict]:
    module = load_script("run_ladder_coherence.py")
    code = module.main([
        "--processed-dir", str(processed), "--output-dir", str(outputs),
        "--fail-on-day", day,
    ])
    body = (outputs / "ladder_coherence.md").read_text(encoding="utf-8")
    record = json.loads(
        (outputs / "ladder_coherence.json").read_text(encoding="utf-8")
    )
    return code, body, record


def test_an_earlier_damaged_day_is_a_standing_warning_not_a_red_run(
    tmp_path: Path, capsys
) -> None:
    processed = tmp_path / "processed"
    _stray_quote(_capture_day(processed, BAD_DAY, ROUNDS))
    _capture_day(processed, TODAY, 1)

    code, body, record = _main_for_day(processed, tmp_path / "outputs", TODAY)
    stderr = capsys.readouterr().err

    assert code == 0, "an earlier day's damage must not red every later run"
    # Still named, in every place, every run.
    assert f"`{BAD_DAY}.csv`" in body, body
    assert "standing warning" in body, body
    [entry] = record["unreadable_captures"]
    assert entry["name"] == f"{BAD_DAY}.csv"
    assert entry["fails_run"] is False
    assert f"::warning::Ladder scan could not read {BAD_DAY}.csv" in stderr, stderr
    assert "::error::" not in stderr, stderr
    assert record["ladders_with_two_rungs"] == 1


@pytest.mark.parametrize("shape", ["stray-quote", "undecodable-byte", "missing-column"])
def test_damage_in_the_day_this_run_wrote_is_a_red_run(
    tmp_path: Path, capsys, shape: str
) -> None:
    damage, _ = DAMAGE[shape]
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    damage(_capture_day(processed, TODAY, ROUNDS))

    code, body, record = _main_for_day(processed, tmp_path / "outputs", TODAY)
    stderr = capsys.readouterr().err

    assert code != 0
    assert f"`{TODAY}.csv`" in body, body
    assert [e["fails_run"] for e in record["unreadable_captures"]] == [True]
    assert f"::error::Ladder scan could not read {TODAY}.csv" in stderr, stderr


def test_without_a_day_every_damaged_file_fails_the_run(tmp_path: Path) -> None:
    """Run by hand, with no day named, the scan stays strict."""
    processed = tmp_path / "processed"
    _stray_quote(_capture_day(processed, BAD_DAY, ROUNDS))
    _capture_day(processed, TODAY, 1)

    code, _, record = _main(processed, tmp_path / "outputs")

    assert code != 0
    assert [e["fails_run"] for e in record["unreadable_captures"]] == [True]


def test_a_truncated_header_with_no_rows_is_named(tmp_path: Path) -> None:
    """Not an empty day: it lacks the capture's columns, as #235 names it."""
    processed = tmp_path / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    path = processed / "line_movement" / f"{BAD_DAY}.csv"
    path.write_text("captured_at,commence\n", encoding="utf-8")

    code, body, record = _main(processed, tmp_path / "outputs")

    assert code != 0
    assert f"`{BAD_DAY}.csv`" in body, body
    assert "missing column(s)" in record["unreadable_captures"][0]["reason"]


#: The clock is pinned at 2026-10-04T01:30Z: still TODAY in the league's
#: zone, already the next day in UTC. That is the last capture of a league
#: day, and a step computing its day in UTC (or with `date -u`) would name
#: tomorrow's file, so damage in the file it had just appended to would read
#: as an earlier day's warning and that league day would never go red. The
#: zone is `capture_line_movement.py`'s own, so the step must name the day
#: the capture wrote to.
UTC_DAY = "2026-10-04"
DATE_STUB = f"""#!/bin/sh
for argument in "$@"; do
  case "$argument" in -u|--utc|--universal) echo {UTC_DAY}; exit 0;; esac
done
if [ "${{TZ:-}}" = "{LEAGUE_TIMEZONE.key}" ]; then
  echo {TODAY}
else
  echo {UTC_DAY}
fi
"""


def _run_step_on_today(root: Path) -> tuple[int, str, str]:
    """The step, with the league day its clock reads pinned to TODAY."""
    _install(root / "bin", "date", DATE_STUB)
    return _run_step(root)


def test_the_step_warns_on_an_earlier_damaged_day_and_stays_green(
    tmp_path: Path,
) -> None:
    processed = tmp_path / "data" / "processed"
    _stray_quote(_capture_day(processed, BAD_DAY, ROUNDS))
    _capture_day(processed, TODAY, 1)

    code, summary, log = _run_step_on_today(tmp_path)

    assert code == 0, log
    assert f"{BAD_DAY}.csv" in summary, summary
    assert "earlier day" in summary, summary
    assert "### Ladder depth: 1\n" in summary, summary


def test_the_step_is_red_when_the_day_it_wrote_is_damaged(tmp_path: Path) -> None:
    processed = tmp_path / "data" / "processed"
    _capture_day(processed, GOOD_DAY, 1)
    _stray_quote(_capture_day(processed, TODAY, ROUNDS))

    code, summary, log = _run_step_on_today(tmp_path)

    assert code != 0, log
    assert f"{TODAY}.csv" in summary, summary
    assert "this run's day" in summary, summary


def test_the_gate_names_no_repair_it_cannot_describe(tmp_path: Path) -> None:
    """Earlier copies of a day file are in the history of the branch the push
    writes, in the repository it writes to; stage two keeps no public copy,
    so the gate may name no artifact this workflow does not upload."""
    chain = load_script("private_movement_chain.py")
    steps = _steps()
    [push_at] = _indices_running(steps, "private_movement_chain.py push")
    push = shlex.split(steps[push_at]["run"])
    repo = push[push.index("--repo") + 1] if "--repo" in push else chain.store.PRIVATE_REPO
    said = _replay_gate(tmp_path).stdout

    assert repo in said, said
    assert f"{chain.CHAIN_BRANCH} branch" in said, said
    uploaded = {
        str(step["with"]["name"]) for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    }
    named = re.findall(r"(?:-n|--name)\s+([A-Za-z0-9._-]+)", said)
    assert set(named) <= uploaded, (named, uploaded)


# --------------------------------------------------------------------------
# What the restore delivers is what the scan judges.
# --------------------------------------------------------------------------

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, **GIT_ENV})


def _private_chain(root: Path, damaged_day: str) -> Path:
    """A bare repository whose `movement` branch holds GOOD_DAY whole and
    `damaged_day` with stray quotes, laid out as the chain is."""
    seed = root / "seed"
    _capture_day(seed, GOOD_DAY, 1)
    _stray_quote(_capture_day(seed, damaged_day, ROUNDS))
    bare = root / "private.git"
    _git(["init", "-q", "--bare", str(bare)], root)
    _git(["init", "-q"], seed)
    _git(["add", "-A"], seed)
    _git(["commit", "-qm", "earlier rounds"], seed)
    _git(["push", "-q", str(bare), "HEAD:refs/heads/movement"], seed)
    return bare


@pytest.mark.parametrize(
    "damaged_day, red, label",
    [(BAD_DAY, False, "an earlier day"), (TODAY, True, "this run's day")],
    ids=["earlier-day-warns", "todays-day-reds"],
)
def test_a_damaged_day_the_private_chain_holds_comes_back_every_round(
    tmp_path: Path, damaged_day: str, red: bool, label: str
) -> None:
    """The restore pulls a day file it lacks whole, damage and all, so the scan
    sees the damage every round: red while that league day is being captured,
    a standing warning on every later day, never silence."""
    bare = _private_chain(tmp_path / "private", damaged_day)
    root = tmp_path / "run"
    root.mkdir()
    _install(root / "bin", "date", DATE_STUB)
    _install(root / "bin", "gh", STUB_GH)
    gh_log = root / "gh.log"

    code, _, log = _replay(
        root, _step("Restore today's captures"), **GIT_ENV,
        CHAIN=str(PROJECT_ROOT / "scripts" / "private_movement_chain.py"),
        CHAIN_REMOTE=f"file://{bare}", GH_LOG=str(gh_log),
    )
    assert code == 0, log
    assert (root / "restore_problem.txt").read_text(encoding="utf-8") == "", log
    asked = gh_log.read_text(encoding="utf-8") if gh_log.is_file() else ""
    assert "actions/artifacts" in asked, "the restore must look for sealed rounds too"
    # This round's capture appends to the league day the clock reads.
    _capture_day(root / "data" / "processed", TODAY, 1)

    code, summary, log = _run_step(root)

    assert (code != 0) is red, log
    assert f"`{damaged_day}.csv`" in summary and label in summary, summary
    # Every readable day the chain held, and this round's, is in the depth.
    assert f"### Ladder depth: {1 if red else 2}\n" in summary, summary
