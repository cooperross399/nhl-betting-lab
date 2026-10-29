"""Play the remaining schedule many times and summarise what comes out.

Each remaining game is two Poisson draws from expected goals — team offense
times opponent defense over the league average, with a small home bump (the
league's, moved by each club's own home ice when the ratings carry it) and
none at a neutral site. Independent Poisson draws under-produce regulation
ties (about 16% against the 24.8% of games that actually reached overtime in
2025-26, because a trailing team pushes), so a calibrated share of one-goal
games is converted into ties before overtime is decided; overtime is a draw
with a shrunken strength edge, and 36.5% of those go to a shootout, which
earns no regulation-or-overtime win. Every simulated season also jitters each
team's offense and defense by a few percent, which is projection uncertainty
rather than game-to-game noise, and is why the 10th–90th percentile ranges
are as wide as they are.

Seasons already under way start from the standings to date and simulate only
what is left.

Inside the same simulated seasons:

* **The playoffs.** The sixteen teams are seeded in the NHL's format (three
  per division and two wild cards per conference; the division winner with
  the better record meets the second wild card, the other the first; second
  meets third in each division; the bracket is fixed by division through the
  conference final) and every series is played best of seven, 2-2-1-1-1, home
  ice to the better regular-season record. A playoff game uses the same
  season's jittered ratings with the strength gap shrunk to
  ``PLAYOFF_GAP_SHRINK`` (PostHockey's published playoff shrink), the home
  edge, and no ties: a level game goes to sudden-death overtime.
* **The trophies.** Each candidate scorer's rest-of-season goals and assists
  are drawn from that season's simulated team goals, thinned by his share of
  them, with a per-season rate jitter and an availability draw, so a scorer
  on a team that scores more scores more. Each goalie's wins are drawn from
  his team's simulated wins. A tie for the lead splits the credit.
"""
from __future__ import annotations

import numpy as np

SIGMA = 0.05
#: "fixed": every team's ratings jitter by SIGMA all season. "shrink": by
#: SIGMA * sqrt(K / (K + games played)), the share of the rating still
#: resting on the prior. The backtest (scripts/backtest_season_sim.py)
#: decides which; fixed is what shipped first and stays until it does.
SIGMA_MODE = "fixed"
HFA = 0.021
OT_SHARE = 0.248
SO_SHARE_OF_OT = 0.365
DEFAULT_SIMS = 10_000
SEED = 20262027

#: PostHockey shrinks the strength gap to 0.479 of its regular-season size
#: in playoff games (docs/posthockey_gap_list.md).
PLAYOFF_GAP_SHRINK = 0.479
#: Per-season log-sd of a scorer's rate (role, linemates, shooting luck).
PLAYER_SIGMA = 0.10
#: Concentration of the availability draw: games a player is fit for, as a
#: share of what is left, is Beta-distributed around his projected share.
#: Eight leaves a durable regular a one-in-ten chance of missing a fifth of
#: the rest of the season, which is about the league's injury rate.
AVAIL_KAPPA = 8.0
#: The same for a goalie's share of starts.
GOALIE_AVAIL_KAPPA = 10.0
#: Candidates carried into the trophy draw (memory-safe at 10,000 seasons).
TOP_SCORERS = 60
TOP_GOALSCORERS = 40
TOP_ROOKIES = 25
MAX_GOALS = 16
#: Candidates published per award.
TROPHY_ROWS = 10


# ----------------------------------------------------------------------
# playoff helpers
# ----------------------------------------------------------------------
def _poisson_pmf(lam: np.ndarray) -> np.ndarray:
    """P(k goals) for k = 0..MAX_GOALS, along a new last axis."""
    k = np.arange(MAX_GOALS + 1)
    logfact = np.cumsum(np.log(np.maximum(k, 1)))
    lam = np.maximum(lam, 1e-9)[..., None]
    return np.exp(k * np.log(lam) - lam - logfact)


def game_win_probability(lam_h: np.ndarray, lam_a: np.ndarray) -> np.ndarray:
    """P(home wins) with no ties: regulation, then sudden-death overtime won
    in proportion to scoring rates."""
    ph = _poisson_pmf(lam_h)
    pa = _poisson_pmf(lam_a)
    cdf_a = np.cumsum(pa, axis=-1)
    below = np.concatenate([np.zeros_like(cdf_a[..., :1]), cdf_a[..., :-1]], axis=-1)
    p_reg_win = (ph * below).sum(-1)
    p_tie = (ph * pa).sum(-1)
    return p_reg_win + p_tie * lam_h / (lam_h + lam_a)


#: Games 1, 2, 5 and 7 at the higher seed.
HOME_PATTERN = (True, True, False, False, True, False, True)


def series_win_probability(p_home: np.ndarray, p_road: np.ndarray) -> np.ndarray:
    """P(the team with home ice wins a best-of-seven), exactly.

    ``p_home`` is its chance in a game at home, ``p_road`` on the road.
    """
    p_home = np.asarray(p_home, dtype=float)
    p_road = np.asarray(p_road, dtype=float)
    # state[a, b]: probability the series stands a-b with neither at four
    state = {(0, 0): np.ones_like(p_home)}
    won = np.zeros_like(p_home)
    for g in range(7):
        p = p_home if HOME_PATTERN[g] else p_road
        nxt: dict[tuple[int, int], np.ndarray] = {}
        for (a, b), pr in state.items():
            if a + b != g:
                nxt[(a, b)] = nxt.get((a, b), 0) + pr
                continue
            if a + 1 == 4:
                won = won + pr * p
            else:
                nxt[(a + 1, b)] = nxt.get((a + 1, b), 0) + pr * p
            if b + 1 < 4:
                nxt[(a, b + 1)] = nxt.get((a, b + 1), 0) + pr * (1 - p)
        state = nxt
    return won


def seed_conference(key: np.ndarray, div: np.ndarray, conf_cols: np.ndarray) -> dict:
    """Seed one conference in every simulated season.

    ``key`` is the (sims, teams) standings key, higher better; ``conf_cols``
    the conference's team columns. Returns the four first-round series as
    (higher seed, lower seed) column arrays, slot by slot: the better
    division winner's division first, each division's 1-v-wild-card then
    2-v-3, plus the division each slot belongs to.
    """
    sims = key.shape[0]
    rows = np.arange(sims)
    divs = sorted(set(div[conf_cols]))
    if len(divs) != 2:
        raise ValueError(f"a conference needs two divisions, not {divs}")
    tops = {}
    in_top = np.zeros((sims, len(conf_cols)), bool)
    for d in divs:
        cols = np.array([c for c in conf_cols if div[c] == d])
        order = np.argsort(-key[:, cols], axis=1, kind="stable")
        tops[d] = cols[order[:, :3]]
        for k in range(3):
            in_top |= conf_cols[None, :] == tops[d][:, k:k + 1]
    rest = np.where(in_top, -np.inf, key[:, conf_cols])
    wc_order = np.argsort(-rest, axis=1, kind="stable")
    wc1 = conf_cols[wc_order[:, 0]]
    wc2 = conf_cols[wc_order[:, 1]]
    d0, d1 = divs
    first_better = key[rows, tops[d0][:, 0]] >= key[rows, tops[d1][:, 0]]
    # the better division winner meets the second wild card
    opp0 = np.where(first_better, wc2, wc1)
    opp1 = np.where(first_better, wc1, wc2)
    return dict(
        divisions=(d0, d1),
        series=[
            (tops[d0][:, 0], opp0), (tops[d0][:, 1], tops[d0][:, 2]),
            (tops[d1][:, 0], opp1), (tops[d1][:, 1], tops[d1][:, 2]),
        ],
        wildcards=(wc1, wc2),
        first_div_better=first_better,
    )


def _top_pairs(codes: np.ndarray, T: int, n: int, teams: list[str]) -> list[dict]:
    counts = np.bincount(codes, minlength=T * T)
    total = counts.sum()
    out = []
    for code in np.argsort(-counts, kind="stable")[:n]:
        if counts[code] == 0:
            break
        out.append(dict(a=teams[code // T], b=teams[code % T], p=round(float(counts[code] / total), 4)))
    return out


def _split_credit(values: np.ndarray) -> np.ndarray:
    """Each candidate's share of the lead in every season, ties split."""
    best = values.max(axis=1, keepdims=True)
    lead = values == best
    return lead / lead.sum(axis=1, keepdims=True)


# ----------------------------------------------------------------------
# the simulation
# ----------------------------------------------------------------------
def simulate(model: dict, *, sims: int = DEFAULT_SIMS, seed: int = SEED,
             sigma: float | None = None, sigma_mode: str | None = None) -> dict:
    rng = np.random.default_rng(seed)
    sigma = SIGMA if sigma is None else sigma
    sigma_mode = SIGMA_MODE if sigma_mode is None else sigma_mode
    teams = sorted(model["teams"])
    idx = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    G = model["games_per_team"]
    off = np.array([model["teams"][t]["off"] for t in teams])
    ga = np.array([model["teams"][t]["ga"] for t in teams])
    mu = model["league_gpg"]
    info = model["team_info"]
    conf = np.array([info[t]["conf"] for t in teams])
    div = np.array([info[t]["div"] for t in teams])
    home_ice = model.get("home_ice") or {}
    hi = np.array([float(home_ice.get(t, 0.0)) for t in teams])

    # season to date
    now = {k: np.array([info[t]["now"][k] for t in teams], dtype=float) for k in ("w", "l", "otl", "pts", "gf", "ga", "rw", "row", "gp")}

    # the season's own ratings: projection uncertainty, one draw per season
    if sigma_mode == "shrink":
        k = float(model.get("k_team_update", 30.0))
        sig = sigma * np.sqrt(k / (k + now["gp"]))[None, :]
    elif sigma_mode == "fixed":
        sig = np.full((1, T), sigma)
    else:
        raise ValueError(f"unknown sigma_mode {sigma_mode!r}")
    off_s = off[None, :] * np.exp(rng.normal(0, 1, (sims, T)) * sig)
    ga_s = ga[None, :] * np.exp(rng.normal(0, 1, (sims, T)) * sig)

    remaining = model["state"]["remaining"]
    NG = len(remaining)
    if NG:
        home = np.array([idx[g["home"]] for g in remaining]); away = np.array([idx[g["away"]] for g in remaining])
        neutral = np.array([g["neutral"] for g in remaining])
        hf = np.where(neutral, 0.0, HFA)[None, :]
        shift = np.where(neutral, 1.0, np.exp((hi[home] + hi[away]) / 2.0))[None, :]
        lam_h = off_s[:, home] * ga_s[:, away] / mu * (1 + hf) * shift
        lam_a = off_s[:, away] * ga_s[:, home] / mu * (1 - hf) / shift
        gh = rng.poisson(lam_h); gaw = rng.poisson(lam_a)
        tie0 = float((gh == gaw).mean()); one = np.abs(gh - gaw) == 1
        q = max(0.0, (OT_SHARE - tie0) / max(float(one.mean()), 1e-9))
        conv = one & (rng.random((sims, NG)) < q)
        gh = np.where(conv & (gh < gaw), gh + 1, gh); gaw = np.where(conv & (gaw < gh), gaw + 1, gaw)
        tie = gh == gaw
        p_ot = 0.5 + 0.5 * (lam_h - lam_a) / (lam_h + lam_a)
        del lam_h, lam_a, conv, one
        ot_home = rng.random((sims, NG)) < p_ot
        so = rng.random((sims, NG)) < SO_SHARE_OF_OT
        home_win = np.where(tie, ot_home, gh > gaw)
        gh_f = gh + (tie & ot_home & ~so); ga_f = gaw + (tie & ~ot_home & ~so)
        Hm = np.zeros((NG, T), dtype=np.float32); Hm[np.arange(NG), home] = 1
        Am = np.zeros((NG, T), dtype=np.float32); Am[np.arange(NG), away] = 1

        def acc(vh, va):
            return vh.astype(np.float32) @ Hm + va.astype(np.float32) @ Am

        W = now["w"] + acc(home_win, ~home_win)
        OTL = now["otl"] + acc(tie & ~home_win, tie & home_win)
        RW = now["rw"] + acc(~tie & (gh > gaw), ~tie & (gaw > gh))
        ROW = now["row"] + acc(home_win & ~(tie & so), ~home_win & ~(tie & so))
        GF = now["gf"] + acc(gh_f, ga_f); GA = now["ga"] + acc(ga_f, gh_f)
        tie_rate = float(tie.mean())
        del gh, gaw, tie, ot_home, so, home_win, gh_f, ga_f, p_ot
    else:
        W = np.tile(now["w"], (sims, 1)); OTL = np.tile(now["otl"], (sims, 1)); RW = np.tile(now["rw"], (sims, 1))
        ROW = np.tile(now["row"], (sims, 1)); GF = np.tile(now["gf"], (sims, 1)); GA = np.tile(now["ga"], (sims, 1))
        tie_rate = 0.0
    L = G - W - OTL
    PTS = 2 * W + OTL
    # every team's goals and wins still to come, season by season
    gf_rest = np.rint(GF - now["gf"]).astype(np.int64)
    w_rest = np.rint(W - now["w"]).astype(np.int64)

    key = PTS * 1e9 + RW * 1e6 + ROW * 1e3 + (GF - GA + 500)
    league_rank = (-key).argsort(axis=1).argsort(axis=1) + 1
    div_rank = np.zeros((sims, T), int); conf_rank = np.zeros((sims, T), int)
    for d in np.unique(div):
        cols = np.where(div == d)[0]
        div_rank[:, cols] = (-key[:, cols]).argsort(axis=1).argsort(axis=1) + 1
    for c in np.unique(conf):
        cols = np.where(conf == c)[0]
        conf_rank[:, cols] = (-key[:, cols]).argsort(axis=1).argsort(axis=1) + 1
    playoff = div_rank <= 3
    for c in np.unique(conf):
        cols = np.where(conf == c)[0]
        rem = np.where(div_rank[:, cols] > 3, key[:, cols], -1)
        order = (-rem).argsort(axis=1)
        wc = np.zeros((sims, len(cols)), bool)
        np.put_along_axis(wc, order[:, :2], True, axis=1)
        playoff[:, cols] |= wc

    bracket = _play_playoffs(rng, key, conf, div, off_s, ga_s, hi, mu, teams)

    def pct(a, q):
        return float(np.percentile(a, q))

    team_rows = []
    for i, t in enumerate(teams):
        tm = model["teams"][t]
        team_rows.append(dict(
            abbrev=t, off=round(tm["off"], 3), ga=round(tm["ga"], 3), diff=round(tm["off"] - tm["ga"], 3),
            pts=round(float(PTS[:, i].mean()), 1), pts_sd=round(float(PTS[:, i].std()), 1),
            pts_p10=round(pct(PTS[:, i], 10), 1), pts_p90=round(pct(PTS[:, i], 90), 1),
            w=round(float(W[:, i].mean()), 1), l=round(float(L[:, i].mean()), 1), otl=round(float(OTL[:, i].mean()), 1),
            gf=round(float(GF[:, i].mean())), ga_sim=round(float(GA[:, i].mean())), row=round(float(ROW[:, i].mean()), 1),
            p_playoff=round(float(playoff[:, i].mean()), 4), p_div=round(float((div_rank[:, i] == 1).mean()), 4),
            p_conf1=round(float((conf_rank[:, i] == 1).mean()), 4), p_pres=round(float((league_rank[:, i] == 1).mean()), 4),
            p_last=round(float((league_rank[:, i] == T).mean()), 4), p_bottom5=round(float((league_rank[:, i] >= T - 4).mean()), 4),
            avg_div_rank=round(float(div_rank[:, i].mean()), 2), avg_conf_rank=round(float(conf_rank[:, i].mean()), 2),
            avg_league_rank=round(float(league_rank[:, i].mean()), 2),
            div_rank_dist=[round(float((div_rank[:, i] == k).mean()), 3) for k in range(1, 9)],
            p_r1=bracket["p_r1"][i], p_r2=bracket["p_r2"][i], p_final=bracket["p_final"][i], p_cup=bracket["p_cup"][i],
            home_ice=round(float(hi[i]), 4),
            td_off=round(tm.get("td_off", tm["off"]), 2), bu_off=round(tm.get("bu_off", tm["off"]), 2), d_xgf=round(tm.get("d_xgf", 0.0), 2),
            td_xga=round(tm.get("td_xga", tm["ga"]), 2), d_xga=round(tm.get("d_xga", 0.0), 2),
            goalie_gsax=round(tm.get("goalie_gsax", 0.0), 3),
            own_off=round(tm.get("own_off", tm["off"]), 3), own_ga=round(tm.get("own_ga", tm["ga"]), 3),
            ph_off=(round(tm["ph_off"], 3) if tm.get("ph_off") is not None else None),
            ph_ga=(round(tm["ph_ga"], 3) if tm.get("ph_ga") is not None else None),
        ))

    goalie_rows, goalie_wins = _goalies(rng, model, teams, idx, G, now, w_rest, sims)
    player_rows, all_players = _player_tables(model, teams)
    trophies = _trophies(rng, model, teams, idx, gf_rest, goalie_rows, goalie_wins, sims)

    return dict(
        meta=dict(sims=sims, games=G, sigma=sigma, sigma_mode=sigma_mode, hfa=HFA, tie_rate=round(tie_rate, 3),
                  remaining_games=NG, league_avg_pts=round(float(PTS.mean()), 2),
                  playoff_shrink=PLAYOFF_GAP_SHRINK, player_sigma=PLAYER_SIGMA),
        teams=sorted(team_rows, key=lambda r: -r["pts"]), goalies=goalie_rows, players=player_rows,
        league_top=all_players[:40], goal_top=sorted(all_players, key=lambda r: -r["g"])[:25],
        playoffs=dict(slots=bracket["slots"], finals=bracket["finals"], conference_finals=bracket["conference_finals"]),
        trophies=trophies,
        # per-season arrays the backtest scores; not written to the site
        _arrays=dict(teams=teams, pts=PTS, playoff=playoff, gf_rest=gf_rest, goalie_wins=goalie_wins),
    )


def _play_playoffs(rng, key, conf, div, off_s, ga_s, hi, mu, teams) -> dict:
    sims, T = key.shape
    rows = np.arange(sims)
    lo = np.log(off_s / mu) * PLAYOFF_GAP_SHRINK
    lg = np.log(ga_s / mu) * PLAYOFF_GAP_SHRINK

    def play(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Winner of a best-of-seven between columns a and b, season by season."""
        a_home = key[rows, a] >= key[rows, b]
        h = np.where(a_home, a, b); r = np.where(a_home, b, a)
        shift = np.exp((hi[h] + hi[r]) / 2.0)
        lam_hh = mu * np.exp(lo[rows, h] + lg[rows, r]) * (1 + HFA) * shift
        lam_rh = mu * np.exp(lo[rows, r] + lg[rows, h]) * (1 - HFA) / shift
        p_home = game_win_probability(lam_hh, lam_rh)          # h at home
        lam_hr = mu * np.exp(lo[rows, h] + lg[rows, r]) * (1 - HFA) / shift
        lam_rr = mu * np.exp(lo[rows, r] + lg[rows, h]) * (1 + HFA) * shift
        p_road = game_win_probability(lam_hr, lam_rr)          # h on the road
        p = series_win_probability(p_home, p_road)
        return np.where(rng.random(sims) < p, h, r)

    r1_win = np.zeros(T); r2_win = np.zeros(T); r3_win = np.zeros(T); cup = np.zeros(T)
    slots, champs, conf_final_codes = [], {}, {}
    names = {"E": "Eastern", "W": "Western"}
    for c in sorted(set(conf)):
        cols = np.where(conf == c)[0]
        seeded = seed_conference(key, div, cols)
        d0, d1 = seeded["divisions"]
        labels = [f"{d0} 1 v wild card", f"{d0} 2 v {d0} 3", f"{d1} 1 v wild card", f"{d1} 2 v {d1} 3"]
        winners = []
        for (a, b), label in zip(seeded["series"], labels):
            w = play(a, b)
            winners.append(w)
            np.add.at(r1_win, w, 1)
            slots.append(dict(conf=names.get(c, c), label=label,
                              matchups=_top_pairs(a * T + b, T, 3, teams)))
        s1 = play(winners[0], winners[1]); s2 = play(winners[2], winners[3])
        np.add.at(r2_win, s1, 1); np.add.at(r2_win, s2, 1)
        conf_final_codes[c] = np.minimum(s1, s2) * T + np.maximum(s1, s2)
        ch = play(s1, s2)
        np.add.at(r3_win, ch, 1)
        champs[c] = ch
    confs = sorted(champs)
    finals = []
    conference_finals = [dict(conf=names.get(c, c), matchups=_top_pairs(conf_final_codes[c], T, 5, teams)) for c in confs]
    if len(confs) == 2:
        e, w = champs[confs[0]], champs[confs[1]]
        winner = play(e, w)
        np.add.at(cup, winner, 1)
        finals = _top_pairs(e * T + w, T, 10, teams)

    def share(x):
        return [round(float(v / sims), 4) for v in x]

    return dict(p_r1=share(r1_win), p_r2=share(r2_win), p_final=share(r3_win), p_cup=share(cup),
                slots=slots, finals=finals, conference_finals=conference_finals)


def _goalies(rng, model, teams, idx, G, now, w_rest, sims):
    goalie_rows, goalie_wins = [], []
    for t in teams:
        i = idx[t]
        left = int(G - now["gp"][i])
        g_eff = model["teams"][t].get("goalie_gsax", 0.0)
        for g in model["goalies"][t]:
            sh = g["share"]
            if sh <= 0:
                continue
            starts = int(round(sh * left))
            if left > 0 and sh > 0:
                # a goalie can be hurt too: his share of the rest is drawn
                # around his projected share, the mean held
                m = 0.93
                u = rng.beta(m * GOALIE_AVAIL_KAPPA, (1 - m) * GOALIE_AVAIL_KAPPA, sims)
                n_starts = rng.binomial(left, np.clip(min(1.0, sh / m) * u, 0, 1))
                p = np.clip(w_rest[:, i] / left + 0.15 * (g["gsax60"] - g_eff) + 0.04 * (sh - 0.5), 0.05, 0.95)
                wins = g["now"]["w"] + rng.binomial(n_starts, p)
            else:
                wins = np.full(sims, g["now"]["w"])
            goalie_wins.append(wins)
            goalie_rows.append(dict(
                name=g["name"], team=t, age=g["age"], share=round(sh, 3), starts=g["now"]["gs"] + starts,
                gsax60=round(g["gsax60"], 3), sv_3yr=(round(g["sv"], 3) if g.get("sv") else None),
                wins=round(float(np.mean(wins)), 1), wins_p10=int(np.percentile(wins, 10)), wins_p90=int(np.percentile(wins, 90)),
                p_30=round(float(np.mean(wins >= 30)), 3), p_35=round(float(np.mean(wins >= 35)), 3), p_40=round(float(np.mean(wins >= 40)), 3),
                now=g["now"], last=g["last"],
            ))
    order = sorted(range(len(goalie_rows)), key=lambda k: -goalie_rows[k]["wins"])
    return [goalie_rows[k] for k in order], [goalie_wins[k] for k in order]


def _player_tables(model, teams):
    player_rows = {}
    all_players = []
    for t in teams:
        ps = sorted((q for q in model["players"][t] if not q.get("filler")), key=lambda q: -q["proj_p"])
        rows = [dict(name=q["name"], pos=q["pos"], age=q["age"], gp=round(q["proj_gp"]), g=round(q["proj_g"], 1),
                     a=round(q["proj_a"], 1), p=round(q["proj_p"], 1), now=q["now"], last=q["last"], toi=q["toi"],
                     rookie=bool(q.get("rookie"))) for q in ps]
        player_rows[t] = rows[:8]
        all_players.extend(dict(r, team=t) for r in rows)
    all_players.sort(key=lambda r: -r["p"])
    return player_rows, all_players


def draw_season_totals(rng, chosen: list[tuple[str, dict]], idx: dict[str, int], gf_rest: np.ndarray,
                       sims: int) -> tuple[np.ndarray, np.ndarray]:
    """Each player's season goals and points in every simulated season.

    His remaining goals and assists are drawn from his team's simulated goals
    still to come, at his projected share of them, with a PLAYER_SIGMA rate
    jitter and an availability draw (games he may miss); the season so far is
    added on. Returns (goals, points), each sims x players.
    """
    P = len(chosen)
    team_col = np.array([idx[t] for t, _ in chosen], dtype=int)
    mean_team_goals = gf_rest.mean(axis=0)
    goals = np.zeros((sims, P), np.int64); assists = np.zeros((sims, P), np.int64)
    for j, (t, q) in enumerate(chosen):
        i = team_col[j]
        n = gf_rest[:, i]
        tg = float(mean_team_goals[i])
        ros_g = q.get("ros_g", q["proj_g"] - q["now"]["g"])
        ros_a = q.get("ros_a", q["proj_a"] - q["now"]["a"])
        if tg <= 0 or (ros_g <= 0 and ros_a <= 0):
            continue
        left = max(float(q.get("team_left", 0) or 0), 1.0)
        f = float(np.clip(q.get("ros_gp", left) / left, 0.0, 1.0)) if "ros_gp" in q else 1.0
        jitter = np.exp(rng.normal(0, PLAYER_SIGMA, sims) - PLAYER_SIGMA ** 2 / 2)
        if 0.02 < f < 0.999:
            avail = rng.beta(f * AVAIL_KAPPA, (1 - f) * AVAIL_KAPPA, sims) / f
        else:
            avail = np.ones(sims)
        m = jitter * avail
        goals[:, j] = rng.binomial(n, np.clip(ros_g / tg * m, 0, 0.9))
        assists[:, j] = rng.binomial(n, np.clip(ros_a / tg * m, 0, 0.9))
    now_g = np.array([q["now"]["g"] for _, q in chosen]); now_a = np.array([q["now"]["a"] for _, q in chosen])
    return goals + now_g, goals + assists + now_g + now_a


def _trophies(rng, model, teams, idx, gf_rest, goalie_rows, goalie_wins, sims) -> dict:
    """Art Ross, Rocket Richard, the wins lead and (where rookies are known)
    the rookie points lead, as each candidate's share of simulated seasons."""
    pool = []
    for t in teams:
        for q in model["players"][t]:
            if q.get("filler"):
                continue
            pool.append((t, q))
    by_p = sorted(pool, key=lambda tq: -tq[1]["proj_p"])
    by_g = sorted(pool, key=lambda tq: -tq[1]["proj_g"])
    rookies = [tq for tq in by_p if tq[1].get("rookie")]
    chosen, seen = [], set()
    for tq in by_p[:TOP_SCORERS] + by_g[:TOP_GOALSCORERS] + rookies[:TOP_ROOKIES]:
        if id(tq[1]) not in seen:
            seen.add(id(tq[1])); chosen.append(tq)
    out = dict(art_ross=[], rocket=[], wins=[], calder=None,
               calder_known=any(q.get("rookie") is not None for _, q in pool),
               candidates=dict(skaters=len(chosen), rookies=0, goalies=len(goalie_rows)))
    if chosen:
        P = len(chosen)
        tot_g, tot_p = draw_season_totals(rng, chosen, idx, gf_rest, sims)

        def table(values: np.ndarray, cols: np.ndarray, n: int, stat: str) -> list[dict]:
            share = _split_credit(values[:, cols]).mean(axis=0)
            rows = []
            for k in np.argsort(-share, kind="stable")[:n]:
                t, q = chosen[cols[k]]
                v = values[:, cols[k]]
                rows.append(dict(name=q["name"], team=t, pos=q["pos"], age=q["age"], p=round(float(share[k]), 4),
                                 proj=round(float(v.mean()), 1), p10=int(np.percentile(v, 10)), p90=int(np.percentile(v, 90)),
                                 stat=stat, now=q["now"]))
            return rows

        every = np.arange(P)
        out["art_ross"] = table(tot_p, every, TROPHY_ROWS, "points")
        out["rocket"] = table(tot_g, every, TROPHY_ROWS, "goals")
        rk = np.array([j for j, (_, q) in enumerate(chosen) if q.get("rookie")], dtype=int)
        out["candidates"]["rookies"] = int(rk.size)
        if out["calder_known"] and rk.size:
            out["calder"] = table(tot_p, rk, TROPHY_ROWS, "points")
    if goalie_wins:
        wins = np.stack(goalie_wins, axis=1)
        share = _split_credit(wins).mean(axis=0)
        for k in np.argsort(-share, kind="stable")[:TROPHY_ROWS]:
            g = goalie_rows[k]
            out["wins"].append(dict(name=g["name"], team=g["team"], age=g["age"], p=round(float(share[k]), 4),
                                    proj=g["wins"], p10=g["wins_p10"], p90=g["wins_p90"], stat="wins", now=g["now"]))
    return out
