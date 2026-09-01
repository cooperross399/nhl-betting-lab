"""Checks that keep the lab honest across a whole season, not one run.

Every test here is a defect that survived a review round and was reproduced
before it was fixed. They are grouped by the shape of the failure rather than
by module, because that is how they were found: each one made the lab report
something false without any error anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from conftest import FakeResponse, RecordingRequester
from nhl_betting_lab.config import PROJECT_ROOT
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import selection_key
from nhl_betting_lab.season import schedule_cache_is_complete


SECRET = "season-readiness-secret"
ENVIRONMENT = {"NHL_ODDS_API_KEY": SECRET}


def _workflow(name: str) -> str:
    return (PROJECT_ROOT / ".github" / "workflows" / name).read_text(
        encoding="utf-8"
    )


# -- one wager, one selection ------------------------------------------


def test_the_scorer_and_the_goals_rung_are_one_selection_at_the_best_price() -> None:
    """Anytime scorer IS goals over 0.5, and two names for it staked it twice.

    The card publishes the best reachable price per selection. When the same
    wager arrived under two spellings the collapse never fired: both were
    published as independent best bets, the stake doubled, the worse price
    was quoted beside the better, and the forward ledger froze one outcome as
    two rows.
    """
    event = {
        "id": "evt1",
        "commence_time": "2026-10-09T23:00:00Z",
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "player_goals",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "Auston Matthews",
                                "price": 420,
                                "point": 0.5,
                            }
                        ],
                    },
                    {
                        "key": "player_goal_scorer_anytime",
                        "outcomes": [
                            {"name": "Auston Matthews", "price": 430}
                        ],
                    },
                ],
            }
        ],
    }

    rows = odds_api.normalize_event(event, fetched_at="2026-10-09T12:00:00Z")
    goals = [row for row in rows if row["market"] == "goals"]
    assert len(goals) == 2, "both spellings should still be staged"

    frame = pd.DataFrame(goals)
    keys = {
        selection_key(
            row,
            market=row.market,
            selection=row.selection,
            line=row.line,
        )
        for row in frame.itertuples()
    }
    assert len(keys) == 1, (
        "one wager must produce one selection key, or the card stakes it "
        f"twice: {keys}"
    )
    assert {str(row["selection"]) for row in goals} == {"over"}


# -- one bad market key must not cost every prop -----------------------


def test_a_refused_market_list_falls_back_to_the_core_markets() -> None:
    """Nineteen keys ride one request, so one dead key would zero the lot.

    The provider answers a market list it does not serve with a 422 for
    *every* event, so a key it stops serving mid-season would take every prop
    on every event with it — a season of empty cards that read exactly like
    books not posting props.
    """
    priced = {
        "id": "evt1",
        "commence_time": "2026-10-09T23:00:00Z",
        "home_team": "Toronto Maple Leafs",
        "away_team": "Boston Bruins",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "player_shots_on_goal",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "Auston Matthews",
                                "price": -115,
                                "point": 3.5,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    dead_key = odds_api.ALTERNATE_PROVIDER_MARKETS[0]

    def odds(url: str, **kwargs):
        asked = str(kwargs.get("params", {}).get("markets", ""))
        if dead_key in asked:
            return FakeResponse(status_code=422, payload={"message": "bad"})
        return FakeResponse(payload=priced, headers={"x-requests-last": "8"})

    # Most specific fragment first: the requester returns the first match,
    # and "/events" is a prefix of the per-event odds URL.
    requester = RecordingRequester(
        {
            "/events/evt1/odds": odds,
            "/events": FakeResponse(payload=[{"id": "evt1"}]),
        }
    )
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_player_props(
        markets=list(odds_api.PER_EVENT_PROVIDER_MARKETS)
        + list(odds_api.ALTERNATE_PROVIDER_MARKETS),
        credit_cap=500,
        fetched_at="2026-10-09T12:00:00Z",
    )

    assert result.rows, "the core markets must survive a refused ladder"
    assert any("422" in warning for warning in result.warnings)
    assert any(dead_key in warning for warning in result.warnings)


# -- a cache with holes cannot judge a slate ---------------------------


def test_a_holed_schedule_cache_reports_itself_incomplete(tmp_path: Path) -> None:
    """A partial cache is the same truth with holes, and the holes look
    exactly like exhibition games to anything that only asks whether a
    fixture is in the set."""
    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True)
    (directory / "TOR.json").write_text(
        json.dumps(
            {
                "games": [
                    {
                        "gameType": 2,
                        "gameDate": "2026-10-08",
                        "homeTeam": {"abbrev": "TOR"},
                        "awayTeam": {"abbrev": "BOS"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    complete, clubs = schedule_cache_is_complete(tmp_path)

    assert complete is False
    assert clubs == 2


def test_the_card_abstains_from_screening_on_a_holed_cache() -> None:
    """Dropping real games shrinks the slate the eligibility gate measures
    against, so a card built on one eighth of the night reports itself
    complete and green."""
    text = (PROJECT_ROOT / "scripts" / "run_gameday_card.py").read_text(
        encoding="utf-8"
    )

    assert "schedule_cache_is_complete" in text
    screen = text.index("not schedule_complete")
    abstain = text.index("preseason screen is skipped")
    assert screen < abstain


# -- the same event set on both sides of a coverage measurement --------


def test_capping_the_per_event_fetch_caps_the_bulk_fetch_too() -> None:
    """The slate is derived from the staged rows, so a bulk fetch of the
    whole board beside a capped per-event fetch reports the cap as the
    provider's absence."""
    events = [
        {
            "id": f"evt{index}",
            "commence_time": f"2026-10-0{index + 1}T23:00:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Toronto Maple Leafs", "price": -140},
                                {"name": "Boston Bruins", "price": 120},
                            ],
                        }
                    ],
                }
            ],
        }
        for index in range(4)
    ]
    requester = RecordingRequester({"/odds": FakeResponse(payload=events)})
    provider = odds_api.OddsApiProvider(
        environment=ENVIRONMENT, requester=requester
    )

    result = provider.fetch_team_markets(
        fetched_at="2026-10-01T12:00:00Z", max_events=2
    )

    assert result.events_seen == 2
    assert {row["provider_event_id"] for row in result.rows} == {"evt0", "evt1"}


def test_the_probe_asks_the_whole_board_with_a_matched_event_cap() -> None:
    """A starved probe and an unquoted market must never look alike: telling
    them apart is the whole job of the discovery workflow."""
    text = _workflow("provider-market-discovery.yml")

    assert "--horizon-days 0" in text
    assert "--max-events 20" in text
    asked = len(odds_api.PER_EVENT_PROVIDER_MARKETS) + len(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    assert f"'{asked * 20}'" in text, (
        "the credit cap must buy exactly the events the fetch is capped to, "
        f"which is {asked} markets x 20 events"
    )


# -- silence must stay safe to read ------------------------------------


def test_a_dark_night_cannot_hide_a_degraded_run() -> None:
    """The league does not play every night, so an empty slate that exits
    before the degraded check hides faults on half the season's nights."""
    text = _workflow("gameday-refresh.yml")
    report = text.index("- name: Report the outcome")
    tail = text[report:]

    assert tail.index("steps.health.outputs.degraded") < tail.index(
        "steps.prices.outputs.empty_slate"
    ), "the degraded check must come before the empty-slate exit"


def test_the_backup_run_stands_down_when_the_primary_already_delivered() -> None:
    """Two scheduled triggers, and when the first works the second has
    nothing to add but a duplicate bill."""
    text = _workflow("gameday-refresh.yml")

    assert "precheck" in text
    assert "needs.precheck.outputs.already != 'true'" in text
    # A manual run means run it, and a degraded card is exactly what the
    # backup exists to replace.
    assert "github.event_name }}\" != \"schedule\"" in text
    assert '"$DEGRADED" = "false"' in text


def test_the_forward_ledger_survives_a_broken_artifact_chain() -> None:
    """The prices it settled against are gone, so the ledger cannot be
    rebuilt from anything if the chain drops it."""
    text = _workflow("gameday-refresh.yml")

    assert "forward_evidence.csv" in text
    publish = text.index("BLOB_LEDGER")
    restore = text.index("refs/card-feed-tip:forward_evidence.csv")
    assert restore < publish, "the restore reads what an earlier run published"


def test_the_scheduled_probe_cannot_spend_without_a_cap() -> None:
    """The discovery workflow now runs on a cron, so nobody is watching it.

    A schedule turns a spending decision into a standing one, and the only
    thing standing between that and an unbounded bill is the cap. The
    expensive purchase workflow stays manual (pinned separately); this one
    may run itself precisely because every live invocation is capped.
    """
    text = _workflow("provider-market-discovery.yml")

    assert "schedule:" in text
    live_calls = [
        line for line in text.splitlines() if "--live" in line
    ]
    assert live_calls
    for line in live_calls:
        block = text[text.index(line):]
        block = block[: block.index("\n\n")]
        assert "--credit-cap" in block, (
            f"a live call with no cap reachable from a cron: {line.strip()}"
        )


# -- October: the logs know last season's club ------------------------


def _prop_row(player: str, home: str, away: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-10-08",
                "commence_time": "2026-10-09T23:00:00Z",
                "home_team": home,
                "away_team": away,
                "market": "shots_on_goal",
                "player": player,
                "selection": "over",
                "line": 2.5,
                "american_odds": -110,
                "book": "DraftKings",
            }
        ]
    )


class _Rates:
    def __init__(self, team: str) -> None:
        self.team = team
        self.expected_toi_seconds = 1200.0


class _StubModel:
    """Just enough model to exercise the side-of-the-game decision."""

    def __init__(self, player_id: int, logged_team: str) -> None:
        self.skaters = {player_id: _Rates(logged_team)}
        self.goalies: dict[int, _Rates] = {}
        self._player_id = player_id
        self.asked: list[tuple[str, str]] = []

    def resolve_player_in_game(self, name, *, home, away):
        return self._player_id

    def over_probability(self, player_id, market, line, *, opponent, venue, **kw):
        self.asked.append((opponent, venue))
        return 0.55


def test_a_traded_player_prices_against_tonights_opponent() -> None:
    """His rates travel with him; his opponent comes from tonight's sheet.

    The fitted team is the club of his last cached game, so every October
    each mover points at the club he left, matches neither side, and produces
    no opinion at all — a silently thinner opening night that reads exactly
    like books not posting props.
    """
    from nhl_betting_lab.reports.card_pricing import price_props

    model = _StubModel(player_id=8478402, logged_team="EDM")
    prices = _prop_row("Traded Forward", home="TOR", away="BOS")

    without, unresolved = price_props(prices, model)
    assert without == {} and unresolved == ["Traded Forward"], (
        "the stale team must not silently price against a guessed opponent"
    )

    with_roster, unresolved = price_props(
        prices, model, rosters={8478402: "TOR"}
    )

    assert unresolved == []
    assert with_roster, "the roster puts him on tonight's home side"
    assert model.asked[-1] == ("BOS", "home")


def test_a_roster_naming_a_team_not_in_the_game_still_produces_no_opinion() -> None:
    """A wrong roster must fail the same safe way a stale log does."""
    from nhl_betting_lab.reports.card_pricing import price_props

    model = _StubModel(player_id=8478402, logged_team="EDM")
    prices = _prop_row("Traded Forward", home="TOR", away="BOS")

    probabilities, unresolved = price_props(
        prices, model, rosters={8478402: "VAN"}
    )

    assert probabilities == {}
    assert unresolved == ["Traded Forward"]


# -- an empty file and a broken one are not the same thing ----------------


def test_an_empty_store_reads_as_empty_for_readers_and_writers(tmp_path) -> None:
    """A zero-byte file has nothing to lose, so neither path should refuse
    it. This one crashed a purchase after 157,870 credits had been spent."""
    from nhl_betting_lab.stores import read_store

    path = tmp_path / "store.csv"
    path.write_text("", encoding="utf-8")

    assert read_store(path, columns=("a",)).empty
    assert read_store(path, columns=("a",), for_append=True).empty


def test_a_damaged_store_is_readable_as_absent_but_never_appendable(
    tmp_path,
) -> None:
    """Something IS in there. A reader may report it as absent; a writer that
    did would replace a damaged file with a shorter one, turning a
    recoverable problem into a permanent one."""
    import pytest

    from nhl_betting_lab.stores import CorruptStoreError, read_store

    path = tmp_path / "store.csv"
    path.write_text('a,b\n1,2\n"unterminated,3\n4,5,6,7,8\n', encoding="utf-8")

    read_store(path, columns=("a", "b"))  # tolerated: reports nothing

    with pytest.raises(CorruptStoreError):
        read_store(path, columns=("a", "b"), for_append=True)


def test_the_purchase_restores_the_prices_it_already_bought() -> None:
    """Every purchase uploaded its bought cache and none restored it, so each
    run re-bought what the last one owned."""
    text = _workflow("historical-props-purchase.yml")

    assert "--name historical-props" in text
    restore = text.index("--name historical-props")
    upload = text.index("name: historical-props\n")
    assert restore < upload, "the restore must read what an earlier run wrote"


def test_the_price_store_deduplicates_on_the_quote_not_the_timestamp() -> None:
    """The store deduplicated on the whole row and called itself idempotent.
    It was not: two purchases of the same window labelled the same quotes with
    two different snapshot strings, nothing collapsed, and every price landed
    twice. The backtest then counted every bet twice — which leaves ROI
    unchanged and shrinks the interval by root two, so a duplicated store does
    not look wrong, it looks *significant*."""
    from nhl_betting_lab.stores import dedupe_prices

    quote = {
        "provider_event_id": "evt1",
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 2.5,
        "book": "DraftKings",
        "american_odds": -115.0,
    }
    frame = pd.DataFrame(
        [
            {**quote, "snapshot": "2025-10-18T15:05:39Z",
             "fetched_at": "2025-10-18T15:05:39Z"},
            {**quote, "snapshot": "2025-10-18T15:10:00Z",
             "fetched_at": "2025-10-18T15:10:00Z"},
            {**quote, "book": "BetMGM", "snapshot": "2025-10-18T15:10:00Z",
             "fetched_at": "2025-10-18T15:10:00Z"},
        ]
    )

    out = dedupe_prices(frame)

    assert len(out) == 2, "one quote per book, whatever the timestamps say"
    assert set(out["book"]) == {"DraftKings", "BetMGM"}


def test_deduplicating_without_the_event_id_is_refused_not_guessed() -> None:
    """It used to dedupe on whatever identity columns the caller passed.

    A frame read without `provider_event_id` has nothing telling one date
    from another, so every night's quote on the same player-market-line-book
    looks like one repeated quote. Asked to dedupe the real 2,675,428-row
    store that way it returned 64,253 rows and reported success: a silent 40x
    data loss inside the one function whose entire job is to be trusted.
    Refusing is the only safe answer, because the caller cannot see the loss.
    """
    import pytest

    from nhl_betting_lab.stores import dedupe_prices

    quote = {
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 2.5,
        "book": "DraftKings",
        "american_odds": -115.0,
    }
    # Two genuinely different nights. Identical on every column but the event.
    frame = pd.DataFrame(
        [
            {**quote, "date": "2025-10-18", "provider_event_id": "evt1"},
            {**quote, "date": "2025-10-21", "provider_event_id": "evt2"},
        ]
    )

    assert len(dedupe_prices(frame)) == 2, "two nights are two quotes"

    with pytest.raises(ValueError) as caught:
        dedupe_prices(frame.drop(columns=["provider_event_id"]))

    message = str(caught.value)
    assert "provider_event_id" in message, "say which column is missing"
    assert "usecols" in message, "say how to fix it"


def test_a_superseded_receipt_approves_nothing() -> None:
    """A withdrawn approval is kept as a record and must never be readable as
    a live one. It is not an orphan either — it is filed, deliberately."""
    from nhl_betting_lab.config import MANUAL_DIR
    from nhl_betting_lab.staging_provider_policy import load_policy

    directory = MANUAL_DIR / "human_acceptance_receipts"
    superseded = directory / "superseded"

    assert not list(directory.glob("*.json")), (
        "a receipt sitting beside the live ones reads as live"
    )
    if superseded.is_dir():
        assert (superseded / "README.md").is_file(), (
            "the archive has to say why these approve nothing"
        )
        cited = {
            entry.evidence_receipt_id
            for entry in load_policy().entries.values()
        }
        for path in superseded.glob("*.json"):
            assert path.stem not in cited, (
                f"{path.stem} is superseded and still cited by the policy"
            )


def test_a_refresh_that_cannot_re_decide_never_reports_a_clean_bill() -> None:
    """The first firing of Experiment Refresh reported "nothing moved" while
    every experiment had failed for want of the bought prices.

    That is the defect this lab keeps finding — a check reporting success
    because it never looked at the thing that failed — occurring inside the
    job built to catch exactly that. So the drift check now distinguishes a
    verdict that is unchanged from one that was never re-decided, and the
    workflow fails on the second.
    """
    source = (PROJECT_ROOT / "scripts" / "check_verdict_drift.py").read_text(
        encoding="utf-8"
    )
    assert "--since" in source
    assert "not re-decided" in source
    # The clean bill must be unreachable while anything is stale.
    assert "elif not stale:" in source

    workflow = _workflow("experiment-refresh.yml")
    assert "historical_prop_prices.csv" in workflow, (
        "the restore must verify the inputs every experiment needs"
    )
    assert "steps.drift.outputs.moved == '2'" in workflow, (
        "exit 2 is a broken refresh and must fail the run"
    )
