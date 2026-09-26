"""A season's player registry, cached once before the season began, was its registry for the whole season.

`fetch_player_registry` served any cached registry that parsed, and
`scripts/fetch_nhl_data.py` never asked it to refresh one, although
`--skip-registry`'s help says "Do not refresh the playerId to full-name
registry". So the first answer for a season stood as the season's answer. For
2026-27 that answer came in August, before a game had been played: the stats
API answers `seasonId=20262027` with `{"data": [], "total": 0}` (checked on
2026-09-26, against 977 rows for 2025-26). Gameday Refresh run 32916019188
(2026-08-26) logged "Registry 20262027: 0 players (fetched)." and every run
after it "0 players (cache).", and the empty file travels in gameday-state,
which every run restores and uploads again. From opening night every player
whose first NHL game is in 2026-27 would have had `player = ""` in the logs;
the props model indexes no name for him, so every prop on him lands under
"Names that could not be matched": no opinion, no card, no forward-ledger
row, all season. `build_datasets.py`'s advice for nameless rows, "Run the
fetch with the registry enabled", served the same empty file again.

Found by the failure-shape sweep (finding s1x0-nhl-api-383, confirmed by all
three refuters, who replayed it through the real script: the second run made
0 stats requests and printed "(cache)"). The 2025-26 analog on the real cache,
re-measured for this fix: 160 players with a 2025-26 game are in neither
earlier registry, 58 of them played 15+ games (the model's minimum), and they
carry 3,033 of 52,478 player-game rows. 55 of the 58 were quoted in the bought
prop prices, 4,937 of 135,284 event-player-market triples.

The same function had two more ways to lose a name. It paged the stats API
with `start`/`limit` and no sort, so pages overlapped and players fell between
them: the cached 2025-26 registry holds 918 distinct players where a fetch
sorted on playerId returns 940 (its 977 rows count each traded player's
playoff row a second time), and 2024-25 holds 899 of 924. And a page that was
not a data list ended the list as if it were the last, and whatever had been
gathered was cached as the season.

What these tests hold:

* a registry fetched before its season closed (the rollover month after the
  season's second year, the boundary `config.current_season_id` already
  uses) is incomplete evidence, like an unfinished boxscore, and is asked
  again on every fetch. The exact file production carries is replaced once
  the stats API lists the players; the newcomer is then named in the logs and
  the model resolves the provider's spelling of him, which is what following
  the build script's advice now does;
* a closed season's registry, fetched after it closed and naming players, is
  read from cache and never asked again;
* an answer naming nobody is never cached, never rewrites a registry, and
  cannot settle one;
* a refresh never loses a name it had, and a fresh spelling replaces a stale
  one;
* a page that is not a data list, or paging that returns fewer rows than the
  API counts, fails the fetch and caches nothing; the run counts the registry
  as failed and exits 1 when that was its only live registry request;
* pages are asked for in playerId order, so none overlap and nobody falls
  between them, and they are paced by `--polite-seconds` like every other
  live request the script makes, since the in-play season is now asked on
  every run.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from conftest import FakeResponse, boxscore_payload
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import load_player_logs, load_player_registry
from nhl_betting_lab.models.player_props import PlayerPropsModel
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


IN_PLAY = 20262027
CLOSED = 20252026

ROOKIE_ID = 8486123
ROOKIE = "Ivan Debutant"

#: The four players `boxscore_payload` dresses by default, as the closed
#: season's registry names them, so the rookie is the only nameless player.
DEFAULT_SKATERS = {8478483: "Mitch Marner", 8480002: "Nico Hischier"}
DEFAULT_GOALIES = {8476932: "Anthony Stolarz", 8474593: "Jacob Markstrom"}

#: What Gameday Refresh wrote on 2026-08-26 and has carried in gameday-state
#: ever since: an answer from before the season, naming nobody.
AUGUST_EMPTY = {
    "seasonId": IN_PLAY,
    "fetched_at": "2026-08-26T13:48:02+00:00",
    "skaters": [],
    "goalies": [],
}


def _registry_row(player_id: int, name: str, position: str) -> dict[str, Any]:
    return {
        "playerId": player_id,
        "fullName": name,
        "positionCode": position,
        "teamAbbrevs": "TOR",
    }


def _registry(season: int, fetched_at: str | None, skaters: dict[int, str],
              goalies: dict[int, str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "seasonId": season,
        "skaters": [_registry_row(pid, name, "C") for pid, name in skaters.items()],
        "goalies": [
            _registry_row(pid, name, "G") for pid, name in (goalies or {}).items()
        ],
    }
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
    return payload


#: The closed season, fetched the day after it rolled over, as the real
#: 2025-26 file was (2026-08-25T19:29:25+00:00).
CLOSED_REGISTRY = _registry(
    CLOSED, "2026-08-25T19:29:25+00:00", DEFAULT_SKATERS, DEFAULT_GOALIES
)


def _registry_path(raw: Path, season: int) -> Path:
    return raw / "nhl" / "registry" / f"{season}.json"


def _write_registry(raw: Path, season: int, payload: Any) -> Path:
    path = _registry_path(raw, season)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _names(raw: Path, season: int) -> dict[int, str]:
    payload = json.loads(_registry_path(raw, season).read_text(encoding="utf-8"))
    return {
        int(row["playerId"]): row["fullName"]
        for role in ("skaters", "goalies")
        for row in payload[role]
    }


def _at(monkeypatch: pytest.MonkeyPatch, moment: str) -> None:
    """Fix the clock the registry stamps `fetched_at` with.

    `raising=False` so the unfixed module, which read the wall clock directly,
    still runs and fails on behaviour rather than on a missing attribute.
    """
    stamp = datetime.fromisoformat(moment)
    monkeypatch.setattr(nhl_api, "_utc_now", lambda: stamp, raising=False)


# --------------------------------------------------------------------------
# The stats API, as far as the registry uses it.
# --------------------------------------------------------------------------

def _skater(player_id: int, name: str) -> dict[str, Any]:
    return {"playerId": player_id, "skaterFullName": name, "positionCode": "C",
            "teamAbbrevs": "TOR"}


def _goalie(player_id: int, name: str) -> dict[str, Any]:
    return {"playerId": player_id, "goalieFullName": name, "positionCode": "G",
            "teamAbbrevs": "TOR"}


class StatsApi:
    """`skater/summary` and `goalie/summary` for the seasons it is given.

    `start`/`limit` paging over one season's rows, with `total` counting the
    rows, as the real endpoints answer. Unless the request sorts on
    `playerId`, each page's query is ordered its own way, as a database orders
    a paged query that has no ORDER BY: the pages overlap and players fall
    between them, which is what the real cached registries show. `broken`
    replaces the answer to one (season, role, start) with a raw body.
    """

    def __init__(
        self,
        seasons: dict[int, dict[str, list[dict[str, Any]]]],
        *,
        broken: dict[tuple[int, str, int], FakeResponse] | None = None,
    ) -> None:
        self.seasons = seasons
        self.broken = broken or {}
        self.requests: list[tuple[int, str, dict[str, Any]]] = []

    @staticmethod
    def _stable(params: dict[str, Any]) -> bool:
        try:
            keys = json.loads(str(params.get("sort", "")))
        except ValueError:
            return False
        return (
            isinstance(keys, list)
            and bool(keys)
            and isinstance(keys[0], dict)
            and keys[0].get("property") == "playerId"
        )

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        params = dict(kwargs.get("params") or {})
        role = "skaters" if url.endswith("/skater/summary") else "goalies"
        season = int(str(params["cayenneExp"]).split("=", 1)[1])
        start = int(params.get("start", 0))
        limit = int(params.get("limit", 100))
        self.requests.append((season, role, params))
        if (season, role, start) in self.broken:
            return self.broken[(season, role, start)]
        rows = list(self.seasons.get(season, {}).get(role, []))
        if self._stable(params):
            ordered = sorted(rows, key=lambda row: row["playerId"])
        else:
            ordered = sorted(
                rows, key=lambda row: (row["playerId"] * (start + 101)) % 10007
            )
        return FakeResponse(
            {"data": ordered[start:start + limit], "total": len(rows)}
        )

    def asked(self) -> set[tuple[int, str]]:
        return {(season, role) for season, role, _ in self.requests}


def _nhl(stats: StatsApi) -> Any:
    """The whole NHL API the fetch script talks to: the stats API as given,
    every club schedule empty (no game ids, so no boxscore requests)."""
    def answer(url: str, **kwargs: Any) -> FakeResponse:
        if url.startswith(nhl_api.STATS_BASE_URL):
            return stats(url, **kwargs)
        if "club-schedule-season" in url:
            return FakeResponse({"games": []})
        return FakeResponse(status_code=404)
    return answer


def _load_script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fetch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    requester: Any, *seasons: int, polite: str = "0",
) -> tuple[int, str, str]:
    """`fetch_nhl_data.py` as Gameday Refresh runs it, rosters aside."""
    monkeypatch.setattr(nhl_api, "_default_requester", requester)
    code = _load_script("fetch_nhl_data.py").main(
        ["--seasons", *(str(s) for s in seasons), "--skip-rosters",
         "--polite-seconds", polite]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------
# The production file, and the newcomer it hid.
# --------------------------------------------------------------------------

def _cache_rookie_season(raw: Path, games: int = 15) -> None:
    """`games` final 2026-27 boxscores with the rookie in Toronto's lineup:
    enough for the props model's MINIMUM_GAMES, so only his name decides
    whether he can be priced."""
    box = raw / "nhl" / "boxscore"
    box.mkdir(parents=True, exist_ok=True)
    rookie = {
        "playerId": ROOKIE_ID, "name": {"default": "I. Debutant"}, "position": "C",
        "goals": 0, "assists": 1, "points": 1, "sog": 3, "blockedShots": 1,
        "hits": 2, "powerPlayGoals": 0, "toi": "15:10",
    }
    marner = {
        "playerId": 8478483, "name": {"default": "M. Marner"}, "position": "R",
        "goals": 1, "assists": 1, "points": 2, "sog": 4, "blockedShots": 0,
        "hits": 1, "powerPlayGoals": 0, "toi": "19:48",
    }
    opening = date(2026, 10, 7)
    for index in range(games):
        day = opening + timedelta(days=2 * index)
        game_id = 2026020001 + index
        payload = boxscore_payload(
            game_id=game_id, season=IN_PLAY, game_date=day.isoformat(),
            start_time=f"{day.isoformat()}T23:00:00Z",
            home_skaters=[rookie, marner],
        )
        (box / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_the_registry_frozen_empty_in_august_is_asked_again_and_names_the_newcomer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The state the 2026-09-29 run restores: the closed season's registry,
    and 2026-27's empty one from August. By mid-November the rookie has 15
    games and the stats API lists him. Following the build script's advice
    must name him, and the model must then resolve the provider's spelling."""
    dirs = point_default_data_dirs_at(monkeypatch, tmp_path)
    raw = dirs.raw
    _write_registry(raw, CLOSED, CLOSED_REGISTRY)
    _write_registry(raw, IN_PLAY, AUGUST_EMPTY)
    _cache_rookie_season(raw)
    build = _load_script("build_datasets.py")

    # Before: his 15 rows, and only his, are nameless, and he cannot be priced.
    assert build.main([]) == 0
    advice = capsys.readouterr().out
    assert "15 player-game rows have no full name" in advice
    before = PlayerPropsModel().fit(load_player_logs(dirs.processed))
    assert ROOKIE_ID in before.skaters, "the fixture must give him enough games"
    assert before.resolve_player_in_game(ROOKIE, home="TOR", away="NJD") is None

    _at(monkeypatch, "2026-11-20T13:30:00+00:00")
    stats = StatsApi({
        CLOSED: {
            "skaters": [_skater(pid, name) for pid, name in DEFAULT_SKATERS.items()],
            "goalies": [_goalie(pid, name) for pid, name in DEFAULT_GOALIES.items()],
        },
        IN_PLAY: {
            "skaters": [_skater(ROOKIE_ID, ROOKIE), _skater(8478483, "Mitch Marner")],
            "goalies": [_goalie(8476932, "Anthony Stolarz")],
        },
    })
    code, out, err = _fetch(monkeypatch, capsys, _nhl(stats), CLOSED, IN_PLAY)

    assert code == 0, err
    assert stats.asked() == {(IN_PLAY, "skaters"), (IN_PLAY, "goalies")}, (
        "the season being played must be asked again, and the closed one never"
    )
    assert load_player_registry(raw_dir=raw)[ROOKIE_ID] == ROOKIE

    assert build.main([]) == 0
    rebuilt = capsys.readouterr().out
    assert "no full name" not in rebuilt, rebuilt
    after = PlayerPropsModel().fit(load_player_logs(dirs.processed))
    assert after.resolve_player_in_game(ROOKIE, home="TOR", away="NJD") == ROOKIE_ID
    # The advice that got him here names the script that did it, which the
    # old advice ("Run the fetch with the registry enabled") could not do.
    assert "scripts/fetch_nhl_data.py" in advice


# --------------------------------------------------------------------------
# Which cached registries are settled.
# --------------------------------------------------------------------------

def _closed_api() -> StatsApi:
    return StatsApi({CLOSED: {
        "skaters": [_skater(pid, name) for pid, name in DEFAULT_SKATERS.items()]
        + [_skater(8484801, "Macklin Celebrini")],
        "goalies": [_goalie(pid, name) for pid, name in DEFAULT_GOALIES.items()],
    }})


@pytest.mark.parametrize(
    "fetched_at",
    ["2026-08-25T19:29:25+00:00", "2026-08-01T00:00:00+00:00"],
    ids=["as-the-real-file", "on-the-day-it-closed"],
)
def test_a_closed_seasons_registry_fetched_after_it_closed_is_never_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fetched_at: str
) -> None:
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")
    path = _write_registry(
        tmp_path, CLOSED, {**CLOSED_REGISTRY, "fetched_at": fetched_at}
    )
    stats = _closed_api()

    entry = nhl_api.fetch_player_registry(CLOSED, requester=stats, raw_dir=tmp_path)

    assert stats.requests == []
    assert entry.from_cache is True
    assert entry.complete is True, "a closed season's registry is settled evidence"
    assert entry.payload == json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("cached", "why"),
    [
        (_registry(CLOSED, "2026-08-25T19:29:25+00:00", {}), "names nobody"),
        (_registry(CLOSED, "2026-04-10T13:30:00+00:00", DEFAULT_SKATERS),
         "fetched while the season was still being played"),
        (_registry(CLOSED, "2026-07-31T23:59:59+00:00", DEFAULT_SKATERS),
         "fetched the day before the season rolled over"),
        (_registry(CLOSED, None, DEFAULT_SKATERS), "says nothing of when it was fetched"),
        (_registry(CLOSED, "yesterday", DEFAULT_SKATERS), "has an unreadable stamp"),
    ],
    ids=["empty", "mid-season", "eve-of-rollover", "no-stamp", "bad-stamp"],
)
def test_a_registry_that_is_not_settled_is_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cached: dict[str, Any], why: str
) -> None:
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")
    _write_registry(tmp_path, CLOSED, cached)
    stats = _closed_api()

    entry = nhl_api.fetch_player_registry(CLOSED, requester=stats, raw_dir=tmp_path)

    assert stats.asked() == {(CLOSED, "skaters"), (CLOSED, "goalies")}, (
        f"a cached registry that {why} was served as the season's answer"
    )
    assert entry.from_cache is False
    assert _names(tmp_path, CLOSED)[8484801] == "Macklin Celebrini"
    assert entry.complete is True, "fetched after the season closed, it is now settled"
    again = nhl_api.fetch_player_registry(CLOSED, requester=stats, raw_dir=tmp_path)
    assert again.from_cache is True and len(stats.requests) == 2


def test_the_season_being_played_is_asked_on_every_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named in October, and a newcomer called up in November is named too."""
    stats = StatsApi({IN_PLAY: {"skaters": [_skater(1, "October Regular")]}})
    _at(monkeypatch, "2026-10-20T13:30:00+00:00")
    first = nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)
    assert first.complete is False, "a season still being played is never settled"

    stats.seasons[IN_PLAY]["skaters"].append(_skater(2, "November Callup"))
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")
    second = nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert second.from_cache is False
    assert _names(tmp_path, IN_PLAY) == {1: "October Regular", 2: "November Callup"}


# --------------------------------------------------------------------------
# What an answer may and may not do to the file.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("already", [None, AUGUST_EMPTY], ids=["cold", "august-file"])
def test_an_answer_naming_nobody_is_never_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, already: dict[str, Any] | None
) -> None:
    """Before opening night the stats API lists nobody for the new season.
    That is today's answer, not the season's: nothing is written, and the
    next fetch asks again."""
    path = _registry_path(tmp_path, IN_PLAY)
    if already is not None:
        _write_registry(tmp_path, IN_PLAY, already)
    before = path.read_bytes() if path.exists() else None
    stats = StatsApi({IN_PLAY: {"skaters": [], "goalies": []}})
    _at(monkeypatch, "2026-09-29T13:30:00+00:00")

    entry = nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert (path.read_bytes() if path.exists() else None) == before
    assert entry.from_cache is False and entry.complete is False
    assert entry.payload["skaters"] == [] and entry.payload["goalies"] == []
    nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)
    assert len(stats.requests) == 4, "the next fetch must ask again"


def test_an_empty_answer_after_the_season_closed_cannot_settle_its_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last in-season refresh was in April. The first run after the
    rollover gets an empty answer (a blip). Stamping the April names with a
    September time would settle them forever, and a player who debuted after
    the last refresh would never be named."""
    april = _registry(IN_PLAY, "2027-04-12T13:30:00+00:00", {1: "April Regular"})
    path = _write_registry(tmp_path, IN_PLAY, april)
    before = path.read_bytes()
    stats = StatsApi({IN_PLAY: {"skaters": [], "goalies": []}})
    _at(monkeypatch, "2027-09-29T13:30:00+00:00")

    nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert stats.asked() == {(IN_PLAY, "skaters"), (IN_PLAY, "goalies")}
    assert path.read_bytes() == before, "an answer naming nobody rewrote the file"

    stats.seasons[IN_PLAY]["skaters"] = [
        _skater(1, "April Regular"), _skater(2, "Late April Debut")
    ]
    _at(monkeypatch, "2027-09-30T13:30:00+00:00")
    settled = nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)
    assert _names(tmp_path, IN_PLAY) == {1: "April Regular", 2: "Late April Debut"}
    assert settled.complete is True


def test_a_refresh_keeps_every_name_it_had_and_takes_the_fresh_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refresh that lists fewer players (one sent down, a short answer)
    must not unname anyone already named; a corrected spelling wins."""
    _write_registry(tmp_path, IN_PLAY, _registry(
        IN_PLAY, "2026-10-20T13:30:00+00:00",
        {1: "Sent Down", 2: "Old Spelling"}, {3: "Backup Goalie"},
    ))
    stats = StatsApi({IN_PLAY: {
        "skaters": [_skater(2, "New Spelling"), _skater(4, "Newcomer")],
        "goalies": [],
    }})
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")

    nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert _names(tmp_path, IN_PLAY) == {
        1: "Sent Down", 2: "New Spelling", 3: "Backup Goalie", 4: "Newcomer"
    }
    assert load_player_registry(raw_dir=tmp_path)[2] == "New Spelling"


# --------------------------------------------------------------------------
# A page that is not an answer.
# --------------------------------------------------------------------------

def _hundred_and_fifty() -> list[dict[str, Any]]:
    return [_skater(8000000 + index, f"Player {index}") for index in range(150)]


@pytest.mark.parametrize(
    "body",
    [{"error": "Service Unavailable"}, {"data": None}, [], "x"],
    ids=["no-data", "data-null", "list", "string"],
)
@pytest.mark.parametrize("already", [None, AUGUST_EMPTY], ids=["cold", "cached"])
@pytest.mark.parametrize("start", [0, 100], ids=["first-page", "second-page"])
def test_a_page_that_is_not_a_data_list_fails_the_fetch_and_caches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: Any,
    already: dict[str, Any] | None, start: int,
) -> None:
    """On the second page the API's `total` from the first would also show
    the list short; on the first there is no total yet, and a malformed page
    read as the end of the list would be "the API lists nobody", an ok
    request, rather than a failed one."""
    path = _registry_path(tmp_path, IN_PLAY)
    if already is not None:
        _write_registry(tmp_path, IN_PLAY, already)
    before = path.read_bytes() if path.exists() else None
    stats = StatsApi(
        {IN_PLAY: {"skaters": _hundred_and_fifty(), "goalies": []}},
        broken={(IN_PLAY, "skaters", start): FakeResponse(body)},
    )
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")

    with pytest.raises(nhl_api.NhlApiError):
        nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert (path.read_bytes() if path.exists() else None) == before, (
        "the first hundred players were cached as the season"
    )


def test_paging_that_returns_fewer_rows_than_the_api_counts_fails_the_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API counts 150 and the second page stops short at 20."""
    stats = StatsApi(
        {IN_PLAY: {"skaters": _hundred_and_fifty(), "goalies": []}},
        broken={(IN_PLAY, "skaters", 100): FakeResponse({
            "data": [_skater(8000100 + index, f"Player {100 + index}")
                     for index in range(20)],
            "total": 150,
        })},
    )
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")

    with pytest.raises(nhl_api.NhlApiError, match="150"):
        nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert not _registry_path(tmp_path, IN_PLAY).exists()


def test_the_pages_are_asked_for_in_player_order_so_nobody_falls_between_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    players = [_skater(8470000 + 3 * index, f"Player {index}") for index in range(250)]
    stats = StatsApi({IN_PLAY: {"skaters": players, "goalies": []}})
    # The fake is not vacuous: paged without a sort it loses players.
    unsorted = {
        row["playerId"]
        for start in (0, 100, 200)
        for row in stats(
            f"{nhl_api.STATS_BASE_URL}/skater/summary",
            params={"limit": "100", "start": str(start),
                    "cayenneExp": f"seasonId={IN_PLAY}"},
        ).json()["data"]
    }
    assert len(unsorted) < 250
    stats.requests.clear()
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")

    nhl_api.fetch_player_registry(IN_PLAY, requester=stats, raw_dir=tmp_path)

    assert set(_names(tmp_path, IN_PLAY)) == {row["playerId"] for row in players}


# --------------------------------------------------------------------------
# The fetch script: what the run says, and how it paces the stats API.
# --------------------------------------------------------------------------

def test_a_registry_that_could_not_be_refreshed_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stats API is down mid-season. Serving October's names and calling
    the run clean is the failure this finding is: the run is degraded, and the
    names it had stand."""
    raw = tmp_path / "raw"
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    path = _write_registry(raw, IN_PLAY, _registry(
        IN_PLAY, "2026-10-20T13:30:00+00:00", {1: "October Regular"}
    ))
    before = path.read_bytes()
    asked: list[str] = []

    def down(url: str, **kwargs: Any) -> FakeResponse:
        if url.startswith(nhl_api.STATS_BASE_URL):
            asked.append(url)
            return FakeResponse(status_code=503)
        return FakeResponse({"games": []})

    _at(monkeypatch, "2026-11-20T13:30:00+00:00")
    code, out, err = _fetch(monkeypatch, capsys, down, IN_PLAY)

    assert asked, "the season being played was not asked at all"
    assert code == 1
    assert "registry" in err and "::error::" in err
    assert "Live requests, registry: 0 ok, 0 from cache, 1 failed." in out
    assert path.read_bytes() == before


def test_an_august_answer_naming_nobody_is_a_clean_run_that_caches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    stats = StatsApi({IN_PLAY: {"skaters": [], "goalies": []}})
    _at(monkeypatch, "2026-08-26T13:30:00+00:00")

    code, out, err = _fetch(monkeypatch, capsys, _nhl(stats), IN_PLAY)

    assert code == 0, err
    assert not _registry_path(raw, IN_PLAY).exists()
    assert "Live requests, registry: 1 ok, 0 from cache, 0 failed." in out
    assert f"Registry {IN_PLAY}: 0 players (fetched)" in out
    assert "nothing was cached" in out


def test_the_registry_pages_are_paced_like_every_other_live_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The season being played is now asked on every run, about a dozen
    pages; they wait `--polite-seconds` between them as the club schedules
    and rosters do. (Run 32909961346 lost 2026-27's registry to an HTTP 429.)"""
    raw = tmp_path / "raw"
    monkeypatch.setattr(nhl_api, "RAW_DIR", raw)
    players = [_skater(8470000 + index, f"Player {index}") for index in range(250)]
    stats = StatsApi({IN_PLAY: {"skaters": players,
                                "goalies": [_goalie(1, "Only Goalie")]}})
    events: list[tuple[str, Any]] = []

    def recording(url: str, **kwargs: Any) -> FakeResponse:
        if url.startswith(nhl_api.STATS_BASE_URL):
            events.append(("stats", url))
        return _nhl(stats)(url, **kwargs)

    monkeypatch.setattr("time.sleep", lambda seconds: events.append(("sleep", seconds)))
    _at(monkeypatch, "2026-11-20T13:30:00+00:00")

    code, out, err = _fetch(monkeypatch, capsys, recording, IN_PLAY, polite="0.25")

    assert code == 0, err
    first = next(i for i, (kind, _) in enumerate(events) if kind == "stats")
    tail = events[first:]
    pages = [i for i, (kind, _) in enumerate(tail) if kind == "stats"]
    assert len(pages) == 4, tail
    for previous, current in zip(pages, pages[1:]):
        assert ("sleep", 0.25) in tail[previous + 1:current], (
            f"stats pages {previous} and {current} were asked back to back"
        )
