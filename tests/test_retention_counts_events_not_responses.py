"""The retention table counted cached responses under the heading "Events probed".

`retention_from_cache` makes one `RetentionProbe` per cached RESPONSE, and the
four-hour and nine-and-a-half-hour purchases each priced nearly every event.
`retention_table` and `unmeasurable_markets` then counted probes, so the table
printed "Events probed 5432" over a cache holding 2,723 events (2,709 events
with two responses, 14 with one), and `player_hits` read "measurable
(1218/5432)", about 22%, where it was seen in 1,218 of 2,723 events, about
45%. The four-hour buy asked one region and neither book that quotes hits is
in it: its 2,706 responses carry no hits at all, and every one of them sat in
the hits denominator. The absence floor was counted the same way, so three
events priced at two moments cleared a floor of five events, and an absence
verdict would have read "not offered in any of N events" with N twice the
events. Found by the failure-shape audit (3/3 refuters), and measured on the
real cache before this fix.

What these tests hold: an event is counted once however many responses it
has, and is seen for a market when any of its responses carried the market;
the absence floor and the absence sentence count events; the table says how
many responses it read over how many events when those differ; the
unmeasurable list is exactly the set of markets the table calls not offered;
and the retention record written by `buy_historical_props.py --from-cache`
stores the event count as `events_probed`, with the response count under its
own key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhl_betting_lab.providers import historical_props as hist
from nhl_betting_lab.providers.odds_api import OddsApiProvider


SOG = "player_shots_on_goal"
HITS = "player_hits"
WANTED = [SOG, HITS]

#: The first-region books the four-hour buy saw; neither quotes hits.
ONE_REGION = {"draftkings": [SOG], "fanduel": [SOG]}
#: The nine-and-a-half-hour buy asked a second region, where hits is quoted.
TWO_REGION = {"draftkings": [SOG], "fanduel": [SOG], "espnbet": [SOG, HITS]}


def _event_id(index: int) -> str:
    # Provider ids are 32 hex characters, and retention_from_cache falls back
    # to the first 32 characters of the filename for one.
    return f"{index + 1:032x}"


def _write_response(
    raw_dir: Path, event_id: str, snapshot: str, books: dict[str, list[str]]
) -> Path:
    """One cached response, at the path and in the shape a purchase writes."""
    payload = {
        "timestamp": snapshot,
        "previous_timestamp": snapshot,
        "next_timestamp": snapshot,
        "data": {
            "id": event_id,
            "sport_key": "icehockey_nhl",
            "commence_time": "2025-01-05T23:00:00Z",
            "home_team": "Toronto Maple Leafs",
            "away_team": "Boston Bruins",
            "bookmakers": [
                {
                    "key": key,
                    "title": key,
                    "markets": [
                        {
                            "key": market,
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Auston Matthews",
                                    "price": -115,
                                    "point": 2.5,
                                }
                            ],
                        }
                        for market in markets
                    ],
                }
                for key, markets in books.items()
            ],
        },
    }
    path = hist._cache_path(event_id, snapshot, raw_dir=raw_dir, markets=WANTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


#: 9.5 hours and 4.0 hours before a 23:00Z face-off.
CARD_WINDOW = "2025-01-05T13:30:00Z"
LATE_WINDOW = "2025-01-05T19:00:00Z"


def _two_moments(raw_dir: Path, events: int, *, card_books, late_books) -> None:
    for index in range(events):
        _write_response(raw_dir, _event_id(index), CARD_WINDOW, card_books)
        _write_response(raw_dir, _event_id(index), LATE_WINDOW, late_books)


def _row(table: str, market: str) -> str:
    rows = [line for line in table.splitlines() if line.startswith(f"| `{market}` |")]
    assert len(rows) == 1, table
    return rows[0]


def test_an_event_priced_at_two_moments_is_one_event_seen_once(
    tmp_path: Path,
) -> None:
    """The real cache's shape: a two-region response and a one-region one.

    Two events, in both orders, so neither the first response nor the last
    one can stand in for the event: the first event's hits response is the
    earlier one, the second event's is the later one.
    """
    _write_response(tmp_path, _event_id(0), CARD_WINDOW, TWO_REGION)
    _write_response(tmp_path, _event_id(0), LATE_WINDOW, ONE_REGION)
    _write_response(tmp_path, _event_id(1), CARD_WINDOW, ONE_REGION)
    _write_response(tmp_path, _event_id(1), LATE_WINDOW, TWO_REGION)

    probes = hist.retention_from_cache(raw_dir=tmp_path, markets=WANTED)
    table = hist.retention_table(probes)

    assert _row(table, HITS) == f"| `{HITS}` | 2 | 2 | measurable (2/2) |", (
        "a response that could not have quoted hits must not pull its event "
        "out of 'Seen in', nor add a second event to 'Events probed'"
    )
    assert _row(table, SOG) == f"| `{SOG}` | 2 | 2 | measurable (2/2) |"
    assert len(probes) == 4, "the evidence is still read response by response"
    assert hist.events_probed(probes) == 2


def test_three_events_at_two_moments_cannot_clear_a_floor_of_five(
    tmp_path: Path,
) -> None:
    """Six responses are three events, and three is below the floor."""
    _two_moments(tmp_path, 3, card_books=ONE_REGION, late_books=ONE_REGION)

    probes = hist.retention_from_cache(raw_dir=tmp_path, markets=WANTED)
    table = hist.retention_table(probes)

    assert len(probes) == 6
    assert "not offered in any of 6" not in table
    assert _row(table, HITS) == (
        f"| `{HITS}` | 3 | 0 | not seen in 3 event(s) — too few to call it "
        "absent |"
    )
    assert "Only 3 event(s) probed." in table
    assert hist.unmeasurable_markets(probes) == {}, (
        "three events cannot write 'cannot be measured' into a report"
    )


def test_an_absence_verdict_names_the_events_it_saw_not_the_responses(
    tmp_path: Path,
) -> None:
    _two_moments(
        tmp_path,
        hist.MINIMUM_PROBES_FOR_ABSENCE,
        card_books=ONE_REGION,
        late_books=ONE_REGION,
    )

    probes = hist.retention_from_cache(raw_dir=tmp_path, markets=WANTED)
    table = hist.retention_table(probes)
    missing = hist.unmeasurable_markets(probes)

    events = hist.MINIMUM_PROBES_FOR_ABSENCE
    assert _row(table, HITS) == (
        f"| `{HITS}` | {events} | 0 | **not offered in any of {events} events** |"
    )
    assert set(missing) == {HITS}
    assert f"any of {events} probed events" in missing[HITS]
    assert str(2 * events) not in missing[HITS]


def test_the_table_says_how_many_responses_it_read_over_how_many_events(
    tmp_path: Path,
) -> None:
    """The doubling stays visible, in the table the report embeds."""
    _two_moments(tmp_path, 3, card_books=TWO_REGION, late_books=ONE_REGION)

    table = hist.retention_table(
        hist.retention_from_cache(raw_dir=tmp_path, markets=WANTED)
    )

    assert "6 responses were read over 3 events." in table
    assert "any of its responses carried it" in table
    assert "regions" in table, (
        "the cache records the markets a response asked for and not the "
        "regions; the table must say so rather than imply it was checked"
    )


def test_one_response_per_event_adds_no_response_count(tmp_path: Path) -> None:
    """A paid probe asks each event once; its table reads as it always did."""
    for index in range(3):
        _write_response(tmp_path, _event_id(index), CARD_WINDOW, TWO_REGION)

    table = hist.retention_table(
        hist.retention_from_cache(raw_dir=tmp_path, markets=WANTED)
    )

    assert _row(table, HITS) == f"| `{HITS}` | 3 | 3 | measurable (3/3) |"
    assert "responses were read" not in table


def test_the_unmeasurable_list_is_exactly_what_the_table_calls_absent() -> None:
    """Both count each market over the events that asked for it.

    `unmeasurable_markets` took its floor and its sentence from every probe,
    whatever each had asked, while the table counted per market. Five events
    of which two asked for hits made the table say "not seen in 2 event(s)"
    and the list say "Not offered on any of 5 probed events" — a market
    missing from a request that never mentioned it counted as absence.
    """
    probes = [
        hist.RetentionProbe(
            event_id=_event_id(index),
            snapshot=CARD_WINDOW,
            markets_requested=(SOG, HITS) if index < 2 else (SOG,),
            markets_returned=(SOG,),
        )
        for index in range(hist.MINIMUM_PROBES_FOR_ABSENCE)
    ]

    table = hist.retention_table(probes)

    assert _row(table, HITS) == (
        f"| `{HITS}` | 2 | 0 | not seen in 2 event(s) — too few to call it "
        "absent |"
    )
    assert hist.unmeasurable_markets(probes) == {}


def test_the_rebuilt_retention_record_counts_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`buy_historical_props.py --from-cache` wrote `events_probed: 5432`.

    Driven through the function `main` returns for `--from-cache`, which runs
    before any provider exists. `main` itself also loads the provider's
    `.env` first, and this path needs no credential, so it is not called.
    """
    from test_scripts import load_script

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("rebuilding retention must never make a request")

    monkeypatch.setattr(OddsApiProvider, "_get", explode)
    monkeypatch.setattr(OddsApiProvider, "__init__", explode)
    module = load_script("buy_historical_props.py")
    _two_moments(tmp_path / "raw", 3, card_books=TWO_REGION, late_books=ONE_REGION)
    out = tmp_path / "out"

    code = module._write_retention_from_cache(
        raw_dir=tmp_path / "raw", output_dir=out, markets=list(WANTED)
    )

    assert code == 0
    record = json.loads((out / module.RETENTION_FILENAME).read_text(encoding="utf-8"))
    assert record["events_probed"] == 3
    assert record["responses_read"] == 6
    assert _row(record["table"], HITS) == f"| `{HITS}` | 3 | 3 | measurable (3/3) |"
    assert record["unmeasurable"] == {}
