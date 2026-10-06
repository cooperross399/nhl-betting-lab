"""The modern-stats shadow model must never reach the card or the ledger.

The forward ledger is written from the card's probability map before any
gate (`tests/test_ladder_route_cannot_reach_the_ledger.py` explains why), and
the model the card runs is frozen until 2027-04-25. A shadow number that
reached that map would change the subject of the registered test without a
trace. So no module outside `nhl_betting_lab.shadow`, other than the shadow
runner script and the tests, may import it.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHADOW = PROJECT_ROOT / "src" / "nhl_betting_lab" / "shadow"
ALLOWED = {PROJECT_ROOT / "scripts" / "run_shadow_stats.py"}


def _imports_shadow(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            continue
        if any(n == "nhl_betting_lab.shadow" or n.startswith("nhl_betting_lab.shadow.") for n in names):
            return True
    return False


def test_nothing_outside_the_shadow_package_imports_it() -> None:
    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for root in (PROJECT_ROOT / "src", PROJECT_ROOT / "scripts", PROJECT_ROOT / "web")
        if root.is_dir()
        for path in root.rglob("*.py")
        if SHADOW not in path.parents and path not in ALLOWED and _imports_shadow(path)
    ]
    assert offenders == []


def test_the_check_would_see_an_import(tmp_path: Path) -> None:
    sample = tmp_path / "card.py"
    sample.write_text("from nhl_betting_lab.shadow.xg import XgModel\n", encoding="utf-8")
    assert _imports_shadow(sample)
    sample.write_text("import nhl_betting_lab.shadow\n", encoding="utf-8")
    assert _imports_shadow(sample)


def test_the_shadow_package_exists_where_this_guard_looks() -> None:
    assert (SHADOW / "__init__.py").is_file()
