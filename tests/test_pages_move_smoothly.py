"""Moving between the site's pages: one tab bar everywhere, and no white flash.

Cooper, 2026-11-02: "When i click the season tab, the tracker/record tabs
dissappear and an archive tab pops up which shouldnt even be a thing", and "the
pages also visibly glitch whenever i click a different tab".
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
TABS = ["Tonight", "Props", "Results", "Season", "Record", "Tracker"]


def _tab_list(page: str) -> list[str]:
    text = (WEB / page).read_text(encoding="utf-8")
    m = re.search(r"const tabsList = \[(.*?)\];", text)
    assert m, f"{page} draws no tab list"
    return re.findall(r'\["([A-Za-z]+)", "', m.group(1))


def test_the_season_page_draws_the_same_tabs_as_tracker_and_record():
    for page in ("Season.dc.html", "Tracker.dc.html", "Record.dc.html", "Game.dc.html"):
        assert _tab_list(page) == TABS, page


def test_the_season_page_links_no_archive_tab():
    text = (WEB / "Season.dc.html").read_text(encoding="utf-8")
    assert 'href="Archive.dc.html"' not in text
    assert '"Archive.dc.html"' not in text


def _smooth():
    spec = importlib.util.spec_from_file_location("smooth_pages", WEB / "smooth_pages.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_published_page_starts_dark_and_preloads_react(tmp_path):
    for p in WEB.glob("*.dc.html"):
        shutil.copy(p, tmp_path / p.name)
    shutil.copy(WEB / "support.js", tmp_path / "support.js")
    changed = _smooth().smooth(tmp_path)
    assert sorted(changed) == sorted(p.name for p in WEB.glob("*.dc.html"))
    support = (WEB / "support.js").read_text(encoding="utf-8")
    for name in changed:
        text = (tmp_path / name).read_text(encoding="utf-8")
        head = text[: text.index("<x-dc")]
        assert "background:#14151a" in head and "@view-transition{navigation:auto;}" in head, name
        assert head.index("smooth-pages") < head.index("support.js"), name
        for url, sri in re.findall(r'href="(https://unpkg\.com/[^"]+)" crossorigin="anonymous" integrity="([^"]+)"', head):
            assert url in support and sri in support, name
        assert head.count('rel="preload"') == 2, name
    # A second run adds nothing.
    before = {n: (tmp_path / n).read_text(encoding="utf-8") for n in changed}
    assert _smooth().smooth(tmp_path) == []
    assert before == {n: (tmp_path / n).read_text(encoding="utf-8") for n in changed}


def test_publish_site_smooths_the_pages_before_upload():
    wf = (WEB.parent / ".github/workflows/publish-site.yml").read_text(encoding="utf-8")
    assert wf.index("python web/smooth_pages.py dist") < wf.index("upload-pages-artifact")
