from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nhl_betting_lab import puck_drop


NOW = datetime(2026, 10, 8, 22, 0, tzinfo=timezone.utc)


def _at(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def test_a_future_start_is_playable() -> None:
    verdict = puck_drop.check_commence_time(_at(2), now=NOW)

    assert verdict.playable is True
    assert verdict.state == puck_drop.PLAYABLE
    assert "Puck drop is in" in verdict.reason


def test_a_past_start_is_not_playable() -> None:
    verdict = puck_drop.check_commence_time(_at(-1), now=NOW)

    assert verdict.playable is False
    assert verdict.state == puck_drop.STARTED
    assert "started" in verdict.reason


def test_a_start_exactly_now_is_started() -> None:
    """No grace period. A game that started sixty seconds ago is started."""
    verdict = puck_drop.check_commence_time(_at(0), now=NOW)

    assert verdict.playable is False


def test_a_start_one_minute_ago_is_started() -> None:
    verdict = puck_drop.check_commence_time(_at(-1 / 60), now=NOW)

    assert verdict.playable is False


@pytest.mark.parametrize("value", ["", None, "   ", "tonight", "2026-13-45", 0])
def test_an_unconfirmable_start_falls_on_the_not_a_play_side(value: object) -> None:
    verdict = puck_drop.check_commence_time(value, now=NOW)

    assert verdict.playable is False
    assert verdict.state == puck_drop.UNCONFIRMED
    assert "not-a-play side" in verdict.reason


def test_a_naive_timestamp_is_unconfirmed_not_assumed_to_be_utc() -> None:
    """Assuming would shift a start by up to a day, confidently wrong."""
    verdict = puck_drop.check_commence_time("2026-10-08T22:00:00", now=NOW)

    assert verdict.state == puck_drop.UNCONFIRMED


def test_the_z_suffix_the_provider_emits_is_accepted() -> None:
    verdict = puck_drop.check_commence_time("2026-10-09T00:00:00Z", now=NOW)

    assert verdict.playable is True


def test_an_offset_timestamp_is_compared_in_utc() -> None:
    """20:00 Eastern is 00:00 UTC the next day; both must agree."""
    verdict = puck_drop.check_commence_time("2026-10-08T20:00:00-04:00", now=NOW)

    assert verdict.playable is True
    assert verdict.commence_time.startswith("2026-10-09T00:00:00")


def test_an_aware_datetime_object_is_accepted() -> None:
    verdict = puck_drop.check_commence_time(NOW + timedelta(hours=3), now=NOW)

    assert verdict.playable is True


def test_a_naive_datetime_object_is_unconfirmed() -> None:
    verdict = puck_drop.check_commence_time(datetime(2026, 10, 9, 1, 0), now=NOW)

    assert verdict.state == puck_drop.UNCONFIRMED


def test_a_naive_now_is_a_bug_not_a_fallback() -> None:
    with pytest.raises(ValueError, match="naive"):
        puck_drop.check_commence_time(_at(2), now=datetime(2026, 10, 8, 22, 0))


# -- quarantine --------------------------------------------------------


def _selection(hours: float, units: float = 0.5, **extra: object) -> dict:
    row = {
        "home_team": "TOR",
        "away_team": "BOS",
        "market": "shots_on_goal",
        "selection": "over",
        "player": "Auston Matthews",
        "commence_time": _at(hours),
        "suggested_units": units,
    }
    row.update(extra)
    return row


def test_a_playable_selection_survives_untouched() -> None:
    result = puck_drop.apply_puck_drop_guard([_selection(3)], now=NOW)

    assert len(result.playable) == 1
    assert result.playable[0]["suggested_units"] == 0.5
    assert result.quarantined == []


def test_a_started_selection_is_quarantined() -> None:
    result = puck_drop.apply_puck_drop_guard([_selection(-2)], now=NOW)

    assert result.playable == []
    assert len(result.quarantined) == 1
    assert result.quarantined[0]["section"] == puck_drop.QUARANTINE_SECTION


def test_the_stake_field_is_removed_not_zeroed() -> None:
    """A renderer finding 0.0 units shows a zero-unit bet, which still reads
    as a recommendation."""
    result = puck_drop.apply_puck_drop_guard([_selection(-2, units=1.5)], now=NOW)
    row = result.quarantined[0]

    assert "suggested_units" not in row
    assert row["_removed_units"] == 1.5


@pytest.mark.parametrize("field", ["suggested_units", "stake_units", "units"])
def test_every_stake_field_name_is_stripped(field: str) -> None:
    row = {"commence_time": _at(-1), field: 2.0}

    result = puck_drop.apply_puck_drop_guard([row], now=NOW)

    assert field not in result.quarantined[0]


def test_the_removed_stake_is_totalled_for_the_report() -> None:
    result = puck_drop.apply_puck_drop_guard(
        [_selection(-1, units=0.5), _selection(-2, units=1.0), _selection(4)],
        now=NOW,
    )

    assert result.stake_removed == pytest.approx(1.5)
    assert "1.5 unit(s) of stake removed" in result.summary_line()


def test_an_unparseable_stake_does_not_crash_the_guard() -> None:
    result = puck_drop.apply_puck_drop_guard(
        [{"commence_time": _at(-1), "suggested_units": "n/a"}], now=NOW
    )

    assert len(result.quarantined) == 1
    assert result.stake_removed == 0.0


def test_a_selection_with_no_start_time_is_quarantined() -> None:
    result = puck_drop.apply_puck_drop_guard(
        [{"market": "points", "selection": "over"}], now=NOW
    )

    assert len(result.quarantined) == 1
    assert result.quarantined[0]["puck_drop_state"] == puck_drop.UNCONFIRMED


def test_the_guard_never_reclassifies_a_pick_as_a_pass() -> None:
    """The section heading and note must say what this is and is not."""
    result = puck_drop.apply_puck_drop_guard([_selection(-1)], now=NOW)
    rendered = "\n".join(puck_drop.render_quarantine_section(result))

    assert puck_drop.QUARANTINE_SECTION in rendered
    assert "not passes, avoids, or no-value calls" in rendered


def test_the_quarantine_section_is_absent_when_nothing_was_pulled() -> None:
    result = puck_drop.apply_puck_drop_guard([_selection(5)], now=NOW)

    assert puck_drop.render_quarantine_section(result) == []


def test_the_rendered_section_names_the_game_and_the_reason() -> None:
    result = puck_drop.apply_puck_drop_guard([_selection(-3)], now=NOW)

    rendered = "\n".join(puck_drop.render_quarantine_section(result))

    assert "BOS @ TOR" in rendered
    assert "shots_on_goal" in rendered
    assert "180 minute(s) ago" in rendered


def test_no_quarantined_row_is_still_stakeable() -> None:
    result = puck_drop.apply_puck_drop_guard(
        [_selection(-1), _selection(-2), _selection(3)], now=NOW
    )

    assert puck_drop.any_selection_is_stakeable(result.quarantined) is False
    assert puck_drop.any_selection_is_stakeable(result.playable) is True


def test_a_custom_commence_field_is_honoured() -> None:
    result = puck_drop.apply_puck_drop_guard(
        [{"start": _at(-1)}], now=NOW, commence_field="start"
    )

    assert len(result.quarantined) == 1


def test_an_empty_slate_produces_an_empty_result() -> None:
    result = puck_drop.apply_puck_drop_guard([], now=NOW)

    assert result.playable == []
    assert result.quarantined == []
    assert "still playable" in result.summary_line()


def test_the_guard_does_not_mutate_the_input_rows() -> None:
    original = _selection(-1)
    copy = dict(original)

    puck_drop.apply_puck_drop_guard([original], now=NOW)

    assert original == copy


def test_the_section_heading_uses_an_em_dash_as_documented() -> None:
    """Contract text: the renderer, the issue comment and the docs share it."""
    assert puck_drop.QUARANTINE_SECTION == "Already started — no longer plays"
