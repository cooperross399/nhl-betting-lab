"""A forward-ledger write that was cut short stood, and lost settled rows for good.

`forward_evidence.settle_snapshots` rewrites the WHOLE forward ledger on every
pass that settles a day: it reads the file, puts the new rows after the old
ones, and wrote the result with `frame.to_csv(ledger_path)` straight onto
`data/processed/forward_evidence.csv`. #146 made the snapshot writer publish
whole or not at all, because a torn day file stood for good. The ledger's
writer was left in place, and it is the one store the code itself says
"cannot be rebuilt".

Found by the failure-shape audit (forward_evidence.py:757; confirmed by all
three refuters) and reproduced through the real `run_forward_evidence.py`.
Six real April 2026 slates were frozen and settled in two passes. Pass 2
rewrote a 14,281,893-byte ledger and was cut short by a file-size limit (a
full disk) or a SIGKILL (a cancelled or timed-out job):

* cut inside the quoted verdicts field, the ledger no longer parsed ("EOF
  inside string starting at row 45122"). Every later pass exited 1 with a
  bare ParserError from the unguarded `snapshot_date` read at the top of
  `settle_snapshots`, and wrote no report;
* cut at a row boundary inside 2026-04-13, 5,171 of its 10,340 rows were
  missing, and the day counted as settled through the `snapshot_date` of the
  rows that landed, so they never settled. Every later pass exited 0. The
  SIGKILL left 5,133 rows missing the same way;
* the old rows come first, so a cut in them lost days that EARLIER passes had
  settled and marked: 7,508 of 2026-04-09's 15,015 rows and all 15,339 of
  2026-04-11's, both still marked, never retried. A SIGKILL 20 ms into
  rewriting a 150-day, 25,800-row ledger left 3,158 rows; the next pass
  exited 0 and reported "Ledger rows: 3,330" — 22,642 rows gone, nothing
  raised.

The shrink guard could not fire: its floor is counted off the file on disk,
which was the torn file. On CI the settle step runs `continue-on-error`, the
state upload and the card-feed push run `if: always()`, and
scripts/restore_state.py kept the torn copy over the last success's in the
first two shapes (45,122 and 45,121 rows against 33,841).

What these tests hold:

* a ledger write that fails partway (inside a quoted field, at a row boundary
  among the new rows, at a row boundary or mid-row inside history already
  settled and marked, inside a multi-byte character, before any byte) leaves
  the ledger byte-identical to what it was, touches no marker, leaves no file
  behind, and the next pass settles every day whole. The same holds for the
  kernel's own file-size refusal through the real runner, and for a SIGKILL;
* the bytes are fsynced before the ledger's name is moved onto them, the
  directory is fsynced after, and only then is a day marked; the bytes are
  exactly those the in-place write produced;
* a ledger that is already damaged (an unclosed quote, no bytes, half a
  character, half a header, blank lines) is refused by name before any day
  is settled or marked, and the runner says so with `::error::` and exits 2
  instead of dying on a traceback. A ledger holding only its header still
  takes an honest append.
"""

from __future__ import annotations

import errno
import importlib.util
import os
import signal
import stat
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data.build_datasets import (
    PLAYER_LOGS_FILENAME,
    TEAM_GAMES_FILENAME,
)
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.providers.team_names import save_team_name_map
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.stores import CorruptStoreError


#: Settled and marked by an earlier pass: the history a rewrite puts first.
HISTORY_DAY = "2026-10-06"
#: Frozen and pending: what the pass under test settles.
NEW_DAY = "2026-10-08"
LATER = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
#: The shape `verdicts.describe` really returns. It holds commas, so the CSV
#: quotes it, and a cut inside it leaves an unclosed quote.
VERDICTS = "by_toi=off, props_b2b=in force, team_b2b=in force"
#: Keyed the way `load_team_name_map` returns it: normalized name -> abbrev.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
#: Two spelled outside ASCII, as the books spell them, so the ledger holds
#: multi-byte characters a cut can split.
PLAYERS = (
    ("Auston Matthews", 8479318, "TOR", 4),
    ("Alexis Lafrenière", 8482109, "BOS", 2),
    ("William Nylander", 8477939, "TOR", 3),
    ("David Pastrňák", 8477956, "BOS", 1),
)
BOOKS = ("DraftKings", "FanDuel", "BetMGM", "Caesars")
ODDS = (-135, -115, 105, 120, 140)
ROWS = 64


# --------------------------------------------------------------------------
# Two days of a real-shaped slate: one settled and marked, one pending.
# --------------------------------------------------------------------------

def _face_off(day: str) -> str:
    """00:10Z the next morning is 20:10 ET, so the league date is `day`."""
    return f"{(date.fromisoformat(day) + timedelta(days=1)).isoformat()}T00:10:00Z"


def _slate(day: str) -> tuple[pd.DataFrame, dict[tuple, float]]:
    rows: list[dict] = []
    probabilities: dict[tuple, float] = {}
    for i in range(ROWS):
        player = PLAYERS[i % len(PLAYERS)][0]
        row = {
            "commence_time": _face_off(day),
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "market": "shots_on_goal",
            "player": player,
            "selection": "over" if i % 2 == 0 else "under",
            "line": 1.5 + i // 16,
            "american_odds": ODDS[i % len(ODDS)],
            "book": BOOKS[(i // 4) % len(BOOKS)],
        }
        rows.append(row)
        probabilities[
            selection_key(
                SimpleNamespace(**row),
                market=row["market"],
                selection=row["selection"],
                line=float(row["line"]),
            )
        ] = round(0.35 + 0.004 * i, 3)
    return pd.DataFrame(rows), probabilities


def freeze(archive: Path, day: str) -> None:
    prices, probabilities = _slate(day)
    assert fe.write_snapshot(
        prices,
        probabilities,
        key_for=selection_key,
        verdicts_line=VERDICTS,
        snapshot_date=day,
        now=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        archive_dir=archive,
    ) is not None


def _logs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": day, "player_id": player_id, "player": name, "team": team,
             "shots_on_goal": shots}
            for day in (HISTORY_DAY, NEW_DAY)
            for name, player_id, team, shots in PLAYERS
        ]
    )


def _games() -> pd.DataFrame:
    """Toronto beating Boston 4-2 on both days."""
    return pd.DataFrame(
        [
            {"game_id": i, "date": day, "home_team": "TOR", "away_team": "BOS",
             "home_goals": 4, "away_goals": 2, "regulation": True}
            for i, day in enumerate((HISTORY_DAY, NEW_DAY))
        ]
    )


def settle(root: Path) -> fe.SettlementResult:
    return fe.settle_snapshots(
        _logs(),
        _games(),
        team_names=TEAM_MAP,
        archive_dir=root / "archive",
        processed_dir=root / "processed",
        now=LATER,
    )


def _ledger(root: Path) -> Path:
    return root / "processed" / fe.LEDGER_FILENAME


def _markers(root: Path) -> list[str]:
    return sorted(
        p.name.removesuffix(".settled")
        for p in fe.snapshots_dir(root / "archive").glob("*.settled")
    )


def _processed_listing(root: Path) -> list[str]:
    return sorted(p.name for p in (root / "processed").iterdir())


def history_and_a_pending_day(root: Path) -> bytes:
    """Settle HISTORY_DAY, freeze NEW_DAY; the ledger's bytes before the pass."""
    freeze(root / "archive", HISTORY_DAY)
    settle(root)
    assert _markers(root) == [HISTORY_DAY]
    freeze(root / "archive", NEW_DAY)
    return _ledger(root).read_bytes()


def whole_ledger(scratch: Path) -> tuple[bytes, bytes]:
    """(before the pass, after an uninterrupted pass)."""
    before = history_and_a_pending_day(scratch)
    settle(scratch)
    return before, _ledger(scratch).read_bytes()


def _per_day(root: Path) -> dict[str, int]:
    ledger = pd.read_csv(_ledger(root))
    return ledger["snapshot_date"].astype(str).value_counts().sort_index().to_dict()


def test_the_rewrite_puts_the_settled_history_first(tmp_path: Path) -> None:
    """Why a cut can land in days an earlier pass settled and marked: the
    old ledger is the first part of every rewrite, byte for byte."""
    before, whole = whole_ledger(tmp_path)

    assert whole.startswith(before)
    assert len(whole) > len(before)
    assert _per_day(tmp_path) == {HISTORY_DAY: ROWS, NEW_DAY: ROWS}
    assert "Lafrenière" in whole.decode("utf-8")


# --------------------------------------------------------------------------
# A write that fails partway leaves the ledger as it was.
# --------------------------------------------------------------------------

def _after(whole: bytes, needle: bytes, start: int) -> int:
    return whole.index(needle, start)


#: Where the rewrite can be cut. `before` is the ledger on disk before the
#: pass, `whole` what the pass would publish; the new rows start at
#: len(before).
CUTS = {
    "inside_the_quoted_verdicts_of_the_new_rows": (
        lambda before, whole: _after(whole, b'"by_toi', len(before)) + 8
    ),
    "at_a_row_boundary_among_the_new_rows": (
        lambda before, whole: _after(
            whole, b"\n", len(before) + (len(whole) - len(before)) // 2
        ) + 1
    ),
    "at_a_row_boundary_inside_the_settled_history": (
        lambda before, whole: _after(whole, b"\n", len(before) // 2) + 1
    ),
    "mid_row_inside_the_settled_history": (
        lambda before, whole: _after(whole, b"\n", len(before) // 2) + 1 + 40
    ),
    "inside_a_multibyte_character": (
        lambda before, whole: _after(
            whole, "è".encode("utf-8"), len(before) // 2
        ) + 1
    ),
    "before_any_byte": lambda before, whole: 0,
}


def cut_every_write_at(cut: int, then) -> object:
    """A `DataFrame.to_csv` that gets `cut` bytes onto disk, then `then()`.

    Given a path (the in-place write) it writes the prefix there; given a
    stream (a temporary) it writes the prefix into the stream. Either way the
    bytes are flushed and fsynced before `then` raises or kills, which is
    what a full disk or a kill leaves behind.
    """
    real = pd.DataFrame.to_csv

    def to_csv(self, path_or_buf=None, *args, **kwargs):
        if path_or_buf is None:
            return real(self, None, *args, **kwargs)
        data = real(self, None, *args, **kwargs).encode("utf-8")[:cut]
        if isinstance(path_or_buf, (str, os.PathLike)):
            with open(path_or_buf, "wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
        else:
            path_or_buf.flush()
            buffer = getattr(path_or_buf, "buffer", path_or_buf)
            buffer.write(data)
            buffer.flush()
            os.fsync(buffer.fileno())
        then()

    return to_csv


def _no_space() -> None:
    raise OSError(errno.ENOSPC, "No space left on device")


@pytest.mark.parametrize("where", sorted(CUTS))
def test_a_ledger_write_that_fails_partway_leaves_the_ledger_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    before, whole = whole_ledger(tmp_path / "reference")
    run = tmp_path / "run"
    assert history_and_a_pending_day(run) == before
    monkeypatch.setattr(
        pd.DataFrame, "to_csv",
        cut_every_write_at(CUTS[where](before, whole), _no_space),
    )

    with pytest.raises(OSError) as caught:
        settle(run)
    monkeypatch.undo()

    assert caught.value.errno == errno.ENOSPC
    assert _ledger(run).read_bytes() == before, (
        "a ledger write cut short changed the ledger; whatever it left stands "
        "as the season's record, and the rows it lost are never settled again"
    )
    assert _markers(run) == [HISTORY_DAY], "a day was marked by a pass that failed"
    assert _processed_listing(run) == [fe.LEDGER_FILENAME], (
        "the failed write left a file behind beside the ledger"
    )

    # The next pass settles the pending day whole, and history is intact.
    result = settle(run)
    assert result.snapshots_settled == 1
    assert _ledger(run).read_bytes() == whole
    assert _markers(run) == [HISTORY_DAY, NEW_DAY]
    assert _per_day(run) == {HISTORY_DAY: ROWS, NEW_DAY: ROWS}


# --------------------------------------------------------------------------
# What gets published: durable first, then marked, and the same bytes.
# --------------------------------------------------------------------------

def test_the_ledger_is_durable_before_it_is_published_and_published_before_any_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name moved onto bytes that are not yet on disk can survive a power
    loss that the bytes do not; a marker made durable before the ledger's new
    name is a day marked settled whose rows may not be there."""
    history_and_a_pending_day(tmp_path)
    ledger = _ledger(tmp_path)
    directory_inode = ledger.parent.stat().st_ino
    events: list[tuple] = []
    real_fsync, real_replace, real_touch = os.fsync, os.replace, Path.touch

    def fsync(fd: int) -> None:
        info = os.fstat(fd)
        events.append(("fsync", info.st_ino, info.st_size, stat.S_ISDIR(info.st_mode)))
        real_fsync(fd)

    def replace(source, destination, *args, **kwargs):
        info = os.stat(source)
        events.append(("replace", info.st_ino, info.st_size, Path(destination)))
        return real_replace(source, destination, *args, **kwargs)

    def touch(self, *args, **kwargs):
        events.append(("touch", self.name))
        return real_touch(self, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "touch", touch)

    settle(tmp_path)
    monkeypatch.undo()

    published = [
        i for i, event in enumerate(events)
        if event[0] == "replace" and event[3] == ledger
    ]
    assert len(published) == 1, f"the ledger was not published by a replace: {events}"
    at = published[0]
    _, inode, size, _ = events[at]
    assert (inode, size) == (ledger.stat().st_ino, ledger.stat().st_size)
    assert ("fsync", inode, size, False) in events[:at], (
        f"the ledger's bytes were not fsynced before its name moved: {events}"
    )
    marked = [
        i for i, event in enumerate(events)
        if event[0] == "touch" and event[1] == f"{NEW_DAY}.settled"
    ]
    assert len(marked) == 1 and marked[0] > at, events
    assert any(
        event[0] == "fsync" and event[3] and event[1] == directory_inode
        for event in events[at + 1: marked[0]]
    ), f"the ledger's directory was not fsynced between the publish and the mark: {events}"


def test_the_published_ledger_is_the_bytes_the_in_place_write_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix changes where the bytes go first, not what they are."""
    history_and_a_pending_day(tmp_path)
    written: list[pd.DataFrame] = []
    real = pd.DataFrame.to_csv

    def recording(self, *args, **kwargs):
        if list(self.columns) == list(fe.LEDGER_COLUMNS):
            written.append(self.copy())
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_csv", recording)
    settle(tmp_path)
    monkeypatch.undo()

    assert len(written) == 1
    in_place = tmp_path / "in_place.csv"
    written[0].to_csv(in_place, index=False, lineterminator="\n")
    assert _ledger(tmp_path).read_bytes() == in_place.read_bytes()
    assert len(written[0]) == 2 * ROWS


# --------------------------------------------------------------------------
# A ledger already damaged is refused by name, before anything is marked.
# --------------------------------------------------------------------------

#: What a damaged ledger can look like: a cut-short in-place write (from
#: before this fix, restored from an artifact) or anything else that damages
#: a file after it is written. Each used to raise a bare pandas or codec
#: error out of the top of the pass, except half a header, which parsed as
#: an empty ledger with the wrong columns and was written over.
DAMAGE = {
    "an_unclosed_quote": lambda whole: _after(whole, b'"by_toi', len(whole) // 2) + 8,
    "no_bytes_at_all": lambda whole: 0,
    "half_a_character": (
        lambda whole: _after(whole, "è".encode("utf-8"), len(whole) // 2) + 1
    ),
    "half_a_header": lambda whole: 30,
}


def _damaged(root: Path, damage: str) -> bytes:
    """HISTORY_DAY settled, NEW_DAY pending, and the ledger damaged."""
    history = history_and_a_pending_day(root)
    if damage == "blank_lines_only":
        data = b"\n\n\n"
    else:
        data = history[: DAMAGE[damage](history)]
    _ledger(root).write_bytes(data)
    return data


@pytest.mark.parametrize("damage", sorted(DAMAGE) + ["blank_lines_only"])
def test_a_damaged_ledger_is_refused_by_name_before_any_day_is_marked(
    tmp_path: Path, damage: str
) -> None:
    data = _damaged(tmp_path, damage)

    with pytest.raises(CorruptStoreError) as caught:
        settle(tmp_path)

    assert str(_ledger(tmp_path)) in str(caught.value)
    assert _ledger(tmp_path).read_bytes() == data, "the damaged ledger was written over"
    assert _markers(tmp_path) == [HISTORY_DAY]
    assert _processed_listing(tmp_path) == [fe.LEDGER_FILENAME]


def test_a_ledger_holding_only_its_header_takes_an_honest_append(
    tmp_path: Path,
) -> None:
    """The refusal is for a ledger that cannot be read, not for one with no
    rows: a header and nothing else holds nothing to lose."""
    history_and_a_pending_day(tmp_path)
    header = _ledger(tmp_path).read_bytes().split(b"\n", 1)[0] + b"\n"
    _ledger(tmp_path).write_bytes(header)

    result = settle(tmp_path)

    assert result.snapshots_settled == 1
    assert _per_day(tmp_path) == {NEW_DAY: ROWS}
    assert _markers(tmp_path) == [HISTORY_DAY, NEW_DAY]


# --------------------------------------------------------------------------
# Through the runner, the way the Gameday Refresh step calls it.
# --------------------------------------------------------------------------

def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runner_tree(root: Path) -> list[str]:
    """The processed tables the runner reads, and its arguments."""
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    _games().to_csv(processed / TEAM_GAMES_FILENAME, index=False)
    _logs().to_csv(processed / PLAYER_LOGS_FILENAME, index=False)
    save_team_name_map(TEAM_MAP, processed_dir=processed)
    return [
        "--processed-dir", str(processed),
        "--output-dir", str(root / "outputs"),
        "--archive-dir", str(root / "archive"),
    ]


def _isolate_defaults(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No real data directory can rescue or break a run here."""
    monkeypatch.setattr(fe, "DATA_DIR", root / "default_data")
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", root / "default_processed")
    monkeypatch.setattr(team_names_module, "RAW_DIR", root / "default_raw")


def test_the_runner_names_a_damaged_ledger_and_exits_2_without_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _isolate_defaults(tmp_path, monkeypatch)
    arguments = _runner_tree(tmp_path)
    data = _damaged(tmp_path, "an_unclosed_quote")
    module = load_script("run_forward_evidence.py")

    for _ in range(2):  # and again on the next run: it does not heal itself
        code = module.main(arguments)
        captured = capsys.readouterr()

        assert code == 2
        assert any(
            line.startswith("::error::") and str(_ledger(tmp_path)) in line
            for line in captured.err.splitlines()
        ), captured.err
        assert "No report was written" in captured.out + captured.err
        assert not (tmp_path / "outputs" / fe.REPORT_MARKDOWN_FILENAME).exists()
        assert _ledger(tmp_path).read_bytes() == data
        assert _markers(tmp_path) == [HISTORY_DAY]


def test_the_kernel_refusing_the_ledger_write_leaves_it_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kernel's own refusal (RLIMIT_FSIZE) through the real runner, as a
    full disk refuses. Python ignores SIGXFSZ, so the write fails with EFBIG."""
    _isolate_defaults(tmp_path, monkeypatch)
    arguments = _runner_tree(tmp_path)
    module = load_script("run_forward_evidence.py")
    freeze(tmp_path / "archive", HISTORY_DAY)
    assert module.main(arguments) == 0
    freeze(tmp_path / "archive", NEW_DAY)
    before = _ledger(tmp_path).read_bytes()
    listing = _processed_listing(tmp_path)

    completed = _runner_child(arguments, file_size_limit=len(before) * 3 // 2)

    assert completed.returncode == 1, completed.stderr
    assert "File too large" in completed.stderr
    assert _ledger(tmp_path).read_bytes() == before
    assert _markers(tmp_path) == [HISTORY_DAY]
    assert _processed_listing(tmp_path) == listing

    assert module.main(arguments) == 0
    assert _ledger(tmp_path).read_bytes().startswith(before)
    assert _per_day(tmp_path) == {HISTORY_DAY: ROWS, NEW_DAY: ROWS}
    assert _markers(tmp_path) == [HISTORY_DAY, NEW_DAY]


def test_a_pass_killed_mid_write_leaves_the_ledger_as_it_was(
    tmp_path: Path,
) -> None:
    """SIGKILL: no handler runs, so whatever the kill leaves on disk stays.
    None of it may be the ledger, and none of it may be a name a reader of
    `*.csv` would take for a store."""
    before, whole = whole_ledger(tmp_path / "reference")
    run = tmp_path / "run"
    history_and_a_pending_day(run)

    completed = _settle_child(
        run, CUTS["at_a_row_boundary_inside_the_settled_history"](before, whole)
    )

    assert completed.returncode == -signal.SIGKILL, completed.stderr
    assert _ledger(run).read_bytes() == before, (
        "the killed rewrite left a torn ledger under the ledger's own name"
    )
    assert _markers(run) == [HISTORY_DAY]
    leftovers = [name for name in _processed_listing(run) if name != fe.LEDGER_FILENAME]
    assert all(
        name.startswith(".") and name.endswith(fe.PARTIAL_SUFFIX) for name in leftovers
    ), leftovers

    settle(run)
    assert _ledger(run).read_bytes() == whole
    assert _markers(run) == [HISTORY_DAY, NEW_DAY]


# --------------------------------------------------------------------------
# The subprocess half: a real kill and a real kernel refusal.
# --------------------------------------------------------------------------

CHILD = r"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_cut_short_ledger_child", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.child_main(sys.argv[2], int(sys.argv[3]))
"""


def child_main(root: str, cut: int) -> None:
    """Runs in a subprocess: settle, and SIGKILL the ledger write at `cut`."""
    pd.DataFrame.to_csv = cut_every_write_at(
        cut, lambda: os.kill(os.getpid(), signal.SIGKILL)
    )
    settle(Path(root))


def _environment() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _settle_child(root: Path, cut: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", CHILD, str(Path(__file__).resolve()),
         str(root), str(cut)],
        capture_output=True, text=True, env=_environment(), timeout=120,
    )


def _runner_child(
    arguments: list[str], *, file_size_limit: int
) -> subprocess.CompletedProcess:
    """The real runner script, as the workflow step runs it, under a limit."""
    import resource

    def limit() -> None:
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (file_size_limit, file_size_limit)
        )

    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "run_forward_evidence.py"),
         *arguments],
        capture_output=True, text=True, env=_environment(), timeout=120,
        preexec_fn=limit,
    )
