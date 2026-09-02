"""Pre-game line combinations and power-play units, with the instant they were known.

The model's largest residual error is one cell: it bets unders on players
whose ice time is about to RISE, priced on the minutes they used to play.
`docs/where_the_remaining_error_lives.md` measures that cell at -6.44% over
5,661 bets and shows an oracle on future ice time is worth about five points.
It also shows the information is **not in the box score** (R-squared 0.080).

`capture_deployment.py` already records who is OUT, from the NHL's own API.
That is only half the signal. A scratch list says nothing about the winger
promoted from the fourth line to the first, or moved onto the top power-play
unit -- which is precisely the "usage about to rise" event that costs the
model money. This module reads that promotion signal.

**Every row carries two timestamps, and they mean different things.**

* `source_updated_at` is what the source itself claims about its data. It
  says how STALE the underlying report is.
* `retrieved_at` is when this lab actually held the value. It is the only
  timestamp that establishes AVAILABILITY, and it is the one
  `usable_before` gates on.

A backfilled "current" line combination presented as though it existed
earlier in the day is the exact leak that would manufacture an edge out of
nothing, which is why nothing here reconstructs history: the collector runs
forward and a night not captured is gone. This lab has retracted four
findings, one of them settled against another season's games; a timestamp
that cannot be defended is worth less than no data at all.

`sourceName` is kept because it is the provenance field: off-season pages say
"Projected", and in-season pages name the report the lines came from. A
projection and a confirmed morning-skate line are not the same evidence and
must never be pooled without saying so.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

#: The Next.js payload the team pages embed. Reading this rather than the
#: rendered table means the parse breaks loudly on a redesign instead of
#: silently returning the wrong players.
NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)

TEAM_PAGE = "https://www.dailyfaceoff.com/teams/{slug}/line-combinations"

#: Groups that mean a player is dressed and deployed. `ir` and `sk` bench
#: groups are recorded too -- an injured-reserve row is information -- but
#: only these carry a deployment rank.
EV_GROUPS = ("f1", "f2", "f3", "f4", "d1", "d2", "d3", "d4")
PP_GROUPS = ("pp1", "pp2")
PK_GROUPS = ("pk1", "pk2")

COLUMNS = (
    "team_slug",
    "team_abbreviation",
    "team_name",
    "player_id",
    "player",
    "player_slug",
    "group_identifier",
    "group_name",
    "category_identifier",
    "position_identifier",
    "injury_status",
    "game_time_decision",
    "source_name",
    "source_updated_at",
    "retrieved_at",
)


def team_slugs(html: str) -> tuple[str, ...]:
    """Every team's slug, read from the page's own team list.

    Hard-coding thirty-two slugs would rot the first time a club is renamed
    or added, and would rot silently -- a missing team looks exactly like a
    team with no lines posted.
    """
    payload = parse_next_data(html)
    teams = (payload.get("props", {}).get("pageProps", {}) or {}).get(
        "sortedTeams"
    ) or []
    slugs = [str(t.get("slug", "")).strip() for t in teams if t.get("slug")]
    return tuple(dict.fromkeys(slugs))


def parse_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA.search(html or "")
    if not match:
        raise ValueError(
            "No __NEXT_DATA__ payload in the page. The site's shape has "
            "changed, or the response was an error page rather than a team "
            "page. Refusing to guess at the rendered HTML."
        )
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"__NEXT_DATA__ was not JSON: {exc}") from exc


def rows_from_page(html: str, *, retrieved_at: str) -> list[dict[str, Any]]:
    """One row per (player, group). A player appears once per unit he is on.

    Matthew Knies on the first line and the first power-play unit is two
    rows, `f1` and `pp1`, because those are two separate facts that can move
    independently -- and a promotion to PP1 without a line change is exactly
    the event this collector exists to catch.
    """
    payload = parse_next_data(html)
    combos = (payload.get("props", {}).get("pageProps", {}) or {}).get(
        "combinations"
    )
    if not isinstance(combos, dict):
        return []

    shared = {
        "team_slug": str(combos.get("teamSlug", "") or ""),
        "team_abbreviation": str(combos.get("teamAbbreviation", "") or ""),
        "team_name": str(combos.get("teamName", "") or ""),
        "source_name": str(combos.get("sourceName", "") or ""),
        "source_updated_at": str(combos.get("updatedAt", "") or ""),
        "retrieved_at": str(retrieved_at),
    }

    rows: list[dict[str, Any]] = []
    for player in combos.get("players") or []:
        if not isinstance(player, dict):
            continue
        rows.append({
            **shared,
            "player_id": player.get("playerId", ""),
            "player": str(player.get("name", "") or ""),
            "player_slug": str(player.get("playerSlug", "") or ""),
            "group_identifier": str(player.get("groupIdentifier", "") or ""),
            "group_name": str(player.get("groupName", "") or ""),
            "category_identifier": str(player.get("categoryIdentifier", "") or ""),
            "position_identifier": str(player.get("positionIdentifier", "") or ""),
            "injury_status": str(player.get("injuryStatus") or ""),
            "game_time_decision": bool(player.get("gameTimeDecision", False)),
        })
    return rows


def usable_before(frame, moment):
    """Only rows this lab demonstrably HELD before `moment`.

    Gated on `retrieved_at`, never on `source_updated_at`. The source's own
    timestamp describes the freshness of a claim, not our possession of it,
    and a source is free to restate it. Using it as the availability gate
    would let a value fetched this evening be treated as though it had been
    in hand this morning -- which is the leak that turns any deployment
    dataset into a fabricated edge.

    `moment` is normally the snapshot instant of the price being tested.
    """
    import pandas as pd

    if frame is None or len(frame) == 0:
        return frame
    when = pd.to_datetime(moment, errors="coerce", utc=True)
    if pd.isna(when):
        raise ValueError(f"Not a usable moment: {moment!r}")
    held = pd.to_datetime(frame["retrieved_at"], errors="coerce", utc=True)
    # A row with no readable retrieval time cannot be shown to have been
    # available, so it is dropped rather than assumed.
    return frame[held.notna() & (held <= when)]


def deployment_rank(rows: Iterable[dict[str, Any]]) -> dict[Any, dict[str, str]]:
    """Per player: which even-strength line, and which special-teams units.

    Returned as plain strings ("f1", "pp2") rather than numbers, because the
    gap between the first and second line is not one unit of anything and
    treating it as arithmetic is how a role signal becomes a fake feature.
    """
    out: dict[Any, dict[str, str]] = {}
    for row in rows:
        pid = row.get("player_id")
        if pid in (None, ""):
            continue
        group = str(row.get("group_identifier", ""))
        seat = out.setdefault(pid, {"ev": "", "pp": "", "pk": ""})
        if group in EV_GROUPS:
            seat["ev"] = group
        elif group in PP_GROUPS:
            seat["pp"] = group
        elif group in PK_GROUPS:
            seat["pk"] = group
    return out
