#!/usr/bin/env python3
"""Send tonight's forward lines and power-play units to The Lineup.

    PYTHONPATH=src .venv/bin/python scripts/publish_lineup_lines.py

The Lineup is Cooper's DFS lineup builder, a separate app on a Cloudflare
Worker. It stacks linemates and power-play mates, and it reads those units
from the worker's `GET /lines?sport=NHL&date=YYYY-MM-DD`. This script fills
that route from the capture `capture_line_combinations.py` just appended to,
once per Line Movement round.

**What leaves, and what never does.** For each team it sends only the most
recent snapshot in today's file: the four forward lines as `L1`-`L4` and the
two power-play units as `PP1`/`PP2`, by player name, plus that snapshot's
source name and timestamps. It never sends earlier snapshots, player ids,
defence pairs, penalty-kill units, goalies or the injured-reserve group. The
capture history stays where it lives, in the private movement chain; this
repository stays free of it (`.gitignore` keeps `line_combinations/` out),
and the worker expires each date after three days so it never accumulates an
archive either.

**This is not evidence and nothing in the lab reads it back.** It places no
bet, freezes no opinion and touches no card. A failed send costs the app one
round of fresher lines, so the workflow step is `continue-on-error` and this
script exits 0 when there is nothing to send (no token, no file, no lines).
A send the worker refuses exits 1, which the step names in the run summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.season import LEAGUE_TIMEZONE


LINES_DIRNAME = "line_combinations"
DEFAULT_URL = "https://the-lineup.cooperross399.workers.dev"
TOKEN_ENV = "LINEUP_INGEST_TOKEN"
USER_AGENT = "nhl-betting-lab/1.0 (publishes line units to The Lineup)"

#: group_identifier -> (kind, label). Everything else in the capture stays home.
UNITS = {
    "f1": ("line", "L1"),
    "f2": ("line", "L2"),
    "f3": ("line", "L3"),
    "f4": ("line", "L4"),
    "pp1": ("pp", "PP1"),
    "pp2": ("pp", "PP2"),
}

#: Within a unit, players in the order the source places them.
SLOT_ORDER = {"lw": 0, "c": 1, "rw": 2, "sk1": 0, "sk2": 1, "sk3": 2, "sk4": 3, "sk5": 4}

EXIT_REFUSED = 1


def lines_path(day: str, *, processed_dir: Path | None = None) -> Path:
    return (processed_dir or PROCESSED_DIR) / LINES_DIRNAME / f"{day}.csv"


def latest_snapshot(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Each team's rows from its own most recent capture, and no older ones.

    Per team, not file-wide: a round that lost a team's page still holds an
    earlier read of it, and that earlier read is better than a hole.
    """
    rows = list(rows)
    newest: dict[str, str] = {}
    for row in rows:
        team, held = row.get("team_abbreviation", ""), row.get("retrieved_at", "")
        if team and held > newest.get(team, ""):
            newest[team] = held
    return [
        row for row in rows
        if row.get("team_abbreviation") and row.get("retrieved_at") == newest[row["team_abbreviation"]]
    ]


def lineup_payload(rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    """The worker's `/lines` body: `{"lines": [...], "sources": {...}}`."""
    units: dict[tuple[str, str], list[tuple[int, str]]] = {}
    sources: dict[str, dict[str, str]] = {}
    for row in latest_snapshot(rows):
        team = row["team_abbreviation"]
        sources.setdefault(team, {
            "sourceName": row.get("source_name", ""),
            "sourceUpdatedAt": row.get("source_updated_at", ""),
            "retrievedAt": row.get("retrieved_at", ""),
        })
        group = row.get("group_identifier", "")
        player = (row.get("player") or "").strip()
        if group not in UNITS or not player:
            continue
        slot = SLOT_ORDER.get(row.get("position_identifier", ""), 9)
        members = units.setdefault((team, group), [])
        if player not in (name for _, name in members):
            members.append((slot, player))

    order = list(UNITS)
    lines = []
    for team, group in sorted(units, key=lambda key: (key[0], order.index(key[1]))):
        kind, label = UNITS[group]
        lines.append({
            "team": team,
            "kind": kind,
            "label": label,
            "players": [name for _, name in sorted(units[(team, group)])],
        })
    return {"lines": lines, "sources": dict(sorted(sources.items()))}


def post(url: str, token: str, body: dict[str, Any], *, timeout: float = 20.0) -> tuple[int, str]:
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


def main(argv: list[str] | None = None, *, send=post) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--date", default="", help="League date; blank is today in New York.")
    parser.add_argument("--url", default=os.environ.get("LINEUP_WORKER_URL", DEFAULT_URL))
    args = parser.parse_args(argv)

    day = args.date or datetime.now(LEAGUE_TIMEZONE).date().isoformat()
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"{TOKEN_ENV} is not set: nothing sent to The Lineup.")
        return 0

    path = lines_path(day, processed_dir=Path(args.processed_dir))
    if not path.is_file():
        print(f"No line capture for {day} at {path}: nothing sent to The Lineup.")
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        payload = lineup_payload(csv.DictReader(handle))
    if not payload["lines"]:
        print(f"The {day} capture holds no forward lines or power-play units: nothing sent.")
        return 0

    endpoint = f"{args.url.rstrip('/')}/lines?sport=NHL&date={day}"
    status, text = send(endpoint, token, payload)
    teams = len(payload["sources"])
    if status != 200:
        print(f"::warning::The Lineup refused the {day} lines (HTTP {status}): {text[:300]}")
        return EXIT_REFUSED
    print(f"Sent {len(payload['lines'])} unit(s) for {teams} team(s) to The Lineup for {day}.")
    print("This spent no provider credits, touched no card, and froze no opinion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
