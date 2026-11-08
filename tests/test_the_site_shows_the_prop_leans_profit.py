"""The Props tab and the Results strip show the prop leans' season record
and profit at 0.25u a lean, read from the graded record (prop_leans.json),
not from the nightly boards, which carry no leans since 2026-10-09
(Cooper, 2026-11-08: "The website isnt showing the prop lean
record/profit")."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_t_{name}", WEB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_season_line_carries_the_record_and_the_profit():
    b = _load("build_site_json")
    leans = {"nights": 39, "season": {"w": 1204, "l": 1503, "p": 0, "void": 33, "pending": 0,
                                       "unmatched": 35, "units": -6.53, "staked": 760.1}}
    line = b.lean_season_line(leans)
    assert line == {"w": 1204, "l": 1503, "p": 0, "void": 33, "units": -6.53, "staked": 760.1,
                    "nights": 39, "stake": 0.25}


def test_no_record_built_leaves_the_line_alone():
    b = _load("build_site_json")
    assert b.lean_season_line(None) is None
    assert b.lean_season_line({"note": "could not be read", "season": None}) is None


def test_the_published_pages_print_the_leans_profit():
    s = _load("smooth_pages")
    board = s.patch("Board.dc.html", (WEB / "Board.dc.html").read_text(encoding="utf-8"))
    assert "units: un(R.propLeans.units), unitsColor: col(R.propLeans.units)" in board
    assert 'tag: "no stake", record: rec(R.propLeans), units: ""' not in board
    results = s.patch("Results.dc.html", (WEB / "Results.dc.html").read_text(encoding="utf-8"))
    assert "u at 0.25u a lean" in results
