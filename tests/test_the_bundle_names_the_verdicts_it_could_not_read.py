"""The evidence bundle checksummed one set of files and read its verdicts from another.

Found by the failure-shape audit (silent empty reports). The bundle lists the
tracked `.md` reports as the reviewed evidence and checksums them, but every
verdict is read from a gitignored JSON beside them — player_props_backtest,
team_markets_measurement, replication — whose absence nothing reported. A
missing JSON became a finding instead of a gap:

* In a fresh checkout, with only the tracked reports, all 12 markets read
  "**not supported** — no price-based measurement exists", beside a
  checksummed `player_props_backtest.md` recording 9,379 `shots_on_goal` bets
  and a checksummed `team_markets_measurement.md` recording 954 moneyline
  bets. The recommendation named only the missing `.md` files.
* Gameday Refresh never runs `run_replication.py` and no artifact carries
  `replication.json`, while the tracked `replication.md` is in every checkout.
  So the bundle CI uploads — the one its own workflow calls the place every
  evidence file exists at once — listed `replication.md` as present, with its
  checksum, and said `points` and `blocked_shots` had "no replication record".

It fails closed (absence never made a market supported), so no verdict was
wrong in direction; the statements about the evidence were. Now a verdict
input that is missing or unreadable is named as such, per market and in the
recommendation, and "no replication record" is kept for a record that exists
and does not list the market. Tests drive the real bundle and its runner.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.reports import allowlist_evidence as ev

VERDICT_INPUTS = (
    "player_props_backtest.json",
    "team_markets_measurement.json",
    "replication.json",
)


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(directory: Path, name: str, payload: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def _tracked_reports_only(directory: Path) -> None:
    """What a fresh checkout holds: the reports, none of the JSONs."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in ev.EVIDENCE_FILENAMES:
        (directory / name).write_text(f"# {name}\n", encoding="utf-8")


def _ci_measurements(directory: Path) -> None:
    """What Gameday Refresh builds before the bundle: everything but replication."""
    _write(
        directory,
        "player_props_backtest.json",
        {
            "phase": "late",
            "by_market": {
                "points": {
                    "bets": 6194, "roi": -0.044, "includes_zero": False,
                    "survives_correction": True, "looks": 7,
                    "adjusted_low": -0.081, "adjusted_high": -0.007,
                },
                "blocked_shots": {
                    "bets": 4286, "roi": 0.049, "includes_zero": False,
                    "survives_correction": True, "looks": 7,
                    "adjusted_low": 0.008, "adjusted_high": 0.090,
                },
            },
        },
    )
    _write(
        directory,
        "team_markets_measurement.json",
        {"markets": [{"market": "moneyline", "bets": 954, "roi": -0.066,
                      "includes_zero": True, "survives_correction": False}]},
    )
    _write(
        directory,
        "props_calibration.json",
        {"markets": [{"market": "points", "samples": 370038}]},
    )


def _bundle(directory: Path) -> ev.EvidenceBundle:
    return ev.build_bundle(
        provider_name="the_odds_api",
        output_dir=directory,
        repository_root=directory,
    )


def _reason(bundle: ev.EvidenceBundle, market: str) -> str:
    return next(v for v in bundle.verdicts if v.market == market).reason


def test_the_tracked_reports_alone_do_not_read_as_no_measurement(
    tmp_path: Path,
) -> None:
    _tracked_reports_only(tmp_path)

    bundle = _bundle(tmp_path)

    assert bundle.missing_files == ()
    assert bundle.unread_inputs == VERDICT_INPUTS
    for verdict in bundle.verdicts:
        assert "no price-based measurement exists" not in verdict.reason, (
            verdict.market,
            verdict.reason,
        )
        assert "could not be read" in verdict.reason
        assert verdict.supported is False
    shots = _reason(bundle, "shots_on_goal")
    assert "`player_props_backtest.json` was not found" in shots
    assert "`player_props_backtest.md` is present" in shots
    assert "`team_markets_measurement.json` was not found" in _reason(
        bundle, "moneyline"
    )
    recommendation = bundle.recommendation()
    assert recommendation.startswith("**Enable nothing yet.**")
    assert all(name in recommendation for name in VERDICT_INPUTS)


def test_the_ci_bundle_does_not_invent_an_absent_replication_record(
    tmp_path: Path,
) -> None:
    """`replication.md` checksummed as present; `replication.json` never built."""
    _tracked_reports_only(tmp_path)
    _ci_measurements(tmp_path)

    bundle = _bundle(tmp_path)
    points = _reason(bundle, "points")
    blocked = _reason(bundle, "blocked_shots")

    assert bundle.unread_inputs == ("replication.json",)
    for reason in (points, blocked):
        assert "no replication record" not in reason
        assert "`replication.json` was not found" in reason
        assert "held-out verdict could not be read" in reason
    # Still the argument against, and still not a demonstrated deficit.
    assert "argues against enabling" in points
    assert "This is a demonstrated deficit" not in points
    assert bundle.supported_markets == ()
    assert "replication.json" in bundle.recommendation()
    assert "Enable nothing yet" in bundle.recommendation()


def test_a_present_record_without_the_market_is_still_no_record(
    tmp_path: Path,
) -> None:
    """The phrase survives where it is true, so the fix is not a rename."""
    _tracked_reports_only(tmp_path)
    _ci_measurements(tmp_path)
    _write(tmp_path, "replication.json", {"markets": []})

    bundle = _bundle(tmp_path)

    assert bundle.unread_inputs == ()
    assert "no replication record" in _reason(bundle, "points")
    assert "could not be read" not in _reason(bundle, "points")
    assert "supports enabling nothing" in bundle.recommendation()


def test_an_unreadable_verdict_input_is_named_as_unreadable(
    tmp_path: Path,
) -> None:
    """A truncated JSON is not an empty measurement."""
    _tracked_reports_only(tmp_path)
    _ci_measurements(tmp_path)
    _write(tmp_path, "replication.json", {"markets": []})
    (tmp_path / "team_markets_measurement.json").write_text(
        "{broken", encoding="utf-8"
    )

    bundle = _bundle(tmp_path)
    moneyline = _reason(bundle, "moneyline")

    assert bundle.unread_inputs == ("team_markets_measurement.json",)
    assert "no price-based measurement exists" not in moneyline
    assert "`team_markets_measurement.json`" in moneyline
    assert "could not be read" in moneyline


def test_the_runner_names_the_inputs_and_saves_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`run_allowlist_evidence.py` as Gameday Refresh runs it."""
    _tracked_reports_only(tmp_path)
    _ci_measurements(tmp_path)
    module = load_script("run_allowlist_evidence.py")

    code = module.main(["--output-dir", str(tmp_path)])
    out = capsys.readouterr().out
    payload = json.loads(
        (tmp_path / ev.BUNDLE_JSON_FILENAME).read_text(encoding="utf-8")
    )
    rendered = (tmp_path / ev.BUNDLE_MARKDOWN_FILENAME).read_text(encoding="utf-8")

    assert code == 0
    assert "Verdict inputs not found or unreadable: replication.json" in out
    assert payload["unread_inputs"] == ["replication.json"]
    assert "no replication record" not in rendered
