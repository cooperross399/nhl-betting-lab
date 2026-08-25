from __future__ import annotations

from datetime import datetime, timezone

from nhl_betting_lab.reports import card_notification as note
from nhl_betting_lab.reports.gameday_card import BEST_BETS_SECTION, GamedayCard


NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc).isoformat()


def _card(*, generated: bool = True, best_bets: list[dict] | None = None) -> GamedayCard:
    return GamedayCard(
        generated_at=NOW,
        card_generated=generated,
        slate_games=6,
        included_markets=("shots_on_goal",),
        best_bets=best_bets
        if best_bets is not None
        else [
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
        ],
    )


def test_a_first_run_always_posts() -> None:
    """Treating "no previous" as "no change" makes the first card the one that
    never arrives."""
    decision = note.decide(_card(), previous_fingerprint=None)

    assert decision.post is True
    assert decision.selections_changed is True


def test_an_unchanged_clean_run_does_not_post() -> None:
    card = _card()

    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint()
    )

    assert decision.post is False
    assert "did not change" in decision.reason


def test_changed_selections_post() -> None:
    decision = note.decide(_card(), previous_fingerprint="something else")

    assert decision.post is True
    assert decision.selections_changed is True


def test_a_degraded_run_posts_even_when_nothing_changed() -> None:
    """Silence is only safe to read as 'nothing moved' if failure breaks it."""
    card = _card()

    decision = note.decide(
        card,
        previous_fingerprint=card.selection_fingerprint(),
        degraded_notes=["The price fetch failed."],
    )

    assert decision.post is True
    assert decision.degraded is True


def test_a_blocked_card_counts_as_degraded_and_posts() -> None:
    """'No card, because nothing is allowlisted' is information."""
    card = _card(generated=False, best_bets=[])

    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint()
    )

    assert decision.post is True
    assert decision.degraded is True


def test_force_posts_regardless() -> None:
    card = _card()

    decision = note.decide(
        card, previous_fingerprint=card.selection_fingerprint(), force=True
    )

    assert decision.post is True
    assert "Forced" in decision.reason


def test_the_marker_is_in_the_first_paragraph_when_selections_changed() -> None:
    """Contract: Cooper's scheduled task matches this phrase literally."""
    card = _card()
    decision = note.decide(card, previous_fingerprint=None)

    body = note.render_comment(card, decision)
    first_paragraph = body.split("\n\n", 1)[0]

    assert note.SELECTIONS_CHANGED_MARKER in first_paragraph


def test_the_marker_is_absent_when_the_selections_did_not_change() -> None:
    card = _card()
    decision = note.decide(
        card,
        previous_fingerprint=card.selection_fingerprint(),
        degraded_notes=["Results could not be refreshed."],
    )

    body = note.render_comment(card, decision, degraded_notes=["x"])

    assert note.SELECTIONS_CHANGED_MARKER not in body


def test_a_blocked_card_still_carries_the_marker_when_it_is_a_change() -> None:
    card = _card(generated=False, best_bets=[])
    decision = note.decide(card, previous_fingerprint="had selections before")

    body = note.render_comment(card, decision)
    first_paragraph = body.split("\n\n", 1)[0]

    assert note.SELECTIONS_CHANGED_MARKER in first_paragraph
    assert "no card this run" in first_paragraph


def test_the_comment_carries_the_whole_card() -> None:
    card = _card()
    decision = note.decide(card, previous_fingerprint=None)

    body = note.render_comment(card, decision)

    assert "# NHL gameday card" in body
    assert "Auston Matthews" in body


def test_the_comment_links_the_three_measurement_paths() -> None:
    card = _card()
    decision = note.decide(card, previous_fingerprint=None)

    body = note.render_comment(card, decision)

    for path in note.MEASUREMENT_PATHS:
        assert path in body


def test_the_comment_states_what_the_run_did_not_do() -> None:
    card = _card()
    decision = note.decide(card, previous_fingerprint=None)

    body = note.render_comment(card, decision)

    assert "No bet was placed" in body
    assert "no market was allowlisted" in body


def test_degraded_notes_appear_in_the_comment() -> None:
    card = _card()
    decision = note.decide(
        card, previous_fingerprint=None, degraded_notes=["The API was down."]
    )

    body = note.render_comment(card, decision, degraded_notes=["The API was down."])

    assert "What went wrong" in body
    assert "The API was down." in body


def test_the_run_url_is_included_when_given() -> None:
    card = _card()
    decision = note.decide(card, previous_fingerprint=None)

    body = note.render_comment(card, decision, run_url="https://example/run/1")

    assert "https://example/run/1" in body


def test_the_issue_body_explains_the_marker_it_will_use() -> None:
    assert note.SELECTIONS_CHANGED_MARKER in note.OPERATING_HOME_BODY
    assert "No bet is ever placed" in note.OPERATING_HOME_BODY


def test_a_previous_fingerprint_is_read_out_of_saved_json() -> None:
    assert note.previous_fingerprint_from({"selection_fingerprint": "abc"}) == "abc"
    assert note.previous_fingerprint_from({}) is None
    assert note.previous_fingerprint_from("not a dict") is None
