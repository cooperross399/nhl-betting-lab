#!/usr/bin/env python3
"""Build ``data/season.json`` for the public site's Season page.

    python web/build_season_json.py --out dist/data --cache data/raw/season_sim

Fetches every input from public endpoints (the NHL API and MoneyPuck, no
credential), builds the team and player model, plays the remaining schedule
ten thousand times, and writes one JSON file in the shape ``web/SCHEMA.md``
describes under ``season.json``. It reads no price, spends no credit, and
places no bet.

When ``--ratings`` names the card's team ratings file
(``data/processed/shadow_team_ratings.json``, PostHockey-style
shooter-adjusted xG with GSAx(sh) and each club's own home ice) and that file
is current, every team's strength is blended toward it, so the Season page and
the card rate teams on the same numbers. Without it the season is simulated on
the model's own ratings and the page says so.

The hand-kept inputs (injured regulars expected back, opening goalie depth
charts, rookies' ice time) live in ``data/season_sim/roster_notes.json``; the
published Hart, Norris and Selke odds and media polls the award trackers read
live in ``data/season_sim/award_inputs.json`` (see ``season_sim/awards.py``).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from season_sim.fetch import fetch_bundle  # noqa: E402
from season_sim.model import build_model, isfinite_all, load_injuries, load_ph_ratings  # noqa: E402
from season_sim.awards import load_inputs, trackers  # noqa: E402
from season_sim.simulate import simulate  # noqa: E402

DEFAULT_NOTES = HERE.parent / "data" / "season_sim" / "roster_notes.json"
DEFAULT_RATINGS = HERE.parent / "data" / "processed" / "shadow_team_ratings.json"
DEFAULT_AWARDS = HERE.parent / "data" / "season_sim" / "award_inputs.json"

#: What the page prints for a Calder table it cannot vouch for.
CALDER_NOTE = ("Rookies are read off the NHL's eligibility rule (under 26 on September 15, at most 25 games in any "
               "earlier season and not six or more in two) against the three seasons on file; a player whose games "
               "came before then could be listed wrongly. Ranked by points, the Calder itself is voted.")


def _team_colors() -> dict:
    """The board's own team colour table, so the two pages match."""
    spec = importlib.util.spec_from_file_location("build_site_json", HERE / "build_site_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TEAMS


def season_label(season: str) -> str:
    return f"{season[:4]}–{season[6:]}"


def compose(model: dict, result: dict, notes: dict, colors: dict, *, generated_at: str,
            award_inputs: dict | None = None) -> dict:
    info = model["team_info"]
    players = result["players"]
    goalies_by_team: dict[str, list[dict]] = {}
    for g in result["goalies"]:
        goalies_by_team.setdefault(g["team"], []).append(g)
    league_gp = sum(info[t]["now"]["gp"] for t in info)
    games = model["games_per_team"]

    def player(p: dict) -> dict:
        return dict(name=p["name"], pos=p["pos"], age=p["age"], gp=p["gp"], g=round(p["g"]), a=round(p["a"]),
                    p=round(p["p"]), now=p["now"], last=p["last"])

    def goalie(g: dict) -> dict:
        return dict(name=g["name"], team=g["team"], age=g["age"], share=g["share"], starts=g["starts"], wins=g["wins"],
                    p10=g["wins_p10"], p90=g["wins_p90"], p30=g["p_30"], p35=g["p_35"], p40=g["p_40"],
                    gsax60=g["gsax60"], sv3=g["sv_3yr"], now=g["now"], last=g["last"])

    def award(rows: list[dict]) -> list[dict]:
        return [dict(name=r["name"], team=r["team"], pos=r.get("pos", "G"), age=r["age"], p=r["p"], proj=r["proj"],
                     p10=r["p10"], p90=r["p90"], now=r["now"]) for r in rows]

    trophies_in = result.get("trophies") or {}
    skaters = [dict(name=q["name"], pos=q["pos"], team=ab, p=q["proj_p"])
               for ab, qs in model["players"].items() for q in qs if not q.get("filler")]
    voted = trackers(award_inputs, skaters, {r["abbrev"]: r["p_playoff"] for r in result["teams"]},
                     today=datetime.fromisoformat(generated_at).date())
    playoffs_in = result.get("playoffs") or {}
    ratings = model.get("ratings") or {}

    teams = []
    for r in result["teams"]:
        ab = r["abbrev"]
        name, short, color, fg = colors.get(ab, (info[ab]["name"], ab, "#14151a", "#FFFFFF"))
        last = info[ab]["last"]
        teams.append(dict(
            abbr=ab, name=name, short=short, color=color, fg=fg, conf=info[ab]["conf"], div=info[ab]["div"],
            now=info[ab]["now"],
            proj=dict(pts=r["pts"], p10=r["pts_p10"], p90=r["pts_p90"], sd=r["pts_sd"], w=r["w"], l=r["l"], otl=r["otl"],
                      gf=r["gf"], ga=r["ga_sim"]),
            odds=dict(playoff=r["p_playoff"], div=r["p_div"], conf1=r["p_conf1"], pres=r["p_pres"], last=r["p_last"],
                      bottom5=r["p_bottom5"], divRankDist=r["div_rank_dist"], avgDivRank=r["avg_div_rank"],
                      round1=r["p_r1"], confFinal=r["p_r2"], final=r["p_final"], cup=r["p_cup"]),
            lastSeason=dict(pts=last["pts"], gp=last["gp"], gf=last["gf"], ga=last["ga"]) if last else None,
            rating=dict(off=r["off"], ga=r["ga"], diff=r["diff"], tdOff=r["td_off"], buOff=r["bu_off"], onIceXgf=r["d_xgf"],
                        tdXga=r["td_xga"], onIceXga=r["d_xga"], goalieGsax=r["goalie_gsax"],
                        ownOff=r["own_off"], ownGa=r["own_ga"], phOff=r["ph_off"], phGa=r["ph_ga"], homeIce=r["home_ice"]),
            scorers=[player(p) for p in players[ab][:5]],
            goalies=[goalie(g) for g in goalies_by_team.get(ab, [])],
        ))

    return dict(
        generatedAt=generated_at,
        season=season_label(model["season"]),
        games=games, sims=result["meta"]["sims"],
        asOf=model["asof"],
        phase="preseason" if league_gp == 0 else "regular",
        leagueGamesPlayed=league_gp // 2,
        remainingGames=result["meta"]["remaining_games"],
        pctPlayed=round(league_gp / (32 * games), 3),
        notice=None,
        teams=teams,
        leaders=dict(points=[dict(player(p), team=p["team"]) for p in result["league_top"][:30]],
                     goals=[dict(player(p), team=p["team"]) for p in result["goal_top"][:20]],
                     wins=[goalie(g) for g in result["goalies"][:20]]),
        notes=dict(asOf=notes.get("asOf"), returning=notes.get("returning", []), out=notes.get("out", []),
                   unknown=model["unknown"]),
        playoffs=dict(
            slots=[dict(conf=sl["conf"], label=sl["label"], matchups=sl["matchups"]) for sl in playoffs_in.get("slots", [])],
            conferenceFinals=playoffs_in.get("conference_finals", []),
            finals=playoffs_in.get("finals", []),
        ),
        trophies=dict(
            artRoss=award(trophies_in.get("art_ross", [])),
            rocket=award(trophies_in.get("rocket", [])),
            wins=award(trophies_in.get("wins", [])),
            calder=award(trophies_in["calder"]) if trophies_in.get("calder") else None,
            calderNote=CALDER_NOTE if trophies_in.get("calder") else
            "The rookie list could not be read off the data, so no Calder table is published.",
            voted=voted,
        ),
        method=dict(sigma=result["meta"]["sigma"], sigmaMode=result["meta"].get("sigma_mode", "fixed"),
                    hfa=result["meta"]["hfa"], tieRate=result["meta"]["tie_rate"],
                    leagueAvgPts=result["meta"]["league_avg_pts"],
                    playoffShrink=result["meta"].get("playoff_shrink"), playerSigma=result["meta"].get("player_sigma"),
                    ratings=dict(phWeight=ratings.get("ph_weight", 0.0), phThrough=ratings.get("ph_through"),
                                 phStatus=ratings.get("ph_status", "not used"))),
    )


def check(site: dict) -> None:
    """Refuse a file the page could not read as a season."""
    teams = site["teams"]
    if len(teams) != 32:
        raise SystemExit(f"season.json holds {len(teams)} teams, not 32")
    total_p = sum(t["odds"]["playoff"] for t in teams)
    if abs(total_p - 16) > 0.05:
        raise SystemExit(f"playoff odds sum to {total_p:.3f}, not 16")
    if not isfinite_all(t["proj"]["pts"] for t in teams):
        raise SystemExit("a projected points total is not finite")
    if any(t["proj"]["p10"] > t["proj"]["pts"] or t["proj"]["p90"] < t["proj"]["pts"] for t in teams):
        raise SystemExit("a percentile range does not contain its mean")
    if not site["leaders"]["points"] or not site["leaders"]["wins"]:
        raise SystemExit("the leader tables are empty")
    # The trophy and playoff-round odds arrived after the first builds; a
    # file without them (the committed baseline) is still a season.
    if "cup" in teams[0]["odds"]:
        for field, want in (("round1", 8), ("confFinal", 4), ("final", 2), ("cup", 1)):
            total = sum(t["odds"][field] for t in teams)
            if abs(total - want) > 0.01:
                raise SystemExit(f"{field} odds sum to {total:.3f}, not {want}")
        for t in teams:
            o = t["odds"]
            if not (o["cup"] <= o["final"] + 1e-9 <= o["confFinal"] + 2e-9 <= o["round1"] + 3e-9 <= o["playoff"] + 4e-9):
                raise SystemExit(f"{t['abbr']}'s round odds do not shrink round by round")
    for name, rows in (site.get("trophies") or {}).items():
        if isinstance(rows, list) and sum(r["p"] for r in rows) > 1.001:
            raise SystemExit(f"the {name} odds sum past 1")
    for name, tr in ((site.get("trophies") or {}).get("voted") or {}).items():
        if sum(r["tracker"] for r in tr["rows"]) > 1.001 or any(r["tracker"] < 0 for r in tr["rows"]):
            raise SystemExit(f"the {name} tracker shares do not make a distribution")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="Directory to write season.json into.")
    parser.add_argument("--cache", default="data/raw/season_sim", help="Where fetched inputs are kept.")
    parser.add_argument("--notes", default=str(DEFAULT_NOTES), help="roster_notes.json to read.")
    parser.add_argument("--sims", type=int, default=10_000)
    parser.add_argument("--ratings", default=str(DEFAULT_RATINGS),
                        help="The card's team ratings file (PostHockey-style xG); blended in when current.")
    parser.add_argument("--ph-weight", type=float, default=None, help="Blend weight toward --ratings (default: the model's).")
    parser.add_argument("--awards", default=str(DEFAULT_AWARDS),
                        help="Hand-kept Hart/Norris/Selke odds and media polls for the award trackers.")
    args = parser.parse_args(argv)

    notes = load_injuries(Path(args.notes))
    bundle = fetch_bundle(Path(args.cache))
    ph, why = load_ph_ratings(Path(args.ratings))
    model = build_model(bundle, notes, starter_shares=notes.get("goalieShares", {}), ph_ratings=ph, ph_weight=args.ph_weight)
    for line in model["unknown"]:
        print(f"::warning::roster_notes.json names a player the stats API does not know: {line}")
    status = model["ratings"]["ph_status"]
    print(f"Team ratings: {status}" + ("" if ph else f" ({why})"))
    if not model["ratings"]["ph_weight"]:
        print("::warning::The season is simulated on its own ratings, not the card's PostHockey-style ratings: " + status)
    result = simulate(model, sims=args.sims)
    award_inputs = load_inputs(Path(args.awards))
    if award_inputs is None:
        print(f"::warning::No award inputs at {args.awards}; the Hart, Norris and Selke trackers are left out")
    site = compose(model, result, notes, _team_colors(), generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   award_inputs=award_inputs)
    check(site)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "season.json").write_text(json.dumps(site, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    top = site["teams"][0]
    print(f"season.json: {site['phase']}, {site['leagueGamesPlayed']} games played, {site['remainingGames']} simulated; "
          f"favourite {top['abbr']} {top['proj']['pts']} pts; league average {site['method']['leagueAvgPts']} pts")
    cup = max(site["teams"], key=lambda t: t["odds"]["cup"])
    tro = site["trophies"]
    print(f"Cup favourite {cup['abbr']} {cup['odds']['cup']:.1%}; "
          + "; ".join(f"{k} {v[0]['name']} {v[0]['p']:.1%}" for k, v in tro.items() if isinstance(v, list) and v))
    # The page's detail, in the log too, so a run can be read without the site.
    for k, v in tro.items():
        if isinstance(v, list) and v:
            print(f"  {k}: " + ", ".join(f"{r['name']} {r['p']:.1%}" for r in v[:5]))
    for sl in site["playoffs"]["slots"]:
        if sl["matchups"]:
            m = sl["matchups"][0]
            print(f"  {sl['conf']} {sl['label']}: {m['a']} v {m['b']} {m['p']:.0%}")
    for m in site["playoffs"]["finals"][:3]:
        print(f"  Final {m['a']} v {m['b']} {m['p']:.1%}")
    for k, tr in (tro.get("voted") or {}).items():
        stale = " (stale inputs)" if tr["stale"] else ""
        print(f"  {k} tracker{stale}: " + ", ".join(f"{r['name']} {r['tracker']:.1%}" for r in tr["rows"][:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
