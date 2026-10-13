"""The shadow models must never reach the card or the ledger.

The forward ledger is written from the card's probability map before any
gate (`tests/test_ladder_route_cannot_reach_the_ledger.py` explains why), and
the model the card runs is frozen until 2027-04-25. A shadow number that
reached that map would change the subject of the registered test without a
trace. So no module outside the shadow packages (`nhl_betting_lab.shadow`,
the modern stats, and `nhl_betting_lab.new_markets`, markets not on the
card), other than their runner scripts and the tests, may import either.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHADOW = PROJECT_ROOT / "src" / "nhl_betting_lab" / "shadow"
NEW_MARKETS = PROJECT_ROOT / "src" / "nhl_betting_lab" / "new_markets"
SHADOW_PACKAGES = (SHADOW, NEW_MARKETS)
SHADOW_MODULES = ("nhl_betting_lab.shadow", "nhl_betting_lab.new_markets")
ALLOWED = {
    PROJECT_ROOT / "scripts" / "run_shadow_stats.py",
    PROJECT_ROOT / "scripts" / "run_period_markets.py",
}


def _imports_shadow(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        if any(n == m or n.startswith(f"{m}.") for n in names for m in SHADOW_MODULES):
            return True
    return False


def _inside_a_shadow_package(path: Path) -> bool:
    return any(package in path.parents for package in SHADOW_PACKAGES)


def test_nothing_outside_the_shadow_package_imports_it() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for root in (PROJECT_ROOT / "src", PROJECT_ROOT / "scripts", PROJECT_ROOT / "web")
        if root.is_dir()
        for path in root.rglob("*.py")
        if not _inside_a_shadow_package(path) and path not in ALLOWED and _imports_shadow(path)
    ]
    assert offenders == []


def test_the_check_would_see_an_import(tmp_path: Path) -> None:
    sample = tmp_path / "card.py"
    sample.write_text("from nhl_betting_lab.shadow.xg import XgModel\n", encoding="utf-8")
    assert _imports_shadow(sample)
    sample.write_text("import nhl_betting_lab.shadow\n", encoding="utf-8")
    assert _imports_shadow(sample)


def test_the_check_would_see_a_new_markets_import(tmp_path: Path) -> None:
    sample = tmp_path / "card.py"
    sample.write_text("from nhl_betting_lab.new_markets import periods\n", encoding="utf-8")
    assert _imports_shadow(sample)
    sample.write_text("from nhl_betting_lab.new_markets.periods import walk_forward\n", encoding="utf-8")
    assert _imports_shadow(sample)
    sample.write_text("import nhl_betting_lab.new_marketsish\n", encoding="utf-8")
    assert not _imports_shadow(sample)


def test_the_shadow_package_exists_where_this_guard_looks() -> None:
    assert (SHADOW / "__init__.py").is_file()
    assert (NEW_MARKETS / "__init__.py").is_file()
