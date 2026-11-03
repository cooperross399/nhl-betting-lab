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
TABS = ["Tonight", "Props", "Results", "Season", "Record"]


def _tab_list(page: str) -> list[str]:
    text = (WEB / page).read_text(encoding="utf-8")
    m = re.search(r"const tabsList = \[(.*?)\];", text)
    assert m, f"{page} draws no tab list"
    return re.findall(r'\["([A-Za-z]+)", "', m.group(1))


def test_the_season_page_draws_the_same_tabs_as_tracker_and_record():
    for page in ("Season.dc.html", "Record.dc.html", "Game.dc.html"):
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
    shutil.copytree(WEB / "lib", tmp_path / "lib")
    changed = [n for n in _smooth().smooth(tmp_path) if n.endswith(".dc.html")]
    assert sorted(changed) == sorted(p.name for p in WEB.glob("*.dc.html") if p.name != "Tracker.dc.html")
    support = (WEB / "support.js").read_text(encoding="utf-8")
    for name in changed:
        text = (tmp_path / name).read_text(encoding="utf-8")
        head = text.split("<x-dc", 1)[0]
        assert "background:#14151a" in head and "html.sp-wait body{visibility:hidden;}" in head, name
        assert "@view-transition" not in head, name
        assert '"prerender"' in head and head.index("sp-wait") < head.index("support.js"), name
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
    shutil.copytree(WEB / "lib", tmp_path / "lib")
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
    for name in ("Board.dc.html", "Results.dc.html", "Season.dc.html", "Record.dc.html"):
        head = (out / name).read_text(encoding="utf-8").split("<x-dc", 1)[0]
        assert 'header>nav[aria-label="Site"]{flex-basis:100%;}' in head, name
        assert "section div:has(+h1){min-height:1.2em;}" in head, name
        assert 'nav[aria-label="Board sections"] a{flex:1 0 auto!important' in head, name


def test_a_page_that_moved_on_fails_the_publish(tmp_path):
    (tmp_path / "Board.dc.html").write_text('<meta charset="utf-8"><script src="./support.js"></script><x-dc></x-dc>', encoding="utf-8")
    try:
        _smooth().smooth(tmp_path)
    except SystemExit as e:
        assert "Board.dc.html" in str(e)
    else:
        raise AssertionError("an unpatchable Board was published")


def test_the_lab_pages_tabs_are_the_same_width_everywhere():
    for page in ("Season.dc.html", "Record.dc.html", "Game.dc.html", "Methods.dc.html"):
        text = (WEB / page).read_text(encoding="utf-8")
        assert "max-width:150px;min-width:56px;" in text, page
        assert "max-width:150px;min-width:72px" not in text, page


def test_record_and_tracker_are_one_page_with_no_tracker_or_archive_tab(tmp_path):
    """Cooper, 2026-11-03: "combine record/tracker into one page for all of the
    sports on the website ... Just make it simple"."""
    tracker = (WEB / "Tracker.dc.html").read_text(encoding="utf-8")
    assert 'location.replace("Record.dc.html" + location.hash)' in tracker
    out = _smoothed(tmp_path)
    for name in ("Board.dc.html", "Results.dc.html", "Archive.dc.html", "Graphic.dc.html", "lib/sports.js"):
        text = (out / name).read_text(encoding="utf-8")
        assert '"Tracker.dc.html"' not in text and 'tab("Archive"' not in text and 'tabLink("Archive"' not in text, name
    record = (WEB / "Record.dc.html").read_text(encoding="utf-8")
    for plain in ("Our<br>record", "is one standard bet", "Do our win chances come true?", "./data/record.json", "./data/tracker.json"):
        assert plain in record, plain
    for jargon in ("Brier", "calibration", "interval", "ROI"):
        assert jargon not in record, jargon


def test_a_page_waits_for_its_data_before_it_shows(tmp_path):
    """Every page drew twice, and the second draw, when its data arrived,
    moved everything (a 0.44 layout shift measured on Results, 0.43 on the
    old Tracker). The gate holds the page until its same-site data is in and
    it has stopped changing, never longer than 1.6 s."""
    gate = _smooth().GATE
    assert "now-t0>1600" in gate and "now-last>120" in gate and "origin===location.origin" in gate


def test_the_season_records_carry_their_profit_at_a_quarter_unit(tmp_path):
    """Cooper, 2026-11-03: "I want a tracked profit/loss for best
    bets/totals/leans/straight up underneath the record" at ".25u per bet. to
    win .25u for -odds"."""
    out = _smoothed(tmp_path)
    sports = (out / "lib/sports.js").read_text(encoding="utf-8")
    for key in ("picks", "straightUp", "totals", "leans"):
        assert f'pl("{key}",' in sports, key
    results = (out / "Results.dc.html").read_text(encoding="utf-8")
    assert "{{ c.sub }}" in results.split('<sc-for list="{{ strip }}"', 1)[1].split("</sc-for>", 1)[0]


def test_a_quarter_unit_record_pays_as_cooper_set_it():
    spec = importlib.util.spec_from_file_location("bsj", WEB / "build_site_json.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(WEB))
    spec.loader.exec_module(mod)
    assert mod.record_units(150, "win") == (0.375, 0.25)
    assert mod.record_units(150, "loss") == (-0.25, 0.25)
    assert mod.record_units(-150, "win") == (0.25, 0.375)
    assert mod.record_units(-150, "loss") == (-0.375, 0.375)
    assert mod.record_units(-110, "push") == (0.0, 0.275)
    assert mod.record_units(None, "win") is None and mod.record_units(0, "win") is None
