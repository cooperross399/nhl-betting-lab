"""A team-level model for moneyline, puck line, and totals.

Team markets are not the point of this lab — props are — but a market that is
never priced is a market where an edge can never be found, so all three are
modelled properly rather than gestured at.

## Why hockey is not football with a different ball

Two structural facts drive everything here.

**Goals are rare and the sport is close.** A typical NHL game is about 6 goals
between two teams whose true strengths differ far less than in most leagues.
That compresses moneylines into a narrow band and makes the puck line —
essentially "win by two or more" — the interesting question. It also means an
independent-Poisson scoreline model is a *better* approximation here than in
football, because the scoring rate is closer to constant across the game.

**Regulation is not the whole game, and the model must know it.** A tie after
sixty minutes goes to three-on-three overtime and then a shootout, and the
winner is awarded exactly one goal. That has three consequences a naive model
gets wrong:

* Moneyline settles on the final result *including* overtime and the shootout,
  so a tie in regulation is roughly a coin flip, not a push.
* The puck line at -1.5 can **never** be won in overtime: the winner takes the
  game by exactly one. So P(win by 2+) must be computed on regulation
  scorelines only, and a model that lets an overtime winner cover -1.5 is
  systematically too optimistic on every favourite.
* Totals settle including overtime, so a 3-3 regulation game that ends 4-3 has
  seven goals for a totals bet. A model that stops at regulation understates
  every Over by about the probability of overtime.

Each of those is handled explicitly below rather than absorbed into a fudge
factor, because a fudge factor would hide which of the three was wrong when
the numbers came out badly.

## What the measurement says, which is not what the reasoning predicted

The docstring used to argue that empty-net goals — disproportionately likely
late in a one-goal game, which is exactly the scoreline the puck line asks
about — would push -1.5 covers *up* relative to this model, making it
conservative on favourites laying the puck line.

`data/outputs/team_markets_measurement.md` says the opposite. Over 14,400
walk-forward samples the model is **optimistic** on favourites, not
conservative: where it predicts a 75.0% cover the observed rate is 70.9% on
3,098 samples, and at 83.7% predicted the observed rate is 78.5% on 1,397. The
same shape appears on the moneyline — 73.4% predicted against 67.9% observed
on 212 samples — so the puck-line error is downstream of a general
favourite-overconfidence rather than of anything specific to empty nets.

The mechanism that fits is the one an independent-Poisson model always has: it
assumes two teams score at constant, unrelated rates for sixty minutes, and
hockey does not work that way. Teams protect leads, coaches shorten benches,
and the trailing side pulls its goalie — which raises the variance of the
final margin in both directions and thins out the blowouts the model expects
from a strong favourite.

Empty nets are still not modelled separately, for the original reason: an
adjustment fitted on the same data that sets the base rates would be fitting
the residual twice. But the direction claimed above was wrong, and the
measurement is what governs. This paragraph stays as written because a
prediction that turned out backwards is worth more on the record than
silently deleted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from nhl_betting_lab.models.counts import Poisson


#: League-average total goals per game. Only a fallback for a team with no
#: history; the fitted value replaces it.
DEFAULT_TOTAL_GOALS = 6.1

#: Share of games that reach overtime. Measured at fit time; this is the
#: fallback for an empty dataset.
DEFAULT_OVERTIME_RATE = 0.23

#: Scorelines are summed to this many goals a side. At 12 the truncation cost
#: about 1% of the mass for a team expected to score four and a half, which is
#: not a rounding error on a tail market; at 20 it is under one in a million.
#: The market functions renormalise anyway, so the truncation cannot bias a
#: probability — it can only make one slightly less precise.
MAX_GOALS = 20


@dataclass(frozen=True)
class TeamRates:
    """One team's shrunk attack and defence multipliers."""

    team: str
    games: int
    attack: float
    defence: float


@dataclass
class TeamModelReport:
    games: int = 0
    teams: int = 0
    league_goals_per_game: float = DEFAULT_TOTAL_GOALS
    home_advantage: float = 1.0
    overtime_rate: float = DEFAULT_OVERTIME_RATE
    b2b_factors: dict[str, float] = None  # type: ignore[assignment]

    def summary_line(self) -> str:
        return (
            f"{self.games} games, {self.teams} teams; league average "
            f"{self.league_goals_per_game:.2f} goals per game, home factor "
            f"{self.home_advantage:.3f}, overtime rate "
            f"{self.overtime_rate:.1%}."
        )


class TeamModel:
    """Independent-Poisson scorelines with explicit overtime handling."""

    #: Games at which a team keeps half its measured deviation from league
    #: average. About a quarter of a season: enough to notice a real change in
    #: a roster, not so little that a hot fortnight becomes an opinion.
    SHRINKAGE_GAMES = 20

    #: Games of evidence at which a fitted back-to-back factor keeps half its
    #: measured deviation from 1.0. A season holds a few hundred B2B sides, so
    #: the factors stabilise within the first fitted season and an early
    #: outlier cannot become a standing opinion.
    B2B_SHRINKAGE_GAMES = 150

    def __init__(self) -> None:
        self.teams: dict[str, TeamRates] = {}
        self.league_goals_per_game = DEFAULT_TOTAL_GOALS
        self.home_advantage = 1.0
        self.overtime_rate = DEFAULT_OVERTIME_RATE
        #: Multipliers on a side's expected goals when it played yesterday,
        #: fitted from the training games and shrunk toward 1.0. Keyed by
        #: (venue, direction): a tired side scores less ("for") and concedes
        #: more ("against"), and the away effect is larger because the road
        #: team travelled overnight — which is why home and away are fitted
        #: separately rather than pooled.
        self.b2b_factors: dict[str, float] = {
            "home_for": 1.0,
            "home_against": 1.0,
            "away_for": 1.0,
            "away_against": 1.0,
        }
        self.report = TeamModelReport()

    def fit(self, games: pd.DataFrame) -> "TeamModel":
        required = {
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
            "regulation",
        }
        missing = required - set(games.columns)
        if missing:
            raise KeyError(
                f"Team games are missing columns {sorted(missing)}; refusing "
                "to model from a partial dataset."
            )
        frame = games.copy()
        for column in ("home_goals", "away_goals"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["home_goals", "away_goals"])
        if frame.empty:
            raise ValueError("No completed games to fit on.")

        home_goals = frame["home_goals"].astype(float)
        away_goals = frame["away_goals"].astype(float)
        total = float((home_goals + away_goals).mean())
        self.league_goals_per_game = total if total > 0 else DEFAULT_TOTAL_GOALS
        half = self.league_goals_per_game / 2.0

        mean_home = float(home_goals.mean())
        mean_away = float(away_goals.mean())
        # Home advantage as a multiplier on the home side's rate, split evenly
        # so the league total is preserved. A hockey home edge is real but
        # small; expressing it as a ratio keeps it from drifting when scoring
        # rates change league-wide.
        self.home_advantage = (
            math.sqrt(mean_home / mean_away) if mean_away > 0 else 1.0
        )
        self.overtime_rate = (
            float((~frame["regulation"].astype(bool)).mean())
            if "regulation" in frame
            else DEFAULT_OVERTIME_RATE
        )

        scored: dict[str, list[float]] = {}
        conceded: dict[str, list[float]] = {}
        for row in frame.itertuples():
            home, away = str(row.home_team), str(row.away_team)
            # Divide out the venue effect before measuring a team's rate, so a
            # team with a home-heavy schedule so far does not look stronger
            # than one with an away-heavy one.
            scored.setdefault(home, []).append(
                float(row.home_goals) / self.home_advantage
            )
            conceded.setdefault(home, []).append(
                float(row.away_goals) * self.home_advantage
            )
            scored.setdefault(away, []).append(
                float(row.away_goals) * self.home_advantage
            )
            conceded.setdefault(away, []).append(
                float(row.home_goals) / self.home_advantage
            )

        self.teams = {}
        for team in sorted(set(scored) | set(conceded)):
            for_rates = scored.get(team, [])
            against_rates = conceded.get(team, [])
            games_played = max(len(for_rates), len(against_rates))
            weight = games_played / (games_played + self.SHRINKAGE_GAMES)
            attack_raw = (
                (sum(for_rates) / len(for_rates)) / half if for_rates and half else 1.0
            )
            defence_raw = (
                (sum(against_rates) / len(against_rates)) / half
                if against_rates and half
                else 1.0
            )
            self.teams[team] = TeamRates(
                team=team,
                games=games_played,
                attack=1.0 + weight * (attack_raw - 1.0),
                defence=1.0 + weight * (defence_raw - 1.0),
            )

        self._fit_b2b_factors(frame)
        self.report = TeamModelReport(
            games=len(frame),
            teams=len(self.teams),
            league_goals_per_game=self.league_goals_per_game,
            home_advantage=self.home_advantage,
            overtime_rate=self.overtime_rate,
            b2b_factors=dict(self.b2b_factors),
        )
        return self

    def _fit_b2b_factors(self, frame: pd.DataFrame) -> None:
        """How much a side that played yesterday scores and concedes.

        Fitted from the training games only, so a walk-forward refit can never
        see the game it prices; rest itself derives from the schedule, which
        is known before puck drop. Measured separately for the home and away
        side because the effect is not symmetric — the road team on a
        back-to-back travelled overnight, and the diagnostic that motivated
        this showed an 8.5-point moneyline miss on away back-to-backs against
        a 4-point miss on home ones.

        Each factor is a plain ratio of mean goals in the B2B state against
        the rested state, shrunk toward 1.0 by the number of B2B games behind
        it. No interaction with team strength is claimed: this is one scalar
        per (venue, direction), deliberately, because a richer model of
        fatigue would be fitted to noise.
        """
        if "date" not in frame.columns:
            return
        ordered = frame.sort_values("date")
        last_played: dict[str, str] = {}
        home_b2b: list[bool] = []
        away_b2b: list[bool] = []
        for row in ordered.itertuples():
            day = pd.Timestamp(str(row.date))
            for team, bucket in (
                (str(row.home_team), home_b2b),
                (str(row.away_team), away_b2b),
            ):
                previous = last_played.get(team)
                bucket.append(
                    previous is not None
                    and (day - pd.Timestamp(previous)).days == 1
                )
                last_played[team] = str(row.date)
        ordered = ordered.assign(_home_b2b=home_b2b, _away_b2b=away_b2b)

        def ratio(tired: pd.Series, rested: pd.Series, count: int) -> float:
            if not len(tired) or not len(rested) or rested.mean() <= 0:
                return 1.0
            raw = float(tired.mean()) / float(rested.mean())
            weight = count / (count + self.B2B_SHRINKAGE_GAMES)
            return 1.0 + weight * (raw - 1.0)

        home_tired = ordered[ordered["_home_b2b"]]
        home_fresh = ordered[~ordered["_home_b2b"]]
        away_tired = ordered[ordered["_away_b2b"]]
        away_fresh = ordered[~ordered["_away_b2b"]]
        self.b2b_factors = {
            "home_for": ratio(
                home_tired["home_goals"], home_fresh["home_goals"], len(home_tired)
            ),
            "home_against": ratio(
                home_tired["away_goals"], home_fresh["away_goals"], len(home_tired)
            ),
            "away_for": ratio(
                away_tired["away_goals"], away_fresh["away_goals"], len(away_tired)
            ),
            "away_against": ratio(
                away_tired["home_goals"], away_fresh["home_goals"], len(away_tired)
            ),
        }

    # -- rates -----------------------------------------------------------

    def expected_goals(
        self,
        home_team: str,
        away_team: str,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> tuple[float, float]:
        """Regulation-time expected goals for each side.

        `home_b2b` / `away_b2b`: whether that side played yesterday. Rest is
        schedule information, known before puck drop, so using it leaks
        nothing; a caller that does not know simply passes nothing and gets
        the unadjusted rates.
        """
        half = self.league_goals_per_game / 2.0
        home = self.teams.get(str(home_team))
        away = self.teams.get(str(away_team))
        home_attack = home.attack if home else 1.0
        home_defence = home.defence if home else 1.0
        away_attack = away.attack if away else 1.0
        away_defence = away.defence if away else 1.0
        home_goals = half * home_attack * away_defence * self.home_advantage
        away_goals = half * away_attack * home_defence / self.home_advantage
        if home_b2b or away_b2b:
            original_total = home_goals + away_goals
            if home_b2b:
                home_goals *= self.b2b_factors["home_for"]
                away_goals *= self.b2b_factors["home_against"]
            if away_b2b:
                away_goals *= self.b2b_factors["away_for"]
                home_goals *= self.b2b_factors["away_against"]
            # Fatigue shifts who scores, not how much hockey happens. The
            # diagnostic that motivated this showed a win-probability bias
            # and said nothing about totals — and the first fit, which let
            # the factors move the total too, improved the moneyline and the
            # puck line while losing 19.7u on totals, exactly where the
            # mechanism made no claim. So the adjustment is constrained to
            # preserve the expected total: it moves goals between the sides
            # and leaves their sum where the base model put it.
            adjusted_total = home_goals + away_goals
            if adjusted_total > 0:
                scale = original_total / adjusted_total
                home_goals *= scale
                away_goals *= scale
        return home_goals, away_goals

    def scoreline_matrix(
        self,
        home_team: str,
        away_team: str,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> list[list[float]]:
        """P(home = i, away = j) over regulation scorelines."""
        home_mean, away_mean = self.expected_goals(
            home_team, away_team, home_b2b=home_b2b, away_b2b=away_b2b
        )
        home_pmf = [Poisson(home_mean).pmf(k) for k in range(MAX_GOALS + 1)]
        away_pmf = [Poisson(away_mean).pmf(k) for k in range(MAX_GOALS + 1)]
        return [[h * a for a in away_pmf] for h in home_pmf]

    # -- markets ---------------------------------------------------------

    def regulation_probabilities(
        self,
        home_team: str,
        away_team: str,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> tuple[float, float, float]:
        """P(home leads), P(tied), P(away leads) after sixty minutes."""
        matrix = self.scoreline_matrix(
            home_team, away_team, home_b2b=home_b2b, away_b2b=away_b2b
        )
        home = tie = away = 0.0
        for i, row in enumerate(matrix):
            for j, mass in enumerate(row):
                if i > j:
                    home += mass
                elif i == j:
                    tie += mass
                else:
                    away += mass
        total = home + tie + away
        if total <= 0:
            return 1 / 3, 1 / 3, 1 / 3
        return home / total, tie / total, away / total

    def moneyline_probabilities(
        self,
        home_team: str,
        away_team: str,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> dict[str, float]:
        """P(home wins), P(away wins), including overtime and the shootout.

        A regulation tie is resolved close to a coin flip. Three-on-three
        overtime is not quite even — the home team gets the last change and
        wins a little over half — but the edge is small and this model does not
        claim to know it, so the tie is split evenly and the assumption is
        stated rather than tuned.
        """
        home, tie, away = self.regulation_probabilities(
            home_team, away_team, home_b2b=home_b2b, away_b2b=away_b2b
        )
        return {"home": home + tie / 2.0, "away": away + tie / 2.0}

    def puck_line_probabilities(
        self,
        home_team: str,
        away_team: str,
        line: float = 1.5,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> dict[str, float]:
        """P(each side covers the puck line).

        The -1.5 side needs a regulation-or-overtime win **by two or more**,
        and an overtime or shootout winner takes the game by exactly one. So
        the margin is computed on regulation scorelines only, and every tied
        regulation scoreline contributes zero to the -1.5 side.

        A model that let an overtime winner cover -1.5 would be systematically
        too optimistic on every favourite.
        """
        size = abs(float(line))
        matrix = self.scoreline_matrix(
            home_team, away_team, home_b2b=home_b2b, away_b2b=away_b2b
        )
        home_covers = away_covers = 0.0
        total = 0.0
        for i, row in enumerate(matrix):
            for j, mass in enumerate(row):
                total += mass
                margin = i - j
                if margin > size:
                    home_covers += mass
                elif -margin > size:
                    away_covers += mass
        if total <= 0:
            return {"home_favourite": 0.0, "away_favourite": 0.0}
        # The +1.5 side of each is the complement: a one-goal loss, a tie
        # taken to overtime, or any win all cover +1.5.
        return {
            "home_minus": home_covers / total,
            "home_plus": 1.0 - away_covers / total,
            "away_minus": away_covers / total,
            "away_plus": 1.0 - home_covers / total,
        }

    def total_probabilities(
        self,
        home_team: str,
        away_team: str,
        line: float = 5.5,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> dict[str, float]:
        """P(over), P(under), P(push) — including the overtime goal.

        Totals settle on the final score, so a game that goes to overtime adds
        exactly one goal. A model that stopped at regulation would understate
        every Over by roughly the overtime rate, which on a 5.5 line is not a
        rounding error.
        """
        matrix = self.scoreline_matrix(
            home_team, away_team, home_b2b=home_b2b, away_b2b=away_b2b
        )
        regulation: dict[int, float] = {}
        tied_mass = 0.0
        for i, row in enumerate(matrix):
            for j, mass in enumerate(row):
                regulation[i + j] = regulation.get(i + j, 0.0) + mass
                if i == j:
                    tied_mass += mass

        # A tied regulation scoreline of n goals finishes at n + 1.
        final: dict[int, float] = {}
        for i, row in enumerate(matrix):
            for j, mass in enumerate(row):
                total_goals = i + j + (1 if i == j else 0)
                final[total_goals] = final.get(total_goals, 0.0) + mass

        value = float(line)
        floor = math.floor(value)
        mass_total = sum(final.values()) or 1.0
        push = final.get(int(floor), 0.0) / mass_total if math.isclose(value, floor) else 0.0
        over = sum(
            mass for goals, mass in final.items() if goals > value
        ) / mass_total
        under = sum(
            mass for goals, mass in final.items() if goals < value
        ) / mass_total
        if push > 0:
            remaining = 1.0 - push
            if remaining > 0:
                over, under = over / remaining, under / remaining
        return {"over": over, "under": under, "push": push}

    def regulation_3_way_probabilities(
        self,
        home_team: str,
        away_team: str,
        *,
        home_b2b: bool = False,
        away_b2b: bool = False,
    ) -> dict[str, float]:
        """P(home), P(draw), P(away) after sixty minutes.

        This needs no new model: it is `regulation_probabilities` under its
        market name. The moneyline is *derived* from this distribution by
        splitting the draw, so pricing the 3-way is the more direct of the two
        — and any disagreement between the two on one card would be a bug
        rather than an opinion, which is why they share one source.
        """
        home, draw, away = self.regulation_probabilities(
            home_team, away_team, home_b2b=home_b2b, away_b2b=away_b2b
        )
        return {"home": home, "draw": draw, "away": away}

    def market_probabilities(
        self, home_team: str, away_team: str, *, total_line: float = 5.5
    ) -> dict[str, dict[str, float]]:
        """Every team market at once, for the card."""
        return {
            "moneyline": self.moneyline_probabilities(home_team, away_team),
            "puck_line": self.puck_line_probabilities(home_team, away_team),
            "total_goals": self.total_probabilities(
                home_team, away_team, line=total_line
            ),
            "regulation_3_way": self.regulation_3_way_probabilities(
                home_team, away_team
            ),
        }
