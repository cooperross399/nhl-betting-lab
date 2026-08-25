# How Claude works in this repository

## The default is: keep going

Most of what this lab needs is work Claude can do alone — data, models,
measurement, reports, tests, workflows, docs, and pull requests with green CI.
The default is to do it, not to ask permission for each step. A session that
stops every twenty minutes to check in produces less than one that works
through the build order and reports at the end.

"I could not find X" is not a stopping point. Look for X somewhere else, or
establish that X does not exist and write down which it was. In this repository
that distinction is load-bearing: "the provider does not offer this market" and
"we looked in the wrong endpoint" have looked identical before, and the second
one cost a market for a season.

## The hard stops

Two, and only two:

1. **Allowlisting a provider or a market.** Claude prepares the evidence,
   opens the pull request, and stops. Claude never writes a human acceptance
   receipt, never adds a name to `allowed_provider_names`, never adds a market
   to `required_markets`, and never presents shadow evidence as though it had
   approved something.
2. **Spending API credits beyond a small measurement budget.** The historical
   endpoints bill ten credits per market per event. A probe is cheap; a season
   is not. State the cost, then wait.

Everything else — including changing a model, restructuring a report, or
deciding a measurement was wrong — is Claude's to do, with the reasoning
written down.

## What "written down" means

Not a changelog entry. The reasoning goes where the decision lives:

- a **mechanism** in the module docstring, before the code that implements it;
- a **finding** in `docs/`, with the numbers and the sample sizes;
- a **test** that fails if the behaviour regresses, named after the thing it
  protects rather than after the function it calls.

The test names in this repository are sentences on purpose. A failing test
should tell a reader what broke without opening the file.

## When a measurement surprises you

The reflex is to explain it. The rule is to check whether the measurement was
asking the right question first.

This has already happened twice here. Goalie saves looked badly miscalibrated
and was being scored on relief appearances nobody can bet. Every skater market
looked mildly miscalibrated and was actually two opposite biases averaging out.
In both cases the numbers were real and the question was wrong, and in both
cases the fix changed the code rather than the wording.

## What never happens, whatever the reasoning

- Fabricating a price. A missing price stays missing.
- Presenting an excluded market as a pass, an avoid, or a no-value call.
- Placing a bet, or automating one.
- Shipping a change on calibration evidence when a price-based backtest exists
  and disagrees.
- Reporting a number without its sample size.
- Saying anything other than "no demonstrated edge" about an interval that
  includes zero.
- Weakening a gate to make something pass.
- Merging with failing CI, or force-pushing.
