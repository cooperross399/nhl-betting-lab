"""The correction experiment records the price window that decided it.

The props store holds two snapshot windows and
`scripts/run_correction_experiment.py` takes `--phase card|late|early`, but the
verdict it wrote — the file `verdicts.ships("by_toi")` reads and
`scripts/check_verdict_drift.py` compares — held only results, ships and
verdicts, and the markdown named no window (its "Window" column is the
season). A `--phase card` run and a `--phase late` run gave files that could
not be told apart, so a `by_toi` verdict re-decided on another window read in
the drift report as new evidence. Both rest experiments record `phase` and
`phase_hours`; this one now does too, as additive fields only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.verdicts import ships


def _script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(tn, "RAW_DIR", tmp_path / "default_raw")


#: The two snapshot windows the store holds: the card's own hour and the
#: originally bought T-4h, at different prices so the windows measure apart.
SNAPSHOTS = ((9.5, 140), (4.0, 125))


def _stores(tmp_path: Path) -> tuple[Path, Path]:
    processed, outputs = tmp_path / "processed", tmp_path / "outputs"
    processed.mkdir()
    outputs.mkdir()
    # This directory's own props_b2b verdict, so the samples' policy is
    # checked against a fixed decision rather than whatever is committed.
    (outputs / "props_rest_experiment.json").write_text(
        json.dumps({"ships": []}), encoding="utf-8"
    )
    (processed / "team_names.csv").write_text(
        "provider_name,abbrev\ntoronto maple leafs,TOR\nboston bruins,BOS\n"
        "tor,TOR\nbos,BOS\n",
        encoding="utf-8",
    )
    logs, samples, prices = [], [], []
    game_id = 100
    for start in ("2024-11-05", "2025-11-05"):
        for offset in range(35):
            day = pd.Timestamp(start) + pd.Timedelta(days=offset)
            face_off = day + pd.Timedelta(hours=23, minutes=30)
            commence = face_off.strftime("%Y-%m-%dT%H:%M:%SZ")
            for player_id, name, team, opponent, venue in (
                (7, "Ann A", "TOR", "BOS", "home"),
                (8, "Ben B", "BOS", "TOR", "away"),
            ):
                logs.append(
                    {"date": day.date().isoformat(), "game_id": game_id,
                     "player_id": player_id}
                )
                samples.append(
                    {"date": day.date().isoformat(), "game_id": game_id,
                     "player_id": player_id, "player": name, "team": team,
                     "opponent": opponent, "venue": venue,
                     "market": "shots_on_goal", "mean": 2.9,
                     "dispersion_r": float("nan"),
                     "actual": (offset * 3 + player_id) % 6,
                     "toi_seconds": 1200, "expected_toi_seconds": 1150.0,
                     "use_rest": False}
                )
                for hours, odds in SNAPSHOTS:
                    snapshot = (face_off - pd.Timedelta(hours=hours)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                    for selection in ("over", "under"):
                        prices.append(
                            {"date": commence[:10], "commence_time": commence,
                             "provider_event_id": f"g{game_id}",
                             "home_team": "Toronto Maple Leafs",
                             "away_team": "Boston Bruins",
                             "market": "shots_on_goal", "player": name,
                             "selection": selection, "line": 2.5,
                             "american_odds": odds, "book": "bk",
                             "snapshot": snapshot}
                        )
            game_id += 1
    pd.DataFrame(logs).to_csv(processed / "player_game_logs.csv", index=False)
    pd.DataFrame(prices).to_csv(
        processed / "historical_prop_prices.csv", index=False
    )
    pd.DataFrame(samples).to_csv(
        outputs / "prop_calibration_samples.csv", index=False
    )
    return processed, outputs


def _run(processed: Path, outputs: Path, phase: str) -> tuple[dict, str]:
    runner = _script("run_correction_experiment.py")
    code = runner.main(
        ["--phase", phase, "--processed-dir", str(processed),
         "--output-dir", str(outputs)]
    )
    assert code == 0
    payload = json.loads(
        (outputs / "correction_experiment.json").read_text(encoding="utf-8")
    )
    markdown = (outputs / "correction_experiment.md").read_text(encoding="utf-8")
    return payload, markdown


@pytest.mark.parametrize("phase,hours", [("card", 9.5), ("late", 4.0)])
def test_the_verdict_file_records_the_window(
    tmp_path: Path, phase: str, hours: float
) -> None:
    processed, outputs = _stores(tmp_path)
    payload, markdown = _run(processed, outputs, phase)
    assert payload["phase"] == phase
    assert payload["phase_hours"] == pytest.approx(hours, abs=0.01)
    # Each season is priced in the same window; the hours are kept per season
    # too, so a season whose median moved can be read on its own.
    assert set(payload["phase_hours_by_window"]) == set(payload["results"])
    for value in payload["phase_hours_by_window"].values():
        assert value == pytest.approx(hours, abs=0.01)
    assert (
        f"Priced in the `{phase}` window, median {hours:.1f} hours before "
        "face-off" in markdown
    ), markdown


def test_two_windows_give_files_that_can_be_told_apart(tmp_path: Path) -> None:
    processed, outputs = _stores(tmp_path)
    card, card_md = _run(processed, outputs, "card")
    late, late_md = _run(processed, outputs, "late")
    assert card["phase"] != late["phase"]
    assert "`card` window" in card_md and "`late` window" in late_md


def test_the_fields_are_additive_and_the_readers_still_read_it(
    tmp_path: Path,
) -> None:
    processed, outputs = _stores(tmp_path)
    payload, _ = _run(processed, outputs, "card")
    assert {"results", "ships", "verdicts"} <= set(payload)
    assert isinstance(payload["ships"], list)
    assert ships("by_toi", output_dir=outputs) == ("by_toi" in payload["ships"])
    drift = _script("check_verdict_drift.py")
    assert drift.ships_of(payload) == sorted(payload["ships"])
    # The results table is still seasons of variants: nothing new was put
    # where a reader iterates windows or variants.
    for season in payload["results"].values():
        assert set(season) == {"raw", "pooled", "by_toi"}
