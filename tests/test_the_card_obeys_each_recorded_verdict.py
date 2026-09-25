"""The card's recorded-verdict gates were guarded by greps that could not fail.

`scripts/run_gameday_card.py` applies three modelling policies only while the
verdict its experiment recorded says the policy ships: the by-TOI correction
(`correction_experiment.json`), the props back-to-back adjustment
(`props_rest_experiment.json`) and the team back-to-back adjustment
(`rest_experiment.json`). The only tests of those three gates read source
text — `'ships("by_toi"' in runner`, `'ships("props_b2b"' in runner`,
`"history=team_history" in text` — and every substring survives inside its
own inversion, `not ships("by_toi", ...)`. Every test that ran the card's
`main()` did so with no player logs on disk, so the lines behind
`if logs.empty:` never executed anywhere in the suite.

Found by the failure-shape audit (finding 67; 3 of 3 refuters confirmed).
Inverting the by_toi gate left the whole suite green (1768 passed at the time
of the audit), and so did inverting either rest gate. On a real slate —
2026-03-14, 11 games, 11,333 bought prop rows — the inverted card applied the
correction that lost the price backtest to every one of its 9,902 priced prop
rows (mean |dp| 0.017, max 0.222), moved the card from 26 best bets / 8.75u
to 18 / 6.75u, and still stamped "by_toi=off" on the frozen snapshot, the
record the forward ledger settles. The first opinion of a day stands, so
those rows could never have been repriced.

These tests run the real `main()` past `if logs.empty:` — player logs, team
games, a boxscore-derived team map and a correction curve on disk — once for
each of the eight combinations of the three verdicts, and hold every frozen
probability to what the real pricers produce under exactly that combination.
Each test also proves its own fixture can see the difference: for every
policy, the price with that one verdict flipped must differ from the price
the card froze. A constant fixture cannot tell an applied policy from an
ignored one, so the fixture's tired nights are measurably worse than its
rested ones and its correction curve is far from the identity.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOGS_FILENAME,
    TEAM_GAMES_FILENAME,
    load_player_logs,
    load_team_games,
)
from nhl_betting_lab.forward_evidence import snapshots_dir
from nhl_betting_lab.models.calibration import PlattCalibration
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.models.toi_corrections import (
    CurrentCorrections,
    load_current_corrections,
    save_current_corrections,
)
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports.card_pricing import (
    price_props,
    price_team_markets,
    selection_key,
)
from nhl_betting_lab import verdicts
from nhl_betting_lab.verdicts import VERDICT_FILES, describe


POLICIES = ("by_toi", "props_b2b", "team_b2b")

#: Which staged market each policy can move. The correction and the props
#: rest adjustment touch props only; the team rest adjustment, team markets.
MOVES = {
    "by_toi": "shots_on_goal",
    "props_b2b": "shots_on_goal",
    "team_b2b": "moneyline",
}

#: Thirty blocks of four days: a rested game, a back-to-back the next day,
#: then two days off. The last game is a back-to-back, and the slate is the
#: day after it, so both sides are on the second night of a back-to-back and
#: the rest adjustment has something to move.
FIRST_DAY = date(2025, 10, 8)
BLOCKS = 30
LAST_GAME_DAY = FIRST_DAY + timedelta(days=4 * (BLOCKS - 1) + 1)
SLATE_DAY = LAST_GAME_DAY + timedelta(days=1)

LEAFS = "Toronto Maple Leafs"
BRUINS = "Boston Bruins"
#: The registry spells him with the accent; the provider does not.
STAR = "Alexis Lafrenière"
STAR_AS_PROVIDED = "Alexis Lafreniere"


def _load_card() -> ModuleType:
    """Import the script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _history() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Player logs and team games for Toronto and Boston.

    Nothing here is constant: every count varies by block, and a side on the
    second night of a back-to-back shoots and scores measurably less than a
    rested one — which is what makes the rest adjustment move a price.
    """
    logs: list[dict] = []
    games: list[dict] = []
    for block in range(BLOCKS):
        home, away = ("TOR", "BOS") if block % 2 == 0 else ("BOS", "TOR")
        for tired in (False, True):
            day = FIRST_DAY + timedelta(days=4 * block + (1 if tired else 0))
            game_id = 2025020000 + 2 * block + (1 if tired else 0)
            games.append(
                {
                    "game_id": game_id,
                    "date": day.isoformat(),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": (1 + block % 2) if tired else (4 + block % 3),
                    "away_goals": (1 + (block + 1) % 2) if tired else (2 + block % 2),
                    "regulation": block % 5 != 0,
                }
            )
            for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
                leafs = team == "TOR"
                for player_id, name, position, toi, shots in (
                    (
                        8480001 if leafs else 8480101,
                        STAR if leafs else "Bruins Shooter",
                        "C",
                        1150 + 40 * (block % 3),
                        (1 + block % 3) if tired else (5 + block % 4),
                    ),
                    (
                        8480002 if leafs else 8480102,
                        "Leafs Defender" if leafs else "Bruins Defender",
                        "D",
                        1250 + 30 * (block % 2),
                        (block % 2) if tired else (1 + block % 3),
                    ),
                ):
                    goals = 0 if tired else block % 2
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
                            "shots_on_goal": shots,
                            "goals": goals,
                            "assists": assists,
                            "points": goals + assists,
                            "blocked_shots": 1 + block % 3,
                            "hits": block % 4,
                            "power_play_goals": 0,
                            "saves": 0,
                            "shots_against": 0,
                        }
                    )
    return pd.DataFrame(logs), pd.DataFrame(games)


def _staged_prices() -> pd.DataFrame:
    commence = f"{SLATE_DAY.isoformat()}T23:30:00Z"
    common = {
        "date": SLATE_DAY.isoformat(),
        "commence_time": commence,
        "provider_event_id": "evt-tor-bos",
        "home_team": LEAFS,
        "away_team": BRUINS,
        "book": "DraftKings",
        "fetched_at": f"{SLATE_DAY.isoformat()}T14:00:00Z",
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
    """Toronto hosting Boston as the NHL API spells both, so the map the card
    builds holds real cache-derived spellings rather than only its aliases."""
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
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Everything the card reads, under tmp_path. Every default directory it
    could fall back to is pointed here too, so the real data tree can neither
    rescue a test nor make one pass by checkout."""
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    staging = tmp_path / "staging"
    outputs = tmp_path / "outputs"
    for directory in (raw, processed, staging, outputs):
        directory.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", processed)
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    # A directory that records no verdict now reads the repository's recorded
    # one (finding 59), so the recorded directory is pointed at an empty one
    # too: "no verdict on file" must mean none anywhere, not data/outputs'.
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", tmp_path / "recorded")

    _boxscore(raw)
    logs, games = _history()
    logs.to_csv(processed / PLAYER_LOGS_FILENAME, index=False)
    games.to_csv(processed / TEAM_GAMES_FILENAME, index=False)
    # Far from the identity, so an applied curve cannot hide inside float
    # noise: it takes a stated 50% down to about 27%.
    save_current_corrections(
        CurrentCorrections(
            fitted_at="2026-01-01T00:00:00Z",
            pooled={
                "shots_on_goal": PlattCalibration(
                    intercept=-1.0, slope=1.0, fitted_on=5000
                )
            },
        ),
        processed_dir=processed,
    )
    _staged_prices().to_csv(
        staging / odds_api.STAGING_PRICES_FILENAME, index=False
    )
    return {"raw": raw, "processed": processed, "staging": staging, "outputs": outputs}


def _record(outputs: Path, shipped: dict[str, bool]) -> None:
    """Write each experiment's verdict file the way the experiment does."""
    for policy, filename in VERDICT_FILES.items():
        (outputs / filename).write_text(
            json.dumps({"ships": [policy] if shipped[policy] else []}),
            encoding="utf-8",
        )


def _run_card(world: dict[str, Path]) -> None:
    code = _load_card().main(
        [
            "--staging-dir", str(world["staging"]),
            "--processed-dir", str(world["processed"]),
            "--output-dir", str(world["outputs"]),
            "--archive-dir", str(world["outputs"] / "archive"),
            "--now", f"{SLATE_DAY.isoformat()}T15:00:00+00:00",
        ]
    )
    assert code == 0


def _frozen(world: dict[str, Path]) -> pd.DataFrame:
    path = snapshots_dir(world["outputs"] / "archive") / f"{SLATE_DAY.isoformat()}.csv"
    assert path.is_file(), "the card froze no snapshot, so it priced nothing"
    return pd.read_csv(path, float_precision="round_trip")


def _expected(world: dict[str, Path], shipped: dict[str, bool]) -> dict[tuple, float]:
    """What the real pricers give under `shipped`, keyed (market, selection).

    Built from the same files the card reads, through the same loaders, and
    with nothing the card is being tested for taken from the card.
    """
    # The staged file read back as the card reads it, so a CSV round-trip
    # (an empty line becomes NaN, a blank player NaN) is on both sides.
    prices = pd.read_csv(world["staging"] / odds_api.STAGING_PRICES_FILENAME)
    logs = load_player_logs(world["processed"])
    games = load_team_games(world["processed"])
    team_names = tn.build_team_name_map(world["raw"])
    props, _ = price_props(
        prices,
        PlayerPropsModel().fit(logs),
        corrections=(
            load_current_corrections(processed_dir=world["processed"])
            if shipped["by_toi"]
            else None
        ),
        team_names=team_names,
        history=games if shipped["props_b2b"] else None,
        rosters=nhl_api.current_rosters(raw_dir=world["raw"]),
    )
    team, _ = price_team_markets(
        prices,
        TeamModel().fit(games),
        team_names=team_names,
        history=games if shipped["team_b2b"] else None,
    )
    priced = {**props, **team}
    expected: dict[tuple, float] = {}
    for row in prices.itertuples():
        selection = str(row.selection)
        line = None if pd.isna(row.line) else float(row.line)
        key = selection_key(row, market=row.market, selection=selection, line=line)
        assert key in priced, f"the reference priced nothing for {key}"
        expected[(row.market, selection)] = priced[key]
    return expected


STATES = [
    dict(zip(POLICIES, flags))
    for flags in itertools.product((False, True), repeat=len(POLICIES))
]


@pytest.mark.parametrize(
    "shipped",
    STATES,
    ids=[
        "-".join(f"{p}={'on' if s[p] else 'off'}" for p in POLICIES)
        for s in STATES
    ],
)
def test_the_card_freezes_the_prices_its_recorded_verdicts_ship(
    world: dict[str, Path],
    shipped: dict[str, bool],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _record(world["outputs"], shipped)

    _run_card(world)
    out = capsys.readouterr().out
    frozen = _frozen(world)
    actual = {
        (row.market, row.selection): float(row.model_probability)
        for row in frozen.itertuples()
    }
    expected = _expected(world, shipped)

    assert set(actual) == set(expected), (
        f"the card froze {sorted(actual)}, expected {sorted(expected)}"
    )
    for key, probability in expected.items():
        assert actual[key] == pytest.approx(probability, abs=1e-12), (
            f"{key} was frozen at {actual[key]!r}; under {shipped} the pricers "
            f"give {probability!r}"
        )

    # The fixture can see every gate: flipping any one verdict moves a price
    # the card froze, so a gate the card read backwards could not also match.
    for policy in POLICIES:
        flipped = _expected(world, {**shipped, policy: not shipped[policy]})
        moved = {
            key: abs(flipped[key] - actual[key])
            for key in actual
            if key[0] == MOVES[policy]
        }
        assert max(moved.values()) > 0.005, (
            f"flipping {policy} moved no frozen price ({moved}): this fixture "
            "cannot tell the policy applied from the policy ignored"
        )

    # The log and the snapshot's stamp say what was applied.
    if shipped["by_toi"]:
        assert "Corrections in force: by-TOI correction fitted 2026-01-01" in out
        assert "No correction is in force" not in out
    else:
        assert "No correction is in force" in out
        assert "Corrections in force" not in out
    assert set(frozen["verdicts_in_force"]) == {describe(output_dir=world["outputs"])}
    for policy in POLICIES:
        state = "in force" if shipped[policy] else "off"
        assert f"{policy}={state}" in frozen["verdicts_in_force"].iloc[0]


def test_with_no_verdict_on_file_the_card_prices_the_raw_rested_model(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing verdict file ships nothing (`verdicts.ships`). The card must
    read that as no policy at all — not as a reason to apply one."""
    _run_card(world)
    out = capsys.readouterr().out
    frozen = _frozen(world)
    expected = _expected(world, dict.fromkeys(POLICIES, False))

    assert "No correction is in force" in out
    for row in frozen.itertuples():
        assert float(row.model_probability) == pytest.approx(
            expected[(row.market, row.selection)], abs=1e-12
        )
