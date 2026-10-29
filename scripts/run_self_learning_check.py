"""Walk-forward check of `self_learning`: each day priced with what the
ledger had settled before it, against the card as it was.

Bets are the wagers clearing the card's best-bet bars (12% prop, 9% team)
inside -160..+600, one per wager at the best price, flat 1u. Information
only: a few weeks of ledger cannot separate either version from zero.

    PYTHONPATH=src python scripts/run_self_learning_check.py --ledger data/processed/forward_evidence.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from nhl_betting_lab.self_learning import (
    PRIOR_STRENGTH,
    TEAM_MARKETS,
    Trust,
    adjusted,
    fit_trust,
    learnable_wagers,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, nargs="+", required=True)
    parser.add_argument("--prior", type=float, default=PRIOR_STRENGTH)
    parser.add_argument("--warmup-days", type=int, default=7)
    args = parser.parse_args(argv)
    paths = [p for given in args.ledger for p in (sorted(given.glob("*.csv")) if given.is_dir() else [given])]
    ledger = pd.concat([pd.read_csv(p, dtype={"player": str}) for p in paths], ignore_index=True)
    wagers = learnable_wagers(ledger)
    units = ledger.assign(
        player=ledger["player"].fillna(""), line=pd.to_numeric(ledger["line"], errors="coerce").fillna(-999.0)
    ).drop_duplicates(["snapshot_date", "home_team", "away_team", "market", "player", "selection", "line", "american_odds"])
    wagers = wagers.merge(
        units[["snapshot_date", "home_team", "away_team", "market", "player", "selection", "line", "american_odds", "profit_units"]],
        on=["snapshot_date", "home_team", "away_team", "market", "player", "selection", "line", "american_odds"],
        how="left",
    )
    days = sorted(wagers["snapshot_date"].astype(str).unique())
    rows = []
    for day in days[args.warmup_days:]:
        trust = fit_trust(ledger[ledger["snapshot_date"].astype(str) < day], prior=args.prior)
        today = wagers[wagers["snapshot_date"].astype(str) == day]
        for row in today.itertuples():
            implied = 1.0 / row.decimal
            learned = adjusted(row.model_probability, row.american_odds, trust.get(row.market, Trust()))
            rows.append((row.market, row.american_odds, row.model_probability - implied, learned - implied, row.profit_units))
    out = pd.DataFrame(rows, columns=["market", "odds", "raw_edge", "learned_edge", "units"])
    bar = np.where(out["market"].isin(TEAM_MARKETS), 0.09, 0.12)
    priced = (out["odds"] >= -160) & (out["odds"] <= 600)
    print(f"Days scored: {len(days) - args.warmup_days} (after {args.warmup_days} warm-up), prior {args.prior:g}")
    for name, edge in (("card as it was", "raw_edge"), ("learned", "learned_edge")):
        bets = out[(out[edge] >= bar) & priced]
        team = bets["market"].isin(TEAM_MARKETS)
        print(
            f"{name:15s} {len(bets):5d} bets  {bets['units'].sum():+7.1f}u  "
            f"ROI {100 * bets['units'].mean():+5.1f}%  | team {team.sum()} {bets[team]['units'].sum():+.1f}u"
            f"  | props {(~team).sum()} {bets[~team]['units'].sum():+.1f}u"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
