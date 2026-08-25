#!/usr/bin/env python3
"""Assemble the evidence bundle a human needs to decide on allowlisting.

Writes `data/outputs/allowlist_evidence_bundle.md`. Read-only: it reads the
measurement outputs, checksums them, and states what they support.

    PYTHONPATH=src .venv/bin/python scripts/run_allowlist_evidence.py

It never writes a receipt, never edits the policy, and never approves
anything. Those are Cooper's, and the bundle says so.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.providers.odds_api import PROVIDER_NAME
from nhl_betting_lab.reports.allowlist_evidence import build_bundle, save_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default=PROVIDER_NAME)
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    bundle = build_bundle(
        provider_name=args.provider, output_dir=Path(args.output_dir)
    )
    paths = save_bundle(bundle, output_dir=Path(args.output_dir))

    print(bundle.recommendation())
    for verdict in bundle.verdicts:
        print(f"  {verdict.sentence()}")
    if bundle.missing_files:
        print(f"Missing evidence: {', '.join(bundle.missing_files)}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print(
        "Claude assembled this and stops here. No receipt was written, no "
        "policy was edited, and nothing was approved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
