#!/usr/bin/env python3
"""Build the modern-stats shadow model and measure it against the card's.

    PYTHONPATH=src .venv/bin/python scripts/run_shadow_stats.py --fetch

`--fetch` downloads the NHL play-by-play for every final game in
`team_games.csv` that is not already cached (free, keyless; a cold cache is
about four thousand requests). Without it, only cached games are read.

Writes the per-game tables to `data/processed/shadow_*.csv` and the report to
`data/outputs/shadow_stats.md` and `.json`. `--tables-only` writes the tables
and the team ratings (`data/processed/shadow_team_ratings.json`,
`measurement.xg_team_ratings`) and stops; Publish Site runs it that way and
rates the public board's teams on those ratings. `--price-backtest` writes the
tables and then prices the bought team markets twice, walk-forward on
identical games: once on the card's goals ratings and once on the site's xG
ratings (`data/outputs/shadow_price_backtest.md` and `.json`, aggregate only:
bets, returns and intervals, never a price). It needs
`data/processed/historical_team_prices.csv`. Nothing here is read by the card or
the forward ledger (`nhl_betting_lab.shadow`). Spends no odds credits.

Exit codes: 0 measured (or, with `--tables-only`, tables written); 1 nothing
to measure (or, with `--price-backtest`, no bought team prices); 2 the play-by-play disagrees with the boxscores too often, or too
many fetches failed, to trust it (with `--tables-only`, the tables are then
not written).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import NhlApiError, _cache_root, _read_cache, game_is_final
from nhl_betting_lab.backtest.team_walk_forward import generate_team_samples
from nhl_betting_lab.models.team_model import TeamModel, TeamRates
from nhl_betting_lab.reports.team_markets_measurement import (
    MixedWindowError,
    UnresolvedTeamsError,
    build_team_measurement,
)
from nhl_betting_lab.verdicts import ships
from nhl_betting_lab.shadow import measurement
from nhl_betting_lab.shadow.metrics import build_tables
from nhl_betting_lab.shadow.play_by_play import fetch_play_by_play, game_events
from nhl_betting_lab.shadow.talent import add_talent, goalie_tier, gsax_plus
from nhl_betting_lab.shadow.xg import add_expected_goals, context_design_matrix

#: The team ratings the public site's board is rated on (`--tables-only`).
RATINGS_FILE = "shadow_team_ratings.json"
#: Below this share of exact boxscore matches the parse is suspect.
MINIMUM_MATCH = 0.95
#: Above this share of failed fetches the coverage is suspect.
MAXIMUM_FETCH_FAILURES = 0.02


def _final_game_ids(team_games: pd.DataFrame) -> list[int]:
    frame = team_games.dropna(subset=["home_goals", "away_goals"])
    return sorted({int(g) for g in frame["game_id"] if int(g) > 0})


def _fmt(cell: dict) -> str:
    return f"{cell['per_1000']:+.2f} [{cell['low']:+.2f}, {cell['high']:+.2f}]"


def posthockey_tables(
    goalie_table: pd.DataFrame,
    latest: int,
    goalies_after: dict,
    shooters_after: dict,
    names: dict,
    player_table: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The latest season's goalies and shooters as PostHockey reports them.

    Goalies (10 or more games): GSAx(sh) against shooter-adjusted xG,
    GSAx+ (mean 100, SD 15 across them), Fenwick save percentage against
    its expectation (dFsv%), and the save-talent posterior with its A-F tier.
    Shooters: the ten highest finishing-talent posteriors among those with
    150 or more unblocked attempts counted, beside their goals above ixG.
    Empty when the run built no talent.
    """
    if not goalies_after or "xga_adj" not in goalie_table or goalie_table["xga_adj"].isna().all():
        return pd.DataFrame(), pd.DataFrame()
    regular = goalie_table[
        (goalie_table["season"] == latest) & (goalie_table["game_id"].astype(str).str[4:6] == "02")
    ]
    g = regular.groupby("goalie_id").agg(
        GP=("game_id", "nunique"), FA=("fa", "sum"), GA=("ga", "sum"), xGA_sh=("xga_adj", "sum")
    )
    g = g[g["GP"] >= 10]
    if g.empty:
        goalies = pd.DataFrame()
    else:
        g["GSAx(sh)"] = g["xGA_sh"] - g["GA"]
        g["GSAx+"] = gsax_plus(g["GSAx(sh)"])
        g["dFsv%"] = 100 * ((1 - g["GA"] / g["FA"]) - (1 - g["xGA_sh"] / g["FA"]))
        post = [goalies_after.get(i) for i in g.index]
        g["Save talent"] = [p.mean if p else float("nan") for p in post]
        g["Tier"] = [goalie_tier(p.mean, p.variance**0.5) if p else "" for p in post]
        g.insert(0, "Goalie", [names.get(i, str(i)) for i in g.index])
        g = g.sort_values("GSAx(sh)", ascending=False)
        g = g if len(g) <= 10 else pd.concat([g.head(5), g.tail(5)])
        goalies = g.drop(columns=["FA", "xGA_sh"]).round(3)
    rows = []
    for pid, post in shooters_after.items():
        mine = player_table[player_table["player_id"] == pid]
        attempts = int(mine["iff"].sum()) if not mine.empty else 0
        if attempts < 150:
            continue
        rows.append(
            {
                "Player": names.get(pid, str(pid)),
                "Unblocked attempts": attempts,
                "Goals": int(mine["igoals"].sum()),
                "GAx (context xG)": round(float(mine["igoals"].sum() - mine["ixg_ctx"].sum()), 1),
                "Finishing talent": round(post.mean, 3),
                "Talent SD": round(post.variance**0.5, 3),
            }
        )
    shooters = (
        pd.DataFrame(rows).sort_values("Finishing talent", ascending=False).head(10)
        if rows else pd.DataFrame()
    )
    return goalies, shooters


def render(
    payload: dict,
    table: pd.DataFrame,
    goalies: pd.DataFrame,
    shooters: pd.DataFrame,
    talent_goalies: pd.DataFrame | None = None,
    talent_shooters: pd.DataFrame | None = None,
) -> str:
    v = payload["validation"]
    lines = [
        "# Shadow model: modern stats against the card's model",
        "",
        "Built beside the card, never on it. The card's model is frozen until "
        "2027-04-25 (`docs/when_this_ends.md`), and nothing in "
        "`nhl_betting_lab.shadow` can reach the card or the forward ledger.",
        "",
        "**Read this first.** These are forecasting comparisons on outcomes, "
        "walk-forward. A stat that forecasts worse is ruled out. A stat that "
        "forecasts better has earned a price backtest, nothing more: the market "
        "already sees most of what these stats see, and only a price backtest "
        "decides (`CLAUDE.md`).",
        "",
        "## Data",
        "",
        f"- Games in `team_games.csv`: {payload['games_listed']}; play-by-play read for "
        f"{payload['games_read']}; fetch failures: {payload['fetch_failures']}.",
        f"- Shot attempts parsed: {payload['attempts']:,}; attempts whose shooting team "
        f"could not be told, and so dropped: {payload['unattributed']:,}.",
        f"- Check against the boxscore, {v['games']:,} games: shots on goal match exactly "
        f"in {100 * v['shots_match']:.1f}%, goals in {100 * v['goals_match']:.1f}%.",
        "",
        "Expected goals, each season fitted only on earlier seasons:",
        "",
        "| Season | Fitted on | Unblocked attempts | Goals | xG | Out of sample |",
        "|:--|:--|--:|--:|--:|:--|",
    ]
    for s in payload["xg_seasons"]:
        lines.append(
            f"| {s['season']} | {', '.join(map(str, s['fitted_on']))} | {s['attempts']:,} | "
            f"{s['goals']:,} | {s['expected']:,.0f} | {'no (not compared)' if s['in_sample'] else 'yes'} |"
        )
    if payload.get("context_xg_seasons"):
        lines += [
            "",
            "Context expected goals (PostHockey's prior-event context: the play "
            "before the attempt, how long ago and how far away, a rush flag, the "
            "score), each season fitted only on earlier seasons:",
            "",
            "| Season | Fitted on | Unblocked attempts | Goals | Context xG | Out of sample |",
            "|:--|:--|--:|--:|--:|:--|",
        ]
        for s in payload["context_xg_seasons"]:
            lines.append(
                f"| {s['season']} | {', '.join(map(str, s['fitted_on']))} | {s['attempts']:,} | "
                f"{s['goals']:,} | {s['expected']:,.0f} | {'no (not compared)' if s['in_sample'] else 'yes'} |"
            )
    lines += [
        "",
        "## Team strength: rated on each stat instead of goals",
        "",
        "Difference in log-likelihood per 1,000 games against the card's goals-based "
        "`TeamModel`, same structure, same games, same back-to-back adjustment. "
        "Positive is better. 95% intervals resample whole dates.",
        "",
        f"Games compared: {payload['team_games_scored']:,}.",
        "",
        "| Rated on | Goals scored | Moneyline | Total 5.5 | Verdict (moneyline) |",
        "|:--|--:|--:|--:|:--|",
    ]
    for e in payload["team"]:
        lines.append(
            f"| {e['label']} | {_fmt(e['goals_ll'])} | {_fmt(e['moneyline_ll'])} | "
            f"{_fmt(e['total_ll'])} | {e['moneyline_ll']['verdict']} |"
        )
    if payload.get("starter"):
        proj = payload.get("starter_projection") or {}
        lines += [
            "",
            "## Tonight's starting goalie against the team's goalies together",
            "",
            "The card's team markets rate goaltending on the team's goalies "
            "together (`xg_luck`). These keep its attack, defence and finishing "
            "and swap only the goaltending factor for the starter's own GSAx, "
            "built the same way over his own appearances on any team. Difference "
            "in log-likelihood per 1,000 games against `xg_luck`, the ratings the "
            "card runs on; positive is better.",
            "",
            "The actual starter is known only after puck drop, so that row is a "
            "ceiling. The projected starter is what a card could name before it: "
            "last game's starter, or on the second night of a back-to-back the "
            "goalie who made most of the team's other recent starts.",
            "",
        ]
        if proj.get("sides"):
            lines += [
                f"Projected starter was the actual one for {proj['correct']:,} of "
                f"{proj['sides']:,} sides ({100 * proj['rate']:.1f}%).",
                "",
            ]
        lines += [
            "| Goaltending factor | Games | Goals scored | Moneyline | Total 5.5 | Verdict (moneyline) |",
            "|:--|--:|--:|--:|--:|:--|",
        ]
        for e in payload["starter"]:
            lines.append(
                f"| {e['label']} | {e['rows']:,} | {_fmt(e['goals_ll'])} | {_fmt(e['moneyline_ll'])} | "
                f"{_fmt(e['total_ll'])} | {e['moneyline_ll']['verdict']} |"
            )
    lines += [
        "",
        "## Prop rates: shot attempts, ixG and recent form instead of box-score counts",
        "",
        "Difference in Poisson log-likelihood per 1,000 player-games against the "
        "card's construction (shrunk box-score rate per 60 over every game on "
        "disk, times trailing-10 ice time). Positive is better. Recent form is "
        "how a player is playing now: his rate with a game's weight halving every "
        f"{measurement.PROP_FORM_HALF_LIFE_GAMES} of his games, regressed toward "
        "his own long-run rate, set in advance and not tuned.",
        "",
        "| Market | Rate built on | Player-games | Difference | Verdict |",
        "|:--|:--|--:|--:|:--|",
    ]
    for stat, entries in payload["props"].items():
        for e in entries:
            lines.append(
                f"| {stat} | {e['label']} | {e['rows']:,} | {_fmt(e['ll'])} | {e['ll']['verdict']} |"
            )
    lines += ["", "## What it says", ""]
    lines += [f"- {s}" for s in payload["findings"]]
    if not table.empty:
        lines += [
            "",
            f"## {table.attrs.get('season', '')} team table",
            "",
            "All situations unless named. PDO is 5v5 on-ice shooting plus save "
            "percentage; GSAx is the team's goalies, empty nets excluded; "
            "high danger is within 25 ft and 45 degrees of the net (an "
            "approximation of the inner slot).",
            "",
            table.to_markdown(),
        ]
    if not goalies.empty:
        lines += ["", "## Goals saved above expected, latest season (min. 20 games)", "", goalies.to_markdown(index=False)]
    if not shooters.empty:
        lines += ["", "## Individual expected goals per 60, latest season (min. 500 minutes)", "", shooters.to_markdown(index=False)]
    if talent_goalies is not None and not talent_goalies.empty:
        lines += [
            "",
            "## Goalies as PostHockey rates them, latest season (min. 10 games)",
            "",
            "GSAx(sh) is goals saved above shooter-adjusted xG; GSAx+ rescales it "
            "to mean 100, SD 15 across these goalies; dFsv% is Fenwick save "
            "percentage minus its expectation; save talent is the posterior on "
            "the logit scale (positive saves more), and the tier says where its "
            "one-sigma band sits against average (A wholly above, F wholly below).",
            "",
            talent_goalies.to_markdown(index=False),
        ]
    if talent_shooters is not None and not talent_shooters.empty:
        lines += [
            "",
            "## Finishing talent, highest posteriors (min. 150 unblocked attempts)",
            "",
            "Logit-scale shift on context xG, updated shot by shot from the "
            "earliest season on disk and re-centred each season. A small SD "
            "means many shots; zero is league average.",
            "",
            talent_shooters.to_markdown(index=False),
        ]
    lines += [
        "",
        "## Not built, and why",
        "",
        "- WAR, GAR, xGAR, RAPM: Evolving-Hockey, paid.",
        "- Zone entries, exits, forecheck and passing microstats: All Three Zones, paid.",
        "- MoneyPuck's xG, flurry adjustment and deserve-to-win: licence required.",
        "- NHL EDGE skating and shot speed: no per-game archive to fit on game by game.",
        "- A confirmed-starter feed: the card runs before starters are confirmed. "
        "The starter section above measures the actual starter as a ceiling and "
        "a rule a card could follow before puck drop.",
        "- Score-adjusted 5v5 and a separate 5v5-plus-special-teams scoreline: not "
        "built yet; all-situations xG already carries the power play.",
        "- From PostHockey's glossary: Net Rating's on-ice half, Quality of "
        "Competition and Teammates, Implied Purpose, xGAx, WPAx and iWPA all "
        "need shift charts and a win-probability model; linemates from shift "
        "charts were already tested here against prices and did not beat them. "
        "Badges are a display of the same numbers. All Three Zones microstats "
        "are licensed to PostHockey's Patreon patrons.",
        "- Talent here has no age drift (no birth dates on the shot table) and "
        "no league scoring-environment term (each season's base model carries "
        "its own intercept).",
    ]
    return "\n".join(lines) + "\n"


def findings(
    team: list[dict], props: dict[str, list[dict]], starter: list[dict] | None = None
) -> list[str]:
    out: list[str] = []
    better = [e["label"] for e in team if e["moneyline_ll"]["verdict"].startswith("better")]
    worse = [e["label"] for e in team if e["moneyline_ll"]["verdict"].startswith("worse")]
    out.append(
        "Team strength on the moneyline: "
        + (f"better than goals for {', '.join(better)}. " if better else "no stat beat goals. ")
        + (f"Worse for {', '.join(worse)}." if worse else "")
    )
    for stat, entries in props.items():
        wins = [e["label"] for e in entries if e["ll"]["verdict"].startswith("better")]
        out.append(
            f"{stat}: " + (f"better than the box-score rate with {', '.join(wins)}." if wins
                           else "no shadow rate beat the box-score rate.")
        )
    for e in starter or []:
        out.append(
            f"{e['label']}: {e['moneyline_ll']['verdict']} on the moneyline against "
            f"the card's team-goalie ratings ({_fmt(e['moneyline_ll'])} per 1,000 games)."
        )
    out.append(
        "Anything better here is a candidate for a price backtest, and any change "
        "to the card waits for 2027-04-25 and Cooper's decision."
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    parser.add_argument(
        "--tables-only",
        action="store_true",
        help="Write the per-game tables and stop, with no comparison or report "
        "(Publish Site, which rates the board's teams on them). Tables that "
        "disagree with the boxscores are not written.",
    )
    parser.add_argument(
        "--price-backtest",
        action="store_true",
        help="Write the tables, then price the bought team markets on the "
        "card's goals ratings and on the site's xG ratings, walk-forward on "
        "identical games, and stop.",
    )
    args = parser.parse_args(argv)
    prices_path = args.processed_dir / "historical_team_prices.csv"
    if args.price_backtest and not prices_path.is_file():
        print(f"No bought team prices at {prices_path}.", file=sys.stderr)
        return 1

    team_games = load_team_games(args.processed_dir)
    if team_games.empty:
        print("No team games on disk; build the datasets first.", file=sys.stderr)
        return 1
    ids = _final_game_ids(team_games)
    failures = 0
    events = []
    for number, gid in enumerate(ids, 1):
        payload = None
        if args.fetch:
            try:
                payload = fetch_play_by_play(gid, raw_dir=args.raw_dir).payload
            except NhlApiError as exc:
                failures += 1
                print(f"Play-by-play {gid}: {exc}", file=sys.stderr)
        else:
            payload = _read_cache(_cache_root(args.raw_dir) / "play_by_play" / f"{gid}.json")
        if payload is not None and game_is_final(payload):
            events.append(game_events(payload))
        if number % 500 == 0:
            print(f"Play-by-play: {number} of {len(ids)} games")
    shots = pd.DataFrame([s for e in events for s in e.shots])
    if shots.empty:
        print("No play-by-play on disk; run with --fetch.", file=sys.stderr)
        return 1
    scored, seasons = add_expected_goals(shots)
    shooters_after: dict = {}
    goalies_after: dict = {}
    context_seasons: list = []
    if not (args.tables_only or args.price_backtest):
        # PostHockey's glossary (posthockey.com/glossary): context xG, then
        # shooter and goalie talent updated shot by shot. Only the full
        # measurement builds them; the ratings the site and the card read come
        # from `xg` alone and do not move.
        scored, context_seasons = add_expected_goals(
            scored, column="xg_ctx", design=context_design_matrix
        )
        dates = team_games.drop_duplicates("game_id").set_index("game_id")["date"].astype(str)
        scored["date"] = scored["game_id"].map(dates).fillna("")
        scored, shooters_after, goalies_after = add_talent(scored, base="xg_ctx", order="date")
    team_table, player_table, goalie_table = build_tables(events, scored)
    validation = measurement.validate_against_boxscores(team_games, team_table)
    if (args.tables_only or args.price_backtest) and not _agrees(validation):
        return 2
    args.processed_dir.mkdir(parents=True, exist_ok=True)
    team_table.to_csv(args.processed_dir / "shadow_team_games.csv", index=False)
    player_table.to_csv(args.processed_dir / "shadow_player_games.csv", index=False)
    goalie_table.to_csv(args.processed_dir / "shadow_goalie_games.csv", index=False)

    if args.tables_only:
        model = TeamModel().fit(team_games)
        try:
            ratings = measurement.xg_team_ratings(model.home_advantage, team_games, team_table)
        except ValueError as exc:
            print(f"::error::{exc} No team ratings written.")
            return 2
        (args.processed_dir / RATINGS_FILE).write_text(
            json.dumps(ratings, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"Shadow tables: {len(events)} of {len(ids)} games read, "
            f"{failures} fetch failure(s), shots match {validation['shots_match']:.1%}, "
            f"goals {validation['goals_match']:.1%}."
        )
        return 0

    if args.price_backtest:
        print(
            f"Shadow tables: {len(events)} of {len(ids)} games read, "
            f"{failures} fetch failure(s)."
        )
        return price_backtest(team_games, team_table, pd.read_csv(prices_path), args)

    out_of_sample = {s.season for s in seasons if not s.in_sample}
    team_rows, team_summary = measurement.compare_team_models(
        team_games, team_table, scored_seasons=out_of_sample, goalie_games=goalie_table
    )
    starter_summary = measurement.starter_against_card(team_rows)
    logs = load_player_logs(args.processed_dir)
    _, prop_summary = measurement.compare_prop_rates(
        logs,
        player_table,
        scored_seasons=out_of_sample,
        covered_games={e.game_id for e in events},
    )

    names = (
        logs.drop_duplicates("player_id", keep="last").set_index("player_id")["player"].to_dict()
        if not logs.empty
        else {}
    )
    latest = int(team_table["season"].max())
    regular = lambda f: f[f["game_id"].astype(str).str[4:6] == "02"]  # noqa: E731
    g = regular(goalie_table[goalie_table["season"] == latest])
    g = g.groupby("goalie_id").agg(GP=("game_id", "nunique"), xGA=("xga", "sum"), GA=("ga", "sum"))
    g = g[g["GP"] >= 20]
    g["GSAx"] = g["xGA"] - g["GA"]
    g.insert(0, "Goalie", [names.get(i, str(i)) for i in g.index])
    goalies = pd.concat([g.nlargest(5, "GSAx"), g.nsmallest(5, "GSAx")]).round(1)
    talent_goalies, talent_shooters = posthockey_tables(
        goalie_table, latest, goalies_after, shooters_after, names, player_table
    )
    toi = regular(logs[pd.to_numeric(logs["season"], errors="coerce") == latest]) if not logs.empty else logs
    p = regular(player_table[player_table["season"] == latest]).groupby("player_id")[["ixg", "igoals", "icf"]].sum()
    if not toi.empty:
        p = p.join(toi.groupby("player_id")["toi_seconds"].sum(), how="inner")
        p = p[p["toi_seconds"] >= 500 * 60]
        p["ixG/60"] = p["ixg"] / p["toi_seconds"] * 3600
        p["iCF/60"] = p["icf"] / p["toi_seconds"] * 3600
        p.insert(0, "Player", [names.get(i, str(i)) for i in p.index])
        shooters = p.nlargest(10, "ixG/60")[["Player", "ixg", "igoals", "ixG/60", "iCF/60"]].round(2)
    else:
        shooters = pd.DataFrame()

    payload = {
        "games_listed": len(ids),
        "games_read": len(events),
        "fetch_failures": failures,
        "attempts": int(len(shots)),
        "unattributed": int(sum(e.unattributed for e in events)),
        "validation": validation,
        "xg_seasons": [s.__dict__ for s in seasons],
        "context_xg_seasons": [s.__dict__ for s in context_seasons],
        "team_games_scored": int(team_rows["game_id"].nunique()) if not team_rows.empty else 0,
        "team": team_summary,
        "starter": starter_summary,
        "starter_projection": team_rows.attrs.get("starter_projection"),
        "props": prop_summary,
        "findings": findings(team_summary, prop_summary, starter_summary),
    }
    table = measurement.latest_season_table(team_table)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "shadow_stats.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    report = render(payload, table, goalies, shooters, talent_goalies, talent_shooters)
    (args.output_dir / "shadow_stats.md").write_text(report, encoding="utf-8")
    print(report)

    if failures > MAXIMUM_FETCH_FAILURES * max(len(ids), 1):
        print(f"::error::{failures} of {len(ids)} play-by-play fetches failed.")
        return 2
    if not _agrees(validation):
        return 2
    return 0


#: The windows the bought team store holds (`stores.label_phases`).
PRICE_WINDOWS = ("late", "early")


def xg_rater(team_games: pd.DataFrame, team_table: pd.DataFrame):
    """A `generate_team_samples` hook rating teams as the site does.

    Each refit takes the `xg_luck` factors from the play-by-play of games
    strictly before the window it prices, combined as
    `measurement.xg_team_ratings` combines them, so the backtest prices what
    the board would have shown that day. A window with no prior play-by-play
    is refused.
    """
    games = team_games[pd.to_numeric(team_games["game_type"], errors="coerce") == 2].copy()
    games["game_id"] = pd.to_numeric(games["game_id"], errors="coerce")
    games["_date"] = games["date"].map(measurement._as_date)
    metrics = team_table.copy()
    metrics["game_id"] = pd.to_numeric(metrics["game_id"], errors="coerce")
    metrics = metrics.merge(games.dropna(subset=["_date"])[["game_id", "_date"]], on="game_id")
    variant = next(v for v in measurement.TEAM_VARIANTS if v.key == measurement.SITE_VARIANT_KEY)

    def rate(model: TeamModel, start) -> None:
        history = metrics[metrics["_date"] < start]
        if history.empty:
            raise ValueError("no play-by-play before this window")
        for team, f in measurement.shadow_factors(history, variant, model.home_advantage).items():
            current = model.teams.get(team)
            model.teams[team] = TeamRates(
                team=team,
                games=current.games if current else 0,
                attack=f["attack"] * f["finishing"],
                defence=f["defence"] * f["goalie"],
            )

    return rate


def _cell(roi) -> str:
    if roi is None or not roi.bets:
        return "no bets"
    return (
        f"{roi.roi:+.1%} over {roi.bets:,} ({roi.low:+.1%} .. {roi.high:+.1%}; "
        f"corrected {roi.adjusted_low:+.1%} .. {roi.adjusted_high:+.1%})"
    )


def price_backtest(team_games, team_table, prices, args) -> int:
    """The bought team markets, priced on goals and on xG, same games."""
    use_rest = ships("team_b2b", output_dir=args.output_dir)
    goals, goals_walk = generate_team_samples(team_games, use_rest=use_rest)
    xg, xg_walk = generate_team_samples(
        team_games, use_rest=use_rest, rate=xg_rater(team_games, team_table)
    )
    common = set(goals["game_id"]) & set(xg["game_id"])
    goals = goals[goals["game_id"].isin(common)]
    xg = xg[xg["game_id"].isin(common)]
    print(f"Goals ratings: {goals_walk.summary_line()}")
    print(f"xG ratings: {xg_walk.summary_line()}")
    print(f"Compared on {len(common):,} games both priced.")

    payload: dict = {"games": len(common), "use_rest": use_rest, "windows": {}}
    lines = [
        "# Team markets against real prices: goals ratings vs xG ratings",
        "",
        "Walk-forward on identical games: each refit sees only games before the "
        "window it prices. Goals is the card's `TeamModel`; xG is the same "
        "model with every team rated as the public site rates it (recent xG, "
        "a finishing factor and a goaltending/GSAx factor). One bet per wager "
        "at the best price, flat stakes, at the measurement's edge bar. An "
        "interval that includes zero means no demonstrated edge.",
        "",
        f"Games compared: {len(common):,}. Back-to-back adjustment: "
        f"{'in force' if use_rest else 'off'}.",
    ]
    for window in PRICE_WINDOWS:
        try:
            reports = {
                name: build_team_measurement(
                    samples, prices, phase=window, processed_dir=args.processed_dir
                )
                for name, samples in (("goals", goals), ("xg", xg))
            }
        except (MixedWindowError, UnresolvedTeamsError) as exc:
            print(f"::error::{exc}")
            return 2
        lines += [
            "",
            f"## `{window}` window (median {reports['goals'].phase_hours:.1f}h before face-off)",
            "",
            "| Market | Goals ratings | xG ratings |",
            "|:--|:--|:--|",
        ]
        by_market = {
            name: {m.market: m.priced for m in report.markets}
            for name, report in reports.items()
        }
        payload["windows"][window] = {}
        for market in sorted(set(by_market["goals"]) | set(by_market["xg"])):
            g, x = by_market["goals"].get(market), by_market["xg"].get(market)
            if (g is None or not g.bets) and (x is None or not x.bets):
                continue
            lines.append(f"| {market} | {_cell(g)} | {_cell(x)} |")
            payload["windows"][window][market] = {
                name: (
                    {"bets": r.bets, "roi": r.roi, "low": r.low, "high": r.high,
                     "adjusted_low": r.adjusted_low, "adjusted_high": r.adjusted_high}
                    if r is not None and r.bets else None
                )
                for name, r in (("goals", g), ("xg", x))
            }
    report_text = "\n".join(lines) + "\n"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "shadow_price_backtest.md").write_text(report_text, encoding="utf-8")
    (args.output_dir / "shadow_price_backtest.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(report_text)
    return 0


def _agrees(validation: dict) -> bool:
    if validation["games"] and min(validation["shots_match"], validation["goals_match"]) < MINIMUM_MATCH:
        print(
            "::error::The play-by-play disagrees with the boxscores too often "
            f"(shots {validation['shots_match']:.1%}, goals {validation['goals_match']:.1%}); "
            "the parse is suspect and its numbers should not be trusted."
        )
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
