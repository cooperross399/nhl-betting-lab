"""The card's prop leans are graded at 1u each from card-feed, and add up.

Cooper, 2026-11-03: "track the prop leans record/profit on the website".
web/prop_leans.py reads every card from card-feed's history of
latest_card_comment.md (each league day's first card listing a prop lean)
and settles each lean on that day's forward-ledger file. These tests build a
small card-feed in a temporary git repository and drive the real module.
"""

from __future__ import annotations

import importlib.util
import subprocess
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("_test_prop_leans", ROOT / "web" / "prop_leans.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _module()

OLD_TABLE = """| Game | Starts | Market | Selection | Model | Edge | Price | Book |
|:-----|:-------|:-------|:----------|------:|-----:|------:|:-----|
"""
NEW_TABLE = """| Game | Starts | Market | Selection | Model | Edge | Price | Bet down to | Book |
|:-----|:-------|:-------|:----------|------:|-----:|------:|------------:|:-----|
"""


def card(generated: str, rows: list[str], *, new: bool = False) -> str:
    table = (NEW_TABLE if new else OLD_TABLE) + "\n".join(rows)
    return (f"**Selections changed**\n\n# NHL gameday card\n\n- Generated: {generated}\n\n## Best bets\n\nnone\n\n"
            f"## Leans\n\n{table}\n\nLeans are recorded and not staked.\n\n## Passes / notable avoids\n\n| x |\n")


LEDGER_HEADER = ("snapshot_date,commence_time,home_team,away_team,market,player,selection,line,american_odds,book,"
                 "model_probability,edge,verdicts_in_force,settled_at,outcome,actual,profit_units\n")


def ledger_row(day, home, away, market, player, side, line, outcome, book="Bovada"):
    return f"{day},{day}T23:00:00Z,{home},{away},{market},{player},{side},{line},-110,{book},0.6,0.08,x,x,{outcome},1,0\n"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


@pytest.fixture()
def feed(tmp_path: Path) -> Path:
    repo = tmp_path / "feed"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "card-feed")
    g = "Utah Mammoth @ Toronto Maple Leafs"
    # Oct 1: the morning card's leans stand; the afternoon re-price is ignored.
    commit(repo, {"latest_card_comment.md": card("2026-10-01T13:40:00+00:00", [
        f"| {g} | Oct 1, 7:00 PM ET | `shots_on_goal` | Auston Matthews under 3.5 | 60.0% | +8.0% | +120 | Bovada |",
        f"| {g} | Oct 1, 7:00 PM ET | `points` | Mitch Marner over 0.5 | 60.0% | +8.0% | -150 | Fliff |",
        f"| {g} | Oct 1, 7:00 PM ET | `total_goals` | over 6.5 | 50.0% | +8.0% | +100 | Fliff |",
        f"| {g} | Oct 1, 7:00 PM ET | `goals` | William Nylander over 0.5 | 40.0% | +8.0% | +200 | Fliff |",
        f"| {g} | Oct 1, 7:00 PM ET | `assists` | Nobody Known under 0.5 | 60.0% | +8.0% | -110 | Fliff |",
    ])}, "card 2026-10-01")
    commit(repo, {"latest_card_comment.md": card("2026-10-01T20:30:00+00:00", [
        f"| {g} | Oct 1, 7:00 PM ET | `hits` | Someone Else over 1.5 | 60.0% | +8.0% | +300 | Fliff |",
    ])}, "card 2026-10-01 later")
    # Oct 2: the morning card lists no prop lean, so the later one is used.
    commit(repo, {"latest_card_comment.md": card("2026-10-02T13:40:00+00:00", [])}, "card 2026-10-02")
    commit(repo, {"latest_card_comment.md": card("2026-10-02T18:00:00+00:00", [
        f"| {g} | Oct 2, 7:00 PM ET | `shots_on_goal` | Auston Matthews over 2.5 | 60.0% | +8.0% | -110 | −105 | Bovada |",
    ], new=True)}, "card 2026-10-02 later")
    # Oct 3: not settled yet (no ledger file).
    commit(repo, {"latest_card_comment.md": card("2026-10-03T13:40:00+00:00", [
        f"| {g} | Oct 3, 7:00 PM ET | `goals` | Auston Matthews over 0.5 | 40.0% | +8.0% | +150 | +130 | Fliff |",
    ], new=True)}, "card 2026-10-03")
    h, a = "Toronto Maple Leafs", "Utah Mammoth"
    commit(repo, {
        "forward_evidence/2026-10-01.csv": LEDGER_HEADER
        + ledger_row("2026-10-01", h, a, "shots_on_goal", "Auston Matthews", "under", 3.5, "won")
        + ledger_row("2026-10-01", h, a, "shots_on_goal", "Auston Matthews", "under", 3.5, "won", book="Fliff")
        + ledger_row("2026-10-01", h, a, "points", "Mitch Marner", "over", 0.5, "lost")
        + ledger_row("2026-10-01", h, a, "goals", "William Nylander", "over", 0.5, "void"),
        "forward_evidence/2026-10-02.csv": LEDGER_HEADER
        + ledger_row("2026-10-02", h, a, "shots_on_goal", "Auston Matthews", "over", 2.5, "push"),
    }, "ledger")
    return repo


def test_each_lean_is_graded_once_at_one_unit_and_the_counts_add_up(feed: Path) -> None:
    doc = P.build(feed, "card-feed", today=date(2026, 10, 4))
    s = doc["season"]
    # Oct 1: 4 prop leans (the total is a team market); Oct 2: 1; Oct 3: 1 pending.
    assert s["listed"] == 6
    assert (s["w"], s["l"], s["p"], s["void"], s["unmatched"], s["pending"]) == (1, 1, 1, 1, 1, 1)
    assert s["w"] + s["l"] + s["p"] + s["void"] + s["unmatched"] + s["pending"] == s["listed"]
    # +1.20 at +120, -1 at -150, 0 on the push.
    assert s["units"] == pytest.approx(0.2)
    assert s["staked"] == 3.0
    assert doc["stake"] == 1.0
    assert sorted(r["result"] for r in doc["rows"]) == ["loss", "push", "win"]
    assert all(r["group"] == "leans" and r["staked"] == 1.0 for r in doc["rows"])
    # The afternoon re-price on Oct 1 never replaced the morning card.
    assert not any(r["market"] == "hits" for r in doc["rows"])
    assert [n["date"] for n in doc["byNight"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert doc["nights"] == 2


def test_today_is_never_graded(feed: Path) -> None:
    doc = P.build(feed, "card-feed", today=date(2026, 10, 3))
    assert doc["season"]["listed"] == 5
    assert doc["lastDate"] == "2026-10-02"


def test_both_table_layouts_parse() -> None:
    g = "A @ B"
    old = P.parse_leans(card("2026-10-01T13:40:00+00:00", [f"| {g} | x | `goals` | Some One over 0.5 | 40.0% | +8.0% | +200 | Fliff |"]))
    new = P.parse_leans(card("2026-10-01T13:40:00+00:00", [f"| {g} | x | `goals` | Some One over 0.5 | 40.0% | +8.0% | +200 | +180 | Fliff |"], new=True))
    assert old == new
    assert old[0]["price"] == 200 and old[0]["book"] == "Fliff" and old[0]["home"] == "B"


def test_the_tracker_page_keeps_leans_out_of_the_bets_headline() -> None:
    page = (ROOT / "web" / "Tracker.dc.html").read_text(encoding="utf-8")
    assert "./data/prop_leans.json" in page
    assert '["leans", "Prop leans"]' in page
    assert "const ov = agg(bets)" in page
    assert 'rows = f === "all" ? bets :' in page
