"""Every Methods link the pages print lands on an entry that exists.

Game.dc.html, Board.dc.html and Record.dc.html link their `?` chips and
labels to `Methods.dc.html#<anchor>`; a link to a missing anchor opens the
page at the top with nothing said. The design drop names twenty anchors.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
NAMED = {"xg", "xg-sh", "score-venue", "gsax", "goalies", "lineup", "home-ice", "rest", "form", "referees",
         "pregame", "proj-goals", "win", "fair", "edge", "bet-lean", "graded", "changelog", "ratings",
         "defence-ratings"}


def _defined() -> set[str]:
    text = (WEB / "Methods.dc.html").read_text(encoding="utf-8")
    # Entries render id="{id}" from their logic class; fixed sections carry id="..." literally.
    return set(re.findall(r'\bid: *"([a-z0-9-]+)"', text)) | set(re.findall(r'\bid="([a-z0-9-]+)"', text))


def test_every_named_anchor_exists() -> None:
    assert NAMED <= _defined(), sorted(NAMED - _defined())


def test_every_linked_anchor_exists() -> None:
    defined = _defined()
    for page in ("Game.dc.html", "Board.dc.html", "Record.dc.html", "Tracker.dc.html"):
        text = (WEB / page).read_text(encoding="utf-8")
        linked = set(re.findall(r'Methods\.dc\.html#([a-z0-9-]+)', text))
        assert linked <= defined, (page, sorted(linked - defined))
