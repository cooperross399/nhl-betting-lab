"""A team window the store lacks was reported as prices nobody had bought.

Found by the failure-shape audit (silent empty reports), and reproduced on
copies of the real team store: 308,944 rows, 247,160 in the `late` window,
61,784 in `early`, none in `card`. `run_team_markets_measurement.py --phase
card` — a window its `--help` lists, and one the mixed-window refusal told the
operator to name ("--phase late (or card/early)") — exited 0 and wrote:

* "Every price below was captured in the `card` window, median **0.0 hours**
  before face-off". There was no price to take a median of; 0.0 was the
  field's default.
* "**No price-based measurement.** 0 historical team price(s) are on disk".
  `priced_outcomes` counts the rows left AFTER the window filter, not the rows
  stored, so 308,944 stored rows were printed as 0 on disk.

Only a standing note told the truth ("Prices measured: 0 of 308,944 stored
rows"), and the JSON's zero bets reached `what_we_can_claim.md` as "no
historical prices have been bought for it yet" for moneyline, puck line and
totals. Separately, the per-market reconciliation ("Where every price
landed") sat inside `if measured:`, so when every price went unmatched — the
exact case it was added to expose — it was not rendered at all.

CLAUDE.md's rule for this path is "a named window that matches nothing
measures nothing and says so". It measured nothing and said something else.
What these tests hold, through the real report, its JSON, and both runners:

* an empty named window says so, names the windows the store does hold, and
  prints no median;
* the "on disk" figure is the stored count, beside the in-window count;
* the reconciliation renders whenever any price was scored;
* the JSON records the stored rows by market, so the claims document can say
  "stored, none in this window" instead of "never bought";
* the mixed-window refusal names only windows the store holds.
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
from nhl_betting_lab.reports import what_we_can_claim as claims
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


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
TEAM_MAP = {"toronto maple leafs": "TOR", "boston bruins": "BOS"}

#: Evening face-offs in UTC, so the league date is the day before.
GAMES = [
    ("2025-01-09", "2025-01-10T00:00:00Z"),
    ("2025-01-11", "2025-01-12T00:00:00Z"),
    ("2025-01-14", "2025-01-15T00:00:00Z"),
]


def _samples(days: list[str] | None = None) -> pd.DataFrame:
    """The model says 60% home on every game; the home side wins them all."""
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
            for index, day in enumerate(days or [day for day, _ in GAMES])
        ]
    )


def _store(*hours_before: float) -> pd.DataFrame:
    """One moneyline quote per game at each distance from face-off.

    +150 is 40% implied against the model's 60%, so every matched quote is a
    bet. 2.0 hours is the `late` window and 20.0 the `early` one; the real
    store holds exactly those two and no `card` rows.
    """
    rows = []
    for day, commence in GAMES:
        for hours in hours_before:
            snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=hours)
            rows.append(
                {
                    "date": day,
                    "commence_time": commence,
                    "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "home_team": "Toronto Maple Leafs",
                    "away_team": "Boston Bruins",
                    "market": "moneyline",
                    "selection": "home",
                    "line": None,
                    "american_odds": 150,
                    "book": "DraftKings",
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """No test here may read the real `data/processed` or boxscore cache,
    nor the tracked verdicts, which the runner read through its scratch
    `--output-dir` (#151) until every default was pointed away here."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    processed = tmp_path / "default_processed"
    raw = tmp_path / "default_raw"
    processed.mkdir()
    raw.mkdir()
    monkeypatch.setattr(team_names_module, "PROCESSED_DIR", processed)
    monkeypatch.setattr(team_names_module, "RAW_DIR", raw)
    return SimpleNamespace(processed=processed, raw=raw)


# --------------------------------------------------------------------------
# The report.
# --------------------------------------------------------------------------

def test_a_named_window_the_store_lacks_says_so_and_prints_no_median(
    defaults: SimpleNamespace,
) -> None:
    """The real run printed "median **0.0 hours**" and "0 ... on disk"."""
    report = tmm.build_team_measurement(
        _samples(), _store(2.0, 20.0), team_names=TEAM_MAP, phase="card"
    )
    rendered = tmm.render_team_measurement(report)

    assert report.priced_outcomes == 0
    assert "0.0 hours" not in rendered
    assert "0 historical team price(s) are on disk" not in rendered
    assert "No price row in the `card` window was captured before face-off" in rendered
    # Named with the windows it DOES hold, as the props backtest names them.
    assert "`early` (3 rows), `late` (3 rows)" in rendered
    # The stored count, never the in-window one, is what is "on disk".
    assert "6 historical team price row(s) are on disk" in rendered


def test_the_on_disk_count_is_every_stored_row_not_the_window(
    defaults: SimpleNamespace,
) -> None:
    """Three windows' worth stored, one window measured, nothing matched.

    The samples cover none of the priced games, so no market is measured and
    the "No price-based measurement" paragraph is the one that renders. It
    used to print the in-window count as the number on disk.
    """
    report = tmm.build_team_measurement(
        _samples(days=["2024-12-01"]),
        _store(2.0, 20.0, -1.0),
        team_names=TEAM_MAP,
        phase="late",
    )
    rendered = tmm.render_team_measurement(report)

    assert report.priced_outcomes == 3
    assert report.stored_rows == 9
    assert "9 historical team price row(s) are on disk" in rendered
    assert "3 of them" in rendered
    assert "3 historical team price(s) are on disk" not in rendered


def test_where_every_price_landed_renders_when_every_price_is_unmatched(
    defaults: SimpleNamespace,
) -> None:
    """The reconciliation was hidden in exactly the case it exists for.

    On the real store, `late`-window prices for games after the samples end
    went 100% unmatched (moneyline 14/14, puck line 16/16, totals 32/32) and
    the report showed no "Where every price landed" section at all.
    """
    report = tmm.build_team_measurement(
        _samples(days=["2024-12-01"]),
        _store(2.0),
        team_names=TEAM_MAP,
        phase="late",
    )
    rendered = tmm.render_team_measurement(report)

    assert not any(item.has_price_evidence for item in report.markets)
    assert "Where every price landed" in rendered
    assert "3 wager(s) seen" in rendered
    assert "3 unmatched (0% matched)" in rendered


def test_a_measured_window_still_prints_its_median(
    defaults: SimpleNamespace,
) -> None:
    """The ordinary path is unchanged: prices in the window, a real median."""
    report = tmm.build_team_measurement(
        _samples(), _store(2.0, 20.0), team_names=TEAM_MAP, phase="late"
    )
    rendered = tmm.render_team_measurement(report)

    assert report.markets[0].priced.bets == 3
    assert "median **2.0 hours** before face-off" in rendered
    assert "No price row in the" not in rendered


def test_the_json_records_what_was_stored_by_market(
    tmp_path: Path, defaults: SimpleNamespace
) -> None:
    """What the claims document needs to say "stored" rather than "unbought"."""
    report = tmm.build_team_measurement(
        _samples(), _store(2.0, 20.0), team_names=TEAM_MAP, phase="card"
    )
    tmm.save_team_measurement(report, output_dir=tmp_path)
    payload = json.loads(
        (tmp_path / tmm.MEASUREMENT_JSON_FILENAME).read_text(encoding="utf-8")
    )

    assert payload["stored_rows"] == 6
    assert payload["stored_by_market"] == {"moneyline": 6}
    assert payload["priced_outcomes"] == 0


def test_the_mixed_window_refusal_names_only_windows_the_store_holds(
    defaults: SimpleNamespace,
) -> None:
    """It said "--phase late (or card/early)" to a store holding no `card`.

    Following that advice is how the misleading report above was reached.
    """
    with pytest.raises(tmm.MixedWindowError) as caught:
        tmm.build_team_measurement(
            _samples(), _store(2.0, 20.0), team_names=TEAM_MAP
        )
    message = str(caught.value)

    assert "--phase early" in message
    assert "--phase late" in message
    assert "card" not in message


# --------------------------------------------------------------------------
# Through both runners, the way an operator reaches it.
# --------------------------------------------------------------------------

def test_the_runner_and_the_claims_say_stored_not_unbought(
    tmp_path: Path,
    defaults: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--phase card` on a store with no `card` rows, then the claims document.

    Exit 0 is the documented behaviour — a named window that matches nothing
    measures nothing — so what is asserted is that both documents say so.
    """
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    save_team_name_map(TEAM_MAP, processed_dir=processed)
    _store(2.0, 20.0).to_csv(processed / "historical_team_prices.csv", index=False)

    module = load_script("run_team_markets_measurement.py")
    # The walk-forward is not under test; what the report says about the
    # prices it was handed is.
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
            "--phase", "card",
            "--processed-dir", str(processed),
            "--output-dir", str(outputs),
        ]
    )
    capsys.readouterr()
    markdown = (outputs / tmm.MEASUREMENT_MARKDOWN_FILENAME).read_text(
        encoding="utf-8"
    )

    assert code == 0
    assert "0.0 hours" not in markdown
    assert "0 historical team price(s) are on disk" not in markdown
    assert "No price row in the `card` window was captured before face-off" in markdown

    claims_module = load_script("run_what_we_can_claim.py")
    assert claims_module.main(["--output-dir", str(outputs)]) == 0
    capsys.readouterr()
    rendered = (outputs / claims.CLAIMS_MARKDOWN_FILENAME).read_text(
        encoding="utf-8"
    )
    moneyline = next(
        line for line in rendered.splitlines() if line.startswith("- `moneyline`")
    )

    assert "no historical prices have been bought" not in moneyline
    assert "6 historical price row(s)" in moneyline
    assert "`card` window" in moneyline
