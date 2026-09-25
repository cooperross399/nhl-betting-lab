"""A scratch --output-dir priced with every shipped policy off.

`verdicts.ships(policy, output_dir=O)` read the verdict from `O` alone and
counted a missing file as "ships nothing". The card, the props calibration
and the team measurement all pass their `--output-dir`, and the verdicts
are tracked files that live in data/outputs only. So any run pointed at a
scratch output directory priced with every shipped policy withdrawn. That
includes every safe reproduction of a past card, because the default
directory would overwrite the real card and freeze into the real archive.
Such a run logged "Recorded policy verdicts: by_toi=off, props_b2b=off,
team_b2b=off" and froze that line into its snapshot. What the repository
records is "by_toi=off, props_b2b=in force, team_b2b=in force".

Found by the failure-shape audit (confirmed by three of three refuters).
Reproduced with the real card on copies of the real tables for the six games
of 2025-03-02, with the history a live run held that morning:
- the scratch run priced Pittsburgh (at home, the night after playing) at
  0.4370, against 0.4141 with the recorded verdicts in force;
- the scratch run moved every one of the six home moneylines;
- the card fell from 3 best bets and 1.25 units to 2 and 0.5.
A refuter's run on 2026-03-15 moved 5,111 of 6,147 prices and took the card
from 26 best bets / 9.25 units to 23 / 8.

The fix keeps #123: a verdict recorded IN the run's --output-dir still
governs that run, in both directions, so the card and the measurement given
the same directory describe the same policy. Where that directory records
no verdict for a policy, the recorded one in data/outputs applies. A file
that is there but unreadable still ships nothing, because the directory
records something and it cannot be read.

What these tests hold, with the recorded directory planted in a tmp dir
holding the shipped verdicts:

* a directory holding no verdict reads the recorded ones, for `ships` and
  for `describe`;
* a verdict in the directory still governs, both ways;
* an unreadable or malformed verdict in the directory ships nothing;
* the card run into a scratch directory logs, freezes and prices with the
  recorded verdicts. Its price equals the run whose directory holds copies
  of them, and differs from the run whose directory withdraws the team
  adjustment, so the fixture can tell the two apart;
* the props calibration and the team measurement given a scratch directory
  generate their samples under the recorded policy.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config, verdicts
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import TEAM_GAME_COLUMNS, TEAM_GAMES_FILENAME
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn


#: What the repository records today, as the three tracked files say it.
SHIPPED = {"by_toi": [], "team_b2b": ["team_b2b"], "props_b2b": ["props_b2b"]}
SHIPPED_LINE = "by_toi=off, props_b2b=in force, team_b2b=in force"


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(directory: Path, policy: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / verdicts.VERDICT_FILES[policy]
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The recorded verdicts, as data/outputs holds them, in a tmp dir."""
    directory = tmp_path / "recorded"
    for policy, ships in SHIPPED.items():
        _write(directory, policy, json.dumps({"ships": ships}))
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", directory)
    return directory


@pytest.mark.parametrize("exists", [True, False])
def test_a_directory_that_records_no_verdict_reads_the_recorded_ones(
    tmp_path: Path, recorded: Path, exists: bool
) -> None:
    scratch = tmp_path / "scratch"
    if exists:
        scratch.mkdir()

    assert verdicts.ships("team_b2b", output_dir=scratch) is True
    assert verdicts.ships("props_b2b", output_dir=scratch) is True
    assert verdicts.ships("by_toi", output_dir=scratch) is False
    assert verdicts.describe(output_dir=scratch) == SHIPPED_LINE
    assert verdicts.describe() == SHIPPED_LINE


def test_a_verdict_in_the_directory_still_governs_it_both_ways(
    tmp_path: Path, recorded: Path
) -> None:
    """What #123 established: a what-if run that re-decided a policy into its
    own directory is priced and measured by that decision."""
    scratch = tmp_path / "scratch"
    _write(scratch, "team_b2b", json.dumps({"ships": []}))
    _write(scratch, "by_toi", json.dumps({"ships": ["by_toi"]}))

    assert verdicts.ships("team_b2b", output_dir=scratch) is False
    assert verdicts.ships("by_toi", output_dir=scratch) is True
    # The one it holds nothing for is still the recorded one.
    assert verdicts.ships("props_b2b", output_dir=scratch) is True
    assert verdicts.describe(output_dir=scratch) == (
        "by_toi=in force, props_b2b=in force, team_b2b=off"
    )


@pytest.mark.parametrize("body", ["{broken", json.dumps({"ships": True}), "[]"])
def test_an_unreadable_verdict_in_the_directory_ships_nothing(
    tmp_path: Path, recorded: Path, body: str
) -> None:
    """The directory records something for the policy and it cannot be read,
    which is not the same as recording nothing: the conservative reading
    holds, and the recorded verdict does not paper over it."""
    scratch = tmp_path / "scratch"
    _write(scratch, "props_b2b", body)

    assert verdicts.ships("props_b2b", output_dir=scratch) is False


# --------------------------------------------------------------------------
# Through the card.
# --------------------------------------------------------------------------

TEAMS = {
    "TOR": ("Toronto", "Maple Leafs"),
    "BOS": ("Boston", "Bruins"),
    "MTL": ("Montréal", "Canadiens"),
    "OTT": ("Ottawa", "Senators"),
}


def _team_games() -> tuple[pd.DataFrame, date]:
    """Forty four-night cycles in which a road side on its second night in a
    row loses 5-1 and a rested one draws, so the fitted back-to-back factors
    sit well away from 1. History ends with Toronto on the road; the slate
    is the next night, Montréal hosting Toronto."""
    rows: list[dict] = []
    start = date(2025, 10, 1)
    cycle_games = (
        (0, "TOR", "OTT", 3, 2),
        (1, "BOS", "TOR", 5, 1),
        (1, "MTL", "OTT", 5, 1),
        (3, "TOR", "MTL", 3, 3),
        (3, "OTT", "BOS", 2, 3),
    )
    for cycle in range(40):
        for offset, home, away, home_goals, away_goals in cycle_games:
            rows.append((start + timedelta(days=4 * cycle + offset), home, away,
                         home_goals, away_goals))
    last = start + timedelta(days=4 * 40)
    rows.append((last, "TOR", "OTT", 3, 2))
    rows.append((last + timedelta(days=1), "BOS", "TOR", 5, 1))
    frame = pd.DataFrame(
        [
            {"game_id": index, "season": 20252026, "game_type": 2,
             "date": day.isoformat(), "start_time_utc": f"{day.isoformat()}T23:00:00Z",
             "home_team": home, "away_team": away, "home_goals": home_goals,
             "away_goals": away_goals, "home_shots": 30, "away_shots": 28,
             "regulation": True}
            for index, (day, home, away, home_goals, away_goals) in enumerate(rows)
        ],
        columns=list(TEAM_GAME_COLUMNS),
    )
    return frame, last + timedelta(days=2)


@pytest.fixture
def card_inputs(
    tmp_path: Path, recorded: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str]:
    """A default raw cache holding the four clubs' boxscores (so the team map
    builds on its own), the processed team games, and the slate."""
    raw = tmp_path / "default_raw"
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True)
    for game_id, (home, away) in enumerate((("TOR", "BOS"), ("MTL", "OTT"))):
        payload = boxscore_payload(game_id=game_id, game_state="OFF")
        for side, abbrev in (("homeTeam", home), ("awayTeam", away)):
            place, common = TEAMS[abbrev]
            payload[side].update(abbrev=abbrev, placeName={"default": place},
                                 commonName={"default": common})
        (directory / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")

    processed = tmp_path / "processed"
    processed.mkdir()
    games, slate_day = _team_games()
    games.to_csv(processed / TEAM_GAMES_FILENAME, index=False)
    staging = tmp_path / "staging"
    staging.mkdir()
    day = slate_day.isoformat()
    pd.DataFrame(
        [
            {"date": day, "commence_time": f"{day}T23:00:00Z",
             "provider_event_id": "evt1", "home_team": "Montréal Canadiens",
             "away_team": "Toronto Maple Leafs", "market": "moneyline",
             "player": "", "selection": selection, "line": "",
             "american_odds": -110, "book": "DraftKings",
             "fetched_at": f"{day}T11:00:00Z"}
            for selection in ("home", "away")
        ],
        columns=list(odds_api.PRICE_COLUMNS),
    ).to_csv(staging / odds_api.STAGING_PRICES_FILENAME, index=False)
    return staging, processed, f"{day}T15:00:00+00:00"


def _card(
    card_inputs: tuple[Path, Path, str],
    outputs: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[str, pd.DataFrame]:
    staging, processed, now = card_inputs
    load_script("run_gameday_card.py").main(
        ["--staging-dir", str(staging), "--processed-dir", str(processed),
         "--output-dir", str(outputs), "--now", now]
    )
    out = capsys.readouterr().out
    (snapshot,) = sorted(outputs.rglob("priced_snapshots/*.csv"))
    return out, pd.read_csv(snapshot)


def _home(snapshot: pd.DataFrame) -> float:
    row = snapshot[snapshot["selection"] == "home"]
    assert len(row) == 1, snapshot
    return float(row["model_probability"].iloc[0])


def test_the_card_in_a_scratch_directory_prices_the_recorded_policy(
    tmp_path: Path,
    recorded: Path,
    card_inputs: tuple[Path, Path, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    scratch_out, scratch = _card(card_inputs, tmp_path / "scratch", capsys)

    copies = tmp_path / "copies"
    copies.mkdir()
    for path in recorded.glob("*.json"):
        shutil.copy(path, copies / path.name)
    _, copied = _card(card_inputs, copies, capsys)

    withdrawn = tmp_path / "withdrawn"
    _write(withdrawn, "team_b2b", json.dumps({"ships": []}))
    withdrawn_out, rested = _card(card_inputs, withdrawn, capsys)

    assert f"Recorded policy verdicts: {SHIPPED_LINE}." in scratch_out
    assert set(scratch["verdicts_in_force"]) == {SHIPPED_LINE}
    assert _home(scratch) == _home(copied), (
        "the scratch run did not price with the recorded back-to-back policy"
    )
    # The fixture can tell the policies apart, and the directory's own
    # verdict still governs its run.
    assert _home(rested) < _home(scratch)
    assert set(rested["verdicts_in_force"]) == {
        "by_toi=off, props_b2b=in force, team_b2b=off"
    }
    # And the run says where each verdict came from.
    for policy, filename in verdicts.VERDICT_FILES.items():
        assert f"{policy} {recorded / filename}" in scratch_out
    assert f"team_b2b {withdrawn / verdicts.VERDICT_FILES['team_b2b']}" in withdrawn_out


# --------------------------------------------------------------------------
# Through the two sample generators that read a verdict.
# --------------------------------------------------------------------------


class _Generated(Exception):
    """Stops the runner once it has decided the policy, which is all that is
    under test here."""


@pytest.mark.parametrize(
    ("script", "loader", "generator", "policy"),
    [
        ("run_props_calibration.py", "load_player_logs", "generate_prop_samples", "props_b2b"),
        ("run_team_markets_measurement.py", "load_team_games", "generate_team_samples", "team_b2b"),
    ],
)
@pytest.mark.parametrize(("withdrawn_in_scratch", "expected"), [(False, True), (True, False)])
def test_the_sample_generators_use_the_recorded_policy_in_a_scratch_dir(
    tmp_path: Path,
    recorded: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    script: str,
    loader: str,
    generator: str,
    policy: str,
    withdrawn_in_scratch: bool,
    expected: bool,
) -> None:
    scratch = tmp_path / "scratch"
    if withdrawn_in_scratch:
        _write(scratch, policy, json.dumps({"ships": []}))
    module = load_script(script)
    monkeypatch.setattr(module, loader, lambda _dir: pd.DataFrame({"game_id": [1]}))
    used: list[bool] = []

    def generate(_frame, **kwargs):
        used.append(kwargs["use_rest"])
        raise _Generated

    monkeypatch.setattr(module, generator, generate)

    with pytest.raises(_Generated):
        module.main(
            ["--processed-dir", str(tmp_path / "processed"),
             "--output-dir", str(scratch)]
        )
    capsys.readouterr()

    assert used == [expected]
