"""Freeze what the model said before the game, settle it after, accumulate.

The historical backtest re-prices past games with walk-forward fits, which is
honest but reconstructed. This is the stronger thing the docs promise: **the
opinion the live card actually held, written down before puck drop, settled
against the boxscore after, and never revised.** It is also the only possible
price evidence for the markets no book retains historically — hits and the
regulation three-way — and the accumulating out-of-sample test for every
market and every shipped policy at once.

Three stages, each idempotent:

**Snapshot.** After the card prices a slate, every priced row is written to
`data/archive/priced_snapshots/{league date}.csv` with the model's
probability, the edge against the price as sold, and the policy verdicts in
force. A snapshot is evidence and is never overwritten: the first opinion of
the day stands, because "the card's opinion" repriced at a better moment is
not the card's opinion any more.

**Settle.** Once a snapshot day's results are final, each row is settled from
the boxscore — via the same identity join and the same settlement rules the
historical backtest uses, because a second copy of either is how every join
bug in this repository started. Settled rows append to the forward ledger; a
player who never dressed voids (stake returned), and a row whose game never
produced a result within the patience window is recorded as unsettleable,
counted, never guessed.

**Report.** `data/outputs/forward_evidence.md`: per-market accumulating
intervals in the house vocabulary — sample sizes beside every number,
family-corrected, and "no demonstrated edge" in those words while it is true.
The detection arithmetic says roughly six hundred bets separate a real +8%
from zero, so the report also says plainly how far along that road the ledger
is.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.stores import read_store

from nhl_betting_lab.backtest.team_walk_forward import (
    settle_moneyline,
    settle_puck_line,
    settle_regulation_3_way,
    settle_team_total,
    settle_total,
)
from nhl_betting_lab.config import DATA_DIR, MIN_EDGE, MIN_PROP_EDGE, OUTPUTS_DIR
from nhl_betting_lab.markets import MARKETS_BY_KEY
from nhl_betting_lab.models.player_props import player_name_aliases
from nhl_betting_lab.models.value import OddsError, american_to_implied, profit_on_win
from nhl_betting_lab.providers.team_names import resolve_team
from nhl_betting_lab.reports.player_props_backtest import settle as settle_prop
from nhl_betting_lab.season import clean_text, row_game_date


SNAPSHOT_DIRNAME = "priced_snapshots"
LEDGER_FILENAME = "forward_evidence.csv"
REPORT_MARKDOWN_FILENAME = "forward_evidence.md"
REPORT_JSON_FILENAME = "forward_evidence.json"

#: Days to keep waiting for a result before recording a row unsettleable.
#: Postponed games are rescheduled within days; a fortnight without a final
#: boxscore means the row will never settle against the game it priced.
PATIENCE_DAYS = 14

SNAPSHOT_COLUMNS = (
    "snapshot_date",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "line",
    "american_odds",
    "book",
    "model_probability",
    "edge",
    "verdicts_in_force",
)

LEDGER_COLUMNS = SNAPSHOT_COLUMNS + (
    "settled_at",
    "outcome",  # won | lost | push | void | unsettleable
    "actual",
    "profit_units",
)


def snapshots_dir(archive_dir: Path | None = None) -> Path:
    return (Path(archive_dir) if archive_dir else DATA_DIR / "archive") / (
        SNAPSHOT_DIRNAME
    )


def write_snapshot(
    prices: pd.DataFrame,
    probabilities: Mapping[tuple, float],
    *,
    key_for,
    verdicts_line: str,
    snapshot_date: str,
    archive_dir: Path | None = None,
) -> Path | None:
    """Freeze today's priced opinions. Returns None when one already stands.

    `key_for(row, market, selection, line)` is the card's own key function,
    passed in rather than imported by both sides — the probability map and
    the snapshot must agree on the key by construction.
    """
    directory = snapshots_dir(archive_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{snapshot_date}.csv"
    if target.exists():
        # The first opinion of the day stands. A repriced snapshot is not the
        # card's opinion any more, and two snapshots for one day would let
        # the flattering one be the one that settles.
        return None

    rows: list[dict[str, object]] = []
    for row in prices.itertuples():
        market = clean_text(getattr(row, "market", ""))
        selection = clean_text(getattr(row, "selection", "")).lower()
        line_value = getattr(row, "line", None)
        try:
            line = (
                None
                if line_value is None or pd.isna(line_value)
                else float(line_value)
            )
        except (TypeError, ValueError):
            line = None
        probability = probabilities.get(
            key_for(row, market=market, selection=selection, line=line)
        )
        if probability is None:
            continue
        try:
            implied = american_to_implied(getattr(row, "american_odds"))
            price = float(getattr(row, "american_odds"))
        except (OddsError, TypeError, ValueError):
            continue
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "commence_time": clean_text(getattr(row, "commence_time", "")),
                "home_team": clean_text(getattr(row, "home_team", "")),
                "away_team": clean_text(getattr(row, "away_team", "")),
                "market": market,
                "player": clean_text(getattr(row, "player", "")),
                "selection": selection,
                "line": line,
                "american_odds": price,
                "book": clean_text(getattr(row, "book", "")),
                "model_probability": float(probability),
                "edge": float(probability) - implied,
                "verdicts_in_force": verdicts_line,
            }
        )
    frame = pd.DataFrame(rows, columns=list(SNAPSHOT_COLUMNS))
    frame.to_csv(target, index=False, lineterminator="\n")
    return target


@dataclass
class SettlementResult:
    """What one settlement pass did, so silence stays legible."""

    snapshots_seen: int = 0
    snapshots_settled: int = 0
    snapshots_waiting: int = 0
    rows_settled: int = 0
    rows_void: int = 0
    rows_unsettleable: int = 0
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (
            f"{self.snapshots_settled} of {self.snapshots_seen} pending "
            f"snapshot(s) settled ({self.snapshots_waiting} still waiting "
            f"for results); {self.rows_settled} row(s) settled, "
            f"{self.rows_void} void, {self.rows_unsettleable} unsettleable."
        )


def _player_index(
    logs: pd.DataFrame, game_date: str
) -> dict[str, dict[int, tuple[str, float | None, dict[str, float]]]]:
    """alias -> {player_id: (team, actuals per settlement column)} for one day."""
    day = logs[logs["date"].astype(str).str.slice(0, 10) == game_date]
    index: dict[str, dict[int, tuple[str, dict[str, float]]]] = {}
    for row in day.itertuples():
        actuals = {
            market.settles_on: float(
                pd.to_numeric(getattr(row, market.settles_on, 0), errors="coerce")
                or 0.0
            )
            for market in MARKETS_BY_KEY.values()
            if market.is_prop
        }
        entry = (str(row.team).strip().upper(), actuals)
        for alias in player_name_aliases(row.player):
            index.setdefault(alias, {})[int(row.player_id)] = entry
    return index


def _finite_line(value: object) -> float | None:
    """The row's line as a real number, or None.

    NaN is the shape a missing CSV field takes, and it is silent poison in a
    settlement: every comparison against it is False, so an absent line
    settles "under" as a win and "over" as a loss without raising anything.
    A market that needs a line and has none is unsettleable — a state this
    ledger already knows how to record.
    """
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _settle_prop_row(
    row, player_index, game_teams: set[str]
) -> tuple[str, float | None, float]:
    """(outcome, actual, profit) for one snapshot prop row."""
    market = MARKETS_BY_KEY.get(str(row.market))
    if market is None or not market.settles_on:
        return "unsettleable", None, 0.0
    candidates: dict[int, tuple[str, dict[str, float]]] = {}
    for alias in player_name_aliases(row.player):
        candidates.update(player_index.get(alias, {}))
    if game_teams:
        candidates = {
            player_id: entry
            for player_id, entry in candidates.items()
            if entry[0] in game_teams
        }
    if len(candidates) > 1:
        return "unsettleable", None, 0.0
    if not candidates:
        # The player never entered the game: books void the bet.
        return "void", None, 0.0
    _, actuals = next(iter(candidates.values()))
    actual = actuals.get(market.settles_on)
    if actual is None:
        return "unsettleable", None, 0.0
    line = _finite_line(row.line)
    if line is None:
        return "unsettleable", actual, 0.0
    try:
        won, push = settle_prop(actual, line, str(row.selection))
    except (TypeError, ValueError):
        return "unsettleable", actual, 0.0
    if push:
        return "push", actual, 0.0
    if won:
        return "won", actual, profit_on_win(float(row.american_odds))
    return "lost", actual, -1.0


def _settle_team_row(row, game) -> tuple[str, float | None, float]:
    """(outcome, actual, profit) for one snapshot team row."""
    home_goals = int(game.home_goals)
    away_goals = int(game.away_goals)
    regulation = bool(getattr(game, "regulation", True))
    market = str(row.market)
    selection = str(row.selection)
    price = float(row.american_odds)

    if market == "moneyline":
        try:
            winner = settle_moneyline(home_goals, away_goals)
        except ValueError:
            return "unsettleable", None, 0.0
        won, push = winner == selection, False
        actual = float(home_goals - away_goals)
    elif market == "regulation_3_way":
        try:
            result = settle_regulation_3_way(
                home_goals, away_goals, regulation=regulation
            )
        except ValueError:
            return "unsettleable", None, 0.0
        won, push = result == selection, False
        actual = float(home_goals - away_goals)
    elif market == "puck_line":
        line = _finite_line(row.line)
        if line is None:
            return "unsettleable", None, 0.0
        side = (
            ("home_minus" if line < 0 else "home_plus")
            if selection == "home"
            else ("away_minus" if line < 0 else "away_plus")
        )
        won, push = settle_puck_line(
            home_goals, away_goals, regulation=regulation, line=abs(line)
        )[side]
        actual = float(home_goals - away_goals)
    elif market == "total_goals":
        line = _finite_line(row.line)
        if line is None:
            return "unsettleable", None, 0.0
        over, push = settle_total(home_goals, away_goals, line)
        won = over if selection == "over" else (not over and not push)
        actual = float(home_goals + away_goals)
    elif market == "team_total":
        # The side rides in the selection vocabulary (`home_over` …); a row
        # outside it cannot be settled and must never be guessed at.
        side, _, direction = selection.partition("_")
        line = _finite_line(row.line)
        if line is None or side not in {"home", "away"} or direction not in {
            "over",
            "under",
        }:
            return "unsettleable", None, 0.0
        side_goals = home_goals if side == "home" else away_goals
        over, push = settle_team_total(side_goals, line)
        won = over if direction == "over" else (not over and not push)
        actual = float(side_goals)
    else:
        return "unsettleable", None, 0.0

    if push:
        return "push", actual, 0.0
    if won:
        return "won", actual, profit_on_win(price)
    return "lost", actual, -1.0


def settle_snapshots(
    logs: pd.DataFrame,
    games: pd.DataFrame,
    *,
    team_names: Mapping[str, str],
    archive_dir: Path | None = None,
    processed_dir: Path | None = None,
    now: datetime | None = None,
) -> SettlementResult:
    """Settle every pending snapshot whose results are in.

    A snapshot settles as a unit only when every game on it is final — a
    half-settled day would make the ledger's totals move twice for one day,
    and whichever half settled first would look like the whole day.
    """
    moment = now or datetime.now(timezone.utc)
    directory = snapshots_dir(archive_dir)
    ledger_path = (
        Path(processed_dir)
        if processed_dir
        else DATA_DIR / "processed"
    ) / LEDGER_FILENAME
    result = SettlementResult()
    if not directory.is_dir():
        return result

    finals = {
        (
            str(game.date)[:10],
            str(game.home_team).strip().upper(),
            str(game.away_team).strip().upper(),
        ): game
        for game in games.itertuples()
    }
    # A day is done when its marker exists. The ledger alone cannot say so:
    # a snapshot that settled with zero rows (an empty preseason day) leaves
    # no ledger trace and would re-settle forever. The marker is a sidecar
    # rather than a rename, because a snapshot's name is part of the
    # evidence and evidence does not get renamed.
    settled_days = {
        marker.name.removesuffix(".settled")
        for marker in directory.glob("*.settled")
    }
    if ledger_path.is_file():
        settled_days |= set(
            pd.read_csv(ledger_path, usecols=["snapshot_date"])[
                "snapshot_date"
            ].astype(str)
        )

    new_rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.csv")):
        day = path.stem
        if day in settled_days:
            continue
        result.snapshots_seen += 1
        snapshot = pd.read_csv(path)
        if snapshot.empty:
            (directory / f"{day}.settled").touch()
            result.snapshots_settled += 1
            continue

        # Which final game each row belongs to, by league date and abbrevs.
        def game_for(row):
            return finals.get(
                (
                    row_game_date(row),
                    resolve_team(getattr(row, "home_team", ""), team_names)
                    or "",
                    resolve_team(getattr(row, "away_team", ""), team_names)
                    or "",
                )
            )

        games_found = [game_for(row) for row in snapshot.itertuples()]
        age_days = (
            moment.date() - datetime.fromisoformat(day).date()
        ).days
        if any(game is None for game in games_found) and age_days <= PATIENCE_DAYS:
            # Results not all in yet. Wait — a half-settled day would make
            # the ledger move twice for one day.
            result.snapshots_waiting += 1
            continue

        player_indexes: dict[str, dict] = {}
        for row, game in zip(snapshot.itertuples(), games_found):
            base = {
                column: getattr(row, column, None)
                for column in SNAPSHOT_COLUMNS
            }
            base["settled_at"] = moment.isoformat(timespec="seconds")
            if game is None:
                outcome, actual, profit = "unsettleable", None, 0.0
                result.rows_unsettleable += 1
            else:
                market = MARKETS_BY_KEY.get(str(row.market))
                if market is not None and market.is_prop:
                    game_day = row_game_date(row)
                    if game_day not in player_indexes:
                        player_indexes[game_day] = _player_index(logs, game_day)
                    game_teams = {
                        resolve_team(row.home_team, team_names),
                        resolve_team(row.away_team, team_names),
                    }
                    game_teams.discard(None)
                    outcome, actual, profit = _settle_prop_row(
                        row, player_indexes[game_day], game_teams
                    )
                else:
                    outcome, actual, profit = _settle_team_row(row, game)
                if outcome == "void":
                    result.rows_void += 1
                elif outcome == "unsettleable":
                    result.rows_unsettleable += 1
                else:
                    result.rows_settled += 1
            base["outcome"] = outcome
            base["actual"] = actual
            base["profit_units"] = profit
            new_rows.append(base)
        (directory / f"{day}.settled").touch()
        result.snapshots_settled += 1

    if new_rows:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(new_rows, columns=list(LEDGER_COLUMNS))
        existing_rows = 0
        if ledger_path.is_file():
            existing = read_store(
                ledger_path, columns=LEDGER_COLUMNS, for_append=True
            )
            existing_rows = len(existing)
            frame = pd.concat([existing, frame], ignore_index=True)
        # The ledger only ever grows: it is an append-only record of opinions
        # that have already settled, and a season of it cannot be
        # reconstructed from anywhere else — the prices it settled against
        # are gone. A write that would shrink it means the file being
        # concatenated is not the file that was read, and the safe move is to
        # refuse rather than to publish a shorter history as the whole truth.
        if len(frame) < existing_rows:
            raise ValueError(
                f"Refusing to write a forward ledger of {len(frame)} rows "
                f"over one holding {existing_rows}. The ledger is "
                "append-only and cannot be rebuilt; something upstream lost "
                "rows."
            )
        frame.to_csv(ledger_path, index=False, lineterminator="\n")
    return result


def load_ledger(processed_dir: Path | None = None) -> pd.DataFrame:
    path = (
        Path(processed_dir) if processed_dir else DATA_DIR / "processed"
    ) / LEDGER_FILENAME
    if not path.is_file():
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    return pd.read_csv(path)


def build_forward_report(
    ledger: pd.DataFrame, *, now: datetime | None = None
) -> dict:
    """Per-market accumulating evidence, in the house vocabulary.

    Two views of the same ledger, kept separate because they answer different
    questions. **Opinions** is every priced row the model held a view on —
    the calibration-grade stream. **Bets** is the subset clearing the shipped
    edge bars at the price as sold — the stream an allowlist decision will
    eventually rest on. Mixing them would flatter whichever is worse.
    """
    from nhl_betting_lab.stats import roi_interval

    moment = now or datetime.now(timezone.utc)
    payload: dict = {
        "generated_at": moment.isoformat(timespec="seconds"),
        "rows": int(len(ledger)),
        "markets": {},
        "unsettleable": 0,
        "void": 0,
    }
    if ledger.empty:
        return payload

    settled = ledger[ledger["outcome"].isin(["won", "lost", "push"])]
    payload["unsettleable"] = int((ledger["outcome"] == "unsettleable").sum())
    payload["void"] = int((ledger["outcome"] == "void").sum())

    markets = sorted(set(settled["market"].astype(str)))
    for market_key in markets:
        subset = settled[settled["market"].astype(str) == market_key]
        market = MARKETS_BY_KEY.get(market_key)
        bar = (
            MIN_PROP_EDGE if market is not None and market.is_prop else MIN_EDGE
        )
        bets = subset[subset["edge"].astype(float) >= bar]
        entry: dict = {
            "opinions": int(len(subset)),
            "first_date": str(subset["snapshot_date"].min()),
            "last_date": str(subset["snapshot_date"].max()),
        }
        if len(bets):
            interval = roi_interval(
                bets["profit_units"].astype(float).tolist(),
                wins=int((bets["outcome"] == "won").sum()),
                pushes=int((bets["outcome"] == "push").sum()),
                looks=len(markets),
            )
            entry["bets"] = interval.bets
            entry["profit_units"] = interval.profit
            entry["roi"] = interval.roi
            entry["low"] = interval.low
            entry["high"] = interval.high
            entry["includes_zero"] = interval.includes_zero
            entry["verdict"] = interval.verdict()
        else:
            entry["bets"] = 0
            entry["verdict"] = (
                "No settled row has yet cleared the shipped edge bar, so "
                "there is nothing to measure. That is a statement about the "
                "season so far, not about the model."
            )
        payload["markets"][market_key] = entry
    return payload


def render_forward_report(payload: dict) -> str:
    from nhl_betting_lab.stats import NO_DEMONSTRATED_EDGE, bets_needed_to_detect

    lines = [
        "# Forward evidence",
        "",
        (
            "The opinion the live card actually held, written down before "
            "puck drop, settled against the boxscore after, never revised. "
            "This is the only possible price evidence for the markets no "
            "book retains historically — hits and the regulation three-way — "
            "and the accumulating out-of-sample test for everything else."
        ),
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Ledger rows: {payload['rows']:,}"
        + (
            f" ({payload['void']:,} void, "
            f"{payload['unsettleable']:,} unsettleable)"
            if payload["rows"]
            else ""
        ),
        "",
    ]
    if not payload["markets"]:
        lines += [
            "## Nothing settled yet",
            "",
            (
                "The ledger is empty or nothing on it has settled. Before "
                "the season starts this is the correct state, not a fault: "
                "forward evidence can only begin accumulating when books "
                "post prices and games produce results."
            ),
            "",
        ]
        return "\n".join(lines)

    lines += [
        "## Accumulated so far, at the shipped edge bars",
        "",
        (
            "| Market | Opinions | Bets | Profit | ROI | 95% interval "
            "| Includes zero |"
        ),
        "|:-------|---------:|-----:|-------:|----:|:-------------|:--|",
    ]
    for market, entry in sorted(payload["markets"].items()):
        if entry["bets"]:
            lines.append(
                f"| `{market}` | {entry['opinions']:,} | {entry['bets']:,} "
                f"| {entry['profit_units']:+.1f}u | {entry['roi']:+.1%} "
                f"| {entry['low']:+.1%} .. {entry['high']:+.1%} "
                f"| {'yes' if entry['includes_zero'] else 'no'} |"
            )
        else:
            lines.append(
                f"| `{market}` | {entry['opinions']:,} | 0 | — | — | — | — |"
            )
    lines += [""]
    for market, entry in sorted(payload["markets"].items()):
        lines.append(f"- `{market}`: {entry['verdict']}")
    lines += [
        "",
        "## How far along the road this is",
        "",
        (
            f"Separating a true +8% edge from zero takes about "
            f"{bets_needed_to_detect(0.08):,} bets per market. Every interval "
            f"that includes zero means **{NO_DEMONSTRATED_EDGE}** — those "
            "words, for as long as they are true."
        ),
        "",
        "## What this stream is and is not",
        "",
        (
            "- Frozen before the games: nothing here was repriced after the "
            "fact, which the historical backtest cannot claim."
        ),
        (
            "- Settled by the same identity join and settlement rules as the "
            "historical backtest — one copy of each, on purpose."
        ),
        (
            "- A void is a player who never entered (stake returned, as "
            "books do). An unsettleable row is a game that never produced a "
            "final result inside the patience window — counted, never "
            "guessed."
        ),
        (
            "- Recommendations were never placed as bets. This ledger prices "
            "a paper record of the shipped policy, nothing more."
        ),
        "",
    ]
    return "\n".join(lines)


def save_forward_report(
    payload: dict, *, output_dir: Path | None = None
) -> dict[str, str]:
    directory = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / REPORT_MARKDOWN_FILENAME
    markdown.write_text(render_forward_report(payload), encoding="utf-8")
    json_path = directory / REPORT_JSON_FILENAME
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(markdown), "json": str(json_path)}
