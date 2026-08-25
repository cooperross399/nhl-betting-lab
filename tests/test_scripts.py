"""The command-line entry points, exercised the way a workflow runs them.

Every script here is invoked by a GitHub Actions step, which means a broken
one surfaces as a red run twenty minutes into a job rather than as a failing
test. The modules they call are tested thoroughly; the wiring between argument
parsing, missing data, and exit codes was not tested at all.

Each test runs the script offline, against a temporary directory, and asserts
on the exit code and the words the operator actually sees.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from nhl_betting_lab.config import PROJECT_ROOT


SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def load_script(name: str) -> ModuleType:
    """Import a script by path. They are entry points, not a package."""
    path = SCRIPTS_DIR / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ALL_SCRIPTS = sorted(path.name for path in SCRIPTS_DIR.glob("*.py"))


@pytest.mark.parametrize("name", ALL_SCRIPTS)
def test_every_script_imports_and_exposes_main(name: str) -> None:
    module = load_script(name)

    assert callable(module.main)


@pytest.mark.parametrize("name", ALL_SCRIPTS)
def test_every_script_accepts_help_without_side_effects(name: str) -> None:
    module = load_script(name)

    with pytest.raises(SystemExit) as exit_info:
        module.main(["--help"])

    assert exit_info.value.code == 0


# -- the card ----------------------------------------------------------


def test_the_card_script_blocks_and_exits_zero_with_no_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A blocked card is the correct outcome, not a failure."""
    module = load_script("run_gameday_card.py")

    code = module.main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
            "--now", "2026-10-08T18:00:00+00:00",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "No card" in out
    assert "no policy was edited" in out
    assert (tmp_path / "outputs" / "gameday_card.md").is_file()


def test_the_card_script_refuses_a_naive_now(tmp_path: Path) -> None:
    """The puck-drop guard compares aware instants; a naive one is a bug."""
    module = load_script("run_gameday_card.py")

    with pytest.raises(SystemExit) as exit_info:
        module.main(
            [
                "--staging-dir", str(tmp_path),
                "--processed-dir", str(tmp_path),
                "--output-dir", str(tmp_path),
                "--now", "2026-10-08T18:00:00",
            ]
        )

    assert exit_info.value.code != 0


def test_the_card_script_says_no_team_map_could_be_built(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    """Without it every game prices league-average against league-average."""
    module = load_script("run_gameday_card.py")
    monkeypatch.setattr(module, "build_team_name_map", lambda: {})

    module.main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
            "--now", "2026-10-08T18:00:00+00:00",
        ]
    )
    card = json.loads(
        (tmp_path / "outputs" / "gameday_card.json").read_text(encoding="utf-8")
    )

    assert any("team-name map" in item for item in card["blockers"])


# -- measurement -------------------------------------------------------


def test_the_backtest_script_reports_that_nothing_is_measured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script("run_player_props_backtest.py")

    code = module.main(
        [
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "nothing is measured" in out
    assert (tmp_path / "outputs" / "player_props_backtest.md").is_file()


def test_the_calibration_script_refuses_to_write_a_report_with_no_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report with no samples that looked like a report is worse than none."""
    module = load_script("run_props_calibration.py")

    code = module.main(
        [
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
        ]
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "No player logs" in out
    assert not (tmp_path / "outputs" / "props_calibration.md").exists()


def test_the_team_measurement_script_refuses_with_no_games(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script("run_team_markets_measurement.py")

    code = module.main(
        [
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
        ]
    )

    assert code == 1
    assert "No team games" in capsys.readouterr().out


def test_the_claims_script_writes_the_contract_path(tmp_path: Path) -> None:
    module = load_script("run_what_we_can_claim.py")

    code = module.main(["--output-dir", str(tmp_path)])

    assert code == 0
    assert (tmp_path / "what_we_can_claim.md").is_file()


def test_the_evidence_script_recommends_nothing_with_no_measurements(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script("run_allowlist_evidence.py")

    code = module.main(["--output-dir", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Enable nothing yet" in out
    assert "No receipt was written" in out


# -- gates and credentials ---------------------------------------------


def test_the_policy_gate_passes_on_the_shipped_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script("run_policy_pr_gate.py")

    code = module.main(["--output-dir", str(tmp_path)])

    assert code == 0
    assert "PASS" in capsys.readouterr().out


def test_the_credential_check_fails_loudly_without_a_key(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deliberately hard: without a key there is no fetch to degrade to."""
    module = load_script("check_provider_credential.py")
    monkeypatch.delenv("NHL_ODDS_API_KEY", raising=False)

    code = module.main(["--no-env-file"])

    assert code == 1
    assert "No credential" in capsys.readouterr().err


def test_the_credential_check_never_prints_the_value(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "test-secret-that-must-not-be-written"
    module = load_script("check_provider_credential.py")
    monkeypatch.setenv("NHL_ODDS_API_KEY", secret)

    code = module.main(["--no-env-file"])
    captured = capsys.readouterr()

    assert code == 0
    assert secret not in captured.out
    assert secret not in captured.err
    assert str(len(secret)) in captured.out


# -- the expensive one -------------------------------------------------


def test_a_live_purchase_without_a_cap_is_refused(tmp_path: Path) -> None:
    """An uncapped purchase is not a thing this script will do."""
    module = load_script("buy_historical_props.py")

    with pytest.raises(SystemExit) as exit_info:
        module.main(["--live", "--from", "2026-01-10", "--to", "2026-01-10"])

    assert exit_info.value.code != 0


def test_a_purchase_with_no_window_and_no_probe_is_refused() -> None:
    module = load_script("buy_historical_props.py")

    with pytest.raises(SystemExit):
        module.main([])


def test_a_dry_run_makes_no_paid_listing_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Listing a past window is itself billable, so a dry run must not."""
    module = load_script("buy_historical_props.py")

    code = module.main(
        [
            "--from", "2026-01-10",
            "--to", "2026-01-10",
            "--raw-dir", str(tmp_path),
            "--output-dir", str(tmp_path),
            "--processed-dir", str(tmp_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "does not make it" in out
    assert not any(tmp_path.rglob("*.json"))


# -- data --------------------------------------------------------------


def test_the_dataset_builder_runs_on_an_empty_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch
) -> None:
    module = load_script("build_datasets.py")
    monkeypatch.chdir(tmp_path)

    code = module.main(["--dry-run"])

    assert code == 0
    assert "Dry run" in capsys.readouterr().out


def test_the_shadow_script_exits_three_on_an_empty_slate(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 3 marks a state the caller must not treat as a failure."""
    from nhl_betting_lab.providers.odds_api import EmptySlateError

    module = load_script("run_provider_shadow.py")

    class NoSlate:
        def fetch_team_markets(self, **kwargs: object) -> object:
            raise EmptySlateError("nothing on the board")

    monkeypatch.setattr(module.odds_api, "OddsApiProvider", lambda: NoSlate())

    code = module.main(
        [
            "--live",
            "--staging-dir", str(tmp_path / "staging"),
            "--output-dir", str(tmp_path / "outputs"),
        ]
    )

    assert code == 3
    assert "No slate" in capsys.readouterr().out
