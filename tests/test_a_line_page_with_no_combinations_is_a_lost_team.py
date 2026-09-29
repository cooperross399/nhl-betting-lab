"""A team page that loads but carries no line combinations is a lost team.

#264 made the line-unit capture name every lost team in a `::warning::` and
exit 2 when fewer than half the teams were read. A team counted as lost only
when its fetch raised or `rows_from_page` raised, and `rows_from_page`
returned [] quietly when __NEXT_DATA__ parsed but held no `combinations`
dict: the shape of a Next.js soft error (`/_error`, statusCode 404) or a
fallback shell served with HTTP 200. The seed page loading and the other 31
answering such pages wrote one team's rows, printed "1 team(s)", named no
one and exited 0, and the source keeps no archive (sweep 6, line-
combinations-empty-team-pages-not-counted-lost).

A real combinations page whose `players` list is empty (no lines posted
yet, a quiet preseason page) is different: it is read, not lost, so a quiet
round cannot turn Line Movement red on its own.

Every fetch goes to a stub; nothing reaches the network.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.data import line_combinations as lc
from test_line_combinations import _load_script, _page, _player

SLUGS = ["toronto-maple-leafs"] + [f"team-{index:02d}" for index in range(31)]

SOFT_404 = (
    '<html><body><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"statusCode":404}},"page":"/_error"}'
    "</script></body></html>"
)


def _run(tmp_path, monkeypatch, capsys, *, soft: set[str] = frozenset(),
         empty: set[str] = frozenset()):
    module = _load_script()
    monkeypatch.setattr(module, "games_today", lambda *a, **k: 12)
    teams = [{"slug": slug} for slug in SLUGS]

    def fetch(url: str, **_kwargs) -> str:
        slug = url.split("/teams/", 1)[1].split("/", 1)[0]
        if slug in soft:
            return SOFT_404
        if slug in empty:
            return _page(players=[], teams=teams)
        return _page(players=[_player(1, "A B", "f1", "ev")], teams=teams)

    monkeypatch.setattr(module, "_fetch", fetch)
    code = module.main(["--processed-dir", str(tmp_path), "--polite-seconds", "0"])
    captured = capsys.readouterr()
    written = list(tmp_path.rglob("*.csv"))
    frame = pd.read_csv(written[0]) if written else None
    return code, captured.out + captured.err, frame


def test_a_soft_error_page_is_refused_not_read_as_empty() -> None:
    with pytest.raises(ValueError, match="no line combinations"):
        lc.rows_from_page(SOFT_404, retrieved_at="x")


def test_a_real_page_with_no_players_is_zero_rows_not_an_error() -> None:
    assert lc.rows_from_page(_page(players=[]), retrieved_at="x") == []


def test_31_soft_error_pages_are_red(tmp_path: Path, monkeypatch, capsys) -> None:
    code, out, frame = _run(tmp_path, monkeypatch, capsys, soft=set(SLUGS[1:]))

    assert code == 2, out
    assert frame is not None and len(frame) == 1, "what arrived is still kept"
    assert "::warning::The line units were NOT captured for 31 of 32 team(s)" in out
    assert "team-00" in out and "team-30" in out
    assert "::error::Only 1 of 32 team page(s) were read" in out


def test_one_soft_error_page_is_a_named_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    code, out, frame = _run(tmp_path, monkeypatch, capsys, soft={"team-05"})

    assert code == 0, out
    assert frame is not None and len(frame) == 31
    assert "::warning::The line units were NOT captured for 1 of 32 team(s)" in out
    assert "(team-05)" in out


def test_teams_with_no_lines_posted_are_not_lost(tmp_path: Path, monkeypatch, capsys) -> None:
    """Most of the league quiet, as in preseason: no warning, no red."""
    code, out, frame = _run(tmp_path, monkeypatch, capsys, empty=set(SLUGS[1:]))

    assert code == 0, out
    assert frame is not None and len(frame) == 1
    assert "::warning::" not in out and "::error::" not in out
    assert "no lines posted yet" in out and "team-30" in out
