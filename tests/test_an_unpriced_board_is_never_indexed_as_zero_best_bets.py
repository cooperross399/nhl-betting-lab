"""A board nobody priced is not a board where nothing cleared the bar.

`web/site_history.py` rewrites `history/index.json` from every frozen board,
and the Archive page (`web/Archive.dc.html`) prints each entry's `bets` as
"N best bets". The count was taken from each game's `pick` without reading
`priced`, so a board where no game carried a price — every regular-season
board Publish Site builds without staged prices
(tests/test_site_never_calls_an_unpriced_game_a_pass.py) — was indexed as
`bets: 0` and listed as "0 best bets". That reads as the model looking at
the slate and finding nothing worth betting, which is a judgement nobody
made. CLAUDE.md's first hard rule: an excluded market is never described as
a pass or a no-value call.

These tests hold the index and the page together: a board with no priced
game is indexed `bets: null` and listed "not priced"; a board with at least
one priced game keeps counting best bets among its priced games, so "0 best
bets" still means what it says there. A board frozen before the `priced`
flag existed is read the way `web/build_site_json.py::build_results` reads
it: a game carrying a market line was priced.

`site_history.py` runs through its own `main()`, loaded by path as the
workflow runs it. The Archive page runs its own component script under node
against the real `web/lib/sports.js` and `web/lib/format.js`, with `fetch`
answering from the index this module wrote.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"

BET = {"market": "moneyline", "label": "TOR +112", "price": 112, "edgePct": 11.0, "kind": "bet"}
LEAN = {"market": "total", "label": "Over 6.5", "price": -105, "edgePct": 2.0, "kind": "lean"}
MONEYLINE = {"open": None, "current": {"home": 112, "away": -130}, "fair": {"home": 100, "away": -100}}


def history_module():
    spec = importlib.util.spec_from_file_location("_site_history_unpriced_index", WEB / "site_history.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def game(gid: str, *, priced=None, pick=None, moneyline=False) -> dict:
    g = {"id": gid, "away": {"abbr": "MTL"}, "home": {"abbr": "TOR"}, "pick": pick}
    if priced is not None:
        g["priced"] = priced
    if moneyline:
        g["moneyline"] = MONEYLINE
    return g


def index_for(tmp_path: Path, boards: dict[str, list[dict]], phases: dict[str, str] | None = None) -> dict[str, dict]:
    """Freeze each board through the real main() and return the index by date."""
    data = tmp_path / "data"
    data.mkdir()
    module = history_module()
    for day, games in boards.items():
        board = {"boardDate": day, "generatedAt": f"{day}T12:00:00Z", "games": games}
        if phases and day in phases:
            board["phase"] = phases[day]
        (data / "board.json").write_text(json.dumps(board), encoding="utf-8")
        assert module.main(["--data", str(data)]) == 0
    index = json.loads((data / "history" / "index.json").read_text(encoding="utf-8"))
    return {e["date"]: e for e in index["dates"]}


def test_a_board_with_no_priced_game_is_indexed_as_not_priced(tmp_path: Path) -> None:
    entry = index_for(tmp_path, {"2026-10-08": [game("1", priced=False), game("2", priced=False)]})["2026-10-08"]
    assert entry["games"] == 2
    assert entry["bets"] is None, (
        f"a board where no game was priced was indexed bets={entry['bets']!r}; "
        "the archive prints that as a count of best bets, a no-value call nobody made"
    )


def test_a_priced_board_with_no_pick_still_counts_zero(tmp_path: Path) -> None:
    entry = index_for(tmp_path, {"2026-10-08": [game("1", priced=True), game("2", priced=False)]})["2026-10-08"]
    assert entry["bets"] == 0


def test_best_bets_are_counted_among_priced_games_only(tmp_path: Path) -> None:
    entries = index_for(tmp_path, {
        "2026-10-08": [game("1", priced=True, pick=BET), game("2", priced=True, pick=LEAN),
                       game("3", priced=True, pick={k: v for k, v in BET.items() if k != "kind"}),
                       game("4", priced=False, pick=BET)],
        # A pick on a game the board says it held no price for is not a best
        # bet the board can stand behind, and one alone does not make the
        # board priced.
        "2026-10-09": [game("5", priced=False, pick=BET)],
    })
    assert entries["2026-10-08"]["bets"] == 2
    assert entries["2026-10-09"]["bets"] is None


def test_a_board_frozen_before_the_flag_is_read_by_its_lines(tmp_path: Path) -> None:
    entries = index_for(tmp_path, {
        "2026-04-01": [game("1"), game("2")],
        "2026-04-02": [game("3", moneyline=True), game("4", moneyline=True, pick=BET)],
    })
    assert entries["2026-04-01"]["bets"] is None
    assert entries["2026-04-02"]["bets"] == 1


def test_an_explicit_unpriced_flag_outranks_a_line_the_game_carries(tmp_path: Path) -> None:
    entry = index_for(tmp_path, {"2026-10-08": [game("1", priced=False, moneyline=True, pick=BET)]})["2026-10-08"]
    assert entry["bets"] is None


def test_a_flagless_game_is_priced_by_any_market_value_it_carries(tmp_path: Path) -> None:
    """Another lab's board, or an older one, with no `priced` flag and no moneyline."""
    def flagless(gid: str, pick=None, **markets) -> dict:
        return {**game(gid, pick=pick), **markets}

    corners = {"market": "corners_total_9_5", "label": "Over 9.5 corners", "price": 110, "edgePct": 6.0, "kind": "bet"}
    unquoted = {"market": "corners_total_9_5", "label": "Over 9.5 corners", "edgePct": 6.0, "kind": "bet"}
    entries = index_for(tmp_path, {
        # The pick quotes no price here, so only the line makes these priced.
        "2026-10-01": [flagless("1", total={"current": 2.5, "over": -110}, pick=unquoted)],
        "2026-10-02": [flagless("2", spread={"current": -1.5}, pick=unquoted)],
        # Probabilities are the model's, not a price anyone quoted.
        "2026-10-03": [flagless("3", total={"overProb": 0.55}, btts={"yesProb": 0.6})],
        # SERIES does not cover corners; a best bet quoting a price still is one.
        "2026-10-04": [flagless("4", pick=corners)],
        "2026-10-05": [flagless("5", pick=corners), flagless("6", total={"current": 2.5, "over": -110}, pick=BET)],
        "2026-10-06": [flagless("7", pick=unquoted)],
    })
    assert entries["2026-10-01"]["bets"] == 1
    assert entries["2026-10-02"]["bets"] == 1
    assert entries["2026-10-03"]["bets"] is None
    assert entries["2026-10-04"]["bets"] == 1
    assert entries["2026-10-05"]["bets"] == 2
    assert entries["2026-10-06"]["bets"] is None


def test_an_empty_board_is_not_called_unpriced(tmp_path: Path) -> None:
    entry = index_for(tmp_path, {"2026-07-01": []})["2026-07-01"]
    assert entry["games"] == 0 and entry["bets"] == 0


# -- the Archive page, rendered through its own component ------------------

_ARCHIVE_DRIVER = r"""
import { readFileSync } from "node:fs";
const index = JSON.parse(readFileSync(process.argv[2], "utf8"));
globalThis.location = { hostname: "localhost" };
globalThis.fetch = async (url) => {
  if (String(url).endsWith("history/index.json")) return { ok: true, status: 200, json: async () => index };
  return { ok: false, status: 404, json: async () => ({}) };
};
class DCLogic { constructor() { this.props = { sport: "nhl" }; this.state = {}; } setState(s) { this.state = { ...this.state, ...s }; } }
const Component = makeComponent(DCLogic);
const archive = new Component();
archive.state = { ...archive.state };
await archive.load();
process.stdout.write(JSON.stringify(archive.renderVals()));
"""


def render_archive(index: dict, tmp_path: Path) -> list[dict]:
    node = shutil.which("node")
    assert node, "node is not on PATH; the Archive page's own script is what prints the count"
    html = (WEB / "Archive.dc.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="text/x-dc" data-dc-script[^>]*>([\s\S]*?)</script>', html)
    assert m, "Archive.dc.html carries no component script"
    site = tmp_path / "archive-site"
    (site / "lib").mkdir(parents=True)
    for name in ("sports.js", "format.js"):
        shutil.copyfile(WEB / "lib" / name, site / "lib" / name)
    (site / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    # The component's `import("./lib/...")` resolves against this module, so
    # its body is written into it rather than evaluated from a string.
    driver = f"function makeComponent(DCLogic) {{\n{m.group(1)}\nreturn Component;\n}}\n" + _ARCHIVE_DRIVER
    (site / "archive.mjs").write_text(driver, encoding="utf-8")
    (site / "index.json").write_text(json.dumps(index), encoding="utf-8")
    result = subprocess.run([node, str(site / "archive.mjs"), str(site / "index.json")],
                            capture_output=True, text=True, timeout=60, check=False, cwd=site)
    assert result.returncode == 0, result.stderr
    vals = json.loads(result.stdout)
    assert not vals["hasFeedNotice"], vals["feedNotice"]
    return [item for month in vals["months"] for item in month["items"]]


def test_the_archive_lists_an_unpriced_board_as_not_priced(tmp_path: Path) -> None:
    entries = index_for(tmp_path, {
        "2026-10-08": [game("1", priced=False), game("2", priced=False)],
        "2026-10-09": [game("3", priced=True), game("4", priced=False)],
        "2026-10-10": [game("5", priced=True, pick=BET)],
        "2026-10-11": [game("6", priced=True, pick=BET), game("7", priced=True, pick=BET)],
    })
    items = render_archive({"dates": list(entries.values())}, tmp_path)
    by_label = {item["href"]: item for item in items}
    bets = {href.split("date=")[1]: item["bets"] for href, item in by_label.items()}
    assert bets == {
        "2026-10-08.json": "not priced",
        "2026-10-09.json": "0 best bets",
        "2026-10-10.json": "1 best bet",
        "2026-10-11.json": "2 best bets",
    }
    assert all(item["games"].endswith("games") for item in items)


def test_an_index_entry_without_a_count_prints_no_count(tmp_path: Path) -> None:
    items = render_archive({"dates": [{"date": "2026-04-01", "file": "2026-04-01.json", "games": 3}]}, tmp_path)
    assert items[0]["bets"] == ""


def test_an_exhibition_board_is_neither_counted_nor_called_unpriced(tmp_path: Path) -> None:
    """The model abstains on a preseason board and nobody looked for a price.

    Every preseason game is `priced: false`, so the index wrote `bets: null`
    and the Archive read "exhibition · not priced", where the board page
    itself says "Exhibition · model abstains" (web/lib/sports.js). An
    unpriced regular-season board beside it still reads "not priced".
    """
    entries = index_for(
        tmp_path,
        {"2026-09-22": [game("1", priced=False), game("2", priced=False)],
         "2026-10-08": [game("3", priced=False), game("4", priced=False)]},
        phases={"2026-09-22": "preseason", "2026-10-08": "regular"},
    )
    assert entries["2026-09-22"]["note"] == "exhibition"
    assert "bets" not in entries["2026-09-22"], entries["2026-09-22"]
    assert entries["2026-10-08"]["bets"] is None

    items = {item["href"].split("date=")[1]: item
             for item in render_archive({"dates": list(entries.values())}, tmp_path)}
    exhibition, regular = items["2026-09-22.json"], items["2026-10-08.json"]
    assert exhibition["slot"] == "exhibition"
    assert exhibition["bets"] == "", exhibition
    assert "not priced" not in json.dumps(exhibition)
    assert regular["bets"] == "not priced"
