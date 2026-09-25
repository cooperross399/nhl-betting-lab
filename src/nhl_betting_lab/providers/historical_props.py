"""Buying historical prop prices, one event at a time, under a hard cap.

A prop model that has only been calibrated has been shown to be internally
sensible and nothing more. The question that matters — does it disagree with a
real price, profitably — needs prices that were actually for sale. The Odds
API retains some of them and sells them back per event.

## What this costs — measured, and now known

The provider's documentation is ambiguous about the per-event historical
endpoint: it documents "10 x [markets] x [regions]" for the *bulk* historical
endpoint, and for the per-event one says either one-per-market-returned or
nothing at all, depending which part of the guide you read. That was a
tenfold uncertainty on the most expensive thing this repository does.

**Measured on 2026-08-25: it is ten credits per market returned.** A probe of
one event requesting six markets got five back and `x-requests-last` said 50.
The pessimistic reading was the right one.

Nothing assumes even so. Every response carries `x-requests-last`, which is
what the request actually cost, and `x-requests-remaining`; those are the
numbers accounted and reported. The estimate is kept for one job — a
**pre-flight upper bound**, so a run refuses to start a request that might
breach the cap — and it stays pessimistic, because a cap that can only be
over-respected is the safe direction to be wrong in.

A day's listing costs 1 credit and returns the whole slate, so the marginal
cost of a sampled slate is `10 x [markets retained] x [games that night]`,
plus one.

Nothing spends a credit without an explicit `--live` and a `credit_cap`, and
the cap is checked before each request rather than after.

## Retention is not uniform, and pretending it is would be the real failure

The provider retains different markets for different periods, and coverage
differs by book. A market that cannot be bought historically **cannot be
measured historically**, and the honest response is to record it by name as
unmeasurable — not to substitute a calibration number and let it read like a
backtest.

`probe_retention` answers that question for one event at a known cost. **One
event is not retention.** A probe of a single event on 2026-01-10 returned
five of six markets and I recorded `player_total_saves` as unmeasurable; the
purchase that followed found it priced on 54 of 58 events across six books.
The market was there all along and the sample of one was not a sample.

That is the EPL `total_2_5` mistake repeating in a new costume — concluding
"not offered" from a look too narrow to support it — in a repository that
carries a document about that exact lesson. So `MINIMUM_PROBES_FOR_ABSENCE`
now governs: below it, a market that did not appear is reported as *not seen
in N events*, which is a different sentence from *cannot be measured*, and
`retention_table` refuses to write the second one.
"""

from __future__ import annotations

import hashlib
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


#: Pessimistic upper bound per market per event, used only to decide whether
#: the *next* request could breach the cap. The provider documents this
#: multiplier for the bulk historical endpoint and is ambiguous about the
#: per-event one; assuming the expensive reading means the cap can only ever
#: be over-respected. Real spend is read from `x-requests-last`.
HISTORICAL_CREDITS_UPPER_BOUND_PER_MARKET = 10

#: Historical events list. Documented flatly, and free when it finds nothing.
HISTORICAL_EVENTS_LIST_COST = 1

#: How many events must be probed before absence means anything. One probe
#: called `player_total_saves` unmeasurable; it was priced on 54 of the next
#: 58 events. Books differ, and a single event is a book's night rather than
#: the provider's retention policy.
MINIMUM_PROBES_FOR_ABSENCE = 5

CACHE_DIRNAME = "historical_props"


@dataclass
class RetentionProbe:
    """Which markets a historical snapshot actually carried, and what it cost."""

    event_id: str
    snapshot: str
    markets_requested: tuple[str, ...]
    markets_returned: tuple[str, ...] = ()
    books_returned: tuple[str, ...] = ()
    #: Read from `x-requests-last`, not estimated.
    credits_spent: int = 0
    credits_remaining: str = ""
    #: What the pessimistic estimate would have predicted, for comparison.
    credits_estimated: int = 0
    error: str = ""

    @property
    def measured_cost_per_market(self) -> float | None:
        """The real per-market rate this probe observed."""
        if not self.credits_spent or not self.markets_returned:
            return None
        return self.credits_spent / len(self.markets_returned)

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
        rate = self.measured_cost_per_market
        detail = (
            f" That is {rate:.2g} credit(s) per market returned, against an "
            f"assumed upper bound of "
            f"{HISTORICAL_CREDITS_UPPER_BOUND_PER_MARKET}."
            if rate is not None
            else ""
        )
        return (
            f"{len(self.markets_returned)} of {len(self.markets_requested)} "
            f"markets retained at {self.snapshot}; "
            f"{self.credits_spent} credit(s) actually spent"
            + (
                f", {self.credits_remaining} remaining."
                if self.credits_remaining
                else "."
            )
            + detail
        )


@dataclass
class HistoricalBuy:
    """What one historical purchase fetched and what it actually cost."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    events_requested: int = 0
    events_bought: int = 0
    events_skipped_for_budget: int = 0
    events_from_cache: int = 0
    #: Measured from `x-requests-last`, summed. Not an estimate.
    credits_spent: int = 0
    credits_remaining: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def credits_per_event(self) -> float | None:
        if not self.events_bought:
            return None
        return self.credits_spent / self.events_bought

    def summary_line(self) -> str:
        rate = self.credits_per_event
        return (
            f"{len(self.rows):,} historical price rows from "
            f"{self.events_bought} bought event(s) and "
            f"{self.events_from_cache} cached one(s); "
            f"{self.credits_spent} credit(s) actually spent"
            + (f" ({rate:.3g} per event)" if rate is not None else "")
            + (
                f", {self.credits_remaining} remaining"
                if self.credits_remaining
                else ""
            )
            + f"; {self.events_skipped_for_budget} event(s) skipped for budget."
        )


def estimate_credits(*, events: int, markets: int, regions: int = 1) -> int:
    """A bound used to decide whether to start a request. **Not a guarantee.**

    Not a prediction either. The provider's documentation is ambiguous about
    the per-event historical rate, so this assumes the expensive reading.

    An earlier version of this docstring said the cap "can only ever be
    over-respected, never breached". That was wrong and a production run
    proved it: seven markets at the assumed ten credits each predicted 70 an
    event and the provider charged **107**, so a run capped at 200,000 spent
    289,984. Asking for seven market KEYS can return more than seven BILLABLE
    markets, because every alternate ladder bills on its own — so a bound
    computed from the keys asked for is not an upper bound on what is
    charged. The caller therefore also enforces the cap against MEASURED
    spend, which is the gate that cannot be mis-specified.

    `regions` is the multiplier this function omitted for its whole life.
    The provider bills `10 x markets returned x regions`, and the lab asks
    for `us,us2` -- two regions. So the measured 107 an event was not the
    documented rule being wrong; it was the documented rule with the region
    factor applied (10 x ~5.35 returned x 2) and this estimate leaving it
    out. The sibling `historical_team_prices.estimate_credits` has carried
    the factor since it was written. Callers pass `provider.region_count`.
    """
    return (
        int(events)
        * int(markets)
        * max(1, int(regions))
        * HISTORICAL_CREDITS_UPPER_BOUND_PER_MARKET
    )


def cost_note(*, events: int, markets: int, regions: int = 1) -> str:
    upper = estimate_credits(events=events, markets=markets, regions=regions)
    lower = int(events) * int(markets) * max(1, int(regions))
    return (
        f"{events} event(s) x {markets} market(s): between **{lower:,}** and "
        f"**{upper:,} credits**. The provider documents 10x per market for "
        "the bulk historical endpoint and is ambiguous about the per-event "
        f"one, so the true figure is somewhere in that range and is read "
        "from `x-requests-last` as it is spent. **This range has been too "
        "low in production**: a run asking seven markets was charged 107 "
        "credits an event, not 70, because every alternate ladder bills as "
        "its own market. The cap is therefore enforced against **both** this "
        "estimate and the measured running total — the second because the "
        "first has already been wrong."
    )


def _markets_fingerprint(markets: Sequence[str] | None) -> str:
    """A short, stable tag for the market list a response was bought with.

    The cache key needs it. A response holds the markets that were asked for
    and nothing else, so a later run asking for one more market would have
    been served the old file and told, quite confidently, that the new market
    is not offered — the same shape as every other silent-shortfall bug in
    this repository, and self-fulfilling to boot.
    """
    if not markets:
        return "all"
    joined = ",".join(sorted(str(item) for item in markets))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:8]


def _cache_path(
    event_id: str,
    snapshot: str,
    *,
    raw_dir: Path | None = None,
    markets: Sequence[str] | None = None,
) -> Path:
    """Where one bought snapshot lives.

    `event_id` is a provider id, or the literal `events` for a slate listing.
    Historical prices never change, so a cached file is evidence and a re-run
    over the same window costs nothing — provided it asked for the same
    markets, which is why they are in the key.
    """
    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / CACHE_DIRNAME
    stamp = str(snapshot).replace(":", "").replace("-", "")
    return directory / f"{event_id}_{stamp}_{_markets_fingerprint(markets)}.json"


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


def _measured_cost(headers: Mapping[str, str]) -> int:
    """What the request actually cost, from `x-requests-last`.

    Returns 0 when the header is absent rather than guessing. A missing header
    is handled by the caller, which falls back to charging the pessimistic
    estimate against the cap — the safe direction.
    """
    try:
        return int(str(headers.get("x-requests-last", "")).strip())
    except (TypeError, ValueError):
        return 0


def list_historical_events(
    provider: OddsApiProvider,
    *,
    snapshot: str,
    raw_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], int, str]:
    """Events on the slate at a past instant, plus what the lookup cost.

    This exists because the live events endpoint only knows about *upcoming*
    games. Pointing it at a past window returns nothing at all — which looks
    exactly like "the provider has no data for that window" and is not. It is
    the bug that would have made a purchase run silently buy zero events and
    report success.

    Documented at one credit, and free when it finds nothing.
    """
    path = _cache_path("events", snapshot, raw_dir=raw_dir, markets=None)
    cached = _read_cache(path)
    if cached is not None:
        data = cached.get("data") if isinstance(cached, Mapping) else cached
        return (
            [item for item in (data or []) if isinstance(item, dict)],
            0,
            "",
        )

    payload, headers = provider._get(  # noqa: SLF001 — one adapter, one door
        f"{provider.base_url}/v4/historical/sports/{provider.sport_key}/events",
        {"apiKey": provider.api_key, "date": str(snapshot), "dateFormat": "iso"},
    )
    _write_cache(path, payload)
    data = payload.get("data") if isinstance(payload, Mapping) else payload
    events = [item for item in (data or []) if isinstance(item, dict)]
    return (
        events,
        _measured_cost(headers) or HISTORICAL_EVENTS_LIST_COST,
        str(headers.get("x-requests-remaining", "")),
    )


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
    probe.credits_estimated = estimate_credits(
        events=1, markets=len(wanted), regions=provider.region_count
    )
    path = _cache_path(event_id, snapshot, raw_dir=raw_dir, markets=wanted)
    payload = _read_cache(path)
    if payload is None:
        try:
            payload, headers = provider._get(  # noqa: SLF001 — one door
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
        # The real number, not the estimate. When the header is missing the
        # pessimistic estimate stands in, so an unreadable response can never
        # make a run look cheaper than it was.
        probe.credits_spent = _measured_cost(headers) or probe.credits_estimated
        probe.credits_remaining = str(headers.get("x-requests-remaining", ""))
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


def retention_from_cache(
    *,
    raw_dir: Path | None = None,
    markets: Sequence[str] | None = None,
) -> list[RetentionProbe]:
    """Retention read from the responses already bought. Costs nothing.

    A probe is a paid question, and its answer is only ever as wide as the
    query that asked it. `player_hits` was recorded here as "not offered in
    any of 256 events" and therefore unmeasurable; that probe asked one
    region, both books that quote hits are in the second, and the next
    purchase came back with 16,048 hits rows over 1,218 events. The verdict
    was not wrong about what it saw. It was wrong about what it meant, and
    nothing existed to refresh it.

    The cache is the better witness and it is free. Every response ever
    bought is on disk, and its filename carries the market list that was
    requested — so "asked for and not returned" is answerable over thousands
    of events instead of hundreds, and the answer is derived from the
    evidence rather than recorded once beside it. A retention record built
    this way cannot go stale while the cache grows.

    **Only responses that requested exactly `markets` are read.** A market
    missing from a response that never asked for it is not evidence of
    anything, and counting it as absence is how a narrow query becomes a
    claim about the provider. That is what the fingerprint in the cache
    filename is for.

    **It returns one probe per cached response, and a response is not an
    event.** The four-hour and nine-and-a-half-hour purchases each priced
    nearly every event, so the real cache holds 5,432 responses over 2,723
    events, and `retention_table` used to print the first number under
    "Events probed": `player_hits` read 1,218/5,432 (22%) where it was seen in
    1,218 of 2,723 events (45%), and three events priced at two moments
    cleared an absence floor of five events. `retention_table` and
    `unmeasurable_markets` now count events (`_responses_by_event`).

    **The fingerprint carries the market list and not the regions**, so this
    cannot tell the four-hour buy's one-region responses (2,706 of them, none
    carrying hits, because neither book that quotes hits is in that region)
    from the two-region ones. Counting by event bounds the damage: a
    narrower response can add a sighting to its event and never remove one.
    It cannot help an event whose only responses asked the narrower region;
    that event still counts as probed and not seen, and the table says so.
    Putting the regions in the key would rename every file already bought,
    so a re-run over a bought window would miss the cache and pay again.

    Nothing here touches the network: no provider is constructed and no
    request is made. It reads files.
    """
    wanted = tuple(
        markets
        if markets is not None
        else (market.provider_key for market in PROP_MARKETS)
    )
    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / CACHE_DIRNAME
    if not directory.is_dir():
        return []
    fingerprint = _markets_fingerprint(wanted)
    probes: list[RetentionProbe] = []
    for path in sorted(directory.glob(f"*_{fingerprint}.json")):
        if path.name.startswith("events_"):
            continue
        payload = _read_cache(path)
        data = payload.get("data") if isinstance(payload, Mapping) else None
        event = data if isinstance(data, Mapping) else payload
        if not isinstance(event, Mapping):
            continue
        returned: set[str] = set()
        books: set[str] = set()
        for bookmaker in event.get("bookmakers", []) or []:
            if not isinstance(bookmaker, Mapping):
                continue
            books.add(str(bookmaker.get("title") or bookmaker.get("key") or ""))
            for market in bookmaker.get("markets", []) or []:
                if isinstance(market, Mapping):
                    returned.add(str(market.get("key", "")).strip())
        probes.append(
            RetentionProbe(
                event_id=str(event.get("id", "")) or path.name[:32],
                snapshot=str(
                    payload.get("timestamp", "")
                    if isinstance(payload, Mapping)
                    else ""
                ),
                markets_requested=wanted,
                markets_returned=tuple(sorted(returned & set(wanted))),
                books_returned=tuple(sorted(book for book in books if book)),
                # Already paid for. Reporting it again would double-count a
                # spend that happened once.
                credits_spent=0,
            )
        )
    return probes


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
    # The cap is checked against the pessimistic bound so a request that
    # *might* breach it is never started; spend is then accounted at the real
    # rate the headers report. The two differ on purpose.
    worst_case_per_event = estimate_credits(
        events=1, markets=len(wanted), regions=provider.region_count
    )
    buy = HistoricalBuy(events_requested=len(events))
    worst_case_spent = 0

    for entry in events:
        event_id = str(entry.get("event_id", "")).strip()
        snapshot = str(entry.get("snapshot", "")).strip()
        if not event_id or not snapshot:
            buy.errors.append(f"Skipped an event with no id or snapshot: {entry!r}")
            continue
        path = _cache_path(event_id, snapshot, raw_dir=raw_dir, markets=wanted)
        payload = _read_cache(path)
        if payload is None:
            # Two gates, because one of them has already failed in
            # production. The estimate said 70 credits an event (7 markets x
            # a "pessimistic" 10) and the provider charged 107, so a run
            # capped at 200,000 spent 289,984. Asking for seven market KEYS
            # can return more than seven BILLABLE markets — every alternate
            # ladder bills on its own — so an estimate built from the keys
            # asked for is not an upper bound at all.
            #
            # The second gate is the one that cannot be wrong: what the
            # provider says it has actually charged, read from
            # `x-requests-last` as it is spent. An estimate can be
            # mis-specified; a running total of measured spend cannot.
            if worst_case_spent + worst_case_per_event > credit_cap:
                buy.events_skipped_for_budget += 1
                continue
            if buy.credits_spent >= credit_cap:
                buy.events_skipped_for_budget += 1
                buy.errors.append(
                    f"Stopped at the {credit_cap:,}-credit cap on MEASURED "
                    f"spend ({buy.credits_spent:,} charged). The per-event "
                    "estimate was too low, which is exactly what this second "
                    "gate exists for."
                )
                break
            try:
                payload, headers = provider._get(  # noqa: SLF001
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
                # A failed request may still have cost quota, so it counts
                # against the worst case. Assuming a failure was free is how a
                # run of failures walks past its own cap.
                worst_case_spent += worst_case_per_event
                continue
            measured = _measured_cost(headers)
            worst_case_spent += worst_case_per_event
            buy.credits_spent += measured or worst_case_per_event
            buy.credits_remaining = str(
                headers.get("x-requests-remaining", "")
            ) or buy.credits_remaining
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


def _responses_by_event(
    probes: Sequence[RetentionProbe],
) -> dict[str, list[RetentionProbe]]:
    """The probes grouped by the event each one describes.

    A paid probe asks each event once, but `retention_from_cache` makes one
    probe per cached response, and the lab bought most events at two moments.
    Everything below counts these groups, never the probes: "Events probed"
    over the real cache used to read 5,432, which is the responses, over 2,723
    events.
    """
    grouped: dict[str, list[RetentionProbe]] = {}
    for probe in probes:
        grouped.setdefault(probe.event_id, []).append(probe)
    return grouped


def events_probed(probes: Sequence[RetentionProbe]) -> int:
    """How many distinct events these probes describe."""
    return len(_responses_by_event(probes))


def _retention_by_market(
    probes: Sequence[RetentionProbe],
) -> list[tuple[str, int, int]]:
    """`(market, events that asked for it, events it was seen in)`, per market.

    An event asked for a market when any of its responses requested it, and
    the market was seen in that event when any response that requested it
    came back carrying it. So a response from a narrower request -- the
    four-hour buy asked one region, and neither book that quotes hits is in
    it -- can add a sighting to its event and never subtract one.

    `retention_table` and `unmeasurable_markets` both read this, so the list
    of unmeasurable markets is exactly the set the table calls not offered.
    The list used to take its floor and its sentence from every probe,
    whatever each had asked, while the table counted per market.
    """
    requested: list[str] = []
    for probe in probes:
        for market in probe.markets_requested:
            if market not in requested:
                requested.append(market)
    by_event = _responses_by_event(probes)
    counts: list[tuple[str, int, int]] = []
    for market in requested:
        asked = 0
        seen = 0
        for responses in by_event.values():
            asking = [
                probe for probe in responses if market in probe.markets_requested
            ]
            if not asking:
                continue
            asked += 1
            if any(market in probe.markets_returned for probe in asking):
                seen += 1
        counts.append((market, asked, seen))
    return counts


def retention_table(probes: Sequence[RetentionProbe]) -> str:
    """The per-market retention table the backtest report embeds.

    Absence is only ever reported as absence once enough events have been
    looked at. Below `MINIMUM_PROBES_FOR_ABSENCE` a market that did not appear
    is "not seen in N events", which is a claim about the probe; "cannot be
    measured" is a claim about the provider, and one event cannot support it.

    Every count is of events, whatever the probes are. This table used to
    count probes under the heading "Events probed", and a cache-derived probe
    is one response: the real cache printed 5,432 for 2,723 events and
    `player_hits` as 1,218/5,432 (22%) where it was seen in 1,218 of 2,723
    events (45%), and the floor of five events could be cleared by three
    events priced at two moments.
    """
    if not probes:
        return (
            "No retention probe has been run, so which prop markets can be "
            "measured historically is **unknown**. It is not assumed to be "
            "all of them, and it is not assumed to be none."
        )
    events = events_probed(probes)
    lines = [
        "| Provider market | Events probed | Seen in | Verdict |",
        "|:----------------|--------------:|--------:|:--------|",
    ]
    for market, probed, retained in _retention_by_market(probes):
        if retained:
            verdict = f"measurable ({retained}/{probed})"
        elif probed >= MINIMUM_PROBES_FOR_ABSENCE:
            verdict = f"**not offered in any of {probed} events**"
        else:
            verdict = (
                f"not seen in {probed} event(s) — too few to call it "
                "absent"
            )
        lines.append(f"| `{market}` | {probed} | {retained} | {verdict} |")
    if len(probes) > events:
        lines.append("")
        lines.append(
            f"{len(probes)} responses were read over {events} events. An "
            "event is counted once, and is seen for a market when any of its "
            "responses carried it, so an event priced at two moments is one "
            "event rather than two. No response records which regions it "
            "asked, so an event whose only responses asked a region without "
            "the market's books still counts as probed and not seen."
        )
    if events < MINIMUM_PROBES_FOR_ABSENCE:
        lines.append("")
        lines.append(
            f"Only {events} event(s) probed. A market missing from this "
            "many is a book's night, not the provider's retention policy: a "
            "single probe once recorded `player_total_saves` as unmeasurable "
            "and the next purchase found it priced on 54 of 58 events."
        )
    return "\n".join(lines)


def unmeasurable_markets(
    probes: Sequence[RetentionProbe],
) -> dict[str, str]:
    """Markets a large enough probe never saw. Empty below the floor.

    Deliberately returns nothing when too few events were probed, so a thin
    probe cannot write "cannot be measured" into a report through this door
    either. The floor and the sentence count the events that asked for each
    market, as the table does: they used to count probes, so three events
    priced at two moments cleared a floor of five, and the sentence would
    have named twice the events it saw.
    """
    return {
        market: (
            f"Not offered on any of {probed} probed events, so it cannot "
            "be measured against real prices."
        )
        for market, probed, seen in sorted(_retention_by_market(probes))
        if not seen and probed >= MINIMUM_PROBES_FOR_ABSENCE
    }
