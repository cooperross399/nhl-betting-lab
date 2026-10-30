"""The award markets Kalshi and Polymarket list, read live from their public APIs.

Both publish their prices through open, keyless endpoints. Each build asks
them for the NHL award markets of the season being played; any it finds are
added to that award's odds as one more source, dated today, its chances read
as the midpoint of the best bid and ask (Kalshi) or the "Yes" price
(Polymarket). A market a person also typed into ``award_inputs.json`` is
replaced by the live read of it, so one venue is never counted twice.

A venue's field is used only when its chances add to between
:data:`MIN_TOTAL` and :data:`MAX_TOTAL` percent: a book of quotes far past
100% is a list of separate bets, not one market's opinion of who wins.
Nothing here signs in, places an order, or spends a credit; a venue that
does not answer is skipped and the build goes on without it.
"""
from __future__ import annotations

import json
from datetime import date

import requests

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET = "https://gamma-api.polymarket.com"
USER_AGENT = "nhl-betting-lab-site/1.0 (+https://github.com/cooperross399/nhl-betting-lab)"
TIMEOUT = 20

#: Kalshi's series for each award; the season's event ends in its closing year.
KALSHI_SERIES = {"hart": "KXNHLHART", "norris": "KXNHLNORRIS", "vezina": "KXNHLVEZINA",
                 "calder": "KXNHLCALDER", "selke": "KXNHLSELKE"}
KALSHI_PAGES = {"hart": "mvp-odds", "norris": "norris-trophy-odds", "vezina": "vezina-trophy-odds",
                "calder": "rookie-of-the-year-odds", "selke": "awards"}
TROPHY_NAMES = {"hart": "Hart", "norris": "Norris", "vezina": "Vezina", "calder": "Calder", "selke": "Selke"}
MIN_TOTAL, MAX_TOTAL = 70.0, 140.0
MIN_PLAYERS = 3


def _get_json(url: str, params: dict | None = None):
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                        timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _cents(m: dict, key: str) -> float | None:
    """A Kalshi price in cents, whichever spelling the API used."""
    for k, scale in ((f"{key}_dollars", 100.0), (key, 1.0)):
        v = m.get(k)
        if v in (None, ""):
            continue
        try:
            x = float(v) * scale
        except (TypeError, ValueError):
            continue
        if x > 0:
            return x
    return None


def kalshi_lines(event: dict, *, bids: bool = False) -> list[dict]:
    """One Kalshi event's open markets as ``[{name, chance}]`` (chance in %).

    The midpoint of bid and ask by default; with ``bids``, the best bid alone
    (what a seller can take), for a field whose wide longshot spreads push the
    midpoints far past 100%."""
    lines = []
    for m in event.get("markets") or []:
        if str(m.get("status", "active")).lower() not in ("active", "open", "initialized"):
            continue
        name = (m.get("yes_sub_title") or m.get("subtitle") or "").strip()
        if not name:
            continue
        bid, ask = _cents(m, "yes_bid"), _cents(m, "yes_ask")
        if bids:
            chance = bid
        else:
            chance = (bid + ask) / 2 if bid and ask else _cents(m, "last_price")
        if chance:
            lines.append(dict(name=name, chance=round(chance, 2)))
    return lines


def polymarket_lines(event: dict) -> list[dict]:
    """One Polymarket event's open markets as ``[{name, chance}]`` (chance in %)."""
    lines = []
    for m in event.get("markets") or []:
        if m.get("closed") or m.get("active") is False:
            continue
        name = (m.get("groupItemTitle") or "").strip()
        try:
            prices = m.get("outcomePrices")
            prices = json.loads(prices) if isinstance(prices, str) else prices
            yes = float(prices[0]) * 100.0
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if name and yes > 0:
            lines.append(dict(name=name, chance=round(yes, 2)))
    return lines


def _usable(lines: list[dict]) -> bool:
    total = sum(x["chance"] for x in lines)
    return len(lines) >= MIN_PLAYERS and MIN_TOTAL <= total <= MAX_TOTAL


def _season_tags(season: str) -> tuple[str, ...]:
    a, b = season[:4], season[4:]
    return (f"{a}-{b[2:]}", f"{a}–{b[2:]}", f"{a}-{b}", f"{a}/{b[2:]}", f"{a}/{b}", b)


def fetch_kalshi(award: str, season: str) -> list[dict] | None:
    series = KALSHI_SERIES[award]
    data = _get_json(f"{KALSHI}/events", dict(series_ticker=series, status="open", with_nested_markets="true"))
    suffix = f"-{season[6:]}"
    for ev in data.get("events") or []:
        if str(ev.get("event_ticker", "")).upper().endswith(suffix):
            lines = kalshi_lines(ev)
            if lines and not _usable(lines):
                by_bid = kalshi_lines(ev, bids=True)
                if _usable(by_bid):
                    return by_bid
            return lines
    return None


def fetch_polymarket(award: str, season: str) -> tuple[list[dict], str] | None:
    trophy = TROPHY_NAMES[award]
    data = _get_json(f"{POLYMARKET}/public-search", dict(q=f"{trophy} Trophy"))
    tags = _season_tags(season)
    for ev in data.get("events") or []:
        title = str(ev.get("title") or "")
        # The season can sit in the title or only in the slug: the 2026-27
        # Selke is titled "NHL Frank J. Selke Trophy Winner", slug ...-2026-27.
        stamp = f"{title} {ev.get('slug') or ''}"
        if ev.get("closed") or trophy.lower() not in title.lower() or not any(t in stamp for t in tags):
            continue
        return polymarket_lines(ev), str(ev.get("slug") or "")
    return None


def live_blocks(season: str, today: date, *, log=print) -> dict[str, list[dict]]:
    """``{award: [odds block]}`` for every award a venue lists this season."""
    out: dict[str, list[dict]] = {}
    for award in KALSHI_SERIES:
        try:
            lines = fetch_kalshi(award, season)
        except (requests.RequestException, ValueError) as exc:
            log(f"Kalshi {award}: not read ({type(exc).__name__})")
            lines = None
        if lines and _usable(lines):
            out.setdefault(award, []).append(dict(
                book="Kalshi", source="Kalshi public market data, read live (mid of bid and ask)",
                url=f"https://kalshi.com/nhl/{KALSHI_PAGES[award]}", date=today.isoformat(), lines=lines, live=True))
            log(f"Kalshi {award}: {len(lines)} players, {sum(x['chance'] for x in lines):.0f}% in all")
        elif lines:
            log(f"Kalshi {award}: {len(lines)} players adding to {sum(x['chance'] for x in lines):.0f}%, left out")
        try:
            got = fetch_polymarket(award, season)
        except (requests.RequestException, ValueError) as exc:
            log(f"Polymarket {award}: not read ({type(exc).__name__})")
            got = None
        if got and _usable(got[0]):
            lines, slug = got
            out.setdefault(award, []).append(dict(
                book="Polymarket", source="Polymarket public market data, read live",
                url=f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com", date=today.isoformat(),
                lines=lines, live=True))
            log(f"Polymarket {award}: {len(lines)} players, {sum(x['chance'] for x in lines):.0f}% in all")
        elif got and got[0]:
            log(f"Polymarket {award}: {len(got[0])} players adding to {sum(x['chance'] for x in got[0]):.0f}%, left out")
    return out


def merge(inputs: dict | None, live: dict[str, list[dict]]) -> dict | None:
    """``inputs`` with each live block added, replacing a hand-kept block from the same venue."""
    if inputs is None or not live:
        return inputs
    from .awards import odds_blocks

    merged = dict(inputs)
    for award, blocks in live.items():
        spec = dict(merged.get(award) or {})
        venues = {b["book"].lower() for b in blocks}
        kept = [b for b in odds_blocks(spec) if str(b.get("book") or "").lower() not in venues]
        spec["odds"] = kept + blocks
        merged[award] = spec
    return merged
