"""The hits-source probe reports who quotes hits and never a price."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "probe_hits_sources", ROOT / "scripts" / "probe_hits_sources.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_books_quoting_counts_outcomes_for_the_market_only():
    payload = {
        "bookmakers": [
            {"title": "Book A", "markets": [
                {"key": "player_hits", "outcomes": [{"price": -120}, {"price": 100}]},
                {"key": "player_points", "outcomes": [{"price": 150}]},
            ]},
            {"title": "Book B", "markets": [{"key": "player_points", "outcomes": [{}]}]},
        ]
    }
    assert probe.books_quoting(payload, "player_hits") == {"Book A": 2}


def test_only_unstarted_events_are_picked_soonest_first():
    now = datetime(2026, 11, 3, 18, tzinfo=timezone.utc)
    events = [
        {"id": "late", "commence_time": "2026-11-04T00:10:00Z"},
        {"id": "started", "commence_time": "2026-11-03T17:00:00Z"},
        {"id": "soon", "commence_time": "2026-11-03T23:10:00Z"},
        {"id": "unknown", "commence_time": ""},
    ]
    picked = probe.pick_events(events, now=now, count=2)
    assert [e["id"] for e in picked] == ["soon", "late"]


def test_the_report_carries_no_price():
    result = {
        "generated_at": "2026-11-03T18:00:00+00:00", "credit_cap": 30,
        "credits_spent": 2, "events": ["A @ B"],
        "asks": [{"event": "A @ B", "region": "us_dfs", "market": "player_hits",
                  "outcome": "answered", "books": {"PrizePicks": 40}}],
    }
    text = probe.render(result)
    assert "PrizePicks (40)" in text
    assert "-120" not in text and "+100" not in text


def test_nothing_is_asked_without_live(capsys):
    assert probe.main(["--credit-cap", "10"]) == 0
    assert "Not asked" in capsys.readouterr().out
