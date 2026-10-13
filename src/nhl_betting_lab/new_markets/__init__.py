"""Shadow models for markets that are not on the card.

Each module here prices a market the card does not carry, and is measured
walk-forward on outcomes beside the card, never on it. Reaching the card needs
a price backtest and Cooper's decision (`CLAUDE.md`).

**Nothing on the card's path may import this package.** The forward ledger is
written from the card's probability map before any gate, so a number from
here reaching that map would contaminate the 2027-04-25 measurement.
`tests/test_the_shadow_model_cannot_reach_the_card.py` holds that apart.

Keep this file minimal: it imports none of its modules.
"""
