"""CLV set a best-of-N price against one book's price, in both directions.

`closing_lines.best_prices` says it in its own docstring: "Comparing our
best-of-twenty against one book's close would measure the book, not the
model." Two paths did exactly that. Found by the failure-shape audit
(finding 21, confirmed by two of three refuters; the second path was found by
two refuters independently while reproducing the first).

* **The close, on the line-movement fallback.** When the dedicated store is
  empty, `load_captures` falls back to `line_movement/<day>.csv`, which holds
  every book's row for every capture round, and `closing_prices` kept the
  FIRST row at the latest moment. That is one book, picked by file order.
  The finder's round had BetMGM +105 listed first, then DraftKings +140 and
  FanDuel +135, against an opinion taken at +130. The fallback reported a
  close of BetMGM +105, beat_close True, CLV +12.2%. The best-price close,
  which is what the dedicated store holds, is DraftKings +140, beat_close
  False, CLV -4.2%. The error can only flatter, because the close it picks
  is never better than the best. A refuter replayed 291 real games on a
  market that did not move at all. The fallback printed mean CLV +0.74%
  [+0.72%, +0.76%], with "The interval excludes zero on the positive side."
* **The price taken, on every path.** `run_closing_line_value._opinions`
  de-duplicated snapshot and ledger rows on a key with no `book` and no
  `american_odds`, before `collapse_to_best` ever saw them. Each selection
  therefore kept the alphabetically first book of the staged snapshot, not
  the best one. On the same static market the dedicated-store path, which
  is the path CI reads, printed mean CLV -1.36%, with 25,504 losses against
  150 beats and "the market moved against these opinions more often than
  not."

What these tests hold, on stores written the way the capture scripts write
them and snapshots frozen by the real `write_snapshot`:

* the fallback holds exactly the rows the dedicated store would hold for the
  same capture rounds, which is one best-price row per selection per round;
* at the latest moment the close is the best price, whatever order the rows
  are in;
* the report `main()` writes is the same whichever store it read;
* on a market that did not move, every opinion ties its close under either
  store.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import selection_key


DAY = "2026-10-08"
GAME = {
    "date": DAY,
    "commence_time": "2026-10-08T23:00:00Z",  # 19:00 ET
    "provider_event_id": "evt1",
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
}
FROZEN_AT = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
EARLY = "2026-10-08T18:00:00+00:00"
LATE = "2026-10-08T22:30:00+00:00"


def _price(market, selection, odds, book, *, player="", line=None,
           fetched_at=LATE) -> dict:
    row = {column: None for column in odds_api.PRICE_COLUMNS}
    row.update(GAME)
    row.update(
        market=market, player=player, selection=selection, line=line,
        american_odds=float(odds), book=book, fetched_at=fetched_at,
    )
    return row


def _board(prices: dict[tuple, dict[str, int]], *, fetched_at: str) -> list[dict]:
    """Rows in the order given, which is the provider's and not alphabetical."""
    rows = []
    for (market, player, selection, line), books in prices.items():
        for book, odds in books.items():
            rows.append(_price(market, selection, odds, book, player=player,
                               line=line, fetched_at=fetched_at))
    return rows


# Six selections, three books each. BetMGM sorts first and is never the
# best; the provider order varies, so the first-listed row is sometimes the
# best and sometimes not.
MORNING = {
    ("moneyline", "", "away", None): {"FanDuel": 125, "BetMGM": 110, "DraftKings": 130},
    ("moneyline", "", "home", None): {"DraftKings": -150, "BetMGM": -165, "FanDuel": -155},
    ("total_goals", "", "over", 6.5): {"BetMGM": -120, "FanDuel": -105, "DraftKings": -110},
    ("total_goals", "", "under", 6.5): {"DraftKings": -110, "FanDuel": -115, "BetMGM": -125},
    ("shots_on_goal", "Auston Matthews", "over", 3.5): {"FanDuel": 105, "DraftKings": 100, "BetMGM": -110},
    ("shots_on_goal", "Auston Matthews", "under", 3.5): {"BetMGM": -140, "DraftKings": -125, "FanDuel": -130},
}
AFTERNOON = {
    ("moneyline", "", "away", None): {"BetMGM": 105, "DraftKings": 140, "FanDuel": 135},
    ("moneyline", "", "home", None): {"FanDuel": -160, "BetMGM": -175, "DraftKings": -165},
    ("total_goals", "", "over", 6.5): {"DraftKings": -115, "BetMGM": -125, "FanDuel": -108},
    ("total_goals", "", "under", 6.5): {"BetMGM": -120, "FanDuel": -110, "DraftKings": -105},
    ("shots_on_goal", "Auston Matthews", "over", 3.5): {"BetMGM": -105, "FanDuel": 115, "DraftKings": 110},
    ("shots_on_goal", "Auston Matthews", "under", 3.5): {"DraftKings": -140, "BetMGM": -150, "FanDuel": -135},
}


def _capture_round(processed: Path, rows: list[dict], captured_at: str, *,
                   movement: bool, dedicated: bool) -> None:
    """One capture round, written as scripts/capture_line_movement.py writes it.

    Lines 110-127 of that script: the provider's rows, every book, with
    `captured_at` beside them, appended to the day's movement file; then
    the round's best price per selection appended to the dedicated store.
    The movement path comes from the script's own `capture_path`.
    """
    from test_scripts import load_script

    frame = pd.DataFrame(rows)
    frame["captured_at"] = captured_at
    if movement:
        path = load_script("capture_line_movement.py").capture_path(
            DAY, processed_dir=processed
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, mode="a", header=not path.is_file(), index=False,
                     lineterminator="\n")
    if dedicated:
        cl.append_captures(cl.best_prices(frame, captured_at=captured_at),
                           processed_dir=processed)


def _freeze(archive: Path, prices: dict[tuple, dict[str, int]]) -> None:
    """The card's morning snapshot, in staging order, by the real writer."""
    rows = _board(prices, fetched_at="2026-10-08T14:55:00+00:00")
    probabilities = {
        selection_key(SimpleNamespace(**row), market=row["market"],
                      selection=row["selection"], line=row["line"]): 0.62
        for row in rows
    }
    written = fe.write_snapshot(
        odds_api.to_frame(rows), probabilities, key_for=selection_key,
        verdicts_line="props_b2b=in force", snapshot_date=DAY, now=FROZEN_AT,
        archive_dir=archive,
    )
    assert written is not None


def _report(processed: Path, archive: Path, output: Path) -> str:
    from test_scripts import load_script

    module = load_script("run_closing_line_value.py")
    code = module.main(["--processed-dir", str(processed), "--archive-dir",
                        str(archive), "--output-dir", str(output)])
    assert code == 0
    text = (output / cl.REPORT_FILENAME).read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith("- Generated:"))


def _two_stores(tmp_path: Path, rounds) -> tuple[Path, Path]:
    movement_only = tmp_path / "movement_only"
    dedicated_only = tmp_path / "dedicated_only"
    for captured_at, board in rounds:
        rows = _board(board, fetched_at=captured_at)
        _capture_round(movement_only, rows, captured_at, movement=True, dedicated=False)
        _capture_round(dedicated_only, rows, captured_at, movement=False, dedicated=True)
    return movement_only, dedicated_only


# -- the finder's reproduction ------------------------------------------------


def test_the_fallback_close_is_the_best_price_not_the_first_book_listed(tmp_path) -> None:
    rows = _board({("moneyline", "", "away", None):
                   {"BetMGM": 105, "DraftKings": 140, "FanDuel": 135}}, fetched_at=LATE)
    _capture_round(tmp_path, rows, LATE, movement=True, dedicated=False)
    taken = pd.DataFrame([{**_price("moneyline", "away", 130, "DraftKings"),
                           "snapshot_date": DAY, "edge": 0.05}])

    clv, counts = cl.clv_rows(taken, cl.load_captures(tmp_path))

    assert counts["matched"] == 1
    row = clv.iloc[0]
    assert (row["closing_odds"], row["closing_book"]) == (140.0, "DraftKings")
    assert not bool(row["beat_close"])
    assert row["clv_pct"] == pytest.approx(2.30 / 2.40 - 1.0)  # -4.2%, not +12.2%


# -- the fallback holds the dedicated store's rows ---------------------------------


def test_the_fallback_holds_exactly_the_rows_the_dedicated_store_holds(tmp_path) -> None:
    """Full-record equality, not a spot check: one best-price row per
    selection per round, the same book, price and stamp."""
    movement_only, dedicated_only = _two_stores(
        tmp_path, [(EARLY, MORNING), (LATE, AFTERNOON)]
    )

    def ordered(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame[list(cl.CAPTURE_COLUMNS)].copy()
        frame["player"] = frame["player"].fillna("").astype(str)
        frame["line"] = pd.to_numeric(frame["line"], errors="coerce")
        frame["american_odds"] = frame["american_odds"].astype(float)
        return frame.sort_values(
            ["captured_at", "market", "player", "selection", "line"]
        ).reset_index(drop=True)

    fallback = cl.load_movement_captures(movement_only)
    dedicated = cl.read_store(cl.captures_path(dedicated_only),
                              columns=cl.CAPTURE_COLUMNS)

    assert len(fallback) == len(dedicated) == 12, "6 selections x 2 rounds"
    pd.testing.assert_frame_equal(ordered(fallback), ordered(dedicated),
                                  check_dtype=False)


# -- closing_prices is independent of row order ---------------------------------


def test_at_one_moment_the_close_is_the_best_price_in_any_row_order() -> None:
    """A store can hold two books at one instant: two capture runs stamped the
    same second, merged. The close must not depend on which came first."""
    rows = [
        {**GAME, "captured_at": LATE, "market": "moneyline", "player": "",
         "selection": "away", "line": None, "american_odds": odds, "book": book}
        for book, odds in (("BetMGM", 105.0), ("DraftKings", 140.0), ("FanDuel", 135.0))
    ]
    shuffler = random.Random(20261008)
    seen = set()
    for _ in range(12):
        shuffler.shuffle(rows)
        (close,) = cl.closing_prices(pd.DataFrame(rows)).values()
        seen.add((close["american_odds"], close["book"]))

    assert seen == {(140.0, "DraftKings")}


def test_a_later_capture_still_beats_a_better_earlier_price() -> None:
    """The best price is taken at the latest moment only. A longer price from
    an earlier round is not the close, however good it was."""
    rows = [
        {**GAME, "captured_at": EARLY, "market": "moneyline", "player": "",
         "selection": "away", "line": None, "american_odds": 200.0, "book": "FanDuel"},
        {**GAME, "captured_at": LATE, "market": "moneyline", "player": "",
         "selection": "away", "line": None, "american_odds": 110.0, "book": "BetMGM"},
        {**GAME, "captured_at": LATE, "market": "moneyline", "player": "",
         "selection": "away", "line": None, "american_odds": 120.0, "book": "DraftKings"},
    ]

    (close,) = cl.closing_prices(pd.DataFrame(rows)).values()

    assert (close["american_odds"], close["book"]) == (120.0, "DraftKings")


# -- end to end, through the runner ----------------------------------------


def test_the_report_is_the_same_whichever_store_it_read(tmp_path) -> None:
    archive = tmp_path / "archive"
    _freeze(archive, MORNING)
    movement_only, dedicated_only = _two_stores(
        tmp_path, [(EARLY, MORNING), (LATE, AFTERNOON)]
    )

    from_movement = _report(movement_only, archive, tmp_path / "out_movement")
    from_dedicated = _report(dedicated_only, archive, tmp_path / "out_dedicated")

    assert "## All opinions" in from_dedicated
    assert from_movement == from_dedicated


@pytest.mark.parametrize("store", ["movement", "dedicated"])
def test_a_market_that_did_not_move_ties_every_opinion(tmp_path, store) -> None:
    """The same board at the freeze and at both rounds: the true CLV of every
    opinion is exactly zero, on either store. The snapshot is in staging
    order, where BetMGM sorts first and is never the best price."""
    archive = tmp_path / "archive"
    processed = tmp_path / "processed"
    _freeze(archive, MORNING)
    for captured_at in (EARLY, LATE):
        _capture_round(processed, _board(MORNING, fetched_at=captured_at),
                       captured_at, movement=store == "movement",
                       dedicated=store == "dedicated")

    text = _report(processed, archive, tmp_path / "out")

    assert "matched to a closing price: **6**" in text
    # Rows | Beat close | Tied | Beat rate | Mean CLV% ...: all six tied, none
    # beat, and the mean CLV is exactly zero. The six are one game, so no
    # interval can be bounded: this read "[+0.00%, +0.00%]", an interval
    # on six rows of one game (tests/test_clv_intervals_count_games_not_rows.py).
    assert "| 6 | 0 | 6 | 0.0% [0.0%, 100.0%] | +0.00% n too small |" in text
    assert "(6) | 1 |" in text, "one game behind the six rows"


def test_the_runner_scores_each_opinion_at_its_best_price(tmp_path) -> None:
    """`_opinions` hands every book's row to the collapse, so the price taken
    is the best the snapshot held and not the first book staged."""
    from test_scripts import load_script

    archive = tmp_path / "archive"
    _freeze(archive, MORNING)

    opinions = load_script("run_closing_line_value.py")._opinions(tmp_path, archive)
    best = cl.collapse_to_best(opinions)

    assert len(opinions) == 18, "every book's row reaches the collapse"
    taken = {(r.market, r.selection): (r.american_odds, r.book) for r in best.itertuples()}
    assert taken[("moneyline", "away")] == (130.0, "DraftKings")
    assert taken[("shots_on_goal", "over")] == (105.0, "FanDuel")
