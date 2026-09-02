#!/usr/bin/env python3
"""Do the low-vig venues quote NHL player props at all? One event, capped.

The props model finishes 0.29 points short of break-even while recovering
about 2.4 of the 2.7 points of margin it pays. The last untested route to
closing that gap is not a better forecast — thirteen inputs and nine feature
families have failed to produce one — but a smaller toll: a venue charging
less than the 6.27% DraftKings takes on a two-sided prop. Pinnacle, the US
exchanges (Novig, ProphetX) and Betfair are the candidates, and every one of
them sits outside the `us,us2` region string this lab has always asked for.

The provider documents player props as "mainly limited to US bookmakers",
and the one reduced-juice operator already inside `us` (LowVig.ag) quotes
NHL moneylines and totals and **no props at all**. That is the pattern this
probe exists to confirm or refute for the venues that matter: a venue that
lists the moneyline but not the props cannot carry a props model, and that
is the decisive negative.

**This spends credits.** It does nothing without `--live`, it takes a
mandatory `--credit-cap`, and the cap is enforced against the **measured**
running total read from `x-requests-last` before every request. The
historical per-event endpoint bills `10 x markets returned x regions`, so a
venue that returns no props costs nothing to ask — the negative answer is
nearly free, and the positive one is bounded by the cap.

    # Free: print what would be asked, and its worst case, and stop.
    PYTHONPATH=src .venv/bin/python scripts/probe_low_vig_venues.py

    # One event, one snapshot, per region, capped.
    PYTHONPATH=src .venv/bin/python scripts/probe_low_vig_venues.py \\
        --live --credit-cap 400

The event is one the 14-book store already holds at the same snapshot, so
when the raw cache is on disk the margins are compared like with like. It
never prints, writes, compares, or transmits the credential.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from nhl_betting_lab.config import OUTPUTS_DIR, RAW_DIR
from nhl_betting_lab.markets import PROP_MARKETS
from nhl_betting_lab.models.value import american_to_implied
from nhl_betting_lab.providers.env_file import load_provider_env, redact
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


#: Anaheim @ Washington, face-off 2025-01-15T00:10Z, priced four hours out.
#: Already in the store at this exact snapshot, which is what makes the
#: margin comparison like with like rather than venue-versus-moment.
PROBE_EVENT_ID = "534946a43ead305dc7d5f9fa6916984b"
PROBE_SNAPSHOT = "2025-01-14T20:10:00Z"

#: The provider's own region keys for the venues in question. `us_ex` is
#: the US exchanges; Pinnacle is served in `eu` only.
DEFAULT_REGIONS = "us_ex,eu,uk,au"

#: A `bookmakers=` request names venues directly and bills every ten of them
#: as one region-equivalent. Nine here, so one.
TARGET_BOOKS = (
    "pinnacle,novig,prophetx,betfair_ex_eu,betfair_ex_uk,"
    "lowvig,betonlineag,matchbook,smarkets"
)
TARGET_VENUES = tuple(TARGET_BOOKS.split(","))

#: The documented per-event historical rate, per market returned, per region.
CREDITS_PER_MARKET_PER_REGION = 10

JSON_FILENAME = "low_vig_venue_probe.json"
MARKDOWN_FILENAME = "low_vig_venue_probe.md"
CACHE_DIRNAME = "venue_probe"


def _prop_keys() -> tuple[str, ...]:
    return tuple(market.provider_key for market in PROP_MARKETS)


def _measured_cost(headers: Mapping[str, str]) -> int:
    try:
        return int(str(headers.get("x-requests-last", "")).strip())
    except ValueError:
        return 0


def _remaining(headers: Mapping[str, str]) -> str:
    return str(headers.get("x-requests-remaining", "")).strip() or "unknown"


def _event_of(payload: Any) -> dict[str, Any]:
    """The historical endpoint wraps the event in `data`; the live one
    does not. Accept both so a cached live response reads the same way."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload if isinstance(payload, dict) else {}


def margins_by_book(payload: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """Per book, per market: how many two-sided quotes, and their median
    two-sided margin. A one-sided quote cannot be devigged and is not
    counted; a venue quoting only overs has not priced the market."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for book in _event_of(payload).get("bookmakers", []) or []:
        key = str(book.get("key", "")).strip()
        if not key:
            continue
        markets: dict[str, dict[str, Any]] = {}
        for market in book.get("markets", []) or []:
            sides: dict[tuple[str, Any], dict[str, Any]] = {}
            for outcome in market.get("outcomes", []) or []:
                ident = (str(outcome.get("description", "")), outcome.get("point"))
                sides.setdefault(ident, {})[str(outcome.get("name", ""))] = outcome.get("price")
            two_sided = [
                american_to_implied(s["Over"]) + american_to_implied(s["Under"]) - 1.0
                for s in sides.values()
                if s.get("Over") is not None and s.get("Under") is not None
            ]
            markets[str(market.get("key", ""))] = {
                "n_two_sided": len(two_sided),
                "median_margin": round(median(two_sided), 4) if two_sided else None,
            }
        out[key] = markets
    return out


def _reference_from_cache(raw_dir: Path) -> dict[str, Any]:
    """The 14-book store's own quotes on this event and snapshot, if the raw
    cache is on disk. Absent in CI, where the cache is an artifact rather
    than a checkout; the comparison is then done locally afterwards."""
    compact = PROBE_SNAPSHOT.replace("-", "").replace(":", "")
    matches = sorted((raw_dir / "historical_props").glob(f"{PROBE_EVENT_ID}_{compact}*.json"))
    if not matches:
        return {"available": False, "books": {}}
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"available": False, "books": {}}
    return {"available": True, "source": matches[0].name, "books": margins_by_book(payload)}


def _plan(regions: list[str], prop_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    worst_props = CREDITS_PER_MARKET_PER_REGION * len(prop_keys)
    plan: list[dict[str, Any]] = []
    for region in regions:
        plan.append({"step": f"props@{region}", "regions": region, "markets": prop_keys, "worst_case": worst_props})
        plan.append({"step": f"h2h@{region}", "regions": region, "markets": ("h2h",), "worst_case": CREDITS_PER_MARKET_PER_REGION})
    plan.append({"step": "props@bookmakers", "bookmakers": TARGET_BOOKS, "markets": prop_keys, "worst_case": worst_props})
    return plan


def _verdict(venues: dict[str, dict[str, Any]], reference: dict[str, Any]) -> str:
    quoting = {v: d for v, d in venues.items() if d["prop_markets"]}
    if not quoting:
        return (
            "No target venue returned a single NHL player-prop market on this "
            "event. The venue route cannot carry the props model: a book "
            "that lists the moneyline and not the props offers nothing for a "
            "props opinion to be placed against."
        )
    lines = []
    ref_best = None
    if reference.get("available"):
        margins = [
            m["median_margin"]
            for b in reference["books"].values()
            for m in b.values()
            if m.get("median_margin") is not None
        ]
        ref_best = min(margins) if margins else None
    for venue, detail in quoting.items():
        margins = [m["median_margin"] for m in detail["prop_markets"].values() if m.get("median_margin") is not None]
        if not margins:
            continue
        own = median(margins)
        note = f"{venue}: props quoted, median two-sided margin {own:.2%}"
        if ref_best is not None:
            note += f" against the store's best {ref_best:.2%} on the same event ({own - ref_best:+.2%} points)"
        lines.append(note)
    return " ".join(lines) if lines else "Props were returned but none were two-sided; nothing can be devigged."


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Low-vig venue probe",
        "",
        f"Event `{result['event_id']}` at `{result['snapshot']}`. "
        f"Spent **{result['spent']}** of a **{result['credit_cap']}** credit cap; "
        f"quota {result['quota_remaining_before']} before, {result['quota_remaining_after']} after.",
        "",
        f"**{result['verdict']}**",
        "",
        "| Venue | Seen in | h2h | Prop markets | Median margin |",
        "|---|---|---|---|---|",
    ]
    for venue in TARGET_VENUES:
        d = result["venues"].get(venue, {"seen_in": [], "h2h": False, "prop_markets": {}})
        margins = [m["median_margin"] for m in d["prop_markets"].values() if m.get("median_margin") is not None]
        med = f"{median(margins):.2%}" if margins else "—"
        lines.append(
            f"| {venue} | {', '.join(d['seen_in']) or '—'} | {'yes' if d['h2h'] else 'no'} "
            f"| {len(d['prop_markets'])} | {med} |"
        )
    lines += ["", "## Calls", "", "| Step | Cost | Books | Markets | Note |", "|---|---|---|---|---|"]
    for c in result["calls"]:
        note = c.get("skipped") or c.get("error") or ""
        lines.append(
            f"| {c['step']} | {c.get('measured_cost', '—')} | {len(c.get('books_returned', []))} "
            f"| {len(c.get('markets_returned', []))} | {note} |"
        )
    ref = result["reference"]
    lines += ["", "## Reference: the store's own books on this event", ""]
    if ref.get("available"):
        lines += ["| Book | Prop markets | Median margin |", "|---|---|---|"]
        for book, markets in sorted(ref["books"].items()):
            margins = [m["median_margin"] for m in markets.values() if m.get("median_margin") is not None]
            lines.append(f"| {book} | {len(markets)} | {median(margins):.2%} |" if margins else f"| {book} | {len(markets)} | — |")
    else:
        lines.append("The raw cache for this event is not on disk here, so the like-for-like comparison is done locally from the artifact.")
    lines += ["", "This probe placed no bet, edited no policy, and allowlisted no venue.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, provider: OddsApiProvider | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Actually spend credits. Requires --credit-cap.")
    parser.add_argument("--credit-cap", type=int, default=0, help="Hard cap, enforced against measured spend before every request.")
    parser.add_argument("--regions", default=DEFAULT_REGIONS, help="Comma-separated provider regions to try, one call each.")
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)
    if args.live and args.credit_cap <= 0:
        parser.error("--live needs a positive --credit-cap.")

    regions = [r.strip() for r in str(args.regions).split(",") if r.strip()]
    prop_keys = _prop_keys()
    plan = _plan(regions, prop_keys)
    worst_total = sum(int(p["worst_case"]) for p in plan)

    if not args.live:
        print(f"Dry run. {len(plan)} call(s) planned on event {PROBE_EVENT_ID} at {PROBE_SNAPSHOT}:")
        for p in plan:
            where = p.get("regions") or f"bookmakers={p['bookmakers']}"
            print(f"  {p['step']:<18} {where:<60} worst case {p['worst_case']:>4}")
        print(f"Worst case in total: {worst_total} credits. A venue returning nothing bills nothing.")
        print("Nothing was sent and no credit was spent. Re-run with --live and a --credit-cap to ask.")
        return 0

    load_provider_env()
    provider = provider or OddsApiProvider()
    if not provider.api_key:
        print("No NHL_ODDS_API_KEY is configured. Nothing was sent.", file=sys.stderr)
        return 2

    raw_dir = Path(args.raw_dir)
    cache_dir = raw_dir / "historical_props" / CACHE_DIRNAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    spent = 0
    calls: list[dict[str, Any]] = []

    # The listing is documented as free and carries the quota headers.
    try:
        _, headers = provider._get(f"{provider.base_url}/v4/sports", provider._params())  # noqa: SLF001 — one door
    except ProviderError as exc:
        print(redact(f"Could not reach the provider: {exc}"), file=sys.stderr)
        return 3
    before = _remaining(headers)
    after = before
    if before.isdigit() and int(before) < args.credit_cap:
        print(f"Only {before} credits remain, below the {args.credit_cap} cap. Nothing was asked.", file=sys.stderr)
        return 3

    url = f"{provider.base_url}/v4/historical/sports/{provider.sport_key}/events/{PROBE_EVENT_ID}/odds"
    responses: dict[str, Any] = {}
    for p in plan:
        record: dict[str, Any] = {"step": p["step"]}
        if spent + int(p["worst_case"]) > args.credit_cap:
            record["skipped"] = f"would breach the cap ({spent} spent + {p['worst_case']} worst case > {args.credit_cap})"
            calls.append(record)
            continue
        extra: dict[str, str] = {"markets": ",".join(p["markets"]), "date": PROBE_SNAPSHOT}
        if p.get("regions"):
            extra["regions"] = str(p["regions"])
        else:
            extra["bookmakers"] = str(p["bookmakers"])
        try:
            payload, headers = provider._get(url, provider._params(**extra))  # noqa: SLF001
        except ProviderError as exc:
            record["error"] = redact(str(exc))
            calls.append(record)
            continue
        cost = _measured_cost(headers)
        spent += cost
        after = _remaining(headers)
        record["measured_cost"] = cost
        event = _event_of(payload)
        record["books_returned"] = sorted(str(b.get("key", "")) for b in event.get("bookmakers", []) or [])
        record["markets_returned"] = sorted({str(m.get("key", "")) for b in event.get("bookmakers", []) or [] for m in b.get("markets", []) or []})
        calls.append(record)
        responses[p["step"]] = payload
        (cache_dir / f"{p['step'].replace('@', '_')}.json").write_text(
            redact(json.dumps(payload, indent=2, sort_keys=True)), encoding="utf-8"
        )

    venues: dict[str, dict[str, Any]] = {v: {"seen_in": [], "h2h": False, "prop_markets": {}} for v in TARGET_VENUES}
    for step, payload in responses.items():
        for book, markets in margins_by_book(payload).items():
            if book not in venues:
                venues[book] = {"seen_in": [], "h2h": False, "prop_markets": {}}
            if step not in venues[book]["seen_in"]:
                venues[book]["seen_in"].append(step)
            if "h2h" in markets:
                venues[book]["h2h"] = True
            for key, detail in markets.items():
                if key in prop_keys:
                    venues[book]["prop_markets"][key] = detail

    reference = _reference_from_cache(raw_dir)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event_id": PROBE_EVENT_ID,
        "snapshot": PROBE_SNAPSHOT,
        "regions": regions,
        "markets_asked": prop_keys,
        "credit_cap": args.credit_cap,
        "spent": spent,
        "quota_remaining_before": before,
        "quota_remaining_after": after,
        "calls": calls,
        "venues": venues,
        "reference": reference,
    }
    result["verdict"] = _verdict(venues, reference)

    outputs = Path(args.output_dir)
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / JSON_FILENAME).write_text(redact(json.dumps(result, indent=2, sort_keys=True, default=str)) + "\n", encoding="utf-8")
    (outputs / MARKDOWN_FILENAME).write_text(redact(render(result)), encoding="utf-8")
    print(redact(result["verdict"]))
    print(f"Measured spend this run: {spent} credit(s) against a cap of {args.credit_cap}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
