"""Play the remaining schedule many times and summarise what comes out.

Each remaining game is two Poisson draws from expected goals — team offense
times opponent defense over the league average, with a small home bump and
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
"""
from __future__ import annotations

import numpy as np

SIGMA = 0.05
HFA = 0.021
OT_SHARE = 0.248
SO_SHARE_OF_OT = 0.365
DEFAULT_SIMS = 10_000
SEED = 20262027


def simulate(model: dict, *, sims: int = DEFAULT_SIMS, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
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

    # season to date
    now = {k: np.array([info[t]["now"][k] for t in teams], dtype=float) for k in ("w", "l", "otl", "pts", "gf", "ga", "rw", "row", "gp")}

    remaining = model["state"]["remaining"]
    NG = len(remaining)
    if NG:
        home = np.array([idx[g["home"]] for g in remaining]); away = np.array([idx[g["away"]] for g in remaining])
        neutral = np.array([g["neutral"] for g in remaining])
        off_s = off[None, :] * np.exp(rng.normal(0, SIGMA, (sims, T)))
        ga_s = ga[None, :] * np.exp(rng.normal(0, SIGMA, (sims, T)))
        hf = np.where(neutral, 0.0, HFA)[None, :]
        lam_h = off_s[:, home] * ga_s[:, away] / mu * (1 + hf)
        lam_a = off_s[:, away] * ga_s[:, home] / mu * (1 - hf)
        gh = rng.poisson(lam_h); gaw = rng.poisson(lam_a)
        tie0 = float((gh == gaw).mean()); one = np.abs(gh - gaw) == 1
        q = max(0.0, (OT_SHARE - tie0) / max(float(one.mean()), 1e-9))
        conv = one & (rng.random((sims, NG)) < q)
        gh = np.where(conv & (gh < gaw), gh + 1, gh); gaw = np.where(conv & (gaw < gh), gaw + 1, gaw)
        tie = gh == gaw
        p_ot = 0.5 + 0.5 * (lam_h - lam_a) / (lam_h + lam_a)
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
    else:
        W = np.tile(now["w"], (sims, 1)); OTL = np.tile(now["otl"], (sims, 1)); RW = np.tile(now["rw"], (sims, 1))
        ROW = np.tile(now["row"], (sims, 1)); GF = np.tile(now["gf"], (sims, 1)); GA = np.tile(now["ga"], (sims, 1))
        tie_rate = 0.0
    L = G - W - OTL
    PTS = 2 * W + OTL

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
            td_off=round(tm["td_off"], 2), bu_off=round(tm["bu_off"], 2), d_xgf=round(tm["d_xgf"], 2),
            td_xga=round(tm["td_xga"], 2), d_xga=round(tm["d_xga"], 2), goalie_gsax=round(tm["goalie_gsax"], 3),
        ))

    goalie_rows = []
    for t in teams:
        i = idx[t]
        left = int(G - now["gp"][idx[t]])
        g_eff = model["teams"][t]["goalie_gsax"]
        ros_w_team = W[:, i] - now["w"][i]
        for g in model["goalies"][t]:
            sh = g["share"]
            if sh <= 0:
                continue
            starts = int(round(sh * left))
            if left > 0 and starts > 0:
                p = np.clip(ros_w_team / left + 0.15 * (g["gsax60"] - g_eff) + 0.04 * (sh - 0.5), 0.05, 0.95)
                wins = g["now"]["w"] + rng.binomial(starts, p)
            else:
                wins = np.full(sims, float(g["now"]["w"]))
            goalie_rows.append(dict(
                name=g["name"], team=t, age=g["age"], share=round(sh, 3), starts=g["now"]["gs"] + starts,
                gsax60=round(g["gsax60"], 3), sv_3yr=(round(g["sv"], 3) if g["sv"] else None),
                wins=round(float(np.mean(wins)), 1), wins_p10=int(np.percentile(wins, 10)), wins_p90=int(np.percentile(wins, 90)),
                p_30=round(float(np.mean(wins >= 30)), 3), p_35=round(float(np.mean(wins >= 35)), 3), p_40=round(float(np.mean(wins >= 40)), 3),
                now=g["now"], last=g["last"],
            ))
    goalie_rows.sort(key=lambda r: -r["wins"])

    player_rows = {}
    all_players = []
    for t in teams:
        ps = sorted((q for q in model["players"][t] if not q.get("filler")), key=lambda q: -q["proj_p"])
        rows = [dict(name=q["name"], pos=q["pos"], age=q["age"], gp=round(q["proj_gp"]), g=round(q["proj_g"], 1),
                     a=round(q["proj_a"], 1), p=round(q["proj_p"], 1), now=q["now"], last=q["last"], toi=q["toi"]) for q in ps]
        player_rows[t] = rows[:8]
        all_players.extend(dict(r, team=t) for r in rows)
    all_players.sort(key=lambda r: -r["p"])

    return dict(
        meta=dict(sims=sims, games=G, sigma=SIGMA, hfa=HFA, tie_rate=round(tie_rate, 3), remaining_games=NG,
                  league_avg_pts=round(float(PTS.mean()), 2)),
        teams=sorted(team_rows, key=lambda r: -r["pts"]), goalies=goalie_rows, players=player_rows,
        league_top=all_players[:40], goal_top=sorted(all_players, key=lambda r: -r["g"])[:25],
    )
