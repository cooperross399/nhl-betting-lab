"""The CLV page blamed the capture for games that had not been played yet.

Gameday Refresh freezes the day's opinions and then, in the same job, runs
`scripts/run_closing_line_value.py` over every snapshot. So every report is
built in the morning with tonight's slate already frozen and none of it
started. A closing price is the last capture strictly before face-off, and
tonight's has not happened, so every one of tonight's opinions was counted
under "no closing price found" — and, since the store held no pre-start
price for its game yet, explained as "No book pulled these. The capture never
priced that market for that game ... a gap in what is captured". Every daily
page carried a full slate of that, and a bet frozen this morning read as a
bet with no close.

Found by sweep 3 (A2). Latent while Closing Lines is disabled, because the
report then reads no captures at all; the moment the store is fed, it fires
on every run. The replay: yesterday's opinion with a capture two hours
before face-off, today's with a 23:00Z face-off, the report built at 13:30Z,
counted opinions 2, matched 1, no_close 1, no_close_uncaptured 1,
bets_no_close 1.

What these tests hold:

* an opinion whose game starts after the report's `now` is counted as not
  yet played, and in none of matched / no close / uncaptured / bets without
  a close — through `build_clv_report`, `render_clv` and the real runner;
* the same opinion, once its face-off has passed, is back in the ordinary
  counts: nothing is excluded for good, and a game that started at `now`
  exactly has started;
* an opinion whose `commence_time` will not parse is never treated as not
  yet played. It stays in the existing counts, which is the safe direction:
  a stamp nobody can read is no reason to drop an opinion from the page;
* the runner uses the real clock unless `--now` is given, and refuses a
  `--now` without a timezone, as `run_gameday_card.py` does.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import forward_evidence as fe

from test_scripts import load_script


HOME, AWAY = "Boston Bruins", "New York Rangers"
YESTERDAY_START = "2026-10-08T23:00:00Z"
TONIGHT_START = "2026-10-09T23:00:00Z"
MORNING = datetime(2026, 10, 9, 13, 30, tzinfo=timezone.utc)


def _opinion(day: str, start: str, *, player="David Pastrnak", edge=0.08) -> dict:
    # edge 0.08 clears the prop staking bar, so every opinion here is a bet.
    return {"snapshot_date": day, "commence_time": start, "home_team": HOME,
            "away_team": AWAY, "market": "shots_on_goal", "player": player,
            "selection": "over", "line": 2.5, "american_odds": 120, "book": "DK",
            "model_probability": 0.55, "edge": edge, "verdicts_in_force": "v"}


def _capture(start: str, at: str) -> dict:
    return {"captured_at": at, "commence_time": start, "home_team": HOME,
            "away_team": AWAY, "market": "shots_on_goal", "player": "David Pastrnak",
            "selection": "over", "line": 2.5, "american_odds": 110, "book": "FD"}


def _yesterday_and_tonight(tonight_start: str = TONIGHT_START):
    opinions = pd.DataFrame([_opinion("2026-10-08", YESTERDAY_START),
                             _opinion("2026-10-09", tonight_start)])
    captures = pd.DataFrame([_capture(YESTERDAY_START, "2026-10-08T21:00:00+00:00")])
    return opinions, captures


def test_tonights_opinion_is_not_yet_played_rather_than_without_a_close() -> None:
    report = cl.build_clv_report(*_yesterday_and_tonight(), now=MORNING)
    counts = report["counts"]

    assert counts["opinions"] == 1
    assert counts["matched"] == 1
    assert counts["no_close"] == 0
    assert counts["no_close_uncaptured"] == 0
    assert report["uncaptured"] == {}
    assert counts["bets"] == 1
    assert counts["bets_no_close"] == 0
    assert counts["not_yet_played"] == 1
    assert counts["bets_not_yet_played"] == 1
    assert report["overall"]["opinions"]["no_close"] == 0
    assert report["overall"]["bets"]["no_close"] == 0


def test_the_page_says_not_yet_played_and_blames_nobody() -> None:
    page = cl.render_clv(
        cl.build_clv_report(*_yesterday_and_tonight(), now=MORNING), generated="t"
    )

    assert "no closing price found: **0**" in page
    assert "No book pulled these" not in page
    assert "Not yet played: **1** opinion(s)" in page
    assert "1 of them clearing the measurement bar" in page
    assert "0 bet(s) had no closing price" in page


def test_once_the_game_has_started_it_is_counted_as_before() -> None:
    """Nothing is excluded for good: after face-off, tonight's opinion with
    no capture is a real no-close again, and a game starting at `now`
    exactly has started."""
    for now in (datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)):
        counts = cl.build_clv_report(*_yesterday_and_tonight(), now=now)["counts"]
        assert counts["not_yet_played"] == 0, now
        assert counts["opinions"] == 2
        assert counts["matched"] == 1
        assert counts["no_close"] == 1
        assert counts["no_close_uncaptured"] == 1
        assert counts["bets_no_close"] == 1


@pytest.mark.parametrize("start", ["", "not a time", "2026-10-09T23:00:00"])
def test_an_unreadable_start_is_never_treated_as_not_yet_played(start: str) -> None:
    """The safe direction: an opinion whose face-off cannot be read stays in
    the ordinary counts rather than vanishing into "not yet played"."""
    counts = cl.build_clv_report(*_yesterday_and_tonight(start), now=MORNING)["counts"]

    assert counts["not_yet_played"] == 0
    assert counts["opinions"] == 2
    assert counts["no_close"] == 1
    assert counts["bets_no_close"] == 1


def test_a_game_captured_this_morning_is_still_not_yet_played() -> None:
    """The backup run: tonight's game already has a 14:00Z capture when the
    report is built at 15:00Z. It has not started, so that capture is not
    its close yet — it is not yet played, never matched."""
    opinions, captures = _yesterday_and_tonight()
    captures = pd.concat(
        [captures, pd.DataFrame([_capture(TONIGHT_START, "2026-10-09T14:00:00+00:00")])],
        ignore_index=True,
    )
    backup = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
    counts = cl.build_clv_report(opinions, captures, now=backup)["counts"]

    assert counts["not_yet_played"] == 1
    assert counts["opinions"] == 1
    assert counts["matched"] == 1
    assert counts["no_close"] == 0
    assert counts["bets_not_yet_played"] == 1


def test_not_yet_played_counts_selections_not_book_rows() -> None:
    """The snapshot freezes one row per book. "Not yet played" counts
    selections at their best price, as "Opinions considered" does."""
    opinions, captures = _yesterday_and_tonight()
    books = pd.DataFrame([{**_opinion("2026-10-09", TONIGHT_START),
                           "book": book, "american_odds": odds}
                          for book, odds in (("FD", 115), ("MGM", 105))])
    opinions = pd.concat([opinions, books], ignore_index=True)
    report = cl.build_clv_report(opinions, captures, now=MORNING)
    page = cl.render_clv(report, generated="t")

    assert report["counts"]["not_yet_played"] == 1
    assert report["counts"]["bets_not_yet_played"] == 1
    assert (
        "Not yet played: **1** opinion(s), 1 of them clearing the "
        "measurement bar"
    ) in page


def test_of_those_still_follows_the_count_it_splits() -> None:
    """"Of those" and "The other" split the no-close count. The not-yet-played
    line sits below them, so neither can be read as splitting it."""
    opinions, captures = _yesterday_and_tonight()
    moneyline = {**_opinion("2026-10-08", YESTERDAY_START), "market": "moneyline",
                 "player": "", "selection": "home", "line": None}
    gone = {**_opinion("2026-10-08", YESTERDAY_START), "line": 3.5}
    opinions = pd.concat([opinions, pd.DataFrame([moneyline, gone])], ignore_index=True)
    page = cl.render_clv(
        cl.build_clv_report(opinions, captures, now=MORNING), generated="t"
    ).splitlines()

    considered = next(i for i, line in enumerate(page)
                      if line.startswith("- Opinions considered"))
    assert "no closing price found: **2**" in page[considered]
    # The lines that split the no-close count follow it directly. #230's
    # "Within that count" line also splits that count, so it may sit between;
    # the not-yet-played line may not.
    split = page[considered + 1:]
    while split and split[0].startswith("- Within that count"):
        split = split[1:]
    assert split[0].startswith("- Of those, **1** are in a market")
    assert split[1].startswith("- The other **1** are in a market")
    assert split[2].startswith("- Not yet played: **1** opinion(s)")


def test_without_a_now_the_library_counts_every_opinion() -> None:
    counts = cl.build_clv_report(*_yesterday_and_tonight())["counts"]
    assert counts["opinions"] == 2
    assert counts["no_close"] == 1
    assert counts.get("not_yet_played", 0) == 0


# --- through the real runner -------------------------------------------------


def _run(tmp_path: Path, starts: tuple[str, str], *extra: str) -> tuple[int, str]:
    archive = tmp_path / "archive"
    snapshots = fe.snapshots_dir(archive)
    snapshots.mkdir(parents=True)
    for day, start in zip(("2026-10-08", "2026-10-09"), starts):
        pd.DataFrame([_opinion(day, start)]).to_csv(snapshots / f"{day}.csv", index=False)
    processed = tmp_path / "processed"
    processed.mkdir()
    # Two hours before yesterday's face-off, whatever year it is in.
    two_hours_before = starts[0].replace("T23:00:00Z", "T21:00:00+00:00")
    pd.DataFrame([_capture(starts[0], two_hours_before)]).to_csv(
        cl.captures_path(processed), index=False
    )
    code = load_script("run_closing_line_value.py").main(
        ["--processed-dir", str(processed), "--archive-dir", str(archive),
         "--output-dir", str(tmp_path / "out"), *extra]
    )
    return code, (tmp_path / "out" / cl.REPORT_FILENAME).read_text(encoding="utf-8")


def test_the_runner_takes_now_and_leaves_tonight_out(tmp_path: Path) -> None:
    code, page = _run(tmp_path, (YESTERDAY_START, TONIGHT_START),
                      "--now", MORNING.isoformat())

    assert code == 0
    assert "matched to a closing price: **1**" in page
    assert "no closing price found: **0**" in page
    assert "Not yet played: **1** opinion(s)" in page


def test_the_runner_reads_the_real_clock_by_default(tmp_path: Path) -> None:
    """With no `--now`, a game in 2099 has not been played and one in 2020
    has — so the default is the clock, not "no cut at all"."""
    code, page = _run(tmp_path, ("2020-10-08T23:00:00Z", "2099-10-09T23:00:00Z"))

    assert code == 0
    assert "matched to a closing price: **1**" in page
    assert "no closing price found: **0**" in page
    assert "Not yet played: **1** opinion(s)" in page


def test_the_runner_refuses_a_now_without_a_timezone(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _run(tmp_path, (YESTERDAY_START, TONIGHT_START), "--now", "2026-10-09T13:30:00")


def test_the_generated_stamp_is_the_now_the_report_was_built_for(tmp_path: Path) -> None:
    code, page = _run(tmp_path, (YESTERDAY_START, TONIGHT_START),
                      "--now", MORNING.isoformat())

    assert code == 0
    assert f"- Generated: {MORNING.isoformat(timespec='seconds')}" in page
