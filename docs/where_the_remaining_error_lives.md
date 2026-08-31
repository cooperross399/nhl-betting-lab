
## What is being collected instead, from 2026-09-29

Daily Faceoff — the standard source for projected lines and starting goalies
— **blocks automated access**: its own `robots.txt` returns a Cloudflare
challenge. That is an explicit signal and this lab does not scrape past it.

The NHL's own API publishes a usable subset for free, inside the licence the
lab already relies on: `gameInfo.{home,away}Team.scratches` and `headCoach`,
plus `referees` and `linesmen`, on the game-centre right rail.

`scripts/capture_deployment.py` records it **with the instant it was taken**,
in the same workflow run as the price capture, so the two share a timestamp
and can be joined. What is not known today, and what a season of this makes
answerable:

1. **How long before puck drop does the scratch list become public?** If it
   populates an hour out it is far too late for a card built at 09:30 — but
   that is a fact worth having rather than assuming, and it decides whether a
   later card is worth building at all.
2. **Had the market already moved by the time it appeared?** Only a shared
   instant between the deployment capture and the price capture can answer
   that, which is why they are one job rather than two.

This collects. It does not fix anything, it is wired into no card, and it
changes no number. Like forward evidence, it cannot be gathered
retroactively, which is the only reason it starts now rather than when the
question is asked.
