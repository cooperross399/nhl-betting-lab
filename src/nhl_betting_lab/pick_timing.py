"""Are the picks the re-prices add worse than the morning's?

Cooper, 2026-11-10 ("ALL"). Gameday Refresh cards the slate three times a
day: the morning card (the 13:30 UTC slot, and the 15:00 backup), the
afternoon update (20:30 UTC) and the pre-game update (22:30 UTC). The later
two re-price the slate and can add best bets the morning card did not list.
This measures every best bet by the run that FIRST listed it, on two things:

* **Closing-line value**: the card's listed price against the close, by
  `closing_lines.closing_prices`, which needs the PRIVATE capture store. It is
  only ever computed inside Gameday Refresh's "Report closing-line value"
  step, the one step allowed to read it.
* **Results**: the forward ledger's settled outcome for that selection, at
  the card's listed price, one unit flat.

**Which picks, and when.** `latest_card_comment.md` on the public
`card-feed` branch is rewritten by every published card, so its git history
holds every card. A pick is a row of a card's "Best bets" table, identified
by its league day, game, market, player, side and line; it belongs to the
run of the first card that listed it, read off that card's "Generated:"
stamp. A card that never reached card-feed (a run that failed to publish) is
not in the history, so a pick it listed is credited to the next card that
did list it.

**What leaves.** Counts, rates, means and intervals by run. Never a price, a
line, a book or a player.

**The rule, fixed before the first reading.** Late additions (afternoon and
pre-game together) TRAIL the morning picks when, with at least
`MIN_LATE_PICKS` late picks in the comparison, the 95% interval of the
difference (late minus morning, each mean game-clustered, the two errors
added in quadrature) sits wholly below zero, for mean CLV or for flat-stake
return. Anything else is "no demonstrated difference".
"""

from __future__ import annotations

import math
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")

CARD_FILE = "latest_card_comment.md"
REPORT_MD = "pick_timing.md"
REPORT_JSON = "pick_timing.json"

#: The runs, in the order the day runs them.
RUNS = ("morning", "afternoon", "pregame")
RUN_LABELS = {
    "morning": "Morning card (13:30 / 15:00 UTC)",
    "afternoon": "Afternoon update (20:30 UTC)",
    "pregame": "Pre-game update (22:30 UTC)",
}
#: How many late picks the comparison needs before it may say "trails".
MIN_LATE_PICKS = 50
Z95 = 1.959963984540054

_GENERATED = re.compile(r"^- Generated: (\S+)", re.M)
_BEST = re.compile(r"^## Best bets\n(.*?)(?=^## |\Z)", re.M | re.S)
_SELECTIONS = frozenset(
    {"over", "under", "home", "away", "draw",
     "home_over", "home_under", "away_over", "away_under"}
)


def run_of(moment: datetime) -> str:
    """Which run a card generated at `moment` was.

    By the UTC clock, because the crons are in UTC: the morning slots finish
    before 18:00, the afternoon update between 18:00 and 22:00, and the
    pre-game update from 22:00 into the small hours.
    """
    hour = moment.astimezone(ZoneInfo("UTC")).hour
    if 10 <= hour < 18:
        return "morning"
    if 18 <= hour < 22:
        return "afternoon"
    return "pregame"


def _fold(text: object) -> str:
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return ""
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(plain.casefold().split())


def _team(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(name))


def _price(text: str) -> float | None:
    try:
        value = float(text.replace("+", "").replace("−", "-").strip())
    except ValueError:
        return None
    return value if abs(value) >= 100 else None


def _units(text: str) -> float | None:
    try:
        return float(text.strip())
    except ValueError:
        return None


def parse_selection(text: str) -> tuple[str, str, float | None] | None:
    """(player, selection, line) from the card's label (`gameday_card._label`)."""
    tokens = text.split()
    if not tokens:
        return None
    line: float | None = None
    try:
        line = float(tokens[-1].replace("−", "-"))
        tokens = tokens[:-1]
    except ValueError:
        line = None
    if not tokens or tokens[-1].lower() not in _SELECTIONS:
        return None
    return " ".join(tokens[:-1]).strip(), tokens[-1].lower(), line


def parse_best_bets(text: str) -> list[dict[str, Any]]:
    """The rows of a card comment's "Best bets" table. A row that cannot be
    read is left out, never guessed at."""
    found = _BEST.search(text)
    if not found:
        return []
    header: dict[str, int] | None = None
    rows: list[dict[str, Any]] = []
    for raw in found[1].splitlines():
        if not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if cells and cells[0] == "Game":
            header = {name: i for i, name in enumerate(cells)}
            continue
        if not header or any(k not in header for k in ("Game", "Market", "Selection", "Price")):
            continue
        if len(cells) < len(header):
            continue
        game = cells[header["Game"]].split(" @ ")
        parsed = parse_selection(cells[header["Selection"]])
        price = _price(cells[header["Price"]])
        if len(game) != 2 or parsed is None or price is None:
            continue
        player, selection, line = parsed
        rows.append({
            "away": game[0].strip(),
            "home": game[1].strip(),
            "market": cells[header["Market"]].strip("`"),
            "player": player,
            "selection": selection,
            "line": line,
            "price": price,
            "units": _units(cells[header["Units"]]) if "Units" in header else None,
        })
    return rows


def pick_key(day: str, row: Mapping[str, Any]) -> tuple:
    line = row.get("line")
    try:
        line_value = None if line is None or pd.isna(line) else round(float(line), 2)
    except (TypeError, ValueError):
        line_value = None
    return (
        day,
        _team(row.get("home") if "home" in row else row.get("home_team")),
        _team(row.get("away") if "away" in row else row.get("away_team")),
        str(row.get("market", "")).strip(),
        _fold(row.get("player")),
        str(row.get("selection", "")).strip().lower(),
        line_value,
    )


def first_listings_from_cards(cards: Sequence[str]) -> list[dict[str, Any]]:
    """Every best bet, at the first card (in the order given, oldest first)
    that listed it."""
    seen: dict[tuple, dict[str, Any]] = {}
    for text in cards:
        stamp = _GENERATED.search(text)
        if not stamp:
            continue
        try:
            moment = datetime.fromisoformat(stamp[1].replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None:
            continue
        day = moment.astimezone(ET).date().isoformat()
        run = run_of(moment)
        for row in parse_best_bets(text):
            key = pick_key(day, row)
            if key in seen:
                continue
            seen[key] = {**row, "day": day, "run": run, "generated": stamp[1], "key": key}
    return list(seen.values())


def card_history(repo: Path, ref: str) -> list[str]:
    """Every card comment `ref` has held, oldest first."""
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout

    commits = git("log", "--reverse", "--format=%H", ref, "--", CARD_FILE).split()
    return [git("show", f"{commit}:{CARD_FILE}") for commit in commits]


def _decimal(american: float) -> float:
    return 1.0 + (american / 100.0 if american > 0 else 100.0 / abs(american))


def _profit(outcome: str, american: float) -> float | None:
    if outcome == "won":
        return _decimal(american) - 1.0
    if outcome == "lost":
        return -1.0
    if outcome == "push":
        return 0.0
    return None


def _settle_from_logs(
    item: Mapping[str, Any],
    logs: pd.DataFrame,
    games: pd.DataFrame,
    team_names: Mapping[str, str],
    cache: dict[str, Any],
) -> str:
    """The forward ledger's outcome for a pick it never froze, or "" while
    its game is not final (or cannot be found)."""
    from nhl_betting_lab.forward_evidence import (
        _player_index,
        _settle_prop_row,
        _settle_team_row,
    )
    from nhl_betting_lab.markets import MARKETS_BY_KEY
    from nhl_betting_lab.providers.team_names import resolve_team

    if "finals" not in cache:
        cache["finals"] = {
            (str(g.date)[:10], str(g.home_team).strip().upper(), str(g.away_team).strip().upper()): g
            for g in games.itertuples()
        }
    day = str(item["day"])
    home = resolve_team(item["home"], team_names) or str(item["home"]).upper()
    away = resolve_team(item["away"], team_names) or str(item["away"]).upper()
    game = cache["finals"].get((day, home, away))
    if game is None:
        return ""
    probe = type("Row", (), {
        "market": item["market"], "player": item["player"], "line": item["line"],
        "selection": item["selection"], "american_odds": float(item["price"]),
    })()
    market = MARKETS_BY_KEY.get(str(item["market"]))
    if market is not None and market.is_prop:
        if ("index", day) not in cache:
            cache[("index", day)] = _player_index(logs, day)
        outcome, _actual, _profit = _settle_prop_row(probe, cache[("index", day)], {home, away})
        return outcome
    outcome, _actual, _profit = _settle_team_row(probe, game)
    return outcome


def _ledger_index(frame: pd.DataFrame) -> dict[tuple, list[Any]]:
    index: dict[tuple, list[Any]] = {}
    if frame is None or frame.empty:
        return index
    for row in frame.itertuples(index=False):
        day = str(getattr(row, "snapshot_date", ""))
        index.setdefault(pick_key(day, row._asdict()), []).append(row)
    return index


def score(
    listings: Sequence[Mapping[str, Any]],
    *,
    ledger: pd.DataFrame | None,
    opinions: pd.DataFrame | None = None,
    captures: pd.DataFrame | None = None,
    logs: pd.DataFrame | None = None,
    games: pd.DataFrame | None = None,
    team_names: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Each listing with its game, its settled profit (one unit flat at the
    card's price, None when unsettled or void) and its CLV (None without a
    close). `opinions` (snapshot or ledger rows) give the row a close is keyed
    on; `captures` are the private store's rows.

    A pick the forward ledger does not hold is settled from the box-score
    `logs` and team `games` by the ledger's own rules, when both are given.
    Until 2026-10-21 the morning snapshot took no market a book posted after
    it, so most afternoon saves and hits picks are in no ledger row; leaving
    them unsettled would measure the late picks on the markets the morning
    already had.
    """
    from nhl_betting_lab.closing_lines import _key_of, closing_prices

    settled = _ledger_index(ledger if ledger is not None else pd.DataFrame())
    rows_for = _ledger_index(opinions if opinions is not None else pd.DataFrame())
    closing = closing_prices(captures) if captures is not None and not captures.empty else {}
    cache: dict[str, Any] = {}
    scored = []
    for item in listings:
        key = item["key"]
        outcomes = {
            str(getattr(r, "outcome", "") or "").strip().lower() for r in settled.get(key, [])
        }
        outcome = next(iter(outcomes)) if len(outcomes) == 1 else ("" if not outcomes else "mixed")
        if not outcomes and logs is not None and games is not None:
            outcome = _settle_from_logs(item, logs, games, team_names or {}, cache)
        profit = _profit(outcome, float(item["price"]))
        clv = None
        if closing:
            for source in (rows_for.get(key, []) or settled.get(key, [])):
                close = closing.get(_key_of(source))
                if close is not None and close.get("decimal"):
                    clv = _decimal(float(item["price"])) / float(close["decimal"]) - 1.0
                    break
        scored.append({
            "run": item["run"],
            "market": item["market"],
            "game": (key[0], key[1], key[2]),
            "outcome": outcome or "pending",
            "profit": profit,
            "clv": clv,
        })
    return scored


@dataclass
class Mean:
    n: int
    games: int
    mean: float
    se: float

    @property
    def low(self) -> float:
        return self.mean - Z95 * self.se

    @property
    def high(self) -> float:
        return self.mean + Z95 * self.se


def clustered_mean(values: Sequence[float], games: Sequence[object]) -> Mean | None:
    """The mean and its game-clustered standard error, by
    `stats.clustered_mean_interval` (never narrower than on rows)."""
    from nhl_betting_lab.stats import clustered_mean_interval

    if not values:
        return None
    result = clustered_mean_interval(list(values), list(games))
    n = len(values)
    if math.isfinite(result.low) and math.isfinite(result.high):
        se = (result.high - result.low) / (2 * Z95)
    else:
        se = float("inf")
    return Mean(n=n, games=len(set(games)), mean=float(result.roi), se=se)


def _view(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    graded = [r for r in rows if r["profit"] is not None]
    priced = [r for r in rows if r["clv"] is not None]
    wins = sum(1 for r in graded if r["outcome"] == "won")
    losses = sum(1 for r in graded if r["outcome"] == "lost")
    out: dict[str, Any] = {
        "picks": len(rows),
        "settled": len(graded),
        "won": wins,
        "lost": losses,
        "push": len(graded) - wins - losses,
        "void_or_pending": len(rows) - len(graded),
        "with_close": len(priced),
    }
    roi = clustered_mean([r["profit"] for r in graded], [r["game"] for r in graded])
    if roi is not None:
        out.update(roi=roi.mean, roi_low=roi.low, roi_high=roi.high,
                   roi_se=roi.se, roi_games=roi.games, units=sum(r["profit"] for r in graded))
    clv = clustered_mean([r["clv"] for r in priced], [r["game"] for r in priced])
    if clv is not None:
        out.update(clv=clv.mean, clv_low=clv.low, clv_high=clv.high, clv_se=clv.se,
                   clv_games=clv.games,
                   beat_close=sum(1 for r in priced if r["clv"] > 1e-12),
                   lost_to_close=sum(1 for r in priced if r["clv"] < -1e-12))
    return out


def _difference(late: Mapping[str, Any], morning: Mapping[str, Any], name: str) -> dict[str, Any] | None:
    if name not in late or name not in morning:
        return None
    se = math.hypot(float(late[f"{name}_se"]), float(morning[f"{name}_se"]))
    diff = float(late[name]) - float(morning[name])
    return {"difference": diff, "low": diff - Z95 * se, "high": diff + Z95 * se}


def summarise(scored: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_run = {run: _view([r for r in scored if r["run"] == run]) for run in RUNS}
    late = _view([r for r in scored if r["run"] != "morning"])
    morning = by_run["morning"]
    comparison: dict[str, Any] = {}
    trails: list[str] = []
    for name, count in (("clv", "with_close"), ("roi", "settled")):
        diff = _difference(late, morning, name)
        if diff is None:
            continue
        diff["late_n"] = int(late[count])
        diff["enough"] = diff["late_n"] >= MIN_LATE_PICKS
        diff["trails"] = bool(diff["enough"] and diff["high"] < 0)
        comparison[name] = diff
        if diff["trails"]:
            trails.append(name)
    return {
        "runs": by_run,
        "late": late,
        "comparison": comparison,
        "late_trails": bool(trails),
        "trails_on": trails,
        "min_late_picks": MIN_LATE_PICKS,
    }


def _pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "unbounded"
    return f"{number:+.2%}"


def _interval(view: Mapping[str, Any], name: str) -> str:
    if name not in view:
        return "n/a"
    return f"{_pct(view[name])} [{_pct(view[f'{name}_low'])}, {_pct(view[f'{name}_high'])}]"


def render(summary: Mapping[str, Any], *, generated: str = "", has_closes: bool = True) -> str:
    lines = [
        "# Picks by the run that first listed them",
        "",
        f"- Generated: {generated}" if generated else "- Generated: unknown",
        "- Source: every card on card-feed (`latest_card_comment.md` history); "
        "results from the forward ledger, at the card's listed price, one unit "
        "flat; CLV against the close from the private capture store.",
        "- Every interval is 95%, clustered by game. Aggregate only: no price, "
        "line, book or player.",
        "",
        "| Run | Picks | Settled | W-L-P | Return | With a close | Beat / lost to close | Mean CLV |",
        "|:----|------:|--------:|:------|:-------|-------------:|:---------------------|:---------|",
    ]
    views = [(RUN_LABELS[run], summary["runs"][run]) for run in RUNS]
    views.append(("Afternoon and pre-game together", summary["late"]))
    for label, view in views:
        lines.append(
            f"| {label} | {view['picks']:,} | {view['settled']:,} | "
            f"{view['won']}-{view['lost']}-{view['push']} | {_interval(view, 'roi')} | "
            f"{view['with_close']:,} | {view.get('beat_close', 0)} / {view.get('lost_to_close', 0)} | "
            f"{_interval(view, 'clv')} |"
        )
    lines += ["", "## Late additions against the morning card", ""]
    if not has_closes:
        lines.append("No closing price was read this run, so CLV is not compared.")
    for name, label in (("clv", "Mean CLV"), ("roi", "Flat-stake return")):
        diff = summary["comparison"].get(name)
        if diff is None:
            lines.append(f"- {label}: nothing to compare yet.")
            continue
        verdict = (
            "**late additions trail the morning picks**"
            if diff["trails"]
            else (
                f"too few late picks to judge (under {MIN_LATE_PICKS})"
                if not diff["enough"]
                else "**no demonstrated difference**"
            )
        )
        lines.append(
            f"- {label}, late minus morning: {_pct(diff['difference'])} "
            f"[{_pct(diff['low'])}, {_pct(diff['high'])}] over {diff['late_n']:,} "
            f"late pick(s): {verdict}."
        )
    lines += [
        "",
        "The rule was fixed before the first reading: late additions trail when, "
        f"with at least {MIN_LATE_PICKS} late picks, the interval of the "
        "difference sits wholly below zero for mean CLV or for return.",
        "",
    ]
    return "\n".join(lines)
