"""Season-long Monte Carlo for the public NHL Projections site.

Three modules, run in order by ``web/build_season_json.py``:

* ``fetch``    — every input, from public endpoints with no credential: the
                 NHL API (standings, rosters, club schedules, skater and
                 goalie summaries) and MoneyPuck's season summaries.
* ``model``    — team strength ratings and per-player projections, built
                 from the three previous seasons plus whatever of the current
                 one has been played, and the injury list under
                 ``data/season_sim/injuries.json``.
* ``simulate`` — the remaining schedule played 10,000 times; standings,
                 playoff odds, scorer and goalie-win projections.

Nothing here reads a price, spends a credit, or reaches the card. It is a
projection of the standings, published as a projection.
"""
