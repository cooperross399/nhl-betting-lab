#!/usr/bin/env python3
"""Build the gated gameday card from staged prices and fitted models.

    PYTHONPATH=src .venv/bin/python scripts/run_gameday_card.py

Reads only what is already on disk: the staged prices, the processed logs, and
the provider policy. It fetches nothing, spends no credits, edits no policy,
and places no bet.

The policy decides what may be priced; the measured bars decide what may be
recommended. A slate where nothing clears them produces a card with no
selections that says why — correct behaviour, not a failure — and a policy
allowlisting nothing produces no card at all, the state this repository
shipped in.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, STAGING_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.data.nhl_api import current_rosters
from nhl_betting_lab.market_eligibility import (
    assess_markets,
    slate_games_with_schedule,
)
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.toi_corrections import load_current_corrections
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.team_names import (
    TEAM_NAMES_FILENAME,
    boxscore_dir,
    build_team_name_map,
    cache_derived_spellings,
    resolve_team,
    save_team_name_map,
    saved_team_name_map,
)
from nhl_betting_lab.puck_drop import parse_commence_time
from nhl_betting_lab.reports.card_pricing import (
    price_props,
    price_team_markets,
    selection_key,
)
from nhl_betting_lab.reports.gameday_card import build_card, save_card
from nhl_betting_lab.forward_evidence import write_snapshot
from nhl_betting_lab.season import (
    EXPECTED_CLUBS,
    LEAGUE_TIMEZONE,
    known_regular_season_games,
    row_game_date,
    schedule_cache_is_complete,
    scheduled_regular_season_starts,
    season_id,
)
from nhl_betting_lab.staging_provider_policy import (
    load_policy,
    staged_prices_are_fresh,
)
from nhl_betting_lab.verdicts import (
    VERDICT_FILES,
    describe as describe_verdicts,
    ships,
    source as verdict_source,
)


def _staged_prices(staging_dir: Path) -> pd.DataFrame:
    frames = []
    for name in (
        odds_api.STAGING_PRICES_FILENAME,
        odds_api.STAGING_PROPS_FILENAME,
    ):
        path = staging_dir / name
        if path.is_file():
            try:
                frames.append(pd.read_csv(path))
            except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
                continue
    if not frames:
        return pd.DataFrame(columns=list(odds_api.PRICE_COLUMNS))
    return pd.concat(frames, ignore_index=True)


def _dated_before(frame: pd.DataFrame, day: date) -> pd.DataFrame:
    """The rows of a processed table whose league game date is before `day`.

    Both tables carry the NHL's own game date (`gameDate`), the league day,
    which is what `day` is. A row whose date cannot be read cannot be shown
    to precede `day`, so it is left out rather than guessed in. The
    walk-forward samplers drop such rows too.
    """

    def _precedes(value: object) -> bool:
        try:
            return date.fromisoformat(str(value)[:10]) < day
        except ValueError:
            return False

    keep = frame["date"].map(_precedes).astype(bool)
    return frame[keep].reset_index(drop=True)


def _under_way(start: str, moment: datetime) -> bool:
    """A scheduled game that has faced off. An unreadable start has not, as
    in `slate_games_with_schedule`: ambiguity counts as a game to card."""
    begins = parse_commence_time(start)
    return begins is not None and begins <= moment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument(
        "--raw-dir",
        default="",
        help=(
            "The NHL cache every raw read comes from: the boxscores the "
            "team-name map is built from, the club schedules the preseason "
            "screen uses, and the rosters. Defaults to data/raw."
        ),
    )
    parser.add_argument(
        "--now",
        default="",
        help=(
            "ISO instant to treat as now, for reproducing a past card. The "
            "processed tables are cut to games dated before its league day, "
            "so the models and the back-to-back flags see only what a run "
            "that morning could have seen."
        ),
    )
    parser.add_argument(
        "--archive-dir",
        default="",
        help=(
            "Where priced snapshots are frozen. Defaults to the real "
            "evidence archive, EXCEPT when --output-dir is not the default, "
            "in which case it follows that instead."
        ),
    )
    args = parser.parse_args(argv)

    moment = (
        datetime.fromisoformat(args.now)
        if args.now
        else datetime.now(timezone.utc)
    )
    if moment.tzinfo is None:
        parser.error("--now must carry a timezone; the puck-drop guard needs one.")

    staging = Path(args.staging_dir)
    processed = Path(args.processed_dir)
    outputs = Path(args.output_dir)
    # Every read of the raw cache goes here; None is each reader's own
    # default, data/raw. The card used to have no such flag and read the
    # default for all of it, whatever --processed-dir it was given.
    raw = Path(args.raw_dir) if args.raw_dir else None

    # A run pointed at a scratch output directory must not write into the
    # real evidence archive. It did once, in testing: a synthetic card
    # dated to opening night froze a snapshot there, and because the first
    # opinion of a day stands and is never repriced, the real opening-night
    # card would have been unable to freeze its own. Test rows would have
    # become the season's first forward evidence.
    #
    # So the archive follows a non-default output directory unless one is
    # named explicitly, and the run says out loud which archive it is
    # writing to whenever that is not the real one.
    archive_dir: Path | None = Path(args.archive_dir) if args.archive_dir else None
    if archive_dir is None and outputs.resolve() != OUTPUTS_DIR.resolve():
        archive_dir = outputs / "archive"
    if archive_dir is not None:
        print(
            f"Snapshots are frozen under {archive_dir}, not the real "
            "evidence archive, because this run is not writing to the "
            "default output directory."
        )

    policy = load_policy()
    print(f"Provider policy: {policy.status}")
    print(f"Recorded policy verdicts: {describe_verdicts(output_dir=outputs)}.")
    if outputs.resolve() != OUTPUTS_DIR.resolve():
        # A verdict the scratch directory records governs this run; one it
        # does not record is the repository's (see verdicts.source). Say
        # which, since the two can now differ within one run.
        read_from = ", ".join(
            f"{policy} {verdict_source(policy, output_dir=outputs)}"
            for policy in sorted(VERDICT_FILES)
        )
        print(f"Verdicts read from: {read_from}.")

    prices = _staged_prices(staging)

    # Freshness, as the policy states it: `max_provider_run_age_hours`, the
    # stricter of the policy-wide limit and the provider entry's (12 and 12
    # as shipped), judged on the oldest staged row at `moment`, so a
    # reproduced card is judged at the instant it reproduces. Until
    # 2026-09-25 the limit was parsed and never applied: a card rendered on
    # Wednesday over prices staged on Monday, 50 hours earlier, staked 0.5u
    # at Monday's price, froze it as the day's first opinion, and said
    # nothing about its age, while docs/provider_allowlist_approval.md
    # promised freshness on every run. Stale prices now block the card and
    # are never frozen, so a later run with fresh prices can still freeze
    # the day. Gameday Refresh fetches in the same job, so in CI this only
    # prints the age.
    stale = ""
    if not prices.empty:
        fresh, age = staged_prices_are_fresh(
            prices["fetched_at"] if "fetched_at" in prices.columns
            else [""] * len(prices),
            max_age_hours=policy.max_run_age_hours(odds_api.PROVIDER_NAME),
            now=moment,
        )
        print(f"Staged prices: {age}")
        if not fresh:
            stale = (
                f"The staged prices are too old to build a card from. {age} "
                "Nothing was priced from them, staked, or frozen; fetch fresh "
                "prices and run the card again."
            )

    # The provider says "Toronto Maple Leafs" and every model here is keyed by
    # "TOR". Without this map every lookup misses and every game is priced
    # league-average against league-average — with no error anywhere.
    #
    # ONE map serves the preseason screen and both pricers: the one the raw
    # cache builds, laid over the `team_names.csv` already in
    # --processed-dir. The cache wins where the two disagree, so a rename
    # still flows in; the file supplies what the cache does not hold. The
    # card used to build from the default raw cache only, twice, and never
    # read that file — the one every other reader of the map reads. Run from
    # a clone, whose data/raw is empty, with --processed-dir holding the real
    # map (101 spellings, 64 of them from the cache), it built the 6-spelling
    # alias map, blocked, and left all 12 team names on a real six-game slate
    # unresolved. And a cache knowing fewer teams than the file overwrote it
    # with the smaller map.
    # Built here, before the preseason screen and the eligibility slate,
    # because both match priced games to the schedule through it.
    from_cache = build_team_name_map(raw) if raw else build_team_name_map()
    team_names = {**saved_team_name_map(processed_dir=processed), **from_cache}

    # Regular season only. The provider does not flag preseason, the models
    # are fitted on regular season only, and exhibition results are never
    # ingested — an unfiltered card would freeze opinions into the forward
    # ledger that can never settle. A game the schedule cache does not know
    # is excluded and counted, never guessed at; with no schedule knowledge
    # at all, nothing is excluded and the run says so loudly.
    schedule = known_regular_season_games(raw)
    # Completeness of THIS slate's season, counted by each club's own file.
    schedule_complete, clubs_cached = schedule_cache_is_complete(
        raw, season=season_id(moment.astimezone(LEAGUE_TIMEZONE).date())
    )
    if not prices.empty and schedule and not schedule_complete:
        # A partial cache screens like a complete one and is wrong in the
        # worst possible direction: every game whose club file never landed
        # reads as "not regular season" and is dropped, the eligibility gate
        # then measures coverage against what survived, and a card built on
        # one eighth of the night reports itself complete and green. So the
        # screen abstains until the cache names every club. A leaked
        # exhibition game is visible in the card and settles as unsettleable;
        # a silently truncated slate is invisible.
        print(
            f"WARNING: the club-schedule cache holds this season's own "
            f"schedule for only {clubs_cached} of {EXPECTED_CLUBS} clubs, so "
            "it cannot say which games are "
            "preseason. The preseason screen is skipped rather than run on a "
            "cache with holes — a hole and an exhibition game look identical "
            "to it, and dropping real games would shrink the slate the "
            "eligibility gate measures against. Nor can the eligibility "
            "slate count a game no cached file names, so for those games "
            "coverage is judged only against what the provider returned. Run "
            "scripts/fetch_nhl_data.py to complete the cache."
        )
    elif not prices.empty and schedule:
        # The screen judges only dates it actually knows. If next season's
        # schedule is not cached yet, every real game would read "unknown"
        # and the screen would exclude the entire opening slate — so outside
        # the known date range it abstains, which lets a stale cache leak a
        # preseason game rather than nuke a real one. The workflow refetches
        # schedules every run, so in production the range always covers the
        # slate.
        known_until = max(day for day, _, _ in schedule)

        def _is_regular(row) -> bool:
            day = row_game_date(row)
            if day > known_until:
                return True  # abstain: the cache cannot judge this date
            return (
                day,
                resolve_team(getattr(row, "home_team", ""), team_names) or "",
                resolve_team(getattr(row, "away_team", ""), team_names) or "",
            ) in schedule

        keep = [_is_regular(row) for row in prices.itertuples()]
        excluded = len(keep) - sum(keep)
        if excluded:
            print(
                f"{excluded} price row(s) are for games the regular-season "
                "schedule does not know — preseason or unrecognisable — and "
                "were excluded before pricing. They are not passes and no "
                "opinion was frozen for them."
            )
        prices = prices[keep].reset_index(drop=True)
    elif not prices.empty:
        print(
            "WARNING: no regular-season schedule is cached, so nothing could "
            "be screened for preseason, and the eligibility gate can judge "
            "each market only against the games the provider returned — a "
            "game it priced in no market cannot count against any. Run "
            "scripts/fetch_nhl_data.py first."
        )

    # The slate is every game the prices cover PLUS every scheduled
    # regular-season game on the same league dates that no row prices. It
    # used to be `slate_games_from(prices)` — the distinct games of the very
    # frame the gate then judged — so a game the provider priced in no market
    # was missing from the slate and could never make any market INCOMPLETE.
    # Found by the failure-shape audit, reproduced on the real 2026-27
    # schedule: 8 games on 2026-10-01, 5 of them staged, and the gate printed
    # "1 of 12 markets eligible across 5 game(s): moneyline", "priced for all
    # 5 game(s) in the slate", while the same prices judged against the 8
    # read "Priced for 5 of 8 games". An allowlisted card then picked only
    # where prices happened to exist — the selection effect
    # `require_full_slate` exists to block — and never mentioned the three
    # games it had not seen. The screen above no longer shrinks the slate on
    # a partial cache; this closes the other door, the provider's.
    starts = scheduled_regular_season_starts(raw)
    slate, unpriced = slate_games_with_schedule(
        prices,
        starts,
        resolve=lambda name: resolve_team(name, team_names),
        now=moment,
    )
    if unpriced:
        print(
            f"{len(unpriced)} scheduled regular-season game(s) not yet under "
            "way match no priced game — the provider priced them in no "
            "market, or its rows could not be matched to the schedule — so "
            f"every market is judged against them too: {', '.join(unpriced)}."
        )
    eligibility = assess_markets(
        prices,
        slate_games=slate,
        policy=policy,
        provider_name=odds_api.PROVIDER_NAME,
    )
    print(eligibility.summary_line())

    blockers: list[str] = [stale] if stale else []
    # The eligibility report above describes what is staged, stale or not.
    # Opinions are another matter: stale rows reach no pricer, and the
    # snapshot below freezes only rows that carry an opinion, so nothing is
    # frozen from them and the day stays open for a run with fresh prices.
    priceable = prices.iloc[0:0] if stale else prices
    probabilities: dict[tuple, float] = {}
    unresolved_names: set[str] = set()

    # Not `if not team_names`: the builder always adds the Utah and Arizona
    # aliases, so with no boxscores it returns six entries and that check
    # never fired — and the six-entry map was then saved as team_names.csv,
    # where every later reader preferred it to a rebuild.
    if not cache_derived_spellings(team_names):
        blockers.append(
            "No team-name map could be built, because no boxscores are "
            f"cached: the map holds only its {len(team_names)} built-in "
            "alias spelling(s). Without it the provider's team names cannot "
            "be matched to the model, and every game would be priced "
            "league-average against league-average with nothing to show it. "
            f"Looked for boxscores under {boxscore_dir(raw)} and for a "
            f"{TEAM_NAMES_FILENAME} built from them under {processed}, and "
            "found neither: point --raw-dir at a boxscore cache or "
            f"--processed-dir at a directory holding {TEAM_NAMES_FILENAME}."
        )
    else:
        if cache_derived_spellings(from_cache):
            # Saved only when the cache supplied something, and saved as the
            # merged map, so a smaller cache never shrinks the file.
            save_team_name_map(team_names, processed_dir=processed)
        else:
            print(
                f"No boxscore under {boxscore_dir(raw)}: the team-name map is "
                f"the {TEAM_NAMES_FILENAME} in {processed}, read and left as "
                "it is."
            )
        print(
            f"Team-name map: {len(set(team_names.values()))} franchises, "
            f"{len(team_names)} spellings."
        )

    logs = load_player_logs(processed)
    games = load_team_games(processed)
    if args.now:
        # A reproduction reads the tables as they stood on the day it
        # reproduces. Until 2026-09-25 `--now` moved the clock and nothing
        # else, and both tables were read whole. Both models were fitted on
        # the reproduced night's own results and everything after it. The
        # whole table was also the back-to-back history, where each team's
        # last game is on or after any past night, so no side was ever on a
        # back-to-back, while the run printed both rest adjustments "in
        # force". Measured on the real tables: cut at each day, 1,187 of
        # 7,872 team-sides are tired; read whole, 0. On 2026-01-10, cut at
        # the day, the tables flag CHI, LAK and STL. The rest history alone
        # moved each of those moneylines by about 4 points and flipped 3 of
        # the card's 4 best bets. The fit read 3,936 games where the day
        # held 3,320, and the card read 4 best bets and 1 unit where the
        # tables cut at the day give 1 and 0.25 (finding f3).
        #
        # The cut is by league date, the day the walk-forward samplers cut
        # their fits on and the day `rest` counts in, so every game dated
        # before the reproduced day is kept and nothing from that day or
        # later is. The one thing it cannot do is keep a game of the same
        # league day that had finished by the instant, such as a matinee
        # before a late run: the tables carry no completion time.
        #
        # The live card is not cut. Its tables hold only games completed
        # before its own clock, so there is nothing to take out, and a cut
        # by league day would take out a same-day matinee that a delayed run
        # fetched. That game is the one that makes the next day's matinee a
        # back-to-back.
        #
        # A table with no date column at all is not one build_datasets
        # writes, and the cut cannot read it. It is read whole and the line
        # below says so, rather than emptied into a "no games on disk"
        # blocker that would be false.
        reproduced_day = moment.astimezone(LEAGUE_TIMEZONE).date()
        read: list[str] = []
        cut: list[pd.DataFrame] = []
        for label, table in (
            ("team game(s)", games),
            ("player-log row(s)", logs),
        ):
            if "date" in table.columns:
                kept = _dated_before(table, reproduced_day)
                read.append(
                    f"{len(kept)} of {len(table)} {label} kept, and "
                    f"{len(table) - len(kept)} dated on or after it or "
                    "undated set aside"
                )
                cut.append(kept)
            else:
                read.append(
                    f"all {len(table)} {label} read uncut, because that "
                    "table has no date column, so this reproduction may see "
                    "games after the day"
                )
                cut.append(table)
        games, logs = cut
        print(
            f"Reproducing {reproduced_day.isoformat()}: the models and the "
            "back-to-back history read only games dated before it, which is "
            f"what a run that morning could have seen: {'; '.join(read)}."
        )
    if logs.empty:
        blockers.append(
            "No player logs on disk, so no prop can be priced. Run "
            "scripts/fetch_nhl_data.py then scripts/build_datasets.py."
        )
    else:
        try:
            props_model = PlayerPropsModel().fit(logs)
            print(props_model.report.summary_line())
            # The by-TOI correction is applied only because — and only while
            # — the recorded experiment verdict says it won the price-based
            # backtest on both measured windows. The pooled correction
            # improved calibration and lost the backtest, so it is not here.
            # The decision is read from disk rather than asserted in code, so
            # the card's configuration is auditable against the experiment
            # that made it.
            corrections = None
            if ships("by_toi", output_dir=outputs):
                corrections = load_current_corrections(processed_dir=processed)
                print(f"Corrections in force: {corrections.describe()}.")
            else:
                print(
                    "No correction is in force: the recorded experiment "
                    "verdict does not ship one."
                )
            # Schedule history reaches the props pricer only while the
            # recorded experiment verdict ships the adjustment. Without it,
            # every side prices as rested — the un-tested policy is the one
            # that never moves a price.
            props_history = (
                games if ships("props_b2b", output_dir=outputs) else None
            )
            rosters = current_rosters(raw_dir=raw)
            if rosters:
                print(
                    f"Rosters: {len(rosters)} players across "
                    f"{len(set(rosters.values()))} clubs decide which side "
                    "each player is on."
                )
            else:
                print(
                    "No rosters are cached, so each player's side comes from "
                    "his last cached game. In October that is last season's "
                    "club for everyone who moved, and those props produce no "
                    "opinion. Run scripts/fetch_nhl_data.py."
                )
            prop_probabilities, unresolved = price_props(
                priceable,
                props_model,
                corrections=corrections,
                team_names=team_names,
                history=props_history,
                rosters=rosters,
            )
            probabilities.update(prop_probabilities)
            unresolved_names.update(unresolved)
            if props_model.ambiguous_names:
                print(
                    f"{len(props_model.ambiguous_names)} name(s) are shared by "
                    "two priced players and resolve to neither."
                )
        except (KeyError, ValueError) as exc:
            blockers.append(f"The props model could not be fitted: {exc}")

    if games.empty:
        blockers.append(
            "No team games on disk, so no team market can be priced."
        )
    else:
        try:
            team_model = TeamModel().fit(games)
            print(team_model.report.summary_line())
            # Schedule history reaches the team pricer only while the
            # recorded verdict ships the adjustment — the same door the props
            # side reads, because a policy the verdict file has withdrawn
            # must actually be withdrawn, not merely reported as off while
            # the factors keep applying.
            team_history = (
                games if ships("team_b2b", output_dir=outputs) else None
            )
            team_probabilities, unresolved = price_team_markets(
                priceable, team_model, team_names=team_names,
                history=team_history,
            )
            probabilities.update(team_probabilities)
            unresolved_names.update(unresolved)
        except (KeyError, ValueError) as exc:
            blockers.append(f"The team model could not be fitted: {exc}")

    if unresolved_names:
        preview = ", ".join(sorted(unresolved_names)[:8])
        print(
            f"{len(unresolved_names)} name(s) could not be resolved and "
            f"produced no selection: {preview}"
            + (" ..." if len(unresolved_names) > 8 else "")
        )
        print(
            "A fuzzy match would produce a confident price for a bet nobody "
            "placed, on a row that looks exactly like a correct one."
        )

    # Freeze today's opinions before anything else can reprice them. The
    # forward ledger settles these rows against the boxscore later; a
    # snapshot that already exists for today stands untouched, because the
    # card's first opinion of the day is the one that counts.
    snapshot_day = moment.astimezone(LEAGUE_TIMEZONE).date().isoformat()
    frozen: dict[str, object] = {}
    written = write_snapshot(
        prices,
        probabilities,
        key_for=selection_key,
        verdicts_line=describe_verdicts(output_dir=outputs),
        snapshot_date=snapshot_day,
        now=moment,
        archive_dir=archive_dir,
        tally=frozen,
    )
    withheld = (
        f"{frozen['started']} priced row(s) for games already under way and "
        f"{frozen['unconfirmed']} with an unconfirmable start were not frozen"
    )
    if frozen.get("state") == "frozen":
        print(f"Priced snapshot frozen: {written} ({frozen['frozen']} row(s)); {withheld}.")
    elif frozen.get("state") == "nothing_to_freeze" and stale:
        print(
            f"No snapshot was frozen for {snapshot_day}: the staged prices "
            "are too old to use, so none was priced. A later run today with "
            "fresh prices can still freeze the day's first opinion."
        )
    elif frozen.get("state") == "nothing_to_freeze" and prices.empty:
        print(
            f"No snapshot was frozen for {snapshot_day}: there were no prices. "
            "A later run today can still freeze the day's first opinion."
        )
    elif frozen.get("state") == "nothing_to_freeze":
        print(
            f"No snapshot was frozen for {snapshot_day}: the slate has prices "
            f"and no priced row could be frozen ({withheld}). A later run "
            "today can still freeze the day's first opinion."
        )
    else:
        print(
            f"A priced snapshot for {snapshot_day} already stands; the first "
            "opinion of the day is the one that settles."
        )

    # What tells a blocked card that is a fault from one that is not
    # (`why_nothing_to_card`): what the policy allowlists, and how many
    # regular-season games are still to be played on this league day.
    # Gameday Refresh used to read only this script's exit, 0 on every
    # blocked card, so a card blocked because the board priced 7 of 8 games
    # published a clean status and the 15:00 backup stood down. A policy that
    # did not load, or a schedule cache with holes, cannot vouch for anything,
    # so each is passed as None and the block stays a fault.
    allowlisted = (
        None if policy.blockers
        else policy.allowed_markets(odds_api.PROVIDER_NAME)
    )
    still_to_play: int | None = None
    if schedule_complete:
        still_to_play = sum(
            1
            for (day, _home, _away), start in starts.items()
            if day == snapshot_day and not _under_way(start, moment)
        )
    card = build_card(
        prices,
        probabilities,
        eligibility=eligibility,
        blockers=blockers,
        now=moment,
        unresolved_names=sorted(unresolved_names),
        allowlisted_markets=allowlisted,
        scheduled_games=still_to_play,
    )
    paths = save_card(card, output_dir=outputs)
    print(card.summary_line())
    if not card.card_generated:
        print(
            f"Not a fault: {card.nothing_to_card}"
            if card.nothing_to_card
            else "This block is a fault, not the policy's decision or an "
            "empty day: Gameday Refresh records the run as degraded, and the "
            "15:00 backup does not stand down for it."
        )
    if card.quarantined:
        print(
            f"Puck-drop guard removed {len(card.quarantined)} selection(s) "
            f"and {card.stake_removed_by_guard:g} unit(s) of stake."
        )
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print(
        "No bet was placed, no policy was edited, no market was allowlisted, "
        "and no price was invented."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
