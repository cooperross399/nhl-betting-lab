"""A game under way or over keeps our projected winner and total (Cooper,
2026-11-22: "once games have started/ended on the website they need to still
show what our projected total and the projected winner were based off our
line calculations").

Two halves. The builder: a build after puck drop holds no staged price for a
game under way, so it used to publish that game with no line, no total and no
pick; `keep_started_projections` now gives it what the day's frozen board
published. The page: the game's row reads "Projected: TOR 58% · 6.4 goals"
once it has started, and its score box prints our projection under the score
with how it is going (smooth_pages patches the published Board).
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 22, 1, 0, tzinfo=timezone.utc)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_game(gid: str, start: str) -> dict:
    return {"id": gid, "startUtc": start, "priced": True,
            "away": {"abbr": "BOS", "projGoals": 2.8, "winProb": 0.42, "b2b": False},
            "home": {"abbr": "TOR", "projGoals": 3.4, "winProb": 0.58, "b2b": False},
            "moneyline": {"current": {"home": -140, "away": 120}},
            "total": {"current": 6.5, "proj": 6.43, "overProb": 0.47, "side": "under"},
            "pick": {"kind": "bet", "market": "Moneyline", "label": "TOR ML", "price": -140}}


def unpriced(gid: str, start: str) -> dict:
    return {"id": gid, "startUtc": start, "priced": False, "pick": None,
            "away": {"abbr": "BOS", "projGoals": 2.9, "winProb": 0.43}, "home": {"abbr": "TOR", "projGoals": 3.3, "winProb": 0.57}}


def test_a_started_unpriced_game_takes_the_frozen_projection_and_lines(tmp_path) -> None:
    site = _load("_site_started", "web/build_site_json.py")
    path = tmp_path / "2026-11-21.json"
    path.write_text(json.dumps({"games": [frozen_game("1", "2026-11-22T00:00:00Z"), frozen_game("2", "2026-11-22T03:00:00Z"),
                                          frozen_game("3", "2026-11-22T00:00:00Z")]}))
    started, later, priced = unpriced("1", "2026-11-22T00:00:00Z"), unpriced("2", "2026-11-22T03:00:00Z"), frozen_game("3", "2026-11-22T00:00:00Z")
    priced["total"] = {"current": 6.0, "proj": 6.1}
    assert site.keep_started_projections([started, later, priced], path, NOW) == 1
    assert started["priced"] is True and started["total"]["proj"] == 6.43 and started["pick"]["label"] == "TOR ML"
    assert started["home"]["winProb"] == 0.57, "the build's own win chance stands where it has one"
    assert later["priced"] is False and "total" not in later, "a game still to face off is left as built"
    assert priced["total"]["proj"] == 6.1, "a game this build priced keeps its own figures"


def test_no_frozen_board_changes_nothing(tmp_path) -> None:
    site = _load("_site_started_none", "web/build_site_json.py")
    g = unpriced("1", "2026-11-22T00:00:00Z")
    assert site.keep_started_projections([g], tmp_path / "missing.json", NOW) == 0
    (tmp_path / "bad.json").write_text("{not json")
    assert site.keep_started_projections([g], tmp_path / "bad.json", NOW) == 0
    assert "total" not in g


def _helpers_out(cases: list) -> list:
    node = shutil.which("node")
    assert node, "node is not on PATH"
    sp = _load("_smooth_started", "web/smooth_pages.py")
    js = sp.PROJ_HELPERS + "\nconst cases = JSON.parse(process.argv[process.argv.length - 1]);\n" \
        "process.stdout.write(JSON.stringify(cases.map(([r, e, scored]) => projLine(r, e, scored))));\n"
    result = subprocess.run([node, "-e", js, json.dumps(cases)], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_score_box_line_reads_the_projection_and_how_it_is_going() -> None:
    g = frozen_game("1", "2026-11-22T00:00:00Z")
    live = {"state": "in", "home": {"score": 2}, "away": {"score": 1}}
    final = {"state": "post", "home": {"score": 1}, "away": {"score": 4}}
    no_total = {k: v for k, v in g.items() if k != "total"}
    out = _helpers_out([[g, None, False], [g, live, True], [g, final, True], [no_total, None, False], [{"home": {}, "away": {}}, None, False]])
    assert out[0] == "Our projection: TOR to win (58%), 6.4 total goals"
    assert out[1] == "Our projection: TOR to win (58%), 6.4 total goals · 3 goals so far, TOR leads"
    assert out[2] == "Our projection: TOR to win (58%), 6.4 total goals · winner missed, 5 goals scored"
    assert out[3] == "Our projection: TOR to win (58%), 6.2 total goals", "with no priced total, the two projected scores add up"
    assert out[4] == "", "a game the model did not project says nothing"


def test_the_published_board_carries_the_patches() -> None:
    sp = _load("_smooth_started_patch", "web/smooth_pages.py")
    text = sp.patch("Board.dc.html", (ROOT / "web" / "Board.dc.html").read_text(encoding="utf-8"))
    assert "const projOf = (r) =>" in text and "proj: projLine(r, e, scored)," in text
    assert "{{ g.box.proj }}" in text and "statSide(r, (!!e && e.state !== \"pre\") || Date.parse(r.startUtc) <= now)" in text
    assert "`Projected: ${p.abbr} ${p.pct}%" in text
