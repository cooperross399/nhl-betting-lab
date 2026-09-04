"""The guard manifest: deleting a hard-rule guard must turn the build red.

Reproduced before this file existed: `git rm tests/test_no_secrets_committed.py
tests/test_no_sibling_lab_import.py` dropped every test in two files and the
suite stayed green — greener, by the pass count, because fewer tests were
failing and the same number were. pytest has no way to say so. A module that is
gone collects nothing, and nothing is not a failure.

Two mechanisms close that, and they are checked from opposite directions:

* this file asserts each module in `REQUIRED_GUARD_MODULES` is tracked by git
  and still DEFINES at least five test functions, read with `ast.parse` — so
  a guard edited down to a docstring, or one whose file survives with its
  tests removed, is a finding here;
* `tests/conftest.py::pytest_collection_modifyitems` refuses the session when
  any of those modules contributed zero COLLECTED items, which is what catches
  a rename, `--ignore`, `--deselect`, a `-k` that matches none of its tests, a
  positional path naming the others, and the same flags arriving through
  `PYTEST_ADDOPTS`. It exits the session rather than failing a test, so there
  is no test to deselect.

This module is in the manifest itself, so removing the manifest is caught by
the hook, and removing the hook is caught by
`test_the_collection_hook_is_observed_to_refuse_a_missing_guard`, which copies
the real conftest into a synthetic tree and runs pytest against it. That test
is an observation, not a reading: it asserts on the exit code of a subprocess.

What none of this reaches, said plainly: a root-level `conftest.py` or a
plugin loaded before `tests/conftest.py` could monkeypatch `pytest.exit` or
rewrite `REQUIRED_GUARD_MODULES` in place. `test_the_only_conftest_is_the_one_
under_tests` closes the tracked-file half of that; a plugin installed into the
venv is outside what a tracked-file scan can see, and `tests/test_workflows.py`
bans the `-p` flag and `--noconftest` on the required job for the same reason.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

from conftest import REQUIRED_GUARD_MODULES, guard_shortfall

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = PROJECT_ROOT / "tests" / "conftest.py"

#: Fewer than this and a "guard" is a file with the right name. Every module
#: in the manifest is well above it, so the floor catches a hollowing-out
#: rather than negotiating with the count.
MINIMUM_TESTS_PER_GUARD = 5


def _test_functions_in(path: Path) -> list[str]:
    """Every `test_*` function the module defines, at top level or in a class.

    Parsed rather than collected, so a module whose tests are still there but
    which pytest was told not to collect is still counted as defining them —
    the collection half is the hook's job. A module that does not parse is a
    failure that names the file, never a zero.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(
            f"{path.relative_to(PROJECT_ROOT)} does not parse ({exc.msg} at "
            f"line {exc.lineno}). A guard that cannot be imported enforces "
            "nothing, and pytest reports that as a collection error rather "
            "than as a failed guard."
        ) from exc
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                found.append(node.name)
    return found


#: The manifest, restated here so that dropping a guard from `conftest.py`
#: is a red test rather than a quiet narrowing. Editing both files is the
#: only way past this, and that edit is in the diff a reviewer reads.
EXPECTED_GUARDS = frozenset(
    {
        "tests/test_no_secrets_committed.py",
        "tests/test_no_sibling_lab_import.py",
        "tests/test_contract_strings.py",
        "tests/test_workflows.py",
        "tests/test_the_guards_exist.py",
    }
)


def test_the_manifest_is_not_empty_and_names_this_file() -> None:
    """A manifest with nothing in it protects nothing, and one that omits
    itself can be removed without anything noticing."""
    assert REQUIRED_GUARD_MODULES, "REQUIRED_GUARD_MODULES is empty"
    assert "tests/test_the_guards_exist.py" in REQUIRED_GUARD_MODULES
    assert len(set(REQUIRED_GUARD_MODULES)) == len(REQUIRED_GUARD_MODULES)
    assert set(REQUIRED_GUARD_MODULES) == EXPECTED_GUARDS, (
        sorted(EXPECTED_GUARDS ^ set(REQUIRED_GUARD_MODULES))
    )


@pytest.mark.parametrize("module", REQUIRED_GUARD_MODULES)
def test_every_required_guard_is_tracked_by_git(module: str) -> None:
    """Asked of git, not of the filesystem. A file that exists on disk but is
    untracked is one `git clean` away from not existing, and it is not what CI
    checks out."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", module],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"{module} is not tracked by git: {result.stderr.strip()}"
    )


@pytest.mark.parametrize("module", REQUIRED_GUARD_MODULES)
def test_every_required_guard_still_defines_enough_tests(module: str) -> None:
    path = PROJECT_ROOT / module

    assert path.is_file(), f"{module} is missing"
    names = _test_functions_in(path)
    assert len(names) >= MINIMUM_TESTS_PER_GUARD, (
        f"{module} defines {len(names)} test function(s); a guard with fewer "
        f"than {MINIMUM_TESTS_PER_GUARD} has been hollowed out: {names}"
    )


def test_the_shortfall_arithmetic_reports_an_absence() -> None:
    """The hook's counting, pointed at a synthetic list and shown to notice.

    Both directions: a list carrying one item from every required module has
    no shortfall, and dropping any single module's items names that module and
    only that module. Paths outside the root are ignored rather than counted.
    """
    complete = [PROJECT_ROOT / module for module in REQUIRED_GUARD_MODULES]

    assert guard_shortfall(complete, PROJECT_ROOT) == []
    for module in REQUIRED_GUARD_MODULES:
        without = [path for path in complete if path != PROJECT_ROOT / module]
        assert guard_shortfall(without, PROJECT_ROOT) == [module]
    assert guard_shortfall([], PROJECT_ROOT) == list(REQUIRED_GUARD_MODULES)
    elsewhere = [Path("/") / module for module in REQUIRED_GUARD_MODULES]
    assert guard_shortfall(elsewhere, PROJECT_ROOT) == list(REQUIRED_GUARD_MODULES)


def _synthetic_suite(root: Path, *, skipper: bool = False) -> None:
    """A tree with one trivial test per required module, and the REAL conftest.

    The conftest is copied byte for byte, so the observation below is of the
    code that runs in CI and not of a re-implementation of it.
    """
    tests = root / "tests"
    tests.mkdir()
    shutil.copy(CONFTEST, tests / "conftest.py")
    for module in REQUIRED_GUARD_MODULES:
        (root / module).write_text(
            "def test_present() -> None:\n    assert True\n", encoding="utf-8"
        )
    if skipper:
        (tests / "test_skipper.py").write_text(
            textwrap.dedent(
                """\
                import pytest


                def test_waits_on_data_that_never_arrives() -> None:
                    pytest.skip("no data in this checkout")
                """
            ),
            encoding="utf-8",
        )
    (root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8"
    )


def _run_pytest(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST")
    }
    environment["PYTHONPATH"] = str(root / "tests")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_collection_hook_is_observed_to_refuse_a_missing_guard(
    tmp_path: Path,
) -> None:
    """Run pytest, read the exit code. Five ways of losing a guard, one verdict.

    The control run — every required module present, nothing narrowed — has to
    exit 0, or the rejections below would be worth nothing.
    """
    _synthetic_suite(tmp_path)
    control = _run_pytest(tmp_path)

    assert control.returncode == 0, control.stdout + control.stderr

    first = REQUIRED_GUARD_MODULES[0]
    narrowings = {
        "-k": ["-k", "not test_present"],
        "--ignore": [f"--ignore={first}"],
        "--deselect": [f"--deselect={first}::test_present"],
        "positional": [REQUIRED_GUARD_MODULES[1]],
        "PYTEST_ADDOPTS": [],
    }
    for label, arguments in narrowings.items():
        if label == "PYTEST_ADDOPTS":
            environment = dict(os.environ, PYTEST_ADDOPTS=f"--ignore={first}")
            environment["PYTHONPATH"] = str(tmp_path / "tests")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                cwd=tmp_path,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
        else:
            result = _run_pytest(tmp_path, *arguments)
        assert result.returncode == 1, (label, result.stdout, result.stderr)
        assert "contributed zero collected tests" in result.stdout + result.stderr, (
            label,
            result.stdout,
            result.stderr,
        )

    # ...and a deleted file, which is the reproduction this module exists for.
    (tmp_path / first).unlink()
    deleted = _run_pytest(tmp_path)

    assert deleted.returncode == 1, deleted.stdout + deleted.stderr
    assert first in deleted.stdout + deleted.stderr


def test_the_skip_gate_is_observed_to_refuse_a_skipped_test(tmp_path: Path) -> None:
    """One skipping test in an otherwise green tree, and the run exits 1.

    `pytest -q` on its own exits 0 here and prints `1 skipped`. The session
    hook is what turns that into a non-zero exit, and it is asserted by running
    it rather than by reading it.
    """
    _synthetic_suite(tmp_path, skipper=True)
    result = _run_pytest(tmp_path)

    assert "1 skipped" in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout + result.stderr
    assert "did not pass and did not fail" in result.stdout + result.stderr
    assert "test_skipper.py::test_waits_on_data_that_never_arrives [skipped]" in result.stdout

    # ...and the control: the same tree without the skipper exits 0, so the
    # red above came from the skip and from nothing else.
    (tmp_path / "tests" / "test_skipper.py").unlink()
    control = _run_pytest(tmp_path)

    assert control.returncode == 0, control.stdout + control.stderr


def test_the_only_conftest_is_the_one_under_tests() -> None:
    """A second conftest.py — at the root, or deeper — loads before or beside
    this one and could neuter either hook. The tracked-file half of that is
    asserted; a plugin installed into the environment is outside it."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True
    )
    conftests = sorted(
        name
        for name in result.stdout.decode("utf-8").split("\0")
        if name.endswith("conftest.py")
    )

    assert conftests == ["tests/conftest.py"], conftests


def test_no_other_pytest_configuration_file_is_tracked() -> None:
    """`pytest.ini` outranks `pyproject.toml`, and `tox.ini` and `setup.cfg`
    are read when it is absent. Any of them can point `testpaths` at a tree
    that holds no conftest — a run that loads neither hook and reports green
    over a different suite — without touching a file this module reads."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True
    )
    tracked = set(result.stdout.decode("utf-8").split("\0"))

    assert not tracked & {"pytest.ini", "tox.ini", "setup.cfg", ".pytest.ini"}, (
        sorted(tracked & {"pytest.ini", "tox.ini", "setup.cfg", ".pytest.ini"})
    )


def test_pyproject_does_not_reconfigure_the_run() -> None:
    """`addopts` is a command line nobody sees, and `testpaths` decides what a
    bare `pytest` collects. Both are pinned so the workflow linter's reading of
    the command line is a reading of the whole invocation."""
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    options = config["tool"]["pytest"]["ini_options"]

    assert options.get("testpaths") == ["tests"]
    assert "addopts" not in options, options["addopts"]
    assert "confcutdir" not in options
    assert "norecursedirs" not in options
