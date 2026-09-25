"""A reproduced card read the tables as they stand now, not as they stood then.

`scripts/run_gameday_card.py --now <instant>` is the card's documented way to
reproduce a past card ("ISO instant to treat as now, for reproducing a past
card"). `--now` moved the clock and nothing else: the freshness gate, the
puck-drop guard and the snapshot's day. The processed tables were read whole,
so a reproduction over the real `team_games.csv` and player logs did two
things a run on that morning could not have done:

* it fitted both models on every game the tables hold, including the
  reproduced night's own results and every game after it;
* it passed the same whole table to both pricers as the back-to-back
  history. `rest.last_played_dates` keeps each team's LAST date in that
  table. On any past night that date is on or after the night, so
  `played_previous_day` never saw a gap of one day. Every tired side was
  priced as rested, while the run printed "props_b2b=in force,
  team_b2b=in force".

Found by the failure-shape audit (finding f3; confirmed by the reproduce and
reachability refuters; the intent refuter agreed the behaviour is real and
called it a listed follow-up). Measured on the real tables, which hold 3,936
games from 2023-10-10 to 2026-04-16:

* cut at each day, 1,187 of 7,872 team-sides are on the second night of a
  back-to-back. Read whole, the count is 0;
* on 2026-01-10 (10 games, the bought 23:00Z snapshot,
  `--now 2026-01-10T23:00:30+00:00`), the whole tables flagged no tired side.
  Cut at the day, they flag 3 (CHI, LAK, STL). With the model held fixed, the
  rest history alone moved 24 of 82 priced keys and each of those three
  moneylines by about 4 points, and it flipped 3 of the card's 4 best bets;
* the fit printed "3936 games" where the tables cut at the day hold 3,320
  games and 132,781 of 157,419 log rows. The reproduced card read 4 best
  bets / 1 unit. The tables cut at the day give 1 best bet / 0.25 units.

No workflow passes `--now`. The one scheduled card, in Gameday Refresh, runs
on the wall clock over tables that hold only completed games, so no CI card,
snapshot or ledger row was affected. What was wrong was every reproduction,
and every measurement made with one.

These tests run the real `main()` loaded by path, with every default
directory pointed into tmp_path. They hold:

* a reproduction freezes exactly what the real pricers give when both the
  model fits and the rest history are cut to games dated before the
  reproduced league day. This holds for a morning instant and for a
  late-evening one, whose UTC date is already the next day. The fixture can
  see each wrong reading: the whole tables, the whole history with cut fits,
  cut history with whole fits, and tables cut after the night rather than
  before it all move a moneyline and a shots price by more than 0.003;
* a reproduction over the whole tables is byte-identical, in its frozen
  snapshot and its card, to the same run over the tables cut by hand. That
  was the only faithful way to reproduce a card before this fix;
* the live card, with no `--now`, still reads every completed game. That
  includes a same-day matinee a delayed run fetched, which is what tells the
  next day's matinee that its teams are tired;
* a row whose date cannot be read is left out of a reproduction, not
  guessed in.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config, verdicts
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOGS_FILENAME,
    TEAM_GAMES_FILENAME,
)
from nhl_betting_lab.forward_evidence import snapshots_dir
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports.card_pricing import (
    price_props,
    price_team_markets,
    selection_key,
)
from nhl_betting_lab.reports.gameday_card import (
    CARD_JSON_FILENAME,
    CARD_MARKDOWN_FILENAME,
)
from nhl_betting_lab.verdicts import VERDICT_FILES


#: What the repository records today: by_toi off, both rest adjustments on.
SHIPPED = {"by_toi": False, "props_b2b": True, "team_b2b": True}

#: Thirty blocks of four days: a rested game, a back-to-back the next day,
#: then two days off. The last game before the slate is a back-to-back, and
#: the slate is the day after it, so on the slate's morning both sides are
#: on the second night of a back-to-back.
FIRST_DAY = date(2025, 10, 8)
BLOCKS = 30
LAST_GAME_DAY = FIRST_DAY + timedelta(days=4 * (BLOCKS - 1) + 1)
SLATE_DAY = LAST_GAME_DAY + timedelta(days=1)
#: Results the tables hold that no run on the slate's day could have seen:
#: the night's own game, then a fortnight of later ones. Boston runs away
#: with every one of them, so a model fitted on them visibly moves.
LATER_DAYS = tuple(SLATE_DAY + timedelta(days=n) for n in (0, 2, 3, 6, 9, 12))

LEAFS = "Toronto Maple Leafs"
BRUINS = "Boston Bruins"
STAR = "Alexis Lafrenière"
STAR_AS_PROVIDED = "Alexis Lafreniere"

#: Two reproduced instants on the slate's league day (February: UTC-5).
#: The late one is 21:00 in New York and already the next day in UTC.
INSTANTS = {
    "morning": {
        "now": f"{SLATE_DAY.isoformat()}T15:00:00+00:00",
        "commence": f"{SLATE_DAY.isoformat()}T23:30:00Z",
        "fetched_at": f"{SLATE_DAY.isoformat()}T14:00:00Z",
    },
    "late_evening": {
        "now": f"{(SLATE_DAY + timedelta(days=1)).isoformat()}T02:00:00+00:00",
        "commence": f"{(SLATE_DAY + timedelta(days=1)).isoformat()}T03:00:00Z",
        "fetched_at": f"{SLATE_DAY.isoformat()}T20:00:00Z",
    },
}


def _load_card() -> ModuleType:
    """Import the script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _game(
    game_id: int,
    day: date,
    home: str,
    away: str,
    *,
    goals: dict[str, int],
    shots: dict[str, tuple[int, int]],
    block: int,
) -> tuple[dict, list[dict]]:
    """One game and its four player-log rows (a forward and a defender a side)."""
    game = {
        "game_id": game_id,
        "date": day.isoformat(),
        "home_team": home,
        "away_team": away,
        "home_goals": goals[home],
        "away_goals": goals[away],
        "regulation": block % 5 != 0,
    }
    logs: list[dict] = []
    for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
        leafs = team == "TOR"
        forward_shots, defender_shots = shots[team]
        for player_id, name, position, toi, count in (
            (
                8480001 if leafs else 8480101,
                STAR if leafs else "Bruins Shooter",
                "C",
                1150 + 40 * (block % 3),
                forward_shots,
            ),
            (
                8480002 if leafs else 8480102,
                "Leafs Defender" if leafs else "Bruins Defender",
                "D",
                1250 + 30 * (block % 2),
                defender_shots,
            ),
        ):
            scored = 1 if goals[team] >= 3 and position == "C" else 0
            assists = (block + 1) % 2
            logs.append(
                {
                    "game_id": game_id,
                    "date": day.isoformat(),
                    "player_id": player_id,
                    "player": name,
                    "role": "skater",
                    "position": position,
                    "team": team,
                    "opponent": opponent,
                    "venue": venue,
                    "toi_seconds": toi,
                    "shots_on_goal": count,
                    "goals": scored,
                    "assists": assists,
                    "points": scored + assists,
                    "blocked_shots": 1 + block % 3,
                    "hits": block % 4,
                    "power_play_goals": 0,
                    "saves": 0,
                    "shots_against": 0,
                }
            )
    return game, logs


def _season_before_the_slate() -> tuple[list[dict], list[dict]]:
    """Every game up to the slate's eve. Nothing is constant, and a side on
    the second night of a back-to-back shoots and scores measurably less
    than a rested one, which is what gives the rest adjustment something to
    move."""
    games: list[dict] = []
    logs: list[dict] = []
    for block in range(BLOCKS):
        home, away = ("TOR", "BOS") if block % 2 == 0 else ("BOS", "TOR")
        for tired in (False, True):
            day = FIRST_DAY + timedelta(days=4 * block + (1 if tired else 0))
            goals = (
                {home: 1 + block % 2, away: 1 + (block + 1) % 2}
                if tired
                else {home: 4 + block % 3, away: 2 + block % 2}
            )
            shots = {
                "TOR": ((1 + block % 3, block % 2) if tired
                        else (5 + block % 4, 1 + block % 3)),
                "BOS": ((1 + block % 3, block % 2) if tired
                        else (5 + block % 4, 1 + block % 3)),
            }
            game, rows = _game(
                2025020000 + 2 * block + (1 if tired else 0), day, home, away,
                goals=goals, shots=shots, block=block,
            )
            games.append(game)
            logs.extend(rows)
    return games, logs


def _later_game(n: int) -> tuple[dict, list[dict]]:
    """The n-th result dated on or after the slate day. Boston wins big and
    Toronto's star stops shooting, the opposite of the season before."""
    home, away = ("TOR", "BOS") if n % 2 == 0 else ("BOS", "TOR")
    return _game(
        2025021000 + n, LATER_DAYS[n], home, away,
        goals={"TOR": n % 2, "BOS": 6 + n % 3},
        shots={"TOR": (n % 2, 0), "BOS": (9 + n % 3, 3)},
        block=n,
    )


def _tables(later: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player logs, team games): the season before the slate plus the first
    `later` results dated on or after it."""
    games, logs = _season_before_the_slate()
    for n in range(later):
        game, rows = _later_game(n)
        games.append(game)
        logs.extend(rows)
    return pd.DataFrame(logs), pd.DataFrame(games)


def _staged_prices(commence: str, fetched_at: str) -> pd.DataFrame:
    common = {
        "date": commence[:10],
        "commence_time": commence,
        "provider_event_id": "evt-tor-bos",
        "home_team": LEAFS,
        "away_team": BRUINS,
        "book": "DraftKings",
        "fetched_at": fetched_at,
    }
    rows = [
        {**common, "market": "shots_on_goal", "player": STAR_AS_PROVIDED,
         "selection": "over", "line": 3.5, "american_odds": 115},
        {**common, "market": "shots_on_goal", "player": STAR_AS_PROVIDED,
         "selection": "under", "line": 3.5, "american_odds": -140},
        {**common, "market": "moneyline", "player": "",
         "selection": "home", "line": "", "american_odds": -125},
        {**common, "market": "moneyline", "player": "",
         "selection": "away", "line": "", "american_odds": 105},
    ]
    return pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS))


def _boxscore(raw: Path) -> None:
    """Toronto hosting Boston as the NHL API spells both, so the card builds a
    map with real cache-derived spellings rather than only its aliases."""
    payload = boxscore_payload(game_id=2025020001, game_state="OFF")
    payload["homeTeam"].update(
        abbrev="TOR", placeName={"default": "Toronto"},
        commonName={"default": "Maple Leafs"},
    )
    payload["awayTeam"].update(
        abbrev="BOS", placeName={"default": "Boston"},
        commonName={"default": "Bruins"},
    )
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2025020001.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every default directory the card could fall back to into
    tmp_path, so the real data tree can neither rescue a test nor fail one."""
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", tmp_path / "recorded")
    _boxscore(raw)
    return tmp_path


def _run(
    card: ModuleType,
    root: Path,
    name: str,
    *,
    logs: pd.DataFrame,
    games: pd.DataFrame,
    prices: pd.DataFrame,
    now: str | None,
) -> dict[str, Path]:
    """Run the real `main()` over its own processed, staging and output dirs."""
    dirs = {
        "raw": root / "raw",
        "processed": root / name / "processed",
        "staging": root / name / "staging",
        "outputs": root / name / "outputs",
    }
    for key in ("processed", "staging", "outputs"):
        dirs[key].mkdir(parents=True)
    logs.to_csv(dirs["processed"] / PLAYER_LOGS_FILENAME, index=False)
    games.to_csv(dirs["processed"] / TEAM_GAMES_FILENAME, index=False)
    prices.to_csv(dirs["staging"] / odds_api.STAGING_PRICES_FILENAME, index=False)
    for policy, filename in VERDICT_FILES.items():
        (dirs["outputs"] / filename).write_text(
            json.dumps({"ships": [policy] if SHIPPED[policy] else []}),
            encoding="utf-8",
        )
    argv = [
        "--staging-dir", str(dirs["staging"]),
        "--processed-dir", str(dirs["processed"]),
        "--raw-dir", str(dirs["raw"]),
        "--output-dir", str(dirs["outputs"]),
        "--archive-dir", str(dirs["outputs"] / "archive"),
    ]
    if now is not None:
        argv += ["--now", now]
    assert card.main(argv) == 0
    return dirs


def _snapshot(dirs: dict[str, Path]) -> Path:
    path = snapshots_dir(dirs["outputs"] / "archive") / f"{SLATE_DAY.isoformat()}.csv"
    assert path.is_file(), "the card froze no snapshot, so it priced nothing"
    return path


def _frozen(dirs: dict[str, Path]) -> dict[tuple[str, str], float]:
    frame = pd.read_csv(_snapshot(dirs), float_precision="round_trip")
    return {
        (row.market, row.selection): float(row.model_probability)
        for row in frame.itertuples()
    }


def _before(frame: pd.DataFrame, day: date, *, inclusive: bool = False) -> pd.DataFrame:
    """The test's own cut, on the fixture's clean ISO dates."""
    dates = frame["date"].astype(str)
    keep = dates <= day.isoformat() if inclusive else dates < day.isoformat()
    return frame[keep].reset_index(drop=True)


def _priced(
    root: Path,
    prices: pd.DataFrame,
    *,
    logs_fit: pd.DataFrame,
    games_fit: pd.DataFrame,
    history: pd.DataFrame | None,
) -> dict[tuple[str, str], float]:
    """What the real pricers give, keyed (market, selection), with the fits
    and the rest history named separately so each can be varied alone."""
    team_names = tn.build_team_name_map(root / "raw")
    props, _ = price_props(
        prices,
        PlayerPropsModel().fit(logs_fit),
        corrections=None,
        team_names=team_names,
        history=history,
        rosters=nhl_api.current_rosters(raw_dir=root / "raw"),
    )
    team, _ = price_team_markets(
        prices, TeamModel().fit(games_fit), team_names=team_names,
        history=history,
    )
    priced = {**props, **team}
    result: dict[tuple[str, str], float] = {}
    for row in prices.itertuples():
        line = None if pd.isna(row.line) else float(row.line)
        key = selection_key(row, market=row.market, selection=str(row.selection), line=line)
        assert key in priced, f"the reference priced nothing for {key}"
        result[(row.market, str(row.selection))] = priced[key]
    return result


def _moves_both_markets(
    wrong: dict[tuple[str, str], float], right: dict[tuple[str, str], float]
) -> dict[str, float]:
    """The largest move per market between two readings."""
    moved: dict[str, float] = {}
    for key, probability in right.items():
        moved[key[0]] = max(moved.get(key[0], 0.0), abs(wrong[key] - probability))
    return moved


@pytest.mark.parametrize("instant", sorted(INSTANTS))
def test_a_reproduction_freezes_the_prices_of_the_history_before_its_night(
    isolated: Path, instant: str, capsys: pytest.CaptureFixture[str]
) -> None:
    moment = INSTANTS[instant]
    logs, games = _tables(later=len(LATER_DAYS))
    prices = _staged_prices(moment["commence"], moment["fetched_at"])
    dirs = _run(
        _load_card(), isolated, "full",
        logs=logs, games=games, prices=prices, now=moment["now"],
    )
    out = capsys.readouterr().out
    frozen = _frozen(dirs)

    # The references read the files the card read, through the same CSV
    # round-trip, and cut them in the test's own words.
    staged = pd.read_csv(dirs["staging"] / odds_api.STAGING_PRICES_FILENAME)
    whole_logs = pd.read_csv(dirs["processed"] / PLAYER_LOGS_FILENAME)
    whole_games = pd.read_csv(dirs["processed"] / TEAM_GAMES_FILENAME)
    cut_logs = _before(whole_logs, SLATE_DAY)
    cut_games = _before(whole_games, SLATE_DAY)
    assert len(cut_games) == 2 * BLOCKS and len(whole_games) == 2 * BLOCKS + len(LATER_DAYS)

    expected = _priced(
        isolated, staged, logs_fit=cut_logs, games_fit=cut_games, history=cut_games
    )
    assert set(frozen) == set(expected)
    for key, probability in expected.items():
        assert frozen[key] == pytest.approx(probability, abs=1e-12), (
            f"{instant}: {key} was frozen at {frozen[key]!r}; the pricers on the "
            f"history dated before {SLATE_DAY} give {probability!r}"
        )

    # The fixture can see every wrong reading of "the history before the
    # night": each moves a moneyline and a shots price by more than 0.003,
    # so a card that read any of them could not also match above.
    after_the_night_logs = _before(whole_logs, SLATE_DAY, inclusive=True)
    after_the_night_games = _before(whole_games, SLATE_DAY, inclusive=True)
    wrong_readings = {
        "the whole tables (the unfixed card)": dict(
            logs_fit=whole_logs, games_fit=whole_games, history=whole_games
        ),
        "the whole history as rest, fits cut": dict(
            logs_fit=cut_logs, games_fit=cut_games, history=whole_games
        ),
        "cut history, fits on the whole tables": dict(
            logs_fit=whole_logs, games_fit=whole_games, history=cut_games
        ),
        "tables cut after the night, not before it": dict(
            logs_fit=after_the_night_logs,
            games_fit=after_the_night_games,
            history=after_the_night_games,
        ),
    }
    for reading, inputs in wrong_readings.items():
        moved = _moves_both_markets(_priced(isolated, staged, **inputs), expected)
        assert set(moved) == {"moneyline", "shots_on_goal"}
        assert min(moved.values()) > 0.003, (
            f"{reading} moved {moved}: this fixture cannot tell it from the "
            "history before the night"
        )

    # How the unfixed card lost the adjustment: the whole table as history
    # prices exactly as no history at all, because every team's last game in
    # it is on or after the night.
    rest_off = _priced(
        isolated, staged, logs_fit=cut_logs, games_fit=cut_games, history=None
    )
    whole_as_rest = _priced(
        isolated, staged, logs_fit=cut_logs, games_fit=cut_games, history=whole_games
    )
    for key, probability in rest_off.items():
        assert whole_as_rest[key] == pytest.approx(probability, abs=1e-12)

    # The run says what it fitted on and what it set aside.
    assert TeamModel().fit(cut_games).report.summary_line() in out
    assert TeamModel().fit(whole_games).report.summary_line() not in out
    assert PlayerPropsModel().fit(cut_logs).report.summary_line() in out
    assert PlayerPropsModel().fit(whole_logs).report.summary_line() not in out
    assert f"Reproducing {SLATE_DAY.isoformat()}" in out
    assert f"{len(cut_games)} of {len(whole_games)} team game(s)" in out
    assert f"{len(cut_logs)} of {len(whole_logs)} player-log row(s)" in out


@pytest.mark.parametrize("instant", sorted(INSTANTS))
def test_a_reproduction_over_the_whole_tables_is_the_card_the_morning_tables_give(
    isolated: Path, instant: str
) -> None:
    """Before the fix the only faithful reproduction was the one run over
    tables cut by hand. The card now does that cut itself, so the two runs
    freeze and render the same bytes."""
    moment = INSTANTS[instant]
    card = _load_card()
    logs, games = _tables(later=len(LATER_DAYS))
    prices = _staged_prices(moment["commence"], moment["fetched_at"])
    whole = _run(
        card, isolated, "whole", logs=logs, games=games, prices=prices,
        now=moment["now"],
    )
    by_hand = _run(
        card, isolated, "by_hand",
        logs=_before(logs, SLATE_DAY), games=_before(games, SLATE_DAY),
        prices=prices, now=moment["now"],
    )

    assert _snapshot(whole).read_bytes() == _snapshot(by_hand).read_bytes()
    for filename in (CARD_JSON_FILENAME, CARD_MARKDOWN_FILENAME):
        assert (whole["outputs"] / filename).read_bytes() == (
            by_hand["outputs"] / filename
        ).read_bytes(), f"{filename} differs from the run on the morning's tables"


class _DelayedRun(datetime):
    """The wall clock of a Gameday Refresh run that GitHub started late:
    16:00 in New York on the slate day, after that day's matinee is final."""

    INSTANT = datetime(
        SLATE_DAY.year, SLATE_DAY.month, SLATE_DAY.day, 21, 0, tzinfo=timezone.utc
    )

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return cls.INSTANT.astimezone(tz) if tz else cls.INSTANT.replace(tzinfo=None)


def test_the_live_card_still_reads_every_completed_game(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The cut belongs to a reproduction, not to the live card.

    A live run's tables hold only games completed before its own clock, so
    it has nothing to cut. A cut by league day would still take something
    from it. Here a delayed run holds the slate day's completed matinee
    and prices the next day's matinee between the same teams. The first
    matinee is what makes the second one a back-to-back, and a cut at the
    run's league day would throw exactly that game away."""
    card = _load_card()
    monkeypatch.setattr(card, "datetime", _DelayedRun)
    logs, games = _tables(later=1)  # the season, plus the slate day's matinee
    tomorrow = SLATE_DAY + timedelta(days=1)
    prices = _staged_prices(
        f"{tomorrow.isoformat()}T17:00:00Z", f"{SLATE_DAY.isoformat()}T20:30:00Z"
    )
    dirs = _run(card, isolated, "live", logs=logs, games=games, prices=prices, now=None)
    out = capsys.readouterr().out
    frozen = _frozen(dirs)

    staged = pd.read_csv(dirs["staging"] / odds_api.STAGING_PRICES_FILENAME)
    whole_logs = pd.read_csv(dirs["processed"] / PLAYER_LOGS_FILENAME)
    whole_games = pd.read_csv(dirs["processed"] / TEAM_GAMES_FILENAME)
    expected = _priced(
        isolated, staged, logs_fit=whole_logs, games_fit=whole_games,
        history=whole_games,
    )
    assert set(frozen) == set(expected)
    for key, probability in expected.items():
        assert frozen[key] == pytest.approx(probability, abs=1e-12), (
            f"the live card froze {key} at {frozen[key]!r}; over every completed "
            f"game the pricers give {probability!r}"
        )

    # A cut at the run's own league day would be visible here.
    cut_games = _before(whole_games, SLATE_DAY)
    cut = _priced(
        isolated, staged, logs_fit=_before(whole_logs, SLATE_DAY),
        games_fit=cut_games, history=cut_games,
    )
    moved = _moves_both_markets(cut, expected)
    assert min(moved.values()) > 0.005, moved
    assert "Reproducing" not in out
    assert TeamModel().fit(whole_games).report.summary_line() in out


def test_a_row_the_cut_cannot_date_is_left_out_of_a_reproduction() -> None:
    """A row with no readable league date cannot be shown to precede the
    reproduced day, so it is set aside rather than guessed in, as the
    walk-forward samplers drop it too."""
    card = _load_card()
    frame = pd.DataFrame(
        {
            "date": [
                LAST_GAME_DAY.isoformat(),
                SLATE_DAY.isoformat(),
                (SLATE_DAY + timedelta(days=1)).isoformat(),
                "",
                None,
                float("nan"),
                "02/02/2026",
                f"{LAST_GAME_DAY.isoformat()}T23:00:00Z",
            ],
            "row": range(8),
        }
    )
    kept = card._dated_before(frame, SLATE_DAY)
    assert list(kept["row"]) == [0, 7]
    assert list(kept.index) == [0, 1]
