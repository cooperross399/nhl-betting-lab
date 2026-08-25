"""Per-player count models for the six prop markets this lab prices.

The team model answers "how many will this game produce"; a prop asks "how
many will *this player* produce", and that needs per-player rates fitted on
the boxscore logs (`data/processed/player_game_logs.csv`).

Every rate is expressed **per sixty minutes of ice time** and then multiplied
by expected ice time, because ice time is the single largest driver of every
skater prop and it moves for reasons the raw counting stats cannot see —
injuries, line promotions, a coach shortening the bench in a close game.

A per-60 rate computed from a handful of games is mostly noise, so every
player's rate is shrunk toward their position group's league baseline in
proportion to the ice time behind it. A player with 1,200 minutes keeps half
of his measured deviation; a player with 120 keeps a twelfth. The opponent's
concession factor is shrunk the same way, for the same reason.

## Four honest limits, stated here because the numbers cannot show them

**Expected ice time is the weakest input, and the lineup is the real driver.**
Scratches, line combinations, power-play units and — above all — the confirmed
starting goalie are published close to puck drop, hours after the card exists.
Books reprice on every one of them; this model cannot. That is a structural
information deficit on every prop, and it is why `MIN_PROP_EDGE` is higher
than the team-market bar, never lower.

**Power-play deployment is a proxy, not a measurement.** The boxscore carries
power-play goals and nothing else about power-play usage: no PP time on ice,
no PP assists. The proxy here is a player's rolling share of his team's
power-play goals, which is a poor signal for a defenceman who quarterbacks the
first unit and rarely finishes. Its influence is deliberately capped so it can
nudge a rate and never dominate one.

**Goalie saves are not a skater stat wearing different clothes.** A save
happens when the opponent shoots, so expected saves is expected shots against
times save rate — and expected shots against depends on both teams, not on the
goalie. A goalie facing thirty-eight shots and stopping thirty-five had a
better night than one facing twenty-two and stopping twenty-two, and only the
second one goes under a 24.5 line. The model is built that way round.

**Nothing here knows who is starting in goal.** A goalie prop priced for a
backup who does not dress is worthless, and the model has no way to tell. The
card gates on this separately; the model does not pretend to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from nhl_betting_lab.models.counts import (
    CountDistribution,
    Dispersion,
    distribution_for,
    measure_dispersion,
)


#: The skater stats this model prices, each a column of the player game logs.
SKATER_STATS: tuple[str, ...] = (
    "shots_on_goal",
    "points",
    "goals",
    "assists",
    "blocked_shots",
)

#: The goalie stat, modelled through shots against rather than directly.
#: Named for the market, not for the log column it settles on: every stat key
#: in this module is a market key, so nothing downstream has to translate
#: between two vocabularies and get it wrong once.
GOALIE_STAT = "goalie_saves"

#: The player-log column `goalie_saves` settles on.
GOALIE_SETTLEMENT_COLUMN = "saves"

#: Every market name the card and the provider mapping share.
PROP_STATS: tuple[str, ...] = SKATER_STATS + (GOALIE_STAT,)

#: Position groups. Forwards and defencemen have completely different rate
#: profiles on every one of these stats — a defenceman blocks three times as
#: many shots and scores a third as many goals — so a single league baseline
#: would shrink every player toward a number describing nobody.
POSITION_GROUPS = ("F", "D", "G")

#: Stats where power-play deployment plausibly moves the rate. Blocked shots
#: are excluded on purpose: a player on the power play is not blocking shots,
#: he is taking them.
PP_SENSITIVE_STATS = frozenset({"points", "goals", "assists"})


def position_group(position: str) -> str:
    """`"C"`, `"L"`, `"R"` -> F; `"D"` -> D; `"G"` -> G."""
    text = str(position or "").strip().upper()
    if text.startswith("G"):
        return "G"
    if text.startswith("D"):
        return "D"
    if text and text[0] in {"C", "L", "R", "F"}:
        return "F"
    return ""


@dataclass(frozen=True)
class SkaterRates:
    """One skater's shrunk per-60 rates and ice-time expectation."""

    player_id: int
    player: str
    team: str
    group: str
    games: int
    toi_seconds: int
    expected_toi_seconds: float
    per60: dict[str, float]
    #: Rolling share of the team's power-play goals. See the module docstring
    #: for why this is a proxy and not a measurement.
    pp_share: float


@dataclass(frozen=True)
class GoalieRates:
    """One goalie's save rate and workload expectation."""

    player_id: int
    player: str
    team: str
    games: int
    toi_seconds: int
    #: Shots faced per sixty minutes of the goalie's own ice time.
    shots_against_per60: float
    save_rate: float
    expected_toi_seconds: float


@dataclass
class PropsModelReport:
    """What the fit saw, so a thin model announces itself."""

    games: int = 0
    skaters_priced: int = 0
    skaters_below_minimum: int = 0
    goalies_priced: int = 0
    dispersion: dict[str, Dispersion] = field(default_factory=dict)

    def summary_line(self) -> str:
        return (
            f"{self.games} games; {self.skaters_priced} skaters priced "
            f"({self.skaters_below_minimum} below the minimum and not priced); "
            f"{self.goalies_priced} goalies priced."
        )


class PlayerPropsModel:
    """Prop pricing from per-player boxscore logs."""

    #: Ice time at which a skater keeps half of his measured deviation from the
    #: position baseline — about 65 games at 18 minutes.
    SHRINKAGE_SECONDS = 70_000

    #: Games at which a team's concession factor keeps half its deviation.
    OPPONENT_SHRINKAGE_GAMES = 40

    #: Games used for the ice-time expectation. Recent deployment, not career.
    #: Ten rather than a full season: a player promoted to the top line three
    #: weeks ago should be priced as a top-line player, and a season average
    #: would take months to notice.
    RECENT_GAMES = 10

    #: A skater below this many games is not priced at all. The league baseline
    #: would be the honest rate, but a prop priced purely on "average forward"
    #: is not a modelled opinion worth staking.
    MINIMUM_GAMES = 15

    #: A goalie below this many appearances is not priced. Lower than the
    #: skater bar because a goalie's save rate is an average over dozens of
    #: shots per appearance, so it stabilises far faster than a skater's
    #: per-60 goal rate.
    MINIMUM_GOALIE_GAMES = 8

    #: How far the power-play proxy may move a rate. Capped tightly because the
    #: proxy is noisy: it is allowed to nudge and never to dominate.
    PP_MULTIPLIER_RANGE = (0.88, 1.18)

    def __init__(self) -> None:
        self.skaters: dict[int, SkaterRates] = {}
        self.goalies: dict[int, GoalieRates] = {}
        self.baselines: dict[str, dict[str, float]] = {}
        self.opponent_factors: dict[str, dict[str, float]] = {}
        self.venue_factors: dict[str, dict[str, float]] = {}
        self.dispersion: dict[str, Dispersion] = {}
        self.league_save_rate: float = 0.900
        self.league_shots_against_per60: float = 30.0
        self.report = PropsModelReport()
        self.opponent_shot_factors: dict[str, float] = {}
        self._by_name: dict[str, int] = {}

    # -- fitting ---------------------------------------------------------

    def fit(self, logs: pd.DataFrame) -> "PlayerPropsModel":
        required = {
            "game_id",
            "date",
            "player_id",
            "player",
            "role",
            "position",
            "team",
            "opponent",
            "venue",
            "toi_seconds",
            "power_play_goals",
            "saves",
            "shots_against",
            *SKATER_STATS,
        }
        missing = required - set(logs.columns)
        if missing:
            raise KeyError(
                f"Player logs are missing columns {sorted(missing)}; refusing "
                "to model from a partial dataset."
            )
        frame = logs.copy()
        numeric = [
            "toi_seconds",
            "power_play_goals",
            "saves",
            "shots_against",
            *SKATER_STATS,
        ]
        for column in numeric:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
        frame["toi_seconds"] = frame["toi_seconds"].astype(float)
        frame = frame[frame["toi_seconds"] > 0]
        if frame.empty:
            raise ValueError("No usable appearances to fit on.")
        frame["group"] = frame["position"].map(position_group)
        frame = frame.sort_values(["date", "game_id"])

        skaters = frame[frame["role"].astype(str) == "skater"]
        goalies = frame[frame["role"].astype(str) == "goalie"]

        self.report = PropsModelReport(games=int(frame["game_id"].nunique()))
        self._fit_dispersion(skaters, goalies)
        self._fit_baselines(skaters)
        self._fit_opponent_factors(skaters)
        self._fit_venue_factors(skaters)
        self._fit_skaters(skaters)
        self._fit_goalies(goalies)
        self.opponent_shot_factors = fit_opponent_shot_factors(frame)
        self.report.dispersion = dict(self.dispersion)
        self._by_name = {
            rates.player.strip().casefold(): player_id
            for player_id, rates in self.skaters.items()
            if rates.player.strip()
        }
        self._by_name.update(
            {
                rates.player.strip().casefold(): player_id
                for player_id, rates in self.goalies.items()
                if rates.player.strip()
            }
        )
        return self

    def _fit_dispersion(self, skaters: pd.DataFrame, goalies: pd.DataFrame) -> None:
        """Measure variance/mean per stat once, on the whole column.

        Measured on players with real workloads only. Including a fourth-line
        winger's eight-minute nights would drag every mean toward zero and make
        every stat look Poisson by dilution.
        """
        regulars = skaters[skaters["toi_seconds"] >= 600]
        for stat in SKATER_STATS:
            self.dispersion[stat] = measure_dispersion(regulars[stat].tolist())
        starters = goalies[goalies["toi_seconds"] >= 1800]
        self.dispersion[GOALIE_STAT] = measure_dispersion(
            starters[GOALIE_SETTLEMENT_COLUMN].tolist()
        )

    def _fit_baselines(self, skaters: pd.DataFrame) -> None:
        self.baselines = {}
        for group, rows in skaters.groupby("group"):
            seconds = float(rows["toi_seconds"].sum())
            if seconds <= 0:
                continue
            self.baselines[str(group)] = {
                stat: float(rows[stat].sum()) / seconds * 3600.0
                for stat in SKATER_STATS
            }

    def _fit_opponent_factors(self, skaters: pd.DataFrame) -> None:
        """How much of each stat a team allows opposing skaters, vs the league.

        Aggregated per game so a team that plays more games does not get a
        larger factor, and shrunk by games played so an early-season outlier
        does not become a permanent opinion.
        """
        self.opponent_factors = {}
        per_game = (
            skaters.groupby(["opponent", "game_id"])[list(SKATER_STATS)]
            .sum()
            .reset_index()
        )
        if per_game.empty:
            return
        league = {stat: float(per_game[stat].mean()) for stat in SKATER_STATS}
        for team, rows in per_game.groupby("opponent"):
            played = len(rows)
            weight = played / (played + self.OPPONENT_SHRINKAGE_GAMES)
            self.opponent_factors[str(team)] = {
                stat: 1.0
                + weight
                * (
                    (float(rows[stat].mean()) / league[stat] if league[stat] else 1.0)
                    - 1.0
                )
                for stat in SKATER_STATS
            }

    def _fit_venue_factors(self, skaters: pd.DataFrame) -> None:
        self.venue_factors = {}
        total_seconds = float(skaters["toi_seconds"].sum())
        if total_seconds <= 0:
            return
        overall = {
            stat: float(skaters[stat].sum()) / total_seconds * 3600.0
            for stat in SKATER_STATS
        }
        for venue in ("home", "away"):
            rows = skaters[skaters["venue"].astype(str) == venue]
            seconds = float(rows["toi_seconds"].sum())
            if seconds <= 0:
                self.venue_factors[venue] = {stat: 1.0 for stat in SKATER_STATS}
                continue
            self.venue_factors[venue] = {
                stat: (
                    (float(rows[stat].sum()) / seconds * 3600.0) / overall[stat]
                    if overall[stat]
                    else 1.0
                )
                for stat in SKATER_STATS
            }

    def _fit_skaters(self, skaters: pd.DataFrame) -> None:
        self.skaters = {}
        team_pp = (
            skaters.groupby("team")["power_play_goals"].sum().to_dict()
        )
        for player_id, rows in skaters.groupby("player_id"):
            seconds = float(rows["toi_seconds"].sum())
            games = len(rows)
            if games < self.MINIMUM_GAMES or seconds <= 0:
                self.report.skaters_below_minimum += 1
                continue
            group = str(rows["group"].mode().iat[0]) if not rows["group"].empty else "F"
            if group not in {"F", "D"}:
                group = "F"
            baseline = self.baselines.get(group) or {
                stat: 0.0 for stat in SKATER_STATS
            }
            weight = seconds / (seconds + self.SHRINKAGE_SECONDS)
            per60 = {}
            for stat in SKATER_STATS:
                raw = float(rows[stat].sum()) / seconds * 3600.0
                per60[stat] = baseline.get(stat, 0.0) + weight * (
                    raw - baseline.get(stat, 0.0)
                )
            recent = rows.tail(self.RECENT_GAMES)
            team = str(rows["team"].iat[-1])
            team_total = float(team_pp.get(team, 0.0))
            player_pp = float(rows["power_play_goals"].sum())
            self.skaters[int(player_id)] = SkaterRates(
                player_id=int(player_id),
                player=str(rows["player"].iat[-1] or "").strip(),
                team=team,
                group=group,
                games=games,
                toi_seconds=int(seconds),
                expected_toi_seconds=float(recent["toi_seconds"].mean()),
                per60=per60,
                pp_share=(player_pp / team_total) if team_total > 0 else 0.0,
            )
        self.report.skaters_priced = len(self.skaters)

    def _fit_goalies(self, goalies: pd.DataFrame) -> None:
        self.goalies = {}
        total_saves = float(goalies["saves"].sum())
        total_shots = float(goalies["shots_against"].sum())
        total_seconds = float(goalies["toi_seconds"].sum())
        if total_shots > 0:
            self.league_save_rate = total_saves / total_shots
        if total_seconds > 0:
            self.league_shots_against_per60 = total_shots / total_seconds * 3600.0

        for player_id, rows in goalies.groupby("player_id"):
            games = len(rows)
            seconds = float(rows["toi_seconds"].sum())
            shots = float(rows["shots_against"].sum())
            if games < self.MINIMUM_GOALIE_GAMES or seconds <= 0 or shots <= 0:
                continue
            # Save rate is shrunk toward the league on shots faced, not games.
            # Shots are the trials; a goalie with 900 shots has far more
            # evidence than one with 900 minutes of blowouts.
            weight = shots / (shots + 900.0)
            raw_rate = float(rows["saves"].sum()) / shots
            recent = rows.tail(self.RECENT_GAMES)
            self.goalies[int(player_id)] = GoalieRates(
                player_id=int(player_id),
                player=str(rows["player"].iat[-1] or "").strip(),
                team=str(rows["team"].iat[-1]),
                games=games,
                toi_seconds=int(seconds),
                shots_against_per60=shots / seconds * 3600.0,
                save_rate=self.league_save_rate
                + weight * (raw_rate - self.league_save_rate),
                expected_toi_seconds=float(recent["toi_seconds"].mean()),
            )
        self.report.goalies_priced = len(self.goalies)

    # -- pricing ---------------------------------------------------------

    def resolve_player(self, name: str) -> int | None:
        """Map a provider's player name to a fitted player id, or None.

        Deliberately exact after casefolding. Fuzzy matching a prop to the
        wrong player produces a confident price for a bet nobody placed, and
        the failure is invisible: the row looks exactly like a correct one.
        Unmatched names are reported by the caller instead.
        """
        return self._by_name.get(str(name or "").strip().casefold())

    def pp_multiplier(self, rates: SkaterRates, stat: str) -> float:
        if stat not in PP_SENSITIVE_STATS:
            return 1.0
        # A player taking a fifth of his team's power-play goals is a first-unit
        # regular; one taking none is not. Mapped through a shallow curve and
        # then clamped, because the proxy is noisy.
        raw = 1.0 + 1.4 * (rates.pp_share - 0.12)
        low, high = self.PP_MULTIPLIER_RANGE
        return min(max(raw, low), high)

    def expected_count(
        self,
        player_id: int,
        stat: str,
        *,
        opponent: str,
        venue: str,
        expected_toi_seconds: float | None = None,
    ) -> float | None:
        """The distribution's mean, or None when there is no modelled opinion."""
        if stat == GOALIE_STAT:
            return self.expected_saves(
                player_id,
                opponent=opponent,
                venue=venue,
                expected_toi_seconds=expected_toi_seconds,
            )
        if stat not in SKATER_STATS:
            raise KeyError(f"Unknown prop stat {stat!r}. Known: {PROP_STATS}")
        rates = self.skaters.get(int(player_id))
        if rates is None:
            return None
        toi = (
            float(expected_toi_seconds)
            if expected_toi_seconds is not None
            else rates.expected_toi_seconds
        )
        if toi <= 0:
            return None
        opponent_factor = self.opponent_factors.get(str(opponent), {}).get(stat, 1.0)
        venue_factor = self.venue_factors.get(str(venue), {}).get(stat, 1.0)
        return (
            rates.per60[stat]
            * (toi / 3600.0)
            * opponent_factor
            * venue_factor
            * self.pp_multiplier(rates, stat)
        )

    def expected_saves(
        self,
        player_id: int,
        *,
        opponent: str,
        venue: str,
        expected_toi_seconds: float | None = None,
    ) -> float | None:
        """Expected saves = expected shots against x save rate.

        Shots against is driven by the opponent's shot volume and by the
        goalie's own team's defensive profile, neither of which is a property
        of the goalie. Modelling saves directly would attribute both to him.
        """
        rates = self.goalies.get(int(player_id))
        if rates is None:
            return None
        toi = (
            float(expected_toi_seconds)
            if expected_toi_seconds is not None
            else rates.expected_toi_seconds
        )
        if toi <= 0:
            return None
        # The opponent's shooting factor comes from the skater concession
        # table, which measures shots *allowed*. Shots faced by this goalie is
        # the mirror image: how many the opponent generates.
        opponent_factor = self.opponent_shot_factor(str(opponent))
        shots = rates.shots_against_per60 * (toi / 3600.0) * opponent_factor
        return shots * rates.save_rate

    def opponent_shot_factor(self, opponent: str) -> float:
        """How many shots this opponent generates, relative to the league.

        Fitted from the shooting side of the same per-game aggregation the
        concession table uses, so the two cannot drift apart. An unknown team
        gets 1.0 — league average — rather than an error: a team the model has
        never seen is a real early-season state, not a bug.
        """
        return self.opponent_shot_factors.get(str(opponent), 1.0)

    def distribution(
        self,
        player_id: int,
        stat: str,
        *,
        opponent: str,
        venue: str,
        expected_toi_seconds: float | None = None,
    ) -> CountDistribution | None:
        mean = self.expected_count(
            player_id,
            stat,
            opponent=opponent,
            venue=venue,
            expected_toi_seconds=expected_toi_seconds,
        )
        if mean is None or mean <= 0:
            return None
        return distribution_for(mean, self.dispersion.get(stat))

    def over_probability(
        self,
        player_id: int,
        stat: str,
        line: float,
        *,
        opponent: str,
        venue: str,
        expected_toi_seconds: float | None = None,
    ) -> float | None:
        """P(count beats `line`), or None when there is no modelled opinion."""
        shape = self.distribution(
            player_id,
            stat,
            opponent=opponent,
            venue=venue,
            expected_toi_seconds=expected_toi_seconds,
        )
        if shape is None:
            return None
        return shape.over_probability(line)

    def anytime_scorer_probability(
        self, player_id: int, *, opponent: str, venue: str
    ) -> float | None:
        """P(at least one goal). The provider prices this as goals over 0.5.

        There is one name for this in the repository, not two. Maintaining
        `goals_over_0_5` and `anytime_scorer` as separate markets would let
        them disagree on the same card.
        """
        return self.over_probability(
            player_id, "goals", 0.5, opponent=opponent, venue=venue
        )


def fit_opponent_shot_factors(logs: pd.DataFrame) -> dict[str, float]:
    """Shots generated per game by each team, relative to the league.

    Computed from the skater logs so it uses the same evidence as everything
    else, and shrunk on games played for the same reason the concession table
    is.
    """
    skaters = logs[logs["role"].astype(str) == "skater"].copy()
    skaters["shots_on_goal"] = pd.to_numeric(
        skaters["shots_on_goal"], errors="coerce"
    ).fillna(0)
    per_game = (
        skaters.groupby(["team", "game_id"])["shots_on_goal"].sum().reset_index()
    )
    if per_game.empty:
        return {}
    league = float(per_game["shots_on_goal"].mean())
    if league <= 0:
        return {}
    factors: dict[str, float] = {}
    for team, rows in per_game.groupby("team"):
        played = len(rows)
        weight = played / (played + PlayerPropsModel.OPPONENT_SHRINKAGE_GAMES)
        factors[str(team)] = 1.0 + weight * (
            float(rows["shots_on_goal"].mean()) / league - 1.0
        )
    return factors
