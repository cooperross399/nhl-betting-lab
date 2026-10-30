"""Each voted award's model, fitted to how the voters actually voted.

The award models in :mod:`season_sim.awards` rate a field on a handful of
numbers (final points against the leader's, a playoff berth, ice time, the
5v5 chances a defender allows, wins, goals saved above expected...). Their
weights started as judgement. Here they are fitted to the real ballots:
``data/season_sim/award_voting.csv`` holds every vote-getter's points for the
Hart (2008-09 on), Norris (2017-18 on), Selke (six seasons with full
ballots), Vezina (2012-13 on) and Calder (2014-15 on), as published by
Hockey-Reference and the NHL's award releases. Each season's field is rebuilt
from that season's NHL and MoneyPuck stats (:func:`season_sim.fetch.fetch_history`),
the same features the live model reads are computed on it, and the weights
are the ones that make each candidate's softmax share closest to his share of
the vote points:

    maximise  sum over seasons, candidates  v_i log softmax(X b)_i
              - RIDGE x |b - b0|^2

``b0`` is the old hand-set model, so a season or two of ballots can only nudge
it. The fit is checked one season held out at a time; the fitted weights are
used only when they predict the held-out seasons' ballots better than the old
ones did, and otherwise the old ones stay. Both the result and the check are
published, so the page can say which model it ran.

Goalies' Hart votes and Calder votes are left out of those two fits (the
Hart and Calder models rate skaters; goalies reach those rankings through
the odds and polls).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

#: The features each award model reads, in order.
FEATURES = {
    "hart": ("points_vs_leader", "playoffs", "games", "defenseman"),
    "norris": ("points_pg", "toi", "defence", "games"),
    "selke": ("defence", "faceoffs", "pk", "puck", "points_pg", "games"),
    "vezina": ("wins", "gsax", "sv", "games"),
    "calder": ("points_vs_leader", "defenseman", "games"),
}
#: Plain-English names for the page.
FEATURE_LABELS = {
    "points_vs_leader": "points against the leader's", "playoffs": "club makes the playoffs",
    "games": "share of games played", "defenseman": "plays defence", "points_pg": "points a game",
    "toi": "ice time", "defence": "5v5 chances allowed against his teammates", "faceoffs": "faceoffs",
    "pk": "penalty-kill time", "puck": "takeaways less giveaways", "wins": "wins",
    "gsax": "goals saved above expected", "sv": "save percentage",
}
#: The hand-set models these fits start from (and fall back to): softmax
#: weights, i.e. the old composite weights times their temperature (2.2), the
#: old Hart and Calder power of six on points against the leader, and the old
#: Hart playoff factor 0.25 + 0.75 x berth, which is log 4 on a berth.
TEMP = 2.2
DEFAULTS = {
    "hart": (6.0, math.log(4.0), 0.0, 0.0),
    "norris": (TEMP * 0.5, TEMP * 0.2, TEMP * 0.3, 0.0),
    "selke": (TEMP * 0.3, TEMP * 0.2, TEMP * 0.15, TEMP * 0.1, TEMP * 0.25, 0.0),
    "vezina": (TEMP * 0.35, TEMP * 0.45, TEMP * 0.2, 0.0),
    "calder": (6.0, 0.0, 0.0),
}
#: How hard the fit is pulled toward the old weights.
RIDGE = 0.05
#: The share of games played is floored here before its log is taken, so a
#: player who barely played is penalised but not sent to minus infinity.
GAMES_FLOOR = 0.1
#: The fields each history season is rebuilt with (the live model's pools).
POOL = {"hart": 60, "norris": 40, "selke": 80, "calder": 25}
VEZINA_MIN_SHARE = 0.4
MIN_GP = 20
VOTING = Path(__file__).resolve().parents[2] / "data" / "season_sim" / "award_voting.csv"


def name_key(name: str) -> str:
    from .awards import name_key as nk
    return nk(name)


def load_voting(path: Path = VOTING) -> dict[str, dict[str, list[dict]]]:
    """{award: {season: [{player, team, pos, votes}]}} from the ballots file."""
    out: dict[str, dict[str, list[dict]]] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["award"], {}).setdefault(r["season"], []).append(
                dict(player=r["player"], team=r["team"], pos=r["pos"], votes=int(r["votes"])))
    return out


# ----------------------------------------------------------------------
# features, shared by the fit and the simulated awards
# ----------------------------------------------------------------------
def _z(x: np.ndarray) -> np.ndarray:
    """z-scores across the field (the last axis); NaN, a stat not known, counts as average."""
    x = np.asarray(x, dtype=float)
    have = ~np.isnan(x)
    n = np.maximum(have.sum(axis=-1, keepdims=True), 1)
    mean = np.where(have, x, 0.0).sum(axis=-1, keepdims=True) / n
    var = np.where(have, (x - mean) ** 2, 0.0).sum(axis=-1, keepdims=True) / n
    sd = np.sqrt(var)
    z = np.where(sd > 0, (x - mean) / np.where(sd > 0, sd, 1.0), 0.0)
    return np.where(have, z, 0.0)


def design(award: str, cols: dict) -> np.ndarray:
    """The feature array (seasons x candidates x features) for one award.

    ``cols`` holds arrays over candidates, either one value each (a stat that
    does not change season to season) or seasons x candidates (simulated
    final points, wins or berths). Keys: ``points`` (season total),
    ``games`` (share of games played), ``berth``, ``d`` (1 for a
    defenseman), and the stats ``toi``, ``defence``, ``faceoffs``, ``pk``,
    ``puck``, ``wins``, ``gsax``, ``sv``, ``points_pg``.
    """
    def arr(k: str) -> np.ndarray:
        a = np.asarray(cols[k], dtype=float)
        return a[None, :] if a.ndim == 1 else a

    shapes = [arr(k).shape for k in cols]
    S = max(s[0] for s in shapes)
    P = shapes[0][1]
    feats = []
    for f in FEATURES[award]:
        if f == "points_vs_leader":
            pts = np.maximum(arr("points"), 0.5)
            v = np.log(pts / pts.max(axis=-1, keepdims=True))
        elif f == "playoffs":
            v = arr("berth")
        elif f == "games":
            v = np.log(np.clip(arr("games"), GAMES_FLOOR, 1.0))
        elif f == "defenseman":
            v = arr("d")
        else:
            v = _z(arr(f))
        feats.append(np.broadcast_to(v, (S, P)))
    return np.stack(feats, axis=-1)


def shares(X: np.ndarray, beta) -> np.ndarray:
    """Each candidate's softmax share in every season (seasons x candidates)."""
    s = X @ np.asarray(beta, dtype=float)
    s = s - s.max(axis=-1, keepdims=True)
    e = np.exp(s)
    return e / e.sum(axis=-1, keepdims=True)


# ----------------------------------------------------------------------
# the fit
# ----------------------------------------------------------------------
def _loss(beta: np.ndarray, data: list[tuple[np.ndarray, np.ndarray]], b0: np.ndarray, ridge: float):
    total, grad = 0.0, np.zeros_like(beta)
    for X, v in data:
        X2 = X[0]
        s = X2 @ beta
        s = s - s.max()
        p = np.exp(s); p /= p.sum()
        total -= float(v @ np.log(np.maximum(p, 1e-300)))
        grad -= X2.T @ (v - p)
    total += ridge * float(((beta - b0) ** 2).sum())
    grad += 2 * ridge * (beta - b0)
    return total, grad


def fit_beta(data: list[tuple[np.ndarray, np.ndarray]], b0, ridge: float = RIDGE) -> np.ndarray:
    from scipy.optimize import minimize

    b0 = np.asarray(b0, dtype=float)
    res = minimize(_loss, b0.copy(), args=(data, b0, ridge), jac=True, method="L-BFGS-B")
    return np.asarray(res.x, dtype=float)


def _score(beta, X: np.ndarray, v: np.ndarray) -> tuple[float, bool]:
    p = shares(X, beta)[0]
    return float(-(v @ np.log(np.maximum(p, 1e-300)))), bool(int(np.argmax(p)) == int(np.argmax(v)))


def fit_award(award: str, data: dict[str, tuple[np.ndarray, np.ndarray]]) -> dict:
    """Fit one award on ``{season: (X, vote shares)}`` and check it one season held out at a time."""
    b0 = np.asarray(DEFAULTS[award], dtype=float)
    seasons = sorted(data)
    out = dict(features=list(FEATURES[award]), default=[round(float(b), 4) for b in b0], seasons=len(seasons),
               firstSeason=seasons[0] if seasons else None, lastSeason=seasons[-1] if seasons else None)
    if len(seasons) < 2:
        out.update(used="default", reason=f"{len(seasons)} season(s) of ballots")
        return out
    held = dict(fit_ll=0.0, default_ll=0.0, fit_hits=0, default_hits=0)
    for s in seasons:
        beta = fit_beta([data[t] for t in seasons if t != s], b0)
        ll, hit = _score(beta, *data[s])
        dll, dhit = _score(b0, *data[s])
        held["fit_ll"] += ll; held["default_ll"] += dll
        held["fit_hits"] += hit; held["default_hits"] += dhit
    beta = fit_beta([data[t] for t in seasons], b0)
    better = held["fit_ll"] < held["default_ll"]
    out.update(
        beta=[round(float(b), 4) for b in beta],
        used="fitted" if better else "default",
        heldOut=dict(fittedLoss=round(held["fit_ll"] / len(seasons), 4),
                     defaultLoss=round(held["default_ll"] / len(seasons), 4),
                     fittedWinners=held["fit_hits"], defaultWinners=held["default_hits"]),
    )
    if not better:
        out["reason"] = "the fitted weights did not predict held-out ballots better"
    return out


def params(report: dict | None) -> dict[str, tuple[float, ...]]:
    """The weights each award model runs on: fitted where the fit won, else the old ones."""
    out = {a: tuple(DEFAULTS[a]) for a in FEATURES}
    for a, r in (report or {}).items():
        if a in out and r.get("used") == "fitted" and r.get("beta"):
            out[a] = tuple(float(b) for b in r["beta"])
    return out


# ----------------------------------------------------------------------
# rebuilding each season's field from its stats
# ----------------------------------------------------------------------
def _f(x, default=float("nan")) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _match(rows: list[dict], name: str, team: str | None, pos: str | None) -> dict | None:
    """The stats row for a ballot name: name first, then team, then position."""
    k = name_key(name)
    hits = [r for r in rows if r["key"] == k]
    if len(hits) > 1 and team and team != "TOT":
        by_team = [r for r in hits if team in r["teams"]]
        hits = by_team or hits
    if len(hits) > 1 and pos:
        want_d = pos.startswith("D")
        hits = [r for r in hits if (r["pos"] == "D") == want_d] or hits
    return hits[0] if len(hits) == 1 else None


def _rookie(is_rookie_fn, prior_gp: list[int], born: str | None, season: str) -> bool:
    """Calder eligibility; with no birth date, the games rule alone."""
    got = is_rookie_fn(prior_gp, born, season)
    if got is not None:
        return bool(got)
    from .model import CALDER_MAX_SEASON_GP, CALDER_TWO_SEASON_GP
    return all(gp <= CALDER_MAX_SEASON_GP for gp in prior_gp) and sum(gp >= CALDER_TWO_SEASON_GP for gp in prior_gp) < 2


def season_fields(hist: dict, award_stats_fn, is_rookie_fn) -> dict:
    """Each award's candidate rows for one history season.

    ``hist`` is one season of :func:`season_sim.fetch.fetch_history`.
    Returns ``{award: [row]}`` where a row carries the ``cols`` values of
    :func:`design` for one candidate plus his ``key`` and ``teams``.
    """
    season = hist["season"]
    games = float(hist.get("games") or 82)
    berth = hist.get("berths") or {}
    skaters = [q for q in hist["skaters"] if q.get("gamesPlayed")]
    stats = award_stats_fn(dict(season=season, skaters={season: hist["skaters"]},
                                moneypuck={season: hist.get("moneypuck") or {}})) if hist.get("moneypuck") else {}
    born = hist.get("born") or {}
    prior_gp = hist.get("prior_gp") or {}
    rows = []
    for q in skaters:
        teams = [t.strip() for t in str(q.get("teamAbbrevs") or "").split(",") if t.strip()]
        st = stats.get(q["playerId"]) or {}
        gp = _f(q.get("gamesPlayed"), 0.0)
        rows.append(dict(
            key=name_key(q.get("skaterFullName") or ""), teams=teams, pos="D" if q.get("positionCode") == "D" else "F",
            id=q["playerId"], points=_f(q.get("points"), 0.0), games=min(gp / games, 1.0),
            berth=float(any(berth.get(t) for t in teams[-1:])), d=float(q.get("positionCode") == "D"),
            toi=_f(q.get("timeOnIcePerGame")) / 60.0, points_pg=_f(q.get("points"), 0.0) / max(gp, 1.0),
            defence=_f(st.get("defence")), faceoffs=_f(st.get("faceoffs")), pk=_f(st.get("pk")), puck=_f(st.get("puck")),
            gp=gp, rookie=_rookie(is_rookie_fn, prior_gp.get(q["playerId"], []), born.get(q["playerId"]), season),
        ))
    by_pts = sorted(rows, key=lambda r: -r["points"])
    out = {
        "hart": by_pts[:POOL["hart"]],
        "norris": [r for r in by_pts if r["pos"] == "D" and r["gp"] >= MIN_GP and (r["toi"] or 0) >= 17.0][:POOL["norris"]],
        "selke": [r for r in by_pts if r["pos"] == "F" and r["gp"] >= MIN_GP and (r["toi"] or 0) >= 14.0][:POOL["selke"]],
        "calder": [r for r in by_pts if r["rookie"] and r["gp"] >= 1][:POOL["calder"]],
        "_all": rows,
    }
    if not stats:
        out.pop("norris"); out.pop("selke")
    goalies = []
    mp_g = hist.get("goalie_mp") or {}
    for g in hist.get("goalies") or []:
        gs = _f(g.get("gamesStarted"), 0.0)
        teams = [t.strip() for t in str(g.get("teamAbbrevs") or "").split(",") if t.strip()]
        m = mp_g.get(g["playerId"])
        gsax = ((m["xGoals"] - m["goals"]) / m["icetime"] * 3600.0) if m and m["icetime"] > 0 else float("nan")
        goalies.append(dict(key=name_key(g.get("goalieFullName") or ""), teams=teams, pos="G", id=g["playerId"],
                            wins=_f(g.get("wins"), 0.0), sv=_f(g.get("savePct")), gsax=gsax,
                            games=min(gs / games, 1.0), gs=gs))
    if mp_g:
        out["vezina"] = [g for g in goalies if g["games"] >= VEZINA_MIN_SHARE]
        out["_goalies"] = goalies
    return out


def fit_data(award: str, ballots: list[dict], fields: dict) -> tuple[tuple[np.ndarray, np.ndarray] | None, int]:
    """(X, vote shares) for one award in one season, and how many ballot names did not match."""
    pool = list(fields.get(award) or [])
    if len(pool) < 2:
        return None, 0
    everyone = fields["_goalies"] if award == "vezina" else fields["_all"]
    seen = {id(r) for r in pool}
    votes: dict[int, float] = {}
    missed = 0
    for b in ballots:
        if award in ("hart", "calder") and b["pos"] == "G":
            continue
        r = _match(everyone, b["player"], b["team"], b["pos"])
        if r is None:
            missed += 1
            continue
        if id(r) not in seen:
            pool.append(r); seen.add(id(r))
        votes[id(r)] = votes.get(id(r), 0.0) + b["votes"]
    tot = sum(votes.values())
    if tot <= 0:
        return None, missed
    cols = {k: [r.get(k, float("nan")) for r in pool] for k in
            ("points", "games", "berth", "d", "toi", "defence", "faceoffs", "pk", "puck", "wins", "gsax", "sv", "points_pg")
            if any(k in r for r in pool)}
    v = np.array([votes.get(id(r), 0.0) / tot for r in pool])
    return (design(award, cols), v), missed


def fit_all(voting: dict, history: dict[str, dict], award_stats_fn, is_rookie_fn) -> dict:
    """Every award's fit report from the ballots and the rebuilt seasons."""
    fields = {s: season_fields(h, award_stats_fn, is_rookie_fn) for s, h in history.items()}
    report = {}
    for award in FEATURES:
        data, missed, ballots = {}, 0, 0
        for season, rows in (voting.get(award) or {}).items():
            if season not in fields:
                continue
            got, miss = fit_data(award, rows, fields[season])
            ballots += len(rows); missed += miss
            if got is not None:
                data[season] = got
        r = fit_award(award, data)
        r["ballotNamesUnmatched"] = missed
        r["ballotNames"] = ballots
        report[award] = r
    return report
