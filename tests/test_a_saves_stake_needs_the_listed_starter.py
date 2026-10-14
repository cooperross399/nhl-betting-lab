"""A saves stake goes only on tonight's listed starter (2026-10-14).

The card staked Jake Oettinger over 24.5 saves (-110, Fliff, 0.25u) in
DAL @ COL. Daily Faceoff had listed Casey DeSmith as Dallas's confirmed
starter at 11:46 UTC, two hours before the card, and Oettinger did not play.
These tests replay that night: the page as Daily Faceoff served it (trimmed
to the fields read), the card that staked Oettinger, and the card with the
check, which keeps the opinion as a lean and stakes nothing.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

from nhl_betting_lab.data import starting_goalies as sg
from nhl_betting_lab.market_eligibility import ELIGIBLE, EligibilityReport, MarketEligibility
from nhl_betting_lab.reports import gameday_card as card_module
from nhl_betting_lab.reports.card_pricing import selection_key

ROOT = Path(__file__).resolve().parents[1]
CARD_AT = datetime(2026, 10, 14, 13, 40, tzinfo=timezone.utc)
FETCHED = "2026-10-14T13:35:00+00:00"


def _game(home, home_goalie, home_strength, away, away_goalie, away_strength):
    return {
        "homeTeamName": home,
        "homeGoalieName": home_goalie,
        "homeNewsStrengthName": home_strength,
        "homeNewsCreatedAt": "2026-10-14T11:43:26.903Z",
        "homeTeamMoneylinePointSpread": -135,
        "awayTeamName": away,
        "awayGoalieName": away_goalie,
        "awayNewsStrengthName": away_strength,
        "awayNewsCreatedAt": "2026-10-14T11:46:13.929Z",
        "date": "2026-10-14",
        "time": "20:30",
        "dateGmt": "2026-10-15T00:30:00.000Z",
    }


def _page(games) -> str:
    payload = {"props": {"pageProps": {"data": games, "date": "2026-10-14"}}}
    return (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    )


PAGE = _page([
    _game("Colorado Avalanche", "Scott Wedgewood", "Likely",
          "Dallas Stars", "Casey DeSmith", "Confirmed"),
    _game("Washington Capitals", "Charlie Lindgren", "Confirmed",
          "Montreal Canadiens", "Jakub Dobes", "Unconfirmed"),
])


def _starters():
    return sg.starters_from_rows(sg.parse_page(PAGE, retrieved_at=FETCHED), now=CARD_AT)


def _saves(player, home="Colorado Avalanche", away="Dallas Stars", line=24.5, price=-110):
    return {
        "date": "2026-10-14",
        "commence_time": "2026-10-15T00:40:00Z",
        "home_team": home,
        "away_team": away,
        "market": "goalie_saves",
        "player": player,
        "selection": "over",
        "line": line,
        "american_odds": price,
        "book": "Fliff",
    }


def _key(row):
    return selection_key(
        SimpleNamespace(**row), market=row["market"],
        selection=row["selection"], line=row["line"],
    )


def _eligibility():
    return EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=2,
        markets=[
            MarketEligibility(market=market, state=ELIGIBLE, reason="ok")
            for market in ("goalie_saves", "shots_on_goal")
        ],
    )


def _card(rows, probability, starters):
    return card_module.build_card(
        pd.DataFrame(rows),
        {_key(row): probability for row in rows},
        eligibility=_eligibility(),
        now=CARD_AT,
        goalie_starters=starters,
    )


def test_the_page_is_read_from_its_payload_and_keeps_no_price() -> None:
    rows = sg.parse_page(PAGE, retrieved_at=FETCHED)

    assert len(rows) == 4
    dallas = next(row for row in rows if row["team"] == "Dallas Stars")
    assert dallas["goalie"] == "Casey DeSmith"
    assert dallas["strength"] == "Confirmed"
    assert dallas["opponent"] == "Colorado Avalanche"
    assert set(dallas) == set(sg.COLUMNS)
    assert all("-135" not in str(value) for row in rows for value in row.values())


def test_a_page_without_its_payload_is_refused() -> None:
    try:
        sg.parse_page("<html>Redirecting...</html>", retrieved_at=FETCHED)
    except ValueError as exc:
        assert "__NEXT_DATA__" in str(exc)
    else:
        raise AssertionError("an error page was read as a listing")


def test_the_oettinger_night_withholds_the_stake() -> None:
    row = _saves("Jake Oettinger")

    card = _card([row], 0.648, _starters())

    assert card.best_bets == []
    assert [lean["player"] for lean in card.leans] == ["Jake Oettinger"]
    reason = card.leans[0]["demotion_reason"]
    assert reason.startswith(sg.PREFIX)
    assert "Casey DeSmith (Confirmed)" in reason
    rendered = card_module.render_card(card)
    assert "Saves, starter check" in rendered


def test_without_the_check_the_same_night_staked_him() -> None:
    """The defect, reproduced: a starter map that knows nothing about this
    game would have to stake him for the old card to be right, and the old
    card did stake him."""
    row = _saves("Jake Oettinger")
    everyone_starts = sg.GoalieStarters(
        listings={("2026-10-14", "dallas stars"): ("Jake Oettinger", "Confirmed")}
    )

    card = _card([row], 0.648, everyone_starts)

    assert [bet["player"] for bet in card.best_bets] == ["Jake Oettinger"]


def test_the_listed_starter_is_staked_when_confirmed_or_likely() -> None:
    rows = [_saves("Casey DeSmith"), _saves("Scott Wedgewood", line=22.5)]

    card = _card(rows, 0.80, _starters())

    assert sorted(bet["player"] for bet in card.best_bets) == [
        "Casey DeSmith", "Scott Wedgewood",
    ]


def test_an_unconfirmed_guess_is_not_staked() -> None:
    row = _saves("Jakub Dobes", home="Washington Capitals", away="Montréal Canadiens")

    card = _card([row], 0.80, _starters())

    assert card.best_bets == []
    assert "'Unconfirmed'" in card.leans[0]["demotion_reason"]


def test_no_listing_stale_listing_or_no_file_withholds_every_saves_stake(
    tmp_path: Path,
) -> None:
    row = _saves("Casey DeSmith")
    stale = sg.starters_from_rows(
        sg.parse_page(PAGE, retrieved_at=FETCHED), now=CARD_AT + timedelta(hours=13)
    )
    missing = sg.load_starters(tmp_path, now=CARD_AT)
    other_game = sg.GoalieStarters(
        listings={("2026-10-14", "washington capitals"): ("Charlie Lindgren", "Confirmed")}
    )

    for starters in (stale, missing, other_game, None):
        card = _card([row], 0.80, starters)
        assert card.best_bets == [], starters
        assert card.leans[0]["demotion_reason"].startswith(sg.PREFIX)


def test_other_markets_never_read_the_starters() -> None:
    row = dict(_saves("Cale Makar"), market="shots_on_goal", line=2.5, american_odds=120)

    card = _card([row], 0.70, None)

    assert [bet["player"] for bet in card.best_bets] == ["Cale Makar"]


def test_the_fetch_writes_the_file_the_card_reads_and_a_failure_leaves_none(
    tmp_path: Path,
) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fetch_starting_goalies", ROOT / "scripts" / "fetch_starting_goalies.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main(["--processed-dir", str(tmp_path)], fetch=lambda url: PAGE) == 0
    loaded = sg.load_starters(tmp_path, now=datetime.now(timezone.utc))
    assert not loaded.unknown
    assert loaded.listings[("2026-10-14", "dallas stars")] == ("Casey DeSmith", "Confirmed")

    def broken(url):
        raise OSError("offline")

    assert module.main(["--processed-dir", str(tmp_path)], fetch=broken) == 1
    assert not (tmp_path / sg.FILENAME).exists()


def test_gameday_refresh_fetches_the_starters_before_the_card() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text(encoding="utf-8")
    )
    steps = [step for job in workflow["jobs"].values() for step in job.get("steps", [])]
    names = [step.get("name") for step in steps]
    fetch = names.index("Fetch tonight's starting goalies")
    assert fetch < names.index("Render the card")
    assert "fetch_starting_goalies.py" in steps[fetch]["run"]
