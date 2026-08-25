#!/usr/bin/env python3
"""Check that the provider policy is supported by its approval paperwork.

Exits non-zero when it is not, so CI fails a pull request that widens the
policy without the evidence to justify it.

    PYTHONPATH=src .venv/bin/python scripts/run_policy_pr_gate.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.reports.policy_pr_gate import (
    GATE_MARKDOWN_FILENAME,
    render_gate,
    run_gate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)

    result = run_gate()
    rendered = render_gate(result)
    print(rendered)

    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / GATE_MARKDOWN_FILENAME).write_text(rendered, encoding="utf-8")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
