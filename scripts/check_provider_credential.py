#!/usr/bin/env python3
"""Confirm the provider credential is present, without revealing it.

Prints whether a credential is configured and how long it is. It never prints,
writes, compares, or transmits the value, and it makes no provider request, so
it costs no quota.

    PYTHONPATH=src .venv/bin/python scripts/check_provider_credential.py

Exits non-zero when no credential is configured. That is deliberately hard:
without a key there is no price fetch to degrade to, and a dead credential
must be loud rather than surfacing later as a confusing provider error.
"""

from __future__ import annotations

import argparse
import os
import sys

from nhl_betting_lab.providers.env_file import (
    PROVIDER_ENV_ALLOWLIST,
    load_provider_env,
)
from nhl_betting_lab.providers.odds_api import API_KEY_ENV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="Check only the exported environment, ignoring any local .env.",
    )
    args = parser.parse_args(argv)

    if not args.no_env_file:
        result = load_provider_env()
        print(result.summary_line())
        for warning in result.warnings:
            print(f"  warning: {warning}", file=sys.stderr)

    value = os.environ.get(API_KEY_ENV, "").strip()
    if not value:
        print(
            f"No credential in `{API_KEY_ENV}`. In CI this is the GitHub "
            "secret of that name; locally it is a gitignored `.env`. Never "
            "pass it as a command argument and never commit it.",
            file=sys.stderr,
        )
        return 1

    # Length only. Never the value, never a prefix, never a hash that could be
    # checked against a guess.
    print(
        f"`{API_KEY_ENV}` is configured ({len(value)} characters). "
        "The value is never printed, written, or compared."
    )
    print(f"Names that may travel through `.env`: {', '.join(PROVIDER_ENV_ALLOWLIST)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
