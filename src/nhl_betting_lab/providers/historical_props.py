"""Buying historical prop prices, one event at a time, under a hard cap.

A prop model that has only been calibrated has been shown to be internally
sensible and nothing more. The question that matters — does it disagree with a
real price, profitably — needs prices that were actually for sale. The Odds
API retains some of them and sells them back per event.

## What this costs, stated before anything is spent

The historical endpoints bill at **ten credits per market per event**, an
order of magnitude above the live per-event rate. Six prop markets across one
NHL game-day of twelve games is 720 credits. A full season is not affordable
and is not the plan; a stratified sample of game-days is.

Nothing here spends a credit without an explicit `--live` and a `credit_cap`,
and the cap is enforced before each request rather than checked afterwards.

## Retention is not uniform, and pretending it is would be the real failure

The provider retains different markets for different periods, and coverage
differs by book. A market that cannot be bought historically **cannot be
measured historically**, and the honest response is to record it by name as
unmeasurable — not to substitute a calibration number and let it read like a
backtest.

`probe_retention` answers that question for one event at a known cost, so the
per-market retention table in `data/outputs/player_props_backtest.md` is
measured rather than assumed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nhl_betting_lab.config import RAW_DIR
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.providers.odds_api import (
    OddsApiProvider,
    ProviderError,
    normalize_event,
)


#: The historical endpoints bill an order of magnitude above the live ones.
HISTORICAL_CREDITS_PER_MARKET_PER_EVENT = 10

CACHE_DIRNAME = "historical_props"


@dataclass
class RetentionProbe:
    """Which markets a historical snapshot actually carried."""

    event_id: str
    snapshot: str
    markets_requested: tuple[str, ...]
    markets_returned: tuple[str, ...] = ()
    books_returned: tuple[str, ...] = ()
    credits_spent: int = 0
    error: str = ""

    @property
    def markets_missing(self) -> tuple[str, ...]:
        return tuple(
            market
            for market in self.markets_requested
            if market not in self.markets_returned
        )

    def summary_line(self) -> str:
        if self.error:
            return f"Probe failed: {self.error}"
        return (
            f"{len(self.markets_returned)} of {len(self.markets_requested)} "
            f"markets retained at {self.snapshot}; "
            f"{self.credits_spent} credits spent."
        )


@dataclass
class HistoricalBuy:
    """What one historical purchase fetched and what it cost."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    events_requested: int = 0
    events_bought: int = 0
    events_skipped_for_budget: int = 0
    events_from_cache: int = 0
    credits_spent: int = 0
    errors: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (
            f"{len(self.rows):,} historical price rows from "
            f"{self.events_bought} bought event(s) and "
            f"{self.events_from_cache} cached one(s); "
            f"{self.credits_spent} credits spent; "
            f"{self.events_skipped_for_budget} event(s) skipped for budget."
        )


def estimate_credits(*, events: int, markets: int) -> int:
    """Ten credits per market per event. Say it before spending it."""
    return int(events) * int(markets) * HISTORICAL_CREDITS_PER_MARKET_PER_EVENT


def cost_note(*, events: int, markets: int) -> str:
    total = estimate_credits(events=events, markets=markets)
    return (
        f"{events} event(s) x {markets} market(s) x "
        f"{HISTORICAL_CREDITS_PER_MARKET_PER_EVENT} credits = "
        f"**{total:,} credits**. Historical endpoints bill an order of "
        "magnitude above live ones; this is a spend that needs a decision, "
        "not a default."
    )


def _cache_path(event_id: str, snapshot: str, *, raw_dir: Path | None = None) -> Path:
    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / CACHE_DIRNAME
    stamp = str(snapshot).replace(":", "").replace("-", "")
    return directory / f"{event_id}_{stamp}.json"


def _read_cache(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _write_cache(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def probe_retention(
    provider: OddsApiProvider,
    *,
    event_id: str,
    snapshot: str,
    markets: Sequence[str] | None = None,
    raw_dir: Path | None = None,
) -> RetentionProbe:
    """Ask one historical snapshot which markets it actually carries.

    One event, so the cost is bounded and known. The answer feeds the
    per-market retention table, which is what lets the backtest say "this
    market cannot be measured historically" as a measured fact.
    """
    wanted = tuple(
        markets
        if markets is not None
        else (market.provider_key for market in PROP_MARKETS)
    )
    probe = RetentionProbe(
        event_id=str(event_id),
        snapshot=str(snapshot),
        markets_requested=wanted,
    )
    path = _cache_path(event_id, snapshot, raw_dir=raw_dir)
    payload = _read_cache(path)
    if payload is None:
        try:
            payload, _ = provider._get(  # noqa: SLF001 — one adapter, one door
                f"{provider.base_url}/v4/historical/sports/"
                f"{provider.sport_key}/events/{event_id}/odds",
                provider._params(  # noqa: SLF001
                    regions=provider.regions,
                    markets=",".join(wanted),
                    date=str(snapshot),
                ),
            )
        except ProviderError as exc:
            probe.error = str(exc)
            return probe
        probe.credits_spent = estimate_credits(events=1, markets=len(wanted))
        _write_cache(path, payload)

    data = payload.get("data") if isinstance(payload, Mapping) else None
    event = data if isinstance(data, Mapping) else payload
    if not isinstance(event, Mapping):
        probe.error = "The historical snapshot is not a JSON object."
        return probe

    returned: set[str] = set()
    books: set[str] = set()
    for bookmaker in event.get("bookmakers", []) or []:
        if not isinstance(bookmaker, Mapping):
            continue
        books.add(str(bookmaker.get("title") or bookmaker.get("key") or ""))
        for market in bookmaker.get("markets", []) or []:
            if isinstance(market, Mapping):
                returned.add(str(market.get("key", "")).strip())
    probe.markets_returned = tuple(sorted(returned & set(wanted)))
    probe.books_returned = tuple(sorted(book for book in books if book))
    return probe


def buy_historical_props(
    provider: OddsApiProvider,
    *,
    events: Sequence[Mapping[str, str]],
    markets: Sequence[str] | None = None,
    credit_cap: int,
    raw_dir: Path | None = None,
) -> HistoricalBuy:
    """Buy historical prop prices for specific events, under a hard cap.

    `events` is a sequence of `{"event_id": ..., "snapshot": ...}`. The
    snapshot is the ISO instant to price at — use a time a few hours before
    puck drop, matching when a card would actually have been built. Pricing at
    a closing snapshot would measure the model against a line it could never
    have bet.

    A previously bought event is served from the cache and costs nothing, so
    re-running a measurement is free.
    """
    wanted = list(
        markets
        if markets is not None
        else (market.provider_key for market in PROP_MARKETS)
    )
    if not wanted:
        raise ProviderError("A historical buy needs at least one market.")
    per_event = estimate_credits(events=1, markets=len(wanted))
    buy = HistoricalBuy(events_requested=len(events))

    for entry in events:
        event_id = str(entry.get("event_id", "")).strip()
        snapshot = str(entry.get("snapshot", "")).strip()
        if not event_id or not snapshot:
            buy.errors.append(f"Skipped an event with no id or snapshot: {entry!r}")
            continue
        path = _cache_path(event_id, snapshot, raw_dir=raw_dir)
        payload = _read_cache(path)
        if payload is None:
            if buy.credits_spent + per_event > credit_cap:
                buy.events_skipped_for_budget += 1
                continue
            try:
                payload, _ = provider._get(  # noqa: SLF001
                    f"{provider.base_url}/v4/historical/sports/"
                    f"{provider.sport_key}/events/{event_id}/odds",
                    provider._params(  # noqa: SLF001
                        regions=provider.regions,
                        markets=",".join(wanted),
                        date=snapshot,
                    ),
                )
            except ProviderError as exc:
                buy.errors.append(f"Event {event_id} at {snapshot}: {exc}")
                continue
            buy.credits_spent += per_event
            buy.events_bought += 1
            _write_cache(path, payload)
        else:
            buy.events_from_cache += 1

        data = payload.get("data") if isinstance(payload, Mapping) else None
        event = data if isinstance(data, Mapping) else payload
        if not isinstance(event, Mapping):
            buy.errors.append(f"Event {event_id}: malformed historical payload.")
            continue
        rows = normalize_event(event, fetched_at=snapshot)
        for row in rows:
            row["snapshot"] = snapshot
        buy.rows.extend(rows)

    return buy


def retention_table(probes: Sequence[RetentionProbe]) -> str:
    """The per-market retention table the backtest report embeds."""
    if not probes:
        return (
            "No retention probe has been run, so which prop markets can be "
            "measured historically is **unknown**. It is not assumed to be "
            "all of them, and it is not assumed to be none."
        )
    requested: list[str] = []
    for probe in probes:
        for market in probe.markets_requested:
            if market not in requested:
                requested.append(market)
    lines = [
        "| Provider market | Snapshots probed | Retained in | Measurable historically |",
        "|:----------------|-----------------:|------------:|:------------------------|",
    ]
    for market in requested:
        probed = [probe for probe in probes if market in probe.markets_requested]
        retained = [probe for probe in probed if market in probe.markets_returned]
        lines.append(
            f"| `{market}` | {len(probed)} | {len(retained)} | "
            + ("yes" if retained else "**no — cannot be measured**")
            + " |"
        )
    return "\n".join(lines)
