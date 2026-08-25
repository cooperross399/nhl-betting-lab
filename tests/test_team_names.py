from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import boxscore_payload
from nhl_betting_lab.providers import team_names as tn


def _cache(tmp_path: Path, *, abbrev: str, place: str, common: str, game_id: int = 1) -> None:
    payload = boxscore_payload(game_id=game_id, game_state="OFF")
    payload["homeTeam"]["abbrev"] = abbrev
    payload["homeTeam"]["placeName"] = {"default": place}
    payload["homeTeam"]["commonName"] = {"default": common}
    payload["awayTeam"]["abbrev"] = "BOS"
    payload["awayTeam"]["placeName"] = {"default": "Boston"}
    payload["awayTeam"]["commonName"] = {"default": "Bruins"}
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Toronto Maple Leafs", "toronto maple leafs"),
        ("Montréal Canadiens", "montreal canadiens"),
        ("St. Louis Blues", "st louis blues"),
        ("St Louis Blues", "st louis blues"),
        ("  VEGAS   GOLDEN  KNIGHTS ", "vegas golden knights"),
    ],
)
def test_normalisation_removes_representation_only(raw: str, expected: str) -> None:
    assert tn.normalize_team_name(raw) == expected


def test_a_doubled_place_word_collapses() -> None:
    """`placeName` + `commonName` doubles the word when the common name
    already contains the place. Utah is the live example."""
    assert tn.normalize_team_name("Utah Utah Hockey Club") == "utah hockey club"


def test_collapsing_cannot_merge_two_real_teams() -> None:
    """No NHL name repeats a word, so the rule is safe as well as general."""
    assert tn.normalize_team_name("New York Rangers") != tn.normalize_team_name(
        "New York Islanders"
    )


def test_the_map_is_derived_from_the_cache(tmp_path: Path) -> None:
    _cache(tmp_path, abbrev="TOR", place="Toronto", common="Maple Leafs")

    mapping = tn.build_team_name_map(tmp_path)

    assert tn.resolve_team("Toronto Maple Leafs", mapping) == "TOR"
    assert tn.resolve_team("Boston Bruins", mapping) == "BOS"


def test_a_renamed_franchise_maps_under_both_names(tmp_path: Path) -> None:
    _cache(tmp_path, abbrev="UTA", place="Utah", common="Utah Hockey Club", game_id=1)
    _cache(tmp_path, abbrev="UTA", place="Utah", common="Mammoth", game_id=2)

    mapping = tn.build_team_name_map(tmp_path)

    assert tn.resolve_team("Utah Hockey Club", mapping) == "UTA"
    assert tn.resolve_team("Utah Mammoth", mapping) == "UTA"


def test_an_abbreviation_resolves_to_itself(tmp_path: Path) -> None:
    """So a caller that already has one does not need to know that it does."""
    _cache(tmp_path, abbrev="TOR", place="Toronto", common="Maple Leafs")

    mapping = tn.build_team_name_map(tmp_path)

    assert tn.resolve_team("TOR", mapping) == "TOR"
    assert tn.resolve_team("tor", mapping) == "TOR"


def test_an_unknown_name_resolves_to_nothing_rather_than_guessing(
    tmp_path: Path,
) -> None:
    _cache(tmp_path, abbrev="TOR", place="Toronto", common="Maple Leafs")

    mapping = tn.build_team_name_map(tmp_path)

    assert tn.resolve_team("Toronto Raptors", mapping) is None
    assert tn.resolve_team("", mapping) is None


def test_unresolved_names_are_listed_for_the_caller(tmp_path: Path) -> None:
    _cache(tmp_path, abbrev="TOR", place="Toronto", common="Maple Leafs")
    mapping = tn.build_team_name_map(tmp_path)

    missing = tn.unresolved_names(
        ["Toronto Maple Leafs", "Hartford Whalers", "  "], mapping
    )

    assert missing == ["Hartford Whalers"]


def test_an_empty_cache_still_carries_the_provider_aliases(tmp_path: Path) -> None:
    mapping = tn.build_team_name_map(tmp_path)

    assert tn.resolve_team("Utah Mammoth", mapping) == "UTA"
    assert tn.resolve_team("Arizona Coyotes", mapping) == "ARI"


def test_a_corrupt_cache_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    directory = tmp_path / "nhl" / "boxscore"
    directory.mkdir(parents=True)
    (directory / "bad.json").write_text("{not json", encoding="utf-8")

    assert tn.build_team_name_map(tmp_path)


def test_the_map_round_trips_through_disk(tmp_path: Path) -> None:
    _cache(tmp_path, abbrev="TOR", place="Toronto", common="Maple Leafs")
    mapping = tn.build_team_name_map(tmp_path)

    tn.save_team_name_map(mapping, processed_dir=tmp_path / "processed")
    loaded = tn.load_team_name_map(
        processed_dir=tmp_path / "processed", raw_dir=tmp_path
    )

    assert loaded == mapping


def test_loading_without_a_saved_map_rebuilds_from_the_cache(
    tmp_path: Path,
) -> None:
    _cache(tmp_path, abbrev="TOR", place="Toronto", common="Maple Leafs")

    loaded = tn.load_team_name_map(
        processed_dir=tmp_path / "nowhere", raw_dir=tmp_path
    )

    assert tn.resolve_team("Toronto Maple Leafs", loaded) == "TOR"


def test_the_real_cache_covers_every_current_franchise() -> None:
    """Thirty-two clubs plus Arizona, which is in the historical seasons."""
    mapping = tn.build_team_name_map()
    if not mapping or len(set(mapping.values())) < 30:
        pytest.skip("The boxscore cache is not populated in this checkout.")

    assert len(set(mapping.values())) >= 32
    for name in (
        "Toronto Maple Leafs",
        "Montreal Canadiens",
        "St Louis Blues",
        "Vegas Golden Knights",
        "Utah Mammoth",
    ):
        assert tn.resolve_team(name, mapping) is not None, name
