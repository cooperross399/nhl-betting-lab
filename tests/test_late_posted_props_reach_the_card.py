"""Blocked shots, hits and goalie saves can reach the card (Cooper, 2026-10-12).

All three were allowlisted and priced, and never once reached a card. Books
post them late: on every 9:40 AM ET card from 2026-09-29 to 2026-10-12 they
were priced for 0-3 games of the slate, and `require_full_slate` excluded
each one whole; `goalie_saves` was also hard-gated for want of a confirmed
starter. Cooper asked for them on the card. What these tests hold:

* the three are judged game by game: priced for some games, they are
  eligible and say which games they are missing, while every other market
  stays strict;
* the card shows a partly covered market under "Priced game by game", picks
  only where it is priced, and stakes a goalie saves best bet;
* Gameday Refresh carries an afternoon run that a clean morning card never
  stands down.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

from nhl_betting_lab import market_eligibility as elig
from nhl_betting_lab.data.starting_goalies import GoalieStarters
from nhl_betting_lab.providers.team_names import normalize_team_name
from nhl_betting_lab.reports import gameday_card as card_module
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.staging_provider_policy import load_policy

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "gameday-refresh.yml"
AFTERNOON = "30 12 * 1-4,10-12 *"
NOW = datetime(2026, 10, 12, 20, 30, tzinfo=timezone.utc)


def _policy(tmp_path: Path, markets: list[str]):
    path = tmp_path / "data" / "manual" / "staging_provider_policy.json"
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
                        "approved_at": "2026-10-01T09:00:00-04:00",
                        "reviewer_name": "cooperross399",
                        "evidence_receipt_id": "receipt-1",
                        "required_markets": markets,
                    }
                },
                "max_provider_run_age_hours": 12,
            }
        ),
        encoding="utf-8",
    )
    return load_policy(repository_root=tmp_path)


def _row(market: str, home: str, away: str, **extra) -> dict:
    row = {
        "date": "2026-10-12",
        "commence_time": (NOW + timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
        "home_team": home,
        "away_team": away,
        "market": market,
        "player": "Somebody",
        "selection": "over",
        "line": 1.5,
        "book": "DraftKings",
        "american_odds": 120,
    }
    row.update(extra)
    return row


SLATE = ("2026-10-12 BOS@TOR", "2026-10-12 NYR@MTL", "2026-10-12 VGK@MIN")


def test_the_three_late_props_are_the_game_by_game_markets() -> None:
    assert card_module.GAME_BY_GAME_MARKETS == {
        "blocked_shots",
        "goalie_saves",
        "hits",
    }
    assert "goalie_saves" not in card_module.HARD_GATED_MARKETS


def test_a_late_prop_priced_for_some_games_is_eligible_and_names_the_rest(
    tmp_path: Path,
) -> None:
    prices = pd.DataFrame(
        [
            _row("blocked_shots", "TOR", "BOS"),
            _row("hits", "TOR", "BOS"),
            _row("hits", "MTL", "NYR"),
            _row("goalie_saves", "MIN", "VGK"),
            _row("points", "TOR", "BOS"),
        ]
    )
    markets = ["blocked_shots", "hits", "goalie_saves", "points"]

    report = elig.assess_markets(
        prices,
        slate_games=SLATE,
        policy=_policy(tmp_path, markets),
        provider_name="the_odds_api",
        markets=markets,
        game_by_game=card_module.GAME_BY_GAME_MARKETS,
    )
    by_market = {item.market: item for item in report.markets}

    assert set(report.eligible_markets) == {"blocked_shots", "hits", "goalie_saves"}
    assert by_market["blocked_shots"].missing_games == SLATE[1:]
    assert "priced for 1 of 3" in by_market["blocked_shots"].reason
    assert "not a pass" in by_market["blocked_shots"].reason
    assert by_market["hits"].missing_games == (SLATE[2],)
    # Every other market keeps the whole-slate rule.
    assert by_market["points"].state == elig.INCOMPLETE


def test_without_the_rule_the_same_prices_are_incomplete(tmp_path: Path) -> None:
    """The default is unchanged for any caller that does not name markets."""
    prices = pd.DataFrame([_row("blocked_shots", "TOR", "BOS")])

    report = elig.assess_markets(
        prices,
        slate_games=SLATE,
        policy=_policy(tmp_path, ["blocked_shots"]),
        provider_name="the_odds_api",
        markets=["blocked_shots"],
    )

    assert report.markets[0].state == elig.INCOMPLETE


def test_a_late_prop_with_no_rows_at_all_is_still_unavailable(tmp_path: Path) -> None:
    prices = pd.DataFrame([_row("points", "TOR", "BOS")])

    report = elig.assess_markets(
        prices,
        slate_games=SLATE,
        policy=_policy(tmp_path, ["hits", "points"]),
        provider_name="the_odds_api",
        markets=["hits"],
        game_by_game=card_module.GAME_BY_GAME_MARKETS,
    )

    assert report.markets[0].state == elig.UNAVAILABLE


def _key(row: dict) -> tuple:
    return selection_key(
        SimpleNamespace(**row),
        market=row["market"],
        selection=row["selection"],
        line=row["line"],
    )


def test_the_card_stakes_a_saves_bet_and_names_the_missing_games(
    tmp_path: Path,
) -> None:
    saves = _row(
        "goalie_saves",
        "MIN",
        "VGK",
        player="Filip Gustavsson",
        line=25.5,
        american_odds=110,
    )
    prices = pd.DataFrame([saves])
    report = elig.assess_markets(
        prices,
        slate_games=SLATE,
        policy=_policy(tmp_path, ["goalie_saves"]),
        provider_name="the_odds_api",
        markets=["goalie_saves"],
        game_by_game=card_module.GAME_BY_GAME_MARKETS,
    )

    # +110 is in the -110..+110 bracket, which needs 64.4%.
    # Gustavsson is Minnesota's listed starter: since 2026-10-14 a saves
    # stake needs one (tests/test_a_saves_stake_needs_the_listed_starter.py).
    starters = GoalieStarters(
        listings={(_key(saves)[6], normalize_team_name("MIN")): ("Filip Gustavsson", "Confirmed")}
    )
    card = card_module.build_card(
        prices, {_key(saves): 0.70}, eligibility=report, now=NOW,
        goalie_starters=starters,
    )
    rendered = card_module.render_card(card)

    assert card.card_generated
    assert [row["market"] for row in card.best_bets] == ["goalie_saves"]
    assert card.best_bets[0]["suggested_units"] > 0
    assert "goalie_saves" not in card.excluded_markets
    assert "## Priced game by game" in rendered
    assert "priced for 1 of 3" in card.partial_markets["goalie_saves"]


def _precheck_script() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["precheck"]["steps"]
    feed = next(step for step in steps if step.get("id") == "feed")
    assert feed["env"]["SCHEDULE"] == "${{ github.event.schedule }}"
    return (
        feed["run"]
        .replace("${{ github.event_name }}", "schedule")
        .replace("${{ github.repository }}", "cooperross399/nhl-betting-lab")
        .replace("${{ github.ref }}", "refs/heads/main")
    )


def test_gameday_refresh_has_an_afternoon_run() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get("on") or workflow.get(True)
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert AFTERNOON in crons


def test_a_clean_morning_card_never_stands_the_afternoon_run_down(
    tmp_path: Path,
) -> None:
    """The precheck returns before it reads card-feed at all, so no git, no
    network: a git that would fail the run is put first on PATH to prove it."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "git").write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    (stub / "git").chmod(0o755)
    output = tmp_path / "out"
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", _precheck_script()],
        env={
            **os.environ,
            "PATH": f"{stub}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "SCHEDULE": AFTERNOON,
            "GH_TOKEN": "x",
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8").strip() == "already=false"
    assert "Afternoon update" in result.stdout


def test_the_morning_triggers_still_read_card_feed(tmp_path: Path) -> None:
    """The morning backup still asks card-feed: with git failing it runs
    rather than skips, which is the precheck's existing no-branch path."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "git").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (stub / "git").chmod(0o755)
    output = tmp_path / "out"
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", _precheck_script()],
        env={
            **os.environ,
            "PATH": f"{stub}:{os.environ['PATH']}",
            "GITHUB_OUTPUT": str(output),
            "SCHEDULE": "0 7 * 1-4,10-12 *",
            "GH_TOKEN": "x",
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "No card-feed branch yet" in result.stdout
