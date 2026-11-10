"""The league's scoring environment, read into the card's props and totals.

Cooper, 2026-11-10 ("All"): NHL scoring this season ran about 7.0 goals a
game from late October against about 6.2 before 10-19, while the models'
rates are fitted on every game the logs hold (three seasons and more), so
every expected count sat at the old level and population B leaned under.

This reads the league's recent rate of each scoring stat against the rate
over the games the models were fitted on:

* **recent**: regular-season games in the `ENV_DAYS` days before tonight;
* **reference**: every regular-season game before tonight (the window the
  props model's rates and the team model's league total are fitted on);
* **target**: reference x (1 + w x (recent / reference - 1)), with
  w = games / (games + `ENV_SHRINKAGE_GAMES`), so three weeks of games keep
  only part of their move.

A prop's expected count is multiplied by target / (the model's own league
level), and so is the team model's expected total. The model's own level is
the reference times whatever league-wide move last-five team form already
put in (`form_level`): when every club's last five are up, form has already
lifted every count a little, and the environment tops it up to the target
rather than adding to it. The multiplier is clamped to `ENV_RANGE`.

Only the stats in `ENV_STATS` move; blocked shots, hits and goalie saves do
not (`scripts/run_scoring_environment.py` measures each stat's drift, and
the constants here were set from that run). A night with fewer than
`MIN_RECENT_GAMES` recent games moves nothing.

Off by default everywhere: `PlayerPropsModel.scoring_env` and
`TeamModel.environment` start empty / at 1.0, and the walk-forward prices it
only when asked (`generate_prop_samples(scoring_env=True)`), so every
committed measurement stands. The card turns it on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from collections.abc import Mapping

import pandas as pd

#: Days of league games the recent rate reads.
ENV_DAYS = 21
#: Regular-season games at which the recent move counts half.
ENV_SHRINKAGE_GAMES = 150
#: The multiplier on an expected count is read inside this range.
ENV_RANGE = (0.90, 1.12)
#: Fewer recent games than this and nothing moves (opening week).
MIN_RECENT_GAMES = 40
#: The prop stats the environment moves.
ENV_STATS: frozenset[str] = frozenset({"goals", "assists", "points", "shots_on_goal"})
#: Every stat the measurement reads (the environment moves only ENV_STATS).
MEASURED_STATS = ("goals", "assists", "points", "shots_on_goal", "blocked_shots", "hits")
#: The team model's key: total goals a game, from the games table.
TEAM_GOALS = "total_goals"
#: What the card writes each run.
REPORT_MD = "scoring_environment.md"
REPORT_JSON = "scoring_environment.json"


@dataclass
class EnvReading:
    """One night's reading: per stat, the recent and reference per-game rates
    and the shrunk target as a ratio to the reference."""

    night: str = ""
    recent_games: int = 0
    reference_games: int = 0
    recent: dict[str, float] = field(default_factory=dict)
    reference: dict[str, float] = field(default_factory=dict)
    #: target / reference, per stat (1.0 when too few recent games).
    ratio: dict[str, float] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.recent_games >= MIN_RECENT_GAMES and bool(self.ratio)

    def describe(self) -> str:
        if not self.active:
            return (
                f"scoring environment off ({self.recent_games} regular-season "
                f"game(s) in the last {ENV_DAYS} days, {MIN_RECENT_GAMES} needed)"
            )
        parts = []
        for stat in (TEAM_GOALS, *MEASURED_STATS):
            if stat in self.ratio and stat in self.recent:
                parts.append(
                    f"{stat} {self.recent[stat]:.2f}/game vs {self.reference[stat]:.2f} "
                    f"-> x{self.ratio[stat]:.3f}"
                )
        return (
            f"scoring environment over {self.recent_games} games in the last "
            f"{ENV_DAYS} days against {self.reference_games}: " + "; ".join(parts)
        )


def _regular(frame: pd.DataFrame) -> pd.DataFrame:
    if "game_type" not in frame.columns:
        return frame
    kind = pd.to_numeric(frame["game_type"], errors="coerce")
    return frame[kind == 2]


def league_game_table(logs: pd.DataFrame, games: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per regular-season game: its date, both clubs' skater totals
    of every measured stat, and (from `games`, when given) total goals."""
    columns = ["game_id", "date", *MEASURED_STATS, TEAM_GOALS]
    parts = []
    if logs is not None and not logs.empty:
        skaters = _regular(logs)
        skaters = skaters[skaters["role"].astype(str) == "skater"].copy()
        if not skaters.empty:
            for stat in MEASURED_STATS:
                skaters[stat] = pd.to_numeric(skaters[stat], errors="coerce").fillna(0.0)
            skaters["date"] = skaters["date"].astype(str).str[:10]
            parts.append(skaters.groupby(["game_id", "date"])[list(MEASURED_STATS)].sum())
    table = pd.concat(parts, axis=1) if parts else pd.DataFrame()
    if games is not None and not games.empty:
        reg = _regular(games).copy()
        reg["home_goals"] = pd.to_numeric(reg["home_goals"], errors="coerce")
        reg["away_goals"] = pd.to_numeric(reg["away_goals"], errors="coerce")
        reg = reg.dropna(subset=["home_goals", "away_goals"])
        reg["date"] = reg["date"].astype(str).str[:10]
        goals = (reg["home_goals"] + reg["away_goals"]).groupby([reg["game_id"], reg["date"]]).sum()
        goals.name = TEAM_GOALS
        table = goals.to_frame() if table.empty else table.join(goals, how="outer")
    if table.empty:
        return pd.DataFrame(columns=columns)
    table = table.reset_index()
    for column in columns:
        if column not in table.columns:
            table[column] = float("nan")
    return table[columns].sort_values(["date", "game_id"]).reset_index(drop=True)


def reading(table: pd.DataFrame, night: str) -> EnvReading:
    """The environment for `night` from games strictly before it."""
    night = str(night)[:10]
    out = EnvReading(night=night)
    if table is None or table.empty:
        return out
    before = table[table["date"].astype(str) < night]
    if before.empty:
        return out
    start = (date.fromisoformat(night) - timedelta(days=ENV_DAYS)).isoformat()
    recent = before[before["date"].astype(str) >= start]
    out.recent_games = int(len(recent))
    out.reference_games = int(len(before))
    if out.recent_games < MIN_RECENT_GAMES:
        return out
    weight = out.recent_games / (out.recent_games + ENV_SHRINKAGE_GAMES)
    for stat in (TEAM_GOALS, *MEASURED_STATS):
        if stat not in table.columns:
            continue
        ref_values = pd.to_numeric(before[stat], errors="coerce").dropna()
        rec_values = pd.to_numeric(recent[stat], errors="coerce").dropna()
        if ref_values.empty or rec_values.empty:
            continue
        ref, rec = float(ref_values.mean()), float(rec_values.mean())
        if ref <= 0:
            continue
        out.reference[stat] = ref
        out.recent[stat] = rec
        out.ratio[stat] = 1.0 + weight * (rec / ref - 1.0)
    return out


def _clamp(value: float) -> float:
    low, high = ENV_RANGE
    return min(max(float(value), low), high)


def form_level(team_form: Mapping[str, Mapping[str, Mapping[str, float]]], stat: str) -> float:
    """The league-wide part of last-five team form for `stat`: the mean
    over clubs of their own production factor times the mean of what they
    concede. 1.0 with no form."""
    fors = [float(t.get(stat, {}).get("for", 1.0)) for t in team_form.values()]
    against = [float(t.get(stat, {}).get("against", 1.0)) for t in team_form.values()]
    if not fors or not against:
        return 1.0
    return (sum(fors) / len(fors)) * (sum(against) / len(against))


def props_multipliers(
    env: EnvReading,
    team_form: Mapping[str, Mapping[str, Mapping[str, float]]] | None = None,
) -> dict[str, float]:
    """{stat: multiplier on a skater's expected count} for the stats in
    `ENV_STATS`; empty when the reading is not active."""
    if not env.active:
        return {}
    form = team_form or {}
    out = {}
    for stat in sorted(ENV_STATS):
        if stat in env.ratio:
            out[stat] = _clamp(env.ratio[stat] / form_level(form, stat))
    return out


def team_multiplier(env: EnvReading, model) -> float:
    """The multiplier on both sides' expected goals that puts the team
    model's league total at the environment's target. The model's own level
    is its fitted league total times the mean attack and mean defence of the
    clubs it rates (xG ratings and their last-five form included)."""
    if not env.active or TEAM_GOALS not in env.ratio:
        return 1.0
    teams = list(getattr(model, "teams", {}).values())
    attack = sum(t.attack for t in teams) / len(teams) if teams else 1.0
    defence = sum(t.defence for t in teams) / len(teams) if teams else 1.0
    level = float(model.league_goals_per_game) * attack * defence
    if level <= 0:
        return 1.0
    target = env.reference[TEAM_GOALS] * env.ratio[TEAM_GOALS]
    return _clamp(target / level)


def render_card_report(report: Mapping) -> str:
    """The card's run, as `data/outputs/scoring_environment.md`."""
    env = report.get("reading") or {}
    lines = [
        "# Scoring environment",
        "",
        f"The league's scoring over regular-season games in the {ENV_DAYS} days before "
        f"{env.get('night', '?')} against every regular-season game before it, shrunk at "
        f"{ENV_SHRINKAGE_GAMES} games and clamped to {ENV_RANGE[0]}-{ENV_RANGE[1]} "
        "(Cooper, 2026-11-10). Applied before the snapshot is frozen.",
        "",
        f"- Recent games: {env.get('recent_games', 0):,}; reference games: "
        f"{env.get('reference_games', 0):,}; {'on' if report.get('active') else 'off'}",
    ]
    recent, reference, ratio = env.get("recent") or {}, env.get("reference") or {}, env.get("ratio") or {}
    if ratio:
        lines += ["", "| Stat | Recent / game | Reference / game | Shrunk target |", "|:--|--:|--:|--:|"]
        for stat in (TEAM_GOALS, *MEASURED_STATS):
            if stat in ratio:
                lines.append(
                    f"| {stat} | {recent[stat]:.3f} | {reference[stat]:.3f} | x{ratio[stat]:.3f} |"
                )
    props = report.get("props") or {}
    if props:
        lines += ["", "Multipliers on the card (after last-five team form's league-wide part):", ""]
        lines += [f"- {stat}: x{value:.3f}" for stat, value in sorted(props.items())]
    if "team_total" in report:
        lines.append(f"- team model expected goals: x{float(report['team_total']):.3f}")
    lines += ["", "Not measured against prices before going live; see "
              "`scripts/run_scoring_environment.py`.", ""]
    return "\n".join(lines)
