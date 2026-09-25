"""Freeze what the model said before the game, settle it after, accumulate.

The historical backtest re-prices past games with walk-forward fits, which is
honest but reconstructed. This is the stronger thing the docs promise: **the
opinion the live card actually held, written down before puck drop, settled
against the boxscore after, and never revised.** It is also the only possible
price evidence for the markets no book retains historically — hits and the
regulation three-way — and the accumulating out-of-sample test for every
market and every shipped policy at once.

Three stages, each idempotent:

**Snapshot.** After the card prices a slate, every priced row is written to
`data/archive/priced_snapshots/{league date}.csv` with the model's
probability, the edge against the price as sold, and the policy verdicts in
force. A snapshot is evidence and is never overwritten: the first opinion of
the day stands, because "the card's opinion" repriced at a better moment is
not the card's opinion any more. It is published whole or not at all, because
whatever stands under the day's name is the day's opinion for good.

**Settle.** Once a snapshot day's results are final, each row is settled from
the boxscore — via the same identity join and the same settlement rules the
historical backtest uses, because a second copy of either is how every join
bug in this repository started. Settled rows append to the forward ledger; a
player who never dressed voids (stake returned), and a row whose game never
produced a result within the patience window is recorded as unsettleable,
counted, never guessed.

**Report.** `data/outputs/forward_evidence.md`: per-market accumulating
intervals in the house vocabulary — sample sizes beside every number,
family-corrected, and "no demonstrated edge" in those words while it is true.
The detection arithmetic says roughly six hundred bets separate a real +8%
from zero, so the report also says plainly how far along that road the ledger
is.
"""

from __future__ import annotations

import json
import math
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.stores import existing_row_count, read_store

from nhl_betting_lab.backtest.team_walk_forward import (
    settle_moneyline,
    settle_puck_line,
    settle_regulation_3_way,
    settle_team_total,
    settle_total,
)
from nhl_betting_lab.config import DATA_DIR, MIN_EDGE, MIN_PROP_EDGE, OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.player_props import player_name_aliases
from nhl_betting_lab.models.value import OddsError, american_to_implied, profit_on_win
from nhl_betting_lab.puck_drop import check_commence_time
from nhl_betting_lab.providers.team_names import (
    TEAM_NAMES_FILENAME,
    UnresolvedTeamsError,
    resolve_team,
)
from nhl_betting_lab.reports.player_props_backtest import settle as settle_prop
from nhl_betting_lab.season import clean_text, row_game_date


SNAPSHOT_DIRNAME = "priced_snapshots"
LEDGER_FILENAME = "forward_evidence.csv"
REPORT_MARKDOWN_FILENAME = "forward_evidence.md"
REPORT_JSON_FILENAME = "forward_evidence.json"

#: Days to keep waiting for a result before recording a row unsettleable.
#: Postponed games are rescheduled within days; a fortnight without a final
#: boxscore means the row will never settle against the game it priced.
PATIENCE_DAYS = 14

SNAPSHOT_COLUMNS = (
    "snapshot_date",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "line",
    "american_odds",
    "book",
    "model_probability",
    "edge",
    "verdicts_in_force",
)

LEDGER_COLUMNS = SNAPSHOT_COLUMNS + (
    "settled_at",
    "outcome",  # won | lost | push | void | unsettleable
    "actual",
    "profit_units",
)


def snapshots_dir(archive_dir: Path | None = None) -> Path:
    return (Path(archive_dir) if archive_dir else DATA_DIR / "archive") / (
        SNAPSHOT_DIRNAME
    )


def write_snapshot(
    prices: pd.DataFrame,
    probabilities: Mapping[tuple, float],
    *,
    key_for,
    verdicts_line: str,
    snapshot_date: str,
    now: datetime,
    archive_dir: Path | None = None,
    tally: dict[str, object] | None = None,
) -> Path | None:
    """Freeze today's priced opinions. Returns the file, or None when nothing
    was written — because one already stands, or because the slate has
    prices and not one row could be frozen.

    `key_for(row, market, selection, line)` is the card's own key function,
    passed in rather than imported by both sides — the probability map and
    the snapshot must agree on the key by construction.

    ## Only a game not yet under way is frozen

    `now` is required, and every row goes through the card's own puck-drop
    rule (`puck_drop.check_commence_time`): a game that has started, or whose
    start cannot be confirmed, is not frozen. This used to freeze whatever it
    was handed, and the card handed it the unguarded prices before
    `build_card`'s guard ran — so a run after a face-off (a Global Series
    morning, a late manual dispatch) froze in-play prices beside pre-game
    probabilities, and settlement booked them as opinions "written down
    before puck drop". The snapshot has no freeze time, so nothing afterwards
    could tell them apart.

    ## Nothing to freeze writes nothing — never an empty snapshot

    The first snapshot of a day stands and is never replaced. A run that
    could not price anything — its team-name map or its models missing, so
    `probabilities` came back empty — used to write an EMPTY snapshot for a
    day with games, which then stood: every later, working run that day
    found it and froze nothing. Now no run writes an empty snapshot. That
    includes a run with no prices at all: once a degraded run's state became
    restorable (scripts/restore_state.py), a run whose price fetch failed —
    no prices, so it looked like an empty slate — would have frozen an empty
    day that the next run restored and could not replace. A day with no
    games has nothing to settle, so it loses nothing by leaving no file.

    `tally`, when given, receives "state" ("frozen", "exists" or
    "nothing_to_freeze") and the counts "frozen", "started" and
    "unconfirmed".
    """
    counts: dict[str, object] = {"frozen": 0, "started": 0, "unconfirmed": 0}
    if tally is not None:
        tally.update(counts)
    directory = snapshots_dir(archive_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{snapshot_date}.csv"
    if target.exists():
        # The first opinion of the day stands. A repriced snapshot is not the
        # card's opinion any more, and two snapshots for one day would let
        # the flattering one be the one that settles.
        if tally is not None:
            tally["state"] = "exists"
        return None

    rows: list[dict[str, object]] = []
    for row in prices.itertuples():
        market = clean_text(getattr(row, "market", ""))
        selection = clean_text(getattr(row, "selection", "")).lower()
        line_value = getattr(row, "line", None)
        try:
            line = (
                None
                if line_value is None or pd.isna(line_value)
                else float(line_value)
            )
        except (TypeError, ValueError):
            line = None
        probability = probabilities.get(
            key_for(row, market=market, selection=selection, line=line)
        )
        if probability is None:
            continue
        verdict = check_commence_time(getattr(row, "commence_time", ""), now=now)
        if not verdict.playable:
            counts[verdict.state] = int(counts.get(verdict.state, 0)) + 1
            continue
        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            continue
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "commence_time": clean_text(getattr(row, "commence_time", "")),
                "home_team": clean_text(getattr(row, "home_team", "")),
                "away_team": clean_text(getattr(row, "away_team", "")),
                "market": market,
                "player": clean_text(getattr(row, "player", "")),
                "selection": selection,
                "line": line,
                "american_odds": price,
                "book": clean_text(getattr(row, "book", "")),
                "model_probability": float(probability),
                "edge": float(probability) - implied,
                "verdicts_in_force": verdicts_line,
            }
        )
    counts["frozen"] = len(rows)
    if tally is not None:
        tally.update(counts)
    if not rows:
        if tally is not None:
            tally["state"] = "nothing_to_freeze"
        return None
    frame = pd.DataFrame(rows, columns=list(SNAPSHOT_COLUMNS))
    if not _publish_whole(frame, target):
        # Another run froze the day while this one was writing. Its opinion
        # came first, so it stands.
        if tally is not None:
            tally["state"] = "exists"
        return None
    if tally is not None:
        tally["state"] = "frozen"
    return target


#: Ends the name of a snapshot still being written. Such a file is never a
#: day's opinion, and no reader's `*.csv` glob matches it.
PARTIAL_SUFFIX = ".partial"


def _publish_whole(frame: pd.DataFrame, target: Path) -> bool:
    """Write `frame` to `target` whole or not at all, and never over a file
    that is already there. Returns False when `target` already stood.

    ## A cut-short snapshot used to stand for good

    This used to be `frame.to_csv(target)`, written straight onto the day's
    name. If the write was cut short (the process killed, the disk full),
    part of a file stayed there. `write_snapshot` treats any file under that
    name as the day's first opinion, so every later run printed "already
    stands" and froze nothing. The failure-shape audit reproduced this
    through the real scripts on the 2026-04-14 slate. A 48,218-byte snapshot
    cut at 28,672 bytes, inside the quoted verdicts field, made
    `run_forward_evidence.py` exit 1 with a ParserError on that pass and on
    every later one. It wrote no report, no ledger rows and no marker, and
    it blocked a later complete day as well. Only 1 of that file's 11 block
    boundaries falls inside a quote. A cut at any of the others parses
    cleanly as a day missing its later rows, with the last row garbled (a
    model probability of 0.0 where the card said 0.698), and that short day
    would have settled quietly as the card's opinion. CI was exposed too.
    The state upload runs `if: always()`, and scripts/restore_state.py
    restores the newest completed run whatever its conclusion, so a torn
    file from a failed card step would have been carried into every later
    run.

    So the bytes go first to a temporary file in the same directory, and are
    flushed and fsynced there. Only then is the day's name linked to them,
    so the name never points at data that is not yet on disk. `os.link` is
    atomic and, unlike `os.replace`, refuses a name that already exists. The
    first opinion therefore still stands if a second run froze the same day
    while this write was in flight; `replace` would silently put the later
    opinion over it.

    The temporary's name starts with a dot and ends in `PARTIAL_SUFFIX`, not
    ".csv". Settlement and the CLV report both read `*.csv`, so neither can
    take an unfinished write for a day. If the process is killed before the
    link, that file stays and no snapshot does, and the next run freezes the
    day whole. The name is unique to this call, so two writers never share
    one. On any other failure the temporary is removed and the error raised,
    as the in-place write raised it. The encoding and line ending are the
    ones `to_csv(target)` used, so a complete snapshot's bytes are unchanged.
    """
    temporary = target.with_name(
        f".{target.name}.{os.getpid()}.{secrets.token_hex(4)}{PARTIAL_SUFFIX}"
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="") as stream:
            frame.to_csv(stream, index=False, lineterminator="\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _read_snapshot(path: Path) -> tuple[pd.DataFrame | None, str]:
    """The snapshot in `path`, or None and the reason it is not one.

    ## An unreadable file waits, named; it no longer stops the whole pass

    `settle_snapshots` read every pending file with a bare `pd.read_csv`.
    One damaged file raised out of the whole pass, so no day settled, and
    `run_forward_evidence.py` died before it restated the ledger as its
    report, on that run and on every later one. The damage could be a torn
    write, which `_publish_whole` now prevents, or anything that damages a
    file after it is written. A zero-byte file (a write killed before its
    first flush), an unclosed quote and half of a multi-byte character each
    raise. Half a header parses as an empty frame with the wrong columns,
    which used to be marked settled as an empty day. None of these is the
    card's opinion, and none can be guessed back into one. So such a day is
    neither settled nor marked. It is named in the result and retried on
    every pass, and the other days settle as they would have. A file cut
    cleanly between two rows cannot be told from a short day at all; only
    writing it whole prevents that.
    """
    try:
        frame = pd.read_csv(path)
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        UnicodeDecodeError,
    ) as error:
        detail = str(error).strip().splitlines()
        return None, f"{type(error).__name__}: {detail[0] if detail else ''}"
    missing = [column for column in SNAPSHOT_COLUMNS if column not in frame.columns]
    if missing:
        return None, f"missing column(s) {', '.join(missing)}"
    return frame, ""


@dataclass
class SettlementResult:
    """What one settlement pass did, so silence stays legible."""

    snapshots_seen: int = 0
    snapshots_settled: int = 0
    snapshots_waiting: int = 0
    rows_settled: int = 0
    rows_void: int = 0
    rows_unsettleable: int = 0
    #: Rows of the pending snapshots read this pass that name a team the
    #: team-name map could not resolve, and the names. Counted when zero too,
    #: so "every team resolved" is distinguishable from "nobody checked".
    rows_unresolved_teams: int = 0
    unresolved_team_names: list[str] = field(default_factory=list)
    #: Pending snapshot files that could not be read as a snapshot, by file
    #: name, with the reason. Each is left unsettled and unmarked, and is
    #: retried on every pass (see `_read_snapshot`).
    unreadable_snapshots: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (
            f"{self.snapshots_settled} of {self.snapshots_seen} pending "
            f"snapshot(s) settled ({self.snapshots_waiting} still waiting "
            f"for results); {self.rows_settled} row(s) settled, "
            f"{self.rows_void} void, {self.rows_unsettleable} unsettleable; "
            f"{self.rows_unresolved_teams} row(s) named a team the team-name "
            "map could not resolve. "
            f"{len(self.unreadable_snapshots)} pending snapshot file(s) could "
            "not be read and were left unsettled."
        )


def _unresolved_team_rows(
    snapshot: pd.DataFrame, team_names: Mapping[str, str]
) -> tuple[int, set[str]]:
    """Rows naming a team the map cannot resolve, and the names themselves."""
    rows = 0
    names: set[str] = set()
    for row in snapshot.itertuples():
        missing = [
            label
            for label in (
                clean_text(getattr(row, "home_team", "")),
                clean_text(getattr(row, "away_team", "")),
            )
            if resolve_team(label, team_names) is None
        ]
        if missing:
            rows += 1
            names.update(label for label in missing if label)
    return rows, names


def _player_index(
    logs: pd.DataFrame, game_date: str
) -> dict[str, dict[int, tuple[str, float | None, dict[str, float]]]]:
    """alias -> {player_id: (team, actuals per settlement column)} for one day."""
    day = logs[logs["date"].astype(str).str.slice(0, 10) == game_date]
    index: dict[str, dict[int, tuple[str, dict[str, float]]]] = {}
    for row in day.itertuples():
        actuals = {
            market.settles_on: float(
                pd.to_numeric(getattr(row, market.settles_on, 0), errors="coerce")
                or 0.0
            )
            for market in MARKETS_BY_KEY.values()
            if market.is_prop
        }
        entry = (str(row.team).strip().upper(), actuals)
        for alias in player_name_aliases(row.player):
            index.setdefault(alias, {})[int(row.player_id)] = entry
    return index


def _finite_line(value: object) -> float | None:
    """The row's line as a real number, or None.

    NaN is the shape a missing CSV field takes, and it is silent poison in a
    settlement: every comparison against it is False, so an absent line
    settles "under" as a win and "over" as a loss without raising anything.
    A market that needs a line and has none is unsettleable — a state this
    ledger already knows how to record.
    """
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _settle_prop_row(
    row, player_index, game_teams: set[str]
) -> tuple[str, float | None, float]:
    """(outcome, actual, profit) for one snapshot prop row."""
    market = MARKETS_BY_KEY.get(str(row.market))
    if market is None or not market.settles_on:
        return "unsettleable", None, 0.0
    candidates: dict[int, tuple[str, dict[str, float]]] = {}
    for alias in player_name_aliases(row.player):
        candidates.update(player_index.get(alias, {}))
    if game_teams:
        candidates = {
            player_id: entry
            for player_id, entry in candidates.items()
            if entry[0] in game_teams
        }
    if len(candidates) > 1:
        return "unsettleable", None, 0.0
    if not candidates:
        # The player never entered the game: books void the bet.
        return "void", None, 0.0
    _, actuals = next(iter(candidates.values()))
    actual = actuals.get(market.settles_on)
    if actual is None:
        return "unsettleable", None, 0.0
    line = _finite_line(row.line)
    if line is None:
        return "unsettleable", actual, 0.0
    try:
        won, push = settle_prop(actual, line, str(row.selection))
    except (TypeError, ValueError):
        return "unsettleable", actual, 0.0
    if push:
        return "push", actual, 0.0
    if won:
        return "won", actual, profit_on_win(float(row.american_odds))
    return "lost", actual, -1.0


def _settle_team_row(row, game) -> tuple[str, float | None, float]:
    """(outcome, actual, profit) for one snapshot team row."""
    home_goals = int(game.home_goals)
    away_goals = int(game.away_goals)
    regulation = bool(getattr(game, "regulation", True))
    market = str(row.market)
    selection = str(row.selection)
    price = float(row.american_odds)

    if market == "moneyline":
        try:
            winner = settle_moneyline(home_goals, away_goals)
        except ValueError:
            return "unsettleable", None, 0.0
        won, push = winner == selection, False
        actual = float(home_goals - away_goals)
    elif market == "regulation_3_way":
        try:
            result = settle_regulation_3_way(
                home_goals, away_goals, regulation=regulation
            )
        except ValueError:
            return "unsettleable", None, 0.0
        won, push = result == selection, False
        actual = float(home_goals - away_goals)
    elif market == "puck_line":
        line = _finite_line(row.line)
        if line is None:
            return "unsettleable", None, 0.0
        side = (
            ("home_minus" if line < 0 else "home_plus")
            if selection == "home"
            else ("away_minus" if line < 0 else "away_plus")
        )
        won, push = settle_puck_line(
            home_goals, away_goals, regulation=regulation, line=abs(line)
        )[side]
        actual = float(home_goals - away_goals)
    elif market == "total_goals":
        line = _finite_line(row.line)
        if line is None:
            return "unsettleable", None, 0.0
        over, push = settle_total(home_goals, away_goals, line)
        won = over if selection == "over" else (not over and not push)
        actual = float(home_goals + away_goals)
    elif market == "team_total":
        # The side rides in the selection vocabulary (`home_over` …); a row
        # outside it cannot be settled and must never be guessed at.
        side, _, direction = selection.partition("_")
        line = _finite_line(row.line)
        if line is None or side not in {"home", "away"} or direction not in {
            "over",
            "under",
        }:
            return "unsettleable", None, 0.0
        side_goals = home_goals if side == "home" else away_goals
        over, push = settle_team_total(side_goals, line)
        won = over if direction == "over" else (not over and not push)
        actual = float(side_goals)
    else:
        return "unsettleable", None, 0.0

    if push:
        return "push", actual, 0.0
    if won:
        return "won", actual, profit_on_win(price)
    return "lost", actual, -1.0


def settle_snapshots(
    logs: pd.DataFrame,
    games: pd.DataFrame,
    *,
    team_names: Mapping[str, str],
    archive_dir: Path | None = None,
    processed_dir: Path | None = None,
    now: datetime | None = None,
) -> SettlementResult:
    """Settle every pending snapshot whose results are in.

    A snapshot settles as a unit only when every game on it is final — a
    half-settled day would make the ledger's totals move twice for one day,
    and whichever half settled first would look like the whole day.

    ## A map that resolves nothing refuses; it does not write the day off

    Every row finds its game through `team_names`. The runner loads that map
    from `team_names.csv` and rebuilds it from the boxscore cache when the
    file is absent; with neither, it holds only the six Utah and Arizona
    alias entries. Such a map resolves both teams of no row, so every game
    lookup missed, the day waited out `PATIENCE_DAYS`, and then every row
    was appended as `unsettleable` and the day marked settled — permanently,
    in a ledger that cannot be rebuilt. Nothing raised.

    The card freezes only rows whose teams it resolved, so a pending snapshot
    in which no row resolves both teams says the map is broken, not the day.
    Such a snapshot raises `UnresolvedTeamsError`, and it is checked across
    every pending snapshot BEFORE any marker is touched or any row appended:
    markers are written inside the loop and the ledger after it, so a refusal
    raised mid-loop would leave earlier days marked settled with their rows
    never written.
    """
    moment = now or datetime.now(timezone.utc)
    directory = snapshots_dir(archive_dir)
    ledger_path = (
        Path(processed_dir)
        if processed_dir
        else DATA_DIR / "processed"
    ) / LEDGER_FILENAME
    result = SettlementResult()
    if not directory.is_dir():
        return result

    finals = {
        (
            str(game.date)[:10],
            str(game.home_team).strip().upper(),
            str(game.away_team).strip().upper(),
        ): game
        for game in games.itertuples()
    }
    # A day is done when its marker exists. The ledger alone cannot say so:
    # a snapshot that settled with zero rows (an empty preseason day) leaves
    # no ledger trace and would re-settle forever. The marker is a sidecar
    # rather than a rename, because a snapshot's name is part of the
    # evidence and evidence does not get renamed.
    settled_days = {
        marker.name.removesuffix(".settled")
        for marker in directory.glob("*.settled")
    }
    if ledger_path.is_file():
        settled_days |= set(
            pd.read_csv(ledger_path, usecols=["snapshot_date"])[
                "snapshot_date"
            ].astype(str)
        )

    pending: list[tuple[str, pd.DataFrame]] = []
    for path in sorted(directory.glob("*.csv")):
        if path.stem in settled_days:
            continue
        snapshot, problem = _read_snapshot(path)
        if snapshot is None:
            # Named and left pending. It used to raise out of the whole pass.
            result.unreadable_snapshots[path.name] = problem
            continue
        pending.append((path.stem, snapshot))
    names: set[str] = set()
    refused: list[tuple[str, int]] = []
    for day, snapshot in pending:
        unresolved, missing = _unresolved_team_rows(snapshot, team_names)
        result.rows_unresolved_teams += unresolved
        names |= missing
        if len(snapshot) and unresolved == len(snapshot):
            refused.append((day, len(snapshot)))
    result.unresolved_team_names = sorted(names)
    if refused:
        preview = ", ".join(result.unresolved_team_names[:6]) + (
            f" and {len(names) - 6} more" if len(names) > 6 else ""
        )
        raise UnresolvedTeamsError(
            f"Refusing to settle: {len(refused)} pending snapshot day(s) "
            f"({', '.join(f'{day}: {rows:,} row(s)' for day, rows in refused)}) "
            "name two teams the team-name map can resolve on no row "
            f"({len(team_names)} spelling(s) in the map). Unresolved: "
            f"{preview or '(the rows name no team)'}. Settled anyway, every "
            f"row would find no game, wait out the {PATIENCE_DAYS}-day "
            "patience window, and then be appended to the forward ledger as "
            "unsettleable with the day marked settled for good. No day was "
            "marked and no row was appended. Point --processed-dir at a "
            f"directory holding {TEAM_NAMES_FILENAME} "
            "(scripts/run_gameday_card.py writes it) together with the "
            "--archive-dir or --output-dir that belongs with it, or run where "
            "data/raw/nhl/boxscore can rebuild it."
        )

    new_rows: list[dict[str, object]] = []
    # Days this pass finished, marked only once their rows are on disk. See
    # the end of this function.
    finished: list[str] = []
    for day, snapshot in pending:
        result.snapshots_seen += 1
        if snapshot.empty:
            finished.append(day)
            result.snapshots_settled += 1
            continue

        # Which final game each row belongs to, by league date and abbrevs.
        def game_for(row):
            return finals.get(
                (
                    row_game_date(row),
                    resolve_team(getattr(row, "home_team", ""), team_names)
                    or "",
                    resolve_team(getattr(row, "away_team", ""), team_names)
                    or "",
                )
            )

        games_found = [game_for(row) for row in snapshot.itertuples()]
        age_days = (
            moment.date() - datetime.fromisoformat(day).date()
        ).days
        if any(game is None for game in games_found) and age_days <= PATIENCE_DAYS:
            # Results not all in yet. Wait — a half-settled day would make
            # the ledger move twice for one day.
            result.snapshots_waiting += 1
            continue

        player_indexes: dict[str, dict] = {}
        for row, game in zip(snapshot.itertuples(), games_found):
            base = {
                column: getattr(row, column, None)
                for column in SNAPSHOT_COLUMNS
            }
            base["settled_at"] = moment.isoformat(timespec="seconds")
            if game is None:
                outcome, actual, profit = "unsettleable", None, 0.0
                result.rows_unsettleable += 1
            else:
                market = MARKETS_BY_KEY.get(str(row.market))
                if market is not None and market.is_prop:
                    game_day = row_game_date(row)
                    if game_day not in player_indexes:
                        player_indexes[game_day] = _player_index(logs, game_day)
                    game_teams = {
                        resolve_team(row.home_team, team_names),
                        resolve_team(row.away_team, team_names),
                    }
                    game_teams.discard(None)
                    outcome, actual, profit = _settle_prop_row(
                        row, player_indexes[game_day], game_teams
                    )
                else:
                    outcome, actual, profit = _settle_team_row(row, game)
                if outcome == "void":
                    result.rows_void += 1
                elif outcome == "unsettleable":
                    result.rows_unsettleable += 1
                else:
                    result.rows_settled += 1
            base["outcome"] = outcome
            base["actual"] = actual
            base["profit_units"] = profit
            new_rows.append(base)
        finished.append(day)
        result.snapshots_settled += 1

    if new_rows:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(new_rows, columns=list(LEDGER_COLUMNS))
        existing_rows = 0
        if ledger_path.is_file():
            existing = read_store(
                ledger_path, columns=LEDGER_COLUMNS, for_append=True
            )
            # THE FLOOR IS NOT THE PARSE. `len(existing)` is what pandas
            # managed to read; `existing_row_count` is a line count taken
            # straight off the file. A guard whose floor comes from the same
            # read it is protecting cannot catch that read going wrong — it
            # simply lowers the bar to match, and a short write sails
            # through. `merge_capture_store` published a one-row file over a
            # five-hundred-row store that way and exited 0, because its floor
            # was the zero a failed read had just returned.
            #
            # `read_store(for_append=True)` already raises on a damaged file,
            # which closes the loud version of that. This closes the quiet
            # one: `stat` failing, or any future path that returns a short
            # frame without raising. The two observations fail for unrelated
            # reasons, so the maximum of them is only wrong if both are, and
            # `existing_row_count` says in its own docstring that every
            # shrink guard here needs it. This one did not use it.
            existing_rows = max(
                len(existing), existing_row_count(ledger_path)
            )
            frame = pd.concat([existing, frame], ignore_index=True)
        # The ledger only ever grows: it is an append-only record of opinions
        # that have already settled, and a season of it cannot be
        # reconstructed from anywhere else — the prices it settled against
        # are gone. A write that would shrink it means the file being
        # concatenated is not the file that was read, and the safe move is to
        # refuse rather than to publish a shorter history as the whole truth.
        if len(frame) < existing_rows:
            raise ValueError(
                f"Refusing to write a forward ledger of {len(frame)} rows "
                f"over one holding {existing_rows}. The ledger is "
                "append-only and cannot be rebuilt; something upstream lost "
                "rows."
            )
        frame.to_csv(ledger_path, index=False, lineterminator="\n")
    # MARKED ONLY NOW. These were touched inside the loop, before the write,
    # so when `read_store` refused a damaged ledger or the shrink guard
    # refused a short one, every day of the pass was already marked, its
    # rows never written, and the marker kept it from ever being retried:
    # the guards that exist to prevent loss caused it. Touched after the
    # write, a refusal leaves every day pending and the next pass retries it.
    # A crash between the write and these touches is harmless: a day with
    # rows is also recognised as settled by its `snapshot_date` in the
    # ledger, and an empty day has nothing to append twice.
    for day in finished:
        (directory / f"{day}.settled").touch()
    return result


def load_ledger(processed_dir: Path | None = None) -> pd.DataFrame:
    path = (
        Path(processed_dir) if processed_dir else DATA_DIR / "processed"
    ) / LEDGER_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    return pd.read_csv(path)


def build_forward_report(
    ledger: pd.DataFrame, *, now: datetime | None = None
) -> dict:
    """Per-market accumulating evidence, in the house vocabulary.

    Two views of the same ledger, kept separate because they answer different
    questions. **Opinions** is every priced row the model held a view on —
    the calibration-grade stream. **Bets** is the subset clearing the shipped
    edge bars at the price as sold — the stream an allowlist decision will
    eventually rest on. Mixing them would flatter whichever is worse.

    ## One bet per wager, at the best price the card could have taken

    The snapshot freezes one row per book, and the ledger keeps them all —
    they are evidence, and the CLV report reads them. This report used to
    count every one: a selection quoted by eight books was eight opinions
    and eight bets. docs/when_this_ends.md registers the 2027-04-25 decision
    on "one bet per wager at the best price the card could have taken", and
    counting quotes is the defect that once published "-1.6% over 73,918
    bets, interval excluding zero" for a policy that measured -0.3% spanning
    zero. Replayed on the bought card window, the per-quote rule read -1.34%
    over 114,292 with the interval excluding zero — "Stop" under the
    registration — where one bet per wager reads -0.03% over 28,287,
    spanning zero; and the 3,000-opinion floor would have been met about
    3.7x early. So every count here is taken after
    `closing_lines.collapse_to_best`, the one collapse the CLV report
    already applies to the same snapshots. `rows` stays the ledger's row
    count and `wagers` is what it collapses to, so the factor is visible.
    """
    from nhl_betting_lab.closing_lines import collapse_to_best
    from nhl_betting_lab.stats import roi_interval

    moment = now or datetime.now(timezone.utc)
    payload: dict = {
        "generated_at": moment.isoformat(timespec="seconds"),
        "rows": int(len(ledger)),
        "wagers": 0,
        "markets": {},
        "unsettleable": 0,
        "void": 0,
    }
    if ledger.empty:
        return payload

    wagers = collapse_to_best(ledger)
    payload["wagers"] = int(len(wagers))
    settled = wagers[wagers["outcome"].isin(["won", "lost", "push"])]
    payload["unsettleable"] = int((wagers["outcome"] == "unsettleable").sum())
    payload["void"] = int((wagers["outcome"] == "void").sum())

    markets = sorted(set(settled["market"].astype(str)))
    for market_key in markets:
        subset = settled[settled["market"].astype(str) == market_key]
        market = MARKETS_BY_KEY.get(market_key)
        bar = (
            MIN_PROP_EDGE if market is not None and market.is_prop else MIN_EDGE
        )
        bets = subset[subset["edge"].astype(float) >= bar]
        entry: dict = {
            "opinions": int(len(subset)),
            "first_date": str(subset["snapshot_date"].min()),
            "last_date": str(subset["snapshot_date"].max()),
        }
        if len(bets):
            interval = roi_interval(
                bets["profit_units"].astype(float).tolist(),
                wins=int((bets["outcome"] == "won").sum()),
                pushes=int((bets["outcome"] == "push").sum()),
                looks=len(markets),
            )
            entry["bets"] = interval.bets
            entry["profit_units"] = interval.profit
            entry["roi"] = interval.roi
            entry["low"] = interval.low
            entry["high"] = interval.high
            entry["includes_zero"] = interval.includes_zero
            entry["verdict"] = interval.verdict()
        else:
            entry["bets"] = 0
            entry["verdict"] = (
                "No settled row has yet cleared the shipped edge bar, so "
                "there is nothing to measure. That is a statement about the "
                "season so far, not about the model."
            )
        payload["markets"][market_key] = entry
    return payload


def render_forward_report(payload: dict) -> str:
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, bets_needed_to_detect

    lines = [
        "# Forward evidence",
        "",
        (
            "The opinion the live card actually held, written down before "
            "puck drop, settled against the boxscore after, never revised. "
            "This is the only possible price evidence for the markets no "
            "book retains historically — hits and the regulation three-way — "
            "and the accumulating out-of-sample test for everything else."
        ),
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Ledger rows: {payload['rows']:,}"
        + (
            f" — one per book — on {payload.get('wagers', 0):,} wager(s), "
            "each counted once at the best price the card could have taken "
            f"({payload['void']:,} void, {payload['unsettleable']:,} "
            "unsettleable)"
            if payload["rows"]
            else ""
        ),
        "",
    ]
    if not payload["markets"] and not payload["rows"]:
        lines += [
            "## Nothing settled yet",
            "",
            (
                "The ledger is empty or nothing on it has settled. Before "
                "the season starts this is the correct state, not a fault: "
                "forward evidence can only begin accumulating when books "
                "post prices and games produce results."
            ),
            "",
        ]
        return "\n".join(lines)
    if not payload["markets"]:
        # ROWS, AND NONE OF THEM A RESULT. This used to share the branch
        # above, so a ledger whose every row went void or unsettleable was
        # published to card-feed as "Nothing settled yet ... Before the
        # season starts this is the correct state, not a fault". The
        # failure-shape audit (finding 44) settled the real 2026-27 opener,
        # Boston v the Rangers, with its finals never fetched: sixteen days
        # on, "Ledger rows: 2 (0 void, 2 unsettleable)" and then that
        # reassurance. It is the quiet version of a broken results fetch —
        # the runs stay green, settlement waits two weeks and writes the day
        # off — and the page called the write-off normal. Two props for
        # scratched players beside a total with no final read the same way.
        #
        # A ledger with rows on it is not the preseason state. A day
        # reaches the ledger only when all its games were found or its
        # patience ran out, so every row here is a game that was played or
        # waited out. The empty ledger keeps the preseason text above, word
        # for word; this says what the counts are and where to look, and
        # never that nothing is wrong.
        lines += [
            "## No row has settled to a result",
            "",
            (
                f"The ledger holds {payload['rows']:,} row(s) on "
                f"{payload.get('wagers', 0):,} wager(s), and not one wager "
                f"settled won, lost or push: {payload['void']:,} void, "
                f"{payload['unsettleable']:,} unsettleable. This is not the "
                "empty state before a season. A day reaches the ledger only "
                "when every game on it was found or its "
                f"{PATIENCE_DAYS}-day patience window ran out, so these are "
                "games that were played or waited out, and none of them "
                "produced a result here."
            ),
            "",
            (
                "A void is a player who never entered a game that was found. "
                "An unsettleable row is a game that produced no final result "
                "inside the patience window, or a row that could not be "
                "settled against its game. Unsettleable rows with nothing "
                "settled beside them usually mean results never reached "
                "settlement: read the settlement summary Gameday Refresh "
                "prints when it settles the forward ledger, then check the "
                "results fetch, the team-name map that finds each row's "
                "game, and whether a preseason game slipped past the card's "
                "filter."
            ),
            "",
        ]
        return "\n".join(lines)

    lines += [
        "## Accumulated so far, at the shipped edge bars",
        "",
        (
            "| Market | Opinions | Bets | Profit | ROI | 95% interval "
            "| Includes zero |"
        ),
        "|:-------|---------:|-----:|-------:|----:|:-------------|:--|",
    ]
    for market, entry in sorted(payload["markets"].items()):
        if entry["bets"]:
            lines.append(
                f"| `{market}` | {entry['opinions']:,} | {entry['bets']:,} "
                f"| {entry['profit_units']:+.1f}u | {entry['roi']:+.1%} "
                f"| {entry['low']:+.1%} .. {entry['high']:+.1%} "
                f"| {'yes' if entry['includes_zero'] else 'no'} |"
            )
        else:
            lines.append(
                f"| `{market}` | {entry['opinions']:,} | 0 | — | — | — | — |"
            )
    lines += [""]
    for market, entry in sorted(payload["markets"].items()):
        lines.append(f"- `{market}`: {entry['verdict']}")
    lines += [
        "",
        "## How far along the road this is",
        "",
        (
            f"Separating a true +8% edge from zero takes about "
            f"{bets_needed_to_detect(0.08):,} bets per market. Every interval "
            f"that includes zero means **{NO_DEMONSTRATED_EDGE}** — those "
            "words, for as long as they are true."
        ),
        "",
        "## What this stream is and is not",
        "",
        (
            "- Frozen before the games: nothing here was repriced after the "
            "fact, which the historical backtest cannot claim."
        ),
        (
            "- Settled by the same identity join and settlement rules as the "
            "historical backtest — one copy of each, on purpose."
        ),
        (
            "- A void is a player who never entered (stake returned, as "
            "books do). An unsettleable row is a game that never produced a "
            "final result inside the patience window — counted, never "
            "guessed."
        ),
        (
            "- Recommendations were never placed as bets. This ledger prices "
            "a paper record of the shipped policy, nothing more."
        ),
        "",
    ]
    return "\n".join(lines)


def save_forward_report(
    payload: dict, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / REPORT_MARKDOWN_FILENAME
    markdown.write_text(render_forward_report(payload), encoding="utf-8")
    json_path = directory / REPORT_JSON_FILENAME
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
