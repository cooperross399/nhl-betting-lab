"""A same-day leak into the walk-forward calibration could not fail the suite.

`walk_forward_calibrate` promises that the correction applied to a sample was
fitted only on samples from strictly earlier game-days. Its docstring calls
that strictness "the point": one game-day's props share lineup assumptions, so
a fit that includes the day it corrects leaks within the day although the
dates look ordered. The only test of the promise,
`test_walk_forward_never_scores_a_sample_with_its_own_day`, asserted that
each correction's date stamp is a scored date. That holds whatever went into
the fit. Its comment says "that day's samples were not in the fit that
produced it", and nothing checked it.

Found by the failure-shape audit and confirmed by three of three refuters.
With m23, the pooled fit given `history + same_day`, the whole suite gave
1768 passed. On the old test's own fixture, all 225 corrections were fitted
on 208 samples instead of 200. All 1,800 corrected probabilities changed, and
the corrected Brier fell from 0.21731 to 0.21620. Through the real runners on
the real sample stores, both contract reports published the leak with exit 0.
`props_calibration.md` said "fitted on 245406 samples" where the honest number
is 245000, and its goalie_saves delta moved from -0.00026 to -0.00017. The
team measurement's moneyline delta moved from +0.00012 to +0.00021. Every
changed delta moved in the flattering direction. The report would still have
said its corrections were fitted "only on samples from strictly earlier
game-days". The refuters also found that a leak into the per-group
(ice-time) fits gets past a check that looks only at the pooled fit.

The production code was correct throughout. What was missing was a test that
could tell it apart from a broken one. These tests restate the walk-forward
from its contract (`_reference`): for each game-day, the fit is made on the
rows dated strictly before it, and a refit happens on the first scored day
and every `refit_every` scored days after. The tests then compare the
real function against that restatement, and the two published reports
against it:

* every correction is fitted on exactly the samples dated before its stamp:
  `fitted_on`, intercept and slope;
* every scored sample is corrected by the fit in force for its day, and no
  later fit. This is checked pooled, per group with the pooled fallback, and
  under a refit schedule;
* a planted day of 40 extreme samples is corrected without itself. Including
  it moves that day's corrected 0.80 by 0.24, so a leak of that day is not a
  rounding question. The fixture checks this about itself;
* `props_calibration.json`/`.md` and `team_markets_measurement.json`/`.md`,
  built and saved by the real report code, carry the strictly-earlier
  numbers: corrected Brier, per-ice-time Brier, and the printed correction
  with its sample count. The leaked alternative is computed beside them, and
  the test checks it would have differed.

The existing test is left unchanged. It asserts nothing false, only too
little, and its comment's claim is now checked here.
"""

from __future__ import annotations

import inspect
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from nhl_betting_lab.models import calibration as cal
from nhl_betting_lab.reports import props_calibration as props_report
from nhl_betting_lab.reports import team_markets_measurement as team_report


#: The production floor: a correction is fitted only once this much history
#: exists, and before that the day is warm-up.
MINIMUM = cal.PlattCalibration.MINIMUM_SAMPLES
START = date(2025, 1, 1)
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

#: The planted day: a pile of confident losses. Fitting on it drags the whole
#: curve down, so a correction that saw it is unmistakable.
PLANTED_PROBABILITY = 0.80
PLANTED_COUNT = 40
#: How far including the planted day must move its own corrected value for the
#: fixture to be worth anything. Measured: 0.24 pooled, 0.27 in the one group.
PLANTED_SHIFT_FLOOR = 0.15

#: A leak of the same day must move a published Brier by at least this much
#: for the report fixtures to test anything. Measured: 0.015 pooled and 0.036
#: by ice time on the props fixture, 0.015 on the team fixture.
BRIER_SHIFT_FLOOR = 1e-3

#: Same data, same order, same arithmetic: the two sides agree to float noise.
#: A single leaked sample moves a corrected probability by about 1e-3.
TOLERANCE = 1e-12


def _day(offset: int) -> str:
    return (START + timedelta(days=offset)).isoformat()


# -- the contract, restated ----------------------------------------------


@dataclass
class _Walk:
    scored: list[tuple[str, float, float, bool]] = field(default_factory=list)
    #: Per scored row: "group" when a group's own fit corrected it, else "pooled".
    source: list[str] = field(default_factory=list)
    #: Per scored row: the group it belongs to ("" when not grouped).
    groups: list[str] = field(default_factory=list)
    corrections: list[tuple[str, cal.PlattCalibration]] = field(default_factory=list)
    warmup: int = 0

    @property
    def corrected_brier(self) -> float | None:
        return cal.brier_score([(fixed, won) for _, _, fixed, won in self.scored])


def _reference(
    rows: list[tuple],
    *,
    minimum: int = MINIMUM,
    refit_every: int = 1,
    grouped: bool = False,
    fit_through_own_day: bool = False,
) -> _Walk:
    """The walk-forward, restated from its contract rather than its loop.

    For every game-day the fit is made on the rows dated strictly before it
    (`<`), not carried along in a running history. That is the property.
    `fit_through_own_day=True` is the leak (`<=`) and is used only to show
    that each fixture could see a leak. It keeps the honest warm-up boundary,
    so it is exactly m23. Rows keep the function's order, a stable sort on
    the date, so the fits are the same arithmetic on the same list.
    """
    ordered = sorted(rows, key=lambda row: row[0])
    walk = _Walk()
    scored_days = 0
    pooled = cal.PlattCalibration.identity()
    by_group: dict[str, cal.PlattCalibration] = {}
    for day in sorted({row[0] for row in ordered}):
        today = [row for row in ordered if row[0] == day]
        before = [row for row in ordered if row[0] < day]
        if len(before) < minimum:
            walk.warmup += len(today)
            continue
        if scored_days % max(1, refit_every) == 0:
            fitted = (
                [row for row in ordered if row[0] <= day]
                if fit_through_own_day
                else before
            )
            pooled = cal.PlattCalibration.fit(
                [(row[1], row[2]) for row in fitted], minimum=minimum
            )
            walk.corrections.append((day, pooled))
            if grouped:
                names = sorted({row[3] for row in fitted})
                by_group = {
                    name: cal.PlattCalibration.fit(
                        [(row[1], row[2]) for row in fitted if row[3] == name],
                        minimum=minimum,
                    )
                    for name in names
                }
        scored_days += 1
        for row in today:
            own = by_group.get(row[3]) if grouped else None
            use_own = own is not None and not own.is_identity
            correction = own if use_own else pooled
            walk.scored.append((day, row[1], correction.apply(row[1]), row[2]))
            walk.source.append("group" if use_own else "pooled")
            walk.groups.append(row[3] if grouped else "")
    return walk


def _assert_same_walk(result: cal.WalkForwardResult, expected: _Walk) -> None:
    assert result.warmup_skipped == expected.warmup
    assert len(result.scored) == len(expected.scored)
    for got, want in zip(result.scored, expected.scored):
        assert got[0] == want[0] and got[1] == want[1] and got[3] == want[3]
        assert got[2] == pytest.approx(want[2], abs=TOLERANCE), (got, want)


def _assert_same_corrections(
    got: list[tuple[str, cal.PlattCalibration]],
    want: list[tuple[str, cal.PlattCalibration]],
) -> None:
    assert [day for day, _ in got] == [day for day, _ in want]
    for (day, fit), (_, expected) in zip(got, want):
        assert fit.fitted_on == expected.fitted_on, (day, fit, expected)
        assert fit.intercept == pytest.approx(expected.intercept, abs=TOLERANCE)
        assert fit.slope == pytest.approx(expected.slope, abs=TOLERANCE)


# -- fixtures --------------------------------------------------------------


#: Eight props a game-day for sixty days. The 200-sample floor is first met on
#: day 25, and day 37 is a refit day under refit_every 1 and 3.
POOLED_DAYS = 60
POOLED_PER_DAY = 8
POOLED_PLANTED = 37


def _pooled_rows() -> list[tuple[str, float, bool]]:
    """A model that runs hot, as the per-player Poisson does, plus one planted
    day of confident losses."""
    rng = random.Random(20250101)
    rows: list[tuple[str, float, bool]] = []
    for offset in range(POOLED_DAYS):
        for _ in range(POOLED_PER_DAY):
            claimed = rng.uniform(0.15, 0.85)
            true = claimed - 0.10 * (claimed - 0.10)
            rows.append((_day(offset), claimed, rng.random() < true))
        if offset == POOLED_PLANTED:
            rows.extend(
                [(_day(offset), PLANTED_PROBABILITY, False)] * PLANTED_COUNT
            )
    return rows


GROUPED_DAYS = 70
GROUPED_PLANTED = 50


def _grouped_rows() -> list[tuple[str, float, bool, str]]:
    """Two groups miscalibrated in opposite directions, one too rare ever to be
    fitted, and a planted day in one group.

    Twelve rows a day: pooled history reaches 200 on day 17, each common group
    on day 34, so days 17-33 fall back to the pooled curve for every group and
    later days use each group's own. The rare group never reaches 200.
    """
    rng = random.Random(20250202)
    rows: list[tuple[str, float, bool, str]] = []
    for offset in range(GROUPED_DAYS):
        day = _day(offset)
        for _ in range(6):
            claimed = rng.uniform(0.2, 0.8)
            rows.append((day, claimed, rng.random() < 0.6 * claimed, "hot"))
            claimed = rng.uniform(0.2, 0.8)
            rows.append(
                (day, claimed, rng.random() < min(0.95, 1.25 * claimed), "cold")
            )
        if offset % 10 == 3:
            rows.append((day, 0.5, rng.random() < 0.5, "rare"))
        if offset == GROUPED_PLANTED:
            rows.extend(
                [(day, PLANTED_PROBABILITY, False, "cold")] * PLANTED_COUNT
            )
    return rows


# -- the function ----------------------------------------------------------


def test_every_correction_is_fitted_on_exactly_the_days_before_it() -> None:
    rows = _pooled_rows()

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=MINIMUM)
    expected = _reference(rows)

    # 35 refits, one per scored day, each carrying its own sample count.
    assert len(expected.corrections) == POOLED_DAYS - MINIMUM // POOLED_PER_DAY
    for day, fit in result.corrections:
        assert fit.fitted_on == sum(1 for row in rows if row[0] < day), day
    _assert_same_corrections(result.corrections, expected.corrections)


def test_every_scored_sample_is_corrected_by_a_fit_that_never_saw_its_day() -> None:
    rows = _pooled_rows()

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=MINIMUM)

    assert result.warmup_skipped == MINIMUM
    _assert_same_walk(result, _reference(rows))


def test_a_planted_extreme_day_is_corrected_without_itself() -> None:
    rows = _pooled_rows()
    planted = _day(POOLED_PLANTED)
    before = cal.PlattCalibration.fit(
        [(p, won) for day, p, won in rows if day < planted], minimum=MINIMUM
    )
    through = cal.PlattCalibration.fit(
        [(p, won) for day, p, won in rows if day <= planted], minimum=MINIMUM
    )
    honest = before.apply(PLANTED_PROBABILITY)
    leaked = through.apply(PLANTED_PROBABILITY)
    # The fixture's own premise: a fit that saw the planted day corrects it
    # very differently. If this fails, the fixture tests nothing.
    assert abs(honest - leaked) > PLANTED_SHIFT_FLOOR, (honest, leaked)

    result = cal.walk_forward_calibrate(rows, minimum_fit_samples=MINIMUM)

    on_the_day = [row for row in result.scored if row[0] == planted]
    planted_rows = [row for row in on_the_day if row[1] == PLANTED_PROBABILITY]
    assert len(planted_rows) == PLANTED_COUNT
    for _, raw, fixed, _ in on_the_day:
        assert fixed == pytest.approx(before.apply(raw), abs=TOLERANCE)
    for _, _, fixed, _ in planted_rows:
        assert abs(fixed - leaked) > PLANTED_SHIFT_FLOOR
    stamped = dict(result.corrections)[planted]
    assert stamped.fitted_on == before.fitted_on
    assert stamped.fitted_on != through.fitted_on
    assert stamped.describe() == before.describe()


def test_each_group_is_corrected_by_its_own_strictly_earlier_history() -> None:
    rows = _grouped_rows()

    result = cal.walk_forward_calibrate(
        rows, minimum_fit_samples=MINIMUM, grouped=True
    )
    expected = _reference(rows, grouped=True)

    # The fixture exercises all three paths: a group's own curve, the pooled
    # fallback for a group still too short, and the pooled curve for a group
    # that never qualifies.
    by_group: dict[str, set[str]] = {}
    for group, source in zip(expected.groups, expected.source):
        by_group.setdefault(group, set()).add(source)
    assert by_group == {
        "hot": {"group", "pooled"},
        "cold": {"group", "pooled"},
        "rare": {"pooled"},
    }
    planted = _day(GROUPED_PLANTED)
    cold_before = cal.PlattCalibration.fit(
        [(p, w) for d, p, w, g in rows if g == "cold" and d < planted],
        minimum=MINIMUM,
    )
    cold_through = cal.PlattCalibration.fit(
        [(p, w) for d, p, w, g in rows if g == "cold" and d <= planted],
        minimum=MINIMUM,
    )
    assert (
        abs(
            cold_before.apply(PLANTED_PROBABILITY)
            - cold_through.apply(PLANTED_PROBABILITY)
        )
        > PLANTED_SHIFT_FLOOR
    )

    _assert_same_walk(result, expected)
    _assert_same_corrections(result.corrections, expected.corrections)
    for day, raw, fixed, won in result.scored:
        if day == planted and raw == PLANTED_PROBABILITY and not won:
            assert fixed == pytest.approx(
                cold_before.apply(raw), abs=TOLERANCE
            )


def test_a_correction_held_between_refits_was_fitted_before_its_refit_day() -> None:
    """The reports refit every five scored days, not every day. A held
    correction must still be the one fitted strictly before the day it was
    refit, and no fresher one."""
    rows = _pooled_rows()

    result = cal.walk_forward_calibrate(
        rows, minimum_fit_samples=MINIMUM, refit_every=3
    )
    expected = _reference(rows, refit_every=3)

    scored_days = sorted({row[0] for row in expected.scored})
    assert [day for day, _ in expected.corrections] == scored_days[::3]
    assert _day(POOLED_PLANTED) in dict(expected.corrections)
    _assert_same_corrections(result.corrections, expected.corrections)
    _assert_same_walk(result, expected)


# -- the published reports ---------------------------------------------------


REPORT_DAYS = 60
#: A refit day under the reports' refit_every of 5: 12 rows a day reach the
#: floor on day 17, so refits fall on days 17, 22, ... 42.
REPORT_PLANTED = 42


def _props_frame() -> pd.DataFrame:
    """Shots-on-goal samples in two ice-time buckets that need opposite
    corrections, with a planted day of confident losses in one of them."""
    rng = random.Random(20250303)
    records: list[dict[str, object]] = []
    game_id = 0

    def add(day: str, claimed: float, won: bool, seconds: int, player: int) -> None:
        nonlocal game_id
        game_id += 1
        records.append(
            {
                "date": day,
                "game_id": game_id,
                "player_id": player,
                "market": "shots_on_goal",
                "line": 2.5,
                "model_probability": claimed,
                "outcome": won,
                "actual": 3.0 if won else 1.0,
                "toi_seconds": seconds,
            }
        )

    for offset in range(REPORT_DAYS):
        day = _day(offset)
        for slot in range(12):
            low_minutes = slot % 2 == 0
            claimed = rng.uniform(0.2, 0.8)
            chance = 0.6 * claimed if low_minutes else min(0.95, 1.25 * claimed)
            add(day, claimed, rng.random() < chance, 600 if low_minutes else 1400, slot)
        if offset == REPORT_PLANTED:
            for slot in range(PLANTED_COUNT):
                add(day, PLANTED_PROBABILITY, False, 1400, 100 + slot)
    return pd.DataFrame(records)


def _team_frame() -> pd.DataFrame:
    """Moneyline samples, both sides of every game, from a model that runs
    hot, with a planted day of confident home favourites who all lost."""
    rng = random.Random(20250404)
    records: list[dict[str, object]] = []
    game_id = 0

    def add(day: str, home: float, home_won: bool) -> None:
        nonlocal game_id
        game_id += 1
        for selection, probability, won in (
            ("away", 1.0 - home, not home_won),
            ("home", home, home_won),
        ):
            records.append(
                {
                    "date": day,
                    "game_id": game_id,
                    "home_team": "TOR",
                    "away_team": "BOS",
                    "market": "moneyline",
                    "selection": selection,
                    "line": None,
                    "model_probability": probability,
                    "outcome": won,
                    "push": False,
                    "home_goals": 4 if home_won else 2,
                    "away_goals": 2 if home_won else 4,
                    "regulation": True,
                }
            )

    for offset in range(REPORT_DAYS):
        day = _day(offset)
        for _ in range(6):
            home = rng.uniform(0.25, 0.80)
            add(day, home, rng.random() < 0.5 + 0.8 * (home - 0.5))
        if offset == REPORT_PLANTED:
            for _ in range(PLANTED_COUNT // 2):
                add(day, PLANTED_PROBABILITY, False)
    return pd.DataFrame(records)


def _default_refit(function) -> int:
    """The refit cadence the report actually runs with, read off the code."""
    return int(inspect.signature(function).parameters["refit_every"].default)


def test_the_props_report_publishes_only_strictly_earlier_corrections(
    tmp_path: Path,
) -> None:
    frame = _props_frame()
    refit_every = _default_refit(props_report.measure_market)
    pooled_rows = [
        (row.date, row.model_probability, bool(row.outcome))
        for row in frame.itertuples()
    ]
    grouped_rows = [
        (row.date, row.model_probability, bool(row.outcome), str(row.toi_seconds))
        for row in frame.itertuples()
    ]
    honest = _reference(pooled_rows, refit_every=refit_every)
    honest_grouped = _reference(grouped_rows, refit_every=refit_every, grouped=True)
    leaked = _reference(pooled_rows, refit_every=refit_every, fit_through_own_day=True)
    leaked_grouped = _reference(
        grouped_rows, refit_every=refit_every, grouped=True, fit_through_own_day=True
    )
    # The fixture's premises: the planted day is a refit day, both buckets
    # reach their own curve, and a leak would move what is published.
    assert _day(REPORT_PLANTED) in dict(honest.corrections)
    assert set(honest_grouped.source) == {"group", "pooled"}
    assert abs(honest.corrected_brier - leaked.corrected_brier) > BRIER_SHIFT_FLOOR
    assert (
        abs(honest_grouped.corrected_brier - leaked_grouped.corrected_brier)
        > BRIER_SHIFT_FLOOR
    )
    last = honest.corrections[-1][1]
    assert last.describe() != leaked.corrections[-1][1].describe()

    report = props_report.build_calibration_report(
        frame, now=NOW, minimum_fit_samples=MINIMUM
    )
    written = props_report.save_calibration_report(report, output_dir=tmp_path)

    payload = json.loads(
        (tmp_path / props_report.CALIBRATION_JSON_FILENAME).read_text(encoding="utf-8")
    )
    (market,) = payload["markets"]
    assert market["market"] == "shots_on_goal"
    assert {row["bucket"] for row in market["grouped_volume_rows"]} == {
        "under 12 min",
        "20 min and up",
    }
    assert market["samples"] == len(honest.scored)
    assert market["warmup_skipped"] == honest.warmup
    assert market["corrected_brier"] == pytest.approx(
        honest.corrected_brier, abs=TOLERANCE
    )
    assert market["grouped_brier"] == pytest.approx(
        honest_grouped.corrected_brier, abs=TOLERANCE
    )
    assert market["correction"]["fitted_on"] == last.fitted_on
    assert market["correction"]["intercept"] == pytest.approx(
        last.intercept, abs=TOLERANCE
    )
    assert market["correction"]["slope"] == pytest.approx(last.slope, abs=TOLERANCE)
    assert Path(written["json"]) == tmp_path / props_report.CALIBRATION_JSON_FILENAME
    markdown = Path(written["markdown"]).read_text(encoding="utf-8")
    assert last.describe() in markdown
    assert leaked.corrections[-1][1].describe() not in markdown


def test_the_team_report_publishes_only_strictly_earlier_corrections(
    tmp_path: Path,
) -> None:
    frame = _team_frame()
    refit_every = _default_refit(team_report.measure_calibration)
    rows = [
        (row.date, row.model_probability, bool(row.outcome))
        for row in frame.itertuples()
    ]
    honest = _reference(rows, refit_every=refit_every)
    leaked = _reference(rows, refit_every=refit_every, fit_through_own_day=True)
    assert _day(REPORT_PLANTED) in dict(honest.corrections)
    assert abs(honest.corrected_brier - leaked.corrected_brier) > BRIER_SHIFT_FLOOR
    last = honest.corrections[-1][1]
    assert last.describe() != leaked.corrections[-1][1].describe()

    # No prices, and an explicit empty map in a scratch directory, so nothing
    # is read from the real data tree.
    report = team_report.build_team_measurement(
        frame,
        now=NOW,
        minimum_fit_samples=MINIMUM,
        team_names={},
        processed_dir=tmp_path,
    )
    team_report.save_team_measurement(report, output_dir=tmp_path)

    (measured,) = report.markets
    assert measured.correction.fitted_on == last.fitted_on
    assert measured.correction.intercept == pytest.approx(
        last.intercept, abs=TOLERANCE
    )
    assert measured.correction.slope == pytest.approx(last.slope, abs=TOLERANCE)
    payload = json.loads(
        (tmp_path / team_report.MEASUREMENT_JSON_FILENAME).read_text(encoding="utf-8")
    )
    (market,) = payload["markets"]
    assert market["market"] == "moneyline"
    assert market["samples"] == len(honest.scored)
    assert market["corrected_brier"] == pytest.approx(
        honest.corrected_brier, abs=TOLERANCE
    )
    markdown = (tmp_path / team_report.MEASUREMENT_MARKDOWN_FILENAME).read_text(
        encoding="utf-8"
    )
    assert last.describe() in markdown
    assert leaked.corrections[-1][1].describe() not in markdown
