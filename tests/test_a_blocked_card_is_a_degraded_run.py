"""A card blocked by a fault was recorded as a clean run.

`build_card` returns `card_generated=False` whenever anything blocks it, and
`run_gameday_card.py` exits 0 either way. That part is right: a blocked card
that explains itself is the product working. But Gameday Refresh decided the
run's health from exit codes alone. "Record whether the card was built" asked
only whether the card STEP succeeded, never whether a card came out of it, so
a card that rendered blocked left `run_degraded.txt` empty. The final health
then read `degraded=false`, card-feed published it, "Report the outcome"
finished green, and the 15:00 backup's precheck read a clean card for today
and stood down. Meanwhile `card_notification.decide()` posted the same card
as a degraded run ("A card that is *blocked* is a degraded run, not a quiet
one"), so the comment and the run's own health disagreed.

Found by the failure-shape audit: 2 of 3 refuters confirmed it, and the third
agreed the mechanism is real but argued it was intended, because the workflow
and the precheck were built while nothing was allowlisted. Replayed end to
end on the real card, post script and workflow shell, with 8 regular-season
games scheduled on 2026-10-01, the bulk board pricing 7 of them (VAN-EDM left
off) and the shipped 12-market allowlist:

* moneyline, puck_line and total_goals each read "Priced for 7 of 8 games";
* the card came out `card_generated=false` with the single blocker "No
  market is eligible for automated picks";
* `decide()` returned post=True, degraded=True;
* the workflow wrote `degraded=false`, card-feed got
  `{"decision": "post", "degraded": "false"}`, and the run said "Clean run.";
* the 15:00 precheck printed "Today's card (2026-10-01) is already published
  and clean. Skipping."

The same card at 15:00Z, with the eighth game on the board, builds
(card_generated=true, slate 8), so the day lost a card the backup would have
delivered. A `skip_provider_fetch` dispatch on a game day reached the same
clean status with no prices at all. Dispatched before 13:30 UTC, it stands
down both scheduled runs and leaves the day with no card and no frozen
snapshot.

Production card-feed shows why the rule below cannot simply be "blocked means
degraded". Both 2026-08-27 statuses (f858873, 707aaea) are a "No market is
eligible" card published with `degraded: false`, on an August day when every
market read "The provider returned no rows" and no game was scheduled. That
block was right to stay quiet, and it still does.

How often it happens: across the 358 bought evening bulk snapshots of 2024-25
and 2025-26 (22-23 UTC), 0 of 2,068 not-yet-started scheduled games were
missing from moneyline, puck_line or total_goals. The 09:30 board has not
been measured.

The rule now has one source. The card records, in `nothing_to_card`, why a
blocked card is NOT a fault, and the workflow calls every other blocked card
a degraded run. Two blocks are not faults, because no later run today could
build a card either, and a backup would buy the slate again to learn nothing:

* the provider policy allowlists no market the card may pick from. This is
  the state the lab shipped in, the state after the withdrawal of 2026-08-29,
  and the run CLAUDE.md records as green on 2026-08-26.
* no regular-season game is left to card today. An example is an October day
  before a later opening night, when the board carries only exhibition games.

Anything else that blocks a card on a game day is a degraded run: red,
card-feed `degraded: true`, and the backup runs. That covers a market priced
for 7 of 8 games, stale prices, a model that would not fit, no prices at all,
and a policy file that does not load. An empty slate (the fetch's exit 3)
stays quiet, as before.

These tests drive the real `run_gameday_card.main` over the 2026-10-01 world
of `test_the_card_slate_counts_unpriced_games`, with only the fitted models
stubbed. They then run the workflow's own step blocks under
`bash -eo pipefail`, in this order:

1. "Record whether the card was built";
2. the final health;
3. the card-feed publish, with real git plumbing into a local bare remote;
4. the next trigger's precheck, reading that status back;
5. "Report the outcome", on the same final health.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from nhl_betting_lab import config
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.market_eligibility import EligibilityReport
from nhl_betting_lab.providers import team_names as tn
from nhl_betting_lab.reports.gameday_card import build_card
from nhl_betting_lab.staging_provider_policy import load_policy
from test_no_test_reads_the_checkouts_data import point_default_data_dirs_at
from test_the_card_slate_counts_unpriced_games import (
    DAY,
    MORNING,
    NEXT_DAY,
    SEASON,
    SLATE,
    _boxscores,
    _event,
    _Fitted,
    _game,
    _home_opinions,
    _load_card,
    _schedule,
    _stage,
)


WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "gameday-refresh.yml"

#: The remote every card-feed step names, rewritten to a local bare
#: repository by `url.<path>.insteadOf`, so the real plumbing runs offline.
REMOTE = "https://x-access-token:x@github.com/o/r"

BLOCKED_NOTE = "The card was blocked, so there is no card for today"
UNREADABLE_NOTE = "left no card that could be read"


# --------------------------------------------------------------------------
# The card, from the real script.
# --------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    point_default_data_dirs_at(monkeypatch, tmp_path / "checkout_defaults")
    raw = tmp_path / "raw"
    _boxscores(raw)
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "RAW_DIR", raw)
    monkeypatch.setattr(tn, "PROCESSED_DIR", tmp_path / "default_processed")
    staging = tmp_path / "staging"
    staging.mkdir()
    return SimpleNamespace(tmp=tmp_path, raw=raw, staging=staging)


def _policy(root: Path, markets: list[str] | None):
    """`markets` allowlisted for the provider. An empty list is a valid policy
    that allowlists nothing, as the lab shipped and as the 2026-08-29
    withdrawal left it. None writes no policy file, which the loader refuses:
    a policy that does not load."""
    path = root / "data" / "manual" / "staging_provider_policy.json"
    if markets is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict = {
            "allowed_provider_names": [],
            "allowed_provider_types": [],
            "provider_allowlist_entries": {},
            "max_provider_run_age_hours": 12,
        }
        if markets:
            payload.update(
                allowed_provider_names=["the_odds_api"],
                allowed_provider_types=["odds_api"],
                provider_allowlist_entries={
                    "the_odds_api": {
                        "allowlist_status": "allowed",
                        "provider_type": "odds_api",
                        "approved_at": "2026-09-24T09:00:00-04:00",
                        "reviewer_name": "cooperross399",
                        "evidence_receipt_id": "receipt-1",
                        "required_markets": markets,
                    }
                },
            )
        path.write_text(json.dumps(payload), encoding="utf-8")
    return load_policy(repository_root=root)


def _write_schedule(raw: Path, games: list[dict]) -> None:
    """Every club's own `{ABBR}_{season}.json`, as `fetch_nhl_data` writes."""
    directory = raw / "nhl" / "club_schedule"
    directory.mkdir(parents=True, exist_ok=True)
    clubs = {g["homeTeam"]["abbrev"] for g in games} | {
        g["awayTeam"]["abbrev"] for g in games
    }
    for club in sorted(clubs):
        own = [
            g for g in games
            if club in (g["homeTeam"]["abbrev"], g["awayTeam"]["abbrev"])
        ]
        (directory / f"{club}_{SEASON}.json").write_text(
            json.dumps({"games": own}), encoding="utf-8"
        )


def _exhibitions_only_on_the_day(raw: Path) -> None:
    """2026-10-01 carries only exhibition games, and the regular season opens
    on the 2nd and 3rd. The cache is complete, since every club's own file
    holds its regular-season games; it simply has none on the 1st."""
    _write_schedule(raw, [
        _game(DAY, home, away, start, game_type=1) for home, away, start in SLATE
    ] + [
        _game("2026-10-02", home, away, "2026-10-02T23:00:00Z")
        for home, away in NEXT_DAY
    ] + [
        _game("2026-10-03", home, away, "2026-10-03T23:00:00Z")
        for home, away, _ in SLATE
    ])


def _board(world: SimpleNamespace, *, leave_off: tuple[str, ...] = ()) -> None:
    _stage(world.staging, [
        _event(home, away, start) for home, away, start in SLATE
        if home not in leave_off
    ])


#: Each scenario: (set up the world, the allowlisted markets, the instant).
SCENARIOS = {
    # The finding: VAN-EDM is not on the 09:30 board.
    "board-left-a-game-off": (
        lambda w: (_schedule(w.raw), _board(w, leave_off=("VAN",))),
        ["moneyline"], MORNING,
    ),
    # The control: the whole slate priced, so a card is built.
    "whole-board-priced": (
        lambda w: (_schedule(w.raw), _board(w)),
        ["moneyline"], MORNING,
    ),
    # A skip_provider_fetch dispatch, or a board with no usable rows.
    "no-prices-on-a-game-day": (
        lambda w: _schedule(w.raw),
        ["moneyline"], MORNING,
    ),
    # The schedule cannot vouch for an empty day when it has holes: only
    # the sixteen clubs that play on the 2nd have their files.
    "no-prices-and-a-schedule-with-holes": (
        lambda w: _schedule(w.raw, missing_files=tuple(
            club for home, away, _ in SLATE for club in (home, away)
        )),
        ["moneyline"], MORNING,
    ),
    # A policy file that does not load refuses everything. It is a fault.
    "policy-that-does-not-load": (
        lambda w: (_schedule(w.raw), _board(w)),
        None, MORNING,
    ),
    # The policy allowlists nothing, as shipped and as withdrawn.
    "nothing-allowlisted": (
        lambda w: (_schedule(w.raw), _board(w, leave_off=("VAN",))),
        [], MORNING,
    ),
    # The board carries only exhibition games; the screen removes them all.
    "no-regular-season-game-today": (
        lambda w: (_exhibitions_only_on_the_day(w.raw), _board(w)),
        ["moneyline"], MORNING,
    ),
    # 22:30 in New York: every game of the league day is under way and
    # nothing is priced. The next UTC day (the 2nd) still has eight to play.
    "every-game-already-under-way": (
        lambda w: _schedule(w.raw),
        ["moneyline"], "2026-10-02T02:30:00+00:00",
    ),
    # Production's 2026-08-27 run: no rows, and no game on the schedule.
    "an-august-day": (
        lambda w: _schedule(w.raw),
        ["moneyline"], "2026-08-27T19:17:56+00:00",
    ),
}

FAULTS = {
    "board-left-a-game-off", "no-prices-on-a-game-day",
    "no-prices-and-a-schedule-with-holes", "policy-that-does-not-load",
}


def _card(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
          capsys: pytest.CaptureFixture[str], scenario: str) -> SimpleNamespace:
    setup, markets, now = SCENARIOS[scenario]
    setup(world)
    module = _load_card()
    policy = _policy(world.tmp / "policy_root", markets)
    monkeypatch.setattr(module, "load_policy", lambda: policy)
    monkeypatch.setattr(module, "load_player_logs",
                        lambda _dir: pd.DataFrame({"player": ["x"]}))
    monkeypatch.setattr(module, "load_team_games",
                        lambda _dir: pd.DataFrame({"game_id": [1]}))
    monkeypatch.setattr(module, "PlayerPropsModel", _Fitted)
    monkeypatch.setattr(module, "TeamModel", _Fitted)
    monkeypatch.setattr(module, "current_rosters", lambda **_: {})
    monkeypatch.setattr(module, "price_props", lambda prices, model, **k: ({}, []))
    monkeypatch.setattr(
        module, "price_team_markets",
        lambda prices, model, **k: (_home_opinions(prices), []),
    )
    outputs = world.tmp / "outputs"
    code = module.main(
        ["--staging-dir", str(world.staging),
         "--processed-dir", str(world.tmp / "processed"),
         "--output-dir", str(outputs),
         "--now", now]
    )
    out = capsys.readouterr().out
    assert code == 0, "a blocked card is not a failed card step"
    path = outputs / "gameday_card.json"
    return SimpleNamespace(
        json=json.loads(path.read_text(encoding="utf-8")), out=out, path=path,
    )


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_card_says_whether_its_block_is_a_fault(
    world, monkeypatch, capsys, scenario: str
) -> None:
    card = _card(world, monkeypatch, capsys, scenario).json

    if scenario == "whole-board-priced":
        assert card["card_generated"] is True, card["blockers"]
        assert card["nothing_to_card"] == ""
        return
    assert card["card_generated"] is False
    if scenario in FAULTS:
        assert card["nothing_to_card"] == "", card["nothing_to_card"]
    elif scenario == "nothing-allowlisted":
        assert "allowlists no market" in card["nothing_to_card"]
    else:
        assert card["slate_games"] == 0
        assert "No regular-season game is left" in card["nothing_to_card"]
    if scenario == "board-left-a-game-off":
        assert card["slate_games"] == 8
        assert "Priced for 7 of 8 games" in card["excluded_markets"]["moneyline"]
        assert len(card["blockers"]) == 1
        assert "No market is eligible" in card["blockers"][0]


# --------------------------------------------------------------------------
# The workflow, from its own YAML.
# --------------------------------------------------------------------------

def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _step(*, name: str = "", id_: str = "") -> dict:
    for job in _jobs().values():
        for step in job.get("steps", []):
            if (name and step.get("name") == name) or (id_ and step.get("id") == id_):
                return step
    raise AssertionError(f"no step {name or id_}")


def _render(block: str, values: dict[str, str]) -> str:
    """Fill the `${{ }}` expressions a test names; refuse any it did not."""
    def fill(match: re.Match) -> str:
        expression = match.group(1).strip()
        if expression not in values:
            raise AssertionError(f"unfilled expression: {expression}")
        return values[expression]
    return re.sub(r"\$\{\{(.*?)\}\}", fill, block)


def _bash(block: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", block],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def _outputs(path: Path) -> dict[str, str]:
    """GITHUB_OUTPUT as the runner reads it: the last value of a key wins."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        found[key] = value
    return found


@pytest.fixture(autouse=True)
def a_real_jq() -> None:
    assert shutil.which("jq"), (
        "the workflow's steps read JSON with jq, which every GitHub runner "
        "carries; these tests run those steps as they are"
    )


def _workspace(tmp_path: Path, card: object, *, quiet: str = "") -> Path:
    """A runner's working directory after the health step found nothing
    wrong: `card` is what the card step left on disk (None: nothing)."""
    work = tmp_path / "work"
    (work / "data" / "outputs").mkdir(parents=True)
    if isinstance(card, Path):
        shutil.copy(card, work / "data" / "outputs" / "gameday_card.json")
    elif card is not None:
        (work / "data" / "outputs" / "gameday_card.json").write_text(
            json.dumps(card), encoding="utf-8"
        )
    (work / "run_degraded.txt").write_text("", encoding="utf-8")
    (work / "run_quiet.txt").write_text(quiet, encoding="utf-8")
    return work


def _built(work: Path, outcome: str = "success") -> str:
    block = _render(_step(name="Record whether the card was built")["run"],
                    {"steps.card.outcome": outcome})
    result = _bash(block, work, dict(os.environ))
    assert result.returncode == 0, result.stderr
    return (work / "run_degraded.txt").read_text(encoding="utf-8")


def _final(work: Path, tmp_path: Path) -> str:
    output = tmp_path / "final_output"
    output.write_text("", encoding="utf-8")
    block = _render(_step(id_="final")["run"], {"steps.post.outcome": "success"})
    result = _bash(block, work, {**os.environ, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    return _outputs(output)["degraded"]


def _report(work: Path, degraded: str) -> int:
    block = _render(_step(name="Report the outcome")["run"], {
        "steps.final.outputs.degraded": degraded,
        "steps.prices.outputs.empty_slate": "false",
        # The card-feed publish ran; its failure is its own test's business.
        "steps.cardfeed.outcome": "success",
        "steps.settle.outcome": "success",
        "steps.rebuild.outcome": "success",
        "steps.clv.outcome": "success",
    })
    return _bash(block, work, dict(os.environ)).returncode


def _git_env(tmp_path: Path, day: str) -> dict:
    """Real git, offline: the remote is a local bare repository, no user or
    system configuration is read, and `date` answers the run's day."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "date"
    stub.write_text(f"#!/bin/sh\necho {day}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    remote = tmp_path / "remote.git"
    if not remote.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True,
                       env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                            "GIT_CONFIG_NOSYSTEM": "1"})
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{remote}.insteadOf",
        "GIT_CONFIG_VALUE_0": REMOTE,
        "GH_TOKEN": "x",
    }


def _publish(work: Path, tmp_path: Path, degraded: str, day: str) -> dict:
    env = _git_env(tmp_path, day)
    subprocess.run(["git", "init", "-q"], cwd=work, env=env, check=True)
    block = _render(_step(name="Publish the card to the card-feed branch")["run"], {
        "github.repository": "o/r",
        "github.server_url": "https://github.com",
        "github.run_id": "1",
        "steps.post.outputs.decision || 'none'": "post",
        "steps.final.outputs.degraded || 'unknown'": degraded,
        "steps.prices.outputs.empty_slate || 'false'": "false",
    })
    result = _bash(block, work, env)
    assert result.returncode == 0, result.stderr
    shown = subprocess.run(
        ["git", "--git-dir", str(tmp_path / "remote.git"), "show",
         "card-feed:latest_status.json"],
        env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(shown.stdout)


def _precheck(tmp_path: Path, day: str) -> str:
    """The next scheduled trigger's first job, reading card-feed back."""
    env = _git_env(tmp_path, day)
    checkout = tmp_path / "precheck"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=checkout, env=env, check=True)
    output = tmp_path / "precheck_output"
    output.write_text("", encoding="utf-8")
    block = _render(_step(id_="feed")["run"], {
        "github.event_name": "schedule", "github.repository": "o/r",
    })
    result = _bash(block, checkout, {**env, "GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    return _outputs(output)["already"]


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_the_run_health_follows_the_card(
    world, monkeypatch, capsys, tmp_path: Path, scenario: str
) -> None:
    """End to end: the real card, through the run's final health, card-feed's
    status and the run's exit, into the backup's precheck. A fault leaves the
    backup free to run; a card, or a block no rerun could lift, stands it
    down."""
    card = _card(world, monkeypatch, capsys, scenario)
    work = _workspace(tmp_path, card.path)
    fault = scenario in FAULTS

    notes = _built(work)
    degraded = _final(work, tmp_path)
    status = _publish(work, tmp_path, degraded, DAY)
    already = _precheck(tmp_path, DAY)

    assert degraded == ("true" if fault else "false"), notes
    assert (BLOCKED_NOTE in notes) is fault
    assert status["date"] == DAY and status["degraded"] == degraded
    assert (_report(work, degraded) == 0) is not fault
    assert already == ("false" if fault else "true")


def test_the_comment_says_what_blocked_the_card(
    world, monkeypatch, capsys, tmp_path: Path
) -> None:
    """The post script reads the same notes, so the email says what the run's
    health says, and names the blocker."""
    card = _card(world, monkeypatch, capsys, "board-left-a-game-off")
    work = _workspace(tmp_path, card.path)
    _built(work)

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "post_card_to_issue.py"),
         "--card-json", str(card.path),
         "--degraded-file", str(work / "run_degraded.txt"),
         "--out", str(tmp_path / "comment.md"),
         "--title-out", str(tmp_path / "title.txt"),
         "--body-out", str(tmp_path / "body.md")],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True, text=True,
    )
    comment = (tmp_path / "comment.md").read_text(encoding="utf-8")
    went_wrong = comment.split("### What went wrong", 1)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "post"
    assert len(went_wrong) == 2, "the comment does not say what went wrong"
    assert BLOCKED_NOTE in went_wrong[1] and "No market is eligible" in went_wrong[1]


BLOCKED_BY_A_FAULT = {
    "card_generated": False, "nothing_to_card": "",
    "blockers": ["No market is eligible for automated picks."],
}


@pytest.mark.parametrize(
    ("card", "note"),
    [
        (BLOCKED_BY_A_FAULT, BLOCKED_NOTE),
        # A card that does not say its block is benign is a fault.
        ({"card_generated": False, "blockers": ["Stale."]}, BLOCKED_NOTE),
        ({"card_generated": True, "blockers": [], "nothing_to_card": ""}, None),
        ({**BLOCKED_BY_A_FAULT,
          "nothing_to_card": "The provider policy allowlists no market."}, None),
        # The step succeeded and left nothing, or nothing readable.
        (None, UNREADABLE_NOTE),
        ([], UNREADABLE_NOTE),
    ],
    ids=["blocked-by-a-fault", "blocked-and-silent-about-why", "built",
         "blocked-with-nothing-to-card", "no-card-on-disk", "not-a-card"],
)
def test_the_step_reads_the_card_not_the_exit(
    tmp_path: Path, card: object, note: str | None
) -> None:
    notes = _built(_workspace(tmp_path, card))

    if note is None:
        assert notes == ""
    else:
        assert note in notes, notes
        assert len(notes.splitlines()) == 1
    if card is BLOCKED_BY_A_FAULT:
        assert "No market is eligible for automated picks." in notes


def test_an_empty_slate_stays_quiet(tmp_path: Path) -> None:
    """The fetch's exit 3: no NHL game on the board, which the health step
    records in run_quiet.txt. A blocked card on that day is expected."""
    work = _workspace(
        tmp_path, BLOCKED_BY_A_FAULT,
        quiet="No NHL games are scheduled, so there was nothing to price. Not a fault.\n",
    )

    notes = _built(work)

    assert notes == ""
    assert _final(work, tmp_path) == "false"


def test_a_crashed_card_is_still_a_crash(tmp_path: Path) -> None:
    """The card JSON is read only after a card step that succeeded. A crash
    stays a crash, whatever the disk holds, even on an empty slate."""
    work = _workspace(tmp_path, {"card_generated": True}, quiet="No games.\n")

    notes = _built(work, outcome="failure")

    assert "could not be rendered" in notes
    assert BLOCKED_NOTE not in notes


# --------------------------------------------------------------------------
# build_card's rule, directly.
# --------------------------------------------------------------------------

def _nothing_eligible(games: int) -> EligibilityReport:
    return EligibilityReport(provider_name="the_odds_api", games_in_slate=games)


def test_a_fault_the_caller_names_is_always_a_fault() -> None:
    """Nothing allowlisted and no game to card, but the team model would not
    fit: that is still a fault, because it costs the forward ledger the
    day's opinions whatever the policy says."""
    card = build_card(
        pd.DataFrame(), {}, eligibility=_nothing_eligible(0),
        blockers=["The team model could not be fitted: boom"],
        allowlisted_markets=(), scheduled_games=0,
    )

    assert card.card_generated is False
    assert card.nothing_to_card == ""


def test_a_hard_gated_market_alone_leaves_nothing_to_pick() -> None:
    """goalie_saves cannot produce a selection even when allowlisted, so a
    policy that allowlists only it allows the card nothing."""
    card = build_card(
        pd.DataFrame(), {}, eligibility=_nothing_eligible(8),
        allowlisted_markets=("goalie_saves",), scheduled_games=8,
    )

    assert card.card_generated is False
    assert "allowlists no market" in card.nothing_to_card


def test_a_caller_that_says_nothing_gets_a_fault() -> None:
    """Without the policy and the schedule, build_card cannot vouch that a
    block is benign, so the run is degraded rather than quietly clean."""
    card = build_card(pd.DataFrame(), {}, eligibility=_nothing_eligible(0))

    assert card.card_generated is False
    assert card.nothing_to_card == ""
