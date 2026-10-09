"""The Due List's season record reaches back to opening night, and an unpriced entry takes the card's price.

Cooper (2026-10-09): "I would like for the due list to be tracked season long on
the website as if we bet .25u on each one every night". The list was first
recorded on 2026-10-07, so `drought_forward.backfill_lists` rebuilds every
regular-season night of the season before that, with the card's own
`build_drought_list` and the prices the card froze that morning, and
`fill_prices` gives an entry recorded with no price the card's frozen price.
Both are named in `drought_list/sources.json`, so a rebuilt night or a borrowed
price can never pass for one the list published.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import drought_forward as df
from test_the_drought_forward_record import AFTER, GAMES, LOGS, NAMES, ROWS
from test_the_drought_list import DAY, ROSTERS, STARTS, TEAM_NAMES, make_logs, quote

LAST_SEASON_DAY = "2026-03-01"


def _snapshot(archive: Path, day: str, quotes: list[dict]) -> Path:
    directory = archive / "priced_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{**q, "snapshot_date": day} for q in quotes])
    frame.to_csv(directory / f"{day}.csv", index=False)
    return directory


def _starts() -> dict:
    return {**STARTS, (LAST_SEASON_DAY, "EDM", "CGY"): "2026-03-01T23:00:00Z",
            ("2026-10-09", "EDM", "WPG"): "2026-10-09T23:00:00Z"}


def test_a_night_before_the_first_recorded_list_is_rebuilt_and_priced_at_the_cards_frozen_price(tmp_path: Path) -> None:
    snapshots = _snapshot(tmp_path / "archive", DAY, [quote("Assist Man", "assists", 180, "FanDuel")])
    df.record_list([dict(ROWS[0], date="2026-10-09")], "2026-10-09", processed_dir=tmp_path)

    notes = df.backfill_lists(logs=make_logs(), rosters=ROSTERS, starts=_starts(), team_names=TEAM_NAMES,
                              today="2026-10-10", snapshots=snapshots, processed_dir=tmp_path)

    rebuilt = pd.read_csv(tmp_path / "drought_list" / f"{DAY}.csv").set_index("player")
    # Every game of the night is listed: the guard is asked before the first face-off.
    assert {"Assist Man", "Test Scorer", "Point Man"} <= set(rebuilt.index), notes
    assert rebuilt.loc["Assist Man", "american_odds"] == 180 and rebuilt.loc["Assist Man", "book"] == "FanDuel"
    assert pd.isna(rebuilt.loc["Test Scorer", "american_odds"]), "no frozen price is never filled in"
    sources = df.load_sources(tmp_path)
    assert list(sources["backfilled"]) == [DAY] and sources["backfilled"][DAY]["card_prices"] is True
    # Last season's nights, and the first recorded night on, are never rebuilt.
    assert sorted(p.stem for p in (tmp_path / "drought_list").glob("*.csv")) == [DAY, "2026-10-09"]
    recorded = pd.read_csv(tmp_path / "drought_list" / "2026-10-09.csv")
    assert list(recorded["player"]) == ["Assist Man"]


def test_a_rebuilt_or_recorded_night_is_never_rebuilt_again(tmp_path: Path) -> None:
    args = dict(logs=make_logs(), rosters=ROSTERS, starts=_starts(), team_names=TEAM_NAMES,
                today="2026-10-10", snapshots=None, processed_dir=tmp_path)
    df.backfill_lists(**args)
    first = (tmp_path / "drought_list" / f"{DAY}.csv").read_bytes()
    assert df.backfill_lists(**args) == []
    assert (tmp_path / "drought_list" / f"{DAY}.csv").read_bytes() == first


def test_an_unpriced_entry_takes_the_cards_frozen_price_even_after_it_settled(tmp_path: Path) -> None:
    df.record_list(ROWS, DAY, processed_dir=tmp_path)
    df.settle_lists(LOGS, GAMES, team_names=NAMES, processed_dir=tmp_path, now=AFTER)
    before = df.load_ledger(tmp_path).set_index("player")
    assert before.loc["Not Posted", "outcome"] == "won" and before.loc["Not Posted", "profit_units"] == 0.0

    snapshots = _snapshot(tmp_path / "archive", DAY, [
        quote("Not Posted", "assists", 125, "BetMGM"), quote("Not Posted", "assists", 110, "Caesars"),
        quote("Assist Man", "assists", 400, "Other")])
    df.fill_prices(logs=LOGS, rosters={}, team_names=NAMES, snapshots=snapshots, processed_dir=tmp_path)

    listed = pd.read_csv(tmp_path / "drought_list" / f"{DAY}.csv").set_index("player")
    assert listed.loc["Not Posted", "american_odds"] == 125 and listed.loc["Not Posted", "book"] == "BetMGM"
    assert listed.loc["Assist Man", "american_odds"] == 170, "a recorded price is never replaced"
    after = df.load_ledger(tmp_path).set_index("player")
    assert after.loc["Not Posted", "american_odds"] == 125 and after.loc["Not Posted", "profit_units"] == pytest.approx(1.25)
    assert after.loc["Assist Man", "profit_units"] == pytest.approx(1.7)
    assert json.loads((tmp_path / "drought_list" / "sources.json").read_text())["filled"] == {
        DAY: [{"player_id": 5, "market": "assists", "american_odds": 125.0, "book": "BetMGM"}]}

    payload = df.build_report(df.load_ledger(tmp_path), outputs_dir=tmp_path, sources=df.load_sources(tmp_path))
    text = df.render_report(payload)
    assert payload["filled_entries"] == 1 and "at 0.25u on every priced entry" in text
    # Three priced wagers at a quarter unit: +0.425, +0.3125, -0.25.
    assert "+0.49u over 3 wager(s), 0.75u staked" in text
