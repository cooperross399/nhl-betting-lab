"""Walk-forward check of `self_learning`: each day priced with what the
ledger had settled before it, against the card as it was.

Bets are the wagers clearing the card's best-bet bars (12% prop, 9% team)
inside -160..+600, one per wager at the best price, flat 1u. Leans are the
band below them (6% prop, 3% for a points over, 3.5% team), at 0.25u as the
site tracks them (a minus price risks what wins 0.25u). `--by-side` learns
each side of a market apart, as the card has since 2026-11-05; without it,
each market as one. Information only: a few weeks of ledger cannot
separate either version from zero.

    PYTHONPATH=src python scripts/run_self_learning_check.py --ledger data/processed/forward_evidence.csv --by-side
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
    side_key,
    side_of,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, nargs="+", required=True)
    parser.add_argument("--prior", type=float, default=PRIOR_STRENGTH)
    parser.add_argument("--warmup-days", type=int, default=7)
    parser.add_argument("--by-side", action="store_true", help="learn each side of a market apart")
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
        trust = fit_trust(ledger[ledger["snapshot_date"].astype(str) < day], prior=args.prior, by_side=args.by_side)
        today = wagers[wagers["snapshot_date"].astype(str) == day]
        for row in today.itertuples():
            implied = 1.0 / row.decimal
            side = side_of(row.market, row.selection, row.line)
            learned_trust = trust.get(side_key(row.market, side)) or trust.get(row.market, Trust())
            learned = adjusted(row.model_probability, row.american_odds, learned_trust)
            rows.append((row.market, side, row.american_odds, row.model_probability - implied, learned - implied,
                         row.profit_units, row.outcome == "won"))
    out = pd.DataFrame(rows, columns=["market", "side", "odds", "raw_edge", "learned_edge", "units", "won"])
    odds = out["odds"].astype(float)
    risk = np.where(odds > 0, 0.25, 0.25 * odds.abs() / 100.0)
    out["lean_units"] = np.where(out["won"], risk * (out["units"].clip(lower=0) / 1.0), -risk)
    out["lean_risk"] = risk
    bar = np.where(out["market"].isin(TEAM_MARKETS), 0.09, 0.12)
    priced = (out["odds"] >= -160) & (out["odds"] <= 600)
    print(f"Days scored: {len(days) - args.warmup_days} (after {args.warmup_days} warm-up), prior {args.prior:g}, "
          f"{'each side apart' if args.by_side else 'each market as one'}")
    team_rows = out["market"].isin(TEAM_MARKETS)
    lean_low = np.where(team_rows, 0.035, np.where((out["market"] == "points") & (out["side"] == "over"), 0.03, 0.06))
    for name, edge in (("card as it was", "raw_edge"), ("learned", "learned_edge")):
        bets = out[(out[edge] >= bar) & priced]
        team = bets["market"].isin(TEAM_MARKETS)
        print(
            f"{name:15s} {len(bets):5d} bets  {bets['units'].sum():+7.1f}u  "
            f"ROI {100 * bets['units'].mean():+5.1f}%  | team {team.sum()} {bets[team]['units'].sum():+.1f}u"
            f"  | props {(~team).sum()} {bets[~team]['units'].sum():+.1f}u"
        )
        leans = out[(out[edge] >= lean_low) & (out[edge] < bar) & priced]
        lt = leans["market"].isin(TEAM_MARKETS)
        for label, part in (("prop leans", leans[~lt]), ("team leans", leans[lt])):
            print(f"{'':15s} {label}: {len(part)}, {part['won'].sum()}-{(~part['won']).sum()}, "
                  f"{part['lean_units'].sum():+.2f}u at 0.25u")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
