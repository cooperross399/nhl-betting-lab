# The venue route is closed

**Measured 2026-09-02, workflow run 33629672530, 130 credits.**

## The question

The props model finishes **−0.29% over 25,947 wagers** (95% −1.5% to +0.9%,
**no demonstrated edge**). Against a direction-neutral baseline — both sides
of every two-sided market at the best price, **−5.74%** — it recovers about
5.45 points and stops a third of a point short of break-even.

*(Corrected 2026-09-02: this read "against a −2.70% null … roughly 87% of the
toll". That null was every wager with a positive model edge, a population
already 77.6% unders, so it silently contained the model's own direction. The
conclusion below is unaffected — the toll is what it is regardless of the
baseline the model is scored against.)*

Thirteen external inputs and nine feature families have failed to forecast
better. That left one arithmetically obvious route that had never been tested:
stop trying to forecast better and **pay a smaller toll**. Books charge a
median **6.92%** on a two-sided NHL prop and the cheapest of the fourteen in
the store charges 6.27%. If a venue charged materially less, the same opinions
would cross zero without a single model change.

The candidates — Pinnacle, the US exchanges Novig and ProphetX, and Betfair —
all sit outside the `us,us2` region string this lab has always asked for, so
none of them had ever been priced.

## The answer: no, twice over

One event (Anaheim at Washington, 2025-01-14, priced four hours before
face-off — a game the fourteen-book store already holds at the same instant, so
every venue is compared at the same moment). Median two-sided margin per book,
`n` two-sided in brackets:

| Book | Region | assists | goals | points | shots | saves | Median |
|---|---|---|---|---|---|---|---|
| **pinnacle** | `eu` | 7.23% [15] | — | 7.20% [15] | 7.17% [13] | 7.07% [2] | **7.18%** |
| coolbet | `eu` | 7.96% [21] | 6.89% [2] | 7.00% [31] | 7.08% [8] | — | 7.04% |
| draftkings | `us` | 6.31% [15] | — | 6.41% [15] | 6.30% [13] | — | **6.31%** |
| betonlineag | `us` | — | — | 6.37% [14] | 6.40% [13] | 6.38% [2] | 6.38% |
| bovada | `us` | — | — | — | 6.52% [13] | 6.52% [1] | 6.52% |
| fanduel | `us` | — | 6.53% [12] | **6.10%** [15] | 6.53% [14] | — | 6.53% |
| betrivers | `us` | — | — | — | 6.68% [10] | — | 6.68% |
| betmgm | `us` | 6.96% [15] | 7.11% [5] | 7.18% [15] | 7.62% [13] | 7.33% [2] | 7.18% |
| williamhill_us | `us` | — | — | — | — | 9.48% [2] | 9.48% |

**1. Pinnacle is dearer, not cheaper.** It charges **7.18%** on NHL player
props against DraftKings' 6.31% and a cheapest book-market of 6.10% — it is
**1.08 points more expensive** than the toll already being paid, and prices
like BetMGM. The reduced-juice reputation is a *main-markets* fact: on the
team-price store the same operator class runs 3.00% on the moneyline against a
4.47% field. It does not extend to props. The provider's own note on this feed
— *"odds are from public website which may incur a delay"* — fits a
recreational storefront rather than the sharp book.

**2. No exchange lists NHL player props at all.** Novig and ProphetX (`us_ex`),
Betfair (`uk`), Matchbook and Smarkets all returned the moneyline and nothing
else. The prop calls at `us_ex`, `uk` and `au` each returned **zero markets and
were billed zero credits**.

That second finding is the decisive one, and it was already visible in data the
lab owned: **LowVig.ag**, a reduced-juice book inside the current `us` region,
holds 18,102 NHL team-market rows in the store and **zero** prop rows across
two seasons. A venue that lists the moneyline and not the props offers nothing
for a props opinion to be placed against, whatever its margin.

## What this closes

The venue route was the last way to close a 0.29-point shortfall without
forecasting better. Measured where every venue can be compared at the same
instant, **the smallest toll outside `us,us2` is larger than the one already
paid**, and the venues that charge genuinely less do not sell the product.

The `us,us2` region string stays. The comment in
`providers/odds_api.py` justified it on reachability — "a price at a book
Cooper cannot open is not reachable" — which was always looser than it read,
since offshore books are already in the store. It is now justified on
measurement instead: the excluded regions were priced, and they are worse.

## One correction to scope, 2026-09-02

"No exchange lists NHL player props" is true of **this provider's feed** and
false of the world. Kalshi runs four NHL player-prop series — `KXNHLPTS`,
`KXNHLAST`, `KXNHLSAVES`, `KXNHLGOAL`, settling off NHL.com — which The Odds
API's `us_ex` region does not relay. Verified against Kalshi's public API.

It does not reopen the route, for a reason specific to its fee design. Kalshi
charges a **quadratic** fee (`fee_type: quadratic`, confirmed on the series
record), which is **maximised at a 50/50 price** — precisely where NHL props
sit. At even money the taker fee runs about 3.5% of stake, against a per-side
6.27% ÷ 2 ≈ **3.1%** at DraftKings. So as a taker the exchange is *dearer*
than the book already in use, and the sub-1% figure applies only to the maker
side — which means quoting into exactly the stale-ice-time adverse selection
that `docs/where_the_remaining_error_lives.md` identifies as this model's
largest residual error. There were no open markets to measure at the time of
writing (off-season), so spread and depth are untested.

Worth a forward look once the season opens; not a route on current evidence.

Reproduce with `scripts/probe_low_vig_venues.py` (`--list-events` prints the
cached events; the workflow is **Venue Probe**, manual dispatch, capped).
