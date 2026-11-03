"""The card's player-prop leans, graded season long at a flat 1u: prop_leans.json.

Cooper, 2026-11-03: "track the prop leans record/profit on the website".

A lean is a prop the card lists under "Leans" and stakes at zero: its edge
clears the measurement bar but not the best-bet bar, or it cleared the
best-bet bar and a rule held the stake back (the odds-bracket stats check,
one stake per outcome, the `points` exclusion, the saves starter check).
Nothing here is bet. The record is what 1u on every lean would have done.

Both sources are on the public `card-feed` branch, so this needs no state of
its own and every run rebuilds the whole season:

* **Which leans.** `latest_card_comment.md` is rewritten on every card, so
  its git history holds every card ever published. For each league day the
  card used is the FIRST card of that day (New York time, read off its
  "Generated:" line) whose Leans table lists a player prop: the morning
  card, the one the site's board freezes on and the forward ledger's
  snapshot is taken from. A morning card blocked before props were priced
  (2026-10-06) falls to the first later card that priced them. Re-prices
  later in the day do not replace it.
* **The result.** `forward_evidence/<day>.csv`, the ledger the lab settles
  every morning by its own rules (a player who did not dress is void, a
  goalie under 40 minutes is void). A lean is matched on its game, market,
  player, side and line; the result does not depend on the book. A day with
  no ledger file yet is pending (it settles the next morning). A lean the
  ledger does not hold is counted as unmatched, never guessed.
* **The price.** The card's own listed price for the lean. A win pays at
  that price, a loss is -1u, a push or a void is 0.

Only player props are counted; the card's team-market leans are not.
Every record carries its counts so that W + L + P + voids + unmatched +
pending equals the leans listed, and the build fails if it does not.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

#: The flat notional stake on every lean, in units.
LEAN_STAKE = 1.0

#: The card's prop markets, as the card names them.
PROP_MARKETS = ("shots_on_goal", "points", "goals", "assists", "goalie_saves", "blocked_shots", "hits")

PROP_LABEL = {"shots_on_goal": "Shots on goal", "points": "Points", "goals": "Goals", "assists": "Assists",
              "goalie_saves": "Goalie saves", "blocked_shots": "Blocked shots", "hits": "Hits"}

CARD_FILE = "latest_card_comment.md"
LEDGER_DIR = "forward_evidence"

#: The ledger's outcome words, as the site's results spell them.
OUTCOMES = {"won": "win", "lost": "loss", "push": "push", "void": "void"}

_GENERATED = re.compile(r"^- Generated: (\S+)", re.M)
_LEANS = re.compile(r"^## Leans\n(.*?)(?=^## |\Z)", re.M | re.S)
_SELECTION = re.compile(r"^(?P<player>.+) (?P<side>over|under) (?P<line>\d+(?:\.\d+)?)$")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _fold(text: object) -> str:
    """Case, accents and spacing folded away, for joining names."""
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(plain.casefold().split())


def _team_key(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(name))


def _price(text: str) -> int | None:
    try:
        value = int(text.replace("+", "").replace("−", "-").strip())
    except ValueError:
        return None
    return value if value and abs(value) >= 100 else None


def _percent(text: str) -> float | None:
    try:
        return round(float(text.replace("%", "").replace("+", "").replace("−", "-").strip()) / 100, 4)
    except ValueError:
        return None


def generated_day(text: str) -> str | None:
    """The league day (New York date) of a card comment, or None."""
    m = _GENERATED.search(text)
    if not m:
        return None
    try:
        moment = datetime.fromisoformat(m[1].replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(ET).date().isoformat()


def parse_leans(text: str) -> list[dict]:
    """The player-prop rows of a card comment's Leans table.

    Columns are found by the header, because the table gained "Bet down to"
    on 2026-11-01. A row whose selection, game or price cannot be read is
    left out and counted by the caller as nothing, never guessed at.
    """
    m = _LEANS.search(text)
    if not m:
        return []
    header: dict[str, int] | None = None
    rows: list[dict] = []
    for raw in m[1].splitlines():
        if not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if cells and cells[0] == "Game":
            header = {name: i for i, name in enumerate(cells)}
            continue
        if not header or any(k not in header for k in ("Game", "Market", "Selection", "Price")):
            continue
        if len(cells) < len(header):
            continue
        market = cells[header["Market"]].strip("`")
        if market not in PROP_MARKETS:
            continue
        game = cells[header["Game"]].split(" @ ")
        sel = _SELECTION.match(cells[header["Selection"]])
        price = _price(cells[header["Price"]])
        if len(game) != 2 or not sel or price is None:
            continue
        rows.append({
            "away": game[0].strip(), "home": game[1].strip(), "market": market,
            "player": sel["player"].strip(), "side": sel["side"], "line": float(sel["line"]),
            "price": price,
            "book": cells[header["Book"]] if "Book" in header else None,
            "modelProb": _percent(cells[header["Model"]]) if "Model" in header else None,
            "edge": _percent(cells[header["Edge"]]) if "Edge" in header else None,
            "starts": cells[header["Starts"]] if "Starts" in header else None,
        })
    return rows


def leans_by_day(repo: Path, ref: str) -> dict[str, dict]:
    """{league day: {"commit", "generated", "rows"}} from the card's history:
    each day's first card that lists a player-prop lean."""
    commits = _git(repo, "log", "--reverse", "--format=%H", ref, "--", CARD_FILE).split()
    out: dict[str, dict] = {}
    for commit in commits:
        text = _git(repo, "show", f"{commit}:{CARD_FILE}")
        day = generated_day(text)
        if not day or day in out:
            continue
        rows = parse_leans(text)
        if rows:
            out[day] = {"commit": commit, "generated": _GENERATED.search(text)[1], "rows": rows}
    return out


def ledger_outcomes(text: str) -> dict[tuple, set[str]]:
    """(home, away, market, player, side, line) -> the ledger's outcomes for it."""
    out: dict[tuple, set[str]] = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("market") not in PROP_MARKETS:
            continue
        try:
            line = float(r.get("line") or "")
        except ValueError:
            continue
        key = (_team_key(r.get("home_team")), _team_key(r.get("away_team")), r["market"], _fold(r.get("player")),
               str(r.get("selection") or "").lower(), line)
        out.setdefault(key, set()).add(str(r.get("outcome") or "").strip().lower())
    return out


def _lean_key(row: dict) -> tuple:
    return (_team_key(row["home"]), _team_key(row["away"]), row["market"], _fold(row["player"]), row["side"], row["line"])


def win_profit(american: float) -> float:
    return american / 100.0 if american > 0 else 100.0 / abs(american)


def _units(result: str, price: float) -> float:
    if result == "win":
        return round(LEAN_STAKE * win_profit(price), 4)
    return -LEAN_STAKE if result == "loss" else 0.0


def _empty() -> dict:
    return {"listed": 0, "w": 0, "l": 0, "p": 0, "void": 0, "pending": 0, "unmatched": 0, "units": 0.0, "staked": 0.0}


def _add(tally: dict, result: str | None, units: float) -> None:
    tally["listed"] += 1
    if result in ("win", "loss", "push"):
        tally["w" if result == "win" else "l" if result == "loss" else "p"] += 1
        tally["units"] += units
        tally["staked"] += LEAN_STAKE
    elif result == "void":
        tally["void"] += 1
    elif result == "pending":
        tally["pending"] += 1
    else:
        tally["unmatched"] += 1


def _finish(tally: dict) -> dict:
    out = {**tally, "units": round(tally["units"], 2), "staked": round(tally["staked"], 2)}
    out["graded"] = out["w"] + out["l"] + out["p"]
    out["returnPct"] = round(100 * tally["units"] / tally["staked"], 1) if tally["staked"] else None
    out["winPct"] = round(100 * out["w"] / (out["w"] + out["l"]), 1) if out["w"] + out["l"] else None
    accounted = out["graded"] + out["void"] + out["pending"] + out["unmatched"]
    if accounted != out["listed"]:
        raise AssertionError(f"prop leans do not add up: {accounted} accounted for, {out['listed']} listed")
    return out


def build(repo: Path, ref: str, *, today: date, directory=None, abbr=None,
          generated_at: str | None = None) -> dict:
    """prop_leans.json. `directory(name, home_abbr, away_abbr)` names a
    player's (id, team) when the box-score logs can; `abbr(team name)` gives
    a club's abbreviation."""
    days = leans_by_day(repo, ref)
    ledger_files = set(_git(repo, "ls-tree", "--name-only", ref, f"{LEDGER_DIR}/").split())
    season = _empty()
    by_market: dict[str, dict] = {}
    by_side: dict[str, dict] = {}
    nights: list[dict] = []
    rows: list[dict] = []
    for day in sorted(days):
        if day >= today.isoformat():
            continue
        path = f"{LEDGER_DIR}/{day}.csv"
        outcomes = ledger_outcomes(_git(repo, "show", f"{ref}:{path}")) if path in ledger_files else None
        night = _empty()
        for lean in days[day]["rows"]:
            if outcomes is None:
                result = "pending"
            else:
                found = {OUTCOMES.get(o) for o in outcomes.get(_lean_key(lean), set())}
                result = next(iter(found)) if len(found) == 1 and None not in found else None
            units = _units(result, lean["price"]) if result in ("win", "loss", "push", "void") else 0.0
            for tally in (season, night, by_market.setdefault(lean["market"], _empty()),
                          by_side.setdefault(lean["side"], _empty())):
                _add(tally, result, units)
            if result not in ("win", "loss", "push"):
                continue
            home_abbr = abbr(lean["home"]) if abbr else None
            away_abbr = abbr(lean["away"]) if abbr else None
            pid, team = (directory(lean["player"], home_abbr, away_abbr) if directory else (None, None))
            rows.append({
                "date": day, "group": "leans", "market": lean["market"],
                "propType": PROP_LABEL.get(lean["market"], lean["market"]), "side": lean["side"],
                "line": lean["line"], "player": lean["player"], "playerId": pid, "team": team,
                "opp": (away_abbr if team == home_abbr else home_abbr) if team else None,
                "teams": [away_abbr, home_abbr], "price": lean["price"], "book": lean.get("book"),
                "modelProb": lean.get("modelProb"), "edge": lean.get("edge"),
                "result": result, "staked": LEAN_STAKE, "units": round(units, 2),
            })
        nights.append({"date": day, "card": days[day]["generated"], **_finish(night)})
    rows.sort(key=lambda r: (r["date"], r["player"]), reverse=True)
    graded_nights = [n for n in nights if n["graded"]]
    return {
        "generatedAt": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "stake": LEAN_STAKE,
        "source": "card-feed: each league day's first card that lists a prop lean, settled by the forward ledger",
        "note": ("Leans are props the card lists but does not bet. This is what 1u on every one would have done, "
                 "at the price the card listed. Nothing here was bet."),
        "firstDate": graded_nights[0]["date"] if graded_nights else None,
        "lastDate": graded_nights[-1]["date"] if graded_nights else None,
        "nights": len(graded_nights),
        "season": _finish(season),
        "byMarket": sorted(({"key": m, "label": PROP_LABEL.get(m, m), **_finish(t)} for m, t in by_market.items()),
                           key=lambda g: -g["units"]),
        "bySide": [{"key": s, "label": s.title(), **_finish(t)} for s, t in sorted(by_side.items())],
        "byNight": nights,
        "rows": rows,
    }
