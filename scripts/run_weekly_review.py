#!/usr/bin/env python3
"""Write the weekly review's scorecard (Cooper, 2026-11-12).

    PYTHONPATH=src .venv/bin/python scripts/run_weekly_review.py \
        --card-feed origin/card-feed --ledger <forward_evidence dir or csv>

Reads every card on `--card-feed` (its `latest_card_comment.md` history) and
the forward ledger (a directory of card-feed's `forward_evidence/<day>.csv`
files, or one CSV), and writes `data/outputs/weekly_review.md` and `.json`:
counts, records, units and intervals by market and side, never a price,
line, book or player. Offline, spends nothing.

Exits 0 when it wrote the review, 1 when the card history or the ledger
could not be read.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab import pick_timing, weekly_review
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR


def read_ledger(paths: list[Path]) -> pd.DataFrame:
    files = [p for given in paths for p in (sorted(given.glob("*.csv")) if given.is_dir() else [given])]
    frames = [pd.read_csv(p, dtype={"player": str}) for p in files if p.is_file()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="The git checkout holding --card-feed.")
    parser.add_argument("--card-feed", default="origin/card-feed")
    parser.add_argument("--ledger", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--today", default="", help="League day of the review (default: today, UTC).")
    args = parser.parse_args(argv)

    try:
        cards = pick_timing.card_history(Path(args.repo), args.card_feed)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"::warning::The card history on {args.card_feed} could not be read: {exc}")
        return 1
    ledger = read_ledger(args.ledger or [PROCESSED_DIR / "forward_evidence.csv"])
    if ledger.empty:
        print("::warning::No forward ledger could be read.")
        return 1
    listings = pick_timing.first_listings_from_cards(cards)
    scored = pick_timing.score(listings, ledger=ledger)
    population = weekly_review.learned_population(ledger)
    today = args.today or date.today().isoformat()
    since = (date.fromisoformat(today) - timedelta(days=7)).isoformat()
    review = weekly_review.build_review(listings, scored, population, today=today, last_week_from=since)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "weekly_review.json").write_text(
        json.dumps({"generated_at": generated, **review}, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (out / "weekly_review.md").write_text(weekly_review.render(review, generated=generated), encoding="utf-8")
    print(f"Weekly review: {len(listings)} best bets listed, {len(population)} learned wagers scored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
