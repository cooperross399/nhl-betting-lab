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
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from nhl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, STAGING_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.market_eligibility import assess_markets, slate_games_from
from nhl_betting_lab.models.player_props import PlayerPropsModel
from nhl_betting_lab.models.toi_corrections import load_current_corrections
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.providers.team_names import (
    build_team_name_map,
    resolve_team,
    save_team_name_map,
)
from nhl_betting_lab.reports.card_pricing import (
    price_props,
    price_team_markets,
    selection_key,
)
from nhl_betting_lab.reports.gameday_card import build_card, save_card
from nhl_betting_lab.forward_evidence import write_snapshot
from nhl_betting_lab.season import (
    LEAGUE_TIMEZONE,
    known_regular_season_games,
    row_game_date,
)
from nhl_betting_lab.staging_provider_policy import load_policy
from nhl_betting_lab.verdicts import describe as describe_verdicts, ships


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-dir", default=str(STAGING_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument(
        "--now",
        default="",
        help="ISO instant to treat as now, for reproducing a past card.",
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

    policy = load_policy()
    print(f"Provider policy: {policy.status}")
    print(f"Recorded policy verdicts: {describe_verdicts(output_dir=outputs)}.")

    prices = _staged_prices(staging)

    # Regular season only. The provider does not flag preseason, the models
    # are fitted on regular season only, and exhibition results are never
    # ingested — an unfiltered card would freeze opinions into the forward
    # ledger that can never settle. A game the schedule cache does not know
    # is excluded and counted, never guessed at; with no schedule knowledge
    # at all, nothing is excluded and the run says so loudly.
    schedule = known_regular_season_games()
    if not prices.empty and schedule:
        # The screen judges only dates it actually knows. If next season's
        # schedule is not cached yet, every real game would read "unknown"
        # and the screen would exclude the entire opening slate — so outside
        # the known date range it abstains, which lets a stale cache leak a
        # preseason game rather than nuke a real one. The workflow refetches
        # schedules every run, so in production the range always covers the
        # slate.
        known_until = max(day for day, _, _ in schedule)
        team_lookup = build_team_name_map()

        def _is_regular(row) -> bool:
            day = row_game_date(row)
            if day > known_until:
                return True  # abstain: the cache cannot judge this date
            return (
                day,
                resolve_team(getattr(row, "home_team", ""), team_lookup) or "",
                resolve_team(getattr(row, "away_team", ""), team_lookup) or "",
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
            "be screened for preseason. Run scripts/fetch_nhl_data.py first."
        )

    slate = slate_games_from(prices)
    eligibility = assess_markets(
        prices,
        slate_games=slate,
        policy=policy,
        provider_name=odds_api.PROVIDER_NAME,
    )
    print(eligibility.summary_line())

    blockers: list[str] = []
    probabilities: dict[tuple, float] = {}
    unresolved_names: set[str] = set()

    # The provider says "Toronto Maple Leafs" and every model here is keyed by
    # "TOR". Without this map every lookup misses and every game is priced
    # league-average against league-average — with no error anywhere.
    team_names = build_team_name_map()
    if not team_names:
        blockers.append(
            "No team-name map could be built, because no boxscores are "
            "cached. Without it the provider's team names cannot be matched "
            "to the model, and every game would be priced league-average "
            "against league-average with nothing to show it."
        )
    else:
        save_team_name_map(team_names, processed_dir=processed)
        print(
            f"Team-name map: {len(set(team_names.values()))} franchises, "
            f"{len(team_names)} spellings."
        )

    logs = load_player_logs(processed)
    games = load_team_games(processed)
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
            prop_probabilities, unresolved = price_props(
                prices,
                props_model,
                corrections=corrections,
                team_names=team_names,
                history=props_history,
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
                prices, team_model, team_names=team_names, history=team_history
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
    written = write_snapshot(
        prices,
        probabilities,
        key_for=selection_key,
        verdicts_line=describe_verdicts(output_dir=outputs),
        snapshot_date=snapshot_day,
    )
    if written is not None:
        print(f"Priced snapshot frozen: {written}")
    else:
        print(
            f"A priced snapshot for {snapshot_day} already stands; the first "
            "opinion of the day is the one that settles."
        )

    card = build_card(
        prices,
        probabilities,
        eligibility=eligibility,
        blockers=blockers,
        now=moment,
        unresolved_names=sorted(unresolved_names),
    )
    paths = save_card(card, output_dir=outputs)
    print(card.summary_line())
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
