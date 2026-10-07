"""Cooper's drought list, through the card's real `main()`, on a night with and without prices.

The qualifiers need only the logs, the rosters and the schedule, so a card blocked for
prices still lists them with "not posted"; a staged price for the player shows with its
book; the list is written for the site and recorded for settlement; and nothing about
the card's own selections, stakes or frozen opinions changes because it is there.
"""

from __future__ import annotations

import json
import pandas as pd
import pytest
from pathlib import Path

from nhl_betting_lab import config, verdicts
from nhl_betting_lab.data import nhl_api
from nhl_betting_lab.data.build_datasets import PLAYER_LOG_COLUMNS, PLAYER_LOGS_FILENAME
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers import team_names as tn

import test_the_card_reads_the_dirs_it_is_given as base


@pytest.fixture
def raw_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, value in (("default_raw", None), ("default_processed", None), ("default_outputs", None)):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "default_raw")
    monkeypatch.setattr(nhl_api, "RAW_DIR", tmp_path / "default_raw")
    monkeypatch.setattr(tn, "RAW_DIR", tmp_path / "default_raw")
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", tmp_path / "default_outputs")
    raw = tmp_path / "raw"
    base._boxscore(raw, 1, "TOR", "BOS")
    base._boxscore(raw, 2, "MTL", "OTT")
    base._schedules(raw)
    base._roster(raw)
    base._tables(tmp_path / "processed")
    return raw


def _add_last_season(processed: Path) -> None:
    """Skater 1 (TOR): 35 assists in 70 games in 2025-26 (35 without one first, so his hit rate is 0.5 and
    the drought entering this season starts at zero), then five games this October without one."""
    path = processed / PLAYER_LOGS_FILENAME
    logs = pd.read_csv(path)
    template = logs[logs.player_id == 1].iloc[-1].to_dict()
    rows = []
    for i in range(35):
        rows.append({**template, "game_id": 6000 + i, "season": 20252026, "date": f"2025-11-{1 + i % 28:02d}",
                     "goals": 0, "assists": 0, "points": 0})
    for i in range(35):
        rows.append({**template, "game_id": 7000 + i, "season": 20252026, "date": f"2026-01-{1 + i % 28:02d}",
                     "goals": 0, "assists": 1, "points": 1})
    for i in range(5):
        rows.append({**template, "game_id": 8000 + i, "season": 20262027, "date": f"2026-10-{1 + i:02d}",
                     "goals": 0, "assists": 0, "points": 0})
    pd.concat([logs, pd.DataFrame(rows, columns=list(PLAYER_LOG_COLUMNS))]).to_csv(path, index=False)


def _props(staging: Path, odds: int, book: str) -> None:
    pd.DataFrame([{"date": "2026-10-15", "commence_time": "2026-10-15T23:00:00Z", "provider_event_id": "evt-TOR",
                   "home_team": base.PROVIDER["TOR"], "away_team": base.PROVIDER["BOS"], "market": "assists",
                   "player": "Skater 1", "selection": "over", "line": 0.5, "american_odds": odds, "book": book,
                   "fetched_at": "2026-10-15T11:00:00Z"}],
                 columns=list(odds_api.PRICE_COLUMNS)).to_csv(staging / odds_api.STAGING_PROPS_FILENAME, index=False)


def test_a_card_with_no_prices_still_publishes_the_list_with_not_posted(tmp_path, raw_dirs, capsys) -> None:
    _add_last_season(tmp_path / "processed")

    out, card, _ = base._run(tmp_path, capsys, "--raw-dir", str(raw_dirs))

    assert card["card_generated"] is False and card["blockers"], "no prices: the card is blocked"
    assert [(r["player"], r["market"], r["drought"], r["last_season"], r["team"], r["opponent"], r["american_odds"])
            for r in card["drought_rows"]] == [("Skater 1", "assists", 5, 35, "TOR", "BOS", None)]
    row = card["drought_rows"][0]
    assert (row["tier_bar"], row["surprise_bar"], row["hit_rate"], row["rarity"], row["rule"], row["band"]) == (
        5, 5, 0.5, 0.0312, "both", "30-44")
    committed = json.loads((Path(__file__).resolve().parents[1] / "data" / "outputs" / "drought_rule_backtest.json")
                           .read_text(encoding="utf-8"))
    bucket = next(b for b in committed["buckets"] if b["window"] == "card" and b["season"] == "both"
                  and b["market"] == "assists" and b["bucket"] == "TIER 30-44 @5")
    assert row["cell_record"] == {k: bucket[k] for k in ("wagers", "roi", "ci_low", "ci_high")}, (
        "the band's record is read from the committed backtest through the card's own main()")
    markdown = (tmp_path / "outputs" / "gameday_card.md").read_text(encoding="utf-8")
    section = markdown[markdown.index("## Drought List"):]
    assert "Skater 1" in section and "not posted" in section and "over 0.5" in section
    assert "| 5 (both) | tier 5 / surprise 5 | 1 in 32 for him | band 30-44 @5: " in section
    assert "Backtest" in section.splitlines()[2], "one headline line under the heading"
    assert "Drought rule" not in markdown
    listed = json.loads((tmp_path / "outputs" / "drought_list.json").read_text(encoding="utf-8"))
    assert listed["day"] == "2026-10-15" and listed["rows"][0]["american_odds"] is None
    assert listed["rows"][0]["rule"] == "both" and listed["rows"][0]["cell_record"]["wagers"] == bucket["wagers"]
    recorded = pd.read_csv(tmp_path / "processed" / "drought_list" / "2026-10-15.csv")
    assert recorded.player.tolist() == ["Skater 1"] and recorded.american_odds.isna().all()
    assert "Drought list for 2026-10-15: 1 row(s), 1 with no price posted" in out


def test_a_staged_price_shows_with_its_book(tmp_path, raw_dirs, capsys) -> None:
    _add_last_season(tmp_path / "processed")
    base._slate(tmp_path / "staging", base.TONIGHT)
    _props(tmp_path / "staging", 175, "FanDuel")

    _, card, _ = base._run(tmp_path, capsys, "--raw-dir", str(raw_dirs))

    row = card["drought_rows"][0]
    assert (row["player"], row["american_odds"], row["book"], row["heavy_juice"]) == ("Skater 1", 175, "FanDuel", False)
    assert "+175" in (tmp_path / "outputs" / "gameday_card.md").read_text(encoding="utf-8")


def test_the_cards_own_selections_stakes_and_frozen_opinions_do_not_move(tmp_path, raw_dirs, capsys, monkeypatch) -> None:
    import shutil

    from nhl_betting_lab import drought_rule

    _add_last_season(tmp_path / "processed")
    base._slate(tmp_path / "staging", base.TONIGHT)
    _props(tmp_path / "staging", 175, "FanDuel")
    outputs = tmp_path / "outputs"

    _, with_list, _ = base._run(tmp_path, capsys, "--raw-dir", str(raw_dirs))
    frozen_with = {p.name: p.read_bytes() for p in outputs.rglob("priced_snapshots/*.csv")}
    shutil.rmtree(outputs)
    shutil.rmtree(tmp_path / "processed" / "drought_list")
    monkeypatch.setattr(drought_rule, "build_drought_list",
                        lambda **kw: drought_rule.DroughtList(day=kw["day"]))
    _, without, _ = base._run(tmp_path, capsys, "--raw-dir", str(raw_dirs))
    frozen_without = {p.name: p.read_bytes() for p in outputs.rglob("priced_snapshots/*.csv")}

    assert with_list["drought_rows"] and not without["drought_rows"]
    strip = lambda card: {k: v for k, v in card.items() if not k.startswith("drought_")}  # noqa: E731
    assert strip(with_list) == strip(without), "the list changed something of the card's own"
    assert frozen_with and frozen_with == frozen_without, "the frozen opinions moved"
    assert with_list["best_bets"] or with_list["leans"] or with_list["passes"]


def test_nobody_qualifying_is_an_empty_list_not_a_missing_section(tmp_path, raw_dirs, capsys) -> None:
    _, card, _ = base._run(tmp_path, capsys, "--raw-dir", str(raw_dirs))

    assert card["drought_built"] is True and card["drought_rows"] == []
    assert "Nobody on tonight's slate qualifies" in (tmp_path / "outputs" / "gameday_card.md").read_text(encoding="utf-8")
    assert not (tmp_path / "processed" / "drought_list").exists(), "an empty list records nothing"
