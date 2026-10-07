"""`games[].drought` and `droughtNote`: the shape web/SCHEMA.md names, written by the site builder.

The Board's game cards render Cooper's Drought List (2026-10-07; that evening the tier and
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
from datetime import date
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY, CLUBS, SLATE, make_lab, schedule, site_module,
)

#: What a row gained on 2026-10-07 evening, beyond the #307 shape.
BAR_KEYS = {"tierBar", "surpriseBar", "hitRate", "rarity", "rule", "band", "cellRecord"}
SCHEMA_KEYS = {"player", "playerId", "team", "market", "line", "lastSeason", "drought", "price", "book", "heavyJuice"} | BAR_KEYS
#: The same fields as the card's drought_list.json spells them.
CARD_BAR_FIELDS = ("tier_bar", "surprise_bar", "hit_rate", "rarity", "rule", "band", "cell_record")
ROOT = Path(__file__).resolve().parents[1]


def row(home: str, away: str, **kw) -> dict:
    base = {"date": BOARD_DAY.isoformat(), "home_team": home, "away_team": away, "team": home, "opponent": away,
            "player": "Assist Man", "player_id": 8471111, "market": "assists", "line": 0.5, "last_season": 31,
            "drought": 6, "american_odds": 170.0, "book": "DraftKings", "heavy_juice": False,
            # 31 assists is the 30-44 band (bar 5); a 35% hit rate makes his equal-surprise bar 7
            # (0.65^7 = 0.049 <= 0.05); six games reach the tier bar only, but the card's figures
            # are what is published, so the fixture's "both" is what the board must show.
            "tier_bar": 5, "surprise_bar": 7, "hit_rate": 0.35, "rarity": 0.049, "rule": "both", "band": "30-44",
            "cell_record": {"wagers": 184, "roi": 0.105, "ci_low": -0.017, "ci_high": 0.239}}
    base.update(kw)
    return base


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
                            "lastSeason": 31, "drought": 6, "price": 170, "book": "DraftKings", "heavyJuice": False,
                            "tierBar": 5, "surpriseBar": 7, "hitRate": 0.35, "rarity": 0.049, "rule": "both", "band": "30-44",
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

    assert set(by["TOR"][0]) == SCHEMA_KEYS and by["TOR"][0]["player"] == "Assist Man" and by["TOR"][0]["drought"] == 6
    assert {key: by["TOR"][0][key] for key in BAR_KEYS} == dict.fromkeys(BAR_KEYS), "a missing bar is null, never invented"
    partial_out = by["NYI"][0]
    assert partial_out["surpriseBar"] is None and partial_out["hitRate"] == 0.0 and partial_out["rarity"] == 1.0
    assert partial_out["tierBar"] == 5 and partial_out["rule"] == "tier" and partial_out["band"] == "45-59"
    assert partial_out["cellRecord"] is None, "a record missing its interval is no record"

    listed = {"rows": [row("TOR", "MTL", rule="stake", band="", tier_bar="5", surprise_bar=float("nan"),
                          cell_record={"wagers": 10.0, "roi": "0.1", "ci_low": None, "ci_high": 0.2})]}
    odd = site_module().drought_for_game(listed, "TOR", "MTL", False)[0]
    assert odd["rule"] is None and odd["band"] is None, "a rule or band outside the contract is not one"
    assert odd["tierBar"] == 5 and odd["surpriseBar"] is None and odd["cellRecord"] is None


def test_the_sentence_names_the_drought_list_and_both_bars(lab, tmp_path, monkeypatch) -> None:
    sentence = site_module().DROUGHT_RULE_SENTENCE

    assert "Drought List" in sentence and "unstaked" in sentence
    assert "tier bar" in sentence and "equal-surprise bar" in sentence and "either bar" in sentence
    assert "5+ straight" not in sentence, "the flat rule of #307 is gone"
    assert sentence.count(". ") == 0 and sentence.endswith("."), "one sentence"
    write_list(lab, [row("TOR", "MTL")])
    assert build(lab, tmp_path / "out", monkeypatch)["droughtNote"].startswith(sentence)


def test_the_page_calls_it_the_drought_list_and_reads_every_new_field_guarded() -> None:
    page = (ROOT / "web" / "Board.dc.html").read_text(encoding="utf-8")

    assert "Drought rule" not in page and "drought rule" not in page
    for label in ("Drought List · potential bets", "Drought List ×${dr.length}", "Drought List · ${dCount}",
                  "Drought List starts with the regular season", "Nobody is on the Drought List tonight"):
        assert label in page, label
    for field in ("tierBar", "surpriseBar", "rarity", "cellRecord", "for him", "no record for this cell", "This cell 2024-26"):
        assert field in page, field
    assert '"cellRecord" in x' in page, "an older board without the field renders no record line at all"


def test_a_game_nobody_qualifies_in_carries_an_empty_array(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")])

    board = build(lab, tmp_path / "out", monkeypatch)

    assert {g["home"]["abbr"]: g["drought"] for g in board["games"]}["NYI"] == []


def test_the_note_is_the_rule_and_the_backtest_headline_read_from_its_file(lab, tmp_path, monkeypatch) -> None:
    outputs = lab / "data" / "outputs"
    (outputs / "drought_rule_backtest.json").write_text((ROOT / "data" / "outputs" / "drought_rule_backtest.json").read_text())
    write_list(lab, [row("TOR", "MTL")])

    note = build(lab, tmp_path / "out", monkeypatch)["droughtNote"]

    assert "70+ points, 30+ goals or 30+ assists" in note and "unstaked" in note and "Drought List" in note
    # The shipped rule's card-window headline (either bar), as the committed backtest JSON states it.
    assert "points -1.6% over 311 wagers" in note and "goals -7.0% over 1355" in note and "assists -8.4% over 2135" in note
    assert "no category's interval sits above zero" in note
    assert "did not reach this build" not in note


def test_a_list_built_for_another_day_is_never_shown(lab, tmp_path, monkeypatch) -> None:
    write_list(lab, [row("TOR", "MTL")], day=date(2026, 10, 7))

    board = build(lab, tmp_path / "out", monkeypatch)

    assert all(g["drought"] == [] for g in board["games"])
    assert "did not reach this build" in board["droughtNote"], "an empty array must not read as nobody qualifying"


def test_no_list_at_all_is_an_empty_array_with_a_note_not_a_crash(lab, tmp_path, monkeypatch) -> None:
    board = build(lab, tmp_path / "out", monkeypatch)

    assert all(g["drought"] == [] for g in board["games"]) and "did not reach this build" in board["droughtNote"]


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

    for key in SCHEMA_KEYS | {"droughtNote", "games[].drought"}:
        assert key in schema, key
    assert CLUBS and SLATE
