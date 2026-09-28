"""A game the schedule marks postponed is not tonight's regular-season game.

`season.py` had two readers of the club-schedule cache, and they disagreed
about a called-off game. `scheduled_regular_season_starts`, which the
eligibility slate is built from, drops any game whose `gameScheduleState` is
stated and is not `OK`. `known_regular_season_games`, which the card's
preseason screen matches every price row against, ignored the state. A game
postponed on the day (`PPD`) stays in the NHL's cache under its original
date, and a provider that has not yet pulled it keeps listing it; its
commence time is still in the future, so the puck-drop guard passes it too.
So the screen let its rows through, the card priced them, could stake them,
and froze them into that night's snapshot. `settle_snapshots` then held the
whole night for `PATIENCE_DAYS`, because that game never finals on that
date, and appended its rows as unsettleable.

Found by the second defect sweep. What these tests hold, through the real
`main()` over the real 2026-10-01 slate (the fixture of
`test_the_card_slate_counts_unpriced_games.py`):

* a game the schedule marks `PPD` or `CNCL`, still priced by the provider,
  is screened out before pricing: not picked, not frozen, not in the slate;
* a normal night, every game `OK`, is unchanged: all eight priced, picked
  and frozen, nothing screened;
* the two readers now agree on every state, including an unstated one
  (kept: a missing state is not a called-off game) and a game whose two
  copies disagree (kept: either copy says it is on).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import config
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.season import (
    known_regular_season_games,
    scheduled_regular_season_starts,
)
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_the_card_slate_counts_unpriced_games import (
    DAY,
    SEASON,
    SLATE,
    _boxscores,
    _event,
    _game,
    _picked_games,
    _provider_name,
    _run,
    _schedule,
    _stage,
)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The same world `test_the_card_slate_counts_unpriced_games` builds."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    raw = tmp_path / "raw"
    _boxscores(raw)
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    staging = tmp_path / "staging"
    staging.mkdir()
    return SimpleNamespace(tmp=tmp_path, raw=raw, staging=staging)


def _frozen_home_teams(world) -> set[str]:
    """Every home team named in any snapshot this run froze."""
    frozen: set[str] = set()
    for path in (world.tmp / "outputs").rglob("*.csv"):
        frame = pd.read_csv(path)
        if "home_team" in frame.columns and "market" in frame.columns:
            frozen |= set(frame["home_team"].astype(str))
    return frozen


@pytest.mark.parametrize("state", ["PPD", "CNCL"])
def test_a_called_off_game_the_provider_still_lists_is_screened_out(
    world, monkeypatch, capsys, state
) -> None:
    # Vancouver's game is called off in the schedule; the provider has not
    # pulled it, so all eight games are staged with a future commence time.
    _schedule(world.raw, states={"VAN": state})
    _stage(world.staging, [_event(h, a, s) for h, a, s in SLATE])

    card, out = _run(world, monkeypatch, capsys)

    assert "the regular-season schedule does not know" in out, out
    assert "moneyline" in card["included_markets"], card["excluded_markets"]
    # Not counted as a game every market failed to price, either.
    assert card["slate_games"] == 7
    picked = _picked_games(card)
    assert _provider_name("VAN") not in picked, "priced a postponed game"
    assert picked == {_provider_name(h) for h, _, _ in SLATE if h != "VAN"}
    frozen = _frozen_home_teams(world)
    assert frozen, "nothing was frozen; the test would prove nothing"
    assert _provider_name("VAN") not in frozen, "froze a postponed game"


def test_a_normal_night_is_unchanged(world, monkeypatch, capsys) -> None:
    _schedule(world.raw)
    _stage(world.staging, [_event(h, a, s) for h, a, s in SLATE])

    card, out = _run(world, monkeypatch, capsys)

    assert "the regular-season schedule does not know" not in out
    assert "moneyline" in card["included_markets"], card["excluded_markets"]
    assert card["slate_games"] == 8
    everyone = {_provider_name(h) for h, _, _ in SLATE}
    assert _picked_games(card) == everyone
    assert everyone <= _frozen_home_teams(world)


def test_the_two_schedule_readers_agree_on_every_state(tmp_path: Path) -> None:
    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True)
    on = _game(DAY, "CBJ", "BUF", "2026-10-01T23:00:00Z")
    unstated = _game(DAY, "NJD", "PHI", "2026-10-01T23:00:00Z", state=None)
    cancelled = _game(DAY, "NYR", "TBL", "2026-10-01T23:00:00Z", state="CNCL")
    postponed = _game(DAY, "NSH", "MIN", "2026-10-02T00:00:00Z", state="PPD")
    # The state is read without regard to case or padding, by both readers.
    lower_off = _game(DAY, "UTA", "CHI", "2026-10-02T01:30:00Z", state="ppd")
    lower_on = _game(DAY, "SJS", "FLA", "2026-10-02T02:00:00Z", state=" ok ")
    split_on = _game(DAY, "CGY", "SEA", "2026-10-02T01:00:00Z")
    split_off = _game(DAY, "CGY", "SEA", "2026-10-02T01:00:00Z", state="CNCL")
    (directory / f"AAA_{SEASON}.json").write_text(json.dumps({"games": [
        on, unstated, cancelled, postponed, lower_off, lower_on,
    ]}), encoding="utf-8")
    (directory / f"CGY_{SEASON}.json").write_text(
        json.dumps({"games": [split_on]}), encoding="utf-8"
    )
    (directory / f"SEA_{SEASON}.json").write_text(
        json.dumps({"games": [split_off]}), encoding="utf-8"
    )

    known = known_regular_season_games(tmp_path)

    assert known == {
        (DAY, "CBJ", "BUF"),
        (DAY, "NJD", "PHI"),
        (DAY, "CGY", "SEA"),
        (DAY, "SJS", "FLA"),
    }
    assert known == set(scheduled_regular_season_starts(tmp_path))
