"""A line-unit capture that loses team pages says so, and losing most is red.

`capture_line_combinations.py` exited 2 only when no row was parsed at all.
When the seed (Toronto) page loaded and the other 31 answered 429 (the usual
shape of a cloud IP throttled after its first request), it wrote one team's
rows, printed "31 team page(s) could not be read" to stderr alone, and exited
0. Line Movement's "Capture line combinations" step was green, its gate reads
only a failed outcome, nothing reached the run page, and 31 teams' line units
and PP1 promotions for the round were gone: Daily Faceoff keeps no archive
(sweep 5, line-combinations-partial-capture-reads-green).

The rule is now `capture_deployment.py`'s, with a floor:

* every lost team is named in a `::warning::`, and the teams that were read
  are still appended;
* fewer than half the team pages read is a lost round: exit 2, so the
  workflow's line-units gate turns the run red after every upload;
* one lost page of 32 is a warning, not a red run.

Every fetch goes to a stub; nothing reaches the network.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import requests

from test_line_combinations import _load_script, _page, _player

SLUGS = ["toronto-maple-leafs"] + [f"team-{index:02d}" for index in range(31)]


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    answering: set[str],
) -> tuple[int, str, pd.DataFrame | None]:
    """The real script over 32 team pages, of which only `answering` load;
    every other page raises a 429."""
    module = _load_script()
    monkeypatch.setattr(module, "games_today", lambda *a, **k: 12)
    teams = [{"slug": slug} for slug in SLUGS]

    def fetch(url: str, **_kwargs) -> str:
        slug = url.split("/teams/", 1)[1].split("/", 1)[0]
        if slug not in answering:
            raise requests.HTTPError("429 Client Error: Too Many Requests")
        return _page(players=[_player(1, "A B", "f1", "ev")], teams=teams)

    monkeypatch.setattr(module, "_fetch", fetch)
    code = module.main(["--processed-dir", str(tmp_path), "--polite-seconds", "0"])
    captured = capsys.readouterr()
    written = list(tmp_path.rglob("*.csv"))
    frame = pd.read_csv(written[0]) if written else None
    return code, captured.out + captured.err, frame


def test_losing_31_of_32_pages_is_red_and_keeps_the_one_that_arrived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, frame = _run(
        tmp_path, monkeypatch, capsys, answering={"toronto-maple-leafs"}
    )

    assert code == 2, out
    assert frame is not None and len(frame) == 1, "what arrived is still kept"
    assert "::warning::The line units were NOT captured for 31 of 32 team(s)" in out
    assert "team-00" in out and "team-30" in out, "every lost team is named"
    assert "::error::Only 1 of 32 team page(s) were read" in out


def test_one_lost_page_is_a_warning_not_a_red_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, frame = _run(
        tmp_path, monkeypatch, capsys, answering=set(SLUGS) - {"team-07"}
    )

    assert code == 0, out
    assert frame is not None and len(frame) == 31
    assert "::warning::The line units were NOT captured for 1 of 32 team(s)" in out
    assert "(team-07)" in out
    assert "::error::" not in out


def test_exactly_half_read_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(tmp_path, monkeypatch, capsys, answering=set(SLUGS[:16]))

    assert code == 0, out
    assert "NOT captured for 16 of 32 team(s)" in out
    assert "::error::" not in out


def test_one_fewer_than_half_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, frame = _run(tmp_path, monkeypatch, capsys, answering=set(SLUGS[:15]))

    assert code == 2, out
    assert frame is not None and len(frame) == 15
    assert "::error::Only 15 of 32 team page(s) were read" in out


def test_every_page_read_says_nothing_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, frame = _run(tmp_path, monkeypatch, capsys, answering=set(SLUGS))

    assert code == 0, out
    assert frame is not None and len(frame) == 32
    assert "::warning::" not in out and "::error::" not in out
