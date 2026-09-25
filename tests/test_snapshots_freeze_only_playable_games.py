"""The forward ledger froze games already under way, and empty days that stood.

`run_gameday_card.py` hands `write_snapshot` the unguarded staged prices
before `build_card` applies the puck-drop guard, and `write_snapshot` never
looked at a start time. The provider serves live games beside upcoming ones,
so a run after a face-off froze in-play prices beside pre-game probabilities:
settlement then booked them as opinions "written down before puck drop", and
the snapshot has no freeze time, so nothing afterwards could tell them apart.
It is certain this season: the Düsseldorf Global Series game, OTT at CHI on
2026-12-20, faces off at 13:00Z and the primary Gameday Refresh fires at 13:30Z.

And a run that could price nothing — its team-name map or its models missing —
froze an EMPTY snapshot for a day with games, which then stood: the first
opinion of a day is never replaced, so every later, working run that day
froze nothing. Found by the failure-shape audit (3/3 refuters on each).

What these tests hold:

* only rows whose start the card's own rule calls playable are frozen; a
  started game and an unconfirmable start are withheld and counted;
* a slate with prices and nothing freezable writes nothing, and a later run
  can still freeze the day; an empty slate still writes its empty snapshot;
* the card run on the Global Series morning freezes only the evening game,
  and a blocked card freezes nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import selection_key


CARD_AT = datetime(2026, 12, 20, 13, 30, tzinfo=timezone.utc)


def _row(commence: str, home: str = "Chicago Blackhawks",
         away: str = "Ottawa Senators", selection: str = "home") -> dict:
    return {
        "date": "2026-12-20", "commence_time": commence,
        "provider_event_id": f"{home}-{commence}", "home_team": home,
        "away_team": away, "market": "moneyline", "player": "",
        "selection": selection, "line": None, "american_odds": 150,
        "book": "DraftKings", "fetched_at": "2026-12-20T13:25:00Z",
    }


def _opinions(rows: list[dict]) -> dict:
    return {
        selection_key(SimpleNamespace(**r), market=r["market"],
                      selection=r["selection"], line=None): 0.45
        for r in rows
    }


def _freeze(tmp_path: Path, rows: list[dict], probabilities=None, tally=None):
    return fe.write_snapshot(
        pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS)),
        _opinions(rows) if probabilities is None else probabilities,
        key_for=selection_key,
        verdicts_line="x",
        snapshot_date="2026-12-20",
        now=CARD_AT,
        archive_dir=tmp_path,
        tally=tally,
    )


def test_only_a_game_not_yet_under_way_is_frozen(tmp_path: Path) -> None:
    started = _row("2026-12-20T13:00:00Z")
    evening = _row("2026-12-21T00:30:00Z", home="Boston Bruins",
                   away="New York Rangers")
    blank = _row("", home="Dallas Stars", away="Seattle Kraken")
    naive = _row("2026-12-20T19:00:00", home="Utah Mammoth",
                 away="Calgary Flames")
    tally: dict = {}

    path = _freeze(tmp_path, [started, evening, blank, naive], tally=tally)
    frozen = pd.read_csv(path)

    assert list(frozen["home_team"]) == ["Boston Bruins"]
    assert tally == {"state": "frozen", "frozen": 1, "started": 1,
                     "unconfirmed": 2}


def test_a_slate_with_prices_and_nothing_to_freeze_writes_nothing(
    tmp_path: Path,
) -> None:
    """A blocked run priced nothing; the day must stay open for a working run."""
    rows = [_row("2026-12-21T00:30:00Z")]
    tally: dict = {}

    assert _freeze(tmp_path, rows, probabilities={}, tally=tally) is None
    assert tally["state"] == "nothing_to_freeze"
    assert not (fe.snapshots_dir(tmp_path) / "2026-12-20.csv").exists()

    later = _freeze(tmp_path, rows)
    assert later is not None and len(pd.read_csv(later)) == 1


def test_a_slate_already_under_way_writes_nothing(tmp_path: Path) -> None:
    tally: dict = {}

    assert _freeze(tmp_path, [_row("2026-12-20T13:00:00Z")], tally=tally) is None
    assert tally["state"] == "nothing_to_freeze" and tally["started"] == 1


def test_an_empty_slate_still_marks_its_day(tmp_path: Path) -> None:
    """No prices at all is a day with no games, and it is frozen as empty so
    settlement marks it done once."""
    tally: dict = {}

    path = _freeze(tmp_path, [], tally=tally)

    assert path is not None and pd.read_csv(path).empty
    assert tally["state"] == "frozen"


def test_now_is_required_and_must_be_aware(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        fe.write_snapshot(
            pd.DataFrame([_row("2026-12-21T00:30:00Z")]), {},
            key_for=selection_key, verdicts_line="x",
            snapshot_date="2026-12-20", archive_dir=tmp_path,
        )
    with pytest.raises(ValueError):
        fe.write_snapshot(
            pd.DataFrame([_row("2026-12-21T00:30:00Z")]),
            _opinions([_row("2026-12-21T00:30:00Z")]),
            key_for=selection_key, verdicts_line="x",
            snapshot_date="2026-12-20", now=datetime(2026, 12, 20, 13, 30),
            archive_dir=tmp_path,
        )


# --------------------------------------------------------------------------
# Through the card.
# --------------------------------------------------------------------------

def _card() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stage(tmp_path: Path, rows: list[dict]) -> Path:
    staging = tmp_path / "staging"
    staging.mkdir()
    pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS)).to_csv(
        staging / odds_api.STAGING_PRICES_FILENAME, index=False
    )
    return staging


def _run(module: ModuleType, tmp_path: Path, staging: Path) -> None:
    module.main(
        ["--staging-dir", str(staging),
         "--processed-dir", str(tmp_path / "processed"),
         "--output-dir", str(tmp_path / "outputs"),
         "--now", CARD_AT.isoformat()]
    )


def test_the_global_series_morning_freezes_only_the_evening_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The card's models are stubbed to price every staged row, so what is
    under test is only what reaches the snapshot."""
    started = [_row("2026-12-20T13:00:00Z", selection=s) for s in ("home", "away")]
    evening = [_row("2026-12-21T00:30:00Z", home="Boston Bruins",
                    away="New York Rangers", selection=s) for s in ("home", "away")]
    staging = _stage(tmp_path, started + evening)
    module = _card()

    class StubModel:
        report = SimpleNamespace(summary_line=lambda: "stub team model")

        def fit(self, _games):
            return self

    monkeypatch.setattr(module, "load_team_games",
                        lambda _dir: pd.DataFrame({"game_id": [1]}))
    monkeypatch.setattr(module, "TeamModel", StubModel)
    monkeypatch.setattr(
        module, "price_team_markets",
        lambda prices, model, **k: (_opinions(started + evening), []),
    )

    _run(module, tmp_path, staging)
    out = capsys.readouterr().out
    snapshot = fe.snapshots_dir(tmp_path / "outputs" / "archive") / "2026-12-20.csv"

    assert set(pd.read_csv(snapshot)["home_team"]) == {"Boston Bruins"}
    assert "2 priced row(s) for games already under way" in out


def test_a_card_that_priced_nothing_freezes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No logs and no games: the card is blocked. The day stays open."""
    staging = _stage(tmp_path, [_row("2026-12-21T00:30:00Z")])

    _run(_card(), tmp_path, staging)
    out = capsys.readouterr().out
    snapshot = fe.snapshots_dir(tmp_path / "outputs" / "archive") / "2026-12-20.csv"

    assert not snapshot.exists(), "a blocked run froze the day's first opinion"
    assert "No snapshot was frozen for 2026-12-20" in out
