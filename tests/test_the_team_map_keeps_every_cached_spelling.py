"""Two team-name tests could not fail, and one corrupt-file shape was fatal.

The failure-shape audit (findings 79 and 85, each confirmed by independent
refuters) found two tests in `tests/test_team_names.py` that passed whatever
`build_team_name_map` did with the cache:

* `test_a_renamed_franchise_maps_under_both_names` cached Utah as "Utah
  Hockey Club" and then "Mammoth" and asserted both resolve to UTA. Both names
  are `PROVIDER_ALIASES`, which the builder adds whatever the cache holds, so
  an EMPTY cache already resolved both. A builder that kept only the first
  spelling it saw per abbreviation (audit mutant m14) passed the whole suite,
  1,768 passed. The next rename outside the aliases would then leave one of
  its names unresolved: its games get no card opinion and their forward rows
  cannot settle. Files are read in game-id order, so the name lost would be
  the new one, the one the provider sends for current games.
* `test_a_corrupt_cache_file_is_skipped_not_fatal` cached one corrupt file and
  nothing else, then asserted the map was truthy. The map is never empty (six
  alias entries with no boxscores at all), so a scan that stopped at the
  corrupt file (`continue` -> `break`), one that threw away everything read
  before it, and one that parsed it into an entry all passed the whole suite,
  1,768 passed. In the audit's reproduction, 40 real boxscores plus one
  truncated file sorting first gave the 6-entry alias map under `break`
  instead of 100 entries, and Toronto unresolved.

Writing the corrupt-file test here found a shape that WAS fatal: a boxscore
that parses but is not a JSON object (`null`, `[]`) reached `payload.get` and
raised AttributeError out of the whole build, and the card builds the map with
nothing around it. `fetch_boxscore` stores any HTTP 200 body as-is, and
`build_datasets` already counts that shape as malformed and skips it; the
builder now skips it the same way. 0 of the 5,280 cached boxscores had that
shape on 2026-09-25 (none was unreadable either), so no map changed.

Nothing published depended on either test gap: in that cache UTA is the only
abbreviation with two spellings, and both are aliases. These tests hold the
builder to the cache, through the default directories the card reads:

* a rename that is NOT an alias maps under both names, old and new, and the
  saved map the settlement reads keeps both;
* unreadable files (truncated, empty, not UTF-8) placed before, between and
  after good boxscores contribute nothing and stop nothing: the map is exactly
  the good files' map, entry for entry;
* a boxscore that is valid JSON but not an object is skipped the same way.

Every expected map is keyed as production keys it (normalized lowercase) and
written out rather than rebuilt with the builder, so a builder change cannot
move the answer with it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from conftest import boxscore_payload
from nhl_betting_lab.data.nhl_api import _write_cache
from nhl_betting_lab.providers import team_names as tn


Team = tuple[str, str, str]  # (abbrev, placeName, commonName), as the feed has it

KRAKEN: Team = ("SEA", "Seattle", "Kraken")
#: The renamed Seattle club. Not an alias, so only the cache can supply it.
METROPOLITANS: Team = ("SEA", "Seattle", "Metropolitans")
BRUINS: Team = ("BOS", "Boston", "Bruins")
CANUCKS: Team = ("VAN", "Vancouver", "Canucks")
LEAFS: Team = ("TOR", "Toronto", "Maple Leafs")
CANADIENS: Team = ("MTL", "Montréal", "Canadiens")
SENATORS: Team = ("OTT", "Ottawa", "Senators")
FLAMES: Team = ("CGY", "Calgary", "Flames")


@pytest.fixture
def default_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The builder's and loader's default directories, pointed at scratch, so
    the card's no-argument calls are the ones tested and the real `data/`
    tree can neither rescue a test nor fail it."""
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    raw.mkdir()
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", processed)
    return raw, processed


def _boxscore_dir(raw: Path) -> Path:
    return raw / "nhl" / "boxscore"


def _payload(game_id: int, home: Team, away: Team, *, season: int) -> dict[str, Any]:
    payload = boxscore_payload(
        game_id=game_id, game_state="OFF", season=season, home=home[0], away=away[0]
    )
    for side, (_, place, common) in (("homeTeam", home), ("awayTeam", away)):
        payload[side]["placeName"] = {"default": place}
        payload[side]["commonName"] = {"default": common}
    return payload


def _cache_game(
    raw: Path, game_id: int, home: Team, away: Team, *, season: int = 20242025
) -> None:
    """Written by the production cache writer, at the path `fetch_boxscore`
    uses, so the bytes are the ones the builder meets in `data/raw`."""
    _write_cache(
        _boxscore_dir(raw) / f"{game_id}.json",
        _payload(game_id, home, away, season=season),
    )


def _fixed_entries(abbrevs: set[str]) -> dict[str, str]:
    """What the builder adds whatever the cache holds: the provider aliases,
    and every abbreviation (the cache's and the aliases') naming itself."""
    fixed = dict(tn.PROVIDER_ALIASES)
    for abbrev in abbrevs | set(tn.PROVIDER_ALIASES.values()):
        fixed.setdefault(abbrev.lower(), abbrev)
    return fixed


def _alias_only_map(tmp_path: Path) -> dict[str, str]:
    empty = tmp_path / "empty_raw"
    empty.mkdir()
    return tn.build_team_name_map(empty)


def test_a_rename_outside_the_aliases_maps_under_both_names(
    tmp_path: Path, default_dirs: tuple[Path, Path]
) -> None:
    """Seattle as the Kraken in 2024-25 and the Metropolitans in 2025-26.

    The old name is in the file read first and the new one in the file read
    last, so keeping only the first spelling loses the new name and keeping
    only the latest loses the old one. Prices quoted under the old name (the
    bought history, a slate frozen before the rename) need the old name, and
    today's card needs the new one.
    """
    raw, processed = default_dirs
    old, new = "Seattle Kraken", "Seattle Metropolitans"
    # Precondition: neither name is an alias, so nothing but the cache can
    # resolve it. This is what the Utah test lacked.
    alias_only = _alias_only_map(tmp_path)
    assert tn.resolve_team(old, alias_only) is None
    assert tn.resolve_team(new, alias_only) is None

    _cache_game(raw, 2024020001, home=KRAKEN, away=BRUINS, season=20242025)
    _cache_game(raw, 2025020001, home=CANUCKS, away=METROPOLITANS, season=20252026)

    mapping = tn.build_team_name_map()  # the card's call: the default directory

    assert tn.resolve_team(old, mapping) == "SEA"
    assert tn.resolve_team(new, mapping) == "SEA"
    assert mapping == {
        "seattle kraken": "SEA",
        "kraken": "SEA",
        "seattle metropolitans": "SEA",
        "metropolitans": "SEA",
        "boston bruins": "BOS",
        "bruins": "BOS",
        "vancouver canucks": "VAN",
        "canucks": "VAN",
        **_fixed_entries({"SEA", "BOS", "VAN"}),
    }
    assert tn.cache_derived_spellings(mapping) == 8

    # The card saves the map; settlement and measurement load the saved file.
    tn.save_team_name_map(mapping)
    loaded = tn.load_team_name_map()
    assert (processed / tn.TEAM_NAMES_FILENAME).is_file()
    assert tn.resolve_team(old, loaded) == "SEA"
    assert tn.resolve_team(new, loaded) == "SEA"
    assert tn.unresolved_names([old, new, "Boston Bruins"], loaded) == []


#: The good files' map, entry for entry.
GOOD_FILES_MAP_WITHOUT_FIXED = {
    "toronto maple leafs": "TOR",
    "maple leafs": "TOR",
    "boston bruins": "BOS",
    "bruins": "BOS",
    "montreal canadiens": "MTL",
    "canadiens": "MTL",
    "ottawa senators": "OTT",
    "senators": "OTT",
}


def test_unreadable_files_add_nothing_and_stop_nothing(
    default_dirs: tuple[Path, Path],
) -> None:
    """Unreadable files before, between and after two good boxscores.

    The first is a real boxscore cut off inside `playerByGameStats`, so both
    of its team blocks (Vancouver and Calgary) are complete text that a
    salvaging parser could lift out; nothing from it may reach the map.
    """
    raw, _ = default_dirs
    directory = _boxscore_dir(raw)
    _cache_game(raw, 2024020002, home=LEAFS, away=BRUINS)
    _cache_game(raw, 2024020004, home=CANADIENS, away=SENATORS)

    whole = json.dumps(
        _payload(2024020001, CANUCKS, FLAMES, season=20242025), indent=2, sort_keys=True
    )
    truncated = whole[: whole.index('"playerByGameStats"') + 40]
    (directory / "2024020001.json").write_text(truncated, encoding="utf-8")
    (directory / "2024020003.json").write_bytes(b"")
    (directory / "2024020005.json").write_bytes(b'{"homeTeam": \xff\xfe\x00')

    # Preconditions: each corrupt file is corrupt in the way it claims, the
    # truncated one really carries both team blocks, and each good file has a
    # corrupt one read before it.
    with pytest.raises(json.JSONDecodeError):
        json.loads(truncated)
    assert '"Vancouver"' in truncated and '"Flames"' in truncated
    with pytest.raises(json.JSONDecodeError):
        json.loads((directory / "2024020003.json").read_text(encoding="utf-8"))
    with pytest.raises(UnicodeDecodeError):
        (directory / "2024020005.json").read_text(encoding="utf-8")
    assert [path.name for path in sorted(directory.glob("*.json"))] == [
        "2024020001.json",  # truncated
        "2024020002.json",  # TOR v BOS
        "2024020003.json",  # empty
        "2024020004.json",  # MTL v OTT
        "2024020005.json",  # not UTF-8
    ]

    mapping = tn.build_team_name_map()

    assert tn.resolve_team("Toronto Maple Leafs", mapping) == "TOR"
    assert tn.resolve_team("Montreal Canadiens", mapping) == "MTL"
    assert tn.resolve_team("Vancouver Canucks", mapping) is None
    assert tn.resolve_team("Calgary Flames", mapping) is None
    assert mapping == {
        **GOOD_FILES_MAP_WITHOUT_FIXED,
        **_fixed_entries({"TOR", "BOS", "MTL", "OTT"}),
    }
    assert tn.cache_derived_spellings(mapping) == 8


def test_a_boxscore_that_is_not_an_object_is_skipped_not_fatal(
    default_dirs: tuple[Path, Path],
) -> None:
    """`null` and `[]` parse, so the decode guard lets them through; before
    the fix the next line called `.get` on them and the build raised."""
    raw, _ = default_dirs
    directory = _boxscore_dir(raw)
    _cache_game(raw, 2024020002, home=LEAFS, away=BRUINS)
    _cache_game(raw, 2024020004, home=CANADIENS, away=SENATORS)
    _write_cache(directory / "2024020001.json", None)
    _write_cache(directory / "2024020003.json", [])
    assert json.loads((directory / "2024020001.json").read_text(encoding="utf-8")) is None
    assert json.loads((directory / "2024020003.json").read_text(encoding="utf-8")) == []

    mapping = tn.build_team_name_map()

    assert mapping == {
        **GOOD_FILES_MAP_WITHOUT_FIXED,
        **_fixed_entries({"TOR", "BOS", "MTL", "OTT"}),
    }
    assert tn.cache_derived_spellings(mapping) == 8
