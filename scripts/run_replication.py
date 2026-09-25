#!/usr/bin/env python3
"""Compare two measured windows and say whether a result replicated.

    PYTHONPATH=src .venv/bin/python scripts/run_replication.py \
        --discovery data/outputs/player_props_backtest_2025-26.json \
        --test data/outputs/player_props_backtest_2024-25.json

Offline. Reads two labelled backtest payloads and writes
`data/outputs/replication.md`. It never pools them: pooling asks a different
question and launders a strong first window into a merged average that reads
like confirmation.

It refuses (exit 1, nothing written, the previous record untouched) when
either window is missing, unreadable, or measured no bets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.reports.replication import (
    bets_measured,
    compare,
    load_backtest,
    save_replication,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--discovery-label", default="")
    parser.add_argument("--test-label", default="")
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    discovery_path = Path(args.discovery)
    test_path = Path(args.test)
    discovery = load_backtest(discovery_path)
    test = load_backtest(test_path)

    missing = [
        str(path)
        for path, payload in ((discovery_path, discovery), (test_path, test))
        if not payload
    ]
    if missing:
        print(
            "Cannot compare: these measured windows are missing or unreadable: "
            + ", ".join(missing)
        )
        return 1

    # A WINDOW THAT MEASURED NOTHING IS NOT A WINDOW WHERE NOTHING SURVIVED.
    # The check above catches a missing or unreadable file only. A backtest
    # payload with `bets: 0, by_market: {}` is a well-formed 17-key dict, and
    # `run_player_props_backtest.py` exits 0 and writes one whenever its
    # window matches nothing. On the real store, `--from 2025-10-07 --to
    # 2025-04-30 --label 2025-26` (end year mistyped) read 0 of 3,804,233
    # price rows. Passed here as --discovery, that file produced a run that
    # exited 0 and wrote "Nothing survived correction on
    # **player_props_backtest_2025-26** ... That is not a failure of the test
    # window", with all six markets "untestable". Against the same test
    # window, the home checkout's measured 2025-26 file (2026-08-28) returns
    # `points` replicated, `goalie_saves` not confirmed and `shots_on_goal`
    # contradicted. A comparison that never happened was recorded as a null,
    # in the file `allowlist_evidence` reads. Either window with no bets is
    # now refused, the way a missing one is: there is nothing to compare.
    unmeasured = [
        str(path)
        for path, payload in ((discovery_path, discovery), (test_path, test))
        if bets_measured(payload) == 0
    ]
    if unmeasured:
        print(
            "Cannot compare: these windows measured no bets, so there is "
            "nothing to compare: "
            + ", ".join(unmeasured)
            + ". A window that measured nothing is not a result that failed "
            "correction. Check that the backtest's --from/--to/--phase "
            "matched price rows. Nothing was written, so the previous "
            "replication record is untouched."
        )
        return 1

    report = compare(
        discovery,
        test,
        discovery_label=args.discovery_label or discovery_path.stem,
        test_label=args.test_label or test_path.stem,
    )
    paths = save_replication(report, output_dir=Path(args.output_dir))

    print(report.headline())
    for item in report.markets:
        print(f"  {item.market}: {item.state} — {item.reason}")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
