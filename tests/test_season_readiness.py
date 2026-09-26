"""Checks that keep the lab honest across a whole season, not one run.

Every test here is a defect that survived a review round and was reproduced
before it was fixed. They are grouped by the shape of the failure rather than
by module, because that is how they were found: each one made the lab report
something false without any error anywhere.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
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
    fixture is in the set.

    This fixture used to be one TOR-BOS game in a file called TOR.json, and
    asserted `clubs == 2` — the opponent-counting defect itself, green only
    because no real club file holds one game. A real one meets every other
    club, which is what made a single file read as complete (True, 32).
    """
    directory = tmp_path / "nhl" / "club_schedule"
    directory.mkdir(parents=True)
    others = [
        "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET",
        "EDM", "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT",
        "PHI", "PIT", "SEA", "SJS", "STL", "TBL", "UTA", "VAN", "VGK", "WPG",
        "WSH",
    ]
    (directory / "TOR_20262027.json").write_text(
        json.dumps(
            {
                "games": [
                    {
                        "gameType": 2,
                        "gameDate": f"2026-{10 + i // 28:02d}-{1 + i % 28:02d}",
                        "homeTeam": {"abbrev": "TOR"},
                        "awayTeam": {"abbrev": opponent},
                    }
                    for i, opponent in enumerate(others)
                ]
            }
        ),
        encoding="utf-8",
    )

    complete, clubs = schedule_cache_is_complete(tmp_path)

    assert complete is False
    assert clubs == 1, "one club's own file, however many clubs it names"


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

    # The run's final health, which also knows the card's and the
    # delivery's outcome, not the check that ran before the card.
    assert tail.index("steps.final.outputs.degraded") < tail.index(
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
        "commence_time": "2025-10-18T19:10:00Z",
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


def test_a_second_snapshot_window_does_not_overwrite_the_first() -> None:
    """Two moments are two quotes, and merging them cost 89.5% of a window.

    A purchase priced 2,710 events at 9.5 hours before face-off into a store
    already holding the same events at 4.0 hours. `PRICE_IDENTITY` carries no
    timestamp, so every 9.5-hour quote landed on the identity of the 4.0-hour
    quote it matched and `keep="last"` gave the collision to the new window:
    1,126,739 of 1,259,312 four-hour rows were overwritten, leaving 132,573.
    Nothing raised, the store still held 2.7 million rows, and the canonical
    report went on naming a population that was no longer on disk.
    """
    from nhl_betting_lab.stores import dedupe_prices

    quote = {
        "provider_event_id": "evt1",
        "commence_time": "2025-10-18T19:10:00Z",
        "market": "shots_on_goal",
        "player": "Auston Matthews",
        "selection": "over",
        "line": 2.5,
        "book": "DraftKings",
    }
    # The same wager, at the same book, on two different boards: the card is
    # built at 9.5 hours and the measurement was bought at 4.0.
    card = {**quote, "snapshot": "2025-10-18T09:40:00Z", "american_odds": -105.0}
    late = {**quote, "snapshot": "2025-10-18T15:10:00Z", "american_odds": -130.0}

    out = dedupe_prices(pd.DataFrame([late, card]))

    assert len(out) == 2, (
        "a nine-hour quote is not a re-label of a four-hour one; collapsing "
        "them silently deletes the window that was bought first"
    )
    assert sorted(out["american_odds"]) == [-130.0, -105.0]


def test_deduplicating_prices_that_cannot_be_dated_is_refused() -> None:
    """Without both timestamps the two windows are indistinguishable.

    Guessing here is the expensive direction: the guess that looked right
    merged a nine-hour board into a four-hour one and reported success.
    """
    import pytest

    from nhl_betting_lab.stores import dedupe_prices

    frame = pd.DataFrame(
        [
            {
                "provider_event_id": "evt1",
                "commence_time": "2025-10-18T19:10:00Z",
                "snapshot": "2025-10-18T15:10:00Z",
                "market": "shots_on_goal",
                "player": "Auston Matthews",
                "selection": "over",
                "line": 2.5,
                "book": "DraftKings",
                "american_odds": -115.0,
            }
        ]
    )

    assert len(dedupe_prices(frame)) == 1

    with pytest.raises(ValueError) as caught:
        dedupe_prices(frame.drop(columns=["commence_time"]))

    message = str(caught.value)
    assert "commence_time" in message, "say which column is missing"
    assert "usecols" in message, "say how to fix it"


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
            {**quote, "date": "2025-10-18", "provider_event_id": "evt1",
             "commence_time": "2025-10-18T19:10:00Z",
             "snapshot": "2025-10-18T15:10:00Z"},
            {**quote, "date": "2025-10-21", "provider_event_id": "evt2",
             "commence_time": "2025-10-21T19:10:00Z",
             "snapshot": "2025-10-21T15:10:00Z"},
        ]
    )

    assert len(dedupe_prices(frame)) == 2, "two nights are two quotes"

    with pytest.raises(ValueError) as caught:
        dedupe_prices(frame.drop(columns=["provider_event_id"]))

    message = str(caught.value)
    assert "provider_event_id" in message, "say which column is missing"
    assert "usecols" in message, "say how to fix it"


def test_a_measured_market_is_not_also_reported_unmeasurable() -> None:
    """The report measured `hits` and called it unmeasurable in one document.

    A retention probe of 256 events found `player_hits` at no book and wrote
    "cannot be measured against past prices". It asked one region. Both books
    that quote hits — ESPN BET and theScore Bet — are in the second, so the
    9.5-hour purchase came back with 16,048 rows and the backtest settled
    5,021 wagers on them, under a section still saying the market could not
    be measured. The measurement is the evidence; the probe is the stale side.
    """
    from nhl_betting_lab.reports.player_props_backtest import run_backtest

    prices = pd.DataFrame(
        [
            {
                "date": "2025-10-18",
                "commence_time": "2025-10-18T19:10:00Z",
                "snapshot": "2025-10-18T09:40:00Z",
                "provider_event_id": "evt1",
                "home_team": "Toronto Maple Leafs",
                "away_team": "Ottawa Senators",
                "market": "hits",
                "player": "Auston Matthews",
                "selection": "over",
                "line": 1.5,
                "american_odds": 200.0,
                "book": "ESPN BET",
            }
        ]
    )
    samples = pd.DataFrame(
        [
            {
                "date": "2025-10-18",
                "market": "hits",
                "player": "Auston Matthews",
                "player_id": 1,
                "team": "TOR",
                "line": 1.5,
                "mean": 2.4,
                "dispersion_r": None,
                "actual": 3.0,
            }
        ]
    )

    report = run_backtest(
        prices,
        samples,
        edge_threshold=0.0,
        phase="card",
        unmeasurable_markets={"hits": "Not offered in any of 256 probed events."},
        # A real map: without one this ran on the six-entry alias map, which
        # skipped the check that Matthews' team is in the game, and the
        # backtest now refuses such a store instead.
        team_names={"toronto maple leafs": "TOR", "ottawa senators": "OTT"},
    )

    assert report.by_market.get("hits"), "the fixture must actually measure hits"
    assert "hits" not in report.unmeasurable_markets, (
        "a market this run measured must not also be named unmeasurable"
    )
    assert any("stale" in note for note in report.notes), (
        "retiring the verdict silently is the same failure in the other "
        "direction — say the probe was contradicted"
    )


#: A claim about what may bet, stated as the current state. Each entry is
#: matched against whitespace-collapsed prose with quoted spans removed, so a
#: phrase still counts when it wraps across lines and stops counting when the
#: file is quoting its own superseded text.
#:
#: Present tense only, on purpose. "allowlisted nothing from the withdrawal
#: until Cooper approved twelve markets" is a true sentence about history and
#: must stay sayable; "allowlists nothing" is a claim about now.
_CLAIMS_NOTHING_MAY_BET = (
    "no market is allowlisted",
    "nothing is allowlisted",
    "allowlists nothing",
    "produces no selection, no lean, no pass and no stake",
    "recommends nothing, and says why",
)

_CLAIMS_EVERYTHING_MAY_BET = (
    "all 11 markets are allowlisted",
    "all eleven markets are allowlisted",
)


def _assertive_prose(text: str) -> str:
    """Prose with quoted spans dropped and whitespace collapsed.

    Two separate holes, both of which this repository has shipped through.

    A guard that greps for one spelling proves only that the spelling is
    absent: this test looked for `**No market is allowlisted.` and stayed
    green while CLAUDE.md said the card "produces no selection, no lean, no
    pass and no stake" and `what_we_can_and_cannot_claim.md` said "Nothing is
    allowlisted" — two files, both contradicting the policy, neither spelled
    the way the guard read. Collapsing whitespace also means a claim that
    wraps across a line break still counts, which a literal substring over the
    raw file does not.

    Dropping quoted spans is what makes the first half safe to widen. Both
    files record superseded text rather than deleting it, so the phrases above
    appear on purpose as history; the convention elsewhere in this lab is to
    phrase around a guarded spelling, which does not work for prose whose
    whole job is to quote what it used to say. Quoting it is the signal that
    it is no longer being asserted.
    """
    collapsed = " ".join(text.split())
    return re.sub(r'"[^"]*"', " ", collapsed).lower()


def test_the_operating_docs_agree_with_the_policy_about_what_may_bet() -> None:
    """CLAUDE.md carried both "no market is allowlisted" and "all 11 are".

    Forty lines apart, in the file whose first rule is that it overrides
    everything else, about the one question that decides whether the card may
    recommend a bet. `data/manual/staging_provider_policy.json` is the state
    that actually governs; prose that disagrees with it is not a second
    opinion, it is a false one — and the direction of the error matters,
    because a reader who believes the stale bullet believes the card is
    live.

    It has since been wrong in the other direction too, which is why the
    phrase lists are lists: after the twelve-market approval of 2026-09-23
    both files went on saying the card could not bet, in wording this test did
    not read.
    """
    from nhl_betting_lab.config import MANUAL_DIR
    from nhl_betting_lab.providers.odds_api import PROVIDER_NAME
    from nhl_betting_lab.staging_provider_policy import load_policy

    root = Path(MANUAL_DIR).resolve().parents[1]
    policy = load_policy()
    allowed = policy.allowed_markets(PROVIDER_NAME)

    for name in ("CLAUDE.md", "docs/what_we_can_and_cannot_claim.md"):
        prose = _assertive_prose((root / name).read_text(encoding="utf-8"))
        if allowed:
            for claim in _CLAIMS_NOTHING_MAY_BET:
                assert claim not in prose, (
                    f"{name} asserts {claim!r}, and the policy allowlists "
                    f"{sorted(allowed)}. The policy governs."
                )
        else:
            for claim in _CLAIMS_EVERYTHING_MAY_BET:
                assert claim not in prose, (
                    f"{name} asserts {claim!r}, and the policy allowlists "
                    "nothing. The policy governs."
                )

    operating = _assertive_prose((root / "CLAUDE.md").read_text(encoding="utf-8"))
    assert not (
        any(claim in operating for claim in _CLAIMS_NOTHING_MAY_BET)
        and any(claim in operating for claim in _CLAIMS_EVERYTHING_MAY_BET)
    ), "CLAUDE.md must not hold both answers at once"


def test_the_what_may_bet_guard_reads_more_than_one_spelling() -> None:
    """The guard above is the thing that failed, so it gets its own test.

    Both defects it missed are replayed here as prose, against a policy that
    allows something. A guard that cannot fail on these is the guard that let
    them ship.
    """
    shipped_and_missed = (
        'The card therefore produces no selection, no lean, no pass and no '
        "stake, and says why.",
        "**Nothing is allowlisted.** Cooper approved all eleven markets on "
        "2026-08-27.",
        # The same claim, wrapped the way markdown wraps it. A literal
        # substring over the raw file does not see this one at all.
        "**No market is\nallowlisted.** The 2026-08-27 approval was withdrawn.",
    )
    for prose in shipped_and_missed:
        assert any(
            claim in _assertive_prose(prose) for claim in _CLAIMS_NOTHING_MAY_BET
        ), f"the guard would not have caught: {prose!r}"

    # And the history-preserving forms must stay sayable, or the fix to the
    # docs cannot be written down.
    still_allowed = (
        'This section read "Nothing is allowlisted" until 2026-09-25.',
        'It went on asserting that the card "produces no selection, no lean, '
        'no pass and no stake".',
        "It allowlisted nothing from the withdrawal until Cooper approved "
        "twelve markets on 2026-09-23, which is what it holds now.",
    )
    for prose in still_allowed:
        assert not any(
            claim in _assertive_prose(prose) for claim in _CLAIMS_NOTHING_MAY_BET
        ), f"the guard would fire on legitimate history: {prose!r}"


#: The trees swept for the same claim in Python prose. `tests/` is NOT swept:
#: the phrase lists live there, and the test right above this one reproduces
#: both shipped defects verbatim on purpose, so a sweep of it would fire on
#: its own evidence. `docs/` beyond the one file already read is not swept
#: either, and that gap is deliberate rather than pending —
#: `docs/pre_registered_ladder_coherence.md` still says the policy
#: "allowlists nothing" in its registered text and corrects it in an adjacent
#: dated note, because a pre-registration records what was registered and is
#: not rewritten when the world moves. A guard demanding that sentence change
#: would be demanding the corruption of a registered protocol.
_PROSE_ROOTS = ("src", "scripts")


def _python_prose(path: Path) -> list[tuple[int, str]]:
    """Every comment and docstring in a module, as (line, text).

    Prose only. A string literal in executed code is deliberately excluded,
    which is the same line `test_ladder_route_cannot_reach_the_ledger.py`
    draws in the other direction — there only imports and code are read, and
    the prose "may discuss the allowlist freely"; here only the prose counts.

    That split is not tidiness, it is truth conditions. Two refusal messages
    in this repository say a form of "nothing is allowlisted" —
    `staging_provider_policy.refusal_reason` and
    `reports.policy_pr_gate.summary_line` — and both are correct, because each
    sits behind a branch that runs only when it IS true. A comment asserts
    unconditionally, to a reader, and that is the thing that goes stale.

    Consecutive comment lines are joined, so a claim wrapped across two `#`
    lines is read as one sentence. That is the same hole `_assertive_prose`
    closes for markdown by collapsing whitespace, and the stale comment this
    guard exists for wrapped exactly that way.
    """
    source = path.read_text(encoding="utf-8")
    found: list[tuple[int, str, bool]] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            found.append((token.start[0], token.string, True))
    for node in ast.walk(ast.parse(source)):
        if isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                found.append((getattr(node, "lineno", 1), docstring, False))

    found.sort(key=lambda item: item[0])
    merged: list[tuple[int, str]] = []
    run: list[str] = []
    start = 0
    previous: int | None = None
    for line, body, is_comment in found:
        if is_comment and run and previous == line - 1:
            run.append(body)
            previous = line
            continue
        if run:
            merged.append((start, " ".join(run)))
        run, start = [body], line
        previous = line if is_comment else None
    if run:
        merged.append((start, " ".join(run)))
    return merged


def test_no_source_prose_claims_the_card_may_not_bet() -> None:
    """The third copy of the stale claim was a comment, and nothing read it.

    `LADDER_CLASS_UNITS` in `ladder_coherence.py` explained itself with
    "nothing is allowlisted and only Cooper may change that" for three days
    after the twelve-market approval. The guard above had just been widened
    across the two operating documents and stayed green anyway, because a
    source comment is not one of the two files it reads: restoring that
    comment and running the whole suite passed 2504 tests.

    So the phrase lists are pointed at Python prose as well. Same lists, same
    normalisation, same direction-aware comparison against the live policy.
    """
    from nhl_betting_lab.config import MANUAL_DIR
    from nhl_betting_lab.providers.odds_api import PROVIDER_NAME
    from nhl_betting_lab.staging_provider_policy import load_policy

    root = Path(MANUAL_DIR).resolve().parents[1]
    allowed = load_policy().allowed_markets(PROVIDER_NAME)
    forbidden = _CLAIMS_NOTHING_MAY_BET if allowed else _CLAIMS_EVERYTHING_MAY_BET

    swept = 0
    for tree in _PROSE_ROOTS:
        for module in sorted((root / tree).rglob("*.py")):
            swept += 1
            for line, body in _python_prose(module):
                prose = _assertive_prose(body)
                for claim in forbidden:
                    assert claim not in prose, (
                        f"{module.relative_to(root)}:{line} asserts "
                        f"{claim!r}, and the policy allowlists "
                        f"{sorted(allowed)}. The policy governs. Quote the "
                        "superseded wording if it is being recorded rather "
                        "than asserted."
                    )
    assert swept > 50, (
        f"the sweep read only {swept} modules, so it is no longer reading the "
        f"trees it names ({_PROSE_ROOTS}). A guard over nothing passes."
    )


def test_the_source_sweep_reads_prose_and_spares_conditional_messages(
    tmp_path: Path,
) -> None:
    """Fired on the comment it missed, and on the four forms it must not break.

    The sweep above passing on a clean tree proves nothing by itself — that is
    exactly the state the old guard was in while three files contradicted the
    policy. So it is fired here on the comment it should have caught, and held
    off the prose it must leave alone.
    """
    shipped_and_missed = (
        "#: What the card would stake, if a card were ever licensed to stake\n"
        "#: anything. It is not: nothing is allowlisted and only Cooper may\n"
        "#: change that. These exist so a band means something concrete.\n"
        'UNITS = {"wide": 0.5}\n'
    )

    must_not_fire = (
        # A refusal message: executed code, true only on the branch that
        # prints it. `staging_provider_policy.refusal_reason` ships this.
        "def refusal_reason(blockers: list[str]) -> str:\n"
        "    if blockers:\n"
        '        return "Policy is not usable, so nothing is allowlisted: x"\n'
        '    return ""\n',
        # Prose quoting the claim to record it, not to assert it.
        # `reports.card_notification` ships this.
        '"""A notifier.\n'
        "\n"
        "A card that is blocked is a degraded run, not a quiet one. "
        '"No card,\n'
        'because no market is allowlisted" is information, and the first time\n'
        "it appears it must arrive.\n"
        '"""\n',
        # Prose whose subject is the script, not the policy.
        # `scripts/run_provider_shadow` ships this.
        '"""Run a shadow provider fetch.\n'
        "\n"
        "It adds no allowlist entry, promotes nothing, and places nothing.\n"
        '"""\n',
        # The comment as it now reads: superseded claim in quotation marks.
        '#: It is not — but the reason is no longer that "nothing is\n'
        '#: allowlisted". The policy has allowlisted twelve markets since\n'
        "#: 2026-09-23, and only Cooper may change that.\n"
        'UNITS = {"wide": 0.5}\n',
    )

    def sweep(source: str, name: str) -> list[str]:
        module = tmp_path / f"{name}.py"
        module.write_text(source, encoding="utf-8")
        return [
            claim
            for _, body in _python_prose(module)
            for claim in _CLAIMS_NOTHING_MAY_BET
            if claim in _assertive_prose(body)
        ]

    assert sweep(shipped_and_missed, "shipped"), (
        "the sweep would not have caught the LADDER_CLASS_UNITS comment, "
        "which is the defect it exists for"
    )
    for index, source in enumerate(must_not_fire):
        assert not sweep(source, f"benign_{index}"), (
            f"the sweep fires on prose it must leave alone: {source!r}"
        )

def test_the_operating_file_does_not_repeat_itself_verbatim() -> None:
    """A duplicated paragraph is how a stale figure survives its correction.

    The quota paragraph appeared twice, word for word, and the correction
    landed on one copy. Anything long enough to be a claim should appear
    once, so that fixing it fixes it.
    """
    from nhl_betting_lab.config import MANUAL_DIR

    root = Path(MANUAL_DIR).resolve().parents[1]
    for name in ("CLAUDE.md", "docs/what_we_can_and_cannot_claim.md"):
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        bullets: list[str] = []
        current: list[str] = []
        for line in lines:
            if line.startswith("- **"):
                if current:
                    bullets.append(" ".join(current))
                current = [line.strip()]
            elif current and line.startswith("  "):
                current.append(line.strip())
            elif current:
                bullets.append(" ".join(current))
                current = []
        if current:
            bullets.append(" ".join(current))
        seen: dict[str, int] = {}
        for bullet in bullets:
            seen[bullet] = seen.get(bullet, 0) + 1
        repeated = sorted(text for text, count in seen.items() if count > 1)
        assert not repeated, (
            f"{name} repeats {len(repeated)} bullet(s) verbatim; the first is "
            f"{repeated[0][:120]!r}"
        )


def test_a_superseded_receipt_approves_nothing() -> None:
    """A withdrawn approval is kept as a record and must never be readable as
    a live one. It is not an orphan either — it is filed, deliberately."""
    from nhl_betting_lab.config import MANUAL_DIR
    from nhl_betting_lab.staging_provider_policy import load_policy

    directory = MANUAL_DIR / "human_acceptance_receipts"
    superseded = directory / "superseded"

    # This asserted the live directory was EMPTY. That is the state the
    # repository was in, not the property being protected: the moment Cooper
    # signs, a receipt must sit there for the policy to cite, and the only
    # route back to green would be to weaken this — in the same commit as the
    # signature.
    #
    # "A receipt sitting beside the live ones reads as live" is about an
    # UNCITED receipt. A cited one is supposed to be there. So the invariant
    # is that every receipt in the live directory is cited by the policy, and
    # no superseded one is.
    cited_live = {
        entry.evidence_receipt_id for entry in load_policy().entries.values()
    }
    orphans = sorted(
        path.stem for path in directory.glob("*.json") if path.stem not in cited_live
    )
    assert not orphans, (
        f"receipts sit beside the live ones that no allowlist entry cites: "
        f"{orphans}. An uncited receipt reads as live and approves nothing."
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
