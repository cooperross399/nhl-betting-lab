"""A directory of Python the required job never linted or compiled.

The `Full test suite` job ran `python -m pyflakes src scripts tests` and
`python -m compileall -q -f src scripts tests`. `web/` holds Python too —
`web/build_site_json.py` and `web/site_history.py`, which build the published
site — and neither gate read it. Pyflakes on `web/` was clean when this was
found, so nothing had shipped through the gap; but an unused import or an
undefined name on a path no test walks would have, and a syntax error in a
module no test imports would have passed the compile step it was written to
catch.

The rule below is stated against the tree, not against a list: every
top-level directory that holds a `.py` file must be named by BOTH gate lines
of the required job. A new directory of Python fails here until the gates
read it, instead of waiting to be noticed. `tests/test_workflows.py` pins the
two lines whole, so the pin and this rule move together.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"
REQUIRED_CHECK_CONTEXT = "Full test suite"

#: Top-level directories that are never the repository's own source: the
#: local interpreter, and build output. Hidden directories (`.git`, `.venv`,
#: `.github`) are skipped by the dot rule, not listed here.
NOT_SOURCE = frozenset({"build", "dist", "node_modules", "venv"})


def python_directories() -> set[str]:
    """Every top-level directory holding at least one `.py` file."""
    found = set()
    for child in PROJECT_ROOT.iterdir():
        if not child.is_dir() or child.name.startswith(".") or child.name in NOT_SOURCE:
            continue
        if child.name.endswith(".egg-info"):
            continue
        if any(
            "__pycache__" not in path.parts for path in child.rglob("*.py")
        ):
            found.add(child.name)
    return found


def the_required_job_lines() -> list[str]:
    """Every non-blank line of every run block in the required job."""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = [
        job
        for job in document["jobs"].values()
        if job.get("name") == REQUIRED_CHECK_CONTEXT
    ]
    assert len(jobs) == 1, f"expected one job named {REQUIRED_CHECK_CONTEXT!r}"
    lines = []
    for step in jobs[0]["steps"]:
        block = step.get("run")
        if isinstance(block, str):
            lines.extend(line.strip() for line in block.splitlines() if line.strip())
    return lines


def directories_named_by(prefix: str) -> set[str]:
    """The positional arguments of the one line starting with `prefix`."""
    matches = [line for line in the_required_job_lines() if line.startswith(prefix)]
    assert len(matches) == 1, f"expected one line starting {prefix!r}, got {matches}"
    return {word for word in matches[0][len(prefix):].split() if not word.startswith("-")}


def test_there_is_python_outside_src_scripts_and_tests() -> None:
    """The premise, checked, so the rule below is not vacuous."""
    assert "web" in python_directories()


def test_the_lint_reads_every_directory_of_python() -> None:
    unread = sorted(python_directories() - directories_named_by("python -m pyflakes "))
    assert not unread, (
        f"pyflakes in the required job never reads {unread}. An unused import "
        "or an undefined name there ships green."
    )


def test_the_compile_step_reads_every_directory_of_python() -> None:
    unread = sorted(python_directories() - directories_named_by("python -m compileall "))
    assert not unread, (
        f"compileall in the required job never reads {unread}. A module no "
        "test imports can be syntactically invalid there and pass."
    )


def test_the_compile_guard_asserts_every_compiled_directory_exists() -> None:
    """`compileall` exits 0 on a missing directory, so each directory it
    compiles must also be in the `for directory in ...` guard ahead of it."""
    guards = [
        line
        for line in the_required_job_lines()
        if line.startswith("for directory in ") and line.endswith("; do")
    ]
    assert len(guards) == 1, guards
    guarded = set(guards[0][len("for directory in "):-len("; do")].split())
    unguarded = sorted(directories_named_by("python -m compileall ") - guarded)
    assert not unguarded, f"compiled but never asserted to exist: {unguarded}"
