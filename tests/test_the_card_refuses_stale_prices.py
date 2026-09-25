"""The card priced staged rows of any age, while the policy said twelve hours.

`data/manual/staging_provider_policy.json` sets `max_provider_run_age_hours`
to 12, policy-wide and on the `the_odds_api` entry, and
`staging_provider_policy.run_is_fresh` exists to apply it. Nothing outside the
tests ever called it: `run_gameday_card.py` read `data/staging/` and never
looked at a row's `fetched_at`. Meanwhile `docs/provider_allowlist_approval.md`
says an allowlisted market still passes "freshness" on every run, and the
allowlist evidence bundle Cooper signs receipts against says freshness "still
run[s] on every card".

Found by the failure-shape audit (3 of 3 refuters). Reproduced on the real
`main()`: prices staged on Monday 2026-10-05 14:00Z and carded on Wednesday
2026-10-07 16:00Z, 50 hours later, staked 0.5u on a Wednesday game at
Monday's price, froze it as the day's first opinion, and nothing on the card
or in the log said how old the price was — while `run_is_fresh` on the same
stamp answered "50.0 hours old, past the 12-hour limit". Gameday Refresh
fetches in the same job and never restores `data/staging/`, so no CI card was
affected; the documented operator path (`run_gameday_card.py` over an
existing staging directory) was.

What these tests hold, through the real `main()` with the models stubbed to
price whatever rows the card hands them:

* Monday's prices on Wednesday: no card, the blocker names the age and the
  limit, no unit is staked and no snapshot is frozen;
* the same prices one hour old: a card with a staked best bet, and a snapshot;
* the policy's own numbers decide — a 72-hour policy cards 50-hour prices, and
  the stricter of the policy-wide and provider limits wins in both directions;
* the OLDEST staged row decides, and a row with no timestamp is stale.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.staging_provider_policy import load_policy


#: Wednesday noon in New York; the game is that evening.
CARD_AT = datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc)
GAME_AT = "2026-10-07T23:00:00Z"
SNAPSHOT_DAY = "2026-10-07"


def _stamp(hours_before_card: float) -> str:
    moment = CARD_AT - timedelta(hours=hours_before_card)
    return moment.isoformat(timespec="seconds")


def _event(book: str = "DraftKings", home_price: int = 150) -> dict:
    """One Odds-API-shaped event: Toronto at home to Boston."""
    return {
        "id": "evt-tor-bos",
        "commence_time": GAME_AT,
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": book.lower(),
                "title": book,
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Toronto Maple Leafs", "price": home_price},
                            {"name": "Boston Bruins", "price": -180},
                        ],
                    }
                ],
            }
        ],
    }


def _stage(staging: Path, filename: str, fetched_at: str, **event) -> None:
    """Through the production writer, as a live fetch stages them."""
    odds_api.write_staging(
        odds_api.normalize_event(_event(**event), fetched_at=fetched_at),
        filename=filename,
        staging_dir=staging,
        overwrite=True,
    )


def _policy(root: Path, *, policy_wide: float, provider: float) -> Path:
    path = root / "policy" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["the_odds_api"],
                "allowed_provider_types": ["odds_api"],
                "provider_allowlist_entries": {
                    "the_odds_api": {
                        "allowlist_status": "allowed",
                        "provider_type": "odds_api",
                        "approved_at": "2026-09-24",
                        "reviewer_name": "A Reviewer",
                        "evidence_receipt_id": "a-test-receipt",
                        "required_markets": ["moneyline"],
                        "max_provider_run_age_hours": provider,
                    }
                },
                "max_provider_run_age_hours": policy_wide,
            }
        ),
        encoding="utf-8",
    )
    return path


def _card_module() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_gameday_card.py"
    spec = importlib.util.spec_from_file_location("_script_run_gameday_card", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _StubModel:
    report = SimpleNamespace(summary_line=lambda: "stub model")
    ambiguous_names: list = []

    def fit(self, _frame):
        return self


def _price_what_it_is_given(prices, _model, **_kwargs):
    """A model opinion for every moneyline row the card hands the pricer:
    Toronto 62%, Boston 38%. At +150 Toronto is a best bet; Boston at -180
    is past the juice limit."""
    opinions = {}
    for row in prices.itertuples():
        if str(row.market) != "moneyline":
            continue
        selection = str(row.selection)
        opinions[
            selection_key(row, market="moneyline", selection=selection, line=None)
        ] = 0.62 if selection == "home" else 0.38
    return opinions, []


@pytest.fixture
def card(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The real card `main()` over scratch directories, with the models
    stubbed and every default directory pointed away from the real tree."""
    raw = tmp_path / "default_raw"
    (raw / "nhl" / "boxscore").mkdir(parents=True)
    payload = boxscore_payload(game_id=1, game_state="OFF")
    payload["homeTeam"].update(
        abbrev="TOR", placeName={"default": "Toronto"},
        commonName={"default": "Maple Leafs"},
    )
    payload["awayTeam"].update(
        abbrev="BOS", placeName={"default": "Boston"},
        commonName={"default": "Bruins"},
    )
    (raw / "nhl" / "boxscore" / "1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    default_processed = tmp_path / "default_processed"
    default_processed.mkdir()
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", default_processed)
    # No schedule cache: the preseason screen abstains and says so.
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "no_schedule")

    module = _card_module()
    monkeypatch.setattr(module, "load_player_logs",
                        lambda _dir: pd.DataFrame({"player_id": [1]}))
    monkeypatch.setattr(module, "load_team_games",
                        lambda _dir: pd.DataFrame({"game_id": [1]}))
    monkeypatch.setattr(module, "PlayerPropsModel", _StubModel)
    monkeypatch.setattr(module, "TeamModel", _StubModel)
    monkeypatch.setattr(module, "current_rosters", lambda: {})
    monkeypatch.setattr(module, "price_props", lambda *a, **k: ({}, []))
    monkeypatch.setattr(module, "price_team_markets", _price_what_it_is_given)

    staging = tmp_path / "staging"
    outputs = tmp_path / "outputs"

    def run(*, policy_wide: float = 12, provider: float = 12) -> SimpleNamespace:
        policy_path = _policy(tmp_path, policy_wide=policy_wide, provider=provider)
        monkeypatch.setattr(
            module, "load_policy",
            lambda: load_policy(policy_path, repository_root=tmp_path),
        )
        code = module.main(
            [
                "--staging-dir", str(staging),
                "--processed-dir", str(tmp_path / "processed"),
                "--output-dir", str(outputs),
                "--now", CARD_AT.isoformat(),
            ]
        )
        card_json = json.loads(
            (outputs / "gameday_card.json").read_text(encoding="utf-8")
        )
        snapshot = fe.snapshots_dir(outputs / "archive") / f"{SNAPSHOT_DAY}.csv"
        return SimpleNamespace(code=code, card=card_json, snapshot=snapshot)

    return SimpleNamespace(run=run, staging=staging)


def _staked(card_json: dict) -> float:
    return sum(float(row.get("suggested_units") or 0) for row in card_json["best_bets"])


def test_prices_staged_on_monday_are_not_carded_on_wednesday(
    card, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(card.staging, odds_api.STAGING_PRICES_FILENAME, _stamp(50))

    result = card.run()
    out = capsys.readouterr().out

    assert result.code == 0
    assert result.card["card_generated"] is False
    assert any(
        "50.0 hours old, past the 12-hour limit" in item
        for item in result.card["blockers"]
    ), result.card["blockers"]
    assert result.card["best_bets"] == [] and _staked(result.card) == 0
    assert not result.snapshot.exists(), "a stale price became the day's opinion"
    assert "too old" in out


def test_the_same_prices_an_hour_old_are_carded_and_frozen(
    card, capsys: pytest.CaptureFixture[str]
) -> None:
    """The twin: without it the stale test could pass on any other blocker."""
    _stage(card.staging, odds_api.STAGING_PRICES_FILENAME, _stamp(1))

    result = card.run()
    out = capsys.readouterr().out

    assert result.card["card_generated"] is True, result.card["blockers"]
    assert result.card["blockers"] == []
    assert _staked(result.card) > 0
    assert result.snapshot.exists()
    assert "1.0 hours old" in out, "the age is printed on every run"


def test_the_policys_own_limit_decides_not_a_constant(card) -> None:
    _stage(card.staging, odds_api.STAGING_PRICES_FILENAME, _stamp(50))

    result = card.run(policy_wide=72, provider=72)

    assert result.card["card_generated"] is True, result.card["blockers"]
    assert result.snapshot.exists()


@pytest.mark.parametrize(
    ("policy_wide", "provider"), [(12, 6), (6, 12)],
    ids=["provider-entry-stricter", "policy-wide-stricter"],
)
def test_the_stricter_of_the_two_limits_wins(
    card, policy_wide: float, provider: float
) -> None:
    """Both are limits the policy states; neither may loosen the other."""
    _stage(card.staging, odds_api.STAGING_PRICES_FILENAME, _stamp(8))

    result = card.run(policy_wide=policy_wide, provider=provider)

    assert result.card["card_generated"] is False
    assert any(
        "8.0 hours old, past the 6-hour limit" in item
        for item in result.card["blockers"]
    ), result.card["blockers"]
    assert not result.snapshot.exists()


def test_the_oldest_staged_row_decides(card) -> None:
    """A fresh team fetch beside yesterday's per-event file is not a fresh
    run: `--overwrite-staging` without `--props` rewrites only the first."""
    _stage(card.staging, odds_api.STAGING_PRICES_FILENAME, _stamp(1))
    _stage(card.staging, odds_api.STAGING_PROPS_FILENAME, _stamp(50),
           book="FanDuel", home_price=155)

    result = card.run()

    assert result.card["card_generated"] is False
    assert any("50.0 hours old" in item for item in result.card["blockers"]), (
        result.card["blockers"]
    )
    assert not result.snapshot.exists()


def test_a_row_with_no_timestamp_is_stale(card) -> None:
    """A run that cannot say when it happened is the run not to trust."""
    _stage(card.staging, odds_api.STAGING_PRICES_FILENAME, _stamp(1))
    _stage(card.staging, odds_api.STAGING_PROPS_FILENAME, "",
           book="FanDuel", home_price=155)

    result = card.run()

    assert result.card["card_generated"] is False
    assert any("no timestamp" in item for item in result.card["blockers"]), (
        result.card["blockers"]
    )
    assert not result.snapshot.exists()
