#!/usr/bin/env python3
"""Does the favourite, home ice and tonight's two teams make better saves bets?

Cooper asked on 2026-10-20 to "re-evaluate and fine-tune the goalie saves
portion of the model. Factor in the team that is favored to win and home ice
advantage." This measures that, walk-forward, before anything ships.

**Decision rule, fixed before the first run.** A context variant replaces the
card's saves mean only if BOTH hold:

1. Out of sample, its negative-binomial log-likelihood on actual saves beats
   the current model's, the paired per-start difference's 95% interval
   (clustered on the game) excluding zero, over every scored start.
2. On the bought goalie-saves prices, at the card's prop bar, it does not
   finish behind the current model in units in the `late` window (the
   largest), and not in the `card` window either. Must-not-lose, the bar the
   back-to-back adjustments shipped on; the price sample is too thin to ask
   for a demonstrated edge, and no variant is claimed to have one.

Among variants passing both, the one with the best log-likelihood ships.

How each start is scored. The current model's walk-forward mean
(`generate_prop_samples`, the back-to-back policy in force) is the baseline.
Each variant is a Poisson recalibration of that mean on context features
(`saves_context.FEATURES`), its coefficients fitted only on starts in earlier
refit windows, and its dispersion refitted on those starts' residuals. A
start is scored only once 800 earlier starts carry the market's moneyline;
before that every variant is the baseline. Market win chances come from the
bought team prices (2024-25 and 2025-26), so those are the scored seasons.

Writes `data/outputs/saves_model_study.md` and `.json`: aggregates only, no
price, line or book. Offline; spends nothing.

    PYTHONPATH=src .venv/bin/python scripts/run_saves_model_study.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import gammaln

from nhl_betting_lab import verdicts
from nhl_betting_lab.backtest.walk_forward import (
    GOALIE_START_SECONDS,
    generate_prop_samples,
)
from nhl_betting_lab.config import MIN_PROP_EDGE, OUTPUTS_DIR, PROCESSED_DIR
from nhl_betting_lab.data.build_datasets import load_player_logs, load_team_games
from nhl_betting_lab.models import saves_context as sc
from nhl_betting_lab.providers.team_names import (
    UnresolvedTeamsError,
    load_team_name_map,
    normalize_team_name,
)
from nhl_betting_lab.reports.player_props_backtest import run_backtest
from nhl_betting_lab.stats import clustered_mean_interval

REPORT_MARKDOWN = "saves_model_study.md"
REPORT_JSON = "saves_model_study.json"
REFIT_DAYS = 14
MIN_TRAINING = 800

VARIANTS: dict[str, tuple[str, ...]] = {
    "B_recalibrated": ("log_base",),
    "C_home": ("log_base", "home"),
    "D_favourite": ("log_base", "logit_win"),
    "E_favourite_home": ("log_base", "home", "logit_win"),
    "F_full_context": (
        "log_base", "home", "logit_win", "log_team_sa", "log_opp_sf",
        "log_arena", "log_toi_ratio",
    ),
    "G_context_no_market": (
        "log_base", "home", "log_team_sa", "log_opp_sf", "log_arena",
        "log_toi_ratio",
    ),
}


def nb_loglik(y: np.ndarray, mu: np.ndarray, r: np.ndarray) -> np.ndarray:
    mu = np.maximum(mu, 1e-9)
    out = np.empty_like(mu)
    poisson = ~np.isfinite(r)
    out[poisson] = y[poisson] * np.log(mu[poisson]) - mu[poisson] - gammaln(y[poisson] + 1)
    nb = ~poisson
    rr = r[nb]
    p = rr / (rr + mu[nb])
    out[nb] = (
        gammaln(y[nb] + rr) - gammaln(rr) - gammaln(y[nb] + 1)
        + rr * np.log(p) + y[nb] * np.log1p(-p)
    )
    return out


def _resolver(team_names: dict[str, str]):
    class _R(dict):
        def get(self, name, default=None):  # noqa: D401
            return team_names.get(normalize_team_name(name), default)
    return _R()


def build_features(samples, logs, games, win_probs):
    """Context features per sample, from data before its refit window."""
    dates = pd.to_datetime(logs["date"].astype(str).str[:10], errors="coerce").dt.date
    first = dates.min()
    games = games.copy()
    games["_d"] = pd.to_datetime(games["date"].astype(str).str[:10], errors="coerce").dt.date
    goalie = logs[logs["role"].astype(str) == "goalie"].copy()
    goalie["_d"] = pd.to_datetime(goalie["date"].astype(str).str[:10], errors="coerce").dt.date
    goalie["toi_seconds"] = pd.to_numeric(goalie["toi_seconds"], errors="coerce").fillna(0)

    sample_dates = pd.to_datetime(samples["date"], errors="coerce").dt.date
    window = [((d - first).days // REFIT_DAYS) for d in sample_dates]
    cache: dict[int, tuple] = {}
    rows = []
    for i, row in enumerate(samples.itertuples()):
        k = window[i]
        if k not in cache:
            cutoff = first + timedelta(days=k * REFIT_DAYS)
            rates = sc.team_shot_rates(games[games["_d"] < cutoff])
            starts = goalie[(goalie["_d"] < cutoff) & (goalie["toi_seconds"] >= GOALIE_START_SECONDS)]
            start_toi = float(starts["toi_seconds"].mean()) if len(starts) else 3600.0
            cache[k] = (rates, start_toi)
        rates, start_toi = cache[k]
        team, opp, venue = str(row.team), str(row.opponent), str(row.venue)
        home, away = (team, opp) if venue == "home" else (opp, team)
        p_home = win_probs.get((str(row.date)[:10], home, away))
        p_team = None if p_home is None else (p_home if venue == "home" else 1 - p_home)
        exp_toi = float(row.expected_toi_seconds or 0) or start_toi
        f = sc.feature_row(
            base_mean=float(row.mean), venue=venue, win_probability=p_team,
            team=team, opponent=opp, rates=rates, toi_ratio=start_toi / exp_toi,
        )
        f["has_market"] = p_team is not None
        f["window"] = k
        rows.append(f)
    return pd.DataFrame(rows, index=samples.index)


def walk_forward_variants(samples, feats):
    y = samples["actual"].to_numpy(float)
    base_mu = samples["mean"].to_numpy(float)
    base_r = samples["dispersion_r"].to_numpy(float)
    eligible = feats["has_market"].to_numpy(bool)
    windows = feats["window"].to_numpy(int)
    preds = {name: (base_mu.copy(), base_r.copy()) for name in ["A_current", "A_r_refit", *VARIANTS]}
    scored = np.zeros(len(y), bool)
    final = {}
    for k in sorted(set(windows[eligible])):
        train = eligible & (windows < k)
        test = eligible & (windows == k)
        if train.sum() < MIN_TRAINING or not test.any():
            continue
        scored |= test
        r_base = sc.residual_dispersion(y[train], base_mu[train])
        preds["A_r_refit"][1][test] = r_base if r_base else np.inf
        for name, cols in VARIANTS.items():
            X = np.column_stack([np.ones(train.sum())] + [feats.loc[train, c].to_numpy(float) for c in cols])
            beta = sc.fit_poisson(X, y[train])
            fitted = np.exp(np.clip(X @ beta, -10, 10))
            r = sc.residual_dispersion(y[train], fitted)
            Xt = np.column_stack([np.ones(test.sum())] + [feats.loc[test, c].to_numpy(float) for c in cols])
            preds[name][0][test] = np.exp(np.clip(Xt @ beta, -10, 10))
            preds[name][1][test] = r if r else np.inf
    # Coefficients on every eligible start: what the card would ship.
    for name, cols in VARIANTS.items():
        X = np.column_stack([np.ones(eligible.sum())] + [feats.loc[eligible, c].to_numpy(float) for c in cols])
        beta = sc.fit_poisson(X, y[eligible])
        fitted = np.exp(np.clip(X @ beta, -10, 10))
        final[name] = {
            "intercept": float(beta[0]),
            "coefficients": {c: float(b) for c, b in zip(cols, beta[1:])},
            "dispersion_r": sc.residual_dispersion(y[eligible], fitted),
            "starts": int(eligible.sum()),
        }
    final["A_r_refit"] = {"dispersion_r": sc.residual_dispersion(y[eligible], base_mu[eligible])}
    return preds, scored, final


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--edge-threshold", type=float, default=MIN_PROP_EDGE)
    args = parser.parse_args(argv)
    processed, outputs = Path(args.processed_dir), Path(args.output_dir)

    logs = load_player_logs(processed)
    games = load_team_games(processed)
    prop_path = processed / "historical_prop_prices.csv"
    team_path = processed / "historical_team_prices.csv"
    if logs.empty or games.empty or not prop_path.is_file() or not team_path.is_file():
        print("Need player logs, team games and both bought price files.", file=sys.stderr)
        return 1
    team_names = load_team_name_map(processed_dir=processed)
    team_prices = pd.read_csv(team_path)
    win_probs = sc.home_win_probabilities(team_prices, _resolver(team_names))
    print(f"Market win chances for {len(win_probs):,} games.")

    use_rest = verdicts.ships("props_b2b", output_dir=outputs)
    samples, walk = generate_prop_samples(
        logs, lines={"goalie_saves": (24.5,)}, use_rest=use_rest
    )
    samples = samples[samples["market"] == "goalie_saves"].reset_index(drop=True)
    print(f"Walk-forward: {walk.summary_line()} Goalie starts: {len(samples):,}.")
    feats = build_features(samples, logs, games, win_probs)
    print(f"Starts with a market win chance: {int(feats['has_market'].sum()):,}.")
    preds, scored, final = walk_forward_variants(samples, feats)
    y = samples["actual"].to_numpy(float)
    games_id = samples["game_id"].to_numpy()
    seasons = samples["date"].astype(str).map(
        lambda d: f"{int(d[:4]) - (int(d[5:7]) < 8)}-{str(int(d[:4]) - (int(d[5:7]) < 8) + 1)[2:]}"
    ).to_numpy()

    base_ll = nb_loglik(y, *preds["A_current"])
    outcome = {}
    for name, (mu, r) in preds.items():
        ll = nb_loglik(y, mu, r)
        diff = (ll - base_ll)[scored]
        ci = clustered_mean_interval(diff.tolist(), games_id[scored].tolist())
        by_season = {}
        for s in sorted(set(seasons[scored])):
            m = scored & (seasons == s)
            c = clustered_mean_interval((ll - base_ll)[m].tolist(), games_id[m].tolist())
            by_season[s] = {"starts": int(m.sum()), "delta": c.roi, "low": c.low, "high": c.high}
        outcome[name] = {
            "starts": int(scored.sum()),
            "loglik": float(ll[scored].mean()),
            "delta": ci.roi, "low": ci.low, "high": ci.high,
            "mae": float(np.abs(y - mu)[scored].mean()),
            "bias": float((mu - y)[scored].mean()),
            "by_season": by_season,
        }

    # Favourite / home splits of the error, current model vs E.
    fav = feats["logit_win"].to_numpy(float) > 0
    home = feats["home"].to_numpy(float) > 0
    splits = {}
    for label, mask in (
        ("favourite", fav), ("underdog", ~fav), ("home", home), ("away", ~home),
        ("heavy favourite (>=65%)", feats["logit_win"].to_numpy(float) >= sc.logit(0.65)),
        ("big underdog (<=35%)", feats["logit_win"].to_numpy(float) <= sc.logit(0.35)),
    ):
        m = scored & mask
        splits[label] = {
            "starts": int(m.sum()),
            "actual": float(y[m].mean()) if m.any() else None,
            "current": float(preds["A_current"][0][m].mean()) if m.any() else None,
            "E_favourite_home": float(preds["E_favourite_home"][0][m].mean()) if m.any() else None,
            "F_full_context": float(preds["F_full_context"][0][m].mean()) if m.any() else None,
        }

    prop_prices = pd.read_csv(prop_path)
    prop_prices = prop_prices[prop_prices["market"].astype(str) == "goalie_saves"]
    prices_result = {}
    for name, (mu, r) in preds.items():
        variant = samples.copy()
        variant["mean"] = mu
        variant["dispersion_r"] = np.where(np.isfinite(r), r, np.nan)
        prices_result[name] = {}
        for phase in ("late", "card"):
            try:
                report = run_backtest(
                    prop_prices, variant, edge_threshold=args.edge_threshold,
                    phase=phase, team_names=team_names,
                )
                every = run_backtest(
                    prop_prices, variant, edge_threshold=-1.0,
                    phase=phase, team_names=team_names,
                )
            except UnresolvedTeamsError as error:
                print(f"::error::{error}", file=sys.stderr)
                return 2
            o = report.overall
            bets = [b for b in every.bets if not b.push]
            ll = [
                math.log(max(1e-9, b.model_probability if b.won else 1 - b.model_probability))
                for b in bets
            ]
            prices_result[name][phase] = {
                "bets": o.bets if o else 0,
                "profit": o.profit if o else 0.0,
                "roi": o.roi if o else 0.0,
                "low": o.low if o else 0.0,
                "high": o.high if o else 0.0,
                "priced_outcomes": len(bets),
                "logloss_all_priced": -float(np.mean(ll)) if ll else None,
            }

    passing = []
    for name in ["A_r_refit", *VARIANTS]:
        o = outcome[name]
        p = prices_result[name]
        ok_outcome = o["low"] > 0
        ok_price = all(
            p[ph]["profit"] >= prices_result["A_current"][ph]["profit"] - 1e-9
            for ph in ("late", "card")
        )
        if ok_outcome and ok_price:
            passing.append(name)
    winner = max(passing, key=lambda n: outcome[n]["loglik"]) if passing else None

    payload = {
        "use_rest": use_rest,
        "edge_threshold": args.edge_threshold,
        "min_training": MIN_TRAINING,
        "outcome": outcome,
        "splits": splits,
        "prices": prices_result,
        "final_fits": final,
        "passing": passing,
        "winner": winner,
    }
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_JSON).write_text(json.dumps(payload, indent=2, sort_keys=True, default=float) + "\n")

    lines = [
        "# Goalie saves: does game context make a better projection?",
        "",
        f"Scored starts: {int(scored.sum()):,} (walk-forward, each variant fitted only on earlier windows).",
        "",
        "## Outcomes (log-likelihood per start vs the current model)",
        "",
        "| Variant | Starts | Δ loglik [95%] | MAE | Bias |",
        "|:--|--:|:--|--:|--:|",
    ]
    for name, o in outcome.items():
        lines.append(
            f"| {name} | {o['starts']:,} | {o['delta']:+.4f} [{o['low']:+.4f}, {o['high']:+.4f}] "
            f"| {o['mae']:.3f} | {o['bias']:+.3f} |"
        )
    lines += ["", "By season:", ""]
    for name, o in outcome.items():
        lines.append(f"- {name}: " + "; ".join(
            f"{s} {v['delta']:+.4f} [{v['low']:+.4f}, {v['high']:+.4f}] over {v['starts']:,}"
            for s, v in o["by_season"].items()))
    lines += ["", "## Where the current model misses (mean saves)", "",
              "| Split | Starts | Actual | Current | E | F |", "|:--|--:|--:|--:|--:|--:|"]
    for label, s in splits.items():
        if s["starts"]:
            lines.append(f"| {label} | {s['starts']:,} | {s['actual']:.2f} | {s['current']:.2f} | "
                         f"{s['E_favourite_home']:.2f} | {s['F_full_context']:.2f} |")
    lines += ["", "## Bought goalie-saves prices (card's prop bar, one bet per wager)", "",
              "| Variant | late | card | log loss, every priced outcome (late / card) |",
              "|:--|:--|:--|:--|"]
    for name, p in prices_result.items():
        cell = lambda q: f"{q['profit']:+.1f}u over {q['bets']:,}, {q['roi']:+.2%} [{q['low']:+.2%}, {q['high']:+.2%}]"
        ll = " / ".join(
            f"{p[ph]['logloss_all_priced']:.4f} ({p[ph]['priced_outcomes']:,})" if p[ph]["logloss_all_priced"] else "-"
            for ph in ("late", "card"))
        lines.append(f"| {name} | {cell(p['late'])} | {cell(p['card'])} | {ll} |")
    lines += ["", "## Coefficients on every eligible start", ""]
    for name, f in final.items():
        lines.append(f"- {name}: `{json.dumps(f, default=float)}`")
    lines += ["", "## Verdict", "",
              f"Passing both tests: {', '.join(passing) or 'none'}. Ships: {winner or 'nothing'}.", ""]
    text = "\n".join(lines)
    (outputs / REPORT_MARKDOWN).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
