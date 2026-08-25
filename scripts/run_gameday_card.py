#!/usr/bin/env python3
"""Build the gated gameday card from staged prices and fitted models.

    PYTHONPATH=src .venv/bin/python scripts/run_gameday_card.py

Reads only what is already on disk: the staged prices, the processed logs, and
the provider policy. It fetches nothing, spends no credits, edits no policy,
and places no bet.

With the shipped policy — which allowlists nothing — this produces **no card
and no selections**, and says why. That is the correct behaviour, not a
failure.
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
from nhl_betting_lab.models.team_model import TeamModel
from nhl_betting_lab.providers import odds_api
from nhl_betting_lab.reports.card_pricing import price_props, price_team_markets
from nhl_betting_lab.reports.gameday_card import build_card, save_card
from nhl_betting_lab.staging_provider_policy import load_policy


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

    prices = _staged_prices(staging)
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
            prop_probabilities, unresolved = price_props(prices, props_model)
            probabilities.update(prop_probabilities)
            if unresolved:
                print(
                    f"{len(unresolved)} provider player name(s) could not be "
                    "resolved to a fitted player; they produced no selection. "
                    "A fuzzy match would produce a confident price for a bet "
                    "nobody placed."
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
            probabilities.update(price_team_markets(prices, team_model))
        except (KeyError, ValueError) as exc:
            blockers.append(f"The team model could not be fitted: {exc}")

    card = build_card(
        prices,
        probabilities,
        eligibility=eligibility,
        blockers=blockers,
        now=moment,
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
