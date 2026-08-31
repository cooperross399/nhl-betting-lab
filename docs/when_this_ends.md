# When this ends, decided before the data exists

**Written 2026-08-31, before the 2026-27 season starts and before a single
forward opinion has settled.** That timing is the entire point. A stopping
rule chosen after the numbers arrive is not a stopping rule, it is a
justification, and this project has already watched three findings die that
looked robust right up until someone asked the question their authors had not
pre-committed to.

## Why there has to be a date

Everything measurable on bought history has been measured. Props: no
demonstrated edge over 25,949 wagers. Team markets: no demonstrated edge over
1,366 / 1,762 / 2,201 wagers after buying every snapshot of both seasons.
Model-free structure: 1,175 pre-registered cells across two sports and
twenty-six years of NFL closing lines, zero survivors. The model's
disagreement with the market carries a coefficient of 0.032 where the market
carries 0.97.

One question is left, and it is the only one a pipeline can still answer:
**does the model beat prices on data that did not exist when it was built?**
The forward ledger answers that and nothing else. Once it has answered, there
is no further experiment this lab can run, and continuing to run it would be
a habit rather than an investigation.

## The rule

**Decision date: 2027-04-25** — fourteen days after the last regular-season
game, which is the settlement patience window, so every opinion that can
settle has.

**The measurement**: the forward ledger's pooled return on frozen opinions,
one bet per wager at the best price the card could have taken, corrected
across the markets measured. Opinions, not bets: the card is dark and places
none, but a frozen opinion scored against the price it was frozen at is the
same test.

**Sample floor: 3,000 settled opinions.** Below that the season did not
produce a test — that is a finding about the pipeline, not about the model,
and it means the pipeline failed rather than the model.

Then, exactly one of:

| Result | What it means | What happens |
|:--|:--|:--|
| Corrected interval **excludes zero, positive** | A candidate, on one season | **Not a green light.** A second season confirms or kills it. No stake is placed on one season, ever. |
| Corrected interval **spans zero** | No edge after a clean out-of-sample season, on top of everything already measured | **Stop.** Archive both labs, disable the routines, write the closing note. |
| Corrected interval **excludes zero, negative** | Confirmed loser | **Stop**, same as above. |
| Fewer than 3,000 settled opinions | The test did not run | Diagnose the pipeline. Do not read the number. |

## What may and may not change before then

**May**: defect fixes. A broken join, a settlement error, a ledger that stops
accumulating. Each recorded in `CLAUDE.md` with the date and what it changed,
because a fix that silently alters what is being measured is indistinguishable
from tuning.

**May not**: the model, the edge bar, the market list, the staking rule, or
anything else that changes what is being tested. Not in December because
October looked bad. Not in March because February looked good. The ledger is
a test, and a test whose subject changes mid-run measures nothing.

If a mid-season result looks strong, the correct action is **nothing**. Write
it down and wait for the date.

## The honest prior

Everything measured so far says this comes back null. The season is worth
running because it costs a cron job and a few thousand credits against a
monthly allowance in the millions, and because it is the one test that has
never been run — not because the odds are good.

A null in April is a real result. It closes a question that has been open
since this repository was created, and it closes it with evidence rather than
fatigue.
