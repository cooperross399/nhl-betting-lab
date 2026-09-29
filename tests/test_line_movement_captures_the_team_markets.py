"""Line Movement asks the bulk moneyline, puck line and total in every round.

From 2026-08-29, when the dedicated closing-line schedule was retired, the
capture that feeds the closing-line store asked only the per-event markets
and their alternate ladders (`PER_EVENT_PROVIDER_MARKETS +
ALTERNATE_PROVIDER_MARKETS`). No moneyline opinion could meet a closing
price, and a featured puck line or total only when a ladder repeated its
line; the CLV report named them uncaptured every day. Cooper decided to
capture them (2026-09-29), about 6 credits a round.

What these tests hold, through the real `capture_line_movement.main` over a
stub transport (the script needs `--live`, and no request leaves the test):

* both fetches land in one round: one day file, the same columns, the same
  `captured_at`, and the closing-line store;
* one clock, one window, one screen for the two fetches;
* the team request never costs the per-event round, and never rescues a lost
  one: an empty slate is an absence, a failure a `::warning::`, and the exit
  is the per-event round's, as it was;
* the names meet: a moneyline, puck-line and total opinion frozen from the
  bulk rows the card stages is matched to a close by
  `load_movement_captures` and the CLV report, and none is "uncaptured";
* every reader of the day file handles the new rows: the ladder scan drops
  them (a featured line is another request, not a rung of the ladder), the
  CLV loader uses them, and the site opens the moneyline from them (in
  `test_the_open_is_one_capture_and_never_a_ladder_rung.py`).
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from conftest import FakeResponse
from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import ProviderEnvLoadResult
from nhl_betting_lab.reports.card_pricing import selection_key

from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_scripts import load_script


ENVIRONMENT = {"NHL_ODDS_API_KEY": "stub-credential-never-sent"}

#: The provider class itself, before any test replaces the script's factory.
PROVIDER = odds_api.OddsApiProvider

DAY = "2026-10-15"
HOME, AWAY = "Toronto Maple Leafs", "Boston Bruins"
START = f"{DAY}T23:00:00Z"
#: Two rounds inside `CLOSE_MAX_LEAD` of face-off: the second is the close.
EARLY = datetime(2026, 10, 15, 21, 0, tzinfo=timezone.utc)
LATE = datetime(2026, 10, 15, 22, 30, tzinfo=timezone.utc)
CARD_AT = datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)
AFTER = "2027-06-01T00:00:00+00:00"

#: The featured lines the bulk endpoint carries, per round: (home ml, away
#: ml, home -1.5, away +1.5, over 6.0, under 6.0).
BULK_PRICES = {
    "card": (-150, 130, 190, -230, -110, -110),
    EARLY: (-155, 135, 185, -225, -115, -105),
    LATE: (-160, 140, 180, -220, -120, 100),
}
#: The book's own ladder: coherent on its own.
RUNGS = {5.5: (-160, 135), 6.5: (135, -160)}


def _bulk_payload(prices, *, total_over: int | None = None,
                  total_under: int | None = None) -> list[dict]:
    home_ml, away_ml, home_pl, away_pl, over, under = prices
    over = over if total_over is None else total_over
    under = under if total_under is None else total_under
    markets = [
        {"key": "h2h", "outcomes": [{"name": HOME, "price": home_ml},
                                    {"name": AWAY, "price": away_ml}]},
        {"key": "spreads", "outcomes": [{"name": HOME, "price": home_pl, "point": -1.5},
                                        {"name": AWAY, "price": away_pl, "point": 1.5}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": over, "point": 6.0},
                                       {"name": "Under", "price": under, "point": 6.0}]},
    ]
    return [{"id": "ev0", "commence_time": START, "home_team": HOME,
             "away_team": AWAY,
             "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                             "markets": markets}]}]


def _per_event_payload() -> dict:
    markets = [
        {"key": "player_shots_on_goal", "outcomes": [
            {"name": "Over", "description": "Auston Matthews", "price": -115, "point": 3.5},
            {"name": "Under", "description": "Auston Matthews", "price": -105, "point": 3.5}]},
        {"key": "alternate_totals", "outcomes": [
            outcome
            for line, (over, under) in RUNGS.items()
            for outcome in ({"name": "Over", "price": over, "point": line},
                            {"name": "Under", "price": under, "point": line})]},
    ]
    return {"id": "ev0", "commence_time": START, "home_team": HOME,
            "away_team": AWAY,
            "bookmakers": [{"key": "draftkings", "title": "DraftKings",
                            "markets": markets}]}


class Transport:
    """The events list, each game's odds, and the bulk odds."""

    def __init__(self, bulk) -> None:
        self.bulk = bulk
        self.calls: list[str] = []

    def __call__(self, url: str, **_kwargs) -> FakeResponse:
        self.calls.append(url)
        if "/events/" in url and url.endswith("/odds"):
            return FakeResponse(_per_event_payload())
        if url.endswith("/events"):
            return FakeResponse([{"id": "ev0", "commence_time": START,
                                  "home_team": HOME, "away_team": AWAY}])
        if url.endswith("/odds"):
            return self.bulk()
        raise AssertionError(f"unexpected request: {url}")


def _ok(prices, **totals):
    return lambda: FakeResponse(_bulk_payload(prices, **totals))


def _refused(status: int):
    return lambda: FakeResponse(status_code=status)


def _frozen(instant: datetime):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    return Frozen


def _round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, at: datetime,
           bulk, *, patch=None) -> tuple[int, str, str, Path]:
    """One real round of `capture_line_movement.main`, as the workflow runs it."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    module = load_script("capture_line_movement.py")
    transport = Transport(bulk)
    monkeypatch.setattr(
        module.odds_api, "OddsApiProvider",
        lambda: PROVIDER(environment=ENVIRONMENT, requester=transport, regions="us,us2"),
    )
    monkeypatch.setattr(module, "load_provider_env",
                        lambda: ProviderEnvLoadResult(path=tmp_path / ".env"))
    monkeypatch.setattr(module, "datetime", _frozen(at))
    if patch is not None:
        patch(module)
    processed = tmp_path / "processed"
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    try:
        code = module.main(["--live", "--credit-cap", "600",
                            "--processed-dir", str(processed)])
    finally:
        monkeypatch.setattr(sys, "stdout", sys.__stdout__)
        monkeypatch.setattr(sys, "stderr", sys.__stderr__)
    return code, out.getvalue(), err.getvalue(), processed


def _day_file(processed: Path) -> Path:
    return processed / "line_movement" / f"{DAY}.csv"


def _day(processed: Path) -> pd.DataFrame:
    return pd.read_csv(_day_file(processed), dtype=str, keep_default_na=False)


def _annotations(out: str, kind: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith(f"::{kind}::")]


# -- one round, two fetches ----------------------------------------------------


def test_every_round_writes_the_team_markets_beside_the_per_event_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err, processed = _round(tmp_path, monkeypatch, EARLY, _ok(BULK_PRICES[EARLY]))

    assert code == 0, out + err
    frame = _day(processed)
    stamp = EARLY.isoformat(timespec="seconds")
    # The same columns, in the same order, as a per-event round writes.
    assert list(frame.columns) == [*odds_api.PRICE_COLUMNS, "captured_at"]
    assert set(frame["captured_at"]) == {stamp}, "one round, one captured_at"
    markets = frame.groupby("market").size().to_dict()
    assert markets["moneyline"] == 2 and markets["puck_line"] == 2, markets
    # The featured 6.0 over and under, beside the ladder's four rungs.
    assert markets["total_goals"] == 6, markets
    assert markets["shots_on_goal"] == 2, markets

    team = cl.team_market_rows(frame)
    assert int(team.sum()) == 6, "exactly the bulk request's six rows"
    assert set(frame.loc[team, "market"]) == set(cl.TEAM_MARKET_KEYS)
    assert (frame.loc[~team, "fetched_at"] == stamp).all()
    assert set(frame.loc[team & (frame["market"] == "total_goals"), "line"]) == {"6.0"}

    store = pd.read_csv(cl.captures_path(processed), dtype=str, keep_default_na=False)
    assert {"moneyline", "puck_line", "total_goals"} <= set(store["market"])
    assert set(store["captured_at"]) == {stamp}
    assert "Team markets: 6 price rows from 1 of 1 events" in out, out


def test_the_two_fetches_read_one_clock_one_window_and_one_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, dict] = {}

    def patch(module) -> None:
        provider = PROVIDER
        real_props = provider.fetch_player_props
        real_team = provider.fetch_team_markets

        def props(self, **kwargs):
            seen["props"] = kwargs
            return real_props(self, **kwargs)

        def team(self, **kwargs):
            seen["team"] = kwargs
            return real_team(self, **kwargs)

        monkeypatch.setattr(provider, "fetch_player_props", props)
        monkeypatch.setattr(provider, "fetch_team_markets", team)
        monkeypatch.setattr(module, "preseason_screen",
                            lambda *_a, **_k: (lambda event: True, "screen stub"))

    code, out, err, _ = _round(tmp_path, monkeypatch, EARLY,
                               _ok(BULK_PRICES[EARLY]), patch=patch)

    assert code == 0, out + err
    assert seen["team"]["now"] == seen["props"]["now"] == EARLY
    assert seen["team"]["league_days"] == seen["props"]["league_days"] == [DAY]
    assert seen["team"]["keep_event"] is seen["props"]["keep_event"]
    assert seen["team"]["keep_event"] is not None


# -- the team request never decides the round --------------------------------


@pytest.mark.parametrize("status", [503, 429, 500])
def test_a_failed_team_request_costs_the_per_event_round_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    code, out, err, processed = _round(tmp_path, monkeypatch, EARLY, _refused(status))

    assert code == 0, f"a team failure turned a captured round red\n{out}{err}"
    frame = _day(processed)
    assert "shots_on_goal" in set(frame["market"]), "the per-event round was lost"
    assert not cl.team_market_rows(frame).any()
    warnings = _annotations(out, "warning")
    assert len(warnings) == 1, out
    assert "team-market request" in warnings[0] and f"HTTP {status}" in warnings[0], warnings[0]
    assert "absent from it, not unquoted" in warnings[0]
    assert _annotations(out, "error") == []
    assert "Team-market capture failed" in err


def test_a_team_request_that_raises_anything_costs_the_round_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def patch(module) -> None:
        def boom(self, **_kwargs):
            raise KeyError("an unexpected shape")
        monkeypatch.setattr(PROVIDER, "fetch_team_markets", boom)

    code, out, err, processed = _round(tmp_path, monkeypatch, EARLY,
                                       _ok(BULK_PRICES[EARLY]), patch=patch)

    assert code == 0, out + err
    assert "shots_on_goal" in set(_day(processed)["market"])
    warnings = _annotations(out, "warning")
    assert len(warnings) == 1 and "KeyError" in warnings[0], out


def test_an_empty_team_slate_is_an_absence_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """422 to the market list and to the plain moneyline: the provider serves
    no odds (`NoOddsServedError`), an EmptySlateError like an off-day."""
    code, out, err, processed = _round(tmp_path, monkeypatch, EARLY, _refused(422))

    assert code == 0, out + err
    assert _annotations(out, "warning") == [], out
    assert "No team markets to capture" in out
    assert "shots_on_goal" in set(_day(processed)["market"])


def test_team_rows_never_make_a_lost_per_event_round_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The events list failed: the per-event round is lost, exit 2 as it was,
    and the team rows that came back are still kept in both stores."""
    def patch(module) -> None:
        def listing_failed(self, **_kwargs):
            raise odds_api.ProviderError("The events list failed (HTTP 503).", status=503)
        monkeypatch.setattr(PROVIDER, "fetch_player_props", listing_failed)

    code, out, err, processed = _round(tmp_path, monkeypatch, EARLY,
                                       _ok(BULK_PRICES[EARLY]), patch=patch)

    assert code == 2, f"a lost per-event round read green\n{out}{err}"
    frame = _day(processed)
    assert set(frame["market"]) == set(cl.TEAM_MARKET_KEYS)
    assert cl.team_market_rows(frame).all()
    store = pd.read_csv(cl.captures_path(processed), dtype=str)
    assert set(store["market"]) == set(cl.TEAM_MARKET_KEYS)
    assert "Capture failed" in err


def test_a_round_appends_cleanly_to_a_day_file_an_older_round_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first night's rounds ran before this change and wrote per-event
    rows only. A later round the same night appends to that file, and every
    reader still reads every row of it."""
    processed = tmp_path / "processed"
    older = pd.DataFrame(odds_api.normalize_event(
        _per_event_payload(), fetched_at=EARLY.isoformat(timespec="seconds")))
    older["captured_at"] = EARLY.isoformat(timespec="seconds")
    path = _day_file(processed)
    path.parent.mkdir(parents=True)
    older.to_csv(path, index=False, lineterminator="\n")

    code, out, err, _ = _round(tmp_path, monkeypatch, LATE, _ok(BULK_PRICES[LATE]))

    assert code == 0, out + err
    unreadable: dict[str, str] = {}
    captures = cl.load_movement_captures(processed, unreadable=unreadable)
    assert unreadable == {}
    assert len(pd.read_csv(path)) == len(older) + len(older) + 6
    assert "moneyline" in set(captures["market"])
    scan = load_script("run_ladder_coherence.py")
    damaged: dict[str, str] = {}
    prices, files = scan.load_captures(path.parent, unreadable=damaged)
    assert damaged == {} and files == [path.name]
    assert not cl.team_market_rows(prices).any()


# -- the names meet: an opinion reaches its close ------------------------------


def _staged_team_opinions(tmp_path: Path) -> pd.DataFrame:
    """The team rows the card stages and freezes: `fetch_team_markets` (the
    shadow run's call), written by `write_staging` and read back."""
    transport = Transport(_ok(BULK_PRICES["card"]))
    provider = PROVIDER(environment=ENVIRONMENT, requester=transport, regions="us,us2")
    fetched = provider.fetch_team_markets(
        fetched_at=CARD_AT.isoformat(timespec="seconds"), league_days=[DAY], now=CARD_AT)
    path = odds_api.write_staging(fetched.rows, filename=odds_api.STAGING_PRICES_FILENAME,
                                  staging_dir=tmp_path / "staging")
    return pd.read_csv(path)


def _freeze(archive: Path, prices: pd.DataFrame) -> None:
    probabilities = {}
    for row in prices.itertuples():
        line = None if pd.isna(row.line) else float(row.line)
        probabilities[selection_key(row, market=row.market, selection=row.selection,
                                    line=line)] = 0.55
    assert fe.write_snapshot(
        prices, probabilities, key_for=selection_key, verdicts_line="",
        snapshot_date=DAY, now=CARD_AT, archive_dir=archive,
    ) is not None


def _report(tmp_path: Path, processed: Path) -> tuple[dict, str]:
    runner = load_script("run_closing_line_value.py")
    opinions = runner._opinions(processed, tmp_path / "archive", unreadable={})
    captures = cl.load_movement_captures(processed)
    report = cl.build_clv_report(opinions, captures,
                                 now=datetime.fromisoformat(AFTER))
    assert runner.main(["--processed-dir", str(processed),
                        "--output-dir", str(tmp_path / "outputs"),
                        "--now", AFTER,
                        "--archive-dir", str(tmp_path / "archive")]) == 0
    page = (tmp_path / "outputs" / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    return report, page


def test_a_moneyline_opinion_meets_its_close_through_the_movement_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opinions = _staged_team_opinions(tmp_path)
    assert set(opinions["market"]) == {"moneyline", "puck_line", "total_goals"}
    _freeze(tmp_path / "archive", opinions)
    for at in (EARLY, LATE):
        code, out, err, processed = _round(tmp_path, monkeypatch, at, _ok(BULK_PRICES[at]))
        assert code == 0, out + err
    # Gameday Refresh restores the line-movement chain and no dedicated
    # store, so the CLV step reads the day files (`load_movement_captures`).
    cl.captures_path(processed).unlink()

    captures = cl.load_movement_captures(processed)
    close = cl.closing_prices(captures)
    ml_home = next(
        entry for key, entry in close.items()
        if key[0] == "moneyline" and key[4] == "home"
    )
    assert float(ml_home["american_odds"]) == -160.0, "the close is the last round's price"

    report, page = _report(tmp_path, processed)

    counts = report["counts"]
    assert counts["opinions"] == 6, counts
    assert counts["matched"] == 6, f"an opinion missed its close: {counts}"
    assert counts["no_close"] == 0 and counts["no_close_uncaptured"] == 0, counts
    assert report["uncaptured"] == {}
    assert {"moneyline", "puck_line", "total_goals"} <= set(report["markets"])
    assert "`moneyline`" in page and "Of those" not in page


def test_a_round_whose_team_request_failed_names_those_opinions_uncaptured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The uncaptured split still works for the narrower reason it now has."""
    _freeze(tmp_path / "archive", _staged_team_opinions(tmp_path))
    code, out, err, processed = _round(tmp_path, monkeypatch, LATE, _refused(503))
    assert code == 0, out + err
    cl.captures_path(processed).unlink()

    report, page = _report(tmp_path, processed)

    assert report["counts"]["matched"] == 0 and report["counts"]["no_close"] == 6
    # Moneyline and puck line: no price at all for the game. The total's
    # ladder was captured, so its 6.0 is a line that market never carried
    # in that round, not a market the capture missed, as it always read.
    assert report["uncaptured"] == {"moneyline": 2, "puck_line": 2}
    assert "its request for that market failed or was not yet made" in page


# -- the ladder scan reads the ladders, not the featured line ------------------


def _scan(processed: Path, outputs: Path) -> dict:
    scan = load_script("run_ladder_coherence.py")
    assert scan.main(["--processed-dir", str(processed),
                      "--output-dir", str(outputs)]) == 0
    return json.loads((outputs / "ladder_coherence.json").read_text(encoding="utf-8"))


def test_the_ladder_scan_never_reads_the_featured_line_as_a_rung(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The featured 6.0 comes from another request. Priced so that, read as a
    rung of the same book's ladder, it contradicts the 5.5 below it by more
    than the detection floor (over 6.0 at -250 is likelier than over 5.5 at
    -160 sells). The scan must read exactly what it reads with no bulk row
    in the file."""
    code, out, err, processed = _round(
        tmp_path, monkeypatch, EARLY,
        _ok(BULK_PRICES[EARLY], total_over=-250, total_under=200))
    assert code == 0, out + err

    with_team = _scan(processed, tmp_path / "with-team")

    frame = pd.read_csv(_day_file(processed), dtype=str, keep_default_na=False)
    bulk = frame["fetched_at"] != frame["captured_at"]
    assert bulk.sum() == 6, "the fixture holds the bulk request's rows"
    bare = tmp_path / "bare"
    (bare / "line_movement").mkdir(parents=True)
    frame[~bulk].to_csv(bare / "line_movement" / f"{DAY}.csv", index=False,
                        lineterminator="\n")
    without_team = _scan(bare, tmp_path / "without-team")

    assert with_team == without_team
    assert with_team["violations"] == 0
    assert with_team["ladders_with_two_rungs"] == 1, with_team

    # Not vacuous: the same rows scanned as one ladder do contradict it.
    from nhl_betting_lab.ladder_coherence import find_violations
    found, _ = find_violations(
        frame[frame["market"] == "total_goals"]
        .assign(snapshot=frame["captured_at"], line=lambda f: f["line"].astype(float),
                american_odds=lambda f: f["american_odds"].astype(float))
    )
    assert len(found) == 1, "the fixture's featured line would read as a violation"
