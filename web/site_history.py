#!/usr/bin/env python3
"""Site history for one lab's board. Sport-agnostic. Run right after the board is built:

    python web/site_history.py --data dist/data [--slot morning]

Does three things, all inside --data:
  1. Freezes today's board the first time it is built (history/<date>[_<slot>].json)
     and never overwrites it. That frozen copy is the published opinion.
  2. Appends the current market values to history/lines/<date>.json, one point per
     build, and injects the series into board.json as `lineHistory[gameId][key]`
     so the page can draw the movement.
  3. Rewrites history/index.json, newest first, with game and best-bet counts
     (`bets: null` for a board on which no game was priced; no `bets` at all
     for an exhibition board, where the model abstains).

The workflow restores the previous run's history artifact into --data/history before
this runs and uploads it again afterwards, so the series survive between builds.
Nothing here fetches odds, spends a credit, or places a bet.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

#: series key -> candidate paths into a game dict, first numeric hit wins.
SERIES = {
    "ml_home": [("moneyline", "current", "home")],
    "pl_price": [("puckLine", "price")],
    "spread": [("spread", "current")],
    "total": [("total", "current")],
    "total_over": [("total", "over")],
    "btts_yes": [("btts", "yes")],
    "dnb_home": [("drawNoBet", "home")],
}


def dig(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d if isinstance(d, (int, float)) and not isinstance(d, bool) else None


def game_priced(g: dict) -> bool:
    """Whether the board held a market price for this game.

    Read from the game's `priced` flag. A board frozen before that flag, or
    written by a lab whose builder does not set it, is read by its lines: the
    NHL builder attached `moneyline` under exactly the condition that now sets
    `priced` (as web/build_site_json.py::build_results reads it), and any
    numeric market value in SERIES is a price the board carried. So is a pick
    quoting a numeric `price`: SERIES does not cover every market a lab
    publishes (EPL corners and double chance, or a total carrying only its
    probabilities), and a best bet on one of those is still a priced call.
    An explicit `priced: false` overrides all of it.
    """
    if "priced" in g:
        return g["priced"] is True
    if "moneyline" in g or any(dig(g, p) is not None for paths in SERIES.values() for p in paths):
        return True
    pick = g.get("pick")
    return isinstance(pick, dict) and dig(pick, ("price",)) is not None


def board_date(board: dict) -> str:
    for k in ("boardDate", "slateDate", "windowStart"):
        if board.get(k):
            return str(board[k])[:10]
    return datetime.now(timezone.utc).date().isoformat()


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def dump(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


#: The day a board belongs to, and the day a card was generated on, are both
#: New York days: the card runs at 09:30 there and the slate is the NHL's.
BOARD_ZONE = ZoneInfo("America/New_York")


def built_on_stale_state(board: dict) -> bool:
    """Whether this board must not be frozen: it was built on an earlier day's
    card, so it stands for an opinion the lab did not hold today.

    Publish Site builds on its 14:45 cron and again after each Gameday Refresh,
    and the state it restores is the newest Gameday run that carries one. A
    cron build that starts before today's run has finished restores
    YESTERDAY's run: the model is fitted without last night's games and every
    back-to-back flag is lost (430 of 430 sides on 2025-26; 40 projected
    winners flip). The day's first build froze for good, so that board used to
    become the record that Results grades.

    The first published opinion still stands, and is still never edited: the
    Archive page's promise is unchanged. What changes is that a stale build is
    not a published opinion to begin with. It is shown on the live page and
    not frozen; the build after today's Gameday Refresh freezes the day.

    Stale is: a regular-season board with games, built on a card whose
    `cardGeneratedAt` is a New York day before `boardDate` (or cannot be
    read). A board with NO card is not stale by this rule: that is the lab's
    no-state path, which publishes and freezes the schedule alone so Results
    can say the board carried no projection, and it is guarded elsewhere
    (the state restore refuses an unanswered listing; a thin history projects
    nothing). Preseason and game-less boards are never stale either. The cost,
    accepted: a day whose Gameday runs are ALL dropped after an earlier day's
    card was restored freezes nothing, and settles as "No board was
    published", which is true.
    """
    if board.get("phase") != "regular" or not board.get("games"):
        return False
    stamp = board.get("cardGeneratedAt")
    if stamp is None:
        return False
    try:
        day = datetime.fromisoformat(str(board.get("boardDate"))).date()
    except ValueError:
        return True
    try:
        made = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    if made.tzinfo is None:
        return True
    return made.astimezone(BOARD_ZONE).date() < day


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dist/data")
    ap.add_argument("--slot", default="", help="Card slot suffix for sports with several cards a day.")
    args = ap.parse_args(argv)
    data = Path(args.data)
    board_path = data / "board.json"
    board = load(board_path, None)
    if board is None:
        print("no board.json; nothing to record")
        return 0
    date = board_date(board)
    slot = args.slot or board.get("cardSlot") or ""
    hist = data / "history"
    lines_path = hist / "lines" / f"{date}.json"

    # 2. line series
    lines = load(lines_path, {})
    stamp = board.get("generatedAt") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for g in board.get("games", []):
        gid = str(g.get("id"))
        series = lines.setdefault(gid, {})
        for key, paths in SERIES.items():
            v = next((x for x in (dig(g, p) for p in paths) if x is not None), None)
            if v is None:
                continue
            pts = series.setdefault(key, [])
            if not pts or pts[-1]["v"] != v:
                pts.append({"t": stamp, "v": v})
            elif pts[-1]["t"] != stamp:
                pts[-1] = {"t": stamp, "v": v}  # same value, newer confirmation
    dump(lines_path, lines)
    board["lineHistory"] = {gid: {k: v for k, v in s.items() if len(v) >= 2} for gid, s in lines.items()}
    board["lineHistory"] = {gid: s for gid, s in board["lineHistory"].items() if s}
    dump(board_path, board)

    # 1. freeze
    fname = f"{date}_{slot}.json" if slot else f"{date}.json"
    frozen = hist / fname
    if built_on_stale_state(board):
        print(f"did not freeze {fname}: built on a card generated {board.get('cardGeneratedAt') or 'never'}, "
              "not today; the build after today's Gameday Refresh freezes the day")
    elif not frozen.exists():
        dump(frozen, board)
        print(f"froze {fname}")

    # 3. index
    entries = []
    for p in sorted(hist.glob("*.json")):
        if p.name == "index.json":
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:_(\w+))?\.json$", p.name)
        if not m:
            continue
        b = load(p, {})
        games = b.get("games", [])
        # Best bets are counted among the games the board priced. This used
        # to count every game's pick without reading `priced`, so a board no
        # price reached (every regular-season board Publish Site builds
        # without staged prices) was indexed `bets: 0`, and the Archive page
        # listed it as "0 best bets": a slate the model looked at and passed
        # on. Nobody looked. A board with no priced game is `bets: null`,
        # which the page prints as "not priced"; "0 best bets" stays for a
        # priced board where nothing cleared the bar.
        priced = [g for g in games if isinstance(g, dict) and game_priced(g)]
        if games and not priced:
            bets = None
        else:
            bets = sum(1 for g in priced if isinstance(g.get("pick"), dict) and g["pick"].get("kind", "bet") == "bet")
        e = {"date": m.group(1), "file": p.name, "games": len(games), "bets": bets}
        if m.group(2):
            e["slot"] = m.group(2)
        if b.get("phase") == "preseason":
            e["note"] = "exhibition"
            # The model abstains on exhibitions and nobody looks for a price,
            # so neither a count nor "not priced" is true of one (the board
            # page says "Exhibition · model abstains", web/lib/sports.js).
            # Every preseason game is `priced: false`, so this entry was
            # `bets: null` and the Archive read "exhibition · not priced".
            # No count at all is what the Archive prints as nothing.
            del e["bets"]
        entries.append(e)
    entries.sort(key=lambda e: (e["date"], e.get("slot", "")), reverse=True)
    dump(hist / "index.json", {"generatedAt": stamp, "dates": entries})
    print(f"history: {len(entries)} boards indexed; lines recorded for {len(lines)} games. No bet was placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
