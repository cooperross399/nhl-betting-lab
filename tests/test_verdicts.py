"""The one door every recorded policy decision is read through."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhl_betting_lab import verdicts


def test_a_missing_verdict_file_ships_nothing(tmp_path: Path) -> None:
    """"No recorded decision" reads as "no policy in force"."""
    assert verdicts.ships("props_b2b", output_dir=tmp_path) is False


def test_an_unreadable_verdict_file_ships_nothing(tmp_path: Path) -> None:
    (tmp_path / "props_rest_experiment.json").write_text("{broken")

    assert verdicts.ships("props_b2b", output_dir=tmp_path) is False


def test_a_recorded_ship_is_in_force(tmp_path: Path) -> None:
    (tmp_path / "props_rest_experiment.json").write_text(
        json.dumps({"ships": ["props_b2b"]})
    )

    assert verdicts.ships("props_b2b", output_dir=tmp_path) is True


def test_an_empty_ships_list_is_off(tmp_path: Path) -> None:
    (tmp_path / "correction_experiment.json").write_text(
        json.dumps({"ships": []})
    )

    assert verdicts.ships("by_toi", output_dir=tmp_path) is False


def test_an_unknown_policy_is_an_error_not_a_default() -> None:
    with pytest.raises(KeyError, match="Known:"):
        verdicts.ships("goalie_telepathy")


def test_a_boolean_ships_field_reads_as_off(tmp_path: Path) -> None:
    """The team experiment once wrote `ships: true`, and the shared reader
    saw "off" — which is the conservative failure, and why the convention is
    a list of names rather than a flag."""
    (tmp_path / "rest_experiment.json").write_text(json.dumps({"ships": True}))

    assert verdicts.ships("team_b2b", output_dir=tmp_path) is False


def test_the_live_verdicts_read_as_recorded() -> None:
    """The three shipped decisions, against the real files."""
    assert verdicts.ships("by_toi") is False
    assert verdicts.ships("team_b2b") is True
    assert verdicts.ships("props_b2b") is True


def test_describe_names_every_policy() -> None:
    line = verdicts.describe()

    for policy in ("by_toi", "team_b2b", "props_b2b"):
        assert policy in line
