"""The ladder summary's rate divides wagers by wagers, not wagers by pairs.

`LadderScan.summary_line` printed `violations / comparable_pairs` as a
percentage. `violations` is one per WAGER — the over at the lower line, at
that book, deduped on the ladder key plus `low_line` however many higher
rungs contradict it — while `comparable_pairs` is every priced-low x
de-viggable-high pair. A rate over two different units is neither measure:
one mispriced low rung bounded by three higher rungs read as 1 in 3.

Display only. The registered detector's counts — `violations`,
`comparable_pairs`, the depths, the class bands and the floor — and the
fields `scripts/run_ladder_coherence.py` writes to `ladder_coherence.json`
are unchanged, and these tests hold them where they were.
"""

from __future__ import annotations

import re

import pandas as pd

from nhl_betting_lab.ladder_coherence import find_violations


def _ladder(*specs: tuple[float, str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "provider_event_id": "evt-1",
                "market": "shots_on_goal",
                "player": "A Player",
                "book": "BookOne",
                "snapshot": "2026-10-01T18:00:00Z",
                "line": line,
                "selection": side,
                "american_odds": odds,
            }
            for line, side, odds in specs
        ]
    )


# One priced-only low rung under two de-viggable higher ones. The 2.5 over at
# +200 (q = 0.333) is contradicted by both 3.5 (p = 0.5) and 4.5 (p ~ 0.48):
# ONE wager, two violating pairs. The 3.5 over is a second comparable wager
# (4.5 is above it) that does not violate. So 3 pairs, 2 wagers, 1 violation.
LADDER = _ladder(
    (2.5, "over", +200),
    (3.5, "over", -110), (3.5, "under", -110),
    (4.5, "over", +100), (4.5, "under", -120),
)


def test_the_registered_counts_are_unchanged():
    found, scan = find_violations(LADDER)
    assert len(found) == scan.violations == 1
    assert scan.comparable_pairs == 3
    assert scan.ladders == scan.ladders_with_two_lines == 1
    assert scan.ladders_with_two_rungs == 1


def test_the_rate_is_violating_wagers_over_comparable_wagers():
    _, scan = find_violations(LADDER)
    assert scan.comparable_wagers == 2
    line = scan.summary_line()
    assert "1 of 2 comparable wager(s)" in line
    assert "50.000%" in line
    # The old mixed-unit rate, 1 wager over 3 pairs.
    assert "33.333%" not in line


def test_every_percentage_printed_has_a_same_unit_denominator():
    """No percent sign may follow the pair count: pairs are printed as a
    count beside the rate, never divided into it."""
    _, scan = find_violations(LADDER)
    line = scan.summary_line()
    assert "3 comparable rung pair(s)" in line
    percentages = re.findall(r"(\d+\.\d+)%", line)
    assert percentages == ["50.000"], line


def test_a_scan_with_no_comparable_wager_prints_no_rate():
    """A ladder whose only higher rung is one-sided has no comparable wager,
    so there is nothing to divide by — and a 0.000% there would read as a
    measured clean market."""
    _, scan = find_violations(
        _ladder((2.5, "over", +200), (3.5, "over", -110))
    )
    assert scan.comparable_wagers == 0
    assert "%" not in scan.summary_line()


def test_the_json_checkpoint_fields_are_unchanged():
    """`comparable_wagers` is a display denominator; the registered JSON
    record written by `run_ladder_coherence.py` does not gain or lose a key."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_ladder_coherence.py"
    ).read_text(encoding="utf-8")
    assert "comparable_wagers" not in source
    for key in ('"comparable_pairs": scan.comparable_pairs',
                '"violations": scan.violations',
                '"ladders_with_two_rungs": scan.ladders_with_two_rungs'):
        assert key in source
