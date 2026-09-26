#!/usr/bin/env python3
"""Run a shadow provider fetch and write the verification reports.

A shadow run fetches real prices into `data/staging/` and reports what it
found. It allowlists nothing, promotes nothing, and places nothing. The
gameday card reads `data/staging/` — Gameday Refresh runs this script to
fetch the card's prices — and uses a market from it only if the provider
policy allowlists it, it is priced for every game in the slate, and the
oldest staged row is inside the policy's freshness limit.

    # Offline: assess whatever is already staged. Spends no credits.
    PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py

    # Live team markets only. A handful of credits.
    PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live

    # Live including props. One credit per market per region per event; the
    # cap is hard. 19 markets at the default two regions (us,us2) count 38
    # credits an event, so a cap of 190 buys five events.
    PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live \
        --props --credit-cap 190

(Until 2026-09-25 this denied that the card reads `data/staging/`, and put a
cap of 190 at ten events: one region's arithmetic, wrong since `us2` was
added on 2026-08-28.)

The credential comes from `NHL_ODDS_API_KEY` in the environment, a gitignored
`.env`, or a GitHub Secret. It is never accepted as a command argument.

Exit codes: 0, everything asked was answered (however little the books
quoted); 2, the team-market fetch failed and nothing was staged; 3, no NHL
games are on the board, which is not a fault; 4, at least one per-event
request failed, so those games' props, regulation three-way and alternate
ladders are missing — everything else was still staged and reported.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, STAGING_DIR
from nhl_betting_lab.markets import market_for_provider_key
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.odds_api import EmptySlateError
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.season import LEAGUE_TIMEZONE
from nhl_betting_lab.reports.provider_shadow import (
    build_shadow_summary,
    save_shadow_reports,
)
from nhl_betting_lab.staging_provider_policy import load_policy


#: At least one per-event request failed. Everything was still staged and
#: reported, so the card can be built from what arrived; the code exists so
#: the run cannot read as clean. Gameday Refresh turns it into a degraded
#: note, which is what summons the backup trigger.
EXIT_PER_EVENT_INCOMPLETE = 4


def _staged_prices(staging_dir: Path) -> pd.DataFrame:
    frames = []
    for name in (
        odds_api.STAGING_PRICES_FILENAME,
        odds_api.STAGING_PROPS_FILENAME,
    ):
        path = staging_dir / name
        if path.is_file():
            try:
                frames.append(pd.read_csv(path))
            except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
                continue
    if not frames:
        return pd.DataFrame(columns=list(odds_api.PRICE_COLUMNS))
    return pd.concat(frames, ignore_index=True)


def _project_markets(provider_keys: Iterable[str]) -> set[str]:
    """The project markets a list of provider market keys asks about."""
    found = set()
    for key in provider_keys:
        market = market_for_provider_key(key)
        if market is not None:
            found.add(market.key)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually fetch from the provider. Without this, nothing is spent.",
    )
    parser.add_argument(
        "--props",
        action="store_true",
        help="Include player props. One credit per market per region per event.",
    )
    # What the default buys is computed, not written. This help said "19
    # now, which is ten events at this default" until 2026-09-25: it counted
    # markets and not regions, and since `us2` was added on 2026-08-28 the
    # fetch has counted 19 x 2 = 38 credits an event, so 190 bought five.
    default_cap = 190
    asked = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    regions = odds_api.count_regions(odds_api.DEFAULT_REGIONS)
    per_event = asked * regions
    parser.add_argument(
        "--credit-cap",
        type=int,
        default=default_cap,
        help=(
            "Hard cap on per-event credits. The fetch stops rather than "
            "exceeding it, billing every asked market in every asked region "
            "whether a book quotes it or not — so the cap must be read "
            f"against markets x regions: {asked} x {regions} = {per_event} "
            f"credits an event, so the default {default_cap} buys "
            f"{default_cap // per_event} events. A starved fetch reads "
            "exactly like a market nobody quotes."
        ),
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Fetch props for at most this many events. 0 means the whole slate.",
    )
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=1,
        help=(
            "Fetch per-event markets only for games on this many NHL game "
            "dates starting today (America/New_York). 1 is today's slate — "
            "the daily default. 0 removes the window, which is what a probe "
            "wants and what once let a 32-event August board starve the "
            "day's own games."
        ),
    )
    parser.add_argument(
        "--overwrite-staging",
        action="store_true",
        help="Replace existing staging files rather than refusing.",
    )
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    # The cap governs the per-event fetch, the only one `--props` runs. A
    # dispatched "0" used to reach the provider as "no cap" (the library
    # read `if credit_cap and ...`), buying every event on the board. It is
    # refused here, before a credential is loaded or a provider is built, as
    # capture_line_movement.py and every buy_* script already did.
    if args.live and args.props and args.credit_cap <= 0:
        parser.error("--live --props requires a positive --credit-cap.")

    staging_dir = Path(args.staging_dir)
    loaded = load_provider_env()
    print(loaded.summary_line())
    for warning in loaded.warnings:
        print(f"  warning: {warning}", file=sys.stderr)

    policy = load_policy()
    print(f"Provider policy: {policy.status} ({policy.path})")
    for blocker in policy.blockers:
        print(f"  blocker: {blocker}", file=sys.stderr)

    written: list[Path] = []
    events_seen = events_priced = credits = 0
    quota = ""
    warnings: list[str] = []
    errors: list[str] = []
    per_event_failures: list[str] = []
    # The project markets this run asked the provider for. Without it both
    # reports read an unasked market as an unquoted one: the scheduled
    # discovery run (no `--props`, so the three bulk markets only) published
    # "No book returned this market" and "The provider returned no rows" for
    # nine of twelve markets it had never asked about. None offline: an
    # assessment of staged files cannot know what the run that staged them
    # asked, and says nothing either way.
    requested: set[str] | None = None

    if args.live:
        provider = odds_api.OddsApiProvider()
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # ONE window over both fetches, or none over either. The eligibility
        # gate measures coverage against the slate the staged prices
        # describe: a bulk fetch covering the whole posted board while the
        # per-event fetch covers one day would make every prop read
        # "priced for 9 of 32 games" — INCOMPLETE, excluded from the card,
        # and indistinguishable from books not posting props at all.
        league_days = None
        if args.horizon_days > 0:
            today = datetime.now(LEAGUE_TIMEZONE).date()
            league_days = [
                (today + timedelta(days=offset)).isoformat()
                for offset in range(args.horizon_days)
            ]
            print(
                "Fetch window (league dates): " + ", ".join(league_days) + "."
            )
        try:
            team = provider.fetch_team_markets(
                fetched_at=stamp,
                league_days=league_days,
                max_events=args.max_events,
            )
        except EmptySlateError as exc:
            # Exit 3 marks a state the caller should not treat as a failure.
            # The off-season lasts four months; a red run every day of it is a
            # red nobody reads in October.
            print(f"No slate: {exc}")
            return 3
        except odds_api.ProviderError as exc:
            print(f"Team-market fetch failed: {exc}", file=sys.stderr)
            return 2
        written.append(
            odds_api.write_staging(
                team.rows,
                filename=odds_api.STAGING_PRICES_FILENAME,
                staging_dir=staging_dir,
                overwrite=args.overwrite_staging,
            )
        )
        events_seen, events_priced = team.events_seen, team.events_priced
        credits += team.credits_spent
        quota = team.quota_remaining
        warnings += team.warnings
        errors += team.errors
        print(f"Team markets: {team.summary_line()}")
        # `fetch_team_markets` asks for exactly these.
        requested = _project_markets(odds_api.BULK_PROVIDER_MARKETS)

        if args.props:
            estimate = provider.estimate_prop_credits(
                events=events_seen,
                markets=list(odds_api.PER_EVENT_PROVIDER_MARKETS)
                + list(odds_api.ALTERNATE_PROVIDER_MARKETS),
            )
            print(
                f"Per-event markets would cost about {estimate} credits for "
                f"{events_seen} events; the cap is {args.credit_cap}."
            )
            # Every per-event market rides together: the props, the
            # regulation three-way (which was wired end to end and simply
            # never requested — dead code on every production path), and the
            # alternate team ladders, whose absence from a fetch is the EPL
            # `total_2_5` mistake by another door.
            per_event = list(odds_api.PER_EVENT_PROVIDER_MARKETS) + list(
                odds_api.ALTERNATE_PROVIDER_MARKETS
            )
            # The same window the bulk fetch used. The cap spends
            # front-to-back, so without it the budget buys prices for games
            # days away while starving the slate this card is actually for;
            # tomorrow's run fetches tomorrow's games at tomorrow's prices.
            props = provider.fetch_player_props(
                markets=per_event,
                max_events=args.max_events,
                credit_cap=args.credit_cap,
                fetched_at=stamp,
                league_days=league_days,
            )
            written.append(
                odds_api.write_staging(
                    props.rows,
                    filename=odds_api.STAGING_PROPS_FILENAME,
                    staging_dir=staging_dir,
                    overwrite=args.overwrite_staging,
                )
            )
            requested |= _project_markets(per_event)
            credits += props.credits_spent
            quota = props.quota_remaining or quota
            warnings += props.warnings
            errors += props.errors
            # "Per-event", not "Props": this fetch also carries the
            # regulation three-way and the alternate team ladders, and in
            # August it can return plenty of rows while containing zero
            # player props — a label that says otherwise sends whoever reads
            # the log hunting for a prop-pricing bug that does not exist.
            print(f"Per-event markets: {props.summary_line()}")
            # Keyed on the errors, not on the rows: a fetch whose requests
            # were all answered and in which no book quoted a prop is an
            # absence and exits 0, and a budget skip is a stated warning.
            #
            # This used to be recorded in the provenance and nowhere else,
            # and the script returned 0. Gameday Refresh reads only the exit,
            # so a run in which every per-event request answered HTTP 503
            # was a clean run: the failure-shape audit replayed 3 games at 2
            # books with 3 of 3 per-event calls failing (503, 429 or a
            # timeout alike) and got exit 0, a 0-row props file, a card
            # excluding all nine per-event markets as "The provider returned
            # no rows", a 36-row snapshot holding no prop, and
            # `degraded=false`, so the backup trigger stood down. One of
            # three failing gave exit 0 too, with every per-event market
            # INCOMPLETE — a card with no prop on it.
            per_event_failures = list(props.errors)
            if per_event_failures:
                print(
                    f"{len(per_event_failures)} per-event request(s) failed, "
                    "so those games' props, regulation three-way and "
                    "alternate ladders are missing — absent, not unquoted. "
                    "Everything else is still staged and reported; this run "
                    f"exits {EXIT_PER_EVENT_INCOMPLETE}.",
                    file=sys.stderr,
                )
                for failure in per_event_failures:
                    print(f"  {failure}", file=sys.stderr)

        odds_api.write_provenance(
            odds_api.FetchResult(
                fetched_at=stamp,
                events_seen=events_seen,
                events_priced=events_priced,
                credits_spent=credits,
                quota_remaining=quota,
                warnings=warnings,
                errors=errors,
            ),
            configuration=provider.public_configuration(),
            staging_files=written,
            staging_dir=staging_dir,
        )
    else:
        print("Offline: assessing whatever is already staged. No credits spent.")

    prices = _staged_prices(staging_dir)
    summary, eligibility, discovery = build_shadow_summary(
        prices,
        policy=policy,
        provider_name=odds_api.PROVIDER_NAME,
        events_seen=events_seen,
        events_priced=events_priced,
        credits_spent=credits,
        quota_remaining=quota,
        warnings=warnings,
        errors=errors,
        staging_files=written,
        requested_markets=requested,
    )
    paths = save_shadow_reports(
        summary, eligibility, discovery, output_dir=Path(args.output_dir)
    )
    print(eligibility.summary_line())
    print(discovery.summary_line())
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print(
        "Shadow run only. Nothing was allowlisted, no staging was promoted, "
        "no bet was placed, and no credential was written."
    )
    # Last, so a failed per-event request never costs the staging files,
    # the provenance or the reports the card is still built from.
    if per_event_failures:
        return EXIT_PER_EVENT_INCOMPLETE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
