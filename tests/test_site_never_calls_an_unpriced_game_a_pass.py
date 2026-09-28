"""A game the board holds no price for is not a pass, and the page must not say it is.

`web/build_site_json.py::build_board` attaches market lines and the card's
pick to a game only by joining through `data/staging/*.csv`. Publish Site
restores the `gameday-state` and `gameday-reports` artifacts and nothing
else, and neither carries `data/staging` (on purpose: the staged file is the
provider's raw odds, in a public repository). So from opening night on
2026-09-29 every regular-season game on the public board would have been
published with `pick: null`, no moneyline, no puck line, no total, and no
regulation prices, and `web/lib/sports.js` renders a null pick as "No market
clears the edge bar" whenever markets are allowlisted (twelve are). That is a
model judgement nobody made. CLAUDE.md's first hard rule is that a missing
price stays missing and is never described as a pass or a no-value call.

Found by the failure-shape audit (3 of 3 refuters). Reproduced through the
real `main()`: with the Publish Site tree, 5 of 5 opening-night games
published `pick: None` while the card held a best bet (MTL @ TOR moneyline
home +112, edge 0.110); the same inputs plus the staged CSV published
"TOR +112", edge 11.0%. The next morning graded every game "No play" and the
history index froze 0 bets for the day.

The same shape reached four other places, and these tests hold all of them:

* `web/Graphic.dc.html` printed a hard-coded "Nothing clears the bar" under
  every game without a pick — including exhibitions, where the model
  abstains, and a slate where nothing is allowlisted.
* The builder published the current price as the "open" whenever no
  line-movement capture was on disk, which in Publish Site is always.
* A board built without the model's game history said it showed "the
  schedule and market lines only"; the lines are attached inside the model's
  branch, so it showed no line at all.
* `nhlResults` read `g.total.line` unguarded, so the morning after an
  unpriced board — no game carries a total — the Results page threw and
  rendered nothing.

Carrying prices to Publish Site so the lines and picks actually appear is a
decision about publishing provider odds on a public page, and is left to the
owner. What is fixed here is that the page never says something false while
they are missing.

The builder is driven through its own `main()`, loaded by path as the
workflow runs it, with only the NHL schedule stubbed (it needs the network).
The card is written by the real `save_card`, the team-name map is built by
the real `build_team_name_map` from a boxscore cache in `tmp_path`, and the
page is rendered through `web/lib/sports.js` and the Graphic page's own
`renderVals` under node.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from nhl_betting_lab.config import THIN_HISTORY_GAMES
from nhl_betting_lab.providers import team_names
from nhl_betting_lab.reports.gameday_card import (
    BEST_BETS_SECTION,
    Candidate,
    GamedayCard,
    PASSES_SECTION,
    save_card,
)

from test_scripts import load_script

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
BUILD_SCRIPT = WEB / "build_site_json.py"

BOARD_DAY = date(2026, 10, 8)  # a regular-season league date

#: abbrev -> (placeName, commonName) as the NHL API and the boxscores spell
#: them, and the provider's spelling of the full name.
CLUBS = {
    "TOR": ("Toronto", "Maple Leafs", "Toronto Maple Leafs"),
    "MTL": ("Montréal", "Canadiens", "Montreal Canadiens"),
    "NYI": ("New York", "Islanders", "New York Islanders"),
    "BOS": ("Boston", "Bruins", "Boston Bruins"),
}
#: (away, home, NHL game id)
SLATE = (("MTL", "TOR", "2026020101"), ("BOS", "NYI", "2026020102"))


def site_module():
    """`web/build_site_json.py`, loaded by path as the workflow runs it."""
    spec = importlib.util.spec_from_file_location("_site_build_unpriced", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- rendering through the page's own code ---------------------------------

#: Runs a board through the NHL adapter and the Graphic page's renderVals,
#: or a results file through the results adapter. The two files under
#: web/lib are copied beside a package.json that marks them ES modules,
#: because node reads a bare `.js` as CommonJS on the versions runners carry.
_DRIVER = r"""
import { readFileSync } from "node:fs";
import { ADAPTERS } from "./lib/sports.js";
const [kind, dataPath, graphicPath] = process.argv.slice(2);
const data = JSON.parse(readFileSync(dataPath, "utf8"));
if (kind === "results") {
  process.stdout.write(JSON.stringify({ results: ADAPTERS.nhl.results(data) }));
} else {
  const vm = ADAPTERS.nhl.board(data);
  const html = readFileSync(graphicPath, "utf8");
  const m = html.match(/<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/);
  if (!m) throw new Error("Graphic.dc.html carries no component script");
  class DCLogic { constructor() { this.props = {}; this.state = {}; } setState(s) { this.state = { ...this.state, ...s }; } }
  const Component = new Function("DCLogic", m[1] + "\nreturn Component;")(DCLogic);
  const graphic = new Component();
  graphic.state = { vm: { ...vm, otherSports: [] } };
  process.stdout.write(JSON.stringify({ board: vm, graphic: graphic.renderVals() }));
}
"""


def _node(kind: str, payload: dict, tmp_path: Path) -> dict:
    node = shutil.which("node")
    assert node, (
        "node is not on PATH. These tests render the page's own adapter, "
        "which is the half of the site that prints the sentence a visitor "
        "reads; without it they would check JSON and nothing on the page."
    )
    site = tmp_path / "rendered-site"
    (site / "lib").mkdir(parents=True, exist_ok=True)
    for name in ("sports.js", "format.js"):
        shutil.copyfile(WEB / "lib" / name, site / "lib" / name)
    (site / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (site / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    data = site / f"{kind}.json"
    data.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [node, str(site / "render.mjs"), kind, str(data), str(WEB / "Graphic.dc.html")],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, (
        f"the page's {kind} adapter threw on this file, so the page renders "
        f"nothing:\n{result.stderr}"
    )
    return json.loads(result.stdout)


def render_board(board: dict, tmp_path: Path) -> dict:
    """{"board": nhlBoard(board), "graphic": Graphic renderVals()}."""
    return _node("board", board, tmp_path)


def render_results(results: dict, tmp_path: Path) -> dict:
    return _node("results", results, tmp_path)["results"]


def page_games(rendered: dict) -> list[dict]:
    return [game for group in rendered["board"]["groups"] for game in group["games"]]


# -- the lab a Publish Site runner holds -----------------------------------


def _boxscore(path: Path, home: str, away: str) -> None:
    def side(abbrev: str) -> dict:
        place, common, _ = CLUBS[abbrev]
        return {"abbrev": abbrev, "placeName": {"default": place}, "commonName": {"default": common}}

    path.write_text(json.dumps({"homeTeam": side(home), "awayTeam": side(away)}), encoding="utf-8")


def _team_games(path: Path) -> None:
    """Results ending on 2026-04-05, so TeamModel fits and every club is known.

    Exactly `THIN_HISTORY_GAMES` of them, the fewest the board projects from
    (tests/test_the_board_refuses_a_thin_history.py). This held a month, 36
    games, and every test here that reads the board's projections asserted
    that the board projects from it; the board now calls that history thin
    and projects nothing, as Gameday Refresh calls a run fitted on it
    degraded. The history ends on the same day and repeats the same six
    results, only further back.
    """
    columns = ["game_id", "season", "game_type", "date", "start_time_utc",
               "home_team", "away_team", "home_goals", "away_goals",
               "home_shots", "away_shots", "regulation"]
    pairs = [("TOR", "MTL", 4, 2), ("MTL", "TOR", 2, 3), ("NYI", "BOS", 3, 3),
             ("BOS", "NYI", 2, 1), ("TOR", "BOS", 5, 2), ("NYI", "MTL", 2, 4)]
    rows = []
    start = date(2026, 4, 5) - timedelta(days=THIN_HISTORY_GAMES - 1)
    for index in range(THIN_HISTORY_GAMES):
        home, away, hg, ag = pairs[index % len(pairs)]
        day = start + timedelta(days=index)
        rows.append([2025020000 + index, 20252026, 2, day.isoformat(),
                     f"{day.isoformat()}T23:00:00Z", home, away, hg, ag,
                     30, 28, hg != ag])
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)


def _candidate(away: str, home: str, *, market: str, selection: str,
               odds: float, edge: float, section: str, line=None) -> dict:
    return Candidate(
        date=BOARD_DAY.isoformat(), commence_time=f"{BOARD_DAY.isoformat()}T23:00:00Z",
        home_team=CLUBS[home][2], away_team=CLUBS[away][2], market=market,
        selection=selection, player="", line=line, american_odds=odds,
        book="draftkings", model_probability=0.58, implied_probability=0.47,
        edge=edge, fair_american=-138, tier="A" if section == BEST_BETS_SECTION else "",
        suggested_units=1.0 if section == BEST_BETS_SECTION else 0.0, section=section,
    ).as_row()


def _card(outputs: Path) -> None:
    """The card as `save_card` writes it: one best bet, one pass."""
    card = GamedayCard(
        generated_at=f"{BOARD_DAY.isoformat()}T13:30:00+00:00", card_generated=True,
        slate_games=len(SLATE), included_markets=("moneyline", "puck_line", "total_goals"),
        best_bets=[_candidate("MTL", "TOR", market="moneyline", selection="home",
                              odds=112, edge=0.110, section=BEST_BETS_SECTION)],
        passes=[_candidate("BOS", "NYI", market="total_goals", selection="under",
                           odds=-105, edge=0.012, section=PASSES_SECTION, line=6.0)],
    )
    save_card(card, output_dir=outputs)


def _price_rows(offset: int = 0) -> list[dict]:
    """Staged provider rows, two books, every team market the board shows."""
    rows = []
    for away, home, _ in SLATE:
        for book, bump in (("draftkings", 0), ("fanduel", 4)):
            def add(market, selection, odds, line=""):
                rows.append({
                    "date": BOARD_DAY.isoformat(), "commence_time": f"{BOARD_DAY.isoformat()}T23:00:00Z",
                    "provider_event_id": f"evt-{home}", "home_team": CLUBS[home][2],
                    "away_team": CLUBS[away][2], "market": market, "player": "",
                    "selection": selection, "line": line, "american_odds": odds,
                    "book": book, "fetched_at": f"{BOARD_DAY.isoformat()}T13:00:00Z",
                })
            add("moneyline", "home", 108 + bump + offset)
            add("moneyline", "away", -130 - bump - offset)
            add("puck_line", "home", 210 + bump, -1.5)
            add("puck_line", "away", -250 - bump, 1.5)
            add("total_goals", "over", -110 + bump, 6.0)
            add("total_goals", "under", -110 - bump, 6.0)
            add("regulation_3_way", "home", 150 + bump)
            add("regulation_3_way", "draw", 330 + bump)
            add("regulation_3_way", "away", 190 + bump)
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_lab(tmp_path: Path, monkeypatch, *, staged: bool, model: bool = True,
             opens: bool = False) -> Path:
    """What the runner holds: gameday-state + gameday-reports, and optionally
    the staged prices Publish Site never restores."""
    lab = tmp_path / "lab"
    raw = tmp_path / "raw"
    (raw / "nhl" / "boxscore").mkdir(parents=True)
    for index, (away, home, _) in enumerate(SLATE):
        _boxscore(raw / "nhl" / "boxscore" / f"{index}.json", home, away)
    monkeypatch.setattr(team_names, "RAW_DIR", raw)
    monkeypatch.setattr(team_names, "PROCESSED_DIR", tmp_path / "processed-unused")
    processed = lab / "data" / "processed"
    processed.mkdir(parents=True)
    if model:
        _team_games(processed / "team_games.csv")
    _card(lab / "data" / "outputs")
    if staged:
        _write_csv(lab / "data" / "staging" / "odds_api_prices_staging.csv", _price_rows())
    if opens:
        # Where and how `capture_line_movement.main` writes: one file per
        # league day, each row stamped with its capture's moment. This wrote
        # `<day>_1300.csv`, a name no writer produces, with no `captured_at`
        # (tests/test_the_open_is_one_capture_and_never_a_ladder_rung.py).
        # The rows are the bulk moneyline and total, which the capture does
        # not ask for today; they stand for capturing the team markets too.
        movement = load_script("capture_line_movement.py")
        _write_csv(movement.capture_path(BOARD_DAY.isoformat(), processed_dir=processed),
                   [{**row, "captured_at": f"{BOARD_DAY.isoformat()}T13:00:00+00:00"}
                    for row in _price_rows(offset=20)])
    return lab


def schedule(day: date, *, final: bool = False) -> list[dict]:
    if day != BOARD_DAY:
        return []
    games = []
    for away, home, game_id in SLATE:
        def side(abbrev, score):
            place, common, _ = CLUBS[abbrev]
            entry = {"abbrev": abbrev, "placeName": {"default": place},
                     "commonName": {"default": common}, "record": "1-0-0"}
            if final:
                entry["score"] = score
            return entry
        game = {"id": int(game_id), "gameType": 2, "startTimeUTC": f"{day.isoformat()}T23:00:00Z",
                "venue": {"default": "Arena"}, "venueLocation": {"default": "City"},
                "tvBroadcasts": [], "awayTeam": side(away, 2), "homeTeam": side(home, 5)}
        if final:
            game.update(gameState="OFF", gameOutcome={"lastPeriodType": "REG"})
        games.append(game)
    return games


def build(lab: Path, out: Path, monkeypatch, *, day: date = BOARD_DAY,
          allowlisted: list[str] | None = None, finals: bool = False):
    module = site_module()
    monkeypatch.setattr(module, "schedule_for", lambda d: schedule(d, final=finals and d < day))
    monkeypatch.setattr(
        module, "allowlisted_markets",
        lambda _lab: list(["moneyline", "puck_line", "total_goals"] if allowlisted is None else allowlisted),
    )
    assert module.main(["--lab", str(lab), "--out", str(out), "--date", day.isoformat()]) == 0
    board = json.loads((out / "board.json").read_text(encoding="utf-8"))
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    return board, results


# -- the tests ---------------------------------------------------------------


def test_a_game_with_no_price_is_published_as_unpriced(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert board["phase"] == "regular" and len(board["games"]) == len(SLATE)
    # The model still projects: the page looks healthy while prices are gone.
    assert all("projGoals" in g["home"] for g in board["games"])
    assert [g.get("priced") for g in board["games"]] == [False, False], (
        "a game with no price reached the page without saying so; the page "
        "can only read its null pick as a pass"
    )
    assert all(g["pick"] is None and "moneyline" not in g for g in board["games"])


def test_the_notice_says_why_no_game_has_a_line(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    notice = board["notice"] or ""
    assert "price" in notice.lower() and "not priced" in notice.lower(), (
        f"no game on this board carries a price and the notice said {notice!r}"
    )


@pytest.mark.parametrize(
    "allowlisted",
    [["moneyline", "puck_line", "total_goals"], []],
    ids=["markets-allowlisted", "nothing-allowlisted"],
)
def test_the_page_does_not_call_an_unpriced_game_a_pass(
    tmp_path: Path, monkeypatch, allowlisted: list[str]
) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    board, _ = build(lab, tmp_path / "out", monkeypatch, allowlisted=allowlisted)

    rendered = render_board(board, tmp_path)

    for game in page_games(rendered):
        label = game["pick"]["label"]
        assert "edge bar" not in label and "allowlisted" not in label, (
            f"an unpriced game read {label!r}: a gate nobody reached"
        )
        assert label.startswith("Not priced"), label
    for row in rendered["graphic"]["rows"]:
        assert "clears the bar" not in row["pickSub"], row
        assert row["pickLabel"] == "Not priced", row


def test_an_exhibition_on_the_graphic_does_not_say_nothing_cleared_the_bar(
    tmp_path: Path, monkeypatch
) -> None:
    """The Graphic page's sub-line was one constant for every game without a
    pick. In preseason the model abstains; nothing was measured against a bar."""
    board = {"generatedAt": "2026-09-25T15:00:00Z", "season": "2026–27", "phase": "preseason",
             "boardDate": "2026-09-25", "notice": "Exhibition slate.", "record": {}, "teams": {},
             "allowlistedMarkets": ["moneyline"],
             "games": [{"id": "1", "startUtc": "2026-09-25T23:00:00Z", "away": {"abbr": "MTL"},
                        "home": {"abbr": "TOR"}, "pick": None, "priced": False}]}

    row = render_board(board, tmp_path)["graphic"]["rows"][0]

    assert row["pickLabel"] == "Exhibition"
    assert row["pickSub"] == "model abstains", row


def test_staged_prices_still_publish_the_pick_and_the_lines(tmp_path: Path, monkeypatch) -> None:
    """The companion that keeps the unpriced tests from passing vacuously."""
    lab = make_lab(tmp_path, monkeypatch, staged=True)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert tor["priced"] is True
    assert tor["pick"] == {"kind": "bet", "market": "Moneyline", "label": "TOR +112", "price": 112, "edgePct": 11.0}
    assert tor["moneyline"]["current"] == {"home": 112.0, "away": -130.0}
    assert board["notice"] is None
    rendered = render_board(board, tmp_path)
    shown = next(g for g in page_games(rendered) if g["sides"][1]["abbr"] == "TOR")
    assert shown["pick"]["heading"] == "Best bet" and shown["pick"]["label"] == "TOR +112"
    nyi = next(g for g in page_games(rendered) if g["sides"][1]["abbr"] == "NYI")
    assert nyi["pick"]["label"] == "No market clears the edge bar", (
        "a priced game with no selection is exactly what the edge bar stopped"
    )


def test_a_partly_priced_board_labels_each_game_on_its_own(tmp_path: Path, monkeypatch) -> None:
    """Prices for one game and not the other: the priced game keeps its
    pick, the other says it was not priced, and the board-wide notice —
    which says NO game has a line — stays off."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    rows = [r for r in _price_rows() if r["home_team"] == CLUBS["TOR"][2]]
    _write_csv(lab / "data" / "staging" / "odds_api_prices_staging.csv", rows)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    priced = {g["home"]["abbr"]: g["priced"] for g in board["games"]}
    assert priced == {"TOR": True, "NYI": False}, priced
    assert board["notice"] is None, board["notice"]
    shown = {g["sides"][1]["abbr"]: g["pick"] for g in page_games(render_board(board, tmp_path))}
    assert shown["TOR"]["label"] == "TOR +112"
    assert shown["NYI"]["label"].startswith("Not priced"), shown["NYI"]


def test_an_open_that_was_never_captured_is_not_the_current_price(
    tmp_path: Path, monkeypatch
) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True, opens=False)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert tor["moneyline"]["open"] is None, (
        f"no capture was on disk and the open read {tor['moneyline']['open']}, "
        "which is the current price under another name"
    )
    assert tor["total"]["open"] is None, tor["total"]


def test_a_captured_open_is_published_as_the_open(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=True, opens=True)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    tor = next(g for g in board["games"] if g["home"]["abbr"] == "TOR")
    assert tor["moneyline"]["open"] == {"home": 132.0, "away": -150.0}
    assert tor["moneyline"]["current"] == {"home": 112.0, "away": -130.0}
    # This asserted 6.0. A captured total row cannot say whether it is the
    # featured line or a rung of `alternate_totals`, and the capture asks for
    # the ladder alone, so no open total is read from a capture.
    assert tor["total"]["open"] is None, tor["total"]
    assert tor["total"]["current"] == 6.0, tor["total"]


def test_a_board_without_the_model_does_not_promise_market_lines(
    tmp_path: Path, monkeypatch
) -> None:
    """The lines are attached inside the model's branch, so a board built
    without it has none — even with prices staged."""
    lab = make_lab(tmp_path, monkeypatch, staged=True, model=False)

    board, _ = build(lab, tmp_path / "out", monkeypatch)

    assert all("moneyline" not in g and g["priced"] is False for g in board["games"])
    assert "market lines" not in (board["notice"] or ""), board["notice"]
    for game in page_games(render_board(board, tmp_path)):
        assert game["pick"]["label"].startswith("Not priced"), game["pick"]


def test_the_morning_after_an_unpriced_board_the_results_page_renders(
    tmp_path: Path, monkeypatch
) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)

    _, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    assert len(results["games"]) == len(SLATE)
    assert all("total" not in g for g in results["games"])
    page = render_results(results, tmp_path)
    assert page["count"] == len(SLATE)
    for game in page["games"]:
        titles = [cell["title"] for cell in game["cells"]]
        assert titles == ["Straight up", "Total"], titles
        line = game["cells"][1]["rows"][0]
        assert line["value"] == "—", line


def test_the_next_morning_still_settles_the_projection(tmp_path: Path, monkeypatch) -> None:
    """Straight-up needs only the projection, which an unpriced board still has."""
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    out = tmp_path / "out"
    build(lab, out, monkeypatch)

    _, results = build(lab, out, monkeypatch, day=BOARD_DAY + timedelta(days=1), finals=True)

    straight = results["summary"]["straightUp"]
    assert straight["w"] + straight["l"] == len(SLATE), straight
