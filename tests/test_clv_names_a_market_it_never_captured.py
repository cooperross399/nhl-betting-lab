"""The CLV page blamed the books for a market the capture never asked for.

The card freezes a moneyline opinion every game day, from the bulk `h2h`
fetch. The store CLV is measured from is fed only by Line Movement, and Line
Movement asks the provider for the per-event markets and their alternate
ladders — never `h2h`, `spreads` or `totals`. So no moneyline opinion can ever
meet a closing price. `closing_line_value.md` counted every one of them under
"no closing price found", beside a paragraph explaining such an opinion as "a
selection the books pulled before puck drop"; moneyline never appeared in the
by-market table; and a day whose only opinions were moneylines read "Nothing
to measure yet ... this is the correct state and not a fault."

Found by the failure-shape audit and confirmed 3/3. The reproduction froze a
card with the real `write_snapshot`, captured twice with Line Movement's own
market list and ran the real `run_closing_line_value.main`: the store held 0
moneyline rows, and both moneyline opinions landed in "no closing price
found". Its smaller replay counted {'opinions': 2, 'matched': 1, 'no_close': 1}
with the by-market keys ['shots_on_goal'] alone.

Capturing the team markets is a spending decision (the bulk call costs
3 markets x 2 regions = 6 credits a run), so it is not made here. What is fixed
here is the page: an unmatched opinion in a market the store holds no
pre-start price for, in its game, is named as a gap in the capture and not
blamed on the books.

These tests freeze opinions with the real `forward_evidence.write_snapshot`,
write captures where and how `capture_line_movement.main` writes them (the
per-event markets only, because that is what it asks for), and run the real
`scripts/run_closing_line_value.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.reports.card_pricing import selection_key

from test_scripts import load_script


DAY = "2026-10-15"
HOME, AWAY = "Toronto Maple Leafs", "Boston Bruins"
LATE_HOME, LATE_AWAY = "Vancouver Canucks", "Calgary Flames"
START = f"{DAY}T23:00:00Z"
CARD_AT = datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)


def _moneyline(home=HOME, away=AWAY, start=START) -> list[dict]:
    return [
        {"commence_time": start, "home_team": home, "away_team": away,
         "market": "moneyline", "player": "", "selection": side, "line": None,
         "american_odds": odds, "book": "draftkings"}
        for side, odds in (("home", -150.0), ("away", 130.0))
    ]


def _shots(selection="over", home=HOME, away=AWAY, start=START) -> dict:
    return {"commence_time": start, "home_team": home, "away_team": away,
            "market": "shots_on_goal", "player": "Auston Matthews",
            "selection": selection, "line": 3.5, "american_odds": -110.0,
            "book": "fanduel"}


def _freeze(archive: Path, rows: list[dict]) -> None:
    """The card's own freeze, with a probability for every row it staged."""
    prices = pd.DataFrame(rows)
    probabilities = {}
    for row in prices.itertuples():
        line = None if pd.isna(row.line) else float(row.line)
        probabilities[selection_key(row, market=row.market, selection=row.selection,
                                    line=line)] = 0.58
    assert fe.write_snapshot(
        prices, probabilities, key_for=selection_key, verdicts_line="",
        snapshot_date=DAY, now=CARD_AT, archive_dir=archive,
    ) is not None


def _capture(processed: Path, rows: list[dict], at: str) -> None:
    """Appended where and how `capture_line_movement.main` appends."""
    movement = load_script("capture_line_movement.py")
    frame = pd.DataFrame(rows)
    frame["captured_at"] = at
    path = movement.capture_path(DAY, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                 lineterminator="\n")


def _page(tmp_path: Path) -> str:
    script = load_script("run_closing_line_value.py")
    assert script.main([
        "--processed-dir", str(tmp_path / "processed"),
        "--output-dir", str(tmp_path / "outputs"),
        "--archive-dir", str(tmp_path / "archive"),
    ]) == 0
    return (tmp_path / "outputs" / cl.REPORT_FILENAME).read_text(encoding="utf-8")


def test_a_moneyline_opinion_is_named_as_uncaptured_not_as_pulled(tmp_path: Path) -> None:
    _freeze(tmp_path / "archive", _moneyline() + [_shots()])
    for at in (f"{DAY}T18:00:00+00:00", f"{DAY}T21:00:00+00:00"):
        _capture(tmp_path / "processed", [_shots(), _shots("under")], at)

    page = _page(tmp_path)

    assert "no closing price found: **2**" in page
    assert "Of those, **2** are in a market the store holds no price for" in page
    assert "`moneyline` (2)" in page
    assert "No book pulled these." in page
    assert "`shots_on_goal`" in page, "the matched market still gets its row"


def test_a_moneyline_only_day_is_not_called_the_correct_empty_state(tmp_path: Path) -> None:
    _freeze(tmp_path / "archive", _moneyline())
    _capture(tmp_path / "processed", [_shots(), _shots("under")], f"{DAY}T21:00:00+00:00")

    page = _page(tmp_path)

    assert "## Nothing to measure yet" in page
    assert "correct state and not a fault" not in page
    assert "NOT\nthe empty state before a season" in page
    assert "`moneyline` (2)" in page


def test_an_empty_store_still_reads_as_the_empty_state(tmp_path: Path) -> None:
    """Before the season every opinion is trivially uncaptured; the page says
    what it always said, and does not list every market as a gap."""
    _freeze(tmp_path / "archive", _moneyline() + [_shots()])

    page = _page(tmp_path)

    assert "correct state and not a fault" in page
    assert "Of those" not in page and "No book pulled these" not in page


def test_a_selection_gone_from_a_captured_market_is_still_the_books_doing(
    tmp_path: Path,
) -> None:
    """The over vanished while the under stayed posted: that market WAS
    captured for this game, so nothing here is relabelled."""
    _freeze(tmp_path / "archive", [_shots("over"), _shots("under")])
    _capture(tmp_path / "processed", [_shots("under")], f"{DAY}T21:00:00+00:00")

    page = _page(tmp_path)

    assert "no closing price found: **1**" in page
    assert "Of those" not in page and "No book pulled these" not in page


def test_captured_means_captured_for_that_game_before_its_face_off(tmp_path: Path) -> None:
    """Shots on goal captured for one game says nothing about another, and a
    price taken after face-off is not a close for anything."""
    late = f"{DAY}T23:30:00Z"
    _freeze(tmp_path / "archive", [
        _shots(),
        _shots(home=LATE_HOME, away=LATE_AWAY, start=late),
    ])
    _capture(tmp_path / "processed", [_shots(), _shots("under")], f"{DAY}T21:00:00+00:00")
    # The second game's only capture is live, 30 minutes after its start.
    _capture(tmp_path / "processed",
             [_shots(home=LATE_HOME, away=LATE_AWAY, start=late)],
             f"{DAY}T23:59:00+00:00")

    page = _page(tmp_path)

    assert "no closing price found: **1**" in page
    assert "Of those, **1** are in a market" in page
    assert "`shots_on_goal` (1)" in page
