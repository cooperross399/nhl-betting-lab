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


def _smoothed(tmp_path) -> Path:
    for p in WEB.glob("*.dc.html"):
        shutil.copy(p, tmp_path / p.name)
    shutil.copy(WEB / "support.js", tmp_path / "support.js")
    _smooth().smooth(tmp_path)
    return tmp_path


def test_board_and_results_start_with_this_sites_tabs(tmp_path):
    """Cooper: "When i click the props and results tab it still glitches". Before
    their data arrived both pages drew their tabs without Props, Season, Record or
    Tracker and with an Archive tab, and Board#props drew Tonight first."""
    out = _smoothed(tmp_path)
    board = (out / "Board.dc.html").read_text(encoding="utf-8")
    assert 'tab: /^#(props|drought)$/.test(location.hash) ? "props" : "tonight"' in board
    assert 'pages: new Set(["season","record","tracker","methods","game"])' in board
    assert 'tabs: tabsFor(this.state.tab, { status: "pending"' in board
    assert 'tabsFor("tonight", null)' not in board
    assert 'isProps: this.state.tab === "props"' in board
    results = (out / "Results.dc.html").read_text(encoding="utf-8")
    assert 'pages: new Set(["season","record","tracker","methods","game"]), propsTab: true' in results
    # The keys are this site's pages, as lib/sports.js lists them for the NHL.
    sports = (WEB / "lib/sports.js").read_text(encoding="utf-8")
    for key in ("season", "record", "tracker", "methods", "game"):
        assert f'"{key}"' in sports


def test_the_header_and_tab_bar_hold_their_place(tmp_path):
    out = _smoothed(tmp_path)
    for name in ("Board.dc.html", "Results.dc.html", "Season.dc.html", "Tracker.dc.html", "Record.dc.html"):
        head = (out / name).read_text(encoding="utf-8").split("<x-dc", 1)[0]
        assert 'header>nav[aria-label="Site"]{flex-basis:100%;}' in head, name
        assert "section div:has(+h1){min-height:1.2em;}" in head, name
        assert 'nav[aria-label="Board sections"] a{flex:1 0 auto!important' in head, name


def test_a_page_that_moved_on_fails_the_publish(tmp_path):
    (tmp_path / "Board.dc.html").write_text('<meta charset="utf-8"><x-dc></x-dc>', encoding="utf-8")
    try:
        _smooth().smooth(tmp_path)
    except SystemExit as e:
        assert "Board.dc.html" in str(e)
    else:
        raise AssertionError("an unpatchable Board was published")


def test_the_lab_pages_tabs_are_the_same_width_everywhere():
    for page in ("Season.dc.html", "Tracker.dc.html", "Record.dc.html", "Game.dc.html", "Methods.dc.html"):
        text = (WEB / page).read_text(encoding="utf-8")
        assert "max-width:150px;min-width:56px;" in text, page
        assert "max-width:150px;min-width:72px" not in text, page
