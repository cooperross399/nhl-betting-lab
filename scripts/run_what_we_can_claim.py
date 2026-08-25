#!/usr/bin/env python3
"""Write `data/outputs/what_we_can_claim.md` from the measurements on disk.

The third of the three measurement outputs the operating contract names. It
reads whatever measurement JSON exists and states what it supports, in the
fixed vocabulary this repository uses for its own results.

    PYTHONPATH=src .venv/bin/python scripts/run_what_we_can_claim.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.providers.odds_api import PROVIDER_NAME
from nhl_betting_lab.reports.what_we_can_claim import build_claims_report, save_claims
from nhl_betting_lab.staging_provider_policy import load_policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    policy = load_policy()
    report = build_claims_report(
        output_dir=Path(args.output_dir),
        policy_status=policy.status,
        allowlisted_markets=policy.allowed_markets(PROVIDER_NAME),
    )
    path = save_claims(report, output_dir=Path(args.output_dir))
    print(report.headline())
    print(f"  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
