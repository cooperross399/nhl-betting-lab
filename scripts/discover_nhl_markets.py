#!/usr/bin/env python3
"""Find out which NHL markets the provider actually serves, one at a time.

Guessing a market list is how every team-market fetch in this repository
failed for a week: `alternate_spreads` is real, is documented, and is not
served on the bulk endpoint, and asking for it there makes the provider refuse
the whole request with a 422 that names nothing.

So this probes each candidate **individually**. A market that answers is
served; a market that 422s is not; and because each request is separate, one
bad name cannot hide the others.

A request that fails any other way is **no verdict at all**. A 503, a 500, a
timeout, unreadable JSON, a 401 (the key refused or the credits spent) or a
429 (rate limited) says the provider did not answer, not that the market does
not exist; those markets are listed under `not_answered`. A 401 or a 429
stops the probe, since every request after it would fail the same way, and
the markets it never asked are listed under `not_asked`, as are those a
credit-cap stop leaves. And a 422 is only believed once `h2h` — the one
market every sport serves, asked first — has answered on the same event:
before that, a 422 cannot be told from the provider refusing the request
itself (the event, the regions).

Exit codes: 0 when every candidate got a verdict (served, valid but
unpriced, or not a market); 2 when the events list failed; 3 when no event
is on the board; 4 when the record was written but some candidate has no
verdict, so a continue-on-error step reads `failure` rather than a complete
probe.

    PYTHONPATH=src .venv/bin/python scripts/discover_nhl_markets.py --live \
        --credit-cap 120

Cost: one credit per market that returns data, zero for one that does not.
Roughly thirty candidates, so well under a hundred credits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.markets import ALL_MARKETS
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


DISCOVERY_FILENAME = "nhl_market_discovery.json"

#: Every NHL market worth asking about. Drawn from the provider's own
#: documentation plus the shapes it uses for other sports, because a market
#: that exists and is undocumented costs one credit to find and nothing to
#: ask about.
CANDIDATE_MARKETS: tuple[str, ...] = (
    # Team markets, bulk endpoint.
    "h2h", "spreads", "totals", "outrights",
    "h2h_3_way", "team_totals", "alternate_team_totals",
    # Team markets, per-event ladders and periods.
    "alternate_spreads", "alternate_totals",
    "h2h_p1", "spreads_p1", "totals_p1",
    "h2h_p2", "spreads_p2", "totals_p2",
    "h2h_p3", "spreads_p3", "totals_p3",
    "h2h_3_way_p1", "totals_3_way",
    # Player props.
    "player_points", "player_goals", "player_assists",
    "player_shots_on_goal", "player_blocked_shots", "player_total_saves",
    "player_power_play_points", "player_hits", "player_penalty_minutes",
    "player_faceoffs_won", "player_time_on_ice", "player_giveaways",
    "player_takeaways", "player_shots", "player_goal_scorer_first",
    "player_goal_scorer_last", "player_goal_scorer_anytime",
    "player_points_alternate", "player_assists_alternate",
    "player_shots_on_goal_alternate", "player_blocked_shots_alternate",
    "player_total_saves_alternate", "player_goals_alternate",
)

#: The one market every sport serves, and the first one asked. Until it has
#: answered on this event, a 422 is the provider refusing the request (a
#: dead event, a bad regions list), not a verdict on the market asked about —
#: the same control `OddsApiProvider.fetch_team_markets` uses to tell a
#: refused market list from an empty board.
CONTROL_MARKET = "h2h"

#: Statuses that every later request in a back-to-back probe would meet too.
#: The probe stops on one, so the rest are recorded as not asked rather than
#: failed one by one — and, before 2026-09-26, written off one by one.
STOP_STATUSES: dict[int, str] = {
    401: "the key was refused or the credits are spent",
    429: "the provider is rate-limiting",
}

#: The record was written, but at least one candidate has no verdict.
EXIT_PROBE_INCOMPLETE = 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credit-cap", type=int, default=0)
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error("--live requires a positive --credit-cap.")
    print(
        f"{len(CANDIDATE_MARKETS)} candidate markets. A market that returns "
        "data costs one credit; one that does not costs nothing."
    )
    if not args.live:
        print("Dry run: nothing was asked and no credit was spent.")
        return 0

    load_provider_env()
    provider = OddsApiProvider()
    try:
        events = provider.list_events()
    except ProviderError as exc:
        print(f"Could not list events: {exc}", file=sys.stderr)
        return 2
    if not events:
        print("No NHL events are on the board, so nothing can be probed.")
        return 3
    event_id = str(events[0].get("id", ""))
    print(f"Probing event {event_id} ({len(events)} on the board).")

    served: dict[str, dict[str, object]] = {}
    refused: list[str] = []
    unpriced: list[str] = []
    # Asked, and the provider did not answer: no verdict on the market.
    not_answered: dict[str, str] = {}
    # Never asked, because the probe stopped first.
    not_asked: list[str] = []
    stopped_because: str | None = None
    control_answered = False
    spent = 0

    for index, market in enumerate(CANDIDATE_MARKETS):
        if args.credit_cap and spent >= args.credit_cap:
            stopped_because = f"the {args.credit_cap}-credit cap was reached"
            not_asked = list(CANDIDATE_MARKETS[index:])
            print(f"Stopping at the {args.credit_cap}-credit cap.")
            break
        try:
            payload, headers = provider._get(  # noqa: SLF001 — one door
                f"{provider.base_url}/v4/sports/{provider.sport_key}/events/"
                f"{event_id}/odds",
                provider._params(  # noqa: SLF001
                    regions=provider.regions, markets=market
                ),
            )
        except ProviderError as exc:
            # This used to put EVERY failure here in `not_a_market`. Replayed
            # with only the transport stubbed, a 503, a 429, a 500 and a read
            # timeout on four live markets beside one genuine 422 read "38
            # priced now, 0 valid but unpriced, 5 not a market at all" and
            # exited 0; a 401 from the 21st request wrote off all 23 player
            # markets; an account out of credits wrote off all 43, h2h
            # included. Only a 422 is the provider saying "no such market",
            # and only once the control has shown the request itself is good.
            if exc.status == 422 and control_answered:
                refused.append(market)
                print(f"  {market:<34} not a market (HTTP 422)")
                continue
            reason = " ".join(str(exc).split())
            if exc.status == 422 and market == CONTROL_MARKET:
                reason += (
                    f" {CONTROL_MARKET} is the one market every sport serves, "
                    "so this is the provider refusing the request, not the "
                    "market."
                )
            elif exc.status == 422:
                reason += (
                    f" But {CONTROL_MARKET}, the one market every sport "
                    "serves, had not answered on this event, so this 422 "
                    "cannot be told from the request itself being refused."
                )
            not_answered[market] = reason
            print(f"  {market:<34} NO ANSWER, no verdict ({reason})"[:110])
            if exc.status in STOP_STATUSES:
                stopped_because = (
                    f"the provider answered HTTP {exc.status} to {market} "
                    f"({STOP_STATUSES[exc.status]}), so the probe stopped "
                    "asking"
                )
                not_asked = list(CANDIDATE_MARKETS[index + 1:])
                print(f"Stopping: {stopped_because}.")
                break
            continue
        if market == CONTROL_MARKET:
            control_answered = True
        try:
            cost = int(str(headers.get("x-requests-last", "0")).strip() or 0)
        except ValueError:
            cost = 0
        spent += cost
        books: set[str] = set()
        outcomes = 0
        lines: set[float] = set()
        for book in (payload.get("bookmakers") or []):
            for entry in book.get("markets") or []:
                if str(entry.get("key")) != market:
                    continue
                books.add(str(book.get("title") or book.get("key")))
                for outcome in entry.get("outcomes") or []:
                    outcomes += 1
                    point = outcome.get("point")
                    if point is not None:
                        try:
                            lines.add(float(point))
                        except (TypeError, ValueError):
                            pass
        if not books:
            # Valid name, nobody pricing it right now. That is a different
            # fact from "this market does not exist", and conflating them is
            # how a market gets written off in August for being out of season.
            unpriced.append(market)
            print(f"  {market:<34} valid, not priced on this event")
            continue
        served[market] = {
            "books": sorted(books),
            "outcomes": outcomes,
            "lines": sorted(lines),
            "credits": cost,
        }
        print(
            f"  {market:<34} SERVED  {len(books)} book(s), {outcomes} outcomes"
            + (f", lines {min(lines):g}-{max(lines):g}" if lines else "")
        )

    known = {m.provider_key for m in ALL_MARKETS}
    # A market this lab does not price is worth naming whether or not a book
    # happened to quote it today: the question is what the provider serves,
    # not what was on the board this afternoon.
    unmapped = sorted((set(served) | set(unpriced)) - known)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / DISCOVERY_FILENAME).write_text(
        json.dumps(
            {
                "event_id": event_id,
                "credits_spent": spent,
                "served_and_priced": served,
                "valid_but_unpriced": unpriced,
                "not_a_market": refused,
                "served_but_unmapped": unmapped,
                "not_answered": not_answered,
                "not_asked": not_asked,
                "stopped_because": stopped_because,
                "probe_complete": not (not_answered or not_asked),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"\n{len(served)} priced now, {len(unpriced)} valid but unpriced, "
        f"{len(refused)} not a market at all. {spent} credits spent."
    )
    if not_answered:
        print(
            f"{len(not_answered)} asked and not answered: the request failed, "
            "which says nothing about whether the market exists: "
            f"{', '.join(not_answered)}"
        )
    if not_asked:
        print(
            f"{len(not_asked)} not asked, because {stopped_because}: "
            f"{', '.join(not_asked)}"
        )
    if unmapped:
        print(f"Served but this lab does not price: {', '.join(unmapped)}")
    print(f"Written to {directory / DISCOVERY_FILENAME}.")
    if not_answered or not_asked:
        print(
            f"The probe is incomplete: {len(not_answered) + len(not_asked)} of "
            f"{len(CANDIDATE_MARKETS)} candidate markets have no verdict. "
            f"Exit {EXIT_PROBE_INCOMPLETE}.",
            file=sys.stderr,
        )
        return EXIT_PROBE_INCOMPLETE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
