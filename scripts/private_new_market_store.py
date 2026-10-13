#!/usr/bin/env python3
"""Keep the new markets' bought and captured prices in a PRIVATE repository.

    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_new_market_store.py pull --prices-dir "$RUNNER_TEMP/private-new-markets"
    NHL_CLOSING_LINES_TOKEN=... PYTHONPATH=src .venv/bin/python \\
        scripts/private_new_market_store.py push --prices-dir "$RUNNER_TEMP/private-new-markets"

## Why

This repository is public, and The Odds API's terms forbid redistributing
their data as downloadable files. The responses `buy_new_market_prices.py`
and `capture_new_market_prices.py` cache are that data, so they never sit on
a branch, release, Pages site or artifact of this repository. They live on
branch `new-markets` of `cooperross399/nhl-closing-lines`, the private
repository that already holds the closing-line store (`main`) and the
movement chain (`movement`), and on a runner only in its temp directory.
`tests/test_closing_prices_never_reach_the_public_repo.py` holds the
workflow side of that.

## The refusals, as `private_closing_store.py` makes them

1. The target is never the public lab, by exact name, nor the repository the
   run is in; `--remote` (tests only) is accepted only as a local path not
   named for a public lab, or a canonical github.com URL naming exactly the
   checked repository.
2. Before every push the GitHub API must answer `"private": true` for it.
3. `pull` refuses a `--prices-dir` inside `$GITHUB_WORKSPACE`, because a
   workspace folder can be swept into a public artifact.

## Layout

`raw/<path under --prices-dir>.json.gz`, one gzip file per cached response
(`raw/historical/<event>_<instant>_<markets>.json.gz`,
`raw/live/<league day>/...`). A response is immutable: a path the branch
already holds is never rewritten, so a push only ever adds files, and two
runs that bought the same response cannot disagree about it.

## Exit codes

0 pushed, pulled, or nothing new; 1 GitHub could not be reached; 3
`NHL_CLOSING_LINES_TOKEN` is not set; 4 (pull) the branch does not exist yet,
which holds nothing; 5 refused (a public target, a repository the API does not
call private, a token GitHub turns away, a `--prices-dir` inside the
workspace, or a push to a branch that does not exist without
`--allow-new-branch`, which only a first, deliberate seed passes).
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import private_closing_store as store  # noqa: E402

PRIVATE_REPO = store.PRIVATE_REPO
TOKEN_ENV = store.TOKEN_ENV
BRANCH = "new-markets"
STORE_DIR = "raw"
PUSH_ATTEMPTS = 3

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_TOKEN = 3
EXIT_EMPTY = 4
EXIT_REFUSED = 5

Refused = store.Refused
Unreachable = store.Unreachable


def repo_is_private(repo: str, token: str) -> bool:
    """The GitHub API's answer, as the closing store asks it. Tests replace it."""
    return store.repo_is_private(repo, token)


def require_private(repo: str, token: str) -> None:
    try:
        private = repo_is_private(repo, token)
    except ValueError as exc:
        raise Unreachable(f"GitHub's answer about {repo} was not JSON: {exc}") from exc
    if not private:
        raise Refused(
            f"{repo} is not private. Refusing to write bought odds to it: the "
            "provider's terms forbid publishing them."
        )


def _git(args: list[str], cwd: Path, *, index: Path | None = None, input=None, binary: bool = False):
    """git in `cwd`, never prompting; `index` names a scratch index file."""
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "New Market Prices",
        "GIT_AUTHOR_EMAIL": "actions@github.com",
        "GIT_COMMITTER_NAME": "New Market Prices",
        "GIT_COMMITTER_EMAIL": "actions@github.com",
    }
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, input=input, capture_output=True, text=not binary
    )


def _gzip(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
        handle.write(data)
    return buffer.getvalue()


def local_responses(prices_dir: Path) -> dict[str, Path]:
    """Every cached response under `prices_dir`, keyed by its store path."""
    found: dict[str, Path] = {}
    if not prices_dir.is_dir():
        return found
    for path in sorted(prices_dir.rglob("*.json")):
        relative = path.relative_to(prices_dir).as_posix()
        found[f"{STORE_DIR}/{relative}.gz"] = path
    return found


def _branch_exists(work: Path, remote: str, token: str) -> bool:
    listed = _git(["ls-remote", "--heads", remote, f"refs/heads/{BRANCH}"], work)
    if listed.returncode:
        raise store._remote_failure(listed.stderr, token, "list", "the new-market store")  # noqa: SLF001
    return bool(listed.stdout.strip())


def _fetch(work: Path, remote: str, token: str, *, blobs: bool) -> str:
    """The branch tip's commit, fetched shallow into `work` (trees only unless `blobs`)."""
    options = ["fetch", "-q", "--depth", "1"]
    if not blobs:
        options.append("--filter=blob:none")
    done = _git([*options, remote, f"+refs/heads/{BRANCH}:refs/store-tip"], work)
    if done.returncode:
        raise store._remote_failure(done.stderr, token, "fetch", "the new-market store")  # noqa: SLF001
    return _git(["rev-parse", "refs/store-tip"], work).stdout.strip()


def _init(work: Path) -> None:
    if not (work / ".git").exists():
        done = _git(["init", "-q"], work)
        if done.returncode:
            raise OSError(done.stderr.strip())


def push(args: argparse.Namespace) -> int:
    token = store._token()  # noqa: SLF001
    if not token and not args.remote:
        store._error(f"{TOKEN_ENV} is not set, so the private new-market store cannot be written.")  # noqa: SLF001
        return EXIT_NO_TOKEN
    remote = args.remote or store.remote_url(args.repo, token)
    try:
        store.refuse_public_target(args.repo, remote)
        require_private(args.repo, token)
    except Refused as exc:
        store._error(str(exc))  # noqa: SLF001
        return EXIT_REFUSED
    except Unreachable as exc:
        store._error(f"Refusing to push without confirming the store is private: {exc}")  # noqa: SLF001
        return EXIT_FAILED
    mine = local_responses(Path(args.prices_dir))
    if not mine:
        print("No cached response to push.")
        return EXIT_OK
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        for attempt in range(1, PUSH_ATTEMPTS + 1):
            try:
                _init(work)
                exists = _branch_exists(work, remote, token)
                if not exists and not args.allow_new_branch:
                    store._error(  # noqa: SLF001
                        f"{args.repo} has no {BRANCH} branch. Refusing to create it on an "
                        "ordinary run; seed it once with --allow-new-branch."
                    )
                    return EXIT_REFUSED
                tip = _fetch(work, remote, token, blobs=False) if exists else ""
            except Refused as exc:
                store._error(str(exc))  # noqa: SLF001
                return EXIT_REFUSED
            except OSError as exc:
                store._error(f"The private new-market store could not be reached: {exc}")  # noqa: SLF001
                return EXIT_FAILED
            index = work / ".git" / "store-index"
            index.unlink(missing_ok=True)
            held: set[str] = set()
            if tip:
                _git(["read-tree", tip], work, index=index)
                listed = _git(["ls-files"], work, index=index)
                held = set(listed.stdout.split())
            new = {name: path for name, path in mine.items() if name not in held}
            if not new:
                print(f"Nothing pushed: {args.repo}:{BRANCH} already holds all {len(mine)} response(s).")
                return EXIT_OK
            entries = []
            for name, path in sorted(new.items()):
                blob = _git(["hash-object", "-w", "--stdin"], work, input=_gzip(path.read_bytes()), binary=True)
                if blob.returncode:
                    store._error(f"Could not store {name}: {blob.stderr.decode(errors='replace').strip()}")  # noqa: SLF001
                    return EXIT_FAILED
                entries.append(f"100644 {blob.stdout.decode().strip()}\t{name}")
            done = _git(["update-index", "--add", "--index-info"], work, index=index, input="\n".join(entries) + "\n")
            if done.returncode:
                store._error(f"Could not stage the responses: {done.stderr.strip()}")  # noqa: SLF001
                return EXIT_FAILED
            tree = _git(["write-tree"], work, index=index).stdout.strip()
            parents = ["-p", tip] if tip else []
            commit = _git(
                ["commit-tree", tree, *parents, "-m", f"new-market prices {stamp} ({len(new)} response(s))"], work
            )
            if commit.returncode:
                store._error(f"Could not commit: {commit.stderr.strip()}")  # noqa: SLF001
                return EXIT_FAILED
            done = _git(["push", "-q", remote, f"{commit.stdout.strip()}:refs/heads/{BRANCH}"], work)
            if done.returncode == 0:
                print(f"Pushed {len(new)} response(s) to {args.repo}:{BRANCH} (attempt {attempt}).")
                return EXIT_OK
            failure = store._remote_failure(done.stderr, token, "push to", "the new-market store")  # noqa: SLF001
            if isinstance(failure, Refused):
                store._error(str(failure))  # noqa: SLF001
                return EXIT_REFUSED
            print(f"Push rejected; refetching the tip. {failure}")
    store._error(f"Could not push the new-market store after {PUSH_ATTEMPTS} attempts.")  # noqa: SLF001
    return EXIT_FAILED


def refuse_inside_the_workspace(path: Path) -> None:
    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if not workspace:
        return
    try:
        path.resolve().relative_to(Path(workspace).resolve())
    except ValueError:
        return
    raise Refused(
        f"Refusing to write bought odds to {path}, inside the workspace: a workspace "
        "folder can be swept into a public artifact."
    )


def pull(args: argparse.Namespace) -> int:
    token = store._token()  # noqa: SLF001
    if not token and not args.remote:
        print(f"{TOKEN_ENV} is not set: no private new-market store is configured.")
        return EXIT_NO_TOKEN
    prices_dir = Path(args.prices_dir)
    remote = args.remote or store.remote_url(args.repo, token)
    try:
        refuse_inside_the_workspace(prices_dir)
        store.refuse_public_target(args.repo, remote)
    except Refused as exc:
        store._error(str(exc))  # noqa: SLF001
        return EXIT_REFUSED
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        try:
            _init(work)
            if not _branch_exists(work, remote, token):
                print(f"{args.repo} has no {BRANCH} branch yet, so it holds no prices.")
                return EXIT_EMPTY
            tip = _fetch(work, remote, token, blobs=True)
        except Refused as exc:
            store._error(str(exc))  # noqa: SLF001
            return EXIT_REFUSED
        except OSError as exc:
            store._error(f"The private new-market store could not be read: {exc}")  # noqa: SLF001
            return EXIT_FAILED
        listed = _git(["ls-tree", "-r", "--name-only", tip, "--", STORE_DIR], work)
        written = 0
        for name in listed.stdout.split():
            if not name.endswith(".json.gz"):
                continue
            target = prices_dir / name[len(STORE_DIR) + 1 : -len(".gz")]
            if target.is_file():
                continue
            blob = _git(["cat-file", "blob", f"{tip}:{name}"], work, binary=True)
            if blob.returncode:
                store._error(f"Could not read {name} from the store.")  # noqa: SLF001
                return EXIT_FAILED
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".partial")
            temporary.write_bytes(gzip.decompress(blob.stdout))
            temporary.replace(target)
            written += 1
    print(f"Pulled {written} response(s) from {args.repo}:{BRANCH} into {prices_dir}.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("push", "pull"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=PRIVATE_REPO)
        command.add_argument("--remote", default="", help="Git URL in place of the repo's GitHub URL (tests).")
        command.add_argument("--prices-dir", required=True)
    sub.choices["push"].add_argument(
        "--allow-new-branch", action="store_true", help="Create the branch if it does not exist (a first seed only)."
    )
    args = parser.parse_args(argv)
    return push(args) if args.command == "push" else pull(args)


if __name__ == "__main__":
    raise SystemExit(main())
