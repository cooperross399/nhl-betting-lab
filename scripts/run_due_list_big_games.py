#!/usr/bin/env python3
"""Big games on the Due List: 2-goal games, hat tricks and shutouts, measured.

Cooper asked on 2026-11-04: "Would it be possible for us to work shutouts/2
goal games/hat tricks into the due list for the really elite
goalscorers/goalies". This measures, on the two bought seasons, what a drought
of each says:

1. **2+ goals and 3+ goals** (skaters). Per qualifier (last season's goals at
   or above a floor) and drought bar (straight regular-season games dressed
   without one), the hit rate against the player's own prior-season rate, and,
   where a book priced it, the best `card`-window goals over 1.5 / over 2.5
   (one wager per selection, strictly before face-off), ROI with a 95%
   interval bootstrapped over game nights, per season. The control is the same
   players at a drought below every bar.
2. **Shutouts** (goalies). Per qualifier (last season's shutouts) and drought
   (straight starts without one), the shutout rate against his own prior
   rate. No book in the bought store prices a shutout, so there is no ROI.

A shutout here is a start (`START_SECONDS` of ice time or more) with no goal
against and 59 minutes or more played; shootout goals are not goals against.

With `--history FIRST` (Cooper, 2026-11-04: "test as many seasons as you
can") it also reads the NHL's free game logs from season FIRST onward for
every player who could qualify (30+ goals or 2+ shutouts the season before)
and writes the rates, no prices, to `data/outputs/due_list_big_games_history.md`:
the sweep pooled over every season, and each season alone at the shipped
setting. Prices exist only for the two bought seasons, so the history says
whether a drought makes the event likelier, never whether a price pays.

Every figure is an aggregate. It records nothing the card reads and spends
nothing. Run where the bought prices are (Due List Tuning restores them):

    PYTHONPATH=src python scripts/run_due_list_big_games.py --data data/processed --history 2009
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nhl_betting_lab import drought_rule as dr  # noqa: E402
from nhl_betting_lab.drought_rule import BIG_GAMES, drought_before  # noqa: E402
from nhl_betting_lab.models.player_props import player_name_aliases  # noqa: E402
from nhl_betting_lab.season import game_date  # noqa: E402

START_SECONDS = 2400
FULL_GAME_SECONDS = 59 * 60
BOOTSTRAPS = 1000
EVENTS = {"two_goals": (2, 1.5), "hat_trick": (3, 2.5)}
GOAL_FLOORS = (30, 35, 40, 45, 50)
BARS = {"two_goals": (0, 5, 8, 10, 12, 15, 20, 25), "hat_trick": (0, 20, 30, 40, 50, 60, 80)}
SHUTOUT_FLOORS = (2, 3, 4, 5, 6)
SHUTOUT_BARS = (0, 10, 15, 20, 25, 30, 40)


def decimal(odds):
    odds = np.asarray(odds, dtype=float)
    return np.where(odds > 0, 1 + odds / 100, 1 + 100 / -odds)


def skater_frame(logs: pd.DataFrame) -> pd.DataFrame:
    s = logs[(logs.role == "skater") & (logs.game_type == 2)].sort_values(["player_id", "date", "game_id"]).copy()
    s["season_start"] = s.season // 10000
    for name, (k, _) in EVENTS.items():
        s[name] = (s.goals >= k).astype(int)
        s["drought_" + name] = s.groupby("player_id")[name].transform(
            lambda v: pd.Series(drought_before(v.values), index=v.index))
    per = s.groupby(["player_id", "season_start"]).agg(prior_goals=("goals", "sum"), prior_gp=("goals", "size"),
                                                       **{f"prior_{n}": (n, "sum") for n in EVENTS}).reset_index()
    per["season_start"] += 1
    return s.merge(per, on=["player_id", "season_start"], how="left")


def goalie_frame(logs: pd.DataFrame) -> pd.DataFrame:
    g = logs[(logs.role == "goalie") & (logs.game_type == 2)].copy()
    g["toi"] = pd.to_numeric(g.toi_seconds, errors="coerce")
    g = g[g.toi >= START_SECONDS].sort_values(["player_id", "date", "game_id"]).copy()
    g["season_start"] = g.season // 10000
    g["shutout"] = ((pd.to_numeric(g.goals_against, errors="coerce") == 0) & (g.toi >= FULL_GAME_SECONDS)).astype(int)
    g["drought"] = g.groupby("player_id").shutout.transform(lambda v: pd.Series(drought_before(v.values), index=v.index))
    per = g.groupby(["player_id", "season_start"]).agg(prior_so=("shutout", "sum"), prior_starts=("shutout", "size")).reset_index()
    per["season_start"] += 1
    return g.merge(per, on=["player_id", "season_start"], how="left")


def priced(prices: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
    """Best card-window over 1.5 / over 2.5 per (event, player), joined to the skater game it settles on."""
    p = prices[(prices.market == "goals") & (prices.selection == "over") & prices.line.isin([1.5, 2.5])].copy()
    if p.empty:
        return pd.DataFrame()
    p["gdate"] = p.commence_time.map(game_date)
    p = p[pd.to_datetime(p.snapshot) < pd.to_datetime(p.commence_time)]
    first = p.groupby("provider_event_id").snapshot.transform("min")
    p = p[p.snapshot == first]
    p["dec"] = decimal(p.american_odds)
    best = p.sort_values("dec").groupby(["provider_event_id", "player", "line"]).tail(1)
    keys: dict[tuple[str, str], set] = {}
    for r in s[["player_id", "player", "date"]].drop_duplicates().itertuples():
        for alias in player_name_aliases(r.player):
            keys.setdefault((alias, r.date), set()).add(r.player_id)
    idx = s.drop_duplicates(["player_id", "date"]).set_index(["player_id", "date"])
    rows = []
    for r in best.itertuples():
        ids = set().union(*(keys.get((a, r.gdate), set()) for a in player_name_aliases(r.player)))
        if len(ids) != 1:
            continue
        g = idx.loc[(next(iter(ids)), r.gdate)]
        event = "two_goals" if r.line == 1.5 else "hat_trick"
        won = bool(g.goals >= EVENTS[event][0])
        rows.append({"event": event, "date": r.gdate, "season": int(g.season_start), "player_id": next(iter(ids)),
                     "odds": float(r.american_odds), "dec": float(r.dec), "won": won,
                     "profit": float(r.dec - 1) if won else -1.0, "prior_goals": g.prior_goals,
                     "drought": int(g["drought_" + event])})
    return pd.DataFrame(rows)


def roi(x: pd.DataFrame, seed: int) -> dict | None:
    if x.empty:
        return None
    nights = x.groupby("date").profit.agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(nights), size=(BOOTSTRAPS, len(nights)))
    s, n = nights["sum"].to_numpy(), nights["count"].to_numpy()
    boot = s[i].sum(1) / n[i].sum(1)
    return {"n": int(len(x)), "hit": float(x.won.mean()), "implied": float((1 / x.dec).mean()),
            "median_odds": int(x.odds.median()), "roi": float(x.profit.mean()), "units": float(x.profit.sum()),
            "lo": float(np.percentile(boot, 2.5)), "hi": float(np.percentile(boot, 97.5))}


def pct(v):
    return f"{v * 100:+.1f}%"


def roi_cell(r):
    return "—" if r is None else f"{pct(r['roi'])} / {r['n']}"


def render_skaters(s: pd.DataFrame, w: pd.DataFrame) -> list[str]:
    L = []
    for event, (k, line) in EVENTS.items():
        L += [f"## {k}+ goals (over {line})", "",
              "Rate: the share of games entered at that drought with the event. Own rate: his prior-season share. "
              f"Priced: the best `card`-window over {line}, one per selection.", "",
              "| Last season goals | Drought bar | Games | Rate | Own rate | Priced | Hit | Implied | Median odds | ROI | 95% interval | 2024-25 | 2025-26 |",
              "|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|--:|--:|"]
        for floor in GOAL_FLOORS:
            q = s[s.prior_goals >= floor]
            pw = w[(w.event == event) & (w.prior_goals >= floor)] if len(w) else w
            for bar in BARS[event]:
                x = q[q["drought_" + event] >= bar]
                own = (x["prior_" + event] / x.prior_gp).mean() if len(x) else float("nan")
                px = pw[pw.drought >= bar] if len(pw) else pw
                seed = zlib.crc32(repr((event, floor, bar)).encode())
                r = roi(px, seed) if len(px) else None
                s1 = roi(px[px.season == 2024], seed + 1) if len(px) else None
                s2 = roi(px[px.season == 2025], seed + 2) if len(px) else None
                body = (f"{r['n']} | {r['hit']*100:.1f}% | {r['implied']*100:.1f}% | {r['median_odds']:+d} | {pct(r['roi'])} | "
                        f"{pct(r['lo'])} .. {pct(r['hi'])} | {roi_cell(s1)} | {roi_cell(s2)}") if r else "0 | — | — | — | — | — | — | —"
                L.append(f"| {floor}+ | {bar} | {len(x)} | {x[event].mean()*100 if len(x) else float('nan'):.1f}% | "
                         f"{own*100:.1f}% | {body} |")
        L.append("")
    return L


def render_goalies(g: pd.DataFrame) -> list[str]:
    L = ["## Shutouts (goalies)", "",
         "Starts entered at that drought, the share that were shutouts, his own prior-season shutout rate per start. "
         "No book in the bought store prices a shutout.", "",
         "| Last season shutouts | Drought bar (starts) | Starts | Shutout rate | Own rate | 2024-25 | 2025-26 |",
         "|--:|--:|--:|--:|--:|--:|--:|"]
    for floor in SHUTOUT_FLOORS:
        q = g[g.prior_so >= floor]
        for bar in SHUTOUT_BARS:
            x = q[q.drought >= bar]
            own = (x.prior_so / x.prior_starts).mean() if len(x) else float("nan")
            by = [x[x.season_start == y] for y in (2024, 2025)]
            cells = [f"{b.shutout.mean()*100:.1f}% / {len(b)}" if len(b) else "—" for b in by]
            L.append(f"| {floor}+ | {bar} | {len(x)} | {x.shutout.mean()*100 if len(x) else float('nan'):.1f}% | "
                     f"{own*100:.1f}% | {cells[0]} | {cells[1]} |")
    return L + [""]


STATS = "https://api.nhle.com/stats/rest/en/{role}/summary"
GAME_LOG = "https://api-web.nhle.com/v1/player/{pid}/game-log/{season}/2"
HEADERS = {"User-Agent": "nhl-betting-lab (due list research)"}


def _get(url: str, params: dict | None, cache: Path) -> dict:
    if cache.exists():
        return json.loads(cache.read_text())
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                data = r.json()
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data))
                return data
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"{url} {params}: {last}")


def _seconds(toi) -> float:
    if isinstance(toi, (int, float)):
        return float(toi)
    try:
        m, sec = str(toi).split(":")
        return int(m) * 60 + int(sec)
    except ValueError:
        return float("nan")


def season_qualifiers(season: int, role: str, cache: Path) -> dict[int, str]:
    """Players with 30+ goals (skaters) or 2+ shutouts (goalies) in a regular season."""
    field, floor = ("goals", min(GOAL_FLOORS)) if role == "skater" else ("shutouts", min(SHUTOUT_FLOORS))
    out, start = {}, 0
    while True:
        params = {"isAggregate": "true", "isGame": "false", "start": start, "limit": 100,
                  "cayenneExp": f"seasonId={season} and gameTypeId=2 and {field}>={floor}"}
        data = _get(STATS.format(role=role), params, cache / f"{role}_{season}_{start}.json")
        rows = data.get("data", [])
        for r in rows:
            out[int(r["playerId"])] = r.get("skaterFullName") or r.get("goalieFullName") or ""
        start += len(rows)
        if not rows or start >= int(data.get("total", 0)):
            return out


def history_logs(first: int, last: int, cache: Path) -> pd.DataFrame:
    """Game logs for the seasons around every potential qualifier, in the lab's log schema."""
    want: dict[tuple[int, int], str] = {}
    for start_year in range(first, last + 1):
        season = start_year * 10000 + start_year + 1
        for role in ("skater", "goalie"):
            for pid in season_qualifiers(season, role, cache):
                for s in (season, season + 10001):
                    want[(pid, s)] = role
    rows = []
    for (pid, season), role in sorted(want.items()):
        data = _get(GAME_LOG.format(pid=pid, season=season), None, cache / "log" / f"{pid}_{season}.json")
        for g in data.get("gameLog", []):
            rows.append({"game_id": g.get("gameId"), "season": season, "game_type": 2, "date": g.get("gameDate"),
                         "player_id": pid, "role": role, "goals": g.get("goals", 0) if role == "skater" else 0,
                         "toi_seconds": _seconds(g.get("toi")),
                         "goals_against": g.get("goalsAgainst") if role == "goalie" else np.nan})
    return pd.DataFrame(rows)


def render_history(s: pd.DataFrame, g: pd.DataFrame, first: int, last: int) -> list[str]:
    seasons = sorted(set(s.season_start.dropna().astype(int)) | set(g.season_start.dropna().astype(int)))
    L = ["# Due List big games across every season the NHL's logs reach", "",
         f"Seasons {first + 1}-{str(first + 2)[2:]} to {last + 1}-{str(last + 2)[2:]} (each player qualifies on the "
         "season before). Rates only: no prices exist before 2024-25. Rate is the share of games entered at that "
         "drought with the event; own rate is that player's share the season before. A drought makes the event "
         "likelier only where the rate beats the own rate. Short seasons (2012-13, 2019-20, 2020-21) are counted "
         "on raw goals, so fewer players qualify in them.", ""]
    for event, (k, _) in EVENTS.items():
        L += [f"## {k}+ goals, pooled", "", "| Last season goals | Drought bar | Games | Rate | Own rate | Rate / own |",
              "|--:|--:|--:|--:|--:|--:|"]
        for floor in GOAL_FLOORS:
            q = s[s.prior_goals >= floor]
            for bar in BARS[event]:
                x = q[q["drought_" + event] >= bar]
                if not len(x):
                    continue
                rate, own = x[event].mean(), (x["prior_" + event] / x.prior_gp).mean()
                L.append(f"| {floor}+ | {bar} | {len(x)} | {rate*100:.1f}% | {own*100:.1f}% | {rate/own:.2f} |")
        spec = BIG_GAMES[event]
        L += ["", f"Shipped setting ({spec['floor']}+ goals, {spec['bar']}+ games), by season:", "",
              "| Season | Games | Rate | Own rate |", "|:--|--:|--:|--:|"]
        x = s[(s.prior_goals >= spec["floor"]) & (s["drought_" + event] >= spec["bar"])]
        for y in seasons:
            b = x[x.season_start == y]
            if len(b):
                L.append(f"| {y}-{str(y + 1)[2:]} | {len(b)} | {b[event].mean()*100:.1f}% | "
                         f"{(b['prior_' + event] / b.prior_gp).mean()*100:.1f}% |")
        L.append("")
    L += ["## Shutouts, pooled", "", "| Last season shutouts | Drought bar (starts) | Starts | Rate | Own rate | Rate / own |",
          "|--:|--:|--:|--:|--:|--:|"]
    for floor in SHUTOUT_FLOORS:
        q = g[g.prior_so >= floor]
        for bar in SHUTOUT_BARS:
            x = q[q.drought >= bar]
            if not len(x):
                continue
            rate, own = x.shutout.mean(), (x.prior_so / x.prior_starts).mean()
            L.append(f"| {floor}+ | {bar} | {len(x)} | {rate*100:.1f}% | {own*100:.1f}% | {rate/own:.2f} |")
    spec = BIG_GAMES["shutout"]
    L += ["", f"Shipped setting ({spec['floor']}+ shutouts, {spec['bar']}+ starts), by season:", "",
          "| Season | Starts | Rate | Own rate |", "|:--|--:|--:|--:|"]
    x = g[(g.prior_so >= spec["floor"]) & (g.drought >= spec["bar"])]
    for y in seasons:
        b = x[x.season_start == y]
        if len(b):
            L.append(f"| {y}-{str(y + 1)[2:]} | {len(b)} | {b.shutout.mean()*100:.1f}% | "
                     f"{(b.prior_so / b.prior_starts).mean()*100:.1f}% |")
    return L + [""]


def render_status(logs: pd.DataFrame, day: str) -> list[str]:
    """Every player over a big game's floor tonight, with his current drought against the bar.

    The list's own rule with the bar set to 0, so it shows who is close as well
    as who is listed; whether he plays tonight is not checked here.
    """
    saved = {c: spec["bar"] for c, spec in BIG_GAMES.items()}
    try:
        for spec in BIG_GAMES.values():
            spec["bar"] = 0
        q = dr.big_game_qualifiers_entering(logs, day)
    finally:
        for c, bar in saved.items():
            BIG_GAMES[c]["bar"] = bar
    L = [f"# Due List big games: who is over the floor entering {day}", "",
         "Every player over the floor, his drought now and the bar he must reach to be listed.", ""]
    for c, spec in BIG_GAMES.items():
        x = q[q.market == c].sort_values("drought", ascending=False)
        L += [f"## {dr.category_label(c)} (floor {spec['floor']}, bar {saved[c]})", "",
              "| Player | Last season | Drought | Bar | Listed |", "|:--|--:|--:|--:|:--|"]
        L += [f"| {r.player} | {r.last_season} | {r.drought} | {saved[c]} | {'yes' if r.drought >= saved[c] else 'no'} |"
              for r in x.itertuples()] or ["| nobody over the floor | | | | |"]
        L.append("")
    return L


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "outputs")
    ap.add_argument("--history", type=int, default=None,
                    help="also read the NHL's game logs from this season's first year (e.g. 2009) and report rates")
    ap.add_argument("--status", default=None, help="also list who is over each floor entering this league day")
    a = ap.parse_args(argv)
    logs = pd.read_csv(a.data / "player_game_logs.csv")
    s, g = skater_frame(logs), goalie_frame(logs)
    s_m = s[s.season_start.isin([2024, 2025])]
    g_m = g[g.season_start.isin([2024, 2025])]
    prices_path = a.data / "historical_prop_prices.csv"
    w = pd.DataFrame()
    store = ""
    if prices_path.exists():
        prices = pd.read_csv(prices_path, usecols=["commence_time", "provider_event_id", "market", "player",
                                                   "selection", "line", "american_odds", "book", "snapshot"])
        goals = prices[prices.market == "goals"]
        store = ("Bought goals quotes by line (all snapshots): "
                 + ", ".join(f"{ln:g}: {n}" for ln, n in goals.line.value_counts().sort_index().items())
                 + ". Markets in the store: " + ", ".join(sorted(prices.market.astype(str).unique())) + ".")
        w = priced(prices, s)
        w = w[w.season.isin([2024, 2025])] if len(w) else w
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    L = ["# Due List big games: 2-goal games, hat tricks, shutouts", "",
         f"Generated {now} by `scripts/run_due_list_big_games.py`. Regular seasons 2024-25 and 2025-26.", "",
         store or "No bought prices on disk: rates only.", ""]
    L += render_skaters(s_m, w) + render_goalies(g_m)
    text = "\n".join(L) + "\n"
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "due_list_big_games.md").write_text(text)
    print(text)
    if a.status:
        text = "\n".join(render_status(logs, a.status)) + "\n"
        (a.out / "due_list_big_games_status.md").write_text(text)
        print(text)
    if a.history is not None:
        last = 2024
        hist = history_logs(a.history, last, ROOT / "data" / "raw" / "nhl" / "big_games_history")
        hs, hg = skater_frame(hist), goalie_frame(hist)
        span = range(a.history + 1, last + 2)
        text = "\n".join(render_history(hs[hs.season_start.isin(span)], hg[hg.season_start.isin(span)],
                                         a.history, last)) + "\n"
        (a.out / "due_list_big_games_history.md").write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
