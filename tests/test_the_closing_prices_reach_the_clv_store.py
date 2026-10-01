"""Line Movement's closing prices reach the store CLV is measured from.

On 2026-08-29 Closing Lines lost its schedule, because Line Movement
Capture's single fetch already produced the same best price per selection and
two schedules were paying twice. That retired the store's only writer. From
2026-09-24 Line Movement handed its closing prices over as a
`closing-line-captures` artifact for Closing Lines to publish on a
`closing-lines` branch, and both were downloadable odds files on a public
repository, which the provider's terms forbid; Closing Lines was disabled on
2026-09-25 (#126) before it ever published.

Since 2026-10-01 Closing Lines runs when Line Movement completes, reads the
`line-movement` artifact Line Movement already keeps for its own restore
chain, derives the closing prices from it, and pushes them to the private
repository cooperross399/nhl-closing-lines. That path fetches nothing from
the provider and spends no credit.

The structural half reads the YAML. The executed half runs the hand-off
`run:` block exactly as written under `bash -e`, with `gh` replaced by a
stub, and drives `private_closing_store.py push` against a local bare
repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab.config import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_closing_store as store  # noqa: E402

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
HANDOFF = "Take the captures Line Movement kept"
PUBLISH = "Publish to the private store"
REPO = "owner/lab"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(document: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    return document.get("on", document.get(True)) or {}


def _steps(document: dict) -> dict[str, dict]:
    (job,) = document["jobs"].values()
    return {step.get("name"): step for step in job["steps"]}


def _kept_artifact() -> tuple[str, list[str]]:
    """The artifact Line Movement keeps its day files in, and its paths."""
    for job in _load("line-movement.yml")["jobs"].values():
        for step in job["steps"]:
            given = step.get("with") or {}
            paths = str(given.get("path", "")).split()
            if f"data/processed/{cl.MOVEMENT_DIRNAME}" in paths:
                return str(given["name"]), paths
    raise AssertionError("Line Movement keeps no day files")


# -- structure ----------------------------------------------------------------


def test_closing_lines_takes_the_artifact_line_movement_keeps():
    name, paths = _kept_artifact()
    assert name == "line-movement"
    run = _steps(_load("closing-lines.yml"))[HANDOFF]["run"]
    assert f"--name {name} " in run
    assert f'select(.name == "{name}")' in run
    # Unpacked where it is rooted, so the day files land in
    # data/processed/line_movement, where the push reads them.
    assert all(p.startswith("data/processed/") for p in paths)
    assert "--dir data/processed " in run


def test_line_movement_no_longer_hands_over_a_closing_price_artifact():
    for job in _load("line-movement.yml")["jobs"].values():
        for step in job["steps"]:
            assert (step.get("with") or {}).get("name") != "closing-line-captures"


def test_closing_lines_runs_when_line_movement_completes():
    source = _load("line-movement.yml")["name"]
    trigger = _triggers(_load("closing-lines.yml")).get("workflow_run") or {}
    assert trigger.get("workflows") == [source]
    assert "completed" in trigger.get("types", [])


def test_no_step_that_can_spend_runs_on_a_hand_off():
    """A step that reads the provider key is a step that can buy prices."""
    steps = _load("closing-lines.yml")["jobs"]["capture"]["steps"]
    spending = [s for s in steps if "NHL_ODDS_API_KEY" in yaml.safe_dump(s)]
    assert spending, "the dispatch path must still be able to capture"
    for step in spending:
        assert "github.event_name != 'workflow_run'" in str(step.get("if", "")), step["name"]
    assert "secrets." not in yaml.safe_dump(_steps(_load("closing-lines.yml"))[HANDOFF])


def test_the_store_token_reaches_only_the_publish_step():
    for name, step in _steps(_load("closing-lines.yml")).items():
        if "NHL_CLOSING_LINES_TOKEN" in yaml.safe_dump(step):
            assert name == PUBLISH


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


def test_the_hand_off_can_read_another_runs_artifacts():
    permissions = _load("closing-lines.yml")["permissions"]
    assert permissions == {"contents": "read", "actions": "read"}


# -- the hand-off, executed ---------------------------------------------------


def _handoff(tmp_path: Path, gh: str) -> tuple[subprocess.CompletedProcess, Path, str]:
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "gh").write_text("#!/bin/bash\n" + gh)
    (stub / "gh").chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    output = tmp_path / "out.txt"
    output.write_text("")
    block = _steps(_load("closing-lines.yml"))[HANDOFF]["run"].replace(
        "${{ github.repository }}", REPO
    )
    assert "${{" not in block
    env = {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
           "RUN_ID": "7", "GITHUB_OUTPUT": str(output), "GH_TOKEN": "x"}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
                          cwd=work, env=env, capture_output=True, text=True)
    return done, work, output.read_text()


def test_a_run_that_kept_nothing_publishes_nothing(tmp_path):
    done, _work, output = _handoff(tmp_path, 'if [ "$1" = api ]; then echo 0; exit 0; fi\nexit 9\n')
    assert done.returncode == 0, done.stderr
    assert "empty=true" in output


def test_a_kept_artifact_without_price_captures_publishes_nothing(tmp_path):
    gh = ('if [ "$1" = api ]; then echo 1; exit 0; fi\n'
          'while [ $# -gt 0 ]; do [ "$1" = --dir ] && dir="$2"; shift; done\n'
          'mkdir -p "$dir/deployment"; exit 0\n')
    done, _work, output = _handoff(tmp_path, gh)
    assert done.returncode == 0, done.stderr
    assert "empty=true" in output


def test_a_download_that_fails_is_a_red_run_not_a_quiet_one(tmp_path):
    gh = 'if [ "$1" = api ]; then echo 1; exit 0; fi\necho "HTTP 502" >&2; exit 1\n'
    done, _work, output = _handoff(tmp_path, gh)
    assert done.returncode != 0
    assert "empty=true" not in output


def test_a_kept_day_file_lands_where_the_push_reads_it(tmp_path):
    gh = ('if [ "$1" = api ]; then echo 1; exit 0; fi\n'
          'while [ $# -gt 0 ]; do [ "$1" = --dir ] && dir="$2"; shift; done\n'
          'mkdir -p "$dir/line_movement" && echo x > "$dir/line_movement/2026-10-08.csv"\n')
    done, work, output = _handoff(tmp_path, gh)
    assert done.returncode == 0, done.stderr
    assert "empty=true" not in output
    assert (work / "data" / "processed" / cl.MOVEMENT_DIRNAME / "2026-10-08.csv").is_file()


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
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    return path


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
    """A run whose artifact lost an earlier round must not erase it."""
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


def test_every_day_the_artifact_carries_is_pushed_so_a_gap_heals(tmp_path, bare):
    """A league day weeks old that the store never received (a failed push,
    a week with no token) lands on the next push, for as long as the chain
    carries it."""
    processed = tmp_path / "run"
    old = _round(14, 120.0)
    old["captured_at"] = "2026-09-01T14:00:00Z"
    _day_file(processed, [old], day="2026-09-01")
    _day_file(processed, [_round(14, 120.0)])

    assert _push(processed, bare) == store.EXIT_OK

    assert _stored(bare, "2026-09-01.csv"), "the old day was skipped"
    assert _stored(bare, "2026-10-08.csv")


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


def test_a_remote_day_that_parses_short_without_an_error_is_damage(tmp_path, bare):
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
    store's file, and the push takes it as it is."""
    processed = tmp_path / "run"
    processed.mkdir()
    rows = cl.best_prices(_round(22, 130.0, "Caesars"), captured_at="2026-10-08T22:00:00Z")
    rows.to_csv(processed / cl.CAPTURES_FILENAME, index=False)

    assert _push(processed, bare) == store.EXIT_OK

    stored = pd.read_csv(pd.io.common.StringIO(_stored(bare)))
    assert stored[["captured_at", "american_odds", "book"]].values.tolist() == [
        ["2026-10-08T22:00:00Z", 130.0, "Caesars"]
    ]


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
