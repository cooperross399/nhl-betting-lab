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
goalies PostHockey reads have been posted.

**The weight is refitted (Cooper, 2026-11-10, "All").** `BLEND_WEIGHT` = 0.5
was never tested, so every card now fits it (`fit_blend_weight`) on the
settled games it has blended: for each, the card's own home win chance
before the blend, PostHockey's number, and whether the home club won. The
fitted weight minimises the log loss of p = own + w x (PostHockey - own)
over w in 0..1, then is shrunk toward `BLEND_WEIGHT` by games / (games +
`BLEND_SHRINKAGE_GAMES`) and bounded to 0..1. The card records each game it
blends in `data/processed/posthockey_blend.csv` (`record_blend`: its own
number, read off the factor breakdown's step before the blend, the target
and the weight it used); games blended before that record existed are read
back off the forward ledger's frozen moneyline and the day's first
PostHockey read, at the 0.5 the card then used (`ledger_backfill`). The
fit is written to `data/outputs/posthockey_blend.md` and `.json`. Log loss
on outcomes can rule a weight out, never in; nothing here is measured
against prices.
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

#: How far the card's moneyline moved from its own number toward PostHockey's
#: before the weight was fitted, and the prior the fitted weight is shrunk to.
BLEND_WEIGHT = 0.5
#: Settled games at which the fitted weight counts half against the prior.
BLEND_SHRINKAGE_GAMES = 200
#: The first day the card blended (#350 merged 2026-10-25; its first full
#: card is the next morning's).
BLEND_FROM = "2026-10-26"
BLEND_RECORD_FILENAME = "posthockey_blend.csv"
BLEND_RECORD_COLUMNS = ("date", "home", "away", "p_model", "target", "weight", "recorded_at")
BLEND_REPORT_MD = "posthockey_blend.md"
BLEND_REPORT_JSON = "posthockey_blend.json"
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


# -- the fitted weight (2026-11-10) ------------------------------------------


def record_blend(
    processed_dir: Path,
    breakdowns: Iterable[dict],
    targets: dict[tuple[str, str], float],
    weight: float,
    recorded_at: str,
) -> int:
    """Append each blended game's own number and target to the record.

    `breakdowns` is the card's `factor_breakdown.slate_breakdowns`: the step
    before "posthockey" is the card's own home win chance. A game already
    recorded for its day keeps its first row (the morning's frozen opinion);
    a game PostHockey did not price is not recorded.
    """
    path = Path(processed_dir) / BLEND_RECORD_FILENAME
    seen: set[tuple[str, str, str]] = set()
    if path.is_file():
        try:
            old = pd.read_csv(path, dtype=str, keep_default_na=False)
            seen = set(zip(old["date"], old["home"], old["away"]))
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            seen = set()
    rows = []
    for game in breakdowns:
        home, away = str(game.get("home", "")), str(game.get("away", ""))
        day = str(game.get("date", ""))
        target = targets.get((home, away))
        steps = game.get("steps") or []
        keys = [str(s.get("key")) for s in steps]
        if target is None or "posthockey" not in keys or (day, home, away) in seen:
            continue
        i = keys.index("posthockey")
        if i == 0:
            continue
        rows.append({
            "date": day, "home": home, "away": away,
            "p_model": float(steps[i - 1]["homeWin"]), "target": float(target),
            "weight": float(weight), "recorded_at": recorded_at,
        })
        seen.add((day, home, away))
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(BLEND_RECORD_COLUMNS)).to_csv(
        path, mode="a", header=not path.is_file(), index=False, lineterminator="\n"
    )
    return len(rows)


_FIT_COLUMNS = ["date", "home", "away", "p_model", "target", "source"]


def read_record(processed_dir: Path) -> pd.DataFrame:
    """The card's own blend record, one row per game (its first)."""
    path = Path(processed_dir) / BLEND_RECORD_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=_FIT_COLUMNS)
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame = frame.drop_duplicates(["date", "home", "away"], keep="first").copy()
        frame["p_model"] = pd.to_numeric(frame["p_model"], errors="coerce")
        frame["target"] = pd.to_numeric(frame["target"], errors="coerce")
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return pd.DataFrame(columns=_FIT_COLUMNS)
    frame["source"] = "record"
    return frame.dropna(subset=["p_model", "target"])[_FIT_COLUMNS]


def first_reads(processed_dir: Path) -> pd.DataFrame:
    """Each day's first PostHockey read per game: what the morning card read."""
    directory = Path(processed_dir) / TONIGHT_DIRNAME
    frames = []
    for path in sorted(directory.glob("20??-??-??.csv")) if directory.is_dir() else []:
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, ValueError, pd.errors.ParserError):
            continue
        if frame.empty or not set(TONIGHT_COLUMNS) <= set(frame.columns):
            continue
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["date", "home", "away", "target"])
    reads = pd.concat(frames, ignore_index=True)
    reads = reads.sort_values("retrieved_at").drop_duplicates(
        ["date", "home_team", "away_team"], keep="first"
    )
    reads["target"] = pd.to_numeric(reads["p_home"], errors="coerce")
    low, high = PROBABILITY_RANGE
    reads = reads[(reads["target"] >= low) & (reads["target"] <= high)]
    return reads.rename(columns={"home_team": "home", "away_team": "away"})[
        ["date", "home", "away", "target"]
    ]


def ledger_backfill(
    ledger: pd.DataFrame, reads: pd.DataFrame, team_names: dict[str, str], *, before: str
) -> pd.DataFrame:
    """Blended games before the record began, read back off the ledger.

    The frozen moneyline home chance is own + 0.5 x (target - own), so own =
    2 x frozen - target, with the day's first PostHockey read as the target.
    Approximate: the card blended on the goals split, and the frozen number
    carries the referee crew; both move it by well under a point.
    """
    if ledger is None or ledger.empty or reads.empty:
        return pd.DataFrame(columns=_FIT_COLUMNS)
    from nhl_betting_lab.providers.team_names import resolve_team

    rows = ledger[
        (ledger["market"].astype(str) == "moneyline")
        & (ledger["selection"].astype(str) == "home")
        & (ledger["snapshot_date"].astype(str) >= BLEND_FROM)
        & (ledger["snapshot_date"].astype(str) < str(before))
    ]
    if rows.empty:
        return pd.DataFrame(columns=_FIT_COLUMNS)
    frame = rows.drop_duplicates(["snapshot_date", "home_team", "away_team"]).copy()
    frame["date"] = frame["snapshot_date"].astype(str)
    frame["home"] = frame["home_team"].map(lambda n: resolve_team(n, team_names) if team_names else n)
    frame["away"] = frame["away_team"].map(lambda n: resolve_team(n, team_names) if team_names else n)
    frame = frame.merge(reads, on=["date", "home", "away"], how="inner")
    frozen = pd.to_numeric(frame["model_probability"], errors="coerce")
    frame["p_model"] = (2.0 * frozen - frame["target"]).clip(0.02, 0.98)
    frame["source"] = "ledger"
    return frame.dropna(subset=["p_model", "target"])[_FIT_COLUMNS]


def home_results(games: pd.DataFrame) -> pd.DataFrame:
    """(date, home, away, home_won) for every decided final in the games table."""
    columns = ["date", "home", "away", "home_won"]
    if games is None or games.empty:
        return pd.DataFrame(columns=columns)
    frame = games.copy()
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce")
    frame = frame.dropna(subset=["home_goals", "away_goals"])
    frame = frame[frame["home_goals"] != frame["away_goals"]]
    out = pd.DataFrame({
        "date": frame["date"].astype(str).str[:10],
        "home": frame["home_team"].astype(str),
        "away": frame["away_team"].astype(str),
        "home_won": (frame["home_goals"] > frame["away_goals"]).astype(int),
    }, columns=columns)
    return out.drop_duplicates(["date", "home", "away"])


def blend_log_loss(frame: pd.DataFrame, weight: float) -> float:
    """Mean log loss of own + weight x (target - own) on `frame`'s outcomes."""
    import numpy as np

    pm, t, y = (frame[c].to_numpy(dtype=float) for c in ("p_model", "target", "home_won"))
    p = np.clip(pm + weight * (t - pm), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def best_weight(frame: pd.DataFrame) -> float:
    """The weight in 0..1 (step 0.01) with the lowest log loss on `frame`."""
    grid = [round(i / 100, 2) for i in range(101)]
    losses = [blend_log_loss(frame, w) for w in grid]
    return float(grid[losses.index(min(losses))])


def blend_weight(raw: float, games: int) -> float:
    """`raw` shrunk toward `BLEND_WEIGHT` by games, bounded to 0..1."""
    share = games / (games + BLEND_SHRINKAGE_GAMES) if games > 0 else 0.0
    return min(max(BLEND_WEIGHT + share * (float(raw) - BLEND_WEIGHT), 0.0), 1.0)


def blend_rows(
    processed_dir: Path,
    games: pd.DataFrame,
    team_names: dict[str, str],
    *,
    before: str,
    ledger: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Every settled blended game before `before`: own, target, home_won, source."""
    record = read_record(processed_dir)
    record = record[record["date"].astype(str) < str(before)]
    start = str(record["date"].min()) if not record.empty else str(before)
    if ledger is None:
        from nhl_betting_lab.forward_evidence import LEDGER_FILENAME

        path = Path(processed_dir) / LEDGER_FILENAME
        try:
            ledger = (
                pd.read_csv(path, dtype=str, keep_default_na=False) if path.is_file() else pd.DataFrame()
            )
        except (OSError, ValueError, pd.errors.ParserError):
            ledger = pd.DataFrame()
    backfill = ledger_backfill(ledger, first_reads(processed_dir), team_names, before=start)
    parts = [frame for frame in (backfill, record) if not frame.empty]
    rows = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=_FIT_COLUMNS)
    return rows.merge(home_results(games), on=["date", "home", "away"], how="inner")


def fit_blend_weight(
    processed_dir: Path,
    games: pd.DataFrame,
    team_names: dict[str, str],
    *,
    before: str,
    ledger: pd.DataFrame | None = None,
) -> dict:
    """The weight for a card on `before`, fitted on games settled before it.

    With no settled game the weight is `BLEND_WEIGHT`.
    """
    rows = blend_rows(processed_dir, games, team_names, before=before, ledger=ledger)
    out: dict = {
        "before": str(before), "prior": BLEND_WEIGHT, "shrinkage_games": BLEND_SHRINKAGE_GAMES,
        "games": int(len(rows)),
        "by_source": {str(k): int(v) for k, v in rows["source"].value_counts().items()},
        "first": str(rows["date"].min()) if len(rows) else "",
        "last": str(rows["date"].max()) if len(rows) else "",
        "raw": BLEND_WEIGHT, "weight": BLEND_WEIGHT, "log_loss": {},
    }
    if rows.empty:
        return out
    raw = best_weight(rows)
    weight = blend_weight(raw, len(rows))
    out.update({
        "raw": raw,
        "weight": weight,
        "home_win_rate": float(rows["home_won"].mean()),
        "log_loss": {
            "card alone (0)": blend_log_loss(rows, 0.0),
            f"old fixed weight ({BLEND_WEIGHT})": blend_log_loss(rows, BLEND_WEIGHT),
            f"best on these games ({raw:.2f})": blend_log_loss(rows, raw),
            f"in force ({weight:.3f})": blend_log_loss(rows, weight),
            "PostHockey alone (1)": blend_log_loss(rows, 1.0),
        },
    })
    return out


def render_blend_report(fit: dict) -> str:
    lines = [
        "# PostHockey blend weight",
        "",
        "How far the card's moneyline moves from its own home win chance toward "
        "PostHockey's pre-game number, refitted every card on the blended games that "
        f"have settled (Cooper, 2026-11-10). Prior {fit['prior']}, shrunk at "
        f"{fit['shrinkage_games']} games, bounded 0..1.",
        "",
        f"- Card day: {fit['before']}",
        f"- Settled blended games: {fit['games']:,}"
        + (f" ({fit['first']} to {fit['last']}; by source {fit['by_source']})" if fit["games"] else ""),
        f"- Best weight on those games: {fit['raw']:.2f}",
        f"- **Weight in force: {fit['weight']:.3f}**",
    ]
    losses = fit.get("log_loss") or {}
    if losses:
        lines += [
            "",
            "| Weight | Log loss per game |",
            "|:--|--:|",
            *(f"| {name} | {value:.4f} |" for name, value in losses.items()),
            "",
            f"Home clubs won {fit.get('home_win_rate', 0):.1%} of these games. Log loss on "
            "outcomes can rule a weight out, never in; nothing here is measured against prices.",
        ]
    return "\n".join(lines) + "\n"
