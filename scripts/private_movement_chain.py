#!/usr/bin/env python3
"""Keep Line Movement's capture chain in the PRIVATE repository, and read it back.

    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py pull --dest data/processed
    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py push --processed-dir data/processed
    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py verify --processed-dir data/processed

## Why

Line Movement keeps every book's every rung, five rounds a day, in
`line_movement/<league day>.csv`, beside `deployment/` and
`line_combinations/`. Until 2026-10-02 the only copy was the public
`line-movement` artifact, and closing prices are a subset of it, so Cooper's
rule (closing-line data is never published publicly, 2026-10-01) was not met
while it stayed public. Cooper chose a staged move (2026-10-02):

1. **This stage: dual-write.** Each round restores from the public artifact as
   before, then folds in this private copy (`pull`); after its captures it
   pushes the three stores here (`push`) and checks that the private tip holds
   every row of what it is about to upload publicly (`verify`). The public
   artifact's retention drops from 90 days to 7.
2. **Next stage, after rounds verify clean:** the public upload is dropped and
   every reader (Line Movement, Closing Lines, Gameday Refresh's CLV step)
   reads this copy.

## Where

Branch `movement` of `cooperross399/nhl-closing-lines`, laid out as
`data/processed` is: `line_movement/`, `deployment/`, `line_combinations/`,
one file per New York league day. A branch of its own, not `main`: the
closing-line store's `captures/<UTC day>.csv` files have the same names and
the same capture columns, and a movement file read as one would score every
book's row instead of one best price per selection, the flattering basis
`closing_lines.load_movement_captures` exists to avoid. Closing Lines pushes
`main` and this pushes `movement`, so the two never race. The refusals are
`private_closing_store`'s: this public repository is refused by name, and the
GitHub API must say `"private": true` before every push.

## How it merges: never a row lost, duplicates kept

Every merge is `restore_state.union_csv`, the union the public chain's restore
already uses: a multiset union, so two identical rows from one capture stay
two rows (3.7% of the movement rows measured on 2026-10-02 are exact
duplicates, and `merge_capture_store.merge` would drop them), and a file whose
parse disagrees with its own line count is never merged. A day file is read
and written only when its bytes differ from the tip's (compared by blob hash),
so a round touches the day files it appended to and nothing else, and nothing
is checked out: the tip is fetched at depth 1 and read and written with git
plumbing.

## Exit codes

push: 0 pushed or nothing new; 1 GitHub unreachable after the retries; 2 a day
file that could not be merged (named; every other file is still pushed);
3 no token; 5 refused (a public target, a store the API does not call
private, a token GitHub turns away, a push a rule declines).

pull: 0 folded in (or nothing to fold); 2 a file that could not be merged
(named; the copy already on disk is kept); 3 no token; 4 no chain yet (no
`movement` branch); 1 unreachable; 5 refused.

verify: 0 the tip holds every row of every local file; 2 it does not (each
file and its missing row count named); 3, 4, 1 and 5 as for pull.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import private_closing_store as store  # noqa: E402
from restore_state import _records, _rows, union_csv  # noqa: E402

CHAIN_BRANCH = "movement"
STORES = ("line_movement", "deployment", "line_combinations")
DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$")
PUSH_ATTEMPTS = 5
TIP_REF = "refs/chain-tip"

EXIT_OK = store.EXIT_OK
EXIT_FAILED = store.EXIT_FAILED
EXIT_DAMAGED = store.EXIT_DAMAGED
EXIT_NO_TOKEN = store.EXIT_NO_TOKEN
EXIT_EMPTY = store.EXIT_EMPTY
EXIT_REFUSED = store.EXIT_REFUSED


def _say(message: str) -> None:
    print(message, flush=True)


def _error(message: str) -> None:
    print(f"::error::{message}", flush=True)


def sleep(seconds: float) -> None:
    """Between push attempts. Tests replace it."""
    time.sleep(seconds)


def _git(args: list[str], cwd: Path, *, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0",
             "GIT_AUTHOR_NAME": "Line Movement", "GIT_AUTHOR_EMAIL": "actions@github.com",
             "GIT_COMMITTER_NAME": "Line Movement", "GIT_COMMITTER_EMAIL": "actions@github.com",
             **(env or {})},
    )


def _ok(done: subprocess.CompletedProcess) -> str:
    if done.returncode:
        raise OSError(done.stderr.strip() or f"git exited {done.returncode}")
    return done.stdout


FETCH_ATTEMPTS = 3


def fetch_chain(work: Path, remote: str, token: str) -> str | None:
    """`fetch_chain_once`, tried again after a pause when GitHub could not be
    reached; a refusal is final at once."""
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return fetch_chain_once(work, remote, token)
        except store.Unreachable as exc:
            if attempt == FETCH_ATTEMPTS:
                raise
            _say(f"Could not reach the private chain (attempt {attempt}); trying again. {exc}")
            sleep(5 * attempt)
    return None


def fetch_chain_once(work: Path, remote: str, token: str) -> str | None:
    """Fetch the chain's tip into `work` (depth 1, nothing checked out).
    Its commit, or None when the repository answers and has no chain yet."""
    if not (work / ".git").exists():
        _ok(_git(["init", "-q"], work))
    listed = _git(["ls-remote", "--heads", remote, f"refs/heads/{CHAIN_BRANCH}"], work)
    if listed.returncode:
        raise store._remote_failure(listed.stderr, token, "list")
    if not listed.stdout.strip():
        return None
    done = _git(["fetch", "-q", "--depth", "1", remote,
                 f"+refs/heads/{CHAIN_BRANCH}:{TIP_REF}"], work)
    if done.returncode:
        raise store._remote_failure(done.stderr, token, "fetch")
    return _ok(_git(["rev-parse", TIP_REF], work)).strip()


def tip_files(work: Path) -> dict[str, str]:
    """`store/<day>.csv` -> blob id, for every day file on the tip."""
    out = _ok(_git(["ls-tree", "-r", TIP_REF, "--", *STORES], work))
    files = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        kind, sha = meta.split()[1:3]
        folder, _, name = path.partition("/")
        if kind == "blob" and folder in STORES and DAY_FILE.match(name):
            files[path] = sha
    return files


def local_files(processed: Path) -> dict[str, Path]:
    """`store/<day>.csv` -> path, for every day file under `processed`."""
    files = {}
    for folder in STORES:
        root = processed / folder
        if root.is_dir():
            for path in sorted(root.glob("*.csv")):
                if DAY_FILE.match(path.name):
                    files[f"{folder}/{path.name}"] = path
    return files


def blob_of(work: Path, path: Path, *, write: bool = False) -> str:
    return _ok(_git(["hash-object", *(["-w"] if write else []), "--", str(path)], work)).strip()


def blob_to(work: Path, sha: str, target: Path) -> None:
    """Write a blob to `target` whole or not at all: through a temp file and
    a rename, so a step cut off mid-copy never leaves a truncated day file
    for the capture to append to."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    try:
        with partial.open("wb") as handle:
            done = subprocess.run(["git", "cat-file", "blob", sha], cwd=work, stdout=handle,
                                  stderr=subprocess.PIPE)
        if done.returncode:
            raise OSError(done.stderr.decode(errors="replace").strip())
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def _setup(args: argparse.Namespace, *, writes: bool) -> tuple[str, str] | int:
    token = store._token()
    if not token and not args.remote:
        (_error if writes else _say)(
            f"{store.TOKEN_ENV} is not set, so the private movement chain cannot be "
            f"{'written' if writes else 'read'}."
        )
        return EXIT_NO_TOKEN
    remote = args.remote or store.remote_url(args.repo, token)
    try:
        store.refuse_public_target(args.repo, remote)
        if writes:
            store.require_private(args.repo, token)
    except store.Refused as exc:
        _error(str(exc))
        return EXIT_REFUSED
    except store.Unreachable as exc:
        _error(f"Refusing to push without confirming the store is private: {exc}")
        return EXIT_FAILED
    return token, remote


def _merged(work: Path, sha: str, local: Path, scratch: Path) -> tuple[Path | None, int]:
    """The tip's copy with every row `local` adds (union_csv, the tip as the
    older copy), written in `scratch`. (path, rows the local copy added), or
    (None, 0) when the two cannot be merged."""
    older = scratch / "tip.csv"
    newer = scratch / "merged.csv"
    blob_to(work, sha, older)
    shutil.copyfile(local, newer)
    added = union_csv(older, newer)
    if added is None:
        return None, 0
    return newer, _rows(newer) - _rows(older)


def push(args: argparse.Namespace) -> int:
    setup = _setup(args, writes=True)
    if isinstance(setup, int):
        return setup
    token, remote = setup
    processed = Path(args.processed_dir)
    local = local_files(processed)
    if not local:
        _say("No movement day file on disk; nothing to push.")
        return EXIT_OK
    stamp = store.utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as scratch_dir:
        work = Path(scratch_dir) / "repo"
        work.mkdir()
        for attempt in range(1, PUSH_ATTEMPTS + 1):
            damaged: dict[str, str] = {}
            changed: list[str] = []
            index = Path(scratch_dir) / f"index-{attempt}"
            env = {"GIT_INDEX_FILE": str(index)}
            try:
                tip = fetch_chain(work, remote, token)
                on_tip = tip_files(work) if tip else {}
                if tip:
                    _ok(_git(["read-tree", TIP_REF], work, env=env))
                for rel, path in local.items():
                    if on_tip.get(rel) == blob_of(work, path):
                        continue
                    source = path
                    if rel in on_tip:
                        with tempfile.TemporaryDirectory() as scratch:
                            merged, added = _merged(work, on_tip[rel], path, Path(scratch))
                            if merged is None:
                                damaged[rel] = ("the tip's copy and this run's could not be "
                                                "merged (a different header, or a parse that "
                                                "disagrees with its line count)")
                                continue
                            if not added:
                                continue
                            sha = blob_of(work, merged, write=True)
                    else:
                        sha = blob_of(work, source, write=True)
                    _ok(_git(["update-index", "--add", "--cacheinfo", f"100644,{sha},{rel}"],
                             work, env=env))
                    changed.append(rel)
            except store.Refused as exc:
                _error(str(exc))
                return EXIT_REFUSED
            except OSError as exc:
                _error(f"The private movement chain could not be reached: {exc}")
                return EXIT_FAILED
            for rel, why in sorted(damaged.items()):
                _error(f"{rel} could not be pushed to the private chain: {why}. "
                       "Every other file was.")
            outcome = EXIT_DAMAGED if damaged else EXIT_OK
            if not changed:
                _say("The private chain already holds every row on disk. Nothing pushed.")
                return outcome
            tree = _ok(_git(["write-tree"], work, env=env)).strip()
            parent = ["-p", tip] if tip else []
            commit = _ok(_git(["commit-tree", tree, *parent, "-m",
                               f"round {stamp} ({len(changed)} file(s))"], work)).strip()
            done = _git(["push", "-q", remote, f"{commit}:refs/heads/{CHAIN_BRANCH}"], work)
            if done.returncode == 0:
                _say(f"Pushed {len(changed)} file(s) to the private chain "
                     f"({', '.join(sorted(changed)[:6])}{', ...' if len(changed) > 6 else ''}).")
                return outcome
            failure = store._remote_failure(done.stderr, token, "push to")
            if isinstance(failure, store.Refused):
                _error(str(failure))
                return EXIT_REFUSED
            if attempt < PUSH_ATTEMPTS:
                _say(f"Push rejected (attempt {attempt}); refetching and re-merging. {failure}")
                sleep(2 ** attempt)
    _error(f"Could not push the private movement chain after {PUSH_ATTEMPTS} attempts. "
           "This round is still in the public line-movement artifact.")
    return EXIT_FAILED


def pull(args: argparse.Namespace) -> int:
    setup = _setup(args, writes=False)
    if isinstance(setup, int):
        return setup
    token, remote = setup
    dest = Path(args.dest)
    with tempfile.TemporaryDirectory() as scratch_dir:
        work = Path(scratch_dir) / "repo"
        work.mkdir()
        try:
            tip = fetch_chain(work, remote, token)
            if tip is None:
                _say("No private movement chain yet; nothing to fold in.")
                return EXIT_EMPTY
            on_tip = tip_files(work)
            recovered, copied, not_merged = 0, 0, []
            for rel, sha in sorted(on_tip.items()):
                target = dest / rel
                if not target.exists():
                    blob_to(work, sha, target)
                    copied += 1
                    recovered += _rows(target)
                    continue
                if blob_of(work, target) == sha:
                    continue
                with tempfile.TemporaryDirectory() as scratch:
                    older = Path(scratch) / "tip.csv"
                    blob_to(work, sha, older)
                    added = union_csv(older, target)
                if added is None:
                    not_merged.append(rel)
                    continue
                recovered += added
        except store.Refused as exc:
            _error(str(exc))
            return EXIT_REFUSED
        except OSError as exc:
            _error(f"The private movement chain could not be read: {exc}")
            return EXIT_FAILED
    for rel in not_merged:
        _error(f"{rel} from the private chain could not be merged with the copy on disk "
               "(a different header, or a parse that disagrees with its line count); "
               "the copy on disk is kept.")
    _say(f"Folded in the private movement chain: {copied} file(s) copied, "
         f"{recovered} row(s) the copy on disk did not have.")
    return EXIT_DAMAGED if not_merged else EXIT_OK


def verify(args: argparse.Namespace) -> int:
    setup = _setup(args, writes=False)
    if isinstance(setup, int):
        return setup
    token, remote = setup
    local = local_files(Path(args.processed_dir))
    missing: dict[str, int] = {}
    rows = 0
    with tempfile.TemporaryDirectory() as scratch_dir:
        work = Path(scratch_dir) / "repo"
        work.mkdir()
        try:
            tip = fetch_chain(work, remote, token)
            if tip is None:
                _error("There is no private movement chain to verify against.")
                return EXIT_EMPTY
            on_tip = tip_files(work)
            if not local and on_tip:
                _error(f"This run's folder holds no movement day file while the private "
                       f"chain holds {len(on_tip)}; nothing here was checked.")
                return EXIT_DAMAGED
            for rel, path in local.items():
                if on_tip.get(rel) == blob_of(work, path):
                    # Byte for byte the tip's copy: held, whatever it holds.
                    rows += _rows(path)
                    continue
                theirs = _records(path)
                if theirs is None:
                    missing[rel] = -1
                    continue
                rows += len(theirs[1])
                if rel not in on_tip:
                    missing[rel] = len(theirs[1])
                    continue
                tip_copy = Path(scratch_dir) / "tip.csv"
                blob_to(work, on_tip[rel], tip_copy)
                ours = _records(tip_copy)
                if ours is None or ours[0] != theirs[0]:
                    missing[rel] = len(theirs[1])
                    continue
                short = Counter(map(tuple, theirs[1])) - Counter(map(tuple, ours[1]))
                if short:
                    missing[rel] = sum(short.values())
        except store.Refused as exc:
            _error(str(exc))
            return EXIT_REFUSED
        except OSError as exc:
            _error(f"The private movement chain could not be read: {exc}")
            return EXIT_FAILED
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if missing:
        for rel, count in sorted(missing.items()):
            what = "could not be read on disk" if count < 0 else f"{count} row(s) missing from the private tip"
            _error(f"Private chain check: {rel}: {what}.")
        line = (f"Private chain check FAILED: {len(missing)} of {len(local)} file(s) short "
                "of what this run uploads publicly.")
    else:
        line = (f"Private chain check passed: the private tip holds every row of all "
                f"{len(local)} file(s) ({rows} rows) this run uploads publicly.")
    _say(line)
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return EXIT_DAMAGED if missing else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("push", "pull", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=store.PRIVATE_REPO)
        command.add_argument("--remote", default="", help="A local store, for tests.")
    sub.choices["push"].add_argument("--processed-dir", default="data/processed")
    sub.choices["verify"].add_argument("--processed-dir", default="data/processed")
    sub.choices["pull"].add_argument("--dest", default="data/processed")
    args = parser.parse_args(argv)
    return {"push": push, "pull": pull, "verify": verify}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
