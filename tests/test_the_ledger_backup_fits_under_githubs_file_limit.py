"""card-feed's ledger backup is one file per snapshot day, not one file.

On 2026-10-21 the 13:30 UTC Gameday Refresh built and posted the card, and
its push to card-feed was refused: "File forward_evidence.csv is 100.66 MB;
this exceeds GitHub's file size limit of 100.00 MB". With no status for
today on card-feed, the routines that deliver the card found nothing, and
every later run would have failed the same way, because the ledger only
grows. The publish step now writes `forward_evidence/<snapshot day>.csv`,
and the restore fallback joins them back.

What these tests hold:

* split then join gives back the ledger byte for byte, quoted fields and
  all, and keeps every row;
* join refuses an empty directory, a mismatched header and a row filed
  under the wrong day, and writes nothing on refusal;
* the publish step, run for real against a local bare remote, puts the
  ledger on card-feed as day files and never as `forward_evidence.csv`,
  and those files join back to the ledger it was given;
* the restore fallback reads the day files, and still reads a tip from
  before the change.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_a_blocked_card_is_a_degraded_run import _bash, _git_env, _render, _step

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "split_forward_ledger.py"
sys.path.insert(0, str(SCRIPT.parent))
import split_forward_ledger as ledger_days  # noqa: E402

HEADER = ("snapshot_date,commence_time,home_team,away_team,market,player,selection,"
          "line,american_odds,book,model_probability,edge,verdicts_in_force,"
          "settled_at,outcome,actual,profit_units\n")
ROWS = [
    "2026-09-29,2026-09-29T21:10:47Z,Carolina Hurricanes,Florida Panthers,moneyline,,away,,"
    "110.0,Bally Bet,0.4217309202515957,-0.0544595559388804,"
    '"by_toi=off, props_b2b=in force, team_b2b=in force",2026-09-30T13:40:17+00:00,won,-1.0,1.1\n',
    "2026-09-29,2026-09-29T23:00:00Z,Carolina Hurricanes,Florida Panthers,points,"
    '"Aho, Sebastian",over,0.5,-120.0,FanDuel,0.6,0.05,"a ""quoted"" verdict",'
    "2026-09-30T13:40:17+00:00,lost,0.0,-1.0\n",
    "2026-09-30,2026-09-30T23:00:00Z,Boston Bruins,Chicago Blackhawks,goals,"
    "David Pastrnak,over,0.5,150.0,DraftKings,0.45,0.05,x,2026-10-01T13:40:17+00:00,void,,0.0\n",
]
LEDGER = HEADER + "".join(ROWS)


def _ledger(path: Path) -> Path:
    path.write_text(LEDGER, encoding="utf-8")
    return path


def test_split_then_join_is_the_ledger_byte_for_byte(tmp_path):
    source = _ledger(tmp_path / "forward_evidence.csv")
    counts = ledger_days.split(source, tmp_path / "days")
    assert counts == {"2026-09-29": 2, "2026-09-30": 1}
    assert sorted(p.name for p in (tmp_path / "days").iterdir()) == [
        "2026-09-29.csv", "2026-09-30.csv"]
    for path in (tmp_path / "days").iterdir():
        assert path.read_text(encoding="utf-8").startswith(HEADER)
    assert ledger_days.join(tmp_path / "days", tmp_path / "joined.csv") == 3
    assert (tmp_path / "joined.csv").read_bytes() == source.read_bytes()


def test_join_refuses_what_would_write_a_wrong_ledger(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    target = tmp_path / "out.csv"
    with pytest.raises(SystemExit):
        ledger_days.join(empty, target)
    days = tmp_path / "days"
    ledger_days.split(_ledger(tmp_path / "l.csv"), days)
    (days / "2026-09-30.csv").write_text("other,header\nx,y\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ledger_days.join(days, target)
    ledger_days.split(_ledger(tmp_path / "l.csv"), days)
    (days / "2026-10-01.csv").write_text(HEADER + ROWS[0], encoding="utf-8")
    with pytest.raises(SystemExit):
        ledger_days.join(days, target)
    assert not target.exists()


def _publish(tmp_path: Path) -> dict:
    env = _git_env(tmp_path, "2026-10-21")
    python = tmp_path / "bin" / "python"
    if not python.exists():
        python.symlink_to(sys.executable)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    env = {**env, "RUNNER_TEMP": str(runner_temp)}
    work = tmp_path / "work"
    (work / "data" / "processed").mkdir(parents=True)
    (work / "scripts").mkdir()
    (work / "scripts" / SCRIPT.name).write_text(SCRIPT.read_text(encoding="utf-8"),
                                                encoding="utf-8")
    _ledger(work / "data" / "processed" / "forward_evidence.csv")
    (work / "card_comment.md").write_text("card\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    block = _render(_step(name="Publish the card to the card-feed branch")["run"], {
        "github.repository": "o/r",
        "github.server_url": "https://github.com",
        "github.run_id": "1",
        "github.ref": "refs/heads/main",
        "steps.post.outputs.decision || 'none'": "posted",
        "steps.final.outputs.degraded || 'unknown'": "false",
        "steps.prices.outputs.empty_slate || 'false'": "false",
    })
    result = _bash(block, work, env)
    assert result.returncode == 0, result.stderr
    return env


def test_the_publish_step_puts_day_files_on_card_feed(tmp_path):
    env = _publish(tmp_path)
    remote = str(tmp_path / "remote.git")
    listed = subprocess.run(
        ["git", "--git-dir", remote, "ls-tree", "-r", "--name-only", "card-feed"],
        env=env, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "forward_evidence.csv" not in listed
    assert "forward_evidence/2026-09-29.csv" in listed
    assert "forward_evidence/2026-09-30.csv" in listed
    assert "latest_status.json" in listed
    restored = tmp_path / "restored"
    restored.mkdir()
    archive = subprocess.run(["git", "--git-dir", remote, "archive", "card-feed",
                              "forward_evidence"], env=env, capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(restored)], input=archive.stdout, check=True)
    ledger_days.join(restored / "forward_evidence", tmp_path / "joined.csv")
    assert (tmp_path / "joined.csv").read_text(encoding="utf-8") == LEDGER


def test_the_restore_fallback_reads_the_day_files_and_the_old_single_file():
    block = _step(name="Restore the previous state")["run"]
    assert "refs/card-feed-tip forward_evidence/" in block
    assert "split_forward_ledger.py join" in block
    assert "refs/card-feed-tip:forward_evidence.csv" in block
    assert block.index("split_forward_ledger.py join") < block.index(
        "refs/card-feed-tip:forward_evidence.csv")
    assert os.path.exists(SCRIPT)
