"""A replication run recorded "replicated" on no held-out data at all.

`scripts/run_replication.py` refused a window only when it was missing,
unreadable or measured no bets. It never compared the two windows, and
`reports.replication.compare` reads only `by_market`. So:

* the same file passed as both `--discovery` and `--test` exited 0 and wrote
  `replication.json` with every surviving market `replicated` ("`points` held
  on **player_props_backtest_2025-26** as well as
  **player_props_backtest_2025-26**"). A window compared with itself agrees
  with itself; nothing was held out;
* a `late`-phase payload (4.0 hours before face-off) as discovery and a
  `card`-phase payload (9.5 hours) as test also exited 0 with `points`
  replicated, and neither `replication.md` nor `replication.json` named
  either window. The lab treats a wager priced at two distances from
  face-off as two different questions, and the backtest's own auto-detect
  asks the operator to pick `--phase` per seasonal file, so mixing them is an
  easy slip that nothing caught.

`allowlist_evidence` reads `replicated` in `replication.json` as "a held-out
window confirmed it", and `what_we_can_claim` prints **Replicated**. Found by
sweep 4 (replication-accepts-non-held-out-windows, 2 of 2 verifiers).

What these tests hold, through the real script:

* the same path (or two paths to one file) as both windows is refused: exit
  1, nothing written, the previous record byte-identical;
* two files with the same measurement (a re-run of one window under another
  label differs only in `generated_at`) are refused the same way;
* windows whose `phase` differs, or where either payload names no phase, are
  refused, naming the phases;
* two held-out windows of one phase are still compared, and both phases and
  their hours before face-off are recorded in `replication.json` and
  `replication.md`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from test_scripts import load_script


def _payload(phase: str | None, roi: float, *, hours: float | None = None,
             generated_at: str = "2026-09-01T00:00:00+00:00") -> dict:
    entry = {
        "bets": 3000, "roi": roi, "low": roi - 0.02, "high": roi - 0.005,
        "includes_zero": False, "looks": 7, "adjusted_low": roi - 0.03,
        "adjusted_high": roi - 0.001, "survives_correction": True,
    }
    payload: dict = {
        "generated_at": generated_at,
        "bets": 3000,
        "by_market": {"points": entry},
    }
    if phase is not None:
        payload["phase"] = phase
        payload["phase_hours"] = (
            hours if hours is not None else (4.0 if phase == "late" else 9.5)
        )
    return payload


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


#: A replication record from an earlier, real run. A refusal must leave it.
PREVIOUS = {
    "replication.md": "# Replication\n\n- Discovery window: **2024-25**\n",
    "replication.json": '{"markets": [{"market": "points", "state": "untestable"}]}\n',
}


def _record_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "replication"
    directory.mkdir()
    for name, text in PREVIOUS.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _replicate(discovery: Path, test: Path, output_dir: Path) -> int:
    return load_script("run_replication.py").main(
        [
            "--discovery", str(discovery),
            "--test", str(test),
            "--output-dir", str(output_dir),
        ]
    )


def _refused(tmp_path: Path, capsys, discovery: Path, test: Path) -> str:
    records = _record_dir(tmp_path)
    before = _snapshot(records)
    capsys.readouterr()
    code = _replicate(discovery, test, records)
    out = capsys.readouterr().out
    assert code == 1, f"compared and exited {code}: {out}"
    assert "held on" not in out, out
    assert _snapshot(records) == before, (
        "the previous replication record was replaced by a comparison that "
        "held nothing out"
    )
    return out


def test_one_file_as_both_windows_is_refused(tmp_path: Path, capsys) -> None:
    window = _write(tmp_path / "player_props_backtest_2025-26.json",
                    _payload("late", -0.044))

    out = _refused(tmp_path, capsys, window, window)

    assert "same file" in out
    assert "held out" in out


def test_two_paths_to_one_file_are_one_file(tmp_path: Path, capsys) -> None:
    window = _write(tmp_path / "player_props_backtest_2025-26.json",
                    _payload("late", -0.044))
    (tmp_path / "sub").mkdir()
    dotted = tmp_path / "sub" / ".." / window.name
    linked = tmp_path / "linked.json"
    os.symlink(window, linked)

    records = _record_dir(tmp_path)
    before = _snapshot(records)
    for other in (dotted, linked):
        capsys.readouterr()
        assert _replicate(window, other, records) == 1, other
        assert "same file" in capsys.readouterr().out
    assert _snapshot(records) == before


def test_a_rerun_of_one_window_under_another_label_is_refused(
    tmp_path: Path, capsys
) -> None:
    """The backtest payload carries no label; two runs of one window differ
    only in `generated_at`. That is one measurement, not two windows."""
    first = _write(tmp_path / "player_props_backtest_2025-26.json",
                   _payload("late", -0.044))
    again = _write(
        tmp_path / "player_props_backtest_2024-25.json",
        _payload("late", -0.044, generated_at="2026-09-02T12:00:00+00:00"),
    )

    out = _refused(tmp_path, capsys, first, again)

    assert "same measurement" in out
    assert str(first) in out and str(again) in out


def test_windows_of_different_phases_are_refused(tmp_path: Path, capsys) -> None:
    late = _write(tmp_path / "a.json", _payload("late", -0.044))
    card = _write(tmp_path / "b.json", _payload("card", -0.042))

    out = _refused(tmp_path, capsys, late, card)

    assert "`late`" in out and "`card`" in out
    assert "phase" in out


@pytest.mark.parametrize("role", ["discovery", "test"])
@pytest.mark.parametrize("phase", [None, "", "   "])
def test_a_window_that_names_no_phase_is_refused(
    tmp_path: Path, capsys, role: str, phase: str | None
) -> None:
    named = _write(tmp_path / "named.json", _payload("late", -0.044))
    unnamed_payload = _payload("late", -0.042)
    if phase is None:
        del unnamed_payload["phase"]
    else:
        unnamed_payload["phase"] = phase
    unnamed = _write(tmp_path / "unnamed.json", unnamed_payload)

    if role == "discovery":
        out = _refused(tmp_path, capsys, unnamed, named)
    else:
        out = _refused(tmp_path, capsys, named, unnamed)

    assert str(unnamed) in out
    assert "name no snapshot window" in out


def test_two_held_out_windows_of_one_phase_are_compared_and_both_named(
    tmp_path: Path, capsys
) -> None:
    first = _write(tmp_path / "player_props_backtest_2024-25.json",
                   _payload("late", -0.044, hours=4.1))
    second = _write(tmp_path / "player_props_backtest_2025-26.json",
                    _payload("late", -0.042, hours=4.0))
    records = _record_dir(tmp_path)

    code = _replicate(first, second, records)

    assert code == 0, capsys.readouterr().out
    saved = json.loads((records / "replication.json").read_text(encoding="utf-8"))
    assert saved["replicated_markets"] == ["points"]
    assert saved["discovery_phase"] == "late"
    assert saved["test_phase"] == "late"
    assert saved["discovery_phase_hours"] == 4.1
    assert saved["test_phase_hours"] == 4.0
    markdown = (records / "replication.md").read_text(encoding="utf-8")
    assert "`late` window, 4.1 hours before face-off" in markdown
    assert "`late` window, 4.0 hours before face-off" in markdown
