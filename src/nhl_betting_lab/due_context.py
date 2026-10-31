"""Tonight's context on each Due List row (Cooper, 2026-10-31: "yes do all that except 4").

Three things beside each row, read from what the card already fetches:

1. **Not dressing.** When the player's club has posted tonight's lines (at
   least `lineups.MINIMUM_LISTED` skaters, the card's own rule) and he is not
   on them, he is taken off the list and named in its notes. A listed player
   who does not play is a void, not a pick. A club with no lines posted leaves
   every row as it was.
2. **His line and power-play unit tonight** (`line_tonight`, `pp_tonight`;
   not `line`, which is the prop's 0.5), and how they
   moved against the latest earlier capture that posted his club (`line_before`,
   `pp_before`, `line_move`: "up", "down", "same", "mixed", or None with no
   earlier capture). `status` carries Daily Faceoff's injury or game-time
   note when there is one.
3. **The goalie he faces** (`opp_goalie`, `opp_goalie_status`), whether that
   goalie is his club's backup (`opp_goalie_backup`: not the goalie with the
   most starts in his club's last `STARTS_WINDOW` games), and his record
   against expected goals from the ratings file the card prices on
   (`opp_goalie_vs_expected`: +0.06 means he has allowed 6% more goals than
   the shots he faced were worth, regressed; None when there is no file).

All of it is information beside the row. Apart from taking off a player not
in his club's posted lines, nothing here filters, ranks or stakes a row, and
nothing reaches the model's selections, the snapshot or the forward ledger.
None of it is measured against prices.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from nhl_betting_lab.data.line_combinations import EV_GROUPS, PP_GROUPS
from nhl_betting_lab.data.starting_goalies import load_starters
from nhl_betting_lab.lineups import LINES_DIRNAME, MINIMUM_LISTED, RATINGS_FILE, load_captures
from nhl_betting_lab.models.player_props import player_key, player_name_aliases
from nhl_betting_lab.providers.team_names import resolve_team

#: Goalie starts per club read to decide who its number one is.
STARTS_WINDOW = 20
#: A start, as the backtest counts one (`walk_forward.GOALIE_START_SECONDS`).
START_SECONDS = 2400

CONTEXT_FIELDS = (
    "line_tonight", "pp_tonight", "line_before", "pp_before", "line_move", "status",
    "opp_goalie", "opp_goalie_status", "opp_goalie_backup", "opp_goalie_vs_expected",
)


def _aliases(name: object) -> set[str]:
    return set(player_name_aliases(name))


def _sheet(rows: pd.DataFrame) -> dict[str, dict[str, str]] | None:
    """{alias: {line, pp, status}} for one club's capture, or None if not posted."""
    ev = rows[rows["group_identifier"].isin(EV_GROUPS)]
    if ev["player"].nunique() < MINIMUM_LISTED:
        return None
    pp_of = {alias: str(group).upper()
             for name, group in rows[rows["group_identifier"].isin(PP_GROUPS)][["player", "group_identifier"]]
             .itertuples(index=False) for alias in _aliases(name)}
    table: dict[str, dict[str, str]] = {}
    for r in ev.itertuples(index=False):
        status = str(getattr(r, "injury_status", "") or "").strip()
        if str(getattr(r, "game_time_decision", "") or "").strip().lower() == "true":
            status = f"{status}, game-time decision" if status else "game-time decision"
        for alias in _aliases(r.player):
            table[alias] = {"line": str(r.group_identifier).upper(), "pp": pp_of.get(alias, ""), "status": status}
    return table


def _sheets(processed: Path, day: str) -> dict[str, dict[str, dict[str, str]]]:
    captures = load_captures(processed, day)
    if captures.empty:
        return {}
    out = {}
    for team, rows in captures.groupby("team_abbreviation"):
        sheet = _sheet(rows)
        if sheet is not None:
            out[str(team).strip().upper()] = sheet
    return out


def _earlier_sheets(processed: Path, day: str, teams: set[str]) -> dict[str, dict[str, dict[str, str]]]:
    """Each club's latest posted capture before `day`."""
    directory = Path(processed) / LINES_DIRNAME
    if not directory.is_dir():
        return {}
    out: dict[str, dict[str, dict[str, str]]] = {}
    for path in sorted(directory.glob("*.csv"), reverse=True):
        if path.stem >= day or not (teams - set(out)):
            continue
        for team, sheet in _sheets(processed, path.stem).items():
            if team in teams and team not in out:
                out[team] = sheet
    return out


def _find(sheet: Mapping[str, dict[str, str]], name: object) -> dict[str, str] | None:
    for alias in _aliases(name):
        if alias in sheet:
            return sheet[alias]
    return None


def _rank(line: str | None, pp: str | None) -> tuple[int, int]:
    number = int(line[1:]) if line and line[1:].isdigit() else 9
    unit = int(pp[2:]) if pp and pp[2:].isdigit() else 3
    return number, unit


def line_move(line: str | None, pp: str | None, before_line: str | None, before_pp: str | None) -> str | None:
    """"up", "down", "same" or "mixed" (one better, one worse); None with nothing to compare."""
    if not line or not before_line:
        return None
    (n, u), (bn, bu) = _rank(line, pp), _rank(before_line, before_pp)
    better = (n < bn) or (u < bu)
    worse = (n > bn) or (u > bu)
    if better and worse:
        return "mixed"
    return "up" if better else "down" if worse else "same"


def _number_ones(logs: pd.DataFrame, day: str) -> dict[str, str]:
    """{club: player_key of the goalie with the most starts in its last STARTS_WINDOW games}."""
    needed = {"role", "team", "player", "date", "toi_seconds"}
    if logs is None or logs.empty or not needed <= set(logs.columns):
        return {}
    g = logs[(logs["role"].astype(str) == "goalie")
             & (pd.to_numeric(logs["toi_seconds"], errors="coerce") >= START_SECONDS)
             & (logs["date"].astype(str).str[:10] < day)]
    out: dict[str, str] = {}
    for team, rows in g.groupby("team"):
        recent = rows.sort_values("date").tail(STARTS_WINDOW)
        counts = recent["player"].map(lambda p: player_key(str(p))).value_counts()
        if len(counts):
            out[str(team).strip().upper()] = str(counts.index[0])
    return out


def _goalie_ids(logs: pd.DataFrame) -> dict[str, int]:
    if logs is None or logs.empty or not {"role", "player", "player_id"} <= set(logs.columns):
        return {}
    goalies = logs[logs["role"].astype(str) == "goalie"].drop_duplicates("player_id")
    return {player_key(str(r.player)): int(r.player_id) for r in goalies.itertuples()}


def _goalie_factors(processed: Path) -> tuple[dict[str, float], float | None]:
    try:
        ratings = json.loads((Path(processed) / RATINGS_FILE).read_text(encoding="utf-8"))
        goalies = {str(k): float(v) for k, v in (ratings.get("goalies") or {}).items()}
        unseen = ratings.get("unseen_goalie")
        return goalies, None if unseen is None else float(unseen)
    except (OSError, ValueError, TypeError, AttributeError):
        return {}, None


def annotate(
    rows: list[dict[str, Any]],
    *,
    processed: Path,
    day: str,
    now: datetime,
    logs: pd.DataFrame,
    team_names: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """The rows with tonight's context, and a note per row taken off.

    Every kept row carries every `CONTEXT_FIELDS` key (None where unknown).
    """
    sheets = _sheets(processed, day)
    earlier = _earlier_sheets(processed, day, {str(r.get("team", "")).upper() for r in rows}) if rows else {}
    listing = load_starters(processed, now=now)
    starters: dict[str, tuple[str, str]] = {}
    if not listing.unknown:
        for (listed_day, team), (goalie, strength) in listing.listings.items():
            club = resolve_team(team, team_names) or str(team).strip().upper()
            if listed_day == day and goalie:
                starters[str(club).upper()] = (goalie, strength)
    ones = _number_ones(logs, day)
    ids = _goalie_ids(logs)
    factors, unseen = _goalie_factors(processed)
    kept: list[dict[str, Any]] = []
    removed: list[str] = []
    for row in rows:
        out = dict(row)
        for key in CONTEXT_FIELDS:
            out.setdefault(key, None)
        team = str(row.get("team", "")).strip().upper()
        sheet = sheets.get(team)
        if sheet is not None:
            spot = _find(sheet, row.get("player"))
            if spot is None:
                removed.append(f"{row.get('player')} ({team}, {row.get('market')}): not in {team}'s posted lines tonight, "
                               "so not listed.")
                continue
            out.update(line_tonight=spot["line"], pp_tonight=spot["pp"] or None, status=spot["status"] or None)
            before = _find(earlier.get(team, {}), row.get("player"))
            if before is not None:
                out.update(line_before=before["line"], pp_before=before["pp"] or None)
                out["line_move"] = line_move(spot["line"], spot["pp"], before["line"], before["pp"])
        opp = str(row.get("opponent", "")).strip().upper()
        if opp in starters:
            goalie, strength = starters[opp]
            out.update(opp_goalie=goalie, opp_goalie_status=strength or None)
            if opp in ones:
                out["opp_goalie_backup"] = player_key(goalie) != ones[opp]
            gid = ids.get(player_key(goalie))
            factor = factors.get(str(gid)) if gid is not None else None
            if factor is None and factors and unseen is not None:
                factor = unseen
            if factor is not None:
                out["opp_goalie_vs_expected"] = round(factor - 1.0, 4)
        kept.append(out)
    return kept, removed


def line_text(row: Mapping[str, Any]) -> str:
    """"F1, PP1 (up from F2, PP2)", or "-" with no posted line."""
    line = row.get("line_tonight")
    if not line:
        return "-"
    text = f"{line}, {row.get('pp_tonight')}" if row.get("pp_tonight") else str(line)
    move, before = row.get("line_move"), row.get("line_before")
    if move in {"up", "down", "mixed"} and before:
        was = f"{before}, {row.get('pp_before')}" if row.get("pp_before") else str(before)
        text += f" ({'changed' if move == 'mixed' else move} from {was})"
    if row.get("status"):
        text += f"; {row['status']}"
    return text


def goalie_text(row: Mapping[str, Any]) -> str:
    """"Backup Joe Smith (Confirmed), +6% goals vs expected", or "-" with no listing."""
    name = row.get("opp_goalie")
    if not name:
        return "-"
    text = ("backup " if row.get("opp_goalie_backup") else "") + str(name)
    if row.get("opp_goalie_status"):
        text += f" ({row['opp_goalie_status']})"
    vs = row.get("opp_goalie_vs_expected")
    if vs is not None and not pd.isna(vs):
        text += f", {float(vs) * 100:+.0f}% goals vs expected"
    return text
