"""Season Sim warns only about what went wrong, and reads the notes' names.

Run 42837197651's log carried "The last season projection could not be
restored" and "The card's team ratings could not be restored", and the run
had restored both (the projection from run 42832549612, the ratings through
2026-11-09, blended in at 0.50); none of the 40 runs before it had failed
either. The sentences sat inside the steps' `run:` blocks, which GitHub
prints at the top of every step's log. They now live in
`scripts/season_sim_inputs.py` and reach a log only when they happen.

The same run warned that `roster_notes.json` named three players the stats
API did not know. Two were spelling: "Arvid Soderblom" and "Rémi Poirier"
were compared with the roster's spelling exactly, so an accent on either
side lost the start share. The third, Dylan Larkin, was in `out` (rostered
players missing games) while suspended off the roster with no birth date to
age him; he is under `returning` now, with one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from test_scripts import load_script

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from season_sim.model import _match_shares, _NameIndex  # noqa: E402


def _steps() -> dict[str, dict]:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "season-sim.yml").read_text("utf-8"))
    return {s["name"]: s for s in wf["jobs"]["simulate"]["steps"]}


def test_no_run_block_carries_a_warning_it_has_not_had() -> None:
    inputs = load_script("season_sim_inputs.py")
    for name, step in _steps().items():
        run = str(step.get("run", ""))
        assert inputs.PREVIOUS_MISSING not in run, name
        assert inputs.RATINGS_MISSING not in run, name
        assert "could not be restored" not in run, name
    steps = _steps()
    assert "season_sim_inputs.py previous" in steps["Restore the last projection"]["run"]
    assert "season_sim_inputs.py ratings" in steps["Restore the card's team ratings"]["run"]


def _fake_restore(payload: dict[str, bytes], ok: bool = True):
    calls: list[list[str]] = []

    def restore(args: list[str]) -> bool:
        calls.append(args)
        dest = Path(args[args.index("--dest") + 1])
        for rel, data in payload.items():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(data)
        return ok

    return restore, calls


def test_a_restored_projection_is_moved_and_not_warned_about(tmp_path, capsys) -> None:
    inputs = load_script("season_sim_inputs.py")
    restore, calls = _fake_restore({"season.json": b'{"season": "20262027"}'})
    assert inputs.restore_previous(tmp_path / "previous-season", restore=restore)
    out = capsys.readouterr().out
    assert "::warning::" not in out
    assert (tmp_path / "previous-season" / "season.json").read_bytes() == b'{"season": "20262027"}'
    # The same call the workflow made.
    assert calls[0][:2] == ["--artifact", "season-sim"]
    assert calls[0][4:] == ["--workflow", "season-sim.yml", "--success-only", "--no-merge",
                            "--attempts", "2", "--limit", "60"]


@pytest.mark.parametrize("payload,ok", [({}, False), ({}, True), ({"season.json": b""}, True)])
def test_a_missing_projection_is_warned_about(tmp_path, capsys, payload, ok) -> None:
    inputs = load_script("season_sim_inputs.py")
    restore, _ = _fake_restore(payload, ok)
    assert not inputs.restore_previous(tmp_path / "prev", restore=restore)
    assert f"::warning::{inputs.PREVIOUS_MISSING}" in capsys.readouterr().out
    assert not (tmp_path / "prev" / "season.json").exists()


def test_the_cards_ratings_are_taken_alone(tmp_path, capsys) -> None:
    inputs = load_script("season_sim_inputs.py")
    ratings = json.dumps({"last_game_date": "2026-11-09", "teams": {}}).encode()
    restore, calls = _fake_restore({"processed/shadow_team_ratings.json": ratings,
                                    "processed/other.csv": b"a\n1\n"})
    assert inputs.restore_ratings(tmp_path / "processed", restore=restore)
    out = capsys.readouterr().out
    assert "Card ratings through 2026-11-09" in out and "::warning::" not in out
    assert sorted(p.name for p in (tmp_path / "processed").iterdir()) == ["shadow_team_ratings.json"]
    assert calls[0][:2] == ["--artifact", "gameday-state"]
    assert calls[0][4:] == ["--workflow", "gameday-refresh.yml", "--no-merge", "--attempts", "2"]


@pytest.mark.parametrize("payload,ok", [
    ({}, False),
    ({"processed/other.csv": b"a\n"}, True),
    ({"processed/shadow_team_ratings.json": b"not json"}, True),
])
def test_missing_ratings_are_warned_about(tmp_path, capsys, payload, ok) -> None:
    inputs = load_script("season_sim_inputs.py")
    restore, _ = _fake_restore(payload, ok)
    assert not inputs.restore_ratings(tmp_path / "processed", restore=restore)
    assert f"::warning::{inputs.RATINGS_MISSING}" in capsys.readouterr().out
    assert not (tmp_path / "processed" / "shadow_team_ratings.json").exists()


def test_a_hand_typed_name_finds_the_nhls_spelling() -> None:
    index = _NameIndex([("Arvid Söderblom", 1), ("Rémi Poirier", 2), ("Dylan Larkin", 3)])
    assert index.get("Arvid Soderblom") == 1
    assert index.get("Remi Poirier") == 2
    assert index.get("Dylan Larkin") == 3
    assert index.get("Nobody Here") is None


def test_two_players_who_fold_to_one_name_are_never_guessed_between() -> None:
    index = _NameIndex([("Elias Pettersson", 1), ("Elias Pettersson", 2), ("Éric Côté", 5)])
    assert index.get("Elias Pettersson") == 2  # the exact name, as before
    assert index.get("ELIAS PETTERSSON") is None
    assert index.get("Eric Cote") == 5


def test_start_shares_follow_the_rosters_spelling() -> None:
    matched, missing = _match_shares(
        {"Spencer Knight": 0.65, "Arvid Soderblom": 0.35}, ["Spencer Knight", "Arvid Söderblom"]
    )
    assert matched == {"Spencer Knight": 0.65, "Arvid Söderblom": 0.35} and missing == []
    matched, missing = _match_shares(
        {"Jake Allen": 0.32, "Rémi Poirier": 0.08, "Not Rostered": 0.6},
        ["Jake Allen", "Remi Poirier"],
    )
    assert matched == {"Jake Allen": 0.32, "Remi Poirier": 0.08}
    assert missing == ["Not Rostered"]


def test_a_player_off_the_roster_is_listed_as_returning_with_a_birth_date() -> None:
    notes = json.loads((ROOT / "data" / "season_sim" / "roster_notes.json").read_text("utf-8"))
    assert "Dylan Larkin" not in [e["name"] for e in notes["out"]]
    larkin = [e for e in notes["returning"] if e["name"] == "Dylan Larkin"]
    assert len(larkin) == 1 and larkin[0]["born"] == "1996-07-30" and larkin[0]["team"] == "DET"
