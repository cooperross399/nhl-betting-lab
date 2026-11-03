#!/usr/bin/env python3
"""Which books, in which provider regions, quote NHL hits right now? Capped.

From the 2026-10-27 morning card onward every card's "Excluded markets" read
"`hits`: The provider returned no rows for this market." Every hits price the
card carried from 2026-10-13 to 2026-10-26 came from one book, theScore Bet,
in the `us,us2` regions the lab asks. Cooper asked (2026-11-03) for another
source of hits prices that needs no new account. The only account the lab
holds is this provider, so the first place to look is the regions it has
never asked for hits: `us_dfs`, `us_ex`, `eu`, `uk`, `au`.

This asks ONE upcoming event, one region and one market per request, so a
region or market name the provider refuses (a 422) cannot hide the others.
It records which books answered and how many outcomes each carried. It
records **no price**: the report says who quotes hits, never what they quote.

**This spends credits.** Nothing is asked without `--live`, `--credit-cap`
is mandatory, and the cap is enforced against the measured running total
read from `x-requests-last` before every request. The live per-event
endpoint bills one credit per market returned per region, so a region that
quotes no hits costs nothing to ask.

    # Free: print the plan and its worst case.
    PYTHONPATH=src .venv/bin/python scripts/probe_hits_sources.py --credit-cap 20

    # Ask.
    PYTHONPATH=src .venv/bin/python scripts/probe_hits_sources.py --live --credit-cap 20

It places no bet, edits no policy, writes no receipt and adds no market to the allowlist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.providers.env_file import load_provider_env, redact
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError

DEFAULT_REGIONS = "us,us2,us_dfs,us_ex,eu,uk,au"
DEFAULT_MARKETS = "player_hits,player_hits_alternate"
REPORT_NAME = "hits_source_probe"


def _parse_start(text: object) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def pick_events(
    events: list[Mapping[str, Any]], *, now: datetime, count: int
) -> list[Mapping[str, Any]]:
    """The next `count` events that have not started, soonest first."""
    upcoming = []
    for event in events:
        start = _parse_start(event.get("commence_time"))
        if start is not None and start > now and event.get("id"):
            upcoming.append((start, event))
    upcoming.sort(key=lambda pair: pair[0])
    return [event for _, event in upcoming[:count]]


def books_quoting(payload: Any, market: str) -> dict[str, int]:
    """Book title -> number of outcomes it carried for `market`. No prices."""
    found: dict[str, int] = {}
    if not isinstance(payload, Mapping):
        return found
    for book in payload.get("bookmakers") or []:
        if not isinstance(book, Mapping):
            continue
        title = str(book.get("title") or book.get("key") or "unknown")
        for entry in book.get("markets") or []:
            if isinstance(entry, Mapping) and entry.get("key") == market:
                outcomes = entry.get("outcomes") or []
                found[title] = found.get(title, 0) + len(outcomes)
    return found


def render(result: Mapping[str, Any]) -> str:
    lines = [
        "# Who quotes NHL hits",
        "",
        f"- Generated: {result['generated_at']}",
        f"- Events asked: {len(result['events'])}",
        f"- Credits spent: {result['credits_spent']} (cap {result['credit_cap']})",
        "- No price is recorded here: only which books answered.",
        "",
        "| Event | Region | Market | Outcome | Books (outcomes) |",
        "|:--|:--|:--|:--|:--|",
    ]
    for row in result["asks"]:
        books = ", ".join(f"{name} ({n})" for name, n in sorted(row["books"].items()))
        lines.append(
            f"| {row['event']} | `{row['region']}` | `{row['market']}` | "
            f"{row['outcome']} | {books or '-'} |"
        )
    quoting = sorted({name for row in result["asks"] for name in row["books"]})
    lines += ["", "Books quoting hits: " + (", ".join(quoting) if quoting else "none"), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credit-cap", type=int, required=True)
    parser.add_argument("--regions", default=DEFAULT_REGIONS)
    parser.add_argument("--markets", default=DEFAULT_MARKETS)
    parser.add_argument("--events", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR)
    args = parser.parse_args(argv)

    if args.credit_cap <= 0:
        parser.error("--credit-cap must be a positive number of credits.")
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    worst = len(regions) * len(markets) * max(1, args.events)
    print(
        f"Plan: {args.events} event(s) x {len(regions)} region(s) x "
        f"{len(markets)} market(s), one request each; worst case {worst} "
        f"credits, cap {args.credit_cap}."
    )
    if not args.live:
        print("Not asked: pass --live to spend credits.")
        return 0

    load_provider_env()
    now = datetime.now(timezone.utc)
    spent = 0
    asks: list[dict[str, Any]] = []
    try:
        lister = OddsApiProvider()
        events = pick_events(lister.list_events(), now=now, count=max(1, args.events))
    except ProviderError as exc:
        print(redact(f"::error::The events listing failed: {exc}"))
        return 2
    if not events:
        print("No upcoming event is listed; nothing asked.")
        return 3

    for event in events:
        label = f"{event.get('away_team')} @ {event.get('home_team')}"
        for region in regions:
            for market in markets:
                if spent + 1 > args.credit_cap:
                    asks.append({"event": label, "region": region, "market": market,
                                 "outcome": "not asked (cap)", "books": {}})
                    continue
                try:
                    provider = OddsApiProvider(regions=region)
                    payload, headers = provider._get(  # noqa: SLF001 — one adapter
                        f"{provider.base_url}/v4/sports/{provider.sport_key}"
                        f"/events/{event['id']}/odds",
                        provider._params(regions=region, markets=market),  # noqa: SLF001
                    )
                except ProviderError as exc:
                    status = getattr(exc, "status", None)
                    outcome = (
                        "refused (422: not a market or region here)"
                        if status == 422 else f"failed ({status or 'unreachable'})"
                    )
                    asks.append({"event": label, "region": region, "market": market,
                                 "outcome": outcome, "books": {}})
                    continue
                try:
                    spent += int(float(headers.get("x-requests-last", "0") or 0))
                except ValueError:
                    spent += 1
                books = books_quoting(payload, market)
                asks.append({"event": label, "region": region, "market": market,
                             "outcome": "answered", "books": books})

    result = {
        "generated_at": now.isoformat(timespec="seconds"),
        "credit_cap": args.credit_cap,
        "credits_spent": spent,
        "events": [f"{e.get('away_team')} @ {e.get('home_team')}" for e in events],
        "asks": asks,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{REPORT_NAME}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    report = render(result)
    (args.output_dir / f"{REPORT_NAME}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
