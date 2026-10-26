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
* **the dressed lineup's attack** (Cooper, 2026-10-25, PostHockey's model
  step 3): every skater carries an offensive rating (`skater_ratings`, a
  Marcel-style forecast of his offensive game score per game) and a club's
  attack moves by half the gap between tonight's posted skaters and its
  usual eighteen, between `MIN_ATTACK_FACTOR` and `MAX_ATTACK_FACTOR`. A
  missing star takes attack off; a star back from injury puts it back on.
  (Until 2026-10-25 this was the share of recent points held by regulars
  out tonight, which could only ever take attack off.)
* **the dressed lineup's defence** (Cooper, 2026-10-26, the defensive half
  of PostHockey's Net Rating): every skater's goals prevented a game from his
  on-ice 5v5 xG against relative to his teammates (`shadow.defence`, read
  from the ratings file, never imported), and a club's defence moves by half
  the goals tonight's sheet prevents beyond its usual eighteen's, between
  `MIN_DEFENCE_FACTOR` and `MAX_DEFENCE_FACTOR`.

Nothing here is measured against prices: the lines have no history before
the capture began (2026-09-29), so this ships on Cooper's word and is
measured forward. Every name is matched through `player_name_aliases`, so a
spelling the two sources share is one player, and a club whose page lists
fewer than `MINIMUM_LISTED` skaters is treated as not posted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
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

#: Recent games that decide a club's usual eighteen, and the range of the
#: attack factor tonight's lineup can set.
SHARE_GAMES = 20
MIN_ATTACK_FACTOR = 0.85
MAX_ATTACK_FACTOR = 1.10
HOLE_WEIGHT = 0.5

#: The defensive half (Cooper, 2026-10-26: PostHockey's Net Rating has one).
#: Each skater's goals prevented a game, from his on-ice xG against relative
#: to his team at 5v5 (`shadow.defence`, published in the ratings file as
#: `skater_defence`); a club's defence moves by `HOLE_WEIGHT` of the goals
#: tonight's sheet prevents beyond its usual eighteen's, as a share of
#: `LEAGUE_GOALS_PER_GAME`, between these bounds.
RATINGS_FILE = "shadow_team_ratings.json"
LEAGUE_GOALS_PER_GAME = 3.0
MIN_DEFENCE_FACTOR = 0.90
MAX_DEFENCE_FACTOR = 1.10

#: A skater's offensive game score per game: Luszczyszyn's offensive weights,
#: as PostHockey's Net Rating uses them. The logs do not split primary from
#: secondary assists, so an assist is the mean of the two (0.7, 0.55), and
#: they hold no penalties drawn.
GAME_SCORE_WEIGHTS = {"goals": 0.75, "assists": 0.625, "shots_on_goal": 0.075}
#: The current season, the one before and the one before that, weighted as
#: PostHockey's Estimated Net Rating weights a forward's offence.
SEASON_WEIGHTS = (1.0, 0.5, 0.3)
#: Games of his position's newcomer average a rating starts from (PostHockey's
#: P0: 10 for a forward's offence, 20 for a defenceman's).
PRIOR_GAMES = {"F": 10.0, "D": 20.0}
#: Skater-seasons under this many games define a position's newcomer average.
NEWCOMER_GAMES = 41
#: Aging (PostHockey's Estimated Net Rating ages each past season to the
#: player's age now): a curve fitted on consecutive seasons of the same
#: skater, each with at least `AGING_PAIR_GAMES` games, needing
#: `AGING_MINIMUM_PAIRS` such pairs; ages read inside `AGING_AGES`.
AGING_PAIR_GAMES = 20
AGING_MINIMUM_PAIRS = 150
AGING_AGES = (19.0, 38.0)


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
    #: club -> defence (goals against) multiplier from tonight's sheet
    defence_factors: dict[str, float] = field(default_factory=dict)
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


def _group(position: object) -> str:
    return "D" if str(position).strip().upper().startswith("D") else "F"


def _began(season: float) -> int:
    """The year a season began, from an NHL id (20252026) or the year itself."""
    return int(season) // 10000 if int(season) > 9999 else int(season)


def _age(born: str | None, season: float) -> float | None:
    """Age on 1 January of `season` (an NHL id like 20252026, or the year it
    began), or None."""
    try:
        year, month, day = (int(part) for part in str(born)[:10].split("-"))
    except (TypeError, ValueError):
        return None
    began = _began(season)
    low, high = AGING_AGES
    return min(high, max(low, (began + 1) - year - ((month - 1) * 30.5 + day) / 365.25))


def aging_curves(by_season: pd.DataFrame, born: dict[str, str]) -> dict[str, tuple[float, float]]:
    """{position group: (c0, c1)}: a season's change in game score per game is
    c0 + c1 * age, so the level at an age is A(age) = c0 * age + c1 * age^2 / 2.

    Fitted per group by weighted least squares on consecutive-season pairs
    (weight: the pair's harmonic mean of games). Survivors only: a skater
    who fell out of the league leaves no pair, so the old end is flatter
    than the truth, as PostHockey says of its own curve. A group with too
    few pairs gets no curve.
    """
    out: dict[str, tuple[float, float]] = {}
    rows = by_season[by_season["games"] >= AGING_PAIR_GAMES].sort_values(["player_id", "_season"])
    pairs = []
    for player, seasons in rows.groupby("player_id"):
        listed = seasons.to_dict("records")
        for before, after in zip(listed, listed[1:]):
            if _began(after["_season"]) - _began(before["_season"]) != 1:
                continue
            age = _age(born.get(str(player)), after["_season"])
            if age is None:
                continue
            weight = 2.0 / (1.0 / before["games"] + 1.0 / after["games"])
            pairs.append((after["group"], age - 0.5, after["mean"] - before["mean"], weight))
    frame = pd.DataFrame(pairs, columns=["group", "age", "delta", "weight"])
    for group, rows in frame.groupby("group"):
        if len(rows) < AGING_MINIMUM_PAIRS:
            continue
        w = rows["weight"].to_numpy()
        x = rows["age"].to_numpy()
        y = rows["delta"].to_numpy()
        design = pd.DataFrame({"c0": 1.0, "c1": x}).to_numpy() * w[:, None] ** 0.5
        c0, c1 = (float(c) for c in np.linalg.lstsq(design, y * w**0.5, rcond=None)[0])
        out[str(group)] = (c0, c1)
    return out


def _level(curve: tuple[float, float], age: float) -> float:
    c0, c1 = curve
    return c0 * age + c1 * age * age / 2.0


def _seasons_of(skaters: pd.DataFrame) -> pd.DataFrame:
    """One row per skater-season: games, game score per game, group, name."""
    frame = skaters.copy()
    frame["_gs"] = sum(
        weight * pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        for column, weight in GAME_SCORE_WEIGHTS.items()
    )
    frame["_group"] = frame["position"].map(_group) if "position" in frame else "F"
    if "season" in frame:
        frame["_season"] = pd.to_numeric(frame["season"], errors="coerce")
    else:  # a season starts in the autumn: date it by the year it began
        dates = pd.to_datetime(frame["date"].astype(str).str[:10], errors="coerce")
        frame["_season"] = dates.dt.year - (dates.dt.month < 7).astype(int)
    frame = frame.dropna(subset=["_season"])
    return frame.groupby(["player_id", "_season"]).agg(
        games=("_gs", "size"), mean=("_gs", "mean"), group=("_group", "last"), name=("player", "last")
    ).reset_index()


def skater_ratings(
    logs: pd.DataFrame, day: str, birth_dates: dict[int, str] | None = None
) -> tuple[dict[str, float], dict[str, float]]:
    """({alias: offensive rating per game}, {position group: newcomer rating}).

    Each of a skater's last three seasons before `day` gives his game score
    per game and his games; the rating is their `SEASON_WEIGHTS`-weighted
    mean with `PRIOR_GAMES` of his position's newcomer average mixed in, so
    a skater with little history reads close to a newcomer and a veteran
    close to his own record. With `birth_dates` ({NHL id: "YYYY-MM-DD"},
    the cached rosters'), each past season is first moved along the
    position's aging curve (`aging_curves`) to his age this season.
    """
    skaters = logs[(logs["role"].astype(str) == "skater") & (logs["date"].astype(str).str[:10] < day)]
    if skaters.empty:
        return {}, {"F": 0.0, "D": 0.0}
    every = _seasons_of(skaters)
    seasons = sorted(every["_season"].unique())[-len(SEASON_WEIGHTS):][::-1]
    by_season = every[every["_season"].isin(seasons)]
    newcomers = by_season[by_season["games"] < NEWCOMER_GAMES]
    prior = {
        group: float(
            (rows["mean"] * rows["games"]).sum() / rows["games"].sum()
        ) if not rows.empty else 0.0
        for group, rows in ((g, newcomers[newcomers["group"] == g]) for g in ("F", "D"))
    }
    weight_of = {season: SEASON_WEIGHTS[k] for k, season in enumerate(seasons)}
    born = {str(k): v for k, v in (birth_dates or {}).items()}
    # The curve is fitted on every season the logs hold, not only the three.
    curves = aging_curves(every, born) if born else {}
    ratings: dict[str, float] = {}
    for player, rows in by_season.groupby("player_id"):
        group = str(rows["group"].iloc[-1])
        w = rows["_season"].map(weight_of) * rows["games"]
        means = rows["mean"]
        curve = curves.get(group)
        if curve is not None and seasons:
            now = _age(born.get(str(player)), seasons[0])
            if now is not None:
                means = means + [
                    _level(curve, now) - _level(curve, _age(born[str(player)], season))
                    for season in rows["_season"]
                ]
        p0 = PRIOR_GAMES[group]
        rating = float((w * means).sum() + p0 * prior[group]) / float(w.sum() + p0)
        for alias in _aliases(rows["name"].iloc[-1]):
            ratings[alias] = rating
    return ratings, prior


def _lineup_attack(
    logs: pd.DataFrame,
    roles: dict[str, dict[str, tuple[str, str]]],
    sheets: dict[str, list[tuple[str, str]]],
    day: str,
    birth_dates: dict[int, str] | None = None,
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Each posted club's attack factor from its dressed skaters' ratings."""
    factors: dict[str, float] = {}
    absent: dict[str, list[str]] = {}
    if logs is None or logs.empty:
        return factors, absent
    ratings, prior = skater_ratings(logs, day, birth_dates)
    skaters = logs[(logs["role"].astype(str) == "skater") & (logs["date"].astype(str).str[:10] < day)]
    for team, table in roles.items():
        rows = skaters[skaters["team"].astype(str) == team]
        games = (
            rows[["game_id", "date"]].drop_duplicates("game_id").sort_values("date")["game_id"].tolist()
        )
        recent = rows[rows["game_id"].isin(games[-SHARE_GAMES:])]
        if recent.empty:
            continue
        last_five = set(games[-5:])
        recent = recent.assign(position=recent["position"] if "position" in recent else "F")
        usual = recent.groupby("player").agg(
            games=("game_id", "nunique"), group=("position", "last")
        ).sort_values("games", ascending=False).head(18)
        usual_total = sum(
            next((ratings[a] for a in _aliases(name) if a in ratings), prior[_group(group)])
            for name, group in usual["group"].items()
        )
        # Tonight's eighteen: every skater on the posted even-strength lines,
        # rated by name; one with no record reads as a newcomer at his slot.
        position_of = {
            alias: _group(position)
            for name, position in recent[["player", "position"]].drop_duplicates("player").itertuples(index=False)
            for alias in _aliases(name)
        }
        dressed = set(table)
        tonight_total = 0.0
        for name, group in sheets.get(team, []):
            aliases = _aliases(name)
            rating = next((ratings[a] for a in aliases if a in ratings), None)
            if rating is None:
                slot = "D" if str(group).lower().startswith("d") else next(
                    (position_of[a] for a in aliases if a in position_of), "F"
                )
                rating = prior[slot]
            tonight_total += rating
        names = []
        for name, player_rows in recent.groupby("player"):
            if player_rows["game_id"].isin(last_five).sum() >= 3 and not (_aliases(name) & dressed):
                names.append(str(name))
        sheet = len(sheets.get(team, []))
        if usual_total > 0 and sheet:
            # Per skater, so a sheet of sixteen is not read as two men short.
            ratio = (tonight_total / sheet) / (usual_total / len(usual))
            factors[team] = min(
                MAX_ATTACK_FACTOR, max(MIN_ATTACK_FACTOR, 1.0 + HOLE_WEIGHT * (ratio - 1.0))
            )
        if names:
            absent[team] = sorted(names)
    return factors, absent


def load_skater_defence(processed_dir: Path) -> dict[str, float]:
    """{NHL id: goals prevented a game} from the ratings file; empty without it."""
    try:
        ratings = json.loads((Path(processed_dir) / RATINGS_FILE).read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in (ratings.get("skater_defence") or {}).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _lineup_defence(
    logs: pd.DataFrame,
    roles: dict[str, dict[str, tuple[str, str]]],
    sheets: dict[str, list[tuple[str, str]]],
    day: str,
    impacts: dict[str, float],
) -> dict[str, float]:
    """Each posted club's defence factor from its dressed skaters' defence.

    A skater with no defensive rating counts as zero (a league-average
    defender relative to his teammates), as does every skater in the usual
    eighteen without one, so a club with no rated skaters moves nothing.
    """
    factors: dict[str, float] = {}
    if logs is None or logs.empty or not impacts:
        return factors
    skaters = logs[(logs["role"].astype(str) == "skater") & (logs["date"].astype(str).str[:10] < day)]
    id_of: dict[str, str] = {}
    for name, pid in skaters[["player", "player_id"]].drop_duplicates("player_id").itertuples(index=False):
        for alias in _aliases(name):
            id_of[alias] = str(int(pid)) if pd.notna(pid) else ""

    def impact(name: object) -> float:
        for alias in _aliases(name):
            pid = id_of.get(alias)
            if pid and pid in impacts:
                return impacts[pid]
        return 0.0

    for team in roles:
        rows = skaters[skaters["team"].astype(str) == team]
        games = rows[["game_id", "date"]].drop_duplicates("game_id").sort_values("date")["game_id"].tolist()
        recent = rows[rows["game_id"].isin(games[-SHARE_GAMES:])]
        sheet = sheets.get(team, [])
        if recent.empty or not sheet:
            continue
        usual = recent.groupby("player")["game_id"].nunique().sort_values(ascending=False).head(18)
        usual_mean = sum(impact(name) for name in usual.index) / len(usual)
        tonight_mean = sum(impact(name) for name, _ in sheet) / len(sheet)
        prevented = (tonight_mean - usual_mean) * 18
        factor = 1.0 - HOLE_WEIGHT * prevented / LEAGUE_GOALS_PER_GAME
        factors[team] = min(MAX_DEFENCE_FACTOR, max(MIN_DEFENCE_FACTOR, factor))
    return factors


def tonight_lineups(
    processed_dir: Path, day: str, logs: pd.DataFrame, birth_dates: dict[int, str] | None = None
) -> TonightLineups:
    """Everything the card reads from tonight's posted lines; empty when none."""
    captures = load_captures(processed_dir, day)
    lineups = TonightLineups()
    if captures.empty:
        return lineups
    sheets: dict[str, list[tuple[str, str]]] = {}
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
        sheets[team] = list(
            ev_rows[["player", "group_identifier"]].drop_duplicates("player").itertuples(index=False, name=None)
        )
        if "injury_status" in rows.columns:
            hurt = rows[rows["injury_status"].astype(str).str.strip() != ""]["player"]
            lineups.injured[team] = set(hurt.astype(str))
    lineups.role_minutes = _fit_roles(logs, day)
    lineups.attack_factors, lineups.absent = _lineup_attack(logs, lineups.roles, sheets, day, birth_dates)
    lineups.defence_factors = _lineup_defence(
        logs, lineups.roles, sheets, day, load_skater_defence(processed_dir)
    )
    return lineups
