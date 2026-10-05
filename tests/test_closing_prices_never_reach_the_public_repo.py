"""The closing-line store is never written to this repository, which is public.

The Odds API's terms forbid redistributing their data as downloadable files
that serve as raw data, and anything on a public repository is one: a branch,
a release, a Pages site, an artifact. Closing Lines was disabled on
2026-09-25 for exactly that (#126): it was about to publish its store on a
`closing-lines` branch here. Cooper's decision, 2026-10-01: closing-line data
is never published publicly, and CLV still works. The store now lives in the
private repository cooperross399/nhl-closing-lines.

What this module holds, by what the code does rather than what a comment says:

* **A push.** Closing Lines holds no write grant on this repository and runs
  no `git push` of its own; its only writer is
  `scripts/private_closing_store.py push`, which refuses this repository by
  name and refuses any target the GitHub API does not call private. The
  workflows that do push here (the card-feed publish, and Experiment
  Refresh's verdict branches) commit no capture store, and the card-feed
  publish commits a fixed list of five files.
* **An artifact.** No upload names the capture store or the old hand-off
  artifact, and the set of uploads that can carry captured prices at all is
  pinned to the known carriers, so a new one fails here. Gameday Refresh
  uploads `data/processed` whole as `gameday-state`, so its CLV step is
  replayed against a real private store holding a sentinel price, and the
  workspace is searched for it afterwards.
* **The published report.** The CLV report goes to card-feed and to the
  `gameday-reports` artifact, so it is built from captures carrying sentinel
  prices and books, and must print none of them.

**The movement chain too, since stage two (2026-10-05).** Line Movement's
capture chain, a superset of the closing-line store, lived in the public
`line-movement` artifact until then; it now lives only on the private store's
`movement` branch, and no Line Movement upload names a store folder. A round
whose private push fails is kept only sealed (AES-256, Cooper's key), as one
file in the runner's temp directory. What remains on the pinned list below
is bought history and a run's staging quotes, which predate #286, and the
public artifacts uploaded before stage two until they expire.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab.config import PROJECT_ROOT
from test_a_blocked_card_is_a_degraded_run import _bash, _render

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import private_closing_store as store  # noqa: E402

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
PRIVATE = store.PRIVATE_REPO
PUBLIC = store.PUBLIC_REPO

#: A price, a line and a book no real capture carries, so finding any of
#: them anywhere they should not be is a leak and never a coincidence.
SENTINEL_BOOK = "Zzsentinelbook"
SENTINEL_ODDS = 1777.0
SENTINEL_LINE = 17.5


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _steps(workflow: dict) -> list[dict]:
    return [s for job in workflow["jobs"].values() for s in job.get("steps", [])]


def _all_workflows() -> list[Path]:
    found = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    assert found
    return found


# --- A push --------------------------------------------------------------


def test_closing_lines_holds_no_write_grant_here() -> None:
    workflow = _load("closing-lines.yml")
    assert workflow["permissions"] == {"contents": "read"}


def test_closing_lines_pushes_nothing_itself() -> None:
    text = (WORKFLOWS / "closing-lines.yml").read_text(encoding="utf-8")
    assert not re.search(r"\bgit push\b", text)
    assert "x-access-token:${GH_TOKEN}" not in text


def test_the_only_writer_is_the_private_store_script_with_its_defaults() -> None:
    """No `--remote` or `--repo` in the workflow: the target is the
    script's own constant, which a test below pins to the private repo."""
    (publish,) = [
        s for s in _steps(_load("closing-lines.yml"))
        if "private_closing_store.py" in str(s.get("run", ""))
    ]
    run = publish["run"].strip()
    assert run == "python scripts/private_closing_store.py push --processed-dir data/processed"
    assert publish["env"]["NHL_CLOSING_LINES_TOKEN"] == "${{ secrets.NHL_CLOSING_LINES_TOKEN }}"


def test_the_store_is_the_private_repository_and_never_this_one() -> None:
    assert PRIVATE == "cooperross399/nhl-closing-lines"
    assert PUBLIC == "cooperross399/nhl-betting-lab"
    assert PRIVATE != PUBLIC


@pytest.mark.parametrize("path", _all_workflows(), ids=lambda p: p.name)
def test_no_push_to_this_repository_carries_a_capture_store(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if re.search(r"\bgit push\b", line):
            assert "closing" not in line.lower(), line
    # Every file a plumbing commit puts in a tree, by name.
    committed = set(re.findall(r"blob %s\\t([A-Za-z0-9_.\-]+)", text))
    for name in committed:
        assert "capture" not in name.lower(), name
        assert name != cl.CAPTURES_FILENAME
    if path.name == "gameday-refresh.yml":
        assert committed == {
            "latest_card_comment.md",
            "latest_status.json",
            "latest_forward_evidence.md",
            "latest_closing_line_value.md",
            "forward_evidence.csv",
        }


# --- An artifact ---------------------------------------------------------


@pytest.mark.parametrize("path", _all_workflows(), ids=lambda p: p.name)
def test_no_artifact_carries_a_capture_store(path: Path) -> None:
    for step in _steps(_load(path.name)):
        if not str(step.get("uses", "")).startswith("actions/upload-artifact"):
            continue
        given = step.get("with", {})
        assert given.get("name") != "closing-line-captures", path.name
        for entry in str(given.get("path", "")).split():
            # The aggregate report, data/outputs/closing_line_value.md, may
            # travel; the store may not.
            assert "closing_line_captures" not in entry, (path.name, entry)
            assert "private-closing-store" not in entry, (path.name, entry)
            assert "RUNNER_TEMP" not in entry, (path.name, entry)


def test_line_movement_uploads_no_store_folder() -> None:
    """Stage two: the chain's only home is the private repository. No Line
    Movement upload names a store folder or data/processed at all; the
    sealed fallback is one encrypted file in the runner's temp directory."""
    for step in _steps(_load("line-movement.yml")):
        if not str(step.get("uses", "")).startswith("actions/upload-artifact"):
            continue
        for entry in str(step["with"].get("path", "")).split():
            assert "data/processed" not in entry and not _can_carry_prices(entry), entry


#: Every upload that can carry captured or bought prices, and why it is on
#: the list. A new carrier fails `test_the_uploads_that_carry_prices_are_the_known_ones`.
#: These are KNOWN, not safe: they carry bought history or a run's staging
#: quotes, which predate #286. (Line Movement's two chain uploads left this
#: list in stage two, 2026-10-05.)
KNOWN_PRICE_CARRIERS = {
    ("gameday-refresh.yml", "gameday-state"),
    ("historical-props-purchase.yml", "gameday-state"),
    ("historical-props-purchase.yml", "historical-props"),
    ("venue-probe.yml", "venue-probe"),
}
PRICE_PATHS = (
    "data/processed/line_movement",
    "data/processed/closing_line_captures",
    "data/processed/forward_evidence",
    "data/archive",
    "data/staging",
    "data/raw/historical_props",
    "data/raw/historical_team_prices",
    "data/processed/historical_",
)
WORKSPACE_PREFIXES = ("${{ github.workspace }}/", "$GITHUB_WORKSPACE/", "${GITHUB_WORKSPACE}/")


def _normalise(entry: str) -> str:
    """One spelling per path: no workspace prefix, no ./, no /. or //."""
    entry = entry.strip()
    for prefix in WORKSPACE_PREFIXES:
        if entry.startswith(prefix):
            entry = entry[len(prefix):]
    normal = os.path.normpath(entry) if entry else entry
    return "." if normal in ("", ".") else normal


def _can_carry_prices(entry: str) -> bool:
    """A whole data directory, a glob outside the report folders, or a path
    under one of the known price locations, however it is spelled."""
    entry = _normalise(entry)
    if entry in {".", "data", "data/processed", "data/raw"}:
        return True
    if any(c in entry for c in "*?[") and not entry.startswith(("data/outputs/", "dist/")):
        return True
    return entry.startswith(PRICE_PATHS)


def test_the_uploads_that_carry_prices_are_the_known_ones() -> None:
    carriers = set()
    for path in _all_workflows():
        for step in _steps(_load(path.name)):
            # upload-pages-artifact too: the Pages site is public.
            if not str(step.get("uses", "")).startswith(
                ("actions/upload-artifact", "actions/upload-pages-artifact")
            ):
                continue
            entries = str(step.get("with", {}).get("path", "")).split()
            if any(_can_carry_prices(e) for e in entries):
                carriers.add((path.name, str(step["with"].get("name", "github-pages"))))
    assert carriers == KNOWN_PRICE_CARRIERS


def test_the_carrier_test_sees_a_whole_directory_or_a_glob() -> None:
    for entry in ("data/processed", "data/processed/", "data", ".", "./",
                  "./data/processed", "data/processed/.", "data//processed",
                  "${{ github.workspace }}/data/processed/line_movement",
                  "$GITHUB_WORKSPACE/data/processed",
                  "data/processed/*.csv", "data/processed/closing_line_capture?.csv",
                  "data/processed/[cl]*", "data/**/x.csv",
                  "data/processed/line_movement", "./data/processed/line_movement",
                  "data/processed/closing_line_captures.csv",
                  "data/archive/priced_snapshots", "data/processed/forward_evidence.csv",
                  "data/staging"):
        assert _can_carry_prices(entry), entry
    for entry in ("data/outputs/closing_line_value.md", "data/processed/deployment",
                  "dist/data/history"):
        assert not _can_carry_prices(entry), entry


def _git_add_arguments(text: str) -> list[list[str]]:
    """The arguments of every `git add`, backslash-continued lines joined."""
    joined = re.sub(r"\\\n\s*", " ", text)
    found = []
    for line in joined.splitlines():
        match = re.search(r"\bgit add\b(.*)", line)
        if match:
            words = [w for w in match.group(1).split() if not w.startswith(("2>", "||", "&&", "true"))]
            found.append(words)
    return found


@pytest.mark.parametrize("path", _all_workflows(), ids=lambda p: p.name)
def test_no_workflow_stages_a_capture_store_for_a_push(path: Path) -> None:
    for words in _git_add_arguments(path.read_text(encoding="utf-8")):
        for word in words:
            assert word not in {"-f", "--force", "-A", "--all", ".", "-u"}, (path.name, words)
            assert not _can_carry_prices(word), (path.name, word)
            assert "closing" not in word and "capture" not in word, (path.name, word)
    if path.name == "experiment-refresh.yml":
        assert _git_add_arguments(path.read_text(encoding="utf-8")) == [[
            "data/outputs/*_experiment.json", "data/outputs/*_experiment.md",
            "data/outputs/verdict_drift.md",
        ]]


def test_the_git_add_reader_sees_a_continued_line() -> None:
    text = "git add a \\\n        b 2>/dev/null || true\ngit add -A\n"
    assert _git_add_arguments(text) == [["a", "b"], ["-A"]]


def test_the_site_never_reads_the_store() -> None:
    """The Pages site (publish-site.yml, web/) is a public route this module
    does not otherwise guard: it builds from gameday-state, and would read a
    line_movement day file for a moneyline open if gameday-state ever carried
    one (measured 2026-10-02: none does, and no frozen board has an open). It
    must never read the closing-line store or hold its token."""
    texts = [(WORKFLOWS / "publish-site.yml").read_text(encoding="utf-8")]
    texts += [p.read_text(encoding="utf-8") for p in (PROJECT_ROOT / "web").rglob("*.py")]
    for text in texts:
        assert "closing_line_captures" not in text
        assert "private_closing_store" not in text
        assert "NHL_CLOSING_LINES_TOKEN" not in text


def test_the_docs_say_what_is_still_downloadable() -> None:
    """The honest half of the record. CLAUDE.md and the README say the chain
    moved, and that the public artifacts uploaded before the move stay
    downloadable until they expire."""
    claude = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "**Stage two: the chain's only home is the private repository.**" in claude
    assert "**What is still downloadable:** the `line-movement` artifacts uploaded" in claude
    assert "**The movement chain is private too (stage two):**" in readme
    assert "stay downloadable until they expire" in readme
    for text in (claude, readme):
        assert "closing-line data is never published from here" not in text
        assert "Closing-line data is never published from this repository" not in text


#: Every step, in every workflow, that may read NHL_CLOSING_LINES_TOKEN.
TOKEN_HOLDERS = {
    ("closing-lines.yml", "Take the chain from the private repository"),
    ("closing-lines.yml", "Publish to the private store"),
    ("gameday-refresh.yml", "Report closing-line value"),
    ("line-movement.yml", "Restore today's captures"),
    ("line-movement.yml", "Keep the captures privately"),
    ("line-movement.yml", "Check the private chain holds this round"),
}


SECRET_READS = re.compile(
    r"secrets\s*\.\s*nhl_closing_lines_token|secrets\s*\[\s*['\"]nhl_closing_lines_token['\"]\s*\]",
    re.IGNORECASE,
)


def _reads_the_token(fragment: object) -> bool:
    return bool(SECRET_READS.search(yaml.safe_dump(fragment)))


def test_the_store_token_reaches_only_the_steps_that_need_it() -> None:
    """A read of the secret, at any level and in any spelling GitHub accepts
    (dot or index, any case). A message that names the secret (Report the
    outcome says to replace it) reads nothing."""
    holders = set()
    for path in _all_workflows():
        document = _load(path.name)
        if _reads_the_token({k: v for k, v in document.items() if k != "jobs"}):
            holders.add((path.name, "<workflow level>"))
        for job in document["jobs"].values():
            if _reads_the_token({k: v for k, v in job.items() if k != "steps"}):
                holders.add((path.name, "<job level>"))
            for step in job.get("steps", []):
                if _reads_the_token(step):
                    holders.add((path.name, step.get("name")))
    assert holders == TOKEN_HOLDERS


@pytest.mark.parametrize("path", _all_workflows(), ids=lambda p: p.name)
def test_no_workflow_hands_a_step_every_secret(path: Path) -> None:
    """toJSON(secrets) would hand the store's token to any step, past the
    pin above."""
    assert not re.search(r"tojson\s*\(\s*secrets", path.read_text(encoding="utf-8"), re.IGNORECASE)


def test_the_token_reader_sees_every_spelling() -> None:
    for spelling in ("${{ secrets.NHL_CLOSING_LINES_TOKEN }}", "${{ secrets.nhl_closing_lines_token }}",
                     "${{ secrets['NHL_CLOSING_LINES_TOKEN'] }}", '${{ secrets["NHL_CLOSING_LINES_TOKEN"] }}'):
        assert _reads_the_token({"env": {"T": spelling}}), spelling
    assert not _reads_the_token({"run": "echo replace NHL_CLOSING_LINES_TOKEN"})


def test_no_other_workflow_that_uploads_data_processed_writes_the_store() -> None:
    """historical-props-purchase also uploads data/processed whole; nothing
    in it may write or read the closing-line store."""
    text = (WORKFLOWS / "historical-props-purchase.yml").read_text(encoding="utf-8")
    assert "closing_line_captures" not in text
    assert "private_closing_store" not in text
    assert "NHL_CLOSING_LINES_TOKEN" not in text


# --- The CLV step, replayed against a real private store ----------------


def _git(args: list[str], cwd: Path, env: dict, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, **kw)


def _capture_row(**overrides) -> dict:
    row = {
        "captured_at": "2026-10-08T22:59:00Z",
        "commence_time": "2026-10-08T23:00:00Z",
        "home_team": "Boston Bruins",
        "away_team": "Chicago Blackhawks",
        "market": "player_points",
        "player": "Sentinel Skater",
        "selection": "over",
        "line": SENTINEL_LINE,
        "american_odds": SENTINEL_ODDS,
        "book": SENTINEL_BOOK,
    }
    row.update(overrides)
    return row


def _seed_private(bare: Path, root: Path, env: dict, files: dict[str, str]) -> None:
    seed = root / "seed"
    seed.mkdir()
    _git(["init", "-q", "-b", "main"], seed, env)
    (seed / "README.md").write_text("private\n", encoding="utf-8")
    for name, body in files.items():
        target = seed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(["add", "-A"], seed, env)
    _git(["commit", "-q", "-m", "seed"], seed, env)
    _git(["push", "-q", str(bare), "HEAD:refs/heads/main"], seed, env)


def _day_file(rows: list[dict]) -> str:
    return pd.DataFrame(rows, columns=list(cl.CAPTURE_COLUMNS)).to_csv(
        index=False, lineterminator="\n"
    )


@pytest.fixture
def clv_rig(tmp_path: Path) -> dict:
    """The CLV step's own block, with real git and the real pull script
    against a bare repository standing in for the private store, reached
    through the exact URL the script builds, for both the store (`main`) and
    the movement chain (`movement`). The report is a stub; it records the
    folders it was pointed at and what was in them while it ran."""
    if not (shutil.which("git") and shutil.which("bash")):
        pytest.fail("this test needs git and bash, which every runner here has")
    bare, bin_dir, home, work, temp = (
        tmp_path / d for d in ("private.git", "bin", "home", "work", "runner_temp")
    )
    for d in (bin_dir, home, work / "data" / "processed", temp):
        d.mkdir(parents=True)
    token = "test-token"
    python = bin_dir / "python"
    python.write_text(
        "#!/bin/bash\n"
        'case "$1" in\n'
        f'  scripts/private_closing_store.py|scripts/private_movement_chain.py) exec "{sys.executable}" "$@" ;;\n'
        "  scripts/run_closing_line_value.py)\n"
        '    shift; printf "%s\\n" "$@" > clv_args.txt\n'
        '    for last in "$@"; do :; done\n'
        '    if [ -n "$(ls -A "$last/line_movement" 2>/dev/null)" ]; then cat "$last"/line_movement/*.csv > clv_chain.txt; fi\n'
        '    dir="$2"\n'
        '    if [ -f "$dir/closing_line_captures.csv" ]; then cat "$dir/closing_line_captures.csv" > report_read.txt;\n'
        "    else echo '<no store>' > report_read.txt; fi\n"
        "    mkdir -p data/outputs; echo '# aggregate only' > data/outputs/closing_line_value.md\n"
        "    exit 0 ;;\n"
        "esac\nexit 0\n",
        encoding="utf-8",
    )
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.file://{bare}.insteadOf",
        "GIT_CONFIG_VALUE_0": store.remote_url(PRIVATE, token),
        "GH_TOKEN": "x",
        "NHL_CLOSING_LINES_TOKEN": token,
        "RUNNER_TEMP": str(temp),
        "GITHUB_WORKSPACE": str(work),
        "GITHUB_OUTPUT": str(work / "github_output.txt"),
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    _git(["init", "-q", "--bare", "-b", "main", str(bare)], tmp_path, env)
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    # The scripts the block calls, at the paths it calls them by.
    (work / "scripts").mkdir()
    for name in ("private_closing_store.py", "merge_capture_store.py",
                 "private_movement_chain.py", "restore_state.py"):
        shutil.copy2(PROJECT_ROOT / "scripts" / name, work / "scripts" / name)
    return {"root": tmp_path, "bare": bare, "work": work, "env": env, "temp": temp}


def clv_block() -> str:
    steps = _load("gameday-refresh.yml")["jobs"]["refresh"]["steps"]
    (step,) = [s for s in steps if s.get("name") == "Report closing-line value"]
    return _render(step["run"], {"github.repository": "o/r"})


def run_clv_step(rig: dict) -> tuple[subprocess.CompletedProcess, str, str]:
    work = rig["work"]
    done = _bash(clv_block(), work, rig["env"])
    read_file = work / "report_read.txt"
    read = read_file.read_text(encoding="utf-8") if read_file.is_file() else "<never ran>"
    return done, read, (work / "run_degraded.txt").read_text(encoding="utf-8")


def _leaks(root: Path) -> list[str]:
    found = []
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.parts and path.name != "report_read.txt":
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if SENTINEL_BOOK in text:
                found.append(str(path.relative_to(root)))
    return found


def test_the_report_reads_the_private_store_and_leaves_no_price_behind(clv_rig) -> None:
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row()])})

    done, read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert SENTINEL_BOOK in read, "the report was not pointed at the private store"
    assert degraded == ""
    assert "Read the capture store from the private repository." in done.stdout
    # Nothing in the workspace (which gameday-state uploads) and nothing left
    # in the runner's temp directory holds a captured price.
    assert _leaks(clv_rig["work"]) == []
    assert _leaks(clv_rig["temp"]) == []


def test_a_restored_store_from_an_older_state_is_removed_not_scored(clv_rig) -> None:
    stale = clv_rig["work"] / "data" / "processed" / cl.CAPTURES_FILENAME
    stale.write_text(_day_file([_capture_row()]), encoding="utf-8")
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"],
                  {"captures/2026-10-09.csv": _day_file([_capture_row(book="Fresh")])})

    done, read, _degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stderr
    assert not stale.exists()
    assert "Fresh" in read and SENTINEL_BOOK not in read
    assert _leaks(clv_rig["work"]) == []


def _args_given(rig: dict) -> list[str]:
    path = rig["work"] / "clv_args.txt"
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


MOVEMENT_HEADER = ("date,commence_time,provider_event_id,home_team,away_team,market,player,"
                   "selection,line,american_odds,book,fetched_at,captured_at\n")


def _seed_chain(rig: dict, book: str = SENTINEL_BOOK) -> None:
    """A `movement` branch on the private store, as Line Movement pushes it."""
    work = rig["root"] / "chain-seed"
    work.mkdir()
    env = rig["env"]
    _git(["init", "-q", "-b", "movement"], work, env)
    (work / "line_movement").mkdir()
    (work / "line_movement" / "2026-10-08.csv").write_text(
        MOVEMENT_HEADER + f"2026-10-08,2026-10-08T23:00:00Z,ev1,Boston Bruins,Chicago Blackhawks,"
        f"player_points,Sentinel Skater,over,17.5,1777,{book},2026-10-08T21:00:00Z,2026-10-08T21:00:00Z\n")
    _git(["add", "-A"], work, env)
    _git(["commit", "-qm", "round"], work, env)
    _git(["push", "-q", str(rig["bare"]), "HEAD:refs/heads/movement"], work, env)


def test_with_a_store_the_report_scores_the_store_and_the_chain(clv_rig) -> None:
    """Both private sources, in that order: a round the store has not
    received yet is still scored from the chain, and neither is left
    behind in the workspace or the temp directory."""
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row()])})
    _seed_chain(clv_rig, book="Chainbook")

    done, read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert degraded == ""
    assert SENTINEL_BOOK in read
    assert "Chainbook" in (clv_rig["work"] / "clv_chain.txt").read_text()
    assert _args_given(clv_rig) == [
        "--captures-dir", str(clv_rig["temp"] / "private-closing-store"),
        "--captures-dir", str(clv_rig["temp"] / "private-movement-chain"),
    ]
    assert _leaks(clv_rig["work"]) == [] and _leaks(clv_rig["temp"]) == []
    for leftover in ("Chainbook",):
        assert not any(leftover in p.read_text(errors="ignore")
                       for p in clv_rig["work"].rglob("*") if p.is_file()
                       and p.name not in ("clv_chain.txt", "report_read.txt") and ".git" not in p.parts)


def test_the_chain_alone_is_scored_when_there_is_no_store(clv_rig) -> None:
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"], {"captures/.gitkeep": ""})
    _seed_chain(clv_rig, book="Chainbook")

    done, read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert degraded == ""
    assert _args_given(clv_rig) == ["--captures-dir", str(clv_rig["temp"] / "private-movement-chain")]
    assert "Chainbook" in (clv_rig["work"] / "clv_chain.txt").read_text()


def test_chain_folders_restored_with_an_older_state_are_removed(clv_rig) -> None:
    """gameday-state from before the move may carry the chain in
    data/processed; it must not be scored or uploaded again."""
    old = clv_rig["work"] / "data" / "processed" / "line_movement"
    old.mkdir(parents=True)
    (old / "2026-10-01.csv").write_text(MOVEMENT_HEADER + "x\n")
    run_clv_step(clv_rig)
    assert not old.exists()


def test_a_store_path_with_a_space_stays_one_argument(clv_rig) -> None:
    spaced = clv_rig["root"] / "runner temp"
    spaced.mkdir()
    clv_rig["env"]["RUNNER_TEMP"] = str(spaced)
    clv_rig["temp"] = spaced
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row()])})

    done, read, _degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert _args_given(clv_rig)[1] == str(spaced / "private-closing-store")
    assert SENTINEL_BOOK in read


def _unreachable_for(rig: dict, ref: str) -> None:
    """GitHub cannot be reached for one branch of the private store."""
    real = shutil.which("git", path=os.environ["PATH"])
    wrapper = rig["root"] / "bin" / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        f'case "$*" in *{ref}*) echo "fatal: unable to access: Could not resolve host: github.com" >&2; exit 128;; esac\n'
        f'exec "{real}" "$@"\n'
    )
    wrapper.chmod(0o755)


def test_an_unreachable_store_with_a_chain_scores_the_chain_and_says_so(clv_rig) -> None:
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row()])})
    _seed_chain(clv_rig, book="Chainbook")
    _unreachable_for(clv_rig, "refs/heads/main")

    done, read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert read == "<no store>\n"
    assert degraded == ("GitHub could not be reached for the private closing-line store, so the "
                        "closing-line value report scored the movement chain alone today.\n")


def test_nothing_reachable_says_nothing_was_scored(clv_rig) -> None:
    shutil.rmtree(clv_rig["bare"])

    done, _read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 0, done.stdout + done.stderr
    assert degraded == ("GitHub could not be reached for the private closing-line store and the private "
                        "movement chain, so the closing-line value report scored no closing price today.\n")


def test_a_damaged_day_costs_only_that_day(clv_rig) -> None:
    """Pull names the damaged day and still hands over the good ones, which
    the report scores; the step is red and degrades nothing."""
    good = _day_file([_capture_row(book="Goodday")])
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"], {
        "captures/2026-10-08.csv": good,
        "captures/2026-10-09.csv": good + 'x,"unterminated\n',
    })

    done, read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 2, done.stdout + done.stderr
    assert "Goodday" in read
    assert degraded == ""
    assert "captures/2026-10-09.csv" in done.stdout
    assert "store_fault=damaged-store" in (clv_rig["work"] / "github_output.txt").read_text()


def test_a_rejected_token_is_named_as_one(clv_rig) -> None:
    _seed_private(clv_rig["bare"], clv_rig["root"], clv_rig["env"],
                  {"captures/2026-10-08.csv": _day_file([_capture_row()])})
    real = shutil.which("git", path=os.environ["PATH"])
    wrapper = clv_rig["root"] / "bin" / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'case "$1" in ls-remote|fetch) echo "fatal: Authentication failed for x" >&2; exit 128;; esac\n'
        f'exec "{real}" "$@"\n'
    )
    wrapper.chmod(0o755)

    done, _read, degraded = run_clv_step(clv_rig)

    assert done.returncode == 2, done.stdout + done.stderr
    assert degraded == ""
    assert "turned NHL_CLOSING_LINES_TOKEN away" in done.stdout
    assert "store_fault=rejected-token" in (clv_rig["work"] / "github_output.txt").read_text()


# --- The script's refusals -----------------------------------------------


def _args(tmp_path: Path, **overrides) -> list[str]:
    processed = tmp_path / "processed"
    processed.mkdir(exist_ok=True)
    pd.DataFrame([_capture_row()], columns=list(cl.CAPTURE_COLUMNS)).to_csv(
        processed / cl.CAPTURES_FILENAME, index=False
    )
    argv = ["push", "--processed-dir", str(processed)]
    for key, value in overrides.items():
        argv += [f"--{key}", value]
    return argv


@pytest.fixture
def asked(monkeypatch) -> list[str]:
    """Records every repository the privacy check is asked about, and says
    private; a test that wants another answer patches over it."""
    calls: list[str] = []

    def private(repo: str, token: str) -> bool:
        calls.append(repo)
        return True

    monkeypatch.setattr(store, "repo_is_private", private)
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    return calls


def test_the_public_lab_is_refused_by_name_before_anything_is_asked(tmp_path, asked, capsys) -> None:
    assert store.main(_args(tmp_path, repo=PUBLIC)) == store.EXIT_REFUSED
    assert asked == []
    assert "public lab" in capsys.readouterr().out


def test_the_repository_the_run_is_in_is_refused(tmp_path, asked, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/fork-of-the-lab")
    assert store.main(_args(tmp_path, repo="someone/fork-of-the-lab")) == store.EXIT_REFUSED
    assert asked == []


def _seeded_bare(tmp_path: Path, monkeypatch, files: dict[str, str] | None = None) -> Path:
    """A store a push or pull would succeed against, so that a refusal is
    the only thing that can stop it."""
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    bare = tmp_path / "store.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    _seed_private(bare, tmp_path, dict(os.environ), files or {})
    return bare


def _tip(bare: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "main"],
                          capture_output=True, text=True, check=True).stdout


def _redirect(monkeypatch, url: str, bare: Path) -> None:
    """Send `url` to a working local store, so only a refusal can stop a push."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.file://{bare}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", url)


def test_a_push_to_a_working_store_succeeds(tmp_path, asked, monkeypatch) -> None:
    """The control for every refusal below: the same push, unrefused, lands."""
    bare = _seeded_bare(tmp_path, monkeypatch)
    before = _tip(bare)
    assert store.main(_args(tmp_path, remote=f"file://{bare}")) == store.EXIT_OK
    assert _tip(bare) != before


def test_a_local_remote_naming_the_public_lab_is_refused(tmp_path, asked, monkeypatch) -> None:
    """A working store at a path ending in the public lab's name: only the
    name check can refuse it."""
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    bare = tmp_path / "cooperross399" / "nhl-betting-lab.git"
    bare.parent.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    _seed_private(bare, tmp_path, dict(os.environ), {})
    before = _tip(bare)

    assert store.main(_args(tmp_path, remote=f"file://{bare}")) == store.EXIT_REFUSED
    assert _tip(bare) == before


@pytest.mark.parametrize("other", [
    "cooperross399/some-public-repo",
    "cooperross399/nhl-closing-lines-public",  # a name the checked one prefixes
    "cooperross399/nhl-betting-lab",
])
def test_a_github_remote_other_than_the_checked_repository_is_refused(
    tmp_path, asked, monkeypatch, other
) -> None:
    """The privacy check is made of --repo, so the push may not go elsewhere.
    The other repository's URL is redirected to a working store, so only the
    refusal can stop the push."""
    bare = _seeded_bare(tmp_path, monkeypatch)
    remote = f"https://x-access-token:t@github.com/{other}.git"
    _redirect(monkeypatch, remote, bare)
    before = _tip(bare)

    assert store.main(_args(tmp_path, remote=remote)) == store.EXIT_REFUSED
    assert _tip(bare) == before


@pytest.mark.parametrize("form", [
    "https://x-access-token:t@github.com/cooperross399/nhl-closing-lines.git",
    "https://github.com/cooperross399/nhl-closing-lines",
    "git@github.com:cooperross399/nhl-closing-lines.git",
    "ssh://git@github.com/cooperross399/NHL-Closing-Lines.git",
])
def test_every_form_of_the_checked_repository_is_accepted(form) -> None:
    assert store.github_repo_of(form) == PRIVATE
    store.refuse_public_target(PRIVATE, form)


def test_a_store_that_is_not_private_is_never_written(tmp_path, asked, monkeypatch, capsys) -> None:
    bare = _seeded_bare(tmp_path, monkeypatch)
    before = _tip(bare)
    monkeypatch.setattr(store, "repo_is_private", lambda repo, token: False)

    assert store.main(_args(tmp_path, remote=f"file://{bare}")) == store.EXIT_REFUSED
    assert "is not private" in capsys.readouterr().out
    assert _tip(bare) == before


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        pytest.param(store.Unreachable("no route"), "EXIT_FAILED", id="unreachable"),
        pytest.param(store.Refused("GitHub answered 404"), "EXIT_REFUSED", id="token-turned-away"),
    ],
)
def test_an_unanswered_privacy_check_writes_nothing(tmp_path, asked, monkeypatch, raised, code) -> None:
    bare = _seeded_bare(tmp_path, monkeypatch)
    before = _tip(bare)

    def unanswered(repo: str, token: str) -> bool:
        raise raised

    monkeypatch.setattr(store, "repo_is_private", unanswered)
    assert store.main(_args(tmp_path, remote=f"file://{bare}")) == getattr(store, code)
    assert _tip(bare) == before


@pytest.mark.parametrize(("status", "expected"), [(401, "Refused"), (403, "Refused"),
                                                 (404, "Refused"), (502, "Unreachable")])
def test_the_privacy_check_tells_a_rejected_token_from_an_outage(monkeypatch, status, expected) -> None:
    def answer(request, timeout):
        raise urllib.error.HTTPError(request.full_url, status, "x", {}, None)

    monkeypatch.setattr(store.urllib.request, "urlopen", answer)
    with pytest.raises(getattr(store, expected)):
        store.repo_is_private(PRIVATE, "t")


def test_the_public_lab_is_refused_by_its_own_check_against_a_working_store(
    tmp_path, asked, monkeypatch, capsys
) -> None:
    """--repo naming the public lab, with a --remote that would otherwise
    take the push: only the --repo check can refuse it, and it does so
    before the privacy question is asked."""
    bare = _seeded_bare(tmp_path, monkeypatch)
    before = _tip(bare)

    assert store.main(_args(tmp_path, repo=PUBLIC, remote=f"file://{bare}")) == store.EXIT_REFUSED
    assert asked == []
    assert _tip(bare) == before
    assert "as the closing-line store" in capsys.readouterr().out


@pytest.mark.parametrize("remote", [
    "https://x-access-token:t@www.github.com/cooperross399/nhl-closing-lines.git",
    "https://x-access-token:t@github.com:443/cooperross399/nhl-closing-lines.git",
    "https://x-access-token:t@github%2ecom/cooperross399/nhl-closing-lines.git",
    "https://github.com/someone/x/cooperross399/nhl-closing-lines.git",
    "https://github.com/cooperross399/nhl-closing-lines.git?x=cooperross399/other",
    "https://github.com/cooperross399/other.git#cooperross399/nhl-closing-lines",
    "https://gitlab.com/cooperross399/nhl-closing-lines.git",
    "relative/path/store.git",
])
def test_a_remote_that_is_not_canonical_or_local_is_refused(tmp_path, asked, monkeypatch, remote) -> None:
    """Each is redirected to a working store, so only the refusal stops it."""
    bare = _seeded_bare(tmp_path, monkeypatch)
    _redirect(monkeypatch, remote, bare)
    before = _tip(bare)

    assert store.main(_args(tmp_path, remote=remote)) == store.EXIT_REFUSED
    assert _tip(bare) == before


@pytest.mark.parametrize("suffix", ["nhl-betting-lab/.git", "nhl-betting-lab/.", "NHL-Betting-Lab.GIT",
                                    "nhl-betting-lab.git/", "x/../nhl-betting-lab.git"])
def test_every_spelling_of_a_local_public_lab_path_is_refused(suffix) -> None:
    with pytest.raises(store.Refused):
        store.refuse_public_target(PRIVATE, f"file:///tmp/cooperross399/{suffix}")


def _push_against(tmp_path, monkeypatch, urlopen) -> tuple[int, Path, str]:
    """A push whose privacy question goes through the real repo_is_private,
    with only urlopen replaced, against a store the push would land in."""
    bare = _seeded_bare(tmp_path, monkeypatch)
    before = _tip(bare)
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setattr(store.urllib.request, "urlopen", urlopen)
    return store.main(_args(tmp_path, remote=f"file://{bare}")), bare, before


class _Body:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a):
        return self.body


def _raises(error):
    def urlopen(request, timeout):
        raise error
    return urlopen


@pytest.mark.parametrize(
    ("urlopen", "code"),
    [
        pytest.param(_raises(urllib.error.URLError(socket.timeout("timed out"))), "EXIT_FAILED", id="url-timeout"),
        pytest.param(_raises(TimeoutError()), "EXIT_FAILED", id="timeout"),
        pytest.param(_raises(ConnectionRefusedError()), "EXIT_FAILED", id="refused-connection"),
        pytest.param(lambda request, timeout: _Body(b"<html>busy</html>"), "EXIT_FAILED", id="html-page"),
        pytest.param(lambda request, timeout: _Body(b'{"private": false}'), "EXIT_REFUSED", id="public"),
        pytest.param(lambda request, timeout: _Body(b'["private", true]'), "EXIT_REFUSED", id="not-an-object"),
        pytest.param(_raises(urllib.error.HTTPError("u", 404, "x", {}, None)), "EXIT_REFUSED", id="404"),
        pytest.param(_raises(urllib.error.HTTPError("u", 503, "x", {}, None)), "EXIT_FAILED", id="503"),
    ],
)
def test_every_answer_but_private_true_writes_nothing(tmp_path, monkeypatch, urlopen, code) -> None:
    result, bare, before = _push_against(tmp_path, monkeypatch, urlopen)
    assert result == getattr(store, code)
    assert _tip(bare) == before


def test_private_true_through_the_real_check_lands(tmp_path, monkeypatch) -> None:
    """The control for the table above."""
    result, bare, before = _push_against(
        tmp_path, monkeypatch, lambda request, timeout: _Body(b'{"private": true}'))
    assert result == store.EXIT_OK
    assert _tip(bare) != before


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        pytest.param("fatal: Authentication failed for 'https://github.com/x/y.git/'", "EXIT_REFUSED", id="auth"),
        pytest.param("remote: Repository not found.", "EXIT_REFUSED", id="not-found"),
        pytest.param("fatal: unable to access: The requested URL returned error: 403", "EXIT_REFUSED", id="403"),
        pytest.param("git@github.com: Permission denied (publickey).", "EXIT_REFUSED", id="ssh-key"),
        pytest.param("fatal: unable to access: Could not resolve host: github.com", "EXIT_FAILED", id="dns"),
        pytest.param("fatal: unable to access: The requested URL returned error: 502", "EXIT_FAILED", id="502"),
    ],
)
def test_the_pull_tells_a_rejected_token_from_an_outage(tmp_path, monkeypatch, stderr, code) -> None:
    """Gameday Refresh's pull never asks the API, so git's own words are all
    it has: exit 5 (red, no backup) for a token, exit 1 (degraded) for an outage."""
    real = shutil.which("git")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "git").write_text(
        "#!/bin/sh\n"
        f'case "$1" in ls-remote|fetch) echo "{stderr}" >&2; exit 128;; esac\n'
        f'exec "{real}" "$@"\n'
    )
    (stub / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    out = tmp_path / "out" / cl.CAPTURES_FILENAME

    assert store.main(["pull", "--out", str(out), "--remote", "file:///anywhere"]) == getattr(store, code)
    assert not out.exists()


def test_no_token_publishes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(store.TOKEN_ENV, raising=False)
    assert store.main(_args(tmp_path)) == store.EXIT_NO_TOKEN


def test_a_pull_into_the_workspace_is_refused(tmp_path, monkeypatch) -> None:
    """Against a store the pull would read, so only the refusal stops it."""
    bare = _seeded_bare(tmp_path, monkeypatch,
                        {"captures/2026-10-08.csv": _day_file([_capture_row()])})
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    out = workspace / "data" / "processed" / cl.CAPTURES_FILENAME
    assert store.main(["pull", "--out", str(out), "--remote", f"file://{bare}"]) == store.EXIT_REFUSED
    assert not out.exists()
    # The same pull outside the workspace reads it.
    outside = tmp_path / "runner_temp" / cl.CAPTURES_FILENAME
    assert store.main(["pull", "--out", str(outside), "--remote", f"file://{bare}"]) == store.EXIT_OK
    assert SENTINEL_BOOK in outside.read_text(encoding="utf-8")


def test_a_day_file_that_parses_short_without_an_error_is_damage(tmp_path, monkeypatch) -> None:
    """A stray quote folds rows into one field and pandas raises nothing, so
    the count off the file is what catches it."""
    good = _day_file([_capture_row(), _capture_row(selection="under")])
    lines = good.splitlines()
    # Open a quote in the first data row's player and close it in the second's.
    lines[1] = lines[1].replace("Sentinel Skater", '"Sentinel Skater')
    lines[2] = lines[2].replace("Sentinel Skater", 'Sentinel Skater"')
    folded = "\n".join(lines) + "\n"
    assert len(pd.read_csv(pd.io.common.StringIO(folded))) < 2, "the fixture must fold"
    bare = _seeded_bare(tmp_path, monkeypatch, {"captures/2026-10-08.csv": folded})
    monkeypatch.setenv(store.TOKEN_ENV, "t")
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    out = tmp_path / "out" / cl.CAPTURES_FILENAME

    assert store.main(["pull", "--out", str(out), "--remote", f"file://{bare}"]) == store.EXIT_DAMAGED
    assert not out.exists()


def test_the_privacy_check_wants_true_not_merely_not_false(monkeypatch) -> None:
    class Response:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *a):
            return self.body

    for body, expected in ((b'{"private": true}', True), (b'{"private": false}', False),
                           (b"{}", False), (b'{"private": "true"}', False)):
        monkeypatch.setattr(store.urllib.request, "urlopen",
                            lambda request, timeout, body=body: Response(body))
        assert store.repo_is_private(PRIVATE, "t") is expected, body


# --- The published report ------------------------------------------------


def test_the_published_report_prints_no_price_line_or_book(tmp_path: Path) -> None:
    now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    opinion = {
        "snapshot_date": "2026-10-08",
        "commence_time": "2026-10-08T23:00:00Z",
        "home_team": "Boston Bruins",
        "away_team": "Chicago Blackhawks",
        "market": "player_points",
        "player": "Sentinel Skater",
        "selection": "over",
        "line": SENTINEL_LINE,
        "american_odds": 1555.0,
        "book": "Zzopinionbook",
        "model_probability": 0.2,
        "edge": 0.1,
    }
    opinions = pd.DataFrame([opinion, {**opinion, "selection": "under",
                                       "american_odds": -1999.0}])
    captures = pd.DataFrame(
        [_capture_row(), _capture_row(selection="under", american_odds=-2333.0)],
        columns=list(cl.CAPTURE_COLUMNS),
    )
    report = cl.build_clv_report(opinions, captures, now=now)
    assert report["counts"]["matched"] == 2, report["counts"]
    path = cl.save_clv_report(report, output_dir=tmp_path, generated=now.isoformat())
    text = path.read_text(encoding="utf-8")

    for needle in (SENTINEL_BOOK, "Zzopinionbook", "Sentinel Skater",
                   "1777", "2333", "1555", "1999", "17.5"):
        assert needle not in text, needle
