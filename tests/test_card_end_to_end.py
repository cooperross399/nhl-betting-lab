"""The card, driven with the strings the provider actually sends.

Every unit test in this suite uses tidy fixtures where the team is `"TOR"` and
the player is `"Star TOR"`. That is exactly how two silent bugs survived: the
provider says `"Toronto Maple Leafs"` and `"Alexis Lafreniere"`, the models are
keyed by `"TOR"` and `"Alexis Lafrenière"`, every lookup missed, and the card
priced each game league-average against league-average with no error anywhere.

So these tests use the provider's vocabulary throughout, and assert on the
thing that failed: that a real name produces a real, *differentiated* opinion.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.market_eligibility import (
    ELIGIBLE,
    EligibilityReport,
    MarketEligibility,
)
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers.team_names import build_team_name_map
from nhl_betting_lab.reports.card_pricing import price_props, price_team_markets
from nhl_betting_lab.reports.gameday_card import build_card, render_card


NOW = datetime(2026, 1, 10, 18, 0, tzinfo=timezone.utc)

#: What the provider sends, paired with what the NHL calls them.
LEAFS = "Toronto Maple Leafs"
BRUINS = "Boston Bruins"
CANADIENS = "Montréal Canadiens"


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _logs() -> pd.DataFrame:
    """Two clubs, two players each, enough games to clear every minimum."""
    rows: list[dict] = []
    for index in range(60):
        day = 1 + index % 28
        month = 1 + index // 28
        home, away = ("TOR", "BOS") if index % 2 == 0 else ("BOS", "TOR")
        for team, opponent, venue in ((home, away, "home"), (away, home, "away")):
            star = 1 if team == "TOR" else 101
            grinder = 2 if team == "TOR" else 102
            # A heavy shooter and a light one, so a league-average fallback is
            # visibly different from a real opinion.
            rows.append(
                {
                    "game_id": index,
                    "date": f"2025-{month:02d}-{day:02d}",
                    "player_id": star,
                    "player": (
                        "Alexis Lafrenière" if team == "TOR" else "Sebastian Aho"
                    ),
                    "role": "skater",
                    "position": "C",
                    "team": team,
                    "opponent": opponent,
                    "venue": venue,
                    "toi_seconds": 1400,
                    "shots_on_goal": 6,
                    "goals": 1,
                    "assists": 1,
                    "points": 2,
                    "blocked_shots": 1,
                    "power_play_goals": 1,
                    "saves": 0,
                    "shots_against": 0,
                }
            )
            rows.append(
                {
                    "game_id": index,
                    "date": f"2025-{month:02d}-{day:02d}",
                    "player_id": grinder,
                    "player": f"Grinder {team}",
                    "role": "skater",
                    "position": "D",
                    "team": team,
                    "opponent": opponent,
                    "venue": venue,
                    "toi_seconds": 700,
                    # Low but not zero: a rate of exactly zero is refused by
                    # the model rather than priced, which is correct and would
                    # make this test measure the wrong thing.
                    "shots_on_goal": 1,
                    "goals": 0,
                    "assists": 0,
                    "points": 0,
                    "blocked_shots": 3,
                    "power_play_goals": 0,
                    "saves": 0,
                    "shots_against": 0,
                }
            )
    return pd.DataFrame(rows)


def _games() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": index,
                "date": f"2025-{1 + index // 28:02d}-{1 + index % 28:02d}",
                "home_team": "TOR" if index % 2 == 0 else "BOS",
                "away_team": "BOS" if index % 2 == 0 else "TOR",
                "home_goals": 5 if index % 2 == 0 else 2,
                "away_goals": 2 if index % 2 == 0 else 4,
                "regulation": index % 5 != 0,
            }
            for index in range(60)
        ]
    )


def _team_map(tmp_path: Path) -> dict[str, str]:
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    for index, (abbrev, place, common) in enumerate(
        (("TOR", "Toronto", "Maple Leafs"), ("BOS", "Boston", "Bruins"),
         ("MTL", "Montréal", "Canadiens"))
    ):
        (directory / f"{index}.json").write_text(
            json.dumps(
                {
                    "homeTeam": {
                        "abbrev": abbrev,
                        "placeName": {"default": place},
                        "commonName": {"default": common},
                    },
                    "awayTeam": {
                        "abbrev": "BOS",
                        "placeName": {"default": "Boston"},
                        "commonName": {"default": "Bruins"},
                    },
                }
            ),
            encoding="utf-8",
        )
    return build_team_name_map(tmp_path)


def _prices() -> pd.DataFrame:
    common = {
        "date": "2026-01-10",
        "commence_time": _at(5),
        "home_team": LEAFS,
        "away_team": BRUINS,
        "book": "DraftKings",
    }
    return pd.DataFrame(
        [
            # The provider's accent-free spelling of an accented registry name.
            {**common, "market": "shots_on_goal", "player": "Alexis Lafreniere",
             "selection": "over", "line": 2.5, "american_odds": 160},
            {**common, "market": "shots_on_goal", "player": "Grinder TOR",
             "selection": "over", "line": 2.5, "american_odds": 160},
            {**common, "market": "moneyline", "player": "",
             "selection": "home", "line": None, "american_odds": 120},
            {**common, "market": "total_goals", "player": "",
             "selection": "over", "line": 5.5, "american_odds": 110},
        ]
    )


def _eligibility(markets: list[str]) -> EligibilityReport:
    return EligibilityReport(
        provider_name="the_odds_api",
        games_in_slate=1,
        markets=[
            MarketEligibility(market=m, state=ELIGIBLE, reason="Allowlisted.")
            for m in markets
        ],
    )


def test_a_provider_team_name_produces_a_real_opinion(tmp_path: Path) -> None:
    """Without the team map this returns league-average for every game."""
    model = TeamModel().fit(_games())
    mapping = _team_map(tmp_path)

    priced, unresolved = price_team_markets(_prices(), model, team_names=mapping)

    assert unresolved == []
    moneyline = [v for k, v in priced.items() if k[0] == "moneyline"]
    assert moneyline
    # Toronto wins five of every ten in this fixture, so a real opinion is
    # well above the coin flip a missed lookup would produce.
    assert moneyline[0] > 0.55


def test_an_unmapped_team_produces_no_opinion_rather_than_a_default(
    tmp_path: Path,
) -> None:
    prices = _prices()
    prices["home_team"] = "Hartford Whalers"
    model = TeamModel().fit(_games())

    priced, unresolved = price_team_markets(
        prices, model, team_names=_team_map(tmp_path)
    )

    assert priced == {}
    assert unresolved == ["Hartford Whalers"]


def test_an_accented_player_resolves_from_the_provider_spelling(
    tmp_path: Path,
) -> None:
    model = PlayerPropsModel().fit(_logs())

    priced, unresolved = price_props(
        _prices(), model, team_names=_team_map(tmp_path)
    )

    assert "Alexis Lafreniere" not in unresolved
    assert any(key[1] == "alexis lafreniere" for key in priced)


def test_two_players_in_one_game_get_different_prices(tmp_path: Path) -> None:
    """A missed lookup would give both the same league-average number."""
    model = PlayerPropsModel().fit(_logs())

    priced, _ = price_props(_prices(), model, team_names=_team_map(tmp_path))
    star = next(v for k, v in priced.items() if k[1] == "alexis lafreniere")
    grinder = next(v for k, v in priced.items() if k[1] == "grinder tor")

    assert star > grinder + 0.15


def test_the_card_is_keyed_by_the_providers_own_labels(tmp_path: Path) -> None:
    """The probability map must join back to the price rows it came from."""
    props = PlayerPropsModel().fit(_logs())
    teams = TeamModel().fit(_games())
    mapping = _team_map(tmp_path)
    prices = _prices()

    probabilities, _ = price_props(prices, props, team_names=mapping)
    team_probabilities, _ = price_team_markets(prices, teams, team_names=mapping)
    probabilities.update(team_probabilities)

    card = build_card(
        prices,
        probabilities,
        eligibility=_eligibility(["shots_on_goal", "moneyline", "total_goals"]),
        now=NOW,
    )

    assert card.card_generated is True
    assert card.best_bets or card.leans or card.passes


def test_the_rendered_card_shows_the_provider_team_names(tmp_path: Path) -> None:
    props = PlayerPropsModel().fit(_logs())
    mapping = _team_map(tmp_path)
    prices = _prices()
    probabilities, _ = price_props(prices, props, team_names=mapping)

    card = build_card(
        prices,
        probabilities,
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )
    rendered = render_card(card)

    assert BRUINS in rendered
    assert LEAFS in rendered


def test_a_started_game_is_still_quarantined_with_real_names(
    tmp_path: Path,
) -> None:
    prices = _prices()
    prices["commence_time"] = _at(-1)
    props = PlayerPropsModel().fit(_logs())
    mapping = _team_map(tmp_path)
    probabilities, _ = price_props(prices, props, team_names=mapping)

    card = build_card(
        prices,
        probabilities,
        eligibility=_eligibility(["shots_on_goal"]),
        now=NOW,
    )

    assert card.best_bets == []
    assert card.leans == []
    assert card.quarantined


def test_without_a_team_map_the_prices_are_reported_not_silently_defaulted(
    tmp_path: Path,
) -> None:
    """The old behaviour: every lookup missed and nothing said so. Now an
    empty map means the labels are passed through, and a label that is not an
    abbreviation simply finds no team — which the model reports."""
    props = PlayerPropsModel().fit(_logs())

    priced, unresolved = price_props(_prices(), props, team_names={})

    assert priced == {}
    assert unresolved
