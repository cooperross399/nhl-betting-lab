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



def test_the_operating_state_records_that_the_headline_was_a_defect() -> None:
    """The +18.1% came from a biased subset, not from the strategy."""
    text = _claude_md()

    assert "were data defects, and stay on the record" in text
    assert "discarding seven prices in ten" in text



def test_the_operating_state_records_the_directional_concentration() -> None:
    text = _claude_md()

    assert "92% of prop bets lean Under" in text
    assert "estimation error concentrates" in text
    assert "Diagnosis, not finding" in text



def test_the_operating_state_names_the_hard_gated_market() -> None:
    text = _claude_md()

    assert "goalie_saves` additionally cannot reach a card" in text
    assert "confirmed-starter source" in text


def test_the_honesty_doc_does_not_claim_calibration_is_evidence_of_an_edge() -> None:
    text = (PROJECT_ROOT / "docs" / "what_we_can_and_cannot_claim.md").read_text(
        encoding="utf-8"
    )

    assert "It establishes nothing about whether the market" in text
    assert "will not let the two be" in text



def test_the_operating_state_records_that_nothing_survives() -> None:
    """The single most important fact about this lab's evidence."""
    text = _claude_md()

    assert "nothing survives" in text
    assert "no demonstrated edge" in text
    assert "4,830 bets" in text



def test_the_operating_state_records_that_the_pipeline_runs_live() -> None:
    text = _claude_md()

    assert "Gameday Refresh runs green end to end" in text
    assert "an absence, not a fault" in text



def test_the_operating_state_warns_about_the_bulk_endpoint() -> None:
    text = _claude_md()

    assert "per-event markets ride the per-event fetch" in text
    assert "422s the whole request" in text



def test_the_operating_state_records_the_index_leak_class() -> None:
    """A leak can live in a lookup key as easily as in a fit."""
    text = _claude_md()

    assert "conditioned on what, known when?" in text
    assert "the only TOI a card can know" in text



def test_the_card_correction_gate_is_driven_by_the_recorded_verdict() -> None:
    text = _claude_md()

    assert "What ships is what the recorded verdicts say, through one door" in text
    assert "verdicts.ships()" in text


def test_the_three_in_four_check_is_recorded_as_not_built() -> None:
    """A suggestive cell with a contradicting mirror is what noise looks like,
    and the record of not building something is as load-bearing as the record
    of building it. It lives in docs/, because the first draft was appended
    to a regenerated output file and lasted exactly one re-run."""
    from nhl_betting_lab.config import PROJECT_ROOT

    text = " ".join(
        (PROJECT_ROOT / "docs" / "schedule_states_checked.md")
        .read_text(encoding="utf-8")
        .split()
    )

    assert "The mirror cell points the wrong way" in text
    assert "nothing was built" in text
    assert "closes less than half the team gap" in text
    assert "recorded rather than chased" in text
