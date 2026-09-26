"""A Gameday Refresh dispatched on a feature branch published its card.

Nothing in `gameday-refresh.yml` read `github.ref`. So a run dispatched on a
branch -- code nobody had reviewed -- went all the way out of the runner:

* "Post the card to the operating home" commented its card on the operating
  home issue, which emails everyone watching it, as if it were today's card;
* "Publish the card to the card-feed branch" committed `latest_status.json`
  with today's date and `degraded: false`, and the branch run's own
  `forward_evidence.csv`, to card-feed.

Main's next scheduled precheck then read card-feed, found today's card
"already published and clean", and stood the whole run down. Main's restore
takes state only from runs on main (`scripts/restore_state.py --branch
main`), so the branch run's frozen snapshot never entered main's chain: that
day's opinions were missing from the forward ledger for good, and the board
was built from stale state. The README and `restore_state.py` both say "a
run dispatched on a feature branch is never a source"; card-feed made it one.

Now every step that writes outside the run is gated on the default branch,
the same comparison Closing Lines makes for its hand-off, while every step
that builds the card still runs on any ref -- a branch dispatch is still a
full rehearsal, it just publishes nothing. And, because branches cut before
this fix still carry the unguarded workflow, the status line now names the
ref that wrote it and the precheck counts only one written by the default
branch.

The `if:` conditions are evaluated here, not pattern-matched, by a small
evaluator for the subset of GitHub's expression language this file uses; it
refuses any name or function it was not given, so a condition that grows a
new term fails loudly instead of being read as true.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import (
    _bash,
    _git_env,
    _outputs,
    _precheck,
    _publish,
    _render,
)

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"
DAY = "2026-10-08"
MAIN = "refs/heads/main"
BRANCH = "refs/heads/fix/some-unreviewed-change"

POST = "Post the card to the operating home"
PUBLISH = "Publish the card to the card-feed branch"

# Anything in a run block that writes somewhere a later run, or a person,
# can see. Artifacts are scoped to the run and are read back only from main
# (scripts/restore_state.py), so upload-artifact is not on this list.
OUTWARD = re.compile(
    r"\bgit\s+push\b"
    r"|\bgh\s+issue\s+(?:comment|create|pin|edit|close|reopen|delete)\b"
    r"|\bgh\s+pr\s+(?:create|comment|edit|merge|close|review)\b"
    r"|\bgh\s+release\b"
    r"|\bgh\s+api\b[^\n]*(?:-X|--method)\s*(?:POST|PUT|PATCH|DELETE)"
    r"|\bgh\s+workflow\s+run\b"
)


# --------------------------------------------------------------------------
# A small evaluator for the `if:` expressions this workflow writes.
# --------------------------------------------------------------------------

TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')"
    r"|(?P<op>==|!=|&&|\|\||!|\(|\)|,)"
    r"|(?P<name>[A-Za-z_][\w.\-]*))"
)


def _format(template: str, *args: object) -> str:
    return re.sub(r"\{(\d+)\}", lambda m: str(args[int(m.group(1))]), template)


FUNCTIONS = {
    "always": lambda: True,
    "success": lambda: True,
    "failure": lambda: False,
    "cancelled": lambda: False,
    "format": _format,
}


def _condition(node: dict) -> str:
    """The `if:` as written; a step with none runs on success()."""
    if "if" not in node:
        return "success()"
    raw = str(node["if"]).strip()
    if raw.startswith("${{") and raw.endswith("}}"):
        raw = raw[3:-2].strip()
    return raw


def evaluate(expression: str, context: dict[str, object]) -> bool:
    pieces: list[str] = []
    position = 0
    expression = expression.strip()
    while position < len(expression):
        match = TOKEN.match(expression, position)
        if not match or match.end() == position:
            raise AssertionError(f"cannot read {expression[position:]!r}")
        position = match.end()
        if match.group("str") is not None:
            pieces.append(repr(match.group("str")[1:-1].replace("''", "'")))
        elif match.group("op") is not None:
            op = match.group("op")
            pieces.append({"&&": " and ", "||": " or ", "!": " not "}.get(op, op))
        else:
            name = match.group("name")
            following = expression[position:].lstrip()
            if following.startswith("("):
                if name not in FUNCTIONS:
                    raise AssertionError(f"unknown function {name}() in {expression!r}")
                pieces.append(f"_fn_{name}")
            elif name in ("true", "false"):
                pieces.append(name.capitalize())
            elif name in context:
                pieces.append(repr(context[name]))
            else:
                raise AssertionError(f"no value for {name} in {expression!r}")
    scope = {f"_fn_{name}": fn for name, fn in FUNCTIONS.items()}
    return bool(eval(" ".join(pieces), {"__builtins__": {}}, scope))  # noqa: S307


def _context(ref: str) -> dict[str, object]:
    return {
        "github.ref": ref,
        "github.event.repository.default_branch": "main",
        "github.event_name": "workflow_dispatch",
        "inputs.skip_provider_fetch": False,
        "needs.precheck.outputs.already": "false",
    }


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _refresh_steps() -> list[dict]:
    return _doc()["jobs"]["refresh"]["steps"]


def _writers() -> dict[str, dict]:
    return {
        step.get("name", step.get("id", "?")): step
        for job in _doc()["jobs"].values()
        for step in job.get("steps", [])
        if OUTWARD.search(step.get("run", ""))
    }


# --------------------------------------------------------------------------
# The gate itself.
# --------------------------------------------------------------------------

def test_the_steps_that_write_outside_the_run_are_the_ones_named() -> None:
    """The detector below is not vacuous: it finds both known writers and
    nothing it has not been told about."""
    assert sorted(_writers()) == sorted([POST, PUBLISH])


@pytest.mark.parametrize("name", [POST, PUBLISH])
def test_a_branch_run_skips_every_outward_write(name: str) -> None:
    step = _writers()[name]
    assert evaluate(_condition(step), _context(BRANCH)) is False, (
        f"{name!r} would run on a feature branch: {_condition(step)!r}"
    )


@pytest.mark.parametrize("name", [POST, PUBLISH])
def test_the_default_branch_still_writes_even_after_a_failure(name: str) -> None:
    """The gate is added to `always()`, not in place of it: a degraded run
    on main must still post and still publish, or the silence goes back to
    meaning nothing."""
    step = _writers()[name]
    condition = _condition(step)
    assert evaluate(condition, _context(MAIN)) is True
    assert re.search(r"\balways\(\)", condition), condition


def test_a_branch_run_is_still_a_full_rehearsal() -> None:
    """Only the outward writes are skipped. Everything that fetches, fits,
    builds, gates and records the card still runs on a branch."""
    writers = set(_writers())
    skipped_on_branch = [
        step.get("name", step.get("id", "?"))
        for step in _refresh_steps()
        if not evaluate(_condition(step), _context(BRANCH))
    ]
    assert sorted(skipped_on_branch) == sorted(writers)
    assert evaluate(_condition(_doc()["jobs"]["refresh"]), _context(BRANCH))


# --------------------------------------------------------------------------
# End to end: main's scheduled precheck after a branch run.
# --------------------------------------------------------------------------

def _branch_run_then_main_precheck(tmp_path: Path) -> str:
    """A clean branch run followed by main's 13:30 scheduled precheck, with
    each step running only if its own `if:` says it would."""
    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "data" / "outputs").mkdir(parents=True)
    (work / "card_comment.md").write_text("a card built by unreviewed code\n")
    (work / "data" / "processed" / "forward_evidence.csv").write_text("branch,rows\n")
    step = _writers()[PUBLISH]
    if evaluate(_condition(step), _context(BRANCH)):
        _publish(work, tmp_path, "false", DAY, ref=BRANCH)
    return _precheck(tmp_path, DAY)


def test_a_branch_run_does_not_stand_main_down(tmp_path: Path) -> None:
    assert _branch_run_then_main_precheck(tmp_path) == "false"


def test_a_clean_card_published_by_main_still_stands_the_backup_down(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    (work / "data" / "outputs").mkdir(parents=True)
    (work / "card_comment.md").write_text("card\n")
    status = _publish(work, tmp_path, "false", DAY, ref=MAIN)
    assert status["ref"] == MAIN
    assert _precheck(tmp_path, DAY) == "true"


# --------------------------------------------------------------------------
# Belt and braces: branches cut before the gate still carry the old publish.
# --------------------------------------------------------------------------

def _push_status(tmp_path: Path, status: str) -> None:
    """Write card-feed the way an older copy of the workflow would have."""
    env = _git_env(tmp_path, DAY)
    work = tmp_path / "old"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    (work / "s.json").write_text(status, encoding="utf-8")
    block = (
        'BLOB=$(git hash-object -w s.json)\n'
        'TREE=$(printf "100644 blob %s\\tlatest_status.json\\n" "$BLOB" | git mktree)\n'
        'export GIT_AUTHOR_NAME=a GIT_AUTHOR_EMAIL=a@b GIT_COMMITTER_NAME=a GIT_COMMITTER_EMAIL=a@b\n'
        'COMMIT=$(git commit-tree "$TREE" -m old)\n'
        'git push "https://x-access-token:x@github.com/o/r" "$COMMIT:refs/heads/card-feed"\n'
    )
    result = _bash(block, work, env)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("status", [
    # The unguarded publish, dispatched on a branch cut before this fix:
    # no `ref` at all.
    '{"date": "%s", "degraded": "false", "decision": "post"}' % DAY,
    # A status that names a ref, but not the default branch.
    '{"date": "%s", "degraded": "false", "ref": "%s"}' % (DAY, BRANCH),
])
def test_the_precheck_counts_only_a_card_the_default_branch_published(
    tmp_path: Path, status: str
) -> None:
    _push_status(tmp_path, status)
    assert _precheck(tmp_path, DAY) == "false"


def test_the_precheck_reads_the_status_line_it_is_given(tmp_path: Path) -> None:
    """The control for the test above: the same hand-written status with the
    default branch's ref does stand the backup down."""
    _push_status(tmp_path, '{"date": "%s", "degraded": "false", "ref": "%s"}' % (DAY, MAIN))
    assert _precheck(tmp_path, DAY) == "true"


def test_the_precheck_is_not_fooled_by_a_different_default_branch(
    tmp_path: Path,
) -> None:
    """The comparison is against the repository's default branch, read at
    run time, not a hard-coded `main`."""
    _push_status(tmp_path, '{"date": "%s", "degraded": "false", "ref": "%s"}' % (DAY, MAIN))
    env = _git_env(tmp_path, DAY)
    checkout = tmp_path / "precheck-trunk"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=checkout, env=env, check=True)
    output = tmp_path / "trunk_output"
    output.write_text("", encoding="utf-8")
    feed = next(
        step for step in _doc()["jobs"]["precheck"]["steps"] if step.get("id") == "feed"
    )
    block = _render(feed["run"], {
        "github.event_name": "schedule", "github.repository": "o/r",
        "github.event.repository.default_branch": "trunk",
    })
    result = _bash(block, checkout, {**env, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    assert _outputs(output)["already"] == "false"


def test_the_evaluator_refuses_what_it_was_not_given() -> None:
    with pytest.raises(AssertionError):
        evaluate("github.head_ref == 'x'", _context(MAIN))
    with pytest.raises(AssertionError):
        evaluate("contains(github.ref, 'main')", _context(MAIN))
    assert evaluate("always() && !(github.ref == 'x')", _context(MAIN)) is True
