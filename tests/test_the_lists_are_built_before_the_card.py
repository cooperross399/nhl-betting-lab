"""The Due List and Hot List are built at 3 AM, before the card (Cooper, 2026-11-27).

`scripts/build_early_lists.py` writes today's `drought_list.json` and
`hot_list.json` from the logs, rosters and schedule, leaves a list already
built for today (the card's) alone, and records nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

from test_the_hot_list import DAY, logs

ROOT = Path(__file__).resolve().parents[1]
NOW = f"{DAY}T08:00:00+00:00"  # 3 AM New York


def script(monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("build_early_lists", ROOT / "scripts" / "build_early_lists.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "scheduled_regular_season_starts", lambda raw=None: {(DAY, "TOR", "MTL"): f"{DAY}T23:00:00Z"})
    monkeypatch.setattr(module, "load_player_logs", lambda processed: logs())
    monkeypatch.setattr(module, "current_rosters", lambda raw_dir=None: {1: "TOR", 2: "MTL", 3: "MTL"})
    monkeypatch.setattr(module, "build_team_name_map", lambda *a, **k: {"toronto maple leafs": "TOR", "montreal canadiens": "MTL"})
    monkeypatch.setattr(module, "saved_team_name_map", lambda **k: {})
    return module


def run(module, tmp_path, *extra):
    return module.main(["--now", NOW, "--output-dir", str(tmp_path / "out"), "--processed-dir", str(tmp_path / "proc"),
                        "--staging-dir", str(tmp_path / "staging"), *extra])


def test_both_lists_are_written_for_today_with_no_price_filled_in(tmp_path, monkeypatch) -> None:
    module = script(monkeypatch)
    assert run(module, tmp_path, "--check") == 0
    assert run(module, tmp_path) == 0
    hot = json.loads((tmp_path / "out" / "hot_list.json").read_text())
    due = json.loads((tmp_path / "out" / "drought_list.json").read_text())
    assert hot["day"] == due["day"] == DAY
    assert {r["market"] for r in hot["rows"]} == {"points", "goals"}
    assert all(r["american_odds"] is None for r in hot["rows"] + due["rows"])
    assert any("Built before the card" in n for n in hot["notes"])
    assert run(module, tmp_path, "--check") == 1, "both are built now"
    assert not (tmp_path / "proc").exists(), "nothing is recorded"


def test_a_list_the_card_already_built_for_today_is_left_alone(tmp_path, monkeypatch) -> None:
    module = script(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    card = {"day": DAY, "rows": [{"player": "card row"}], "generated_at": "card"}
    for name in ("drought_list.json", "hot_list.json"):
        (out / name).write_text(json.dumps(card))
    assert run(module, tmp_path) == 0
    for name in ("drought_list.json", "hot_list.json"):
        assert json.loads((out / name).read_text()) == card


def test_yesterdays_list_is_replaced(tmp_path, monkeypatch) -> None:
    module = script(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    (out / "hot_list.json").write_text(json.dumps({"day": "2026-11-18", "rows": []}))
    assert module.lists_needed(out, DAY) == ["drought_list.json", "hot_list.json"]
    run(module, tmp_path)
    assert json.loads((out / "hot_list.json").read_text())["day"] == DAY


def test_publish_site_builds_them_at_3_am_and_before_the_board() -> None:
    flow = yaml.safe_load((ROOT / ".github/workflows/publish-site.yml").read_text())
    crons = {c["cron"] for c in flow[True]["schedule"]}
    assert {"0 20 * * *", "0 21 * * *"} <= crons, "3 AM New York primaries, EDT and EST"
    steps = [s.get("name", "") for s in flow["jobs"]["publish"]["steps"]]
    early = steps.index("Build today's Due List and Hot List before the card")
    assert early < steps.index("Build today's board and yesterday's results")
    text = (ROOT / ".github/workflows/publish-site.yml").read_text()
    assert "scripts/build_early_lists.py" in text
    from wait_for_round import CRON_LEADS  # noqa: E402
    assert "0 20 * * *" in CRON_LEADS and "0 21 * * *" in CRON_LEADS
