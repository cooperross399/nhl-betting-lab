#!/usr/bin/env python3
"""Report the provider quota remaining, without spending any of it.

The `/v4/sports` listing is documented as costing nothing and returns the
`x-requests-remaining` and `x-requests-used` headers, so this is the cheapest
possible way to answer "how much is left".

    PYTHONPATH=src .venv/bin/python scripts/check_provider_quota.py

Prints the numbers and nothing about the credential beyond whether one is
present.
"""

from __future__ import annotations

import argparse
import sys

from nhl_betting_lab.providers.env_file import load_provider_env, redact
from nhl_betting_lab.providers.odds_api import OddsApiProvider, ProviderError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-under",
        type=int,
        default=0,
        help="Exit non-zero when fewer than this many credits remain.",
    )
    args = parser.parse_args(argv)

    load_provider_env()
    try:
        provider = OddsApiProvider()
        _, headers = provider._get(  # noqa: SLF001 — one adapter, one door
            f"{provider.base_url}/v4/sports",
            {"apiKey": provider.api_key},
        )
    except ProviderError as exc:
        print(redact(f"Could not reach the provider: {exc}"), file=sys.stderr)
        return 2

    remaining = str(headers.get("x-requests-remaining", "")).strip()
    used = str(headers.get("x-requests-used", "")).strip()
    print(
        f"Quota: {remaining or 'unknown'} remaining, {used or 'unknown'} used. "
        "This check itself is documented as free."
    )
    if args.fail_under and remaining.isdigit():
        if int(remaining) < args.fail_under:
            print(
                f"::error::Only {remaining} credits remain, below the "
                f"{args.fail_under} this run wanted. Nothing was bought.",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
