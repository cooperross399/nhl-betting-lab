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
    capture's rounds hold the bulk moneyline beside the per-event markets, so
    a moneyline opens at the first round that priced it; every open total and
    puck line is missing, because those rows mix the featured line with the
    ladder's rungs (LADDER_ONLY_IN_CAPTURE).
    Publish Site restores the staged prices: the gameday-state artifact
    carries the data/staging of the Gameday Refresh run it came from. Until
    2026-09-29 it did not, and every regular-season game was published
    unpriced (`priced: false`, no line, no pick). Only the rows for the
    board's own league day are read (todays_rows): the state restored can
    be an earlier day's, and its rows must not price today's games. It still
    restores no line_movement, so there every open is missing. A game this
    build holds no price for says so rather than reading as a pass, and so
    does the next morning's Results page, which grades no game that carried
    no pick. (web/lib/sports.js still says, twice, that Publish Site
    restores none: that file is byte-identical across four repos and is
    revised only in a coordinated drop, so the statement is stale there
    until the next one.)
  * data/processed/team_games.csv + TeamModel: expected goals per side,
    with the back-to-back adjustment only while the recorded `team_b2b`
    verdict ships it — the same verdict, read the same way, as the card.
    Nothing is projected from a table holding fewer games than
    `config.THIN_HISTORY_GAMES`, the line below which Gameday Refresh calls
    its own run degraded (load_model).
  * data/outputs/forward_evidence.json: the forward ledger's SIZE, in wagers.
    Never its return. The page does not show it (owner's call, 2026-10-05).
  * history/settled/YYYY-MM-DD.json: each night's settlement, kept so the
    season record sums every frozen board without re-fetching old finals
    (season_record).
  * data/processed/player_game_logs.csv: the box-score logs, one row per
    player per game, read for the Due List alone (grade_due_list): each
    listed player's goals and assists in the game the frozen board listed
    him for. Never a price, never a stake.

Preseason (gameType 1) is published as schedule only. The models are fitted
on regular-season games and the card excludes exhibitions, so no projection
or pick is invented for them — the page says so instead. That holds per game,
not per night: an exhibition on a night that also holds a regular-season game
(2026-09-29) is published, frozen and settled as schedule only too.

Nothing here fetches odds, spends a credit, or places a bet.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NHL = "https://api-web.nhle.com/v1"
SEASON_OPENS = date(2026, 9, 29)
#: The NHL API's gameType for a regular-season game (1 is preseason, 3 the
#: playoffs). The lab's own `config.REGULAR_SEASON_GAME_TYPE`, spelled out
#: for the reason USER_AGENT gives.
REGULAR_SEASON_GAME_TYPE = 2

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


def league_day(commence_time: object) -> str:
    """The NHL game date of a provider timestamp, as `YYYY-MM-DD`, or "".

    The league's calendar runs on Eastern time whatever the venue's: a 22:00
    Eastern face-off (19:00 Pacific) is 02:00 UTC the next day and still
    that day's game. The staged rows' `date` column is the UTC date of
    `commence_time` and is NOT this — on opening night 286 of the 486 team
    rows carried the next day's date — so the day a row belongs to is read
    from `commence_time` itself. A value with no
    timezone, or none at all, belongs to no day: the row is dropped rather
    than guessed at, because a wrong day here prices a game the row is not
    about.

    A copy of `nhl_betting_lab.season.game_date`, for the reason USER_AGENT
    gives, differing only in that the lab answers a naive or unreadable
    value with its first ten characters (a best guess, for grading) and this
    answers "". tests/test_the_board_prices_only_todays_games.py holds the
    two to each other on every value they read alike.
    """
    text = str(commence_time or "").strip()
    if not text:
        return ""
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if moment.tzinfo is None:
        return ""
    return moment.astimezone(ET).date().isoformat()


def todays_rows(rows: list[dict], day: date) -> list[dict]:
    """The staged rows for `day`'s games and no other day's.

    Until 2026-09-29 Publish Site restored no staged prices; since then it
    does, and that opened this shape (found in review, reproduced through
    main(), never seen live): its 14:45 UTC cron fires before a late
    Gameday run has finished and restores the previous run's state — the
    previous day's card AND the previous day's staging. Joined by team alone
    (build_board looks up the home and the away side independently),
    yesterday's rows priced today's games: a repeat pairing published
    yesterday's moneyline and total as today's, and a team in the same role
    two nights running read `priced: true` with no line and "No market
    clears the edge bar", a model judgement nobody made. The freeze was
    guarded (site_history.built_on_stale_state); the live page was not.
    """
    wanted = day.isoformat()
    return [r for r in rows if league_day(r.get("commence_time")) == wanted]


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

#: Markets whose line-movement rows hold alternate rungs, so none is read as
#: an open. A capture's puck_line rows include `alternate_spreads` and its
#: total_goals rows `alternate_totals`, and since the bulk `spreads` and
#: `totals` joined each round they sit beside the featured line under the
#: same market, captured_at and spelling. The row does not say which is the
#: featured line (only its `fetched_at` tells the two requests apart, see
#: `closing_lines.team_market_rows`), and this page does not read it: the
#: mode over rungs published 4.5 as the open total against a line of 6.0.
#: The moneyline has no ladder, and its open is read.
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

    The moneyline open is the bulk `h2h` the capture has asked for in every
    round since it added the team markets; a day captured before that, or a
    game whose first rounds' bulk request failed, opens at the first round
    that holds it, or prints a dash when none does.
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


class ThinHistory(Exception):
    """The game history on disk is below the floor the lab calls thin."""


def load_model(processed: Path, outputs: Path):
    """The fitted team model, the team-name resolver, the schedule's rest
    fact, and whether that fact may move a price.

    ## A thin history projects nothing

    Raises `ThinHistory` when `team_games.csv` holds fewer games than
    `config.THIN_HISTORY_GAMES`, the line below which Gameday Refresh calls
    its own run degraded ("the models are fitted on a thin history").

    This refused only an empty table. Publish Site restores the newest
    Gameday run that carries the state, whatever its conclusion, and lays
    nothing underneath (`--no-merge`), so after a Gameday run that started
    cold — its restore found nothing, and the fetch caches the 600 oldest
    game ids — the board fitted the model on 600 games from 2023-10-10 to
    2024-01-04, published every projection from it, froze that as the day's
    opinion and graded straight up on it the next morning. Measured on the
    real tables against all 3,936 games: VAN @ EDM home win 0.447 against
    0.623, LAK @ COL 0.495 against 0.601, CAR @ PHI 0.512 against 0.410 and
    BOS @ MIN 0.432 against 0.531, every projected winner flipped. A history
    the lab will not stand behind for its own run is not a public opinion,
    so the board shows the schedule and says why, as it already did for a
    missing history. The restore is unchanged: the state and the reports
    still come from one run
    (tests/test_the_board_refuses_a_thin_history.py).

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
        from nhl_betting_lab.config import THIN_HISTORY_GAMES
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
    if len(games) < THIN_HISTORY_GAMES:
        print(
            f"The game history holds {len(games)} games, fewer than the "
            f"{THIN_HISTORY_GAMES} below which Gameday Refresh calls its run "
            "degraded, so the board projects nothing from it."
        )
        raise ThinHistory(len(games))
    model = TeamModel().fit(games)
    ratings = rate_on_xg(model, games, processed)
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
        "ratings": ratings,
    }


#: The team ratings Publish Site writes in the run that builds the board
#: (`scripts/run_shadow_stats.py --tables-only`), relative to the processed
#: directory. Read as a file, so this builder imports nothing from the shadow
#: package.
SHADOW_RATINGS = "shadow_team_ratings.json"


def rate_on_xg(model, games, processed: Path) -> str:
    """Rate the board's teams on expected goals and goaltending, as Cooper
    asked on 2026-10-05: built into the site's numbers, not shown beside them.

    The same ratings the card's team markets are priced on
    (`models.team_ratings.apply_xg_ratings`), so the board's probabilities and
    the card's picks come from one model. Returns "xg", or "goals" with a
    `::warning::` when the ratings file is missing, unreadable or stale; then
    the board publishes the goals ratings rather than nothing.
    """
    from nhl_betting_lab.models.team_ratings import apply_xg_ratings

    ratings, detail = apply_xg_ratings(model, games, processed)
    if ratings == "xg":
        print(f"Board ratings: {detail}.")
    else:
        print(f"::warning::{detail}; the board is rated on goals.")
    return ratings


def _site_history():
    """`web/site_history.py`, loaded from beside this file. It owns the rule
    for when a board may be frozen, and freezes the same file after this
    script does: one copy of the rule, so the two freezes cannot disagree."""
    path = Path(__file__).resolve().with_name("site_history.py")
    spec = importlib.util.spec_from_file_location("_nhl_site_history", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    drought_listed = read_drought_list(lab, day) if not preseason else None
    prices = todays_rows(read_prices(lab / "data" / "staging"), day) if not preseason else []
    featured = todays_rows(read_prices(lab / "data" / "staging", featured_only=True), day) if not preseason else []
    opens = earliest_capture(lab / "data" / "processed", day) if not preseason else []
    lab_model, thin = None, False
    if not preseason:
        try:
            lab_model = load_model(lab / "data" / "processed", lab / "data" / "outputs")
        except ThinHistory:
            thin = True

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
            # held no price for. Until 2026-09-29 Publish Site restored no
            # staged prices, so from opening night that would have been every
            # regular-season game: 5 of 5 published as edge-bar passes while
            # the card held a best bet (MTL @ TOR moneyline home +112, edge
            # 0.110), and the history froze 0 bets for the day. A game nobody
            # priced is not a pass — and a build holding another day's rows
            # (todays_rows) has priced nobody either.
            "priced": False,
            # Whether this game is anything but a regular-season game. The
            # night used to be judged once, `preseason` above, and this loop
            # never read the game's own gameType: on a mixed night (one
            # regular-season game and one exhibition, 2026-09-29) the board
            # read "regular", projected and priced BOTH, froze both, and
            # settle() graded both the next morning. The models are fitted on
            # regular-season games and the card never prices an exhibition,
            # so an exhibition is published as schedule only, whatever else
            # is on the night — no projection, no line, no pick — and with no
            # projGoals, settle() and site_history's bet count pass it by.
            # The game type is published so the page can say why the game
            # carries nothing, which "Not priced" would misstate. A game with
            # no type reads as preseason, as `preseason` above reads it.
            "gameType": int(g.get("gameType", 1)),
        }
        if row["gameType"] == REGULAR_SEASON_GAME_TYPE:
            # Every regular-season game carries the list, empty when nobody
            # qualifies or the game has started. It needs the card's list
            # and nothing of the model, so it is written even on a board
            # that could not project.
            begun = (_moment(g["startTimeUTC"]) or datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc)
            row["drought"] = drought_for_game(drought_listed, h, a, begun)
        if not preseason and lab_model and row["gameType"] == REGULAR_SEASON_GAME_TYPE:
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
                # A best bet first, and a lean only on a game with none; the
                # pick says which it is. This took the highest edge among
                # every row but the passes and set no `kind`, and the page
                # reads a pick without one as a bet. So a lean was headed
                # "Best bet", counted in the strip and in history/index.json's
                # `bets`, and graded into the Results record. A lean's edge
                # can be the game's largest precisely because what stopped it
                # was not the edge (a stake-excluded market, a rung that
                # one-stake-per-outcome demoted), so it also displaced the
                # game's real best bet. Pinned by
                # tests/test_a_lean_is_never_published_as_a_best_bet.py.
                mine = [c for c in candidates if c.get("home_team") == provider_home and c.get("away_team") == provider_away]
                for section, kind in (("Best bets", "bet"), ("Leans", "lean")):
                    rows = [c for c in mine if c.get("section") == section]
                    if rows:
                        top = max(rows, key=lambda c: float(c.get("edge", 0)))
                        row["pick"] = {
                            "kind": kind, "market": MARKET_LABEL[top["market"]], "label": pick_label(top, h, a),
                            "price": int(float(top["american_odds"])), "edgePct": round(float(top["edge"]) * 100, 1),
                            **pick_side_and_line(top),
                        }
                        break
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
    elif thin:
        # The history was there, and too thin to stand behind (load_model):
        # "not available" would misstate why nothing is projected.
        notice = ("The model's game history on this run is too thin to project from, so the board shows the schedule only: "
                  "no projection, no market line and no pick.")
    elif not lab_model:
        # This said "the schedule and market lines only". The lines are
        # attached inside the model's branch above, so a board without the
        # model carries none, and the sentence promised what was not there.
        notice = ("The model's game history was not available to this run, so the board shows the schedule only: "
                  "no projection, no market line and no pick.")
    elif out_games and not any(g["priced"] for g in out_games):
        # Said nothing before, while the page printed "No market clears the
        # edge bar" under every game. Cause-neutral on purpose: the prices
        # may be absent (a failed fetch; until 2026-09-29 Publish Site
        # restored none), present and unmatched (a team-name map that
        # resolves nothing), or present and another league day's
        # (todays_rows). Either way this build priced no game for this day,
        # and that is all it can truthfully say — "reached this build" alone
        # was untrue on the build todays_rows was written for, where
        # hundreds of yesterday's rows had.
        notice = ("No market price for this league day reached this build, so no game on the board shows a line or a pick. "
                  "A game here without a pick was not priced, which is not the same as the model passing on it.")
    board = {
        "generatedAt": now, "season": "2026–27", "phase": "preseason" if preseason else "regular",
        "boardDate": day.isoformat(), "droughtNote": drought_note(lab, drought_listed is not None), "droughtWindow": drought_window(lab),
        "notice": notice, "record": record, "teams": teams, "games": out_games,
        "allowlistedMarkets": allowlisted,
        # What the projections are rated on (rate_on_xg): "xg", "goals" when
        # the play-by-play table was not usable, None when nothing was projected.
        "ratings": lab_model["ratings"] if lab_model else None,
        # When the Gameday card this board was built from was generated; None
        # when no card was restored. A board built on an earlier day's card is
        # shown but not frozen (web/site_history.py::built_on_stale_state).
        "cardGeneratedAt": card.get("generated_at") or None,
    }
    history_dir.mkdir(parents=True, exist_ok=True)
    frozen = history_dir / f"{day.isoformat()}.json"
    if _site_history().built_on_stale_state(board):
        print(f"history/{frozen.name}: not frozen; this board was built on a card generated "
              f"{board['cardGeneratedAt'] or 'never'}, not today.")
    elif not frozen.exists():  # the day's first published opinion stands
        frozen.write_text(json.dumps(board, indent=1), encoding="utf-8")
    return board


#: The rule in one sentence (Cooper, 2026-10-07 evening; it replaces the flat
#: 5-game rule shipped in #307). Two bars, and a drought at EITHER lists him.
DROUGHT_RULE_SENTENCE = ("Cooper's Due List, an unstaked list he picks from: a skater with 70+ points, 30+ goals or 30+ assists "
                         "last regular season whose drought in that category has reached either bar, the tier bar his total sets "
                         "(points 100+ → 3, 85-99 → 4, 70-84 → 5; goals 40+ → 3, 35-39 → 4, 30-34 → 5; assists 60+ → 3, 45-59 → 4, "
                         "30-44 → 5) or his own equal-surprise bar, the shortest drought with no more than a 5% chance at his "
                         "last-season hit rate.")

#: What a listed row carries beyond the #307 fields, as the card's
#: drought_list.json spells it -> as this board spells it. Each is read, never
#: computed here, and is null when the row lacks it (a list written by the
#: flat-rule card, or a field the lab could not fill).
DROUGHT_BAR_FIELDS = (("tier_bar", "tierBar"), ("surprise_bar", "surpriseBar"), ("one_in", "oneIn"))
DROUGHT_RATE_FIELDS = (("hit_rate", "hitRate"), ("rarity", "rarity"))
DROUGHT_RULES = frozenset({"tier", "surprise", "both"})


def _whole(value: object) -> int | None:
    """An integer field, or None: a blank, NaN, infinite or unreadable value is nothing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def _real(value: object) -> float | None:
    """A float field, or None: a blank, NaN, infinite or unreadable value is nothing.

    An infinity is refused because json.dumps would write it as `Infinity`,
    which the browser's JSON.parse rejects, and the board would not load.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def cell_record(source: object) -> dict | None:
    """The band's measured record in percent, or None when the lab gave none.

    The card writes `cell_record` as {wagers, roi, ci_low, ci_high} (fractions,
    from data/outputs/drought_rule_backtest.json, card window, both seasons)
    or null when that file lacks the cell. Here it is {wagers, returnPct,
    lowPct, highPct}, the three figures as percents rounded to one place, and
    a record missing any of the four is None rather than a half-record.

    The keys are not spelled roiPct / ciLowPct / ciHighPct, which is how the
    FORWARD ledger's return would be spelled on the page, and
    tests/test_site_publishes_no_forward_return.py forbids those spellings on
    Board.dc.html (and `roi` / `low` / `high` as keys anywhere on the board).
    That seal is on the pre-registered forward test; this cell is the
    historical backtest's, the same measurement `droughtNote` already prints,
    and its keys say so rather than borrowing the sealed ones.
    """
    if not isinstance(source, dict):
        return None
    wagers = _whole(source.get("wagers"))
    figures = [_real(source.get(key)) for key in ("roi", "ci_low", "ci_high")]
    if wagers is None or any(figure is None for figure in figures):
        return None
    pct = [round(figure * 100, 1) for figure in figures]
    return {"wagers": wagers, "returnPct": pct[0], "lowPct": pct[1], "highPct": pct[2]}


def read_drought_list(lab: Path, day: date) -> dict | None:
    """The card's Due List for `day`, or None when this build holds none for it.

    The card writes it (data/outputs/drought_list.json) and Publish Site restores
    it with the rest of `gameday-reports`; the site imports nothing from the card.
    A list built for another day is never shown on this one.
    """
    path = lab / "data" / "outputs" / "drought_list.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("day") != day.isoformat() or not isinstance(payload.get("rows"), list):
        return None
    return payload


def drought_window(lab: Path) -> str | None:
    """The seasons the cell records were measured on, as the page's label ("2024-26"), read from the backtest file.

    The label spans the first season start to the last season's end, taken
    from the card-window buckets of data/outputs/drought_rule_backtest.json
    (their `season` is the start year; "both" is the pooled bucket). None when
    the file is missing, unreadable or names no season; the page then prints
    the cell record with no window named rather than a season it was not
    measured on.
    """
    path = lab / "data" / "outputs" / "drought_rule_backtest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        starts = sorted({int(b["season"]) for b in payload["buckets"]
                         if b.get("window") == "card" and str(b.get("season")).isdigit()})
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not starts:
        return None
    return f"{starts[0]}-{str(starts[-1] + 1)[-2:]}"


def drought_note(lab: Path, listed: bool) -> str:
    """One sentence above each game's list: the rule and the backtest headline, read from its file."""
    try:
        from nhl_betting_lab.drought_rule import backtest_headline
        headline = backtest_headline(lab / "data" / "outputs")
    except ImportError:
        headline = "Backtest headline unavailable: the lab's package could not be imported."
    note = f"{DROUGHT_RULE_SENTENCE} {headline}"
    if not listed:
        note += " The card's list for this day did not reach this build, so no game shows one."
    return note


def drought_for_game(listed: dict | None, home: str, away: str, started: bool) -> list[dict]:
    """The listed players of one game, in the card's order, in the shape web/SCHEMA.md names.

    A game that has started lists nobody (the puck-drop guard). A price the card
    did not stage stays null; nothing is filled in. The same holds for the bars,
    the hit rate, the rarity, the rule, the band and the cell record: each is
    the card's figure or null, never computed or guessed here, so a list the
    flat-rule card wrote (no such fields) still publishes, with nulls.
    """
    if not listed or started:
        return []
    out = []
    for r in listed["rows"]:
        if r.get("home_team") != home or r.get("away_team") != away:
            continue
        odds = r.get("american_odds")
        rule, band = r.get("rule"), r.get("band")
        out.append({
            "player": r.get("player"), "playerId": r.get("player_id"), "team": r.get("team"),
            "market": r.get("market"), "line": r.get("line"), "lastSeason": r.get("last_season"),
            "drought": r.get("drought"),
            "price": None if odds is None else (int(odds) if float(odds).is_integer() else float(odds)),
            "book": (r.get("book") or None) if odds is not None else None,
            "heavyJuice": bool(r.get("heavy_juice")),
            **{site: _whole(r.get(card)) for card, site in DROUGHT_BAR_FIELDS},
            **{site: _real(r.get(card)) for card, site in DROUGHT_RATE_FIELDS},
            "rule": rule if isinstance(rule, str) and rule in DROUGHT_RULES else None,
            "band": band if isinstance(band, str) and band else None,
            "cellRecord": cell_record(r.get("cell_record")),
        })
    return out


def pick_side_and_line(c: dict) -> dict:
    """What the page's live status needs to judge a pick against the score.

    `side` is the candidate's own selection (home, away, over, under; a
    regulation draw has none) and `line` the total's or puck line's number.
    Without them the live status reads "unavailable" (web/lib/live.js
    `pickStatus`). Nothing is inferred from the label.
    """
    sel = str(c.get("selection", "")).lower()
    line = c.get("line")
    try:
        line = float(line) if c.get("market") in ("total_goals", "puck_line") and line not in (None, "") else None
    except (TypeError, ValueError):
        line = None
    if line is not None and line != line:  # NaN from a CSV-borne blank
        line = None
    return {"side": sel if sel in ("home", "away", "over", "under") else None, "line": line}


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
    entry under `markets` carries its own `roi` / `low` / `high` — the site
    reads no pooled figure, and inventing one here would have shown a
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


def settle(day: date, history_dir: Path, *, processed: Path | None = None) -> dict:
    """Yesterday's frozen board, graded: results.json.

    `processed` is the lab's data/processed, read only for the Due List's
    box-score counts (grade_due_list); without it every listed player waits
    for a box score, and none is voided.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    frozen = history_dir / f"{day.isoformat()}.json"
    base = {"generatedAt": now, "season": "2026–27", "resultsDate": day.isoformat(), "teams": {}, "games": [],
            "summary": {"straightUp": {"w": 0, "l": 0}, "picks": {"w": 0, "l": 0, "p": 0},
                        "leans": {"w": 0, "l": 0, "p": 0}, "totals": {"w": 0, "l": 0, "p": 0}}}
    if not frozen.exists():
        base["notice"] = "No board was published for this date, so there is nothing to settle."
        return base
    board = json.loads(frozen.read_text(encoding="utf-8"))
    if board.get("phase") == "preseason":
        base.update(phase="preseason", notice="No projections were published for the exhibition games, so there is nothing to settle. "
                    "The first results page lands the morning after opening night, September 30.")
        return base
    shown = board.get("games") or []
    schedule_only = bool(shown) and not any("projGoals" in (g.get("home") or {}) for g in shown)
    # The Due List needs the card's list and nothing of the model, so a board
    # that carried it is graded on it even where the model projected nothing.
    carries_list = any("drought" in g for g in shown if isinstance(g, dict))
    if schedule_only:
        # A regular-season board frozen without the model (build_board's
        # schedule-only notice) grades nothing below, and this set no notice,
        # so the page fell back to "No games were settled for this date."
        # with Straight up 0–0 about a slate that was played to a final: in
        # the failure-shape audit's replay, 0 of 10 finals on 2026-10-08
        # after one failed state listing froze the schedule alone. What was
        # published had nothing to settle, and that is what the page says.
        base["notice"] = ("The board published for this date showed the schedule only, with no projection, "
                          "so there is nothing to settle.")
        if not carries_list:
            return base
    finals = {str(g["id"]): g for g in schedule_for(day) if g.get("gameState") in {"OFF", "FINAL"}}
    if carries_list:
        base["dueList"] = grade_due_list(board, finals, processed)
    if schedule_only:
        return base
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
            # The record is the best bets'. A lean is judged on its own row
            # and kept out of it: it was recorded, not staked. A pick frozen
            # before `kind` existed reads as a bet, as site_history.py and
            # the page read it.
            # Leans keep their own tally, so the season can show how the
            # recorded-not-staked calls did without mixing them into it.
            tally = s["picks"] if pick.get("kind", "bet") == "bet" else s["leans"]
            tally["w" if outcome == "win" else "l" if outcome == "loss" else "p"] += 1
            row["pick"] = {**pick, "result": outcome}
        else:
            # A game with no pick settles with no pick. This used to write
            # {"market": "—", "label": "No play", "price": 0, "result":
            # "push"} for every such game, without reading `priced`. Until
            # 2026-09-29 Publish Site restored no staged prices, so from
            # opening night that would have been every regular-season game: 2 of 2 in
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


#: The box-score table `build_datasets` writes, one row per player per game
#: (`PLAYER_LOGS_FILENAME` there, spelled out for the reason USER_AGENT
#: gives). Publish Site restores it with the rest of data/processed in
#: gameday-state. Read for the Due List alone.
PLAYER_LOGS_FILENAME = "player_game_logs.csv"

#: The Due List's categories, every one over 0.5 (web/SCHEMA.md, games[].drought).
#: Points are goals plus assists.
DUE_LIST_MARKETS = ("points", "goals", "assists")

#: The line a Due List entry is graded against when the frozen entry carries
#: none: the rule's own, over 0.5.
DUE_LIST_LINE = 0.5


def _count(value: object) -> int:
    """A box-score count as the logs spell it; a blank is nothing scored."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def read_player_counts(processed: Path | None, game_ids: set[str]) -> tuple[dict, dict, set[str]]:
    """Each player's goals, assists and points in the games named, from the box-score logs.

    Returns (by_id, by_name, boxed): `by_id` maps (game id, player id) and
    `by_name` (game id, lowercased player name, team) to the player's counts,
    and `boxed` is the set of game ids the logs hold at least one row for. A
    missing or unreadable file holds no game, which grade_due_list reads as a
    box score that has not arrived, never as a scratch.
    """
    by_id: dict[tuple[str, str], dict] = {}
    by_name: dict[tuple[str, str, str], dict] = {}
    boxed: set[str] = set()
    if processed is None or not game_ids:
        return by_id, by_name, boxed
    path = Path(processed) / PLAYER_LOGS_FILENAME
    if not path.is_file():
        return by_id, by_name, boxed
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                game_id = str(r.get("game_id") or "").strip()
                if game_id not in game_ids:
                    continue
                boxed.add(game_id)
                goals, assists = _count(r.get("goals")), _count(r.get("assists"))
                counts = {"goals": goals, "assists": assists, "points": goals + assists}
                player_id = str(r.get("player_id") or "").strip()
                if player_id:
                    by_id[(game_id, player_id)] = counts
                name = str(r.get("player") or "").strip().lower()
                if name:
                    by_name[(game_id, name, str(r.get("team") or "").strip().upper())] = counts
    except (OSError, UnicodeDecodeError, csv.Error):
        return {}, {}, set()
    return by_id, by_name, boxed


def _due_list_key(entry: dict) -> tuple:
    """One entry per (player, category) a night: the player by id, or by name when the card had none."""
    player_id = entry.get("playerId")
    who = str(player_id) if player_id not in (None, "") else f"name:{str(entry.get('player') or '').strip().lower()}"
    return who, entry.get("market")


def grade_due_list(board: dict, finals: dict, processed: Path | None) -> dict:
    """results.json's `dueList` (its `summary` and `rows`) for one frozen board.

    Every entry the frozen board published is graded, priced or not, against
    the player's final count in his category from the box-score logs: one or
    more over 0.5 wins, none loses (a push cannot happen at 0.5; `p` is kept
    at 0 for shape). The frozen entry is passed through as published, with
    the game's id and the opponent beside it.

    A player with no row in a game the logs hold did not dress: void, no
    count, in neither tally. A game not final, or final but not yet in the
    logs (its box score arrives with the next Gameday Refresh), is result
    null, not counted and not voided, and season_record keeps re-settling
    that night rather than keeping it (due_list_tallies' `pending`), for up
    to DUE_LIST_PATIENCE_DAYS. One entry per (player, category) a night,
    however many times the board lists it. Nothing here is a stake: no
    units, no profit, in any row or tally.
    """
    games = [g for g in board.get("games") or [] if isinstance(g, dict) and "drought" in g]
    by_id, by_name, boxed = read_player_counts(processed, {str(g.get("id")) for g in games if str(g.get("id")) in finals})
    tally = {"w": 0, "l": 0, "p": 0}
    rows: list[dict] = []
    seen: set[tuple] = set()
    for g in games:
        game_id = str(g.get("id"))
        home, away = (g.get("home") or {}).get("abbr"), (g.get("away") or {}).get("abbr")
        for entry in g.get("drought") or []:
            if not isinstance(entry, dict):
                continue
            key = _due_list_key(entry)
            if key in seen:
                continue
            seen.add(key)
            row = {"gameId": game_id, **entry}
            if "opp" not in row:
                team = entry.get("team")
                row["opp"] = away if team == home else home if team == away else None
            row.update(actual=None, result=None)
            if game_id in finals and game_id in boxed:
                counts = by_id.get((game_id, str(entry.get("playerId"))))
                if counts is None:
                    counts = by_name.get((game_id, str(entry.get("player") or "").strip().lower(),
                                          str(entry.get("team") or "").strip().upper()))
                if counts is None:
                    row["result"] = "void"
                elif entry.get("market") in DUE_LIST_MARKETS:
                    actual = counts[entry["market"]]
                    try:
                        line = float(entry.get("line") if entry.get("line") is not None else DUE_LIST_LINE)
                    except (TypeError, ValueError):
                        line = DUE_LIST_LINE
                    result = "push" if actual == line else "win" if actual > line else "loss"
                    tally["w" if result == "win" else "l" if result == "loss" else "p"] += 1
                    row.update(actual=actual, result=result)
            rows.append(row)
    return {"summary": tally, "rows": rows}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def due_list_tallies(rows: list[dict]) -> dict:
    """One night's Due List, summed for the season: w, l, p, the split by
    category, the implied probability of every graded entry's posted price
    (summed, with its count, so nights average correctly), and `pending`,
    every entry still unread (result null): its game not final, or final
    with a box score the logs do not hold yet. The night is kept only once
    that is zero, or once DUE_LIST_PATIENCE_DAYS have passed (season_record).

    Until 2026-10-07 `pending` counted only entries on a game in
    results["games"], the team games the night settled. That is empty on a
    schedule-only board (settle grades no team game there) and never holds
    a game that is not yet final, so on both an ungraded entry held nothing:
    the night was kept two days on with it unread, and read back from the
    cache ever after. An entry is pending by its own result, not by its
    game's place in another tally."""
    out = {"w": 0, "l": 0, "p": 0, "byMarket": {m: {"w": 0, "l": 0} for m in DUE_LIST_MARKETS},
           "impliedSum": 0.0, "impliedCount": 0, "pending": 0}
    for r in rows:
        if not isinstance(r, dict):
            continue
        result = r.get("result")
        if result in ("win", "loss", "push"):
            out["w" if result == "win" else "l" if result == "loss" else "p"] += 1
            if result != "push" and r.get("market") in out["byMarket"]:
                out["byMarket"][r["market"]]["w" if result == "win" else "l"] += 1
            if _is_number(r.get("price")):
                out["impliedSum"] += implied(float(r["price"]))
                out["impliedCount"] += 1
        elif result is None:
            out["pending"] += 1
    return out


def props_tallies(rows: list[dict]) -> dict:
    """One night's props, summed for the season, by the row shape web/SCHEMA.md
    names (`props.rows[]`: kind, units, result, profitUnits): best bets with
    their profit in units, and leans apart, with none. A void or ungraded row
    is in neither; a pass is never a record."""
    out = {"bets": {"w": 0, "l": 0, "p": 0, "units": 0.0}, "leans": {"w": 0, "l": 0, "p": 0}}
    for r in rows:
        if not isinstance(r, dict) or r.get("result") not in ("win", "loss", "push"):
            continue
        kind = r.get("kind")
        if kind not in ("bet", "lean"):
            continue
        tally = out["bets"] if kind == "bet" else out["leans"]
        tally["w" if r["result"] == "win" else "l" if r["result"] == "loss" else "p"] += 1
        if kind == "bet" and _is_number(r.get("profitUnits")):
            tally["units"] += float(r["profitUnits"])
    return out


def night_record(results: dict) -> dict:
    """What the season keeps of one settled night: its settled game count and
    summary, the Due List's tallies when the frozen board carried the list,
    and the props tallies when the night's props block was published (status
    "ok", as the page reads a block without one)."""
    games = results.get("games") or []
    night = {"games": len(games), "summary": results.get("summary") or {}}
    due = results.get("dueList")
    if isinstance(due, dict):
        night["dueList"] = due_list_tallies(due.get("rows") or [])
    props = results.get("props")
    if isinstance(props, dict) and props.get("status", "ok") == "ok" and isinstance(props.get("rows"), list):
        night["props"] = props_tallies(props["rows"])
    return night


#: Where each night's settlement is kept, inside the history Publish Site
#: restores and uploads, so the season record reads an old night once.
SETTLED_DIR = "settled"

#: A frozen board's name: one per league day. Slot copies are not settled.
FROZEN_BOARD = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")

SEASON_KEYS = ("straightUp", "picks", "leans", "totals")

#: How long a night with a Due List entry still unread (result null) is
#: settled again each run rather than kept: the forward ledger's rule for a
#: game with no result (`nhl_betting_lab.forward_evidence.PATIENCE_DAYS`,
#: spelled out here for the reason USER_AGENT gives). Past it the night is
#: kept with the entry uncounted, in neither tally, as a void is; so a
#: postponed game, a box score build_datasets dropped, or a category the
#: list does not grade can hold a night out of the cache for two weeks and
#: no longer. While a night is held it is settled through the live schedule,
#: and a day that schedule cannot answer for is that run's `missingNights`,
#: as every night under two days old already is.
DUE_LIST_PATIENCE_DAYS = 14


def _kept_night(path: Path) -> dict | None:
    """A night read from history/settled, or None when none is kept or the file cannot be read."""
    if not path.is_file():
        return None
    try:
        night = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return night if isinstance(night, dict) else None


def _kept_before_the_list_was_graded(night: dict, frozen: Path) -> bool:
    """A night kept without a `dueList` while its frozen board carries the list.

    season_record wrote `{resultsDate, games, summary}` until 2026-10-07, and
    boards have carried `games[].drought` since #307 merged that morning, so
    a night cached between the two holds no Due List tallies and, read back
    as is, would keep every entry its board published out of the season for
    good. Such a night is settled again and the cache rewritten.
    """
    if "dueList" in night:
        return False
    try:
        board = json.loads(frozen.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(board, dict):
        return False
    return any(isinstance(g, dict) and "drought" in g for g in board.get("games") or [])


def season_record(today: date, history_dir: Path, latest: dict, *, processed: Path | None = None) -> dict:
    """The season so far: every frozen board before `today`, settled and summed.

    `latest` is the night this run just settled (yesterday), used as is. Any
    other night is read from `history/settled/<day>.json` when one is kept,
    and otherwise settled now and kept once it is at least two days old,
    when every game on it has finished. A night whose finals cannot be
    fetched is left out and counted in `missingNights`, never counted as
    0–0, and the next run tries it again.

    Before any night has settled the tallies are left out altogether, not
    published as 0–0. results.json carries this object as `seasonRecord`,
    and on opening morning it read `picks {w:0, l:0, p:0}` with `nights: 0`:
    a record nobody had counted, which the page happened not to show.

    ## The Due List and the props, kept apart and never staked

    Each night is kept as `night_record` shapes it. `dueList` sums every
    graded Due List entry on every frozen board that carried the list
    (`dueList {w, l, p, nights, byMarket, impliedPct}`; the board's record
    takes the first four): no units, because nothing on it is staked. A
    night counts toward it when its board carried the list and the night
    settled (a game graded, or an entry graded); a night with an entry still
    unread (its game not final, or final with no box score in the logs yet)
    is settled again next run and kept only once nothing waits, or once it
    is DUE_LIST_PATIENCE_DAYS old, whichever is first. A night kept before
    the list was graded (no `dueList` in the cache, `drought` on its frozen
    board) is settled again once and the cache rewritten, so no night the
    boards have carried the list on is read back without it; a kept night
    that cannot be read is settled again the same way. `props` and `propLeans` sum each
    settled night's published props rows, best bets with their units and
    leans without (`props {w, l, p, units, nights}`, `propLeans {w, l, p,
    nights}`), and a lean is never in `props`. All three are absent until a
    night that carried them has settled, as the four tallies are.
    """
    tally = {key: {"w": 0, "l": 0} if key == "straightUp" else {"w": 0, "l": 0, "p": 0}
             for key in SEASON_KEYS}
    due = {"w": 0, "l": 0, "p": 0, "nights": 0, "byMarket": {m: {"w": 0, "l": 0} for m in DUE_LIST_MARKETS},
           "impliedSum": 0.0, "impliedCount": 0}
    props = {"w": 0, "l": 0, "p": 0, "units": 0.0, "nights": 0}
    prop_leans = {"w": 0, "l": 0, "p": 0, "nights": 0}
    kept = history_dir / SETTLED_DIR
    nights, missing, first, last = 0, 0, None, None
    for path in sorted(history_dir.glob("*.json")):
        m = FROZEN_BOARD.match(path.name)
        if not m:
            continue
        day = date.fromisoformat(m[1])
        if day >= today:
            continue
        cached = kept / path.name
        kept_night = _kept_night(cached)
        if kept_night is not None and _kept_before_the_list_was_graded(kept_night, path):
            kept_night = None
        if day.isoformat() == latest.get("resultsDate"):
            night = night_record(latest)
        elif kept_night is not None:
            night = kept_night
        else:
            try:
                settled = settle(day, history_dir, processed=processed)
            except (OSError, ValueError, KeyError):
                missing += 1
                continue
            night = night_record(settled)
        night_due = night.get("dueList") if isinstance(night.get("dueList"), dict) else None
        waiting = bool(night_due and night_due.get("pending")) and day > today - timedelta(days=DUE_LIST_PATIENCE_DAYS)
        if day <= today - timedelta(days=2) and kept_night is None and not waiting:
            kept.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps({"resultsDate": day.isoformat(), **night}, indent=1), encoding="utf-8")
        graded_due = bool(night_due) and sum(int(night_due.get(k) or 0) for k in ("w", "l", "p")) > 0
        if night_due and (night["games"] or graded_due):
            due["nights"] += 1
            for k in ("w", "l", "p"):
                due[k] += int(night_due.get(k) or 0)
            for market, split in (night_due.get("byMarket") or {}).items():
                if market in due["byMarket"] and isinstance(split, dict):
                    for k in ("w", "l"):
                        due["byMarket"][market][k] += int(split.get(k) or 0)
            due["impliedSum"] += float(night_due.get("impliedSum") or 0.0)
            due["impliedCount"] += int(night_due.get("impliedCount") or 0)
        night_props = night.get("props") if isinstance(night.get("props"), dict) else None
        if night_props:
            props["nights"] += 1
            prop_leans["nights"] += 1
            for k in ("w", "l", "p"):
                props[k] += int((night_props.get("bets") or {}).get(k) or 0)
                prop_leans[k] += int((night_props.get("leans") or {}).get(k) or 0)
            props["units"] += float((night_props.get("bets") or {}).get("units") or 0.0)
        if not night["games"]:
            continue
        nights += 1
        first = first or day.isoformat()
        last = day.isoformat()
        for key in SEASON_KEYS:
            for k, v in (night["summary"].get(key) or {}).items():
                if k in tally[key]:
                    tally[key][k] += int(v)
    span = {"nights": nights, "firstDate": first, "lastDate": last, "missingNights": missing}
    season = {**tally, **span} if nights else span
    if due["nights"]:
        season["dueList"] = {"w": due["w"], "l": due["l"], "p": due["p"], "nights": due["nights"], "byMarket": due["byMarket"]}
        if due["impliedCount"]:
            season["dueList"]["impliedPct"] = round(100 * due["impliedSum"] / due["impliedCount"], 1)
    if props["nights"]:
        season["props"] = {**props, "units": round(props["units"], 2)}
        season["propLeans"] = prop_leans
    return season


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
    processed = Path(args.lab) / "data" / "processed"
    results = settle(today - timedelta(days=1), history, processed=processed)
    season = season_record(today, history, results, processed=processed)
    results["seasonRecord"] = season
    # The board's record is the season's. Untallied (no settled night yet)
    # stays None, which the page renders as an absence, never 0–0.
    if season["nights"]:
        board["record"].update({key: season[key] for key in SEASON_KEYS}, season=season)
    # The Due List's and the props' season lines, absent until a night that
    # carried them has settled (season_record). The Due List's record is a
    # count and nothing else: no units, on the board or on the page.
    if "dueList" in season:
        board["record"]["dueList"] = {k: season["dueList"][k] for k in ("w", "l", "p", "nights")}
        if isinstance(results.get("dueList"), dict):
            results["dueList"]["season"] = season["dueList"]
    if "props" in season:
        board["record"]["props"] = season["props"]
        board["record"]["propLeans"] = season["propLeans"]
        if isinstance(results.get("props"), dict):
            results["props"]["seasonLeans"] = season["propLeans"]
            results["props"].setdefault("season", season["props"])
    (out / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"board {today}: {len(board['games'])} games ({board['phase']}); results {today - timedelta(days=1)}: {len(results['games'])} settled.")
    print("No odds were fetched, no credit was spent, and no bet was placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
