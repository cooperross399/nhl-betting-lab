"""The Drought List's backtest: the drought count, last season's record, and the buckets each bar fills."""
import importlib.util
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "drought_rule_backtest", Path(__file__).resolve().parents[1] / "scripts" / "run_drought_rule_backtest.py")
drb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drb)


def test_drought_counts_games_before_this_one_and_resets_on_a_hit():
    assert drb.drought_before([0, 0, 1, 0, 0, 0]) == [0, 1, 2, 0, 1, 2]


def test_drought_carries_across_the_season_boundary_and_uses_last_seasons_record():
    rows = []
    for i, (season, date, goals) in enumerate([(20232024, "2024-04-01", 3), (20232024, "2024-04-03", 0),
                                               (20242025, "2024-10-10", 0), (20242025, "2024-10-12", 0)]):
        rows.append({"game_id": i, "season": season, "game_type": 2, "date": date, "player_id": 9, "player": "A B",
                     "role": "skater", "goals": goals, "assists": 0, "points": goals})
    rows.append({**rows[0], "game_id": 99, "role": "goalie", "player_id": 1})
    out = drb.prepare_logs(pd.DataFrame(rows)).set_index("date")
    assert list(out.drought_goals) == [0, 0, 1, 2]
    assert out.loc["2024-10-12", "prior_goals"] == 3          # 2023-24 total applies to 2024-25
    assert out.loc["2024-10-12", "prior_gp"] == 2 and out.loc["2024-10-12", "prior_hit_goals"] == 1
    assert out.loc["2024-10-12", "prior_hit_points"] == 1 and out.loc["2024-10-12", "prior_hit_assists"] == 0
    assert pd.isna(out.loc["2024-04-01", "prior_goals"])       # no season before the first
    assert pd.isna(out.loc["2024-04-01", "prior_gp"])
    assert 1 not in set(out.player_id)                         # goalies never qualify


def test_qualifying_bars_are_the_ones_cooper_set():
    assert drb.THRESHOLDS == {"points": 70, "goals": 30, "assists": 30}
    assert drb.TIERS == {"points": ((100, 3), (85, 4), (70, 5)), "goals": ((40, 3), (35, 4), (30, 5)),
                         "assists": ((60, 3), (45, 4), (30, 5))}
    assert drb.SURPRISE_LEVEL == 0.05
    assert drb.FLAT_DROUGHT == 5, "the #307 rule's bar, kept so the history buckets read the same"
    assert drb.SHIPPED_BUCKET == "SHIPPED: either bar" and drb.TIER_ONLY_BUCKET == "TIER bars only"
    assert drb.SURPRISE_ONLY_BUCKET == "SURPRISE 5% only"


def _wager(date, prior, hits, drought, *, gp=80, won=True, market="assists", season=2024, window="card"):
    return {"window": window, "date": date, "season": season, "market": market, "player": f"P {date}",
            "odds": 100.0, "book": "B", "dec": 2.0, "won": won, "prior": prior, "drought": drought,
            "prior_gp": gp, "prior_hits": hits}


def _wagers() -> pd.DataFrame:
    """Assists, card window: one wager per profile, each on its own night."""
    return pd.DataFrame([
        _wager("2024-11-01", 60, 60, 3),   # A: 60+ (tier 3), p .75 (surprise 3): both bars at 3
        _wager("2024-11-02", 60, 60, 2),   # B: the same player a night earlier: neither bar
        _wager("2024-11-03", 65, 40, 4),   # C: 60+ (tier 3), p .5 (surprise 5): the tier bar only, past it
        _wager("2024-11-04", 35, 60, 3),   # D: 30-44 (tier 5), p .75 (surprise 3): the surprise bar only
        _wager("2024-11-05", 35, 40, 5),   # E: 30-44, p .5: both bars, exactly at 5
        _wager("2024-11-06", 35, 40, 6),   # F: 30-44, p .5: both bars, past 5
        _wager("2024-11-07", 50, 60, 4),   # G: 45-59 (tier 4), p .75 (surprise 3): both, exactly at 4
        _wager("2024-11-08", 20, 10, 10),  # H: not a qualifier, however long the drought
        _wager("2024-11-09", 60, 0, 3),    # I: p = 0: the surprise bar is undefined; the tier bar lists him
    ])


def test_each_wager_is_labelled_with_its_band_and_both_bars():
    w = drb.label_bars(_wagers()).set_index("date")

    assert w.loc["2024-11-01", ["band", "tier_bar", "surprise_bar", "either_bar", "hit_rate"]].tolist() == ["60+", 3, 3, 3, 0.75]
    assert w.loc["2024-11-03", ["tier_bar", "surprise_bar", "either_bar"]].tolist() == [3, 5, 3]
    assert w.loc["2024-11-04", ["band", "tier_bar", "surprise_bar", "either_bar"]].tolist() == ["30-44", 5, 3, 3]
    assert w.loc["2024-11-07", ["band", "tier_bar", "surprise_bar"]].tolist() == ["45-59", 4, 3]
    assert not w.loc["2024-11-08", "qualifies"] and pd.isna(w.loc["2024-11-08", "band"])
    assert pd.isna(w.loc["2024-11-08", "tier_bar"]) and w.loc["2024-11-08", "either_bar"] == 23, (
        "a non-qualifier has no tier bar; his surprise bar (p = 0.125) exists, and `qualifies` keeps him out of every bucket")
    assert pd.isna(w.loc["2024-11-09", "surprise_bar"]) and w.loc["2024-11-09", "either_bar"] == 3
    assert w.qualifies.tolist() == [True] * 7 + [False, True]


def test_the_buckets_count_the_wagers_each_bar_lists():
    result = drb.measure(drb.label_bars(_wagers()))
    wagers = {b["bucket"]: b["wagers"] for b in result["buckets"] if b["window"] == "card" and b["season"] == "both"}

    assert wagers == {
        "not in drought (0-4)": 6, "RULE: drought 5+": 2, "drought 5-6": 2,
        "SHIPPED: either bar": 7, "TIER bars only": 6, "SURPRISE 5% only": 5,
        "TIER 60+ @3": 3, "TIER 60+ ==3": 2, "TIER 45-59 @4": 1, "TIER 45-59 ==4": 1,
        "TIER 30-44 @5": 2, "TIER 30-44 ==5": 1,
    }, "a bucket with no wager is absent; H, the non-qualifier, is in none"
    assert {b["market"] for b in result["buckets"]} == {"assists"} and {b["window"] for b in result["buckets"]} == {"card"}
    seasons = {(b["bucket"], b["season"]) for b in result["buckets"]}
    assert ("SHIPPED: either bar", "2024") in seasons and ("SHIPPED: either bar", "2025") not in seasons
    order = [b["bucket"] for b in result["buckets"] if b["season"] == "both"]
    assert order.index("RULE: drought 5+") < order.index("SHIPPED: either bar") < order.index("TIER 60+ @3") < order.index("TIER 30-44 ==5")
    for b in result["buckets"]:
        assert {"wagers", "nights", "hit_rate", "implied", "median_odds", "roi", "units", "ci_low", "ci_high", "mde"} <= set(b)
        assert b["ci_low"] <= b["roi"] <= b["ci_high"]


def test_the_json_keeps_its_keys_and_names_the_tiers_the_level_and_the_rule():
    result = drb.measure(drb.label_bars(_wagers()))
    payload = drb.payload(result, {"card": {"graded": 9}}, "2026-10-07T00:00:00+00:00")

    assert set(payload) == {"generated_at", "thresholds", "min_drought", "tiers", "surprise_level", "rule",
                            "accounting", "buckets", "goal_sweep"}
    assert payload["tiers"] == {"points": [[100, 3], [85, 4], [70, 5]], "goals": [[40, 3], [35, 4], [30, 5]],
                                "assists": [[60, 3], [45, 4], [30, 5]]}
    assert payload["surprise_level"] == 0.05 and payload["min_drought"] == 5
    assert "either" in payload["rule"] and "(1 - p)^n <= 0.05" in payload["rule"] and "100+ -> 3" in payload["rule"]
    text = drb.render(result, {"card": {"graded": 9}}, "now")
    assert text.startswith("# Drought List backtest") and "## Headline (card window, the shipped rule: either bar)" in text
    assert "| assists | 7 | 7 |" in text, "the headline row is the SHIPPED bucket"
    assert "| assists | 60+ | 3 | 3 |" in text and "| assists | 30-44 | 5 | 2 |" in text, "the per-band table"
    assert "| points | 0 | 0 |" in text, "a market with no wager is a row of zeros, not a missing row"
    assert "| assists | SURPRISE 5% only | 5 |" in text and "Drought rule" not in text


def test_the_committed_report_was_generated_by_the_shipped_rule():
    import json

    root = Path(__file__).resolve().parents[1] / "data" / "outputs"
    payload = json.loads((root / "drought_rule_backtest.json").read_text(encoding="utf-8"))
    assert payload["tiers"] == {m: [list(t) for t in tiers] for m, tiers in drb.TIERS.items()}
    assert payload["surprise_level"] == drb.SURPRISE_LEVEL and payload["rule"] == drb.RULE_SENTENCE
    buckets = {b["bucket"] for b in payload["buckets"]}
    assert {"SHIPPED: either bar", "TIER bars only", "SURPRISE 5% only", "RULE: drought 5+", "not in drought (0-4)"} <= buckets
    assert {drb.tier_bucket(drb.band_label(m, floor), bar) for m, tiers in drb.TIERS.items() for floor, bar in tiers} <= buckets
    markdown = (root / "drought_rule_backtest.md").read_text(encoding="utf-8")
    assert markdown.startswith("# Drought List backtest") and payload["generated_at"] in markdown
