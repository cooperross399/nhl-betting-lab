"""Tests read the checkout's own data/ tree, so they ran different code by checkout.

Every default data directory is an absolute path under the checkout
(`config.PROJECT_ROOT / "data"`), and several modules bind their own copy at
import. A test that calls a script or a report without naming a directory, or
names only some of them, falls back to whatever the checkout it runs in holds.
CI's checkout holds nothing gitignored; the operator's holds the whole season.
Found by the failure-shape audit (findings 88 and 89, each confirmed by two of
three refuters), and by the #151 reviewer for the recorded verdicts:

* Six tests in `test_team_markets_measurement.py` built a measurement with no
  `team_names` and no `processed_dir`, so `load_team_name_map()` read
  `data/processed/team_names.csv`: 6 spellings on a clean clone (none from the
  cache; "TOR" resolved only through the samples-codes fallback), 101 in the
  operator's checkout (64 from the cache; "TOR" through the map). With that
  fallback deleted, the whole suite failed 7 tests on a clean clone and 1 in
  the operator's checkout: there, these six could not see it.
* `test_the_dataset_builder_runs_on_an_empty_cache` used `monkeypatch.chdir`,
  which moves no absolute path. In the operator's checkout it opened 5,280
  boxscores and 3 registries and printed "3936 of 5280 cached games used;
  157419 player-game rows"; the empty case it is named for ran only on CI
  ("0 of 0"). The card test built its team map from those 5,280 boxscores
  (3 blockers, not CI's 4), and the backtest test rebuilt the map from them.
* Measured again for this fix on the whole suite at d418e57, with an audit
  hook recording every open and directory listing under data/ per test, once
  on a clean clone (2197 passed) and once on the same commit with a copy of
  the operator's gitignored data laid in (1 failed, 2196 passed): 15 tests
  read gitignored data, the card and builder tests 5,280 to 5,664 files each,
  and one of them FAILED in the operator's checkout while passing on CI.
  `test_the_global_series_morning_freezes_only_the_evening_game` stages a
  Boston-Rangers game on 2026-12-20; the operator's 2026-27 club-schedule
  cache knows that night's real slate and not that game, so the card
  excluded it as "not regular season" and froze no snapshot at all.
* Since #151 a scratch `--output-dir` that records no verdict falls back to
  the tracked verdicts in `data/outputs/`. 35 test items reached them that
  way — every card test given a bare scratch output directory, the
  calibration and team-measurement runners, and
  `ships("by_toi", output_dir=tmp_path) is False` in `test_toi_corrections.py`,
  which held only while the recorded by_toi verdict was off. Seven more read
  the tracked verdicts on purpose (the secrets scan's five, and the two tests
  that pin the committed verdicts), as does one module at import, and those
  are left alone.

What this module holds:

* `point_default_data_dirs_at` is the one list of default data directories a
  test can fall back to, and every test in `CHECKOUT_SENSITIVE_TESTS` points
  them away from the checkout, directly or through its module's fixture;
* those tests pass, and read nothing, in a stand-in checkout whose data/ is
  populated the way the operator's is (a boxscore cache, a complete club
  schedule for 2026-27 that does not list the tests' games, a saved team-name
  map, an evidence archive, and recorded verdicts that ship all three
  policies — the opposite of today's by_toi verdict);
* the stand-in is not vacuous: a probe that does not isolate reads every
  stand-in default and sees what it holds, and the same probe after
  `point_default_data_dirs_at` reads none of it.

The limit, stated rather than hidden: `CHECKOUT_SENSITIVE_TESTS` names the
tests the audit found on 2026-09-25. A test written later that falls back to
a default directory is not in it, and nothing here will notice; the probe
proves only that the helper covers every default in the list, not that every
test uses it. The audit hook this module installs in its subprocess is the
tool that finds the next one: run the whole suite under it in a checkout that
holds data.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import boxscore_payload
from nhl_betting_lab import config, forward_evidence, verdicts
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.data import build_datasets, nhl_api
from nhl_betting_lab.providers import team_names


def point_default_data_dirs_at(
    monkeypatch: pytest.MonkeyPatch, root: Path
) -> SimpleNamespace:
    """Point every default data directory a test can fall back to under `root`.

    Nothing is created: a missing directory reads as an empty one to every
    reader here, and a write lands under `root` rather than in the checkout.
    A caller that needs one of these to hold something overrides that one
    AFTER this call.

    * `config.RAW_DIR` — `season.py` imports it inside each function, so the
      club-schedule readers (the preseason screen, the eligibility slate,
      schedule completeness) see the patched value at call time;
    * `nhl_api.RAW_DIR` — boxscores, the player registry and the rosters,
      read by `build_datasets` and by the card's `current_rosters`;
    * `team_names.RAW_DIR` and `team_names.PROCESSED_DIR` — the saved
      team-name map and the boxscores it is rebuilt from;
    * `build_datasets.PROCESSED_DIR` — where a dataset build writes;
    * `verdicts.OUTPUTS_DIR` — the recorded verdicts a scratch `--output-dir`
      that records none falls back to (#151); empty here, every policy is off,
      and a test that means a policy to ship records it itself;
    * `forward_evidence.DATA_DIR` — the real evidence archive a card run on
      the default output directory freezes into.
    """
    root = Path(root)
    dirs = SimpleNamespace(
        raw=root / "raw",
        processed=root / "processed",
        recorded=root / "recorded",
        data=root / "data",
    )
    monkeypatch.setattr(config, "RAW_DIR", dirs.raw)
    monkeypatch.setattr(nhl_api, "RAW_DIR", dirs.raw)
    monkeypatch.setattr(team_names, "RAW_DIR", dirs.raw)
    monkeypatch.setattr(team_names, "PROCESSED_DIR", dirs.processed)
    monkeypatch.setattr(build_datasets, "PROCESSED_DIR", dirs.processed)
    monkeypatch.setattr(verdicts, "OUTPUTS_DIR", dirs.recorded)
    monkeypatch.setattr(forward_evidence, "DATA_DIR", dirs.data)
    return dirs


#: Every test the whole-suite audit found reading a default data directory,
#: by function: the gitignored data (the nine tests findings 88 and 89 name,
#: and six more the audit found) and the tracked verdicts through the #151
#: fallback.
CHECKOUT_SENSITIVE_TESTS: tuple[str, ...] = (
    # Gitignored data: the boxscore cache, club schedules, team-name map, archive.
    "tests/test_periphery_markets.py::test_a_scratch_run_cannot_freeze_into_the_real_evidence_archive",
    "tests/test_scripts.py::test_the_backtest_script_reports_that_nothing_is_measured",
    "tests/test_scripts.py::test_the_card_script_blocks_and_exits_zero_with_no_data",
    "tests/test_scripts.py::test_the_card_script_says_no_team_map_could_be_built",
    "tests/test_scripts.py::test_the_dataset_builder_runs_on_an_empty_cache",
    "tests/test_snapshots_freeze_only_playable_games.py::test_a_card_that_priced_nothing_freezes_nothing",
    "tests/test_snapshots_freeze_only_playable_games.py::test_the_global_series_morning_freezes_only_the_evening_game",
    "tests/test_team_markets_measurement.py::test_a_matched_price_above_the_threshold_becomes_a_bet",
    "tests/test_team_markets_measurement.py::test_a_price_below_the_threshold_produces_no_bet",
    "tests/test_team_markets_measurement.py::test_an_unmatched_price_is_not_scored_as_a_loss",
    "tests/test_team_markets_measurement.py::test_a_push_returns_the_stake_rather_than_losing_it",
    "tests/test_team_markets_measurement.py::test_every_priced_row_lands_in_a_bucket",
    "tests/test_team_markets_measurement.py::test_the_report_prints_the_match_rate_per_market",
    "tests/test_the_card_blocks_on_an_alias_only_map.py::test_the_card_blocks_and_saves_nothing_when_no_boxscores_are_cached",
    "tests/test_the_card_blocks_on_an_alias_only_map.py::test_the_card_saves_a_map_the_cache_supplied",
    # The tracked verdicts, reached through a scratch --output-dir (#151).
    "tests/test_a_missed_team_window_says_so.py::test_the_runner_and_the_claims_say_stored_not_unbought",
    "tests/test_schedule_completeness_counts_club_files.py::test_the_card_keeps_a_real_game_when_the_seasons_cache_is_partial",
    "tests/test_schedule_completeness_counts_club_files.py::test_the_card_warns_when_its_season_has_no_files_at_all",
    "tests/test_scripts.py::test_the_calibration_script_refuses_to_write_a_report_with_no_logs",
    "tests/test_scripts.py::test_the_team_measurement_script_refuses_with_no_games",
    "tests/test_team_names_come_from_the_processed_dir.py::test_the_runner_reads_the_map_from_its_processed_dir",
    "tests/test_team_names_come_from_the_processed_dir.py::test_the_runner_refuses_when_its_processed_dir_has_no_map",
    "tests/test_the_card_refuses_stale_prices.py::test_prices_staged_on_monday_are_not_carded_on_wednesday",
    "tests/test_the_card_refuses_stale_prices.py::test_the_same_prices_an_hour_old_are_carded_and_frozen",
    "tests/test_the_card_refuses_stale_prices.py::test_the_policys_own_limit_decides_not_a_constant",
    "tests/test_the_card_refuses_stale_prices.py::test_the_stricter_of_the_two_limits_wins",
    "tests/test_the_card_refuses_stale_prices.py::test_the_oldest_staged_row_decides",
    "tests/test_the_card_refuses_stale_prices.py::test_a_row_with_no_timestamp_is_stale",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_a_game_priced_in_no_market_makes_the_market_incomplete",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_the_whole_slate_priced_is_eligible_and_picks",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_a_game_already_under_way_is_not_part_of_the_slate",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_a_called_off_game_is_not_part_of_the_slate",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_a_screened_exhibition_game_never_enters_the_slate",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_a_partial_cache_still_counts_every_game_it_knows",
    "tests/test_the_card_slate_counts_unpriced_games.py::test_with_no_schedule_the_run_says_the_gate_saw_only_the_provider",
    "tests/test_the_ledger_freezes_what_the_gate_excludes.py::test_the_snapshot_holds_every_market_the_card_excluded",
    "tests/test_the_ledger_freezes_what_the_gate_excludes.py::test_a_dark_card_still_freezes_every_priced_row",
    "tests/test_the_screen_abstains_past_the_schedule_it_knows.py::test_a_slate_past_the_schedule_is_priced_and_frozen_not_excluded",
    "tests/test_the_screen_abstains_past_the_schedule_it_knows.py::test_inside_the_schedule_an_unknown_game_is_still_excluded_and_counted",
    "tests/test_toi_corrections.py::test_the_card_applies_corrections_only_on_the_recorded_verdict",
    "tests/test_verdicts.py::test_describe_names_every_policy",
)

#: Every club, so the stand-in's club-schedule cache is complete for 2026-27.
CLUBS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
    "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
    "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK",
    "WPG", "WSH",
)

#: The stand-in paths no listed test may read, relative to the checkout.
STAND_IN_PATHS = (
    "data/raw",
    "data/processed/team_names.csv",
    "data/processed/player_game_logs.csv",
    "data/processed/team_games.csv",
    "data/archive",
    "data/outputs/correction_experiment.json",
    "data/outputs/rest_experiment.json",
    "data/outputs/props_rest_experiment.json",
)

#: Loaded into the subprocess with `-p`: records, per test, every open and
#: directory listing under a stand-in path, and every test's outcome.
WATCHER = '''
import json, os, sys
import pytest

ROOT = os.path.realpath(os.environ["STAND_IN_ROOT"])
WATCHED = [os.path.join(ROOT, p) for p in json.loads(os.environ["STAND_IN_PATHS"])]
STATE = {"node": None}
READS = {}
OUTCOMES = {}


def _hook(event, args):
    node = STATE["node"]
    if node is None or event not in ("open", "os.scandir", "os.listdir", "glob.glob"):
        return
    path = args[0] if args else None
    if path is None or isinstance(path, int):
        return
    try:
        full = os.path.abspath(os.fsdecode(path))
    except Exception:
        return
    for watched in WATCHED:
        if full == watched or full.startswith(watched + os.sep):
            READS.setdefault(node, set()).add(os.path.relpath(watched, ROOT))


sys.addaudithook(_hook)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    STATE["node"] = item.nodeid
    yield
    STATE["node"] = None


def pytest_runtest_logreport(report):
    if report.outcome != "passed" or report.when == "call":
        OUTCOMES.setdefault(report.nodeid, []).append(f"{report.when}:{report.outcome}")


def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["STAND_IN_REPORT"], "w", encoding="utf-8") as handle:
        json.dump(
            {"reads": {k: sorted(v) for k, v in READS.items()}, "outcomes": OUTCOMES},
            handle,
        )
'''

#: Two probes run in the stand-in beside the listed tests: the first reads
#: every default without isolation and must see the stand-in's contents; the
#: second isolates first and must see none of them.
PROBE = '''
from nhl_betting_lab import forward_evidence, verdicts
from nhl_betting_lab.data import build_datasets, nhl_api
from nhl_betting_lab.providers import team_names
from nhl_betting_lab.season import known_regular_season_games

from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at


def _look(tmp_path):
    return {
        "boxscores": nhl_api.cached_boxscore_ids(),
        "player_logs": len(build_datasets.load_player_logs()),
        "team_games": len(build_datasets.load_team_games()),
        "rebuilt_map_knows_toronto": team_names.resolve_team(
            "Toronto Maple Leafs", team_names.build_team_name_map()
        ),
        "saved_map": team_names.saved_team_name_map(),
        "schedule": sorted(known_regular_season_games())[:1],
        "verdicts": verdicts.describe(output_dir=tmp_path),
        "archive": sorted(p.name for p in forward_evidence.snapshots_dir().glob("*")),
    }


def test_probe_without_isolation_sees_the_checkout(tmp_path):
    seen = _look(tmp_path)
    assert seen["boxscores"] == [1], seen
    assert seen["player_logs"] == 1 and seen["team_games"] == 1, seen
    assert seen["rebuilt_map_knows_toronto"] == "TOR", seen
    assert seen["saved_map"].get("toronto maple leafs") == "TOR", seen
    assert seen["schedule"], seen
    assert seen["verdicts"] == (
        "by_toi=in force, props_b2b=in force, team_b2b=in force"
    ), seen
    assert seen["archive"] == ["2026-10-01.csv"], seen


def test_probe_after_isolation_sees_nothing(tmp_path, monkeypatch):
    point_default_data_dirs_at(monkeypatch, tmp_path / "defaults")
    seen = _look(tmp_path)
    assert seen == {
        "boxscores": [],
        "player_logs": 0,
        "team_games": 0,
        "rebuilt_map_knows_toronto": None,
        "saved_map": {},
        "schedule": [],
        "verdicts": "by_toi=off, props_b2b=off, team_b2b=off",
        "archive": [],
    }, seen
'''


def _stand_in_checkout(root: Path) -> Path:
    """This checkout's code and tracked data, with data/ populated the way the
    operator's is. Written only under `root`; the real tree is never touched."""
    for name in ("src", "scripts"):
        shutil.copytree(
            PROJECT_ROOT / name, root / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
        )
    (root / "tests").mkdir(parents=True)
    for path in (PROJECT_ROOT / "tests").glob("*.py"):
        shutil.copy2(path, root / "tests" / path.name)
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", root / "pyproject.toml")
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "data"],
        cwd=PROJECT_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8").split("\0")
    for relative in filter(None, tracked):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative, target)

    data = root / "data"
    # A boxscore cache: one final Toronto-Boston game, spelled as the API does.
    box = boxscore_payload(game_id=1, game_state="OFF")
    box["homeTeam"].update(abbrev="TOR", placeName={"default": "Toronto"},
                           commonName={"default": "Maple Leafs"})
    box["awayTeam"].update(abbrev="BOS", placeName={"default": "Boston"},
                           commonName={"default": "Bruins"})
    (data / "raw" / "nhl" / "boxscore").mkdir(parents=True)
    (data / "raw" / "nhl" / "boxscore" / "1.json").write_text(
        json.dumps(box), encoding="utf-8"
    )
    # A complete 2026-27 club-schedule cache whose one night, 2027-04-01, is
    # after every date the listed tests use: the screen judges their nights
    # and knows none of their games, as the operator's full season does.
    schedule = data / "raw" / "nhl" / "club_schedule"
    schedule.mkdir(parents=True)
    for index, club in enumerate(CLUBS):
        other = CLUBS[(index + 1) % len(CLUBS)]
        (schedule / f"{club}_20262027.json").write_text(
            json.dumps({"games": [{
                "gameType": 2, "gameDate": "2027-04-01",
                "homeTeam": {"abbrev": club}, "awayTeam": {"abbrev": other},
            }]}),
            encoding="utf-8",
        )
    # Built tables and a saved team-name map, as the builder and card write them.
    (data / "processed").mkdir(parents=True, exist_ok=True)
    for table in ("player_game_logs.csv", "team_games.csv"):
        (data / "processed" / table).write_text(
            "game_id,date\n1,2026-10-01\n", encoding="utf-8"
        )
    (data / "processed" / "team_names.csv").write_text(
        "provider_name,abbrev\nboston bruins,BOS\nbruins,BOS\nmaple leafs,TOR\n"
        "toronto maple leafs,TOR\nbos,BOS\ntor,TOR\n",
        encoding="utf-8",
    )
    # An evidence archive holding one frozen day.
    archive = data / "archive" / "priced_snapshots"
    archive.mkdir(parents=True)
    (archive / "2026-10-01.csv").write_text("date\n2026-10-01\n", encoding="utf-8")
    # Recorded verdicts that ship every policy: not today's, where by_toi is off.
    for policy, filename in verdicts.VERDICT_FILES.items():
        (data / "outputs" / filename).write_text(
            json.dumps({"ships": [policy]}), encoding="utf-8"
        )
    return root


PROBES = (
    "tests/test_stand_in_probe.py::test_probe_without_isolation_sees_the_checkout",
    "tests/test_stand_in_probe.py::test_probe_after_isolation_sees_nothing",
)


@pytest.fixture(scope="module")
def stand_in_run(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Every listed test and both probes, run once in the stand-in checkout.

    Only the listed tests run, so the suite's own conftest, which refuses any
    narrowed run by design, is not loaded (`--noconftest`); the tests import
    what they use from it directly.
    """
    root = tmp_path_factory.mktemp("stand_in")
    checkout = _stand_in_checkout(root / "checkout")
    (checkout / "tests" / "test_stand_in_probe.py").write_text(
        textwrap.dedent(PROBE), encoding="utf-8"
    )
    plugins = root / "plugins"
    plugins.mkdir()
    (plugins / "stand_in_watcher.py").write_text(WATCHER, encoding="utf-8")
    report_path = root / "report.json"
    env = {
        key: value for key, value in os.environ.items()
        if key not in ("PYTEST_ADDOPTS", "PYTHONPATH")
    }
    env.update(
        PYTHONSAFEPATH="1",
        PYTHONPATH=os.pathsep.join([str(checkout / "src"), str(plugins)]),
        STAND_IN_ROOT=str(checkout),
        STAND_IN_PATHS=json.dumps(STAND_IN_PATHS),
        STAND_IN_REPORT=str(report_path),
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--noconftest", "-p", "stand_in_watcher", "-rf",
         *CHECKOUT_SENSITIVE_TESTS, *PROBES],
        cwd=checkout, env=env, capture_output=True, text=True, timeout=600,
    )
    tail = (completed.stdout + completed.stderr)[-4000:]
    assert report_path.is_file(), tail
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return SimpleNamespace(
        returncode=completed.returncode, tail=tail,
        reads=report["reads"], outcomes=report["outcomes"],
    )


def _items(run: SimpleNamespace, node: str) -> dict[str, list[str]]:
    """Every collected item of `node`, one per parameter set."""
    return {
        item: states for item, states in run.outcomes.items()
        if item == node or item.startswith(node + "[")
    }


def test_a_test_that_does_not_isolate_reads_every_stand_in_default(
    stand_in_run: SimpleNamespace,
) -> None:
    """The stand-in is not vacuous: each default holds something, and a
    reader that is not pointed away finds it."""
    assert _items(stand_in_run, PROBES[0]) == {PROBES[0]: ["call:passed"]}, (
        stand_in_run.tail
    )
    assert sorted(stand_in_run.reads.get(PROBES[0], [])) == sorted(STAND_IN_PATHS)


def test_the_helper_leaves_every_stand_in_default_unread(
    stand_in_run: SimpleNamespace,
) -> None:
    assert _items(stand_in_run, PROBES[1]) == {PROBES[1]: ["call:passed"]}, (
        stand_in_run.tail
    )
    assert stand_in_run.reads.get(PROBES[1], []) == []


def test_the_stand_in_run_collected_every_listed_test_and_passed(
    stand_in_run: SimpleNamespace,
) -> None:
    assert stand_in_run.returncode == 0, stand_in_run.tail


@pytest.mark.parametrize("node", CHECKOUT_SENSITIVE_TESTS)
def test_it_passes_and_reads_nothing_in_a_populated_checkout(
    stand_in_run: SimpleNamespace, node: str
) -> None:
    items = _items(stand_in_run, node)

    assert items, f"{node} did not run in the stand-in checkout"
    assert all(states == ["call:passed"] for states in items.values()), (
        items, stand_in_run.tail
    )
    read = {item: stand_in_run.reads[item] for item in items if item in stand_in_run.reads}
    assert not read, f"read the checkout's own data: {read}"
