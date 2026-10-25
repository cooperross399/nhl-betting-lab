"""PostHockey's pre-game win probability, read into the card's team markets.

Cooper, 2026-10-25, asked for what PostHockey does that this model does not
to be wired into the card. The largest piece is how PostHockey rates a game:
not the two clubs' recent shot rates, as `models.team_ratings` does, but the
players dressed tonight. Each skater carries an Estimated Net Rating (a
Marcel-style forecast of his goals above average per game, aged, shrunk by
how much history he has, updated game by game), each goalie a season
forecast of goals saved per shot faced (aged, with an unseen goalie starting
below average), and the expected roster's total, with the listed starter,
home ice and back-to-backs, becomes the probability the home club wins,
overtime and shootout included. PostHockey publishes that number for every
game on its free live endpoint (`/api/v1/live`), beside its calibration
record: home clubs given 63-67% won 64.1% of 1,330 games.

So the card blends the two opinions rather than rebuilding PostHockey's
lineup model: `TeamModel` moves goals between the sides, keeping the game's
expected total, until its moneyline reads `BLEND_WEIGHT` of the way from its
own number to PostHockey's. The puck line and team totals follow from the
same moved goals, and the game total does not move. A game PostHockey has
not priced, or a file that is missing, moves nothing.

`scripts/fetch_posthockey_pregame.py` writes tonight's numbers to
`data/processed/posthockey_tonight/<league day>.csv`; Gameday Refresh runs it
before the card, and again at the pre-game update, when the lineups and
goalies PostHockey reads have been posted. Nothing here is measured against
prices, and the weight is this lab's choice.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

#: PostHockey's free live endpoint: today's games with their win probability.
LIVE_URL = "https://posthockey.com/api/v1/live"
TONIGHT_DIRNAME = "posthockey_tonight"
TONIGHT_COLUMNS = (
    "date", "game_id", "home_team", "away_team", "p_home",
    "goalie_home_status", "goalie_away_status", "retrieved_at",
)

#: How far the card's moneyline moves from its own number toward PostHockey's.
BLEND_WEIGHT = 0.5
#: PostHockey's number is read only inside this range; outside it the row is
#: taken as malformed rather than as a 99% opinion.
PROBABILITY_RANGE = (0.05, 0.95)


def pregame_rows(payload: object, day: str, retrieved_at: str) -> list[dict]:
    """Tonight's not-yet-started games PostHockey has priced, as file rows.

    Only a game whose number is the pre-game kind is kept: once the puck
    drops PostHockey's `p_home` is the live in-game probability, which says
    nothing about a bet made before the game.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise ValueError("PostHockey's live payload has no games list")
    rows = []
    for game in payload["games"]:
        if not isinstance(game, dict):
            continue
        prob = game.get("win_prob")
        if not isinstance(prob, dict) or prob.get("kind") != "pre":
            continue
        if str(game.get("game_type", "2")) != "2" or game.get("is_preseason"):
            continue
        p_home = prob.get("p_home_pre", prob.get("p_home"))
        try:
            p_home = float(p_home)
        except (TypeError, ValueError):
            continue
        rows.append({
            "date": day,
            "game_id": str(game.get("game_id", "")),
            "home_team": str((game.get("home") or {}).get("abbrev", "")),
            "away_team": str((game.get("away") or {}).get("abbrev", "")),
            "p_home": p_home,
            "goalie_home_status": str(prob.get("goalie_home_status", "")),
            "goalie_away_status": str(prob.get("goalie_away_status", "")),
            "retrieved_at": retrieved_at,
        })
    return rows


def append_rows(path: Path, rows: Iterable[dict]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(TONIGHT_COLUMNS)).to_csv(
        path, mode="a", header=not path.is_file(), index=False, lineterminator="\n"
    )
    return len(rows)


def tonight_targets(processed_dir: Path, day: str) -> dict[tuple[str, str], float]:
    """{(home, away): PostHockey's P(home wins)} for tonight, latest read per game."""
    path = Path(processed_dir) / TONIGHT_DIRNAME / f"{day}.csv"
    if not path.is_file():
        return {}
    try:
        tonight = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError):
        return {}
    if tonight.empty or not set(TONIGHT_COLUMNS) <= set(tonight.columns):
        return {}
    tonight = tonight.sort_values("retrieved_at").drop_duplicates("game_id", keep="last")
    low, high = PROBABILITY_RANGE
    out: dict[tuple[str, str], float] = {}
    for row in tonight.itertuples():
        try:
            p_home = float(row.p_home)
        except (TypeError, ValueError):
            continue
        if not low <= p_home <= high or not row.home_team or not row.away_team:
            continue
        out[(str(row.home_team), str(row.away_team))] = p_home
    return out
