"""The props backtest called an empty window "0.0 hours before face-off".

Found by the failure-shape audit (finding v4, confirmed by all three refuters:
reproduce, reachability and intent). `run_backtest` sets `report.phase` for
every named window. When the window keeps no row it only appends a note, so
`phase_hours` kept its dataclass default of 0.0. `render_backtest` checked
`report.phase` and nothing else, so it printed that default as a distance.
The refuters reproduced this on commit 68dcbb4 through the real runner and
the real bought store: 3,804,233 rows, of which 2,544,921 are `card`, 1,259,312
are `late` and none are `early`.

* `--phase early`, a choice argparse offers, exited 0. It wrote the contract
  `player_props_backtest.md` with "Priced **0.0 hours before face-off**
  (`early` window)" in its header. The same report said "Outside the measured
  window, excluded: 3,804,233" and "Priced outcomes seen: 0", and a standing
  note said "No price row is in the `early` window". The JSON carried
  `"phase_hours": 0.0`.
* `--phase late --from 2026-04-18 --to 2026-04-20` gave the same header. It
  read 12,191 rows, and all of them are `card`.
* `--phase card --label card` is the first backtest step of both workflows.
  Over a store holding only `late` rows it gave the same header, in both the
  contract report and `player_props_backtest_card.md`.

#147 fixed this "median of nothing" in the team measurement, and #162 fixed it
in the team rest experiment. This is the last of the three reports. CLAUDE.md
says "a named window that matches nothing measures nothing and says so". This
report measured nothing and then stated a distance.

What these tests hold, through the real runner's `main`, `run_backtest`,
`render_backtest` and `save_backtest`:

* A named window that keeps no row prints no distance. Its header says no
  price row is in that window and names the windows the rows it read are in,
  with counts (`held_windows`, the team reports' wording). Both the contract
  and the labelled copy say so, and the JSON records `phase_hours` as null
  rather than 0.0.
* A window that kept rows still prints its median, byte for byte as before,
  and that includes a real median of 0.0 hours. The fix tells "no median"
  apart from "a median of zero". It does not ban the string.
* A run that filters no window still says so, and it carries no invented
  distance either.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports import player_props_backtest as bt
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


#: Keyed the way production keys it: normalized lowercase names.
TEAM_MAP = {"toronto maple leafs": "TOR", "ottawa senators": "OTT"}

#: 7:10pm ET face-offs, so the league dates are 2025-10-18 and 2025-10-20.
GAME_A = ("evt1", "2025-10-18", "2025-10-18T23:10:00Z")
GAME_B = ("evt2", "2025-10-20", "2025-10-20T23:10:00Z")

#: The header line a named window that kept no row now prints.
MISSED = (
    "- **No price row is in the `{phase}` window**, so nothing was priced at "
    "any distance from face-off and nothing was measured against a real "
    "price. The price rows read, by window: {held}."
)

#: The header line a window that kept rows prints. It is unchanged, byte for
#: byte, and the committed reports carry it.
PRICED = (
    "- Priced **{hours} hours before face-off** (`{phase}` window). A return "
    "measured at one distance from the puck is not comparable to one "
    "measured at another: the lineup is known at four hours and guessed at "
    "nine."
)

NO_FILTER = (
    "- No snapshot window was filtered, so this number may mix prices taken "
    "at different distances from face-off."
)


def _quote(game: tuple[str, str, str], hours_before: float, player: str,
           odds: int, book: str) -> dict:
    event, day, commence = game
    snapshot = pd.Timestamp(commence) - pd.Timedelta(hours=hours_before)
    return {
        "date": day,
        "commence_time": commence,
        "snapshot": snapshot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider_event_id": event,
        "home_team": "Toronto Maple Leafs",
        "away_team": "Ottawa Senators",
        "market": "shots_on_goal",
        "player": player,
        "selection": "over",
        "line": 2.5,
        "american_odds": odds,
        "book": book,
    }


def _late_quotes() -> list[dict]:
    """Three quotes on game A at 4.0 hours out, the `late` window."""
    return [
        _quote(GAME_A, 4.0, "Auston Matthews", -110, "DraftKings"),
        _quote(GAME_A, 4.0, "Auston Matthews", 100, "FanDuel"),
        _quote(GAME_A, 4.0, "Brady Tkachuk", 105, "DraftKings"),
    ]


def _card_quotes() -> list[dict]:
    """Five quotes at 9.5 hours out, the `card` window. Game B has only these."""
    return [
        _quote(GAME_A, 9.5, "Auston Matthews", -120, "DraftKings"),
        _quote(GAME_A, 9.5, "Brady Tkachuk", 100, "DraftKings"),
        _quote(GAME_A, 9.5, "William Nylander", 110, "DraftKings"),
        _quote(GAME_B, 9.5, "Auston Matthews", 100, "DraftKings"),
        _quote(GAME_B, 9.5, "Brady Tkachuk", 105, "DraftKings"),
    ]


def _two_windows() -> pd.DataFrame:
    return pd.DataFrame(_late_quotes() + _card_quotes())


def _late_only() -> pd.DataFrame:
    return pd.DataFrame(_late_quotes())


def _unreadable_times() -> pd.DataFrame:
    """The late quotes with a snapshot nothing can parse, so their window is
    unknown. No row is in any window."""
    frame = _late_only()
    frame["snapshot"] = "not a time"
    return frame


def _samples() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": day, "market": "shots_on_goal", "player": player,
             "player_id": pid, "team": team, "line": 2.5, "mean": mean,
             "dispersion_r": None, "actual": actual}
            for day in (GAME_A[1], GAME_B[1])
            for player, pid, team, mean, actual in (
                ("Auston Matthews", 1, "TOR", 3.4, 4.0),
                ("Brady Tkachuk", 2, "OTT", 3.0, 1.0),
            )
        ]
    )


@pytest.fixture(autouse=True)
def _isolated_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test here may read the checkout's data/ tree."""
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")


def _run(tmp_path: Path, store: pd.DataFrame, *flags: str) -> tuple[int, Path]:
    """The real runner, as both workflows call it, on scratch directories."""
    processed = tmp_path / "processed"
    outputs = tmp_path / "outputs"
    processed.mkdir()
    outputs.mkdir()
    tn.save_team_name_map(TEAM_MAP, processed_dir=processed)
    store.to_csv(processed / "historical_prop_prices.csv", index=False)
    _samples().to_csv(outputs / "prop_calibration_samples.csv", index=False)
    module = load_script("run_player_props_backtest.py")
    code = module.main(
        [*flags, "--processed-dir", str(processed), "--output-dir", str(outputs)]
    )
    return code, outputs


def _header(markdown: str) -> str:
    """Everything above the first section: the lines a reader sees first."""
    return markdown.split("\n## ", 1)[0]


# --------------------------------------------------------------------------
# A named window that kept no row, through the runner.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("store", "flags", "phase", "held", "labelled"),
    [
        # `early` is an argparse choice; the real store holds none.
        (_two_windows, ("--phase", "early"), "early",
         "`card` (5 rows), `late` (3 rows)", ""),
        # Both workflows' first step, over a store holding only `late`.
        (_late_only, ("--phase", "card", "--label", "card"), "card",
         "`late` (3 rows)", "card"),
        # A date range whose rows are all `card`, like 2026-04-18..20 on the
        # real store. The counts are the rows read, after the date filter.
        (_two_windows,
         ("--phase", "late", "--from", "2025-10-20", "--to", "2025-10-20"),
         "late", "`card` (2 rows)", ""),
        # Rows whose window cannot be read are in no window.
        (_unreadable_times, ("--phase", "late"), "late", "none", ""),
    ],
    ids=[
        "early-over-two-windows",
        "card-over-late-only",
        "late-over-a-card-only-date-range",
        "late-over-unreadable-times",
    ],
)
def test_a_window_that_kept_no_row_states_no_distance(
    tmp_path: Path, store, flags: tuple[str, ...], phase: str, held: str,
    labelled: str,
) -> None:
    code, outputs = _run(tmp_path, store(), *flags)

    assert code == 0, (
        "a named window that matches nothing measures nothing and says so; "
        "it is not a refusal"
    )
    names = [("player_props_backtest.md", "player_props_backtest.json")]
    if labelled:
        names.append(
            (f"player_props_backtest_{labelled}.md",
             f"player_props_backtest_{labelled}.json")
        )
    for markdown_name, json_name in names:
        markdown = (outputs / markdown_name).read_text(encoding="utf-8")
        header = _header(markdown)
        assert "0.0 hours" not in markdown, (
            f"{markdown_name} printed the field's default as a distance: "
            "there was no price to take a median of"
        )
        assert "hours before face-off" not in header, (
            f"{markdown_name} states a distance for a window it priced nothing in"
        )
        assert MISSED.format(phase=phase, held=held) in header.splitlines(), (
            f"{markdown_name}'s header must say the `{phase}` window was empty "
            f"and name the windows the rows read are in:\n{header}"
        )
        assert NO_FILTER not in header, (
            "a window was named and filtered; it just kept nothing"
        )

        payload = json.loads((outputs / json_name).read_text(encoding="utf-8"))
        assert payload["phase"] == phase
        assert payload["phase_hours"] is None, (
            f"{json_name} carried {payload['phase_hours']!r}; a median of no "
            "rows is not a number"
        )
        assert payload["priced_outcomes"] == 0
        # The JSON boundary: what the claims and allowlist readers print.
        assert bt.window_phrase(payload) == f"`{phase}` window"


# --------------------------------------------------------------------------
# Controls: a window that kept rows, and a run that filters none.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flags", "phase", "hours", "labelled"),
    [
        (("--phase", "late"), "late", 4.0, ""),
        (("--phase", "card", "--label", "card"), "card", 9.5, "card"),
        (("--phase", "card", "--from", "2025-10-20", "--to", "2025-10-20"),
         "card", 9.5, ""),
    ],
    ids=["late", "card-labelled", "card-over-a-date-range"],
)
def test_a_window_that_kept_rows_still_states_its_distance(
    tmp_path: Path, flags: tuple[str, ...], phase: str, hours: float,
    labelled: str,
) -> None:
    code, outputs = _run(tmp_path, _two_windows(), *flags)

    assert code == 0
    names = ["player_props_backtest"] + (
        [f"player_props_backtest_{labelled}"] if labelled else []
    )
    for stem in names:
        header = _header((outputs / f"{stem}.md").read_text(encoding="utf-8"))
        assert PRICED.format(hours=f"{hours:.1f}", phase=phase) in header.splitlines()
        assert "No price row is in the" not in header
        payload = json.loads((outputs / f"{stem}.json").read_text(encoding="utf-8"))
        assert payload["phase_hours"] == pytest.approx(hours)
        assert bt.window_phrase(payload) == (
            f"`{phase}` window, {hours:.1f} hours before face-off"
        )


def test_a_run_that_filters_no_window_says_so_and_invents_no_distance(
    tmp_path: Path,
) -> None:
    """`--phase all` measures the mixture on purpose. It took no median, so
    its JSON must not carry one either."""
    code, outputs = _run(tmp_path, _two_windows(), "--phase", "all")

    assert code == 0
    header = _header((outputs / "player_props_backtest.md").read_text(encoding="utf-8"))
    assert NO_FILTER in header.splitlines()
    assert "No price row is in the" not in header, (
        "no window was named, so none was missed"
    )
    payload = json.loads(
        (outputs / "player_props_backtest.json").read_text(encoding="utf-8")
    )
    assert payload["phase"] == ""
    assert payload["phase_hours"] is None


# --------------------------------------------------------------------------
# In the report itself.
# --------------------------------------------------------------------------


def test_the_report_records_no_median_for_an_empty_window() -> None:
    report = bt.run_backtest(
        pd.DataFrame(_card_quotes()), _samples(), edge_threshold=0.0,
        phase="late", team_names=TEAM_MAP,
    )

    assert report.phase == "late", "the report still names the window asked for"
    assert report.phase_hours is None
    assert report.rows_by_window == {"card": 5}
    assert report.quotes_seen == 0
    assert MISSED.format(phase="late", held="`card` (5 rows)") in (
        _header(bt.render_backtest(report)).splitlines()
    )


def test_a_real_median_of_zero_hours_is_still_printed(tmp_path: Path) -> None:
    """A quote captured at the puck drop is in the `late` window, and its
    distance really is 0.0 hours. The defect was a missing median printed as
    zero, not the figure zero, so this one must still print."""
    at_face_off = [
        _quote(GAME_A, 0.0, "Auston Matthews", -110, "DraftKings"),
        _quote(GAME_A, 0.0, "Brady Tkachuk", 105, "DraftKings"),
    ]
    report = bt.run_backtest(
        pd.DataFrame(at_face_off), _samples(), edge_threshold=0.0,
        phase="late", team_names=TEAM_MAP,
    )

    assert report.phase_hours == 0.0
    assert PRICED.format(hours="0.0", phase="late") in (
        _header(bt.render_backtest(report)).splitlines()
    )
    bt.save_backtest(report, output_dir=tmp_path)
    payload = json.loads(
        (tmp_path / "player_props_backtest.json").read_text(encoding="utf-8")
    )
    assert payload["phase_hours"] == 0.0
