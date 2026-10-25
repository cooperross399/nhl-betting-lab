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

import re
import unicodedata
from dataclasses import dataclass, field, replace

import numpy as np
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
    "hits",
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
#: and hits are excluded on purpose, and for the same reason: a player on the
#: power play is not blocking shots or finishing checks, he is carrying the
#: puck. If anything the effect runs the other way, and this model does not
#: claim to know by how much.
PP_SENSITIVE_STATS = frozenset({"points", "goals", "assists"})

#: The parts of the hits model Cooper asked to have dialled in (2026-10-25:
#: "enhance and improve the hits portion of our model ... i think overs could
#: be in play a lot more often"). Each is a name so the walk-forward can
#: price any subset against the old model; the card fits all of them.
#:
#: ``rink``: hits are counted by the home club's off-ice scorers, and rinks
#: disagree about what a hit is by a third or more. Every logged hit is
#: divided by its rink's factor before any rate is fitted, and tonight's
#: rink's factor is multiplied back in.
#: ``shrinkage``: hitting is a style, not luck, so a skater's hit rate is
#: shrunk toward his position by an amount measured from the spread of real
#: hit rates (empirical Bayes) rather than the 70,000 seconds every stat
#: shares. The shared figure pulled the league's heavy hitters toward an
#: average forward, the very players books post hits lines on.
#: ``recency``: a game's weight in the hit rate halves every
#: `HITS_HALF_LIFE_GAMES` of the player's games, so a role change shows.
#: ``dispersion``: the spread is measured inside each player's own games.
#: Measured on the whole column it counted the gap between a grinder and a
#: skill winger as game-to-game noise, which widened every distribution,
#: piled probability on 0 and 1 hits, and so under-priced every over.
HITS_OPTIONS = frozenset({"rink", "shrinkage", "recency", "dispersion"})


def normalize_player_name(name: object) -> str:
    """A comparison key that removes representation without inventing identity.

    The NHL registry spells `"Alexis Lafrenière"`; the odds provider sends
    `"Alexis Lafreniere"`. Fifty-one of the thirteen hundred players in the
    log carry an accent, a hyphen, an apostrophe or a full stop, so matching
    on the raw string loses about four percent of the league silently — and
    silently is the problem, because the row simply never appears.

    This strips accents and punctuation and collapses whitespace. It does
    **not** do anything fuzzy — and it does *not* make `"J.T. Miller"` equal
    `"JT Miller"`: the dots become spaces, so the first normalises to
    `"j t miller"` and the second to `"jt miller"`. An earlier version of this
    docstring claimed otherwise, and the claim cost twenty priced A.J. Greer
    outcomes their match. Joining the two spellings is the alias layer's job
    (`player_name_aliases`), which emits an initials-collapsed variant —
    a *stated* equivalence, not a fuzzy one.
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return " ".join(text.split()).casefold()


def _collapse_initials(normalized: str) -> str:
    """`"j t miller"` -> `"jt miller"`; `"a j greer"` -> `"aj greer"`.

    A run of single-letter tokens is initials however the source punctuated
    them, and books print `"JT Miller"` where the registry writes
    `"J.T. Miller"`. Joining the letters is a stated equivalence about
    initials, not a fuzzy match: multi-letter tokens are never merged, so
    `"j miller"` stays distinct from `"jt miller"`.
    """
    tokens = normalized.split()
    collapsed: list[str] = []
    run: list[str] = []
    for token in tokens + [""]:
        if len(token) == 1:
            run.append(token)
            continue
        if run:
            collapsed.append("".join(run))
            run = []
        if token:
            collapsed.append(token)
    return " ".join(collapsed)


def player_key(name: object) -> str:
    """One key per player as a bet is written: normalized, initials collapsed.

    `"Alexis Lafreniere"` (one book) and `"Alexis Lafrenière"` (another), or
    `"JT Miller"` and `"J.T. Miller"`, are one player and so one wager.
    `"Elias Pettersson (2004)"` keeps its disambiguating number and stays
    apart from `"Elias Pettersson"`. `card_pricing.selection_key` keys on
    this, so every consumer of that key — the card, the snapshot, the CLV
    collapse — agrees with the resolver that prices both spellings as one.
    """
    return _collapse_initials(normalize_player_name(name))


def player_name_aliases(name: object) -> tuple[str, ...]:
    """Every normalized form one registry spelling can legitimately take.

    The registry carries constructions like `"Anthony-John (AJ) Greer"`, where
    the parenthesis is the name the player actually goes by and the name a
    book will print. Both forms are indexed, because the alias is stated in
    the source rather than guessed at — and every form is also indexed with
    its initials collapsed, so `"J.T. Miller"` meets `"JT Miller"` without
    anything fuzzy happening.
    """
    text = str(name or "")
    digits = re.search(r"\((\d+)\)", text)
    if digits:
        # A parenthesised number is a disambiguator, not a nickname: the
        # provider writes "Elias Pettersson (2004)" precisely because two
        # players share the name. Erasing it to the bare name re-creates the
        # collision the provider went out of its way to prevent — the bare
        # form then binds to whichever same-named player happens to have a
        # sample, which put one wrong-player bet into a shipped measurement.
        # The disambiguated form aliases only to itself; a sample side that
        # cannot produce the same form goes honestly unmatched (a void, not
        # a coin flip).
        return (normalize_player_name(text),)
    forms = {normalize_player_name(text)}
    nickname = re.search(r"\(([^)]+)\)", text)
    if nickname:
        without = normalize_player_name(re.sub(r"\([^)]*\)", " ", text))
        parts = without.split()
        called = normalize_player_name(nickname.group(1))
        if called and parts:
            # The nickname replaces the given name, keeping the surname.
            forms.add(" ".join([called, parts[-1]]))
        forms.add(without)
    forms |= {_collapse_initials(form) for form in set(forms)}
    return tuple(sorted(form for form in forms if form))


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

    #: Player-appearances of back-to-back evidence at which a fitted factor
    #: keeps half its measured deviation from 1.0. About twelve percent of
    #: appearances are back-to-backs, so a full fit holds many thousands and
    #: an early walk-forward window a few hundred — early factors sit near
    #: 1.0 and grow with evidence, the same shape the team model uses.
    B2B_SHRINKAGE_APPEARANCES = 1500

    #: Last-five team form (Cooper, 2026-10-21): how a club's skaters have
    #: produced, and what its opponents have produced against it, over its
    #: last `TEAM_FORM_GAMES` games, against its own longer record. Shrunk by
    #: games / (games + `TEAM_FORM_SHRINKAGE_GAMES`), so five games keep a
    #: quarter of their deviation, and clamped to `TEAM_FORM_RANGE`.
    TEAM_FORM_GAMES = 5
    TEAM_FORM_SHRINKAGE_GAMES = 15
    TEAM_FORM_RANGE = (0.85, 1.18)

    #: Hits model (`HITS_OPTIONS`). A rink's factor is its recent home games'
    #: hits (both clubs) over the same club's recent road games', so the home
    #: club's own style cancels; shrunk at `HITS_RINK_SHRINKAGE_GAMES` home
    #: games and clamped to `HITS_RINK_RANGE`.
    HITS_RINK_GAMES = 82
    HITS_RINK_SHRINKAGE_GAMES = 20
    HITS_RINK_RANGE = (0.6, 1.6)
    HITS_HALF_LIFE_GAMES = 60
    #: Bounds on the measured hits shrinkage, in seconds of ice time.
    HITS_SHRINKAGE_RANGE = (3_000.0, 70_000.0)
    #: Games a skater needs to count toward the measured spread.
    HITS_MEASURE_GAMES = 30

    def __init__(self, hits_options: frozenset[str] | set[str] | None = None) -> None:
        #: Which parts of the hits model are fitted; the card fits all of
        #: them. The walk-forward passes an empty set by default, so every
        #: committed measurement stands as it was made.
        self.hits_options = frozenset(
            HITS_OPTIONS if hits_options is None else hits_options
        )
        unknown = self.hits_options - HITS_OPTIONS
        if unknown:
            raise ValueError(f"Unknown hits options {sorted(unknown)}; known {sorted(HITS_OPTIONS)}")
        #: Rink -> hits scorer factor (1.0 is the league). Keyed by the home
        #: club, whose rink it is.
        self.hits_rink_factors: dict[str, float] = {}
        #: Position group -> measured hits shrinkage, seconds of ice time.
        self.hits_shrinkage_seconds: dict[str, float] = {}
        self.skaters: dict[int, SkaterRates] = {}
        self.goalies: dict[int, GoalieRates] = {}
        self.baselines: dict[str, dict[str, float]] = {}
        self.opponent_factors: dict[str, dict[str, float]] = {}
        #: The same concession table split by the scorer's position group
        #: (forwards, defencemen): what each club allows opposing forwards and
        #: opposing defencemen, each against the league's figure for that
        #: group (Cooper, 2026-10-21: opponent matchup by position). Used in
        #: place of `opponent_factors` where it holds the player's group.
        self.opponent_group_factors: dict[str, dict[str, dict[str, float]]] = {}
        self.venue_factors: dict[str, dict[str, float]] = {}
        self.dispersion: dict[str, Dispersion] = {}
        #: Per-market production multipliers when a side played yesterday,
        #: keyed by market then "own"/"opp". Fitted in `_fit_b2b_factors`.
        self.b2b_factors: dict[str, dict[str, float]] = {}
        self.league_save_rate: float = 0.900
        self.league_shots_against_per60: float = 30.0
        self.report = PropsModelReport()
        self.opponent_shot_factors: dict[str, float] = {}
        #: Per team, per skater stat: {"for": own skaters' last-five
        #: production, "against": opponents' last-five production against
        #: it}, each a shrunk multiplier on its own longer record. Set by
        #: `fit` from the logs it saw; `team_form_factors` rebuilds it for
        #: any night.
        self.team_form: dict[str, dict[str, dict[str, float]]] = {}
        #: Tonight's referee crew per game, {frozenset({team, opponent}):
        #: factor}, set by the card (`referees.tonight_factors`); it scales
        #: goals, assists and points. Empty moves nothing.
        self.game_factors: dict[frozenset, float] = {}
        #: Names two priced players share, which resolve to neither on their
        #: own. Some are recoverable with a team; see `_index_names`.
        self.ambiguous_names: tuple[str, ...] = ()
        #: Every player id that claims an indexed form, and the same by
        #: (form, team). Kept whole rather than deduplicated, because the
        #: resolver unions them across all of a provider name's forms.
        self._claims: dict[str, frozenset[int]] = {}
        self._claims_team: dict[tuple[str, str], frozenset[int]] = {}

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
        frame["_hits_raw"] = frame["hits"].astype(float)
        self.hits_rink_factors = {}
        self.hits_shrinkage_seconds = {}
        if "rink" in self.hits_options:
            self.hits_rink_factors = fit_hits_rink_factors(frame)
            arena = _arena(frame)
            frame["hits"] = frame["hits"].astype(float) / arena.map(
                lambda club: self.hits_rink_factors.get(club, 1.0)
            ).astype(float)

        skaters = frame[frame["role"].astype(str) == "skater"]
        goalies = frame[frame["role"].astype(str) == "goalie"]

        self.report = PropsModelReport(games=int(frame["game_id"].nunique()))
        self._fit_b2b_factors(frame)
        self._fit_dispersion(skaters, goalies)
        self._fit_baselines(skaters)
        self._fit_opponent_factors(skaters)
        self._fit_opponent_group_factors(skaters)
        self._fit_venue_factors(skaters)
        self._fit_skaters(skaters)
        self._fit_hits(skaters)
        self._fit_goalies(goalies)
        self.opponent_shot_factors = fit_opponent_shot_factors(frame)
        self.team_form = team_form_factors(team_game_totals(frame))
        self.report.dispersion = dict(self.dispersion)
        self._index_names()
        return self

    def _index_names(self) -> None:
        """Index every priced player under every legitimate spelling.

        A key two different players share keeps **both** owners, and a name
        that reaches both resolves to neither — it is never assigned to one
        of them. Resolving it to whichever was indexed first would produce a
        confident price for the wrong man on a row that looks correct.

        The league has two of these right now and they are not hypothetical:
        two Elias Petterssons, both Vancouver, and two Sebastian Ahos, one
        Carolina and one on the Islanders. So names are indexed a second time
        **by name and team**, which is not a fuzzier match but a stricter one
        — it uses a field the price row already carries. That recovers Aho.
        It does not recover Pettersson, because both play for the same club
        and nothing in a prop row separates them, and that is the correct
        outcome rather than a coin flip.
        """
        claims: dict[str, set[int]] = {}
        claims_team: dict[tuple[str, str], set[int]] = {}

        for source in (self.skaters, self.goalies):
            for player_id, rates in source.items():
                if not rates.player.strip():
                    continue
                team = str(rates.team).strip().upper()
                for alias in player_name_aliases(rates.player):
                    claims.setdefault(alias, set()).add(player_id)
                    if team:
                        claims_team.setdefault((alias, team), set()).add(player_id)

        self.ambiguous_names = tuple(
            sorted(alias for alias, owners in claims.items() if len(owners) > 1)
        )
        self._claims = {
            alias: frozenset(owners) for alias, owners in claims.items()
        }
        self._claims_team = {
            key: frozenset(owners) for key, owners in claims_team.items()
        }

    def _fit_b2b_factors(self, frame: pd.DataFrame) -> None:
        """How production shifts when a side played yesterday, per market.

        Fitted from the training logs only — the schedule state of a training
        game derives from earlier training games, so a walk-forward refit can
        never see the game it prices. Two factors per market:

        ``own``: the player's team played yesterday. Scoring drops about six
        percent in the diagnostic; blocked shots hold; the tired team's goalie
        faces *more* shots.

        ``opp``: the opponent played yesterday. The mirror image — facing
        tired legs, scoring rises — and the both-tired case multiplies the two
        and lands near baseline, which is what the diagnostic showed without
        being asked to.

        The ratio is per *appearance*, not per sixty minutes, so it carries
        both the rate effect and any bench-shortening in one number — the
        model's expected TOI is a trailing mean that knows nothing about
        tonight's schedule, so the correction has to carry the minutes effect
        itself.
        """
        dated = frame[["game_id", "team", "date"]].drop_duplicates()
        last_seen: dict[str, str] = {}
        flags: dict[tuple[int, str], bool] = {}
        for row in dated.sort_values("date").itertuples():
            day = str(row.date)[:10]
            team = str(row.team)
            previous = last_seen.get(team)
            tired = False
            if previous:
                try:
                    tired = (
                        pd.Timestamp(day) - pd.Timestamp(previous)
                    ).days == 1
                except (ValueError, TypeError):
                    tired = False
            flags[(int(row.game_id), team)] = tired
            last_seen[team] = day

        working = frame.copy()
        working["_own_b2b"] = [
            flags.get((int(g), str(team)), False)
            for g, team in zip(working["game_id"], working["team"])
        ]
        working["_opp_b2b"] = [
            flags.get((int(g), str(opponent)), False)
            for g, opponent in zip(working["game_id"], working["opponent"])
        ]

        skaters = working[working["role"].astype(str) == "skater"]
        goalies = working[
            (working["role"].astype(str) == "goalie")
            & (working["toi_seconds"] >= 2400)
        ]
        self.b2b_factors = {}
        for stat, rows_frame, column in (
            *((stat, skaters, stat) for stat in SKATER_STATS),
            (GOALIE_STAT, goalies, GOALIE_SETTLEMENT_COLUMN),
        ):
            factors = {}
            for side, flag_column in (("own", "_own_b2b"), ("opp", "_opp_b2b")):
                tired_rows = rows_frame[rows_frame[flag_column]]
                rested_rows = rows_frame[~rows_frame[flag_column]]
                rested_rate = (
                    float(rested_rows[column].mean())
                    if len(rested_rows)
                    else 0.0
                )
                if not len(tired_rows) or rested_rate <= 0:
                    factors[side] = 1.0
                    continue
                raw = float(tired_rows[column].mean()) / rested_rate
                weight = len(tired_rows) / (
                    len(tired_rows) + self.B2B_SHRINKAGE_APPEARANCES
                )
                factors[side] = 1.0 + weight * (raw - 1.0)
            self.b2b_factors[stat] = factors

    def _fit_dispersion(self, skaters: pd.DataFrame, goalies: pd.DataFrame) -> None:
        """Measure variance/mean per stat once, on the whole column.

        Measured on players with real workloads only. Including a fourth-line
        winger's eight-minute nights would drag every mean toward zero and make
        every stat look Poisson by dilution.
        """
        regulars = skaters[skaters["toi_seconds"] >= 600]
        for stat in SKATER_STATS:
            column = "_hits_raw" if stat == "hits" and "_hits_raw" in regulars else stat
            self.dispersion[stat] = measure_dispersion(regulars[column].tolist())
        if "dispersion" in self.hits_options:
            measured = self._hits_within_player_dispersion(regulars)
            if measured is not None:
                self.dispersion["hits"] = measured
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

    def _fit_opponent_group_factors(self, skaters: pd.DataFrame) -> None:
        """`_fit_opponent_factors` per position group: per game, what each
        club allowed opposing forwards and opposing defencemen, against the
        league's per-game figure for that group, shrunk the same way."""
        self.opponent_group_factors = {}
        rows = skaters[skaters["group"].isin(["F", "D"])]
        per_game = (
            rows.groupby(["opponent", "game_id", "group"])[list(SKATER_STATS)]
            .sum()
            .reset_index()
        )
        if per_game.empty:
            return
        for group, by_group in per_game.groupby("group"):
            league = {stat: float(by_group[stat].mean()) for stat in SKATER_STATS}
            for team, team_rows in by_group.groupby("opponent"):
                played = len(team_rows)
                weight = played / (played + self.OPPONENT_SHRINKAGE_GAMES)
                self.opponent_group_factors.setdefault(str(team), {})[str(group)] = {
                    stat: 1.0
                    + weight
                    * (
                        (float(team_rows[stat].mean()) / league[stat] if league[stat] else 1.0)
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

    def _hits_within_player_dispersion(self, regulars: pd.DataFrame) -> Dispersion | None:
        """Hits' negative-binomial spread inside each player's own games.

        Each game's expected count is the player's own mean (on the rink
        adjusted scale where `rink` is fitted, times that game's rink), so
        the gap between one player and another is not counted as noise. Ice
        time is not conditioned on, because the card prices on expected ice
        time and tonight's minutes are part of tonight's noise. Method of
        moments: 1/r = sum((x - mu)^2 * n/(n-1) - mu) / sum(mu^2). Returned
        as a `Dispersion` at the league's mean with that r, so the shape every
        reader builds is the measured one. None when too few players.
        """
        rows = regulars[["player_id", "hits", "_hits_raw"]].copy()
        if "rink" in self.hits_options:
            rows["_rink"] = _arena(regulars).map(
                lambda club: self.hits_rink_factors.get(club, 1.0)
            ).astype(float)
        else:
            rows["_rink"] = 1.0
        counts = rows.groupby("player_id")["hits"].transform("size")
        rows = rows[counts >= self.HITS_MEASURE_GAMES]
        if rows["player_id"].nunique() < 20:
            return None
        n = rows.groupby("player_id")["hits"].transform("size").astype(float)
        level = rows.groupby("player_id")["hits"].transform("mean")
        mu = level * rows["_rink"]
        x = rows["_hits_raw"].astype(float)
        excess = float((((x - mu) ** 2) * n / (n - 1.0) - mu).sum())
        scale = float((mu**2).sum())
        mean = float(x.mean())
        if scale <= 0 or mean <= 0:
            return None
        inverse_r = excess / scale
        if inverse_r <= 0:
            return Dispersion(mean=mean, variance=mean, samples=len(rows))
        return Dispersion(
            mean=mean, variance=mean + mean * mean * inverse_r, samples=len(rows)
        )

    def _fit_hits(self, skaters: pd.DataFrame) -> None:
        """Refit every priced skater's hit rate, as `hits_options` says.

        `shrinkage`: per position group, the shrinkage is sampling noise over
        the real spread of hit rates. For players with `HITS_MEASURE_GAMES`
        or more games, the spread of their raw per-second rates minus the
        noise expected at each one's ice time (Poisson noise times the hits
        dispersion) is the real spread tau^2, and the shrinkage in seconds is
        phi * m / tau^2, bounded by `HITS_SHRINKAGE_RANGE`. `recency` weights
        each game by 0.5 ** (games ago / `HITS_HALF_LIFE_GAMES`) in both the
        hits and the seconds behind the rate. Without either the rate is the
        one `_fit_skaters` fitted.
        """
        if not ({"shrinkage", "recency"} & self.hits_options) or not self.skaters:
            return
        frame = skaters[["player_id", "group", "toi_seconds", "hits", "date", "game_id"]].copy()
        frame["hits"] = frame["hits"].astype(float)
        frame = frame.sort_values(["player_id", "date", "game_id"], ascending=[True, False, False])
        if "recency" in self.hits_options:
            ago = frame.groupby("player_id").cumcount().to_numpy(dtype=float)
            frame["_w"] = np.power(0.5, ago / self.HITS_HALF_LIFE_GAMES)
        else:
            frame["_w"] = 1.0
        frame["_wh"] = frame["hits"] * frame["_w"]
        frame["_ws"] = frame["toi_seconds"] * frame["_w"]
        sums = frame.groupby("player_id")[["_wh", "_ws"]].sum()

        shrink: dict[str, float] = {}
        for group in ("F", "D"):
            if "shrinkage" in self.hits_options:
                shrink[group] = self._measured_hits_shrinkage(skaters, group)
            else:
                shrink[group] = float(self.SHRINKAGE_SECONDS)
        self.hits_shrinkage_seconds = shrink

        for player_id, rates in list(self.skaters.items()):
            if player_id not in sums.index:
                continue
            seconds = float(sums.at[player_id, "_ws"])
            if seconds <= 0:
                continue
            baseline = self.baselines.get(rates.group, {}).get("hits", 0.0)
            k = shrink.get(rates.group, float(self.SHRINKAGE_SECONDS))
            weight = seconds / (seconds + k)
            raw = float(sums.at[player_id, "_wh"]) / seconds * 3600.0
            per60 = dict(rates.per60)
            per60["hits"] = baseline + weight * (raw - baseline)
            self.skaters[player_id] = replace(rates, per60=per60)

    def _measured_hits_shrinkage(self, skaters: pd.DataFrame, group: str) -> float:
        low, high = self.HITS_SHRINKAGE_RANGE
        rows = skaters[skaters["group"] == group]
        per_player = rows.groupby("player_id").agg(
            hits=("hits", "sum"), seconds=("toi_seconds", "sum"), games=("hits", "size")
        )
        per_player = per_player[
            (per_player["games"] >= self.HITS_MEASURE_GAMES) & (per_player["seconds"] > 0)
        ]
        if len(per_player) < 20:
            return float(self.SHRINKAGE_SECONDS)
        rate = per_player["hits"] / per_player["seconds"]
        seconds = per_player["seconds"].astype(float)
        mean = float(per_player["hits"].sum() / seconds.sum())
        if mean <= 0:
            return float(self.SHRINKAGE_SECONDS)
        # Game-to-game noise beyond Poisson: the hits dispersion's
        # variance-to-mean at a typical game's count.
        dispersion = self.dispersion.get("hits")
        per_game = float(per_player["hits"].sum() / per_player["games"].sum())
        r = dispersion.r if dispersion is not None else None
        phi = 1.0 + (per_game / r if r else 0.0)
        spread = float(np.average((rate - mean) ** 2, weights=seconds))
        noise = float(np.average(phi * mean / seconds, weights=seconds))
        tau2 = spread - noise
        if tau2 <= 0:
            return high
        return float(min(max(phi * mean / tau2, low), high))

    def hits_rink_factor(self, arena: object) -> float:
        """Tonight's rink's hits scorer factor; 1.0 when it is not fitted."""
        return float(self.hits_rink_factors.get(str(arena), 1.0))

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

    def resolve_player(self, name: str, *, team: str | None = None) -> int | None:
        """Map a provider's player name to a fitted player id, or None.

        Exact after normalisation — accents, punctuation and casing are
        representation and are removed — over the forms `player_name_aliases`
        states (initials collapsed, a parenthesised nickname), which are the
        forms the backtest and settlement join on. Nothing else is. Fuzzy
        matching a prop to the wrong player produces a confident price for a
        bet nobody placed, and the failure is invisible: the row looks exactly
        like a correct one. Unmatched names are reported by the caller instead.

        `team` is consulted only when the name alone is ambiguous, and it
        narrows rather than loosens: it is another field that must agree, not
        a tolerance.
        """
        # Every form the alias layer states for the provider's spelling, not
        # just its plain normalisation: a book's "A.J. Greer" normalises to
        # "a j greer", which the registry's "Anthony-John (AJ) Greer" never
        # produces, but both state "aj greer". The backtest and forward
        # settlement join on these forms on both sides; resolving on one form
        # here left the card with no opinion (and the ledger with no row) on
        # players the measurement bets.
        #
        # A match is the union of every player any form reaches, and it
        # resolves only when that union is one player — the same candidate
        # set settlement builds. Stopping at the first form that hits would
        # let an unambiguous form outvote an ambiguous one.
        forms = player_name_aliases(name)
        owners = set().union(*(self._claims.get(form, ()) for form in forms))
        if len(owners) == 1:
            return next(iter(owners))
        if team:
            label = str(team).strip().upper()
            owners = set().union(
                *(self._claims_team.get((form, label), ()) for form in forms)
            )
            if len(owners) == 1:
                return next(iter(owners))
        return None

    def resolve_player_in_game(
        self, name: str, *, home: str, away: str
    ) -> int | None:
        """Resolve a name given the two teams in the game it was priced for.

        A prop row names the game but not which side the player is on, so both
        are tried. Exactly one match resolves; two matches is a genuine
        ambiguity — the same name on both teams — and resolves to neither.
        """
        found = self.resolve_player(name)
        if found is not None:
            return found
        candidates = {
            self.resolve_player(name, team=team)
            for team in (home, away)
            if team
        }
        candidates.discard(None)
        return candidates.pop() if len(candidates) == 1 else None

    def pp_multiplier(self, rates: SkaterRates, stat: str) -> float:
        if stat not in PP_SENSITIVE_STATS:
            return 1.0
        # A player taking a fifth of his team's power-play goals is a first-unit
        # regular; one taking none is not. Mapped through a shallow curve and
        # then clamped, because the proxy is noisy.
        raw = 1.0 + 1.4 * (rates.pp_share - 0.12)
        low, high = self.PP_MULTIPLIER_RANGE
        return min(max(raw, low), high)

    def b2b_multiplier(
        self, stat: str, *, own_b2b: bool = False, opp_b2b: bool = False
    ) -> float:
        """The fitted rest effect for one market, given tonight's schedule.

        Both-tired multiplies the two factors, which the diagnostic showed
        landing near baseline without being asked to — the effects genuinely
        cancel rather than compounding.
        """
        factors = self.b2b_factors.get(stat, {})
        multiplier = 1.0
        if own_b2b:
            multiplier *= float(factors.get("own", 1.0))
        if opp_b2b:
            multiplier *= float(factors.get("opp", 1.0))
        return multiplier

    def expected_count(
        self,
        player_id: int,
        stat: str,
        *,
        opponent: str,
        venue: str,
        expected_toi_seconds: float | None = None,
        own_b2b: bool = False,
        opp_b2b: bool = False,
        team: str | None = None,
    ) -> float | None:
        """The distribution's mean, or None when there is no modelled opinion.

        `own_b2b` / `opp_b2b`: whether each side played yesterday. Rest is
        schedule information, known before puck drop; a caller that does not
        know passes nothing and prices every side as rested — the direction
        that only ever declines to move a price.
        """
        if stat == GOALIE_STAT:
            return self.expected_saves(
                player_id,
                opponent=opponent,
                venue=venue,
                expected_toi_seconds=expected_toi_seconds,
                own_b2b=own_b2b,
                opp_b2b=opp_b2b,
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
        opponent_factor = self.opponent_factor(str(opponent), rates.group, stat)
        venue_factor = self.venue_factors.get(str(venue), {}).get(stat, 1.0)
        return (
            rates.per60[stat]
            * (toi / 3600.0)
            * opponent_factor
            * venue_factor
            * self.pp_multiplier(rates, stat)
            * self.b2b_multiplier(stat, own_b2b=own_b2b, opp_b2b=opp_b2b)
            * self.team_form_multiplier(
                stat, team=team if team else rates.team, opponent=str(opponent)
            )
            * self.crew_multiplier(stat, team if team else rates.team, opponent)
            * (
                self.hits_rink_factor(
                    (team if team else rates.team)
                    if str(venue) == "home"
                    else opponent
                )
                if stat == "hits"
                else 1.0
            )
        )

    def crew_multiplier(self, stat: str, team: object, opponent: object) -> float:
        """Tonight's referee crew, on the scoring stats only."""
        if not self.game_factors or stat not in ("goals", "assists", "points"):
            return 1.0
        return float(self.game_factors.get(frozenset({str(team), str(opponent)}), 1.0))

    def opponent_factor(self, opponent: str, group: str, stat: str) -> float:
        """What `opponent` allows this player's position group in `stat`,
        against the league; the all-skater figure where the group has none."""
        by_group = self.opponent_group_factors.get(str(opponent), {}).get(str(group))
        if by_group and stat in by_group:
            return float(by_group[stat])
        return float(self.opponent_factors.get(str(opponent), {}).get(stat, 1.0))

    def team_form_multiplier(self, stat: str, *, team: str, opponent: str) -> float:
        """Own club's last-five production times the opponent's last-five
        concession, each against its longer record; 1.0 for a club with no
        form. Goalie saves are not touched here: the saves context model
        reads both clubs' recent shot rates itself."""
        own = self.team_form.get(str(team), {}).get(stat, {}).get("for", 1.0)
        opp = self.team_form.get(str(opponent), {}).get(stat, {}).get("against", 1.0)
        return float(own) * float(opp)

    def expected_saves(
        self,
        player_id: int,
        *,
        opponent: str,
        venue: str,
        expected_toi_seconds: float | None = None,
        own_b2b: bool = False,
        opp_b2b: bool = False,
    ) -> float | None:
        """Expected saves = expected shots against x save rate.

        Shots against is driven by the opponent's shot volume and by the
        goalie's own team's defensive profile, neither of which is a property
        of the goalie. Modelling saves directly would attribute both to him.

        The rest flags are *team* facts, deliberately: `own_b2b` means the
        skaters in front of him played yesterday — tired legs concede more
        shots, so his expected saves rise — whatever the goalie himself did,
        which matters because back-to-backs are exactly when backups start.
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
        return (
            shots
            * rates.save_rate
            * self.b2b_multiplier(
                GOALIE_STAT, own_b2b=own_b2b, opp_b2b=opp_b2b
            )
        )

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
        own_b2b: bool = False,
        opp_b2b: bool = False,
        team: str | None = None,
    ) -> CountDistribution | None:
        mean = self.expected_count(
            player_id,
            stat,
            opponent=opponent,
            venue=venue,
            expected_toi_seconds=expected_toi_seconds,
            own_b2b=own_b2b,
            opp_b2b=opp_b2b,
            team=team,
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
        own_b2b: bool = False,
        opp_b2b: bool = False,
        team: str | None = None,
    ) -> float | None:
        """P(count beats `line`), or None when there is no modelled opinion."""
        shape = self.distribution(
            player_id,
            stat,
            opponent=opponent,
            venue=venue,
            expected_toi_seconds=expected_toi_seconds,
            own_b2b=own_b2b,
            opp_b2b=opp_b2b,
            team=team,
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


def _arena(frame: pd.DataFrame) -> pd.Series:
    """The club whose rink each row was played in: the home side."""
    home = frame["venue"].astype(str) == "home"
    return frame["team"].astype(str).where(home, frame["opponent"].astype(str))


def fit_hits_rink_factors(logs: pd.DataFrame) -> dict[str, float]:
    """Each rink's hits scorer factor, from skater logs (see `HITS_OPTIONS`).

    For each club, total hits (both sides) per game over its last
    `HITS_RINK_GAMES` home games, over the same over its last as many road
    games: the club's own style and its schedule are on both sides of the
    ratio, so what is left is the home scorer. Shrunk toward 1.0 at
    `HITS_RINK_SHRINKAGE_GAMES` home games, rescaled so the clubs' factors
    average 1.0, and clamped to `HITS_RINK_RANGE`.
    """
    model = PlayerPropsModel
    skaters = logs[logs["role"].astype(str) == "skater"].copy()
    if skaters.empty:
        return {}
    column = "_hits_raw" if "_hits_raw" in skaters else "hits"
    skaters["_h"] = pd.to_numeric(skaters[column], errors="coerce").fillna(0.0)
    skaters["_arena"] = _arena(skaters)
    per_game = (
        skaters.groupby(["game_id", "date", "_arena"])["_h"].sum().reset_index()
    )
    teams_in = skaters[["game_id", "team"]].drop_duplicates()
    per_game = per_game.merge(teams_in, on="game_id")
    per_game["_home"] = per_game["team"].astype(str) == per_game["_arena"].astype(str)
    per_game = per_game.sort_values(["date", "game_id"])
    raw: dict[str, tuple[float, int]] = {}
    for club, rows in per_game.groupby("team"):
        home = rows[rows["_home"]].tail(model.HITS_RINK_GAMES)
        road = rows[~rows["_home"]].tail(model.HITS_RINK_GAMES)
        if home.empty or road.empty or float(road["_h"].mean()) <= 0:
            continue
        raw[str(club)] = (float(home["_h"].mean()) / float(road["_h"].mean()), len(home))
    if not raw:
        return {}
    shrunk = {
        club: 1.0 + games / (games + model.HITS_RINK_SHRINKAGE_GAMES) * (ratio - 1.0)
        for club, (ratio, games) in raw.items()
    }
    scale = float(np.mean(list(shrunk.values())))
    low, high = model.HITS_RINK_RANGE
    return {
        club: float(min(max(value / scale, low), high)) for club, value in shrunk.items()
    }


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


def team_game_totals(logs: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, game): its skaters' totals of every skater stat and
    what its opponents' skaters totalled against it, with the game's date.

    Built once so a walk-forward can ask `team_form_factors` for any night
    without re-aggregating the logs.
    """
    columns = ["team", "game_id", "date", *(f"for_{s}" for s in SKATER_STATS),
               *(f"against_{s}" for s in SKATER_STATS)]
    skaters = logs[logs["role"].astype(str) == "skater"].copy()
    if skaters.empty:
        return pd.DataFrame(columns=columns)
    for stat in SKATER_STATS:
        skaters[stat] = pd.to_numeric(skaters[stat], errors="coerce").fillna(0)
    skaters["date"] = skaters["date"].astype(str).str[:10]
    made = (
        skaters.groupby(["team", "game_id", "date"])[list(SKATER_STATS)].sum()
        .rename(columns={s: f"for_{s}" for s in SKATER_STATS})
    )
    allowed = (
        skaters.groupby(["opponent", "game_id", "date"])[list(SKATER_STATS)].sum()
        .rename(columns={s: f"against_{s}" for s in SKATER_STATS})
    )
    allowed.index = allowed.index.set_names(["team", "game_id", "date"])
    out = made.join(allowed, how="inner").reset_index()
    out["team"] = out["team"].astype(str)
    return out[columns].sort_values(["date", "game_id"]).reset_index(drop=True)


def team_form_factors(
    totals: pd.DataFrame, before: str | None = None
) -> dict[str, dict[str, dict[str, float]]]:
    """Each club's last-five form per skater stat, from games before `before`.

    `for` is its skaters' production over its last
    `PlayerPropsModel.TEAM_FORM_GAMES` games over their production in every
    game the logs hold for it; `against` the same for what opponents produced
    against it. Each is shrunk by games / (games + TEAM_FORM_SHRINKAGE_GAMES)
    and clamped to TEAM_FORM_RANGE. A ratio with a zero denominator is 1.0.
    """
    if totals is None or totals.empty:
        return {}
    frame = totals if before is None else totals[totals["date"] < str(before)[:10]]
    if frame.empty:
        return {}
    n_last = PlayerPropsModel.TEAM_FORM_GAMES
    low, high = PlayerPropsModel.TEAM_FORM_RANGE
    out: dict[str, dict[str, dict[str, float]]] = {}
    for team, rows in frame.groupby("team"):
        last = rows.tail(n_last)
        n = len(last)
        weight = n / (n + PlayerPropsModel.TEAM_FORM_SHRINKAGE_GAMES)
        stats: dict[str, dict[str, float]] = {}
        for stat in SKATER_STATS:
            entry = {}
            for side in ("for", "against"):
                column = f"{side}_{stat}"
                level = float(rows[column].mean())
                recent = float(last[column].mean())
                ratio = recent / level if level > 0 else 1.0
                entry[side] = min(max(1.0 + weight * (ratio - 1.0), low), high)
            stats[stat] = entry
        out[str(team)] = stats
    return out
