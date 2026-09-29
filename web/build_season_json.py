#!/usr/bin/env python3
"""Build ``data/season.json`` for the public site's Season page.

    python web/build_season_json.py --out dist/data --cache data/raw/season_sim

Fetches every input from public endpoints (the NHL API and MoneyPuck, no
credential), builds the team and player model, plays the remaining schedule
ten thousand times, and writes one JSON file in the shape ``web/SCHEMA.md``
describes under ``season.json``. It reads no price, spends no credit, and
places no bet.

The hand-kept inputs (injured regulars expected back, opening goalie depth
charts, rookies' ice time) live in ``data/season_sim/roster_notes.json``.
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
from season_sim.model import build_model, isfinite_all, load_injuries  # noqa: E402
from season_sim.simulate import simulate  # noqa: E402

DEFAULT_NOTES = HERE.parent / "data" / "season_sim" / "roster_notes.json"


def _team_colors() -> dict:
    """The board's own team colour table, so the two pages match."""
    spec = importlib.util.spec_from_file_location("build_site_json", HERE / "build_site_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TEAMS


def season_label(season: str) -> str:
    return f"{season[:4]}–{season[6:]}"


def compose(model: dict, result: dict, notes: dict, colors: dict, *, generated_at: str) -> dict:
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
                      bottom5=r["p_bottom5"], divRankDist=r["div_rank_dist"], avgDivRank=r["avg_div_rank"]),
            lastSeason=dict(pts=last["pts"], gp=last["gp"], gf=last["gf"], ga=last["ga"]) if last else None,
            rating=dict(off=r["off"], ga=r["ga"], diff=r["diff"], tdOff=r["td_off"], buOff=r["bu_off"], onIceXgf=r["d_xgf"],
                        tdXga=r["td_xga"], onIceXga=r["d_xga"], goalieGsax=r["goalie_gsax"]),
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
        method=dict(sigma=result["meta"]["sigma"], hfa=result["meta"]["hfa"], tieRate=result["meta"]["tie_rate"],
                    leagueAvgPts=result["meta"]["league_avg_pts"]),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="Directory to write season.json into.")
    parser.add_argument("--cache", default="data/raw/season_sim", help="Where fetched inputs are kept.")
    parser.add_argument("--notes", default=str(DEFAULT_NOTES), help="roster_notes.json to read.")
    parser.add_argument("--sims", type=int, default=10_000)
    args = parser.parse_args(argv)

    notes = load_injuries(Path(args.notes))
    bundle = fetch_bundle(Path(args.cache))
    model = build_model(bundle, notes, starter_shares=notes.get("goalieShares", {}))
    for line in model["unknown"]:
        print(f"::warning::roster_notes.json names a player the stats API does not know: {line}")
    result = simulate(model, sims=args.sims)
    site = compose(model, result, notes, _team_colors(), generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    check(site)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "season.json").write_text(json.dumps(site, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    top = site["teams"][0]
    print(f"season.json: {site['phase']}, {site['leagueGamesPlayed']} games played, {site['remainingGames']} simulated; "
          f"favourite {top['abbr']} {top['proj']['pts']} pts; league average {site['method']['leagueAvgPts']} pts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
