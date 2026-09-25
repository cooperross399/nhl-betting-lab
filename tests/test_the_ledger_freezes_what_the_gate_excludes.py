"""The ledger freezes every priced row, including the markets the gate excludes.

`scripts/run_gameday_card.py` freezes the day's opinions with `write_snapshot`
on the unfiltered price frame and the full probability map, and only then
hands both to `build_card`, which applies the eligibility gate. That is what
lets the forward ledger accumulate for every market while the card shows few
of them, or none: the ledger is the out-of-sample test the pre-registered
2027-04-25 decision reads (`docs/when_this_ends.md`), and it settles only what
a snapshot holds.

The only test of that was
`test_the_snapshot_is_still_written_before_the_eligibility_gate` in
`tests/test_ladder_route_cannot_reach_the_ledger.py`, and it compares where
the strings `write_snapshot(` and `build_card(` sit in the script's text. A
filtered argument leaves both where they were. Found by the failure-shape
audit (finding 77; 3 of 3 refuters confirmed): mutant m17, which passes
`prices[prices["market"].isin(eligibility.eligible_markets)]` to
`write_snapshot`, left the whole suite green (1768 passed at the time of the
audit; 1860 of 1860 at the commit this was written on). So did
`filter_to_eligible(prices, eligibility)`, filtering the probability map
instead, and freezing nothing while no market is eligible. Every test that
ran the card's `main()` did so with nothing staged, so no test ever read a
frozen row.

What m17 costs, measured by the refuters on real data. On the real 2026-03-21
slate (12 games) under the committed policy, `goalie_saves` was quoted for 7
of 12 games and so INCOMPLETE: the committed card froze 6,754 rows and m17
6,670, losing all 84 goalie_saves opinions. Staged as of the 13:30 UTC card
time, 9 markets were INCOMPLETE and m17 kept 326 of 7,728 rows. Under the
allowlisting-nothing policy in force from the withdrawal (6d1dfd4,
2026-08-28) to the twelve-market approval (#101, 2026-09-23), the card was
dark and m17 froze 0 of 6,754. The card JSON was byte-identical to
the committed card's in every case, so nothing on the card shows the loss,
and a day's first snapshot is never replaced, so those opinions could not be
frozen later.

These tests run the real `main()` on a two-game slate over four clubs, with
player logs, team games, boxscore-derived team names and a provider policy
on disk under `tmp_path`, and read the frozen snapshot back. The slate puts
every way the card can exclude a priced market in front of the snapshot:

* `moneyline`: allowlisted and quoted for both games, so ELIGIBLE. It is the
  only market that reaches the card.
* `total_goals`: quoted for both games and left out of the policy's
  `required_markets`, so NOT_ALLOWLISTED.
* `shots_on_goal`: allowlisted and quoted for one game of two, so INCOMPLETE.
* `goalie_saves`: allowlisted and quoted for both games, so ELIGIBLE to the
  gate, and then kept off the card by `HARD_GATED_MARKETS` (no confirmed
  starter).
* Every market dark: the policy allowlists nothing, as the withdrawn policy
  did, or the policy file is missing and nothing is allowed.

DISABLED cannot arise from the card at this commit: it passes no `disabled=`
to `assess_markets` and assesses only `MARKETS_BY_KEY`. UNAVAILABLE has no row
to freeze.

Each test first proves its fixture can lose something: the real pricers give
an opinion on every staged row, including every excluded market's, and the
card really does exclude them. The snapshot must then hold every staged row,
at the probability the real pricers give it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from conftest import boxscore_payload
from test_scripts import load_script
from nhl_betting_lab import config
from nhl_betting_lab import staging_provider_policy
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOGS_FILENAME,
    TEAM_GAMES_FILENAME,
    load_player_logs,
    load_team_games,
)
from nhl_betting_lab.forward_evidence import snapshots_dir
from nhl_betting_lab.market_eligibility import (
    ELIGIBLE,
    INCOMPLETE,
    NOT_ALLOWLISTED,
    assess_markets,
    slate_games_from,
)
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports.card_pricing import (
    price_props,
    price_team_markets,
    selection_key,
)
from nhl_betting_lab.reports.gameday_card import CARD_JSON_FILENAME, HARD_GATED_MARKETS
from nhl_betting_lab.staging_provider_policy import POLICY_FILENAME, load_policy


#: Four clubs as the NHL API names them (place, common name) and as the
#: provider spells them in a price row.
CLUBS = {
    "TOR": ("Toronto", "Maple Leafs"),
    "BOS": ("Boston", "Bruins"),
    "NJD": ("New Jersey", "Devils"),
    "NYR": ("New York", "Rangers"),
}


def _provider_name(abbrev: str) -> str:
    place, common = CLUBS[abbrev]
    return f"{place} {common}"


#: Each club dresses a forward, a defender and a goalie every night.
ROSTER = {
    abbrev: (
        (8481000 + 10 * index, f"{CLUBS[abbrev][1]} Forward", "C"),
        (8481001 + 10 * index, f"{CLUBS[abbrev][1]} Defender", "D"),
        (8481002 + 10 * index, f"{CLUBS[abbrev][1]} Goalie", "G"),
    )
    for index, abbrev in enumerate(CLUBS)
}

#: A three-night rotation in which every club meets every other, with home
#: and away swapped every second rotation. Games are two days apart, so no
#: side is ever on a back-to-back.
ROTATION = (
    (("TOR", "BOS"), ("NJD", "NYR")),
    (("TOR", "NJD"), ("BOS", "NYR")),
    (("TOR", "NYR"), ("BOS", "NJD")),
)
FIRST_DAY = date(2025, 10, 8)
NIGHTS = 36
SLATE_DAY = FIRST_DAY + timedelta(days=2 * NIGHTS + 1)
NOW = f"{SLATE_DAY.isoformat()}T15:00:00+00:00"

#: Tonight's two games, home first.
GAME_A = ("TOR", "BOS")
GAME_B = ("NJD", "NYR")

#: The policy for the partly-dark night: moneyline, shots on goal and goalie
#: saves are approved; total goals is not.
APPROVED = ["moneyline", "shots_on_goal", "goalie_saves"]


def _history() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Player logs and team games. Nothing here is constant across nights."""
    logs: list[dict] = []
    games: list[dict] = []
    for night in range(NIGHTS):
        day = FIRST_DAY + timedelta(days=2 * night)
        flip = (night // len(ROTATION)) % 2 == 1
        for slot, (first, second) in enumerate(ROTATION[night % len(ROTATION)]):
            home, away = (second, first) if flip else (first, second)
            game_id = 2025020000 + 2 * night + slot
            goals = {
                home: 2 + (night + slot) % 4,
                away: 1 + (3 * night + slot) % 3,
            }
            games.append(
                {
                    "game_id": game_id,
                    "date": day.isoformat(),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": goals[home],
                    "away_goals": goals[away],
                    "regulation": (night + slot) % 5 != 0,
                }
            )
            shots = {
                home: 30 + (night + 2 * slot) % 7,
                away: 26 + (2 * night + slot) % 9,
            }
            for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
                for player_id, name, position in ROSTER[team]:
                    goalie = position == "G"
                    forward_shots = 1 + (night + player_id) % 5
                    defender_shots = (night + player_id) % 3
                    scored = 0 if goalie else (night + player_id) % 2
                    assists = 0 if goalie else (night + player_id + 1) % 2
                    logs.append(
                        {
                            "game_id": game_id,
                            "date": day.isoformat(),
                            "player_id": player_id,
                            "player": name,
                            "role": "goalie" if goalie else "skater",
                            "position": position,
                            "team": team,
                            "opponent": opponent,
                            "venue": venue,
                            "toi_seconds": 3600 if goalie else (
                                1100 + 40 * (night % 4) if position == "C"
                                else 1300 + 30 * (night % 3)
                            ),
                            "shots_on_goal": 0 if goalie else (
                                forward_shots if position == "C" else defender_shots
                            ),
                            "goals": scored,
                            "assists": assists,
                            "points": scored + assists,
                            "blocked_shots": 0 if goalie else 1 + night % 3,
                            "hits": 0 if goalie else (night + slot) % 4,
                            "power_play_goals": 0,
                            "saves": (
                                shots[opponent] - goals[opponent] if goalie else 0
                            ),
                            "shots_against": shots[opponent] if goalie else 0,
                        }
                    )
    return pd.DataFrame(logs), pd.DataFrame(games)


def _row(game: tuple[str, str], commence: str, **fields) -> dict:
    home, away = game
    return {
        "date": SLATE_DAY.isoformat(),
        "commence_time": f"{SLATE_DAY.isoformat()}T{commence}:00Z",
        "provider_event_id": f"evt-{away.lower()}-{home.lower()}",
        "home_team": _provider_name(home),
        "away_team": _provider_name(away),
        "book": "DraftKings",
        "fetched_at": f"{SLATE_DAY.isoformat()}T14:00:00Z",
        "player": "",
        "line": "",
        **fields,
    }


def _staged_team_rows() -> pd.DataFrame:
    rows = []
    for game, commence, home_price, away_price in (
        (GAME_A, "23:00", -135, 115),
        (GAME_B, "23:30", 110, -130),
    ):
        rows += [
            _row(game, commence, market="moneyline", selection="home",
                 american_odds=home_price),
            _row(game, commence, market="moneyline", selection="away",
                 american_odds=away_price),
            _row(game, commence, market="total_goals", selection="over",
                 line=6.5, american_odds=105),
            _row(game, commence, market="total_goals", selection="under",
                 line=6.5, american_odds=-125),
        ]
    return pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS))


def _staged_prop_rows() -> pd.DataFrame:
    leafs_forward = ROSTER["TOR"][0][1]
    rows = [
        # Shots on goal for one game of two: INCOMPLETE.
        _row(GAME_A, "23:00", market="shots_on_goal", player=leafs_forward,
             selection="over", line=2.5, american_odds=120),
        _row(GAME_A, "23:00", market="shots_on_goal", player=leafs_forward,
             selection="under", line=2.5, american_odds=-150),
    ]
    # Goalie saves for both games: eligible, then hard-gated off the card.
    for game, commence in ((GAME_A, "23:00"), (GAME_B, "23:30")):
        goalie = ROSTER[game[0]][2][1]
        rows += [
            _row(game, commence, market="goalie_saves", player=goalie,
                 selection="over", line=25.5, american_odds=-110),
            _row(game, commence, market="goalie_saves", player=goalie,
                 selection="under", line=25.5, american_odds=-110),
        ]
    return pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS))


def _boxscores(raw: Path) -> None:
    """One cached 2024-25 game per pairing on tonight's slate, spelled as the
    NHL API spells the clubs, so the card's team-name map is cache-derived."""
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    for game_id, (home, away) in ((2024020001, GAME_A), (2024020002, GAME_B)):
        payload = boxscore_payload(game_id=game_id, home=home, away=away)
        for side, abbrev in (("homeTeam", home), ("awayTeam", away)):
            place, common = CLUBS[abbrev]
            payload[side].update(
                placeName={"default": place}, commonName={"default": common}
            )
        (directory / f"{game_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _write_policy(root: Path, markets: list[str] | None) -> None:
    """The provider policy under `root`, in the shape the real one takes.

    `markets=None` writes the allowlisting-nothing policy the repository
    shipped with, and returned to when the 2026-08-27 approval was withdrawn.
    """
    path = root / "data" / "manual" / POLICY_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    if markets is None:
        payload: dict = {
            "allowed_provider_names": [],
            "allowed_provider_types": [],
            "provider_allowlist_entries": {},
            "max_provider_run_age_hours": 12,
        }
    else:
        payload = {
            "allowed_provider_names": [odds_api.PROVIDER_NAME],
            "allowed_provider_types": [odds_api.PROVIDER_TYPE],
            "provider_allowlist_entries": {
                odds_api.PROVIDER_NAME: {
                    "allowlist_status": "allowed",
                    "provider_type": odds_api.PROVIDER_TYPE,
                    "approved_at": "2026-09-24",
                    "reviewer_name": "fixture reviewer",
                    "evidence_receipt_id": "fixture-receipt",
                    "required_markets": markets,
                }
            },
            "max_provider_run_age_hours": 12,
        }
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Everything the card reads, under tmp_path. Every default directory it
    could fall back to is pointed here too — including the policy's
    repository root — so neither the real data tree nor the tracked policy
    can decide a result."""
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    staging = tmp_path / "staging"
    outputs = tmp_path / "outputs"
    policy_root = tmp_path / "repository"
    for directory in (raw, processed, staging, outputs, policy_root):
        directory.mkdir()
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", processed)
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    monkeypatch.setattr(staging_provider_policy, "PROJECT_ROOT", policy_root)

    _boxscores(raw)
    logs, games = _history()
    logs.to_csv(processed / PLAYER_LOGS_FILENAME, index=False)
    games.to_csv(processed / TEAM_GAMES_FILENAME, index=False)
    _staged_team_rows().to_csv(staging / odds_api.STAGING_PRICES_FILENAME, index=False)
    _staged_prop_rows().to_csv(staging / odds_api.STAGING_PROPS_FILENAME, index=False)
    return {
        "raw": raw,
        "processed": processed,
        "staging": staging,
        "outputs": outputs,
        "policy_root": policy_root,
    }


def _staged(world: dict[str, Path]) -> pd.DataFrame:
    """The staged files read back as the card reads them."""
    return pd.concat(
        [
            pd.read_csv(world["staging"] / odds_api.STAGING_PRICES_FILENAME),
            pd.read_csv(world["staging"] / odds_api.STAGING_PROPS_FILENAME),
        ],
        ignore_index=True,
    )


def _identity(row) -> tuple:
    """One staged or frozen row, independent of CSV blanks and NaN."""
    player = row.player
    line = row.line
    return (
        str(row.market),
        str(row.home_team),
        str(row.away_team),
        "" if player is None or pd.isna(player) else str(player),
        str(row.selection).strip().lower(),
        None if line is None or pd.isna(line) else float(line),
        float(row.american_odds),
    )


def _reference(world: dict[str, Path]) -> dict[tuple, float]:
    """What the real pricers say about every staged row, by identity.

    Built from the same files the card reads, through the same loaders, and
    with nothing taken from the card. Asserting that every staged row gets
    an opinion is what makes the snapshot checks below able to fail: an
    excluded market the models could not price would have nothing to lose.
    """
    prices = _staged(world)
    team_names = tn.build_team_name_map(world["raw"])
    logs = load_player_logs(world["processed"])
    games = load_team_games(world["processed"])
    props, unresolved_props = price_props(
        prices,
        PlayerPropsModel().fit(logs),
        team_names=team_names,
        rosters=nhl_api.current_rosters(raw_dir=world["raw"]),
    )
    team, unresolved_teams = price_team_markets(
        prices, TeamModel().fit(games), team_names=team_names
    )
    assert not unresolved_props and not unresolved_teams
    priced = {**props, **team}
    reference: dict[tuple, float] = {}
    for row in prices.itertuples():
        selection = str(row.selection).strip().lower()
        line = None if pd.isna(row.line) else float(row.line)
        key = selection_key(row, market=row.market, selection=selection, line=line)
        assert key in priced, f"the fixture's models priced nothing for {key}"
        reference[_identity(row)] = priced[key]
    assert len(reference) == len(prices)
    assert prices["market"].value_counts().to_dict() == {
        "moneyline": 4,
        "total_goals": 4,
        "goalie_saves": 4,
        "shots_on_goal": 2,
    }
    return reference


def _run_card(world: dict[str, Path]) -> dict:
    code = load_script("run_gameday_card.py").main(
        [
            "--staging-dir", str(world["staging"]),
            "--processed-dir", str(world["processed"]),
            "--output-dir", str(world["outputs"]),
            "--archive-dir", str(world["outputs"] / "archive"),
            "--now", NOW,
        ]
    )
    assert code == 0
    return json.loads(
        (world["outputs"] / CARD_JSON_FILENAME).read_text(encoding="utf-8")
    )


def _frozen(world: dict[str, Path]) -> pd.DataFrame:
    path = (
        snapshots_dir(world["outputs"] / "archive") / f"{SLATE_DAY.isoformat()}.csv"
    )
    assert path.is_file(), (
        "the card froze no snapshot for a slate whose every row the models "
        "price: the forward ledger lost the whole night"
    )
    return pd.read_csv(path, float_precision="round_trip")


def _assert_snapshot_holds_every_priced_row(
    frozen: pd.DataFrame, reference: dict[tuple, float]
) -> None:
    held = {_identity(row): float(row.model_probability) for row in frozen.itertuples()}

    def by_market(keys) -> list[str]:
        return sorted({key[0] for key in keys})

    missing = sorted(set(reference) - set(held))
    assert not missing, (
        f"the snapshot is missing {len(missing)} of {len(reference)} priced "
        f"row(s), in {by_market(missing)}. It froze only {by_market(held)}. "
        "The card's gates decide what it may recommend, never what the "
        "forward ledger records: an opinion left out of the day's first "
        "snapshot can never be frozen again."
    )
    assert len(frozen) == len(reference), (
        f"the snapshot holds {len(frozen)} rows for {len(reference)} priced"
    )
    for identity, probability in reference.items():
        assert held[identity] == pytest.approx(probability, abs=1e-12), (
            f"{identity} was frozen at {held[identity]!r}; the pricers give "
            f"{probability!r}"
        )


def test_the_snapshot_holds_every_market_the_card_excluded(
    world: dict[str, Path],
) -> None:
    """One market on the card, three kept off it, all four in the ledger."""
    _write_policy(world["policy_root"], APPROVED)
    reference = _reference(world)

    # The fixture's night is the one described above, judged by the real
    # gate: nothing here is taken from the card.
    states = {
        item.market: item.state
        for item in assess_markets(
            _staged(world),
            slate_games=slate_games_from(_staged(world)),
            policy=load_policy(),
            provider_name=odds_api.PROVIDER_NAME,
        ).markets
    }
    assert {market: states[market] for market in sorted({k[0] for k in reference})} == {
        "goalie_saves": ELIGIBLE,
        "moneyline": ELIGIBLE,
        "shots_on_goal": INCOMPLETE,
        "total_goals": NOT_ALLOWLISTED,
    }
    assert "goalie_saves" in HARD_GATED_MARKETS

    card = _run_card(world)

    # The card excluded all three, and put only the moneyline in front of
    # a reader.
    assert card["card_generated"] is True
    assert card["included_markets"] == ["moneyline"]
    excluded = card["excluded_markets"]
    assert excluded["shots_on_goal"].startswith("Priced for 1 of 2 games.")
    assert "Provider approval is not market approval" in excluded["total_goals"]
    assert excluded["goalie_saves"] == HARD_GATED_MARKETS["goalie_saves"]
    offered = {
        row["market"] for row in card["best_bets"] + card["leans"] + card["passes"]
    }
    assert offered <= {"moneyline"}

    _assert_snapshot_holds_every_priced_row(_frozen(world), reference)


@pytest.mark.parametrize(
    "policy_state", ["allowlists_nothing", "missing"]
)
def test_a_dark_card_still_freezes_every_priced_row(
    world: dict[str, Path], policy_state: str
) -> None:
    """The state this season's experiment was built for: no market approved,
    no card, and the ledger accumulating regardless.

    `allowlists_nothing` is the policy the repository shipped with and
    returned to at the withdrawal (6d1dfd4, 2026-08-28) until the
    twelve-market approval (#101, 2026-09-23). `missing` is the fail-closed
    state every unreadable policy resolves to.
    """
    if policy_state == "allowlists_nothing":
        _write_policy(world["policy_root"], None)
    reference = _reference(world)
    assert load_policy().allowed_markets(odds_api.PROVIDER_NAME) == ()

    card = _run_card(world)

    assert card["card_generated"] is False
    assert card["included_markets"] == []
    assert card["best_bets"] == card["leans"] == card["passes"] == []
    for market in sorted({key[0] for key in reference}):
        assert market in card["excluded_markets"]

    _assert_snapshot_holds_every_priced_row(_frozen(world), reference)
