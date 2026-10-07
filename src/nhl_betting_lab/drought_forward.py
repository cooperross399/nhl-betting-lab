"""The Due List's own forward record: what the list showed, and how it did.

Every night the Gameday card lists the Due List's qualifiers (Cooper picks
from them; nothing is staked). This module records each listed row with the
best price it showed, to a dated file of its own, settles those rows after the
games with the forward ledger's settlement rules, and restates the results in
`data/outputs/drought_rule_forward.md`. It records the RULE's results. Cooper's
actual picks are his and are not tracked.

## Kept apart from the registered forward test, on purpose

The registered 2027-04-25 test is `forward_evidence` (frozen opinions, its
ledger, its report). Nothing here writes into any of that: the files are
`data/processed/drought_list/<day>.csv` and `data/processed/drought_forward.csv`
and the report is `drought_rule_forward.md`. This module READS the settlement
helpers `forward_evidence` already has, so a row settles by the same rules
(a player who never entered the game is void, a game with no result inside
`PATIENCE_DAYS` is unsettleable and never guessed, one row per wager at the
listed best price), and imports nothing that writes the registered ledger.
`write_snapshot`, `forward_evidence.csv` and `build_forward_report` are
byte-for-byte what they would have been without it; a test proves it.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.drought_rule import SECTION_TITLE, THRESHOLDS, backtest_headline
from nhl_betting_lab.forward_evidence import (
    PATIENCE_DAYS,
    _player_index,
    _replace_whole,
    _settle_prop_row,
)
from nhl_betting_lab.providers.team_names import resolve_team
from nhl_betting_lab.stats import clustered_mean_interval

LIST_DIRNAME = "drought_list"
LEDGER_FILENAME = "drought_forward.csv"
REPORT_MARKDOWN_FILENAME = "drought_rule_forward.md"
REPORT_JSON_FILENAME = "drought_rule_forward.json"

LIST_COLUMNS = (
    "date", "commence_time", "home_team", "away_team", "team", "opponent", "player",
    "player_id", "market", "selection", "line", "last_season", "drought",
    "american_odds", "book",
)
LEDGER_COLUMNS = LIST_COLUMNS + ("settled_at", "outcome", "actual", "profit_units")
_KEY = ["player_id", "market"]


def list_dir(processed_dir: Path | None = None) -> Path:
    return (Path(processed_dir) if processed_dir else PROCESSED_DIR) / LIST_DIRNAME


def _frame(rows) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=list(LIST_COLUMNS))
    frame["american_odds"] = pd.to_numeric(frame["american_odds"], errors="coerce")
    frame["book"] = frame["book"].fillna("").astype(str)
    return frame


def record_list(rows, day: str, *, processed_dir: Path | None = None) -> str:
    """Freeze tonight's list in its own dated file, and say what happened.

    A row, once listed, stays as listed. A row listed with no price may take
    one later in the day (a later run found a book posting it), once; a price
    already recorded is never replaced, because the listed price is the one
    the wager is settled at. A day already settled into the ledger is never
    reopened. An empty list writes nothing: a day with no row has nothing to
    settle.
    """
    directory = list_dir(processed_dir)
    target = directory / f"{day}.csv"
    ledger = Path(processed_dir or PROCESSED_DIR) / LEDGER_FILENAME
    if ledger.is_file():
        settled = pd.read_csv(ledger, usecols=["date"])
        if day in set(settled["date"].astype(str)):
            return f"{day} is already settled; its list stands."
    new = _frame(rows)
    if new.empty and not target.is_file():
        return "nothing to record: no row is listed."
    if target.is_file():
        old = pd.read_csv(target)
        old["book"] = old["book"].fillna("").astype(str)
        merged = old.copy()
        have = {(int(r.player_id), r.market): i for i, r in enumerate(old.itertuples())}
        add = []
        for r in new.itertuples():
            i = have.get((int(r.player_id), r.market))
            if i is None:
                add.append(r._asdict())
            elif pd.isna(merged.at[i, "american_odds"]) and not pd.isna(r.american_odds):
                merged.at[i, "american_odds"], merged.at[i, "book"] = r.american_odds, r.book
        if add:
            merged = pd.concat([merged, pd.DataFrame(add).drop(columns="Index")[list(LIST_COLUMNS)]], ignore_index=True)
        if merged.equals(old):
            return f"{day}'s list stands ({len(old)} row(s)); nothing new to record."
        frame = merged
    else:
        frame = new
    directory.mkdir(parents=True, exist_ok=True)
    _replace_whole(frame[list(LIST_COLUMNS)], target)
    return f"{len(frame)} row(s) recorded for {day} in {target}."


@dataclass
class DroughtSettlement:
    days_settled: int = 0
    days_waiting: int = 0
    rows_settled: int = 0
    rows_void: int = 0
    rows_unsettleable: int = 0
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (f"Due List: {self.days_settled} day(s) settled ({self.rows_settled} row(s) graded, "
                f"{self.rows_void} void, {self.rows_unsettleable} unsettleable), {self.days_waiting} waiting.")


def load_ledger(processed_dir: Path | None = None) -> pd.DataFrame:
    path = Path(processed_dir or PROCESSED_DIR) / LEDGER_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    return pd.read_csv(path)


def settle_lists(
    logs: pd.DataFrame,
    games: pd.DataFrame,
    *,
    team_names: Mapping[str, str],
    processed_dir: Path | None = None,
    now: datetime | None = None,
) -> DroughtSettlement:
    """Settle every dated list whose games are all final, once, by the forward ledger's rules."""
    moment = now or datetime.now(timezone.utc)
    result = DroughtSettlement()
    directory = list_dir(processed_dir)
    ledger_path = Path(processed_dir or PROCESSED_DIR) / LEDGER_FILENAME
    if not directory.is_dir():
        return result
    existing = load_ledger(processed_dir)
    done = set(existing["date"].astype(str))
    finals = {(str(g.date)[:10], str(g.home_team).strip().upper(), str(g.away_team).strip().upper()): g
              for g in games.itertuples()}
    new_rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.csv")):
        day = path.stem
        if day in done:
            continue
        listed = pd.read_csv(path)
        listed["american_odds"] = pd.to_numeric(listed["american_odds"], errors="coerce")
        found = [finals.get((day, str(r.home_team).strip().upper(), str(r.away_team).strip().upper()))
                 for r in listed.itertuples()]
        age = (moment.date() - datetime.fromisoformat(day).date()).days
        if any(g is None for g in found) and age <= PATIENCE_DAYS:
            result.days_waiting += 1
            continue
        index = _player_index(logs, day)
        for r, game in zip(listed.itertuples(), found):
            base = {c: getattr(r, c, None) for c in LIST_COLUMNS}
            if game is None:
                outcome, actual, profit = "unsettleable", None, 0.0
            else:
                # An unpriced row is not a wager: it is graded for the hit rate with a
                # placeholder price that never reaches the profit column.
                priced = not pd.isna(r.american_odds)
                probe = type("Row", (), {"market": r.market, "player": r.player, "line": r.line,
                                         "selection": r.selection,
                                         "american_odds": r.american_odds if priced else 100.0})()
                teams = {resolve_team(r.home_team, team_names) or str(r.home_team).upper(),
                         resolve_team(r.away_team, team_names) or str(r.away_team).upper()}
                outcome, actual, profit = _settle_prop_row(probe, index, teams)
                if not priced:
                    profit = 0.0
            if outcome == "void":
                result.rows_void += 1
            elif outcome == "unsettleable":
                result.rows_unsettleable += 1
            else:
                result.rows_settled += 1
            base.update(settled_at=moment.isoformat(timespec="seconds"), outcome=outcome,
                        actual=actual, profit_units=profit)
            new_rows.append(base)
        result.days_settled += 1
    if new_rows:
        frame = pd.DataFrame(new_rows, columns=list(LEDGER_COLUMNS))
        if len(existing):
            frame = pd.concat([existing[list(LEDGER_COLUMNS)], frame], ignore_index=True)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        _replace_whole(frame, ledger_path)
    return result


def _stat(rows: pd.DataFrame) -> dict[str, Any]:
    """Counts and the game-clustered return for one slice of the ledger."""
    graded = rows[rows["outcome"].isin(["won", "lost"])]
    wagers = graded[graded["american_odds"].notna()]
    out: dict[str, Any] = {
        "listed": int(len(rows)), "unpriced": int(rows["american_odds"].isna().sum()),
        "void": int((rows["outcome"] == "void").sum()),
        "unsettleable": int((rows["outcome"] == "unsettleable").sum()),
        "graded": int(len(graded)), "graded_hits": int((graded["outcome"] == "won").sum()),
        "wagers": int(len(wagers)), "hits": int((wagers["outcome"] == "won").sum()),
        "hit_rate": None, "units": None, "roi": None, "low": None, "high": None, "games": 0,
    }
    if len(wagers):
        values = wagers["profit_units"].astype(float).tolist()
        games_of = list(zip(wagers["home_team"], wagers["away_team"], wagers["date"]))
        interval = clustered_mean_interval(values, games_of, looks=1)
        out.update(hit_rate=out["hits"] / len(wagers), units=float(sum(values)), roi=float(interval.roi),
                   low=None if not math.isfinite(interval.low) else float(interval.low),
                   high=None if not math.isfinite(interval.high) else float(interval.high),
                   games=len(set(games_of)))
    return out


def build_report(ledger: pd.DataFrame, *, pending_rows: int = 0, outputs_dir: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pending_rows": int(pending_rows),
        "headline": backtest_headline(outputs_dir, fallback=OUTPUTS_DIR),
        "categories": {m: _stat(ledger[ledger["market"] == m]) for m in THRESHOLDS},
        "overall": _stat(ledger),
    }
    return payload


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:+.1f}%"


def render_report(payload: dict[str, Any]) -> str:
    L = [
        "# Due List, forward record",
        "",
        "Generated by `scripts/run_drought_rule_forward.py`. Every figure below comes from "
        "`data/processed/drought_forward.csv`, which records each row the Gameday card's "
        f"\"{SECTION_TITLE}\" showed, with the best price it showed, and settles it "
        "after the game by the forward ledger's rules (a player who never entered the game is "
        f"void, a game with no result inside {PATIENCE_DAYS} days is unsettleable and not guessed, "
        "one row per wager at the listed best price).",
        "",
        "**This is the rule's own result.** The list is unstaked and Cooper picks from it; his "
        "picks are his and are not tracked here. It is separate from the registered forward test "
        "(`forward_evidence.md`) and moves nothing in it.",
        "",
        f"**Backtest, for comparison.** {payload['headline']}",
        "",
        "A wager is a listed row with a price that settled won or lost; a row listed as \"not "
        "posted\" is counted as listed and graded for hits but is not a wager and carries no "
        "return. Flat stake of one unit. The interval is 95%, clustered on the game, uncorrected "
        "for looks; `unbounded` means too few games to bound it.",
        "",
        "| Category | Listed | Not posted | Void | Unsettleable | Wagers | Games | Hit rate | ROI | 95% interval | Units |",
        "|:--|--:|--:|--:|--:|--:|--:|--:|--:|:--|--:|",
    ]
    for name, s in [*payload["categories"].items(), ("overall", payload["overall"])]:
        interval = "unbounded" if s["roi"] is not None and (s["low"] is None or s["high"] is None) \
            else ("n/a" if s["roi"] is None else f"{_pct(s['low'])} .. {_pct(s['high'])}")
        hit = "n/a" if s["hit_rate"] is None else f"{s['hit_rate'] * 100:.1f}% ({s['hits']}/{s['wagers']})"
        units = "n/a" if s["units"] is None else f"{s['units']:+.2f}"
        L.append(f"| {name} | {s['listed']} | {s['unpriced']} | {s['void']} | {s['unsettleable']} | "
                 f"{s['wagers']} | {s['games']} | {hit} | {_pct(s['roi'])} | {interval} | {units} |")
    L += ["", f"{payload['pending_rows']} listed row(s) are waiting on their games and are in none of the figures above.", ""]
    if payload["overall"]["wagers"] == 0:
        L += ["No wager has settled yet, so no hit rate or return is stated.", ""]
    return "\n".join(L)


def save_report(payload: dict[str, Any], *, output_dir: Path | None = None) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else OUTPUTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    md, js = directory / REPORT_MARKDOWN_FILENAME, directory / REPORT_JSON_FILENAME
    md.write_text(render_report(payload), encoding="utf-8")
    js.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"markdown": str(md), "json": str(js)}


def pending_rows(processed_dir: Path | None = None) -> int:
    """Rows in dated lists the ledger has not settled yet."""
    directory = list_dir(processed_dir)
    if not directory.is_dir():
        return 0
    done = set(load_ledger(processed_dir)["date"].astype(str))
    return sum(len(pd.read_csv(p)) for p in directory.glob("*.csv") if p.stem not in done)

