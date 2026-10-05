"""CLV scored yesterday's capture store when today's fetch failed.

Gameday Refresh restores the `gameday-state` artifact before it does anything
else, and that artifact uploads `data/processed` whole. So whatever an earlier
run left there is already on disk when "Report closing-line value" starts.
The step used to fetch the `closing-lines` branch and, when the fetch did not
succeed, print "No capture store yet" and score the restored store as if it
were today's: a fetch that FAILED took the path of a branch that did not
exist. Confirmed on main d0cc593. Since 2026-10-01 the store is the private
repository cooperross399/nhl-closing-lines (`main`), pulled into the runner's
temp directory.

Since 2026-10-05 (stage two of the movement chain's move) the step's second
source, Line Movement's capture chain, is private too: branch `movement` of
the same repository, pulled by `private_movement_chain.py pull` into
`$RUNNER_TEMP/private-movement-chain` and no longer restored from the public
`line-movement` artifact into `data/processed`. So the finding now has two
shapes, and the step answers both the same way. Anything a restore laid down
in `data/processed` (a store from before 2026-10-01, chain folders from before
the move) is removed before either read, and the report is pointed only at
the two temp directories, so it scores only what this run fetched. For each
source it tells the states apart:

* no NHL_CLOSING_LINES_TOKEN, or nothing there yet: nothing to read, and not
  a fault;
* GitHub could not be reached: a fault that may pass, written to
  `run_degraded.txt` as one sentence naming every source not reached and what
  was scored instead, so the backup is sent for;
* the store is damaged, or GitHub turns the token away: a fault the backup
  would hit again, so the step fails red (exit 2) WITHOUT degrading the run;
* the source was read: the report scores it, and nothing restored.

The chain's own damaged-file exit (pull 2) is not replayed here: the step
pulls into a directory it has just emptied, where the real pull only copies
and never merges, so it cannot exit 2.

These run the step's own `run:` block under `bash -eo pipefail`, with real git,
the real store pull and the real chain pull (its retry pause replaced, which
its `sleep` docstring invites) against one local bare repository standing in
for the private one (the rig in `test_closing_prices_never_reach_the_public_repo.py`).
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

import test_closing_prices_never_reach_the_public_repo as guard
from nhl_betting_lab.closing_lines import CAPTURES_FILENAME
from nhl_betting_lab.config import PROJECT_ROOT
from test_closing_prices_never_reach_the_public_repo import (
    _capture_row,
    _day_file,
    _git,
    _seed_private,
    run_clv_step,
)

#: The guard module's rig, made a fixture of this module too. Assigned rather
#: than imported by name, which pyflakes would read as an unused import.
clv_rig = guard.clv_rig

NOT_READ = "<no store>\n"
NO_CHAIN = "<no chain>\n"

#: The folders Line Movement's chain is laid out in, on `movement` and in
#: `data/processed` alike.
CHAIN_FOLDERS = ("line_movement", "deployment", "line_combinations")

#: What git prints when the network is down, and when GitHub refuses a token.
OFFLINE = ("fatal: unable to access 'https://github.com/cooperross399/nhl-closing-lines.git/':"
           " Could not resolve host: github.com")
REFUSED = "remote: Repository not found.\nfatal: Authentication failed"


@pytest.fixture
def rig(clv_rig):
    """An earlier run's store AND chain restored into data/processed, the
    real chain pull wired in beside the real store pull, and the report
    recording every movement row it was pointed at in `chain_read.txt`."""
    root, work = clv_rig["root"], clv_rig["work"]
    processed = work / "data" / "processed"
    stale = processed / CAPTURES_FILENAME
    stale.write_text(_day_file([_capture_row(book="Yesterday")]), encoding="utf-8")
    clv_rig["stale"] = stale
    for folder in CHAIN_FOLDERS:
        (processed / folder).mkdir()
    (processed / "line_movement" / "2026-10-07.csv").write_text(
        _day_file([_capture_row(book="Yesterday")]), encoding="utf-8")
    for folder in ("deployment", "line_combinations"):
        (processed / folder / "2026-10-07.csv").write_text("restored\n", encoding="utf-8")
    clv_rig["stale_chain"] = [processed / folder for folder in CHAIN_FOLDERS]

    scripts = work / "scripts"
    for name in ("private_movement_chain.py", "restore_state.py"):
        shutil.copy2(PROJECT_ROOT / "scripts" / name, scripts / name)
    shim = root / "chain_pull.py"
    shim.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(scripts)!r})\n"
        "import private_movement_chain as chain\n"
        "chain.sleep = lambda seconds: None\n"
        "raise SystemExit(chain.main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    inner = root / "bin" / "python-rig"
    (root / "bin" / "python").rename(inner)
    wrapper = root / "bin" / "python"
    wrapper.write_text(
        "#!/bin/bash\n"
        'case "$1" in\n'
        f'  scripts/private_movement_chain.py) shift; exec "{sys.executable}" "{shim}" "$@" ;;\n'
        "  scripts/run_closing_line_value.py)\n"
        "    : > chain_read.txt; prev=''\n"
        '    for arg in "$@"; do\n'
        '      if [ "$prev" = --captures-dir ]; then\n'
        '        for day in "$arg"/line_movement/*.csv; do\n'
        '          if [ -f "$day" ]; then cat "$day" >> chain_read.txt; fi\n'
        "        done\n"
        "      fi\n"
        '      prev="$arg"\n'
        "    done\n"
        "    [ -s chain_read.txt ] || echo '<no chain>' > chain_read.txt ;;\n"
        "esac\n"
        f'exec "{inner}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return clv_rig


def _seed_chain(rig, files: dict[str, str]) -> None:
    """Branch `movement` of the stand-in repository, where the chain lives."""
    seed, env = rig["root"] / "seed-chain", rig["env"]
    seed.mkdir()
    _git(["init", "-q", "-b", "movement"], seed, env)
    for name, body in files.items():
        target = seed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(["add", "-A"], seed, env)
    _git(["commit", "-q", "-m", "round"], seed, env)
    _git(["push", "-q", str(rig["bare"]), "HEAD:refs/heads/movement"], seed, env)


def _seed_both(rig) -> None:
    _seed_private(rig["bare"], rig["root"], rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row(book="Todaystore")])})
    _seed_chain(rig, {"line_movement/2026-10-08.csv": _day_file([_capture_row(book="Todaychain")])})


def _git_fails_for_the_chain(rig, stderr: str) -> None:
    """git fails every read of `movement`, and only those: the store on
    `main` is still read."""
    real = shutil.which("git", path=os.environ["PATH"])
    wrapper = rig["root"] / "bin" / "git"
    lines = "".join(f'echo "{line}" >&2; ' for line in stderr.splitlines())
    wrapper.write_text(
        "#!/bin/sh\n"
        f'case "$*" in *refs/heads/movement*) {lines}exit 128;; esac\n'
        f'exec "{real}" "$@"\n'
    )
    wrapper.chmod(0o755)


def _run(rig):
    done, read, degraded = run_clv_step(rig)
    chain_file = rig["work"] / "chain_read.txt"
    chain = chain_file.read_text(encoding="utf-8") if chain_file.is_file() else "<never ran>"
    return done, read, chain, degraded


def _assert_nothing_restored_is_left(rig) -> None:
    assert not rig["stale"].exists(), "the restored store would be uploaded again"
    left = [p.name for p in rig["stale_chain"] if p.exists()]
    assert left == [], f"restored chain folders would be uploaded again: {left}"


def test_no_token_is_a_red_fault_that_reads_nothing_restored(rig) -> None:
    """Since stage two both closing-price sources need the token, so a
    missing secret is not "nothing configured": it is a fault a backup
    would repeat, red without degrading, and the restored copies are still
    removed rather than scored."""
    del rig["env"]["NHL_CLOSING_LINES_TOKEN"]

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 2, done.stdout + done.stderr
    assert read == NOT_READ
    assert chain == NO_CHAIN
    assert degraded == ""
    assert "::error::NHL_CLOSING_LINES_TOKEN is not set" in done.stdout
    assert "store_fault=no-token" in (rig["work"] / "github_output.txt").read_text()
    _assert_nothing_restored_is_left(rig)


def test_a_store_and_chain_with_nothing_yet_is_a_clean_run(rig) -> None:
    """A store with no captures, and no `movement` branch at all."""
    _seed_private(rig["bare"], rig["root"], rig["env"], {"captures/.gitkeep": ""})

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert read == NOT_READ
    assert chain == NO_CHAIN
    assert degraded == ""
    assert "holds nothing yet" in done.stdout
    assert "No private movement chain to read." in done.stdout
    _assert_nothing_restored_is_left(rig)


def test_both_sources_are_read_in_place_of_the_restored_ones(rig) -> None:
    _seed_both(rig)

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "Todaystore" in read and "Yesterday" not in read
    assert "Todaychain" in chain and "Yesterday" not in chain
    assert degraded == ""
    _assert_nothing_restored_is_left(rig)


def test_an_unreachable_repository_degrades_the_run_and_scores_nothing_restored(rig) -> None:
    """The finding: a read that fails is not "nothing yet". The report must
    not score what was restored, and the run says, in one sentence, which
    sources were not reached and what was scored instead."""
    shutil.rmtree(rig["bare"])

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert read == NOT_READ, "the report scored a store this run did not fetch"
    assert chain == NO_CHAIN, "the report scored a chain this run did not fetch"
    assert ("GitHub could not be reached for the private closing-line store "
            "and the private movement chain") in degraded
    assert "scored no closing price today" in degraded
    assert len(degraded.splitlines()) == 1, degraded
    _assert_nothing_restored_is_left(rig)


def test_an_unreachable_chain_degrades_the_run_and_scores_no_restored_chain(rig) -> None:
    """The finding again, for the chain alone: the store is read and scored,
    the chain is not reached, and yesterday's restored chain is not scored in
    its place."""
    _seed_both(rig)
    _git_fails_for_the_chain(rig, OFFLINE)

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "Todaystore" in read
    assert chain == NO_CHAIN, "the report scored a chain this run did not fetch"
    assert "GitHub could not be reached for the private movement chain," in degraded
    assert "closing-line store" not in degraded
    assert "scored the store alone today" in degraded
    assert len(degraded.splitlines()) == 1, degraded
    _assert_nothing_restored_is_left(rig)


def _damaged(rig) -> None:
    good = _day_file([_capture_row(book="Today")])
    _seed_private(rig["bare"], rig["root"], rig["env"],
                  {"captures/2026-10-08.csv": good + 'x,"unterminated\n'})


def _token_turned_away(rig) -> None:
    """GitHub answers, and refuses the token, for both sources."""
    _seed_both(rig)
    real = shutil.which("git", path=os.environ["PATH"])
    wrapper = rig["root"] / "bin" / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'case "$1" in ls-remote|fetch) echo "remote: Repository not found." >&2;'
        ' echo "fatal: Authentication failed" >&2; exit 128;; esac\n'
        f'exec "{real}" "$@"\n'
    )
    wrapper.chmod(0o755)


@pytest.mark.parametrize(
    "fault",
    [pytest.param(_damaged, id="store-damaged"),
     pytest.param(_token_turned_away, id="token-turned-away")],
)
def test_a_fault_a_backup_would_repeat_fails_red_without_degrading(rig, fault) -> None:
    """A degraded run sends for the backup, which buys prices again and would
    meet the same damaged file or the same rejected token. So the step exits
    2, which "Report the outcome" fails the run on, and degrades nothing."""
    fault(rig)

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 2, done.stdout + done.stderr
    assert read == NOT_READ, "the report scored a store this run did not fetch"
    assert chain == NO_CHAIN, "the report scored a chain this run did not fetch"
    assert degraded == ""
    assert "::error::The private closing-line store" in done.stdout
    _assert_nothing_restored_is_left(rig)


def test_a_chain_that_turns_the_token_away_fails_red_without_degrading(rig) -> None:
    """The chain's refusal is the same kind of fault as the store's: red,
    nothing degraded, and the store this run did read is still scored."""
    _seed_both(rig)
    _git_fails_for_the_chain(rig, REFUSED)

    done, read, chain, degraded = _run(rig)

    assert done.returncode == 2, done.stdout + done.stderr
    assert "Todaystore" in read
    assert chain == NO_CHAIN, "the report scored a chain this run did not fetch"
    assert degraded == ""
    assert "::error::The private movement chain turned NHL_CLOSING_LINES_TOKEN away" in done.stdout
    _assert_nothing_restored_is_left(rig)
