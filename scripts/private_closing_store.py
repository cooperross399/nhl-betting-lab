#!/usr/bin/env python3
"""Write and read the closing-line store, which lives in a PRIVATE repository.

    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_closing_store.py push --processed-dir data/processed
    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_closing_store.py pull --out "$RUNNER_TEMP/store/closing_line_captures.csv"

## Why a second repository

This repository is public. A `closing-lines` branch here was a permanent,
downloadable file of captured odds (book, price, line, capture time), and The
Odds API's terms forbid redistributing their data as downloadable files that
serve as raw data. Closing Lines was disabled on 2026-09-25 for that reason
(#126). Cooper's decision on 2026-10-01: closing-line data is never published
publicly, and CLV still works. So the store lives in
`cooperross399/nhl-closing-lines`, which is private, and nothing in this
repository may hold it on a branch, a release, a Pages site or an artifact.
`tests/test_closing_prices_never_reach_the_public_repo.py` holds that.

## The two refusals before every push

1. The target is never this repository. `--repo` naming the public lab, or a
   `--remote` URL naming it, is refused before anything is read.
2. The target is private, asked of the GitHub API with the same token on
   every push. A store whose repository was made public is not written to
   again, whatever the code around it says. A push needs `"private": true`,
   not just an answer that lacks `"private": false`.

## Layout: one file per UTC day of `captured_at`

`captures/<YYYY-MM-DD>.csv`, with `closing_lines.CAPTURE_COLUMNS`. A season
in one file would pass GitHub's 100 MB file limit by midwinter (five rounds a
day, one best-price row per selection per round), and every push would
rewrite all of it. Each day file goes through `merge_capture_store.merge`,
the merge the closing-lines branch used: every row either side holds, once,
and never fewer than the remote had.

## push

Takes this run's closing prices from `--processed-dir`:

* `line_movement/<day>.csv`, Line Movement's day files, as its `line-movement`
  artifact carries them. They go through `closing_lines.load_movement_captures`,
  which is the dedicated store's rows by construction: one `best_prices` row
  per selection per round. Only the last `--recent-days` league days are read.
  The artifact carries the whole season, an earlier day cannot gain a capture
  after its games have started, and three days lets a round whose push failed
  heal on the next one.
* `closing_line_captures.csv`, which a dispatched `capture_closing_lines.py`
  writes, taken whole.

Exit 0 when pushed or when there was nothing new, 1 when the store could not
be reached or written, 2 when a movement day file or the remote store is
damaged (the good days are still pushed), and 3 when `NHL_CLOSING_LINES_TOKEN`
is not set.

## pull

Joins every day file into one capture store at `--out`, which must sit
outside the workspace. Gameday Refresh uploads `data/processed` whole as the
public `gameday-state` artifact, so the store is never written there.

Exit 0 with rows written, 3 when `NHL_CLOSING_LINES_TOKEN` is not set (no
store configured, not a fault), 4 when the store is reachable and holds no
rows yet (not a fault), 1 when it could not be reached, and 2 when a day file
is damaged. Nothing is written to `--out` unless the exit is 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from merge_capture_store import merge  # noqa: E402

from nhl_betting_lab.closing_lines import (  # noqa: E402
    CAPTURE_COLUMNS,
    CAPTURES_FILENAME,
    MOVEMENT_DIRNAME,
    load_movement_captures,
)
from nhl_betting_lab.stores import (  # noqa: E402
    CorruptStoreError,
    existing_row_count,
    read_store,
)

#: The private repository that holds the store.
PRIVATE_REPO = "cooperross399/nhl-closing-lines"
#: This lab. Public, so the store may never be written to it.
PUBLIC_REPO = "cooperross399/nhl-betting-lab"
#: The Actions secret both workflows read.
TOKEN_ENV = "NHL_CLOSING_LINES_TOKEN"
BRANCH = "main"
CAPTURES_DIR = "captures"
DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$")
PUSH_ATTEMPTS = 3

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DAMAGED = 2
EXIT_NO_TOKEN = 3
EXIT_EMPTY = 4


class Refused(Exception):
    """A push or pull that must not happen, and why."""


def _say(message: str) -> None:
    print(message, flush=True)


def _error(message: str) -> None:
    print(f"::error::{message}", flush=True)


def utc_now() -> datetime:
    """The clock the recent-days window is read against. Tests replace it."""
    return datetime.now(timezone.utc)


def _token() -> str:
    return os.environ.get(TOKEN_ENV, "").strip()


def remote_url(repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def refuse_public_target(repo: str, remote: str) -> None:
    """Refuse the public lab as a target, by name, before anything is read."""
    public = {PUBLIC_REPO.lower()}
    running_in = os.environ.get("GITHUB_REPOSITORY", "").strip().lower()
    if running_in:
        public.add(running_in)
    if repo.strip().lower() in public:
        raise Refused(
            f"Refusing to use {repo} as the closing-line store: it is the "
            "public lab, and closing-line data is never published publicly."
        )
    lowered = remote.lower()
    if "github.com" in lowered and f"/{repo.strip().lower()}" not in lowered:
        raise Refused(
            f"Refusing a GitHub remote that does not name {repo}: the privacy "
            "check is made of that repository, so the push must go to it."
        )
    for name in public:
        if f"/{name}" in lowered or f":{name}" in lowered:
            raise Refused(
                f"Refusing to push the closing-line store to a remote that "
                f"names {name}, the public lab."
            )


def repo_is_private(repo: str, token: str) -> bool:
    """True only when the GitHub API says `"private": true` for `repo`.

    Any failure to ask raises: a push is never made on an unanswered
    question. The request carries urllib's default User-Agent, which
    api.github.com accepts.
    """
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    return body.get("private") is True


def require_private(repo: str, token: str) -> None:
    try:
        private = repo_is_private(repo, token)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Refused(
            f"Could not confirm that {repo} is private ({exc}); refusing to "
            "write closing-line data to it."
        ) from exc
    if not private:
        raise Refused(
            f"{repo} is not private. Refusing to write closing-line data to "
            "it: the provider's terms forbid publishing it, and this store "
            "exists so that it is never published."
        )


def _git(args: list[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "Closing Lines",
        "GIT_AUTHOR_EMAIL": "actions@github.com",
        "GIT_COMMITTER_NAME": "Closing Lines",
        "GIT_COMMITTER_EMAIL": "actions@github.com",
    }
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, **kw
    )


def _scrub(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def fetch_tip(work: Path, remote: str, token: str) -> str:
    """Fetch the store's branch into `work` and check it out. Its commit."""
    if not (work / ".git").exists():
        done = _git(["init", "-q"], work)
        if done.returncode:
            raise OSError(done.stderr.strip())
    # A retry reuses the directory: drop the rejected attempt's commit and files.
    _git(["reset", "-q", "--hard"], work)
    _git(["clean", "-q", "-fdx"], work)
    done = _git(["fetch", "-q", "--depth", "1", remote, f"+refs/heads/{BRANCH}:refs/store-tip"], work)
    if done.returncode:
        raise OSError(
            f"could not fetch {BRANCH} of the closing-line store: "
            f"{_scrub(done.stderr.strip(), token)}"
        )
    done = _git(["checkout", "-q", "-f", "--detach", "refs/store-tip"], work)
    if done.returncode:
        raise OSError(done.stderr.strip())
    return _git(["rev-parse", "HEAD"], work).stdout.strip()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".csv.tmp")
    frame.to_csv(temp, index=False, lineterminator="\n")
    temp.replace(path)


def _day_of(frame: pd.DataFrame) -> pd.Series:
    stamps = pd.to_datetime(frame["captured_at"], utc=True, errors="coerce", format="mixed")
    if stamps.isna().any():
        bad = frame.loc[stamps.isna(), "captured_at"].astype(str).head(3).tolist()
        raise CorruptStoreError(
            f"{int(stamps.isna().sum())} capture row(s) carry a captured_at "
            f"that is not an instant (e.g. {bad}); a row that cannot be "
            "ordered against face-off is never stored."
        )
    return stamps.dt.strftime("%Y-%m-%d")


def incoming_rows(
    processed_dir: Path, *, recent_days: int, today: datetime, damaged: dict[str, str]
) -> pd.DataFrame:
    """This run's closing prices, in the dedicated store's columns."""
    frames = []
    movement = processed_dir / MOVEMENT_DIRNAME
    if movement.is_dir():
        floor = (today - timedelta(days=recent_days)).strftime("%Y-%m-%d")
        recent = sorted(
            path for path in movement.glob("*.csv")
            if DAY_FILE.match(path.name) and path.stem >= floor
        )
        if recent:
            with tempfile.TemporaryDirectory() as scratch:
                copy = Path(scratch) / MOVEMENT_DIRNAME
                copy.mkdir()
                for path in recent:
                    shutil.copy2(path, copy / path.name)
                frames.append(load_movement_captures(Path(scratch), unreadable=damaged))
    dispatched = processed_dir / CAPTURES_FILENAME
    if dispatched.is_file():
        rows_on_disk = existing_row_count(dispatched)
        frame = read_store(dispatched, columns=CAPTURE_COLUMNS, for_append=True)
        if len(frame) < rows_on_disk:
            raise CorruptStoreError(
                f"{dispatched} holds {rows_on_disk} row(s) and parses to only {len(frame)}."
            )
        frames.append(frame)
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    return pd.concat(frames, ignore_index=True)[list(CAPTURE_COLUMNS)]


def merge_into(work: Path, rows: pd.DataFrame) -> list[str]:
    """Merge `rows` into the checked-out store. The day files that changed."""
    if rows.empty:
        return []
    changed = []
    days = _day_of(rows)
    for day, mine in rows.groupby(days, sort=True):
        target = work / CAPTURES_DIR / f"{day}.csv"
        with tempfile.TemporaryDirectory() as scratch:
            # Through a file, so both sides are parsed by the same reader and
            # a float that went to disk compares equal to its own read-back.
            mine_path = Path(scratch) / "mine.csv"
            _write_csv(mine, mine_path)
            mine_read = read_store(mine_path, columns=CAPTURE_COLUMNS, for_append=True)
            remote_rows = existing_row_count(target)
            theirs = read_store(target, columns=CAPTURE_COLUMNS, for_append=True)
            merged = merge(
                mine_read,
                theirs,
                remote_rows=remote_rows,
                local_rows=existing_row_count(mine_path),
            )
        if len(merged) == len(theirs) and target.is_file():
            continue
        _write_csv(merged, target)
        changed.append(target.name)
    return changed


def push(args: argparse.Namespace) -> int:
    token = _token()
    if not token and not args.remote:
        _error(
            f"{TOKEN_ENV} is not set, so the private closing-line store cannot "
            "be written. Nothing was published anywhere."
        )
        return EXIT_NO_TOKEN
    remote = args.remote or remote_url(args.repo, token)
    try:
        refuse_public_target(args.repo, remote)
        require_private(args.repo, token)
    except Refused as exc:
        _error(str(exc))
        return EXIT_FAILED

    damaged: dict[str, str] = {}
    today = utc_now()
    try:
        rows = incoming_rows(
            Path(args.processed_dir), recent_days=args.recent_days, today=today, damaged=damaged
        )
    except CorruptStoreError as exc:
        _error(f"Refusing to push: {exc}")
        return EXIT_DAMAGED
    for name, reason in sorted(damaged.items()):
        _error(
            f"Line-movement day file {name} could not be read ({reason}); its "
            "closing prices were not pushed. Every other day was."
        )
    _say(f"{len(rows)} closing-price row(s) to merge into {args.repo}.")
    if rows.empty:
        _say("Nothing to publish.")
        return EXIT_DAMAGED if damaged else EXIT_OK

    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        for attempt in range(1, PUSH_ATTEMPTS + 1):
            try:
                fetch_tip(work, remote, token)
                changed = merge_into(work, rows)
            except OSError as exc:
                _error(f"The private closing-line store could not be reached: {exc}")
                return EXIT_FAILED
            except (CorruptStoreError, ValueError) as exc:
                _error(f"Refusing to push: {exc}")
                return EXIT_DAMAGED
            if not changed:
                _say("The private store already holds every row. Nothing pushed.")
                return EXIT_DAMAGED if damaged else EXIT_OK
            _git(["add", "--", CAPTURES_DIR], work)
            stamp = today.strftime("%Y-%m-%dT%H:%M:%SZ")
            done = _git(["commit", "-q", "-m", f"captures {stamp} ({', '.join(changed)})"], work)
            if done.returncode:
                _error(f"Could not commit the merged store: {done.stderr.strip()}")
                return EXIT_FAILED
            done = _git(["push", "-q", remote, f"HEAD:refs/heads/{BRANCH}"], work)
            if done.returncode == 0:
                _say(
                    f"Pushed {', '.join(changed)} to {args.repo} "
                    f"(attempt {attempt})."
                )
                return EXIT_DAMAGED if damaged else EXIT_OK
            _say(
                "Push rejected; refetching the tip and re-merging. "
                f"{_scrub(done.stderr.strip(), token)}"
            )
    _error(f"Could not publish the private store after {PUSH_ATTEMPTS} attempts.")
    return EXIT_FAILED


def read_day_files(work: Path) -> pd.DataFrame:
    frames = []
    for path in sorted((work / CAPTURES_DIR).glob("*.csv")):
        if not DAY_FILE.match(path.name):
            continue
        rows_on_disk = existing_row_count(path)
        frame = read_store(path, columns=CAPTURE_COLUMNS, for_append=True)
        if len(frame) < rows_on_disk:
            raise CorruptStoreError(
                f"{path.name} holds {rows_on_disk} row(s) and parses to only {len(frame)}."
            )
        missing = [c for c in CAPTURE_COLUMNS if c not in frame.columns]
        if missing and not frame.empty:
            raise CorruptStoreError(f"{path.name} lacks column(s): {', '.join(missing)}.")
        if not frame.empty:
            frames.append(frame[list(CAPTURE_COLUMNS)])
    if not frames:
        return pd.DataFrame(columns=list(CAPTURE_COLUMNS))
    return pd.concat(frames, ignore_index=True)


def refuse_an_out_inside_the_workspace(out: Path) -> None:
    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if not workspace:
        return
    try:
        out.resolve().relative_to(Path(workspace).resolve())
    except ValueError:
        return
    raise Refused(
        f"Refusing to write the private store to {out}, inside the workspace: "
        "the workspace's data/processed is uploaded as a public artifact."
    )


def pull(args: argparse.Namespace) -> int:
    token = _token()
    if not token and not args.remote:
        _say(f"{TOKEN_ENV} is not set: no private closing-line store is configured.")
        return EXIT_NO_TOKEN
    out = Path(args.out)
    remote = args.remote or remote_url(args.repo, token)
    try:
        refuse_an_out_inside_the_workspace(out)
    except Refused as exc:
        _error(str(exc))
        return EXIT_FAILED
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        try:
            fetch_tip(work, remote, token)
            rows = read_day_files(work)
        except OSError as exc:
            _error(f"The private closing-line store could not be read: {exc}")
            return EXIT_FAILED
        except CorruptStoreError as exc:
            _error(f"The private closing-line store is damaged: {exc}")
            return EXIT_DAMAGED
    if rows.empty:
        _say("The private closing-line store holds no captures yet.")
        return EXIT_EMPTY
    _write_csv(rows, out)
    _say(f"Read {len(rows)} capture row(s) from the private closing-line store.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("push", "pull"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=PRIVATE_REPO)
        command.add_argument(
            "--remote",
            default="",
            help="Git URL to use in place of the repo's GitHub URL (tests).",
        )
    sub.choices["push"].add_argument("--processed-dir", default="data/processed")
    sub.choices["push"].add_argument("--recent-days", type=int, default=3)
    sub.choices["pull"].add_argument("--out", required=True)
    args = parser.parse_args(argv)
    return push(args) if args.command == "push" else pull(args)


if __name__ == "__main__":
    raise SystemExit(main())
