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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.drought_rule import (
    SECTION_TITLE,
    THRESHOLDS,
    backtest_headline,
    best_over_prices,
    build_drought_list,
)
from nhl_betting_lab.forward_evidence import (
    PATIENCE_DAYS,
    _player_index,
    _replace_whole,
    _settle_prop_row,
)
from nhl_betting_lab.models.value import profit_on_win
from nhl_betting_lab.season import season_id
from nhl_betting_lab.providers.team_names import resolve_team
from nhl_betting_lab.stats import clustered_mean_interval

LIST_DIRNAME = "drought_list"
LEDGER_FILENAME = "drought_forward.csv"
REPORT_MARKDOWN_FILENAME = "drought_rule_forward.md"
REPORT_JSON_FILENAME = "drought_rule_forward.json"
#: Beside the dated lists: which days were rebuilt after the fact
#: (`backfill_lists`) and which entries took their price from the morning's
#: frozen card prices because the list had none (`fill_prices`). Read by the
#: report and by the public site, so each says which entries it covers.
SOURCES_FILENAME = "sources.json"

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


#: The notional stake the season record is kept at (Cooper, 2026-10-09: "as
#: if we bet .25u on each one every night"). The ledger is kept at one unit;
#: this scales it. Nothing is bet.
TRACKED_STAKE = 0.25


def build_report(ledger: pd.DataFrame, *, pending_rows: int = 0, outputs_dir: Path | None = None,
                 sources: Mapping[str, Any] | None = None) -> dict[str, Any]:
    sources = sources or {}
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pending_rows": int(pending_rows),
        "headline": backtest_headline(outputs_dir, fallback=OUTPUTS_DIR),
        "categories": {m: _stat(ledger[ledger["market"] == m]) for m in THRESHOLDS},
        "overall": _stat(ledger),
        "tracked_stake": TRACKED_STAKE,
        "backfilled_days": sorted((sources.get("backfilled") or {}).keys()),
        "filled_entries": sum(len(v) for v in (sources.get("filled") or {}).values()),
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
    stake, overall = payload.get("tracked_stake", TRACKED_STAKE), payload["overall"]
    if overall["units"] is not None:
        L += [f"**Season, at {stake}u on every priced entry:** {overall['units'] * stake:+.2f}u over "
              f"{overall['wagers']} wager(s), {overall['wagers'] * stake:.2f}u staked. Nothing is bet; this is the "
              "list's record as if it had been.", ""]
    backfilled = payload.get("backfilled_days") or []
    if backfilled:
        L += [f"Rebuilt after the fact, before the list was first recorded: {', '.join(backfilled)}. "
              "Each night is today's rule applied to the games before it, priced at the card's frozen prices "
              "from that morning.", ""]
    if payload.get("filled_entries"):
        L += [f"{payload['filled_entries']} entry(ies) were listed with no price and are graded at the card's "
              "frozen price from that morning (`drought_list/sources.json` names each).", ""]
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



# ---------------------------------------------------------------------------
# Season-long tracking (Cooper, 2026-10-09): every entry as if 0.25u were bet.
#
# The list was first recorded on 2026-10-07. The nights of the season before
# that are rebuilt here from what the lab already held that morning, and an
# entry recorded with no price takes the price the card had frozen that
# morning. Both are written down in `sources.json`, so no backfilled night or
# borrowed price can pass for one the list published.
# ---------------------------------------------------------------------------


def _snapshot(snapshots: Path | None, day: str) -> pd.DataFrame:
    """The card's frozen prices for `day` (forward_evidence's priced snapshot), or nothing."""
    path = Path(snapshots) / f"{day}.csv" if snapshots else None
    if path is None or not path.is_file():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()
    return frame if {"market", "selection", "line", "player", "american_odds"} <= set(frame.columns) else pd.DataFrame()


def load_sources(processed_dir: Path | None = None) -> dict[str, Any]:
    path = list_dir(processed_dir) / SOURCES_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    data.setdefault("backfilled", {})
    data.setdefault("filled", {})
    return data


def _save_sources(data: Mapping[str, Any], processed_dir: Path | None) -> None:
    path = list_dir(processed_dir) / SOURCES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _teams_on(logs: pd.DataFrame, rosters: Mapping[int, str], day: str) -> dict[int, str]:
    """{player id: club} for `day`: the club he dressed for that night, else the cached roster's."""
    team_of = {int(pid): str(team).strip().upper() for pid, team in rosters.items()}
    if not logs.empty and {"date", "player_id", "team"} <= set(logs.columns):
        that_night = logs[logs["date"].astype(str).str.slice(0, 10) == day]
        for r in that_night.itertuples():
            if pd.notna(r.player_id) and str(r.team).strip():
                team_of[int(r.player_id)] = str(r.team).strip().upper()
    return team_of


def _first_start(starts: Mapping[tuple[str, str, str], str], day: str) -> datetime | None:
    moments = []
    for (d, _h, _a), start in starts.items():
        if d != day or not start:
            continue
        try:
            moments.append(datetime.fromisoformat(str(start).replace("Z", "+00:00")))
        except ValueError:
            continue
    return min(moments) if moments else None


def backfill_lists(
    *,
    logs: pd.DataFrame,
    rosters: Mapping[int, str],
    starts: Mapping[tuple[str, str, str], str],
    team_names: Mapping[str, str],
    today: str,
    snapshots: Path | None,
    processed_dir: Path | None = None,
    records: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> list[str]:
    """Rebuild the list for every regular-season night of this season before
    the first one recorded, and say what was done.

    Each night is built by the card's own `build_drought_list`, from the logs
    of games before that night (`qualifiers_entering` reads nothing on or
    after it), with each player on the club he dressed for that night (else
    his cached roster's), every game of the night listed (the puck-drop guard
    is asked a minute before the first face-off), and the best over 0.5 price
    the card froze that morning (`priced_snapshots/<day>.csv`), or "not
    posted" when it froze none. The rule is today's, not the one in force
    that night (the list did not exist yet). A night already recorded or
    settled is never touched, and nothing is rebuilt from the first recorded
    night onward. Every rebuilt night is named in `sources.json`.
    """
    directory = list_dir(processed_dir)
    have = {p.stem for p in directory.glob("*.csv")} if directory.is_dir() else set()
    have |= set(load_ledger(processed_dir)["date"].astype(str))
    season = season_id(today)
    days = sorted({d for (d, _h, _a) in starts if season_id(d) == season and d < today})
    if have:
        first_recorded = min(have)
        days = [d for d in days if d < first_recorded]
    sources = load_sources(processed_dir)
    notes: list[str] = []
    for day in days:
        if day in have:
            continue
        first = _first_start(starts, day)
        if first is None:
            notes.append(f"{day}: no face-off time is cached, so the night cannot be rebuilt.")
            continue
        prices = _snapshot(snapshots, day)
        built = build_drought_list(
            logs=logs, rosters=_teams_on(logs, rosters, day), starts=starts, prices=prices,
            team_names=team_names, day=day, now=first - timedelta(minutes=1), records=records,
        )
        if not built.rows:
            notes.append(f"{day}: nobody qualified" + (f" ({'; '.join(built.notes)})" if built.notes else "") + ".")
            continue
        record_list(built.rows, day, processed_dir=processed_dir)
        priced = sum(1 for r in built.rows if r["american_odds"] is not None)
        sources["backfilled"][day] = {"rows": len(built.rows), "priced": priced, "card_prices": not prices.empty}
        notes.append(f"{day}: rebuilt, {len(built.rows)} row(s), {priced} priced from the card's frozen prices.")
    if any(day in sources["backfilled"] for day in days):
        _save_sources(sources, processed_dir)
    return notes


def fill_prices(
    *,
    logs: pd.DataFrame,
    rosters: Mapping[int, str],
    team_names: Mapping[str, str],
    snapshots: Path | None,
    processed_dir: Path | None = None,
) -> list[str]:
    """Give an entry recorded with no price the best over 0.5 price the card
    froze that morning, and say which entries that covers.

    The price is written into the dated list (as `record_list` lets a later
    run do once) and, where the night has already settled, into the ledger,
    where a won or lost row's profit is restated at it. A recorded price is
    never replaced, and an entry no frozen price covers stays "not posted"
    and is not a wager. Every entry filled is named in `sources.json`.
    """
    directory = list_dir(processed_dir)
    if not directory.is_dir():
        return []
    sources = load_sources(processed_dir)
    ledger_path = Path(processed_dir or PROCESSED_DIR) / LEDGER_FILENAME
    ledger = load_ledger(processed_dir)
    ledger_changed = False
    notes: list[str] = []
    for path in sorted(directory.glob("*.csv")):
        day = path.stem
        listed = pd.read_csv(path)
        listed["american_odds"] = pd.to_numeric(listed["american_odds"], errors="coerce")
        listed["book"] = listed["book"].fillna("").astype(str)
        missing = listed[listed["american_odds"].isna()]
        if missing.empty:
            continue
        prices = _snapshot(snapshots, day)
        if prices.empty:
            continue
        team_of = _teams_on(logs, rosters, day)
        for r in listed.itertuples():
            team_of[int(r.player_id)] = str(r.team).strip().upper()
        playing = {team: (str(r.home_team), str(r.away_team)) for r in listed.itertuples()
                   for team in (str(r.home_team), str(r.away_team))}
        rows = [{"player_id": int(r.player_id), "market": r.market} for r in missing.itertuples()]
        # The listed names themselves, under any the logs hold (a later row wins), so a
        # listed player is known to the name match even where his logs are not loaded.
        named = pd.DataFrame({"role": "skater", "date": "0000-00-00", "game_id": 0,
                              "player_id": listed["player_id"].astype(int), "player": listed["player"].astype(str)})
        if {"role", "date", "game_id", "player_id", "player"} <= set(logs.columns):
            named = pd.concat([named, logs[["role", "date", "game_id", "player_id", "player"]]], ignore_index=True)
        best, _ = best_over_prices(rows, prices=prices, logs=named, team_of=team_of, playing=playing,
                                   team_names=team_names, day=day)
        if not best:
            continue
        filled = sources["filled"].setdefault(day, [])
        for i in missing.index:
            key = (int(listed.at[i, "player_id"]), listed.at[i, "market"])
            if key not in best:
                continue
            odds, book = best[key]
            listed.at[i, "american_odds"], listed.at[i, "book"] = odds, book
            filled.append({"player_id": key[0], "market": key[1], "american_odds": odds, "book": book})
            if len(ledger):
                hit = ((ledger["date"].astype(str) == day) & (pd.to_numeric(ledger["player_id"], errors="coerce") == key[0])
                       & (ledger["market"] == key[1]) & pd.to_numeric(ledger["american_odds"], errors="coerce").isna())
                for j in ledger.index[hit]:
                    ledger.at[j, "american_odds"], ledger.at[j, "book"] = odds, book
                    outcome = ledger.at[j, "outcome"]
                    ledger.at[j, "profit_units"] = profit_on_win(odds) if outcome == "won" else -1.0 if outcome == "lost" else 0.0
                    ledger_changed = True
        _replace_whole(listed[list(LIST_COLUMNS)], path)
        notes.append(f"{day}: {len(filled)} entry(ies) priced from the card's frozen prices.")
    if any(sources["filled"].values()):
        sources["filled"] = {d: v for d, v in sources["filled"].items() if v}
        _save_sources(sources, processed_dir)
    if ledger_changed:
        _replace_whole(ledger[list(LEDGER_COLUMNS)], ledger_path)
    return notes
