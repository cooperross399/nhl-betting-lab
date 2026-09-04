"""The workflows' self-declared invariants, checked against the parse and by
running the shell — never by matching text.

Until this file existed, nothing in this repository read
`.github/workflows/*.yml` as YAML. `tests/test_repository_discipline.py` and
`tests/test_contract_strings.py` read the files as strings, and a string test
proves only that a spelling is present or absent. The audit reproduced every
consequence on `tests.yml`, the workflow branch protection gates on: the job
that carries the required-check context `Full test suite` could be renamed,
emptied (`echo` where pytest was), disabled (`if: false`, `continue-on-error`),
narrowed (`-x`, a positional path, `PYTEST_ADDOPTS`), or deleted, and every
test in this suite stayed green.

So the rules here are of two kinds, and the file says which is which:

* STRUCTURAL rules read `yaml.safe_load`'s tree. `if: false` parses to the
  boolean False, not the string; `python-version: 3.10` parses to the float
  3.1; `continue-on-error` is a key, not a phrase. A rule over the tree does
  not care how the YAML was spelled.
* EXECUTED rules write a run block to a sandbox, replace every command word it
  contains with a shell function of known exit status, run it under `bash -e`
  — the shell GitHub runs a `run:` block with — and read the exit code. That
  is what catches `if ! cmd; then echo; fi`, `set +e`, `|| true`, `set +o
  pipefail`, a `trap` that exits zero, and every future rewording: the
  question is not what the block says but whether it can reach its end after
  a command in it failed.

Ported from the NCAAF lab's linter, mechanism by mechanism, and scoped to what
this repository's nine workflows actually are. The template lab has two
workflows and neither tolerates a failure; this one has seven OPERATIONAL
workflows that tolerate failure by design — a state restore that finds no
artifact, a slate with no games, a provider that answers 422 — and pin that
tolerance with `continue-on-error`, `set +e` and `if git fetch …; then`. Those
are not gates and are not graded as gates. The two workflows that GATE a pull
request, `tests.yml` and `provider-policy-pr-gate.yml`, are held to the full
rule set, and `tests.yml` — the one whose job name is the required status
check — carries the extra rules that pin that job to the whole suite.

Every rule is a `check_*` function so the bottom half of this file can point
it at a workflow written to break it and assert it REJECTS. `GOOD_WORKFLOW` is
the control: it passes every rule, and every bad case is that text with one
anchored substitution, so a rejection can only have come from the
substitution. A linter nobody has watched fail is a linter that might not
work.

What still gets through is written down in
`test_the_disclosed_holes_are_real`, asserted to be exactly as open as the
sentence says, so closing one turns this file red and the sentence gets
rewritten rather than outliving the fix.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator, NamedTuple

import pytest
import yaml

from nhl_betting_lab.providers.env_file import PROVIDER_ENV_ALLOWLIST

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"

#: The workflow branch protection gates on, and the job `name:` it looks for.
#: The context is a contract string: renaming the job produces no error
#: anywhere — the required check simply never reports, and a pull request
#: with a required check that never reports cannot merge, which looks like
#: GitHub being slow rather than like a broken gate. Pinned in CLAUDE.md's
#: contract table as well.
REQUIRED_CHECK_WORKFLOW = "tests.yml"
REQUIRED_CHECK_CONTEXT = "Full test suite"

#: The workflows that gate a pull request. Neither may tolerate a failure in
#: any step, reach for a secret, hold write permission, or persist a token.
GATE_WORKFLOWS = frozenset({REQUIRED_CHECK_WORKFLOW, "provider-policy-pr-gate.yml"})

#: The provider credential names. Neither may be bound into an `env:` in a
#: gate workflow: the suite must pass without one, and that is what proves no
#: test needs a live provider.
CREDENTIAL_NAMES = frozenset(PROVIDER_ENV_ALLOWLIST)

#: The `secrets` CONTEXT being reached into, in any spelling GitHub accepts —
#: dot, bracket, closing paren, any casing — and the context word anywhere
#: inside a `${{ }}` expression, which is what `${{ toJSON(secrets) }}` and a
#: bare `${{ secrets }}` need neither a dot nor a bracket for. Checked against
#: the raw text so a commented-out reference counts too.
SECRET_REFERENCE = re.compile(r"(?i)\bsecrets\s*[.\[)]")
GITHUB_EXPRESSION = re.compile(r"(?s)\$\{\{.*?\}\}")
SECRETS_WORD = re.compile(r"(?i)\bsecrets\b")

#: `exit` with a status that fails the step, searched per or-list BRANCH.
NONZERO_EXIT = re.compile(r"\bexit\s+[1-9]")

#: A segment whose `||` joins two TESTS rather than guarding a command.
CONDITION = re.compile(r"^\s*(?:if|elif|while|until)\b")

#: `set +e` and every synonym that turns off the option protecting the step.
DISABLES_ERREXIT = re.compile(
    r"\bset\b[^;&|]*\+(?:[a-z]*e[a-z]*\b|o\s+(?:errexit|pipefail)\b)"
)

#: `set -o pipefail` turned ON at the start of a line, and turned back OFF
#: anywhere. Both applied to a line with its quoted spans blanked.
ENABLES_PIPEFAIL = re.compile(r"^\s*set\b[^;&|]*-[a-zA-Z]*o\s+pipefail\b")
DISABLES_PIPEFAIL = re.compile(r"\bset\b[^;&|]*\+o?\s*pipefail\b")

#: A single `|`, not the `||` of an or-list.
PIPELINE = re.compile(r"(?<!\|)\|(?!\|)")

#: Process substitution — a pipeline with no pipe character — and a background
#: operator that is not `&&`, `>&`, `&>`. Both are bans on a capability that
#: no shell option propagates the status of.
PROCESS_SUBSTITUTION = re.compile(r"[<>]\(")
BACKGROUND = re.compile(r"(?<![&>])&(?![&>])")
ASYNC_LAUNCHER = re.compile(r"\b(?:setsid|coproc)\b")

#: A physical line bash continues onto the next one.
CONTINUATION = re.compile(r"(?:\\|\|\||&&|\|)$")

#: pytest flags that stop the run early, select a subset, reconfigure what a
#: bare `pytest` collects, disarm a marker, or drop the conftest whose hooks
#: refuse a narrowed run. Each is a full pass on a string test that looks for
#: `pytest -q`, because none of them changes that substring.
#:
#: `--noconftest`, `-p` and `--continue-on-collection-errors` are here for
#: this lab specifically: `tests/conftest.py` carries the hook that exits the
#: session when a guard module collected nothing, and each of those three is
#: a way to run the suite without that hook or past the collection error a
#: deleted guard raises. `--rootdir` is deliberately NOT here: the hook
#: compares item paths against `config.rootpath`, so a moved root makes every
#: required module fail to match and the hook exits — fail-closed without a
#: rule.
NARROWING_PYTEST_LONG_FLAGS = frozenset(
    {
        "--maxfail",
        "--ignore",
        "--ignore-glob",
        "--deselect",
        "--exitfirst",
        "--override-ini",
        "--config-file",
        "--confcutdir",
        "--noconftest",
        "--runxfail",
        "--continue-on-collection-errors",
        "--collect-only",
        "--co",
        "--last-failed",
        "--lf",
        "--stepwise",
        "--sw",
        "--stepwise-skip",
        "--sw-skip",
        "--stepwise-reset",
        "--sw-reset",
        "--pyargs",
    }
)

#: `-x`, `-k`, `-m`, `-o`, `-c` and `-p`, matched as letters inside a cluster
#: so `-xq` and `-qcci.ini` are caught. `-m` and `-k` have no long spelling.
NARROWING_PYTEST_SHORT_FLAGS = frozenset("xkmocp")

#: pytest reads this as if the flags had been typed. Checked as a key at every
#: level, and as a token in every run block — `export PYTEST_ADDOPTS=-x`
#: narrows the step and `echo PYTEST_ADDOPTS=-x >> "$GITHUB_ENV"` narrows every
#: later one, and neither appears in any `env:` mapping.
PYTEST_ADDOPTS = "PYTEST_ADDOPTS"
PYTEST_ADDOPTS_TOKEN = re.compile(r"(?i)\bPYTEST_ADDOPTS\b")

#: A change of directory before the suite hands pytest a smaller tree with a
#: command line that reads as clean. Banned as command words in the suite
#: step's block; `working-directory:` is banned as a key on it.
DIRECTORY_CHANGERS = frozenset({"cd", "pushd"})

#: The only words that may stand in front of `pytest` on the suite line. A
#: wrapper — `bash -c`, `xargs`, `env`, a script — is a command the harness
#: stubs, and what it does with the string it is handed is never graded.
SUITE_LAUNCHERS = frozenset({"python", "python3", "pytest"})

#: Keys on the required job that would make its check-run name differ from the
#: context branch protection looks for, hand its steps to another file, or
#: switch it off. `strategy` because a matrix job reports as
#: `Full test suite (3.12)`, which matches nothing.
DISQUALIFYING_JOB_KEYS = frozenset(
    {"if", "continue-on-error", "uses", "strategy", "defaults", "container"}
)

#: The only `if:` a step in the suite job may carry. `always()` WIDENS when a
#: step runs; every other expression can evaluate false.
PERMITTED_CONDITION = "always()"

#: Values GitHub accepts for `shell:` that keep the block under the shell the
#: executed rules grade it under. `bash {0}` is bash without the `-e`.
SAFE_SHELLS = frozenset({"bash", "sh"})

#: Directories a gate block may guard on before it does anything. Created in
#: the sandbox before the swallow rule runs a block, so a block that opens with
#: `test -d src || exit 1` reaches the command under test instead of being
#: accepted for having died at its own guard.
STANDARD_DIRECTORIES = ("src", "scripts", "tests", "data", "docs", ".github")

#: Bash keywords are never stubbed (a function named `for` is a syntax error)
#: and builtins are deliberately left real, so that `cmd || true` comes out as
#: exit 0 and reads as the swallow it is.
SHELL_KEYWORDS = frozenset(
    {
        "if", "then", "else", "elif", "fi", "for", "while", "until", "do",
        "done", "case", "esac", "in", "function", "select", "time", "coproc",
        "!", "{", "}", "[[", "]]",
    }
)
SHELL_BUILTINS = frozenset(
    {
        "set", "unset", "exit", "return", "echo", "printf", "test", "[", "]",
        ":", "true", "false", "cd", "pwd", "read", "eval", "exec", "export",
        "local", "shift", "trap", "source", ".", "wait", "break", "continue",
        "declare", "typeset", "let", "mapfile", "readarray", "alias",
        "unalias", "bind", "builtin", "caller", "command", "compgen",
        "complete", "dirs", "disown", "enable", "fc", "fg", "bg", "getopts",
        "hash", "help", "history", "jobs", "kill", "logout", "popd", "pushd",
        "readonly", "suspend", "times", "type", "ulimit", "umask", "shopt",
    }
)
STUB_SAFE_NAME = re.compile(r"^[A-Za-z_./][A-Za-z0-9_./+-]*$")
PREFIX_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
COMMAND_NOT_FOUND = re.compile(r"[:\s]([^:\s]+): command not found")
RUNNER_FILE_VARIABLES = ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH")
VARIABLE_WITH_DEFAULT = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\s*:?[-=+?]")
VARIABLE_BRACED = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)")
VARIABLE_BARE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

#: The shell the harness runs blocks under. Absent, every executed rule FAILS
#: rather than passing quietly.
HARNESS_SHELL = shutil.which("bash")


# --------------------------------------------------------------------------
# Reading the parse.
# --------------------------------------------------------------------------


def workflow_files_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )


WORKFLOW_FILES = workflow_files_in(WORKFLOWS_DIR)
GATE_FILES = [path for path in WORKFLOW_FILES if path.name in GATE_WORKFLOWS]

every_workflow = pytest.mark.parametrize(
    "path", WORKFLOW_FILES, ids=[path.name for path in WORKFLOW_FILES]
)
every_gate = pytest.mark.parametrize(
    "path", GATE_FILES, ids=[path.name for path in GATE_FILES]
)


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(document: Any) -> Any:
    """The `on:` block, whichever key it landed under.

    Bare `on` is a YAML 1.1 boolean, so `yaml.safe_load` files it under the
    key `True`; a quoted `"on"` lands under the string. GitHub reads the two
    identically, so a rule that knew only one would pass every workflow
    written the other way.
    """
    if isinstance(document, dict):
        if "on" in document:
            return document["on"]
        if True in document:
            return document[True]
    return None


def mappings(node: Any) -> Iterator[dict]:
    """Every mapping in the document, at any depth."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from mappings(item)


def jobs_of(document: Any) -> dict[str, dict]:
    jobs = document.get("jobs") if isinstance(document, dict) else None
    if not isinstance(jobs, dict):
        return {}
    return {str(name): job for name, job in jobs.items() if isinstance(job, dict)}


def steps_of(job: dict) -> list[dict]:
    steps = job.get("steps")
    return [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []


def steps_using(document: Any, action: str) -> Iterator[dict]:
    for mapping in mappings(document):
        uses = mapping.get("uses")
        if isinstance(uses, str) and uses.split("@", 1)[0] == action:
            yield mapping


def run_blocks(document: Any) -> Iterator[tuple[str, str]]:
    for mapping in mappings(document):
        command = mapping.get("run")
        if isinstance(command, str):
            yield str(mapping.get("name", "<unnamed step>")), command


def commands(block: str) -> list[str]:
    """The LOGICAL lines bash will execute: comments dropped, continuations
    joined. A `pytest \\` on one line and `-k slow` on the next is one command,
    and a rule that read physical lines never saw the `-k`."""
    joined: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if joined and CONTINUATION.search(joined[-1]):
            previous = joined[-1]
            if previous.endswith("\\"):
                previous = previous[:-1].rstrip()
            joined[-1] = f"{previous} {line}"
        else:
            joined.append(line)
    return [line[:-1].rstrip() if line.endswith("\\") else line for line in joined]


def condition_of(node: dict) -> str | None:
    """The `if:` as written, unwrapped from `${{ }}` and stringified.

    YAML parses `if: false` to the BOOLEAN False, so a rule that only ever
    compared strings would pass the single cheapest way to switch a gate off.
    """
    if "if" not in node:
        return None
    raw = str(node["if"]).strip()
    if raw.startswith("${{") and raw.endswith("}}"):
        raw = raw[3:-2].strip()
    return raw


# --------------------------------------------------------------------------
# The stub harness: the swallow rule stops reading shell and starts running it.
# --------------------------------------------------------------------------


def _uncommented(block: str) -> str:
    return "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )


def _shell_regions(text: str) -> list[str]:
    """The text with `$(...)` and backtick spans lifted out, plus those spans.

    A command inside a substitution still runs, so it still needs a stub.
    Single quotes are opaque; double quotes are not.
    """
    outer: list[str] = []
    inner: list[str] = []
    index, size = 0, len(text)
    while index < size:
        character = text[index]
        if character == "'":
            close = text.find("'", index + 1)
            close = size if close < 0 else close
            outer.append(text[index : close + 1])
            index = close + 1
            continue
        if character == "\\":
            outer.append(text[index : index + 2])
            index += 2
            continue
        if text.startswith("$(", index):
            depth, cursor = 1, index + 2
            while cursor < size and depth:
                if text[cursor] == "'":
                    close = text.find("'", cursor + 1)
                    cursor = (size if close < 0 else close) + 1
                    continue
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == "(":
                    depth += 1
                elif text[cursor] == ")":
                    depth -= 1
                cursor += 1
            inner.append(text[index + 2 : max(cursor - 1, index + 2)])
            outer.append(" ")
            index = cursor
            continue
        if character == "`":
            close = text.find("`", index + 1)
            close = size if close < 0 else close
            inner.append(text[index + 1 : close])
            outer.append(" ")
            index = close + 1
            continue
        outer.append(character)
        index += 1
    regions = ["".join(outer)]
    for span in inner:
        regions.extend(_shell_regions(span))
    return regions


def _scan_command_words(
    region: str, found: list[str], *, keep_builtins: bool = False
) -> None:
    current: list[str] = []
    quote: str | None = None
    at_command, skip_next = True, False
    index, size = 0, len(region)

    def flush() -> None:
        nonlocal current, at_command, skip_next
        token = "".join(current)
        current = []
        if not token:
            return
        if skip_next:
            skip_next = False
            return
        if not at_command:
            return
        if token in SHELL_KEYWORDS or PREFIX_ASSIGNMENT.match(token):
            return
        at_command = False
        if re.fullmatch(r"[0-9]+", token):
            return
        if token in SHELL_BUILTINS and not keep_builtins:
            return
        if "$" in token or "*" in token or "?" in token:
            return
        if token not in found:
            found.append(token)

    while index < size:
        character = region[index]
        if quote is not None:
            if character == quote:
                quote = None
            elif quote == '"' and character == "\\":
                index += 1
            current.append(character)
            index += 1
            continue
        if character in "'\"":
            quote = character
            current.append(character)
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character in "<>":
            flush()
            skip_next = True
            index += 1
            continue
        if character == "\n" or character in ";|&(){}`":
            flush()
            at_command, skip_next = True, False
            index += 1
            continue
        if character.isspace():
            flush()
            index += 1
            continue
        current.append(character)
        index += 1
    flush()


def command_words(block: str) -> list[str]:
    """Every word this block would invoke as a command. Over-collection is
    safe (an unused stub) and under-collection is not (an unmodelled command),
    which `run_block_under_stubs` reports from the other side."""
    found: list[str] = []
    for region in _shell_regions(_uncommented(block)):
        _scan_command_words(region, found)
    return found


def directory_changes(block: str) -> list[str]:
    """Every `cd`/`pushd` in command position. `command_words` drops builtins
    on purpose (a stubbed `true` would turn `|| true` into a failure path), so
    this reads the same positions with the builtins kept."""
    found: list[str] = []
    for region in _shell_regions(_uncommented(block)):
        _scan_command_words(region, found, keep_builtins=True)
    return sorted(DIRECTORY_CHANGERS & set(found))


def first_command_word(line: str) -> str:
    found: list[str] = []
    _scan_command_words(line, found, keep_builtins=True)
    return found[0] if found else ""


def referenced_variables(block: str) -> list[str]:
    named = set(VARIABLE_BRACED.findall(block)) | set(VARIABLE_BARE.findall(block))
    return sorted(named - set(VARIABLE_WITH_DEFAULT.findall(block)))


def _quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def stub_preamble(
    words: list[str],
    failing: set[str] | None,
    failure_log: Path,
    any_failure_log: Path,
    unmodelled_log: Path,
    marker: Path,
) -> str:
    """One bash function per command word, of known exit status.

    Written flat rather than through a helper, because bash does not inherit
    an ERR trap into a nested frame without `set -E`, and `trap 'exit 0' ERR`
    is a swallow with no `||` in it. A failing stub logs itself twice: once
    only when it ran in the top-level shell (the pid test — a failure inside
    `$(...)` is invisible to errexit and must not be counted), and once
    unconditionally, which is what sees a backgrounded failure.
    """
    assert HARNESS_SHELL, "no bash on PATH: the executed swallow rule cannot run"
    lines = [
        "command_not_found_handle() { printf '%s\\n' \"$1\" >> "
        + _quote(str(unmodelled_log))
        + "; return 127; }",
        "readonly PATH",
    ]
    for word in words:
        status = 1 if (failing is None or word in failing) else 0
        body = ["%s() {" % word]
        if status:
            body.append(
                "  printf '%s\\n' " + _quote(word) + " >> " + _quote(str(any_failure_log))
            )
            body.append(
                '  __SWALLOW_PID="$( exec %s -c \'echo $PPID\' )"' % _quote(HARNESS_SHELL)
            )
            body.append(
                '  if [ "$__SWALLOW_PID" = "$$" ]; then printf \'%s\\n\' '
                + _quote(word)
                + " >> "
                + _quote(str(failure_log))
                + "; fi"
            )
        body.append("  printf 'stub:%s\\n' " + _quote(word))
        body.append("  return %d" % status)
        body.append("}")
        lines.append("\n".join(body))
    lines.append(": > %s" % _quote(str(marker)))
    return "\n".join(lines) + "\n"


class BlockRun(NamedTuple):
    exit_code: int
    top_level_failures: list[str]
    unmodelled: list[str]
    stderr: str
    any_failures: list[str]


def run_block_under_stubs(
    block: str,
    failing: set[str] | None,
    sandbox: Path,
    *,
    populate: tuple[str, ...] = (),
) -> BlockRun:
    """Execute one run block with every command replaced by a stub.

    `failing` is the set of command words whose stub returns 1; `None` means
    all of them, and an empty set means none. Nothing real executes: PATH is
    an empty directory inside the sandbox, the working directory is the
    sandbox, and the environment is built from scratch. `populate` names
    directories to create in the sandbox first, so a block may guard on them.

    A `:` is appended after the block. Without it a block that ends in a
    failing command exits non-zero whatever it did with the failure, so
    `set +e` would read as clean. With it, the question the exit code answers
    is the right one: once a top-level command has failed, this block must not
    reach its end.
    """
    assert HARNESS_SHELL, "no bash on PATH: the executed swallow rule cannot run"
    sandbox = Path(sandbox)
    failure_log = sandbox / "top_level_failures.txt"
    any_failure_log = sandbox / "any_failures.txt"
    unmodelled_log = sandbox / "unmodelled_commands.txt"
    marker = sandbox / "preamble_completed"
    failure_log.write_text("", encoding="utf-8")
    any_failure_log.write_text("", encoding="utf-8")
    unmodelled_log.write_text("", encoding="utf-8")
    if marker.exists():
        marker.unlink()
    empty_path_dir = sandbox / "empty-path"
    empty_path_dir.mkdir(exist_ok=True)
    for name in populate:
        (sandbox / name).mkdir(parents=True, exist_ok=True)

    words = command_words(block)
    unstubbable = [word for word in words if not STUB_SAFE_NAME.match(word)]
    preamble = stub_preamble(
        [word for word in words if STUB_SAFE_NAME.match(word)],
        failing,
        failure_log,
        any_failure_log,
        unmodelled_log,
        marker,
    )
    parsed = subprocess.run(
        [HARNESS_SHELL, "-n"], input=preamble, capture_output=True, text=True
    )
    if parsed.returncode != 0:
        raise RuntimeError(
            "the stub preamble does not parse, so no verdict from it means "
            f"anything: {parsed.stderr}"
        )

    script = sandbox / "run_block.sh"
    script.write_text(preamble + block + "\n:\n", encoding="utf-8")
    environment = {
        "PATH": str(empty_path_dir),
        "LC_ALL": "C",
        "HOME": str(sandbox),
        "GITHUB_WORKSPACE": str(sandbox),
        "RUNNER_TEMP": str(sandbox),
    }
    for name in RUNNER_FILE_VARIABLES:
        target = sandbox / name.lower()
        target.touch()
        environment[name] = str(target)
    for name in referenced_variables(block):
        environment.setdefault(name, "__harness__")

    completed = subprocess.run(
        [HARNESS_SHELL, "-e", str(script)],
        cwd=sandbox,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if not marker.exists():
        raise RuntimeError(
            "the stub preamble did not run to completion, so the exit code "
            f"below is not a verdict on the block: {completed.stderr}"
        )
    unmodelled = sorted(
        set(unstubbable)
        | set(unmodelled_log.read_text(encoding="utf-8").split())
        | set(COMMAND_NOT_FOUND.findall(completed.stderr))
    )
    return BlockRun(
        completed.returncode,
        failure_log.read_text(encoding="utf-8").split(),
        unmodelled,
        completed.stderr,
        any_failure_log.read_text(encoding="utf-8").split(),
    )


def swallow_findings(block: str) -> list[str]:
    """Run the block under every single-failure configuration; report swallows.

    Every command failing, then each alone: with everything failing a block
    stops at its first gate and a swallow further down is never reached, so
    `cmd_a; cmd_b || true` needs `cmd_b` failing alone.
    """
    findings: list[str] = []
    words = command_words(block)
    backgrounded = [
        line
        for line in commands(block)
        if BACKGROUND.search(without_quoted_spans(line))
        or ASYNC_LAUNCHER.search(without_quoted_spans(line))
    ]
    with tempfile.TemporaryDirectory() as directory:
        sandbox = Path(directory)
        for failing in [None] + [{word} for word in words]:
            result = run_block_under_stubs(
                block, failing, sandbox, populate=STANDARD_DIRECTORIES
            )
            label = (
                "every command failing"
                if failing is None
                else "only %s failing" % ", ".join(sorted(failing))
            )
            if result.unmodelled:
                findings.append(
                    f"with {label}, {result.unmodelled} reached the shell with "
                    "no stub behind it, so this block was never modelled. A "
                    "gate that could not run the thing has not cleared it."
                )
                continue
            if result.exit_code == 0 and result.top_level_failures:
                findings.append(
                    f"with {label}, {sorted(set(result.top_level_failures))} "
                    "failed and the block still exited 0. In CI that is a green "
                    "step over a failed command."
                )
                continue
            if result.exit_code == 0 and backgrounded and result.any_failures:
                findings.append(
                    f"with {label}, {sorted(set(result.any_failures))} failed "
                    f"and the block still exited 0 while running {backgrounded} "
                    "in the background."
                )
    return findings


def without_quoted_spans(line: str) -> str:
    """The line with every quoted span replaced by spaces of the same width,
    so `echo 'set +e'` does not trip the rule about `set +e`."""
    text: list[str] = []
    index, size = 0, len(line)
    while index < size:
        character = line[index]
        if character == "\\":
            text.append(" ")
            index += 2
            continue
        if character in "'\"":
            cursor = index + 1
            while cursor < size:
                if character == '"' and line[cursor] == "\\":
                    cursor += 2
                    continue
                if line[cursor] == character:
                    break
                cursor += 1
            text.append(" " * (min(cursor, size - 1) - index + 1))
            index = cursor + 1
            continue
        text.append(character)
        index += 1
    return "".join(text)


def _top_level_pieces(line: str) -> list[list[str]]:
    """Segments split on top-level `;` and `&&`, each split on top-level `||`,
    with brace and paren groups kept whole."""
    blanked = without_quoted_spans(line)
    segments: list[list[str]] = []
    chunks: list[str] = []
    current: list[str] = []
    depth = 0
    index, size = 0, len(blanked)
    while index < size:
        character = blanked[index]
        if character in "({":
            depth += 1
        elif character in ")}":
            depth = max(0, depth - 1)
        if depth == 0 and blanked.startswith("||", index):
            chunks.append("".join(current))
            current = []
            index += 2
            continue
        if depth == 0 and blanked.startswith("&&", index):
            chunks.append("".join(current))
            segments.append(chunks)
            chunks, current = [], []
            index += 2
            continue
        if depth == 0 and character == ";":
            chunks.append("".join(current))
            segments.append(chunks)
            chunks, current = [], []
            index += 1
            continue
        current.append(character)
        index += 1
    chunks.append("".join(current))
    segments.append(chunks)
    return segments


def unguarded_or_branches(line: str) -> list[str]:
    """The `||` branches on this line that do NOT end in a non-zero exit.
    The textual net beside the executed rule: it sees `( cmd ) || true`, where
    the failure is in a subshell and execution does not."""
    branches: list[str] = []
    for chunks in _top_level_pieces(line):
        if len(chunks) < 2:
            continue
        if CONDITION.search(chunks[0]):
            continue
        for position in range(1, len(chunks)):
            branch = "||".join(chunks[position:])
            if not NONZERO_EXIT.search(branch):
                branches.append(branch.strip())
    return branches


def pytest_arguments(line: str) -> list[str]:
    found = re.search(r"\bpytest\b", line)
    if found is None:
        return []
    tail = line[found.end() :]
    try:
        return shlex.split(tail)
    except ValueError:
        return tail.split()


def pytest_lines_in(block: str) -> list[str]:
    return [line for line in commands(block) if re.search(r"\bpytest\b", line)]


def pytest_lines(document: Any) -> Iterator[tuple[str, str]]:
    for name, block in run_blocks(document):
        for line in pytest_lines_in(block):
            yield name, line


def narrowing_findings(line: str) -> list[str]:
    """Every argument after `pytest` on this line that narrows the run."""
    findings: list[str] = []
    for argument in pytest_arguments(line):
        if not argument.startswith("-"):
            findings.append(
                f"positional {argument!r} — a path, a node id or a directory "
                "selects a subset exactly as --ignore does"
            )
        elif argument.startswith("--"):
            flag = argument.split("=", 1)[0]
            if flag in NARROWING_PYTEST_LONG_FLAGS:
                findings.append(f"{flag} narrows, reconfigures or disarms the run")
        elif argument != "-":
            cluster = set(argument[1:].split("=", 1)[0])
            narrowing = cluster & NARROWING_PYTEST_SHORT_FLAGS
            if narrowing:
                findings.append(
                    f"{argument} carries -{''.join(sorted(narrowing))}, which "
                    "narrows, reconfigures or disarms the run"
                )
    return findings


def required_jobs(paths: list[Path]) -> list[tuple[str, str, dict]]:
    """Every (file, job id, job) whose `name:` is the required-check context."""
    found: list[tuple[str, str, dict]] = []
    for path in paths:
        for job_id, job in jobs_of(load(path)).items():
            if str(job.get("name", "")).strip() == REQUIRED_CHECK_CONTEXT:
                found.append((path.name, job_id, job))
    return found


def compile_lines(document: Any) -> list[tuple[str, str, str]]:
    """(step, block, line) for every `compileall` invocation."""
    found: list[tuple[str, str, str]] = []
    for name, block in run_blocks(document):
        for line in commands(block):
            if "compileall" in line:
                found.append((name, block, line))
    return found


# --------------------------------------------------------------------------
# The rules. Each is a function so it can be aimed at a synthetic workflow as
# well as at the real ones.
# --------------------------------------------------------------------------


def check_parses_and_declares_a_trigger(path: Path) -> None:
    document = load(path)
    assert isinstance(document, dict), f"{path.name} did not parse to a mapping"
    assert triggers(document), (
        f"{path.name} declares no `on:` trigger. A workflow that never runs "
        "reports nothing, and nothing is indistinguishable from green."
    )


def check_python_version_is_pinned_to_an_exact_minor(path: Path) -> None:
    for mapping in mappings(load(path)):
        version = mapping.get("python-version")
        if version is None:
            continue
        assert isinstance(version, str), (
            f"{path.name}: python-version {version!r} is not a string. "
            "Unquoted 3.10 parses as the float 3.1."
        )
        assert re.fullmatch(r"\d+\.\d+", version), (
            f"{path.name}: python-version {version!r} is not an exact X.Y pin."
        )


def check_no_workflow_overrides_the_shell(path: Path) -> None:
    """Every executed rule grades a block under `bash -e`. `shell: bash {0}`
    — on a step, or in a `defaults.run` at job or workflow level — is bash
    without the `-e`, and after it every verdict here is about a shell the
    workflow does not run. Structural: the value must be the bare keyword."""
    for mapping in mappings(load(path)):
        if "shell" not in mapping:
            continue
        declared = mapping["shell"]
        assert isinstance(declared, str) and declared in SAFE_SHELLS, (
            f"{path.name}: `shell: {declared!r}` on "
            f"{mapping.get('name', 'a step, a job default or the workflow')}. "
            f"Only {sorted(SAFE_SHELLS)} are accepted, as bare keywords."
        )


def check_no_workflow_declares_a_secrets_key(path: Path) -> None:
    """`secrets: inherit` on a `uses:` job hands the called workflow every
    secret in the repository and contains no `${{ }}` for an expression rule
    to see. A rule about structure: at any level, `secrets` is not a key."""
    for mapping in mappings(load(path)):
        declared = [key for key in mapping if str(key).strip().lower() == "secrets"]
        assert not declared, (
            f"{path.name}: a `secrets:` key on "
            f"{mapping.get('name', 'a job or the workflow')}."
        )


def check_no_job_delegates_to_a_reusable_workflow(path: Path) -> None:
    """A job written as `uses:` has its steps in another file, out of reach
    of every rule here, and a green tick would mean nothing objected rather
    than that anything ran."""
    for job_id, job in jobs_of(load(path)).items():
        assert "uses" not in job, (
            f"{path.name}: job {job_id!r} delegates to {job['uses']!r} instead "
            "of declaring its steps."
        )


def check_the_suite_is_never_narrowed(path: Path) -> None:
    """No pytest invocation anywhere carries a narrowing argument, and
    PYTEST_ADDOPTS is bound nowhere — not as a key at any level, not as a
    token in any run block."""
    document = load(path)
    for mapping in mappings(document):
        environment = mapping.get("env")
        if not isinstance(environment, dict):
            continue
        bound = [key for key in environment if str(key).strip().upper() == PYTEST_ADDOPTS]
        assert not bound, (
            f"{path.name}: `env:` binds {PYTEST_ADDOPTS} on "
            f"{mapping.get('name', 'a job or the workflow')}. pytest reads it "
            "as if the flags had been typed."
        )
    for name, block in run_blocks(document):
        for line in commands(block):
            assert not PYTEST_ADDOPTS_TOKEN.search(line), (
                f"{path.name}: step {name!r} sets {PYTEST_ADDOPTS} from the "
                f"shell: {line!r}."
            )
    for name, line in pytest_lines(document):
        findings = narrowing_findings(line)
        assert not findings, (
            f"{path.name}: step {name!r} narrows the suite: {line!r} — "
            + "; ".join(findings)
        )


def check_permissions_are_declared_and_read_only(path: Path) -> None:
    document = load(path)
    assert isinstance(document, dict) and "permissions" in document, (
        f"{path.name} declares no top-level `permissions:`. The omitted block "
        "inherits the repository default, which may be write."
    )
    for mapping in mappings(document):
        granted = mapping.get("permissions")
        if granted is None:
            continue
        rendered = (
            " ".join(f"{scope}:{level}" for scope, level in granted.items())
            if isinstance(granted, dict)
            else str(granted)
        )
        assert "write" not in rendered, (
            f"{path.name} grants write permission ({rendered}). A gate that "
            "can push is a gate that can rewrite the evidence it guards."
        )


def check_no_step_or_job_continues_on_error(path: Path) -> None:
    for mapping in mappings(load(path)):
        assert "continue-on-error" not in mapping, (
            f"{path.name}: `continue-on-error` on "
            f"{mapping.get('name', 'a job')}. A step that reports success "
            "after failing is worse than no step."
        )


def check_no_workflow_references_a_secret(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    accesses = [
        text[found.start() : found.end() + 40] for found in SECRET_REFERENCE.finditer(text)
    ]
    accesses += [
        expression.group(0)
        for expression in GITHUB_EXPRESSION.finditer(text)
        if SECRETS_WORD.search(expression.group(0))
    ]
    assert not accesses, (
        f"{path.name} references a secret ({accesses!r}). The gate's whole "
        "claim is that it passes without one."
    )
    for mapping in mappings(load(path)):
        environment = mapping.get("env")
        if not isinstance(environment, dict):
            continue
        bound = CREDENTIAL_NAMES.intersection(map(str, environment))
        assert not bound, (
            f"{path.name}: `env:` binds {sorted(bound)} on "
            f"{mapping.get('name', 'a job or the workflow')}."
        )


def check_checkout_never_persists_credentials(path: Path) -> None:
    for step in steps_using(load(path), "actions/checkout"):
        options = step.get("with") or {}
        assert options.get("persist-credentials") is False, (
            f"{path.name}: checkout does not set `persist-credentials: false`."
        )


def check_every_piped_run_block_sets_pipefail(path: Path) -> None:
    for name, block in run_blocks(load(path)):
        lines = [without_quoted_spans(line) for line in commands(block)]
        if not any(PIPELINE.search(line) for line in lines):
            continue
        first = lines[0]
        assert ENABLES_PIPEFAIL.search(first), (
            f"{path.name}: step {name!r} pipes but does not open with "
            f"`set -o pipefail`; its first command is {first!r}."
        )
        for line in lines:
            assert not DISABLES_PIPEFAIL.search(line), (
                f"{path.name}: step {name!r} turns pipefail back off: {line!r}."
            )


def check_no_run_block_swallows_a_failure(path: Path) -> None:
    """Run every run block with its commands failing and demand it notices.

    The executed rule is the gate; the textual nets in front of it are kept
    because execution has blind spots of its own — a failure inside `$(...)`,
    a pipeline element, or a `( )` subshell is invisible to errexit — and
    either net rejecting is a rejection.
    """
    for name, block in run_blocks(load(path)):
        for line in commands(block):
            blanked = without_quoted_spans(line)
            assert not DISABLES_ERREXIT.search(blanked), (
                f"{path.name}: step {name!r} turns off the option that makes a "
                f"failing command fail the step: {line!r}."
            )
            assert not PROCESS_SUBSTITUTION.search(blanked), (
                f"{path.name}: step {name!r} uses process substitution: "
                f"{line!r}. No shell option propagates its status."
            )
            assert not BACKGROUND.search(blanked), (
                f"{path.name}: step {name!r} runs a command in the background: "
                f"{line!r}. errexit does not apply to an asynchronous command."
            )
            assert not ASYNC_LAUNCHER.search(blanked), (
                f"{path.name}: step {name!r} detaches a command: {line!r}."
            )
            unguarded = unguarded_or_branches(line)
            assert not unguarded, (
                f"{path.name}: step {name!r} swallows a failure: {line!r}. The "
                f"branch(es) {unguarded} run when the command on the left "
                "fails and do not end in a non-zero exit."
            )
        findings = swallow_findings(block)
        assert not findings, (
            f"{path.name}: step {name!r} was executed under stubs and "
            + "; ".join(findings)
        )


def check_the_pull_request_trigger_is_unfiltered(path: Path) -> None:
    """`pull_request` is present and carries nothing.

    A `paths:` or `paths-ignore:` filter leaves a required check pending
    rather than passing on a pull request that touches nothing listed — and
    the change that breaks a guard rarely touches the guard's own file. A
    `branches:` filter does the same for a pull request into any other base,
    and `types:` for any activity type it omits. The only value that cannot
    be narrowed is no value at all.
    """
    trigger = triggers(load(path))
    assert isinstance(trigger, dict) and "pull_request" in trigger, (
        f"{path.name}: no `pull_request` trigger. The required check never "
        "reports on a pull request, so nothing can merge — or, if protection "
        "is ever relaxed, everything can."
    )
    filters = trigger["pull_request"]
    assert filters is None or filters == {}, (
        f"{path.name}: `pull_request` carries {filters!r}. Any key here narrows "
        "when the required check runs."
    )


def check_exactly_one_job_carries_the_required_context(path: Path) -> None:
    """Across the whole directory, one job — in this file — is named for the
    context branch protection gates on. Zero means the check never reports;
    two means a second workflow can satisfy the protection in its place."""
    document = load(path)
    here = [
        job_id
        for job_id, job in jobs_of(document).items()
        if str(job.get("name", "")).strip() == REQUIRED_CHECK_CONTEXT
    ]
    assert len(here) == 1, (
        f"{path.name}: {len(here)} job(s) named {REQUIRED_CHECK_CONTEXT!r} "
        f"({here}). Branch protection requires exactly that name."
    )


def _the_required_job(path: Path) -> tuple[str, dict]:
    matches = [
        (job_id, job)
        for job_id, job in jobs_of(load(path)).items()
        if str(job.get("name", "")).strip() == REQUIRED_CHECK_CONTEXT
    ]
    assert len(matches) == 1, f"{path.name}: expected one required job, found {matches}"
    return matches[0]


def check_the_required_job_is_unconditional_and_undelegated(path: Path) -> None:
    document = load(path)
    assert "defaults" not in document, (
        f"{path.name}: a workflow-level `defaults:` block ({document['defaults']!r}) "
        "applies a shell or a directory to every step without appearing on any."
    )
    job_id, job = _the_required_job(path)
    runner = job.get("runs-on")
    assert isinstance(runner, str) and runner.startswith("ubuntu"), (
        f"{path.name}: job {job_id!r} runs on {runner!r}. The default shell on "
        "a Windows runner is pwsh, which fails a step on its LAST command's "
        "status only, so `pytest; echo done` is green there — and every "
        "executed rule here grades `bash -e`, which is the Linux default."
    )
    present = sorted(DISQUALIFYING_JOB_KEYS & set(map(str, job)))
    assert not present, (
        f"{path.name}: job {job_id!r} carries {present}. `if` and "
        "`continue-on-error` switch the gate off, `uses` moves its steps out "
        "of reach, `strategy` renames its check run, `defaults` and `container` "
        "change the shell every executed rule grades it under."
    )


def check_the_required_job_runs_the_whole_suite(path: Path) -> None:
    """The job has a step that invokes pytest, literally, with nothing that
    narrows it — and that step cannot be conditioned, told to continue, moved
    to another directory or handed another shell."""
    job_id, job = _the_required_job(path)
    suite_steps = [
        step
        for step in steps_of(job)
        if isinstance(step.get("run"), str) and pytest_lines_in(step["run"])
    ]
    assert suite_steps, (
        f"{path.name}: job {job_id!r} has no step whose `run:` invokes pytest. "
        "A job that runs no suite reports green having tested nothing."
    )
    for step in suite_steps:
        name = step.get("name", "<unnamed step>")
        condition = condition_of(step)
        assert condition is None or condition == PERMITTED_CONDITION, (
            f"{path.name}: the suite step {name!r} carries `if: {condition}`."
        )
        for key in ("continue-on-error", "shell", "working-directory", "uses"):
            assert key not in step, f"{path.name}: the suite step {name!r} carries `{key}:`."
        moved = directory_changes(step["run"])
        assert not moved, (
            f"{path.name}: the suite step {name!r} changes directory "
            f"({moved}) before running pytest."
        )
        for line in pytest_lines_in(step["run"]):
            # pytest inside a quoted string is an argument to something else —
            # `bash -c '…pytest…'`, `python -c "import pytest; …"` — and the
            # something else is a stub the executed rule cannot see into. The
            # word has to be on the line itself, and the line has to begin
            # with the interpreter or with pytest: no wrapper in front of it.
            assert re.search(r"\bpytest\b", without_quoted_spans(line)), (
                f"{path.name}: the suite step {name!r} invokes pytest only "
                f"inside a quoted string: {line!r}. Whatever runs that string "
                "is what the harness stubs, and its contents are never graded."
            )
            first = first_command_word(line)
            assert first in SUITE_LAUNCHERS, (
                f"{path.name}: the suite step {name!r} launches pytest through "
                f"{first!r}: {line!r}. Only {sorted(SUITE_LAUNCHERS)} may stand "
                "in front of the suite; a wrapper can hand it anything."
            )
            findings = narrowing_findings(line)
            assert not findings, (
                f"{path.name}: the suite step {name!r} narrows the suite: "
                f"{line!r} — " + "; ".join(findings)
            )


def check_the_suite_step_fails_when_pytest_fails(path: Path) -> None:
    """Executed: with every command failing, and with only the command that
    carries pytest failing, the suite step's block must exit non-zero. This is
    the rule `echo` in place of pytest cannot satisfy by spelling, because
    the step is first required to invoke pytest at all."""
    _, job = _the_required_job(path)
    executed = 0
    for step in steps_of(job):
        block = step.get("run")
        if not isinstance(block, str) or not pytest_lines_in(block):
            continue
        carriers = {
            word
            for line in pytest_lines_in(block)
            for word in command_words(line)
        }
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            for failing in (None, carriers):
                result = run_block_under_stubs(
                    block, failing, sandbox, populate=STANDARD_DIRECTORIES
                )
                executed += 1
                assert not result.unmodelled, (
                    f"{path.name}: the suite step could not be modelled: "
                    f"{result.unmodelled}"
                )
                assert result.exit_code != 0, (
                    f"{path.name}: the suite step {step.get('name')!r} exited 0 "
                    f"with {sorted(failing or carriers)} failing. A failed "
                    "suite would be a green check."
                )
    assert executed, f"{path.name}: no suite step was executed"


def check_the_compile_step_refuses_a_missing_directory(path: Path) -> None:
    """`python -m compileall -q missing/` prints "Can't list" and exits 0 —
    measured, not assumed. So every compile invocation must pass `-f`, and its
    block must refuse to run when a directory it compiles is absent. Observed
    three ways: nothing failing and no directories, the block must exit
    non-zero; nothing failing and the directories present, it must exit zero;
    everything failing and the directories present, non-zero again — the third
    is what a `|| true` behind the guard would otherwise hide."""
    invocations = compile_lines(load(path))
    assert invocations, f"{path.name}: no `compileall` invocation"
    for name, block, line in invocations:
        arguments = pytest_arguments(line.replace("compileall", "pytest", 1))
        assert "-f" in arguments, (
            f"{path.name}: step {name!r} compiles without `-f`: {line!r}. A "
            "stale .pyc makes a broken module look compiled."
        )
        directories = tuple(argument for argument in arguments if not argument.startswith("-"))
        assert directories, f"{path.name}: step {name!r} compiles nothing: {line!r}"
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            absent = run_block_under_stubs(block, set(), sandbox)
            assert absent.exit_code != 0, (
                f"{path.name}: step {name!r} exited 0 with {directories} absent."
            )
            present = run_block_under_stubs(block, set(), sandbox, populate=directories)
            assert present.exit_code == 0, (
                f"{path.name}: step {name!r} exited {present.exit_code} with "
                f"{directories} present and nothing failing: {present.stderr}"
            )
            failing = run_block_under_stubs(block, None, sandbox, populate=directories)
            assert failing.exit_code != 0, (
                f"{path.name}: step {name!r} exited 0 with every command failing."
            )


#: Rules that hold for every workflow in the directory.
CORPUS_CHECKS: dict[str, Callable[[Path], None]] = {
    "parses_and_declares_a_trigger": check_parses_and_declares_a_trigger,
    "python_version_is_pinned_to_an_exact_minor": check_python_version_is_pinned_to_an_exact_minor,
    "no_workflow_overrides_the_shell": check_no_workflow_overrides_the_shell,
    "no_workflow_declares_a_secrets_key": check_no_workflow_declares_a_secrets_key,
    "no_job_delegates_to_a_reusable_workflow": check_no_job_delegates_to_a_reusable_workflow,
    "the_suite_is_never_narrowed": check_the_suite_is_never_narrowed,
}

#: Rules that hold for the two workflows that gate a pull request.
GATE_CHECKS: dict[str, Callable[[Path], None]] = {
    "permissions_are_declared_and_read_only": check_permissions_are_declared_and_read_only,
    "no_step_or_job_continues_on_error": check_no_step_or_job_continues_on_error,
    "no_workflow_references_a_secret": check_no_workflow_references_a_secret,
    "checkout_never_persists_credentials": check_checkout_never_persists_credentials,
    "every_piped_run_block_sets_pipefail": check_every_piped_run_block_sets_pipefail,
    "no_run_block_swallows_a_failure": check_no_run_block_swallows_a_failure,
}

#: Rules that hold for the workflow carrying the required status check.
REQUIRED_CHECKS: dict[str, Callable[[Path], None]] = {
    "the_pull_request_trigger_is_unfiltered": check_the_pull_request_trigger_is_unfiltered,
    "exactly_one_job_carries_the_required_context": check_exactly_one_job_carries_the_required_context,
    "the_required_job_is_unconditional_and_undelegated": check_the_required_job_is_unconditional_and_undelegated,
    "the_required_job_runs_the_whole_suite": check_the_required_job_runs_the_whole_suite,
    "the_suite_step_fails_when_pytest_fails": check_the_suite_step_fails_when_pytest_fails,
    "the_compile_step_refuses_a_missing_directory": check_the_compile_step_refuses_a_missing_directory,
}

CHECKS = {**CORPUS_CHECKS, **GATE_CHECKS, **REQUIRED_CHECKS}


# --------------------------------------------------------------------------
# The rules, applied to the real .github/workflows/*.yml.
# --------------------------------------------------------------------------


def test_the_workflow_directory_holds_the_workflows_these_rules_expect() -> None:
    """A linter that lints nothing passes. Every parametrised test below
    collects zero cases over an empty directory, so the directory, the gate
    files and the required-check file are asserted present by name."""
    assert WORKFLOWS_DIR.is_dir(), f"{WORKFLOWS_DIR} does not exist"
    assert WORKFLOW_FILES, f"no workflow files under {WORKFLOWS_DIR}"
    names = {path.name for path in WORKFLOW_FILES}
    assert GATE_WORKFLOWS <= names, sorted(GATE_WORKFLOWS - names)
    assert REQUIRED_CHECK_WORKFLOW in names


def test_the_executed_rules_have_a_shell_to_run_in() -> None:
    """No bash, no verdict — and no verdict must not read as a clean one."""
    assert HARNESS_SHELL, (
        "bash is not on PATH, so run blocks cannot be executed. That is a "
        "broken gate, not evidence that no failure is swallowed."
    )


@pytest.mark.parametrize("rule", sorted(CORPUS_CHECKS))
@every_workflow
def test_every_workflow_passes_the_corpus_rules(path: Path, rule: str) -> None:
    CORPUS_CHECKS[rule](path)


@pytest.mark.parametrize("rule", sorted(GATE_CHECKS))
@every_gate
def test_every_gate_workflow_passes_the_gate_rules(path: Path, rule: str) -> None:
    GATE_CHECKS[rule](path)


@pytest.mark.parametrize("rule", sorted(REQUIRED_CHECKS))
def test_the_required_check_workflow_passes_the_required_rules(rule: str) -> None:
    REQUIRED_CHECKS[rule](WORKFLOWS_DIR / REQUIRED_CHECK_WORKFLOW)


def test_exactly_one_job_in_the_whole_directory_carries_the_required_context() -> None:
    """The per-file rule counts one file; this counts all of them, because a
    second workflow carrying the same job name could satisfy the protection
    in the suite's place."""
    found = required_jobs(WORKFLOW_FILES)

    assert [(name, job_id) for name, job_id, _ in found] == [
        (REQUIRED_CHECK_WORKFLOW, found[0][1] if found else "")
    ], found


def test_every_gate_run_block_is_actually_executed_by_the_swallow_rule() -> None:
    """The executed rule's own anti-vacuity check: the gate workflows contain
    run blocks, and those blocks contain command words the harness stubs."""
    blocks = [
        (path.name, name, block)
        for path in GATE_FILES
        for name, block in run_blocks(load(path))
    ]
    assert blocks, f"no `run:` block in {sorted(GATE_WORKFLOWS)}"
    assert any(command_words(block) for _, _, block in blocks), blocks


def test_the_real_pytest_invocation_survives_the_line_joining() -> None:
    invocations = [
        (path.name, name, line)
        for path in WORKFLOW_FILES
        for name, line in pytest_lines(load(path))
    ]
    assert invocations, "no `pytest` invocation survives `commands()` in any workflow"
    for filename, step, line in invocations:
        assert pytest_arguments(line), (filename, step, line)


def test_the_secret_accessor_pattern_ignores_prose() -> None:
    for prose in (
        "tests/test_no_secrets_committed.py",
        "It uses no repository secret, makes no provider request,",
        "no secret is reachable from here",
        "rejects the substring `secrets` followed by a dot",
    ):
        assert SECRET_REFERENCE.search(prose) is None, prose


# --------------------------------------------------------------------------
# The self-regression suite: proof that the rules above can actually FAIL.
# --------------------------------------------------------------------------

#: The control, in this repository's own shape. It passes every rule, and
#: every bad case below is this text with ONE anchored substitution.
GOOD_WORKFLOW = """\
name: Tests
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  pytest:
    name: Full test suite
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4
        with:
          persist-credentials: false
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install project
        run: |
          python -m pip install -r requirements.txt
      - name: Compile every module
        run: |
          for directory in src scripts tests; do
            test -d "$directory" || { echo "::error::$directory is missing"; exit 1; }
          done
          python -m compileall -q -f src scripts tests
      - name: Run the full test suite
        env:
          PYTHONPATH: src
        run: |
          python -m coverage run -m pytest -q
      - name: Confirm no odds were fetched
        if: always()
        run: |
          echo "This job installs the project and runs unit tests only."
"""

SUITE_LINE = "python -m coverage run -m pytest -q"
SUITE_STEP_HEADER = "      - name: Run the full test suite\n"
COMPILE_LINE = "python -m compileall -q -f src scripts tests"
COMPILE_GUARD = (
    "          for directory in src scripts tests; do\n"
    '            test -d "$directory" || { echo "::error::$directory is missing"; exit 1; }\n'
    "          done\n"
)
JOB_NAME_LINE = "    name: Full test suite\n"
TRIGGER_BLOCK = "on:\n  pull_request:\n"
PERSIST_LINE = "          persist-credentials: false\n"
PYTHON_VERSION_LINE = 'python-version: "3.12"'


def mutate(anchor: str, replacement: str) -> str:
    """GOOD_WORKFLOW with exactly one substitution, or a loud failure."""
    assert anchor in GOOD_WORKFLOW, f"anchor no longer in GOOD_WORKFLOW: {anchor!r}"
    return GOOD_WORKFLOW.replace(anchor, replacement, 1)


def suite_block(*lines: str) -> str:
    """The suite step rewritten to carry `lines` as its run block."""
    body = "".join(f"          {line}\n" for line in lines)
    return mutate(f"          {SUITE_LINE}\n", body)


def workflow(tmp_path: Path, text: str, name: str = "tests.yml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def assert_rejects(check: Callable[[Path], None], path: Path) -> None:
    with pytest.raises(AssertionError):
        check(path)


@pytest.mark.parametrize("rule", sorted(CHECKS), ids=sorted(CHECKS))
def test_the_control_workflow_passes_every_rule(tmp_path: Path, rule: str) -> None:
    CHECKS[rule](workflow(tmp_path, GOOD_WORKFLOW))


#: Every reproduction the audit ran, and the rule that now rejects it. Each
#: entry is (rule, mutated workflow text); `assert_rejects` demands an
#: AssertionError from that rule over that text. The audit's list is the first
#: block; the rest are the rewordings tried against each fix.
REPRODUCTIONS: dict[str, tuple[str, str]] = {
    # -- the audit's reproductions ------------------------------------------
    "echo in place of pytest": (
        "the_required_job_runs_the_whole_suite",
        suite_block('echo "1298 passed"'),
    ),
    "if: false on the suite step": (
        "the_required_job_runs_the_whole_suite",
        mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        if: false\n"),
    ),
    "if ! pytest; then echo; fi": (
        "the_suite_step_fails_when_pytest_fails",
        suite_block(
            "if ! python -m coverage run -m pytest -q; then",
            '  echo "suite failed, continuing"',
            "fi",
        ),
    ),
    "continue-on-error on the suite step": (
        "the_required_job_runs_the_whole_suite",
        mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        continue-on-error: true\n"),
    ),
    "continue-on-error on the job": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    continue-on-error: true\n"),
    ),
    "continue-on-error anywhere in a gate workflow, on a step": (
        "no_step_or_job_continues_on_error",
        mutate("      - name: Install project\n", "      - name: Install project\n        continue-on-error: true\n"),
    ),
    "continue-on-error anywhere in a gate workflow, on the job": (
        "no_step_or_job_continues_on_error",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    continue-on-error: true\n"),
    ),
    "-x": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " -x")),
    "a positional path": (
        "the_required_job_runs_the_whole_suite",
        suite_block(SUITE_LINE + " tests/test_config.py"),
    ),
    "PYTEST_ADDOPTS in the step env": (
        "the_suite_is_never_narrowed",
        mutate("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          PYTEST_ADDOPTS: -x\n"),
    ),
    "the job renamed": (
        "exactly_one_job_carries_the_required_context",
        mutate(JOB_NAME_LINE, "    name: Full test suite (fast)\n"),
    ),
    "the job deleted": (
        "exactly_one_job_carries_the_required_context",
        mutate(JOB_NAME_LINE, ""),
    ),
    # -- rewordings tried against each fix -----------------------------------
    "if: ${{ false }} on the job": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    if: ${{ false }}\n"),
    ),
    "if: github.event_name == 'schedule' on the suite step": (
        "the_required_job_runs_the_whole_suite",
        mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        if: github.event_name == 'schedule'\n"),
    ),
    "pytest || true": (
        "no_run_block_swallows_a_failure",
        suite_block(SUITE_LINE + " || true"),
    ),
    "set +e before pytest": (
        "no_run_block_swallows_a_failure",
        suite_block("set +e", SUITE_LINE, "true"),
    ),
    "trap 'exit 0' ERR": (
        "the_suite_step_fails_when_pytest_fails",
        suite_block("trap 'exit 0' ERR", SUITE_LINE),
    ),
    "pytest in a subshell that is or-ed away": (
        "no_run_block_swallows_a_failure",
        suite_block(f"( {SUITE_LINE} ) || true"),
    ),
    "pytest backgrounded and waited on": (
        "no_run_block_swallows_a_failure",
        suite_block(SUITE_LINE + " &", "wait"),
    ),
    "pytest piped to tee without pipefail": (
        "every_piped_run_block_sets_pipefail",
        suite_block(SUITE_LINE + " | tee suite.log"),
    ),
    "--exitfirst": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --exitfirst")),
    "--maxfail=1": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --maxfail=1")),
    "-k not_slow": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " -k not_slow")),
    "-m fast": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " -m fast")),
    "-qx clustered": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE.replace("-q", "-qx"))),
    "--ignore": (
        "the_required_job_runs_the_whole_suite",
        suite_block(SUITE_LINE + " --ignore=tests/test_no_secrets_committed.py"),
    ),
    "--ignore-glob": (
        "the_required_job_runs_the_whole_suite",
        suite_block(SUITE_LINE + " --ignore-glob='tests/test_no_*'"),
    ),
    "--deselect": (
        "the_required_job_runs_the_whole_suite",
        suite_block(SUITE_LINE + " --deselect tests/test_workflows.py::test_x"),
    ),
    "-c other.ini": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " -c other.ini")),
    "--config-file": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --config-file=ci.ini")),
    "-o testpaths": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " -o testpaths=tests/unit")),
    "--override-ini": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --override-ini=testpaths=x")),
    "--confcutdir": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --confcutdir=/")),
    "--noconftest": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --noconftest")),
    "-p no:something": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " -p no:cacheprovider")),
    "--continue-on-collection-errors": (
        "the_required_job_runs_the_whole_suite",
        suite_block(SUITE_LINE + " --continue-on-collection-errors"),
    ),
    "--runxfail": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --runxfail")),
    "--lf": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --lf")),
    "--co": ("the_required_job_runs_the_whole_suite", suite_block(SUITE_LINE + " --co")),
    "a positional behind a backslash continuation": (
        "the_required_job_runs_the_whole_suite",
        suite_block(SUITE_LINE + " \\", "  tests/test_config.py"),
    ),
    "PYTEST_ADDOPTS at workflow level": (
        "the_suite_is_never_narrowed",
        mutate("permissions:\n", "env:\n  PYTEST_ADDOPTS: -x\npermissions:\n"),
    ),
    "PYTEST_ADDOPTS at job level": (
        "the_suite_is_never_narrowed",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    env:\n      PYTEST_ADDOPTS: -x\n"),
    ),
    "pytest_addopts lower-cased": (
        "the_suite_is_never_narrowed",
        mutate("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          pytest_addopts: -x\n"),
    ),
    "export PYTEST_ADDOPTS in the block": (
        "the_suite_is_never_narrowed",
        suite_block("export PYTEST_ADDOPTS=-x", SUITE_LINE),
    ),
    "PYTEST_ADDOPTS written into GITHUB_ENV by an earlier step": (
        "the_suite_is_never_narrowed",
        mutate(
            "          python -m pip install -r requirements.txt\n",
            "          python -m pip install -r requirements.txt\n"
            '          echo "PYTEST_ADDOPTS=-x" >> "$GITHUB_ENV"\n',
        ),
    ),
    "cd before pytest": (
        "the_required_job_runs_the_whole_suite",
        suite_block("cd tests/unit", "python -m pytest -q"),
    ),
    "working-directory on the suite step": (
        "the_required_job_runs_the_whole_suite",
        mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        working-directory: tests/unit\n"),
    ),
    "shell: bash {0} on the suite step": (
        "no_workflow_overrides_the_shell",
        mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        shell: bash {0}\n"),
    ),
    "shell: pwsh on the suite step": (
        "the_required_job_runs_the_whole_suite",
        mutate(SUITE_STEP_HEADER, SUITE_STEP_HEADER + "        shell: pwsh\n"),
    ),
    "defaults.run.shell on the job": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    defaults:\n      run:\n        shell: bash {0}\n"),
    ),
    "defaults.run.shell on the workflow": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate("permissions:\n", "defaults:\n  run:\n    shell: bash {0}\npermissions:\n"),
    ),
    "the job delegated to a reusable workflow": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate("    runs-on: ubuntu-latest\n", "    uses: octo/ci/.github/workflows/suite.yml@main\n"),
    ),
    "any job delegated to a reusable workflow": (
        "no_job_delegates_to_a_reusable_workflow",
        mutate("    runs-on: ubuntu-latest\n", "    uses: octo/ci/.github/workflows/suite.yml@main\n"),
    ),
    "pytest inside bash -c": (
        "the_required_job_runs_the_whole_suite",
        suite_block("bash -c 'python -m pytest -q; true'"),
    ),
    "pytest inside a multi-line quoted script": (
        "the_required_job_runs_the_whole_suite",
        suite_block("sh -c 'python -m pytest -q", "true'"),
    ),
    "pytest inside python -c": (
        "the_required_job_runs_the_whole_suite",
        suite_block('python -c "import pytest; raise SystemExit(pytest.main([\'-x\']))"'),
    ),
    "pytest behind a wrapper": (
        "the_required_job_runs_the_whole_suite",
        suite_block("xargs python -m pytest -q < /dev/null"),
    ),
    "pytest behind env": (
        "the_required_job_runs_the_whole_suite",
        suite_block("env PYTEST_ADDOPTS=-x python -m pytest -q"),
    ),
    "a Windows runner, whose default shell is pwsh": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate("    runs-on: ubuntu-latest\n", "    runs-on: windows-latest\n"),
    ),
    "a runner named by expression": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate("    runs-on: ubuntu-latest\n", "    runs-on: ${{ vars.RUNNER }}\n"),
    ),
    "a matrix on the job": (
        "the_required_job_is_unconditional_and_undelegated",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    strategy:\n      matrix:\n        python: ['3.12']\n"),
    ),
    "paths on pull_request": (
        "the_pull_request_trigger_is_unfiltered",
        mutate(TRIGGER_BLOCK, "on:\n  pull_request:\n    paths: ['src/**']\n"),
    ),
    "paths-ignore on pull_request": (
        "the_pull_request_trigger_is_unfiltered",
        mutate(TRIGGER_BLOCK, "on:\n  pull_request:\n    paths-ignore: ['tests/**']\n"),
    ),
    "branches on pull_request": (
        "the_pull_request_trigger_is_unfiltered",
        mutate(TRIGGER_BLOCK, "on:\n  pull_request:\n    branches: [release]\n"),
    ),
    "types on pull_request": (
        "the_pull_request_trigger_is_unfiltered",
        mutate(TRIGGER_BLOCK, "on:\n  pull_request:\n    types: [labeled]\n"),
    ),
    "pull_request removed": (
        "the_pull_request_trigger_is_unfiltered",
        mutate(TRIGGER_BLOCK, "on:\n  workflow_dispatch:\n"),
    ),
    "a second job with the same name": (
        "exactly_one_job_carries_the_required_context",
        GOOD_WORKFLOW + "  shadow:\n    name: Full test suite\n    runs-on: ubuntu-latest\n    steps:\n      - run: 'true'\n",
    ),
    "compileall without -f": (
        "the_compile_step_refuses_a_missing_directory",
        mutate(COMPILE_LINE, "python -m compileall -q src scripts tests"),
    ),
    "compileall without the directory guard": (
        "the_compile_step_refuses_a_missing_directory",
        mutate(COMPILE_GUARD, ""),
    ),
    "compileall or-ed away behind the guard": (
        "the_compile_step_refuses_a_missing_directory",
        mutate(COMPILE_LINE, COMPILE_LINE + " || true"),
    ),
    "compileall step deleted": (
        "the_compile_step_refuses_a_missing_directory",
        mutate(COMPILE_GUARD + "          " + COMPILE_LINE + "\n", "          true\n"),
    ),
    "a secret bound into the suite env": (
        "no_workflow_references_a_secret",
        mutate("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          NHL_ODDS_API_KEY: ${{ secrets.NHL_ODDS_API_KEY }}\n"),
    ),
    "the whole secrets context interpolated": (
        "no_workflow_references_a_secret",
        mutate("          PYTHONPATH: src\n", "          PYTHONPATH: src\n          ALL: ${{ toJSON(secrets) }}\n"),
    ),
    "secrets: inherit": (
        "no_workflow_declares_a_secrets_key",
        mutate(JOB_NAME_LINE, JOB_NAME_LINE + "    secrets: inherit\n"),
    ),
    "write permissions": (
        "permissions_are_declared_and_read_only",
        mutate("permissions:\n  contents: read\n", "permissions:\n  contents: write\n"),
    ),
    "persist-credentials left at its default": (
        "checkout_never_persists_credentials",
        mutate(PERSIST_LINE, "          fetch-depth: 1\n"),
    ),
    "an unpinned python version": (
        "python_version_is_pinned_to_an_exact_minor",
        mutate(PYTHON_VERSION_LINE, 'python-version: "3.x"'),
    ),
    "an unquoted python version": (
        "python_version_is_pinned_to_an_exact_minor",
        mutate(PYTHON_VERSION_LINE, "python-version: 3.10"),
    ),
    "no trigger at all": (
        "parses_and_declares_a_trigger",
        mutate("on:\n  pull_request:\n  push:\n    branches: [main]\n", ""),
    ),
}


@pytest.mark.parametrize("label", sorted(REPRODUCTIONS), ids=sorted(REPRODUCTIONS))
def test_every_reproduction_is_rejected(tmp_path: Path, label: str) -> None:
    rule, text = REPRODUCTIONS[label]
    assert_rejects(CHECKS[rule], workflow(tmp_path, text))


def test_every_rule_has_a_reproduction_that_proves_it_fires() -> None:
    """A rule nobody has watched fail is a rule that might not work. Every
    entry in CHECKS must be the named rule of at least one reproduction."""
    exercised = {rule for rule, _ in REPRODUCTIONS.values()}
    unproved = sorted(set(CHECKS) - exercised)

    assert not unproved, f"rules with no rejecting case: {unproved}"
    unknown = sorted(exercised - set(CHECKS))
    assert not unknown, f"reproductions naming a rule that does not exist: {unknown}"


def test_every_reproduction_is_a_real_change_to_the_control() -> None:
    """A mutation whose anchor drifted out of GOOD_WORKFLOW would feed the
    linter the clean text and 'prove' a rejection that never happened."""
    for label, (_, text) in REPRODUCTIONS.items():
        assert text != GOOD_WORKFLOW, f"{label!r} did not change the control"


def test_the_control_is_the_shape_of_the_real_workflow() -> None:
    """The control must stay recognisably `tests.yml`, or the reproductions
    prove things about a workflow this repository does not run."""
    real = load(WORKFLOWS_DIR / REQUIRED_CHECK_WORKFLOW)
    control = yaml.safe_load(GOOD_WORKFLOW)

    assert set(jobs_of(control)) == set(jobs_of(real))
    assert [n for n, _, _ in required_jobs([WORKFLOWS_DIR / REQUIRED_CHECK_WORKFLOW])]
    real_suite = [line for _, line in pytest_lines(real)]
    assert real_suite == [SUITE_LINE], real_suite


def test_the_real_workflow_pins_pytest_in_the_required_job_only() -> None:
    """pytest runs in the required job and nowhere else in the directory, so
    no other workflow's run can be mistaken for the suite."""
    where = [
        (path.name, name)
        for path in WORKFLOW_FILES
        for name, _ in pytest_lines(load(path))
    ]

    assert {filename for filename, _ in where} == {REQUIRED_CHECK_WORKFLOW}, where


# --------------------------------------------------------------------------
# The harness's own guarantees, executed.
# --------------------------------------------------------------------------


def test_nothing_real_runs_under_the_stub_harness(tmp_path: Path) -> None:
    block = (
        "python -c \"open('pwned', 'w').write('x')\"\n"
        "touch also-pwned\n"
        "/bin/sh -c 'touch third'\n"
    )
    result = run_block_under_stubs(block, None, tmp_path)
    assert result.unmodelled == [], (result.unmodelled, result.stderr)
    for name in ("pwned", "also-pwned", "third"):
        assert not (tmp_path / name).exists(), f"{name} was really created"
    escaped = run_block_under_stubs("PATH=/usr/bin:/bin\ntouch escaped\n", None, tmp_path)
    assert escaped.exit_code != 0
    assert not (tmp_path / "escaped").exists()


def test_the_stub_harness_reports_a_command_it_could_not_model(tmp_path: Path) -> None:
    """Indirection through a variable defeats the word scanner — a real hole —
    but not the check, because 'not modelled' is reported as a finding."""
    result = run_block_under_stubs(
        'SUITE="python -m pytest"\neval "$SUITE" || true\n', None, tmp_path
    )
    assert result.unmodelled, result


def test_the_stub_harness_distinguishes_a_top_level_failure(tmp_path: Path) -> None:
    """A failure inside `$(...)` must not count: errexit never sees it, and
    counting it would reject a real step's `echo "$(head -n 1 f)"`."""
    top = run_block_under_stubs("gate\n", None, tmp_path)
    assert top.top_level_failures == ["gate"] and top.exit_code != 0
    nested = run_block_under_stubs('echo "$(gate)"\n', None, tmp_path)
    assert nested.top_level_failures == [] and nested.any_failures == ["gate"]


def test_the_swallow_rule_sees_a_swallow_behind_an_earlier_gate(tmp_path: Path) -> None:
    """With everything failing the block stops at `first`; only `second`
    failing alone reaches the swallow. Both configurations are run."""
    assert swallow_findings("first\nsecond || true\n")
    assert swallow_findings("first\nsecond\n") == []


def test_commands_joins_the_shapes_bash_joins() -> None:
    block = "python -m pytest \\\n  -q \\\n  -k slow\n# a comment with pytest -x in it\necho done ||\n  true\n"
    assert commands(block) == ["python -m pytest -q -k slow", "echo done || true"]


def test_the_disclosed_holes_are_real(tmp_path: Path) -> None:
    """What still gets through, asserted to be exactly as open as described.

    1. An EARLIER step. Every rule here reads the suite step and the job's
       keys; none reads what a step before it did to the runner. A step that
       copies a `python` shim from a tracked file into a directory it
       appends to `$GITHUB_PATH` (a shim spelled inline with the word
       `pytest -x` in it IS caught, by the corpus rule reading every pytest
       token in every block — so the narrowing has to live in a file),
       or `pip install`s a plugin that disables the conftest, or drops a
       `conftest.py` at the repository root, changes what `python -m pytest
       -q` does without changing a character of the suite line. `tests/
       test_the_guards_exist.py` closes the tracked-conftest half of that;
       the runner's filesystem is outside anything a file-reading test can
       see. The pip-install shape is written out below and observed to pass.
    2. A script file beside the suite. `run: bash scripts/ci.sh` before the
       real suite line passes every rule, because the narrowing is in a file
       the rule never opens. It cannot BE the suite step — pytest has to
       appear literally, unquoted, launched by the interpreter — and it
       cannot un-fail the job, because `continue-on-error` is banned. It can
       do anything else.
    3. PYTEST_ADDOPTS assembled from pieces (`PYTEST_ADD""OPTS=-x`, or through
       a variable) is invisible to the token rule. The executed rule does
       not help: the value reaches pytest's environment, not its exit code.
    4. `cd` reached through a sourced file (`. ./enter.sh`) or a variable is
       invisible to the command-word scanner. `working-directory:` and a
       literal `cd`/`pushd` are closed.
    5. The seven operational workflows are held to the corpus rules only. A
       swallowed failure in Gameday Refresh is not a gate failing open — it is
       a card not posting, which the workflow reports as degraded — and it is
       not graded here.

    Closed this round and kept here as a record, because each was open when
    first tried: pytest inside `bash -c '…'` (single- and multi-line), inside
    `python -c "…"`, and behind `xargs` or `env`. All four are now
    reproductions above, rejected by the unquoted-word and launcher rules.
    """
    shimmed = mutate(
        "          python -m pip install -r requirements.txt\n",
        "          python -m pip install -r requirements.txt\n"
        "          python -m pip install conftest-disabling-plugin\n"
        "          mkdir -p shim\n"
        "          cp tools/python-shim shim/python\n"
        '          echo "$PWD/shim" >> "$GITHUB_PATH"\n',
    )
    for rule in CHECKS:
        CHECKS[rule](workflow(tmp_path, shimmed, f"shimmed-{rule}.yml"))

    scripted = suite_block("bash scripts/ci.sh", SUITE_LINE)
    for rule in CHECKS:
        CHECKS[rule](workflow(tmp_path, scripted, f"scripted-{rule}.yml"))

    for assembled in ('export PYTEST_ADD""OPTS=-x', "export PYTEST_${X}ADDOPTS=-x"):
        assert not PYTEST_ADDOPTS_TOKEN.search(assembled), assembled

    sourced = suite_block(". ./enter.sh", SUITE_LINE)
    check_the_required_job_runs_the_whole_suite(workflow(tmp_path, sourced, "sourced.yml"))

    operational = [path for path in WORKFLOW_FILES if path.name not in GATE_WORKFLOWS]
    assert operational, "no operational workflow left to disclose about"
    tolerant = [
        path.name
        for path in operational
        if any("continue-on-error" in mapping for mapping in mappings(load(path)))
    ]
    assert tolerant, "no operational workflow tolerates a failure; widen GATE_WORKFLOWS"
