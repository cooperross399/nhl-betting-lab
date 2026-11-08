"""The Season page, award races included, rebuilds after every game.

Cooper, 2026-11-08: "this should update with every game played ... for every
award". Season Sim runs hourly, builds only when a game has gone final since
the last projection, and Publish Site publishes after a Season Sim run that
uploaded one.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

_spec = importlib.util.spec_from_file_location(
    "season_sim_has_new_games", ROOT / "scripts" / "season_sim_has_new_games.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def _standings(*gp: int) -> dict:
    return {"standings": [{"gamesPlayed": g} for g in gp]}


def test_games_final_counts_each_game_once():
    assert check.games_final(_standings(10, 10, 9, 11)) == 20
    assert check.games_final({}) == 0


def test_a_new_final_builds_and_none_does_not():
    assert check.decide(100, 101)[0] is True
    assert check.decide(100, 100)[0] is False


def test_anything_unreadable_builds():
    assert check.decide(None, 100)[0] is True
    assert check.decide(100, None)[0] is True


def test_previous_games_reads_the_last_projection(tmp_path):
    path = tmp_path / "season.json"
    path.write_text(json.dumps({"leagueGamesPlayed": 212}), encoding="utf-8")
    assert check.previous_games(path) == 212
    assert check.previous_games(tmp_path / "missing.json") is None
    path.write_text("not json", encoding="utf-8")
    assert check.previous_games(path) is None


def _on(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))


def test_season_sim_runs_hourly_and_gates_every_build_step():
    wf = yaml.safe_load((WORKFLOWS / "season-sim.yml").read_text(encoding="utf-8"))
    crons = [c["cron"] for c in _on(wf)["schedule"]]
    assert "35 * * * *" in crons and "5 13 * * *" in crons
    steps = wf["jobs"]["simulate"]["steps"]
    names = [s["name"] for s in steps]
    fresh = names.index("Ask whether a game has gone final since")
    assert names.index("Restore the last projection") < fresh
    for name in ("Restore the card's team ratings", "Restore past seasons' stats",
                 "Build the season projection", "Hand the projection to Publish Site"):
        step = steps[names.index(name)]
        assert names.index(name) > fresh
        assert "steps.fresh.outputs.build == 'true'" in step["if"], name


def test_publish_site_follows_a_season_sim_that_built():
    text = (WORKFLOWS / "publish-site.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    assert "Season Sim" in _on(wf)["workflow_run"]["workflows"]
    assert "Gameday Refresh" in _on(wf)["workflow_run"]["workflows"]
    clock = wf["jobs"]["when"]["steps"][0]["run"]
    assert 'if [ "$TRIGGER" = "Season Sim" ]' in clock
    assert "grep -qx season-sim" in clock
    assert "--workflow season-sim.yml --success-only --no-merge --attempts 2 --limit 60" in text
