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

## What this does not cover

Every row this script pushes is derived from Line Movement's capture chain
(every book's every rung, the face-off round included), and `push` reads
nothing else on a hand-off. Until stage two (#298) that chain was uploaded
from this public repository as the `line-movement` artifact on every round
(7-day retention from 2026-10-02, 90 before), so closing prices were
downloadable here; those artifacts stay downloadable until they expire.
Since stage two the chain lives only on branch `movement` of the same private
repository (`scripts/private_movement_chain.py`, CLAUDE.md), and Closing Lines
pulls it from there. `tests/test_closing_prices_never_reach_the_public_repo.py`
pins the known price carriers so a new one fails rather than joining them
silently.

## The refusals before every push

1. The target is never this repository. `--repo` naming the public lab (or
   the repository the run is in) is refused before anything is read.
   `--remote` exists for tests and is accepted only as a local path
   (`file://` or absolute) whose last two components are not a public lab's
   name, or as a canonical github.com URL (https, ssh or scp form, no `%`,
   `?` or `#`) naming exactly the repository the privacy check is made of.
   Anything else is refused.
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
and no row a day file held is ever dropped, except an exact duplicate of
another row in the same file, which carries no information. A day file that
parses to fewer rows than its lines is damage: that day is left alone and
named, with how to repair it (restore `captures/<day>.csv` from the private
repository's history).

## push

Takes this run's closing prices from `--processed-dir`:

* `line_movement/<day>.csv`, every day file Line Movement's `line-movement`
  artifact carries, one at a time. Each goes through
  `closing_lines.load_movement_captures`, which is the dedicated store's rows
  by construction: one `best_prices` row per selection per round. Reading
  every day, not just the latest, means a round whose push failed (or a week
  with no token) heals on the next push for as long as the chain carries it.
  Three preseason days took 0.76 s.
* `closing_line_captures.csv`, which a dispatched `capture_closing_lines.py`
  writes, taken whole.

Exit 0 when pushed or when there was nothing new; 1 when GitHub could not be
reached (transient); 2 when a movement day file, the dispatched file, or a
remote day file is damaged (every other day is still pushed, and each damaged
one is named); 3 when `NHL_CLOSING_LINES_TOKEN` is not set; 5 when the push
is refused and a retry would be refused again: a public target, a store the
API does not call private, a token GitHub rejects, a push a repository rule
declines, or a store with no `main`. A damaged movement day stays in Line
Movement's chain until someone repairs it, so it keeps this red on every run,
as it keeps the CLV report red (#235): the rule is the same in both places.

## pull

Joins every day file into one capture store at `--out`, which must sit
outside the workspace. Gameday Refresh uploads `data/processed` whole as the
public `gameday-state` artifact, so the store is never written there.

Exit 0 with rows written; 2 when a day file is damaged (each one is named,
and the good days are still written to `--out`, so they are still scored);
3 when `NHL_CLOSING_LINES_TOKEN` is not set (no store configured, not a
fault); 4 when the store is reachable and holds no rows yet, or has no
`main` (not a fault); 1 when GitHub could not be reached (transient); 5 when
the token is rejected or `--out` is inside the workspace. `--out` is written
only when the exit is 0, or 2 with at least one good day.
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
from datetime import datetime, timezone
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
EXIT_REFUSED = 5

#: What git prints when GitHub turned the token away, as opposed to a network
#: failure. A retry, or a backup run, would be turned away again.
AUTH_FAILURES = (
    "authentication failed",
    "could not read username",
    "repository not found",
    "returned error: 401",
    "returned error: 403",
    "permission to",
    "denied to",
    "permission denied (publickey)",
    # A repository rule or branch protection that declines the push: GitHub
    # prints GH013 and GH006, and a retry is declined the same way.
    "gh013",
    "gh006",
    "protected branch",
    "rule violations",
)
GITHUB_REMOTE = re.compile(
    r"^(?:https?://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"([^/\s]+/[^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


class Refused(Exception):
    """A push or pull that must not happen, and why. A retry would be refused too."""


class Unreachable(OSError):
    """GitHub could not be reached. Possibly transient."""


class NoBranch(Exception):
    """The store's repository answered and has no `main`."""


def _say(message: str) -> None:
    print(message, flush=True)


def _error(message: str) -> None:
    print(f"::error::{message}", flush=True)


def utc_now() -> datetime:
    """The clock a commit message is stamped with. Tests replace it."""
    return datetime.now(timezone.utc)


def _token() -> str:
    return os.environ.get(TOKEN_ENV, "").strip()


def remote_url(repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def github_repo_of(remote: str) -> str | None:
    """`owner/name` of a GitHub remote, lower-cased, or None for any other URL."""
    match = GITHUB_REMOTE.match(remote.strip())
    return match.group(1).lower() if match else None


def _public_names() -> set[str]:
    names = {PUBLIC_REPO.lower()}
    running_in = os.environ.get("GITHUB_REPOSITORY", "").strip().lower()
    if running_in:
        names.add(running_in)
    return names


def refuse_public_target(repo: str, remote: str) -> None:
    """Refuse the public lab as a target, by exact name, before anything is read."""
    public = _public_names()
    wanted = repo.strip().lower()
    if wanted in public:
        raise Refused(
            f"Refusing to use {repo} as the closing-line store: it is the "
            "public lab, and the store never lives there."
        )
    named = github_repo_of(remote) if not re.search(r"[%?#]", remote) else None
    if named is not None:
        if named in public:
            raise Refused(
                f"Refusing to push the closing-line store to {named}, the public lab."
            )
        if named != wanted:
            raise Refused(
                f"Refusing a GitHub remote naming {named} when the privacy check "
                f"is made of {repo}: the push must go to the repository checked."
            )
        return
    local = remote[len("file://"):] if remote.lower().startswith("file://") else remote
    if not os.path.isabs(local) or re.search(r"[%?#]", remote):
        raise Refused(
            "Refusing a remote that is neither a canonical github.com URL "
            "naming the checked repository nor a local path: this script "
            "cannot tell which repository it names."
        )
    # A local store is refused when its last two path components are a
    # public lab's name, however the path is spelled.
    parts = [p for p in os.path.normpath(local).split(os.sep) if p]
    if parts and parts[-1].lower() == ".git":
        parts = parts[:-1]
    if len(parts) >= 2:
        tail = f"{parts[-2]}/{re.sub(r'(?i)[.]git$', '', parts[-1])}".lower()
        if tail in public:
            raise Refused(
                f"Refusing to push the closing-line store to a remote that "
                f"names {tail}, the public lab."
            )


def repo_is_private(repo: str, token: str) -> bool:
    """True only when the GitHub API says `"private": true` for `repo`.

    Raises `Refused` when GitHub turns the token away (401, 403, 404: a 404 is
    also what a token without access to a private repository gets) and
    `Unreachable` when it cannot be asked. A push is never made on an
    unanswered question. The request carries urllib's default User-Agent,
    which api.github.com accepts.
    """
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise Refused(
                f"GitHub answered {exc.code} for {repo}: the token is missing, "
                "expired, or not granted that repository."
            ) from exc
        raise Unreachable(f"GitHub answered {exc.code} for {repo}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Unreachable(f"could not ask GitHub about {repo}: {exc}") from exc
    return isinstance(body, dict) and body.get("private") is True


def require_private(repo: str, token: str) -> None:
    try:
        private = repo_is_private(repo, token)
    except ValueError as exc:
        raise Unreachable(f"GitHub's answer about {repo} was not JSON: {exc}") from exc
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
    """The text with the token masked. A token too short to be a real one is
    left alone (masking "t" would mask every t)."""
    return text.replace(token, "***") if len(token) >= 8 else text


def _remote_failure(stderr: str, token: str, what: str,
                    subject: str = "the closing-line store") -> Exception:
    # Classified on git's own words, scrubbed only for display: scrubbing
    # first let a token that happens to occur inside a marker hide it.
    raw = stderr.strip()
    text = _scrub(raw, token)
    if any(marker in raw.lower() for marker in AUTH_FAILURES):
        return Refused(
            f"GitHub turned the token away while trying to {what} {subject}: {text}"
        )
    return Unreachable(f"could not {what} {subject}: {text}")


def fetch_tip(work: Path, remote: str, token: str) -> str:
    """Fetch the store's branch into `work` and check it out. Its commit."""
    if not (work / ".git").exists():
        done = _git(["init", "-q"], work)
        if done.returncode:
            raise OSError(done.stderr.strip())
    # A retry reuses the directory: drop the rejected attempt's commit and files.
    _git(["reset", "-q", "--hard"], work)
    _git(["clean", "-q", "-fdx"], work)
    listed = _git(["ls-remote", "--heads", remote, f"refs/heads/{BRANCH}"], work)
    if listed.returncode:
        raise _remote_failure(listed.stderr, token, "list")
    if not listed.stdout.strip():
        raise NoBranch(f"the closing-line store has no {BRANCH} branch")
    done = _git(["fetch", "-q", "--depth", "1", remote, f"+refs/heads/{BRANCH}:refs/store-tip"], work)
    if done.returncode:
        raise _remote_failure(done.stderr, token, "fetch")
    done = _git(["checkout", "-q", "-f", "--detach", "refs/store-tip"], work)
    if done.returncode:
        raise OSError(done.stderr.strip())
    return _git(["rev-parse", "HEAD"], work).stdout.strip()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".csv.tmp")
    frame.to_csv(temp, index=False, lineterminator="\n")
    temp.replace(path)


def _read_dispatched(path: Path) -> pd.DataFrame:
    rows_on_disk = existing_row_count(path)
    frame = read_store(path, columns=CAPTURE_COLUMNS, for_append=True)
    if len(frame) < rows_on_disk:
        raise CorruptStoreError(
            f"{path.name} holds {rows_on_disk} row(s) and parses to only {len(frame)}."
        )
    return frame


def incoming(processed_dir: Path, damaged: dict[str, str]):
    """This run's closing prices, one source file at a time, in the
    dedicated store's columns. Each damaged source is named in `damaged`."""
    movement = processed_dir / MOVEMENT_DIRNAME
    if movement.is_dir():
        for path in sorted(movement.glob("*.csv")):
            if not DAY_FILE.match(path.name):
                continue
            with tempfile.TemporaryDirectory() as scratch:
                copy = Path(scratch) / MOVEMENT_DIRNAME
                copy.mkdir()
                shutil.copy2(path, copy / path.name)
                frame = load_movement_captures(Path(scratch), unreadable=damaged)
            if not frame.empty:
                yield path.name, frame[list(CAPTURE_COLUMNS)]
    dispatched = processed_dir / CAPTURES_FILENAME
    if dispatched.is_file():
        try:
            frame = _read_dispatched(dispatched)
        except CorruptStoreError as exc:
            damaged[dispatched.name] = str(exc)
            return
        if not frame.empty:
            yield dispatched.name, frame[list(CAPTURE_COLUMNS)]


REPAIR = f"restore it from the history of {PRIVATE_REPO}"


def _short(reason: object, work: Path) -> str:
    """A damage reason without the scratch path or the branch-era hint."""
    text = str(reason).replace(f"{work}/", "").replace(str(work), "")
    return re.sub(r"\s*Restore it from the raw cache or the branch that carries it, then re-run\.?", "", text).strip()


def merge_into(
    work: Path, rows: pd.DataFrame, damaged: dict[str, str], *, source: str = "rows"
) -> list[str]:
    """Merge `rows` into the checked-out store. The day files that changed.

    A day whose remote file is damaged, or whose rows carry a captured_at
    that is not an instant, is left alone and named in `damaged`; every
    other day is still merged.
    """
    if rows.empty:
        return []
    changed = []
    stamps = pd.to_datetime(rows["captured_at"], utc=True, errors="coerce", format="mixed")
    if stamps.isna().any():
        bad = rows.loc[stamps.isna(), "captured_at"].astype(str).head(3).tolist()
        damaged[f"{source} (captured_at)"] = (
            f"{int(stamps.isna().sum())} capture row(s) carry a captured_at that "
            f"is not an instant (e.g. {bad}); a row that cannot be ordered "
            "against face-off is never stored"
        )
        rows, stamps = rows[stamps.notna()], stamps[stamps.notna()]
    for day, mine in rows.groupby(stamps.dt.strftime("%Y-%m-%d"), sort=True):
        target = work / CAPTURES_DIR / f"{day}.csv"
        try:
            with tempfile.TemporaryDirectory() as scratch:
                # Through a file, so both sides are parsed by the same reader
                # and a float that went to disk compares equal to its read-back.
                mine_path = Path(scratch) / "mine.csv"
                _write_csv(mine, mine_path)
                mine_read = read_store(mine_path, columns=CAPTURE_COLUMNS, for_append=True)
                remote_rows = existing_row_count(target)
                theirs = read_store(target, columns=CAPTURE_COLUMNS, for_append=True)
                if len(theirs) < remote_rows:
                    raise CorruptStoreError(
                        f"holds {remote_rows} row(s) and parses to only {len(theirs)} "
                        "without an error (a stray quote folds rows into one field)"
                    )
                unique = theirs.drop_duplicates()
                merged = merge(
                    mine_read,
                    unique,
                    local_rows=existing_row_count(mine_path),
                )
        except (CorruptStoreError, ValueError) as exc:
            damaged[f"{CAPTURES_DIR}/{target.name}"] = f"{_short(exc, work)}; {REPAIR}"
            continue
        if target.is_file() and len(merged) == len(unique):
            continue
        _write_csv(merged, target)
        if target.name not in changed:
            changed.append(target.name)
    return changed


def _name_damage(damaged: dict[str, str]) -> None:
    for name, reason in sorted(damaged.items()):
        _error(f"{name} could not be used ({reason}); its rows were not pushed.")


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
        return EXIT_REFUSED
    except Unreachable as exc:
        _error(f"Refusing to push without confirming the store is private: {exc}")
        return EXIT_FAILED

    processed = Path(args.processed_dir)
    stamp = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        for attempt in range(1, PUSH_ATTEMPTS + 1):
            damaged: dict[str, str] = {}
            rows = 0
            changed: list[str] = []
            try:
                fetch_tip(work, remote, token)
                for source, frame in incoming(processed, damaged):
                    rows += len(frame)
                    for name in merge_into(work, frame, damaged, source=source):
                        if name not in changed:
                            changed.append(name)
            except Refused as exc:
                _name_damage(damaged)
                _error(str(exc))
                return EXIT_REFUSED
            except NoBranch as exc:
                _name_damage(damaged)
                _error(f"Refusing to push: {exc}; seed it with a README first.")
                return EXIT_REFUSED
            except OSError as exc:
                _name_damage(damaged)
                _error(f"The private closing-line store could not be reached: {exc}")
                return EXIT_FAILED
            if attempt == 1:
                _say(f"{rows} closing-price row(s) to merge into {args.repo}.")
            outcome = EXIT_DAMAGED if damaged else EXIT_OK
            if not changed:
                _name_damage(damaged)
                _say(
                    "Nothing pushed: the private store already holds every row "
                    "that could be read."
                )
                return outcome
            _git(["add", "--", CAPTURES_DIR], work)
            message = f"captures {stamp} ({len(changed)} day file(s): {', '.join(sorted(changed)[:5])}{', ...' if len(changed) > 5 else ''})"
            done = _git(["commit", "-q", "-m", message], work)
            if done.returncode:
                _name_damage(damaged)
                _error(f"Could not commit the merged store: {done.stderr.strip()}")
                return EXIT_FAILED
            done = _git(["push", "-q", remote, f"HEAD:refs/heads/{BRANCH}"], work)
            if done.returncode == 0:
                _name_damage(damaged)
                _say(f"Pushed {', '.join(sorted(changed))} to {args.repo} (attempt {attempt}).")
                return outcome
            failure = _remote_failure(done.stderr, token, "push to")
            if isinstance(failure, Refused):
                _name_damage(damaged)
                _error(str(failure))
                return EXIT_REFUSED
            _say(f"Push rejected; refetching the tip and re-merging. {failure}")
    _name_damage(damaged)
    _error(f"Could not publish the private store after {PUSH_ATTEMPTS} attempts.")
    return EXIT_FAILED


def read_day_files(work: Path, damaged: dict[str, str]) -> pd.DataFrame:
    """Every good day file joined; each damaged one named in `damaged` and
    left out, as a damaged movement day is (#235)."""
    frames = []
    for path in sorted((work / CAPTURES_DIR).glob("*.csv")):
        if not DAY_FILE.match(path.name):
            continue
        name = f"{CAPTURES_DIR}/{path.name}"
        try:
            rows_on_disk = existing_row_count(path)
            frame = read_store(path, columns=CAPTURE_COLUMNS, for_append=True)
            if len(frame) < rows_on_disk:
                raise CorruptStoreError(
                    f"holds {rows_on_disk} row(s) and parses to only {len(frame)}"
                )
            missing = [c for c in CAPTURE_COLUMNS if c not in frame.columns]
            if missing and not frame.empty:
                raise CorruptStoreError(f"lacks column(s): {', '.join(missing)}")
        except (CorruptStoreError, ValueError) as exc:
            damaged[name] = f"{_short(exc, work)}; {REPAIR}"
            continue
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
        return EXIT_REFUSED
    damaged: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        try:
            fetch_tip(work, remote, token)
            rows = read_day_files(work, damaged)
        except NoBranch:
            _say("The private closing-line store has no main branch yet, so it holds no captures.")
            return EXIT_EMPTY
        except Refused as exc:
            _error(str(exc))
            return EXIT_REFUSED
        except OSError as exc:
            _error(f"The private closing-line store could not be read: {exc}")
            return EXIT_FAILED
    for name, reason in sorted(damaged.items()):
        _error(
            f"The private closing-line store's {name} is damaged ({reason}). "
            "Its rows are not scored; every other day is."
        )
    if rows.empty:
        if damaged:
            return EXIT_DAMAGED
        _say("The private closing-line store holds no captures yet.")
        return EXIT_EMPTY
    _write_csv(rows, out)
    _say(f"Read {len(rows)} capture row(s) from the private closing-line store.")
    return EXIT_DAMAGED if damaged else EXIT_OK


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
    sub.choices["pull"].add_argument("--out", required=True)
    args = parser.parse_args(argv)
    return push(args) if args.command == "push" else pull(args)


if __name__ == "__main__":
    raise SystemExit(main())
