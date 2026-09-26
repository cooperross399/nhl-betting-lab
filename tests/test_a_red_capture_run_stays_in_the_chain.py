"""A red Line Movement run's captures were dropped from the chain for good.

Line Movement's "Restore today's captures" took `gh run list --status success
--limit 1`. A run goes red when the price capture's events list fails (the
script exits 2 on a ProviderError) or when the line units were not captured
(the gate at the end of the job). Either way the steps marked `if: always()`
still ran and `Keep the captures` uploaded them: the deployment and line units
on a price failure, the prices and the deployment on a line failure. The next
run restored the last GREEN run instead, appended to that older file and
uploaded it, so the red run's rows fell out of the chain and lived only in
that run's own artifact, which nothing reads and which expires in 90 days.
Neither the NHL scratch list nor Daily Faceoff keeps an archive.

Found by the failure-shape audit and confirmed 3/3 by the refuters. Their
replay of one league day (14:00 green, 18:00 provider 503, 21:00 and 23:00
green) left the 18:00 deployment and line-combination rows in no later
artifact: the scratch list and the PP1 promotion that first appeared at 18:00
read in the surviving chain as first public at 21:00, three hours late —
which is the one question these captures exist to answer. A missing or
revoked NHL_ODDS_API_KEY makes EVERY run red, so every free capture from then
on would have been dropped the same way.

The same selection had a second hole: a run whose own restore found nothing
(the GitHub API down for that minute) is green, carries only its own rows,
and became the next run's base — so the whole season's history behind it was
gone from the chain. The restore now takes the newest carrier of any
conclusion and unions every CSV, row by row, with the two carriers before it.

These tests run the restore step itself, taken from the workflow file, under
`bash --noprofile --norc -eo pipefail` with an offline `gh` that honours
`--status` the way `gh run list --help` documents it (a status or a
conclusion). Between restores they run the real `capture_deployment.main` and
`capture_line_combinations.main` with their network and clock stubbed, append
prices exactly as `capture_line_movement.main` does, and upload each run's
artifact from the paths `Keep the captures` names in the same YAML.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.season import LEAGUE_TIMEZONE

from test_scripts import load_script


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "line-movement.yml"
RESTORE_SCRIPT = PROJECT_ROOT / "scripts" / "restore_state.py"
RESTORE_STEP = "Restore today's captures"
ARTIFACT = "line-movement"

#: The in-season crons, in UTC, on one league day (2026-10-15 Eastern).
AT_14, AT_18 = "2026-10-15T14:00:00+00:00", "2026-10-15T18:00:00+00:00"
AT_21, AT_23 = "2026-10-15T21:00:00+00:00", "2026-10-15T23:00:00+00:00"
AT_01 = "2026-10-16T01:00:00+00:00"
#: 21:00 Eastern the evening before.
YESTERDAY = "2026-10-15T01:00:00+00:00"

FAKE_GH = r'''#!{python}
import json, os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
if os.environ.get("FAKE_GH_DOWN") == "1":
    print("HTTP 502: Bad Gateway", file=sys.stderr)
    sys.exit(1)
registry = json.loads(Path(os.environ["FAKE_GH_REGISTRY"]).read_text())

def value(flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default

if args[:2] == ["run", "list"]:
    runs = [r for r in registry if r["workflow"] == value("--workflow")]
    status = value("--status")
    if status:
        # As `gh run list --help` documents it: a status or a conclusion.
        runs = [r for r in runs if status in (r["status"], r["conclusion"])]
    runs = runs[: int(value("--limit", "20"))]
    fields = [f for f in value("--json", "").split(",") if f]
    rows = [{{k: r[k] for k in fields}} for r in runs]
    jq = value("--jq")
    if jq is None:
        print(json.dumps(rows))
    elif jq == ".[0].databaseId // empty":
        if rows:
            print(rows[0]["databaseId"])
    else:
        print("fake gh: unsupported --jq " + jq, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
if args[:2] == ["run", "download"]:
    run_id, name, dest = args[2], value("--name"), Path(value("--dir"))
    broken = os.environ.get("FAKE_GH_BROKEN", "").split(",")
    run = next((r for r in registry if str(r["databaseId"]) == run_id), {{}})
    source = (run.get("artifacts") or {{}}).get(name)
    if source is None or run_id in broken:
        print("no valid artifacts found to download", file=sys.stderr)
        sys.exit(1)
    shutil.copytree(source, dest, dirs_exist_ok=True)
    sys.exit(0)
print("fake gh: unhandled " + " ".join(args), file=sys.stderr)
sys.exit(2)
'''


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _restore_step() -> str:
    matches = [s for s in _steps() if s.get("name") == RESTORE_STEP]
    assert len(matches) == 1, f"exactly one step named {RESTORE_STEP!r}"
    return matches[0]["run"]


def _upload_paths() -> tuple[str, list[str]]:
    """What `Keep the captures` uploads, and the root upload-artifact gives it."""
    for step in _steps():
        given = step.get("with") or {}
        if str(step.get("uses", "")).startswith("actions/upload-artifact") and (
            given.get("name") == ARTIFACT
        ):
            paths = [
                line.strip()
                for line in str(given["path"]).splitlines()
                if line.strip() and not line.strip().startswith(("#", "!"))
            ]
            return os.path.commonpath(paths), paths
    raise AssertionError(f"line-movement.yml uploads no {ARTIFACT!r} artifact")


def _day(instant: str) -> str:
    return datetime.fromisoformat(instant).astimezone(LEAGUE_TIMEZONE).date().isoformat()


def _clock(instant: str) -> type:
    fixed = datetime.fromisoformat(instant)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 - the scripts' only use
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    return Frozen


def _nhl_api(instant: str):
    """The schedule and right-rail payloads. The scratch goes public at 18:00."""
    day = _day(instant)
    scratched = instant >= f"{day}T18:00:00+00:00"

    def fetch(url, requester=None):
        if url.endswith("/v1/schedule/now"):
            return {"gameWeek": [{"games": [
                {"id": 2026020077, "startTimeUTC": f"{day}T23:00:00Z"},
            ]}]}
        return {"gameInfo": {
            "referees": [{"default": "Wes McCauley"}, {"default": "Chris Rooney"}],
            "linesmen": [{"default": "Ryan Gibbons"}],
            "homeTeam": {
                "headCoach": {"default": "Craig Berube"},
                "scratches": [{"id": 8471817, "firstName": {"default": "Ryan"},
                               "lastName": {"default": "Reaves"}}] if scratched else [],
            },
            "awayTeam": {"headCoach": {"default": "Marco Sturm"}, "scratches": []},
        }}

    return fetch


def _lines_page(instant: str) -> str:
    """The team page. Knies is promoted to the top power-play unit at 18:00."""
    players = [{
        "playerId": 8479318, "name": "Auston Matthews", "playerSlug": "auston-matthews",
        "groupIdentifier": "f1", "groupName": "F1", "categoryIdentifier": "ev",
        "positionIdentifier": "c",
    }]
    if instant >= f"{_day(instant)}T18:00:00+00:00":
        players.append({
            "playerId": 8482720, "name": "Matthew Knies", "playerSlug": "matthew-knies",
            "groupIdentifier": "pp1", "groupName": "PP1", "categoryIdentifier": "pp",
            "positionIdentifier": "sk1",
        })
    payload = {"props": {"pageProps": {
        "sortedTeams": [{"slug": "toronto-maple-leafs"}],
        "combinations": {
            "teamSlug": "toronto-maple-leafs", "teamAbbreviation": "TOR",
            "teamName": "Toronto Maple Leafs", "sourceName": "Morning Skate",
            "updatedAt": "2026-10-15T13:02:00.000Z", "players": players,
        },
    }}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload) + "</script></body></html>"
    )


class Chain:
    """Line Movement's runs, one after another, as GitHub would run them."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tmp = tmp_path
        self.monkeypatch = monkeypatch
        self.registry: list[dict] = []  # newest first, as `gh run list` lists
        self.next_id = 1000
        self.logs: dict[int, str] = {}
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.path = f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"
        self.movement = load_script("capture_line_movement.py")
        self.deployment = load_script("capture_deployment.py")
        self.lines = load_script("capture_line_combinations.py")

    def _registry(self, in_progress: int | None = None) -> Path:
        runs = list(self.registry)
        if in_progress is not None:
            runs.insert(0, {"databaseId": in_progress, "workflow": "line-movement.yml",
                            "status": "in_progress", "conclusion": "",
                            "headBranch": "main", "artifacts": {}})
        path = self.tmp / "registry.json"
        path.write_text(json.dumps(runs), encoding="utf-8")
        return path

    def cancelled(self) -> int:
        """A run cancelled before it uploaded anything: completed, no artifact."""
        run_id = self.next_id
        self.next_id += 1
        self.registry.insert(0, {"databaseId": run_id, "workflow": "line-movement.yml",
                                 "status": "completed", "conclusion": "cancelled",
                                 "headBranch": "main", "artifacts": {}})
        return run_id

    def run(
        self, instant: str, *, prices: bool = True, lines: bool = True,
        gh_down: bool = False, broken: tuple[int, ...] = (),
    ) -> Path:
        """One scheduled run: restore, capture, upload. Returns data/processed."""
        run_id = self.next_id
        self.next_id += 1
        work = self.tmp / f"run{run_id}"
        (work / "scripts").mkdir(parents=True)
        shutil.copy(RESTORE_SCRIPT, work / "scripts" / "restore_state.py")
        env = {
            **os.environ,
            "PATH": self.path,
            "GH_TOKEN": "not-a-token",
            "FAKE_GH_REGISTRY": str(self._registry(in_progress=run_id)),
            "FAKE_GH_LOG": str(self.tmp / "gh.log"),
            "FAKE_GH_DOWN": "1" if gh_down else "0",
            "FAKE_GH_BROKEN": ",".join(str(b) for b in broken),
        }
        # `continue-on-error: true`: the job goes on whatever the step returns.
        restored = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", _restore_step()],
            cwd=work, env=env, capture_output=True, text=True, timeout=120,
        )
        self.logs[run_id] = restored.stdout + restored.stderr
        processed = work / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        day = _day(instant)

        if prices:
            # Exactly the append `capture_line_movement.main` makes; the
            # script itself needs --live, which no test may pass.
            frame = pd.DataFrame([{
                "provider_event_id": f"evt-{day}", "commence_time": f"{day}T23:00:00Z",
                "home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins",
                "market": "shots_on_goal", "player": "Auston Matthews",
                "selection": "over", "line": 3.5,
                "american_odds": -110 - int(instant[11:13]), "book": "draftkings",
            }])
            frame["captured_at"] = instant
            path = self.movement.capture_path(day, processed_dir=processed)
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                         lineterminator="\n")

        clock = _clock(instant)
        self.monkeypatch.setattr(self.deployment, "datetime", clock)
        self.monkeypatch.setattr(self.deployment, "_get_json", _nhl_api(instant))
        assert self.deployment.main(
            ["--processed-dir", str(processed), "--polite-seconds", "0"]
        ) == 0

        self.monkeypatch.setattr(self.lines, "datetime", clock)
        self.monkeypatch.setattr(self.lines, "games_today", lambda *a, **k: 1)
        if lines:
            self.monkeypatch.setattr(self.lines, "_fetch", lambda url, **k: _lines_page(instant))
        else:
            def refused(url, **k):
                raise OSError("403 Forbidden")
            self.monkeypatch.setattr(self.lines, "_fetch", refused)
        code = self.lines.main(["--processed-dir", str(processed), "--polite-seconds", "0"])
        assert code == (0 if lines else 2)

        self.registry.insert(0, {
            "databaseId": run_id, "workflow": "line-movement.yml", "status": "completed",
            # Scheduled, so on main. `gh run list --json` answers every field it
            # is asked for, and the restore now asks for this one.
            "headBranch": "main",
            # The price step has no continue-on-error, and the last step fails
            # the job when the line capture did.
            "conclusion": "success" if prices and lines else "failure",
            "artifacts": self._upload(run_id, work),
        })
        return processed

    def _upload(self, run_id: int, work: Path) -> dict:
        root, paths = _upload_paths()
        artifact = self.tmp / "artifacts" / str(run_id)
        kept = False
        for relative in paths:
            source = work / relative
            if source.is_dir():
                shutil.copytree(source, artifact / os.path.relpath(relative, root))
                kept = True
        # `if-no-files-found: warn`: nothing to keep is no artifact at all.
        return {ARTIFACT: str(artifact)} if kept else {}

    def last_id(self) -> int:
        return self.registry[0]["databaseId"]


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Chain:
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    return Chain(tmp_path, monkeypatch)


def _column(processed: Path, store: str, column: str, day: str = "2026-10-15") -> list[str]:
    path = processed / store / f"{day}.csv"
    return [str(v) for v in pd.read_csv(path)[column]] if path.is_file() else []


def _instants(processed: Path, day: str = "2026-10-15") -> dict[str, list[str]]:
    return {
        "line_movement": _column(processed, "line_movement", "captured_at", day),
        "deployment": _column(processed, "deployment", "captured_at", day),
        "line_combinations": _column(processed, "line_combinations", "retrieved_at", day),
    }


def test_a_red_price_runs_free_captures_reach_the_next_run(chain: Chain) -> None:
    """The finding's own replay: 14:00 green, 18:00 red, 21:00 and 23:00 green."""
    chain.run(AT_14)
    chain.run(AT_18, prices=False)  # the events list failed: exit 2, a red run
    chain.run(AT_21)
    after = chain.run(AT_23)

    seen = _instants(after)
    assert AT_18 in seen["deployment"], "the 18:00 scratch list fell out of the chain"
    assert AT_18 in seen["line_combinations"], "the 18:00 line units fell out of the chain"
    assert AT_18 not in seen["line_movement"], "no price was captured at 18:00"

    deployment = pd.read_csv(after / "deployment" / "2026-10-15.csv")
    lines = pd.read_csv(after / "line_combinations" / "2026-10-15.csv")
    # The whole reason these exist: WHEN the news became public.
    assert deployment.loc[deployment["player"] == "Ryan Reaves", "captured_at"].min() == AT_18
    assert lines.loc[lines["player"] == "Matthew Knies", "retrieved_at"].min() == AT_18


def test_a_run_red_for_its_line_units_keeps_its_prices_in_the_chain(chain: Chain) -> None:
    """The gate that turns a missed line capture red said "the red X is the
    report, not the damage" — while the restore was dropping that run's
    prices, the ones that cost credits."""
    chain.run(AT_14)
    chain.run(AT_18, lines=False)
    after = chain.run(AT_21)

    seen = _instants(after)
    assert seen["line_movement"] == [AT_14, AT_18, AT_21]
    assert seen["deployment"].count(AT_18) >= 1


def test_a_run_whose_restore_found_nothing_is_not_the_new_base(chain: Chain) -> None:
    """Green, but the GitHub API was down for its restore: its artifact holds
    only its own rows. Taken alone as the next base, it would have cost every
    earlier capture, yesterday's included."""
    chain.run(YESTERDAY)
    chain.run(AT_14)
    chain.run(AT_18, gh_down=True)
    after = chain.run(AT_21)

    seen = _instants(after)
    for store, instants in seen.items():
        assert instants == sorted(instants), f"{store} is not in capture order"
        assert {AT_14, AT_18, AT_21} <= set(instants), store
    yesterday = _instants(after, day="2026-10-14")
    for store, instants in yesterday.items():
        assert instants and set(instants) == {YESTERDAY}, f"yesterday's {store} was lost"


def test_two_thin_runs_in_a_row_and_a_run_with_no_artifact_lose_nothing(
    chain: Chain,
) -> None:
    chain.run(AT_14)
    chain.cancelled()
    chain.run(AT_18, gh_down=True)
    chain.run(AT_21, gh_down=True)
    after = chain.run(AT_23)

    for store, instants in _instants(after).items():
        assert {AT_14, AT_18, AT_21, AT_23} <= set(instants), store


def test_a_download_that_failed_once_is_folded_back_in_by_the_next_run(
    chain: Chain,
) -> None:
    chain.run(AT_14)
    chain.run(AT_18)
    chain.run(AT_21)
    chain.run(AT_23, broken=(chain.last_id(),))  # the newest carrier, once
    after = chain.run(AT_01)

    for store, instants in _instants(after).items():
        assert {AT_14, AT_18, AT_21, AT_23, AT_01} <= set(instants), store


# --------------------------------------------------------------------------
# The union itself.
# --------------------------------------------------------------------------

def _union():
    return load_script("restore_state.py").union_csv


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_the_union_keeps_a_repeated_row_as_often_as_it_was_captured(tmp_path: Path) -> None:
    older = _write(tmp_path / "old.csv", "a,b\n1,x\n1,x\n2,y\n")
    newer = _write(tmp_path / "new.csv", "a,b\n3,z\n")

    assert _union()(older, newer) == 3
    assert newer.read_text() == "a,b\n1,x\n1,x\n2,y\n3,z\n"


def test_a_row_the_newer_copy_repeats_is_kept_as_often_as_it_repeats(
    tmp_path: Path,
) -> None:
    """The multiset union from the other side: the newer copy holds a row
    twice that the older holds once, and the older holds a row the newer
    lacks. Each row is kept as often as the copy holding it most often has
    it, so nothing is lost and nothing is doubled. (A union that never
    counted down the older copy's matches read both newer rows as already
    known, recovered nothing and dropped the older row; the independent
    reviewer found that no test told the two apart.)"""
    older = _write(tmp_path / "old.csv", "a,b\n0,x\n1,a\n")
    newer = _write(tmp_path / "new.csv", "a,b\n1,a\n1,a\n")

    assert _union()(older, newer) == 1
    assert newer.read_text() == "a,b\n0,x\n1,a\n1,a\n"


def test_two_headers_are_not_merged_and_the_newer_file_is_untouched(tmp_path: Path) -> None:
    older = _write(tmp_path / "old.csv", "a,b\n1,x\n")
    newer = _write(tmp_path / "new.csv", "a,b,c\n3,z,q\n")

    assert _union()(older, newer) is None
    assert newer.read_text() == "a,b,c\n3,z,q\n"


def test_a_file_whose_parse_disagrees_with_its_lines_is_not_merged(tmp_path: Path) -> None:
    """A stray quote folds the rest of the file into one record; a union
    written from that read would drop rows and report success."""
    older = _write(tmp_path / "old.csv", 'a,b\n1,"x\n2,y\n3,z\n')
    newer = _write(tmp_path / "new.csv", "a,b\n4,w\n")

    assert _union()(older, newer) is None
    assert newer.read_text() == "a,b\n4,w\n"


def test_a_newer_copy_that_lost_rows_gets_them_back(tmp_path: Path) -> None:
    """The newer copy is a byte prefix of the older one: it restored from a
    carrier before it and captured nothing new for this store."""
    older = _write(tmp_path / "old.csv", "a,b\n1,x\n2,y\n")
    newer = _write(tmp_path / "new.csv", "a,b\n1,x\n")

    assert _union()(older, newer) == 1
    assert newer.read_text() == "a,b\n1,x\n2,y\n"


def test_a_merged_file_is_byte_for_byte_what_the_capture_would_have_written(
    tmp_path: Path,
) -> None:
    """The deployment rows carry JSON lists, which the CSV has to quote. The
    next capture appends to this file and every reader parses it, so the
    union must write exactly what pandas writes for the same rows."""
    deployment = load_script("capture_deployment.py")
    early = deployment.rows_for_game(_nhl_api(AT_14)("right-rail"), game_id="77",
                                     captured_at=AT_14)
    late = deployment.rows_for_game(_nhl_api(AT_18)("right-rail"), game_id="77",
                                    captured_at=AT_18)
    older, newer, whole = (tmp_path / n for n in ("old.csv", "new.csv", "whole.csv"))
    pd.DataFrame(early).to_csv(older, index=False, lineterminator="\n")
    pd.DataFrame(late).to_csv(newer, index=False, lineterminator="\n")
    pd.DataFrame(early + late).to_csv(whole, index=False, lineterminator="\n")

    assert _union()(older, newer) == len(early)
    assert newer.read_bytes() == whole.read_bytes()
