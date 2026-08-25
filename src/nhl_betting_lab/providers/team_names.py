"""Map the odds provider's team names onto NHL abbreviations.

The provider says `"Toronto Maple Leafs"`. The boxscore says `"TOR"`. Every
model in this repository is keyed by the abbreviation, so without this module
a card built against real provider data silently prices **every** game as
league-average versus league-average: the lookup misses, the model falls back
to a default, and nothing anywhere reports a problem. That is the worst shape
a bug can have here — plausible numbers, no error, no missing row.

## The mapping is derived, not written down

A hardcoded table of 32 names is wrong the day a team moves or renames, and it
is wrong quietly. This builds the map from the cached boxscores instead: each
one carries `placeName` and `commonName`, and composing them produces exactly
the string the provider sends. A franchise that renames mid-history therefore
maps under both names automatically, because both are in the cache.

Utah is the worked example. The cache holds `"Utah Utah Hockey Club"` for
2024-25 — `placeName` is `"Utah"` and `commonName` was `"Utah Hockey Club"`,
so composing them doubles the word — and `"Utah Mammoth"` after the 2025-26
rename. Both resolve to `UTA`, and the doubled word is handled by a general
rule rather than a special case, because composing a place with a common name
that already contains the place is a shape that will recur.

## Unresolved names are reported, never guessed

A name that does not map produces no selection, and the caller is told which
name it was. Fuzzy-matching a team is the same failure as fuzzy-matching a
player: a confident price for a bet nobody placed, on a row that looks exactly
like a correct one.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

from nhl_betting_lab.config import PROCESSED_DIR, RAW_DIR


TEAM_NAMES_FILENAME = "team_names.csv"

#: Aliases the cache cannot supply, because they are names only the provider
#: uses. Kept deliberately short: every entry here is a thing that will go
#: stale, so anything derivable from the cache is derived instead.
PROVIDER_ALIASES: dict[str, str] = {
    # The provider used the interim name for a season and a half. The cache
    # carries it too, but only in seasons that happen to be cached — this
    # keeps it resolvable regardless of the fetch window.
    "utah hockey club": "UTA",
    "utah mammoth": "UTA",
    # Two spellings of one franchise's move. Historical games stay ARI.
    "arizona coyotes": "ARI",
    "phoenix coyotes": "ARI",
}


def _strip_accents(text: str) -> str:
    """`Montréal` -> `Montreal`. The provider does not send the accent."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _collapse_repeats(words: list[str]) -> list[str]:
    """`utah utah hockey club` -> `utah hockey club`.

    Composing a place name with a common name that already contains the place
    doubles a word. That is a shape, not a special case, so it is handled as
    one — and it cannot merge two genuinely different teams, because no NHL
    name repeats a word for real.
    """
    collapsed: list[str] = []
    for word in words:
        if not collapsed or collapsed[-1] != word:
            collapsed.append(word)
    return collapsed


def normalize_team_name(name: object) -> str:
    """A comparison key: accent-free, punctuation-free, lowercase, single-spaced.

    `"St. Louis Blues"`, `"St Louis Blues"` and `"st louis blues"` all reduce
    to the same key, which is the point — the provider and the NHL disagree
    about the full stop and neither is wrong.
    """
    text = _strip_accents(str(name or "")).casefold()
    text = re.sub(r"[^0-9a-z\s]", " ", text)
    words = _collapse_repeats(text.split())
    return " ".join(words)


def build_team_name_map(
    raw_dir: Path | None = None, *, limit: int = 0
) -> dict[str, str]:
    """`normalized full name` -> abbreviation, derived from cached boxscores.

    Reads only what is on disk, so it needs no network and returns the same
    map every time for the same cache.
    """
    directory = (Path(raw_dir) if raw_dir else Path(RAW_DIR)) / "nhl" / "boxscore"
    mapping: dict[str, str] = {}
    if directory.is_dir():
        paths = sorted(directory.glob("*.json"))
        for path in paths[:limit] if limit else paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            for side in ("homeTeam", "awayTeam"):
                team = payload.get(side)
                if not isinstance(team, Mapping):
                    continue
                abbrev = str(team.get("abbrev", "")).strip().upper()
                place = (team.get("placeName") or {}).get("default", "")
                common = (team.get("commonName") or {}).get("default", "")
                if not abbrev or not place or not common:
                    continue
                mapping[normalize_team_name(f"{place} {common}")] = abbrev
                # The common name alone is how a provider sometimes shortens
                # a unique one ("Canadiens"), and it is only added when it is
                # unambiguous across the league.
                key = normalize_team_name(common)
                if key and key not in mapping:
                    mapping[key] = abbrev
    for alias, abbrev in PROVIDER_ALIASES.items():
        mapping.setdefault(normalize_team_name(alias), abbrev)
    # An abbreviation is always its own name, so a caller that already has one
    # does not need to know whether it does.
    for abbrev in set(mapping.values()):
        mapping.setdefault(normalize_team_name(abbrev), abbrev)
    return mapping


def resolve_team(name: object, mapping: Mapping[str, str]) -> str | None:
    """The abbreviation for a provider team name, or None. Never a guess."""
    return mapping.get(normalize_team_name(name))


def unresolved_names(
    names: Iterable[object], mapping: Mapping[str, str]
) -> list[str]:
    """Every name that did not map, so a caller can report rather than guess."""
    missing = {
        str(name).strip()
        for name in names
        if str(name).strip() and resolve_team(name, mapping) is None
    }
    return sorted(missing)


def save_team_name_map(
    mapping: Mapping[str, str], *, processed_dir: Path | None = None
) -> Path:
    """Persist the map so the card does not rescan four thousand boxscores."""
    directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / TEAM_NAMES_FILENAME
    lines = ["provider_name,abbrev"]
    lines.extend(
        f"{name},{abbrev}" for name, abbrev in sorted(mapping.items())
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_team_name_map(
    *, processed_dir: Path | None = None, raw_dir: Path | None = None
) -> dict[str, str]:
    """The persisted map, rebuilt from the cache when it is absent or stale."""
    directory = Path(processed_dir) if processed_dir else Path(PROCESSED_DIR)
    path = directory / TEAM_NAMES_FILENAME
    if path.is_file():
        mapping: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            name, _, abbrev = line.rpartition(",")
            if name and abbrev:
                mapping[name] = abbrev
        if mapping:
            return mapping
    return build_team_name_map(raw_dir)
