"""The public site never names the outside rating site the model borrowed from.

Cooper, 2026-10-26: "dont show anything about post hockey ... I just wanted
you to use it as a reference". The pages, their shared scripts and the sample
boards may carry the data key `posthockey` (the factor step's key in
board.json), but no reader-facing text names the site.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
NAMED = re.compile(r"Post ?Hockey|POST ?HOCKEY|post hockey|posthockey\.com", re.IGNORECASE)


def _published() -> list[Path]:
    return [*WEB.glob("*.html"), *(WEB / "lib").glob("*.js"), *(WEB / "data" / "sample").glob("*.json")]


def test_no_page_names_it() -> None:
    for path in _published():
        text = path.read_text(encoding="utf-8")
        # The bare lowercase key is data, not text a reader sees.
        hits = [m.group(0) for m in NAMED.finditer(text) if m.group(0) != "posthockey"]
        assert not hits, (path.name, hits)


def test_the_factor_label_does_not_name_it() -> None:
    from nhl_betting_lab.factor_breakdown import STEPS

    assert not any(NAMED.search(label) for _, label in STEPS)
