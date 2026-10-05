#!/usr/bin/env python3
"""The site's history only grows: record what was restored, refuse to upload less.

    python scripts/site_history_floor.py record --history dist/data/history \\
        --floor "$RUNNER_TEMP/site-history-floor.json" \\
        --restored-run "$RUNNER_TEMP/site-history.run" --repo "$GITHUB_REPOSITORY" \\
        --deployed-index https://nhl.maverickhightower.com/data/history/index.json
    python scripts/site_history_floor.py check --history dist/data/history \\
        --floor "$RUNNER_TEMP/site-history-floor.json"

Publish Site restores the last publish's `site-history` artifact, builds
today's board into it, and uploads it again as tomorrow's source. Nothing
used to compare the history it uploaded with the one it restored. When the
restore failed on a transient API error, the build froze today's board
alone, `index.json` was rewritten with one entry, the run went green, and
that one-board history became every later run's source: in the failure-shape
audit's replay a three-board history became one, for good, and Results said
"No board was published for this date" about a day whose board was
published with 14 games.

`record` runs straight after the restore, before anything is built, and
writes the floor: a SHA-256 of every frozen board (`<date>[_<slot>].json`,
the published opinion Results settles against) and the name of every line
file. `check` runs before the upload and the deploy and fails (exit 1)
unless every recorded board is still there and byte-identical — a board is
frozen once, the day's first published opinion stands, and nothing may
re-freeze it — every recorded line file is still there, and `index.json`,
which the Archive page reads, still lists every recorded board. A missing
floor record is a refusal, not an empty floor: it means the restore step
never got that far.

**The floor needs a source of its own** (`--restored-run`, `--repo`,
`--deployed-index`). The floor was taken from whatever the restore had just
brought back, so it could catch a loss after the restore and never a restore
that brought back the wrong thing. On 2026-10-05 run 37318279569 (13:37Z)
`gh run list --workflow publish-site.yml --branch main --status success`
listed run 36176147420, the 2026-09-25 publish, first, although run
37224089121 (2026-10-04 18:20Z, artifact 11311226915, 24,647 bytes) was newer
and successful; the same listing later that day was in order. The restore
took the 09-25 history, the floor recorded its 4 boards, the run went green,
and the live Archive went from 13 boards to 5, jumping from 2026-09-25 to
2026-10-05; the 15:31Z publish then restored that thin copy, as it should,
and was green too. So with these flags `record` first refuses (exit 1, no
floor written) unless two sources that are not the run listing agree with
the restore:

* the artifacts API (`actions/artifacts?name=site-history`, every page,
  sorted by `created_at` here, not by GitHub): the newest unexpired
  site-history on main whose run is a successful Publish Site run must be
  the run the restore names. An artifact from a run that did not succeed is
  passed over, as the restore passes over that run; and
* the live site: every board the deployed `index.json` lists must be in the
  restored history. The history only grows, so what the public Archive shows
  is a floor no restore may come in under. A `404` reads as nothing deployed
  only when no artifact exists either (the first publish); otherwise it is
  refused like any other failure to fetch.

Either source failing to answer after `--attempts` tries is a refusal too:
an unchecked restore is what this exists to stop. A dispatch with
`start_history_afresh` passes none of these flags.

Standard library only. Spends nothing, places no bet; with the flags above it
reads two GitHub API listings and one public file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

#: The names `web/site_history.py` freezes and indexes.
BOARD = re.compile(r"^\d{4}-\d{2}-\d{2}(?:_\w+)?\.json$")


def snapshot(history: Path) -> dict:
    """{"boards": {name: sha256}, "lines": [relative names]} for `history`."""
    boards = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(history.glob("*.json"))
        if BOARD.match(path.name)
    }
    lines = sorted(
        path.relative_to(history).as_posix()
        for path in (history / "lines").glob("*.json")
    )
    return {"boards": boards, "lines": lines}


#: The workflow whose successful runs are the history's only sources.
WORKFLOW_PATH = ".github/workflows/publish-site.yml"
ARTIFACT = "site-history"
BRANCH = "main"

#: `deployed_boards`' answer when the site has no archive at all.
NOT_DEPLOYED = None


class SourceUnknown(RuntimeError):
    """An independent source could not be asked, so the restore is unchecked."""


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _pause(attempt: int) -> None:
    """10s, then 20s; the tests set RESTORE_STATE_RETRY_SECONDS to 0, as for
    restore_state.py."""
    time.sleep(float(os.environ.get("RESTORE_STATE_RETRY_SECONDS", "10")) * attempt)


def _gh_json(path: str, attempts: int, *extra: str):
    said = ""
    for attempt in range(attempts):
        if attempt:
            _pause(attempt)
        result = _gh("api", path, *extra)
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                said = "an answer that is not JSON"
                continue
        said = " ".join((result.stderr or "").split()) or f"exit {result.returncode}"
    raise SourceUnknown(f"GitHub did not answer {path} ({attempts} attempt(s); gh said: {said}).")


def newest_artifact_run(repo: str, attempts: int = 3) -> int | None:
    """The run of the newest unexpired `site-history` artifact on main whose
    run is a successful Publish Site run, from the artifacts API — which
    knows nothing of the run listing the restore read. None when there is
    no such artifact."""
    pages = _gh_json(
        f"repos/{repo}/actions/artifacts?name={ARTIFACT}&per_page=100",
        attempts, "--paginate", "--slurp",
    )
    try:
        artifacts = [a for page in pages for a in page["artifacts"]]
        candidates = sorted(
            (a for a in artifacts
             if a["name"] == ARTIFACT and not a["expired"]
             and a["workflow_run"]["head_branch"] == BRANCH),
            key=lambda a: a["created_at"], reverse=True,
        )
    except (KeyError, TypeError) as exc:
        raise SourceUnknown(f"The artifacts API answered in a shape this cannot read ({exc!r}).")
    asked = set()
    for artifact in candidates:
        run_id = artifact["workflow_run"]["id"]
        if run_id in asked:
            continue
        asked.add(run_id)
        run = _gh_json(f"repos/{repo}/actions/runs/{run_id}", attempts)
        # The branch was read from the artifact's own workflow_run above,
        # the same field of the same run; asking it twice would leave each
        # copy untestable behind the other.
        # A conclusion is only ever set on a completed run.
        if run.get("path") == WORKFLOW_PATH and run.get("conclusion") == "success":
            return int(run_id)
    return None


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def deployed_boards(url: str, attempts: int = 3,
                    fetch: Callable[[str], bytes] = _fetch) -> set[str] | None:
    """Every board file the live Archive's index.json lists, or NOT_DEPLOYED
    when the site has no index (404). Anything else that is not an answer
    raises `SourceUnknown`."""
    said = ""
    for attempt in range(attempts):
        if attempt:
            _pause(attempt)
        try:
            body = fetch(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return NOT_DEPLOYED
            said = f"HTTP {exc.code}"
            continue
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, FileNotFoundError):
                return NOT_DEPLOYED  # a file:// URL, as the tests give
            said = str(exc.reason)
            continue
        except OSError as exc:
            said = str(exc)
            continue
        try:
            index = json.loads(body)
            return {str(entry["file"]) for entry in index["dates"]}
        except (ValueError, KeyError, TypeError):
            said = "an index.json this cannot read"
    raise SourceUnknown(f"The deployed archive {url} could not be read ({attempts} attempt(s): {said}).")


def source_problems(history: Path, restored: int | None, newest: int | None,
                    deployed: set[str] | None) -> list[str]:
    """Where the restore disagrees with the two sources that are not the run
    listing it was chosen from."""
    found = []
    if newest != restored:
        if newest is None:
            found.append(
                f"The restore names run {restored}, but the artifacts API holds "
                f"no unexpired {ARTIFACT} from a successful Publish Site run on {BRANCH}."
            )
        elif restored is None:
            found.append(
                f"The restore found no successful publish to restore from, but "
                f"the artifacts API's newest {ARTIFACT} is run {newest}'s."
            )
        else:
            found.append(
                f"The restore took {ARTIFACT} from run {restored}, but the "
                f"artifacts API's newest from a successful publish is run "
                f"{newest}'s: the run listing it was chosen from was out of date."
            )
    have = set(snapshot(history)["boards"])
    if deployed is NOT_DEPLOYED:
        if newest is not None:
            found.append(
                "The live site has no history/index.json, though a successful "
                f"publish (run {newest}) kept a {ARTIFACT}; what is public cannot be checked."
            )
    else:
        for name in sorted(deployed - have):
            found.append(f"history/{name} is on the live Archive and not in the restored history.")
    return found


def verify_source(history: Path, restored_run: Path, repo: str, deployed_index: str,
                  attempts: int = 3) -> list[str]:
    try:
        text = restored_run.read_text(encoding="utf-8").strip()
        restored = int(text) if text else None
    except (OSError, ValueError):
        return [f"No readable record of which run the history was restored from ({restored_run})."]
    try:
        newest = newest_artifact_run(repo, attempts)
        deployed = deployed_boards(deployed_index, attempts)
    except SourceUnknown as exc:
        return [f"{exc} The restore cannot be checked against it."]
    return source_problems(history, restored, newest, deployed)


def record(history: Path, floor: Path, source: dict | None = None) -> int:
    if source is not None:
        found = verify_source(history, **source)
        if found:
            for line in found:
                print(f"::error::{line}")
            print(
                "::error::The restored history is not the newest the site has "
                "kept, so nothing is built, kept or deployed and the public site "
                "keeps its last build. If the newest successful publish's "
                "site-history really is the one to build on, the next run "
                "restores it; boards a run already dropped come back only by "
                "folding in the run that still holds them."
            )
            return 1
        print("The restore agrees with the artifacts API and the live Archive.")
    taken = snapshot(history)
    floor.parent.mkdir(parents=True, exist_ok=True)
    floor.write_text(json.dumps(taken, indent=1, sort_keys=True), encoding="utf-8")
    print(
        f"Restored history: {len(taken['boards'])} frozen board(s) and "
        f"{len(taken['lines'])} line file(s); the upload may hold no fewer."
    )
    return 0


def _indexed(history: Path) -> set[str]:
    """The boards `index.json` lists; none when it is missing or unreadable."""
    try:
        index = json.loads((history / "index.json").read_text(encoding="utf-8"))
        return {str(entry["file"]) for entry in index["dates"]}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def problems(history: Path, floor: dict) -> list[str]:
    """Everything the restored history held that this one has lost."""
    now = snapshot(history)
    found = []
    for name, digest in sorted(floor["boards"].items()):
        if name not in now["boards"]:
            found.append(f"history/{name} was restored and is gone.")
        elif now["boards"][name] != digest:
            found.append(
                f"history/{name} was restored and has been rewritten; the "
                "day's first published opinion stands."
            )
    for name in floor["lines"]:
        if name not in now["lines"]:
            found.append(f"history/{name} was restored and is gone.")
    for name in sorted(set(floor["boards"]) - _indexed(history)):
        found.append(f"history/index.json no longer lists {name}.")
    return found


def check(history: Path, floor_path: Path) -> int:
    try:
        floor = json.loads(floor_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(
            f"::error::No record of the history this run restored ({floor_path}). "
            "Without it there is no telling what an upload would lose, so "
            "nothing is kept or deployed."
        )
        return 1
    found = problems(history, floor)
    if found:
        for line in found:
            print(f"::error::{line}")
        print(
            f"::error::The history holds less than the {len(floor['boards'])} "
            "frozen board(s) this run restored. It is not kept for tomorrow "
            "and not deployed; the site keeps its last build."
        )
        return 1
    boards = len(snapshot(history)["boards"])
    print(
        f"history: all {len(floor['boards'])} restored board(s) and "
        f"{len(floor['lines'])} line file(s) are still here; {boards} to keep."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("record", "check"))
    parser.add_argument("--history", required=True)
    parser.add_argument("--floor", required=True)
    source = parser.add_argument_group(
        "the restore's independent check (record only; all three or none)")
    source.add_argument("--restored-run", metavar="FILE",
                        help="restore_state.py --record-run's file.")
    source.add_argument("--repo", help="owner/name, as GITHUB_REPOSITORY gives it.")
    source.add_argument("--deployed-index", metavar="URL",
                        help="The live site's data/history/index.json.")
    source.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args(argv)
    given = [args.restored_run, args.repo, args.deployed_index]
    if any(given) and not all(given):
        parser.error("--restored-run, --repo and --deployed-index go together")
    if any(given) and args.action != "record":
        parser.error("the restore's check belongs to record")
    if args.action == "record":
        source = None
        if all(given):
            source = {"restored_run": Path(args.restored_run), "repo": args.repo,
                      "deployed_index": args.deployed_index, "attempts": args.attempts}
        return record(Path(args.history), Path(args.floor), source)
    return check(Path(args.history), Path(args.floor))


if __name__ == "__main__":
    sys.exit(main())
