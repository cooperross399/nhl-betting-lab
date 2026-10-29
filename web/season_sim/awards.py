"""Trackers for the voted awards: the Hart, the Norris and the Selke.

These trophies are voted by the PHWA, so no simulation can count them. Each
tracker instead reads three signals and shows them side by side:

* **market**: the award odds published by every book and prediction market on
  file, as hand-kept in ``data/season_sim/award_inputs.json``. Each source is
  turned into probabilities with its own margin taken out (each implied
  probability divided by their sum over that source's listed field), and the
  sources are averaged into one consensus, a player a source does not list
  counting zero in it. A source older than :data:`STALE_DAYS` sits out the
  consensus while a fresher one exists;
* **poll**: the latest media poll's points for each player over the poll's
  total (a winner-only poll counts each vote as a point);
* **model**: what the season so far says, from :func:`award_stats` (NHL
  season-to-date stats, MoneyPuck's on-ice and faceoff tables, and the card's
  shift-chart defence ratings). Each stat is this season's per-game rate
  blended with last season's by games played (``gp / (gp + PRIOR_GAMES)``),
  so ten games in a hot start counts but does not yet decide. Hart: the
  player's points (the sim's season projection blended with his scoring pace)
  raised to the sixth power, times 0.25 + 0.75 x his club's playoff odds.
  Norris and Selke: a weighted sum of z-scores across the position
  (:data:`NORRIS_PARTS`, :data:`SELKE_PARTS`), turned into shares with
  ``exp(TEMPERATURE x score)``. Without those stats (an old build) the model
  falls back to projected points, and the Selke has none.

When the season simulation's arrays reach the build, the **model** signal is
the award simulated instead (:func:`simulated_shares`): in every simulated
season each candidate's final points (and, for a goalie, wins) are drawn, the
award's own model rates the field on those final numbers, and his chance is
the mean over seasons of his share of that season's vote. The Vezina and the
voted Calder have only this model. Then :data:`SIM_WEIGHTS` replaces
:data:`WEIGHTS`, because the simulated model already carries the rest of the
season, which the stats model could not.

The tracker share, one ranking per award, is the weighted mean of the signals
that exist, with the weights renormalised over them; a player missing from a signal counts
as zero in it. It is a projection of the vote, not a forecast of it, and the
page says so. Nothing here reads a sportsbook, spends a credit or places a bet.
"""
from __future__ import annotations

import json
import math

import numpy as np
import unicodedata
from datetime import date
from pathlib import Path

#: How much each signal counts in the tracker share (renormalised over the
#: signals an award has). The book is the most informed, the poll is what the
#: voters themselves say, the model is a points projection voters only partly
#: follow. Chosen, not fitted: three seasons of trackers is too few to fit.
WEIGHTS = {"market": 0.5, "poll": 0.3, "model": 0.2}
#: The weights when the model is the simulated award. Chosen, not fitted.
SIM_WEIGHTS = {"market": 0.45, "poll": 0.2, "model": 0.35}
#: Candidates the simulation rates per award (the top of each field by
#: projected points; every starting goalie for the Vezina).
SIM_POOL = {"hart": 60, "norris": 40, "selke": 80, "calder": 25}
#: A goalie rated for the Vezina has at least this share of his club's starts
#: (a tandem's two halves both qualify).
VEZINA_MIN_SHARE = 0.4
#: The Vezina composite: simulated wins, goals saved above expected per 60,
#: and save percentage (this season blended with his three-year rate).
VEZINA_PARTS = {"wins": 0.35, "gsax": 0.45, "sv": 0.2}
#: Starts of the three-year save percentage a goalie's season-to-date rate is
#: blended with.
SV_PRIOR_STARTS = 20
#: Projected points are raised to this power so the model signal is as
#: top-heavy as a real vote (the leader is far likelier than the tenth man).
MODEL_POWER = 6
#: Games of last season's rate a player's season-to-date rate is blended with.
PRIOR_GAMES = 15
#: The Norris and Selke composites: z-scores across the position, weighted.
#: Chosen, not fitted, to read like the vote: the Norris goes to a scoring
#: defenseman who plays big minutes and is not beaten at 5v5; the Selke to a
#: centre who wins draws, kills penalties, suppresses chances and still scores.
NORRIS_PARTS = {"points": 0.5, "toi": 0.2, "defence": 0.3}
SELKE_PARTS = {"defence": 0.3, "faceoffs": 0.2, "pk": 0.15, "puck": 0.1, "points": 0.25}
#: How top-heavy the composite shares are: exp(TEMPERATURE x score).
TEMPERATURE = 2.2
#: Fewest games played this season (or last, early on) to be rated at all.
MIN_GAMES = 5
#: Model leaders added to a field the books and polls have not priced.
MODEL_ADDS = 3
#: An input older than this is flagged stale on the page.
STALE_DAYS = 14
#: Rows published per award.
ROWS = 10

AWARDS = ("hart", "norris", "selke", "vezina", "calder")
LABELS = {"hart": "Hart Trophy", "norris": "Norris Trophy", "selke": "Selke Trophy",
          "vezina": "Vezina Trophy", "calder": "Calder Trophy"}
SIM_NOTES = {
    "hart": "Sim: in each simulated season, final points over the leader's, to the sixth power, times 0.25 + 0.75 if his club makes the playoffs that season.",
    "norris": "Sim: in each simulated season, final points a game 50%, ice time 20%, 5v5 chances allowed against his teammates 30%.",
    "selke": "Sim: in each simulated season, 5v5 chances allowed against his teammates 30%, final points a game 25%, faceoffs 20%, penalty kill time 15%, takeaways less giveaways 10%.",
    "vezina": "Sim: in each simulated season, final wins 35%, goals saved above expected per 60 45%, save percentage 20%, among goalies with two fifths of their club's starts.",
    "calder": "Sim: in each simulated season, a rookie's final points over the rookie leader's, to the sixth power.",
}
FALLBACK_VEZINA = "No model signal: the simulation did not reach this build, so this tracker is the odds and the poll."
FALLBACK_CALDER = FALLBACK_VEZINA
MODEL_NOTES = {
    "hart": "Model: this season's points (pace blended with the projection), to the sixth power, times 0.25 + 0.75 x the club's playoff odds.",
    "norris": "Model: points 50%, ice time 20%, 5v5 chances allowed against his teammates 30%, this season blended with last.",
    "selke": "Model: 5v5 chances allowed against his teammates 30%, points 25%, faceoffs 20%, penalty kill time 15%, takeaways less giveaways 10%.",
    "vezina": FALLBACK_VEZINA,
    "calder": FALLBACK_CALDER,
}
#: Notes for a build that has no season-to-date stats (the old projection).
FALLBACK_NOTES = {
    "hart": "Model: projected points to the sixth power, times 0.25 + 0.75 x the club's playoff odds.",
    "norris": "Model: a defenseman's projected points to the sixth power.",
    "selke": "No model signal: no defensive stats reached this build, so this tracker is the odds and the poll.",
    "vezina": "No model signal: the simulation did not reach this build, so this tracker is the odds and the poll.",
    "calder": "No model signal: the simulation did not reach this build, so this tracker is the odds and the poll.",
}


def name_key(name: str) -> str:
    """Accent-free lower-case name, so 'Pastrňák' meets 'Pastrnak'."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace(".", " ").replace("-", " ").split())


def implied(american: float) -> float:
    """The probability an American price implies, margin still in."""
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def load_inputs(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _age_days(when: str | None, today: date) -> int | None:
    if not when:
        return None
    try:
        return (today - date.fromisoformat(when)).days
    except ValueError:
        return None


def _line_prob(x: dict) -> float | None:
    """A line's probability, margin still in: an American price, or a
    prediction market's printed chance in percent."""
    if x.get("american") is not None:
        return implied(x["american"])
    if x.get("chance") is not None:
        return float(x["chance"]) / 100.0
    return None


def _market(block: dict | None) -> dict[str, float]:
    lines = (block or {}).get("lines") or []
    raw = {name_key(x["name"]): p for x in lines if (p := _line_prob(x)) is not None}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else {}


def odds_blocks(spec: dict) -> list[dict]:
    """An award's odds sources: ``odds`` is one block or a list of them."""
    odds = spec.get("odds")
    if not odds:
        return []
    return [b for b in (odds if isinstance(odds, list) else [odds]) if b]


def _in_consensus(blocks: list[dict], today: date) -> list[bool]:
    """Which sources the consensus averages: every fresh one, or all of them
    when none is fresh (an old price beats no price, and the page flags it)."""
    fresh = [(a := _age_days(b.get("date"), today)) is not None and a <= STALE_DAYS for b in blocks]
    return fresh if any(fresh) else [True] * len(blocks)


def _consensus(blocks: list[dict]) -> dict[str, float]:
    """The mean of each source's margin-free shares, renormalised."""
    shares = [m for m in (_market(b) for b in blocks) if m]
    if not shares:
        return {}
    keys = {k for m in shares for k in m}
    mean = {k: sum(m.get(k, 0.0) for m in shares) / len(shares) for k in keys}
    total = sum(mean.values())
    return {k: v / total for k, v in mean.items()} if total > 0 else {}


def _poll(block: dict | None) -> tuple[dict[str, float], dict[str, int], dict[str, float]]:
    entries = (block or {}).get("entries") or []
    pts = {name_key(e["name"]): float(e.get("points") or 0) for e in entries}
    total = sum(pts.values())
    share = {k: v / total for k, v in pts.items()} if total > 0 else {}
    ordered = sorted(pts.values(), reverse=True)
    rank = {k: 1 + ordered.index(v) for k, v in pts.items()}
    return share, rank, pts


def _blend(now: float | None, gp_now: float, prior: float | None) -> float | None:
    """This season's per-game rate, leaning on last season's until games pile up."""
    if now is None and prior is None:
        return None
    if prior is None:
        return now
    if now is None or gp_now <= 0:
        return prior
    w = gp_now / (gp_now + PRIOR_GAMES)
    return w * now + (1 - w) * prior


def _z(values: dict[str, float]) -> dict[str, float]:
    if len(values) < 2:
        return {k: 0.0 for k in values}
    mean = sum(values.values()) / len(values)
    sd = (sum((v - mean) ** 2 for v in values.values()) / len(values)) ** 0.5
    return {k: ((v - mean) / sd if sd > 0 else 0.0) for k, v in values.items()}


def _composite(pool: list[dict], parts: dict[str, float]) -> dict[str, float]:
    """Shares from a weighted z-score sum; a missing stat counts as average."""
    if not pool:
        return {}
    keys = [name_key(p["name"]) for p in pool]
    score = {k: 0.0 for k in keys}
    for part, weight in parts.items():
        have = {k: float(p["stats"][part]) for k, p in zip(keys, pool) if p["stats"].get(part) is not None}
        for k, z in _z(have).items():
            score[k] += weight * z
    raw = {k: math.exp(TEMPERATURE * v) for k, v in score.items()}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def _model(award: str, players: list[dict], playoff: dict[str, float]) -> dict[str, float]:
    if award not in ("hart", "norris", "selke"):
        return {}
    rated = [p for p in players if p.get("stats") and p["stats"].get("gp", 0) >= MIN_GAMES]
    if award == "selke":
        pool = [p for p in rated if p.get("pos") in ("C", "L", "R") and p["stats"].get("toi", 0) >= 14.0]
        return _composite(pool, SELKE_PARTS)
    if award == "norris" and rated:
        pool = [p for p in rated if p.get("pos") == "D" and p["stats"].get("toi", 0) >= 17.0]
        return _composite(pool, NORRIS_PARTS)
    pool = [p for p in players if p.get("pos") != "G" and (award != "norris" or p.get("pos") == "D")]
    if not pool:
        return {}

    def points(p: dict) -> float:
        st = p.get("stats") or {}
        if award == "hart" and st.get("points") is not None and st.get("gp", 0) > 0:
            # The season projection, pulled toward his pace by games played.
            w = st["gp_now"] / (st["gp_now"] + 20) if st.get("gp_now") else 0.0
            return (1 - w) * p["p"] + w * st["points"] * 82
        return p["p"]

    top = max(points(p) for p in pool) or 1.0
    raw = {}
    for p in pool:
        w = (max(points(p), 0.0) / top) ** MODEL_POWER
        if award == "hart":
            w *= 0.25 + 0.75 * playoff.get(p["team"], 0.0)
        k = name_key(p["name"])
        raw[k] = max(raw.get(k, 0.0), w)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else {}


def _f(row: dict | None, key: str) -> float:
    try:
        return float((row or {}).get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def award_stats(bundle: dict, *, defence: dict[str, float] | None = None) -> dict[int, dict]:
    """Per-game award stats for every skater, keyed by NHL id.

    ``bundle`` is :func:`season_sim.fetch.fetch_bundle`'s. Rates are this
    season's blended with last season's (:func:`_blend`): points, ice time a
    game, faceoffs won less lost a game, penalty-kill minutes a game,
    takeaways less giveaways a game, and ``defence``, the goals a game a
    player prevents at 5v5 against his teammates. ``defence`` comes from the
    card's shift-chart ratings (``skater_defence``) when given; otherwise
    from MoneyPuck's 5v5 on- and off-ice expected goals against.
    """
    from .model import _read_csv  # local: keeps this module light for the page tests

    season = bundle["season"]
    years = [season, *[s for s in bundle["skaters"] if s != season]]
    prior = years[1] if len(years) > 1 else None
    nhl = {s: {q["playerId"]: q for q in bundle["skaters"].get(s, [])} for s in (season, prior) if s}
    mp: dict[str, dict[tuple[int, str], dict]] = {}
    mp_team: dict[str, dict[tuple[str, str], dict]] = {}
    for s in (season, prior):
        files = (bundle.get("moneypuck") or {}).get(s) or {}
        mp[s] = {(int(r["playerId"]), r["situation"]): r for r in _read_csv(files.get("skaters"))}
        mp_team[s] = {(r["team"], r["situation"]): r for r in _read_csv(files.get("teams"))}

    def rates(s: str | None, pid: int) -> tuple[float, dict]:
        q = nhl.get(s, {}).get(pid) if s else None
        gp = float((q or {}).get("gamesPlayed") or 0)
        if gp <= 0:
            return 0.0, {}
        m_all = mp.get(s, {}).get((pid, "all"))
        m_pk = mp.get(s, {}).get((pid, "4on5"))
        m_ev = mp.get(s, {}).get((pid, "5on5"))
        out = dict(points=float(q.get("points") or 0) / gp, toi=float(q.get("timeOnIcePerGame") or 0) / 60.0)
        if m_all:
            mgp = _f(m_all, "games_played") or gp
            out["faceoffs"] = (_f(m_all, "faceoffsWon") - _f(m_all, "faceoffsLost")) / mgp
            out["puck"] = (_f(m_all, "I_F_takeaways") - _f(m_all, "I_F_giveaways")) / mgp
            out["pk"] = _f(m_pk, "icetime") / 60.0 / mgp if m_pk else 0.0
        if m_ev and _f(m_ev, "icetime") >= 1800:
            it = _f(m_ev, "icetime")
            team = mp_team.get(s, {}).get((m_ev.get("team"), "5on5"))
            if team and _f(team, "games_played") > 0:
                team_it = _f(team, "iceTime") * _f(m_ev, "games_played") / _f(team, "games_played")
                off_it = max(team_it - it, 3600.0)
                rel = _f(m_ev, "OnIce_A_xGoals") / it - _f(m_ev, "OffIce_A_xGoals") / off_it
                out["defence"] = -rel * it / max(_f(m_ev, "games_played"), 1.0)
        return gp, out

    stats: dict[int, dict] = {}
    for pid in set(nhl.get(season, {})) | set(nhl.get(prior, {}) if prior else {}):
        gp_now, now = rates(season, pid)
        gp_prior, before = rates(prior, pid)
        row: dict = dict(gp=max(gp_now, gp_prior if gp_now < MIN_GAMES else 0), gp_now=gp_now)
        for key in ("points", "toi", "faceoffs", "pk", "puck", "defence"):
            row[key] = _blend(now.get(key), gp_now, before.get(key))
        if defence and str(pid) in defence:
            row["defence"] = float(defence[str(pid)])
        stats[pid] = row
    return stats


def _source(block: dict | None, kind: str, today: date, used: bool | None = None) -> dict | None:
    if not block:
        return None
    age = _age_days(block.get("date"), today)
    out = dict(kind=kind, date=block.get("date"), url=block.get("url"), ageDays=age,
               stale=age is None or age > STALE_DAYS)
    if kind == "odds":
        out.update(book=block.get("book"), source=block.get("source"))
        if used is not None:
            out["used"] = used
    else:
        out.update(outlet=block.get("outlet"), voters=block.get("voters"), scoring=block.get("scoring"))
    return out


def tracker(award: str, inputs: dict, players: list[dict], playoff: dict[str, float], *, today: date,
            sim: dict | None = None) -> dict:
    """One award's tracker: rows, the sources with their age, the weights used."""
    spec = inputs.get(award) or {}
    blocks, poll_block = odds_blocks(spec), spec.get("poll")
    used = _in_consensus(blocks, today)
    counted = [b for b, u in zip(blocks, used) if u]
    market = _consensus(counted)
    poll, poll_rank, poll_pts = _poll(poll_block)
    simulated = (sim or {}).get(award) or {}
    model = dict(simulated.get("share") or {}) or _model(award, players, playoff)
    base = SIM_WEIGHTS if simulated.get("share") else WEIGHTS
    have = {"market": bool(market), "poll": bool(poll), "model": bool(model)}
    wsum = sum(base[k] for k, on in have.items() if on)
    weights = {k: (round(base[k] / wsum, 4) if on and wsum else 0.0) for k, on in have.items()}

    # The candidates are the people a book or a poll names; the model only
    # re-weights them, so a points leader no one has priced is not invented
    # into the race. Their model share is renormalised over that field.
    names: dict[str, tuple[str, str]] = {}
    for blk, key in [*((b, "lines") for b in counted), (poll_block, "entries")]:
        for x in (blk or {}).get(key) or []:
            names.setdefault(name_key(x["name"]), (x["name"], x.get("team")))
    # A field the books and polls have not caught up with: the model's own
    # leaders join it, so a breakout season is on the page before it is priced.
    if names and (any(p.get("stats") for p in players) or simulated.get("share")):
        by_key = {name_key(p["name"]): p for p in players}
        by_key.update({k: dict(name=n, team=t) for k, (n, t) in (simulated.get("who") or {}).items() if k not in by_key})
        for k in sorted(model, key=lambda k: -model[k])[:MODEL_ADDS]:
            if k not in names and k in by_key:
                names[k] = (by_key[k]["name"], by_key[k].get("team"))
    field_model = {k: model.get(k, 0.0) for k in names}
    mtot = sum(field_model.values())
    field_model = {k: v / mtot for k, v in field_model.items()} if mtot > 0 else {}
    if have["model"] and not field_model:
        weights = {k: (round(base[k] / (wsum - base["model"]), 4) if k != "model" and have[k] else 0.0)
                   for k in have}
    # The longest American price any counted book quotes (the one a bettor
    # would take); a prediction market prints a chance, not a price.
    odds_by: dict[str, float] = {}
    for b in counted:
        for x in b.get("lines") or []:
            k, a = name_key(x["name"]), x.get("american")
            if a is not None and (k not in odds_by or implied(a) < implied(odds_by[k])):
                odds_by[k] = a
    proj_by = {}
    for p in players:
        proj_by.setdefault(name_key(p["name"]), p)

    rows = []
    for k, (name, team) in names.items():
        m, q, s = market.get(k, 0.0), poll.get(k, 0.0), field_model.get(k, 0.0)
        share = weights["market"] * m + weights["poll"] * q + weights["model"] * s
        proj = proj_by.get(k)
        rows.append(dict(
            name=name, team=(proj or {}).get("team") or team or (simulated.get("who") or {}).get(k, (None, None))[1],
            tracker=round(share, 4),
            market=round(m, 4) if market else None, poll=round(q, 4) if poll else None,
            model=round(s, 4) if field_model else None,
            odds=odds_by.get(k), pollRank=poll_rank.get(k), pollPoints=(int(poll_pts[k]) if k in poll_pts else None),
            projP=(round(proj["p"], 1) if proj else None),
        ))
    rows.sort(key=lambda r: (-r["tracker"], r["name"]))
    sources = [_source(b, "odds", today, used=u) for b, u in zip(blocks, used)]
    sources += [s for s in (_source(poll_block, "poll", today),) if s]
    return dict(
        label=LABELS[award], rows=rows[:ROWS], weights=weights, sources=sources,
        noPoll=poll_block is None,
        stale=any(s["stale"] for s in sources if s.get("used", True)) or not sources,
        modelNote=(SIM_NOTES if simulated.get("share") else
                   MODEL_NOTES if any(p.get("stats") for p in players) else FALLBACK_NOTES)[award],
        modelKind="sim" if simulated.get("share") else ("stats" if model else None),
    )


def trackers(inputs: dict | None, players: list[dict], playoff: dict[str, float], *, today: date,
             sim: dict | None = None) -> dict | None:
    """All three trackers, or None when there is no inputs file."""
    if not inputs:
        return None
    return {a: tracker(a, inputs, players, playoff, today=today, sim=sim) for a in AWARDS}


# ----------------------------------------------------------------------
# the awards, simulated
# ----------------------------------------------------------------------
def _softmax_mean(score: np.ndarray) -> np.ndarray:
    """Each candidate's vote share exp(T x score) in every season, averaged."""
    z = TEMPERATURE * score
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return (e / e.sum(axis=1, keepdims=True)).mean(axis=0)


def _zcols(x: np.ndarray) -> np.ndarray:
    """z-scores across the field in every season (rows)."""
    sd = x.std(axis=1, keepdims=True)
    return np.where(sd > 0, (x - x.mean(axis=1, keepdims=True)) / np.where(sd > 0, sd, 1.0), 0.0)


def _fixed_z(values: list[float | None]) -> np.ndarray:
    """z-scores of a stat that does not change season to season; a missing one counts as average."""
    have = {i: float(v) for i, v in enumerate(values) if v is not None}
    z = _z({str(i): v for i, v in have.items()})
    return np.array([z.get(str(i), 0.0) for i in range(len(values))])


def _power_mean(points: np.ndarray, scale: np.ndarray | None = None) -> np.ndarray:
    top = np.maximum(points.max(axis=1, keepdims=True), 1)
    w = (np.maximum(points, 0) / top) ** MODEL_POWER
    if scale is not None:
        w = w * scale
    tot = w.sum(axis=1, keepdims=True)
    return np.where(tot > 0, w / np.where(tot > 0, tot, 1.0), 0.0).mean(axis=0)


def simulated_shares(model: dict, result: dict, stats_by_id: dict | None = None, *, seed: int = 20262028) -> dict:
    """Every award, simulated: {award: {"share": {key: p}, "who": {key: (name, team)}}}.

    ``result`` is :func:`season_sim.simulate.simulate`'s; its ``_arrays``
    carry each team's goals still to come and its playoff berth in every
    simulated season, and each goalie's wins. Players' season totals are drawn
    the way the trophy tables draw them (:func:`draw_season_totals`), with
    their own generator so the published trophy odds do not move. Empty when
    the arrays are missing.
    """
    from .simulate import draw_season_totals  # local: keeps this module light for the page tests

    arrays = result.get("_arrays") or {}
    gf_rest, playoff = arrays.get("gf_rest"), arrays.get("playoff")
    if gf_rest is None or playoff is None:
        return {}
    teams = list(arrays["teams"])
    idx = {t: i for i, t in enumerate(teams)}
    sims = int(gf_rest.shape[0])
    rng = np.random.default_rng(seed)
    stats_by_id = stats_by_id or {}
    pool = [(t, q) for t in teams for q in model["players"].get(t, []) if not q.get("filler")]

    def stat(q: dict) -> dict:
        return stats_by_id.get(q.get("id")) or {}

    def keyed(chosen: list[tuple[str, dict]], share: np.ndarray) -> dict:
        out: dict = {"share": {}, "who": {}}
        for (t, q), p in zip(chosen, share):
            k = name_key(q["name"])
            if p > out["share"].get(k, -1.0):
                out["share"][k] = float(p)
                out["who"][k] = (q["name"], t)
        return out

    def composite(chosen: list[tuple[str, dict]], parts: dict[str, float]) -> np.ndarray:
        _, pts = draw_season_totals(rng, chosen, idx, gf_rest, sims)
        gp = np.array([max(float(q.get("proj_gp") or 0.0), 1.0) for _, q in chosen])
        score = parts["points"] * _zcols(pts / gp)
        for part, weight in parts.items():
            if part != "points":
                score = score + weight * _fixed_z([stat(q).get(part) for _, q in chosen])[None, :]
        return _softmax_mean(score)

    out: dict = {}
    by_p = sorted(pool, key=lambda tq: -tq[1]["proj_p"])
    hart = by_p[:SIM_POOL["hart"]]
    if hart:
        _, pts = draw_season_totals(rng, hart, idx, gf_rest, sims)
        berth = playoff[:, [idx[t] for t, _ in hart]].astype(float)
        out["hart"] = keyed(hart, _power_mean(pts, 0.25 + 0.75 * berth))
    rated = [tq for tq in by_p if stat(tq[1]).get("gp", 0) >= MIN_GAMES]
    d_pool = [tq for tq in rated if tq[1]["pos"] == "D" and stat(tq[1]).get("toi", 0) >= 17.0][:SIM_POOL["norris"]]
    if len(d_pool) >= 2:
        out["norris"] = keyed(d_pool, composite(d_pool, NORRIS_PARTS))
    f_pool = [tq for tq in rated if tq[1]["pos"] in ("C", "L", "R") and stat(tq[1]).get("toi", 0) >= 14.0][:SIM_POOL["selke"]]
    if len(f_pool) >= 2 and any(stat(q).get("defence") is not None for _, q in f_pool):
        out["selke"] = keyed(f_pool, composite(f_pool, SELKE_PARTS))
    rookies = [tq for tq in by_p if tq[1].get("rookie")][:SIM_POOL["calder"]]
    if rookies:
        _, pts = draw_season_totals(rng, rookies, idx, gf_rest, sims)
        out["calder"] = keyed(rookies, _power_mean(pts))
    goalies, wins_by = result.get("goalies") or [], arrays.get("goalie_wins") or []
    starters = [(g, w) for g, w in zip(goalies, wins_by) if g.get("share", 0) >= VEZINA_MIN_SHARE]
    if len(starters) >= 2:
        wins = np.stack([np.asarray(w, dtype=float) for _, w in starters], axis=1)

        def sv(g: dict) -> float | None:
            now, prior = (g.get("now") or {}).get("sv"), g.get("sv_3yr")
            gs = float((g.get("now") or {}).get("gs") or 0)
            if now is None:
                return prior
            if prior is None:
                return now
            w = gs / (gs + SV_PRIOR_STARTS)
            return w * float(now) + (1 - w) * float(prior)

        score = (VEZINA_PARTS["wins"] * _zcols(wins)
                 + VEZINA_PARTS["gsax"] * _fixed_z([g.get("gsax60") for g, _ in starters])[None, :]
                 + VEZINA_PARTS["sv"] * _fixed_z([sv(g) for g, _ in starters])[None, :])
        share = _softmax_mean(score)
        out["vezina"] = {"share": {}, "who": {}}
        for (g, _), p in zip(starters, share):
            k = name_key(g["name"])
            out["vezina"]["share"][k] = float(p)
            out["vezina"]["who"][k] = (g["name"], g["team"])
    return out
