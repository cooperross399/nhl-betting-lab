"""The weekly layer scoring reaches Cooper, and decides nothing.

Cooper, 2026-11-10 ("All"): re-score the model layers every Monday and show
him the result. Layer Scoring runs on a Monday cron and keeps its report as
an artifact; Gameday Refresh restores it, the Monday card carries a "Layer
scorecard" section, and card-feed carries the full report.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _payload(generated_at: str = "2026-11-09T00:45:00+00:00") -> dict:
    side = {"bets": 120, "units": -4.2, "roi": -0.035, "low": -0.20, "high": 0.13}
    return {
        "results": {
            "referees": {
                "population_b": {"with": side, "without": side, "contribution_units": -1.5,
                                 "changed_wagers": 44, "union_wagers": 130,
                                 "halves": {"before": -1.0, "after": -0.5}},
                "staked": {"with": side, "without": side, "contribution_units": 0.5,
                           "changed_wagers": 3, "union_wagers": 20,
                           "halves": {"before": 0.0, "after": 0.5}},
                "verdict": "keep",
            },
        },
        "notes": {"settled_wagers": 9876, "window_from": "2026-10-22",
                  "last_night": "2026-11-07", "generated_at": generated_at},
    }


def test_a_fresh_report_is_shown_with_its_sample_and_no_price(tmp_path: Path) -> None:
    from nhl_betting_lab import layer_scorecard as ls

    (tmp_path / ls.REPORT_JSON).write_text(json.dumps(_payload()), encoding="utf-8")
    lines = ls.render_scorecard(ls.load_scorecard(tmp_path), "2026-11-09")
    text = "\n".join(lines)
    assert lines[0] == "## Layer scorecard"
    assert "Referee crews" in text
    assert "-4.2u over 120" in text and "9,876 settled wagers" in text
    assert "| 44 |" in text
    assert "no demonstrated edge" in text
    assert "stays Cooper's call" in text


def test_a_stale_or_missing_report_is_named_never_shown_as_this_weeks(tmp_path: Path) -> None:
    from nhl_betting_lab import layer_scorecard as ls

    missing = "\n".join(ls.render_scorecard(ls.load_scorecard(tmp_path), "2026-11-09"))
    assert "No layer scoring is on hand" in missing

    (tmp_path / ls.REPORT_JSON).write_text(
        json.dumps(_payload("2026-10-26T00:45:00+00:00")), encoding="utf-8")
    stale = "\n".join(ls.render_scorecard(ls.load_scorecard(tmp_path), "2026-11-09"))
    assert "2026-10-26" in stale and "not shown as this week's" in stale
    assert "Referee crews" not in stale

    (tmp_path / ls.REPORT_JSON).write_text("{not json", encoding="utf-8")
    assert ls.load_scorecard(tmp_path) is None


def test_the_card_renders_the_section_it_is_given() -> None:
    from nhl_betting_lab.reports import gameday_card as gc

    card = gc.GamedayCard(generated_at="2026-11-09T14:00:00+00:00")
    card.layer_scorecard = ["## Layer scorecard", "", "body", ""]
    assert "## Layer scorecard" in gc.render_card(card)
    assert "## Layer scorecard" not in gc.render_card(gc.GamedayCard(generated_at="2026-11-10T14:00:00+00:00"))


def test_the_card_script_reads_it_on_mondays_only() -> None:
    source = (ROOT / "scripts" / "run_gameday_card.py").read_text(encoding="utf-8")
    monday = source.index("weekday() == 0")
    assert source.index("card.layer_scorecard = render_layer_scorecard") > monday


def test_layer_scoring_runs_every_monday_and_keeps_only_its_report() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "layer-scoring.yml").read_text(encoding="utf-8"))
    triggers = workflow[True] if True in workflow else workflow["on"]
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert crons == ["30 0 * * 1"]
    assert "workflow_dispatch" in triggers
    steps = workflow["jobs"]["measure"]["steps"]
    uploads = [s for s in steps if "upload-artifact" in str(s.get("uses", ""))]
    assert len(uploads) == 1
    assert uploads[0]["with"]["name"] == "layer-scoring"
    assert uploads[0]["with"]["path"].split() == [
        "data/outputs/layer_scoring.md", "data/outputs/layer_scoring.json"]
    text = (WORKFLOWS / "layer-scoring.yml").read_text(encoding="utf-8")
    assert "ODDS_API" not in text and "NHL_CLOSING_LINES_TOKEN" not in text
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}


def test_gameday_refresh_restores_it_before_the_card_and_publishes_it() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "gameday-refresh.yml").read_text(encoding="utf-8"))
    steps = next(iter(workflow["jobs"].values()))["steps"]
    for job in workflow["jobs"].values():
        names = [s.get("name") for s in job.get("steps", [])]
        if "Render the card" in names:
            steps = job["steps"]
    names = [s.get("name") for s in steps]
    restore = names.index("Restore the weekly layer scorecard")
    assert restore < names.index("Render the card")
    step = steps[restore]
    assert step["continue-on-error"] is True
    assert "--artifact layer-scoring" in step["run"]
    assert "--workflow layer-scoring.yml" in step["run"]
    feed = steps[names.index("Publish the card to the card-feed branch")]["run"]
    assert "latest_layer_scoring.md" in feed
