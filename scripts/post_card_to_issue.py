#!/usr/bin/env python3
"""Decide whether the card is worth an email, and write the comment body.

Prints the decision (`post` or `skip`) on the last line so the workflow can
branch on it, and writes the comment body to `--out`.

    PYTHONPATH=src .venv/bin/python scripts/post_card_to_issue.py --out comment.md

It writes a file. It does not talk to GitHub — the workflow does that with
`gh`, so this stays runnable and testable offline.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from nhl_betting_lab.config import OUTPUTS_DIR
from nhl_betting_lab.reports.card_notification import (
    OPERATING_HOME_BODY,
    OPERATING_HOME_TITLE,
    decide,
    previous_fingerprint_from,
    render_comment,
)
from nhl_betting_lab.reports.gameday_card import CARD_JSON_FILENAME, GamedayCard


def _load_card(path: Path) -> GamedayCard | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    known = {field.name for field in fields(GamedayCard)}
    return GamedayCard(**{k: v for k, v in payload.items() if k in known})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-json", default=str(OUTPUTS_DIR / CARD_JSON_FILENAME))
    parser.add_argument("--previous-json", default="")
    parser.add_argument("--out", default="card_comment.md")
    parser.add_argument("--title-out", default="card_title.txt")
    parser.add_argument("--body-out", default="issue_body.md")
    parser.add_argument("--degraded-file", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    card = _load_card(Path(args.card_json))
    if card is None:
        print("No card JSON on disk; nothing to post.")
        print("skip")
        return 0

    previous = None
    if args.previous_json:
        path = Path(args.previous_json)
        if path.is_file():
            try:
                previous = previous_fingerprint_from(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                previous = None

    degraded: list[str] = []
    if args.degraded_file:
        path = Path(args.degraded_file)
        if path.is_file():
            degraded = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

    decision = decide(
        card,
        previous_fingerprint=previous,
        degraded_notes=degraded,
        force=args.force,
    )
    body = render_comment(
        card, decision, run_url=args.run_url, degraded_notes=degraded
    )
    Path(args.out).write_text(body, encoding="utf-8")
    Path(args.title_out).write_text(OPERATING_HOME_TITLE, encoding="utf-8")
    Path(args.body_out).write_text(OPERATING_HOME_BODY, encoding="utf-8")

    print(decision.summary_line())
    print("post" if decision.post else "skip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
