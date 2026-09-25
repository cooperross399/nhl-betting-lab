"""A snapshot write that was cut short stayed as the day's first opinion for good.

`forward_evidence.write_snapshot` wrote the day's snapshot in place, with
`frame.to_csv(target)` straight onto `priced_snapshots/{day}.csv`. Every
later call starts with `if target.exists(): return None`, because the first
opinion of a day stands and is never repriced. So when a write was cut short
(the process killed, the disk full), part of a file stayed under the day's
name, and every later run took it for the day's complete opinion. Settlement
then read it with a bare `pd.read_csv`.

Found by the failure-shape audit (finding #12; confirmed by two of the three
refuters). The mechanism was reproduced through the real scripts on the real
2026-04-14 slate. The card froze a 48,218-byte snapshot. A write cut at
28,672 bytes landed inside the quoted verdicts field ("by_toi=off, props_b2b=
in force, team_b2b=in force"). The card exited 1. A second card run printed
"already stands" and left the file byte-identical. `run_forward_evidence.py`
then exited 1 with "ParserError ... EOF inside string" on that pass and on
every later one, writing no report, no ledger rows and no marker, and a later
complete day was blocked behind it.

That was the loud outcome. Only 1 of that file's 11 block boundaries falls
inside a quote. A cut at any of the other 10 parses without error, as a day
missing its later rows, and the last row is garbled: model_probability 0.0
where the card said 0.698, home_team "Philadelphia Fly", snapshot_date
"2026-04-". Because the first snapshot stands, that short day would have
settled quietly as the card's opinion.

Two refuters placed the reach only on local runs, because every restore was
then success-only. At this commit it reaches CI too. `scripts/restore_state.py`
restores the newest completed run's `gameday-state` whatever its conclusion,
and the state upload runs `if: always()`, so a torn file from a failed card
step would be carried into every later run.

What these tests hold:

* a write that fails partway (inside a quoted field, mid-row where the cut
  would still parse, inside a multi-byte character, before any byte) leaves
  no snapshot and nothing else behind, and the next run freezes the whole
  day. The same holds for a real kernel file-size failure;
* a process killed mid-write leaves no file that settlement or the CLV
  report would read as the day's opinion, and the day can still be frozen;
* the bytes are fsynced before the day's name is published, and they are
  exactly the bytes the in-place write produced;
* a day another run froze while this write was in flight is not overwritten;
* a pending snapshot that cannot be read (an unclosed quote, no bytes, half a
  character, half a header) is named in the result and left unsettled and
  unmarked, and every other day settles. The runner still restates the
  ledger as its report and exits 2 with an `::error::` naming the file.
"""

from __future__ import annotations

import errno
import importlib.util
import os
import signal
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.models.value import american_to_implied
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.providers.team_names import save_team_name_map
from nhl_betting_lab.reports.card_pricing import selection_key


DAY = "2026-10-08"
#: Well after every day here, and inside no patience question: the finals
#: these tests settle against are all on disk.
LATER = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)
#: The shape `verdicts.describe` really returns. It holds commas, so the CSV
#: quotes it, and a cut inside it leaves an unclosed quote.
VERDICTS = "by_toi=off, props_b2b=in force, team_b2b=in force"
#: Keyed the way `load_team_name_map` returns it: normalized name -> abbrev.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
#: Two of these are spelled outside ASCII, as the books spell them, so the
#: file holds multi-byte characters a cut can split.
PLAYERS = (
    "Auston Matthews",
    "Alexis Lafrenière",
    "William Nylander",
    "David Pastrňák",
)
BOOKS = ("DraftKings", "FanDuel", "BetMGM", "Caesars")
ODDS = (-135, -115, 105, 120, 140)
ROWS = 64


# --------------------------------------------------------------------------
# A day's slate, frozen the way the card freezes it.
# --------------------------------------------------------------------------

def _face_off(day: str) -> str:
    """00:10Z the next morning is 20:10 ET, so the league date is `day`."""
    return f"{(date.fromisoformat(day) + timedelta(days=1)).isoformat()}T00:10:00Z"


def slate(day: str = DAY) -> tuple[pd.DataFrame, dict[tuple, float]]:
    """A day's priced props, every row carrying a model opinion."""
    rows: list[dict] = []
    probabilities: dict[tuple, float] = {}
    for i in range(ROWS):
        row = {
            "commence_time": _face_off(day),
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "market": "shots_on_goal",
            "player": PLAYERS[i % len(PLAYERS)],
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


def freeze(
    archive: Path, day: str = DAY, tally: dict | None = None
) -> Path | None:
    prices, probabilities = slate(day)
    return fe.write_snapshot(
        prices,
        probabilities,
        key_for=selection_key,
        verdicts_line=VERDICTS,
        snapshot_date=day,
        # That morning, before the face-off.
        now=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        archive_dir=archive,
        tally=tally,
    )


def whole_bytes(scratch: Path, day: str = DAY) -> bytes:
    """What an uninterrupted freeze of the day publishes."""
    path = freeze(scratch, day)
    assert path is not None
    return path.read_bytes()


def _after_half(whole: bytes, needle: bytes) -> int:
    return whole.index(needle, len(whole) // 2)


#: Where a write can be cut, and so where a file on disk can end. The shapes
#: the audit measured: inside the quoted verdicts (ParserError), mid-row (the
#: silent one: it parses as a short day), and two more that raise on read,
#: half of a multi-byte character (UnicodeDecodeError) and no bytes at all
#: (EmptyDataError: killed before the first flush).
CUTS = {
    "inside_the_quoted_verdicts": lambda whole: _after_half(whole, b'"by_toi') + 8,
    "mid_row_where_it_still_parses": (
        lambda whole: _after_half(whole, b"\n") + 1 + 40
    ),
    "inside_a_multibyte_character": (
        lambda whole: _after_half(whole, "è".encode("utf-8")) + 1
    ),
    "before_any_byte": lambda whole: 0,
}


def cut_every_write_at(cut: int, then) -> object:
    """A `DataFrame.to_csv` that gets `cut` bytes onto disk, then `then()`.

    It serves both writers. Given a path (the in-place write) it writes the
    prefix there. Given a stream (the temporary) it writes the prefix into
    the stream. Either way the bytes are flushed and fsynced before `then`
    raises or kills, which is what a full disk or a kill leaves behind.
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


def _listing(archive: Path) -> list[str]:
    directory = fe.snapshots_dir(archive)
    return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []


# --------------------------------------------------------------------------
# A write that fails partway leaves nothing, and the day is frozen whole.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("where", sorted(CUTS))
def test_a_write_that_fails_partway_leaves_no_snapshot_and_the_rerun_freezes_the_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    whole = whole_bytes(tmp_path / "reference")
    archive = tmp_path / "archive"
    monkeypatch.setattr(
        pd.DataFrame, "to_csv", cut_every_write_at(CUTS[where](whole), _no_space)
    )

    with pytest.raises(OSError) as caught:
        freeze(archive)
    monkeypatch.undo()

    assert caught.value.errno == errno.ENOSPC
    assert _listing(archive) == [], (
        "a write cut short left a file behind; under the day's name it "
        "stands for good as the day's first opinion"
    )
    tally: dict = {}
    path = freeze(archive, tally=tally)
    assert tally["state"] == "frozen"
    assert path is not None and path.read_bytes() == whole
    assert len(pd.read_csv(path)) == ROWS


def test_a_real_file_size_failure_leaves_no_snapshot(tmp_path: Path) -> None:
    """The kernel's own refusal (RLIMIT_FSIZE), not a simulated one. Python
    ignores SIGXFSZ, so the write fails with EFBIG, as it does on a full
    disk."""
    whole = whole_bytes(tmp_path / "reference")
    archive = tmp_path / "archive"

    completed = _child(archive, "file_size_limit", len(whole) // 2)

    assert completed.returncode == 1, completed.stderr
    assert "File too large" in completed.stderr
    assert _listing(archive) == []
    path = freeze(archive)
    assert path is not None and path.read_bytes() == whole


def test_a_run_killed_mid_write_leaves_no_snapshot_and_the_day_can_still_be_frozen(
    tmp_path: Path,
) -> None:
    """SIGKILL: no handler runs, so whatever the kill leaves on disk stays
    there. None of it may be a file that settlement or the CLV report reads
    as the day's opinion."""
    whole = whole_bytes(tmp_path / "reference")
    archive = tmp_path / "archive"

    completed = _child(
        archive, "kill", CUTS["inside_the_quoted_verdicts"](whole)
    )

    assert completed.returncode == -signal.SIGKILL, completed.stderr
    directory = fe.snapshots_dir(archive)
    assert sorted(directory.glob("*.csv")) == [], (
        "the killed write left a file under the name every reader globs"
    )
    result = fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        _games(),
        team_names=TEAM_MAP,
        archive_dir=archive,
        processed_dir=tmp_path / "processed",
        now=LATER,
    )
    assert result.snapshots_seen == 0
    path = freeze(archive)
    assert path is not None and path.read_bytes() == whole


# --------------------------------------------------------------------------
# What gets published: durable first, the same bytes, and never over a day.
# --------------------------------------------------------------------------

def test_the_bytes_are_on_disk_before_the_day_is_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name published before its data is durable can survive a power loss
    that the data does not, and then an empty or partial file stands."""
    events: list[tuple[str, int, int]] = []
    real_fsync, real_link = os.fsync, os.link

    def fsync(fd: int) -> None:
        info = os.fstat(fd)
        events.append(("fsync", info.st_ino, info.st_size))
        real_fsync(fd)

    def link(source, destination, *args, **kwargs):
        info = os.stat(source)
        events.append(("link", info.st_ino, info.st_size))
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", link)

    path = freeze(tmp_path)

    assert path is not None
    links = [i for i, event in enumerate(events) if event[0] == "link"]
    assert len(links) == 1, f"the day was not published by a link: {events}"
    _, inode, size = events[links[0]]
    assert size == path.stat().st_size
    assert ("fsync", inode, size) in events[: links[0]], (
        f"the published bytes were not fsynced before the link: {events}"
    )


def test_the_published_bytes_are_the_ones_the_in_place_write_produced(
    tmp_path: Path,
) -> None:
    """The fix changes where the bytes are written first, not what they are,
    and it leaves nothing but the snapshot behind."""
    prices, probabilities = slate()
    path = freeze(tmp_path)

    expected_rows = []
    for row in prices.itertuples():
        probability = probabilities[
            selection_key(
                row, market=row.market, selection=row.selection,
                line=float(row.line),
            )
        ]
        expected_rows.append(
            {
                "snapshot_date": DAY,
                "commence_time": row.commence_time,
                "home_team": row.home_team,
                "away_team": row.away_team,
                "market": row.market,
                "player": row.player,
                "selection": row.selection,
                "line": float(row.line),
                "american_odds": float(row.american_odds),
                "book": row.book,
                "model_probability": float(probability),
                "edge": float(probability) - american_to_implied(row.american_odds),
                "verdicts_in_force": VERDICTS,
            }
        )
    in_place = tmp_path / "in_place.csv"
    pd.DataFrame(expected_rows, columns=list(fe.SNAPSHOT_COLUMNS)).to_csv(
        in_place, index=False, lineterminator="\n"
    )

    assert path is not None and path.read_bytes() == in_place.read_bytes()
    assert _listing(tmp_path) == [f"{DAY}.csv"]


def test_a_day_frozen_while_this_write_was_in_flight_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between the existence check and the publish, another run froze the
    day. Its opinion came first, so it stands. A publish that replaces the
    name would silently put the later opinion over it."""
    target = fe.snapshots_dir(tmp_path) / f"{DAY}.csv"
    rival = whole_bytes(tmp_path / "rival").replace(b"DraftKings", b"RivalBook")
    assert rival != whole_bytes(tmp_path / "reference")
    real = pd.DataFrame.to_csv

    def to_csv_while_a_rival_freezes(self, *args, **kwargs):
        written = real(self, *args, **kwargs)
        target.write_bytes(rival)
        return written

    monkeypatch.setattr(pd.DataFrame, "to_csv", to_csv_while_a_rival_freezes)
    tally: dict = {}

    written = freeze(tmp_path, tally=tally)
    monkeypatch.undo()

    assert written is None
    assert tally["state"] == "exists"
    assert target.read_bytes() == rival
    assert _listing(tmp_path) == [f"{DAY}.csv"]


# --------------------------------------------------------------------------
# A pending file that cannot be read waits, named, and the rest settle.
# --------------------------------------------------------------------------

#: How a file already on disk can be damaged, and what reading it did:
#: ParserError, EmptyDataError, UnicodeDecodeError, and, for half a header,
#: an empty frame with the wrong columns that was marked settled as an
#: empty day.
DAMAGE = {
    "an_unclosed_quote": CUTS["inside_the_quoted_verdicts"],
    "no_bytes_at_all": CUTS["before_any_byte"],
    "half_a_character": CUTS["inside_a_multibyte_character"],
    "half_a_header": lambda whole: 30,
}

TORN_DAY = "2026-10-07"


def _torn(tmp_path: Path, archive: Path, damage: str) -> tuple[Path, bytes]:
    """The TORN_DAY snapshot as a cut-short write left it, before this fix."""
    whole = whole_bytes(tmp_path / "reference", TORN_DAY)
    data = whole[: DAMAGE[damage](whole)]
    path = fe.snapshots_dir(archive) / f"{TORN_DAY}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, data


def _moneyline_day(archive: Path, day: str = DAY) -> None:
    row = {
        "commence_time": _face_off(day),
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "market": "moneyline",
        "player": "",
        "selection": "home",
        "line": None,
        "american_odds": -120,
        "book": "DraftKings",
    }
    assert fe.write_snapshot(
        pd.DataFrame([row]),
        {selection_key(SimpleNamespace(**row), market="moneyline",
                       selection="home", line=None): 0.62},
        key_for=selection_key,
        verdicts_line=VERDICTS,
        snapshot_date=day,
        now=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        archive_dir=archive,
    ) is not None


def _games(*days: str) -> pd.DataFrame:
    """Toronto beating Boston 4-2 on each league date given."""
    return pd.DataFrame(
        [
            {"game_id": i, "date": day, "home_team": "TOR", "away_team": "BOS",
             "home_goals": 4, "away_goals": 2, "regulation": True}
            for i, day in enumerate(days)
        ],
        columns=["game_id", "date", "home_team", "away_team", "home_goals",
                 "away_goals", "regulation"],
    )


def _markers(archive: Path) -> list[str]:
    return sorted(
        p.name.removesuffix(".settled")
        for p in fe.snapshots_dir(archive).glob("*.settled")
    )


@pytest.mark.parametrize("damage", sorted(DAMAGE))
def test_an_unreadable_pending_snapshot_is_named_and_waits_while_the_rest_settle(
    tmp_path: Path, damage: str
) -> None:
    archive = tmp_path / "archive"
    torn, data = _torn(tmp_path, archive, damage)
    _moneyline_day(archive)

    result = fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        _games(TORN_DAY, DAY),
        team_names=TEAM_MAP,
        archive_dir=archive,
        processed_dir=tmp_path / "processed",
        now=LATER,
    )

    assert list(result.unreadable_snapshots) == [f"{TORN_DAY}.csv"]
    assert _markers(archive) == [DAY], (
        "the unreadable day was marked settled, or the readable one was not"
    )
    ledger = fe.load_ledger(tmp_path / "processed")
    assert list(ledger["snapshot_date"].astype(str)) == [DAY]
    assert list(ledger["outcome"]) == ["won"]
    assert torn.read_bytes() == data, "the evidence file itself was touched"
    assert "1 pending snapshot file(s) could not be read" in result.summary_line()

    # Retried, and named again, on the next pass; nothing appended twice.
    again = fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        _games(TORN_DAY, DAY),
        team_names=TEAM_MAP,
        archive_dir=archive,
        processed_dir=tmp_path / "processed",
        now=LATER,
    )
    assert list(again.unreadable_snapshots) == [f"{TORN_DAY}.csv"]
    assert len(fe.load_ledger(tmp_path / "processed")) == 1


def test_a_readable_pass_reports_no_unreadable_file(tmp_path: Path) -> None:
    """Counted when zero too, so "every file read" is distinguishable from
    "nobody checked"."""
    _moneyline_day(tmp_path / "archive")

    result = fe.settle_snapshots(
        pd.DataFrame(columns=["date", "player_id", "player", "team"]),
        _games(DAY),
        team_names=TEAM_MAP,
        archive_dir=tmp_path / "archive",
        processed_dir=tmp_path / "processed",
        now=LATER,
    )

    assert result.unreadable_snapshots == {}
    assert "0 pending snapshot file(s) could not be read" in result.summary_line()


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


def test_the_runner_names_the_file_restates_the_ledger_and_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No real data directory can rescue or break this run.
    monkeypatch.setattr(fe, "DATA_DIR", tmp_path / "default_data")
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(team_names_module, "RAW_DIR", tmp_path / "default_raw")
    processed = tmp_path / "processed"
    processed.mkdir()
    _games(TORN_DAY, DAY).to_csv(processed / "team_games.csv", index=False)
    save_team_name_map(TEAM_MAP, processed_dir=processed)
    archive = tmp_path / "archive"
    _torn(tmp_path, archive, "an_unclosed_quote")
    _moneyline_day(archive)
    arguments = [
        "--processed-dir", str(processed),
        "--output-dir", str(tmp_path / "outputs"),
        "--archive-dir", str(archive),
    ]
    module = load_script("run_forward_evidence.py")

    code = module.main(arguments)
    captured = capsys.readouterr()

    assert code == 2
    assert any(
        line.startswith("::error::") and f"{TORN_DAY}.csv" in line
        for line in captured.err.splitlines()
    ), captured.err
    assert (tmp_path / "outputs" / fe.REPORT_MARKDOWN_FILENAME).is_file()
    assert list(fe.load_ledger(processed)["snapshot_date"].astype(str)) == [DAY]
    assert _markers(archive) == [DAY]

    again = module.main(arguments)
    captured = capsys.readouterr()

    assert again == 2
    assert f"{TORN_DAY}.csv" in captured.err
    assert len(fe.load_ledger(processed)) == 1


# --------------------------------------------------------------------------
# The subprocess half: a real kill and a real kernel refusal.
# --------------------------------------------------------------------------

CHILD = r"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_cut_short_child", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.child_main(sys.argv[2], sys.argv[3], int(sys.argv[4]))
"""


def child_main(archive: str, how: str, cut: int) -> None:
    """Runs in a subprocess: freeze the slate, and fail `how` at `cut` bytes."""
    if how == "file_size_limit":
        import resource

        resource.setrlimit(resource.RLIMIT_FSIZE, (cut, cut))
    elif how == "kill":
        pd.DataFrame.to_csv = cut_every_write_at(
            cut, lambda: os.kill(os.getpid(), signal.SIGKILL)
        )
    else:
        raise SystemExit(f"unknown failure {how!r}")
    freeze(Path(archive))


def _child(archive: Path, how: str, cut: int) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-c", CHILD, str(Path(__file__).resolve()),
         str(archive), how, str(cut)],
        capture_output=True, text=True, env=env, timeout=120,
    )
