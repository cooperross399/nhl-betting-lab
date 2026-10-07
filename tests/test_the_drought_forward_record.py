"""The Due List's own forward record, kept apart from the registered forward test.

Every listed row is recorded with its price to a dated file of its own, settled by the
forward ledger's rules (voids, the 14-day patience window, one row per wager at the
listed best price), and restated in `drought_rule_forward.md`. None of it may move the
registered 2027-04-25 test: `write_snapshot`'s frozen opinions, `forward_evidence.csv`
and `build_forward_report` stay byte for byte what they would have been.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import drought_forward as df
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key

DAY = "2026-10-08"
NAMES = {"edmonton oilers": "EDM", "calgary flames": "CGY", "winnipeg jets": "WPG", "montreal canadiens": "MTL"}
AFTER = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)


def listed(player_id, player, market, odds, *, home="EDM", away="CGY", team="EDM", book="DraftKings"):
    return {"date": DAY, "commence_time": f"{DAY}T23:00:00Z", "home_team": home, "away_team": away, "team": team,
            "opponent": away if team == home else home, "player": player, "player_id": player_id, "market": market,
            "selection": "over", "line": 0.5, "last_season": 31, "drought": 5,
            "american_odds": odds, "book": book if odds is not None else ""}


def box(rows):
    return pd.DataFrame([{"date": DAY, "player_id": pid, "player": name, "team": team, "shots_on_goal": 0.0,
                          "points": g + a, "goals": g, "assists": a, "blocked_shots": 0.0, "hits": 0.0, "saves": 0.0}
                         for pid, name, team, g, a in rows])


def final(home="EDM", away="CGY"):
    return pd.DataFrame([{"game_id": 1, "date": DAY, "home_team": home, "away_team": away,
                          "home_goals": 3, "away_goals": 2, "regulation": True}])


ROWS = [listed(1, "Assist Man", "assists", 170), listed(3, "Test Scorer", "goals", 210, home="WPG", away="MTL", team="WPG"),
        listed(5, "Not Posted", "assists", None), listed(6, "Never Dressed", "assists", 150)]
LOGS = box([(1, "Assist Man", "EDM", 0, 1), (3, "Test Scorer", "WPG", 0, 0), (5, "Not Posted", "EDM", 0, 1)])
GAMES = pd.concat([final(), final("WPG", "MTL").assign(game_id=2)])


def test_a_listed_row_is_recorded_with_its_price_and_a_price_is_never_replaced(tmp_path: Path) -> None:
    assert "4 row(s) recorded" in df.record_list(ROWS, DAY, processed_dir=tmp_path)
    path = tmp_path / "drought_list" / f"{DAY}.csv"
    assert len(pd.read_csv(path)) == 4

    later = [dict(ROWS[0], american_odds=300, book="Other"), dict(ROWS[2], american_odds=125, book="BetMGM"),
             listed(7, "New Qualifier", "goals", None)]
    df.record_list(later, DAY, processed_dir=tmp_path)
    got = pd.read_csv(path).set_index("player_id")

    assert got.loc[1, "american_odds"] == 170 and got.loc[1, "book"] == "DraftKings", "a recorded price stands"
    assert got.loc[5, "american_odds"] == 125 and got.loc[5, "book"] == "BetMGM", "not posted took the price a later run found"
    assert 7 in got.index and len(got) == 5


def test_an_empty_list_records_nothing(tmp_path: Path) -> None:
    assert "nothing to record" in df.record_list([], DAY, processed_dir=tmp_path)
    assert not (tmp_path / "drought_list").exists()


def test_a_listed_row_settles_by_the_forward_ledgers_rules(tmp_path: Path) -> None:
    df.record_list(ROWS, DAY, processed_dir=tmp_path)

    result = df.settle_lists(LOGS, GAMES, team_names=NAMES, processed_dir=tmp_path, now=AFTER)
    ledger = df.load_ledger(tmp_path).set_index("player")

    assert (result.days_settled, result.rows_void) == (1, 1)
    assert ledger.loc["Assist Man", "outcome"] == "won" and ledger.loc["Assist Man", "profit_units"] == pytest.approx(1.7)
    assert ledger.loc["Test Scorer", "outcome"] == "lost" and ledger.loc["Test Scorer", "profit_units"] == -1.0
    assert ledger.loc["Never Dressed", "outcome"] == "void" and ledger.loc["Never Dressed", "profit_units"] == 0.0
    assert ledger.loc["Not Posted", "outcome"] == "won" and ledger.loc["Not Posted", "profit_units"] == 0.0
    # Settled once: a second pass appends nothing, and the day is never reopened.
    df.settle_lists(LOGS, GAMES, team_names=NAMES, processed_dir=tmp_path, now=AFTER)
    assert len(df.load_ledger(tmp_path)) == 4
    assert "already settled" in df.record_list(ROWS + [listed(8, "Late", "goals", 100)], DAY, processed_dir=tmp_path)


def test_a_day_waits_inside_the_patience_window_and_is_then_written_off_unguessed(tmp_path: Path) -> None:
    df.record_list(ROWS, DAY, processed_dir=tmp_path)
    one_game = final()

    waiting = df.settle_lists(LOGS, one_game, team_names=NAMES, processed_dir=tmp_path, now=AFTER)
    assert (waiting.days_waiting, waiting.days_settled) == (1, 0) and df.load_ledger(tmp_path).empty

    late = datetime(2026, 10, 8 + df.PATIENCE_DAYS + 1, 15, 0, tzinfo=timezone.utc)
    df.settle_lists(LOGS, one_game, team_names=NAMES, processed_dir=tmp_path, now=late)
    ledger = df.load_ledger(tmp_path).set_index("player")
    assert ledger.loc["Test Scorer", "outcome"] == "unsettleable" and ledger.loc["Test Scorer", "profit_units"] == 0.0


def test_the_report_counts_wagers_not_unposted_rows_and_clusters_on_the_game(tmp_path: Path) -> None:
    df.record_list(ROWS, DAY, processed_dir=tmp_path)
    df.settle_lists(LOGS, GAMES, team_names=NAMES, processed_dir=tmp_path, now=AFTER)

    payload = df.build_report(df.load_ledger(tmp_path), pending_rows=0, outputs_dir=tmp_path)
    a, g, overall = payload["categories"]["assists"], payload["categories"]["goals"], payload["overall"]

    assert (a["listed"], a["unpriced"], a["void"], a["wagers"], a["hits"]) == (3, 1, 1, 1, 1)
    assert (g["listed"], g["wagers"], g["hits"], g["roi"]) == (1, 1, 0, -1.0)
    assert (overall["listed"], overall["wagers"], overall["hits"], overall["games"]) == (4, 2, 1, 2)
    assert overall["units"] == pytest.approx(0.7) and overall["roi"] == pytest.approx(0.35)
    text = df.render_report(payload)
    assert "Backtest, for comparison" in text and "Cooper's actual picks" not in text.split("**This is the rule's own result.**")[0]
    assert "his picks are his and are not tracked" in text and "unbounded" in text, "one game per slice cannot bound an interval"
    assert payload["categories"]["points"]["wagers"] == 0 and "n/a" in text


def test_with_nothing_settled_the_report_states_no_return(tmp_path: Path) -> None:
    text = df.render_report(df.build_report(df.load_ledger(tmp_path), pending_rows=3, outputs_dir=tmp_path))

    assert "No wager has settled yet" in text and "3 listed row(s) are waiting" in text


# -- the registered forward test does not move -----------------------------


def _registered_test(tmp_path: Path, *, with_drought: bool) -> dict[str, bytes]:
    """The registered organ end to end in `tmp_path`, with or without the drought list beside it."""
    archive, processed, outputs = tmp_path / "archive", tmp_path / "processed", tmp_path / "outputs"
    prices = pd.DataFrame([{"commence_time": "2026-10-09T00:10:00Z", "home_team": "Toronto Maple Leafs",
                            "away_team": "Boston Bruins", "market": "shots_on_goal", "player": "Auston Matthews",
                            "selection": "over", "line": 3.5, "american_odds": 120, "book": "DraftKings"}])
    row = SimpleNamespace(**prices.iloc[0].to_dict())
    probabilities = {selection_key(row, market="shots_on_goal", selection="over", line=3.5): 0.62}
    frozen_at = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
    if with_drought:
        df.record_list(ROWS, DAY, processed_dir=processed)
    fe.write_snapshot(prices, probabilities, key_for=selection_key, verdicts_line="props_b2b=in force",
                      snapshot_date=DAY, now=frozen_at, archive_dir=archive)
    logs = pd.DataFrame([{"date": DAY, "player_id": 8479318, "player": "Auston Matthews", "team": "TOR",
                          "shots_on_goal": 5.0, "points": 1.0, "goals": 1.0, "assists": 0.0,
                          "blocked_shots": 0.0, "hits": 2.0, "saves": 0.0}])
    games = pd.DataFrame([{"game_id": 1, "date": DAY, "home_team": "TOR", "away_team": "BOS",
                           "home_goals": 4, "away_goals": 2, "regulation": True}])
    names = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}
    fe.settle_snapshots(logs, games, team_names=names, archive_dir=archive, processed_dir=processed, now=AFTER)
    if with_drought:
        df.settle_lists(LOGS, GAMES, team_names=NAMES, processed_dir=processed, now=AFTER)
        df.save_report(df.build_report(df.load_ledger(processed), outputs_dir=outputs), output_dir=outputs)
    fe.save_forward_report(fe.build_forward_report(fe.load_ledger(processed)), output_dir=outputs)
    files = {}
    for base in (archive, processed, outputs):
        for path in sorted(base.rglob("*")):
            if path.is_file() and "drought" not in path.name and "drought_list" not in path.parts:
                files[str(path.relative_to(tmp_path))] = path.read_bytes()
    return files


def _scrub(files: dict[str, bytes]) -> dict[str, str]:
    """The registered files, with the one field each run stamps with the wall clock dropped."""
    out = {}
    for name, blob in files.items():
        lines = [ln for ln in blob.decode("utf-8", "replace").splitlines()
                 if "generated_at" not in ln and "Generated" not in ln]
        out[name] = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return out


def test_the_registered_forward_test_is_byte_for_byte_what_it_would_have_been(tmp_path: Path) -> None:
    plain = _registered_test(tmp_path / "plain", with_drought=False)
    beside = _registered_test(tmp_path / "beside", with_drought=True)

    strip = lambda files, root: {k.split("/", 1)[1]: v for k, v in files.items()}  # noqa: E731
    assert plain and sorted(strip(plain, "")) == sorted(strip(beside, "")), "the drought rule added or removed a registered file"
    assert any(name.endswith("forward_evidence.csv") for name in strip(plain, ""))
    assert any(name.endswith("forward_evidence.md") for name in strip(plain, ""))
    assert any("priced_snapshots" in name for name in strip(plain, ""))
    assert _scrub(strip(plain, "")) == _scrub(strip(beside, ""))


def test_the_drought_modules_write_none_of_the_registered_files() -> None:
    import ast

    root = Path(__file__).resolve().parents[1]
    reads_only = {"PATIENCE_DAYS", "_player_index", "_replace_whole", "_settle_prop_row"}
    for module in ("src/nhl_betting_lab/drought_forward.py", "src/nhl_betting_lab/drought_rule.py",
                   "scripts/run_drought_rule_forward.py"):
        tree = ast.parse((root / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("forward_evidence"):
                assert {a.name for a in node.names} <= reads_only, (module, [a.name for a in node.names])
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in ("forward_evidence.csv", "forward_evidence.md", "priced_snapshots"), module
    for registered in ("src/nhl_betting_lab/forward_evidence.py", "scripts/run_forward_evidence.py"):
        assert "drought" not in (root / registered).read_text(encoding="utf-8").lower(), registered


# -- delivery ---------------------------------------------------------------


def test_a_changed_drought_list_posts_without_calling_it_a_selection_change() -> None:
    from nhl_betting_lab.reports import card_notification as cn
    from nhl_betting_lab.reports.gameday_card import GamedayCard

    card = GamedayCard(generated_at="2026-10-08T13:30:00+00:00", card_generated=True)
    quiet = cn.decide(card, previous_fingerprint=card.selection_fingerprint())
    assert not quiet.post, "no list, no change: silence is unchanged"

    card.drought_built, card.drought_rows = True, [dict(r, heavy_juice=False) for r in ROWS]
    first = cn.decide(card, previous_fingerprint=card.selection_fingerprint())
    again = cn.decide(card, previous_fingerprint=card.selection_fingerprint(),
                      previous_drought_fingerprint=card.drought_fingerprint())
    moved = dict(ROWS[0], american_odds=500)
    priced_only = cn.decide(GamedayCard(generated_at="x", card_generated=True, drought_rows=[moved] + ROWS[1:]),
                            previous_fingerprint="", previous_drought_fingerprint=card.drought_fingerprint())

    assert first.post and first.drought_changed and not first.selections_changed
    assert not again.post, "the same names the next run is not news"
    assert not priced_only.post, "a moving price is not a changed list"
    body = cn.render_comment(card, first)
    assert cn.SELECTIONS_CHANGED_MARKER not in body and "drought list changed" in body
    assert cn.previous_drought_fingerprint_from({"drought_rows": card.drought_rows}) == card.drought_fingerprint()
    assert cn.previous_drought_fingerprint_from({"best_bets": []}) is None


def _workflow(name: str) -> dict:
    return yaml.safe_load((Path(__file__).resolve().parents[1] / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def _uses(job: dict, artifact: str) -> dict:
    return next(s for s in job["steps"] if s.get("with", {}).get("name") == artifact)


def test_the_list_file_travels_in_the_reports_artifact_that_publish_site_restores() -> None:
    jobs = _workflow("gameday-refresh.yml")["jobs"]
    job = next(j for j in jobs.values() if any(s.get("with", {}).get("name") == "gameday-reports" for s in j.get("steps", [])))
    reports = _uses(job, "gameday-reports")["with"]["path"].split()
    assert "data/outputs/drought_list.json" in reports, "Publish Site would never see the list"
    assert "data/outputs/drought_rule_forward.md" in reports
    state = _uses(job, "gameday-state")["with"]["path"].split()
    assert "data/processed" in state, "the dated lists and their ledger travel in the state artifact"
    publish = _workflow("publish-site.yml")["jobs"]["publish"]
    restore = next(s for s in publish["steps"] if "gameday-reports=data/outputs" in str(s.get("run", "")))
    assert "--artifact gameday-state" in restore["run"]


def test_the_drought_step_fails_the_run_without_degrading_it() -> None:
    text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "gameday-refresh.yml").read_text(encoding="utf-8")
    jobs = _workflow("gameday-refresh.yml")["jobs"]
    job = next(j for j in jobs.values() if any(s.get("id") == "settle" for s in j.get("steps", [])))
    step = next(s for s in job["steps"] if s.get("id") == "drought")

    assert step["continue-on-error"] is True and step["env"]["PYTHONPATH"] == "src"
    assert "scripts/run_drought_rule_forward.py" in step["run"]
    assert 'steps.drought.outcome }}" = "failure"' in text
