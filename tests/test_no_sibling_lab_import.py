"""This lab may not reach into a sibling lab, and nothing was checking.

There are five betting labs in this account — NFL, NCAAF, NHL, EPL and college
basketball — one per sport, and they deliberately share no code. Machinery moves
between them by being **ported**: copied into the repository that uses it, where
it is visible and free to diverge as the sport demands.

That was a promise in a docstring until it was broken. The NCAAF lab's venv was
copied from the NFL lab's to save a few minutes of setup, and that installed
`football_betting_lab` into it as an editable package pointing at the sibling
repository. No line of code had to be written for the two labs to be coupled:
any module could have imported it and it would simply have worked, with no
error and no warning, through a path nobody reads.

Two things are asserted, because either alone is insufficient:

* no module here imports a sibling lab — catches a line someone writes;
* no sibling lab is importable from this environment — catches the environment
  making it possible in the first place.

The second is the one that actually bit. A test that only read source would have
passed all day.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: The other four labs. Named individually rather than derived, so a copied
#: venv from ANY of them fails the same way rather than only the one that
#: happened to cause this.
SIBLING_PACKAGES = ("cbb_betting_lab", "epl_betting_lab", "football_betting_lab", "ncaaf_betting_lab",)


def _python_files() -> list[Path]:
    keep: list[Path] = []
    for root in (PROJECT_ROOT / "src", PROJECT_ROOT / "scripts", PROJECT_ROOT / "tests"):
        if root.is_dir():
            keep.extend(
                p for p in root.rglob("*.py")
                if ".venv" not in p.parts and p.name != Path(__file__).name
            )
    return keep


def test_the_corpus_this_guard_reads_is_not_empty() -> None:
    """A guard over zero files passes by having read nothing.

    `_python_files` globs three directories and silently returns fewer when one
    is renamed or moved. Every rule below is a loop over that list, so an empty
    list is a green tick over a repository that was never scanned — absence is
    never a pass. Each directory is asserted separately so the failure names
    the one that went missing.
    """
    for name in ("src", "scripts", "tests"):
        assert (PROJECT_ROOT / name).is_dir(), f"{name}/ is missing"
        assert any(
            name in path.relative_to(PROJECT_ROOT).parts[:1]
            for path in _python_files()
        ), f"no Python file collected under {name}/"


def _sibling_imports(paths: list[Path], root: Path) -> tuple[list[str], list[str]]:
    """(modules importing a sibling, modules that could not be parsed).

    Corpus-as-argument so the regression tests below can run this exact code
    over a synthetic tree instead of asserting about it from a distance.
    """
    offenders: list[str] = []
    unparseable: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            # A module this guard cannot parse is a module it cannot clear.
            # It used to `continue` here, so a file with a syntax error — or
            # one deliberately made unparseable — sat outside the scan and was
            # reported as clean. Named and failed instead.
            unparseable.append(f"{relative}:{exc.lineno}")
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in SIBLING_PACKAGES:
                    offenders.append(f"{relative}:{node.lineno}: imports {name}")
    return offenders, unparseable


def test_no_module_imports_a_sibling_lab() -> None:
    offenders, unparseable = _sibling_imports(_python_files(), PROJECT_ROOT)

    assert not unparseable, (
        "These modules do not parse, so this guard could not read their "
        "imports. An unparseable module is a failure, not an exemption:\n  "
        + "\n  ".join(unparseable)
    )
    assert not offenders, (
        "This lab imports a sibling lab. Machinery is shared by PORTING it "
        "here, visibly, never by coupling two repositories:\n  "
        + "\n  ".join(offenders)
    )


def test_an_unparseable_module_is_reported_rather_than_skipped(tmp_path: Path) -> None:
    """Reproduction: `except SyntaxError: continue` made an unparseable file
    invisible to this guard, so a module that also imported a sibling — or
    that had simply been broken — was reported as clean. Both halves on a
    synthetic tree: the broken file is named, and a sibling import in a file
    that does parse is still found beside it."""
    broken = tmp_path / "broken.py"
    broken.write_text("def half(:\n    pass\n", encoding="utf-8")
    coupled = tmp_path / "coupled.py"
    coupled.write_text(
        "import os\nfrom epl_betting_lab.models import thing\n", encoding="utf-8"
    )
    clean = tmp_path / "clean.py"
    clean.write_text("import nhl_betting_lab\n", encoding="utf-8")

    offenders, unparseable = _sibling_imports([broken, coupled, clean], tmp_path)

    assert unparseable == ["broken.py:1"]
    assert offenders == ["coupled.py:2: imports epl_betting_lab.models"]


@pytest.mark.parametrize("package", SIBLING_PACKAGES)
def test_no_sibling_lab_is_even_importable(package: str) -> None:
    """The environment half, and the one that actually bit."""
    assert importlib.util.find_spec(package) is None, (
        f"{package} is importable from this environment. A copied venv or a "
        "stray editable install couples two labs through a path nobody reads. "
        f"Uninstall it: `.venv/bin/python -m pip uninstall "
        f"{package.replace('_', '-')}`."
    )


def test_this_lab_s_own_package_is_importable() -> None:
    """The positive control. A guard that passes because nothing is installed
    is not a guard, it is a broken environment."""
    assert importlib.util.find_spec("nhl_betting_lab") is not None
