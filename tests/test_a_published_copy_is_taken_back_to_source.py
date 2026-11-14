"""A drop built from the live site's copies is taken back to source at intake.

The 2026-11-14 modern-redesign drop was built from the published pages: each
carried the block `web/smooth_pages.py` adds after `<meta charset>`, this
lab's publish-time patches, no Tracker/Archive tab, and `import(new URL(...))`
in place of the plain `import("./lib/...")`. Every lab's suite refused it
(NHL, EPL and CBB all red) though nothing in the design was wrong.
`design_drop.unpublish` undoes exactly what publishing does, so a published
copy of a page comes back byte for byte as its source.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _published(tmp_path: Path) -> Path:
    """The site's pages as the publish step leaves them, plus the URL-import
    spelling the redesign drop carried."""
    dist = tmp_path / "dist"
    (dist / "lib").mkdir(parents=True)
    for page in WEB.glob("*.dc.html"):
        shutil.copyfile(page, dist / page.name)
    for lib in (WEB / "lib").glob("*.js"):
        shutil.copyfile(lib, dist / "lib" / lib.name)
    shutil.copyfile(WEB / "support.js", dist / "support.js")
    shutil.copyfile(WEB / "site.json", dist / "site.json")
    _load("smooth_pages", WEB / "smooth_pages.py").smooth(dist)
    for page in dist.glob("*.dc.html"):
        text = page.read_text(encoding="utf-8")
        text = re.sub(r'import\("(\./lib/[A-Za-z0-9_-]+\.js)"\)', r'import(new URL("\1", location.href).href)', text)
        page.write_text(text, encoding="utf-8")
    return dist


def test_every_published_page_comes_back_as_its_source(tmp_path):
    drop = _load("design_drop", ROOT / "scripts" / "design_drop.py")
    dist = _published(tmp_path)
    names = [p.name for p in WEB.glob("*.dc.html") if "support.js" in p.read_text(encoding="utf-8")]
    assert {"Board.dc.html", "Results.dc.html", "Archive.dc.html", "Graphic.dc.html", "Record.dc.html"} <= set(names)
    for name in names + ["lib/sports.js"]:
        source = (WEB / name).read_text(encoding="utf-8")
        published = (dist / name).read_text(encoding="utf-8")
        assert published != source, name
        back, undone = drop.unpublish(f"web/{name}", published, source)
        assert back == source, name
        assert undone, name


def test_a_source_copy_is_left_alone():
    drop = _load("design_drop", ROOT / "scripts" / "design_drop.py")
    for path in list(WEB.glob("*.dc.html")) + [WEB / "lib" / "sports.js"]:
        text = path.read_text(encoding="utf-8")
        assert drop.unpublish(f"web/{path.relative_to(WEB)}", text, text) == (text, []), path.name


def test_the_intake_takes_a_published_copy_back_to_source(tmp_path):
    drop = _load("design_drop", ROOT / "scripts" / "design_drop.py")
    dist = _published(tmp_path)
    archive = tmp_path / "drop.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(dist / "Board.dc.html", "web/Board.dc.html")
        z.write(dist / "lib" / "sports.js", "web/lib/sports.js")
    root = tmp_path / "lab"
    (root / "web" / "lib").mkdir(parents=True)
    shutil.copyfile(WEB / "Board.dc.html", root / "web" / "Board.dc.html")
    shutil.copyfile(WEB / "lib" / "sports.js", root / "web" / "lib" / "sports.js")
    written, _ = drop.intake(archive, root)
    assert sorted(written) == ["web/Board.dc.html", "web/lib/sports.js"]
    for name in ("Board.dc.html", "lib/sports.js"):
        assert (root / "web" / name).read_bytes() == (WEB / name).read_bytes(), name
