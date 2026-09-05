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
  guard test left the count above zero and the whole suite green — measured on
  this branch before the arm existed;
* this file refuses a tracked file whose basename is `pytest.py`,
  `coverage.py`, `sitecustomize.py` or `usercustomize.py` at any depth, and a
  tracked top-level name at any import root the workflow declares that
  collides with a module `tests.yml` launches, a start-up hook, or a stdlib
  top-level name. A `coverage.py` at the repository root IS `python -m
  coverage`: a three-line one printing a fabricated pass count was measured to
  satisfy the whole suite step, and a `pyflakes.py` did the same to the lint
  step while the suite stayed green. `tests/test_workflows.py` requires
  `PYTHONSAFEPATH: "1"` in effect on every step of the required job that
  starts an interpreter, which is the untracked half of the same shape and
  holds only where something sets that variable.

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
directory off `sys.path`; it does not remove `PYTHONPATH: src`, so an
UNTRACKED `src/coverage.py` is still imported before the real tool — measured
with the variable set, exit 0 and a fabricated pass line — and the tracked
half of that route is what the root-scoped scan here refuses. A guard hollowed
to five `pass` bodies keeps its five names and its five collected items and is
caught by neither the count nor the floor.
"""

from __future__ import annotations

import ast
import os
import re
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


#: Basenames that would BE the suite wherever git tracks them. `python -m
#: coverage run -m pytest -q` resolves `coverage` against the working directory
#: before site-packages, so a `coverage.py` at the repository root is the tool
#: the workflow launches: measured in a clone of this branch, a three-line one
#: printing a pass count and exiting 0 satisfied the whole step, and no test in
#: this suite saw it. `sitecustomize.py` and `usercustomize.py` are worse in
#: kind: Python imports them at interpreter start-up, before pytest and before
#: any conftest, so one on ANY `sys.path` entry can set `PYTEST_ADDOPTS` for
#: the run that is about to happen — measured too, at `src/sitecustomize.py`,
#: which deselected a guard test and left the run green.
#:
#: This set is refused at any tracked depth, which is wider than the import
#: rules require: `docs/notes/pytest.py` shadows nothing. The width is
#: deliberate for these four names and these four only. Everything else is
#: scoped to an actual import root by the rule below.
SHADOWING_BASENAMES = frozenset(
    {"pytest.py", "coverage.py", "sitecustomize.py", "usercustomize.py"}
)

#: Imported by the interpreter itself, before the command line is looked at.
#: They appear in no `python -m` line, so they cannot be read off the workflow.
STARTUP_HOOK_MODULES = frozenset({"sitecustomize", "usercustomize"})

#: `-m <name>` on a line that names an interpreter. Read as two pieces rather
#: than as one `python\s+-m\s+(\w+)` pattern because `python -m coverage run
#: -m pytest -q` launches BOTH, and the second `-m` has `run` in front of it,
#: not `python` — a single-pattern first draft matched `coverage` alone and
#: left `pytest.py` unrefused, which the scan's own proof caught.
INTERPRETER_ON_THE_LINE = re.compile(r"\bpython[0-9.]*\b")
LAUNCHED_MODULE = re.compile(r"(?:^|\s)-m\s+([A-Za-z_][A-Za-z0-9_]*)")


def _tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, check=True
    )
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def _workflow_document() -> object:
    return yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "tests.yml").read_text("utf-8")
    )


def _import_path_roots() -> list[str]:
    """The directories the required job puts on `PYTHONPATH`, plus the root.

    Read out of `.github/workflows/tests.yml` with `yaml.safe_load` and split
    on `:` the way Python splits it, so a second entry added to the workflow
    is covered without anyone remembering to add it here. The repository root
    is always in the list: it is the working directory, which `python -m` puts
    on `sys.path` first unless `PYTHONSAFEPATH` says otherwise.
    """
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

    walk(_workflow_document())
    return sorted(roots)


def _modules_the_workflow_launches() -> frozenset[str]:
    """Every module name `tests.yml` hands to `python -m`, read off the file.

    Hard-coding the list would go stale the day a step is added. Reading it
    means a new tool in the workflow is covered on the same commit that adds
    it — and a tool REMOVED from the workflow stops being refused, which is
    the right direction: the name matters because the job launches it.
    """
    launched: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            block = node.get("run")
            if isinstance(block, str):
                for line in block.replace("\\\n", " ").splitlines():
                    if INTERPRETER_ON_THE_LINE.search(line):
                        launched.update(LAUNCHED_MODULE.findall(line))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(_workflow_document())
    return frozenset(launched)


def _shadowable_module_names() -> frozenset[str]:
    """What a tracked top-level name at an import root must not be called.

    Three sources, none of them a hand-written list of four:

    * every module `tests.yml` launches with `python -m` — `pip`, `pyflakes`,
      `compileall`, `coverage`, `pytest` as the workflow stands;
    * the two start-up hooks, which no command line mentions;
    * `sys.stdlib_module_names`, because those tools import the standard
      library: a shadow of `struct` or `token` reaches `compileall` just as a
      shadow of `compileall` does.
    """
    return (
        frozenset(sys.stdlib_module_names)
        | _modules_the_workflow_launches()
        | STARTUP_HOOK_MODULES
    )


def _top_level_importables(
    tracked: list[str], roots: list[str]
) -> list[tuple[str, str, str]]:
    """`(root, tracked path, module name)` for every top-level import a root has.

    A path only shadows from a root it sits directly under: `src/coverage.py`
    is `coverage` when `src` is on the path, while `src/nhl_betting_lab/types.py`
    is `nhl_betting_lab.types` from that same root and shadows nothing. A
    DIRECTORY is listed whether or not it holds `__init__.py`: without one it
    is a namespace package, which loses to site-packages today and wins the
    moment somebody adds the file.
    """
    found: list[tuple[str, str, str]] = []
    for name in tracked:
        parts = Path(name).parts
        for root in roots:
            prefix = tuple(part for part in root.split("/") if part)
            if parts[: len(prefix)] != prefix:
                continue
            remainder = parts[len(prefix) :]
            if not remainder:
                continue
            head = remainder[0]
            if len(remainder) == 1:
                if head.endswith(".py"):
                    found.append((root, name, head[:-3]))
            else:
                found.append((root, name, head))
    return found


def test_no_tracked_file_shadows_the_tools_the_suite_line_launches() -> None:
    """No tracked file is named for pytest, coverage or a start-up hook.

    What this covers: the four basenames above, at any tracked depth. What it
    does not cover is every other shadowing name — that is the root-scoped
    rule below, and the two together are what the workflow's `env:` comment
    points at.

    Neither reaches a file git does not track. `PYTHONSAFEPATH: "1"` on the CI
    job keeps the working directory off `sys.path` there, which is the
    untracked half on the runner and only on the runner: on a laptop nobody
    exports it, and it never removes an explicit `PYTHONPATH` entry on either.
    That residue is executed, not asserted in prose, in
    `test_the_gaps_these_guards_still_have_are_the_ones_written_down`.

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


def test_no_tracked_name_shadows_a_launched_or_stdlib_module_at_an_import_root() -> None:
    """The general shape: a tracked top-level name at a root the job declares.

    Covered: every module `tests.yml` hands to `python -m`, the two start-up
    hooks, and every name in `sys.stdlib_module_names` — as a `.py` file or as
    a directory — at the top of the repository root or of any `PYTHONPATH`
    entry the workflow sets. Both lists are read at run time, the roots off
    `env.PYTHONPATH` and the tools off the `run:` blocks, so a step added to
    the workflow is covered by this test on the same commit that adds it.

    Not covered, said plainly: a name nested inside a package, which is an
    attribute of that package rather than a top-level module; a root nothing
    in `tests.yml` declares; and any file git does not track.

    This is the rule that was missing when the suite stayed green with a
    tracked `pyflakes.py` at the repository root — measured on this branch
    before the rule existed, with the lint step's own module holding an unused
    import and an undefined name.
    """
    roots = _import_path_roots()
    assert "src" in roots and "" in roots, roots
    launched = _modules_the_workflow_launches()
    assert {"pip", "pyflakes", "compileall", "coverage", "pytest"} <= launched, (
        "tests.yml no longer launches the tools this rule was written for: "
        f"{sorted(launched)}"
    )
    tracked = _tracked_paths()
    assert tracked, "git ls-files returned nothing; this guard would be vacuous"

    forbidden = _shadowable_module_names()
    offenders = sorted(
        {
            (root, name, module)
            for root, name, module in _top_level_importables(tracked, roots)
            if module in forbidden
        }
    )

    assert not offenders, (
        f"tracked names that shadow a module the required job needs: {offenders}. "
        f"Import roots read from tests.yml: {roots}."
    )


def test_the_shadow_scan_would_notice_one() -> None:
    """The scan's own proof that it fires, since the repository is clean.

    A guard whose corpus is clean has never been watched fail. The names below
    were run against a real interpreter first: a `pyflakes.py` in the working
    directory made `python -m pyflakes src scripts tests` print one clean line
    and exit 0 over a module holding an unused import and an undefined name,
    and a `pyflakes/` package with an `__main__.py` did the same. Both
    spellings are here, at both roots.
    """
    roots = _import_path_roots()
    forbidden = _shadowable_module_names()

    def offenders(tracked: list[str]) -> list[str]:
        return [
            name
            for _, name, module in _top_level_importables(tracked, roots)
            if module in forbidden
        ]

    for shadow in (
        "coverage.py",
        "pytest.py",
        "pyflakes.py",
        "compileall.py",
        "pip.py",
        "src/sitecustomize.py",
        "src/struct.py",
        "pyflakes/__init__.py",
        "compileall/__main__.py",
        "src/coverage/__init__.py",
    ):
        assert offenders([shadow]) == [shadow], shadow

    for clean in (
        "tests/test_coverage_report.py",
        "src/nhl_betting_lab/config.py",
        "src/nhl_betting_lab/types.py",
        "docs/coverage/notes.md",
        "scripts/pytest_helpers.py",
    ):
        assert offenders([clean]) == [], clean

    for named in ("coverage.py", "pytest.py", "src/sitecustomize.py", "a/b/pytest.py"):
        assert Path(named).name in SHADOWING_BASENAMES, named
    for clean in ("tests/test_coverage_report.py", "src/nhl_betting_lab/config.py"):
        assert Path(clean).name not in SHADOWING_BASENAMES, clean


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
    4. `PYTHONSAFEPATH` is set on the CI job, not on a laptop. The shadowing
       names are refused at the tracked level for exactly that reason, but an
       UNTRACKED `coverage.py` in a working copy still shadows a local
       `python -m coverage run -m pytest -q`.
    5. `PYTHONSAFEPATH` never removes an explicit `PYTHONPATH` entry, so an
       untracked `src/coverage.py` shadows the tool WITH the variable set —
       on the runner as much as on a laptop. Nothing in this suite closes
       that: a `git ls-files` scan cannot see an untracked file, and the
       variable is not aimed at that entry. What would close it is a step that
       refuses a working tree holding an untracked shadow, and no such step
       exists; until one does this sentence is the whole of the coverage.
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

    # 4. the working-directory shadow is closed by a variable the workflow
    #    sets, not by Python: a run that does not set it is still shadowed by
    #    an UNTRACKED file, which no `git ls-files` scan can reach. Observed in
    #    a subprocess with the variable explicitly removed, so the verdict is
    #    the same whether this suite is running on CI (where the workflow sets
    #    it) or on a laptop (where nothing does). The first version of this
    #    line asserted on the AMBIENT environment instead and passed locally
    #    while failing on CI — the exact shape this file exists to refuse.
    (tmp_path / "untracked_shadow").mkdir()
    (tmp_path / "untracked_shadow" / "coverage.py").write_text(
        "import sys\n\nprint('9999 passed in 0.01s')\nsys.exit(0)\n", encoding="utf-8"
    )
    (tmp_path / "untracked_shadow" / "test_truth.py").write_text(
        "def test_fails() -> None:\n    raise AssertionError('the suite ran')\n",
        encoding="utf-8",
    )
    bare = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST") and key != "PYTHONSAFEPATH"
    }
    shadowed = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q",
         "-p", "no:cacheprovider"],
        cwd=tmp_path / "untracked_shadow",
        env=bare,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert shadowed.returncode == 0, shadowed.stdout + shadowed.stderr
    assert "9999 passed" in shadowed.stdout, shadowed.stdout

    # 5. and the variable does not reach an explicit PYTHONPATH entry. Same
    #    shadow, moved one directory across, with PYTHONSAFEPATH="1" set the
    #    way the workflow sets it: still exit 0, still a fabricated pass line.
    #    This is the route that stays open on the runner, and it is why the
    #    tracked scan above covers `src` rather than only the root.
    (tmp_path / "path_shadow" / "src").mkdir(parents=True)
    (tmp_path / "path_shadow" / "src" / "coverage.py").write_text(
        "import sys\n\nprint('9999 passed in 0.01s')\nsys.exit(0)\n", encoding="utf-8"
    )
    (tmp_path / "path_shadow" / "test_truth.py").write_text(
        "def test_fails() -> None:\n    raise AssertionError('the suite ran')\n",
        encoding="utf-8",
    )
    on_the_path = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q",
         "-p", "no:cacheprovider"],
        cwd=tmp_path / "path_shadow",
        env=dict(bare, PYTHONSAFEPATH="1", PYTHONPATH="src"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert on_the_path.returncode == 0, on_the_path.stdout + on_the_path.stderr
    assert "9999 passed" in on_the_path.stdout, on_the_path.stdout
