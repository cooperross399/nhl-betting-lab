"""The team report called its wager counts prices and rows, next to real row counts.

`measure_prices` collapses each market to one bet per wager at the best price
any book quoted (`stores.best_price_per_wager`) and only then counts
`accounting["seen"]`, `unresolved`, `unmatched` and the rest. That is the
right unit: twenty-one books quoting one game are one bet. But three places
printed those per-wager counts as prices or rows:

* the reconciliation line, "`moneyline`: 4,200 prices seen ... (96% matched)";
* the standing note, "Team names: 0 of the 16,708 prices scored ...";
* the runner's stdout, "Unresolved team names: N priced row(s)."

Each sat beside "Prices measured: 212,964 of 308,944 stored rows", which does
count rows. Measured on the bought `late` window: moneyline is 71,430 book
quotes and 4,200 wagers, puck line 70,298 and 4,582, totals 71,236 and 7,926
(9x to 17x). The three "prices seen" summed to 16,708, printed a few lines
from "212,964" prices measured. With one real provider spelling ("St Louis
Blues") dropped from the map, the runner said "1,078 priced row(s)" while
14,042 quote rows in the window named that team. The refusal for a map that
resolves nothing ("Not one of the N `moneyline` price row(s)") counted wagers
under the same label. No verdict, ROI or interval moved; only the unit did.

Found by the failure-shape audit (units), confirmed by two of three
refuters; the third read the wording as ambiguous rather than wrong. What
these tests hold, through the real report, its JSON, and the runner's
`main()`, on stores where several books quote each wager (two shapes, so a
count that equals a constant cannot pass):

* every count taken after the collapse is printed as wagers, and the book
  quotes it was taken from are counted and printed beside it;
* the per-market quote counts add up to the "Prices measured" row figure,
  which is still printed as rows;
* the refusal names the rows it read as rows and the wagers as wagers;
* a reconciliation gap is a gap in wagers, and a record with no quote count
  prints none rather than passing the wager count off as one.

No number the lab has published moves. Measured on a scratch copy of the
bought store, before and after: the rendered report and its JSON differ
only in these labels and the new `quotes` and `scored_wagers` fields.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as team_names_module
from nhl_betting_lab.providers.team_names import save_team_name_map
from nhl_betting_lab.reports import team_markets_measurement as tmm


def load_script(name: str) -> ModuleType:
    """Import a script by path, as `tests/test_scripts.py` does."""
    path = PROJECT_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"_script_{path.stem}", path)
    assert spec and spec.loader, name
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Keyed the way `load_team_name_map` keys it: normalized name -> abbreviation.
#: Vancouver is deliberately absent, so its game is an unresolved wager.
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}

#: (league date, UTC face-off). Evening starts, so the league date is the
#: day before the UTC one.
GAMES = [
    ("2025-01-09", "2025-01-10T00:00:00Z"),
    ("2025-01-11", "2025-01-12T00:00:00Z"),
    ("2025-01-14", "2025-01-15T00:00:00Z"),
]
UNRESOLVED_GAME = ("2025-01-16", "2025-01-17T00:00:00Z")

BOOKS = ("DraftKings", "FanDuel", "BetMGM", "Caesars", "PointsBet")

#: Books quoting each of the three resolvable games, and the unresolved one.
#: Four wagers either way; 9 and 11 book quotes; the unresolved wager is 2
#: and 3 quotes. A label that printed quotes as wagers, or wagers as quotes,
#: fails both.
SHAPES = {
    "books-4-2-1-and-2": ((4, 2, 1), 2),
    "books-2-5-1-and-3": ((2, 5, 1), 3),
}


def _quotes(shape: str) -> int:
    per_game, unresolved = SHAPES[shape]
    return sum(per_game) + unresolved


def _samples() -> pd.DataFrame:
    """The model says 60% home on every TOR-BOS game; home wins them all."""
    return pd.DataFrame(
        [
            {
                "game_id": index,
                "date": day,
                "home_team": "TOR",
                "away_team": "BOS",
                "market": "moneyline",
                "selection": "home",
                "line": None,
                "model_probability": 0.60,
                "outcome": True,
                "push": False,
            }
            for index, (day, _) in enumerate(GAMES)
        ]
    )


def _row(day: str, commence: str, home: str, book: str, odds: int) -> dict:
    snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=2)
    return {
        "date": day,
        "commence_time": commence,
        "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": home,
        "away_team": "Boston Bruins",
        "market": "moneyline",
        "selection": "home",
        "line": None,
        "american_odds": odds,
        "book": book,
    }


def _store(shape: str) -> pd.DataFrame:
    """`late`-window moneyline quotes, several books per wager.

    Every book's price is at least +130 (43% implied) against the model's
    60%, so each resolvable wager is a bet at its best price.
    """
    per_game, unresolved = SHAPES[shape]
    rows = [
        _row(day, commence, "Toronto Maple Leafs", BOOKS[book], 150 - 5 * book)
        for (day, commence), books in zip(GAMES, per_game)
        for book in range(books)
    ]
    rows += [
        _row(*UNRESOLVED_GAME, "Vancouver Canucks", BOOKS[book], 150 - 5 * book)
        for book in range(unresolved)
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """No test here may read the real `data/processed` or boxscore cache."""
    processed = tmp_path / "default_processed"
    raw = tmp_path / "default_raw"
    processed.mkdir()
    raw.mkdir()
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(team_names_module, "RAW_DIR", raw)
    return SimpleNamespace(processed=processed, raw=raw)


def _report(shape: str) -> tmm.TeamMeasurementReport:
    return tmm.build_team_measurement(
        _samples(), _store(shape), team_names=TEAM_MAP, phase="late"
    )


# --------------------------------------------------------------------------
# The report.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_reconciliation_counts_wagers_and_names_the_quotes_behind_them(
    shape: str, defaults: SimpleNamespace
) -> None:
    """It printed "N prices seen" where N was the wagers left by the collapse."""
    report = _report(shape)
    moneyline = report.markets[0]
    rendered = tmm.render_team_measurement(report)

    # The counts themselves are unchanged: one per wager.
    assert moneyline.accounting["seen"] == 4
    assert moneyline.accounting["unresolved"] == 1
    assert moneyline.priced is not None and moneyline.priced.bets == 3
    # And the quotes they were collapsed from are counted, not guessed.
    assert moneyline.accounting["quotes"] == _quotes(shape)
    assert (
        f"- `moneyline`: 4 wager(s) seen, each at its best price among "
        f"{_quotes(shape)} book quote(s), 1 naming a team the map could not "
        "resolve, 0 unmatched (75% matched), 0 below threshold, 3 bets."
    ) in rendered.splitlines()
    assert "prices seen" not in rendered
    assert "DOES NOT RECONCILE" not in rendered
    # The section says what it counts, above the lines.
    assert "Everything here is counted one per wager, at the best price" in (
        rendered
    )


def test_a_gap_is_counted_in_wagers_and_no_quote_figure_is_invented() -> None:
    """The two branches the real stores never reach, on the real method.

    A gap between the buckets and `seen` is a gap in wagers, and it said
    "row(s) dropped". A measurement recorded before `quotes` existed prints
    no quote figure rather than passing its wager count off as one.
    """
    gap = tmm.MarketMeasurement(
        market="moneyline",
        accounting={"quotes": 9, "seen": 5, "unresolved": 0, "unmatched": 1},
    )
    unrecorded = tmm.MarketMeasurement(
        market="moneyline",
        accounting={"seen": 5, "unresolved": 0, "unmatched": 5},
    )

    assert gap.reconciliation_line() == (
        "`moneyline`: 5 wager(s) seen, each at its best price among 9 book "
        "quote(s), 0 naming a team the map could not resolve, 1 unmatched "
        "(80% matched), 0 below threshold, 0 bets. **DOES NOT RECONCILE**: 4 "
        "wager(s) dropped by a path with no counter."
    )
    assert unrecorded.reconciliation_line() == (
        "`moneyline`: 5 wager(s) seen, each at its best price, 0 naming a "
        "team the map could not resolve, 5 unmatched (0% matched), 0 below "
        "threshold, 0 bets."
    )


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_team_names_note_counts_wagers(
    shape: str, tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """ "Team names: X of the Y prices scored" counted wagers, not prices."""
    report = _report(shape)
    tmm.save_team_measurement(report, output_dir=tmp_path)
    payload = json.loads(
        (tmp_path / tmm.MEASUREMENT_JSON_FILENAME).read_text(encoding="utf-8")
    )

    notes = [note for note in report.notes if note.startswith("Team names:")]
    assert len(notes) == 1, report.notes
    assert notes[0].startswith(
        "Team names: 1 of the 4 wager(s) scored (each at its best price) "
        "named a team the team-name map could not resolve (Vancouver Canucks)."
    ), notes[0]
    assert not any("prices scored" in note for note in report.notes)
    # The JSON key keeps its old name for its readers; the denominator beside
    # it says which unit it is in, and the quotes are recorded per market.
    assert payload["unresolved_team_rows"] == 1
    assert payload["scored_wagers"] == 4
    assert payload["markets"][0]["accounting"]["quotes"] == _quotes(shape)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_prices_measured_stays_rows_and_the_quotes_add_up_to_it(
    shape: str, defaults: SimpleNamespace
) -> None:
    """The row figure was right; now the per-market figures reconcile to it."""
    report = _report(shape)

    assert f"Prices measured: {_quotes(shape)} of {_quotes(shape)} stored rows" in (
        tmm.render_team_measurement(report)
    )
    assert report.priced_outcomes == _quotes(shape)
    assert (
        sum(item.accounting.get("quotes", 0) for item in report.markets)
        == report.priced_outcomes
    )
    assert report.scored_wagers == 4


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_refusal_counts_rows_as_rows_and_wagers_as_wagers(
    shape: str, defaults: SimpleNamespace
) -> None:
    """ "Not one of the N `moneyline` price row(s)" printed the wager count."""
    with pytest.raises(tmm.UnresolvedTeamsError) as caught:
        tmm.build_team_measurement(
            _samples(), _store(shape), team_names={}, phase="late"
        )

    assert (
        f"Not one of the {_quotes(shape)} `moneyline` price row(s) (4 "
        "wager(s), one per wager at its best price) names two teams"
    ) in str(caught.value)


# --------------------------------------------------------------------------
# Through the runner, the way a workflow calls it.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_runner_prints_unresolved_wagers_not_rows(
    shape: str,
    tmp_path: Path,
    defaults: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """It printed "Unresolved team names: N priced row(s)." with N in wagers."""
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    save_team_name_map(TEAM_MAP, processed_dir=processed)
    _store(shape).to_csv(processed / "historical_team_prices.csv", index=False)
    module = load_script("run_team_markets_measurement.py")
    # The walk-forward is not what is under test; the printed unit is.
    monkeypatch.setattr(
        module, "load_team_games", lambda _dir: pd.DataFrame({"game_id": [0]})
    )
    monkeypatch.setattr(
        module,
        "generate_team_samples",
        lambda *_a, **_k: (_samples(), SimpleNamespace(summary_line=lambda: "")),
    )

    code = module.main(
        [
            "--phase", "late",
            "--processed-dir", str(processed),
            "--output-dir", str(outputs),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "Unresolved team names: 1 of 4 wager(s) scored." in out.splitlines()
    assert "priced row" not in out
