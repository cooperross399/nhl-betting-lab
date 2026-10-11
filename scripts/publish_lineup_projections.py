#!/usr/bin/env python3
"""Send tonight's DraftKings projections to The Lineup.

    PYTHONPATH=src .venv/bin/python scripts/publish_lineup_projections.py

The Lineup is Cooper's DFS lineup builder, a separate app on a Cloudflare
Worker. Its projection used to be DraftKings' season average nudged by the
website board's team numbers; this sends it the lab's own: every modelled
player on tonight's slate, his expected DraftKings points, a p10/p90 range and
the four bonus chances (`nhl_betting_lab.dfs_projections`).

**The books' numbers stay off by default, measured.** The DFS Projection Test
(2026-10-11, 83,183 player-games with a card-window prop) found the model's
own means closer than the books' de-vigged ones: MAE 4.665 against 4.785,
paired +0.120 [+0.111, +0.129] in the model's favour, because a proportional
de-vig leaves the over's shading in, so the books' means run high (bias
+0.818 against +0.180). `--anchor-on-books` sends them anyway.

**What leaves, and what never does.** Names, teams, expected counts and
DraftKings points. Never a price, a line, a book, a player id or a capture
time: the means derived from the staged prices are the only trace of them.

**Not evidence, and nothing in the lab reads it back.** It places no bet,
freezes no opinion, touches no card and spends no credit (it reads the prices
the run already staged). A failed send costs the app one night of lab
projections, so the workflow step is `continue-on-error`; this exits 0 when
there is nothing to send (no token, no slate, no logs) and 1 when the worker
refuses the send.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

from nhl_betting_lab import verdicts
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR, STAGING_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import current_rosters
from nhl_betting_lab.dfs_projections import project_slate, staged_quotes
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.models.team_ratings import apply_xg_ratings
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.team_names import load_team_name_map
from nhl_betting_lab.rest import last_played_dates, played_previous_day
from nhl_betting_lab.season import LEAGUE_TIMEZONE, scheduled_regular_season_starts

DEFAULT_URL = "https://the-lineup.cooperross399.workers.dev"
TOKEN_ENV = "LINEUP_INGEST_TOKEN"
USER_AGENT = "nhl-betting-lab/1.0 (publishes projections to The Lineup)"
EXIT_REFUSED = 1


def post(url: str, token: str, body: dict, *, timeout: float = 30.0) -> tuple[int, str]:
    """The same POST `publish_lineup_lines.py` makes, with the same token."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def staged_props(staging_dir: Path) -> pd.DataFrame:
    path = staging_dir / odds_api.STAGING_PROPS_FILENAME
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def build_payload(
    day: str, *, processed: Path, raw: Path, staging: Path, outputs: Path, anchor: bool = False,
) -> dict | None:
    games_today = {
        (home, away): start
        for (date, home, away), start in scheduled_regular_season_starts(raw_dir=raw).items()
        if date == day
    }
    if not games_today:
        print(f"No regular-season game is scheduled for {day}: nothing sent to The Lineup.")
        return None
    logs = load_player_logs(processed)
    games = load_team_games(processed)
    if logs.empty or games.empty:
        print("No player logs or game history on disk: nothing sent to The Lineup.")
        return None
    model = PlayerPropsModel().fit(logs)
    team_model = TeamModel().fit(games)
    ratings, detail = apply_xg_ratings(team_model, games, processed)
    print(f"Team ratings for goalie win chances: {ratings} ({detail}).")

    b2b: dict[str, bool] = {}
    if verdicts.ships("props_b2b", output_dir=outputs):
        last = last_played_dates(games)
        for home, away in games_today:
            for team in (home, away):
                b2b[team] = played_previous_day(last, team, day)

    team_names = load_team_name_map(processed_dir=processed, raw_dir=raw)
    quotes = (
        staged_quotes(staged_props(staging), model, set(games_today), team_names=team_names)
        if anchor else []
    )
    rows = project_slate(
        model, team_model, games_today,
        rosters=current_rosters(raw_dir=raw), b2b=b2b, quotes=quotes,
    )
    anchored = sum(1 for row in rows if row["source"] == "market")
    print(
        f"Projected {len(rows)} player(s) across {len(games_today)} game(s); "
        + (f"{anchored} carry at least one stat from the books' de-vigged prices "
           f"({len(quotes)} two-sided quotes read)." if anchor else "the books' numbers were not used.")
    )
    return {
        "model": "nhl-betting-lab dfs v1",
        "scoring": "DraftKings classic NHL (short-handed and shootout bonuses not modelled)",
        "teamRatings": ratings,
        "note": (
            "Expected DraftKings points from the lab's player model"
            + ("; where books post a prop, the de-vigged price sets that stat's mean. " if anchor else ". ")
            + "p10/p90 simulate the night with stats drawn independently. "
            "Goalies are projected as if they start."
        ),
        "rows": rows,
    }


def main(argv: list[str] | None = None, *, send=post) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--date", default="", help="League date; blank is today in New York.")
    parser.add_argument("--url", default=os.environ.get("LINEUP_WORKER_URL", DEFAULT_URL))
    parser.add_argument("--anchor-on-books", action="store_true",
                        help="Replace the model's means with the books' de-vigged ones (measured worse).")
    args = parser.parse_args(argv)

    day = args.date or datetime.now(LEAGUE_TIMEZONE).date().isoformat()
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"{TOKEN_ENV} is not set: nothing sent to The Lineup.")
        return 0
    payload = build_payload(
        day, processed=Path(args.processed_dir), raw=Path(args.raw_dir),
        staging=Path(args.staging_dir), outputs=Path(args.output_dir), anchor=args.anchor_on_books,
    )
    if not payload or not payload["rows"]:
        return 0
    endpoint = f"{args.url.rstrip('/')}/projections?sport=NHL&date={day}"
    status, text = send(endpoint, token, payload)
    if status != 200:
        print(f"::warning::The Lineup refused the {day} projections (HTTP {status}): {text[:300]}")
        return EXIT_REFUSED
    print(f"Sent {len(payload['rows'])} projection(s) to The Lineup for {day}.")
    print("This spent no provider credits, touched no card, and froze no opinion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
