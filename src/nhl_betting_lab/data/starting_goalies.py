"""Tonight's starting goalies, so a saves prop is staked only on the starter.

On 2026-10-14 the card staked Jake Oettinger over 24.5 saves (-110, Fliff,
0.25u) in DAL @ COL. Casey DeSmith had been confirmed as Dallas's starter at
11:46 UTC, two hours before the 9:40 AM ET card, and Oettinger did not play.
The card had been told, when `goalie_saves` left `HARD_GATED_MARKETS` on
2026-10-12, that "books post a saves line only for the goalie they expect to
start". That is false: the same card priced BOTH Colorado goalies (Mackenzie
Blackwood over 21.5 and Scott Wedgewood under 22.5 were both leans), and a
book still quoted Oettinger at 20:41 UTC, eight hours after DeSmith was
confirmed. A posted line is not a starter.

Daily Faceoff publishes each night's starters with a strength label
("Confirmed", "Likely", "Unconfirmed", ...). This module reads that page's
Next.js payload, never the rendered table, so a redesign breaks loudly. The
card reads the result through `GoalieStarters.reason`: a `goalie_saves` best
bet is staked only on the goalie the page lists as his team's starter, and
only when the label is in `STAKEABLE_STRENGTHS`. Anything else -- another
goalie listed, an unconfirmed guess, no listing for the game, or no page at
all -- keeps the opinion as a lean at zero units and names why. Ambiguity
falls on the unstaked side, as the puck-drop guard's does.

What leaves the page: the date, both teams, both goalies, each strength
label, the source's own news timestamp and the instant this lab fetched it.
Not the page's moneylines or anything else.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from nhl_betting_lab.models.player_props import player_key
from nhl_betting_lab.providers.team_names import normalize_team_name

PAGE = "https://www.dailyfaceoff.com/starting-goalies"
FILENAME = "starting_goalies.csv"

NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)

COLUMNS = (
    "date",
    "starts_at",
    "team",
    "opponent",
    "side",
    "goalie",
    "strength",
    "news_at",
    "retrieved_at",
)

#: Labels a saves stake may go on. "Confirmed" is the team or a beat writer
#: saying so; "Likely" and "Expected" are the site's word for a starter it
#: has reported but not seen confirmed. "Unconfirmed" is the site's own guess
#: from the rotation, which is exactly the heuristic
#: `docs/goalie_props_need_a_confirmed_starter.md` refuses.
STAKEABLE_STRENGTHS = frozenset({"confirmed", "likely", "expected"})

#: A listing older than this is not tonight's word on the starter.
MAX_AGE = timedelta(hours=12)

PREFIX = "Not tonight's known starter:"


def parse_page(html: str, *, retrieved_at: str) -> list[dict[str, str]]:
    """One row per team per game on the page."""
    match = NEXT_DATA.search(html or "")
    if not match:
        raise ValueError(
            "No __NEXT_DATA__ payload on the starting-goalies page: the site "
            "changed shape, or this was an error page."
        )
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"__NEXT_DATA__ was not JSON: {exc}") from exc
    props = (payload.get("props") or {}).get("pageProps") or {}
    games = props.get("data") if isinstance(props, dict) else None
    if not isinstance(games, list):
        raise ValueError(
            "The starting-goalies payload carries no `data` list of games."
        )
    rows: list[dict[str, str]] = []
    for game in games:
        if not isinstance(game, dict):
            continue
        for side, other in (("home", "away"), ("away", "home")):
            goalie = str(game.get(f"{side}GoalieName") or "").strip()
            team = str(game.get(f"{side}TeamName") or "").strip()
            if not team:
                continue
            rows.append({
                "date": str(game.get("date") or "").strip(),
                "starts_at": str(game.get("dateGmt") or "").strip(),
                "team": team,
                "opponent": str(game.get(f"{other}TeamName") or "").strip(),
                "side": side,
                "goalie": goalie,
                "strength": str(game.get(f"{side}NewsStrengthName") or "").strip(),
                "news_at": str(game.get(f"{side}NewsCreatedAt") or "").strip(),
                "retrieved_at": str(retrieved_at),
            })
    return rows


@dataclass
class GoalieStarters:
    """What the card knows about tonight's starters.

    `listings` maps (league day, normalized team) to (goalie, strength).
    `unknown` is set when there is nothing to read at all, and says why;
    every saves stake is then withheld with that reason.
    """

    listings: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    unknown: str = ""
    retrieved_at: str = ""

    def reason(self, *, player: str, home: str, away: str, day: str) -> str:
        """Why a saves stake on `player` is withheld, or "" when he starts."""
        if self.unknown:
            return f"{PREFIX} {self.unknown} Recorded as a lean and staked at zero."
        key = player_key(player)
        listed = [
            self.listings.get((day, normalize_team_name(team)))
            for team in (home, away)
        ]
        found = [item for item in listed if item is not None]
        if not found:
            return (
                f"{PREFIX} Daily Faceoff lists no starter for this game, so "
                "the card cannot tell whether he plays. Recorded as a lean and "
                "staked at zero."
            )
        for goalie, strength in found:
            if goalie and player_key(goalie) == key:
                if strength.strip().casefold() in STAKEABLE_STRENGTHS:
                    return ""
                label = strength or "no label"
                return (
                    f"{PREFIX} Daily Faceoff lists him as the starter but marks "
                    f"it {label!r}, not confirmed or likely. Recorded as a lean "
                    "and staked at zero."
                )
        named = ", ".join(
            f"{goalie} ({strength or 'no label'})" for goalie, strength in found if goalie
        )
        return (
            f"{PREFIX} Daily Faceoff lists {named or 'another goalie'} for "
            "this game, not him. A saves bet on a goalie who does not play is "
            "void. Recorded as a lean and staked at zero."
        )


def starters_from_rows(
    rows: list[Mapping[str, Any]], *, now: datetime | None = None
) -> GoalieStarters:
    if not rows:
        return GoalieStarters(
            unknown="The starting-goalies page listed no games."
        )
    moment = now or datetime.now(timezone.utc)
    stamps = []
    for row in rows:
        try:
            stamp = datetime.fromisoformat(str(row.get("retrieved_at", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamps.append(stamp)
    if not stamps:
        return GoalieStarters(
            unknown="The starting-goalies file carries no readable fetch time."
        )
    newest = max(stamps)
    if moment - newest > MAX_AGE:
        return GoalieStarters(
            unknown=(
                f"The starting goalies were fetched at "
                f"{newest.isoformat(timespec='minutes')}, more than "
                f"{int(MAX_AGE.total_seconds() // 3600)} hours before this card."
            ),
            retrieved_at=newest.isoformat(timespec="seconds"),
        )
    listings: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        day = str(row.get("date", "")).strip()
        team = normalize_team_name(row.get("team", ""))
        if not day or not team:
            continue
        listings[(day, team)] = (
            str(row.get("goalie", "") or "").strip(),
            str(row.get("strength", "") or "").strip(),
        )
    return GoalieStarters(
        listings=listings, retrieved_at=newest.isoformat(timespec="seconds")
    )


def load_starters(
    processed_dir: Path, *, now: datetime | None = None
) -> GoalieStarters:
    """Read the file `fetch_starting_goalies.py` wrote, failing closed."""
    import pandas as pd

    path = Path(processed_dir) / FILENAME
    if not path.exists():
        return GoalieStarters(
            unknown="No starting-goalies file was fetched for this card."
        )
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:  # a damaged file is no listing, never a guess
        return GoalieStarters(
            unknown=f"The starting-goalies file could not be read ({exc})."
        )
    return starters_from_rows(frame.to_dict("records"), now=now)
