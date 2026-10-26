#!/usr/bin/env python3
"""Pages from Claude Design: what a design branch may change, and the shared tag.

Claude Design pushes page files to a branch named `design/<date>-<slug>` and
opens a pull request against main. Design Drop Guard holds that branch to page
files (`ALLOWED`); Design Drop pins any changed shared page to a new tag of
cooperross399/betting-lab-shared, merges the pull request once Tests is green,
and then moves EPL, CBB and the hub to the same tag.

    python scripts/design_drop.py guard --base origin/main --head HEAD
    python scripts/design_drop.py pin --shared DIR       # copy changed shared files, name the next tag
    python scripts/design_drop.py hub --shared DIR --tag vN --hub DIR
    python scripts/design_drop.py intake --zip FILE   # unpack a drop (zip or tarball)

Standard library only. Nothing here fetches odds, spends a credit, edits a
policy or places a bet.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

#: The only paths a design/** branch may change. `web/shared.lock.json` is
#: written by Design Drop's pin step, never by Claude Design: it is the lock
#: that the suite checks the committed copies against, so it cannot let a
#: page through that the tag does not hold.
ALLOWED = (
    "web/*.dc.html",
    "web/lib/live.js",
    "web/lib/format.js",
    "web/lib/sports.js",
    "web/SCHEMA.md",
    "web/DROP_NOTE.md",
    "web/data/sample/**",
    "web/logos/**",
    "web/shared.lock.json",
)

#: A change here means the drop needs a feed change a human (or a Claude Code
#: run) makes: the pull request is labelled `needs-builder`.
BUILDER_NOTE = "web/DROP_NOTE.md"

TAG = re.compile(r"^v(\d+)$")

#: A drop (zip or tarball) is refused past these sizes rather than half unpacked.
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024


def allowed(path: str) -> bool:
    """`*` stays inside one folder; `**` takes any depth below it."""
    for pattern in ALLOWED:
        if pattern.endswith("/**"):
            if path.startswith(pattern[:-2]):
                return True
        else:
            folder, name = pattern.rsplit("/", 1)
            if path.rsplit("/", 1)[0] == folder and fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], name):
                return True
    return False


def refused(paths: list[str]) -> list[str]:
    return [p for p in paths if not allowed(p)]


def changed(base: str, head: str, cwd: Path = ROOT) -> list[str]:
    """Every path the branch changes against its merge base, a rename as both names."""
    out = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{base}...{head}"],
                         cwd=cwd, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def _sync():
    spec = importlib.util.spec_from_file_location("sync_shared", WEB / "sync_shared.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def next_tag(tags: list[str]) -> str:
    numbers = [int(m.group(1)) for t in tags if (m := TAG.match(t.strip()))]
    return f"v{max(numbers, default=0) + 1}"


def shared_names(web: Path = WEB) -> list[str]:
    """This lab's shared files: the pages and libraries, and every logo on disk."""
    sync = _sync()
    logos = sorted(f"logos/{p.name}" for p in (web / "logos").iterdir() if p.is_file())
    return list(sync.PAGES) + logos


def pin(shared: Path, web: Path = WEB) -> list[str]:
    """Copy every shared file whose bytes differ from the lock into the shared
    checkout (logos into this lab's sport folder). Returns what was copied;
    an empty list means the lock already holds this branch's pages."""
    sync = _sync()
    lock = sync.load_lock(web / "shared.lock.json")
    copied = []
    for name in shared_names(web):
        path = web / name
        if lock["files"].get(name) == sync.digest(path):
            continue
        dst = sync.source(shared, name, lock["sport"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst)
        copied.append(name)
    return copied


def hub(shared: Path, tag: str, hub_dir: Path) -> list[str]:
    """Move the hub's `shared.lock.json` to `tag`, copying each file it pins."""
    sync = _sync()
    lock_path = hub_dir / "shared.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    moved = []
    for name, src in lock["source"].items():
        source = shared / src
        want = sync.digest(source)
        if lock["files"].get(name) != want or not (hub_dir / name).is_file() \
                or sync.digest(hub_dir / name) != want:
            moved.append(name)
        (hub_dir / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, hub_dir / name)
        lock["files"][name] = want
    lock["tag"] = tag
    lock_path.write_text(json.dumps(lock, indent=1) + "\n", encoding="utf-8")
    return moved


def _repo_path(names: list[str]):
    """How a zip member's name becomes a repository path.

    A zip may hold `web/...`, one wrapping folder around `web/...`, or the
    contents of `web/` itself. Files beside `web/` (a README, a note) do not
    change the layout; they are skipped as files outside it."""
    if any(n.startswith("web/") for n in names):
        return lambda n: n
    if any(n.split("/", 1)[-1].startswith("web/") for n in names if "/" in n):
        return lambda n: n.split("/", 1)[-1] if "/" in n else n
    return lambda n: "web/" + n


def _entries(archive_path: Path) -> list[tuple[str, int, object]]:
    """(name, size, read) for each file in a zip or a tarball (plain or
    gzip). A tarball's links and devices are never entries."""
    if zipfile.is_zipfile(archive_path):
        archive = zipfile.ZipFile(archive_path)
        return [(m.filename.replace("\\", "/"), m.file_size, lambda m=m: archive.read(m))
                for m in archive.infolist() if not m.is_dir()]
    if tarfile.is_tarfile(archive_path):
        archive = tarfile.open(archive_path)
        return [(m.name.replace("\\", "/").removeprefix("./"), m.size,
                 lambda m=m: archive.extractfile(m).read())
                for m in archive.getmembers() if m.isfile()]
    raise ValueError(f"{archive_path} is neither a zip nor a tarball")


def intake(zip_path: Path, root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Write a drop's page files, from a zip or a tarball, under `root`.
    Returns (written, skipped): anything outside `ALLOWED`, the lock (Design
    Drop's pin step writes that), a path that climbs out, and macOS litter
    are skipped."""
    entries = _entries(zip_path)
    if sum(size for _, size, _ in entries) > MAX_TOTAL_BYTES:
        raise ValueError(f"the drop unpacks to more than {MAX_TOTAL_BYTES} bytes")
    to_path = _repo_path([n for n, _, _ in entries if not n.startswith("__MACOSX/")])
    written, skipped = [], []
    for name, size, read in entries:
        path = to_path(name)
        parts = path.split("/")
        if (name.startswith("__MACOSX/") or parts[-1] == ".DS_Store" or path.startswith("/")
                or ".." in parts or path == "web/shared.lock.json" or not allowed(path)
                or size > MAX_FILE_BYTES):
            skipped.append(name)
            continue
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read())
        written.append(path)
    return written, skipped


def _output(**values: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("guard", help="refuse a design branch that changes anything but page files")
    g.add_argument("--base", required=True)
    g.add_argument("--head", required=True)
    p = sub.add_parser("pin", help="copy changed shared files into a checkout of the shared repository")
    p.add_argument("--shared", type=Path, required=True)
    h = sub.add_parser("hub", help="move the hub's lock to a tag")
    h.add_argument("--shared", type=Path, required=True)
    h.add_argument("--tag", required=True)
    h.add_argument("--hub", type=Path, required=True)
    z = sub.add_parser("intake", help="unpack a drop's page files (zip or tarball) into this checkout")
    z.add_argument("--zip", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.command == "guard":
        paths = changed(args.base, args.head)
        bad = refused(paths)
        for path in bad:
            print(f"::error file={path}::a design branch may change only page files; {path} is not one")
        print(f"{len(paths)} path(s) changed, {len(bad)} refused")
        _output(needs_builder="true" if BUILDER_NOTE in paths else "false")
        return 1 if bad else 0

    if args.command == "pin":
        tags = subprocess.run(["git", "tag", "--list"], cwd=args.shared, capture_output=True,
                              text=True, check=True).stdout.split()
        copied = pin(args.shared)
        tag = next_tag(tags)
        for name in copied:
            print(f"changed: {name}")
        print(f"{len(copied)} shared file(s) changed" + (f"; next tag {tag}" if copied else ""))
        _output(changed="true" if copied else "false", tag=tag)
        return 0

    if args.command == "intake":
        written, skipped = intake(args.zip)
        for path in written:
            print(f"wrote: {path}")
        for name in skipped:
            print(f"::warning::skipped {name}: not a page file a drop may change")
        print(f"{len(written)} page file(s) written, {len(skipped)} skipped")
        _output(written=str(len(written)))
        return 0 if written else 1

    moved = hub(args.shared, args.tag, args.hub)
    print(f"hub pinned to {args.tag}: {', '.join(moved) or 'no file changed'}")
    _output(changed="true" if moved else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
