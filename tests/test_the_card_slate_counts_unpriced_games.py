"""The card's eligibility slate came from the prices it judged.

`run_gameday_card.py` built the slate with `slate_games_from(prices)`: the
distinct games of the very frame `assess_markets` then judged. A game the
provider priced in NO market was therefore absent from the slate, and could
never make any market INCOMPLETE — so `require_full_slate`, which exists to
stop an allowlisted card picking only where prices happen to exist, could not
see the one shape of partial coverage that hides every trace of itself.

Found by the failure-shape audit (2 of 3 refuters confirmed; the third agreed
the mechanism is real). Reproduced on the real 2026-27 schedule: 8
regular-season games on 2026-10-01, the provider's prices for 5 of them
staged, moneyline allowlisted. The gate printed "1 of 12 markets eligible
across 5 game(s): moneyline" and "priced for all 5 game(s) in the slate";
the card published picks across the 5 and never mentioned the 3. Judged
against the 8, the same prices read "Priced for 5 of 8 games".

What these tests hold, driving the real `main()` over the real 2026-10-01
slate — the provider's own event shape through `normalize_event`, a complete
club-schedule cache, a team-name map built from boxscores, and a policy
allowlisting moneyline; only the fitted models are stubbed, so what is under
test is the gate:

* a scheduled game priced in no market makes every market incomplete, the
  card makes no pick, and the run names the game;
* the whole slate priced is eligible and picks — the control, which also
  pins that only the prices' own league dates are filled in, on the league
  date and not the UTC one, through the team-name map;
* a game already under way, or called off, is not part of the slate;
* an exhibition game the screen removes never enters it;
* a partial cache still counts every game it does know, and says what it
  cannot;
* with no schedule at all the run says the gate saw only the provider's
  games.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.staging_provider_policy import load_policy
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


SEASON = "20262027"
DAY = "2026-10-01"

#: The real 2026-10-01 slate, as the cached club schedules carry it:
#: (HOME, AWAY, startTimeUTC). The four western games face off after
#: midnight UTC, so their UTC date is the 2nd while the league's is the 1st.
SLATE = (
    ("CBJ", "BUF", "2026-10-01T23:00:00Z"),
    ("NJD", "PHI", "2026-10-01T23:00:00Z"),
    ("NYR", "TBL", "2026-10-01T23:00:00Z"),
    ("NSH", "MIN", "2026-10-02T00:00:00Z"),
    ("CGY", "SEA", "2026-10-02T01:00:00Z"),
    ("UTA", "CHI", "2026-10-02T01:30:00Z"),
    ("SJS", "FLA", "2026-10-02T02:00:00Z"),
    ("VAN", "EDM", "2026-10-02T02:00:00Z"),
)

#: The other sixteen clubs play the next day, so the cache is complete and
#: holds a date the prices do not cover.
NEXT_DAY = (
    ("CAR", "WSH"), ("DAL", "STL"), ("DET", "NYI"), ("VGK", "ANA"),
    ("WPG", "BOS"), ("TOR", "MTL"), ("PIT", "OTT"), ("LAK", "COL"),
)

#: What the NHL API calls each club: (placeName, commonName). Composed, this
#: is exactly the string the provider sends.
NAMES = {
    "CBJ": ("Columbus", "Blue Jackets"), "BUF": ("Buffalo", "Sabres"),
    "NJD": ("New Jersey", "Devils"), "PHI": ("Philadelphia", "Flyers"),
    "NYR": ("New York", "Rangers"), "TBL": ("Tampa Bay", "Lightning"),
    "NSH": ("Nashville", "Predators"), "MIN": ("Minnesota", "Wild"),
    "CGY": ("Calgary", "Flames"), "SEA": ("Seattle", "Kraken"),
    "UTA": ("Utah", "Mammoth"), "CHI": ("Chicago", "Blackhawks"),
    "SJS": ("San Jose", "Sharks"), "FLA": ("Florida", "Panthers"),
    "VAN": ("Vancouver", "Canucks"), "EDM": ("Edmonton", "Oilers"),
    "TOR": ("Toronto", "Maple Leafs"), "MTL": ("Montréal", "Canadiens"),
}

#: The three late western games the audit left unposted.
UNPOSTED = ("UTA", "SJS", "VAN")

MORNING = "2026-10-01T13:30:00+00:00"


def _provider_name(abbrev: str) -> str:
    place, common = NAMES[abbrev]
    return f"{place.replace('é', 'e')} {common}"


def _game(day: str, home: str, away: str, start: str, *, game_type: int = 2,
          state: str | None = "OK") -> dict:
    game = {
        "gameType": game_type, "gameDate": day, "startTimeUTC": start,
        "homeTeam": {"abbrev": home}, "awayTeam": {"abbrev": away},
    }
    if state is not None:
        game["gameScheduleState"] = state
    return game


def _schedule(raw: Path, *, states: dict[str, str] | None = None,
              exhibitions: tuple[dict, ...] = (),
              missing_files: tuple[str, ...] = ()) -> None:
    """Every club's own `{ABBR}_{season}.json`, as `fetch_nhl_data` writes
    them: each file holds every game its club plays."""
    states = states or {}
    games = [
        _game(DAY, home, away, start, state=states.get(home, "OK"))
        for home, away, start in SLATE
    ] + [
        _game("2026-10-02", home, away, "2026-10-02T23:00:00Z")
        for home, away in NEXT_DAY
    ] + list(exhibitions)
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    clubs = {g["homeTeam"]["abbrev"] for g in games} | {
        g["awayTeam"]["abbrev"] for g in games
    }
    for club in sorted(clubs - set(missing_files)):
        own = [
            g for g in games
            if club in (g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"])
        ]
        (directory / f"{club}_{SEASON}.json").write_text(
            json.dumps({"games": own}), encoding="utf-8"
        )


def _boxscores(raw: Path) -> None:
    """One finished game per pairing, so the team-name map is built from the
    cache the way production builds it."""
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    pairs = [(home, away) for home, away, _ in SLATE] + [("TOR", "MTL")]
    for game_id, (home, away) in enumerate(pairs, start=1):
        payload = boxscore_payload(game_id=game_id, game_state="OFF")
        for side, club in (("homeTeam", home), ("awayTeam", away)):
            place, common = NAMES[club]
            payload[side].update(
                abbrev=club, placeName={"default": place},
                commonName={"default": common},
            )
        (directory / f"{game_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )


def _event(home: str, away: str, start: str) -> dict:
    """One event in the shape the provider's bulk odds endpoint returns."""
    home_name, away_name = _provider_name(home), _provider_name(away)
    return {
        "id": f"evt-{home}-{away}",
        "commence_time": start,
        "home_team": home_name,
        "away_team": away_name,
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": home_name, "price": 120},
                            {"name": away_name, "price": -140},
                        ],
                    }
                ],
            }
        ],
    }


def _stage(staging: Path, events: list[dict], *,
           fetched_at: str = "2026-10-01T13:25:00Z") -> None:
    rows = [
        row
        for event in events
        for row in odds_api.normalize_event(event, fetched_at=fetched_at)
    ]
    odds_api.write_staging(
        rows, filename=odds_api.STAGING_PRICES_FILENAME, staging_dir=staging
    )


def _policy(root: Path):
    """Moneyline allowlisted, standing in for a signed receipt: the shipped
    policy changes the day an approval lands or is withdrawn, and the gate's
    rule must hold on both sides of that day."""
    path = root / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["the_odds_api"],
                "allowed_provider_types": ["odds_api"],
                "provider_allowlist_entries": {
                    "the_odds_api": {
                        "allowlist_status": "allowed",
                        "provider_type": "odds_api",
                        "approved_at": "2026-09-24T09:00:00-04:00",
                        "reviewer_name": "cooperross399",
                        "evidence_receipt_id": "receipt-1",
                        "required_markets": ["moneyline"],
                    }
                },
                "max_provider_run_age_hours": 12,
            }
        ),
        encoding="utf-8",
    )
    return load_policy(repository_root=root)


def _load_card() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Fitted:
    """A fitted model, so neither side of the card blocks on missing data."""

    report = SimpleNamespace(summary_line=lambda: "stub model")
    ambiguous_names = ()

    def fit(self, _frame):
        return self


def _home_opinions(prices: pd.DataFrame) -> dict:
    """The home side at 62% everywhere: a best bet on every priced game at
    +120, so whether moneyline reaches the card shows in the picks."""
    return {
        selection_key(row, market=row.market, selection=row.selection, line=None):
            0.62 if row.selection == "home" else 0.38
        for row in prices.itertuples()
        if row.market == "moneyline"
    }


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    # Every default first, so the tracked verdicts are not read through the
    # scratch --output-dir (#151); the lines below override what this needs.
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    raw = tmp_path / "raw"
    _boxscores(raw)
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    staging = tmp_path / "staging"
    staging.mkdir()
    return SimpleNamespace(tmp=tmp_path, raw=raw, staging=staging)


def _run(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
         capsys: pytest.CaptureFixture[str], *, now: str = MORNING):
    module = _load_card()
    policy = _policy(world.tmp / "policy_root")
    monkeypatch.setattr(module, "load_policy", lambda: policy)
    monkeypatch.setattr(module, "load_player_logs",
                        lambda _dir: pd.DataFrame({"player": ["x"]}))
    monkeypatch.setattr(module, "load_team_games",
                        lambda _dir: pd.DataFrame({"game_id": [1]}))
    monkeypatch.setattr(module, "PlayerPropsModel", _Fitted)
    monkeypatch.setattr(module, "TeamModel", _Fitted)
    monkeypatch.setattr(module, "current_rosters", lambda **_: {})
    monkeypatch.setattr(module, "price_props", lambda prices, model, **k: ({}, []))
    monkeypatch.setattr(
        module, "price_team_markets",
        lambda prices, model, **k: (_home_opinions(prices), []),
    )
    outputs = world.tmp / "outputs"
    module.main(
        ["--staging-dir", str(world.staging),
         "--processed-dir", str(world.tmp / "processed"),
         "--output-dir", str(outputs),
         "--now", now]
    )
    out = capsys.readouterr().out
    card = json.loads((outputs / "gameday_card.json").read_text(encoding="utf-8"))
    return card, out


def _picked_games(card: dict) -> set[str]:
    return {
        row["home_team"]
        for row in card["best_bets"] + card["leans"]
        if row["market"] == "moneyline"
    }


# --------------------------------------------------------------------------
# The defect, through the card.
# --------------------------------------------------------------------------

def test_a_game_priced_in_no_market_makes_the_market_incomplete(
    world, monkeypatch, capsys
) -> None:
    _schedule(world.raw)
    _stage(world.staging, [
        _event(home, away, start) for home, away, start in SLATE
        if home not in UNPOSTED
    ])

    card, out = _run(world, monkeypatch, capsys)

    assert card["slate_games"] == 8, out
    assert "moneyline" not in card["included_markets"]
    assert "Priced for 5 of 8 games" in card["excluded_markets"]["moneyline"]
    assert _picked_games(card) == set(), "picks made where prices happened to exist"
    assert card["blockers"] == [
        item for item in card["blockers"] if "No market is eligible" in item
    ], "blocked by something other than the gate; the test would prove nothing"
    assert "3 scheduled regular-season game(s)" in out
    for game in ("2026-10-01 CHI@UTA", "2026-10-01 FLA@SJS", "2026-10-01 EDM@VAN"):
        assert game in out


def test_the_whole_slate_priced_is_eligible_and_picks(
    world, monkeypatch, capsys
) -> None:
    """The control. Also pins that the slate fills in only the prices' own
    league date (not 2026-10-02, which the cache also holds), matches a
    western game whose UTC date is the 2nd, and matches through the
    team-name map rather than on the provider's spelling."""
    _schedule(world.raw)
    _stage(world.staging, [_event(h, a, s) for h, a, s in SLATE])

    card, out = _run(world, monkeypatch, capsys)

    assert "moneyline" in card["included_markets"], card["excluded_markets"]
    assert card["slate_games"] == 8
    assert _picked_games(card) == {_provider_name(h) for h, _, _ in SLATE}
    assert "scheduled regular-season game(s)" not in out


def test_a_game_already_under_way_is_not_part_of_the_slate(
    world, monkeypatch, capsys
) -> None:
    """An evening run: Utah's game faced off at 01:30Z and the provider no
    longer lists it. It cannot be played, so it cannot be missing."""
    _schedule(world.raw)
    # The evening run fetches its own prices minutes before it cards them,
    # as Gameday Refresh does; the morning's, 12h20m old by now, are stale
    # under the policy's 12-hour limit (finding 55) and would block the card.
    _stage(world.staging, [
        _event(h, a, s) for h, a, s in SLATE if h != "UTA"
    ], fetched_at="2026-10-02T01:40:00Z")

    card, out = _run(world, monkeypatch, capsys, now="2026-10-02T01:45:00+00:00")

    assert "moneyline" in card["included_markets"], card["excluded_markets"]
    assert card["slate_games"] == 7
    assert _picked_games(card) == {_provider_name("SJS"), _provider_name("VAN")}


def test_a_called_off_game_is_not_part_of_the_slate(
    world, monkeypatch, capsys
) -> None:
    """A postponed game stays in the cache under its original date. Counted,
    it would exclude every market for a game nobody will play."""
    _schedule(world.raw, states={"VAN": "PPD"})
    _stage(world.staging, [
        _event(h, a, s) for h, a, s in SLATE if h != "VAN"
    ])

    card, out = _run(world, monkeypatch, capsys)

    assert "moneyline" in card["included_markets"], card["excluded_markets"]
    assert card["slate_games"] == 7


def test_a_screened_exhibition_game_never_enters_the_slate(
    world, monkeypatch, capsys
) -> None:
    """The workflow's September dates carry exhibition prices. The screen
    removes them before pricing, and the slate must not count them after."""
    _schedule(world.raw, exhibitions=(
        _game(DAY, "TOR", "MTL", "2026-10-01T23:30:00Z", game_type=1),
    ))
    _stage(world.staging, [_event(h, a, s) for h, a, s in SLATE] + [
        _event("TOR", "MTL", "2026-10-01T23:30:00Z"),
    ])

    card, out = _run(world, monkeypatch, capsys)

    assert "the regular-season schedule does not know" in out
    assert "moneyline" in card["included_markets"], card["excluded_markets"]
    assert card["slate_games"] == 8


def test_a_partial_cache_still_counts_every_game_it_knows(
    world, monkeypatch, capsys
) -> None:
    """Utah's and Chicago's files did not land. The screen abstains, and the
    two western games the cache still knows are still missing — while the
    game neither file names cannot be counted, and the run says so."""
    _schedule(world.raw, missing_files=("UTA", "CHI"))
    _stage(world.staging, [
        _event(h, a, s) for h, a, s in SLATE if h not in UNPOSTED
    ])

    card, out = _run(world, monkeypatch, capsys)

    assert "only 30 of 32 clubs" in out
    assert "Priced for 5 of 7 games" in card["excluded_markets"]["moneyline"]
    assert _picked_games(card) == set()
    assert " ".join(out.split()).count(
        "Nor can the eligibility slate count a game no cached file names"
    ) == 1


def test_with_no_schedule_the_run_says_the_gate_saw_only_the_provider(
    world, monkeypatch, capsys
) -> None:
    _stage(world.staging, [
        _event(h, a, s) for h, a, s in SLATE if h not in UNPOSTED
    ])

    card, out = _run(world, monkeypatch, capsys)

    assert "no regular-season schedule is cached" in out
    assert (
        "the eligibility gate can judge each market only against the games "
        "the provider returned" in " ".join(out.split())
    )
    assert card["slate_games"] == 5


# --------------------------------------------------------------------------
# The two readers, directly.
# --------------------------------------------------------------------------

def test_the_schedule_keeps_every_game_it_does_not_positively_call_off(
    tmp_path: Path,
) -> None:
    from nhl_betting_lab.season import scheduled_regular_season_starts

    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True)
    on = _game(DAY, "CBJ", "BUF", "2026-10-01T23:00:00Z")
    unstated = _game(DAY, "NJD", "PHI", "2026-10-01T23:00:00Z", state=None)
    cancelled = _game(DAY, "NYR", "TBL", "2026-10-01T23:00:00Z", state="CNCL")
    postponed = _game(DAY, "NSH", "MIN", "2026-10-02T00:00:00Z", state="PPD")
    # Two copies of one game that disagree: Calgary's file (read first)
    # says it is on, Seattle's that it is off. Either says on, so it stays.
    split_on = _game(DAY, "CGY", "SEA", "2026-10-02T01:00:00Z")
    split_off = _game(DAY, "CGY", "SEA", "2026-10-02T01:00:00Z", state="CNCL")
    exhibition = _game(DAY, "TOR", "MTL", "2026-10-01T23:30:00Z", game_type=1)
    (directory / f"AAA_{SEASON}.json").write_text(json.dumps({"games": [
        on, unstated, cancelled, postponed, exhibition,
    ]}), encoding="utf-8")
    (directory / f"CGY_{SEASON}.json").write_text(
        json.dumps({"games": [split_on]}), encoding="utf-8"
    )
    (directory / f"SEA_{SEASON}.json").write_text(
        json.dumps({"games": [split_off]}), encoding="utf-8"
    )

    starts = scheduled_regular_season_starts(tmp_path)

    assert starts == {
        (DAY, "CBJ", "BUF"): "2026-10-01T23:00:00Z",
        (DAY, "NJD", "PHI"): "2026-10-01T23:00:00Z",
        (DAY, "CGY", "SEA"): "2026-10-02T01:00:00Z",
    }


def test_an_unreadable_face_off_stays_in_the_slate(tmp_path: Path) -> None:
    """An unreadable start is not a started game: excluded is the safe side."""
    from nhl_betting_lab.market_eligibility import slate_games_with_schedule

    prices = pd.DataFrame([{
        "date": "2026-10-01", "commence_time": "2026-10-01T23:00:00Z",
        "home_team": "Columbus Blue Jackets", "away_team": "Buffalo Sabres",
        "market": "moneyline",
    }])
    mapping = {"columbus blue jackets": "CBJ", "buffalo sabres": "BUF"}
    scheduled = {
        (DAY, "CBJ", "BUF"): "2026-10-01T23:00:00Z",
        (DAY, "NJD", "PHI"): "",
        (DAY, "NYR", "TBL"): "not a time",
        (DAY, "NSH", "MIN"): "2026-10-01T12:00:00Z",
    }

    slate, unpriced = slate_games_with_schedule(
        prices, scheduled,
        resolve=lambda name: tn.resolve_team(name, mapping),
        now=datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc),
    )

    assert unpriced == ("2026-10-01 PHI@NJD", "2026-10-01 TBL@NYR")
    assert len(slate) == 3
    with pytest.raises(ValueError):
        slate_games_with_schedule(
            prices, scheduled,
            resolve=lambda name: tn.resolve_team(name, mapping),
            now=datetime(2026, 10, 1, 13, 30),
        )
