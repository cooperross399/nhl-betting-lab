"""A closing price is one captured near face-off, not merely before it.

`closing_prices` took the last capture strictly before puck drop however
early it was. The line-movement capture runs five times a day, so on a night
the last pre-face-off round misses, a 14:00Z price for a 23:00Z game was
returned as that game's close, and CLV scored an intraday price as the
market's last word. The close now has to be within `CLOSE_MAX_LEAD` of
face-off. A selection whose only pre-face-off price is older than that is
counted under its own bucket — never scored, never silently dropped — and
the report prints how many fell there.

The "strictly before face-off" rule is unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import yaml

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab.config import PROJECT_ROOT


WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"


FACE_OFF = datetime(2026, 10, 8, 23, 0, tzinfo=timezone.utc)

GAME = {
    "commence_time": "2026-10-08T23:00:00Z",
    "home_team": "Toronto Maple Leafs",
    "away_team": "Boston Bruins",
}


def _stamp(lead: timedelta) -> str:
    return (FACE_OFF - lead).isoformat()


def _opinion(**overrides) -> pd.DataFrame:
    row = {
        **GAME,
        "snapshot_date": "2026-10-08",
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 3.5,
        "american_odds": 150.0,
        "book": "DraftKings",
        "model_probability": 0.45,
        "edge": 0.05,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _capture(lead: timedelta, **overrides) -> dict:
    row = {
        **GAME,
        "captured_at": _stamp(lead),
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 3.5,
        "american_odds": 120.0,
        "book": "BetMGM",
    }
    row.update(overrides)
    return row


def test_a_capture_nine_hours_before_face_off_is_not_the_close() -> None:
    """The defect: a 14:00Z price for a 23:00Z game was returned as the close."""
    captures = pd.DataFrame([_capture(timedelta(hours=9))])

    assert cl.closing_prices(captures) == {}
    rows, counts = cl.clv_rows(_opinion(), captures)

    assert rows.empty, "an intraday price must never be scored as the close"
    assert counts["matched"] == 0
    # Counted, never dropped: it is still an opinion with no close, and it
    # is named as the specific reason.
    assert counts["no_close"] == 1
    assert counts["no_close_not_near_face_off"] == 1


def test_a_capture_thirty_minutes_before_face_off_is_the_close() -> None:
    captures = pd.DataFrame(
        [
            _capture(timedelta(hours=9), american_odds=200.0),
            _capture(timedelta(minutes=30), american_odds=110.0),
        ]
    )

    rows, counts = cl.clv_rows(_opinion(), captures)

    assert counts["matched"] == 1
    assert counts["no_close"] == 0
    assert counts["no_close_not_near_face_off"] == 0
    assert rows.iloc[0]["closing_odds"] == 110.0


def test_a_capture_exactly_at_the_bound_is_a_close() -> None:
    captures = pd.DataFrame([_capture(cl.CLOSE_MAX_LEAD)])

    rows, counts = cl.clv_rows(_opinion(), captures)

    assert counts["matched"] == 1
    assert counts["no_close_not_near_face_off"] == 0


def test_a_capture_one_second_past_the_bound_is_not_a_close() -> None:
    captures = pd.DataFrame(
        [_capture(cl.CLOSE_MAX_LEAD + timedelta(seconds=1))]
    )

    rows, counts = cl.clv_rows(_opinion(), captures)

    assert rows.empty
    assert counts["matched"] == 0
    assert counts["no_close_not_near_face_off"] == 1


def _in_season_rounds() -> list[int]:
    """Minutes past midnight UTC of every in-season Line Movement round, read
    from the workflow itself so a moved cron moves this test with it.

    In-season means every day of the month (day-of-month `*`); the opening-
    week crons name days and are not the regular schedule.
    """
    document = yaml.safe_load(
        (WORKFLOWS / "line-movement.yml").read_text(encoding="utf-8")
    )
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = document.get("on", document.get(True)) or {}
    rounds = []
    for entry in triggers.get("schedule") or []:
        minute, hour, day, _month, _weekday = str(entry["cron"]).split()
        if day != "*":
            continue
        rounds.append(int(hour) * 60 + int(minute))
    assert rounds, "no in-season cron was read from line-movement.yml"
    return sorted(set(rounds))


def _leads(start_utc_minutes: int, rounds: list[int]) -> list[int]:
    """Minutes from each daily round to the start, nearest first. Strictly
    before face-off, so a round AT the start is a day away, never zero."""
    return sorted(
        (start_utc_minutes - r) % (24 * 60) or 24 * 60 for r in rounds
    )


#: Common evening starts, as (label, UTC minutes past midnight). EDT is
#: UTC-4 (October, and from mid-March), EST is UTC-5.
EVENING_STARTS = [
    (f"{et} {zone}", ((h + offset) % 24) * 60 + m)
    for et, h, m in (("19:00", 19, 0), ("19:30", 19, 30), ("22:00", 22, 0))
    for zone, offset in (("EDT", 4), ("EST", 5))
]


def test_the_bound_is_what_the_capture_schedule_can_meet() -> None:
    """Every common evening start has a scheduled round within the bound,
    so on a normal night it closes. A 19:00 EDT start is 23:00 UTC, whose
    own round lands at or after face-off; the 21:00 round, two hours out,
    must still close it, which is why 60-90 minutes was not chosen.

    Lateness cannot break this: a late stamp is nearer face-off, and a
    round that slips past face-off hands the close to the previous round,
    stamped late by the same drift. The afternoon starts the schedule
    cannot close are recorded in `CLOSE_MAX_LEAD`'s comment, not here.
    """
    rounds = _in_season_rounds()
    for label, start in EVENING_STARTS:
        nearest = _leads(start, rounds)[0]
        assert timedelta(minutes=nearest) <= cl.CLOSE_MAX_LEAD, (
            f"a {label} start's nearest round is {nearest} minutes out, "
            "beyond the bound, so it could never close"
        )


def test_a_live_price_does_not_rescue_a_stale_one() -> None:
    """Strictly before face-off is unchanged: a price at the puck-drop second
    is still discarded, so a T-9h price alongside it is still not a close."""
    captures = pd.DataFrame(
        [
            _capture(timedelta(hours=9)),
            _capture(timedelta(0), american_odds=-300.0),
        ]
    )

    rows, counts = cl.clv_rows(_opinion(), captures)

    assert rows.empty
    assert counts["no_close_not_near_face_off"] == 1


def test_a_stale_selection_is_not_called_an_uncaptured_market() -> None:
    """The market WAS priced for that game before face-off, only too early.
    The two explanations are disjoint so the report's split adds up."""
    captures = pd.DataFrame([_capture(timedelta(hours=9))])

    report = cl.build_clv_report(_opinion(), captures)
    counts = report["counts"]

    assert counts["no_close_not_near_face_off"] == 1
    assert counts["no_close_uncaptured"] == 0
    assert report["uncaptured"] == {}


def test_the_report_prints_how_many_had_no_close_near_face_off() -> None:
    captures = pd.DataFrame(
        [
            _capture(timedelta(hours=9)),
            # A second selection that DID close, so the report has a table.
            _capture(
                timedelta(minutes=20), player="William Nylander",
                american_odds=105.0,
            ),
        ]
    )
    opinions = pd.concat(
        [_opinion(), _opinion(player="William Nylander")], ignore_index=True
    )

    report = cl.build_clv_report(opinions, captures)
    text = cl.render_clv(report)

    assert report["counts"]["matched"] == 1
    assert report["counts"]["no_close_not_near_face_off"] == 1
    assert "no close near face-off: **1**" in text


def test_the_report_split_counts_too_early_apart_from_uncaptured() -> None:
    """Uncaptured, too early, and books-pulled are three disjoint reasons.
    A moneyline opinion in a market never captured for the game, and a
    shots opinion priced only nine hours out: neither is "the other", so
    no opinion may be explained as a line the books pulled or moved."""
    captures = pd.DataFrame([_capture(timedelta(hours=9))])
    opinions = pd.concat(
        [
            _opinion(),
            _opinion(
                market="moneyline", player="", selection="away", line=None
            ),
        ],
        ignore_index=True,
    )

    report = cl.build_clv_report(opinions, captures)
    text = cl.render_clv(report)

    assert report["counts"]["no_close"] == 2
    assert report["counts"]["no_close_uncaptured"] == 1
    assert report["counts"]["no_close_not_near_face_off"] == 1
    assert "Of those, **1** are in a market" in text
    assert "no close near face-off: **1**" in text
    assert "The other" not in text, (
        "a too-early opinion was explained as a line the books pulled"
    )


def test_the_report_prints_the_bucket_even_when_it_is_empty() -> None:
    captures = pd.DataFrame([_capture(timedelta(minutes=20))])

    text = cl.render_clv(cl.build_clv_report(_opinion(), captures))

    assert "no close near face-off: **0**" in text


def test_only_stale_prices_is_not_called_the_empty_pre_season_state() -> None:
    """With nothing matched, the page used to say this is "the correct state
    and not a fault". Prices were captured; none was near face-off."""
    captures = pd.DataFrame([_capture(timedelta(hours=9))])

    text = cl.render_clv(cl.build_clv_report(_opinion(), captures))

    assert "Nothing to measure yet" in text
    assert "correct state and not a fault" not in text
    assert "no close near face-off: **1**" in text
