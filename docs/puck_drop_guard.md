# The puck-drop guard

## What it does

Before a card is rendered, every selection is checked against the provider's
`commence_time` for its game. A selection is quarantined — moved out of best
bets, leans and passes into a section headed **"Already started — no longer
plays"** — when either of these is true:

1. The game's start time is at or before the moment the card is generated.
2. The game's start time **cannot be confirmed**: it is missing, blank,
   unparseable, or carries no timezone.

Its stake is removed with it. A quarantined selection is not a pass, not an
avoid, and not a no-value call; it is a bet that is no longer available.

## Why ambiguity falls on the not-a-play side

The two failure directions are not symmetric.

Letting a started game through produces a card that recommends a bet nobody can
place, at a price that no longer exists, and — worse — a bet whose result may
already be partly known. That is the failure that destroys trust in every other
line on the card.

Pulling a game that had not actually started costs one missed bet on a card
that lists dozens, and the card says exactly why it was pulled, so the loss is
visible and recoverable in seconds.

So a missing or unparseable start time is treated as **started**. It is not
treated as "probably fine".

## Why it is here on day one

The EPL lab retrofitted this after a card carried a fixture that had already
kicked off. Retrofitting a guard means every card before it was unguarded, and
there is no way to go back and re-check them. Building it first is cheaper and
honest.

## What it deliberately does not do

It does not use the NHL API's `gameState`. That would be a second source of
truth about whether a bet is placeable, and the two could disagree. The
provider's `commence_time` is the one that matters, because the provider is the
one selling the price. If the provider's time is wrong, the guard is wrong in
the safe direction.

It does not apply a grace period. A game that started sixty seconds ago is
started.

It does compare in UTC, always. Every comparison is between timezone-aware
instants; a naive datetime is a bug, not a fallback.
