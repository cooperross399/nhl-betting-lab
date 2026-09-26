"""One failed state listing froze a schedule-only public board for the day, for good.

Publish Site's "Restore the lab's latest state" ran
`scripts/restore_state.py --artifact gameday-state --workflow
gameday-refresh.yml --no-merge --also gameday-reports=data/outputs` with
neither `--require-newest` nor `--attempts`, inside a `continue-on-error`
step ending `|| echo "...building schedule-only."`. restore_state.py reads a
`gh run list` that fails as no runs unless it is told to be strict, so one
HTTP 502 printed "Could not list gameday-refresh.yml runs", then "No
completed run of gameday-refresh.yml on main carries gameday-state; this run
starts without it" — false — and exited 0, so the `|| echo` never fired
either. The build then had no game history and published the schedule
alone, and `build_board` froze that board as the day's first published
opinion (`if not frozen.exists()`), which `scripts/site_history_floor.py`
refuses to let any later build rewrite. #175 made the site-history restore
in the same job strict (`--require-newest --attempts 3`) against exactly one
502, and left this listing as it was.

Found by the failure-shape audit (publish-site.yml:96) and confirmed by two
of three refuters (reproduce, reachability; the intent refuter read the
permanence as the documented first-opinion rule, which HELD #184 puts to the
owner). Their replay of Publish Site's own steps on 1b8d58b, on the real
10-game 2026-10-08 slate with the lab's real team_games.csv in the
artifact, and a control identical but for the 502:

* the first publish of 2026-10-08 froze 0 of 10 games with a projection,
  under "The model's game history was not available to this run" (control:
  10 of 10);
* a later publish that day restored the state and put 10 of 10 projected
  games in board.json, and the frozen board stayed byte-identical;
* the next morning settle() graded 0 of the 10 final games and set no
  notice, so the Results page fell back to "No games were settled for this
  date." with Straight up 0–0 (control: 10 settled, 8–2), while the Archive
  listed the day as 10 games.

The reachability refuter's replay through this suite's own chain, on a
2-game slate, read the same: 0 of 2 frozen with a projection against 2 of 2,
and 0 settled against 2.

These tests run Publish Site's steps in order through the chain in
test_a_failed_history_restore_never_truncates_the_site.py — every `run:`
block from the workflow under `bash --noprofile --norc -eo pipefail`, the
real restore_state.py behind an offline `gh` with injected HTTP 502s, the
real build_site_json.py and site_history.py `main()`s with only the NHL
schedule stubbed, `continue-on-error` honoured from the YAML — with Gameday
Refresh runs added to the registry, carrying a `gameday-state` artifact
whose game history the model fits on. Results are rendered through the
page's own adapter (web/lib/sports.js) under node.

Not changed here, and left to the owner's HELD #184 decision: whether a
board built without the model may be frozen at all (a listing that answers
with no carrier still builds and freezes the schedule), and the newest
carrier's download failing over to the one before it (the stale-state path).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest

from nhl_betting_lab.config import PROJECT_ROOT

from test_a_failed_history_restore_never_truncates_the_site import (
    PublishSite,
    assert_the_history_only_grows,
)
from test_site_never_calls_an_unpriced_game_a_pass import render_results


STATE_STEP = "Restore the lab's latest state"
#: The fake gh's key for an injected failure of Gameday Refresh's run listing.
STATE_LISTING = "list:gameday-refresh.yml"

D1, D2, D3 = (date(2026, 10, day) for day in (8, 9, 10))

#: Final scores the NHL schedule reports for the chain's two nightly games
#: (MTL @ TOR, BOS @ NYI), as (home, away).
FINALS = ((4, 2), (1, 3))

#: More games than the site will fit on: #194 (config.THIN_HISTORY_GAMES,
#: 1,000) projects nothing from a thinner table, and a fixture below it would
#: test that floor instead of this restore.
HISTORY_GAMES = 1_040

#: What the page prints when results.json carries no notice.
PAGE_FALLBACK = "No games were settled for this date."


def _team_games(path: Path) -> None:
    """A game history the team model fits on: the chain's four clubs, keyed
    by abbreviation as the board resolves them, ending long before the
    boards, so no side is on a back-to-back."""
    columns = ["game_id", "season", "game_type", "date", "start_time_utc",
               "home_team", "away_team", "home_goals", "away_goals",
               "home_shots", "away_shots", "regulation"]
    pairs = [("TOR", "MTL", 4, 2), ("MTL", "TOR", 2, 3), ("NYI", "BOS", 3, 3),
             ("BOS", "NYI", 2, 1), ("TOR", "BOS", 5, 2), ("NYI", "MTL", 2, 4)]
    start = date(2023, 10, 10)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for index in range(HISTORY_GAMES):
            home, away, home_goals, away_goals = pairs[index % len(pairs)]
            day = start + timedelta(days=index // 2)
            writer.writerow([2023020000 + index, 20232024, 2, day.isoformat(),
                             f"{day.isoformat()}T23:00:00Z", home, away,
                             home_goals, away_goals, 30, 28,
                             home_goals != away_goals])


class PublishSiteBesideTheLab(PublishSite):
    """Publish Site's chain, with Gameday Refresh's runs in the same registry
    and every game on the schedule played to a final."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        super().__init__(tmp_path, monkeypatch)
        self.next_gameday = 501

    def _schedule(self, day: date) -> list[dict]:
        games = super()._schedule(day)
        for game, (home, away) in zip(games, FINALS):
            game["homeTeam"]["score"] = home
            game["awayTeam"]["score"] = away
            game.update(gameState="OFF", gameOutcome={"lastPeriodType": "REG"})
        return games

    def gameday(self, *, carries: bool = True) -> int:
        """A completed Gameday Refresh run on main, newest from now on. One
        that `carries` uploaded gameday-state; one that does not is the
        skipped 15:00 backup, which GitHub records as a success with no
        artifact."""
        run_id = self.next_gameday
        self.next_gameday += 1
        artifacts = {}
        if carries:
            state = self.tmp / f"gameday-state-{run_id}"
            _team_games(state / "processed" / "team_games.csv")
            artifacts["gameday-state"] = str(state)
        self.registry.insert(0, {"databaseId": run_id, "workflow": "gameday-refresh.yml",
                                 "status": "completed", "conclusion": "success",
                                 "artifacts": artifacts})
        return run_id

    def gh_calls(self) -> list[str]:
        log = self.state / "gh.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PublishSiteBesideTheLab:
    if shutil.which("bash") is None:
        pytest.fail("this test needs bash, which every runner here has")
    return PublishSiteBesideTheLab(tmp_path, monkeypatch)


def _frozen(outcome, day: date) -> dict:
    """The board the run kept for tomorrow's settlement: the published opinion."""
    assert "site-history" in outcome.artifacts, outcome.log
    path = Path(outcome.artifacts["site-history"]) / f"{day.isoformat()}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _projected(board: dict) -> int:
    """Games on the board with a projection for both sides."""
    return sum(1 for g in board["games"]
               if "projGoals" in g["home"] and "projGoals" in g["away"])


# --------------------------------------------------------------------------
# The listing.
# --------------------------------------------------------------------------


def test_one_502_on_the_state_listing_is_retried_and_the_board_is_projected(
    chain: PublishSiteBesideTheLab,
) -> None:
    """The finding's scenario: one 502 on the first publish of the day. It
    froze 0 of the day's games with a projection; the listing is now asked
    again, and the day's frozen board is the model's."""
    carrier = chain.gameday()

    first = chain.run(D1, fail={STATE_LISTING: 1})

    assert first.conclusion == "success", first.log
    assert f"Restored gameday-state from gameday-refresh.yml run {carrier}" in first.log
    frozen = _frozen(first, D1)
    assert len(frozen["games"]) == 2
    assert _projected(frozen) == 2, frozen["notice"]


def test_a_state_listing_that_never_answers_freezes_nothing_and_the_day_stays_the_models(
    chain: PublishSiteBesideTheLab, tmp_path: Path,
) -> None:
    """Every attempt fails. The run stops at the state step, before anything
    is built, frozen, kept or deployed; the next publish that day freezes
    the model's board, and the next morning settles every game on it."""
    chain.gameday()
    chain.run(D1)

    refused = chain.run(D2, fail={STATE_LISTING: 99})

    assert refused.conclusion == "failure", refused.log
    assert refused.failed_at == STATE_STEP, refused.failed_at
    assert "site-history" not in refused.artifacts, "a board built without the state was kept"
    assert refused.deployed is None, "a board built without the state was deployed"
    # The listing never answered; that is not an answer of "no carrier".
    assert "carries gameday-state" not in refused.log, refused.log
    assert "Could not list gameday-refresh.yml runs" in refused.log

    later = chain.run(D2)

    assert later.conclusion == "success", later.log
    frozen = _frozen(later, D2)
    assert _projected(frozen) == len(frozen["games"]) == 2, frozen["notice"]

    morning = chain.run(D3)

    results = morning.deployed["results"]
    assert results["resultsDate"] == D2.isoformat()
    assert len(results["games"]) == 2
    straight_up = results["summary"]["straightUp"]
    assert straight_up["w"] + straight_up["l"] == 2
    assert results.get("notice") is None
    assert render_results(results, tmp_path)["count"] == 2
    assert_the_history_only_grows(chain)


def test_the_skipped_backup_is_passed_over_and_asked_once(
    chain: PublishSiteBesideTheLab,
) -> None:
    """The newest Gameday Refresh run is usually the 15:00 backup, skipped
    because the primary ran clean: a success with no artifact. Only the
    listing is strict. A strict download (`--require-newest`) would fail
    Publish Site's run after every such backup, and retrying a run with no
    artifact asks the same question three times — every one of up to 30
    listed runs once the 90-day retention has passed, 30 seconds apiece."""
    primary = chain.gameday()
    backup = chain.gameday(carries=False)

    run = chain.run(D1)

    assert run.conclusion == "success", run.log
    assert f"Restored gameday-state from gameday-refresh.yml run {primary}" in run.log
    assert _projected(_frozen(run, D1)) == 2
    asked = [call for call in chain.gh_calls()
             if call.startswith(f"run download {backup} --name gameday-state ")]
    assert len(asked) == 1, asked


def test_a_listing_that_answers_with_no_carrier_still_publishes_the_schedule(
    chain: PublishSiteBesideTheLab,
) -> None:
    """GitHub answered and no run carries the state (a bare repository, or
    preseason before the first card): the one case that may build without
    it, and it still says so."""
    chain.gameday(carries=False)

    run = chain.run(D1)

    assert run.conclusion == "success", run.log
    assert "No completed run of gameday-refresh.yml on main carries gameday-state" in run.log
    frozen = _frozen(run, D1)
    assert len(frozen["games"]) == 2 and _projected(frozen) == 0
    assert "not available" in (frozen["notice"] or ""), frozen["notice"]


# --------------------------------------------------------------------------
# Results for a board that showed the schedule only.
# --------------------------------------------------------------------------


def test_results_say_the_board_carried_no_projection_rather_than_nothing_settled(
    chain: PublishSiteBesideTheLab, tmp_path: Path,
) -> None:
    """A schedule-only board is still frozen when GitHub answered with no
    carrier. Its games were played to a final, and the page said "No games
    were settled for this date." with Straight up 0–0, as if nothing had been
    played. It now says why there is nothing to settle."""
    chain.gameday(carries=False)
    chain.run(D1)

    morning = chain.run(D2)

    results = morning.deployed["results"]
    assert results["resultsDate"] == D1.isoformat()
    assert results["games"] == []
    notice = results.get("notice") or ""
    assert "schedule only" in notice and "no projection" in notice, notice
    assert "nothing to settle" in notice, notice
    page = render_results(results, tmp_path)
    assert page["isEmpty"] is True
    assert page["notice"] == notice
    assert page["notice"] != PAGE_FALLBACK


def _site_builder():
    path = PROJECT_ROOT / "web" / "build_site_json.py"
    spec = importlib.util.spec_from_file_location("_site_build_state_listing", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _board_game(game_id: str, *, projected: bool) -> dict:
    home, away = {"abbr": "TOR", "record": ""}, {"abbr": "MTL", "record": ""}
    if projected:
        home.update(projGoals=3.4, winProb=0.6, b2b=False)
        away.update(projGoals=2.7, winProb=0.4, b2b=False)
    return {"id": game_id, "startUtc": "2026-10-08T23:00:00Z", "venue": "Arena",
            "city": "City", "tv": "", "away": away, "home": home, "pick": None,
            "priced": False}


@pytest.mark.parametrize("games", ["projected-none-final", "dark-night"])
def test_a_board_with_a_projection_or_no_game_keeps_the_plain_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, games: str,
) -> None:
    """The notice is for a board that showed the schedule alone. A projected
    board whose games are not final, and a night with no game, settle
    nothing for their own reasons, and the page's own sentence is true of
    both."""
    module = _site_builder()
    history = tmp_path / "history"
    history.mkdir()
    board = {"phase": "regular", "boardDate": D1.isoformat(), "notice": None,
             "games": [_board_game("1", projected=True)]
             if games.startswith("projected") else []}
    (history / f"{D1.isoformat()}.json").write_text(json.dumps(board), encoding="utf-8")
    # The schedule answers, and no game on it is final.
    monkeypatch.setattr(module, "schedule_for", lambda day: [{"id": 1, "gameState": "FUT"}])

    results = module.settle(D1, history)

    assert results["games"] == []
    assert results.get("notice") is None, results.get("notice")
