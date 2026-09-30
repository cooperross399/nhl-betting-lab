#!/usr/bin/env python3
"""Capture the day's prices repeatedly, so line movement becomes observable.

    PYTHONPATH=src .venv/bin/python scripts/capture_line_movement.py --live \
        --credit-cap 400

Two of the three ideas left after the no-edge finding — a book leaving its
alternate ladder behind when it moves the main line, and a book lagging the
market on lineup news — are untestable for the same reason: this lab has only
ever seen **one** price per game, four hours before puck drop. A single
snapshot cannot show movement, and movement is the whole hypothesis.

So this captures the same board several times a day and keeps every
observation with the moment it was taken. It answers nothing on its own. It
makes two questions answerable that otherwise never are, and like forward
evidence it cannot be collected retroactively: a night not captured is gone.

**It touches nothing the card reads.** It writes only under
`data/processed/line_movement/`, never `data/staging/`, never the forward
ledger, never the policy. It places no bet and it decides nothing.

Each round asks two things on one clock: the per-event markets and their
alternate ladders (`fetch_player_props`, under `--credit-cap`), and the bulk
moneyline, puck line and total (`fetch_team_markets`, about 6 credits a
round: 3 markets x 2 regions, outside the per-event cap). Both land in the
same day file and the closing-line store, so a moneyline, puck-line or total
opinion can meet a closing price (`capture_team_markets`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.closing_lines import append_captures, best_prices
from nhl_betting_lab.config import PROCESSED_DIR
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.env_file import load_provider_env
from nhl_betting_lab.providers.odds_api import EmptySlateError
from nhl_betting_lab.preseason_screen import preseason_screen
from nhl_betting_lab.season import (
    LEAGUE_TIMEZONE,
    regular_season_games_still_to_play,
)


MOVEMENT_DIRNAME = "line_movement"

#: The per-event round was lost: the events list could not be read, or
#: per-event requests failed and no game's price came back, or the board is
#: missing games the schedule still lists. The Capture prices step goes red
#: on it, and every step after that one is `if: always()`. Team-market rows
#: that did come back are still written first; they never turn a lost
#: per-event round green, and a failed team fetch never turns a captured one
#: red (`capture_team_markets`).
EXIT_NOTHING_CAPTURED = 2


def report_failed_requests(
    failures: list[str], *, captured_nothing: bool, team_rows_kept: int = 0
) -> None:
    """Name every per-event request that failed, on the run page and in the log.

    A failed request is an absence of a different kind from a game no book
    quoted, and the capture has to say which one it was. `summary_line()`
    cannot: "4 price rows from 2 of 3 events" reads the same either way.

    `captured_nothing` is about the per-event round. `team_rows_kept` says
    how many bulk team-market rows were written beside a lost one, so the
    red run does not read as nothing written at all.
    """
    count = len(failures)
    named = "; ".join(failures)
    if captured_nothing:
        kept = (
            f" ({team_rows_kept} team-market row(s) from the bulk request "
            "were kept)"
            if team_rows_kept
            else ""
        )
        print(
            f"::error::No per-event price was captured this round and {count} "
            f"per-event request(s) failed, so this round's per-event prices "
            f"are lost, not empty{kept}: {named}"
        )
    else:
        print(
            f"::warning::{count} per-event price request(s) failed this round, "
            "so those games are absent from it, not unquoted; the games that "
            f"answered were kept: {named}"
        )
    print(
        f"{count} per-event request(s) failed. Those games' prices are absent "
        "from this round, not unquoted, and if it was a game's last round "
        "before face-off its closing price is an earlier round's.",
        file=sys.stderr,
    )
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)


def capture_team_markets(
    provider: odds_api.OddsApiProvider,
    *,
    league_days: list[str],
    keep_event,
    now: datetime,
) -> list[dict]:
    """The bulk moneyline, puck line and total for this round, or no rows.

    Until this was added the capture asked only the per-event markets and
    their ladders, so from 2026-08-29 (when the dedicated closing-line
    schedule was retired) no moneyline opinion could meet a closing price,
    and a featured puck line or total only when an alternate ladder repeated
    its line. The CLV report named them uncaptured every day.

    ONE CLOCK. `now`, the started-game filter's instant, is the per-event
    fetch's, and the rows are stamped with the round's `captured_at` when
    they are written (`write_round`), so a game facing off between the two fetches is dropped by both
    or by neither and the two land in one round for every reader. The screen
    and the window are the per-event fetch's too (`fetch_team_markets` says
    why they must be).

    `fetched_at` on these rows is the instant the bulk request went out, to
    the microsecond, where a per-event row's is the round's `captured_at` to
    the second. It is a different request, and that is how a reader tells
    the two apart without a new column: the ladder scan keeps one book's one
    response per ladder (`closing_lines.team_market_rows`).

    NEVER AT THE PER-EVENT ROUND'S EXPENSE. It runs after the per-event
    fetch, so a slow or hanging bulk request cannot delay it, and nothing it
    does reaches the exit code:

    * `EmptySlateError` (an off-day, the off-season, or a window holding no
      game) is an absence, printed as one;
    * `ProviderError`, and anything else it raises, is a named failure: a
      `::warning::` on the run page, and those markets are absent from this
      round, not unquoted. The per-event rows are written either way.
    """
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    try:
        team = provider.fetch_team_markets(
            fetched_at=fetched_at,
            keep_event=keep_event,
            league_days=league_days,
            now=now,
        )
    except EmptySlateError as exc:
        print(f"No team markets to capture: {exc}")
        return []
    except Exception as exc:  # noqa: BLE001 -- a team failure costs nothing else
        print(
            "::warning::The bulk team-market request (moneyline, puck line, "
            f"total) failed this round ({type(exc).__name__}: {exc}), so those "
            "markets are absent from it, not unquoted; the per-event prices "
            "were kept."
        )
        print(
            f"Team-market capture failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return []
    print(f"Team markets: {team.summary_line()}")
    for warning in team.warnings:
        print(f"  warning: {warning}")
    return list(team.rows)


def capture_path(day: str, *, processed_dir: Path | None = None) -> Path:
    """One file per league game date, so a season is many small files.

    A single accumulating file would be rewritten whole on every capture
    several times a day, which is how a long file gets truncated by a run
    that dies halfway.
    """
    root = (processed_dir or PROCESSED_DIR) / MOVEMENT_DIRNAME
    return root / f"{day}.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credit-cap", type=int, default=0)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=1,
        help="League game dates to capture, starting today.",
    )
    args = parser.parse_args(argv)

    if args.live and args.credit_cap <= 0:
        parser.error("--live requires a positive --credit-cap.")

    processed = Path(args.processed_dir)
    load_provider_env()
    if not args.live:
        print("Dry run: nothing was asked and no credit was spent.")
        return 0

    provider = odds_api.OddsApiProvider()
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(LEAGUE_TIMEZONE).date()
    league_days = [
        (today + timedelta(days=offset)).isoformat()
        for offset in range(max(args.horizon_days, 1))
    ]
    print(f"Capturing {league_days} at {captured_at}.")

    markets = list(odds_api.PER_EVENT_PROVIDER_MARKETS) + list(
        odds_api.ALTERNATE_PROVIDER_MARKETS
    )
    # The card's preseason screen, before the cap is spent. At 38 credits an
    # event the workflow's 600 buys fifteen, spent front-to-back in face-off
    # order, and from 2026-09-29 into early October the board holds
    # exhibition games that face off before the evening's regular-season
    # ones. Unscreened, a window holding more than fifteen events skipped a
    # regular-season game for the budget, and that round's movement and its
    # closing price were lost: no source keeps an archive. The screen is the
    # shadow run's (`nhl_betting_lab.preseason_screen`), with its
    # abstentions: no club-schedule cache, a cache missing a club, or a
    # team-name map that resolves nothing screens nothing and says so.
    # Guarded: the screen reads cached files, and a round is worth more than
    # a screen. Whatever goes wrong building it, the round is captured
    # unscreened, as it was before the screen existed, and says so.
    try:
        screen, screen_note = preseason_screen(
            today.isoformat(), processed_dir=processed
        )
    except Exception as exc:  # noqa: BLE001 -- any failure means no screen
        screen, screen_note = None, (
            "WARNING: the preseason screen could not be built "
            f"({type(exc).__name__}: {exc}), so nothing was screened for "
            "preseason. The per-event cap is spent in plain face-off order."
        )
    print(screen_note)
    # One clock for the started-game filter in both fetches and the schedule
    # check below, so a game facing off between two readings of the clock
    # cannot be dropped by one and counted by the other.
    now = datetime.fromisoformat(captured_at)
    result = None
    lost_exit = 0
    try:
        result = provider.fetch_player_props(
            markets=markets,
            keep_event=screen,
            credit_cap=args.credit_cap,
            fetched_at=captured_at,
            league_days=league_days,
            now=now,
        )
    except EmptySlateError as exc:
        # Not a fault, and not a red run: the league does not play every
        # night and does not play in July.
        print(f"Nothing to capture: {exc}")
    except odds_api.ProviderError as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        lost_exit = EXIT_NOTHING_CAPTURED

    # After the per-event fetch, whatever it did, so a lost per-event round
    # still keeps the moneyline, puck line and total, and a failed team fetch
    # costs the per-event round nothing (`capture_team_markets`).
    team_rows = capture_team_markets(
        provider,
        league_days=league_days,
        keep_event=screen,
        now=now,
    )
    per_event_rows = list(result.rows) if result is not None else []
    # Written before any exit is decided, so every rule below keeps what
    # came back from either fetch.
    write_round(
        per_event_rows + team_rows,
        captured_at=captured_at,
        day=league_days[0],
        processed=processed,
    )
    if result is None:
        return lost_exit

    # Keyed on the errors, not the rows. This script used to ignore
    # `result.errors` completely: it printed `summary_line()` and the
    # warnings and then returned 0. `fetch_player_props` records a failed
    # per-event request (a 503, a 429, a timeout, or a 422 the core-market
    # fallback could not recover) and moves on to the next game. So when one
    # request of three answered HTTP 503, the failure-shape audit's replay
    # exited 0 and logged "4 price rows from 2 of 3 events". That is the same
    # line a game no book quoted produces, apart from the credit figure, and
    # 503 never appeared. The round was lost for that game, and this source
    # keeps no archive. The same round is the one the closing-line store uses
    # as the close, so if it was the last one before face-off, CLV silently
    # fell back to the earlier round's price. When every request failed, the
    # log read "No rows returned; nothing written." with exit 0, the same as
    # a board nobody had priced.
    #
    # The rule now matches the one `capture_deployment.py` follows in this
    # same job. A partial round keeps what came back, exits 0, and names the
    # failed requests in a `::warning::`: one blip is not a red run. A round
    # where requests failed and nothing came back exits 2, and the Capture
    # prices step goes red. A game answered with no book, and a credit-cap
    # skip, are absences rather than failures, and they stay as they were.
    #
    # These rules read the PER-EVENT round alone. The team markets are one
    # bulk request beside it: their rows are written above whatever happens
    # here, a failed team request is its own `::warning::`, and neither
    # changes the exit. Team rows never make a lost per-event round green
    # (it lost every prop and ladder), and a failed team request never makes
    # a captured per-event round red.
    failures = list(result.errors)
    if not result.rows:
        print("No per-event rows returned.")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        if failures:
            report_failed_requests(
                failures, captured_nothing=True, team_rows_kept=len(team_rows)
            )
            return EXIT_NOTHING_CAPTURED
        # No failure, and no game in the window left to ask: an off-day, or
        # a board missing today's games. Sweep 4 (#257) taught the shadow
        # run to tell the two apart by the cached club schedule, which the
        # workflow's "Cache the club schedules" step fetches before this one
        # for free. This script read the same board and never asked, so a
        # provider or region glitch that dropped tonight's games from
        # /events was a red run in Gameday Refresh and a green one here,
        # "No rows returned; nothing written." with exit 0, and that round's
        # movement and closing price were gone: no source keeps an archive
        # (sweep 5, line-movement-capture-offday-board-green). Same rule,
        # same helper: games the schedule lists in the window that have not
        # faced off by the capture instant make it a failed round (exit 2,
        # Capture prices goes red). A red exit buys nothing more; no step
        # of the workflow retries the fetch on it. A board that had games to
        # ask and no book priced them is an absence, as it was, and so is a
        # day the schedule lists nothing still to play. Team rows the bulk
        # request returned do not answer it: that is another endpoint, and
        # the per-event board (/events) is the one missing the games.
        if result.events_seen == 0:
            scheduled = regular_season_games_still_to_play(
                league_days, not_started_by=now
            )
            if scheduled:
                print(
                    "::error::The provider's board lists none of the games "
                    f"on {', '.join(league_days)}, while the cached NHL "
                    f"schedule lists {scheduled} regular-season game(s) "
                    "there still to face off. The board is missing them, so "
                    "this round's per-event prices are lost, not an off-day"
                    + (
                        f" ({len(team_rows)} team-market row(s) were kept)."
                        if team_rows
                        else "."
                    )
                )
                return EXIT_NOTHING_CAPTURED
        return 0

    print(result.summary_line())
    for warning in result.warnings:
        print(f"  warning: {warning}")
    # After both writes, so the games that answered are kept either way.
    if failures:
        report_failed_requests(failures, captured_nothing=False)
    print(
        "This capture wrote no staging file, froze no opinion, edited no "
        "policy, and placed no bet."
    )
    return 0


def write_round(
    rows: list[dict], *, captured_at: str, day: str, processed: Path
) -> int:
    """Append one round to the day file and the closing-line store.

    Returns the rows appended to the day file; 0, and nothing written, when
    the round holds none.
    """
    if not rows:
        print("No rows returned; nothing written.")
        return 0
    frame = pd.DataFrame(rows, columns=list(odds_api.PRICE_COLUMNS))
    frame["captured_at"] = captured_at
    path = capture_path(day, processed_dir=processed)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append. Each capture is its own observation of the same market, and the
    # point of the file is that they differ. The same columns in the same
    # order for both fetches (PRICE_COLUMNS, then captured_at), so a round
    # written by this code appends cleanly to a day file an older round
    # started.
    header = not path.is_file()
    frame.to_csv(path, mode="a", header=header, index=False, lineterminator="\n")

    print(f"{len(frame)} rows appended to {path}.")

    # The same round also feeds the closing-line store, which keeps one row
    # per selection at the best price any book showed. It is a strict subset
    # of what was just written, so deriving it here retired a second
    # scheduled fetch. That fetch also bought the bulk moneyline, puck line
    # and total, and from 2026-08-29 until those were added to this round
    # (`capture_team_markets`) no moneyline opinion could meet a closing
    # price. Now both halves reach the store, featured line and ladder rung
    # alike: `best_prices` keys on the line, so the featured 6.0 and a ladder
    # rung at 6.0 are one selection at the better of the two prices.
    narrow = best_prices(frame, captured_at=captured_at)
    added = append_captures(narrow, processed_dir=processed)
    print(f"{added} best-price row(s) appended to the closing-line store.")
    return len(frame)


if __name__ == "__main__":
    raise SystemExit(main())
