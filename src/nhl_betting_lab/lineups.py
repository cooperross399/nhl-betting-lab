"""Tonight's posted lineups: who is out, and what role everyone else has.

Cooper, 2026-10-21, asked for the model to carry tonight's injuries and
scratches, with the missing player's ice time moved to his teammates, and
each player's current line and power-play unit. Daily Faceoff posts each
club's projected lines and power-play units, and its injured list, and
`scripts/capture_line_combinations.py` captures them into
`data/processed/line_combinations/<league day>.csv`; Gameday Refresh runs it
before the card. This reads the latest capture per club and gives the card:

* **who is out**: a skater whose club has posted lines and who is not on any
  of its even-strength lines. His props get no opinion, and the card names
  him. A club with no posted lines tonight decides nothing.
* **expected ice time from his role**: his line and power-play unit, through
  `models.role_minutes` (each line's ice-time distribution, fitted walk-
  forward on the logs), blended with his own last-ten ice time by the weight
  that table fits. A promoted player gets the higher line's minutes, which is
  how a missing player's minutes reach the teammates who replace him.
* **the hole in a club's attack**: the share of its skaters' recent points
  scored by players out tonight, half of which is taken off its attack (the
  other half is what the replacements produce), never below
  `MIN_ATTACK_FACTOR`.

Nothing here is measured against prices: the lines have no history before
the capture began (2026-09-29), so this ships on Cooper's word and is
measured forward. Every name is matched through `player_name_aliases`, so a
spelling the two sources share is one player, and a club whose page lists
fewer than `MINIMUM_LISTED` skaters is treated as not posted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from nhl_betting_lab.data.line_combinations import EV_GROUPS, PP_GROUPS
from nhl_betting_lab.models.player_props import player_name_aliases
from nhl_betting_lab.models.role_minutes import RoleMinutes, fit_role_minutes, with_usage_bands

LINES_DIRNAME = "line_combinations"

#: A club's page counts as posted only with at least this many skaters on its
#: even-strength lines (twelve forwards and six defencemen dress).
MINIMUM_LISTED = 16

#: The days of logs the role table is fitted on.
ROLE_HISTORY_DAYS = 400

#: Recent games read for a club's point shares, and the floor on the attack
#: factor a hole can leave.
SHARE_GAMES = 20
MIN_ATTACK_FACTOR = 0.85
HOLE_WEIGHT = 0.5


def _aliases(name: object) -> set[str]:
    return set(player_name_aliases(name))


@dataclass
class TonightLineups:
    """Tonight's posted roles per club, and the role-minutes table."""

    #: club -> {alias -> (even-strength group, power-play group)}
    roles: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    #: club -> names Daily Faceoff lists as injured
    injured: dict[str, set[str]] = field(default_factory=dict)
    role_minutes: RoleMinutes | None = None
    #: club -> attack multiplier from tonight's absences
    attack_factors: dict[str, float] = field(default_factory=dict)
    #: club -> names of recent regulars not in tonight's lines
    absent: dict[str, list[str]] = field(default_factory=dict)
    #: "Player (TEAM)" for each priced prop the card withheld because his
    #: club posted lines without him; filled by `card_pricing.price_props`.
    out_tonight: set[str] = field(default_factory=set)

    def posted(self, team: str) -> bool:
        return str(team) in self.roles

    def role(self, team: str, *names: object) -> tuple[str, str] | None:
        """(ev, pp) for a player on a posted club, or None when he is not on
        its lines (out tonight). Raises KeyError for a club not posted."""
        table = self.roles[str(team)]
        for name in names:
            for alias in _aliases(name):
                if alias in table:
                    return table[alias]
        return None

    def expected_toi(self, ev: str, pp: str, trailing_seconds: float) -> float:
        """Ice time from his line and unit, blended with his own last ten."""
        if self.role_minutes is None:
            return float(trailing_seconds)
        labels = [label for label in (ev, pp) if label]
        if not labels:
            return float(trailing_seconds)
        return float(
            self.role_minutes.blend(*labels, trailing_toi_seconds=trailing_seconds).mean_seconds
        )

    def describe(self) -> str:
        out = sum(len(names) for names in self.absent.values())
        return (
            f"lines posted for {len(self.roles)} club(s); {out} recent regular(s) "
            "not in tonight's lines"
        )


def load_captures(processed_dir: Path, day: str) -> pd.DataFrame:
    """Tonight's capture, the latest `retrieved_at` per club."""
    path = Path(processed_dir) / LINES_DIRNAME / f"{day}.csv"
    if not path.is_file():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()
    needed = {"team_abbreviation", "player", "group_identifier", "retrieved_at"}
    if frame.empty or not needed <= set(frame.columns):
        return pd.DataFrame()
    latest = frame.groupby("team_abbreviation")["retrieved_at"].transform("max")
    return frame[frame["retrieved_at"] == latest]


def _fit_roles(logs: pd.DataFrame, day: str) -> RoleMinutes | None:
    if logs is None or logs.empty:
        return None
    frame = logs.copy()
    dates = pd.to_datetime(frame["date"], errors="coerce")
    start = pd.Timestamp(day) - pd.Timedelta(days=ROLE_HISTORY_DAYS)
    frame = frame[dates.notna() & (dates >= start) & (dates < pd.Timestamp(day))]
    if frame.empty:
        return None
    try:
        banded = with_usage_bands(frame)
        banded = banded.sort_values(["player_id", "date"])
        banded["_trailing"] = banded.groupby("player_id")["toi_seconds"].transform(
            lambda s: pd.to_numeric(s, errors="coerce").shift(1).rolling(10, min_periods=3).mean()
        )
        return fit_role_minutes(banded, before=day, trailing_column="_trailing", ranked=banded)
    except (KeyError, ValueError):
        return None


def _attack_holes(
    logs: pd.DataFrame, roles: dict[str, dict[str, tuple[str, str]]], day: str
) -> tuple[dict[str, float], dict[str, list[str]]]:
    factors: dict[str, float] = {}
    absent: dict[str, list[str]] = {}
    if logs is None or logs.empty:
        return factors, absent
    skaters = logs[(logs["role"].astype(str) == "skater") & (logs["date"].astype(str).str[:10] < day)]
    for team, table in roles.items():
        rows = skaters[skaters["team"].astype(str) == team]
        games = (
            rows[["game_id", "date"]].drop_duplicates("game_id").sort_values("date")["game_id"].tolist()
        )
        recent_games = games[-SHARE_GAMES:]
        last_five = set(games[-5:])
        recent = rows[rows["game_id"].isin(recent_games)]
        points = pd.to_numeric(recent["points"], errors="coerce").fillna(0)
        total = float(points.sum())
        missing_points = 0.0
        names: list[str] = []
        for name, player_rows in recent.groupby("player"):
            if player_rows["game_id"].isin(last_five).sum() < 3:
                continue  # not a regular lately; his absence is not news
            if _aliases(name) & set(table):
                continue
            names.append(str(name))
            missing_points += float(points[player_rows.index].sum())
        share = missing_points / total if total > 0 else 0.0
        factors[team] = max(MIN_ATTACK_FACTOR, 1.0 - HOLE_WEIGHT * share)
        if names:
            absent[team] = sorted(names)
    return factors, absent


def tonight_lineups(processed_dir: Path, day: str, logs: pd.DataFrame) -> TonightLineups:
    """Everything the card reads from tonight's posted lines; empty when none."""
    captures = load_captures(processed_dir, day)
    lineups = TonightLineups()
    if captures.empty:
        return lineups
    for team, rows in captures.groupby("team_abbreviation"):
        team = str(team).strip().upper()
        ev_rows = rows[rows["group_identifier"].isin(EV_GROUPS)]
        if ev_rows["player"].nunique() < MINIMUM_LISTED:
            continue
        table: dict[str, tuple[str, str]] = {}
        pp_of = {
            alias: str(group)
            for name, group in rows[rows["group_identifier"].isin(PP_GROUPS)][
                ["player", "group_identifier"]
            ].itertuples(index=False)
            for alias in _aliases(name)
        }
        for name, group in ev_rows[["player", "group_identifier"]].itertuples(index=False):
            for alias in _aliases(name):
                table[alias] = (str(group), pp_of.get(alias, ""))
        lineups.roles[team] = table
        if "injury_status" in rows.columns:
            hurt = rows[rows["injury_status"].astype(str).str.strip() != ""]["player"]
            lineups.injured[team] = set(hurt.astype(str))
    lineups.role_minutes = _fit_roles(logs, day)
    lineups.attack_factors, lineups.absent = _attack_holes(logs, lineups.roles, day)
    return lineups
