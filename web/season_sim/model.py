"""Team strength ratings and player projections for the season simulation.

Offense for a team is half top-down (last season's goals and expected goals
per game, regressed) and half bottom-up (the sum of projected goals from the
players on its current roster, scaled to league level), plus a quarter-weight
on the roster's relative on-ice xGF impact. Defense is last season's expected
goals against, adjusted for who left and arrived (TOI-weighted on/off 5v5 xGA
impact, shrunk by half), minus the goalie tandem's projected goals saved above
expected. Once the season is under way both are updated toward what the team
has actually done, weighted by games played.

Player rates come from up to four seasons weighted 6/5/3/2 (current season
first), regressed forty games toward a role prior set by ice time, then aged.
Every number is a projection; none is a price.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path

LEAGUE_GPG = 3.08          # goals per team-game excluding shootout deciders, 2025-26
ASSISTS_PER_GOAL = 1.69
REGRESSION = 0.20          # top-down ratings toward the league mean
SHRINK_ONICE = 0.5
K_PLAYER = 40.0            # games of prior in a player's rate
K_GOALIE_MINUTES = 6000.0  # minutes of prior in a goalie's GSAx/60
K_TEAM_UPDATE = 30.0       # games of prior when updating a team toward its season to date
#: How far each team's offense and defense move from this model's own number
#: toward the card's PostHockey-style ratings (shooter-adjusted xG with
#: GSAx(sh), `data/processed/shadow_team_ratings.json`, the file the card's
#: team markets are priced on). 0.5 is the card's own weight for
#: PostHockey's number (`posthockey.BLEND_WEIGHT`), chosen, not measured:
#: scripts/backtest_season_sim.py scores 0 to 1 where the ratings can be
#: rebuilt as of a past date.
PH_WEIGHT = 0.5
#: A ratings file older than the latest game in the standings by more than
#: this many days is ignored rather than blended.
PH_MAX_LAG_DAYS = 3
#: The Calder Trophy's eligibility (NHL rule): under 26 on September 15 of
#: the season, no more than 25 games in any earlier season, and not six or
#: more in each of two earlier seasons.
CALDER_AGE = 26.0
CALDER_MAX_SEASON_GP = 25
CALDER_TWO_SEASON_GP = 6
SEASON_WEIGHTS = (6.0, 5.0, 3.0, 2.0)   # current season, then the three before it

#: Default ice time for a player with no NHL history, by position; a touted
#: prospect on an opening-night roster is usually given more than this.
DEFAULT_TOI = {"F": 11.5, "D": 15.0}


class ModelError(RuntimeError):
    """The inputs cannot support a projection."""


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _age(born: str, asof: date) -> float:
    y, m, d = (int(x) for x in born.split("-"))
    return (asof - date(y, m, d)).days / 365.25


def _read_csv(path: Path | None) -> list[dict]:
    if not path:
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def age_multiplier(age: float, pos: str) -> float:
    """Expected year-over-year change in scoring rate, applied at 1.3x because
    the sample it multiplies is centred about a year in the past."""
    if pos == "D":
        steps = ((22, 0.08), (24, 0.05), (26, 0.03), (29, 0.01), (31, -0.01), (33, -0.03), (35, -0.05), (37, -0.07))
        tail = -0.10
    else:
        steps = ((21, 0.10), (22, 0.08), (23, 0.06), (24, 0.04), (26, 0.02), (28, 0.005), (30, -0.01),
                 (32, -0.03), (34, -0.045), (36, -0.065), (38, -0.09))
        tail = -0.12
    for limit, change in steps:
        if age < limit:
            return 1 + 1.3 * change
    return 1 + 1.3 * tail


def role_prior(skaters_prior: list[dict]) -> dict:
    """Mean goals and assists per game by two-minute ice-time bucket, F and D,
    from the most recent closed season."""
    buckets: dict[str, dict[int, list[float]]] = {"F": defaultdict(lambda: [0.0, 0.0, 0.0]), "D": defaultdict(lambda: [0.0, 0.0, 0.0])}
    for q in skaters_prior:
        if q["gamesPlayed"] < 20:
            continue
        grp = "D" if q["positionCode"] == "D" else "F"
        b = int(q["timeOnIcePerGame"] / 60 // 2) * 2
        row = buckets[grp][b]
        row[0] += q["goals"]; row[1] += q["assists"]; row[2] += q["gamesPlayed"]
    out = {}
    for grp, rows in buckets.items():
        out[grp] = {b: (v[0] / v[2], v[1] / v[2]) for b, v in rows.items() if v[2] > 200}
        if not out[grp]:
            raise ModelError(f"no role prior could be fitted for {grp}")
    return out


def _prior_rates(prior: dict, grp: str, toi: float) -> tuple[float, float]:
    keys = sorted(prior[grp])
    b = min(max(int(toi // 2) * 2, keys[0]), keys[-1])
    if b in prior[grp]:
        return prior[grp][b]
    return prior[grp][min(keys, key=lambda k: abs(k - b))]


# ----------------------------------------------------------------------
# schedule state
# ----------------------------------------------------------------------
def schedule_state(bundle: dict) -> dict:
    """Every regular-season game once, split into played and remaining."""
    games: dict[int, dict] = {}
    for sched in bundle["schedules"].values():
        for g in sched.get("games", []):
            if g.get("gameType") == 2:
                games[g["id"]] = g
    played, remaining = [], []
    for g in sorted(games.values(), key=lambda g: (g["gameDate"], g["id"])):
        home, away = g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"]
        state = g.get("gameState", "FUT")
        if state in ("OFF", "FINAL") and "score" in g["homeTeam"] and "score" in g["awayTeam"]:
            played.append(dict(
                id=g["id"], date=g["gameDate"], home=home, away=away,
                hg=int(g["homeTeam"]["score"]), ag=int(g["awayTeam"]["score"]),
                last=(g.get("gameOutcome") or {}).get("lastPeriodType", "REG"),
            ))
        else:
            remaining.append(dict(id=g["id"], date=g["gameDate"], home=home, away=away,
                                  neutral=bool(g.get("neutralSite"))))
    per_team = {ab: 0 for ab in bundle["teams"]}
    for g in games.values():
        per_team[g["homeTeam"]["abbrev"]] += 1
        per_team[g["awayTeam"]["abbrev"]] += 1
    counts = set(per_team.values())
    if len(counts) != 1:
        raise ModelError(f"uneven schedule: {sorted(counts)} games per team")
    return dict(games_per_team=counts.pop(), played=played, remaining=remaining)


def _team_remaining(state: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for g in state["remaining"]:
        out[g["home"]].append(g)
        out[g["away"]].append(g)
    return out


def _games_before(games: list[dict], until: str | None) -> int:
    if until is None:
        return 0
    if until == "season":
        return len(games)
    return sum(1 for g in games if g["date"] < until)


def _fit_on(until: str | None, day: str) -> bool:
    """Whether a player listed as out until ``until`` can play on ``day``."""
    if until is None:
        return True
    if until == "season":
        return False
    return day >= until


def _remaining_starts(weights: dict, returns: dict, games: list[dict]) -> dict:
    """Expected starts per goalie over ``games``.

    Each game is split by ``weights`` among the goalies fit to play it, so an
    injured goalie starts nothing until his return date and nothing at all when
    he is out for the season. A night with no fit goalie falls back to the
    plain weights.
    """
    starts = dict.fromkeys(weights, 0.0)
    for g in games:
        fit = {k: w for k, w in weights.items() if _fit_on(returns.get(k), g["date"])}
        tot = sum(fit.values())
        if tot <= 0:
            fit, tot = weights, sum(weights.values())
        if tot <= 0:
            continue
        for k, w in fit.items():
            starts[k] += w / tot
    return starts


# ----------------------------------------------------------------------
# the model
# ----------------------------------------------------------------------
def is_rookie(prior_gp: list[int], born: str | None, season: str) -> bool | None:
    """Calder eligibility from earlier seasons' games and the birth date;
    None when the birth date is unknown."""
    if not born:
        return None
    y, m, d = (int(x) for x in born[:10].split("-"))
    sep15 = date(int(season[:4]), 9, 15)
    turns = date(y + int(CALDER_AGE), m, 28 if (m, d) == (2, 29) else d)
    if turns <= sep15:
        return False
    if any(gp > CALDER_MAX_SEASON_GP for gp in prior_gp):
        return False
    return sum(gp >= CALDER_TWO_SEASON_GP for gp in prior_gp) < 2


def load_ph_ratings(path: Path) -> tuple[dict | None, str]:
    """The card's team ratings file, or None and why not."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        teams = data["teams"]
        str(data["last_game_date"])
        for rate in teams.values():
            float(rate["attack"]); float(rate["defence"])
    except FileNotFoundError:
        return None, f"no {Path(path).name}"
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, f"{Path(path).name} could not be read ({exc})"
    if len(teams) < 30:
        return None, f"{Path(path).name} rates {len(teams)} teams"
    return data, "read"


def build_model(bundle: dict, injuries: dict, *, starter_shares: dict, ph_ratings: dict | None = None,
                ph_weight: float | None = None, k_team_update: float | None = None) -> dict:
    """Ratings and projections from a fetched bundle.

    ``injuries`` is the parsed ``data/season_sim/injuries.json``;
    ``starter_shares`` maps team -> {goalie full name: share of starts}.
    ``ph_ratings`` is the parsed ratings file the card prices team markets
    on (``load_ph_ratings``); when given and current, each team's strength
    moves ``ph_weight`` of the way toward it and its own home ice is used.
    """
    ph_weight = PH_WEIGHT if ph_weight is None else ph_weight
    k_team_update = K_TEAM_UPDATE if k_team_update is None else k_team_update
    asof: date = bundle["today"]
    season = bundle["season"]
    seasons = [season, *[s for s in bundle["skaters"] if s != season]]
    weights = dict(zip(seasons, SEASON_WEIGHTS))
    wmax = SEASON_WEIGHTS[0]
    state = schedule_state(bundle)
    remaining_by_team = _team_remaining(state)
    games_total = state["games_per_team"]

    # stats by player id and season
    sk: dict[int, dict[str, dict]] = defaultdict(dict)
    for s, rows in bundle["skaters"].items():
        for q in rows:
            sk[q["playerId"]][s] = q
    gl: dict[int, dict[str, dict]] = defaultdict(dict)
    for s, rows in bundle["goalies"].items():
        for q in rows:
            gl[q["playerId"]][s] = q
    name_to_skater = {q["skaterFullName"]: pid for pid, ss in sk.items() for q in ss.values()}
    name_to_goalie = {q["goalieFullName"]: pid for pid, ss in gl.items() for q in ss.values()}

    prior_season = seasons[1]
    prior = role_prior(bundle["skaters"][prior_season])

    # MoneyPuck tables
    mp_teams: dict[str, dict[tuple[str, str], dict]] = {}
    mp_sk: dict[str, dict[tuple[int, str], dict]] = {}
    mp_g: dict[str, dict[tuple[int, str], dict]] = {}
    for s, files in bundle["moneypuck"].items():
        mp_teams[s] = {(r["team"], r["situation"]): r for r in _read_csv(files["teams"])}
        mp_sk[s] = {(int(r["playerId"]), r["situation"]): r for r in _read_csv(files["skaters"])}
        mp_g[s] = {(int(r["playerId"]), r["situation"]): r for r in _read_csv(files["goalies"])}

    def mpteam(s: str, ab: str, sit: str = "all") -> dict | None:
        table = mp_teams.get(s, {})
        if (ab, sit) in table:
            return table[(ab, sit)]
        if ab == "UTA" and ("ARI", sit) in table:
            return table[("ARI", sit)]
        return None

    # ---------------- rosters, plus injured or unsigned regulars expected back
    rosters: dict[str, dict] = {}
    returns: dict[tuple[str, int], str | None] = {}
    for ab in bundle["teams"]:
        r = bundle["rosters"][ab]
        rosters[ab] = dict(skaters=[], goalies=[])
        for grp in ("forwards", "defensemen"):
            for p in r.get(grp, []):
                rosters[ab]["skaters"].append(dict(
                    id=p["id"], name=f"{p['firstName']['default']} {p['lastName']['default']}",
                    pos=p["positionCode"], age=_age(p["birthDate"], asof), born=p.get("birthDate")))
        for p in r.get("goalies", []):
            rosters[ab]["goalies"].append(dict(
                id=p["id"], name=f"{p['firstName']['default']} {p['lastName']['default']}", age=_age(p["birthDate"], asof)))
    on_roster = {(ab, p["id"]) for ab, r in rosters.items() for p in r["skaters"]}
    on_roster |= {(ab, p["id"]) for ab, r in rosters.items() for p in r["goalies"]}
    unknown: list[str] = []
    for entry in injuries.get("returning", []) + injuries.get("out", []):
        ab = entry["team"]
        if ab not in rosters:
            unknown.append(f"{entry['name']} ({ab}: no such team)")
            continue
        is_goalie = entry.get("pos") == "G"
        pid = (name_to_goalie if is_goalie else name_to_skater).get(entry["name"])
        if pid is None:
            unknown.append(entry["name"])
            continue
        if (ab, pid) not in on_roster:
            if "born" not in entry:
                unknown.append(f"{entry['name']} (not on the {ab} roster and no 'born' date to age him)")
                continue
            if is_goalie:
                rosters[ab]["goalies"].append(dict(id=pid, name=entry["name"], age=_age(entry["born"], asof)))
            else:
                pos = entry.get("pos") or sk[pid][max(sk[pid])]["positionCode"]
                rosters[ab]["skaters"].append(dict(id=pid, name=entry["name"], pos=pos, age=_age(entry["born"], asof),
                                                   born=entry["born"]))
            on_roster.add((ab, pid))
        returns[(ab, pid)] = entry.get("return")

    prospect_toi = {p["name"]: float(p["toi"]) for p in injuries.get("prospects", [])}

    # ---------------- skater projections
    def project_skater(ab: str, p: dict) -> dict:
        s = sk.get(p["id"], {})
        grp = "D" if p["pos"] == "D" else "F"
        num_g = num_a = eff_gp = toi_num = toi_den = avail_num = avail_den = 0.0
        for yr, w in weights.items():
            q = s.get(yr)
            if not q:
                continue
            wn = w / wmax
            num_g += wn * q["goals"]; num_a += wn * q["assists"]; eff_gp += wn * q["gamesPlayed"]
            toi_num += wn * q["gamesPlayed"] * q["timeOnIcePerGame"] / 60; toi_den += wn * q["gamesPlayed"]
            if yr != season:
                avail_num += wn * q["gamesPlayed"]; avail_den += wn * 82
        if toi_den > 0:
            toi = toi_num / toi_den
        else:
            toi = prospect_toi.get(p["name"], DEFAULT_TOI[grp])
        pg, pa = _prior_rates(prior, grp, toi)
        rate_g = (num_g + K_PLAYER * pg) / (eff_gp + K_PLAYER)
        rate_a = (num_a + K_PLAYER * pa) / (eff_gp + K_PLAYER)
        if eff_gp < 10 and p["name"] in prospect_toi:
            rate_g *= 1.15; rate_a *= 1.15
        m = age_multiplier(p["age"], p["pos"])
        rate_g *= m; rate_a *= m
        avail = (avail_num + 30 * 0.88) / (avail_den + 30) if avail_den > 0 else 0.86
        avail = min(avail, 0.955)
        team_left = remaining_by_team.get(ab, [])
        out_games = _games_before(team_left, returns.get((ab, p["id"])))
        ros_gp = max(0.0, min(len(team_left) * avail, len(team_left) - out_games))
        now = s.get(season)
        rookie = is_rookie([q["gamesPlayed"] for yr, q in s.items() if yr != season], p.get("born"), season)
        return dict(
            id=p["id"], name=p["name"], pos=p["pos"], age=round(p["age"], 1), toi=round(toi, 1),
            rate_g=rate_g, rate_a=rate_a, ros_gp=ros_gp, eff_gp=eff_gp, rookie=rookie, team_left=len(team_left),
            now=dict(gp=now["gamesPlayed"], g=now["goals"], a=now["assists"], p=now["points"]) if now else dict(gp=0, g=0, a=0, p=0),
            last=dict(gp=s[prior_season]["gamesPlayed"], g=s[prior_season]["goals"], a=s[prior_season]["assists"],
                      p=s[prior_season]["points"]) if prior_season in s else None,
        )

    # ---------------- on-ice impact (5v5 on/off xG per 60, TOI-share weighted, 3 closed seasons)
    def onice_impact(pid: int) -> tuple[float, float]:
        num_f = num_a = den = 0.0
        for yr, w in weights.items():
            if yr == season:
                continue
            m = mp_sk.get(yr, {}).get((pid, "5on5"))
            if not m:
                continue
            it = float(m["icetime"]); gp = float(m["games_played"])
            if it < 7200 or gp <= 0:
                continue
            tm = mpteam(yr, m["team"], "5on5")
            if not tm:
                continue
            team_it = float(tm["iceTime"]) * gp / float(tm["games_played"])
            off_it = max(team_it - it, 3600.0)
            on_f = float(m["OnIce_F_xGoals"]) / it * 3600; off_f = float(m["OffIce_F_xGoals"]) / off_it * 3600
            on_a = float(m["OnIce_A_xGoals"]) / it * 3600; off_a = float(m["OffIce_A_xGoals"]) / off_it * 3600
            share = (it / gp) / 3600.0
            wn = w / wmax * min(gp, 82) / 82
            num_f += wn * (on_f - off_f) * share
            num_a += wn * (on_a - off_a) * share
            den += wn
        if den == 0:
            return 0.0, 0.0
        return num_f / den, num_a / den

    # ---------------- goalies
    def project_goalie(g: dict) -> dict:
        num = den = sv_num = sv_den = 0.0
        for yr, w in weights.items():
            m = mp_g.get(yr, {}).get((g["id"], "all"))
            if not m:
                continue
            minutes = float(m["icetime"]) / 60.0
            if minutes < 60:
                continue
            wn = w / wmax
            num += wn * (float(m["xGoals"]) - float(m["goals"])); den += wn * minutes
            q = gl.get(g["id"], {}).get(yr)
            if q:
                sv_num += wn * q["saves"]; sv_den += wn * q["shotsAgainst"]
        rate = num / den * 60 if den > 0 else 0.0
        gsax60 = rate * (den / (den + K_GOALIE_MINUTES))
        if g["age"] >= 35:
            gsax60 -= 0.03 * (g["age"] - 34)
        elif g["age"] < 24:
            gsax60 += 0.02
        now = gl.get(g["id"], {}).get(season)
        last = gl.get(g["id"], {}).get(prior_season)
        return dict(
            id=g["id"], name=g["name"], age=round(g["age"], 1), gsax60=gsax60, minutes=den,
            sv=(sv_num / sv_den if sv_den else None),
            now=dict(gs=now["gamesStarted"], w=now["wins"], sv=now["savePct"]) if now else dict(gs=0, w=0, sv=None),
            last=dict(gs=last["gamesStarted"], w=last["wins"], sv=last["savePct"]) if last else None,
        )

    # ---------------- top-down team ratings from the two closed seasons
    def topdown(ab: str) -> tuple[float, float]:
        offs, xdefs, ws = [], [], []
        for yr, w in ((seasons[1], 0.75), (seasons[2], 0.25)):
            m = mpteam(yr, ab)
            if not m:
                continue
            gp = float(m["games_played"])
            xgf = float(m["flurryScoreVenueAdjustedxGoalsFor"]); xga = float(m["flurryScoreVenueAdjustedxGoalsAgainst"])
            gf = float(m["goalsFor"])
            offs.append(w * (0.5 * gf + 0.5 * xgf) / gp); xdefs.append(w * xga / gp); ws.append(w)
        if not ws:
            raise ModelError(f"no MoneyPuck team table for {ab}")
        return sum(offs) / sum(ws), sum(xdefs) / sum(ws)

    raw = {ab: topdown(ab) for ab in bundle["teams"]}
    mu_off = sum(o for o, _ in raw.values()) / 32
    mu_xga = sum(x for _, x in raw.values()) / 32

    now_rows = {t["teamAbbrev"]["default"]: t for t in bundle["standings_now"]["standings"]}
    teams: dict[str, dict] = {}
    players: dict[str, list[dict]] = {}
    goalies: dict[str, list[dict]] = {}
    bottom_up: dict[str, float] = {}
    for ab in bundle["teams"]:
        o, xd = raw[ab]
        td_off = mu_off + (o - mu_off) * (1 - REGRESSION)
        td_xga = mu_xga + (xd - mu_xga) * (1 - REGRESSION)
        projs = [project_skater(ab, p) for p in rosters[ab]["skaters"]]
        left = len(remaining_by_team.get(ab, []))
        for grp, slots in (("F", 12), ("D", 6)):
            ps = sorted((q for q in projs if (q["pos"] == "D") == (grp == "D")), key=lambda q: -q["toi"])
            total = sum(q["ros_gp"] for q in ps); avail = slots * left
            if total > avail:
                excess = total - avail
                for q in reversed(ps):
                    cut = min(q["ros_gp"] * 0.85, excess)
                    q["ros_gp"] -= cut; excess -= cut
                    if excess <= 0:
                        break
            elif total < avail:
                projs.append(dict(id=0, name=f"{ab} call-ups ({grp})", pos=grp, age=0, toi=0,
                                  rate_g=0.07 if grp == "F" else 0.03, rate_a=0.11 if grp == "F" else 0.09,
                                  ros_gp=avail - total, eff_gp=0, now=dict(gp=0, g=0, a=0, p=0), last=None, filler=True))
        bottom_up[ab] = (sum(q["rate_g"] * q["ros_gp"] for q in projs) / left) if left else td_off
        d_xgf = d_xga = 0.0
        for q in projs:
            if q.get("filler") or not left:
                continue
            f, a = onice_impact(q["id"])
            share = q["ros_gp"] / left
            d_xgf += f * share; d_xga += a * share
        gps = [project_goalie(g) for g in rosters[ab]["goalies"]]
        shares = dict(starter_shares.get(ab, {}))
        names = {g["name"] for g in gps}
        missing = [n for n in shares if n not in names]
        if missing:
            unknown.extend(f"{n} (start share, {ab})" for n in missing)
            for n in missing:
                shares.pop(n)
        if not shares:
            # no depth chart: split starts by last season's starts, else evenly
            weights_g = {g["name"]: max((g["last"] or {}).get("gs", 0), 1) for g in gps}
            shares = {n: w / sum(weights_g.values()) for n, w in weights_g.items()}
        tot = sum(shares.values())
        shares = {n: v / tot for n, v in shares.items()}
        # lean the depth chart toward the starts actually made this season, then
        # hand each remaining game only to the goalies fit to play it
        gp_now = now_rows[ab]["gamesPlayed"]
        start_w = {g["id"]: shares.get(g["name"], 0.0) for g in gps}
        if gp_now > 0:
            start_w = {g["id"]: (start_w[g["id"]] * 20 + g["now"]["gs"]) / (20 + gp_now) for g in gps}
        team_left = remaining_by_team.get(ab, [])
        if team_left:
            starts = _remaining_starts(start_w, {g["id"]: returns.get((ab, g["id"])) for g in gps}, team_left)
            start_w = {k: v / len(team_left) for k, v in starts.items()}
        else:
            tot = sum(start_w.values())
            start_w = {k: v / tot for k, v in start_w.items()} if tot else start_w
        g_eff = 0.0
        for g in gps:
            g["share"] = start_w[g["id"]]
            g_eff += g["share"] * g["gsax60"]
        teams[ab] = dict(td_off=td_off, td_xga=td_xga, d_xgf=d_xgf, d_xga=d_xga, goalie_gsax=g_eff)
        players[ab] = projs
        goalies[ab] = gps

    mu_bu = sum(bottom_up.values()) / 32
    for ab, t in teams.items():
        bu = bottom_up[ab] * (mu_off / mu_bu)
        t["bu_off"] = bu
        t["off"] = 0.5 * t["td_off"] + 0.5 * bu + SHRINK_ONICE * 0.5 * t["d_xgf"]
        t["ga"] = t["td_xga"] + SHRINK_ONICE * t["d_xga"] - t["goalie_gsax"]

    # ---------------- in-season update toward the season to date
    mp_now = mp_teams.get(season, {})
    for ab, t in teams.items():
        row = now_rows[ab]
        gp = row["gamesPlayed"]
        t["gp"] = gp
        if gp <= 0:
            t["off_pre"], t["ga_pre"] = t["off"], t["ga"]
            continue
        m = mp_now.get((ab, "all"))
        gf = row["goalFor"] / gp; ga = row["goalAgainst"] / gp
        if m and float(m["games_played"]) > 0:
            mgp = float(m["games_played"])
            obs_off = 0.5 * gf + 0.5 * float(m["flurryScoreVenueAdjustedxGoalsFor"]) / mgp
            obs_ga = 0.5 * ga + 0.5 * float(m["flurryScoreVenueAdjustedxGoalsAgainst"]) / mgp
            k = k_team_update
        else:
            obs_off, obs_ga, k = gf, ga, k_team_update * 1.5
        t["off_pre"], t["ga_pre"] = t["off"], t["ga"]
        t["off"] = (t["off"] * k + obs_off * gp) / (k + gp)
        t["ga"] = (t["ga"] * k + obs_ga * gp) / (k + gp)

    # ---------------- toward the card's PostHockey-style ratings
    ph_status, home_ice = _blend_ph(teams, ph_ratings, ph_weight, state)

    mo = sum(t["off"] for t in teams.values()) / 32
    mg = sum(t["ga"] for t in teams.values()) / 32
    for ab, t in teams.items():
        for k in ("own_off", "own_ga", "ph_off", "ph_ga"):
            if t.get(k) is not None:
                t[k] *= LEAGUE_GPG / (mo if "off" in k else mg)
        t["off"] *= LEAGUE_GPG / mo
        t["ga"] *= LEAGUE_GPG / mg
        left = len(remaining_by_team.get(ab, []))
        ps = players[ab]
        sg = sum(q["rate_g"] * q["ros_gp"] for q in ps); sa = sum(q["rate_a"] * q["ros_gp"] for q in ps)
        tg = t["off"] * left; ta = ASSISTS_PER_GOAL * tg
        for q in ps:
            q["ros_g"] = q["rate_g"] * q["ros_gp"] * tg / sg if sg else 0.0
            q["ros_a"] = q["rate_a"] * q["ros_gp"] * ta / sa if sa else 0.0
            q["proj_gp"] = q["now"]["gp"] + q["ros_gp"]
            q["proj_g"] = q["now"]["g"] + q["ros_g"]
            q["proj_a"] = q["now"]["a"] + q["ros_a"]
            q["proj_p"] = q["proj_g"] + q["proj_a"]

    # standings rows for the site and the sim
    prior_rows = {t["teamAbbrev"]["default"]: t for t in bundle["standings_prior"]["standings"]}
    team_info = {}
    for ab in bundle["teams"]:
        row = now_rows[ab]; last = prior_rows.get(ab)
        team_info[ab] = dict(
            abbrev=ab, name=row["teamName"]["default"], conf=row["conferenceAbbrev"], div=row["divisionName"],
            now=dict(gp=row["gamesPlayed"], w=row["wins"], l=row["losses"], otl=row["otLosses"], pts=row["points"],
                     gf=row["goalFor"], ga=row["goalAgainst"], rw=row.get("regulationWins", 0),
                     row=row.get("regulationPlusOtWins", 0)),
            last=dict(gp=last["gamesPlayed"], pts=last["points"], w=last["wins"], l=last["losses"], otl=last["otLosses"],
                      gf=last["goalFor"], ga=last["goalAgainst"]) if last else None,
        )

    return dict(
        asof=asof.isoformat(), season=season, games_per_team=games_total, state=state,
        teams=teams, team_info=team_info, players=players, goalies=goalies,
        unknown=unknown, league_gpg=LEAGUE_GPG, home_ice=home_ice or {}, k_team_update=k_team_update,
        ratings=dict(ph_weight=ph_weight if home_ice is not None else 0.0, ph_status=ph_status,
                     ph_through=(ph_ratings or {}).get("last_game_date") if home_ice is not None else None),
    )


def _blend_ph(teams: dict, ph: dict | None, weight: float, state: dict) -> tuple[str, dict | None]:
    """Move each team's offense and defense ``weight`` of the way toward the
    ratings file's, in place. Returns a status line and the file's home ice
    (None when the file was not used).

    The file's attack and defence are multipliers on the league rate with
    the last-five form multiplied in; form is divided back out, because a
    five-game streak says little about the seventy games still to play.
    Both are re-centred on this model's own league means before blending, so
    the blend moves teams relative to each other and not the league's
    scoring.
    """
    for t in teams.values():
        t["own_off"], t["own_ga"] = t["off"], t["ga"]
        t["ph_off"] = t["ph_ga"] = None
    if ph is None:
        return "not used: no ratings file", None
    if weight <= 0:
        return "not used: weight 0", None
    through = str(ph.get("last_game_date", ""))[:10]
    latest = max((g["date"] for g in state["played"]), default=None)
    if latest:
        try:
            lag = (date.fromisoformat(latest) - date.fromisoformat(through)).days
        except ValueError:
            return f"not used: the ratings carry no readable date ({through!r})", None
        if lag > PH_MAX_LAG_DAYS:
            return f"not used: the ratings run through {through}, the standings through {latest}", None
    form = ph.get("form") or {}
    att, dfn = {}, {}
    for ab in teams:
        rate = ph["teams"].get(ab)
        if not rate:
            continue
        f = form.get(ab) or {}
        att[ab] = float(rate["attack"]) / float(f.get("attack", 1.0) or 1.0)
        dfn[ab] = float(rate["defence"]) / float(f.get("defence", 1.0) or 1.0)
    if len(att) < 30:
        return f"not used: the ratings rate {len(att)} of the teams", None
    ma = sum(att.values()) / len(att); md = sum(dfn.values()) / len(dfn)
    mo = sum(t["off"] for t in teams.values()) / len(teams)
    mg = sum(t["ga"] for t in teams.values()) / len(teams)
    for ab, t in teams.items():
        if ab not in att:
            continue
        t["ph_off"] = mo * att[ab] / ma
        t["ph_ga"] = mg * dfn[ab] / md
        t["off"] = (1 - weight) * t["off"] + weight * t["ph_off"]
        t["ga"] = (1 - weight) * t["ga"] + weight * t["ph_ga"]
    home_ice = {str(k): float(v) for k, v in (ph.get("home_ice") or {}).items() if str(k) in teams}
    return f"blended at {weight:.2f}, through {through}, {len(att)} teams, home ice for {len(home_ice)}", home_ice


def load_injuries(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("returning", "out"):
        for entry in data.get(key, []):
            for field in ("name", "team"):
                if field not in entry:
                    raise ModelError(f"injuries.json {key} entry is missing {field!r}: {entry}")
            ret = entry.get("return")
            if ret not in (None, "season"):
                date.fromisoformat(ret)
            if key == "returning" and "born" not in entry:
                raise ModelError(f"injuries.json returning entry needs 'born': {entry}")
    return data


def isfinite_all(values) -> bool:
    return all(math.isfinite(v) for v in values)
