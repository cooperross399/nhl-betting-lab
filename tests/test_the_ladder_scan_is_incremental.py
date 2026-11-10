"""The ladder scan reuses each unchanged day's counts, and writes what a full scan writes.

`scripts/run_ladder_coherence.py` rescanned every day file the private chain
holds on every Line Movement round: 6.4 to 15.9 minutes per round on
2026-11-09/10 over 43 day files, growing with the season (#447 raised the
job's timeout to 45 minutes to hold it). Since 2026-11-10, with `--cache-dir`,
it keeps each readable day's counts keyed on the day file's name, its content
hash and the detector's fingerprint, and reads only the days that are new or
changed.

Every registered output must be what the full scan produced: the depth per
capture day, the checkpoint window, the violations by class, every
denominator, `unreadable_captures`, and the `--fail-on-day` exit. These
tests hold that by computing the full scan the way the runner did before
the cache (one concatenation of every day, one `find_violations`), and by
comparing the runner's report and JSON with no cache, a cold cache and a warm
cache, byte for byte, across new days, a changed day, a damaged day and a
mixed-moment chain. The cache itself may hold counts and hashes only.

No test reads the real `data/` tree.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.ladder_coherence import LADDER_CLASSES, find_violations

from test_scripts import load_script


PLAYERS = ("Ann Ames", "Bo Bell", "Cy Cole")
BOOKS = ("BookOne", "BookTwo")
MARKETS = ("shots_on_goal", "points")


def _odds(probability: float) -> int:
    """An American price for a probability, clamped off the -100..+100 gap."""
    probability = min(max(probability, 0.05), 0.95)
    if probability >= 0.5:
        return int(round(-100 * probability / (1 - probability)))
    return int(round(100 * (1 - probability) / probability))


def _round_rows(day: str, hour: int, rng: random.Random) -> list[dict]:
    """One capture round: ladders that are often incoherent, of every class."""
    captured_at = f"{day}T{hour:02d}:00:00+00:00"
    rows: list[dict] = []
    for game in range(2):
        event = f"evt-{day}-{game}"
        for market in MARKETS:
            for player in PLAYERS:
                for book in BOOKS:
                    for line in (0.5, 1.5, 2.5, 3.5):
                        if rng.random() < 0.2:
                            continue  # a rung the book did not hang
                        fair = max(0.9 - 0.2 * line + rng.uniform(-0.15, 0.15), 0.06)
                        for side, p in (("over", fair), ("under", 1 - fair)):
                            if side == "under" and rng.random() < 0.25:
                                continue  # one-sided: priced, not de-viggable
                            rows.append({
                                "provider_event_id": event,
                                "market": market,
                                "player": player,
                                "book": book,
                                "line": line,
                                "selection": side,
                                "american_odds": _odds(p + 0.03),
                                "fetched_at": captured_at,
                                "captured_at": captured_at,
                            })
                    if rows and rng.random() < 0.3:  # an exact duplicate row
                        rows.append(dict(rows[-1]))
        # The bulk request's featured total, which is never a ladder rung.
        rows.append({
            "provider_event_id": event, "market": "total_goals", "player": "",
            "book": "BookOne", "line": 6.5, "selection": "over",
            "american_odds": -110, "fetched_at": f"{day}T{hour:02d}:00:07.123456+00:00",
            "captured_at": captured_at,
        })
    return rows


def _write_day(processed: Path, day: str, rounds: int, seed: int) -> Path:
    path = processed / "line_movement" / f"{day}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    rows = [row for index in range(rounds)
            for row in _round_rows(day, 14 + 2 * index, rng)]
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")
    return path


def _append_round(path: Path, hour: int, seed: int) -> None:
    rows = _round_rows(path.stem, hour, random.Random(seed))
    pd.DataFrame(rows).to_csv(path, mode="a", header=False, index=False,
                              lineterminator="\n")


def _full_scan_reference(module, processed: Path) -> dict:
    """The scan as the runner made it before the cache: every day at once."""
    unreadable: dict[str, str] = {}
    prices, files = module.load_captures(
        processed / module.MOVEMENT_DIRNAME, unreadable=unreadable
    )
    prices = module.with_ladder_moment(prices)
    found, scan = find_violations(
        prices[prices["line"].notna()].copy(), depth_by=module.CAPTURE_DAY
    )
    by_class = found["ladder_class"].value_counts().to_dict() if not found.empty else {}
    return {
        "captures": len(files),
        "ladders": scan.ladders,
        "ladders_with_two_rungs": scan.ladders_with_two_rungs,
        "ladders_with_two_lines": scan.ladders_with_two_lines,
        "comparable_pairs": scan.comparable_pairs,
        "duplicate_rows_collapsed": scan.duplicate_rows_collapsed,
        "violations": scan.violations,
        "by_class": {name: int(by_class.get(name, 0)) for name, _ in LADDER_CLASSES},
        "checkpoint_window": module.checkpoint_window(scan.depth_by, files),
        "ladders_with_two_rungs_by_day": dict(sorted(scan.depth_by.items())),
        "summary_line": scan.summary_line(),
        "unreadable": sorted(unreadable),
    }


def _run(module, processed: Path, outputs: Path, *extra: str) -> tuple[int, str, str, str]:
    code = module.main(["--processed-dir", str(processed),
                        "--output-dir", str(outputs), *extra])
    return (
        code,
        (outputs / "ladder_coherence.json").read_text("utf-8"),
        (outputs / "ladder_coherence.md").read_text("utf-8"),
        "",
    )


def _assert_matches_reference(module, processed: Path, json_text: str, md: str) -> None:
    reference = _full_scan_reference(module, processed)
    record = json.loads(json_text)
    for key, value in reference.items():
        if key in ("summary_line", "unreadable"):
            continue
        assert record[key] == value, key
    assert reference["summary_line"] in md
    assert sorted(e["name"] for e in record["unreadable_captures"]) == reference["unreadable"]


@pytest.fixture()
def module():
    return load_script("run_ladder_coherence.py")


def test_incremental_equals_full_across_a_growing_chain(module, tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    days = ["2026-10-01", "2026-10-09", "2026-10-15", "2026-10-16", "2026-11-09"]
    for seed, day in enumerate(days):
        _write_day(processed, day, rounds=3, seed=seed)

    def both(label: str, fail_on_day: str | None = None) -> tuple[int, str, str]:
        flags = ("--fail-on-day", fail_on_day) if fail_on_day else ()
        full = _run(module, processed, tmp_path / f"full-{label}", *flags)
        cached = _run(module, processed, tmp_path / f"cached-{label}", *flags,
                      "--cache-dir", str(cache))
        assert cached[:3] == full[:3], label  # exit, JSON and report, byte for byte
        _assert_matches_reference(module, processed, full[1], full[2])
        return full[:3]

    code, text, _ = both("cold")
    assert code == 0
    record = json.loads(text)
    assert record["violations"] > 0, "the fixture must exercise violations"
    assert sum(record["by_class"].values()) == record["violations"]
    assert len(record["ladders_with_two_rungs_by_day"]) == len(days)
    both("warm")

    # This round appends to today's file; a new day appears.
    _append_round(processed / "line_movement" / "2026-11-09.csv", hour=23, seed=99)
    _write_day(processed, "2026-11-10", rounds=1, seed=100)
    both("grown")

    # A damaged earlier day is named and warns; damage in this run's day fails it.
    (processed / "line_movement" / "2026-10-09.csv").write_bytes(b"")
    code, text, _ = both("damaged-earlier", fail_on_day="2026-11-10")
    assert code == 0
    assert [e["name"] for e in json.loads(text)["unreadable_captures"]] == ["2026-10-09.csv"]
    code, _, _ = both("damaged-today", fail_on_day="2026-10-09")
    assert code == 2

    # Repaired, the day is counted again.
    _write_day(processed, "2026-10-09", rounds=3, seed=1)
    both("repaired")


def test_a_warm_run_reads_only_the_new_or_changed_days(module, tmp_path, monkeypatch) -> None:
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    for seed, day in enumerate(["2026-10-01", "2026-10-02", "2026-10-03"]):
        _write_day(processed, day, rounds=2, seed=seed)
    _run(module, processed, tmp_path / "a", "--cache-dir", str(cache))

    read: list[str] = []
    original = module.read_day

    def counting(path: Path):
        read.append(path.name)
        return original(path)

    monkeypatch.setattr(module, "read_day", counting)
    _run(module, processed, tmp_path / "b", "--cache-dir", str(cache))
    assert read == []

    _append_round(processed / "line_movement" / "2026-10-03.csv", hour=22, seed=7)
    _write_day(processed, "2026-10-04", rounds=1, seed=8)
    _run(module, processed, tmp_path / "c", "--cache-dir", str(cache))
    assert read == ["2026-10-03.csv", "2026-10-04.csv"]


def test_a_damaged_day_is_read_every_run_and_never_cached(module, tmp_path, monkeypatch) -> None:
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    _write_day(processed, "2026-10-01", rounds=2, seed=1)
    bad = _write_day(processed, "2026-10-02", rounds=2, seed=2)
    raw = bad.read_bytes()
    index = raw.index(b"BookOne", raw.index(b"\n"))
    bad.write_bytes(raw[:index] + b"\xff" + raw[index + 1:])  # undecodable
    for label in ("cold", "warm"):
        code, text, _, _ = _run(module, processed, tmp_path / label,
                                "--cache-dir", str(cache))
        assert code == 2, label
        assert [e["name"] for e in json.loads(text)["unreadable_captures"]] == ["2026-10-02.csv"]
    cached = json.loads((cache / module.CACHE_FILENAME).read_text("utf-8"))
    assert sorted(cached["days"]) == ["2026-10-01.csv"]


def test_a_new_detector_fingerprint_rescans_every_day(module, tmp_path, monkeypatch) -> None:
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    _write_day(processed, "2026-10-01", rounds=2, seed=1)
    _run(module, processed, tmp_path / "a", "--cache-dir", str(cache))
    monkeypatch.setattr(module, "detector_fingerprint", lambda: "another detector")
    read: list[str] = []
    original = module.read_day
    monkeypatch.setattr(module, "read_day",
                        lambda path: (read.append(path.name), original(path))[1])
    _run(module, processed, tmp_path / "b", "--cache-dir", str(cache))
    assert read == ["2026-10-01.csv"]


def test_a_cached_count_is_never_trusted_over_a_changed_file(module, tmp_path) -> None:
    """Same name, same size, different bytes: the hash, not the name, decides."""
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    path = _write_day(processed, "2026-10-01", rounds=2, seed=1)
    _run(module, processed, tmp_path / "a", "--cache-dir", str(cache))
    frame = pd.read_csv(path)
    frame["american_odds"] = frame["american_odds"].iloc[::-1].to_numpy()
    frame.to_csv(path, index=False, lineterminator="\n")
    full = _run(module, processed, tmp_path / "full")
    cached = _run(module, processed, tmp_path / "b", "--cache-dir", str(cache))
    assert cached[:3] == full[:3]


def test_a_mixed_moment_chain_counts_as_the_concatenation_did(module, tmp_path) -> None:
    """One day carrying `snapshot`: the concatenated scan read every other
    day's moment as blank, and the incremental scan must agree."""
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    _write_day(processed, "2026-10-01", rounds=3, seed=1)
    other = _write_day(processed, "2026-10-02", rounds=2, seed=2)
    frame = pd.read_csv(other)
    frame["snapshot"] = frame["captured_at"]
    frame.to_csv(other, index=False, lineterminator="\n")
    full = _run(module, processed, tmp_path / "full")
    cold = _run(module, processed, tmp_path / "cold", "--cache-dir", str(cache))
    warm = _run(module, processed, tmp_path / "warm", "--cache-dir", str(cache))
    assert cold[:3] == full[:3] == warm[:3]
    _assert_matches_reference(module, processed, full[1], full[2])
    # Remove it, and the plain day's own moments come back, from the cache.
    other.unlink()
    full = _run(module, processed, tmp_path / "full2")
    warm = _run(module, processed, tmp_path / "warm2", "--cache-dir", str(cache))
    assert warm[:3] == full[:3]
    _assert_matches_reference(module, processed, full[1], full[2])


def test_the_cache_holds_counts_and_hashes_only(module, tmp_path) -> None:
    """It is kept in the Actions cache: no price, line, book, player or event."""
    processed = tmp_path / "processed"
    cache = tmp_path / "cache"
    _write_day(processed, "2026-10-01", rounds=2, seed=1)
    _run(module, processed, tmp_path / "a", "--cache-dir", str(cache))
    text = (cache / module.CACHE_FILENAME).read_text("utf-8")
    for leak in (*PLAYERS, *BOOKS, "evt-", "american_odds", "shots_on_goal", "captured_at"):
        assert leak not in text, leak

    def leaves(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from leaves(value)
        else:
            yield node

    payload = json.loads(text)
    for leaf in leaves(payload):
        assert isinstance(leaf, (int, bool, str)), leaf
        if isinstance(leaf, str):
            allowed = {*module.SCAN_COUNTS, "by_class", "depth_by", "counts",
                       "sha256", "empty", "has_snapshot", "days", "fingerprint",
                       "own_moment", "snapshot_elsewhere",
                       *(name for name, _ in LADDER_CLASSES)}
            assert (leaf in allowed or leaf.endswith(".csv")
                    or len(leaf) == 64 and all(c in "0123456789abcdef" for c in leaf)
                    or leaf == "2026-10-01"), leaf


def test_the_line_movement_step_keeps_the_cache_off_every_upload() -> None:
    """Restored and saved through the Actions cache under the runner's temp
    directory, which no upload may name; the scan is pointed at it."""
    import yaml

    from nhl_betting_lab.config import PROJECT_ROOT

    workflow = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
    steps = [step for job in yaml.safe_load(workflow.read_text("utf-8"))["jobs"].values()
             for step in job["steps"]]
    restore = [s for s in steps if str(s.get("uses", "")).startswith("actions/cache/restore")]
    save = [s for s in steps if str(s.get("uses", "")).startswith("actions/cache/save")]
    assert len(restore) == len(save) == 1
    for step in (*restore, *save):
        assert step["with"]["path"].strip() == "${{ runner.temp }}/ladder-scan-cache"
        assert step["with"]["key"].startswith("ladder-scan-")
    scan = next(s for s in steps if s.get("name") == "Scan the captured ladders")
    assert '--cache-dir "$RUNNER_TEMP/ladder-scan-cache"' in scan["run"]
    names = [s.get("name") for s in steps]
    assert names.index(restore[0]["name"]) < names.index(scan["name"]) < names.index(save[0]["name"])
    for step in steps:
        if "upload-artifact" in str(step.get("uses", "")):
            assert "ladder-scan-cache" not in str(step.get("with", {}).get("path", ""))
