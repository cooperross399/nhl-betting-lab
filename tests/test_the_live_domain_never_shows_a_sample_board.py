"""On maverickhightower.com the Board and Results pages show the real slate.

The props + live drop (#304) let each page choose its data with
`this.props.scenario || (onSite ? "Normal" : <sample>)`. The preview control
declares a DEFAULT for `scenario` (a props sample), so `props.scenario` was
always set, the `||` never fell through, and on 2026-10-07 the first deploy
served the sample board (NYR @ PHI, a sample Panarin) on
nhl.maverickhightower.com while the real board.json held PIT @ WSH. Nothing
local could see it: off the domain the sample is the intended default.

This evaluates each page's own `const scenario = ...` statement under node,
with `props.scenario` set to the default the page itself declares, on the
real hostname and off it.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
PAGES = ("Board.dc.html", "Results.dc.html")


def _declared_default(page: str) -> str:
    raw = re.search(r'data-props="([^"]*)"', page).group(1)
    return json.loads(html.unescape(raw))["scenario"]["default"]


def _scenario_statement(page: str) -> str:
    lines = [ln.strip() for ln in page.splitlines() if ln.strip().startswith("const scenario =")]
    assert len(lines) == 1, f"expected one scenario statement, found {lines!r}"
    return lines[0]


def _evaluate(statement: str, hostname: str, scenario: str) -> str:
    on_site = bool(re.search(r"(^|\.)maverickhightower\.com$", hostname))
    script = (
        f"const onSite = {json.dumps(on_site)};"
        f"const self = {{ props: {{ scenario: {json.dumps(scenario)} }}, onSite: () => onSite }};"
        f"const f = function () {{ {statement} return scenario; }};"
        "process.stdout.write(f.call(self));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.mark.parametrize("name", PAGES)
def test_the_real_domain_shows_the_real_slate_whatever_the_preview_default(name: str) -> None:
    assert shutil.which("node"), "node is required; the site's other render tests use it too"
    page = (WEB / name).read_text(encoding="utf-8")
    default = _declared_default(page)
    assert default != "Normal", "the guard is only meaningful while the preview default is a sample"
    statement = _scenario_statement(page)
    for host in ("nhl.maverickhightower.com", "maverickhightower.com"):
        assert _evaluate(statement, host, default) == "Normal", (
            f"{name} on {host} chose {default!r} from the preview control's default: "
            "the live site would serve the sample"
        )


@pytest.mark.parametrize("name", PAGES)
def test_off_the_domain_the_preview_default_still_applies(name: str) -> None:
    page = (WEB / name).read_text(encoding="utf-8")
    default = _declared_default(page)
    assert _evaluate(_scenario_statement(page), "localhost", default) == default
