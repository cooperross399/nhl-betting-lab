"""Every artifact a workflow restores must unpack where it was rooted.

`upload-artifact` roots an artifact at the common ancestor of its paths, and
each restore here is `gh run download <run> --name X --dir D`. The two agree
only while the upload's root is D. On 2026-09-22 two `data/outputs` files were
added to Line Movement Capture's upload, moving its root from `data/processed`
to `data/`, while the restore still unpacked into `data/processed`. From the
first in-season run every restored capture would have landed one directory too
deep. Each run would have started the day's file afresh, and continue-on-error
kept the job green. The captures cannot be re-collected: the history would
have lived only in per-run artifacts that expire after 90 days.

This test does not trust a comment beside either step. It pairs every restore
in every workflow with every upload of the same name and derives the root.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
DOWNLOAD = re.compile(r'gh run download \S+ --name ("?\$?\w[\w-]*"?) --dir (\S+)')
LOOP = re.compile(r"for name in ([\w\- ]+); do")


def _uploads() -> dict[str, list[tuple[str, list[str]]]]:
    found: dict[str, list[tuple[str, list[str]]]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps", []) or []:
                if not str(step.get("uses", "")).startswith("actions/upload-artifact"):
                    continue
                given = step.get("with", {}) or {}
                paths = upload_paths(str(given.get("path", "")))
                found.setdefault(str(given.get("name")), []).append((path.name, paths))
    return found


def upload_paths(block: str) -> list[str]:
    """The search paths of a `path:` block, as upload-artifact reads them.

    Its glob skips blank lines, `#` comments and `!` exclusions. The EPL lab's
    uploads carry comments inside the block, and counting one as a path
    computes a root of "" and fails a restore that is correct.
    """
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.strip().startswith(("!", "#"))
    ]


def artifact_root(paths: list[str]) -> str:
    """The directory `upload-artifact` makes the artifact's root."""
    searched = [p.split("*")[0].rstrip("/") for p in paths]
    if len(searched) == 1:
        only = searched[0]
        return os.path.dirname(only) if Path(only).suffix else only
    return os.path.commonpath(searched)


def _restores() -> list[tuple[str, str, str]]:
    """(workflow, artifact name, directory) for every restore into the repo."""
    out = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        loop = LOOP.search(text)
        for match in DOWNLOAD.finditer(text):
            name, directory = match.group(1).strip('"'), match.group(2)
            if directory.startswith("/"):
                continue  # a scratch download to inspect, not a restore in place
            names = loop.group(1).split() if name == "$name" and loop else [name]
            out.extend((path.name, n, directory) for n in names)
    return out


RESTORES = _restores()


def test_the_restores_were_actually_found():
    """A regex that stopped matching would make every case below vanish."""
    assert len(RESTORES) >= 8
    assert ("line-movement.yml", "line-movement", "data/processed") in RESTORES


@pytest.mark.parametrize("workflow,name,directory", RESTORES)
def test_a_restore_unpacks_where_its_artifact_was_rooted(workflow, name, directory):
    uploads = _uploads().get(name)
    assert uploads, f"{workflow} restores `{name}`, which no workflow uploads"
    for source, paths in uploads:
        assert artifact_root(paths) == directory, (
            f"{workflow} unpacks `{name}` into {directory}, but {source} roots it at "
            f"{artifact_root(paths)}: every restored file lands in the wrong place"
        )


def test_the_line_movement_restore_checks_the_stores_it_uploads():
    """The restore's own check names three day-stores; each must be uploaded."""
    text = (WORKFLOWS / "line-movement.yml").read_text(encoding="utf-8")
    checked = re.search(r"for store in ([\w ]+); do", text).group(1).split()
    uploaded = next(paths for _, paths in _uploads()["line-movement"])
    assert checked
    for store in checked:
        assert f"data/processed/{store}" in uploaded


@pytest.mark.parametrize(
    "paths,root",
    [
        (["data/processed/line_movement", "data/processed/deployment"], "data/processed"),
        (["data/processed/line_movement", "data/outputs/ladder_coherence.json"], "data"),
        (["data/outputs/a.json", "data/outputs/b.md"], "data/outputs"),
        (["dist/data/history"], "dist/data/history"),
        (["data/outputs/closing_line_value.md"], "data/outputs"),
    ],
)
def test_the_root_rule(paths, root):
    """The second case is the 2026-09-22 upload."""
    assert artifact_root(paths) == root


def test_a_comment_inside_a_path_block_is_not_a_path():
    block = """
        data/outputs/archive/automated_cards
        # Restored at the top of each run like the archive beside it.
        data/processed/epl_historical_matches.csv
        !data/processed/*.tmp
    """
    assert upload_paths(block) == [
        "data/outputs/archive/automated_cards",
        "data/processed/epl_historical_matches.csv",
    ]
    assert artifact_root(upload_paths(block)) == "data"
