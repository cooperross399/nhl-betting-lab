"""The card resolves a provider's spelling the way the backtest and settlement do.

The backtest (`player_props_backtest`) and forward settlement
(`forward_evidence._settle_prop_row`) join a price row to a player by
expanding `player_name_aliases` on BOTH sides. The card's resolver
(`PlayerPropsModel.resolve_player`) looked up only
`normalize_player_name(provider_name)`, so a book's "A.J. Greer" against the
registry's "Anthony-John (AJ) Greer" (or "J.J. Peterka" against "JJ Peterka")
got no opinion on the card, and so no forward-ledger row, while the backtest
the forward record is compared against matched and bet him. That is a silent,
name-shaped gap between the measured population and the forward one.

What these tests hold: the card resolves every provider form the alias layer
states, and a resolution is still unambiguous — forms that reach different
players resolve to none of them, team narrows exactly as before, and a
parenthesised birth-year disambiguator still never collapses to the bare name.
"""

from __future__ import annotations

import pandas as pd

from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.reports import card_pricing
from test_player_props_model import sample_logs


def _row(player: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "market": "shots_on_goal",
                "player": player,
                "home_team": "TOR",
                "away_team": "BOS",
                "selection": "over",
                "line": 2.5,
                "american_odds": 120,
                "commence_time": "2026-10-01T23:00:00Z",
            }
        ]
    )


def _model(**names: str) -> PlayerPropsModel:
    """Fit sample_logs with player ids (as `p<id>` keys) renamed."""
    logs = sample_logs()
    for key, name in names.items():
        logs.loc[logs["player_id"] == int(key[1:]), "player"] = name
    return PlayerPropsModel().fit(logs)


def test_a_dotted_book_spelling_prices_against_a_nickname_registry_name() -> None:
    model = _model(p1="Anthony-John (AJ) Greer")

    assert model.resolve_player("A.J. Greer") == 1
    probabilities, unresolved = card_pricing.price_props(_row("A.J. Greer"), model)
    assert len(probabilities) == 1
    assert unresolved == []


def test_a_dotted_book_spelling_prices_against_a_dotless_registry_name() -> None:
    model = _model(p1="JJ Peterka")

    assert model.resolve_player("J.J. Peterka") == 1
    probabilities, unresolved = card_pricing.price_props(
        _row("J.J. Peterka"), model
    )
    assert len(probabilities) == 1
    assert unresolved == []


def test_forms_that_reach_different_players_resolve_to_neither() -> None:
    # The provider's "Anthony-John (AJ) Greer" states two forms; each reaches
    # a different fitted player. Picking whichever form is tried first would
    # be a coin flip priced as a certainty.
    model = _model(p1="Anthony John Greer", p2="AJ Greer")

    assert model.resolve_player("Anthony John Greer") == 1
    assert model.resolve_player("AJ Greer") == 2
    assert model.resolve_player("Anthony-John (AJ) Greer") is None
    assert model.resolve_player_in_game(
        "Anthony-John (AJ) Greer", home="TOR", away="BOS"
    ) is None


def test_a_form_two_players_share_is_not_rescued_by_a_form_only_one_has() -> None:
    # "J.J. Peterka" states "j j peterka" (only player 2 has it) and
    # "jj peterka" (both have it). The backtest and settlement see both
    # players as candidates, so the card must not quietly pick player 2.
    model = _model(p1="JJ Peterka", p2="J.J. Peterka")

    assert model.resolve_player("J.J. Peterka") is None
    assert model.resolve_player("J.J. Peterka", team="TOR") is None
    probabilities, unresolved = card_pricing.price_props(
        _row("J.J. Peterka"), model
    )
    assert probabilities == {}
    assert unresolved == ["J.J. Peterka"]


def test_team_narrows_a_shared_name_under_every_book_spelling() -> None:
    # Player 1 plays for TOR, player 101 for BOS (sample_logs).
    model = _model(p1="AJ Greer", p101="AJ Greer")

    assert model.resolve_player("A.J. Greer") is None
    assert model.resolve_player("A.J. Greer", team="TOR") == 1
    assert model.resolve_player("A.J. Greer", team="BOS") == 101
    assert model.resolve_player_in_game("A.J. Greer", home="BOS", away="MTL") == 101
    assert model.resolve_player_in_game("A.J. Greer", home="TOR", away="BOS") is None


def test_a_birth_year_disambiguator_still_never_binds_the_bare_name() -> None:
    model = _model(p1="Elias Pettersson")

    assert model.resolve_player("Elias Pettersson") == 1
    assert model.resolve_player("Elias Pettersson (2004)") is None
    assert model.resolve_player("Elias Pettersson (2004)", team="TOR") is None
