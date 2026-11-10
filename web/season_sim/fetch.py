"""Inputs for the season simulation, from public endpoints with no credential.

Everything is written under a cache directory so a run can be replayed, and
so one flaky response does not cost the whole build: a file already on disk
is reused for the current-season endpoints only within ``CURRENT_TTL_HOURS``,
and for closed seasons for good.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

NHL = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
MONEYPUCK = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
USER_AGENT = "nhl-betting-lab-site/1.0 (+https://github.com/cooperross399/nhl-betting-lab)"

#: The season being simulated and the three that feed its priors, as the
#: NHL API spells them and as MoneyPuck spells them (the calendar year the
#: season started).
SEASON = "20262027"
PRIOR_SEASONS = ("20252026", "20242025", "20232024")
MONEYPUCK_YEAR = {"20262027": 2026, "20252026": 2025, "20242025": 2024, "20232024": 2023}

CURRENT_TTL_HOURS = 6
ATTEMPTS = 3
TIMEOUT = 40


class FetchError(RuntimeError):
    """A required endpoint never answered."""


def _get(url: str, dest: Path, *, required: bool, ttl_hours: float | None) -> bool:
    """Download ``url`` to ``dest`` unless a fresh copy is there. Returns
    whether a file is now on disk."""
    if dest.exists() and dest.stat().st_size > 50:
        if ttl_hours is None:
            return True
        age = (time.time() - dest.stat().st_mtime) / 3600
        if age < ttl_hours:
            return True
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            if resp.status_code == 404 and not required:
                return dest.exists()
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
        except requests.RequestException as exc:  # pragma: no cover - network
            last = exc
            time.sleep(2 * (attempt + 1))
    if required:
        raise FetchError(f"{url}: {last}")
    return dest.exists()


def _stats_url(kind: str, season: str, sort: str) -> str:
    return (
        f"{STATS}/{kind}/summary?isAggregate=false&isGame=false&limit=-1&sort={sort}"
        f"&cayenneExp=seasonId={season}%20and%20gameTypeId=2"
    )


def fetch_bundle(cache: Path, *, season: str = SEASON, today: date | None = None,
                 availability: bool = True) -> dict:
    """Fetch every input and return the parsed bundle.

    ``today`` dates the standings request (the league date whose standings are
    wanted); it defaults to the current UTC date. ``availability`` also reads
    who is out right now (``fetch_availability``); it never fails the build.
    """
    today = today or datetime.now(timezone.utc).date()
    cache = Path(cache)
    ttl = CURRENT_TTL_HOURS
    # Standings as of today: the team list, division alignment and the
    # season-to-date record. The previous season's final standings are the
    # top-down prior.
    _get(f"{NHL}/standings/{today.isoformat()}", cache / "standings_now.json", required=True, ttl_hours=ttl)
    # The previous season's final standings are read at its last standings
    # day, which the API states; a date inside the playoffs answers with an
    # empty table rather than an error.
    _get(f"{NHL}/standings-season", cache / "standings_season.json", required=True, ttl_hours=ttl)
    seasons_meta = {str(s["id"]): s for s in json.loads((cache / "standings_season.json").read_text())["seasons"]}
    prior_end = seasons_meta.get(PRIOR_SEASONS[0], {}).get("standingsEnd")
    if not prior_end:
        raise FetchError(f"standings-season does not state when {PRIOR_SEASONS[0]} ended")
    _get(f"{NHL}/standings/{prior_end}", cache / "standings_prior.json", required=True, ttl_hours=None)
    now = json.loads((cache / "standings_now.json").read_text())
    prior = json.loads((cache / "standings_prior.json").read_text())
    if len(prior.get("standings", [])) != 32:
        raise FetchError(f"final standings for {PRIOR_SEASONS[0]} list {len(prior.get('standings', []))} teams")
    teams = sorted(t["teamAbbrev"]["default"] for t in now["standings"])
    if len(teams) != 32:
        raise FetchError(f"standings list {len(teams)} teams, not 32")

    rosters, schedules = {}, {}
    for ab in teams:
        _get(f"{NHL}/roster/{ab}/{season}", cache / "roster" / f"{ab}.json", required=True, ttl_hours=ttl)
        _get(f"{NHL}/club-schedule-season/{ab}/{season}", cache / "sched" / f"{ab}.json", required=True, ttl_hours=ttl)
        rosters[ab] = json.loads((cache / "roster" / f"{ab}.json").read_text())
        schedules[ab] = json.loads((cache / "sched" / f"{ab}.json").read_text())

    skaters, goalies = {}, {}
    for s in (season, *PRIOR_SEASONS):
        closed = s != season
        _get(_stats_url("skater", s, "points"), cache / f"skaters_{s}.json", required=closed, ttl_hours=None if closed else ttl)
        _get(_stats_url("goalie", s, "wins"), cache / f"goalies_{s}.json", required=closed, ttl_hours=None if closed else ttl)
        for kind, store in (("skaters", skaters), ("goalies", goalies)):
            path = cache / f"{kind}_{s}.json"
            store[s] = json.loads(path.read_text()).get("data", []) if path.exists() else []

    moneypuck = {}
    for s in (season, *PRIOR_SEASONS):
        year = MONEYPUCK_YEAR[s]
        closed = s != season
        got = {}
        for kind in ("teams", "skaters", "goalies"):
            path = cache / f"mp_{kind}_{year}.csv"
            ok = _get(f"{MONEYPUCK}/{year}/regular/{kind}.csv", path, required=closed, ttl_hours=None if closed else ttl)
            got[kind] = path if ok and path.exists() else None
        moneypuck[s] = got

    return dict(
        today=today, season=season, teams=teams, standings_now=now,
        standings_prior=prior,
        rosters=rosters, schedules=schedules, skaters=skaters, goalies=goalies, moneypuck=moneypuck,
        availability=fetch_availability(cache, teams) if availability else None,
    )


#: Daily Faceoff's pages: each club's line combinations (its injured-reserve
#: group names who is out) and tonight's starting goalies. The lab already
#: reads both (``nhl_betting_lab.data.line_combinations`` and
#: ``.starting_goalies``); the sim reads them for availability only.
DF_TEAM_PAGE = "https://www.dailyfaceoff.com/teams/{slug}/line-combinations"
DF_STARTERS_PAGE = "https://www.dailyfaceoff.com/starting-goalies"
DF_SEED_SLUG = "toronto-maple-leafs"
DF_POLITE_SECONDS = 1.0


def _get_text(url: str) -> str:  # pragma: no cover - network
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _current_roster(cache: Path, ab: str) -> list[int] | None:  # pragma: no cover - network
    path = cache / "roster_current" / f"{ab}.json"
    ok = _get(f"{NHL}/roster/{ab}/current", path, required=False, ttl_hours=1)
    data = json.loads(path.read_text()) if ok and path.exists() else None
    if not isinstance(data, dict):
        return None
    return [int(p["id"]) for grp in ("forwards", "defensemen", "goalies")
            for p in data.get(grp) or [] if isinstance(p, dict) and "id" in p]


def fetch_availability(cache: Path, teams: list[str], *, get_text=_get_text, current_roster=_current_roster,
                       polite_seconds: float = DF_POLITE_SECONDS) -> dict:
    """Who is out right now, from free sources with no account. Soft: a source
    that does not answer is left out and named in ``said``.

    * ``current``: each club's CURRENT roster ids from the NHL API
      (``roster/{ab}/current``), or None when it did not answer. The bundle's
      season roster keeps a goalie who has since gone to injured reserve, the
      minors or another club; the current one is today's.
    * ``df_players``: Daily Faceoff's line-combination rows, one per player per
      group, with its injured-reserve group and injury status.
    * ``df_starters``: Daily Faceoff's starting-goalie listings for tonight.
    """
    cache = Path(cache)
    said: list[str] = []
    current: dict[str, list[int] | None] = {}
    for ab in teams:
        try:
            current[ab] = current_roster(cache, ab)
        except Exception as exc:  # noqa: BLE001 - one club's roster
            said.append(f"current roster {ab} not read ({type(exc).__name__})")
            current[ab] = None
    missing = [ab for ab, ids in current.items() if ids is None]
    if missing:
        said.append(f"NHL current roster not read for {', '.join(missing)}")
    try:
        from nhl_betting_lab.data.line_combinations import rows_from_page, team_slugs
        from nhl_betting_lab.data.starting_goalies import parse_page
    except ImportError as exc:  # pragma: no cover - PYTHONPATH without src
        said.append(f"Daily Faceoff parsers not importable ({exc})")
        return dict(current=current, df_players=None, df_starters=None, said=said)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    df_players: list[dict] | None = None
    df_starters: list[dict] | None = None
    try:
        seed = get_text(DF_TEAM_PAGE.format(slug=DF_SEED_SLUG))
        slugs = team_slugs(seed)
        df_players, lost = [], []
        for slug in slugs:
            try:
                if slug == DF_SEED_SLUG:
                    html = seed
                else:
                    if polite_seconds > 0:
                        time.sleep(polite_seconds)
                    html = get_text(DF_TEAM_PAGE.format(slug=slug))
                df_players.extend(rows_from_page(html, retrieved_at=stamp))
            except Exception as exc:  # noqa: BLE001 - one club's page
                lost.append(f"{slug} ({type(exc).__name__})")
        if lost:
            said.append(f"Daily Faceoff line combinations not read for {len(lost)} club(s): {', '.join(lost)}")
    except Exception as exc:  # noqa: BLE001 - the site, on a bad day
        said.append(f"Daily Faceoff line combinations not read ({type(exc).__name__}: {exc})")
        df_players = None
    try:
        df_starters = parse_page(get_text(DF_STARTERS_PAGE), retrieved_at=stamp)
    except Exception as exc:  # noqa: BLE001 - the site, on a bad day
        said.append(f"Daily Faceoff starting goalies not read ({type(exc).__name__}: {exc})")
    return dict(current=current, df_players=df_players, df_starters=df_starters, said=said)


#: The first season the award fits rebuild; earlier seasons' games are read
#: only to tell who was still a rookie.
HISTORY_FIRST = "20082009"
ROOKIE_LOOKBACK_FIRST = "20052006"


def _seasons(first: str, last: str) -> list[str]:
    return [f"{y}{y + 1}" for y in range(int(first[:4]), int(last[:4]) + 1)]


def _read_mp_goalies(path: Path | None) -> dict[int, dict]:
    import csv
    if not path or not Path(path).exists():
        return {}
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("situation") != "all":
                continue
            try:
                out[int(r["playerId"])] = dict(xGoals=float(r["xGoals"]), goals=float(r["goals"]), icetime=float(r["icetime"]))
            except (KeyError, ValueError):
                continue
    return out


def fetch_history(cache: Path, seasons: list[str], *, moneypuck_seasons: set[str] | None = None) -> dict[str, dict]:
    """Closed seasons for the award fits: {season: {...}}.

    Each season carries the NHL skater and goalie summaries, birth dates,
    every earlier season's games for each skater (for Calder eligibility),
    which clubs made the playoffs, the season's length, and (for the seasons
    in ``moneypuck_seasons``) MoneyPuck's skater, team and goalie tables.
    Closed seasons never change, so everything is cached for good; nothing
    here is required, and a season whose stats do not arrive is left out.
    """
    cache = Path(cache) / "history"
    moneypuck_seasons = set(moneypuck_seasons or ())
    meta_path = Path(cache).parent / "standings_season.json"
    _get(f"{NHL}/standings-season", meta_path, required=False, ttl_hours=CURRENT_TTL_HOURS)
    try:
        meta = {str(s["id"]): s for s in json.loads(meta_path.read_text())["seasons"]}
    except (OSError, ValueError, KeyError):
        meta = {}
    gp_by: dict[str, dict[int, int]] = {}
    summaries: dict[str, list[dict]] = {}
    for s in _seasons(ROOKIE_LOOKBACK_FIRST, max(seasons)):
        path = cache / f"skaters_{s}.json"
        if _get(_stats_url("skater", s, "points"), path, required=False, ttl_hours=None):
            try:
                summaries[s] = json.loads(path.read_text()).get("data", [])
            except ValueError:
                continue
            gp_by[s] = {int(q["playerId"]): int(q.get("gamesPlayed") or 0) for q in summaries[s]}
    out: dict[str, dict] = {}
    for s in seasons:
        if s not in summaries:
            continue
        goalies_path = cache / f"goalies_{s}.json"
        goalies = []
        if _get(_stats_url("goalie", s, "wins"), goalies_path, required=False, ttl_hours=None):
            try:
                goalies = json.loads(goalies_path.read_text()).get("data", [])
            except ValueError:
                goalies = []
        bios_path = cache / f"bios_{s}.json"
        born: dict[int, str] = {}
        bios_url = (f"{STATS}/skater/bios?isAggregate=false&isGame=false&limit=-1&sort=playerId"
                    f"&cayenneExp=seasonId={s}%20and%20gameTypeId=2")
        if _get(bios_url, bios_path, required=False, ttl_hours=None):
            try:
                born = {int(q["playerId"]): q["birthDate"] for q in json.loads(bios_path.read_text()).get("data", [])
                        if q.get("birthDate")}
            except (ValueError, KeyError, TypeError):
                born = {}
        berths, games, team_pct = {}, 82.0, {}
        end = (meta.get(s) or {}).get("standingsEnd")
        if end:
            st_path = cache / f"standings_{s}.json"
            if _get(f"{NHL}/standings/{end}", st_path, required=False, ttl_hours=None):
                try:
                    table = json.loads(st_path.read_text()).get("standings", [])
                except ValueError:
                    table = []
                flagged = {t["teamAbbrev"]["default"]: (t.get("clinchIndicator") or "") for t in table}
                team_pct = {t["teamAbbrev"]["default"]: float(t.get("pointPctg") or 0) for t in table}
                if any(v and v != "e" for v in flagged.values()):
                    berths = {k: bool(v) and v != "e" for k, v in flagged.items()}
                elif table:
                    ranked = sorted(table, key=lambda t: -float(t.get("pointPctg") or 0))
                    berths = {t["teamAbbrev"]["default"]: i < 16 for i, t in enumerate(ranked)}
                gps = sorted(float(t.get("gamesPlayed") or 0) for t in table)
                if gps:
                    games = gps[len(gps) // 2] or 82.0
        prior = [p for p in summaries if p < s]
        prior_gp: dict[int, list[int]] = {}
        for p in prior:
            for pid, gp in gp_by.get(p, {}).items():
                prior_gp.setdefault(pid, []).append(gp)
        mp = goalie_mp = None
        if s in moneypuck_seasons:
            year = int(s[:4])
            got = {}
            for kind in ("teams", "skaters", "goalies"):
                path = cache / f"mp_{kind}_{year}.csv"
                ok = _get(f"{MONEYPUCK}/{year}/regular/{kind}.csv", path, required=False, ttl_hours=None)
                got[kind] = path if ok and path.exists() else None
            if got["skaters"] and got["teams"]:
                mp = dict(skaters=got["skaters"], teams=got["teams"])
            goalie_mp = _read_mp_goalies(got["goalies"]) or None
        out[s] = dict(season=s, skaters=summaries[s], goalies=goalies, born=born, prior_gp=prior_gp,
                      berths=berths, games=games, team_pct=team_pct, moneypuck=mp, goalie_mp=goalie_mp)
    return out
