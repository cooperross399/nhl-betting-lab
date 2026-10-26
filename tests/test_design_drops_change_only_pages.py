"""Pages from Claude Design publish themselves, and change nothing but pages.

A design/** branch may change only the paths in `design_drop.ALLOWED`; Design
Drop Guard fails any other, and Design Drop merges only a head the guard
passed and Tests passed. The pin step moves a changed shared page into
betting-lab-shared under a new tag and re-pins this lab's lock; fan-out moves
the other labs and the hub to that tag through pull requests merged on green.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _drop():
    spec = importlib.util.spec_from_file_location("design_drop", ROOT / "scripts" / "design_drop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", [
    "web/Board.dc.html", "web/Game.dc.html", "web/lib/live.js", "web/lib/format.js",
    "web/lib/sports.js", "web/SCHEMA.md", "web/DROP_NOTE.md",
    "web/data/sample/board.json", "web/data/sample/history/2026-10-25.json",
    "web/logos/TOR.png", "web/shared.lock.json",
])
def test_page_files_pass(path: str) -> None:
    assert _drop().allowed(path), path


@pytest.mark.parametrize("path", [
    "web/build_site_json.py", "web/sync_shared.py", "web/support.js", "web/lib/other.js",
    "web/sub/Board.dc.html", "web/data/season.json", "builders/build.py",
    "tests/test_x.py", ".github/workflows/design-drop.yml", "src/nhl_betting_lab/cli.py",
    "scripts/design_drop.py", "CLAUDE.md", "data/manual/staging_provider_policy.json",
    "Board.dc.html",
])
def test_everything_else_is_refused(path: str) -> None:
    assert not _drop().allowed(path), path


def test_the_guard_reads_the_branch_against_its_base(tmp_path: Path) -> None:
    """Planted on a real repository: a page passes, a builder beside it does not."""
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "Board.dc.html").write_text("a")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "design/test")
    (tmp_path / "web" / "Board.dc.html").write_text("b")
    (tmp_path / "web" / "DROP_NOTE.md").write_text("note")
    git("add", "-A")
    git("commit", "-qm", "page")
    drop = _drop()
    paths = drop.changed("main", "HEAD", cwd=tmp_path)
    assert sorted(paths) == ["web/Board.dc.html", "web/DROP_NOTE.md"]
    assert drop.refused(paths) == []
    (tmp_path / "builders").mkdir()
    (tmp_path / "builders" / "x.py").write_text("x")
    git("add", "-A")
    git("commit", "-qm", "builder")
    assert drop.refused(drop.changed("main", "HEAD", cwd=tmp_path)) == ["builders/x.py"]


def test_the_next_tag_counts_past_the_highest() -> None:
    drop = _drop()
    assert drop.next_tag(["v1"]) == "v2"
    assert drop.next_tag(["v1", "v10", "v9", "release"]) == "v11"
    assert drop.next_tag([]) == "v1"


def _lab(tmp_path: Path) -> tuple[Path, Path]:
    """A lab's web/ and a shared checkout, both holding the locked bytes."""
    drop = _drop()
    sync = drop._sync()
    web, shared = tmp_path / "web", tmp_path / "shared"
    lock = sync.load_lock()
    for name in drop.shared_names():
        for dst in (web / name, sync.source(shared, name, lock["sport"])):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes((ROOT / "web" / name).read_bytes())
    (web / "shared.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return web, shared


def test_pin_copies_only_what_differs_from_the_lock(tmp_path: Path) -> None:
    drop = _drop()
    web, shared = _lab(tmp_path)
    assert drop.pin(shared, web) == []
    (web / "Board.dc.html").write_bytes(b"<!doctype html>new")
    (web / "logos" / "TOR.png").write_bytes(b"png")
    assert drop.pin(shared, web) == ["Board.dc.html", "logos/TOR.png"]
    assert (shared / "web" / "Board.dc.html").read_bytes() == b"<!doctype html>new"
    assert (shared / "web" / "logos" / "nhl" / "TOR.png").read_bytes() == b"png"


def test_the_hub_moves_to_the_tag(tmp_path: Path) -> None:
    drop = _drop()
    shared, hub = tmp_path / "shared", tmp_path / "hub"
    (shared / "web" / "lib").mkdir(parents=True)
    (shared / "web" / "lib" / "sports.js").write_text("sports v2")
    (shared / "web" / "lib" / "format.js").write_text("format")
    (hub / "lib").mkdir(parents=True)
    (hub / "lib" / "sports.js").write_text("sports v1")
    (hub / "lib" / "format.js").write_text("format")
    sync = drop._sync()
    (hub / "shared.lock.json").write_text(json.dumps({
        "repo": "cooperross399/betting-lab-shared", "tag": "v1",
        "source": {"lib/sports.js": "web/lib/sports.js", "lib/format.js": "web/lib/format.js"},
        "files": {"lib/sports.js": sync.digest(hub / "lib" / "sports.js"),
                  "lib/format.js": sync.digest(hub / "lib" / "format.js")}}))
    assert drop.hub(shared, "v2", hub) == ["lib/sports.js"]
    lock = json.loads((hub / "shared.lock.json").read_text())
    assert lock["tag"] == "v2"
    assert (hub / "lib" / "sports.js").read_text() == "sports v2"
    assert lock["files"]["lib/sports.js"] == sync.digest(hub / "lib" / "sports.js")


def test_the_guard_runs_on_design_branches_and_names_the_check_the_merge_reads() -> None:
    guard = _load("design-drop-guard.yml")
    (job,) = guard["jobs"].values()
    assert job["name"] == "Design drop guard"
    assert "startsWith(github.head_ref, 'design/')" in job["if"]
    merge = _load("design-drop.yml")["jobs"]["merge"]
    text = "\n".join(str(step.get("run", "")) for step in merge["steps"])
    assert "check_name=Design%20drop%20guard" in text
    assert '"$guard" != "success"' in text


def test_a_drop_merges_only_after_tests_pass_on_its_own_head() -> None:
    workflow = _load("design-drop.yml")
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert triggers["workflow_run"]["workflows"] == ["Tests"]
    condition = workflow["jobs"]["merge"]["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "startsWith(github.event.workflow_run.head_branch, 'design/')" in condition
    text = "\n".join(str(step.get("run", "")) for step in workflow["jobs"]["merge"]["steps"])
    assert '--match-head-commit "$SHA"' in text
    fanout = "\n".join(str(step.get("run", "")) for step in workflow["jobs"]["fanout"]["steps"])
    assert 'gh pr checks "$PR" --watch' in fanout
    assert fanout.index("--watch") < fanout.index("gh pr merge")


def test_the_drop_never_pushes_this_repositorys_main() -> None:
    """Every push names its ref: the design branch it pins, betting-lab-shared
    (a separate clone) and the other repositories' shared-sync branches."""
    text = (WORKFLOWS / "design-drop.yml").read_text(encoding="utf-8")
    pushes = [line.strip() for line in text.splitlines() if re.search(r"\bgit push\b", line)]
    assert pushes == [
        'git push --quiet origin HEAD:refs/heads/main "refs/tags/$TAG"',
        'git push --quiet origin "HEAD:refs/heads/$BRANCH"',
        'git push --quiet origin "HEAD:refs/heads/shared-sync/$tag"',
    ]
    # The first runs inside the shared clone, never this checkout.
    assert 'cd "$RUNNER_TEMP/shared"' in text.split(pushes[0])[0].rsplit("(", 1)[1]
    assert "contents: write" not in text


def _zip(tmp_path: Path, members: dict[str, bytes]) -> Path:
    import zipfile
    path = tmp_path / "drop.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return path


@pytest.mark.parametrize("layout", ["web/", "Drop 3/web/", ""])
def test_intake_unpacks_only_page_files(tmp_path: Path, layout: str) -> None:
    """A zip holding web/, a folder around web/, or web/'s contents unpacks
    the same; everything outside ALLOWED, and the lock, is skipped."""
    root = tmp_path / "repo"
    zipped = _zip(tmp_path, {
        f"{layout}Board.dc.html": b"page",
        f"{layout}lib/sports.js": b"js",
        f"{layout}build_site_json.py": b"builder",
        f"{layout}shared.lock.json": b"{}",
        f"{layout}../../evil.txt": b"x",
        "__MACOSX/._Board.dc.html": b"",
    })
    written, skipped = _drop().intake(zipped, root)
    assert sorted(written) == ["web/Board.dc.html", "web/lib/sports.js"]
    assert (root / "web" / "Board.dc.html").read_bytes() == b"page"
    assert len(skipped) == 4
    assert not (root / "web" / "build_site_json.py").exists()
    assert not (root / "web" / "shared.lock.json").exists()
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.parametrize("layout", ["", "Drop 3/"])
def test_a_file_beside_web_does_not_move_the_pages(tmp_path: Path, layout: str) -> None:
    """A README next to web/ once sent every page to web/web/, so a real
    drop wrote nothing."""
    zipped = _zip(tmp_path, {
        f"{layout}web/Methods.dc.html": b"page",
        f"{layout}README.txt": b"note",
        "README.txt" if layout else "NOTES.md": b"note",
    })
    written, skipped = _drop().intake(zipped, tmp_path / "repo")
    assert written == ["web/Methods.dc.html"]
    assert len(skipped) == 2


def test_the_intake_opens_the_drop_with_the_token_and_never_twice() -> None:
    workflow = _load("design-drop-intake.yml")
    (job,) = workflow["jobs"].values()
    assert job["env"]["GH_TOKEN"] == "${{ secrets.DESIGN_DROP_TOKEN }}"
    text = (WORKFLOWS / "design-drop-intake.yml").read_text(encoding="utf-8")
    pushes = [line.strip() for line in text.splitlines() if re.search(r"\bgit push\b", line)]
    assert pushes == ['git push --quiet origin "HEAD:refs/heads/$branch"']
    assert 'branch="design/' in text
    assert "git diff --cached --quiet" in text
    assert "contents: write" not in text
