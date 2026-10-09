"""The site shows the card's player props tonight, and grades them the next morning.

Cooper, 2026-10-09: "player props need to be posting to the website". The
pages already rendered a `props` block (web/SCHEMA.md, "Additions (props and
live scores)"), and `season_record` already summed one, but nothing wrote it:
every board read "Props are not on this board" while the card staked props
every night.

`build_board` now writes `props` from the card's own best bets (price, book, model probability, edge, tier, units — nothing priced again; leans are counted, not listed, by
Cooper's 2026-10-09 call "Only show the best bets"),
joined to a game through the same provider names the team pick uses, and
`settle` grades the frozen rows the next morning on the box-score logs by the
forward ledger's rules. Driven through the real `main()` with only the NHL
schedule stubbed, and rendered through the page's own adapters under node.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

from test_site_never_calls_an_unpriced_game_a_pass import (
    BOARD_DAY,
    CLUBS,
    WEB,
    build,
    make_lab,
)

NEXT_DAY = BOARD_DAY + timedelta(days=1)
GAME = "2026020101"  # MTL @ TOR
START = f"{BOARD_DAY.isoformat()}T23:00:00Z"


def _prop(player, market, selection, line, odds, edge, section, *, units=0.0, tier="C", day=BOARD_DAY, reason=""):
    return {
        "date": day.isoformat(), "commence_time": f"{day.isoformat()}T23:00:00Z",
        "home_team": CLUBS["TOR"][2], "away_team": CLUBS["MTL"][2], "market": market,
        "selection": selection, "player": player, "line": line, "american_odds": odds,
        "book": "Bovada", "model_probability": 0.69, "implied_probability": 0.49,
        "edge": edge, "fair_american": -222, "tier": tier, "suggested_units": units,
        "section": section, "demotion_reason": reason,
    }


def _add_props(lab: Path) -> None:
    path = lab / "data" / "outputs" / "gameday_card.json"
    card = json.loads(path.read_text(encoding="utf-8"))
    card["best_bets"].append(_prop("Auston Matthews", "shots_on_goal", "under", 3.5, 105, 0.202,
                                   "Best bets", units=0.5, tier="A"))
    # Scratched tonight: on the board, then void the next morning.
    card["best_bets"].append(_prop("John Tavares", "shots_on_goal", "over", 2.5, 110, 0.13,
                                   "Best bets", units=0.25, tier="B"))
    card["leans"] = [
        _prop("Nick Suzuki", "points", "under", 0.5, 123, 0.15, "Leans", reason="points is never staked"),
        _prop("Sam Montembeault", "goalie_saves", "over", 24.5, -110, 0.09, "Leans"),
        # Tomorrow's game between the same clubs: not tonight's board.
        _prop("Auston Matthews", "goals", "over", 0.5, 150, 0.2, "Leans", day=NEXT_DAY),
    ]
    card["passes"].append(_prop("William Nylander", "shots_on_goal", "over", 3.5, 120, 0.01, "Passes"))
    card["excluded_markets"] = {"hits": "priced for 1 of 2 games"}
    path.write_text(json.dumps(card), encoding="utf-8")


LOG_COLUMNS = ["game_id", "date", "player_id", "player", "position", "team", "toi_seconds",
               "shots_on_goal", "goals", "assists", "points", "blocked_shots", "hits", "saves"]


def _logs(lab: Path, *, tonight: bool) -> None:
    rows = [
        ["2026020001", "2026-10-01", "8479318", "Auston Matthews", "C", "TOR", 1200, 4, 1, 0, 1, 0, 1, 0],
        ["2026020002", "2026-10-01", "8480018", "Nick Suzuki", "C", "MTL", 1200, 2, 0, 1, 1, 0, 0, 0],
        ["2026020001", "2026-10-01", "8475166", "John Tavares", "C", "TOR", 1100, 3, 0, 1, 1, 0, 0, 0],
        ["2026020002", "2026-10-01", "8477492", "Sam Montembeault", "G", "MTL", 3600, 0, 0, 0, 0, 0, 0, 30],
        # Another Nick Suzuki on a club not in the game: never this game's player.
        ["2026020003", "2026-10-01", "9999999", "Nick Suzuki", "R", "BOS", 900, 1, 0, 0, 0, 0, 0, 0],
    ]
    if tonight:
        rows += [
            [GAME, BOARD_DAY.isoformat(), "8479318", "Auston Matthews", "C", "TOR", 1250, 2, 0, 0, 0, 0, 0, 0],
            [GAME, BOARD_DAY.isoformat(), "8480018", "Nick Suzuki", "C", "MTL", 1180, 3, 0, 1, 1, 0, 0, 0],
            # The backup sat: on the sheet, no ice time, so his saves prop is void.
            [GAME, BOARD_DAY.isoformat(), "8477492", "Sam Montembeault", "G", "MTL", 0, 0, 0, 0, 0, 0, 0, 0],
        ]
    path = lab / "data" / "processed" / "player_game_logs.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(LOG_COLUMNS)
        writer.writerows(rows)


_DRIVER = r"""
import { readFileSync } from "node:fs";
import { ADAPTERS } from "./lib/sports.js";
const [kind, path] = process.argv.slice(2);
const data = JSON.parse(readFileSync(path, "utf8"));
process.stdout.write(JSON.stringify(kind === "board" ? ADAPTERS.nhl.props(data) : ADAPTERS.nhl.propResults(data)));
"""


def _render(kind: str, payload: dict, tmp_path: Path) -> dict:
    node = shutil.which("node")
    assert node, "node is not on PATH; the page's own adapter is what a visitor reads"
    site = tmp_path / f"render-{kind}"
    (site / "lib").mkdir(parents=True, exist_ok=True)
    for name in ("sports.js", "format.js"):
        shutil.copyfile(WEB / "lib" / name, site / "lib" / name)
    (site / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (site / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    (site / "data.json").write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run([node, str(site / "render.mjs"), kind, str(site / "data.json")],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _lab(tmp_path, monkeypatch, *, tonight: bool) -> Path:
    lab = make_lab(tmp_path, monkeypatch, staged=True)
    _add_props(lab)
    _logs(lab, tonight=tonight)
    return lab


def test_tonights_props_are_on_the_board(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch, tonight=False)
    board, _ = build(lab, tmp_path / "site", monkeypatch)
    props = board["props"]
    assert props["status"] == "ok"
    rows = props["rows"]
    assert [(r["player"], r["market"], r["kind"]) for r in rows] == [
        ("Auston Matthews", "shots_on_goal", "bet"),
        ("John Tavares", "shots_on_goal", "bet"),
    ], "the card's best bets for tonight only; leans, the pass and tomorrow's row are not listed (Cooper, 2026-10-09)"
    bet = rows[0]
    assert bet == {
        "gameId": GAME, "player": "Auston Matthews", "playerId": "8479318", "team": "TOR", "opp": "MTL",
        "position": "C", "market": "shots_on_goal", "line": 3.5, "side": "under", "price": 105, "book": "Bovada",
        "projection": None, "modelProb": 0.69, "fairPrice": -222, "edgePct": 20.2, "kind": "bet", "tier": "A",
        "units": 0.5, "allowlisted": False, "starterConfirmed": None,
    }
    assert "Only best bets are listed; 3 other priced props (leans and passes) are not." in props["note"]
    assert props["marketNotes"]["hits"].startswith("Excluded tonight, not a pass")
    assert "points" in props["marketNotes"]

    page = _render("board", board, tmp_path)
    assert page["counts"] == {"bets": 2, "leans": 0, "total": 2}
    assert page["rows"][0]["stake"] == "Tier A · 0.5 units · $12.50"


def test_the_next_morning_grades_the_props(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch, tonight=False)
    out = tmp_path / "site"
    build(lab, out, monkeypatch)  # freezes tonight's board, props included
    _logs(lab, tonight=True)
    board, results = build(lab, out, monkeypatch, day=NEXT_DAY, finals=True)

    props = results["props"]
    graded = {r["player"]: r for r in props["rows"]}
    assert (graded["Auston Matthews"]["actual"], graded["Auston Matthews"]["result"]) == (2, "win")
    assert graded["Auston Matthews"]["profitUnits"] == 0.53  # 0.5 units at +105
    assert graded["John Tavares"]["result"] == "void", "a best bet on a player who did not dress is void"
    assert set(graded) == {"Auston Matthews", "John Tavares"}, "no lean was published, so none is graded"
    assert props["summary"] == {"w": 1, "l": 0, "p": 0, "units": 0.53, "ungraded": 0}
    assert props["season"]["w"] == 1 and props["seasonLeans"]["l"] == 0
    assert board["record"]["props"]["w"] == 1, "the board's season line counts the props"
    assert results["summary"]["picks"] == {"w": 1, "l": 0, "p": 0}, "props never reach the team record"

    page = _render("results", results, tmp_path)
    assert page["summaryLine"] == "2 best bets settled", "no leans line when no lean was published"


def test_a_prop_whose_box_score_has_not_arrived_waits(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch, tonight=False)
    out = tmp_path / "site"
    build(lab, out, monkeypatch)
    _, results = build(lab, out, monkeypatch, day=NEXT_DAY, finals=True)
    props = results["props"]
    assert all(r["result"] is None for r in props["rows"]), "no box score is not a scratch"
    assert props["summary"]["ungraded"] == 2
