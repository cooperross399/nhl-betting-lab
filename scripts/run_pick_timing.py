#!/usr/bin/env python3
"""Measure the card's best bets by the run that first listed them.

    PYTHONPATH=src .venv/bin/python scripts/run_pick_timing.py \
        --card-feed origin/card-feed --captures-dir <private store dir>

Cooper, 2026-11-10 ("ALL"): are the picks the afternoon (20:30 UTC) and
pre-game (22:30 UTC) re-prices add worse than the morning card's? Reads every
card on `--card-feed` (a git ref holding `latest_card_comment.md`, whose
history is every card), the forward ledger, the priced snapshots, the logs,
and the closing prices in each `--captures-dir`, and writes
`data/outputs/pick_timing.md` and `.json`: counts, rates, means and
intervals by run, never a price, line, book or player. Offline, spends
nothing. Gameday Refresh runs it inside "Report closing-line value", the one
step that may read the private capture store; without `--captures-dir` it
measures results alone.

Exits 0 when it wrote the report, 1 when the card history could not be read.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab import pick_timing
from nhl_betting_lab.closing_lines import load_captures
from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.forward_evidence import load_ledger, read_snapshot, snapshots_dir
from nhl_betting_lab.providers.team_names import load_team_name_map


def _snapshots(archive: Path | None) -> pd.DataFrame:
    frames = []
    directory = snapshots_dir(archive)
    if directory.is_dir():
        for path in sorted(directory.glob("*.csv")):
            try:
                frame, _problem = read_snapshot(path)
            except OSError:
                frame = None
            if frame is not None:
                frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="The git checkout holding --card-feed.")
    parser.add_argument("--card-feed", default="origin/card-feed")
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--archive-dir", default="")
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--captures-dir", action="append", default=[])
    args = parser.parse_args(argv)

    try:
        cards = pick_timing.card_history(Path(args.repo), args.card_feed)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"::warning::The card history on {args.card_feed} could not be read: {exc}")
        return 1
    listings = pick_timing.first_listings_from_cards(cards)
    processed = Path(args.processed_dir)
    ledger = load_ledger(processed)
    opinions = _snapshots(Path(args.archive_dir) if args.archive_dir else None)
    captures_frames = []
    for directory in args.captures_dir:
        try:
            captures_frames.append(load_captures(Path(directory), unreadable={}))
        except Exception as exc:  # a damaged store is the CLV report's to name
            print(f"::warning::Captures in {directory} could not be read for the timing report: {exc}")
    frames = [frame for frame in captures_frames if not frame.empty]
    captures = pd.concat(frames, ignore_index=True) if frames else None
    try:
        names = load_team_name_map(processed_dir=processed)
    except Exception:  # noqa: BLE001 - the ledger alone still settles most picks
        names = {}
    scored = pick_timing.score(
        listings,
        ledger=ledger,
        opinions=opinions,
        captures=captures,
        logs=load_player_logs(processed),
        games=load_team_games(processed),
        team_names=names,
    )
    summary = pick_timing.summarise(scored)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary["generated_at"] = generated
    summary["cards_read"] = len(cards)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / pick_timing.REPORT_MD).write_text(
        pick_timing.render(summary, generated=generated, has_closes=captures is not None),
        encoding="utf-8",
    )
    (output / pick_timing.REPORT_JSON).write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(pick_timing.render(summary, generated=generated, has_closes=captures is not None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
