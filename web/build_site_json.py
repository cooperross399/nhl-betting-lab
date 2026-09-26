#!/usr/bin/env python3
"""Build the JSON the NHL Projections site reads, from the lab's own outputs.

    PYTHONPATH=src python web/build_site_json.py --out dist/data

Writes `board.json` (today's slate) and `results.json` (yesterday, settled),
and keeps one frozen copy of each board under `history/YYYY-MM-DD.json` so
tomorrow's settlement reads the opinion that was actually published.

Sources, in order of trust:
  * NHL API schedule (free, keyless): slate, start times, venues, TV,
    game type, records, finals. Works in preseason, when nothing else does.
  * data/outputs/gameday_card.json: the card's selections and passes, which
    carry the model probability, edge and best price for every team market.
  * data/staging/*.csv: current prices, the total's line read from the bulk
    file's featured rows alone; data/processed/line_movement/<day>.csv: each
    game's market at the first capture that held it, used as the open. The
    capture holds no bulk market, so every open total is missing (its totals
    are ladder rungs) and so is every open moneyline (it asks for no h2h).
    Publish Site restores NEITHER — its two artifacts carry no data/staging
    and no line_movement — so there every regular-season game is published
    unpriced (`priced: false`, no line, no pick) and every open is missing.
    The board says so rather than reading as a pass, and so does the next
    morning's Results page, which grades no game that carried no pick.
  * data/processed/team_games.csv + TeamModel: expected goals per side,
    with the back-to-back adjustment only while the recorded `team_b2b`
    verdict ships it — the same verdict, read the same way, as the card.
  * data/outputs/forward_evidence.json: the forward ledger's SIZE, in wagers.
    Never its return, and never a season record: nothing here tallies one.

Preseason (gameType 1) is published as schedule only. The models are fitted
on regular-season games and the card excludes exhibitions, so no projection
or pick is invented for them — the page says so instead.

Nothing here fetches odds, spends a credit, or places a bet.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NHL = "https://api-web.nhle.com/v1"
SEASON_OPENS = date(2026, 9, 29)

TEAMS = {
    "ANA": ("Anaheim Ducks", "Ducks", "#F47A38", "#000000"),
    "BOS": ("Boston Bruins", "Bruins", "#FFB81C", "#000000"),
    "BUF": ("Buffalo Sabres", "Sabres", "#003087", "#FFFFFF"),
    "CAR": ("Carolina Hurricanes", "Hurricanes", "#CC0000", "#FFFFFF"),
    "CBJ": ("Columbus Blue Jackets", "Blue Jackets", "#002654", "#FFFFFF"),
    "CGY": ("Calgary Flames", "Flames", "#C8102E", "#FFFFFF"),
    "CHI": ("Chicago Blackhawks", "Blackhawks", "#CF0A2C", "#FFFFFF"),
    "COL": ("Colorado Avalanche", "Avalanche", "#6F263D", "#FFFFFF"),
    "DAL": ("Dallas Stars", "Stars", "#006847", "#FFFFFF"),
    "DET": ("Detroit Red Wings", "Red Wings", "#CE1126", "#FFFFFF"),
    "EDM": ("Edmonton Oilers", "Oilers", "#FF4C00", "#FFFFFF"),
    "FLA": ("Florida Panthers", "Panthers", "#C8102E", "#FFFFFF"),
    "LAK": ("Los Angeles Kings", "Kings", "#111111", "#FFFFFF"),
    "MIN": ("Minnesota Wild", "Wild", "#154734", "#FFFFFF"),
    "MTL": ("Montréal Canadiens", "Canadiens", "#AF1E2D", "#FFFFFF"),
    "NJD": ("New Jersey Devils", "Devils", "#CE0E2D", "#FFFFFF"),
    "NSH": ("Nashville Predators", "Predators", "#FFB81C", "#000000"),
    "NYI": ("New York Islanders", "Islanders", "#00539B", "#FFFFFF"),
    "NYR": ("New York Rangers", "Rangers", "#0038A8", "#FFFFFF"),
    "OTT": ("Ottawa Senators", "Senators", "#C52032", "#FFFFFF"),
    "PHI": ("Philadelphia Flyers", "Flyers", "#F74902", "#FFFFFF"),
    "PIT": ("Pittsburgh Penguins", "Penguins", "#FCB514", "#000000"),
    "SEA": ("Seattle Kraken", "Kraken", "#001628", "#FFFFFF"),
    "SJS": ("San Jose Sharks", "Sharks", "#006D75", "#FFFFFF"),
    "STL": ("St. Louis Blues", "Blues", "#002F87", "#FFFFFF"),
    "TBL": ("Tampa Bay Lightning", "Lightning", "#002868", "#FFFFFF"),
    "TOR": ("Toronto Maple Leafs", "Maple Leafs", "#00205B", "#FFFFFF"),
    "UTA": ("Utah Mammoth", "Mammoth", "#6CACE4", "#000000"),
    "VAN": ("Vancouver Canucks", "Canucks", "#00205B", "#FFFFFF"),
    "VGK": ("Vegas Golden Knights", "Golden Knights", "#B4975A", "#000000"),
    "WPG": ("Winnipeg Jets", "Jets", "#041E42", "#FFFFFF"),
    "WSH": ("Washington Capitals", "Capitals", "#041E42", "#FFFFFF"),
}
MARKET_LABEL = {"moneyline": "Moneyline", "puck_line": "Puck line", "total_goals": "Total", "regulation_3_way": "Regulation"}


def team_entry(abbr: str) -> dict:
    name, short, color, fg = TEAMS.get(abbr, (abbr, abbr, "#14151a", "#FFFFFF"))
    return {"name": name, "short": short, "color": color, "fg": fg}


#: api-web.nhle.com answers `User-Agent: Python-urllib/3.12` with **403
#: Forbidden**. Any other agent gets a 200 — this is not authentication, a
#: rate limit, or an outage, and the first deployment failed on it with a
#: traceback that looked like a network problem and was not.
#:
#: The lab's own client (`nhl_betting_lab.data.nhl_api`) never hit this
#: because it uses `requests`, which sends its own agent. This script stays
#: stdlib-only on purpose — it builds a static site and must run without
#: pandas or the lab's dependency tree — so it sets the header itself rather
#: than growing an import. That is the whole reason for the duplication, and
#: it is written down here so the next person does not resolve it by
#: importing the lab.
USER_AGENT = "nhl-betting-lab-site/1.0 (+https://github.com/cooperross399/nhl-betting-lab)"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310 - fixed host
        return json.load(resp)


def schedule_for(day: date) -> list[dict]:
    payload = fetch_json(f"{NHL}/schedule/{day.isoformat()}")
    for entry in payload.get("gameWeek", []):
        if entry.get("date") == day.isoformat():
            return entry.get("games", []) or []
    return []


def implied(american: float) -> float:
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def to_american(p: float) -> int:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


#: The staged file holding the bulk endpoint's featured lines and nothing
#: else: `run_provider_shadow.py` writes `fetch_team_markets` here, and the
#: per-event fetch, alternate ladders included, to `player_props_staging.csv`.
#: Spelled out rather than imported for the reason USER_AGENT gives; the
#: tests stage through `odds_api.write_staging` under the provider's own
#: constant, so a rename there leaves this board with no line and fails them.
FEATURED_PRICES_FILENAME = "odds_api_prices_staging.csv"

#: Where `scripts/capture_line_movement.py::capture_path` writes a day's
#: captures: `line_movement/<day>.csv`, every capture of the day appended to
#: one file, each row stamped with its `captured_at`.
MOVEMENT_DIRNAME = "line_movement"

#: Markets whose every row in a line-movement capture is an alternate rung.
#: The capture asks for the per-event markets and their ladders and never the
#: bulk `spreads` or `totals`, so its puck_line rows are `alternate_spreads`
#: and its total_goals rows are `alternate_totals`; and a normalized row does
#: not say which rung, if any, is the featured line.
LADDER_ONLY_IN_CAPTURE = frozenset({"puck_line", "total_goals"})


def read_prices(staging: Path, *, featured_only: bool = False) -> list[dict]:
    """Staged team-market rows. `featured_only` reads the bulk file alone.

    Every staged file used to be pooled for everything, including the line a
    total is published at. `player_props_staging.csv` holds the per-event
    fetch, `alternate_totals` staged as `total_goals`, so the most common
    staged line was whichever rung the ladders repeated: 4.5 (over -350,
    under +295) against a bulk main line of 6.0. The prices at a line stay
    pooled (a quote at 6.0 is the same bet in either market); which line is
    THE line is read from the featured rows alone.
    """
    paths = [staging / FEATURED_PRICES_FILENAME] if featured_only else sorted(staging.glob("*.csv"))
    rows: list[dict] = []
    for path in paths:
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return [r for r in rows if r.get("market") in MARKET_LABEL]


def _moment(value: object) -> datetime | None:
    """A capture's `captured_at`, or None when it cannot be placed in time."""
    try:
        moment = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def earliest_capture(processed: Path, day: date) -> list[dict]:
    """Each game's market as the first capture that held it saw it: the open.

    This globbed `line_movement/<day>*.csv` and returned every row of the
    first file. The capture writes one file per day and appends every capture
    to it, so the "open" was the whole day pooled, and each later capture
    moved it: a 14:00 total of 6.5 read 5.5 once an 18:00 capture was
    appended, and a captured moneyline opening at +110 read +135, the best
    price of the day. The only test of the open read `<day>_1300.csv`, a name
    no writer produces. Now the file is the one `capture_path` names, and a
    row is kept only if its `captured_at` is the first moment its game and
    market were captured. A row that cannot be placed in time is no capture's
    and is dropped: missing stays missing.

    The ladder markets are dropped too (LADDER_ONLY_IN_CAPTURE). The most
    common line among them published a rung as the open total, 4.5 against a
    current line of 6.0. Until a capture records which of its rows is the
    featured line, it has no open total to give.

    The capture asks for no bulk `h2h` today (a spending decision left to the
    owner), so every moneyline open is missing and the page prints a dash.
    """
    path = processed / MOVEMENT_DIRNAME / f"{day.isoformat()}.csv"
    if not path.is_file():
        return []
    stamped: list[tuple[datetime, dict]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("market") not in MARKET_LABEL or r.get("market") in LADDER_ONLY_IN_CAPTURE:
                continue
            moment = _moment(r.get("captured_at"))
            if moment is not None:
                stamped.append((moment, r))

    def key(r: dict) -> tuple:
        return r.get("home_team"), r.get("away_team"), r.get("market")

    first: dict[tuple, datetime] = {}
    for moment, r in stamped:
        if key(r) not in first or moment < first[key(r)]:
            first[key(r)] = moment
    return [r for moment, r in stamped if moment == first[key(r)]]


def best_price(rows: list[dict], home: str, away: str, market: str, selection: str, line: float | None = None) -> float | None:
    best = None
    for r in rows:
        if r.get("home_team") != home or r.get("away_team") != away or r.get("market") != market:
            continue
        if str(r.get("selection", "")).lower() != selection:
            continue
        if line is not None:
            try:
                if abs(float(r.get("line") or 0) - line) > 1e-6:
                    continue
            except ValueError:
                continue
        try:
            price = float(r["american_odds"])
        except (KeyError, ValueError):
            continue
        best = price if best is None or price > best else best
    return best


def headline_line(rows: list[dict], home: str, away: str, market: str) -> float | None:
    lines = []
    for r in rows:
        if r.get("home_team") == home and r.get("away_team") == away and r.get("market") == market:
            try:
                lines.append(float(r["line"]))
            except (KeyError, ValueError):
                pass
    if not lines:
        return None
    return max(set(lines), key=lines.count)


def ml_pair(rows, home, away):
    h, a = best_price(rows, home, away, "moneyline", "home"), best_price(rows, home, away, "moneyline", "away")
    return {"home": h, "away": a} if h is not None and a is not None else None


def load_model(processed: Path, outputs: Path):
    """The fitted team model, the team-name resolver, the schedule's rest
    fact, and whether that fact may move a price.

    ## Rest moves a price only while its verdict ships

    `b2b` is the schedule fact — the side played the previous league day —
    and the board publishes it as the chip whatever any verdict says. `rest`
    is whether the fact reaches the model, and it is the recorded `team_b2b`
    verdict, read through `verdicts.ships` from the lab's own `data/outputs`
    (falling back to the recorded directory exactly as the card's does).

    This used to feed the fact into every price unconditionally. The card
    applies rest only while `ships("team_b2b", output_dir=outputs)` is true
    (`scripts/run_gameday_card.py`), so once Experiment Refresh's drift PR
    withdrew the policy the card would price every side rested while the
    board kept publishing the adjusted winProb, projGoals, fair odds,
    coverProb, overProb and regulation split, froze them as the day's first
    opinion, and graded straight up on them. Measured on the real history
    with the verdict withdrawn: on 2025-03-02 the card priced Pittsburgh (at
    home, the night after playing) at 0.4370 and the board published 0.4141,
    fair +142; over the 2025-26 regular season, refitted each day as the
    board fits, the flag moved the published winProb by a median 3.6 points
    (max 4.6) in the 358 of 1,312 games with a tired side and flipped the
    projected winner in 39. A withdrawn policy is withdrawn from the public
    page as well, or the page shows a policy nobody stands behind beside a
    pick priced without it.
    """
    try:
        from nhl_betting_lab.data.build_datasets import load_team_games
        from nhl_betting_lab.models.team_model import TeamModel
        from nhl_betting_lab.providers.team_names import build_team_name_map, resolve_team
        from nhl_betting_lab.rest import last_played_dates, played_previous_day
        from nhl_betting_lab.verdicts import ships, source
    except ImportError:
        return None
    games = load_team_games(processed)
    if games.empty:
        return None
    model = TeamModel().fit(games)
    names = build_team_name_map()
    last = last_played_dates(games)
    rest = ships("team_b2b", output_dir=outputs)
    print(
        f"Back-to-back adjustment on the board: team_b2b={'in force' if rest else 'off'} "
        f"(verdict read from {source('team_b2b', output_dir=outputs)})."
    )
    return {
        "model": model,
        "resolve": lambda label: resolve_team(label, names),
        "b2b": lambda team, day: played_previous_day(last, team, day),
        "rest": rest,
    }


def build_board(day: date, lab: Path, history_dir: Path) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    games = schedule_for(day)
    preseason = all(int(g.get("gameType", 1)) == 1 for g in games) if games else day < SEASON_OPENS
    teams: dict[str, dict] = {}
    out_games: list[dict] = []

    card = {}
    card_path = lab / "data" / "outputs" / "gameday_card.json"
    if card_path.is_file():
        card = json.loads(card_path.read_text(encoding="utf-8"))
    candidates = [r for r in card.get("best_bets", []) + card.get("leans", []) + card.get("passes", []) if r.get("market") in MARKET_LABEL]
    prices = read_prices(lab / "data" / "staging") if not preseason else []
    featured = read_prices(lab / "data" / "staging", featured_only=True) if not preseason else []
    opens = earliest_capture(lab / "data" / "processed", day) if not preseason else []
    lab_model = load_model(lab / "data" / "processed", lab / "data" / "outputs") if not preseason else None

    for g in games:
        away, home = g["awayTeam"], g["homeTeam"]
        a, h = away["abbrev"], home["abbrev"]
        teams.setdefault(a, team_entry(a))
        teams.setdefault(h, team_entry(h))
        venue = g.get("venue", {}).get("default", "")
        tv = " / ".join(sorted({b.get("network", "") for b in g.get("tvBroadcasts", []) if b.get("network")})) or "Local / ESPN+"
        row = {
            "id": str(g["id"]), "startUtc": g["startTimeUTC"], "venue": venue,
            "city": g.get("venueLocation", {}).get("default", ""), "tv": tv,
            "away": {"abbr": a, "record": away.get("record", "")}, "home": {"abbr": h, "record": home.get("record", "")},
            "pick": None,
            # Whether this build attached market prices to the game. A null
            # pick used to be the whole story, and the page read every null
            # as "No market clears the edge bar" — including games this build
            # held no price for. Publish Site restores no staged prices, so
            # from opening night that was every regular-season game: 5 of 5
            # published as edge-bar passes while the card held a best bet
            # (MTL @ TOR moneyline home +112, edge 0.110), and the history
            # froze 0 bets for the day. A game nobody priced is not a pass.
            "priced": False,
        }
        if not preseason and lab_model:
            home_key = lab_model["resolve"](f"{home.get('placeName', {}).get('default', '')} {home.get('commonName', {}).get('default', '')}".strip()) or h
            away_key = lab_model["resolve"](f"{away.get('placeName', {}).get('default', '')} {away.get('commonName', {}).get('default', '')}".strip()) or a
            hb, ab = lab_model["b2b"](home_key, day.isoformat()), lab_model["b2b"](away_key, day.isoformat())
            # The chip publishes the schedule fact; the prices see it only
            # while the team_b2b verdict ships (see load_model). This passed
            # hb/ab straight through, so a withdrawn policy kept moving
            # every figure below.
            rest = {"home_b2b": hb and lab_model["rest"], "away_b2b": ab and lab_model["rest"]}
            m = lab_model["model"]
            eh, ea = m.expected_goals(home_key, away_key, **rest)
            ml = m.moneyline_probabilities(home_key, away_key, **rest)
            reg = m.regulation_3_way_probabilities(home_key, away_key, **rest)
            row["home"].update({"projGoals": round(eh, 2), "winProb": round(ml["home"], 4), "b2b": hb})
            row["away"].update({"projGoals": round(ea, 2), "winProb": round(ml["away"], 4), "b2b": ab})
            # Provider rows are keyed by the provider's team strings; match on either.
            provider_home = next((r["home_team"] for r in prices if lab_model["resolve"](r.get("home_team", "")) == home_key), None)
            provider_away = next((r["away_team"] for r in prices if lab_model["resolve"](r.get("away_team", "")) == away_key), None)
            if provider_home and provider_away:
                row["priced"] = True
                cur, opn = ml_pair(prices, provider_home, provider_away), ml_pair(opens, provider_home, provider_away)
                # The open is the game's first line-movement capture
                # (earliest_capture), or it is missing. It used to fall back
                # to the current price, and
                # Publish Site restores no capture, so every "Open" it could
                # publish was the current price under another name: a line
                # that never moved because it was only ever read once.
                row["moneyline"] = {"open": opn, "current": cur, "fair": {"home": to_american(ml["home"]), "away": to_american(ml["away"])}}
                fav_home = ml["home"] >= ml["away"]
                pl = m.puck_line_probabilities(home_key, away_key, line=1.5, **rest)
                row["puckLine"] = {
                    "favorite": h if fav_home else a, "line": -1.5,
                    "price": best_price(prices, provider_home, provider_away, "puck_line", "home" if fav_home else "away", -1.5),
                    "coverProb": round(pl["home_minus" if fav_home else "away_minus"], 4),
                }
                # The line from the featured rows only; a ladder rung is not
                # the line (read_prices). The open total is None while the
                # capture holds nothing but rungs (earliest_capture).
                line = headline_line(featured, provider_home, provider_away, "total_goals")
                if line is not None:
                    tot = m.total_probabilities(home_key, away_key, line=line, **rest)
                    row["total"] = {
                        "open": headline_line(opens, provider_home, provider_away, "total_goals"), "current": line,
                        "overPrice": best_price(prices, provider_home, provider_away, "total_goals", "over", line),
                        "underPrice": best_price(prices, provider_home, provider_away, "total_goals", "under", line),
                        "proj": round(eh + ea + m.overtime_rate, 2), "overProb": round(tot["over"], 4),
                    }
                row["regulation"] = {
                    "home": round(reg["home"], 4), "draw": round(reg["draw"], 4), "away": round(reg["away"], 4),
                    "prices": {s: best_price(prices, provider_home, provider_away, "regulation_3_way", s) for s in ("home", "draw", "away")},
                }
                mine = [c for c in candidates if c.get("home_team") == provider_home and c.get("away_team") == provider_away and c.get("section") != "Passes / notable avoids"]
                if mine:
                    top = max(mine, key=lambda c: float(c.get("edge", 0)))
                    row["pick"] = {
                        "market": MARKET_LABEL[top["market"]], "label": pick_label(top, h, a),
                        "price": int(float(top["american_odds"])), "edgePct": round(float(top["edge"]) * 100, 1),
                    }
        out_games.append(row)

    record = load_record(lab / "data" / "outputs" / "forward_evidence.json")
    # Published so the page can name the gate that ACTUALLY stopped a pick.
    # With nothing allowlisted the card never reaches the edge bar, so saying
    # it failed the bar reports a model judgement where a permission gate is
    # what happened. With markets allowlisted the bar is exactly what stopped
    # it. The page cannot tell which without being told.
    allowlisted = allowlisted_markets(lab)
    notice = None
    if preseason:
        # "and picks" used to be in this sentence and was not true, because
        # the card selects only from allowlisted markets. The allowlist is no
        # longer empty, so the clause is read rather than asserted — and
        # "no demonstrated edge" is NOT read, because approving a market says
        # its prices may be used and says nothing about whether the model
        # beats them.
        gate = (
            f"{len(allowlisted)} market(s) are allowlisted"
            if allowlisted
            else "No market is allowlisted"
        )
        notice = ("Exhibition slate. The model is fitted on regular-season games only and prices nothing before opening night on "
                  "September 29. Tonight shows the schedule; projections and market lines arrive with the first regular-season "
                  f"card. {gate}, and the model has no demonstrated edge.")
    elif not lab_model:
        # This said "the schedule and market lines only". The lines are
        # attached inside the model's branch above, so a board without the
        # model carries none, and the sentence promised what was not there.
        notice = ("The model's game history was not available to this run, so the board shows the schedule only: "
                  "no projection, no market line and no pick.")
    elif out_games and not any(g["priced"] for g in out_games):
        # Said nothing before, while the page printed "No market clears the
        # edge bar" under every game. Cause-neutral on purpose: the prices
        # may be absent (Publish Site restores none) or present and
        # unmatched (a team-name map that resolves nothing). Either way this
        # build priced no game, and that is all it can truthfully say.
        notice = ("No market price reached this build, so no game on the board shows a line or a pick. "
                  "A game here without a pick was not priced, which is not the same as the model passing on it.")
    board = {
        "generatedAt": now, "season": "2026–27", "phase": "preseason" if preseason else "regular",
        "boardDate": day.isoformat(), "notice": notice, "record": record, "teams": teams, "games": out_games,
        "allowlistedMarkets": allowlisted,
    }
    history_dir.mkdir(parents=True, exist_ok=True)
    frozen = history_dir / f"{day.isoformat()}.json"
    if not frozen.exists():  # the day's first published opinion stands
        frozen.write_text(json.dumps(board, indent=1), encoding="utf-8")
    return board


def pick_label(c: dict, home: str, away: str) -> str:
    sel, mk = str(c.get("selection", "")).lower(), c.get("market")
    price = int(float(c["american_odds"]))
    ptxt = f"{price:+d}".replace("-", "−")
    team = home if sel == "home" else away
    if mk == "moneyline":
        return f"{team} {ptxt}"
    if mk == "puck_line":
        line = float(c.get("line") or 0)
        return f"{team} {line:+.1f} {ptxt}".replace("-", "−")
    if mk == "total_goals":
        return f"{sel.capitalize()} {float(c.get('line') or 0):g}"
    if mk == "regulation_3_way":
        return f"{'Draw' if sel == 'draw' else team} in regulation {ptxt}"
    return f"{sel} {ptxt}"


#: The date the forward test is decided (docs/when_this_ends.md). Until
#: then the ledger's return is not published, here or anywhere.
FORWARD_DECISION_DATE = "2027-04-25"


def allowlisted_markets(lab: Path) -> list[str]:
    """What the card may actually select from, read rather than asserted.

    The notice below used to state "no market is allowlisted" as a constant.
    That is a fact about data/manual/staging_provider_policy.json, which
    Cooper changes by signing a receipt, and a page stating it from a string
    keeps stating it afterwards.

    Failure resolves to the empty list, which is the same direction the
    policy loader fails in: every unreadable state there allowlists nothing,
    and the restrictive sentence is the safe one to print when the answer is
    unavailable.
    """
    try:
        from nhl_betting_lab.staging_provider_policy import (
            POLICY_FILENAME,
            load_policy,
        )
    except Exception:
        return []
    try:
        # `load_policy` takes the POLICY FILE, not the directory holding it.
        # Passing the directory returns an invalid policy rather than raising,
        # so the board silently said nothing was allowlisted while twelve
        # markets were — the exact failure this function exists to prevent,
        # arrived at from the other side.
        policy = load_policy(Path(lab) / "data" / "manual" / POLICY_FILENAME)
    except Exception as exc:
        print(f"policy unreadable, board will say nothing is allowlisted: {exc}")
        return []
    return sorted(
        market
        for entry in policy.entries.values()
        for market in entry.required_markets
    ) if policy.allowed_provider_names else []


def load_record(path: Path) -> dict:
    """The forward ledger's SIZE, never its return.

    The site used to read `overall.roi` / `roi_low` / `roi_high` / `clv`.
    None of those keys exist. `forward_evidence.build_forward_report` writes
    `generated_at`, `rows`, `markets`, `unsettleable` and `void`, and each
    entry under `markets` carries its own `roi` / `low` / `high` — there is
    no pooled figure anywhere, and inventing one here would have shown a
    permanently zeroed record instead.

    Publishing a pooled ROI is the thing this function deliberately will not
    do. That number is the pre-registered test decided on 2027-04-25
    (`docs/when_this_ends.md`), and a test whose running total is on a public
    page every morning is a test someone is watching — which is the exact
    dynamic the registration exists to prevent. Its own words: "If a
    mid-season result looks strong, the correct action is nothing."

    So the site reports how far the experiment has got and not how it is
    going: opinions accumulated, markets covered, the span of dates. Those
    are facts about the ledger's size, and none of them is the answer.

    ## The count is wagers, not ledger rows

    The page printed `rows` as "{rows} opinions frozen". A ledger row is one
    BOOK'S QUOTE — the snapshot freezes one row per book — so one selection
    at three books was "3 opinions": about 3.7 rows per opinion on the
    bought card window (2,544,921 quotes over 685,746 wagers), and 180 rows
    from 18 opinions on one real slate. `wagers` is the report's own count
    of one per selection at the best price, the unit docs/when_this_ends.md
    registers. The ledger holds only slates whose games have all finished,
    so it counts opinions on SETTLED slates, never everything frozen, and
    the page says so. `rows` stays in the payload as the per-quote size it
    is; the page does not show it.

    A report written before the wager count existed carries `rows` only.
    Zero rows is zero wagers; any other row count cannot be turned into
    wagers, so `wagers` is None and the page shows no number.

    ## No season record

    `straightUp`, `puckLine` and `totals` were the constants 0–0, 0–0–0 and
    0–0–0 on every path: nothing tallies a season, and nothing grades a puck
    line at all. After 55 settled games (28–27 straight up) the strip still
    read "Straight up 0–0". They are None until something keeps a tally,
    and the page renders None as an absence. Publishing a real tally would
    be a new figure on a public page, which is the owner's decision.
    """
    sealed = {
        "sealed": True,
        "decisionDate": FORWARD_DECISION_DATE,
        "rows": 0,
        "wagers": 0,
        "markets": 0,
        "firstDate": None,
        "lastDate": None,
        "unsettleable": 0,
    }
    empty = {
        "straightUp": None,
        "puckLine": None,
        "totals": None,
        "forward": sealed,
    }
    # No readable report is not an empty ledger. Publish Site restores
    # forward_evidence.json with the run's reports, so a board built without
    # it knows nothing about the ledger, and "No slate settled yet" would be
    # false from the first settled night on. The count is unknown, so none
    # is published: the page reads "Ledger size not reported". (`rows`
    # stays 0: the page never shows it, and the seal pins every failure
    # path to it — tests/test_site_publishes_no_forward_return.py.)
    unknown = {**empty, "forward": {**sealed, "wagers": None}}
    if not path.is_file():
        return unknown
    try:
        fe = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return unknown
    if not isinstance(fe, dict):
        return unknown

    markets = fe.get("markets")
    markets = markets if isinstance(markets, dict) else {}
    firsts = sorted(
        str(entry["first_date"])
        for entry in markets.values()
        if isinstance(entry, dict) and entry.get("first_date")
    )
    lasts = sorted(
        str(entry["last_date"])
        for entry in markets.values()
        if isinstance(entry, dict) and entry.get("last_date")
    )
    rows = int(fe.get("rows", 0) or 0)
    try:
        wagers = int(fe["wagers"])
    except (KeyError, TypeError, ValueError):
        wagers = 0 if rows == 0 else None
    sealed.update(
        rows=rows,
        wagers=wagers,
        markets=len(markets),
        firstDate=firsts[0] if firsts else None,
        lastDate=lasts[-1] if lasts else None,
        unsettleable=int(fe.get("unsettleable", 0) or 0),
    )
    return empty


def settle(day: date, history_dir: Path) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    frozen = history_dir / f"{day.isoformat()}.json"
    base = {"generatedAt": now, "season": "2026–27", "resultsDate": day.isoformat(), "teams": {}, "games": [],
            "summary": {"straightUp": {"w": 0, "l": 0}, "picks": {"w": 0, "l": 0, "p": 0}, "totals": {"w": 0, "l": 0, "p": 0}}}
    if not frozen.exists():
        base["notice"] = "No board was published for this date, so there is nothing to settle."
        return base
    board = json.loads(frozen.read_text(encoding="utf-8"))
    if board.get("phase") == "preseason":
        base.update(phase="preseason", notice="No projections were published for the exhibition games, so there is nothing to settle. "
                    "The first results page lands the morning after opening night, September 30.")
        return base
    finals = {str(g["id"]): g for g in schedule_for(day) if g.get("gameState") in {"OFF", "FINAL"}}
    s = base["summary"]
    for g in board["games"]:
        f = finals.get(g["id"])
        if not f or "projGoals" not in g["home"]:
            continue
        ha, aa = g["home"]["abbr"], g["away"]["abbr"]
        hs, as_ = int(f["homeTeam"].get("score", 0)), int(f["awayTeam"].get("score", 0))
        finish = (f.get("gameOutcome") or {}).get("lastPeriodType", "REG")
        winner = ha if hs > as_ else aa
        proj_winner = ha if g["home"]["projGoals"] >= g["away"]["projGoals"] else aa
        s["straightUp"]["w" if winner == proj_winner else "l"] += 1
        base["teams"].setdefault(ha, team_entry(ha)); base["teams"].setdefault(aa, team_entry(aa))
        row = {"id": g["id"], "startUtc": g["startUtc"], "finish": finish, "projWinner": proj_winner,
               "away": {"abbr": aa, "projGoals": g["away"]["projGoals"], "final": as_},
               "home": {"abbr": ha, "projGoals": g["home"]["projGoals"], "final": hs}}
        tot = g.get("total")
        if tot:
            total_goals = hs + as_
            res = "push" if total_goals == tot["current"] else "over" if total_goals > tot["current"] else "under"
            proj_side = "over" if tot["proj"] > tot["current"] else "under"
            s["totals"]["p" if res == "push" else "w" if res == proj_side else "l"] += 1
            row["total"] = {"line": tot["current"], "proj": tot["proj"], "result": res}
        # What the frozen board said about this game's prices, carried onto
        # the results row so the page can say it. A board frozen before the
        # flag existed carries none. Every version of build_board attached
        # `moneyline` under exactly the condition that now sets `priced`
        # (both provider team strings matched), so its line answers the
        # question for those boards.
        row["priced"] = bool(g["priced"] if "priced" in g else "moneyline" in g)
        pick = g.get("pick")
        if pick:
            outcome = grade_pick(pick, ha, aa, hs, as_, finish)
            s["picks"]["w" if outcome == "win" else "l" if outcome == "loss" else "p"] += 1
            row["pick"] = {**pick, "result": outcome}
        else:
            # A game with no pick settles with no pick. This used to write
            # {"market": "—", "label": "No play", "price": 0, "result":
            # "push"} for every such game, without reading `priced`. Publish
            # Site restores no staged prices, so from opening night that
            # was every regular-season game: 2 of 2 in
            # tests/test_results_never_grade_an_unpriced_game.py, and 5 of 5
            # on the real 2026-09-29 slate. The Results page showed each one
            # under "Model pick" as "No play · — · −0 · Push". That called a
            # game no price reached a model pass, graded a pass that was
            # never a bet, and printed a price nobody quoted. The page reads
            # `priced` and says "Not priced" or "No play". It grades
            # neither.
            row["pick"] = None
        base["games"].append(row)
    return base


def grade_pick(pick: dict, home: str, away: str, hs: int, as_: int, finish: str) -> str:
    label, market = pick["label"], pick["market"]
    margin = hs - as_
    if market == "Moneyline":
        team = label.split()[0]
        return "win" if (team == home and margin > 0) or (team == away and margin < 0) else "loss"
    if market == "Puck line":
        team, line = label.split()[0], float(label.split()[1].replace("−", "-"))
        adj = (margin if team == home else -margin) + line
        return "push" if adj == 0 else "win" if adj > 0 else "loss"
    if market == "Total":
        side, line = label.split()[0].lower(), float(label.split()[1])
        total = hs + as_
        return "push" if total == line else "win" if (total > line) == (side == "over") else "loss"
    if market == "Regulation":
        if finish != "REG":
            return "win" if label.startswith("Draw") else "loss"
        team = label.split()[0]
        return "win" if (team == home and margin > 0) or (team == away and margin < 0) else "loss"
    return "push"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", default=".", help="Root of the nhl-betting-lab checkout.")
    ap.add_argument("--out", default="dist/data", help="Where board.json / results.json / history/ are written.")
    ap.add_argument("--date", default="", help="League date to build (default: today in New York).")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else datetime.now(ET).date()
    out = Path(args.out)
    history = out / "history"
    out.mkdir(parents=True, exist_ok=True)
    board = build_board(today, Path(args.lab), history)
    results = settle(today - timedelta(days=1), history)
    (out / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"board {today}: {len(board['games'])} games ({board['phase']}); results {today - timedelta(days=1)}: {len(results['games'])} settled.")
    print("No odds were fetched, no credit was spent, and no bet was placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
