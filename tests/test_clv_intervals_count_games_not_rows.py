"""The CLV report counted every row of one game as an independent trial.

`closing_lines._summarise` took the beat-rate interval from
`wilson_interval(beat, decided)` and the CLV% and EV-at-close intervals from
`roi_interval` over the rows, and `_verdict` turned those intervals into "The
interval excludes zero". A row is one selection at its best price. The card
freezes every priced row, so one game contributes both sides of a market,
every rung of every alternate ladder and every player, and all of them move
with that game's news. `clv_rows` did not even carry the game.

Found by the failure-shape audit (finding v1, confirmed by three of three
refuters). What they measured, on the lab's own runner and the bought prices
(read-only):

* One game, 162 rows, the 2024-10-04 opener: the page printed beat rate
  78.3% [64.4%, 87.7%] and "The interval excludes zero on the positive
  side". No interval can be bounded from one game.
* The first week of 2025-26, 48 games and 8,552 rows: All opinions read
  CLV +0.33% [+0.251%, +0.404%], "excludes zero on the positive side". The
  game-clustered interval is [-0.015%, +0.670%], and a game-block bootstrap
  agrees. The design effect on mean CLV was 17-23 for opinions (the printed
  intervals 4-4.8x too narrow) and 1.2-1.6 for bets.
* By market, at the page's own Bonferroni z, `goals` opinions excluded zero
  on 142 of 167 cumulative daily reports in 2025-26 while its clustered
  interval included zero.
* A null simulation through `build_clv_report` (true mean CLV zero, 40
  games): the row-level report said "excludes zero" in 41% of runs on the
  opinions view and 27% on bets; a game-clustered interval in 5% and 6%.
* A second proxy on the whole bought store (525,821 rows over 2,708 games):
  the game-clustered SE of mean CLV is 2.05x the row SE, 2.4-2.5x in a
  season's first month; the beat-rate interval 2.72x (3.75x on goals).

Almost every flip flattered the model. `roi_interval`'s own docstring said
game dependence makes the true interval only "slightly wider"; here it is
two to five times wider. Nothing has been published yet: Closing Lines is
disabled pending Cooper's decision, so the Gameday Refresh step reads no
store. The day it reads one, it publishes this page to card-feed.

What these tests hold, through the real report path and the real runner:

* one game cannot bound an interval, however many rows it has;
* repeating every row of a game k times moves no interval and no verdict;
* one row per game keeps today's row-level intervals, bit for bit, and the
  two sides of one line (which move in opposite directions) never narrow
  below them;
* a shock every row of a game shares is not a finding;
* every interval, plain and Bonferroni-corrected, is the game-clustered one,
  computed here independently of `stats`;
* every table prints the games behind each row.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import NormalDist
from types import SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab import closing_lines as cl
from nhl_betting_lab import stats


Z95 = NormalDist().inv_cdf(0.975)

#: Six pairings, so a day's games never repeat one and the same pairing
#: recurs on every day: a key without the date would merge ten games.
MATCHUPS = (
    ("Toronto Maple Leafs", "Boston Bruins"),
    ("Montreal Canadiens", "Ottawa Senators"),
    ("Detroit Red Wings", "Buffalo Sabres"),
    ("Florida Panthers", "Tampa Bay Lightning"),
    ("New York Rangers", "New Jersey Devils"),
    ("Colorado Avalanche", "Dallas Stars"),
)

#: Closing prices: over +150, under -150. No hold, so the de-vigged fair
#: probability of the over is exactly 0.4 and EV at close equals CLV.
CLOSE_OVER = 150.0
CLOSE_UNDER = -150.0
CLOSE_OVER_DECIMAL = 2.5


def _z(looks: int) -> float:
    return Z95 if looks == 1 else NormalDist().inv_cdf(1.0 - 0.05 / (2 * looks))


def _game(index: int, *, per_day: int) -> dict:
    day = date(2026, 10, 7) + timedelta(days=index // per_day)
    home, away = MATCHUPS[index % per_day]
    return {
        "commence_time": f"{day.isoformat()}T23:00:00Z",  # 19:00 ET
        "home_team": home,
        "away_team": away,
        "snapshot_date": day.isoformat(),
        "captured_at": f"{day.isoformat()}T22:30:00+00:00",
    }


def _american(decimal: float) -> float:
    return (decimal - 1.0) * 100.0 if decimal >= 2.0 else -100.0 / (decimal - 1.0)


def _board(spec: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Opinions and captures from `spec`: one entry per selection with its
    game, market, player, CLV and edge. Every selection is an over at 2.5,
    taken at `+150 x (1 + clv)` and closing at +150 against an under at
    -150 in the same round, so its CLV is `clv` and its EV at close is too.
    An entry with `no_under` has no under captured, so it carries no EV.
    """
    opinions, captures = [], []
    for entry in spec:
        game = entry["game"]
        base = {
            "commence_time": game["commence_time"],
            "home_team": game["home_team"],
            "away_team": game["away_team"],
            "market": entry["market"],
            "player": entry["player"],
            "line": 2.5,
        }
        taken = CLOSE_OVER_DECIMAL * (1.0 + entry["clv"])
        opinions.append(
            {**base, "snapshot_date": game["snapshot_date"], "selection": "over",
             "american_odds": _american(taken), "book": "Best",
             "edge": entry["edge"]}
        )
        for selection, odds in (("over", CLOSE_OVER), ("under", CLOSE_UNDER)):
            if selection == "under" and entry.get("no_under"):
                continue
            captures.append(
                {**base, "captured_at": game["captured_at"],
                 "selection": selection, "american_odds": odds,
                 "book": "Close"}
            )
    return pd.DataFrame(opinions), pd.DataFrame(captures)


def _game_key(game: dict) -> tuple:
    return (game["home_team"], game["away_team"], game["snapshot_date"])


# -- the intervals, computed here without `stats` ---------------------------


def _clustered_mean(values: list[float], games: list, z: float) -> tuple[float, float]:
    """Mean with a CR1 cluster-robust SE, never below the SE on rows."""
    n = len(values)
    mean = statistics.fmean(values)
    residuals: dict = defaultdict(float)
    for value, game in zip(values, games):
        residuals[game] += value - mean
    count = len(residuals)
    if count < 2:
        return -math.inf, math.inf
    rows = statistics.stdev(values) / math.sqrt(n)
    clustered = math.sqrt(count / (count - 1) * sum(r * r for r in residuals.values())) / n
    se = max(rows, clustered)
    return mean - z * se, mean + z * se


def _row_mean(values: list[float], z: float) -> tuple[float, float]:
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return mean - z * se, mean + z * se


def _wilson(p: float, n: float, z: float) -> tuple[float, float]:
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _clustered_beat(beats: list[bool], games: list, z: float) -> tuple[float, float]:
    """Wilson at the game-clustered effective sample size, design effect held
    at one or above (the convention `clustered_wilson_interval` states)."""
    tally: dict = defaultdict(lambda: [0, 0])
    for beat, game in zip(beats, games):
        tally[game][0] += int(beat)
        tally[game][1] += 1
    n = len(beats)
    p = sum(beats) / n
    if len(tally) == n:
        return _wilson(p, n, z)
    spread = sum((hits - p * size) ** 2 for hits, size in tally.values())
    design_effect = max(1.0, spread / (n * p * (1 - p)))
    return _wilson(p, n / design_effect, z)


def _section(rendered: str, heading: str, until: str) -> str:
    return rendered.split(heading, 1)[1].split(until, 1)[0]


def _table_row(section: str) -> list[str]:
    (line,) = [
        line for line in section.splitlines()
        if line.startswith("| ") and "---" not in line and "Rows" not in line
    ]
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _market_row(rendered: str, market: str, view: str) -> list[str]:
    prefix = f"| `{market}` | {view} |"
    (line,) = [row for row in rendered.splitlines() if row.startswith(prefix)]
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


# -- one game ------------------------------------------------------------------


def test_one_game_cannot_bound_an_interval_however_many_rows_it_has(tmp_path) -> None:
    """The one-game opener, through the real snapshot writer, capture store
    and runner: 100 players of one game, every one taken at a longer price
    than the close. The page said "excludes zero on the positive side"."""
    from nhl_betting_lab import forward_evidence as fe
    from nhl_betting_lab.providers import odds_api
    from nhl_betting_lab.reports.card_pricing import selection_key
    from test_scripts import load_script

    game = _game(0, per_day=1)
    event = {
        "date": game["snapshot_date"], "commence_time": game["commence_time"],
        "provider_event_id": "evt1", "home_team": game["home_team"],
        "away_team": game["away_team"], "market": "shots_on_goal", "line": 2.5,
    }
    frozen, closing = [], []
    for player in range(100):
        clv = 0.002 + 0.028 * player / 99
        common = {**event, "player": f"Skater {player}"}
        frozen.append({**common, "selection": "over", "book": "Best",
                       "american_odds": _american(CLOSE_OVER_DECIMAL * (1 + clv)),
                       "fetched_at": "2026-10-07T14:55:00+00:00"})
        for selection, odds in (("over", CLOSE_OVER), ("under", CLOSE_UNDER)):
            closing.append({**common, "selection": selection, "book": "Close",
                            "american_odds": odds,
                            "fetched_at": game["captured_at"]})

    archive, processed, output = tmp_path / "archive", tmp_path / "processed", tmp_path / "out"
    probabilities = {
        selection_key(SimpleNamespace(**row), market=row["market"],
                      selection=row["selection"], line=row["line"]): 0.62
        for row in frozen
    }
    assert fe.write_snapshot(
        odds_api.to_frame(frozen), probabilities, key_for=selection_key,
        verdicts_line="props_b2b=in force", snapshot_date=game["snapshot_date"],
        now=datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc), archive_dir=archive,
    ) is not None
    cl.append_captures(
        cl.best_prices(odds_api.to_frame(closing), captured_at=game["captured_at"]),
        processed_dir=processed,
    )

    code = load_script("run_closing_line_value.py").main(
        ["--processed-dir", str(processed), "--archive-dir", str(archive),
         "--output-dir", str(output)]
    )
    rendered = (output / cl.REPORT_FILENAME).read_text(encoding="utf-8")

    assert code == 0
    assert "matched to a closing price: **100**" in rendered
    for view, until in (("opinions", "## All bets"), ("bets", "## By market")):
        section = _section(rendered, f"## All {view}", until)
        cells = _table_row(section)
        assert "too small to bound an interval" in section, section
        assert "excludes zero" not in section, section
        assert cells[:3] == ["100", "100", "0"], cells
        assert "n too small" in cells[4], cells
        assert cells[-1] == "1", f"one game behind {view}: {cells}"


# -- repeating rows inside a game ----------------------------------------------


def _repeated(copies_per_market: int, markets: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """36 games, 6 a day; each game's rows share one CLV, spread across
    `markets` so that a key holding the market would split the game."""
    rng = random.Random(1)
    spec = []
    for index in range(36):
        game = _game(index, per_day=6)
        clv = round(rng.uniform(-0.03, 0.035), 4) or 0.001
        edge = 0.10 if index % 3 else 0.01  # two games in three are bets
        for market in markets:
            for copy in range(copies_per_market):
                spec.append({"game": game, "market": market, "clv": clv,
                             "edge": edge, "player": f"Skater {index}-{copy}"})
    return _board(spec)


INTERVAL_FIELDS = (
    "beat_low", "beat_high", "beat_adjusted_low", "beat_adjusted_high",
    "clv_low", "clv_high", "clv_adjusted_low", "clv_adjusted_high",
    "ev_low", "ev_high", "ev_adjusted_low", "ev_adjusted_high",
)


def test_repeating_every_row_of_a_game_moves_no_interval_and_no_verdict() -> None:
    once = cl.build_clv_report(*_repeated(1, ("shots_on_goal",)))
    four = cl.build_clv_report(*_repeated(2, ("shots_on_goal", "points")))

    for view in ("opinions", "bets"):
        single, repeated = once["overall"][view], four["overall"][view]
        assert repeated["bets"] == 4 * single["bets"] > 0
        assert single["clv_low"] < single["clv_high"], "the fixture must spread"
        for field in INTERVAL_FIELDS:
            assert repeated[field] == pytest.approx(single[field], rel=1e-9, abs=1e-12), (
                f"{view} {field}: {repeated[field]!r} against {single[field]!r}"
            )
        assert repeated["games"] == single["games"]

    def verdicts(report: dict) -> list[str]:
        rendered = cl.render_clv(report, generated="t")
        pooled = _section(rendered, "## All opinions", "## By market")
        return [line for line in pooled.splitlines() if "interval" in line.lower()
                and not line.startswith("|")]

    assert verdicts(four) == verdicts(once)


# -- one row per game ------------------------------------------------------------


def _one_row_per_game() -> tuple[pd.DataFrame, pd.DataFrame, list[float]]:
    """60 games, one opinion each. The CLV carries a day effect and a pairing
    effect, so clustering on the day or on the pairing would widen it."""
    rng = random.Random(7)
    day_effect = [rng.uniform(-0.02, 0.02) for _ in range(10)]
    pairing_effect = [rng.uniform(-0.02, 0.02) for _ in range(6)]
    spec = []
    for index in range(60):
        clv = day_effect[index // 6] + pairing_effect[index % 6] + rng.uniform(-0.004, 0.004)
        spec.append({"game": _game(index, per_day=6), "market": "shots_on_goal",
                     "clv": clv, "edge": 0.10, "player": f"Skater {index}"})
    opinions, captures = _board(spec)
    return opinions, captures, [entry["clv"] for entry in spec]


def test_one_row_per_game_keeps_the_row_intervals_bit_for_bit() -> None:
    opinions, captures, _ = _one_row_per_game()
    rows, _ = cl.clv_rows(opinions, captures)
    summary = cl.build_clv_report(opinions, captures)["overall"]["opinions"]

    beat = int(rows["beat_close"].sum())
    decided = len(rows) - int(rows["tied_close"].sum())
    clv = stats.roi_interval([float(v) for v in rows["clv_pct"]])
    ev = stats.roi_interval([float(v) for v in rows["ev_at_close"]])

    assert (summary["beat_low"], summary["beat_high"]) == stats.wilson_interval(beat, decided)
    assert (summary["clv_low"], summary["clv_high"]) == (clv.low, clv.high)
    assert (summary["ev_low"], summary["ev_high"]) == (ev.low, ev.high)
    assert (summary["bets"], summary["games"]) == (60, 60)


def test_both_sides_of_one_line_are_never_narrower_than_the_rows() -> None:
    """An over and an under of one line move in opposite directions when the
    line moves, so the game-clustered variance is below the one on rows. The
    interval keeps the row interval there rather than narrowing."""
    opinions, captures = [], []
    for index in range(40):
        game = _game(index, per_day=5)
        move = (0.01, -0.012, 0.02, -0.004, 0.015)[index % 5] + 0.001 * (index // 5)
        base = {"commence_time": game["commence_time"], "home_team": game["home_team"],
                "away_team": game["away_team"], "market": "total_goals",
                "player": "", "line": 6.5}
        # Taken at +150 / -150; the close moved `move` towards the over.
        for selection, taken, close in (
            ("over", 2.5, 2.5 / (1 + move)),
            ("under", 2.5, 2.5 * (1 + move)),
        ):
            opinions.append({**base, "snapshot_date": game["snapshot_date"],
                             "selection": selection, "american_odds": _american(taken),
                             "book": "Best", "edge": 0.10})
            captures.append({**base, "captured_at": game["captured_at"],
                             "selection": selection, "american_odds": _american(close),
                             "book": "Close"})
    opinions, captures = pd.DataFrame(opinions), pd.DataFrame(captures)
    rows, _ = cl.clv_rows(opinions, captures)
    summary = cl.build_clv_report(opinions, captures)["overall"]["opinions"]
    values = [float(v) for v in rows["clv_pct"]]

    plain = stats.roi_interval(values)
    residual = defaultdict(float)
    mean = statistics.fmean(values)
    for index, value in enumerate(values):
        residual[index // 2] += value - mean
    clustered = math.sqrt(40 / 39 * sum(r * r for r in residual.values())) / len(values)
    assert clustered < plain.standard_error, "the fixture must be anti-correlated"
    assert (summary["clv_low"], summary["clv_high"]) == (plain.low, plain.high)
    assert (summary["bets"], summary["games"]) == (80, 40)


# -- a shock every row of a game shares -------------------------------------------


def _shared_shock() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """40 games, 4 a day, ten rows each over two markets. Every row of a game
    shares its game's movement, +2% or -2%, around a +0.5% mean; the rows
    inside a game differ by at most 0.4%."""
    spec = []
    for index in range(40):
        game = _game(index, per_day=4)
        shock = 0.02 if index % 2 == 0 else -0.02
        for row in range(10):
            spec.append({
                "game": game,
                "market": "shots_on_goal" if row < 5 else "points",
                "player": f"Skater {index}-{row}",
                "clv": 0.005 + shock + 0.004 * (row - 4.5) / 4.5,
                "edge": 0.10 if row in (0, 5) else 0.01,
            })
    opinions, captures = _board(spec)
    return opinions, captures, spec


def test_a_movement_every_row_of_a_game_shares_is_not_a_finding() -> None:
    opinions, captures, spec = _shared_shock()
    rendered = cl.render_clv(cl.build_clv_report(opinions, captures), generated="t")

    values = [entry["clv"] for entry in spec]
    games = [_game_key(entry["game"]) for entry in spec]
    row_low, _ = _row_mean(values, Z95)
    game_low, game_high = _clustered_mean(values, games, Z95)
    assert row_low > 0, "on rows the fixture excludes zero"
    assert game_low < 0 < game_high, "clustered on the game it does not"

    section = _section(rendered, "## All opinions", "## All bets")
    assert (
        "The interval includes zero, which means **no demonstrated edge** "
        "(closing-line value)."
    ) in section, section
    assert "excludes zero" not in section, section
    assert _table_row(section)[-1] == "40"


# -- the numbers themselves ---------------------------------------------------------


MARKETS = ("shots_on_goal", "points")


def _structured() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple]]:
    """30 games, 3 a day, the same three pairings every day. Each game holds
    one to three `shots_on_goal` rows and one or two `points` rows, sharing a
    game movement; the first player of each market in a game is a bet. A
    game's third `shots_on_goal` row, and the `points` bet of every fifth
    game, never had its under captured, so they carry CLV and no EV: each
    EV must still be counted in its own game."""
    rng = random.Random(157)
    spec = []
    for index in range(30):
        game = _game(index, per_day=3)
        shock = rng.uniform(-0.025, 0.03)
        for market, count in (("shots_on_goal", 1 + index % 3), ("points", 2 - index % 2)):
            for player in range(count):
                clv = shock + rng.uniform(-0.006, 0.006)
                if abs(clv) < 1e-4:
                    clv = 0.0005
                spec.append({"game": game, "market": market, "clv": clv,
                             "edge": 0.10 if player == 0 else 0.01,
                             "player": f"Skater {index}-{market}-{player}",
                             "no_under": player == 2 or (
                                 market == "points" and player == 0 and index % 5 == 0
                             )})
    opinions, captures = _board(spec)
    games = {entry["player"]: _game_key(entry["game"]) for entry in spec}
    return opinions, captures, games


def _expected(rows: pd.DataFrame, games_of: dict, z: float) -> dict[str, tuple[float, float]]:
    games = [games_of[player] for player in rows["player"]]
    decided = ~rows["tied_close"].astype(bool)
    has_ev = rows["ev_at_close"].notna()
    return {
        "beat": _clustered_beat(
            [bool(b) for b, d in zip(rows["beat_close"], decided) if d],
            [g for g, d in zip(games, decided) if d], z,
        ),
        "clv": _clustered_mean([float(v) for v in rows["clv_pct"]], games, z),
        "ev": _clustered_mean(
            [float(v) for v in rows["ev_at_close"][has_ev]],
            [g for g, keep in zip(games, has_ev) if keep], z,
        ),
    }


def _check(summary: dict, expected: dict, *, adjusted: bool, where: str) -> None:
    bound = "adjusted_" if adjusted else ""
    for name, (low, high) in expected.items():
        got = (summary[f"{name}_{bound}low"], summary[f"{name}_{bound}high"])
        assert got == pytest.approx((low, high), rel=1e-9, abs=1e-12), (
            f"{where} {name}{' corrected' if adjusted else ''}: {got} against {(low, high)}"
        )


def test_every_interval_is_the_game_clustered_one_plain_and_corrected() -> None:
    opinions, captures, games_of = _structured()
    rows, _ = cl.clv_rows(opinions, captures)
    report = cl.build_clv_report(opinions, captures)
    rows = rows.assign(is_bet=[edge >= 0.06 for edge in rows["edge"]])
    looks = report["looks"]
    assert looks == len(MARKETS) == 2

    # The fixture separates the game from the row, or it tests nothing, and
    # some rows (in both views) carry no EV.
    everything = _expected(rows, games_of, Z95)
    assert everything["clv"][0] < _row_mean([float(v) for v in rows["clv_pct"]], Z95)[0]
    assert 0 < rows["ev_at_close"].isna().sum() < len(rows)
    assert rows[rows["is_bet"]]["ev_at_close"].isna().any()

    checked = 0
    for view, frame in (("opinions", rows), ("bets", rows[rows["is_bet"]])):
        _check(report["overall"][view], _expected(frame, games_of, Z95),
               adjusted=False, where=f"All {view}")
        checked += 1
        for market in MARKETS:
            subset = frame[frame["market"] == market]
            summary = report["markets"][market][view]
            _check(summary, _expected(subset, games_of, Z95), adjusted=False,
                   where=f"{market} {view}")
            _check(summary, _expected(subset, games_of, _z(looks)), adjusted=True,
                   where=f"{market} {view}")
            checked += 2
    assert checked == 10


def test_the_by_market_table_prints_the_clustered_corrected_intervals() -> None:
    opinions, captures, games_of = _structured()
    rows, _ = cl.clv_rows(opinions, captures)
    rendered = cl.render_clv(cl.build_clv_report(opinions, captures), generated="t")

    for market in MARKETS:
        subset = rows[rows["market"] == market]
        expected = _expected(subset, games_of, _z(2))
        cells = _market_row(rendered, market, "opinions")
        beat, clv, ev = cells[5], cells[6], cells[7]
        low, high = expected["beat"]
        assert f"[{low:.1%}, {high:.1%}]" in beat, beat
        low, high = expected["clv"]
        assert f"[{low:+.2%}, {high:+.2%}]" in clv, clv
        low, high = expected["ev"]
        assert f"[{low:+.1%}, {high:+.1%}]" in ev, ev


# -- the page says what the unit is ------------------------------------------------


def test_every_table_prints_the_games_behind_each_row() -> None:
    opinions, captures, games_of = _structured()
    rows, _ = cl.clv_rows(opinions, captures)
    rendered = cl.render_clv(cl.build_clv_report(opinions, captures), generated="t")
    rows = rows.assign(game=[games_of[p] for p in rows["player"]],
                       is_bet=[edge >= 0.06 for edge in rows["edge"]])

    header = next(line for line in rendered.splitlines() if line.startswith("| Rows |"))
    assert [c.strip() for c in header.strip().strip("|").split("|")][-1] == "Games"
    opinions_row = _table_row(_section(rendered, "## All opinions", "## All bets"))
    bets_row = _table_row(_section(rendered, "## All bets", "## By market"))
    assert (opinions_row[0], opinions_row[-1]) == (str(len(rows)), "30")
    bets = rows[rows["is_bet"]]
    assert (bets_row[0], bets_row[-1]) == (str(len(bets)), str(bets["game"].nunique()))
    for market in MARKETS:
        for view, frame in (("opinions", rows), ("bets", bets)):
            subset = frame[frame["market"] == market]
            cells = _market_row(rendered, market, view)
            assert (cells[2], cells[-1]) == (str(len(subset)), str(subset["game"].nunique()))
    assert "clustered by game" in rendered


# -- the statistics ------------------------------------------------------------------


def test_clusters_of_one_are_exactly_the_row_interval() -> None:
    """Bit for bit, on a hundred samples. With one row per cluster CR1 is the
    row error algebraically, but in floating point it lands an ulp above it
    on 8 of these 100; only the exact return for clusters of one keeps
    those identical, and the floor alone does not."""
    adverse = 0
    for seed in range(100):
        rng = random.Random(seed)
        n = rng.choice((40, 60, 120, 250))
        values = [rng.uniform(-0.05, 0.06) for _ in range(n)]
        plain = stats.roi_interval(values)
        spread = sum((value - plain.roi) ** 2 for value in values)
        adverse += math.sqrt(n / (n - 1) * spread) / n > plain.standard_error
        for looks in (1, 4):
            assert stats.clustered_mean_interval(
                values, list(range(n)), looks=looks
            ) == stats.roi_interval(values, looks=looks), (seed, looks)
    assert adverse > 0, "some sample must separate CR1 from the row error"


def test_one_cluster_cannot_bound_a_mean() -> None:
    values = [0.002 + 0.0003 * index for index in range(100)]
    interval = stats.clustered_mean_interval(values, ["one game"] * 100, looks=3)

    assert (interval.bets, interval.roi) == (100, pytest.approx(statistics.fmean(values)))
    assert (interval.low, interval.high) == (-math.inf, math.inf)
    assert (interval.adjusted_low, interval.adjusted_high) == (-math.inf, math.inf)
    assert stats.clustered_mean_interval([], [], looks=1) == stats.roi_interval([])


def test_repeating_rows_inside_their_cluster_moves_nothing() -> None:
    rng = random.Random(5)
    base = [rng.uniform(-0.04, 0.05) for _ in range(40)]
    once = stats.clustered_mean_interval(base, list(range(40)), looks=3)
    for copies in (2, 5):
        values = [value for value in base for _ in range(copies)]
        clusters = [index for index in range(40) for _ in range(copies)]
        repeated = stats.clustered_mean_interval(values, clusters, looks=3)
        for field in ("roi", "low", "high", "adjusted_low", "adjusted_high"):
            assert getattr(repeated, field) == pytest.approx(getattr(once, field), rel=1e-9)


def test_the_clustered_mean_is_cr1_with_its_small_sample_factor() -> None:
    rng = random.Random(11)
    values, clusters = [], []
    for game in range(12):
        shock = rng.uniform(-0.03, 0.03)
        for _ in range(1 + game % 4):
            values.append(shock + rng.uniform(-0.002, 0.002))
            clusters.append(game)
    interval = stats.clustered_mean_interval(values, clusters, looks=5)

    assert (interval.low, interval.high) == pytest.approx(
        _clustered_mean(values, clusters, Z95), rel=1e-12
    )
    assert (interval.adjusted_low, interval.adjusted_high) == pytest.approx(
        _clustered_mean(values, clusters, _z(5)), rel=1e-12
    )
    assert interval.low < stats.roi_interval(values).low, "wider than rows here"


def test_an_anti_correlated_cluster_keeps_the_row_interval() -> None:
    values = [value for move in (0.01, 0.02, -0.015, 0.03, 0.005) * 8
              for value in (move, -move + 0.001)]
    clusters = [index // 2 for index in range(len(values))]

    assert stats.clustered_mean_interval(values, clusters, looks=2) == stats.roi_interval(
        values, looks=2
    )


def test_a_value_and_its_cluster_must_pair() -> None:
    with pytest.raises(ValueError):
        stats.clustered_mean_interval([0.1, 0.2], ["a"])


def test_the_clustered_wilson_interval_takes_a_corrected_z() -> None:
    z = stats.bonferroni_z(3)
    rng = random.Random(13)
    clusters = []
    for _ in range(50):
        size = rng.randint(1, 6)
        clusters.append((rng.randint(0, size) if rng.random() < 0.7 else size, size))
    hits = sum(h for h, _ in clusters)
    trials = sum(n for _, n in clusters)
    beats: list[bool] = []
    games: list[int] = []
    for game, (h, n) in enumerate(clusters):
        beats += [True] * h + [False] * (n - h)
        games += [game] * n

    assert stats.clustered_wilson_interval(clusters) == stats.clustered_wilson_interval(
        clusters, z=stats.Z95
    )
    assert stats.clustered_wilson_interval(clusters, z=z) == pytest.approx(
        _clustered_beat(beats, games, z), rel=1e-12
    )
    assert stats.clustered_wilson_interval(clusters, z=z) != pytest.approx(
        _clustered_beat(beats, games, Z95), rel=1e-6
    )
    singles = [(1, 1)] * hits + [(0, 1)] * (trials - hits)
    assert stats.clustered_wilson_interval(singles, z=z) == stats.wilson_interval(
        hits, trials, z=z
    )
    assert stats.clustered_wilson_interval([(2, 5)], z=z) == stats.wilson_interval_on_rate(
        0.4, 1.0, z=z
    )

