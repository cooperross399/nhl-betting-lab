#!/usr/bin/env python3
"""Settle pending priced snapshots and rebuild the forward-evidence report.

Runs after results are fetched: every snapshot day whose games are all final
settles as a unit into `data/processed/forward_evidence.csv`, and
`data/outputs/forward_evidence.md` restates what the ledger supports.

    PYTHONPATH=src .venv/bin/python scripts/run_forward_evidence.py

Offline: reads the archive, the processed tables, and nothing else. It
fetches nothing, spends nothing, and revises no frozen opinion — a snapshot
is evidence, and settlement only ever appends.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.forward_evidence import (
    build_forward_report,
    load_ledger,
    save_forward_report,
    settle_snapshots,
)
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--archive-dir", default="")
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    archive = Path(args.archive_dir) if args.archive_dir else None

    # The archive and the ledger are one pair: a day counts as settled if its
    # marker is in the archive OR its rows are in the ledger. This used to
    # take the real archive whatever directories it was given, so a scratch
    # run (--processed-dir/--output-dir elsewhere) settled the real archive's
    # days into a scratch ledger and marked them settled in the real archive,
    # and the next real run found nothing pending: the real ledger never got
    # those rows. It also never looked where a scratch card freezes.
    #
    # So, as in run_gameday_card.py, the archive follows a non-default output
    # directory unless one is named, and a scratch ledger with the real
    # archive is refused rather than guessed at.
    if archive is None and outputs.resolve() != OUTPUTS_DIR.resolve():
        archive = outputs / "archive"
    if archive is None and processed.resolve() != PROCESSED_DIR.resolve():
        print(
            f"::error::Refusing to settle the real evidence archive into the "
            f"ledger in {processed}. Its days would be marked settled in the "
            "real archive while their rows went to a ledger the real run "
            "never reads, and nothing would ever settle them again. Pass "
            "--archive-dir for the archive that belongs with this "
            "--processed-dir, or --output-dir (whose archive/ a scratch card "
            "freezes into).",
            file=sys.stderr,
        )
        return 2
    if archive is not None:
        print(
            f"Settling the snapshots under {archive}, not the real evidence "
            "archive, because this run was given its own directories."
        )

    logs = load_player_logs(processed)
    games = load_team_games(processed)
    try:
        result = settle_snapshots(
            logs,
            games,
            team_names=load_team_name_map(processed_dir=processed),
            archive_dir=archive,
            processed_dir=processed,
        )
    except UnresolvedTeamsError as error:
        print(f"::error::{error}", file=sys.stderr)
        refused = True
    else:
        print(result.summary_line())
        refused = False

    # Restated from the ledger even on a refusal, because the ledger did not
    # change and the report is only its restatement. The card-feed commit
    # builds its tree from the files present, so a run that wrote no report
    # would drop `latest_forward_evidence.md` from the feed for the day.
    payload = build_forward_report(load_ledger(processed))
    paths = save_forward_report(payload, output_dir=outputs)
    for name, path in paths.items():
        print(f"  {name}: {path}")
    if refused:
        print(
            "Settlement refused: nothing was settled, marked or appended. The "
            "report above restates the ledger as it already stood."
        )
        return 2
    print(
        "Settlement appends; no frozen opinion was revised, no price was "
        "fetched, and no bet was placed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
