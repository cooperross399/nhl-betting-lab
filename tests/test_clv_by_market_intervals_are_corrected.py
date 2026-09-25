"""The CLV 'By market' table said its intervals were corrected, and they were not.

The table sits under "Every interval here is corrected for how many markets
share the table", and #53 added the correction together with that sentence.
Only half of it landed:

* `_summarise` computed the Bonferroni-corrected CLV interval
  (`clv_adjusted_low/high`), but `_summary_cells` rendered the plain 95% one,
  and nothing read the corrected one.
* The EV-at-close interval was computed with `looks`, and then only its plain
  95% bounds were kept.
* The beat-rate Wilson interval was never corrected at all.

Found by the failure-shape audit (finding 22, confirmed by three of three
refuters). The finder's two-market example rendered moneyline as
[-2.31%, +1.38%] where the corrected interval is [-2.57%, +1.65%]. With
three markets every interval printed was about 18% too narrow (z 1.960
against 2.394), under a heading saying it was corrected. That is the error
the heading exists to prevent: a borderline row that only looks remarkable
because a dozen were searched.

The expected intervals here are computed in this file from the per-row CLV,
EV and beat counts, independently of `stats`, and each By-market row must
print the corrected interval and not the plain one. The All-opinions table
is one test (looks = 1) and must keep the plain 95% interval. A one-market
table has nothing to correct, and it must say so rather than claim a
correction.
"""

from __future__ import annotations

import math
import random
import statistics
from statistics import NormalDist

import pandas as pd

from nhl_betting_lab import closing_lines as cl


Z95 = NormalDist().inv_cdf(0.975)
CLOSED_AT = "2026-10-08T22:30:00+00:00"
GAMES = 40
MARKETS = {
    # market: (selection, other side, line, player)
    "moneyline": ("away", "home", None, ""),
    "total_goals": ("over", "under", 6.5, ""),
    "shots_on_goal": ("over", "under", 3.5, "Auston Matthews"),
}


def _odds(rng: random.Random) -> float:
    """An American price between -200 and +200, never inside (-100, +100)."""
    value = rng.randint(100, 200)
    return float(value if rng.random() < 0.5 else -value)


def _fixture(markets: dict = MARKETS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forty games per market; the taken and closing prices vary, so beat,
    tie-free CLV and EV all spread, and half the opinions are bets."""
    rng = random.Random(22)
    opinions, captures = [], []
    for market, (side, other, line, player) in markets.items():
        for game in range(GAMES):
            base = {
                "commence_time": "2026-10-08T23:00:00Z",
                "home_team": f"Home {game}", "away_team": f"Away {game}",
                "market": market, "player": player, "line": line,
            }
            taken = _odds(rng)
            close = _odds(rng)
            while close == taken:
                close = _odds(rng)
            opinions.append({**base, "snapshot_date": "2026-10-08",
                             "selection": side, "american_odds": taken,
                             "book": "Best", "edge": 0.5 if game % 2 else -0.5})
            captures.append({**base, "captured_at": CLOSED_AT, "selection": side,
                             "american_odds": close, "book": "Close"})
            captures.append({**base, "captured_at": CLOSED_AT, "selection": other,
                             "american_odds": -close if abs(close) > 105 else -110.0,
                             "book": "Close"})
    return pd.DataFrame(opinions), pd.DataFrame(captures)


def _z(looks: int) -> float:
    return Z95 if looks == 1 else NormalDist().inv_cdf(1.0 - 0.05 / (2 * looks))


def _mean_interval(values: list[float], z: float, fmt: str) -> str:
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return f"[{mean - z * se:{fmt}}, {mean + z * se:{fmt}}]"


def _wilson(hits: int, n: int, z: float) -> str:
    p = hits / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return f"[{max(0.0, centre - margin):.1%}, {min(1.0, centre + margin):.1%}]"


def _expected(rows: pd.DataFrame, z: float) -> tuple[str, str, str]:
    beat = int(rows["beat_close"].sum())
    decided = len(rows) - int(rows["tied_close"].sum())
    ev = [float(v) for v in rows["ev_at_close"].dropna()]
    return (
        _wilson(beat, decided, z),
        _mean_interval([float(v) for v in rows["clv_pct"]], z, "+.2%"),
        _mean_interval(ev, z, "+.1%"),
    )


def _cells(rendered: str, market: str, view: str) -> list[str]:
    prefix = f"| `{market}` | {view} |"
    (line,) = [row for row in rendered.splitlines() if row.startswith(prefix)]
    return [cell.strip() for cell in line.strip("|").split("|")]


def _rendered(markets: dict = MARKETS) -> tuple[str, pd.DataFrame]:
    opinions, captures = _fixture(markets)
    rows, _ = cl.clv_rows(opinions, captures)
    report = cl.build_clv_report(opinions, captures)
    return cl.render_clv(report, generated="t"), rows


def test_every_by_market_row_prints_the_corrected_intervals() -> None:
    rendered, rows = _rendered()
    looks = len(MARKETS)
    assert looks == 3 and rows["market"].nunique() == 3

    checked = 0
    for market in MARKETS:
        subset = rows[rows["market"] == market]
        is_bet = [row.edge > 0 for row in subset.itertuples()]
        for view, frame in (("opinions", subset), ("bets", subset[is_bet])):
            cells = _cells(rendered, market, view)
            beat, clv, ev = cells[5], cells[6], cells[7]
            corrected = _expected(frame, _z(looks))
            plain = _expected(frame, Z95)
            assert corrected != plain, "the fixture must separate the two"
            for cell, want, not_want in zip((beat, clv, ev), corrected, plain):
                assert want in cell, f"{market}/{view}: {cell!r} lacks {want}"
                assert not_want not in cell, f"{market}/{view}: {cell!r} is uncorrected"
                checked += 1
    assert checked == 18, "three columns, two views, three markets"


def test_the_all_opinions_table_is_one_test_and_keeps_the_plain_interval() -> None:
    rendered, rows = _rendered()

    beat, clv, ev = _expected(rows, Z95)
    section = rendered.split("## All opinions", 1)[1].split("## All bets", 1)[0]
    (row,) = [line for line in section.splitlines()
              if line.startswith("| ") and "---" not in line and "Rows" not in line]

    assert beat in row and clv in row and ev in row


def test_the_by_market_heading_names_the_correction_and_its_factor() -> None:
    rendered, _ = _rendered()
    section = rendered.split("## By market", 1)[1].split("## How to read this", 1)[0]
    header = [line for line in section.splitlines() if line.startswith("| Market")]

    assert len(header) == 1
    for column in ("Beat rate", "Mean CLV%", "EV at close"):
        (label,) = [c for c in header[0].split("|") if column in c]
        assert "3 markets" in label, label
    assert f"z = {_z(3):.3f}" in section, "the correction prints its factor"


def test_a_one_market_table_says_there_is_nothing_to_correct() -> None:
    """With one market the corrected and plain intervals are the same numbers,
    so the page must not claim a correction it did not need to make."""
    rendered, rows = _rendered({"moneyline": MARKETS["moneyline"]})
    section = rendered.split("## By market", 1)[1].split("## How to read this", 1)[0]

    assert "corrected for" not in section
    cells = _cells(rendered, "moneyline", "opinions")
    for cell, want in zip((cells[5], cells[6], cells[7]), _expected(rows, Z95)):
        assert want in cell
