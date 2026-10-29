"""The card learns from its own settled opinions (Cooper, 2026-10-28).

Cooper: "I just want it to learn from the most information possible.
Whatever helps it make winning plays more often." Every model here already
refits each run on the games themselves; nothing fed back whether its
opinions WON against the price. This does.

For each market, the forward ledger's settled opinions (one per wager at the
best price the card could have taken) fit

    logit(P(win)) = logit(price) + a + w * (logit(model) - logit(price))

`w` is how far the model's disagreement with the book has been worth
trusting in that market, and `a` how far the book's own price has been off
(mostly its margin). A market where the model's lean has paid keeps `w`
near or above 1; a market where it has not shrinks toward the price, so its
edges shrink with it, and one where the lean has run the wrong way is held
at 0, so no edge in it survives the learning. Each game counts once
whatever its ladder, because every rung of one game settles on one
boxscore. Fitted on the ledger through 2026-10-27: shots on goal 0.81,
points 0.84, assists 0.86, hits 0.72, total goals 0.93 (45 games), the
rest 0.94-1.03.

A ridge prior pulls `(a, w)` toward `(0, 1)`, which is the card as it was,
so a market with few settled games barely moves, and `w` is held to
[0, 1.5] and `a` to +/-0.25. Opinions priced before a model change in their
market (team markets before `TEAM_RATINGS_FROM`, goalie saves before
`SAVES_CONTEXT_FROM`) are not learned from: they are another model's.

It moves the card's probabilities AFTER the day's snapshot is frozen, so
the forward ledger keeps the model's own opinions (what this learns from
next time) and the 2027-04-25 test scores the same opinions as before. Only
the card's edges, and so its selections and stakes, move. The constants are
this lab's choice. `PRIOR_STRENGTH` was picked on the walk-forward in
`scripts/run_self_learning_check.py` (ledger 2026-09-29 to 10-27, 22 days
scored after a week's warm-up, best-bet bars): the card as it was +1.2u over
379, learned +17.0u over 237 at 10; +10.9u over 173 at 5, +7.1u over 303 at
20, +3.9u over 338 at 40, +5.3u over 369 at 150. Every strength beat the
card as it was, and all of it is three weeks: no demonstrated edge.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from nhl_betting_lab.models.saves_context import SAVES_CONTEXT_FROM
from nhl_betting_lab.models.team_ratings import TEAM_RATINGS_FROM

#: Strength of the pull toward the unlearned card, in game-weighted
#: observations' worth of Fisher information.
PRIOR_STRENGTH = 10.0
W_BOUNDS = (0.0, 1.5)
A_BOUND = 0.25
TEAM_MARKETS = frozenset(
    {"moneyline", "puck_line", "total_goals", "team_total", "regulation_3_way"}
)
REPORT_JSON = "self_learning.json"
REPORT_MARKDOWN = "self_learning.md"

_LEDGER_COLUMNS = [
    "snapshot_date", "home_team", "away_team", "market", "player",
    "selection", "line", "american_odds", "model_probability", "outcome",
]
_WAGER = ["snapshot_date", "home_team", "away_team", "market", "player", "selection", "line"]


@dataclass(frozen=True)
class Trust:
    a: float = 0.0
    w: float = 1.0
    wagers: int = 0
    games: int = 0


def _decimal(american: pd.Series) -> pd.Series:
    odds = pd.to_numeric(american, errors="coerce")
    return pd.Series(
        np.where(odds > 0, 1 + odds / 100.0, 1 + 100.0 / odds.abs()), index=odds.index
    ).where(odds.notna() & (odds.abs() >= 100))


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def learnable_wagers(ledger: pd.DataFrame) -> pd.DataFrame:
    """Settled won/lost opinions, one per wager at its best price, from the
    current model in each market."""
    if ledger.empty:
        return ledger.iloc[0:0]
    frame = ledger[[c for c in _LEDGER_COLUMNS if c in ledger.columns]].copy()
    frame = frame[frame["outcome"].isin(["won", "lost"])]
    day = frame["snapshot_date"].astype(str)
    market = frame["market"].astype(str)
    frame = frame[
        ~(market.isin(TEAM_MARKETS) & (day < TEAM_RATINGS_FROM))
        & ~((market == "goalie_saves") & (day < SAVES_CONTEXT_FROM))
    ]
    frame["decimal"] = _decimal(frame["american_odds"])
    frame["model_probability"] = pd.to_numeric(frame["model_probability"], errors="coerce")
    frame = frame.dropna(subset=["decimal", "model_probability"])
    frame["player"] = frame["player"].fillna("").astype(str)
    frame["line"] = pd.to_numeric(frame["line"], errors="coerce").fillna(-999.0)
    frame = frame.sort_values("decimal", ascending=False).drop_duplicates(_WAGER)
    return frame.reset_index(drop=True)


def fit_market(wagers: pd.DataFrame, *, prior: float = PRIOR_STRENGTH) -> Trust:
    """`(a, w)` for one market's wagers, each game weighing one."""
    if wagers.empty:
        return Trust()
    offset = _logit(1.0 / wagers["decimal"].to_numpy())
    d = _logit(wagers["model_probability"].to_numpy()) - offset
    y = (wagers["outcome"] == "won").to_numpy(dtype=float)
    game = wagers["snapshot_date"].astype(str) + "|" + wagers["home_team"].astype(str)
    weight = 1.0 / game.map(game.value_counts()).to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(d)), d])
    b0 = np.array([0.0, 1.0])
    b = b0.copy()
    for _ in range(50):
        mu = 1.0 / (1.0 + np.exp(-(offset + X @ b)))
        H = X.T @ (X * (weight * mu * (1 - mu))[:, None]) + prior * np.eye(2)
        step = np.linalg.solve(H, X.T @ (weight * (y - mu)) - prior * (b - b0))
        b = b + step
        if np.abs(step).max() < 1e-9:
            break
    return Trust(
        a=float(np.clip(b[0], -A_BOUND, A_BOUND)),
        w=float(np.clip(b[1], *W_BOUNDS)),
        wagers=int(len(d)),
        games=int(game.nunique()),
    )


def fit_trust(ledger: pd.DataFrame, *, prior: float = PRIOR_STRENGTH) -> dict[str, Trust]:
    wagers = learnable_wagers(ledger)
    if wagers.empty:
        return {}
    return {
        str(market): fit_market(group, prior=prior)
        for market, group in wagers.groupby("market")
    }


def load_ledger_for_learning(path: Path) -> pd.DataFrame:
    """The ledger's learnable columns, or an empty frame when it is absent
    or unreadable (the card then prices as it did before)."""
    if not path.is_file():
        return pd.DataFrame(columns=_LEDGER_COLUMNS)
    try:
        return pd.read_csv(path, usecols=lambda c: c in _LEDGER_COLUMNS, dtype={"player": str})
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=_LEDGER_COLUMNS)


def adjusted(probability: float, american: float, trust: Trust) -> float:
    decimal = 1 + american / 100.0 if american > 0 else 1 + 100.0 / abs(american)
    m = float(_logit(1.0 / decimal))
    z = m + trust.a + trust.w * (float(_logit(probability)) - m)
    return min(0.999, max(0.001, 1.0 / (1.0 + math.exp(-z))))


def apply_trust(
    probabilities: Mapping[tuple, float],
    prices: pd.DataFrame,
    trust: Mapping[str, Trust],
    *,
    key_for: Callable,
) -> tuple[dict[tuple, float], int]:
    """The probabilities learned against the best staged price of each
    selection, and how many moved. A selection with no usable price, or in
    a market with nothing learned, keeps its probability."""
    out = dict(probabilities)
    if not trust or prices.empty:
        return out, 0
    best: dict[tuple, float] = {}
    for row in prices.itertuples():
        market = str(getattr(row, "market", "")).strip()
        if market not in trust:
            continue
        selection = str(getattr(row, "selection", "")).strip().lower()
        line_value = getattr(row, "line", None)
        try:
            line = float(line_value) if line_value is not None and not pd.isna(line_value) else None
            price = float(getattr(row, "american_odds"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or abs(price) < 100:
            continue
        key = key_for(row, market=market, selection=selection, line=line)
        if key in out and (key not in best or price > best[key]):
            best[key] = price
    moved = 0
    for key, price in best.items():
        learned = trust.get(str(key[0]))
        if learned is None or (learned.a == 0.0 and learned.w == 1.0):
            continue
        out[key] = adjusted(float(out[key]), price, learned)
        moved += 1
    return out, moved


def save_report(trust: Mapping[str, Trust], output_dir: Path, *, generated_at: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": generated_at,
        "prior_strength": PRIOR_STRENGTH,
        "markets": {market: asdict(t) for market, t in sorted(trust.items())},
    }
    (output_dir / REPORT_JSON).write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# What the card learned from its own results",
        "",
        f"- Generated: {generated_at}",
        "- Fit on the forward ledger's settled opinions, one per wager at its best "
        "price, each game counting once. `w` = how much of the model's "
        "disagreement with the book to keep (1 = all of it, 0 = none); `a` = how "
        "far the book's price itself has been off, mostly its margin.",
        "",
        "| Market | Games | Wagers | w | a |",
        "|:--|--:|--:|--:|--:|",
    ]
    for market, t in sorted(trust.items()):
        lines.append(f"| `{market}` | {t.games:,} | {t.wagers:,} | {t.w:.2f} | {t.a:+.3f} |")
    lines += [
        "",
        "Applied to the card after the day's snapshot is frozen, so the ledger "
        "keeps the model's own opinions. Not measured to make money: a "
        "walk-forward over a few weeks of the ledger is noise-level either way.",
        "",
    ]
    (output_dir / REPORT_MARKDOWN).write_text("\n".join(lines))
