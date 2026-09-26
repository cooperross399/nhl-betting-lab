"""The card's "no team-name map" blocker could never fire, and it poisoned the file.

`run_gameday_card.py` blocked the card `if not team_names`. But
`build_team_name_map` always adds the Utah and Arizona aliases and every
abbreviation's own name, so with no boxscores cached it returns six entries —
never an empty map. The blocker was dead, and the only test of it passed by
monkeypatching the builder to return `{}`, a value production never returns.

Worse, the card then saved that six-entry map as `team_names.csv`, and
`load_team_name_map` prefers the file to a rebuild whenever it is non-empty. So
one run without boxscores left a map that resolves no Toronto or Boston behind
for every later reader: the team measurement and forward settlement now refuse
on it (#107, #108), but they should never be handed it.

What these tests hold, with the REAL builder over an empty cache:

* `cache_derived_spellings` is zero for the alias-only map and positive for a
  map built from one boxscore;
* the card blocks with the team-name reason and writes no `team_names.csv`;
* a `team_names.csv` holding only aliases is ignored on load in favour of a
  rebuild from the cache, so a file already poisoned heals.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from conftest import boxscore_payload
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as tn
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _one_boxscore(raw: Path) -> None:
    """Toronto hosting Boston, as the NHL API spells both."""
    payload = boxscore_payload(game_id=1, game_state="OFF")
    payload["homeTeam"].update(
        abbrev="TOR", placeName={"default": "Toronto"},
        commonName={"default": "Maple Leafs"},
    )
    payload["awayTeam"].update(
        abbrev="BOS", placeName={"default": "Boston"},
        commonName={"default": "Bruins"},
    )
    directory = raw / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "1.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def empty_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Default raw and processed directories that hold nothing, so the real
    boxscore cache cannot rescue a test or make it pass by checkout.

    Every other default goes too: this used to redirect only the team-name
    ones, and the card still read the checkout's club schedules (384 files in
    the operator's checkout) and the tracked verdicts."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    raw = tmp_path / "default_raw"
    processed = tmp_path / "default_processed"
    raw.mkdir()
    processed.mkdir()
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", processed)
    return raw


def test_the_alias_only_map_is_not_empty_and_derives_nothing(
    tmp_path: Path, empty_cache: Path
) -> None:
    aliases_only = tn.build_team_name_map()
    _one_boxscore(tmp_path / "raw")
    from_cache = tn.build_team_name_map(tmp_path / "raw")

    assert len(aliases_only) == 6, "never empty: `if not map` cannot see it"
    assert tn.cache_derived_spellings(aliases_only) == 0
    assert tn.cache_derived_spellings(from_cache) > 0
    assert tn.resolve_team("Toronto Maple Leafs", from_cache) == "TOR"


def test_the_card_blocks_and_saves_nothing_when_no_boxscores_are_cached(
    tmp_path: Path, empty_cache: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script("run_gameday_card.py")

    module.main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
            "--now", "2026-10-08T18:00:00+00:00",
        ]
    )
    capsys.readouterr()
    card = json.loads(
        (tmp_path / "outputs" / "gameday_card.json").read_text(encoding="utf-8")
    )

    assert any(
        "No team-name map could be built" in item for item in card["blockers"]
    ), card["blockers"]
    assert not (tmp_path / "processed" / tn.TEAM_NAMES_FILENAME).exists()


def test_the_card_saves_a_map_the_cache_supplied(
    tmp_path: Path, empty_cache: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _one_boxscore(empty_cache)
    module = load_script("run_gameday_card.py")

    module.main(
        [
            "--staging-dir", str(tmp_path / "staging"),
            "--processed-dir", str(tmp_path / "processed"),
            "--output-dir", str(tmp_path / "outputs"),
            "--now", "2026-10-08T18:00:00+00:00",
        ]
    )
    capsys.readouterr()
    card = json.loads(
        (tmp_path / "outputs" / "gameday_card.json").read_text(encoding="utf-8")
    )
    saved = tn.load_team_name_map(processed_dir=tmp_path / "processed")

    assert not any("team-name map" in item for item in card["blockers"])
    assert tn.resolve_team("Toronto Maple Leafs", saved) == "TOR"


def test_a_saved_alias_only_map_is_ignored_in_favour_of_a_rebuild(
    tmp_path: Path, empty_cache: Path
) -> None:
    """A file the old card wrote heals on the next read once boxscores exist."""
    processed = tmp_path / "processed"
    tn.save_team_name_map(tn.build_team_name_map(), processed_dir=processed)
    _one_boxscore(empty_cache)

    loaded = tn.load_team_name_map(processed_dir=processed)

    assert tn.resolve_team("Toronto Maple Leafs", loaded) == "TOR"


def test_a_saved_map_the_cache_supplied_still_outranks_a_rebuild(
    tmp_path: Path, empty_cache: Path
) -> None:
    processed = tmp_path / "processed"
    tn.save_team_name_map(
        {"toronto maple leafs": "TOR", "boston bruins": "BOS"},
        processed_dir=processed,
    )

    loaded = tn.load_team_name_map(processed_dir=processed)

    assert loaded == {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
