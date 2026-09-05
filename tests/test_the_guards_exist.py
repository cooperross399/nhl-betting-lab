"""The guard manifest: deleting a hard-rule guard must turn the build red.

Reproduced before this file existed: `git rm tests/test_no_secrets_committed.py
tests/test_no_sibling_lab_import.py` dropped every test in two files and the
suite stayed green — greener, by the pass count, because fewer tests were
failing and the same number were. pytest has no way to say so. A module that is
gone collects nothing, and nothing is not a failure.

Four mechanisms close that, and they are checked from different directions:

* this file asserts each module in `REQUIRED_GUARD_MODULES` is tracked by git
  and still DEFINES at least five test functions, read with `ast.parse` — so
  a guard edited down to a docstring, or one whose file survives with its
  tests removed, is a finding here;
* `tests/conftest.py::pytest_configure` reads what pytest ACTUALLY RECEIVED —
  `--deselect`, `-k`, `-m`, `--ignore`, `--ignore-glob`, an ini `addopts`, a
  non-empty `PYTEST_ADDOPTS` — off `config`, and refuses the session. It is an
  observation rather than a spelling, which is why `PYTEST_ADD""OPTS=-x`
  reaches it: by the time it looks, the shell has joined the pieces;
* `tests/conftest.py::pytest_collection_modifyitems` refuses a session in
  which any required module contributed zero COLLECTED items, AND one in which
  any test function such a module defines on disk was not collected. The
  per-TEST arm is what a per-module floor cannot do: deselecting exactly one
  guard test left the count above zero and the whole suite green at
  1520 passed, 1 deselected — measured on this branch before the arm existed;
* this file refuses a tracked file whose basename is `pytest.py`,
  `coverage.py`, `sitecustomize.py` or `usercustomize.py`, or a tracked
  `pytest`/`coverage` package on any import root the workflow declares. A
  `coverage.py` at the repository root IS `python -m coverage`: a three-line
  one printing `1521 passed in 0.01s` was measured to satisfy the whole suite
  step. `tests/test_workflows.py` requires `PYTHONSAFEPATH: "1"` on that step
  for the untracked half of the same shape.

This module is in the manifest itself, so removing the manifest is caught by
the hook, and removing the hook is caught by
`test_the_collection_hook_is_observed_to_refuse_a_missing_guard`, which copies
the real conftest into a synthetic tree and runs pytest against it. That test
is an observation, not a reading: it asserts on the exit code of a subprocess.

What none of this reaches, said plainly. A plugin loaded before
`tests/conftest.py` — through `-p`, or installed into the environment as an
entry point — could monkeypatch `pytest.exit` or rewrite
`REQUIRED_GUARD_MODULES` in place; `tests/test_workflows.py` bans `-p` and
`--noconftest` on the required job, and the per-test floor makes a plugin that
merely removes items visible, but a plugin that disarms the hooks themselves is
outside what any test in this suite can see. `PYTHONSAFEPATH` keeps the working
directory off `sys.path`; it does not remove `PYTHONPATH: src`, so a
`src/sitecustomize.py` would still be imported before pytest — which is why
that name is refused at the tracked level here rather than left to the
variable. A guard hollowed to five `pass` bodies keeps its five names and its
five collected items and is caught by neither the count nor the floor.
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
import yaml

from conftest import (
    REQUIRED_GUARD_MODULES,
    defined_test_functions,
    guard_shortfall,
    guard_test_shortfall,
)

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


def _synthetic_suite(
    root: Path, *, skipper: bool = False, tests_per_guard: int = 1
) -> None:
    """A tree with `tests_per_guard` trivial tests per required module, and
    the REAL conftest.

    The conftest is copied byte for byte, so the observations below are of the
    code that runs in CI and not of a re-implementation of it. The second test
    exists for the per-TEST floor: with one test per module, losing a test and
    losing the module are the same event, and the floor being checked would
    not be distinguishable from the older per-module one.
    """
    tests = root / "tests"
    tests.mkdir()
    shutil.copy(CONFTEST, tests / "conftest.py")
    bodies = ["def test_present() -> None:\n    assert True\n"]
    if tests_per_guard > 1:
        bodies.append("\n\ndef test_second() -> None:\n    assert True\n")
    for module in REQUIRED_GUARD_MODULES:
        (root / module).write_text("".join(bodies), encoding="utf-8")
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
    #: label -> (arguments, PYTEST_ADDOPTS, the refusal that must appear).
    #: `-k`, `--ignore` and `--deselect` are refused by `pytest_configure`
    #: reading them back off `config` — earlier and for a better reason than
    #: the shortfall arithmetic, which only ever saw them by their effect. A
    #: positional path narrows without setting any option, so that one still
    #: comes out as a shortfall.
    narrowings = {
        "-k": (["-k", "not test_present"], None, "pytest received keyword="),
        "--ignore": ([f"--ignore={first}"], None, "pytest received ignore="),
        "--ignore-glob": (
            ["--ignore-glob=tests/test_no_*"],
            None,
            "pytest received ignore_glob=",
        ),
        "--deselect": (
            [f"--deselect={first}::test_present"],
            None,
            "pytest received deselect=",
        ),
        "-m": (["-m", "not slow"], None, "pytest received markexpr="),
        "positional": (
            [REQUIRED_GUARD_MODULES[1]],
            None,
            "contributed zero collected tests",
        ),
        "PYTEST_ADDOPTS": ([], f"--ignore={first}", "PYTEST_ADDOPTS="),
        # Assembled from pieces, which the workflow linter's token scan for
        # the name cannot see and this can: by the time `config` is built the
        # shell has already joined them.
        "PYTEST_ADDOPTS assembled": (
            [],
            "--dese" "lect " + f"{first}::test_present",
            "PYTEST_ADDOPTS=",
        ),
    }
    for label, (arguments, addopts, expected) in narrowings.items():
        if addopts is not None:
            environment = dict(os.environ, PYTEST_ADDOPTS=addopts)
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
        assert expected in result.stdout + result.stderr, (
            label,
            result.stdout,
            result.stderr,
        )

    # ...and a deleted file, which is the reproduction this module exists for.
    (tmp_path / first).unlink()
    deleted = _run_pytest(tmp_path)

    assert deleted.returncode == 1, deleted.stdout + deleted.stderr
    assert first in deleted.stdout + deleted.stderr


def test_an_addopts_in_the_ini_file_is_observed_to_refuse_the_session(
    tmp_path: Path,
) -> None:
    """`addopts` is a command line nobody types and nobody reads in review.

    `test_pyproject_does_not_reconfigure_the_run` asserts this repository's
    `pyproject.toml` carries none. This asserts the session would refuse to
    run if it did — read back off `config.inicfg`, so the value reaches the
    check however it was spelled.
    """
    _synthetic_suite(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
        f'addopts = "--deselect {REQUIRED_GUARD_MODULES[0]}::test_present"\n',
        encoding="utf-8",
    )
    result = _run_pytest(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "addopts in the ini file=" in result.stdout + result.stderr


def test_the_per_test_floor_is_observed_to_refuse_one_missing_guard_test(
    tmp_path: Path,
) -> None:
    """Deselecting exactly ONE test of a guard module leaves that module's
    collected count above zero, so the per-module floor sees nothing wrong.

    Driven here through a plugin rather than through `--deselect`, because
    `--deselect` is now refused before collection starts and would prove the
    wrong hook. A plugin is also the honest shape of the residual risk: it is
    what a `-p`, an installed entry point, or a second conftest would do.
    """
    _synthetic_suite(tmp_path, tests_per_guard=2)
    control = _run_pytest(tmp_path)

    assert control.returncode == 0, control.stdout + control.stderr

    target = REQUIRED_GUARD_MODULES[0]
    (tmp_path / "tests" / "thief.py").write_text(
        textwrap.dedent(
            f"""\
            def pytest_collection_modifyitems(items):
                for item in list(items):
                    if item.name == "test_second" and {target.split("/")[-1][:-3]!r} in str(item.path):
                        items.remove(item)
            """
        ),
        encoding="utf-8",
    )
    result = _run_pytest(tmp_path, "-p", "thief")

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{target}::test_second" in result.stdout + result.stderr
    assert "defined on disk but were not collected" in result.stdout + result.stderr


def test_the_shortfall_arithmetic_counts_tests_and_not_modules() -> None:
    """`guard_test_shortfall` pointed at a synthetic mapping, both ways.

    The names come from the real guard modules on disk, so this is also the
    assertion that those modules parse and define tests: an empty `defined`
    would make every case below vacuously true, and the first assertion would
    then be the one that fails.
    """
    defined = {
        module: defined_test_functions(PROJECT_ROOT / module)
        for module in REQUIRED_GUARD_MODULES
    }

    assert all(len(names) >= MINIMUM_TESTS_PER_GUARD for names in defined.values()), {
        module: len(names) for module, names in defined.items()
    }
    complete = {module: set(names) for module, names in defined.items()}
    assert guard_test_shortfall(complete, PROJECT_ROOT) == []
    for module, names in defined.items():
        one_short = {key: set(value) for key, value in complete.items()}
        dropped = sorted(names)[0]
        one_short[module].discard(dropped)
        assert guard_test_shortfall(one_short, PROJECT_ROOT) == [
            f"{module}::{dropped}"
        ]
    everything = guard_test_shortfall({}, PROJECT_ROOT)
    assert len(everything) == sum(len(names) for names in defined.values())


def test_the_collection_skip_gate_is_observed_to_refuse_a_module_level_skip(
    tmp_path: Path,
) -> None:
    """The shape `pytest_runtest_logreport` is structurally unable to see.

    A module-level `pytest.skip(allow_module_level=True)` and a module-level
    `pytest.importorskip` are both decided during collection: no test is set
    up, so no TestReport is ever produced, and the run-time hook alone was
    measured to exit 0 on this exact tree printing `2 skipped`. Both shapes
    are here because they are two different code paths in pytest, and both
    are the shape this suite actually shipped — a permanent skip standing in
    for a check on data CI does not have.
    """
    _synthetic_suite(tmp_path)
    (tmp_path / "tests" / "test_module_skip.py").write_text(
        textwrap.dedent(
            """\
            import pytest

            pytest.skip("no data in this checkout", allow_module_level=True)


            def test_never_runs() -> None:
                raise AssertionError("collection stopped before this")
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_import_skip.py").write_text(
        textwrap.dedent(
            """\
            import pytest

            pytest.importorskip("a_package_this_environment_does_not_have")


            def test_also_never_runs() -> None:
                raise AssertionError("collection stopped before this")
            """
        ),
        encoding="utf-8",
    )
    result = _run_pytest(tmp_path)

    assert "2 skipped" in result.stdout, result.stdout
    assert result.returncode == 1, result.stdout + result.stderr
    assert "did not pass and did not fail" in result.stdout + result.stderr
    for module in ("test_module_skip.py", "test_import_skip.py"):
        assert f"{module} [skipped at collection]" in result.stdout, result.stdout

    # ...and the control: the same tree without them exits 0.
    (tmp_path / "tests" / "test_module_skip.py").unlink()
    (tmp_path / "tests" / "test_import_skip.py").unlink()
    control = _run_pytest(tmp_path)

    assert control.returncode == 0, control.stdout + control.stderr


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


#: Basenames that would BE the suite. `python -m coverage run -m pytest -q`
#: resolves `coverage` against the working directory before site-packages, so a
#: `coverage.py` at the repository root is the tool the workflow launches:
#: measured in a clone of this branch, a three-line one printing
#: `1521 passed in 0.01s` and exiting 0 satisfied the whole step, and no test
#: in this suite saw it. `sitecustomize.py` and `usercustomize.py` are worse in
#: kind: Python imports them at interpreter start-up, before pytest and before
#: any conftest, so one on `PYTHONPATH` can set `PYTEST_ADDOPTS` for the run
#: that is about to happen — measured too, at `src/sitecustomize.py`, which
#: deselected a guard test and left the run green at 1520 passed.
SHADOWING_BASENAMES = frozenset(
    {"pytest.py", "coverage.py", "sitecustomize.py", "usercustomize.py"}
)

#: The same shadowing as a package rather than as a module.
SHADOWING_DIRECTORIES = frozenset({"pytest", "coverage"})


def _tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def _import_path_roots() -> list[str]:
    """The directories the required job puts on `PYTHONPATH`, plus the root.

    Read out of `.github/workflows/tests.yml` with `yaml.safe_load` and split
    on `:` the way Python splits it, so a second entry added to the workflow
    is covered without anyone remembering to add it here. The repository root
    is always in the list: it is the working directory, which `python -m` puts
    on `sys.path` first unless `PYTHONSAFEPATH` says otherwise.
    """
    document = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "tests.yml").read_text("utf-8")
    )
    roots = {""}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            environment = node.get("env")
            if isinstance(environment, dict):
                for key, value in environment.items():
                    if str(key).strip().upper() == "PYTHONPATH":
                        for entry in str(value).split(":"):
                            roots.add(entry.strip().strip("/"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return sorted(roots)


def test_no_tracked_file_shadows_the_tools_the_suite_line_launches() -> None:
    """No tracked file is named for pytest, coverage or a start-up hook.

    The workflow linter requires `PYTHONSAFEPATH: "1"` on the suite step,
    which keeps the working directory off `sys.path`. This is the other half,
    and it is the half that still holds on a laptop, where nobody exports
    that variable — and the half that covers `PYTHONPATH: src`, which
    `PYTHONSAFEPATH` does not touch: an explicit entry stays on the path, so
    `src/sitecustomize.py` would still run before pytest.

    Asked of git rather than of the filesystem: an untracked file is not what
    CI checks out, and a tracked one is.
    """
    tracked = _tracked_paths()

    assert tracked, "git ls-files returned nothing; this guard would be vacuous"
    shadows = sorted(
        name for name in tracked if Path(name).name in SHADOWING_BASENAMES
    )
    assert not shadows, (
        f"tracked files that shadow the suite: {shadows}. A `coverage.py` at "
        "the root IS `python -m coverage`; a `sitecustomize.py` on PYTHONPATH "
        "runs before pytest and can set PYTEST_ADDOPTS for it."
    )


def test_no_tracked_directory_shadows_those_tools_on_any_declared_import_root() -> None:
    """The package spelling of the same shadow, at every root the run has.

    The roots come from `env.PYTHONPATH` in `tests.yml`, split on `:`, plus
    the repository root itself. Reading them out of the workflow rather than
    hard-coding `src` means a second entry added there is covered here on the
    same commit.
    """
    roots = _import_path_roots()

    assert "src" in roots and "" in roots, roots
    tracked = _tracked_paths()
    assert tracked, "git ls-files returned nothing; this guard would be vacuous"
    offenders: list[str] = []
    for name in tracked:
        parts = Path(name).parts
        for root in roots:
            prefix = tuple(part for part in root.split("/") if part)
            if parts[: len(prefix)] != prefix:
                continue
            remainder = parts[len(prefix) :]
            if len(remainder) > 1 and remainder[0] in SHADOWING_DIRECTORIES:
                offenders.append(name)

    assert not offenders, (
        f"tracked packages that shadow the suite's tools: {sorted(set(offenders))} "
        f"on import roots {roots}."
    )


def test_the_shadow_scan_would_notice_one(tmp_path: Path) -> None:
    """The scan's own proof that it fires, since the repository is clean.

    Both arms are pointed at a synthetic tracked list: the module spelling at
    the root and under `src`, and the package spelling at both. A guard whose
    corpus is clean has never been watched fail, and this is the mutation
    that watches it.
    """
    roots = _import_path_roots()
    for name in ("coverage.py", "pytest.py", "src/sitecustomize.py", "a/b/pytest.py"):
        assert Path(name).name in SHADOWING_BASENAMES, name
    for clean in ("tests/test_coverage_report.py", "src/nhl_betting_lab/config.py"):
        assert Path(clean).name not in SHADOWING_BASENAMES, clean

    def package_offenders(tracked: list[str]) -> list[str]:
        found = []
        for name in tracked:
            parts = Path(name).parts
            for root in roots:
                prefix = tuple(part for part in root.split("/") if part)
                if parts[: len(prefix)] != prefix:
                    continue
                remainder = parts[len(prefix) :]
                if len(remainder) > 1 and remainder[0] in SHADOWING_DIRECTORIES:
                    found.append(name)
        return found

    assert package_offenders(["coverage/__init__.py"]) == ["coverage/__init__.py"]
    assert package_offenders(["src/pytest/__init__.py"]) == ["src/pytest/__init__.py"]
    assert package_offenders(["tests/coverage_helpers.py"]) == []
    assert package_offenders(["docs/coverage/notes.md"]) == []


def test_a_root_coverage_module_is_observed_to_be_the_suite(tmp_path: Path) -> None:
    """Why the two scans above exist, run rather than argued.

    A three-line `coverage.py` beside a real test tree: `python -m coverage
    run -m pytest -q` prints a pass count and exits 0 without importing
    pytest. Under `PYTHONSAFEPATH=1` the same command reaches the real tool
    and the real failing test. Both halves are asserted, because the claim
    being made in `tests.yml` is about that variable specifically.
    """
    (tmp_path / "coverage.py").write_text(
        "import sys\n\nprint('9999 passed in 0.01s')\nsys.exit(0)\n", encoding="utf-8"
    )
    (tmp_path / "test_truth.py").write_text(
        "def test_fails() -> None:\n    raise AssertionError('the suite ran')\n",
        encoding="utf-8",
    )
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("PYTEST")
    }
    environment.pop("PYTHONSAFEPATH", None)
    command = [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q",
               "-p", "no:cacheprovider"]
    shadowed = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True,
        timeout=120,
    )

    assert shadowed.returncode == 0, shadowed.stdout + shadowed.stderr
    assert "9999 passed" in shadowed.stdout, shadowed.stdout

    guarded = subprocess.run(
        command,
        cwd=tmp_path,
        env=dict(environment, PYTHONSAFEPATH="1"),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert guarded.returncode != 0, guarded.stdout + guarded.stderr
    assert "the suite ran" in guarded.stdout + guarded.stderr


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


def test_the_gaps_these_guards_still_have_are_the_ones_written_down(
    tmp_path: Path,
) -> None:
    """What still gets through, run rather than asserted in prose.

    Each item below was tried against the guards in this file and in
    `tests/conftest.py` after they were written, and each still gets through.
    They are executed here so that closing one turns this test red and the
    sentence gets rewritten rather than outliving the fix.

    1. A guard test DELETED from its file is invisible to the per-TEST floor.
       The floor compares what the module defines on disk against what the run
       collected; delete the definition and the two agree. What catches that is
       `MINIMUM_TESTS_PER_GUARD`, and only once the count falls below five — so
       a guard of fifty tests can lose forty-five quietly.
    2. A plugin implementing `pytest_load_initial_conftests` can clear the
       narrowing options and the environment variable before this conftest is
       ever loaded, and `pytest_configure` then sees a clean session. The same
       plugin written as `pytest_configure` LOSES that race and is refused —
       tried, and it is — so it is this one hook that is the gap. `-p` and
       `--noconftest` are banned on the required job by
       `tests/test_workflows.py`; an entry point installed into the environment
       is not, and is outside what a tracked-file scan can see.
    3. A `collect_ignore` in a conftest silently drops a module that is not in
       the manifest. Only the five listed guards have a floor.
    4. `PYTHONSAFEPATH` is set on the CI suite step, not on a laptop. The
       shadowing basenames are refused at the tracked level for exactly that
       reason, but an UNTRACKED `coverage.py` in a working copy still shadows a
       local `python -m coverage run -m pytest -q`.
    """
    # 1. deletion is invisible to the floor, and the count is what is left.
    _synthetic_suite(tmp_path, tests_per_guard=2)
    target = PROJECT_ROOT / REQUIRED_GUARD_MODULES[0]
    shrunk = {
        module: set(defined_test_functions(PROJECT_ROOT / module))
        for module in REQUIRED_GUARD_MODULES
    }
    assert guard_test_shortfall(shrunk, PROJECT_ROOT) == []
    assert len(defined_test_functions(target)) > MINIMUM_TESTS_PER_GUARD, (
        "the floor is the only thing left when a definition is deleted"
    )

    # 2. a plugin that clears the options BEFORE the conftest loads is not
    #    seen. The same plugin written as `pytest_configure` loses the race and
    #    is refused — tried, and it is; `pytest_load_initial_conftests` runs
    #    first, which is what makes this shape the gap and the other one not.
    (tmp_path / "tests" / "blinder.py").write_text(
        textwrap.dedent(
            """\
            import os


            def pytest_load_initial_conftests(early_config, parser, args):
                os.environ.pop("PYTEST_ADDOPTS", None)
                early_config.option.deselect = None
            """
        ),
        encoding="utf-8",
    )
    environment = dict(os.environ, PYTEST_ADDOPTS="-x")
    environment["PYTHONPATH"] = str(tmp_path / "tests")
    blinded = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "-p", "blinder",
        ],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=120,
    )
    assert blinded.returncode == 0, blinded.stdout + blinded.stderr
    (tmp_path / "tests" / "blinder.py").unlink()

    # 3. a module outside the manifest can be dropped without a word.
    (tmp_path / "tests" / "test_not_in_the_manifest.py").write_text(
        "def test_unprotected() -> None:\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "conftest.py").write_text(
        (tmp_path / "tests" / "conftest.py").read_text(encoding="utf-8")
        + '\n\ncollect_ignore = ["test_not_in_the_manifest.py"]\n',
        encoding="utf-8",
    )
    dropped = _run_pytest(tmp_path)
    assert dropped.returncode == 0, dropped.stdout + dropped.stderr
    assert "test_unprotected" not in dropped.stdout

    # 4. the shadow is closed by a variable the workflow sets, not by Python.
    assert "PYTHONSAFEPATH" not in os.environ or os.environ["PYTHONSAFEPATH"] != "1", (
        "this assertion describes a local run; if CI ever runs the suite with "
        "PYTHONSAFEPATH set, say so here instead of leaving the claim"
    )
