# Where every number comes from, and what it cannot tell us

## The official NHL API — `api-web.nhle.com`

The primary source. Public, keyless, no quota. Everything the models are fitted
on comes from here.

| What | Endpoint | Cached at |
|:-----|:---------|:----------|
| Day's schedule | `/v1/schedule/{YYYY-MM-DD}` | `data/raw/nhl/schedule/{date}.json` |
| Club season schedule | `/v1/club-schedule-season/{TEAM}/{seasonId}` | `data/raw/nhl/club_schedule/{team}_{season}.json` |
| Boxscore | `/v1/gamecenter/{gameId}/boxscore` | `data/raw/nhl/boxscore/{gameId}.json` |

The boxscore carries, per player: `sog`, `goals`, `assists`, `points`,
`blockedShots`, `hits`, `toi`, `powerPlayGoals`, and for goalies
`saveShotsAgainst` in `"saves/shots"` form. That is every settlement column the
priced prop markets need.

**Caching is not an optimisation, it is a correctness rule.** A completed game's
boxscore never changes, so it is fetched once and never again. Refetching would
mean the dataset silently depends on when it was built.

## The NHL stats API — `api.nhle.com/stats/rest`

Used for **one thing**: the player registry that maps `playerId` to a full
name. The boxscore abbreviates first names (`"S. Noesen"`), and the odds
provider spells them out (`"Stefan Noesen"`), so a join needs the full form.

It is deliberately **not** used as a model input. Its per-player endpoints
return season-to-date totals with no as-of date, so feeding them into a
walk-forward fit would leak the rest of the season into a game being priced.
Names cannot leak anything.

## Power-play deployment: what we have and what we do not

Power-play time on ice is the single input this model most wants and does not
have per game. The boxscore does not carry it. The stats API carries it as a
season total, which cannot be used walk-forward without leakage.

So the model uses a **leak-free proxy**: a rolling share of the player's
recent power-play *goals* against his team's, computed from per-game boxscore
data only. Power-play goals is what the boxscore actually carries — not PP
assists, not PP points, not PP time. It is a much noisier deployment signal
than PP TOI would be, especially for a defenceman who quarterbacks a unit and
rarely finishes, and this is stated in every report that depends on it rather
than quietly assumed away.

There is deliberately no `power_play_points` column in the processed logs.
Naming a goals count "points" would be a lie the model would inherit and every
downstream report would repeat.

If per-game PP TOI becomes reachable without leakage, it replaces the proxy and
the change is judged by the backtest, not by whether it looks more principled.

## MoneyPuck — deliberately not used

MoneyPuck's public CSVs would be a good shot-quality and xG source. Fetching
them programmatically returns a data-licence notice asking scrapers to arrange
a licence first:

> "it looks like you're using MoneyPuck to scrape data … Please reach out to us
> … to get a data license agreement"

So this repository does not scrape them. If Cooper obtains a licence, the
adapter goes in `src/nhl_betting_lab/data/moneypuck.py` and this section is
rewritten. Until then, no xG source is used and no report claims one.

## The Odds API — prices only

Sport key `icehockey_nhl`. The only source of prices, and the only source that
costs anything. It is never a source of results: settlement always comes from
the NHL boxscore, so a provider outage can never change what a bet did.

Prop market keys the provider prices for the NHL:

| Provider key | What this lab calls it | Settles on |
|:-------------|:-----------------------|:-----------|
| `player_shots_on_goal` | `shots_on_goal` | boxscore `sog` |
| `player_points` | `points` | boxscore `points` |
| `player_goals` | `goals` | boxscore `goals` |
| `player_assists` | `assists` | boxscore `assists` |
| `player_total_saves` | `goalie_saves` | boxscore `saveShotsAgainst` numerator |
| `player_blocked_shots` | `blocked_shots` | boxscore `blockedShots` |
| `player_hits` | `hits` | boxscore `hits` — live only; see below |

Anytime goal scorer is priced by the provider as `player_goals` at the 0.5 line
(and by some books as a dedicated market); this lab treats it as `goals` over
0.5 and says so, rather than maintaining two names for one thing.

Team market keys: `h2h` (moneyline), `spreads` (puck line), `totals`, and
`h2h_3_way` (the regulation result, draw included). The alternate ladders
`alternate_spreads` and `alternate_totals` are **per-event only** — asking for
them on the bulk endpoint makes the provider refuse the entire request.

**Hits is priced live and not retained historically.** A purchase requested
`player_hits` across 256 events spanning both sampled seasons and got zero
rows back from every book — this time measured well past the probe floor, not
concluded from one event. So hits can appear on a future card once approved,
but it can never be backtested against past prices; its evidence will have to
accumulate forward, one game-day at a time, like BTTS did in the EPL lab.

Markets probed and deliberately not priced, with the reason:

| Provider key | Why not |
|:-------------|:--------|
| `player_power_play_points` | the boxscore has PP goals, not PP assists — nothing here can settle it |
| `player_faceoffs_won` | the boxscore has a win percentage, not counts |
| `player_goal_scorer_first` / `_last` | ordering, not a rate this model measures |
| `h2h_p1`..`totals_p3` | need period scores the stored boxscore does not keep |
| `player_penalty_minutes`, `player_time_on_ice`, `player_giveaways`, `player_takeaways` | not markets the provider serves at all (422 by name) |

**Coverage is checked per bookmaker, including alternate lines, before any
market is called unavailable.** See the `total_2_5` lesson in `CLAUDE.md`.
