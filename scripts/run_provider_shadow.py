#!/usr/bin/env python3
"""Run a shadow provider fetch and write the verification reports.

A shadow run fetches real prices into `data/staging/` — which the card cannot
read — and reports what it found. It allowlists nothing, promotes nothing, and
places nothing.

    # Offline: assess whatever is already staged. Spends no credits.
    PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py

    # Live team markets only. A handful of credits.
    PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live

    # Live including props. One credit per market per event; the cap is hard.
    PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow.py --live \
        --props --credit-cap 120

The credential comes from `NHL_ODDS_API_KEY` in the environment, a gitignored
`.env`, or a GitHub Secret. It is never accepted as a command argument.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, STAGING_DIR
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.reports.provider_shadow import (
    build_shadow_summary,
    save_shadow_reports,
)
from nhl_betting_lab.staging_provider_policy import load_policy


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
        help="Include player props. One credit per market per event.",
    )
    parser.add_argument(
        "--credit-cap",
        type=int,
        default=60,
        help="Hard cap on props credits. The fetch stops rather than exceeding it.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Fetch props for at most this many events. 0 means the whole slate.",
    )
    parser.add_argument(
        "--overwrite-staging",
        action="store_true",
        help="Replace existing staging files rather than refusing.",
    )
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

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

    if args.live:
        provider = odds_api.OddsApiProvider()
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            team = provider.fetch_team_markets(fetched_at=stamp)
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

        if args.props:
            estimate = provider.estimate_prop_credits(events=events_seen)
            print(
                f"Props would cost about {estimate} credits for "
                f"{events_seen} events; the cap is {args.credit_cap}."
            )
            props = provider.fetch_player_props(
                max_events=args.max_events,
                credit_cap=args.credit_cap,
                fetched_at=stamp,
            )
            written.append(
                odds_api.write_staging(
                    props.rows,
                    filename=odds_api.STAGING_PROPS_FILENAME,
                    staging_dir=staging_dir,
                    overwrite=args.overwrite_staging,
                )
            )
            credits += props.credits_spent
            quota = props.quota_remaining or quota
            warnings += props.warnings
            errors += props.errors
            print(f"Props: {props.summary_line()}")

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
