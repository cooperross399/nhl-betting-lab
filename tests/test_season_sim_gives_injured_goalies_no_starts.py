"""The season simulator gives a goalie who is out today no remaining starts.

Until 2026-11-10 the Season page knew a goalie was hurt only when the
hand-kept ``data/season_sim/roster_notes.json`` said so, and that file is
updated weekly. A goalie who went on injured reserve, to the minors or to
another club since then kept his usual share of every remaining game, so the
club's projected goaltending, and with it the playoff and standings odds,
were his. The sim now reads who is out today from free sources with no
account (Daily Faceoff's injured-reserve groups and tonight's starting
goalies, which the lab already captures, and each club's current NHL roster)
and these tests hold it to them, with fixtures and no network:

* a goalie Daily Faceoff lists on injured reserve, or the club's current
  roster leaves off, starts nothing for the rest of the horizon when the notes
  give no return date, and from the notes' date when they do;
* his starts go to the club's healthy goalies by their usual share, and every
  remaining game still has a starter;
* a goalie listed as tonight's confirmed, likely or expected starter is back,
  whatever else says he is out; an "Unconfirmed" listing is not enough;
* a source that did not answer moves nobody.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from season_sim.fetch import DF_STARTERS_PAGE, DF_TEAM_PAGE, fetch_availability  # noqa: E402
from season_sim.model import _remaining_starts, goalie_availability  # noqa: E402

ASOF = date(2026, 11, 10)
SCHEDULE = [dict(date=f"2026-11-{d:02d}") for d in range(10, 31)] + [dict(date=f"2026-12-{d:02d}") for d in range(1, 31)]

GOALIES = {
    "VAN": [dict(id=1, name="Thatcher Demko"), dict(id=2, name="Kevin Lankinen"), dict(id=3, name="Nikita Tolopilo")],
    "TBL": [dict(id=4, name="Andrei Vasilevskiy"), dict(id=5, name="Jonas Johansson")],
    "MTL": [dict(id=6, name="Samuel Montembeault"), dict(id=7, name="Jakub Dobeš")],
}


def _ir(name: str, team: str, status: str = "ir") -> dict:
    return dict(player=name, team_abbreviation=team, group_identifier="ir", injury_status=status)


def _starter(name: str, strength: str, day: str = "2026-11-10") -> dict:
    return dict(date=day, goalie=name, strength=strength, team="Somewhere")


def _avail(**kw) -> dict:
    base = dict(current={ab: None for ab in GOALIES}, df_players=[], df_starters=[], said=[])
    base.update(kw)
    return base


def test_a_goalie_on_injured_reserve_with_no_return_date_starts_nothing() -> None:
    avail = _avail(df_players=[_ir("Andrei Vasilevskiy", "TB")])
    updates, said = goalie_availability(avail, GOALIES, {}, ASOF)
    assert updates == {("TBL", 4): "season"}
    assert any("Andrei Vasilevskiy" in line for line in said)
    starts = _remaining_starts({4: 0.7, 5: 0.3}, {4: updates[("TBL", 4)]}, SCHEDULE)
    assert starts[4] == 0.0
    assert starts[5] == pytest.approx(len(SCHEDULE))


def test_the_notes_return_date_stands_for_an_injured_goalie() -> None:
    avail = _avail(df_players=[_ir("Thatcher Demko", "VAN", status="ltir")])
    notes = {("VAN", 1): "2026-12-21"}
    updates, said = goalie_availability(avail, GOALIES, notes, ASOF)
    assert updates == {}
    assert any("out until 2026-12-21" in line for line in said)


def test_a_goalie_off_the_current_roster_is_out_and_his_starts_go_by_share() -> None:
    avail = _avail(current={"VAN": [2, 3, 99], "TBL": None, "MTL": None})
    updates, _ = goalie_availability(avail, GOALIES, {}, ASOF)
    assert updates == {("VAN", 1): "season"}
    weights = {1: 0.6, 2: 0.3, 3: 0.1}
    starts = _remaining_starts(weights, {1: "season"}, SCHEDULE)
    assert starts[1] == 0.0
    assert starts[2] == pytest.approx(0.75 * len(SCHEDULE))
    assert starts[3] == pytest.approx(0.25 * len(SCHEDULE))
    assert sum(starts.values()) == pytest.approx(len(SCHEDULE))


def test_a_listed_starter_is_back_whatever_else_says() -> None:
    avail = _avail(df_players=[_ir("Thatcher Demko", "VAN")],
                   df_starters=[_starter("Thatcher Demko", "Confirmed")])
    updates, said = goalie_availability(avail, GOALIES, {("VAN", 1): "2026-12-21"}, ASOF)
    assert updates == {("VAN", 1): None}
    assert any("starts from today" in line for line in said)


def test_an_unconfirmed_listing_does_not_bring_him_back() -> None:
    avail = _avail(df_players=[_ir("Thatcher Demko", "VAN")],
                   df_starters=[_starter("Thatcher Demko", "Unconfirmed")])
    updates, _ = goalie_availability(avail, GOALIES, {}, ASOF)
    assert updates == {("VAN", 1): "season"}


def test_names_match_without_accents() -> None:
    avail = _avail(df_players=[_ir("Jakub Dobes", "MON")])
    updates, _ = goalie_availability(avail, GOALIES, {}, ASOF)
    assert updates == {("MTL", 7): "season"}


def test_nothing_moves_when_no_source_answered() -> None:
    assert goalie_availability(None, GOALIES, {}, ASOF) == ({}, [])
    assert goalie_availability(_avail(), GOALIES, {}, ASOF) == ({}, [])
    # a roster that answered with nobody is not read as "everyone is out"
    assert goalie_availability(_avail(current={"VAN": [], "TBL": None, "MTL": None}), GOALIES, {}, ASOF) == ({}, [])


def test_a_call_up_behind_an_injured_pair_takes_the_starts() -> None:
    # the depth chart weights only the two injured goalies; the healthy
    # call-up has no usual share and must still start every game
    starts = _remaining_starts({1: 0.6, 2: 0.4, 3: 0.0}, {1: "season", 2: "season"}, SCHEDULE)
    assert starts[1] == 0.0 and starts[2] == 0.0
    assert starts[3] == pytest.approx(len(SCHEDULE))


def test_build_model_lays_the_availability_over_the_notes_before_the_split() -> None:
    source = (WEB / "season_sim" / "model.py").read_text(encoding="utf-8")
    body = source[source.index("def build_model("):]
    lay = body.index("returns.update(avail_updates)")
    split = body.index("_remaining_starts(start_w")
    assert lay < split


# ---------------------------------------------------------------- the fetch


def _page(page_props: dict) -> str:
    payload = json.dumps({"props": {"pageProps": page_props}, "page": "/teams"})
    return f'<html><script id="__NEXT_DATA__" type="application/json">{payload}</script></html>'


def _team_page(slug: str, abbr: str, players: list[dict]) -> str:
    return _page({
        "sortedTeams": [{"slug": "toronto-maple-leafs"}, {"slug": "vancouver-canucks"}],
        "combinations": {"teamSlug": slug, "teamAbbreviation": abbr, "teamName": slug,
                         "sourceName": "Lines", "updatedAt": "2026-11-10T12:00:00Z", "players": players},
    })


def _player(name: str, group: str, status: str | None = None) -> dict:
    return {"playerId": 1, "name": name, "playerSlug": name.lower().replace(" ", "-"),
            "groupIdentifier": group, "groupName": group.upper(), "categoryIdentifier": "ev",
            "positionIdentifier": group + "1", "injuryStatus": status, "gameTimeDecision": False}


def test_fetch_availability_reads_the_pages_it_is_given(tmp_path: Path) -> None:
    pages = {
        DF_TEAM_PAGE.format(slug="toronto-maple-leafs"): _team_page(
            "toronto-maple-leafs", "TOR", [_player("Anthony Stolarz", "g")]),
        DF_TEAM_PAGE.format(slug="vancouver-canucks"): _team_page(
            "vancouver-canucks", "VAN", [_player("Kevin Lankinen", "g"), _player("Thatcher Demko", "ir", "ir")]),
        DF_STARTERS_PAGE: _page({"data": [{"date": "2026-11-10", "homeTeamName": "Vancouver Canucks",
                                           "awayTeamName": "Toronto Maple Leafs", "homeGoalieName": "Kevin Lankinen",
                                           "homeNewsStrengthName": "Confirmed"}]}),
    }
    avail = fetch_availability(tmp_path, ["TOR", "VAN"], get_text=pages.__getitem__,
                               current_roster=lambda cache, ab: [2, 3] if ab == "VAN" else None, polite_seconds=0)
    assert avail["current"] == {"TOR": None, "VAN": [2, 3]}
    assert any(r["player"] == "Thatcher Demko" and r["group_identifier"] == "ir" for r in avail["df_players"])
    assert any(r["goalie"] == "Kevin Lankinen" for r in avail["df_starters"])
    updates, _ = goalie_availability(avail, {"VAN": GOALIES["VAN"]}, {}, ASOF)
    assert updates[("VAN", 1)] == "season"
    assert ("VAN", 2) not in updates


def test_fetch_availability_is_soft_when_the_site_is_down(tmp_path: Path) -> None:
    def down(url: str) -> str:
        raise OSError("connection refused")

    def no_roster(cache, ab):
        raise OSError("blocked")

    avail = fetch_availability(tmp_path, ["VAN"], get_text=down, current_roster=no_roster, polite_seconds=0)
    assert avail["df_players"] is None and avail["df_starters"] is None
    assert avail["current"] == {"VAN": None}
    assert avail["said"]
    assert goalie_availability(avail, GOALIES, {}, ASOF) == ({}, [])
