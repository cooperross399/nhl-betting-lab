"""The Lineup receives tonight's line units, and nothing else from the capture.

`scripts/publish_lineup_lines.py` sends Cooper's DFS app each team's newest
snapshot of its forward lines and power-play units. The capture it reads is the
lab's own record, kept privately and out of this repository, so what may leave
is pinned here: names in L1-L4 and PP1/PP2 from each team's latest read, never
an older read, a player id, a defence pair, a penalty-kill unit, a goalie or
the injured-reserve group. The workflow step that runs it is pinned too: after
the round is home, never able to fail the capture run, default branch only.

Offline, like the rest of the suite: the sender is injected, and the real one
is made to explode if anything reaches it.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_lineup_lines.py"
WORKFLOW = ROOT / ".github" / "workflows" / "line-movement.yml"

spec = importlib.util.spec_from_file_location("publish_lineup_lines", SCRIPT)
pll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pll)

COLUMNS = (
    "team_abbreviation", "player_id", "player", "group_identifier",
    "position_identifier", "source_name", "source_updated_at", "retrieved_at",
)
EARLY, LATE = "2026-10-08T14:00:56+00:00", "2026-10-08T18:00:12+00:00"


def _row(team, pid, player, group, pos, held=LATE, source="Last Game (2026-10-07)"):
    return dict(zip(COLUMNS, (team, pid, player, group, pos, source, "2026-10-08T12:54:06Z", held)))


def _vgk(held=LATE, centre="Jack Eichel"):
    return [
        _row("VGK", "1", "Mark Stone", "f1", "rw", held),
        _row("VGK", "2", centre, "f1", "c", held),
        _row("VGK", "3", "Ivan Barbashev", "f1", "lw", held),
        _row("VGK", "4", "Shea Theodore", "d1", "rd", held),
        _row("VGK", "5", "Carter Hart", "g", "g1", held),
        _row("VGK", "6", "Mark Stone", "pk1", "sk1", held),
        _row("VGK", "7", "Alex Pietrangelo", "ir", "ir1", held),
        *[_row("VGK", str(10 + i), name, "pp1", f"sk{i + 1}", held) for i, name in enumerate(
            ["Mark Stone", "Tomas Hertl", "Mitch Marner", "Jack Eichel", "Shea Theodore"])],
    ]


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def test_only_lines_and_power_play_units_leave_in_slot_order() -> None:
    payload = pll.lineup_payload(_vgk())
    assert payload["lines"] == [
        {"team": "VGK", "kind": "line", "label": "L1",
         "players": ["Ivan Barbashev", "Jack Eichel", "Mark Stone"]},
        {"team": "VGK", "kind": "pp", "label": "PP1",
         "players": ["Mark Stone", "Tomas Hertl", "Mitch Marner", "Jack Eichel", "Shea Theodore"]},
    ]


def test_no_player_id_or_withheld_group_reaches_the_payload() -> None:
    text = json.dumps(pll.lineup_payload(_vgk()))
    assert "Carter Hart" not in text, "a goalie group left the lab"
    assert "Alex Pietrangelo" not in text, "the injured-reserve group left the lab"
    assert "player_id" not in text and "playerId" not in text
    assert set(pll.UNITS) == {"f1", "f2", "f3", "f4", "pp1", "pp2"}


def test_each_team_sends_only_its_newest_snapshot() -> None:
    rows = _vgk(EARLY, centre="William Karlsson") + _vgk(LATE)
    payload = pll.lineup_payload(rows)
    l1 = next(l for l in payload["lines"] if l["label"] == "L1")
    assert "Jack Eichel" in l1["players"] and "William Karlsson" not in l1["players"]
    assert payload["sources"]["VGK"]["retrievedAt"] == LATE


def test_a_team_missing_from_the_newest_round_keeps_its_earlier_read() -> None:
    rows = _vgk(LATE) + [_row("TOR", "20", "Auston Matthews", "f1", "c", EARLY)]
    payload = pll.lineup_payload(rows)
    assert {l["team"] for l in payload["lines"]} == {"VGK", "TOR"}
    assert payload["sources"]["TOR"]["retrievedAt"] == EARLY


def _write(tmp_path: Path, day: str, rows: list[dict]) -> Path:
    path = tmp_path / "line_combinations" / f"{day}.csv"
    path.parent.mkdir(parents=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_no_token_sends_nothing_and_stays_green(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(pll.TOKEN_ENV, raising=False)
    _write(tmp_path, "2026-10-08", _vgk())
    sent = []
    code = pll.main(["--processed-dir", str(tmp_path), "--date", "2026-10-08"], send=lambda *a: sent.append(a))
    assert code == 0 and sent == []


def test_no_capture_today_sends_nothing_and_stays_green(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(pll.TOKEN_ENV, "t")
    sent = []
    code = pll.main(["--processed-dir", str(tmp_path), "--date", "2026-10-08"], send=lambda *a: sent.append(a))
    assert code == 0 and sent == []


def test_a_capture_with_no_units_sends_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(pll.TOKEN_ENV, "t")
    _write(tmp_path, "2026-10-08", [_row("VGK", "5", "Carter Hart", "g", "g1")])
    sent = []
    code = pll.main(["--processed-dir", str(tmp_path), "--date", "2026-10-08"], send=lambda *a: sent.append(a))
    assert code == 0 and sent == []


def test_a_send_names_the_date_sport_and_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(pll.TOKEN_ENV, "secret-token")
    _write(tmp_path, "2026-10-08", _vgk())
    sent = []

    def accept(url, token, body):
        sent.append((url, token, body))
        return 200, '{"ok":true}'

    code = pll.main(
        ["--processed-dir", str(tmp_path), "--date", "2026-10-08", "--url", "https://example.test/"],
        send=accept,
    )
    assert code == 0
    (url, token, body), = sent
    assert url == "https://example.test/lines?sport=NHL&date=2026-10-08"
    assert token == "secret-token"
    assert len(body["lines"]) == 2


def test_a_refused_send_exits_one(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv(pll.TOKEN_ENV, "t")
    _write(tmp_path, "2026-10-08", _vgk())
    code = pll.main(["--processed-dir", str(tmp_path), "--date", "2026-10-08"],
                    send=lambda *a: (401, '{"error":"unauthorized"}'))
    assert code == pll.EXIT_REFUSED
    assert "HTTP 401" in capsys.readouterr().out


def _steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in document["jobs"].values() for step in job["steps"]]


def _send_step() -> tuple[int, dict]:
    found = [(i, s) for i, s in enumerate(_steps()) if "publish_lineup_lines.py" in str(s.get("run", ""))]
    assert len(found) == 1, "exactly one step sends line units to The Lineup"
    return found[0]


def test_the_send_can_never_fail_or_delay_the_capture_run() -> None:
    index, step = _send_step()
    assert step.get("continue-on-error") is True
    assert step.get("timeout-minutes", 99) <= 5
    names = [s.get("name") for s in _steps()]
    for earlier in ("Capture line combinations", "Keep the captures privately",
                    "Check the private chain holds this round", "Keep the sealed round"):
        assert names.index(earlier) < index, f"the send must run after {earlier!r}"


def test_the_send_runs_only_from_the_default_branch_with_its_own_token() -> None:
    _, step = _send_step()
    condition = str(step.get("if", ""))
    assert "github.event_name == 'schedule'" in condition
    assert "github.event.repository.default_branch" in condition
    assert step["env"]["LINEUP_INGEST_TOKEN"] == "${{ secrets.LINEUP_INGEST_TOKEN }}"
    secrets_named = {k for k, v in step["env"].items() if "secrets." in str(v)}
    assert secrets_named == {"LINEUP_INGEST_TOKEN"}, "the send must hold no other credential"
