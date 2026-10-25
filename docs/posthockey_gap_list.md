# PostHockey against this lab: what it does, what we took, what still differs

Read 2026-10-25 from posthockey.com (Glossary & Methods, the Writeups tab,
the changelog, About, and the live game pages and their public endpoint).
Cooper asked for the gaps to be wired into the card; the earlier pass
(2026-10-08, `shadow/`) took the glossary's shot model and talent filter.

## What PostHockey's model is

| Piece | How PostHockey builds it | In this lab |
|:--|:--|:--|
| Expected goals | Logistic fit on every Fenwick shot: distance and signed angle, a 26-column distance-by-angle spline, shot type, strength, prior-event context; two eras (pre-chip, chip from 2023-24); a season scoring-environment term E | Context xG (`shadow/xg.py`), one era, no E term |
| Shooter and goalie talent | Bayesian walk updated shot by shot; age drift at season boundaries (full for goalies, half for shooters); re-centred each season | Same walk (`shadow/talent.py`); no age drift, no re-centring |
| Team xGF/xGA | Shooter-adjusted on both sides | Same, on the card since 2026-10-22 |
| Score and venue adjustment | Each attempt weighted by score state, venue and strength, weights fitted per season with team strength controlled | **Not built.** Ratings are venue-adjusted only |
| Goaltending | GSAx(sh); a season forecast per goalie (decayed history, age spline, an unseen goalie starts at -1.40 goals per 1,000 shots) | Tonight's listed starter's own GSAx(sh), regressed toward an unseen goalie's 1.02 (since 2026-10-25); no age spline yet |
| Player value | Net Rating (Luszczyszyn game score split into offence and defence, per 84) and Estimated Net Rating (Marcel-style, aged, bucket-shrunk, updated game by game) | **Not built.** Posted lines move attack by the points share of missing regulars |
| Game probability | The expected roster's Estimated Net Rating, the listed goalies' forecasts, home ice and back-to-backs, as P(home wins), with a calibration record per bucket | **Now blended into the card** (below) |
| Team ratings | Pythagorean and xW%, SRS, Massey (home 0.288 goals), Elo (K 8, home 25, carry 0.65), Colley, Keener, Markov, OD | Not used; the Poisson team model stands |
| Playoffs | Strength gap shrunk to 0.479 in playoff games | Not relevant until April |
| Microstats and badges | Contact %, rebounds over expected, FO value, burst speed, A3Z tracking (patrons only), badges, iWPA, implied purpose, linemates | Not on the card: none prices a market this lab bets, or the data is licensed |

## What went on the card (2026-10-25)

PostHockey's pre-game win probability (`posthockey.py`,
`scripts/fetch_posthockey_pregame.py`). Gameday Refresh records it for every
game not yet started, before the card and again at the pre-game update, and
`TeamModel` moves goals between the sides, the total held, until its
moneyline is half way from its own number to PostHockey's. The puck line and
team totals follow; game totals do not move. That one number carries the
three things above this lab lacked: the dressed lineup's player ratings, the
listed starting goalies, and PostHockey's own calibration. The weight (0.5)
is this lab's choice, made before any price was read.

## Still different, and why

* **Score-state adjustment** of the xG ratings: needs the play-by-play
  pipeline to carry score state per attempt; the blend covers part of it,
  since PostHockey's lineup ratings are built on adjusted inputs.
* **A lineup model of our own** (Estimated Net Rating, goalie forecasts):
  read through the blend rather than rebuilt; rebuilding it would be weeks of
  work to re-derive a number PostHockey publishes free.
* **Age drift and the E term** in the talent walk: small, and they change
  the shadow walk only.
* **Props**: PostHockey publishes no per-game player projection; its
  xPts and luck columns describe the past and are not on the card.

Nothing here is measured against prices. A forward row frozen from
2026-10-26 on carries the blended number.
