#!/usr/bin/env python3
"""Find out which NHL markets the provider actually serves, one at a time.

Guessing a market list is how every team-market fetch in this repository
failed for a week: `alternate_spreads` is real, is documented, and is not
served on the bulk endpoint, and asking for it there makes the provider refuse
the whole request with a 422 that names nothing.

So this probes each candidate **individually**. A market that answers is
served; a market that 422s is not; and because each request is separate, one
bad name cannot hide the others.

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
    spent = 0

    for market in CANDIDATE_MARKETS:
        if args.credit_cap and spent >= args.credit_cap:
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
            refused.append(market)
            print(f"  {market:<34} not served ({exc})"[:110])
            continue
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
    if unmapped:
        print(f"Served but this lab does not price: {', '.join(unmapped)}")
    print(f"Written to {directory / DISCOVERY_FILENAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
