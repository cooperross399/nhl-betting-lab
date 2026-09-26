"""Publish Site's reports never reached the site: `gh` refused to overwrite.

Publish Site restores with

    restore_state.py --artifact gameday-state --dest data \\
        --workflow gameday-refresh.yml --no-merge \\
        --also gameday-reports=data/outputs

`gameday-state` went through a temporary directory and was copied over
`data/`, putting `outputs/gameday_card.json` in place. `--also` then ran
`gh run download <run> --name gameday-reports --dir data/outputs` STRAIGHT
into a directory that already held that card and five committed reports
(props_calibration.md, player_props_backtest.md, team_markets_measurement.md,
what_we_can_claim.md, allowlist_evidence_bundle.md). `gh` creates every zip
entry with O_EXCL and stops at the first one that exists, so six of the
artifact's 13 entries collided and `forward_evidence.json`, entry 12, was
never extracted, in the listed order or alphabetical. restore_state.py
swallowed gh's stderr and logged "Run N carries no gameday-reports." — false:
the artifact was there — and exited 0. `web/build_site_json.py::load_record`
then found no file and published `wagers: None`, so the board's
"Forward ledger · sealed" chip read "Ledger size not reported" on every
build from opening night on, where it should say "No slate settled yet" and
later the ledger's size. Found by the failure-shape audit (3/3 refuters).
Replayed with the real gh 2.97.0 against a local fake API: exit 1,
`error extracting "gameday_card.json": ... file exists`, one file extracted;
the same artifact into an empty directory extracted all 13. Production logs
show the same line: Publish Site 36176147420 (2026-09-25) "Run 33142173149
carries no gameday-reports." while the API listed that artifact at 15,257
bytes, and the older direct-download step on 2026-09-24 logged `error
extracting "props_calibration.md"`.

The only test of `--also` passed on the defect because its fake `gh` did
`copytree(dirs_exist_ok=True)` into an empty directory — it overwrote where
gh refuses. The fake in tests/test_state_restores_from_the_run_that_carries_it.py
now extracts the way gh does, and the first test here holds it to that.

These tests run the Publish Site step itself, from the workflow file, under
bash -eo pipefail with that fake on PATH, and read the result through the
site's own `load_record`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.models.value import american_to_implied, profit_on_win
from test_state_restores_from_the_run_that_carries_it import (
    SCRIPT,
    _env,
    _run,
    _state,
)


WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
RESTORE_STEP = "Restore the lab's latest state and the site's history"
#: Committed under data/outputs AND listed in the gameday-reports upload, so
#: every Publish Site checkout already holds them when the reports arrive.
CHECKED_IN = (
    "props_calibration.md",
    "player_props_backtest.md",
    "team_markets_measurement.md",
    "what_we_can_claim.md",
    "allowlist_evidence_bundle.md",
)
CARD = '{"generated_for": "2026-10-09", "best_bets": [], "leans": [], "passes": []}'


def _reports_upload() -> list[str]:
    """The gameday-reports entries, relative to data/outputs, in listed order.

    upload-artifact@v4 zips its search paths in the order they are listed,
    and nothing sorts them, so this is the order gh extracts them in.
    """
    document = yaml.safe_load(
        (WORKFLOWS / "gameday-refresh.yml").read_text(encoding="utf-8")
    )
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            given = step.get("with") or {}
            if (str(step.get("uses", "")).startswith("actions/upload-artifact")
                    and given.get("name") == "gameday-reports"):
                entries = [
                    line.strip() for line in str(given["path"]).splitlines()
                    if line.strip() and not line.strip().startswith(("#", "!"))
                ]
                assert all(e.startswith("data/outputs/") for e in entries), entries
                return [e[len("data/outputs/"):] for e in entries]
    raise AssertionError("no gameday-reports upload in gameday-refresh.yml")


def _publish_step() -> str:
    document = yaml.safe_load(
        (WORKFLOWS / "publish-site.yml").read_text(encoding="utf-8")
    )
    steps = [s for job in document["jobs"].values() for s in job["steps"]
             if s.get("name") == RESTORE_STEP]
    assert len(steps) == 1, f"exactly one step named {RESTORE_STEP!r}"
    return steps[0]["run"]


def _ledger_row(player: str, book: str, odds: int) -> dict:
    """A settled ledger row, shaped as settlement writes it."""
    return {
        "snapshot_date": "2026-10-08", "commence_time": "2026-10-09T00:10:00Z",
        "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
        "market": "shots_on_goal", "player": player, "selection": "over",
        "line": 3.5, "american_odds": float(odds), "book": book,
        "model_probability": 0.62, "edge": 0.62 - american_to_implied(odds),
        "verdicts_in_force": "x", "settled_at": "2026-10-10T12:00:00+00:00",
        "outcome": "won", "actual": 5.0, "profit_units": profit_on_win(float(odds)),
    }


def _reports(root: Path) -> tuple[dict, int]:
    """The gameday-reports artifact as the run uploads it: every listed file,
    the forward report written by the lab's own writer. Returns the fake-gh
    artifact spec and the report's wager count."""
    root.mkdir(parents=True)
    order = _reports_upload()
    for name in order:
        (root / name).write_text(f"run 101's {name}\n", encoding="utf-8")
    (root / "gameday_card.json").write_text(CARD, encoding="utf-8")
    # Three wagers, each quoted by two books: six ledger rows.
    ledger = pd.DataFrame(
        [_ledger_row(p, b, o) for p in ("Auston Matthews", "Mitch Marner",
                                        "William Nylander")
         for b, o in (("BetMGM", -110), ("DraftKings", 120))],
        columns=list(fe.LEDGER_COLUMNS),
    )
    payload = fe.build_forward_report(ledger)
    fe.save_forward_report(payload, output_dir=root)
    assert payload["rows"] == 6 and payload["wagers"] == 3
    return {"root": str(root), "order": order}, payload["wagers"]


def _checkout(work: Path) -> None:
    """A Publish Site checkout: the committed reports sit in data/outputs."""
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "restore_state.py").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    outputs = work / "data" / "outputs"
    outputs.mkdir(parents=True)
    for name in CHECKED_IN:
        (outputs / name).write_text("as committed\n", encoding="utf-8")


def _run_step(tmp_path: Path, scenario: dict) -> tuple[Path, subprocess.CompletedProcess]:
    env = _env(tmp_path, scenario)
    env["PATH"] = (f"{tmp_path / 'bin'}:{Path(sys.executable).parent}:"
                   f"{os.environ.get('PATH', '')}")
    env["GH_TOKEN"] = "not-a-token"
    work = tmp_path / "work"
    _checkout(work)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _publish_step()],
        cwd=work, env=env, capture_output=True, text=True, timeout=120,
    )
    return work, result


def _scenario(tmp_path: Path, **extra: object) -> tuple[dict, dict, int]:
    state = _state(tmp_path / "state", boxscores=range(3), card=CARD)
    reports, wagers = _reports(tmp_path / "reports")
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(101, "success")]},
        "artifacts": {"101": {"gameday-state": str(state),
                              "gameday-reports": reports}},
        **extra,
    }
    return scenario, reports, wagers


def _load_record(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location(
        "_bsj_reports_restore", PROJECT_ROOT / "web" / "build_site_json.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_record(path)


def test_the_fake_gh_refuses_a_file_that_already_exists(tmp_path: Path) -> None:
    """The fixture must not supply what gh lacks. Into an empty directory
    every entry lands; into one that holds an entry, gh stops there, exits 1,
    leaves the existing file alone and writes nothing after it."""
    scenario, reports, _ = _scenario(tmp_path)
    env = _env(tmp_path, scenario)
    order = reports["order"]
    blocker = order.index("gameday_card.json")
    assert blocker < order.index("forward_evidence.json")

    empty = tmp_path / "empty"
    clean = subprocess.run(
        [str(tmp_path / "bin" / "gh"), "run", "download", "101", "--name",
         "gameday-reports", "--dir", str(empty)],
        env=env, capture_output=True, text=True,
    )
    full = tmp_path / "full"
    full.mkdir()
    (full / "gameday_card.json").write_text("already here", encoding="utf-8")
    refused = subprocess.run(
        [str(tmp_path / "bin" / "gh"), "run", "download", "101", "--name",
         "gameday-reports", "--dir", str(full)],
        env=env, capture_output=True, text=True,
    )

    assert clean.returncode == 0, clean.stderr
    assert sorted(p.name for p in empty.iterdir()) == sorted(order)
    assert refused.returncode == 1
    assert 'error extracting "gameday_card.json"' in refused.stderr
    assert "file exists" in refused.stderr
    assert (full / "gameday_card.json").read_text() == "already here"
    assert sorted(p.name for p in full.iterdir()) == sorted(order[: blocker + 1])


def test_the_publish_site_step_lands_the_forward_report(tmp_path: Path) -> None:
    """The one that failed on every Publish Site run: the state's card and
    the committed reports are already in data/outputs when the reports
    arrive. The forward report must land, and the site must read its size."""
    scenario, reports, wagers = _scenario(tmp_path)

    work, result = _run_step(tmp_path, scenario)
    landed = work / "data" / "outputs" / "forward_evidence.json"
    record = _load_record(landed)

    assert result.returncode == 0, result.stderr
    assert "carries no gameday-reports" not in result.stdout, result.stdout
    assert landed.is_file(), result.stdout
    assert landed.read_bytes() == (
        Path(reports["root"]) / "forward_evidence.json"
    ).read_bytes()
    assert record["forward"]["wagers"] == wagers == 3
    # The state came from the same run, and nothing else was disturbed.
    assert (work / "data" / "outputs" / "gameday_card.json").read_text() == CARD
    assert "Restored gameday-state from gameday-refresh.yml run 101" in result.stdout


def test_the_runs_reports_replace_the_checked_in_copies(tmp_path: Path) -> None:
    """"The state and the reports from one run": every file the reports
    artifact carries ends up as that run's copy, not the commit's."""
    scenario, reports, _ = _scenario(tmp_path)

    work, result = _run_step(tmp_path, scenario)
    outputs = work / "data" / "outputs"

    assert result.returncode == 0, result.stderr
    for name in reports["order"]:
        assert (outputs / name).read_bytes() == (
            Path(reports["root"]) / name
        ).read_bytes(), name
    for name in CHECKED_IN:
        assert (outputs / name).read_text() == f"run 101's {name}\n", name


def test_a_reports_download_that_fails_is_not_called_absent(tmp_path: Path) -> None:
    """A failure to download an artifact that exists is gh's error, printed
    as gh said it — never "carries no", which sends the reader looking for
    an upload that happened."""
    scenario, _, _ = _scenario(
        tmp_path,
        fail={"101:gameday-reports": "error extracting zip archive: unexpected EOF"},
    )

    work, result = _run_step(tmp_path, scenario)

    assert result.returncode == 0, result.stderr
    assert "carries no gameday-reports" not in result.stdout, result.stdout
    assert "::warning::" in result.stdout
    assert "unexpected EOF" in result.stdout
    assert not (work / "data" / "outputs" / "forward_evidence.json").exists()
    assert "Restored gameday-state from gameday-refresh.yml run 101" in result.stdout


def test_a_run_without_reports_still_says_it_carries_none(tmp_path: Path) -> None:
    """The one true "carries no": the run uploaded state and no reports, which
    gh reports as no artifact matching the name. Still exit 0, state kept."""
    state = _state(tmp_path / "state", boxscores=range(3), card=CARD)
    scenario = {
        "runs": {"gameday-refresh.yml": [_run(101, "failure")]},
        "artifacts": {"101": {"gameday-state": str(state)}},
    }

    work, result = _run_step(tmp_path, scenario)

    assert result.returncode == 0, result.stderr
    assert "Run 101 carries no gameday-reports" in result.stdout, result.stdout
    assert "::warning::" not in result.stdout
    assert (work / "data" / "outputs" / "gameday_card.json").read_text() == CARD

