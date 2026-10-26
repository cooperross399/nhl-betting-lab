"""Trackers for the voted awards: the Hart, the Norris and the Selke.

These trophies are voted by the PHWA, so no simulation can count them. Each
tracker instead reads three signals and shows them side by side:

* **market**: the award odds a book published, as hand-kept in
  ``data/season_sim/award_inputs.json``, turned into probabilities with the
  margin taken out (each implied probability divided by their sum over the
  listed field);
* **poll**: the latest media poll's points for each player over the poll's
  total (a winner-only poll counts each vote as a point);
* **model**: the season sim's own projection. Hart: projected points raised
  to the sixth power, times 0.25 + 0.75 x the team's playoff odds (voters
  rarely pick a player whose club misses). Norris: defensemen's projected
  points to the sixth power. Selke: none, because the sim has no defensive
  rating for a forward, so the Selke tracker is odds and poll only.

The tracker share is the weighted mean of the signals that exist, with
:data:`WEIGHTS` renormalised over them; a player missing from a signal counts
as zero in it. It is a projection of the vote, not a forecast of it, and the
page says so. Nothing here reads a sportsbook, spends a credit or places a bet.
"""
from __future__ import annotations

import json
import unicodedata
from datetime import date
from pathlib import Path

#: How much each signal counts in the tracker share (renormalised over the
#: signals an award has). The book is the most informed, the poll is what the
#: voters themselves say, the model is a points projection voters only partly
#: follow. Chosen, not fitted: three seasons of trackers is too few to fit.
WEIGHTS = {"market": 0.5, "poll": 0.3, "model": 0.2}
#: Projected points are raised to this power so the model signal is as
#: top-heavy as a real vote (the leader is far likelier than the tenth man).
MODEL_POWER = 6
#: An input older than this is flagged stale on the page.
STALE_DAYS = 14
#: Rows published per award.
ROWS = 10

AWARDS = ("hart", "norris", "selke")
LABELS = {"hart": "Hart Trophy", "norris": "Norris Trophy", "selke": "Selke Trophy"}
MODEL_NOTES = {
    "hart": "Model: projected points to the sixth power, times 0.25 + 0.75 x the club's playoff odds.",
    "norris": "Model: a defenseman's projected points to the sixth power.",
    "selke": "No model signal: the season sim has no defensive rating for a forward, so this tracker is the odds and the poll.",
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


def _market(block: dict | None) -> dict[str, float]:
    lines = (block or {}).get("lines") or []
    raw = {name_key(x["name"]): implied(x["american"]) for x in lines if x.get("american") is not None}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else {}


def _poll(block: dict | None) -> tuple[dict[str, float], dict[str, int], dict[str, float]]:
    entries = (block or {}).get("entries") or []
    pts = {name_key(e["name"]): float(e.get("points") or 0) for e in entries}
    total = sum(pts.values())
    share = {k: v / total for k, v in pts.items()} if total > 0 else {}
    ordered = sorted(pts.values(), reverse=True)
    rank = {k: 1 + ordered.index(v) for k, v in pts.items()}
    return share, rank, pts


def _model(award: str, players: list[dict], playoff: dict[str, float]) -> dict[str, float]:
    if award == "selke":
        return {}
    pool = [p for p in players if p.get("pos") != "G" and (award != "norris" or p.get("pos") == "D")]
    if not pool:
        return {}
    top = max(p["p"] for p in pool) or 1.0
    raw = {}
    for p in pool:
        w = (max(p["p"], 0.0) / top) ** MODEL_POWER
        if award == "hart":
            w *= 0.25 + 0.75 * playoff.get(p["team"], 0.0)
        k = name_key(p["name"])
        raw[k] = max(raw.get(k, 0.0), w)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else {}


def _source(block: dict | None, kind: str, today: date) -> dict | None:
    if not block:
        return None
    age = _age_days(block.get("date"), today)
    out = dict(kind=kind, date=block.get("date"), url=block.get("url"), ageDays=age,
               stale=age is None or age > STALE_DAYS)
    if kind == "odds":
        out.update(book=block.get("book"), source=block.get("source"))
    else:
        out.update(outlet=block.get("outlet"), voters=block.get("voters"), scoring=block.get("scoring"))
    return out


def tracker(award: str, inputs: dict, players: list[dict], playoff: dict[str, float], *, today: date) -> dict:
    """One award's tracker: rows, the sources with their age, the weights used."""
    spec = inputs.get(award) or {}
    odds_block, poll_block = spec.get("odds"), spec.get("poll")
    market = _market(odds_block)
    poll, poll_rank, poll_pts = _poll(poll_block)
    model = _model(award, players, playoff)
    have = {"market": bool(market), "poll": bool(poll), "model": bool(model)}
    wsum = sum(WEIGHTS[k] for k, on in have.items() if on)
    weights = {k: (round(WEIGHTS[k] / wsum, 4) if on and wsum else 0.0) for k, on in have.items()}

    # The candidates are the people a book or a poll names; the model only
    # re-weights them, so a points leader no one has priced is not invented
    # into the race. Their model share is renormalised over that field.
    names: dict[str, tuple[str, str]] = {}
    for blk, key in ((odds_block, "lines"), (poll_block, "entries")):
        for x in (blk or {}).get(key) or []:
            names.setdefault(name_key(x["name"]), (x["name"], x.get("team")))
    field_model = {k: model.get(k, 0.0) for k in names}
    mtot = sum(field_model.values())
    field_model = {k: v / mtot for k, v in field_model.items()} if mtot > 0 else {}
    if have["model"] and not field_model:
        weights = {k: (round(WEIGHTS[k] / (wsum - WEIGHTS["model"]), 4) if k != "model" and have[k] else 0.0)
                   for k in have}
    odds_by = {name_key(x["name"]): x["american"] for x in (odds_block or {}).get("lines") or []}
    proj_by = {}
    for p in players:
        proj_by.setdefault(name_key(p["name"]), p)

    rows = []
    for k, (name, team) in names.items():
        m, q, s = market.get(k, 0.0), poll.get(k, 0.0), field_model.get(k, 0.0)
        share = weights["market"] * m + weights["poll"] * q + weights["model"] * s
        proj = proj_by.get(k)
        rows.append(dict(
            name=name, team=(proj or {}).get("team") or team, tracker=round(share, 4),
            market=round(m, 4) if market else None, poll=round(q, 4) if poll else None,
            model=round(s, 4) if field_model else None,
            odds=odds_by.get(k), pollRank=poll_rank.get(k), pollPoints=(int(poll_pts[k]) if k in poll_pts else None),
            projP=(round(proj["p"], 1) if proj else None),
        ))
    rows.sort(key=lambda r: (-r["tracker"], r["name"]))
    sources = [s for s in (_source(odds_block, "odds", today), _source(poll_block, "poll", today)) if s]
    return dict(
        label=LABELS[award], rows=rows[:ROWS], weights=weights, sources=sources,
        noPoll=poll_block is None, stale=any(s["stale"] for s in sources) or not sources,
        modelNote=MODEL_NOTES[award],
    )


def trackers(inputs: dict | None, players: list[dict], playoff: dict[str, float], *, today: date) -> dict | None:
    """All three trackers, or None when there is no inputs file."""
    if not inputs:
        return None
    return {a: tracker(a, inputs, players, playoff, today=today) for a in AWARDS}
