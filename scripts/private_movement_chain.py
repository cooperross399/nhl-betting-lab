#!/usr/bin/env python3
"""Keep Line Movement's capture chain in the PRIVATE repository, and read it back.

    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py pull --dest data/processed
    NHL_CHAIN_FALLBACK_KEY=... GH_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py unseal --dest data/processed
    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py push --processed-dir data/processed
    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py verify --processed-dir data/processed
    NHL_CHAIN_FALLBACK_KEY=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_movement_chain.py seal --processed-dir data/processed --out "$RUNNER_TEMP/sealed/round.enc"

## Why

Line Movement keeps every book's every rung, five rounds a day, in
`line_movement/<league day>.csv`, beside `deployment/` and
`line_combinations/`. Until 2026-10-02 the only copy was the public
`line-movement` artifact, and closing prices are a subset of it, so Cooper's
rule (closing-line data is never published publicly, 2026-10-01) was not met
while it stayed public. Cooper chose a staged move (2026-10-02):

1. **Stage one (#289): dual-write.** Each round restored from the public
   artifact, folded in this private copy, pushed here, checked the tip, and
   still uploaded publicly (7-day retention instead of 90).
2. **Stage two: this copy is the only one.** Each round restores from here
   (`pull`) and folds in any sealed round (`unseal`); after its captures it
   pushes here (`push`) and checks the tip holds the round (`verify`). If
   either fails, the round is encrypted with Cooper's key (`seal`) into a
   7-day artifact nobody without the key can read, and the next round's
   `unseal` brings it home. Closing Lines and Gameday Refresh's CLV step
   `pull` this copy too. Nothing uploads the chain publicly.

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

push: 0 pushed or nothing new; 1 GitHub unreachable after the retries, or a
local error (named as which); 2 a day file that could not be merged (named,
and this run's copy kept on the branch as a sidecar
`unmerged/<store>/<day>/<blob>.csv`; every other file is still pushed);
3 no token; 5 refused (a public target, a store the API does not call
private, a token GitHub turns away, a push a rule declines, or no `movement`
branch: a round never recreates the chain; `--allow-new-chain` seeds one).

pull: 0 folded in (or nothing to fold); 2 a file that could not be merged
(named; the copy already on disk is kept); 3 no token; 4 no `movement`
branch (a fault for every caller since the 2026-10-02 seed); 1 unreachable;
5 refused.

verify: 0 the tip holds every row of every local file (as the day file, or
as its kept sidecar); 2 it does not (each file and its missing row count
named); 3, 4, 1 and 5 as for pull.

seal: 0 sealed (only what the tip lacks, when the tip can be listed); 1
openssl failed; 3 no key (unset, or saved as whitespace only); 4 nothing
on disk to seal (said, not an error);
5 a weak key (under 32 characters, or padded with whitespace) or `--out`
inside the workspace.

unseal: 0 every sealed round folded in, already home, or none exist; 1 GitHub
could not be asked for the list after the retries; 2 a sealed round that
could not be downloaded, decrypted or opened, or a sealed copy that could not
be merged (parked under `--dest/unmerged/` for the push to keep; named);
3 sealed rounds exist and there is no key (unset, or whitespace only); 5 the
key is weak.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import private_closing_store as store  # noqa: E402
from restore_state import _records, _rows, union_csv  # noqa: E402

CHAIN_BRANCH = "movement"
CHAIN_SUBJECT = "the private movement chain"
STORES = ("line_movement", "deployment", "line_combinations")
#: Where a day file's copy that cannot be merged with the tip's is kept, on
#: the private branch: `unmerged/<store>/<day>/<blob id>.csv`. Durable and
#: private, instead of a sealed artifact that expires; merged by hand.
UNMERGED = "unmerged"
SIDECAR = re.compile(r"^unmerged/(line_movement|deployment|line_combinations)/\d{4}-\d{2}-\d{2}/[0-9a-f]{40,64}\.csv$")
DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$")
PUSH_ATTEMPTS = 5
TIP_REF = "refs/chain-tip"

EXIT_OK = store.EXIT_OK
EXIT_FAILED = store.EXIT_FAILED
EXIT_DAMAGED = store.EXIT_DAMAGED
EXIT_NO_TOKEN = store.EXIT_NO_TOKEN
EXIT_EMPTY = store.EXIT_EMPTY
EXIT_REFUSED = store.EXIT_REFUSED

#: The Actions secret the sealed fallback is encrypted with (Cooper's key).
KEY_ENV = "NHL_CHAIN_FALLBACK_KEY"
#: Every sealed fallback artifact is named this, then the run attempt.
SEALED_PREFIX = "line-movement-sealed-"
SEALED_FILE = "round.enc"
OPENSSL_CIPHER = ["-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-md", "sha256"]


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
    Its commit, or None when the repository answers and has no movement
    branch (since 2026-10-02 that means it was deleted or renamed: a fault
    for every caller but a deliberate seed)."""
    if not (work / ".git").exists():
        _ok(_git(["init", "-q"], work))
    listed = _git(["ls-remote", "--heads", remote, f"refs/heads/{CHAIN_BRANCH}"], work)
    if listed.returncode:
        raise store._remote_failure(listed.stderr, token, "list", CHAIN_SUBJECT)
    if not listed.stdout.strip():
        return None
    done = _git(["fetch", "-q", "--depth", "1", remote,
                 f"+refs/heads/{CHAIN_BRANCH}:{TIP_REF}"], work)
    if done.returncode:
        raise store._remote_failure(done.stderr, token, "fetch", CHAIN_SUBJECT)
    return _ok(_git(["rev-parse", TIP_REF], work)).strip()


def tip_blobs(work: Path) -> dict[str, str]:
    """path -> blob id, for every day file and every sidecar on the tip."""
    out = _ok(_git(["ls-tree", "-r", TIP_REF, "--", *STORES, UNMERGED], work))
    files = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        kind, sha = meta.split()[1:3]
        folder, _, name = path.partition("/")
        if kind == "blob" and ((folder in STORES and DAY_FILE.match(name)) or SIDECAR.match(path)):
            files[path] = sha
    return files


def tip_files(work: Path) -> dict[str, str]:
    """`store/<day>.csv` -> blob id, for every day file on the tip."""
    return {p: sha for p, sha in tip_blobs(work).items() if not p.startswith(UNMERGED + "/")}


def sidecar_path(rel: str, sha: str) -> str:
    """Where a day file's unmergeable copy with blob `sha` is kept."""
    return f"{UNMERGED}/{rel[:-len('.csv')]}/{sha}.csv"


def held(rel: str, sha: str, on_tip: dict[str, str]) -> bool:
    """The tip holds this exact copy: a day file as itself or as its kept
    sidecar, a sidecar as itself."""
    if SIDECAR.match(rel):
        return rel in on_tip
    return on_tip.get(rel) == sha or sidecar_path(rel, sha) in on_tip


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


def local_sidecars(processed: Path) -> dict[str, Path]:
    """Sidecars parked under `processed/unmerged` (by unseal) -> path."""
    root = processed / UNMERGED
    if not root.is_dir():
        return {}
    found = {}
    for path in sorted(root.rglob("*.csv")):
        rel = path.relative_to(processed).as_posix()
        if SIDECAR.match(rel):
            found[rel] = path
    return found


def blob_of(work: Path, path: Path, *, write: bool = False) -> str:
    """The blob id of a file on disk. Resolved first: git runs inside the
    scratch repository `work`, so a relative path (the workflow passes
    `data/processed`) would be looked up there, not where it lives. That
    turned every push, check and pull red on 2026-10-05, the first rounds
    with a working token."""
    target = str(Path(path).resolve())
    return _ok(_git(["hash-object", *(["-w"] if write else []), "--", target], work)).strip()


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
    parked = local_sidecars(processed)
    if not local and not parked:
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
                if tip is None and not args.allow_new_chain:
                    _error(f"The private repository has no `{CHAIN_BRANCH}` branch. The chain has "
                           "existed since 2026-10-02, so it was deleted or renamed: restore it from "
                           "its history rather than let this round start a thin one. (A first "
                           "seed passes --allow-new-chain.)")
                    return EXIT_REFUSED
                on_tip = tip_blobs(work) if tip else {}
                if tip:
                    _ok(_git(["read-tree", TIP_REF], work, env=env))

                def stage(path_in_tree: str, sha: str) -> None:
                    _ok(_git(["update-index", "--add", "--cacheinfo",
                              f"100644,{sha},{path_in_tree}"], work, env=env))
                    changed.append(path_in_tree)

                for rel, path in local.items():
                    local_sha = blob_of(work, path)
                    if held(rel, local_sha, on_tip):
                        continue
                    if rel in on_tip:
                        with tempfile.TemporaryDirectory() as scratch:
                            merged, added = _merged(work, on_tip[rel], path, Path(scratch))
                            if merged is None:
                                side = sidecar_path(rel, blob_of(work, path, write=True))
                                damaged[rel] = (
                                    "the tip's copy and this run's could not be merged (a "
                                    "different header, or a parse that disagrees with its line "
                                    f"count). This run's copy is kept on the private chain as {side}; "
                                    "merge the two by hand")
                                stage(side, local_sha)
                                continue
                            if not added:
                                continue
                            stage(rel, blob_of(work, merged, write=True))
                    else:
                        stage(rel, blob_of(work, path, write=True))
                for rel, path in parked.items():
                    if rel not in on_tip:
                        stage(rel, blob_of(work, path, write=True))
            except store.Refused as exc:
                _error(str(exc))
                return EXIT_REFUSED
            except store.Unreachable as exc:
                _error(f"The private movement chain could not be reached: {exc}")
                return EXIT_FAILED
            except OSError as exc:
                _error(f"A local error stopped the push (not GitHub): {exc}")
                return EXIT_FAILED
            for rel, why in sorted(damaged.items()):
                _error(f"{rel} could not be merged into the private chain: {why}. "
                       "Every other file was pushed.")
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
            failure = store._remote_failure(done.stderr, token, "push to", CHAIN_SUBJECT)
            if isinstance(failure, store.Refused):
                _error(str(failure))
                return EXIT_REFUSED
            if attempt < PUSH_ATTEMPTS:
                _say(f"Push rejected (attempt {attempt}); refetching and re-merging. {failure}")
                sleep(2 ** attempt)
    _error(f"Could not push the private movement chain after {PUSH_ATTEMPTS} attempts; "
           "the next step seals this round so the next run can bring it home.")
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
                _error("The private repository has no `movement` branch; the chain has existed "
                       "since 2026-10-02, so it was deleted or renamed. Nothing was folded in.")
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
    parked = local_sidecars(Path(args.processed_dir))
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
            on_tip = tip_blobs(work)
            day_files_on_tip = [p for p in on_tip if not p.startswith(UNMERGED + "/")]
            if not local and day_files_on_tip:
                _error(f"This run's folder holds no movement day file while the private "
                       f"chain holds {len(day_files_on_tip)}; nothing here was checked.")
                return EXIT_DAMAGED
            for rel in parked:
                if rel not in on_tip:
                    missing[rel] = _rows(parked[rel])
            for rel, path in local.items():
                if held(rel, blob_of(work, path), on_tip):
                    # Byte for byte the tip's copy, or its kept sidecar: held,
                    # whatever it holds.
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
            what = ("differs from the private tip and could not be read on disk" if count < 0
                    else f"{count} row(s) missing from the private tip")
            _error(f"Private chain check: {rel}: {what}.")
        line = (f"Private chain check FAILED: {len(missing)} of {len(local)} file(s) on this "
                "run's disk are not fully held by the private tip.")
    else:
        line = (f"Private chain check passed: the private tip holds every row of all "
                f"{len(local)} file(s) ({rows} rows) on this run's disk.")
    _say(line)
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return EXIT_DAMAGED if missing else EXIT_OK


def _openssl(args: list[str], source: Path, target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["openssl", "enc", *args, *OPENSSL_CIPHER, "-pass", f"env:{KEY_ENV}",
         "-in", str(source), "-out", str(target)],
        capture_output=True, text=True,
    )


#: The fallback key is a passphrase into PBKDF2; the recipe in CLAUDE.md
#: (`openssl rand -base64 48`) gives 64 characters.
MIN_KEY_CHARS = 32


def key_problem() -> str | None:
    """None for a usable fallback key, else why not. openssl reads the raw
    environment value, so surrounding whitespace is refused rather than
    silently made part of the key."""
    raw = os.environ.get(KEY_ENV, "")
    if not raw.strip():
        return f"{KEY_ENV} is not set"
    if raw != raw.strip():
        return f"{KEY_ENV} has leading or trailing whitespace"
    if len(raw) < MIN_KEY_CHARS:
        return f"{KEY_ENV} is shorter than {MIN_KEY_CHARS} characters"
    return None


def key_exit() -> int:
    """The exit for a key `key_problem` refused: a key that is unset or blank
    is a missing secret (3), as its message says; a weak one is refused (5)."""
    return EXIT_NO_TOKEN if not os.environ.get(KEY_ENV, "").strip() else EXIT_REFUSED


def seal(args: argparse.Namespace) -> int:
    """Encrypt this round's three stores into `--out`, outside the workspace.

    Only when the private push failed or the check found the tip short: the
    private repository is the round's only home in stage two, and rows that
    reach neither it nor this sealed copy are gone. Only what the tip lacks is
    sealed when the tip can be listed (else everything on disk). AES-256,
    PBKDF2-SHA256 at 200k iterations, Cooper's key (NHL_CHAIN_FALLBACK_KEY,
    at least 32 characters, no surrounding whitespace); a weak or missing key
    seals nothing, and the run says so.
    """
    problem = key_problem()
    if problem:
        _error(f"This round cannot be sealed: {problem}. The rows the private chain lacks are on no copy.")
        return key_exit()
    out = Path(args.out)
    try:
        store.refuse_an_out_inside_the_workspace(out)
    except store.Refused as exc:
        _error(str(exc))
        return EXIT_REFUSED
    processed = Path(args.processed_dir)
    local = {**local_files(processed), **local_sidecars(processed)}
    if not local:
        _say("No movement day file on disk: this round restored nothing and captured "
             "nothing, so no captured row is outside the private chain. Nothing to seal.")
        return EXIT_EMPTY
    # Only what the private tip lacks, when the tip can be read: a seal holding
    # the whole season would grow to the chain's size, and every later round
    # downloads it. With no listing, everything is sealed.
    on_tip = _tip_listing(args)
    if on_tip:
        try:
            with tempfile.TemporaryDirectory() as scratch_dir:
                git_dir = Path(scratch_dir)
                _ok(_git(["init", "-q"], git_dir))
                lacking = {rel: path for rel, path in local.items()
                           if not held(rel, blob_of(git_dir, path), on_tip)}
        except OSError as exc:
            _say(f"Could not compare this round with the private tip ({exc}); sealing everything.")
            lacking = {}
        # Empty when the tip already holds every file (the push failed after
        # an earlier attempt landed, or the check failed for another reason):
        # everything is sealed then, which costs size and loses nothing.
        if lacking:
            local = lacking
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        bundle = Path(scratch) / "round.tar"
        with tarfile.open(bundle, "w") as tar:
            for rel, path in sorted(local.items()):
                tar.add(path, arcname=rel)
        done = _openssl(["-e", "-salt"], bundle, out)
    if done.returncode:
        out.unlink(missing_ok=True)
        _error(f"Could not seal this round: {done.stderr.strip()}")
        return EXIT_FAILED
    _say(f"Sealed {len(local)} day file(s) into {out.name} for the next round to fold in.")
    return EXIT_OK


GH_ATTEMPTS = 3


def _gh(args: list[str], **kw) -> subprocess.CompletedProcess:
    """A `gh` call tried again after a pause when it fails."""
    for attempt in range(1, GH_ATTEMPTS + 1):
        done = subprocess.run(["gh", *args], **kw)
        if done.returncode == 0 or attempt == GH_ATTEMPTS:
            return done
        sleep(5 * attempt)
    return done


def list_sealed(repo: str) -> list[dict]:
    """Every unexpired sealed fallback artifact this repository's own default
    branch uploaded, oldest first. Fail closed: an artifact whose run names
    no branch, another branch, or code from another repository (a fork's pull
    request runs in this repository's context and could upload the same name
    from a branch it calls main; its head_repository_id is the fork's) is left
    out. The default branch is `main`, as `restore_state.py`'s listing also
    assumes (`--branch main`); NHL_DEFAULT_BRANCH overrides it, for tests or
    a renamed default branch. Raises OSError when GitHub cannot be asked,
    after the retries."""
    default_branch = os.environ.get("NHL_DEFAULT_BRANCH", "").strip() or "main"
    done = _gh(["api", "--paginate", f"repos/{repo}/actions/artifacts?per_page=100",
                "--jq", ".artifacts[]"], capture_output=True, text=True)
    if done.returncode:
        raise OSError(done.stderr.strip() or "gh api failed")
    found = []
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        run = item.get("workflow_run") or {}
        same_repo = (run.get("repository_id") is not None
                     and run.get("repository_id") == run.get("head_repository_id"))
        if (str(item.get("name", "")).startswith(SEALED_PREFIX) and not item.get("expired")
                and run.get("head_branch") == default_branch and same_repo):
            found.append(item)
    return sorted(found, key=lambda a: a.get("created_at", ""))


def download_sealed(repo: str, artifact: dict, target: Path) -> None:
    """The artifact's sealed file, written to `target`. Raises OSError."""
    with tempfile.TemporaryDirectory() as scratch:
        archive = Path(scratch) / "a.zip"
        with archive.open("wb") as handle:
            done = None
            for attempt in range(1, GH_ATTEMPTS + 1):
                handle.seek(0)
                handle.truncate()
                done = subprocess.run(["gh", "api", f"repos/{repo}/actions/artifacts/{artifact['id']}/zip"],
                                      stdout=handle, stderr=subprocess.PIPE)
                if done.returncode == 0:
                    break
                if attempt < GH_ATTEMPTS:
                    sleep(5 * attempt)
        if done.returncode:
            raise OSError(done.stderr.decode(errors="replace").strip() or "download failed")
        with zipfile.ZipFile(archive) as zipped:
            with zipped.open(SEALED_FILE) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)


def _tip_listing(args: argparse.Namespace) -> dict[str, str] | None:
    """The private tip's blobs, to tell a sealed copy already home from one
    that is not; None when there is no token or the tip cannot be read
    (every sealed file is then folded, as it would have been)."""
    token = store._token()
    if not token and not args.remote:
        return None
    remote = args.remote or store.remote_url(args.repo, token)
    try:
        store.refuse_public_target(args.repo, remote)
        with tempfile.TemporaryDirectory() as scratch_dir:
            work = Path(scratch_dir) / "repo"
            work.mkdir()
            return tip_blobs(work) if fetch_chain(work, remote, token) else {}
    except (store.Refused, OSError):
        return None


def unseal(args: argparse.Namespace) -> int:
    """Fold every sealed fallback round into `--dest`, so this round's push
    carries it into the private chain. Each fold is the chain's own union:
    a row already on disk is not added twice. A sealed copy the private tip
    already holds (as the day file or its sidecar) is skipped. A sealed copy
    that cannot be merged with the one on disk is parked as a sidecar under
    `--dest/unmerged/`, which the push keeps on the private branch, so its
    rows never strand in an artifact that expires."""
    repo = args.github_repo or os.environ.get("GITHUB_REPOSITORY", "")
    try:
        sealed = list_sealed(repo)
    except OSError as exc:
        _error(f"Could not list sealed fallback rounds: {exc}")
        return EXIT_FAILED
    if not sealed:
        _say("No sealed fallback round to fold in.")
        return EXIT_OK
    problem = key_problem()
    if problem:
        _error(f"{len(sealed)} sealed fallback round(s) exist and they cannot be opened: {problem}")
        return key_exit()
    on_tip = _tip_listing(args)
    dest = Path(args.dest)
    failed: list[str] = []
    parked: list[str] = []
    recovered = skipped = 0
    for artifact in sealed:
        name = f"{artifact.get('name')} (run {(artifact.get('workflow_run') or {}).get('id')})"
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            try:
                download_sealed(repo, artifact, work / SEALED_FILE)
            except (OSError, KeyError, zipfile.BadZipFile) as exc:
                failed.append(f"{name}: {exc}")
                continue
            done = _openssl(["-d"], work / SEALED_FILE, work / "round.tar")
            if done.returncode:
                failed.append(f"{name}: could not be decrypted ({done.stderr.strip()})")
                continue
            opened = work / "opened"
            try:
                with tarfile.open(work / "round.tar") as tar:
                    members = [m for m in tar.getmembers() if m.isfile()]
                    for member in members:
                        folder, _, file_name = member.name.partition("/")
                        day_file = folder in STORES and DAY_FILE.match(file_name)
                        if ".." in member.name or not (day_file or SIDECAR.match(member.name)):
                            raise tarfile.TarError(f"unexpected member {member.name}")
                    tar.extractall(opened, members=members, filter="data")
            except tarfile.TarError as exc:
                failed.append(f"{name}: {exc}")
                continue
            git_dir = work / "git"
            git_dir.mkdir()
            _git(["init", "-q"], git_dir)
            for member in members:
                rel = member.name
                source = opened / rel
                sha = blob_of(git_dir, source)
                target = dest / rel
                if on_tip is not None and held(rel, sha, on_tip):
                    skipped += 1
                    continue
                if SIDECAR.match(rel) or not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    recovered += _rows(target) if not SIDECAR.match(rel) else 0
                    continue
                added = union_csv(source, target)
                if added is None:
                    side = dest / sidecar_path(rel, sha)
                    side.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, side)
                    parked.append(f"{rel} from {name} -> {sidecar_path(rel, sha)}")
                    continue
                recovered += added
    for line in failed:
        _error(f"Sealed fallback round {line}.")
    for line in parked:
        _error(f"A sealed copy could not be merged with the one on disk and is parked for the "
               f"push to keep on the private chain as a sidecar: {line}. Merge it by hand.")
    _say(f"Folded in {len(sealed) - len(failed)} sealed fallback round(s): {recovered} row(s) "
         f"the copy on disk did not have; {skipped} file(s) already home.")
    return EXIT_DAMAGED if failed or parked else EXIT_OK


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
    sub.choices["push"].add_argument(
        "--allow-new-chain", action="store_true",
        help="Create the movement branch when it does not exist (a first seed only).")
    sealer = sub.add_parser("seal")
    sealer.add_argument("--processed-dir", default="data/processed")
    sealer.add_argument("--out", required=True)
    opener = sub.add_parser("unseal")
    opener.add_argument("--dest", default="data/processed")
    opener.add_argument("--github-repo", default="", help="Defaults to $GITHUB_REPOSITORY.")
    for command in (sealer, opener):
        command.add_argument("--repo", default=store.PRIVATE_REPO)
        command.add_argument("--remote", default="", help="A local store, for tests.")
    args = parser.parse_args(argv)
    return {"push": push, "pull": pull, "verify": verify,
            "seal": seal, "unseal": unseal}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
