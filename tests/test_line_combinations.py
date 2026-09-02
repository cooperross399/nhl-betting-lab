"""The promotion signal, and the timestamp discipline that makes it usable."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.data import line_combinations as lc


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_line_combinations.py"


def _page(
    *,
    players: list[dict],
    updated: str = "2026-10-15T14:02:00.000Z",
    source_name: str = "Morning Skate",
    teams: list[dict] | None = None,
) -> str:
    payload = {
        "props": {
            "pageProps": {
                "sortedTeams": teams
                if teams is not None
                else [{"slug": "toronto-maple-leafs"}, {"slug": "boston-bruins"}],
                "combinations": {
                    "teamSlug": "toronto-maple-leafs",
                    "teamAbbreviation": "TOR",
                    "teamName": "Toronto Maple Leafs",
                    "sourceName": source_name,
                    "updatedAt": updated,
                    "players": players,
                },
            }
        }
    }
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


def _player(pid: int, name: str, group: str, category: str, **extra) -> dict:
    return {
        "playerId": pid,
        "name": name,
        "playerSlug": name.lower().replace(" ", "-"),
        "groupIdentifier": group,
        "groupName": group.upper(),
        "categoryIdentifier": category,
        "positionIdentifier": extra.pop("position", "lw"),
        **extra,
    }


def test_a_player_on_two_units_is_two_rows() -> None:
    """A line change and a power-play promotion move independently, and a
    promotion to PP1 with no line change is exactly the event this exists to
    catch. Collapsing them to one row per player would lose it."""
    html = _page(players=[
        _player(1, "Matthew Knies", "f1", "ev"),
        _player(1, "Matthew Knies", "pp1", "pp", position="sk1"),
    ])

    rows = lc.rows_from_page(html, retrieved_at="2026-10-15T14:05:00+00:00")

    assert len(rows) == 2
    assert {r["group_identifier"] for r in rows} == {"f1", "pp1"}
    seats = lc.deployment_rank(rows)
    assert seats[1] == {"ev": "f1", "pp": "pp1", "pk": ""}


def test_the_two_timestamps_are_kept_apart() -> None:
    """`source_updated_at` says how stale the claim is; `retrieved_at` says
    when this lab held it. Only the second establishes availability."""
    html = _page(
        players=[_player(1, "A B", "f1", "ev")],
        updated="2026-10-15T14:02:00.000Z",
    )

    row = lc.rows_from_page(html, retrieved_at="2026-10-15T18:30:00+00:00")[0]

    assert row["source_updated_at"] == "2026-10-15T14:02:00.000Z"
    assert row["retrieved_at"] == "2026-10-15T18:30:00+00:00"
    assert row["source_name"] == "Morning Skate", "provenance is kept"


def test_availability_gates_on_retrieval_never_on_the_sources_own_stamp() -> None:
    """THE LEAK THIS PREVENTS. The source publishes only its CURRENT lines and
    restates `updatedAt` freely. If availability were gated on that, a page
    fetched tonight bearing a 14:02 stamp would count as available at 14:05
    this afternoon -- and every deployment 'edge' would be manufactured out of
    information nobody held. Gate on retrieval, which cannot be restated."""
    frame = pd.DataFrame([
        # Claims to have been updated early; was not actually fetched until late.
        {"player": "late", "source_updated_at": "2026-10-15T14:02:00Z",
         "retrieved_at": "2026-10-15T23:00:00+00:00"},
        {"player": "early", "source_updated_at": "2026-10-15T14:02:00Z",
         "retrieved_at": "2026-10-15T14:05:00+00:00"},
    ])

    kept = lc.usable_before(frame, "2026-10-15T18:00:00+00:00")

    assert list(kept["player"]) == ["early"], (
        "a row fetched after the quote must never be usable at the quote"
    )


def test_a_row_with_no_readable_retrieval_time_is_dropped() -> None:
    """Unprovable availability is not the same as available."""
    frame = pd.DataFrame([
        {"player": "unknown", "retrieved_at": ""},
        {"player": "known", "retrieved_at": "2026-10-15T14:05:00+00:00"},
    ])

    kept = lc.usable_before(frame, "2026-10-15T18:00:00+00:00")

    assert list(kept["player"]) == ["known"]


def test_the_team_list_comes_from_the_page_not_a_hardcoded_thirty_two() -> None:
    """A hardcoded list rots silently: a missing team looks exactly like a
    team with no lines posted."""
    html = _page(
        players=[],
        teams=[{"slug": "a"}, {"slug": "b"}, {"slug": "a"}, {"slug": ""}],
    )

    assert lc.team_slugs(html) == ("a", "b")


def test_a_redesign_raises_rather_than_returning_the_wrong_players() -> None:
    with pytest.raises(ValueError, match="__NEXT_DATA__"):
        lc.rows_from_page("<html><body>redesigned</body></html>", retrieved_at="x")


def test_an_error_page_is_not_read_as_an_empty_roster() -> None:
    """A 200 with no payload must be loud. Silently returning zero rows would
    look identical to a team that posted no lines."""
    with pytest.raises(ValueError):
        lc.rows_from_page("<html>403 Forbidden</html>", retrieved_at="x")


def test_deployment_rank_ignores_bench_and_injury_groups() -> None:
    rows = lc.rows_from_page(
        _page(players=[
            _player(7, "Scratch Guy", "ir", "ev", position="ir1"),
            _player(8, "Bench Guy", "sk", "ev", position="sk1"),
            _player(9, "Real Guy", "d2", "ev", position="ld"),
            _player(9, "Real Guy", "pk1", "pk", position="sk1"),
        ]),
        retrieved_at="2026-10-15T14:05:00+00:00",
    )

    seats = lc.deployment_rank(rows)

    assert seats[9] == {"ev": "d2", "pp": "", "pk": "pk1"}
    assert seats[7] == {"ev": "", "pp": "", "pk": ""}, "IR carries no deployment rank"
    assert seats[8] == {"ev": "", "pp": "", "pk": ""}


def _load_script():
    spec = importlib.util.spec_from_file_location("_cap_lines", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_day_with_no_games_captures_nothing_and_is_not_a_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    fetched: list[str] = []
    monkeypatch.setattr(module, "_fetch", lambda url, **k: fetched.append(url))
    monkeypatch.setattr(module, "games_today", lambda *a, **k: 0)

    code = module.main(["--processed-dir", str(tmp_path)])

    assert code == 0
    assert "Not a fault" in capsys.readouterr().out
    assert fetched == [], "no team page is fetched on a quiet night"


def test_nothing_parsed_exits_loudly_rather_than_writing_an_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silence here looks exactly like a quiet night, which is why it is a
    non-zero exit rather than a clean one."""
    module = _load_script()
    monkeypatch.setattr(module, "games_today", lambda *a, **k: 6)
    monkeypatch.setattr(
        module, "_fetch", lambda url, **k: _page(players=[], teams=[{"slug": "x"}])
    )

    code = module.main(["--processed-dir", str(tmp_path)])

    assert code == 2
    assert not list(tmp_path.rglob("*.csv"))


def test_a_capture_appends_and_keeps_both_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    monkeypatch.setattr(module, "games_today", lambda *a, **k: 4)
    monkeypatch.setattr(
        module,
        "_fetch",
        lambda url, **k: _page(
            players=[_player(1, "A B", "f1", "ev")], teams=[{"slug": "toronto-maple-leafs"}]
        ),
    )

    assert module.main(["--processed-dir", str(tmp_path), "--polite-seconds", "0"]) == 0
    assert module.main(["--processed-dir", str(tmp_path), "--polite-seconds", "0"]) == 0

    written = list(tmp_path.rglob("*.csv"))
    assert len(written) == 1, "one file per league game date"
    frame = pd.read_csv(written[0])
    assert len(frame) == 2, "append-only; a second look is a second row"
    assert list(frame.columns) == list(lc.COLUMNS)
    assert frame["retrieved_at"].notna().all()
