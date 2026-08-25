"""Cooper's local scheduled tasks hard-code these strings and paths.

Renaming any of them silently breaks his automation, and the breakage looks
exactly like the lab going quiet — which is the one failure mode the delivery
design cannot otherwise see. So each one is asserted here, against the file
that actually carries it rather than against a copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.reports.card_notification import (
    MEASUREMENT_PATHS,
    OPERATING_HOME_TITLE,
    SELECTIONS_CHANGED_MARKER,
)


WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _claude_md() -> str:
    """CLAUDE.md with its line wrapping flattened.

    Asserting on wrapped prose otherwise fails on where a paragraph happened
    to break, which is a test failing on formatting rather than on meaning.
    """
    return " ".join(
        (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8").split()
    )


def test_the_workflow_file_is_at_the_contracted_path() -> None:
    assert WORKFLOW_PATH.is_file()


def test_the_workflow_is_named_exactly_gameday_refresh() -> None:
    assert re.search(r"^name: Gameday Refresh$", _workflow_text(), re.MULTILINE)


def test_the_job_display_name_matches_too() -> None:
    """`gh run list --workflow` matches the file; a human reads the job name."""
    assert "name: Gameday Refresh" in _workflow_text()


def test_the_operating_home_title_is_exact() -> None:
    assert OPERATING_HOME_TITLE == "NHL Betting Lab — Claude Operating Home"


def test_the_operating_home_title_uses_an_em_dash_not_a_hyphen() -> None:
    """A hyphen would create a second issue and split the history in two."""
    assert "—" in OPERATING_HOME_TITLE
    assert " - " not in OPERATING_HOME_TITLE


def test_the_changed_marker_is_exact() -> None:
    assert SELECTIONS_CHANGED_MARKER == "Selections changed"


def test_the_three_measurement_paths_are_exact() -> None:
    assert MEASUREMENT_PATHS == (
        "data/outputs/player_props_backtest.md",
        "data/outputs/props_calibration.md",
        "data/outputs/what_we_can_claim.md",
    )


@pytest.mark.parametrize("path", MEASUREMENT_PATHS)
def test_each_measurement_path_is_the_one_its_module_writes(path: str) -> None:
    from nhl_betting_lab.reports.player_props_backtest import (
        BACKTEST_MARKDOWN_FILENAME,
    )
    from nhl_betting_lab.reports.props_calibration import (
        CALIBRATION_MARKDOWN_FILENAME,
    )
    from nhl_betting_lab.reports.what_we_can_claim import CLAIMS_MARKDOWN_FILENAME

    written = {
        BACKTEST_MARKDOWN_FILENAME,
        CALIBRATION_MARKDOWN_FILENAME,
        CLAIMS_MARKDOWN_FILENAME,
    }
    assert Path(path).name in written


def test_the_workflow_uses_the_contracted_secret_name() -> None:
    assert "secrets.NHL_ODDS_API_KEY" in _workflow_text()


def test_the_workflow_never_echoes_the_secret() -> None:
    """A secret in a log is a secret that has left the building."""
    text = _workflow_text()

    assert "echo ${{ secrets" not in text
    assert "echo $NHL_ODDS_API_KEY" not in text


def test_the_workflow_says_it_places_no_bet_and_edits_no_policy() -> None:
    text = _workflow_text()

    assert "placed no bet" in text
    assert "edited no policy" in text
    assert "allowlisted no provider" in text


def test_the_workflow_can_post_issue_comments_and_nothing_more() -> None:
    text = _workflow_text()

    assert "issues: write" in text
    assert "contents: read" in text
    assert "contents: write" not in text


def test_claude_md_records_every_contract_string() -> None:
    """The operating instructions must not drift from the code."""
    text = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "Gameday Refresh" in text
    assert OPERATING_HOME_TITLE in text
    assert SELECTIONS_CHANGED_MARKER in text
    for path in MEASUREMENT_PATHS:
        assert path in text


def test_claude_md_carries_a_current_operating_state() -> None:
    """A future session reads this first; if it is absent or stale, every
    other document is being read without context."""
    text = _claude_md()

    assert "## Current operating state" in text
    assert "no demonstrated edge" in text
    assert "No market is allowlisted" in text


def test_the_operating_state_hedges_the_one_surviving_result() -> None:
    """It survived on one window and was contradicted on the next."""
    text = _claude_md()

    assert "shots_on_goal` was the one result" in text
    assert "did not replicate" in text
    assert "Nothing is allowlisted" in text


def test_the_operating_state_records_the_directional_concentration() -> None:
    text = _claude_md()

    assert "on the Under" in text
    assert "One directional disagreement" in text


def test_the_operating_state_names_the_hard_gated_market() -> None:
    text = _claude_md()

    assert "goalie_saves` cannot reach the card" in text
    assert "not a no-value judgement" in text


def test_the_honesty_doc_does_not_claim_calibration_is_evidence_of_an_edge() -> None:
    text = (PROJECT_ROOT / "docs" / "what_we_can_and_cannot_claim.md").read_text(
        encoding="utf-8"
    )

    assert "It establishes nothing about whether the market" in text
    assert "will not let the two be" in text


def test_the_operating_state_records_the_failed_replication() -> None:
    """The single most important fact about this lab's evidence."""
    text = _claude_md()

    assert "did not replicate" in text
    assert "nothing survives" in text
    assert "system working, not failing" in text
