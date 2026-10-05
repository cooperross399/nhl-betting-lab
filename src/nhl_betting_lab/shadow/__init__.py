"""The shadow model: modern shot-based stats, measured beside the card.

Cooper asked on 2026-10-05 for the model to use the modern analytical stats
(Corsi, Fenwick, expected goals, high-danger chances, PDO, goals saved above
expected, special-teams rates, individual shot attempts and ixG). The model
the card runs is frozen until 2027-04-25 (`docs/when_this_ends.md`): the
season's forward ledger is the test, and a test whose subject changes mid-run
measures nothing. He chose to build them as a **shadow model** instead.

So this package computes every one of those stats from the NHL's own free
play-by-play feed, builds a team model and a props rate model on them, and
measures both walk-forward against the model the card runs. It reports to
`data/outputs/shadow_stats.md` and nowhere else.

**Nothing on the card's path may import this package.** The forward ledger
is written from the card's probability map before any gate, so a shadow
number reaching that map would contaminate the 2027-04-25 measurement with
no way to separate it out afterwards.
`tests/test_the_shadow_model_cannot_reach_the_card.py` holds that apart.
Promoting anything here onto the card is Cooper's decision, after the
decision date, and only on price evidence.
"""
