"""`games[].drought` and `droughtNote`: the shape web/SCHEMA.md names, written by the site builder.

The Board's game cards render Cooper's Due List (2026-10-07; that evening the tier and
equal-surprise bars replaced the flat 5-game rule of #307). The site reads a file and
imports nothing from the card: the card writes `data/outputs/drought_list.json`, Publish
Site restores it with `gameday-reports`, and `web/build_site_json.py` turns it into
`games[].drought`. Every regular-season game carries the array, empty when nobody
qualifies; a missing price stays null; a list built for another day is never shown on this one.
The bars, the hit rate, the rarity, the rule, the band and the cell record are the card's
figures or null, never computed here, so a list the flat-rule card wrote still publishes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY, CLUBS, SLATE, make_lab, schedule, site_module,
)

#: What a row gained on 2026-10-07 evening, beyond the #307 shape.
BAR_KEYS = {"tierBar", "surpriseBar", "hitRate", "rarity", "oneIn", "rule", "band", "cellRecord"}
SCHEMA_KEYS = {"player", "playerId", "team", "market", "line", "lastSeason", "drought", "price", "book", "heavyJuice"} | BAR_KEYS
#: The same fields as the card's drought_list.json spells them.
CARD_BAR_FIELDS = ("tier_bar", "surprise_bar", "hit_rate", "rarity", "one_in", "rule", "band", "cell_record")
ROOT = Path(__file__).resolve().parents[1]
BACKTEST_JSON = ROOT / "data" / "outputs" / "drought_rule_backtest.json"


def row(home: str, away: str, **kw) -> dict:
    base = {"date": BOARD_DAY.isoformat(), "home_team": home, "away_team": away, "team": home, "opponent": away,
            "player": "Assist Man", "player_id": 8471111, "market": "assists", "line": 0.5, "last_season": 31,
            "drought": 7, "american_odds": 170.0, "book": "DraftKings", "heavy_juice": False,
            # A row the card can write: 31 assists is the 30-44 band (bar 5); a 35% hit rate makes his
            # equal-surprise bar 7 (0.65^7 = 0.049 <= 0.05); seven games reach both bars, so "both",
            # and 1 / 0.65^7 = 20.4 is his "1 in 20 for him".
            "tier_bar": 5, "surprise_bar": 7, "hit_rate": 0.35, "rarity": 0.049, "one_in": 20, "rule": "both", "band": "30-44",
            "cell_record": {"wagers": 184, "roi": 0.105, "ci_low": -0.017, "ci_high": 0.239}}
    base.update(kw)
    return base


def older(r: dict) -> dict:
    """The same row as a card without `one_in` wrote it."""
    return {key: value for key, value in r.items() if key != "one_in"}


def write_list(lab: Path, rows: list[dict], day: date = BOARD_DAY) -> None:
    (lab / "data" / "outputs" / "drought_list.json").write_text(
        json.dumps({"generated_at": "x", "day": day.isoformat(), "headline": "h", "rows": rows,
                    "unresolved": [], "notes": []}), encoding="utf-8")


def build(lab: Path, out: Path, monkeypatch, *, start: str = "2099-10-08T23:00:00Z") -> dict:
    module = site_module()

    def later(d):
        games = schedule(d)
        for g in games:
            g["startTimeUTC"] = start
        return games

    monkeypatch.setattr(module, "schedule_for", later)
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline"])
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", BOARD_DAY.isoformat()]) == 0
    return json.loads((out / "board.json").read_text(encoding="utf-8"))


@pytest.fixture
def lab(tmp_path: Path, monkeypatch) -> Path:
    return make_lab(tmp_path, monkeypatch, staged=False)


def test_every_regular_season_game_carries_the_array_in_the_schemas_shape(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL"), row("TOR", "MTL", player="Second", player_id=2, market="goals",
                                              american_odds=None, book="", heavy_juice=False),
                     row("NYI", "BOS", player="Heavy", player_id=3, american_odds=-190.0, heavy_juice=True)])

    board = build(lab, tmp_path / "out", monkeypatch)
    by = {g["home"]["abbr"]: g["drought"] for g in board["games"]}

    assert all(isinstance(g["drought"], list) for g in board["games"])
    assert [r["player"] for r in by["TOR"]] == ["Assist Man", "Second"], "the card's order is kept"
    assert set(by["TOR"][0]) == SCHEMA_KEYS
    # The pinned shape: the #307 fields, then the bars as the card wrote them and the cell
    # record in percent (roi 0.105 -> 10.5), under keys that are not the sealed forward
    # return's spellings (tests/test_site_publishes_no_forward_return.py).
    assert by["TOR"][0] == {"player": "Assist Man", "playerId": 8471111, "team": "TOR", "market": "assists", "line": 0.5,
                            "lastSeason": 31, "drought": 7, "price": 170, "book": "DraftKings", "heavyJuice": False,
                            "tierBar": 5, "surpriseBar": 7, "hitRate": 0.35, "rarity": 0.049, "oneIn": 20, "rule": "both", "band": "30-44",
                            "cellRecord": {"wagers": 184, "returnPct": 10.5, "lowPct": -1.7, "highPct": 23.9}}
    assert by["TOR"][1]["price"] is None and by["TOR"][1]["book"] is None, "a missing price stays null"
    assert by["NYI"][0]["price"] == -190 and by["NYI"][0]["heavyJuice"] is True


def test_a_row_without_the_bars_publishes_with_nulls_not_a_crash(lab, tmp_path, monkeypatch) -> None:
    """The card writes the bars in parallel with this page. A list the flat-rule card wrote
    carries none of them, and a field the lab could not fill is null: each publishes as null,
    nothing is computed here, and a half record is no record."""
    flat = {key: value for key, value in row("TOR", "MTL").items() if key not in CARD_BAR_FIELDS}
    partial = row("NYI", "BOS", player="Partial", player_id=4, surprise_bar=None, hit_rate=0.0, rarity=1.0,
                  rule="tier", band="45-59", cell_record={"wagers": 12, "roi": 0.01})
    write_list(lab, [flat, partial])

    by = {g["home"]["abbr"]: g["drought"] for g in build(lab, tmp_path / "out", monkeypatch)["games"]}

    assert set(by["TOR"][0]) == SCHEMA_KEYS and by["TOR"][0]["player"] == "Assist Man" and by["TOR"][0]["drought"] == 7
    assert {key: by["TOR"][0][key] for key in BAR_KEYS} == dict.fromkeys(BAR_KEYS), "a missing bar is null, never invented"
    partial_out = by["NYI"][0]
    assert partial_out["surpriseBar"] is None and partial_out["hitRate"] == 0.0 and partial_out["rarity"] == 1.0
    assert partial_out["tierBar"] == 5 and partial_out["rule"] == "tier" and partial_out["band"] == "45-59"
    assert partial_out["cellRecord"] is None, "a record missing its interval is no record"
    assert partial_out["oneIn"] == 20, "the card's one_in is copied, never recomputed from the hit rate here"

    listed = {"rows": [row("TOR", "MTL", rule="stake", band="", tier_bar="5", surprise_bar=float("nan"),
                          cell_record={"wagers": 10.0, "roi": "0.1", "ci_low": None, "ci_high": 0.2})]}
    odd = site_module().drought_for_game(listed, "TOR", "MTL", False)[0]
    assert odd["rule"] is None and odd["band"] is None, "a rule or band outside the contract is not one"
    assert odd["tierBar"] == 5 and odd["surpriseBar"] is None and odd["cellRecord"] is None
    # An unhashable rule is outside the contract too, not a TypeError that takes the whole build down.
    for bad_rule in ([], {}, ["both"]):
        unhashable = {"rows": [row("TOR", "MTL", rule=bad_rule)]}
        assert site_module().drought_for_game(unhashable, "TOR", "MTL", False)[0]["rule"] is None, bad_rule
    # An infinity is nothing: json.dumps would write `Infinity`, which the browser's JSON.parse refuses.
    infinite = {"rows": [row("TOR", "MTL", hit_rate=float("inf"), rarity=float("-inf"), one_in=float("inf"), tier_bar=float("inf"),
                             cell_record={"wagers": 184, "roi": float("inf"), "ci_low": -0.017, "ci_high": 0.239})]}
    out = site_module().drought_for_game(infinite, "TOR", "MTL", False)[0]
    assert (out["hitRate"], out["rarity"], out["oneIn"], out["tierBar"], out["cellRecord"]) == (None, None, None, None, None)
    json.dumps(out, allow_nan=False)


def test_the_sentence_names_the_drought_list_and_both_bars(lab, tmp_path, monkeypatch) -> None:
    sentence = site_module().DROUGHT_RULE_SENTENCE

    assert "Due List" in sentence and "unstaked" in sentence
    assert "tier bar" in sentence and "equal-surprise bar" in sentence and "either bar" in sentence
    assert "5+ straight" not in sentence, "the flat rule of #307 is gone"
    assert sentence.count(". ") == 0 and sentence.endswith("."), "one sentence"
    write_list(lab, [row("TOR", "MTL")])
    assert build(lab, tmp_path / "out", monkeypatch)["droughtNote"].startswith(sentence)


def test_the_page_calls_it_the_drought_list_and_reads_every_new_field_guarded() -> None:
    page = (ROOT / "web" / "Board.dc.html").read_text(encoding="utf-8")

    assert "Drought rule" not in page and "drought rule" not in page
    for label in ("Due List · potential bets", "Due List ×${dr.length}", "Due List · ${dCount}",
                  "Due List starts with the regular season", "Nobody on the Due List tonight"):
        assert label in page, label
    for field in ("tierBar", "surpriseBar", "rarity", "oneIn", "cellRecord", "for him", "no record for this cell",
                  "This cell${DROUGHT_WINDOW}", "data.droughtWindow"):
        assert field in page, field
    assert "This cell 2024-26" not in page, "the measured window is read from the board, never hard-coded on a page three labs share"
    assert '"cellRecord" in x' in page, "an older board without the field renders no record line at all"


def test_a_game_nobody_qualifies_in_carries_an_empty_array(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")])

    board = build(lab, tmp_path / "out", monkeypatch)

    assert {g["home"]["abbr"]: g["drought"] for g in board["games"]}["NYI"] == []


def test_the_note_is_the_rule_and_the_backtest_headline_read_from_its_file(lab, tmp_path, monkeypatch) -> None:
    outputs = lab / "data" / "outputs"
    (outputs / "drought_rule_backtest.json").write_text(BACKTEST_JSON.read_text())
    write_list(lab, [row("TOR", "MTL")])

    board = build(lab, tmp_path / "out", monkeypatch)
    note = board["droughtNote"]

    assert "70+ points, 30+ goals or 30+ assists" in note and "unstaked" in note and "Due List" in note
    # The shipped rule's card-window headline (either bar), as the committed backtest JSON states it.
    assert "points -1.6% over 311 wagers" in note and "goals -7.0% over 1355" in note and "assists -8.4% over 2135" in note
    assert "no category's interval sits above zero" in note
    assert "did not reach this build" not in note
    # The seasons the cell records were measured on, read from the same file's card-window buckets (2024 and 2025 starts).
    assert board["droughtWindow"] == "2024-26"
    assert site_module().drought_window(tmp_path / "nowhere") is None
    (outputs / "drought_rule_backtest.json").write_text(json.dumps({"buckets": [
        {"window": "card", "season": "2026", "market": "goals", "bucket": "x"}, {"window": "late", "season": "2019", "market": "goals", "bucket": "x"},
        {"window": "card", "season": "both", "market": "goals", "bucket": "x"}]}))
    assert site_module().drought_window(lab) == "2026-27", "one season spans itself; the late window and the pooled bucket name none"
    (outputs / "drought_rule_backtest.json").write_text("{not json")
    assert site_module().drought_window(lab) is None


def test_a_list_built_for_another_day_is_never_shown(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")], day=date(2026, 10, 7))

    board = build(lab, tmp_path / "out", monkeypatch)

    assert all(g["drought"] == [] for g in board["games"])
    assert "did not reach this build" in board["droughtNote"], "an empty array must not read as nobody qualifying"


def test_no_list_at_all_is_an_empty_array_with_a_note_not_a_crash(lab, tmp_path, monkeypatch) -> None:
    board = build(lab, tmp_path / "out", monkeypatch)

    assert all(g["drought"] == [] for g in board["games"]) and "did not reach this build" in board["droughtNote"]
    assert board["droughtWindow"] is None, "no backtest file in this lab: no window is named"


def test_a_game_that_has_started_lists_nobody(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")])

    board = build(lab, tmp_path / "out", monkeypatch, start="2020-10-08T00:00:00Z")

    assert all(g["drought"] == [] for g in board["games"])


def test_the_builder_imports_nothing_from_the_card() -> None:
    import ast

    imported = set()
    for node in ast.walk(ast.parse((ROOT / "web" / "build_site_json.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)

    assert not {m for m in imported if m.startswith("nhl_betting_lab.reports") or "gameday_card" in m}, imported


def test_the_schema_the_builder_writes_is_the_one_the_page_reads() -> None:
    schema = (ROOT / "web" / "SCHEMA.md").read_text(encoding="utf-8")

    for key in SCHEMA_KEYS | {"droughtNote", "droughtWindow", "games[].drought"}:
        assert key in schema, key
    assert CLUBS and SLATE


# -- the page, rendered through its own component --------------------------

#: Drives web/Board.dc.html's x-dc component under node on a board.json, as the browser does
#: after load(): S/F/L are the three lib modules, vm is ADAPTERS.nhl.board(data). Prints each
#: game's Due List rows as the Tonight tab lays them out (meta: the bar and the "for him"
#: line; record: the cell), and the Props tab's Due List view beside it.
_PAGE_DRIVER = r"""
import { readFileSync } from "node:fs";
import * as S from "./lib/sports.js";
import * as F from "./lib/format.js";
import * as L from "./lib/live.js";
const [boardPath, dataPath] = process.argv.slice(2);
const data = JSON.parse(readFileSync(dataPath, "utf8"));
const html = readFileSync(boardPath, "utf8");
const m = html.match(/<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/);
if (!m) throw new Error("Board.dc.html carries no component script");
globalThis.location = { hostname: "localhost", hash: "", search: "", pathname: "/Board.dc.html" };
class DCLogic { constructor() { this.props = {}; this.state = {}; } setState(s, cb) { this.state = { ...this.state, ...s }; if (cb) cb(); } }
const Component = new Function("DCLogic", m[1] + "\nreturn Component;")(DCLogic);
const c = new Component();
c.S = S; c.F = F; c.L = L;
const vm = S.ADAPTERS.nhl.board(data);
vm.otherSports = [];
const pick = (x) => ({ player: x.player, meta: x.meta, record: x.record });
const out = {};
for (const tab of ["tonight", "props"]) {
  c.state = { vm, data, pv: null, sportKey: "nhl", deployed: false, tab, propView: "drought", now: Date.now(), expanded: {}, allOpen: true, wide: true,
    f: { q: "", game: "", team: "", market: "", betsOnly: false }, live: { mode: "off", data: null, at: null, error: null, nextAt: null }, boxes: {} };
  const r = c.renderVals();
  out[tab] = { games: r.groups.flatMap((grp) => grp.games.map((g) => ({ label: g.sum.drought, rows: g.drought.rows.map(pick) }))),
               view: r.dv.groups.map((g) => ({ sub: g.sub, rows: g.rows.map(pick) })) };
}
process.stdout.write(JSON.stringify(out));
"""


def render_page(board: dict, tmp_path: Path) -> dict:
    node = shutil.which("node")
    assert node, "node is not on PATH; this test renders the Board page's own component, which is what a visitor reads"
    site = tmp_path / "rendered-page"
    (site / "lib").mkdir(parents=True, exist_ok=True)
    for name in ("sports.js", "format.js", "live.js"):
        shutil.copyfile(ROOT / "web" / "lib" / name, site / "lib" / name)
    (site / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (site / "render.mjs").write_text(_PAGE_DRIVER, encoding="utf-8")
    data = site / "board.json"
    data.write_text(json.dumps(board), encoding="utf-8")
    result = subprocess.run([node, str(site / "render.mjs"), str(ROOT / "web" / "Board.dc.html"), str(data)],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, f"the Board page threw on this board, so it renders nothing:\n{result.stderr}"
    return json.loads(result.stdout)


def test_the_page_prints_the_cards_rarity_line_for_every_row_and_names_the_measured_window(lab, tmp_path, monkeypatch) -> None:
    """Rendered through Board.dc.html's own component on the builder's output, so producer and page are pinned together.

    The rarest rows are the ones rarity's 4 dp rounds to 0.0 (p 0.7 at 9 straight, p 0.75 at 8): the page
    used to print no "for him" line for exactly those, the rows the sort puts first, while every ordinary row
    got one. It now prints the card's own N (oneIn) with a thousands separator; a row written before oneIn
    existed reads N off the rarity and spells rarity 0 as the card does; the cell's window comes from the
    board; and a row that is not an object is skipped, not thrown on.
    """
    (lab / "data" / "outputs" / "drought_rule_backtest.json").write_text(BACKTEST_JSON.read_text())
    write_list(lab, [
        row("TOR", "MTL", player="Rarest", player_id=1, market="points", last_season=104, drought=9, american_odds=-190.0, heavy_juice=True,
            tier_bar=3, surprise_bar=3, hit_rate=0.7, rarity=0.0, one_in=50805, rule="both", band="100+",
            cell_record={"wagers": 15, "roi": 0.155, "ci_low": -0.255, "ci_high": 0.469}),
        older(row("TOR", "MTL", player="Old Never", player_id=2, market="goals", last_season=40, drought=3, american_odds=None, book="",
                  tier_bar=3, surprise_bar=1, hit_rate=1.0, rarity=0.0, rule="both", band="40+", cell_record=None)),
        older(row("TOR", "MTL", player="Old Rarer", player_id=3, last_season=60, drought=5, tier_bar=3, surprise_bar=2, hit_rate=0.9,
                  rarity=0.0, rule="both", band="60+")),
        older(row("TOR", "MTL", player="Old Plain", player_id=4, american_odds=None, book="")),
        {key: value for key, value in row("TOR", "MTL", player="Flat", player_id=5, american_odds=None, book="").items()
         if key not in CARD_BAR_FIELDS},
    ])
    board = build(lab, tmp_path / "out", monkeypatch)
    assert board["droughtWindow"] == "2024-26"
    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert [r["oneIn"] for r in tor["drought"]] == [50805, None, None, None, None]
    tor["drought"].append(None)

    page = render_page(board, tmp_path)

    shown = next(g for g in page["tonight"]["games"] if g["rows"])
    by = {r["player"]: r for r in shown["rows"]}
    assert shown["label"] == "Due List ×5" and list(by) == ["Rarest", "Old Never", "Old Rarer", "Old Plain", "Flat"], (
        "the card's order is kept and the null row is skipped, not thrown on")
    assert by["Rarest"]["meta"] == "bar 3 · both · 1 in 50,805 for him", "the rarest row carries its line, from oneIn, with a separator"
    assert by["Old Never"]["meta"] == "bar 3 · both · never last season"
    assert by["Old Rarer"]["meta"] == "bar 3 · both · rarer than 1 in 10,000 for him", "what the card prints for the same row"
    assert by["Old Plain"]["meta"] == "bar 7 · both · 1 in 20 for him", "a row without oneIn reads N off the rarity, as before"
    assert by["Flat"]["meta"] == "", "a flat-rule row has no bar and no rarity: no line at all"
    assert by["Rarest"]["record"] == "This cell 2024-26: +15.5% over 15 (95% -25.5% to +46.9%)"
    assert by["Old Never"]["record"] == "no record for this cell"
    assert by["Old Plain"]["record"] == "This cell 2024-26: +10.5% over 184 (95% -1.7% to +23.9%)"
    view = page["props"]["view"]
    assert len(view) == 1 and view[0]["sub"].endswith("5 listed") and [r["meta"] for r in view[0]["rows"]] == [by[p]["meta"] for p in by]

    board["droughtWindow"] = None
    unnamed = next(g for g in render_page(board, tmp_path)["tonight"]["games"] if g["rows"])
    assert unnamed["rows"][0]["record"].startswith("This cell: +15.5% over 15"), (
        "a board naming no window prints none, never a season the record was not measured on")
