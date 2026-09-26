#!/usr/bin/env python3
"""Run a shadow provider fetch and write the verification reports.

A shadow run fetches real prices into `data/staging/` and reports what it
found. It adds no allowlist entry, promotes nothing, and places nothing. The
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
quoted); 2, the team-market fetch failed and nothing was staged, which
includes a refused market list whose moneyline check failed, and "no NHL odds
at all" on a day the cached NHL schedule lists a regular-season game; 3, no
NHL games are on the board, which is not a fault; 4, at least one per-event
request failed, or the free events list they start from did, so those games'
props, regulation three-way and alternate ladders are missing — everything
else was still staged and reported. (Until 2026-09-26 a failed events list
escaped as a traceback and exit 1, after the team file was staged and before
the provenance and the reports were written.)
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
from nhl_betting_lab.season import LEAGUE_TIMEZONE, scheduled_regular_season_starts
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


def _scheduled_regular_season_games(days: Iterable[str]) -> int:
    """Regular-season games the cached NHL club schedules list on `days`.

    Games the schedule calls off are not counted, and neither are
    exhibitions, which books may never price. With no cache there is
    nothing to count, and the answer is 0.
    """
    wanted = set(days)
    return sum(
        1 for day, _home, _away in scheduled_regular_season_starts()
        if day in wanted
    )


def _project_markets(provider_keys: Iterable[str]) -> set[str]:
    """The project markets a list of provider market keys asks about."""
    found = set()
    for key in provider_keys:
        market = market_for_provider_key(key)
        if market is not None:
            found.add(market.key)
    return found


def _listing_failed(
    staged_rows: Iterable[dict],
    markets: Iterable[str],
    exc: Exception,
    *,
    fetched_at: str,
) -> odds_api.FetchResult:
    """The per-event fetch's result when the events list it starts from failed.

    No per-event request was made, so every game the bulk fetch staged is
    missing everything only the per-event request asks for. That is one
    failure (one line in `errors`) that left every staged game unanswered
    (one `failed_events` entry each), recorded in the shape
    `fetch_player_props` gives a failed per-event request. The games come
    from the staged team rows because they are the only list this run has,
    and the eligibility gate keys a failure to its game through the
    `provider_event_id` those rows carry. A game in the window that the
    bulk fetch returned with no usable price has no row, and so no entry.

    The error drops "No staging file was written.", which `_get` ends every
    failure with and which is false here: the team file is already staged.
    """
    cause = " ".join(str(exc).replace(odds_api.NO_STAGING_WRITTEN, "").split())
    games: dict[str, dict] = {}
    for row in staged_rows:
        event_id = str(row.get("provider_event_id", "") or "").strip()
        if event_id and event_id not in games:
            games[event_id] = row
    ordered = sorted(
        games.items(),
        key=lambda item: (str(item[1].get("commence_time", "") or ""), item[0]),
    )
    asked = sorted(_project_markets(markets))
    result = odds_api.FetchResult(fetched_at=fetched_at)
    result.errors.append(
        f"Events list: {cause} The per-event fetch lists the games before it "
        "asks about any, so no per-event request was made for any of the "
        f"{len(ordered)} game(s) the bulk fetch staged."
    )
    for event_id, row in ordered:
        result.failed_events.append(
            {
                "provider_event_id": event_id,
                "date": str(row.get("date", "") or "").strip(),
                "commence_time": str(row.get("commence_time", "") or "").strip(),
                "home_team": str(row.get("home_team", "") or "").strip(),
                "away_team": str(row.get("away_team", "") or "").strip(),
                "markets": list(asked),
                "error": (
                    f"Event {event_id}: not asked, because the events list "
                    f"failed: {cause}"
                ),
            }
        )
    return result


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
    # Which games' per-event requests failed, and which markets that left
    # with no answer. It goes to the provenance (the card reads it there)
    # and to both reports, so none of them reads a failed request as a
    # market no book quotes.
    failed_events: list[dict] = []
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
        # One instant for the whole run. Both fetches drop a game that has
        # started by `now`, and each reading its own clock would let a game
        # that starts between the two calls be staged by the bulk fetch and
        # dropped by the per-event one: the slate would count it, and every
        # per-event market would read "priced for N-1 of N" and leave the
        # card.
        fetched = datetime.now(timezone.utc)
        stamp = fetched.isoformat(timespec="seconds")
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
                now=fetched,
            )
        except EmptySlateError as exc:
            # A 422 to the market list and to a plain moneyline is the
            # provider's only evidence for "no NHL odds at all". Until
            # 2026-09-26 it was taken on that evidence alone, and exit 3 is
            # what makes Gameday Refresh record empty_slate=true and
            # degraded=false, post nothing, and stand the 15:00 backup down.
            # A parameter both requests share, such as a region the provider
            # stops serving, would draw the same two refusals on every run of
            # a season, and every one of those runs would be green with no
            # card. The NHL schedule this run's "Fetch results" cached can
            # tell: books post regular-season lines days ahead, so a game
            # scheduled in the window makes "no odds at all" a fault
            # (failure-shape audit, c3x0-odds-api-600).
            if isinstance(exc, odds_api.NoOddsServedError):
                days = league_days or [datetime.now(LEAGUE_TIMEZONE).date().isoformat()]
                scheduled = _scheduled_regular_season_games(days)
                if scheduled:
                    print(
                        "Team-market fetch failed: the provider refused the "
                        "market list and a plain moneyline with HTTP 422, "
                        "which reads as the off-season, but the cached NHL "
                        f"schedule lists {scheduled} regular-season game(s) "
                        f"on {', '.join(days)}. Books price regular-season "
                        "games days ahead, so this is a provider or request "
                        "fault and not an empty slate. "
                        f"{odds_api.NO_STAGING_WRITTEN}",
                        file=sys.stderr,
                    )
                    return 2
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
            try:
                props = provider.fetch_player_props(
                    markets=per_event,
                    max_events=args.max_events,
                    credit_cap=args.credit_cap,
                    fetched_at=stamp,
                    league_days=league_days,
                    now=fetched,
                )
            except odds_api.ProviderError as exc:
                # The events list failed. `fetch_player_props` asks the free
                # `/events` endpoint for the slate before it asks any game's
                # `/events/{id}/odds`, and that one request sits outside the
                # per-event loop's `except`. Everything else it raises before
                # the loop cannot happen here: the bulk call has already
                # proved the credential, the argument parser refused a cap
                # that is not positive, and the market list is fixed.
                #
                # This call used to have no guard, so the failure escaped
                # `main` after the team file was staged. The failure-shape
                # sweep (s1x2-run-provider-shadow-269, 3 of 3 refuters)
                # replayed a bulk call pricing 3 games at 2 books and a 502
                # on `/events`. The script died with a traceback and exit 1,
                # outside its 0/2/3/4 contract. It said "No staging file was
                # written." beside a 36-row team file. It wrote no props
                # file, no provenance and neither report, and exit 1 meant
                # the price step wrote no per-event note. The card, finding
                # no provenance, excluded all 9 per-event markets as "The
                # provider returned no rows for this market ... Check
                # per-bookmaker coverage", the wording #193 was merged to
                # stop, where a per-event 502 on the same slate gives 0 of
                # 9. A refused connection took the same path, and the
                # interpreter's traceback printed the chained `requests`
                # error, whose URL carries `apiKey=`.
                #
                # It is recorded as what it is: a per-event fetch that failed
                # for every game the bulk fetch staged. Only `str(exc)` is
                # printed, never a traceback. It then falls through to the
                # same staging, provenance, reports and exit 4 as any failed
                # per-event request.
                props = _listing_failed(
                    team.rows, per_event, exc, fetched_at=stamp
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
            # And the exit code was all the failure reached. Both reports
            # and the card still read the nine per-event markets of that
            # all-503 run as "No book returned this market" and "The
            # provider returned no rows", and the discovery report was
            # byte-identical to one from a run whose books quoted nothing.
            #
            # A failed per-event request leaves unanswered only the markets
            # no other request answered for that game. The bulk request
            # asked moneyline, puck line and totals for every game and was
            # answered, so a failed request costs those their alternate
            # rungs, not the market: `puck_line` with no `spreads` quoted is
            # still the books' answer, and must not read as a failed fetch.
            answered_in_bulk = _project_markets(odds_api.BULK_PROVIDER_MARKETS)
            failed_events = [
                {
                    **entry,
                    "markets": sorted(
                        set(entry.get("markets", ())) - answered_in_bulk
                    ),
                }
                for entry in props.failed_events
            ]
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
                failed_events=failed_events,
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
        failed_events=failed_events,
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
