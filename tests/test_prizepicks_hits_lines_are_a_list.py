"""PrizePicks hits lines reach the card as a list and never as a price.

Cooper, 2026-11-04: "Add as lines only". The lines are priced into a map of
their own, rendered with the model's chance, and never staked, frozen or
read as one of the card's priced inputs.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.dfs_hits_lines import (
    LINES_FILENAME,
    SECTION_TITLE,
    build_hits_lines,
    load_lines,
    pricing_frame,
)
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.reports.gameday_card import GamedayCard, render_card

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)


def _row(player: str, line: float, selection: str, start: datetime) -> dict:
    return {
        "date": "2026-11-04",
        "commence_time": start.isoformat().replace("+00:00", "Z"),
        "home_team": "Washington Capitals",
        "away_team": "Dallas Stars",
        "market": "hits",
        "player": player,
        "selection": selection,
        "line": line,
        "american_odds": -137,
        "book": "PrizePicks",
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return odds_api.to_frame(rows)


def _script():
    spec = importlib.util.spec_from_file_location(
        "run_gameday_card", ROOT / "scripts" / "run_gameday_card.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_the_card_never_reads_the_lines_file_as_prices(tmp_path):
    later = NOW + timedelta(hours=9)
    odds_api.write_staging(
        [_row("Tom Wilson", 2.5, "over", later)], filename=LINES_FILENAME,
        staging_dir=tmp_path,
    )
    assert LINES_FILENAME not in {
        odds_api.STAGING_PRICES_FILENAME, odds_api.STAGING_PROPS_FILENAME,
    }
    assert _script()._staged_prices(tmp_path).empty
    assert len(load_lines(tmp_path)) == 1


def test_both_sides_are_priced_even_when_one_is_posted():
    later = NOW + timedelta(hours=9)
    frame = pricing_frame(_frame([_row("Tom Wilson", 2.5, "over", later)]), day="2026-11-04")
    assert sorted(frame["selection"]) == ["over", "under"]


def test_a_listed_line_carries_the_models_chance_and_no_stake():
    later = NOW + timedelta(hours=9)
    lines = _frame([
        _row("Tom Wilson", 2.5, "over", later),
        _row("Jamie Benn", 1.5, "over", later),
        _row("Nobody Known", 1.5, "over", later),
    ])
    priced = pricing_frame(lines, day="2026-11-04")
    probabilities = {}
    for row in priced.itertuples():
        if row.player == "Nobody Known":
            continue
        over = 0.62 if row.player == "Tom Wilson" else 0.41
        probabilities[selection_key(row, market="hits", selection=row.selection,
                                    line=float(row.line))] = (
            over if row.selection == "over" else 1 - over
        )
    hits = build_hits_lines(lines, probabilities, now=NOW, day="2026-11-04")
    assert [r["player"] for r in hits.rows] == ["Tom Wilson", "Jamie Benn"]
    assert hits.without_opinion == 1
    assert hits.rows[0]["model_side"] == "over"
    assert hits.rows[1]["model_side"] == "under"
    for row in hits.rows:
        assert not {"suggested_units", "units", "stake", "american_odds", "edge"} & set(row)

    card = GamedayCard(generated_at=NOW.isoformat())
    card.hits_lines_built = True
    card.hits_lines_fetched = True
    card.hits_lines = hits.rows
    card.hits_lines_without_opinion = hits.without_opinion
    text = render_card(card)
    assert f"## {SECTION_TITLE}" in text
    assert "| Tom Wilson | 2.5 | 62.0% | 38.0% | Over |" in text
    assert "-137" not in text
    assert "nothing here is a bet" in text
    assert card.selection_fingerprint() == GamedayCard(generated_at=NOW.isoformat()).selection_fingerprint()


def test_a_started_game_is_not_listed():
    earlier = NOW - timedelta(minutes=5)
    lines = _frame([_row("Tom Wilson", 2.5, "over", earlier)])
    probabilities = {
        selection_key(r, market="hits", selection=r.selection, line=2.5): 0.5
        for r in pricing_frame(lines, day="2026-11-04").itertuples()
    }
    hits = build_hits_lines(lines, probabilities, now=NOW, day="2026-11-04")
    assert hits.rows == []
    assert hits.removed_by_guard == 1


def test_no_file_says_so_rather_than_saying_nobody_posted(tmp_path):
    assert load_lines(tmp_path) is None
    card = GamedayCard(generated_at=NOW.isoformat())
    card.hits_lines_built = True
    assert "were not fetched this run" in render_card(card)


def test_the_workflow_fetches_the_lines_softly_before_the_card():
    text = (ROOT / ".github" / "workflows" / "gameday-refresh.yml").read_text()
    fetch = text.index("scripts/fetch_dfs_hits_lines.py --live --credit-cap 20")
    assert text.index("name: Fetch prices into staging") < fetch
    assert fetch < text.index("scripts/run_gameday_card.py")
    step = text[text.index("name: Fetch PrizePicks hits lines"):fetch]
    assert "continue-on-error: true" in step
