"""DraftKings fantasy-point projections for The Lineup, built from the lab's models.

The Lineup is Cooper's DFS lineup builder (a Cloudflare Worker, outside this
repository). Until 2026-10-11 its projection was DraftKings' own season
average nudged a few percent by the website board's team numbers, so the
player model this lab maintains never reached a DraftKings lineup. This
module turns that model into DraftKings points.

**What a projection is.** For each skater, the expected goals, assists, shots
on goal and blocked shots tonight (the props model's means: per-60 rates times
expected ice time, with the opponent, venue, power-play and back-to-back
factors), scored on DraftKings' classic NHL table, plus the four 3-point
bonuses at the probabilities the model's count distributions give them. For a
goalie, expected saves, goals against, a win, an overtime loss, a shutout and
35+ saves, all *if he starts*: nothing here knows who starts.

**Where the books post a line, the books' number wins.** This lab's own
record (`docs/why_the_model_has_no_edge.md`) is that the model's disagreement
with a de-vigged prop price carries no information. So for each player and
stat with a two-sided quote, the mean is the one that makes the model's own
distribution shape reproduce the de-vigged chance of the over, and the model's
mean is used only where no book quotes him. `points` anchors assists when
there is no assists quote (assists = points - goals). Only these derived means
leave the lab: no price, line or book is in the payload.

**Spread.** `p10`, `p90` and `sd` come from simulating each player's night
from the same distributions, with shots never fewer than goals and points
always goals plus assists. Goals, assists, shots and blocks are otherwise drawn
independently, which understates how much a big night travels together, so
the ceiling is a floor on the true ceiling, not a measured quantile.

Scoring omits DraftKings' short-handed point and shootout-goal bonuses: the
boxscore logs do not carry short-handed points, so the measurement could not
score them either, and leaving them out of both keeps the comparison honest.

Nothing here reaches the card, a frozen opinion or the forward ledger.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

import numpy as np
from scipy import stats

#: DraftKings classic NHL scoring (2026-27), skaters.
DK_SKATER = {
    "goal": 8.5,
    "assist": 5.0,
    "shot": 1.5,
    "block": 1.3,
    "hat_trick": 3.0,
    "three_points": 3.0,
    "five_shots": 3.0,
    "three_blocks": 3.0,
}

#: DraftKings classic NHL scoring, goalies.
DK_GOALIE = {
    "win": 6.0,
    "save": 0.7,
    "goal_against": -3.5,
    "shutout": 4.0,
    "ot_loss": 2.0,
    "saves_35": 3.0,
}

#: The props-model stats a skater projection reads. `points` sets the 3+
#: point bonus's dispersion and can anchor assists.
SKATER_STATS = ("goals", "assists", "shots_on_goal", "blocked_shots", "points")
GOALIE_STAT = "goalie_saves"
ANCHORABLE = frozenset(SKATER_STATS) | {GOALIE_STAT}

#: A de-vigged over chance outside this band says little about the mean (a
#: 0.5 line on a fourth-liner's points is a statement about zero, not about
#: his average), so such lines do not anchor.
ANCHOR_BAND = (0.05, 0.95)

SIM_DRAWS = 4000


# -- count distribution arithmetic, vectorised ---------------------------


def _r_or_nan(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return math.nan
    return number if math.isfinite(number) and number > 0 else math.nan


def tail(mean, r, k) -> np.ndarray:
    """P(X >= k) for Poisson (r NaN) or negative binomial (variance m + m^2/r)."""
    mean = np.maximum(np.asarray(mean, dtype=float), 1e-9)
    r = np.broadcast_to(np.asarray(r, dtype=float), mean.shape)
    k = np.broadcast_to(np.asarray(k, dtype=float), mean.shape)
    out = stats.poisson.sf(k - 1, mean)
    nb = np.isfinite(r)
    if nb.any():
        rr = r[nb]
        out = np.array(out, dtype=float)
        out[nb] = stats.nbinom.sf(k[nb] - 1, rr, rr / (rr + mean[nb]))
    return np.asarray(out, dtype=float)


def _pmf(mean, r, k) -> np.ndarray:
    mean = np.maximum(np.asarray(mean, dtype=float), 1e-9)
    r = np.broadcast_to(np.asarray(r, dtype=float), mean.shape)
    k = np.broadcast_to(np.asarray(k, dtype=float), mean.shape)
    out = np.array(stats.poisson.pmf(k, mean), dtype=float)
    nb = np.isfinite(r)
    if nb.any():
        rr = r[nb]
        out[nb] = stats.nbinom.pmf(k[nb], rr, rr / (rr + mean[nb]))
    return out


def over_probability(mean, r, line) -> np.ndarray:
    """P(over `line`), a whole-number line conditioned on no push, as books grade it."""
    line = np.asarray(line, dtype=float)
    floor = np.floor(line)
    over = tail(mean, r, floor + 1)
    whole = np.isclose(line, floor)
    if np.any(whole):
        push = _pmf(mean, r, floor)
        over = np.where(whole, over / np.maximum(1.0 - push, 1e-12), over)
    return over


def implied_mean(p_over, line, r, *, low: float = 1e-4, high: float = 80.0, steps: int = 60) -> np.ndarray:
    """The mean whose distribution (shape `r`) gives `p_over` at `line`.

    Bisection, vectorised: the over chance rises monotonically with the mean.
    """
    p_over = np.asarray(p_over, dtype=float)
    lo = np.full(p_over.shape, low)
    hi = np.full(p_over.shape, high)
    for _ in range(steps):
        mid = (lo + hi) / 2.0
        above = over_probability(mid, r, line) > p_over
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return (lo + hi) / 2.0


# -- DraftKings points ------------------------------------------------------


def skater_expected_points(goals, assists, shots, blocks, *, r: Mapping[str, float]) -> dict[str, np.ndarray]:
    """Expected DraftKings points and the four bonus chances, per skater."""
    goals = np.asarray(goals, dtype=float)
    assists = np.asarray(assists, dtype=float)
    shots = np.maximum(np.asarray(shots, dtype=float), goals)
    blocks = np.asarray(blocks, dtype=float)
    points = goals + assists
    p_hat = tail(goals, r.get("goals", math.nan), 3)
    p_3pts = tail(points, r.get("points", math.nan), 3)
    p_5sog = tail(shots, r.get("shots_on_goal", math.nan), 5)
    p_3blk = tail(blocks, r.get("blocked_shots", math.nan), 3)
    s = DK_SKATER
    expected = (
        s["goal"] * goals
        + s["assist"] * assists
        + s["shot"] * shots
        + s["block"] * blocks
        + s["hat_trick"] * p_hat
        + s["three_points"] * p_3pts
        + s["five_shots"] * p_5sog
        + s["three_blocks"] * p_3blk
    )
    return {
        "dk": expected,
        "p_hat_trick": p_hat,
        "p_three_points": p_3pts,
        "p_five_shots": p_5sog,
        "p_three_blocks": p_3blk,
    }


def goalie_expected_points(saves, goals_against, win, ot_loss, *, saves_r: float = math.nan) -> dict[str, np.ndarray]:
    """Expected DraftKings points for a goalie who starts.

    A shutout is scored as no goal against in a win: P(GA = 0) under a Poisson
    on goals against, which is a win in every game but a 0-0 shootout loss.
    """
    saves = np.asarray(saves, dtype=float)
    ga = np.maximum(np.asarray(goals_against, dtype=float), 1e-9)
    win = np.asarray(win, dtype=float)
    ot_loss = np.asarray(ot_loss, dtype=float)
    p_shutout = np.exp(-ga)
    p_35 = tail(saves, saves_r, 35)
    g = DK_GOALIE
    expected = (
        g["win"] * win
        + g["save"] * saves
        + g["goal_against"] * ga
        + g["shutout"] * p_shutout
        + g["ot_loss"] * ot_loss
        + g["saves_35"] * p_35
    )
    return {"dk": expected, "p_shutout": p_shutout, "p_35_saves": p_35}


def _draw(rng: np.random.Generator, mean: np.ndarray, r: float, size: int) -> np.ndarray:
    mean = np.maximum(mean, 1e-9)[:, None]
    if math.isfinite(r) and r > 0:
        lam = rng.gamma(r, mean / r, size=(mean.shape[0], size))
        return rng.poisson(lam)
    return rng.poisson(np.broadcast_to(mean, (mean.shape[0], size)))


def skater_spread(goals, assists, shots, blocks, *, r: Mapping[str, float], draws: int = SIM_DRAWS, seed: int = 20261011) -> dict[str, np.ndarray]:
    """p10, p90 and standard deviation of each skater's DraftKings night."""
    rng = np.random.default_rng(seed)
    g = _draw(rng, np.asarray(goals, float), r.get("goals", math.nan), draws)
    a = _draw(rng, np.asarray(assists, float), r.get("assists", math.nan), draws)
    s = np.maximum(_draw(rng, np.asarray(shots, float), r.get("shots_on_goal", math.nan), draws), g)
    b = _draw(rng, np.asarray(blocks, float), r.get("blocked_shots", math.nan), draws)
    k = DK_SKATER
    dk = (
        k["goal"] * g + k["assist"] * a + k["shot"] * s + k["block"] * b
        + k["hat_trick"] * (g >= 3) + k["three_points"] * (g + a >= 3)
        + k["five_shots"] * (s >= 5) + k["three_blocks"] * (b >= 3)
    )
    return {
        "p10": np.percentile(dk, 10, axis=1),
        "p90": np.percentile(dk, 90, axis=1),
        "sd": dk.std(axis=1),
    }


def goalie_spread(saves, goals_against, win, ot_loss, *, saves_r: float = math.nan, draws: int = SIM_DRAWS, seed: int = 20261012) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    sv = _draw(rng, np.asarray(saves, float), saves_r, draws)
    ga = _draw(rng, np.asarray(goals_against, float), math.nan, draws)
    u = rng.random(sv.shape)
    win = np.asarray(win, float)[:, None]
    otl = np.asarray(ot_loss, float)[:, None]
    won = u < win
    lost_ot = (u >= win) & (u < win + otl)
    k = DK_GOALIE
    dk = (
        k["win"] * won + k["save"] * sv + k["goal_against"] * ga
        + k["shutout"] * (won & (ga == 0)) + k["ot_loss"] * lost_ot + k["saves_35"] * (sv >= 35)
    )
    return {"p10": np.percentile(dk, 10, axis=1), "p90": np.percentile(dk, 90, axis=1), "sd": dk.std(axis=1)}


def actual_skater_points(goals, assists, shots, blocks) -> np.ndarray:
    goals = np.asarray(goals, float)
    assists = np.asarray(assists, float)
    shots = np.asarray(shots, float)
    blocks = np.asarray(blocks, float)
    k = DK_SKATER
    return (
        k["goal"] * goals + k["assist"] * assists + k["shot"] * shots + k["block"] * blocks
        + k["hat_trick"] * (goals >= 3) + k["three_points"] * (goals + assists >= 3)
        + k["five_shots"] * (shots >= 5) + k["three_blocks"] * (blocks >= 3)
    )


def actual_goalie_points(saves, goals_against, won, lost_in_ot) -> np.ndarray:
    saves = np.asarray(saves, float)
    ga = np.asarray(goals_against, float)
    won = np.asarray(won, bool)
    lost_in_ot = np.asarray(lost_in_ot, bool)
    k = DK_GOALIE
    return (
        k["win"] * won + k["save"] * saves + k["goal_against"] * ga
        + k["shutout"] * (won & (ga == 0)) + k["ot_loss"] * lost_in_ot + k["saves_35"] * (saves >= 35)
    )


# -- the books' means -------------------------------------------------------


def devig(over_american: float, under_american: float) -> float | None:
    def implied(value: float) -> float | None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(v) or -100 < v < 100:
            return None
        return 100.0 / (v + 100.0) if v > 0 else -v / (-v + 100.0)

    o, u = implied(over_american), implied(under_american)
    if o is None or u is None or o + u <= 0:
        return None
    return o / (o + u)


def market_means(quotes: Iterable[tuple[object, str, float, float]], r: Mapping[str, float]) -> dict[tuple[object, str], tuple[float, int]]:
    """{(player id, market): (implied mean, books)} from de-vigged chances.

    `quotes` yields (player id, market, line, de-vigged over chance), one per
    book. Chances are averaged per line across books; each line inside
    `ANCHOR_BAND` implies a mean under the market's dispersion, and the means
    are averaged weighted by how many books quoted each line.
    """
    by_line: dict[tuple[object, str, float], list[float]] = {}
    for player_id, market, line, p in quotes:
        if market not in ANCHORABLE or p is None or not math.isfinite(p):
            continue
        by_line.setdefault((player_id, market, float(line)), []).append(float(p))
    keys = [k for k, ps in by_line.items() if ANCHOR_BAND[0] <= sum(ps) / len(ps) <= ANCHOR_BAND[1]]
    if not keys:
        return {}
    out: dict[tuple[object, str], list[tuple[float, int]]] = {}
    for market in {k[1] for k in keys}:
        mk = [k for k in keys if k[1] == market]
        p = np.array([sum(by_line[k]) / len(by_line[k]) for k in mk])
        lines = np.array([k[2] for k in mk])
        means = implied_mean(p, lines, r.get(market, math.nan))
        for k, m in zip(mk, means):
            out.setdefault((k[0], market), []).append((float(m), len(by_line[k])))
    return {
        key: (sum(m * n for m, n in vals) / sum(n for _, n in vals), sum(n for _, n in vals))
        for key, vals in out.items()
    }


def blend(model: Mapping[str, float], market: Mapping[str, float]) -> tuple[dict[str, float], dict[str, str]]:
    """The means a projection uses, and where each came from.

    The book's mean replaces the model's wherever there is one. Assists with
    no quote of their own come from a points quote less the goals mean.
    """
    means = dict(model)
    source = {stat: "model" for stat in model}
    for stat in ("goals", "assists", "shots_on_goal", "blocked_shots", GOALIE_STAT):
        if stat in market:
            means[stat] = market[stat]
            source[stat] = "market"
    if "assists" not in market and "points" in market and "goals" in means:
        means["assists"] = max(0.01, market["points"] - means["goals"])
        source["assists"] = "market (points less goals)"
    return means, source


# -- tonight's slate ----------------------------------------------------------


def _dispersion_r(model, stat: str) -> float:
    found = getattr(model, "dispersion", {}).get(stat)
    return _r_or_nan(getattr(found, "r", None)) if found is not None else math.nan


def staged_quotes(prices, model, games, *, team_names: Mapping[str, str] | None = None) -> list[tuple[int, str, float, float]]:
    """(player id, market, line, de-vigged over chance), one per book, for tonight.

    `games` is {(HOME, AWAY)} for the slate. A row whose game is not on it, or
    whose player does not resolve to one modelled player in that game, is
    left out rather than guessed.
    """
    from nhl_betting_lab.models.player_props import player_key
    from nhl_betting_lab.providers.team_names import resolve_team

    if prices is None or len(prices) == 0:
        return []
    lookup = dict(team_names or {})
    pairs: dict[tuple, dict[str, float]] = {}
    for row in prices.itertuples():
        market = str(getattr(row, "market", "")).strip()
        if market not in ANCHORABLE:
            continue
        selection = str(getattr(row, "selection", "")).strip().lower()
        if selection not in {"over", "under"}:
            continue
        try:
            line = float(getattr(row, "line", math.nan))
            price = float(getattr(row, "american_odds", math.nan))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(line) and math.isfinite(price)):
            continue
        home_label = str(getattr(row, "home_team", ""))
        away_label = str(getattr(row, "away_team", ""))
        home = resolve_team(home_label, lookup) if lookup else home_label
        away = resolve_team(away_label, lookup) if lookup else away_label
        if (home, away) not in games:
            continue
        player = str(getattr(row, "player", "") or "").strip()
        if not player:
            continue
        key = (home, away, player_key(player), market, line, str(getattr(row, "book", "")))
        pairs.setdefault(key, {"player": player})[selection] = price
    resolved: dict[tuple, int | None] = {}
    out: list[tuple[int, str, float, float]] = []
    for (home, away, pkey, market, line, _book), sides in pairs.items():
        if "over" not in sides or "under" not in sides:
            continue
        who = (home, away, pkey)
        if who not in resolved:
            resolved[who] = model.resolve_player_in_game(sides["player"], home=home, away=away)
        player_id = resolved[who]
        p = devig(sides["over"], sides["under"])
        if player_id is None or p is None:
            continue
        out.append((int(player_id), market, line, p))
    return out


def project_slate(
    model,
    team_model,
    games: Mapping[tuple[str, str], str],
    *,
    rosters: Mapping[int, str] | None = None,
    b2b: Mapping[str, bool] | None = None,
    quotes: Iterable[tuple[int, str, float, float]] = (),
) -> list[dict]:
    """One projection row per modelled player on tonight's slate.

    `games` maps (HOME, AWAY) to face-off. A player's side is his roster club
    where the roster has him, else the club he last played for, unless that
    club's roster is held and leaves him off (the card's rule in
    `card_pricing.price_props`, for the same reason: in October the logs point
    at the club a mover left).
    """
    rosters = dict(rosters or {})
    b2b = dict(b2b or {})
    rostered = {str(t).upper() for t in rosters.values()}
    side: dict[str, tuple[str, str, str]] = {}
    for (home, away), start in games.items():
        side[home] = (away, "home", start)
        side[away] = (home, "away", start)

    r = {stat: _dispersion_r(model, stat) for stat in SKATER_STATS}
    saves_r = _dispersion_r(model, GOALIE_STAT)
    anchors = market_means(quotes, {**r, GOALIE_STAT: saves_r})

    def team_of(player_id: int, logged: str) -> str:
        club = str(rosters.get(player_id, "") or "").upper()
        if club:
            return club
        logged = str(logged or "").upper()
        return "" if logged in rostered else logged

    skaters, goalies = [], []
    for player_id, rates in model.skaters.items():
        team = team_of(player_id, rates.team)
        if team in side:
            skaters.append((player_id, rates, team))
    for player_id, rates in model.goalies.items():
        team = team_of(player_id, rates.team)
        if team in side:
            goalies.append((player_id, rates, team))

    rows: list[dict] = []
    if skaters:
        cols: dict[str, list[float]] = {s: [] for s in SKATER_STATS}
        sources: list[dict[str, str]] = []
        books: list[int] = []
        for player_id, rates, team in skaters:
            opponent, venue, _ = side[team]
            own, opp = bool(b2b.get(team)), bool(b2b.get(opponent))
            model_means = {
                stat: float(model.expected_count(player_id, stat, opponent=opponent, venue=venue, own_b2b=own, opp_b2b=opp) or 0.0)
                for stat in SKATER_STATS
            }
            market = {stat: anchors[(player_id, stat)][0] for stat in SKATER_STATS if (player_id, stat) in anchors}
            means, source = blend(model_means, market)
            for stat in SKATER_STATS:
                cols[stat].append(means[stat])
            sources.append(source)
            books.append(max((anchors[(player_id, s)][1] for s in SKATER_STATS if (player_id, s) in anchors), default=0))
        arr = {s: np.array(v) for s, v in cols.items()}
        exp = skater_expected_points(arr["goals"], arr["assists"], arr["shots_on_goal"], arr["blocked_shots"], r=r)
        spread = skater_spread(arr["goals"], arr["assists"], arr["shots_on_goal"], arr["blocked_shots"], r=r)
        for i, (player_id, rates, team) in enumerate(skaters):
            opponent, venue, start = side[team]
            rows.append({
                "name": rates.player, "team": team, "opp": opponent, "venue": venue, "start": start,
                "pos": rates.group, "dk": round(float(exp["dk"][i]), 2),
                "p10": round(float(spread["p10"][i]), 1), "p90": round(float(spread["p90"][i]), 1),
                "sd": round(float(spread["sd"][i]), 2),
                "goals": round(float(arr["goals"][i]), 3), "assists": round(float(arr["assists"][i]), 3),
                "shots": round(float(arr["shots_on_goal"][i]), 3), "blocks": round(float(arr["blocked_shots"][i]), 3),
                "toiMin": round(rates.expected_toi_seconds / 60.0, 1),
                "bonus": {
                    "hatTrick": round(float(exp["p_hat_trick"][i]), 4),
                    "threePoints": round(float(exp["p_three_points"][i]), 4),
                    "fiveShots": round(float(exp["p_five_shots"][i]), 4),
                    "threeBlocks": round(float(exp["p_three_blocks"][i]), 4),
                },
                "source": "market" if any(v.startswith("market") for v in sources[i].values()) else "model",
                "marketStats": sorted(k for k, v in sources[i].items() if v.startswith("market") and k != "points"),
                "books": books[i],
            })
    if goalies:
        saves, ga, win, otl, src, nbooks = [], [], [], [], [], []
        for player_id, rates, team in goalies:
            opponent, venue, _ = side[team]
            own, opp = bool(b2b.get(team)), bool(b2b.get(opponent))
            model_saves = float(model.expected_saves(player_id, opponent=opponent, venue=venue, own_b2b=own, opp_b2b=opp) or 0.0)
            anchored = anchors.get((player_id, GOALIE_STAT))
            saves.append(anchored[0] if anchored else model_saves)
            src.append("market" if anchored else "model")
            nbooks.append(anchored[1] if anchored else 0)
            home, away = (team, opponent) if venue == "home" else (opponent, team)
            flags = {"home_b2b": bool(b2b.get(home)), "away_b2b": bool(b2b.get(away))}
            h_goals, a_goals = team_model.expected_goals(home, away, **flags)
            p_home, p_tie, p_away = team_model.regulation_probabilities(home, away, **flags)
            ml = team_model.moneyline_probabilities(home, away, **flags)
            win.append(ml["home" if venue == "home" else "away"])
            otl.append(p_tie / 2.0)
            ga.append(a_goals if venue == "home" else h_goals)
        exp = goalie_expected_points(saves, ga, win, otl, saves_r=saves_r)
        spread = goalie_spread(np.array(saves), np.array(ga), np.array(win), np.array(otl), saves_r=saves_r)
        for i, (player_id, rates, team) in enumerate(goalies):
            opponent, venue, start = side[team]
            rows.append({
                "name": rates.player, "team": team, "opp": opponent, "venue": venue, "start": start,
                "pos": "G", "dk": round(float(exp["dk"][i]), 2),
                "p10": round(float(spread["p10"][i]), 1), "p90": round(float(spread["p90"][i]), 1),
                "sd": round(float(spread["sd"][i]), 2),
                "saves": round(float(saves[i]), 2), "goalsAgainst": round(float(ga[i]), 2),
                "win": round(float(win[i]), 4), "otLoss": round(float(otl[i]), 4),
                "bonus": {"shutout": round(float(exp["p_shutout"][i]), 4), "saves35": round(float(exp["p_35_saves"][i]), 4)},
                "ifStarts": True, "source": src[i],
                "marketStats": [GOALIE_STAT] if src[i] == "market" else [], "books": nbooks[i],
            })
    rows.sort(key=lambda row: (-row["dk"], row["name"]))
    return rows
