"""A clean run posted on request never tells the reader the run was degraded.

`decide(..., force=True)` posts whatever happened. When the run was clean and
the selections did not change, the decision says `degraded=False` — and the
comment used to open "this comment is here because the run was degraded"
anyway. A reader who trusts the comment then goes looking for a fault that
does not exist, and the next genuinely degraded comment reads like the same
false alarm. The opening now follows the decision: a clean forced post says it
was posted on request, a degraded one keeps saying it was degraded, and the
"Selections changed" marker is untouched either way.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nhl_betting_lab.reports import card_notification as note
from nhl_betting_lab.reports.gameday_card import BEST_BETS_SECTION, GamedayCard


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc).isoformat()


def _card(*, generated: bool = True) -> GamedayCard:
    return GamedayCard(
        generated_at=NOW,
        card_generated=generated,
        slate_games=6,
        included_markets=("shots_on_goal",),
        best_bets=[
            {
                "market": "shots_on_goal",
                "player": "Auston Matthews",
                "home_team": "TOR",
                "away_team": "BOS",
                "selection": "over",
                "line": 3.5,
                "american_odds": 135,
                "model_probability": 0.60,
                "edge": 0.15,
                "suggested_units": 0.5,
                "book": "FanDuel",
                "section": BEST_BETS_SECTION,
            }
        ]
        if generated
        else [],
    )


def _first_paragraph(body: str) -> str:
    return body.split("\n\n", 1)[0]


def test_a_clean_forced_unchanged_post_does_not_say_degraded() -> None:
    card = _card()
    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint(), force=True
    )
    assert decision.post is True
    assert decision.degraded is False
    assert decision.selections_changed is False

    body = note.render_comment(card, decision)

    assert "degraded" not in body.lower()


def test_a_clean_forced_unchanged_post_says_it_was_on_request() -> None:
    card = _card()
    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint(), force=True
    )

    opening = _first_paragraph(note.render_comment(card, decision))

    assert "Selections are unchanged" in opening
    assert "on request" in opening
    assert note.SELECTIONS_CHANGED_MARKER not in opening


def test_a_degraded_unchanged_post_still_says_it_was_degraded() -> None:
    card = _card()
    decision = note.decide(
        card,
        previous_fingerprint=card.selection_fingerprint(),
        degraded_notes=["Results could not be refreshed."],
    )
    assert decision.degraded is True

    opening = _first_paragraph(
        note.render_comment(
            card, decision, degraded_notes=["Results could not be refreshed."]
        )
    )

    assert "because the run was degraded" in opening
    assert "on request" not in opening
    assert note.SELECTIONS_CHANGED_MARKER not in opening


def test_a_forced_degraded_unchanged_post_still_says_it_was_degraded() -> None:
    """Forcing a post never hides that the run was degraded."""
    card = _card()
    decision = note.decide(
        card,
        previous_fingerprint=card.selection_fingerprint(),
        degraded_notes=["The price fetch failed."],
        force=True,
    )
    assert decision.degraded is True

    opening = _first_paragraph(
        note.render_comment(
            card, decision, degraded_notes=["The price fetch failed."]
        )
    )

    assert "because the run was degraded" in opening


def test_a_forced_changed_post_still_carries_the_marker_first() -> None:
    """The contract marker's behaviour is unchanged by the new wording."""
    card = _card()
    decision = note.decide(card, previous_fingerprint="other", force=True)

    opening = _first_paragraph(note.render_comment(card, decision))

    assert note.SELECTIONS_CHANGED_MARKER in opening
    assert "on request" not in opening
    assert "degraded" not in opening.lower()
