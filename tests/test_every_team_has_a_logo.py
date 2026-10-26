"""Every team the site builder knows has a logo on disk, and board.json points at it.

Drop 6 (2026-10-18) put a logo in every team circle on the Board, Results and Graphic pages. The
page reads `teams[abbr].logo` from board.json, falls back to `./logos/<ABBR>.png`, and then to the
coloured abbreviation. `web/fetch_logos.py` filled `web/logos/` once (ESPN's teams endpoint, the
host the live scoreboard already reads) and the PNGs are committed; Publish Site copies `web/`
whole into the deployed site, so the folder ships beside the pages.

`web/build_site_json.py::team_entry` writes `logo` only when the file exists at build time, so a
board can never name an image the site does not serve. What these tests hold:

* every abbreviation in the builder's `TEAMS` has `web/logos/<ABBR>.png`, a whole PNG (signature,
  IHDR, every chunk's CRC, an IDAT stream that inflates) of 128 px and more than 1 KB (shrunk from a 500 px download), checked by
  the fetch script's own standard-library validator, so a truncated download or an HTML error page
  saved as `.png` is red;
* `team_entry` writes `./logos/<ABBR>.png` for each of them, and that path, read against `web/`
  as the page reads it, is a file;
* a board built by the real `main()` carries `logo` on every team it publishes, each pointing at a
  file that exists;
* a team with no file gets no `logo` key at all, never a path to nothing;
* `web/logos/SOURCES.md` names every file and where it came from, and says the logos are
  trademarks shown for identification only.

Offline: nothing here fetches a logo.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from test_site_never_calls_an_unpriced_game_a_pass import build, make_lab

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
LOGOS = WEB / "logos"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load("_site_build_logos", WEB / "build_site_json.py")


@pytest.fixture(scope="module")
def fetcher():
    return _load("_fetch_logos", WEB / "fetch_logos.py")


def served(path: str) -> Path:
    """Where a page-relative path such as "./logos/TOR.png" lands in web/."""
    assert path.startswith("./"), path
    return WEB / path[2:]


def test_the_builder_knows_every_club(builder) -> None:
    """The check below is over `TEAMS`; an empty or short table would check nothing."""
    assert len(builder.TEAMS) == 32


def test_every_team_the_builder_knows_has_a_real_logo_file(builder, fetcher) -> None:
    missing, broken = [], []
    for abbr in sorted(builder.TEAMS):
        path = LOGOS / f"{abbr}.png"
        if not path.is_file():
            missing.append(abbr)
            continue
        data = path.read_bytes()
        if not fetcher.usable(data, fetcher.PUBLISHED_PX, fetcher.PUBLISHED_MIN_BYTES):
            broken.append(f"{abbr} ({len(data)} bytes, size {fetcher.png_size(data)})")
    assert not missing, f"no web/logos/<ABBR>.png for {missing}: run web/fetch_logos.py"
    assert not broken, f"not a whole {fetcher.PUBLISHED_PX} px PNG over 1 KB: {broken}"


def test_team_entry_points_every_team_at_its_existing_file(builder) -> None:
    for abbr in sorted(builder.TEAMS):
        entry = builder.team_entry(abbr)
        assert entry["logo"] == f"./logos/{abbr}.png", abbr
        assert served(entry["logo"]).is_file(), abbr


def test_a_built_board_points_every_team_at_an_existing_file(tmp_path: Path, monkeypatch) -> None:
    lab = make_lab(tmp_path, monkeypatch, staged=False)
    board, _ = build(lab, tmp_path / "out", monkeypatch)
    assert board["teams"], "the board published no teams, so nothing was checked"
    for abbr, team in board["teams"].items():
        assert "logo" in team, abbr
        assert served(team["logo"]).is_file(), (abbr, team["logo"])


def test_a_team_without_a_file_gets_no_logo_key(builder, tmp_path: Path, monkeypatch) -> None:
    assert "logo" not in builder.team_entry("ZZZ")
    monkeypatch.setattr(builder, "LOGOS", tmp_path / "empty")
    assert "logo" not in builder.team_entry("TOR")
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "TOR.png").write_bytes(b"stand-in")
    assert builder.team_entry("TOR")["logo"] == "./logos/TOR.png"


def test_sources_name_every_file_and_the_trademark_notice(fetcher) -> None:
    files = sorted(path.stem for path in LOGOS.glob("*.png"))
    recorded = fetcher.read_sources(LOGOS)
    assert files, "web/logos holds no PNG"
    assert sorted(recorded) == files
    for abbr, (source, url) in recorded.items():
        assert source in {"ESPN", "Wikimedia Commons"}, abbr
        assert url.startswith("https://"), abbr
    text = (LOGOS / "SOURCES.md").read_text(encoding="utf-8")
    assert "trademarks, shown for identification only" in text
