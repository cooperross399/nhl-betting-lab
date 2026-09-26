"""The public board applied the back-to-back adjustment whatever the team_b2b verdict said.

`scripts/run_gameday_card.py` hands the schedule history to the team pricer
only while `verdicts.ships("team_b2b", output_dir=outputs)` is true, and its
comment says why: a policy the verdict file has withdrawn "must actually be
withdrawn, not merely reported as off while the factors keep applying".
`web/build_site_json.py` never read the verdict. `load_model` built its `b2b`
flag from the schedule unconditionally, and `build_board` passed it into
`expected_goals`, `moneyline_probabilities`, `regulation_3_way_probabilities`,
`puck_line_probabilities` and `total_probabilities`. It then published the
results as `projGoals`, `winProb`, the fair moneyline, the puck line's
`coverProb`, the total's `overProb` and the regulation split. It also froze
them into `history/<day>.json`, the day's first opinion, which is never
rewritten and from whose `projGoals` the next morning grades straight up.

Found by the failure-shape audit (3 of 3 refuters: reproduce, reachability,
intent). Latent today: `data/outputs/rest_experiment.json` ships `team_b2b`,
and while it does the board and the card agree. Experiment Refresh re-runs
the rest experiment every week and opens a drift PR when the verdict moves.
Once such a PR withdrew it, the card would price every side as rested while
the board kept publishing the adjusted figures beside the card's pick.
Measured on the real processed history with the verdict withdrawn:

* 2025-03-02: the card priced Pittsburgh (at home the night after playing)
  at 0.4370 to win; the board published 0.4141, fair +142, projected goals
  3.04-3.61 against 3.12-3.53 rested, and a puck-line cover of 0.3538
  against 0.3319.
* The 2025-26 regular season, refitted each league day on the games before
  it as the board fits: 358 of 1,312 games had a side on a back-to-back. For
  those games the flag moved the published winProb by a median of 3.6
  points (max 4.6), and it flipped the projected winner, which the
  straight-up tally grades, in 39 of them. (The audit's single fit on the
  whole history said 3.9 points and 44.)

These tests drive the real `main()` of `web/build_site_json.py`, loaded by
path as Publish Site runs it, with only the NHL schedule stubbed. The team
map is built by the real `build_team_name_map` from boxscores in `tmp_path`,
and every directory a verdict could be read from is under `tmp_path`: the
lab's own `data/outputs` and the recorded directory `verdicts.OUTPUTS_DIR`.
They hold:

* withdrawn, every model figure the board publishes is the model's rested
  figure; shipped, it is the adjusted one. The fixture's tired nights are
  measurably worse than its rested ones, and every test first proves that
  the two sets of figures differ, so neither direction can pass on a
  constant;
* the verdict is read the way the card reads it: from the lab's own
  `data/outputs` when that records one, with the recorded directory holding
  the opposite verdict each time, and otherwise from the recorded one;
* under each verdict, the board's probabilities are the card pricer's
  (`price_team_markets`, gated by the card's own expression);
* the `b2b` chip stays the schedule fact under both verdicts: a side that
  played yesterday did, whether or not its price moves for it;
* the build log says which state the board priced under.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from nhl_betting_lab import verdicts
from nhl_betting_lab.data.build_datasets import TEAM_GAME_COLUMNS, load_team_games
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import team_names
from nhl_betting_lab.reports.card_pricing import price_team_markets, selection_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "web" / "build_site_json.py"
REST_FILE = verdicts.VERDICT_FILES["team_b2b"]

#: abbrev -> (placeName, commonName) as the NHL API spells them, and the
#: provider's full name.
CLUBS = {
    "TOR": ("Toronto", "Maple Leafs", "Toronto Maple Leafs"),
    "BOS": ("Boston", "Bruins", "Boston Bruins"),
    "MTL": ("Montréal", "Canadiens", "Montreal Canadiens"),
    "NYI": ("New York", "Islanders", "New York Islanders"),
}

#: Forty-five blocks of four days. Night one, Toronto hosts Boston, both
#: rested. Night two, each of them plays again against a rested side:
#: Toronto hosts Montreal, Boston visits the Islanders. Then two nights off.
FIRST_DAY = date(2025, 10, 8)
BLOCKS = 45
LAST_BLOCK_NIGHT = FIRST_DAY + timedelta(days=4 * (BLOCKS - 1) + 1)
#: Toronto hosts Boston the night before the board, rested.
YESTERDAY = LAST_BLOCK_NIGHT + timedelta(days=2)
BOARD_DAY = YESTERDAY + timedelta(days=1)

#: (away, home, NHL game id). Toronto is at home the night after playing and
#: Boston on the road the night after playing; Montreal and the Islanders
#: last played three days earlier.
SLATE = (("MTL", "TOR", "2025021001"), ("BOS", "NYI", "2025021002"))
TIRED = frozenset({"TOR", "BOS"})
TOTAL_LINE = 6.0

SHIPPED = ["team_b2b"]
WITHDRAWN: list[str] = []


# -- the lab a Publish Site runner holds -----------------------------------


def _team_games(path: Path) -> None:
    """Nothing constant: counts vary by block, and a side on the second
    night scores less and concedes more than it does rested."""
    rows: list[list] = []

    def add(day: date, home: str, away: str, hg: int, ag: int, regulation: bool) -> None:
        rows.append([2025020000 + len(rows), 20252026, 2, day.isoformat(),
                     f"{day.isoformat()}T23:30:00Z", home, away, hg, ag, 30, 28,
                     regulation])

    for block in range(BLOCKS):
        first = FIRST_DAY + timedelta(days=4 * block)
        second = first + timedelta(days=1)
        add(first, "TOR", "BOS", 3 + block % 3, 2 + block % 3, block % 5 != 0)
        add(second, "TOR", "MTL", 1 + block % 3, 3 + block % 2, block % 4 != 0)
        add(second, "NYI", "BOS", 3 + block % 3, 1 + block % 2, block % 3 != 0)
    add(YESTERDAY, "TOR", "BOS", 3, 2, True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(TEAM_GAME_COLUMNS)
        writer.writerows(rows)


def _boxscore(path: Path, home: str, away: str) -> None:
    def side(abbrev: str) -> dict:
        place, common, _ = CLUBS[abbrev]
        return {"abbrev": abbrev, "placeName": {"default": place},
                "commonName": {"default": common}}

    path.write_text(json.dumps({"homeTeam": side(home), "awayTeam": side(away)}),
                    encoding="utf-8")


def _staged_prices(path: Path) -> None:
    """Every team market the board shows, both puck-line favourites, so the
    card pricer holds a key for whichever side the board calls favourite."""
    rows = []
    for away, home, _ in SLATE:
        common = {
            "date": BOARD_DAY.isoformat(),
            "commence_time": f"{BOARD_DAY.isoformat()}T23:30:00Z",
            "provider_event_id": f"evt-{home}", "home_team": CLUBS[home][2],
            "away_team": CLUBS[away][2], "player": "", "book": "draftkings",
            "fetched_at": f"{BOARD_DAY.isoformat()}T14:00:00Z",
        }
        for market, selection, odds, line in (
            ("moneyline", "home", -120, ""), ("moneyline", "away", 100, ""),
            ("puck_line", "home", 190, -1.5), ("puck_line", "away", -230, 1.5),
            ("puck_line", "away", 210, -1.5), ("puck_line", "home", -250, 1.5),
            ("total_goals", "over", -110, TOTAL_LINE),
            ("total_goals", "under", -110, TOTAL_LINE),
            ("regulation_3_way", "home", 150, ""),
            ("regulation_3_way", "draw", 330, ""),
            ("regulation_3_way", "away", 190, ""),
        ):
            rows.append({**common, "market": market, "selection": selection,
                         "line": line, "american_odds": odds})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _record(directory: Path, ships: list[str] | None) -> None:
    """Write the rest experiment's verdict the way it does; None writes none."""
    directory.mkdir(parents=True, exist_ok=True)
    if ships is not None:
        (directory / REST_FILE).write_text(json.dumps({"ships": ships}), encoding="utf-8")


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Everything the builder reads, under tmp_path. The recorded verdict
    directory is pointed here too, so the tracked data/outputs can neither
    rescue a test nor make one pass by checkout."""
    raw = tmp_path / "raw"
    boxscores = raw / "nhl" / "boxscore"
    boxscores.mkdir(parents=True)
    for index, (away, home, _) in enumerate(SLATE):
        _boxscore(boxscores / f"{index}.json", home, away)
    monkeypatch.setattr(team_names, "RAW_DIR", raw)
    monkeypatch.setattr(team_names, "PROCESSED_DIR", tmp_path / "processed-unused")
    recorded = tmp_path / "recorded"
    recorded.mkdir()
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", recorded)

    lab = tmp_path / "lab"
    processed = lab / "data" / "processed"
    processed.mkdir(parents=True)
    _team_games(processed / "team_games.csv")
    _staged_prices(lab / "data" / "staging" / "odds_api_prices_staging.csv")
    (lab / "data" / "outputs").mkdir(parents=True)
    return {"lab": lab, "raw": raw, "recorded": recorded, "out": tmp_path / "out"}


def site_module() -> ModuleType:
    """`web/build_site_json.py`, loaded by path as the workflow runs it."""
    spec = importlib.util.spec_from_file_location("_site_build_rest_verdict", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schedule(day: date) -> list[dict]:
    if day != BOARD_DAY:
        return []
    games = []
    for away, home, game_id in SLATE:
        def side(abbrev: str) -> dict:
            place, common, _ = CLUBS[abbrev]
            return {"abbrev": abbrev, "placeName": {"default": place},
                    "commonName": {"default": common}, "record": "20-15-5"}
        games.append({
            "id": int(game_id), "gameType": 2, "startTimeUTC": f"{day.isoformat()}T23:30:00Z",
            "venue": {"default": "Arena"}, "venueLocation": {"default": "City"},
            "tvBroadcasts": [], "awayTeam": side(away), "homeTeam": side(home),
        })
    return games


def build(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, *,
          lab_verdict: list[str] | None, recorded_verdict: list[str] | None
          ) -> tuple[dict, ModuleType]:
    _record(world["lab"] / "data" / "outputs", lab_verdict)
    _record(world["recorded"], recorded_verdict)
    module = site_module()
    monkeypatch.setattr(module, "schedule_for", schedule)
    monkeypatch.setattr(module, "allowlisted_markets", lambda _lab: ["moneyline"])
    code = module.main(["--lab", str(world["lab"]), "--out", str(world["out"]),
                        "--date", BOARD_DAY.isoformat()])
    assert code == 0
    board = json.loads((world["out"] / "board.json").read_text(encoding="utf-8"))
    assert board["phase"] == "regular" and len(board["games"]) == len(SLATE)
    assert all(g["priced"] for g in board["games"]), (
        "the fixture's prices did not reach the board, so its lines are untested"
    )
    return board, module


# -- the two oracles ---------------------------------------------------------


def model_figures(world: dict[str, Path], module: ModuleType, *, rest: bool) -> dict:
    """What the real TeamModel says for each game, with the schedule's rest
    flags applied (`rest=True`) or every side priced as rested. The flags
    come from the fixture's own schedule, not from the builder."""
    model = TeamModel().fit(load_team_games(world["lab"] / "data" / "processed"))
    figures: dict[str, dict] = {}
    for away, home, _ in SLATE:
        flags = {"home_b2b": rest and home in TIRED, "away_b2b": rest and away in TIRED}
        eh, ea = model.expected_goals(home, away, **flags)
        ml = model.moneyline_probabilities(home, away, **flags)
        reg = model.regulation_3_way_probabilities(home, away, **flags)
        fav_home = ml["home"] >= ml["away"]
        pl = model.puck_line_probabilities(home, away, line=1.5, **flags)
        tot = model.total_probabilities(home, away, line=TOTAL_LINE, **flags)
        figures[home] = {
            "projGoals": (round(eh, 2), round(ea, 2)),
            "winProb": (round(ml["home"], 4), round(ml["away"], 4)),
            "fair": {"home": module.to_american(ml["home"]),
                     "away": module.to_american(ml["away"])},
            "puckLine": (home if fav_home else away,
                         round(pl["home_minus" if fav_home else "away_minus"], 4)),
            "overProb": round(tot["over"], 4),
            "regulation": tuple(round(reg[s], 4) for s in ("home", "draw", "away")),
        }
    return figures


def published(board: dict) -> dict:
    """The same figures, as the board published them."""
    figures: dict[str, dict] = {}
    for g in board["games"]:
        figures[g["home"]["abbr"]] = {
            "projGoals": (g["home"]["projGoals"], g["away"]["projGoals"]),
            "winProb": (g["home"]["winProb"], g["away"]["winProb"]),
            "fair": g["moneyline"]["fair"],
            "puckLine": (g["puckLine"]["favorite"], g["puckLine"]["coverProb"]),
            "overProb": g["total"]["overProb"],
            "regulation": tuple(g["regulation"][s] for s in ("home", "draw", "away")),
        }
    return figures


def card_probabilities(world: dict[str, Path]) -> dict[tuple, float]:
    """The card's team pricer over the staged file, gated by the card's own
    expression, keyed (home abbrev, market, selection, line)."""
    lab = world["lab"]
    outputs = lab / "data" / "outputs"
    games = load_team_games(lab / "data" / "processed")
    prices = pd.read_csv(lab / "data" / "staging" / "odds_api_prices_staging.csv")
    probabilities, unresolved = price_team_markets(
        prices,
        TeamModel().fit(games),
        team_names=team_names.build_team_name_map(world["raw"]),
        # scripts/run_gameday_card.py, verbatim.
        history=(games if verdicts.ships("team_b2b", output_dir=outputs) else None),
    )
    assert unresolved == []
    by_name = {full: abbrev for abbrev, (_, _, full) in CLUBS.items()}
    keyed: dict[tuple, float] = {}
    for row in prices.itertuples():
        line = None if pd.isna(row.line) else float(row.line)
        selection = str(row.selection).strip().lower()
        key = selection_key(row, market=row.market, selection=selection, line=line)
        if key in probabilities:
            keyed[(by_name[row.home_team], row.market, selection, line)] = probabilities[key]
    return keyed


def assert_the_fixture_can_tell(world: dict[str, Path], module: ModuleType) -> None:
    """Every figure differs between the adjusted and the rested model, in
    every game, or a test could pass on a constant."""
    adjusted = model_figures(world, module, rest=True)
    rested = model_figures(world, module, rest=False)
    for home in adjusted:
        for figure in adjusted[home]:
            assert adjusted[home][figure] != rested[home][figure], (
                f"{figure} in the game at {home} is {rested[home][figure]} with "
                "or without rest, so this fixture cannot tell an applied "
                "adjustment from an ignored one"
            )


# -- the tests ---------------------------------------------------------------


@pytest.mark.parametrize("recorded_verdict", [SHIPPED, None], ids=["recorded-ships", "none-recorded"])
def test_a_withdrawn_verdict_is_withdrawn_from_every_figure_the_board_publishes(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, recorded_verdict: list[str] | None
) -> None:
    board, module = build(world, monkeypatch, lab_verdict=WITHDRAWN,
                          recorded_verdict=recorded_verdict)
    assert_the_fixture_can_tell(world, module)

    assert published(board) == model_figures(world, module, rest=False), (
        "the lab's verdict withdrew team_b2b and the board still published "
        "rest-adjusted figures"
    )
    frozen = json.loads((world["out"] / "history" / f"{BOARD_DAY.isoformat()}.json")
                        .read_text(encoding="utf-8"))
    assert published(frozen) == published(board), (
        "the frozen first opinion, which the morning grades, differs from the board"
    )


@pytest.mark.parametrize("recorded_verdict", [WITHDRAWN, None], ids=["recorded-withdrawn", "none-recorded"])
def test_a_shipped_verdict_still_adjusts_the_board(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, recorded_verdict: list[str] | None
) -> None:
    board, module = build(world, monkeypatch, lab_verdict=SHIPPED,
                          recorded_verdict=recorded_verdict)
    assert_the_fixture_can_tell(world, module)

    assert published(board) == model_figures(world, module, rest=True), (
        "the lab's verdict ships team_b2b and the board priced every side as rested"
    )


@pytest.mark.parametrize(
    ("recorded_verdict", "rest"),
    [(SHIPPED, True), (WITHDRAWN, False), (None, False)],
    ids=["recorded-ships", "recorded-withdrawn", "no-verdict-anywhere"],
)
def test_a_lab_that_records_no_verdict_reads_the_recorded_one(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    recorded_verdict: list[str] | None, rest: bool,
) -> None:
    """The card's door (`verdicts.source`): the lab's own file when it has
    one, else the recorded one; a verdict recorded nowhere ships nothing."""
    board, module = build(world, monkeypatch, lab_verdict=None,
                          recorded_verdict=recorded_verdict)
    assert_the_fixture_can_tell(world, module)

    assert published(board) == model_figures(world, module, rest=rest)


@pytest.mark.parametrize(
    ("lab_verdict", "recorded_verdict"),
    [(WITHDRAWN, SHIPPED), (SHIPPED, WITHDRAWN), (None, SHIPPED), (None, None)],
    ids=["lab-withdrawn", "lab-ships", "recorded-ships", "no-verdict-anywhere"],
)
def test_the_board_prices_each_game_as_the_card_would(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    lab_verdict: list[str] | None, recorded_verdict: list[str] | None,
) -> None:
    board, module = build(world, monkeypatch, lab_verdict=lab_verdict,
                          recorded_verdict=recorded_verdict)
    assert_the_fixture_can_tell(world, module)
    card = card_probabilities(world)

    for g in board["games"]:
        home = g["home"]["abbr"]
        fav_side = "home" if g["puckLine"]["favorite"] == home else "away"
        board_says = {
            "moneyline home": g["home"]["winProb"],
            "moneyline away": g["away"]["winProb"],
            "puck line favourite -1.5": g["puckLine"]["coverProb"],
            "over": g["total"]["overProb"],
            "regulation home": g["regulation"]["home"],
            "regulation draw": g["regulation"]["draw"],
            "regulation away": g["regulation"]["away"],
        }
        card_says = {
            "moneyline home": card[(home, "moneyline", "home", None)],
            "moneyline away": card[(home, "moneyline", "away", None)],
            "puck line favourite -1.5": card[(home, "puck_line", fav_side, -1.5)],
            "over": card[(home, "total_goals", "over", TOTAL_LINE)],
            "regulation home": card[(home, "regulation_3_way", "home", None)],
            "regulation draw": card[(home, "regulation_3_way", "draw", None)],
            "regulation away": card[(home, "regulation_3_way", "away", None)],
        }
        for figure, value in board_says.items():
            assert value == round(card_says[figure], 4), (
                f"{figure} at {home}: the board published {value} and the card "
                f"prices {card_says[figure]:.4f} under the same verdict"
            )


@pytest.mark.parametrize(
    ("lab_verdict", "recorded_verdict"),
    [(WITHDRAWN, SHIPPED), (SHIPPED, WITHDRAWN)],
    ids=["withdrawn", "ships"],
)
def test_the_b2b_chip_is_the_schedule_fact_under_either_verdict(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    lab_verdict: list[str], recorded_verdict: list[str],
) -> None:
    """A side that played yesterday did. The verdict decides whether its
    price moves, not whether the page may say so."""
    board, _ = build(world, monkeypatch, lab_verdict=lab_verdict,
                     recorded_verdict=recorded_verdict)

    chips = {g[side]["abbr"]: g[side]["b2b"] for g in board["games"] for side in ("home", "away")}
    assert chips == {"TOR": True, "MTL": False, "NYI": False, "BOS": True}, chips


@pytest.mark.parametrize(
    ("lab_verdict", "recorded_verdict", "state"),
    [(WITHDRAWN, SHIPPED, "off"), (SHIPPED, WITHDRAWN, "in force"),
     (None, SHIPPED, "in force"), (None, None, "off")],
    ids=["lab-withdrawn", "lab-ships", "recorded-ships", "no-verdict-anywhere"],
)
def test_the_build_log_names_the_state_the_board_priced_under(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    lab_verdict: list[str] | None, recorded_verdict: list[str] | None, state: str,
) -> None:
    build(world, monkeypatch, lab_verdict=lab_verdict, recorded_verdict=recorded_verdict)

    log = capsys.readouterr().out
    lines = [line for line in log.splitlines() if "team_b2b" in line]
    assert len(lines) == 1, f"the build log does not say how rest was priced:\n{log}"
    assert f"team_b2b={state}" in lines[0], lines[0]
