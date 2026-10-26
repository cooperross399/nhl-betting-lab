# The NHL's two public APIs: every endpoint, checked live

Saved 2026-10-25 at Cooper's request. Every row was requested on that date
and answered 200 unless it says otherwise; the "returns" column is the
payload's top-level keys. `docs/nhl_data_sources.md` says which of these the
lab reads and why; this file is the full menu. Both hosts are keyless and
free.

**Two things that bite.**

* **Rate limit.** Both hosts answered 429 to everything after about 35
  requests in quick succession and recovered after a minute. Space requests
  (the lab's fetchers sleep between calls) and retry 429 with backoff
  (`data.nhl_api._get_json` does).
* **Redirects.** `api-web.nhle.com` answers some paths (`/v1/schedule/now`,
  every `now` alias) with a 307 to the dated path; curl needs `-L` or it
  prints nothing. python-requests and urllib follow it. User-agent
  conventions differ by host (root `CLAUDE.md`): never carry one host's to
  another.

Placeholders: `{game}` 10-digit game id (`2026020180`: season 2026, type 02
regular season, game 0180); `{season}` 8-digit (`20262027`); `{type}` 2
regular season, 3 playoffs; `{TEAM}` three-letter code; `{player}` NHL id;
`{team_id}` the numeric team id (EDGE); `{date}` `YYYY-MM-DD`; `now` works in
place of a date or season wherever one is taken.

## `api-web.nhle.com/v1` (the site's own API)

### Schedule and scores

| Endpoint | Returns |
|:--|:--|
| `/schedule/{date}` · `/schedule/now` | the week from that date: `gameWeek`, `oddsPartners`, season start and end dates |
| `/schedule-calendar/{date}` · `/now` | which dates have games, `teams` |
| `/score/{date}` · `/score/now` | that day's games with scores, goals, clock: `games`, `oddsPartners` |
| `/scoreboard/now` | `gamesByDate` around today |
| `/club-schedule-season/{TEAM}/{season}` | a club's whole season, `clubTimezone` |
| `/club-schedule/{TEAM}/week/now` · `/month/now` | a club's week or month |
| `/network/tv-schedule/now` | national `broadcasts` |
| `/partner-game/{country}/now` | the NHL's betting partner's odds on today's games (`bettingPartner`, `games`) |
| `/where-to-watch` | **404** |

### One game (`/gamecenter/{game}/…`)

| Endpoint | Returns |
|:--|:--|
| `/play-by-play` | every event with coordinates, players, `situationCode` (the lab's xG source) |
| `/boxscore` | per-player and team lines (the lab's settlement source) |
| `/landing` | summary: scoring, penalties, three stars |
| `/right-rail` | `gameInfo` (referees, linesmen, scratches), `seasonSeries`, `teamGameStats`, `shotsByPeriod`, `gameReports` |
| `/wsc/game-story/{game}` | the narrative game story |
| `/wsc/play-by-play/{game}` | play-by-play as a list (the web scoreboard's form) |
| `/ppt-replay/goal/{game}/{event}` | puck and player tracking for a goal replay |

### Standings and seasons

| Endpoint | Returns |
|:--|:--|
| `/standings/{date}` · `/standings/now` | `standings`, `wildCardIndicator` |
| `/standings-season` | which seasons have standings and their rules |
| `/season` | every season id (list) |
| `/playoff-series/carousel/{season}/` | `currentRound`, `rounds` |
| `/playoff-bracket/{year}` | `series` |

### Clubs

| Endpoint | Returns |
|:--|:--|
| `/roster/{TEAM}/current` · `/{season}` | `forwards`, `defensemen`, `goalies`, each with `birthDate`, height, weight, `shootsCatches` (the lab's aging source) |
| `/roster-season/{TEAM}` | seasons a roster exists for |
| `/prospects/{TEAM}` | prospects by position |
| `/club-stats/{TEAM}/now` · `/{season}/{type}` | season stats for every skater and goalie |
| `/club-stats-season/{TEAM}` | seasons and game types available |

### Players

| Endpoint | Returns |
|:--|:--|
| `/player/{player}/landing` | bio, current team, career and featured stats, last five games |
| `/player/{player}/game-log/now` · `/{season}/{type}` | one row per game (`gameLog`) |
| `/player-spotlight` | the site's featured players |
| `/skater-stats-leaders/current` · `/{season}/{type}` | leaders in goals, assists, points, PP and SH goals, faceoffs, plus-minus, PIM |
| `/goalie-stats-leaders/current` | wins, shutouts, save %, GAA leaders |
| `/meta?players={id,...}` | names and teams for ids |

### NHL EDGE (puck and player tracking)

| Endpoint | Returns |
|:--|:--|
| `/edge/skater-detail/{player}/now` | `topShotSpeed`, `skatingSpeed`, `totalDistanceSkated`, `distanceMaxGame` |
| `/edge/skater-skating-distance-detail/{player}/now` | distance last 10 games and by game |
| `/edge/skater-shot-speed-detail/{player}/now` | `hardestShots`, shot speed by game |
| `/edge/skater-zone-time/{player}/now` | offensive/neutral/defensive zone time, `zoneStarts` |
| `/edge/skater-landing/now` | league `leaders` |
| `/edge/team-detail/{team_id}/now` | team shot speed, skating speed, distance, `sogSummary` |
| `/edge/team-zone-time-details/{team_id}/now` | team zone time, `shotDifferential` |
| `/edge/team-landing/now` | team `leaders` |
| `/edge/goalie-detail/{player}/now` | save stats with `shotLocationSummary` and `shotLocationDetails` |
| `/edge/goalie-save-percentage-detail/{player}/now` | save % last 10 and by game |
| `/edge/skater-speed-detail/{player}/now` | **404** |

### Draft and misc

| Endpoint | Returns |
|:--|:--|
| `/draft/rankings/now` · `/draft/picks/now` · `/draft-tracker/picks/now` | prospect rankings, picks, live tracker |
| `/location` | the caller's `country` |

## `api.nhle.com/stats/rest/en` (the stats site's API)

Paged (`start`, `limit`; `limit=-1` for everything), filtered with
`cayenneExp` (for example `seasonId=20262027 and gameTypeId=2`), sorted with
`sort=[{"property":"points","direction":"DESC"}]`. Answers `{data, total}`.
Season-to-date totals with no as-of date: fine for names and bios, a leak if
fed to a walk-forward fit (`nhl_data_sources.md`).

| Endpoint | Returns |
|:--|:--|
| `/skater/{report}` | one row per skater; reports: `summary`, `bios` (birth date, draft), `realtime` (hits, blocks, giveaways, takeaways), `timeonice`, `powerplay`, `penaltykill`, `faceoffpercentages`, `faceoffwins`, `goalsForAgainst`, `penalties`, `penaltyShots`, `percentages`, `puckPossessions`, `scoringRates`, `scoringpergame`, `shootout`, `shottype`, `summaryshooting` |
| `/goalie/{report}` | `summary`, `advanced`, `bios`, `daysrest`, `penaltyShots`, `savesByStrength`, `shootout`, `startedVsRelieved` |
| `/team/{report}` | `summary`, `realtime`, `powerplay`, `powerplaytime`, `penaltykill`, `penaltykilltime`, `penalties`, `faceoffpercentages`, `faceoffwins`, `goalgames`, `goalsagainstbystrength`, `goalsagainstbystrengthgoaliepull`, `goalsforbystrength`, `goalsforbystrengthgoaliepull`, `goalsbyperiod`, `leadingtrailing`, `outshootoutshotby`, `percentages`, `savePercentage`, `scoretrailfirst`, `shootout`, `shottype`, `summaryshooting`, `daysbetweengames` |
| `/shiftcharts?cayenneExp=gameId={game}` | **every shift of a game**: player, period, start, end, duration (727 rows for one game) |
| `/game?cayenneExp=season={season}` | every game with date, state and score |
| `/players?cayenneExp=id={player}` | one player's name, team, position, number |
| `/team` · `/franchise` · `/season` · `/draft` · `/country` · `/componentSeason` | reference tables |
| `/glossary` | the NHL's own definitions (321 stats) |
| `/config` | every report name and its columns (how the lists above were read) |

## What this opens up for the model

* **Shift charts** (`/shiftcharts`) give who was on the ice for every shot,
  which is what PostHockey's Net Rating needs for its defensive half and for
  quality of competition. `docs/posthockey_gap_list.md` lists that half as
  not built for want of shift data; this is the data.
* **EDGE** gives skating and shot speed and zone time per player; PostHockey
  builds its burst speed from the same counts.
* **`/partner-game/US/now`** is a free odds feed from the NHL's betting
  partner, worth comparing against the bought prices before trusting it.
