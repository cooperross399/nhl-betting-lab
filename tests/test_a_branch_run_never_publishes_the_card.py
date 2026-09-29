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
the same comparison Closing Lines makes for its hand-off, with a schedule let
through first because a schedule only ever runs on the default branch and
`github.event.repository` has never been seen populated on a cron run here.
Every step that builds the card still runs on any ref -- a branch dispatch is
still a full rehearsal, it just publishes nothing -- and "Report the outcome"
reads a skipped publish as a failure only where the publish was meant to
run. Because branches cut before this fix still carry the unguarded
workflow, the status line now names the ref that wrote it and the precheck
counts only one written by its own (default-branch) ref.

The `if:` conditions are evaluated here, not pattern-matched, by a small
evaluator for the subset of GitHub's expression language this file uses; it
refuses any name or function it was not given, so a condition that grows a
new term fails loudly instead of being read as true.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import (
    _card_on_disk,
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
REPORT = "Report the outcome"

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


def _functions(*, failed: bool) -> dict:
    """The status functions as the runner answers them: `failed` is a run
    in which an earlier step has already failed the job."""
    return {
        "always": lambda: True,
        "success": lambda: not failed,
        "failure": lambda: failed,
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


def evaluate(expression: str, context: dict[str, object], *,
             failed: bool = False) -> bool:
    functions = _functions(failed=failed)
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
                if name not in functions:
                    raise AssertionError(f"unknown function {name}() in {expression!r}")
                pieces.append(f"_fn_{name}")
            elif name in ("true", "false"):
                pieces.append(name.capitalize())
            elif name in context:
                pieces.append(repr(context[name]))
            else:
                raise AssertionError(f"no value for {name} in {expression!r}")
    scope = {f"_fn_{name}": fn for name, fn in functions.items()}
    return bool(eval(" ".join(pieces), {"__builtins__": {}}, scope))  # noqa: S307


def _context(ref: str, *, event: str = "workflow_dispatch",
             default_branch: str = "main") -> dict[str, object]:
    """`default_branch=""` is `github.event.repository` missing: the runner
    reads a missing property as null, and format() writes null as ''."""
    return {
        "github.ref": ref,
        "github.event.repository.default_branch": default_branch,
        "github.event_name": event,
        "inputs.skip_provider_fetch": False,
        "needs.precheck.result": "success",
        "needs.precheck.outputs.already": "false",
    }


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _refresh_steps() -> list[dict]:
    return _doc()["jobs"]["refresh"]["steps"]


def _named(name: str) -> dict:
    found = [step for step in _refresh_steps() if step.get("name") == name]
    assert len(found) == 1, name
    return found[0]


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


@pytest.mark.parametrize("failed", [False, True], ids=["clean", "after-a-failure"])
@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
@pytest.mark.parametrize("name", [POST, PUBLISH])
def test_the_default_branch_still_writes_even_after_a_failure(
    name: str, event: str, failed: bool
) -> None:
    """The gate is added to `always()`, not in place of it: a degraded run
    on main must still post and still publish, or the silence goes back to
    meaning nothing. Evaluated with an earlier step failed as well, so a
    `success()` or `!failure()` slipped in beside the ref fails here."""
    condition = _condition(_writers()[name])
    assert evaluate(condition, _context(MAIN, event=event), failed=failed) is True


@pytest.mark.parametrize("failed", [False, True], ids=["clean", "after-a-failure"])
@pytest.mark.parametrize("name", [POST, PUBLISH])
def test_a_schedule_publishes_with_no_repository_in_its_event(
    name: str, failed: bool
) -> None:
    """If `github.event.repository` is empty on a cron run, the ref test
    alone reads `refs/heads/` and every scheduled run would skip the post
    and the publish from opening night, with the backup then firing every
    afternoon. A schedule only ever runs on the default branch, so it goes
    through without reading the repository at all."""
    condition = _condition(_writers()[name])
    context = _context(MAIN, event="schedule", default_branch="")
    assert evaluate(condition, context, failed=failed) is True


def test_the_post_and_the_publish_share_one_condition() -> None:
    """"Report the outcome" decides whether a skipped publish is a failure
    by this condition; two copies that drift apart would make it lie."""
    assert _condition(_writers()[POST]) == _condition(_writers()[PUBLISH])


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
# "Report the outcome": a skip is a failure only where the publish should run.
# --------------------------------------------------------------------------

def _report(context: dict[str, object], cardfeed: str, tmp_path: Path
            ) -> subprocess.CompletedProcess:
    block = _render(_named(REPORT)["run"], {
        "steps.final.outputs.degraded": "false",
        "steps.prices.outputs.empty_slate": "false",
        "steps.cardfeed.outcome": cardfeed,
        "steps.settle.outcome": "success",
        "steps.rebuild.outcome": "success",
        "steps.clv.outcome": "success",
        "github.event_name": str(context["github.event_name"]),
        "github.ref": str(context["github.ref"]),
        "github.event.repository.default_branch":
            str(context["github.event.repository.default_branch"]),
    })
    tmp_path.mkdir(parents=True, exist_ok=True)
    return _bash(block, tmp_path, dict(os.environ))


def test_a_clean_branch_rehearsal_is_a_green_run(tmp_path: Path) -> None:
    """The publish was skipped because the gate worked, not because it
    failed; a rehearsal that always finished red would teach the reader to
    ignore red."""
    report = _report(_context(BRANCH), "skipped", tmp_path)
    assert report.returncode == 0, report.stdout
    assert "rehearsal" in report.stdout
    assert "card-feed branch" not in "".join(
        line for line in report.stdout.splitlines() if line.startswith("::error::")
    )


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_a_skipped_publish_on_the_default_branch_is_still_a_failure(
    tmp_path: Path, event: str
) -> None:
    report = _report(_context(MAIN, event=event), "skipped", tmp_path)
    assert report.returncode != 0, report.stdout
    assert "card-feed" in report.stdout


def test_a_dispatch_that_cannot_read_the_default_branch_is_red(tmp_path: Path) -> None:
    """Both steps skipped (the ref test read `refs/heads/`), and that must
    not pass as a rehearsal: nothing was delivered."""
    context = _context(MAIN, default_branch="")
    assert not evaluate(_condition(_writers()[PUBLISH]), context)
    report = _report(context, "skipped", tmp_path)
    assert report.returncode != 0, report.stdout
    assert "default branch" in report.stdout


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
@pytest.mark.parametrize("ref", [MAIN, BRANCH])
@pytest.mark.parametrize("default_branch", ["main", "trunk", ""])
def test_the_outcome_reads_a_skip_exactly_where_the_gate_skips(
    tmp_path: Path, event: str, ref: str, default_branch: str
) -> None:
    """Across every combination: when the publish's own condition says it
    runs, a skip there is red; when it says a branch dispatch skips, a skip
    is green; and the one ambiguous case, a dispatch with no default branch
    to read, is red rather than read as a rehearsal."""
    context = _context(ref, event=event, default_branch=default_branch)
    should_run = evaluate(_condition(_writers()[PUBLISH]), context)
    unreadable = event != "schedule" and default_branch == ""
    report = _report(context, "skipped", tmp_path / "w")
    assert (report.returncode != 0) == (should_run or unreadable), report.stdout
    published = _report(context, "success", tmp_path / "ok")
    assert (published.returncode != 0) == unreadable, published.stdout


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
    _card_on_disk(work, DAY)
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
    _card_on_disk(work, DAY)
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


def _precheck_as(tmp_path: Path, run_ref: str) -> tuple[str, str]:
    """The precheck on a schedule whose own ref is `run_ref`. It is given no
    `github.event.repository` at all, and _render refuses an expression it
    was not given, so reading it would fail here."""
    env = _git_env(tmp_path, DAY)
    checkout = tmp_path / f"precheck-{abs(hash(run_ref))}"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=checkout, env=env, check=True)
    output = tmp_path / f"out-{abs(hash(run_ref))}"
    output.write_text("", encoding="utf-8")
    feed = next(
        step for step in _doc()["jobs"]["precheck"]["steps"] if step.get("id") == "feed"
    )
    block = _render(feed["run"], {
        "github.event_name": "schedule", "github.repository": "o/r",
        "github.ref": run_ref,
    })
    result = _bash(block, checkout, {**env, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    return _outputs(output)["already"], result.stdout


@pytest.mark.parametrize("status", [
    # The unguarded publish, dispatched on a branch cut before this fix:
    # no `ref` at all.
    '{"date": "%s", "degraded": "false", "decision": "post"}' % DAY,
    # A status that names a ref, but not the default branch.
    '{"date": "%s", "card_day": "%s", "degraded": "false", "ref": "%s"}'
    % (DAY, DAY, BRANCH),
])
def test_the_precheck_counts_only_a_card_the_default_branch_published(
    tmp_path: Path, status: str
) -> None:
    _push_status(tmp_path, status)
    assert _precheck(tmp_path, DAY) == "false"


def test_the_precheck_reads_the_status_line_it_is_given(tmp_path: Path) -> None:
    """The control for the test above: the same hand-written status with the
    default branch's ref does stand the backup down."""
    _push_status(tmp_path, '{"date": "%s", "card_day": "%s", "degraded": "false", "ref": "%s"}' % (DAY, DAY, MAIN))
    assert _precheck(tmp_path, DAY) == "true"


def test_the_precheck_compares_against_its_own_ref(tmp_path: Path) -> None:
    """A schedule runs on the default branch, whatever it is called; the
    comparison is against that ref, not a hard-coded `main`."""
    _push_status(tmp_path, '{"date": "%s", "card_day": "%s", "degraded": "false", "ref": "%s"}' % (DAY, DAY, MAIN))
    assert _precheck_as(tmp_path, "refs/heads/trunk")[0] == "false"
    assert _precheck_as(tmp_path, MAIN)[0] == "true"


def test_a_precheck_that_cannot_read_its_ref_runs_and_says_so(tmp_path: Path) -> None:
    """Failing the precheck would skip the refresh job and leave the day with
    no card; an empty ref must also never match a status that names none."""
    _push_status(tmp_path, '{"date": "%s", "degraded": "false"}' % DAY)
    already, stdout = _precheck_as(tmp_path, "")
    assert already == "false"
    assert "::warning::" in stdout


def test_the_evaluator_refuses_what_it_was_not_given() -> None:
    with pytest.raises(AssertionError):
        evaluate("github.head_ref == 'x'", _context(MAIN))
    with pytest.raises(AssertionError):
        evaluate("contains(github.ref, 'main')", _context(MAIN))
    assert evaluate("always() && !(github.ref == 'x')", _context(MAIN)) is True
    assert evaluate("always() && success()", _context(MAIN), failed=True) is False
    assert evaluate("always() && !failure()", _context(MAIN), failed=True) is False
