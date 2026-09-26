# SHL API reverse engineering

Current site: `https://www.shl.se/`

## Schedule
`GET /api/sports-v2/game-schedule`

Observed query parameters:
`seasonUuid`, `seriesUuid`, `gameTypeUuid`, `gamePlace=all`, `played=all`.

Observed response contains `gameInfo` and `teamList`. Game objects include
`uuid`, `rawStartDateTime`, `startDateTime`, `state`, `overtime`, `shootout`,
`ssgtUuid`, `homeTeamInfo`, `awayTeamInfo`, `venueInfo`, `seriesInfo`,
`roundNumber`.

## Season/series/game-type filter
`GET /api/sports-v2/season-series-game-types-filter?series=...&season=...`

Useful for discovering current identifiers instead of hard-coding them.

## Game info
`GET /api/gameday/game-info/{gameUuid}`

Observed shape includes:
- `gameInfo.gameUuid`, `extId`, `startDateTime`, `arenaName`, `state`,
  `overtime`, `shootout`, `seriesCode`, `seriesName`, `roundNumber`
- `homeTeam` and `awayTeam`, each with names, uuid and score
- `ssgtUuid`
- `seriesUuid`

Example observed game was CHL: Mannheim (MAN) 1 - Skellefteå (SKE) 3,
shootout true. Do not assume seriesCode is always SHL.

## Play-by-play
`GET /api/gameday/play-by-play/{gameUuid}`

Observed event fields include:
`eventId`, `eventUuid`, `revision`, `type`, `period`, `time`, `gameState`,
`realWorldTime`, `updatedTime`, `homeTeam`, `awayTeam`, `eventTeam`, `player`,
`assists`, `homeGoals`, `awayGoals`, `goalSection`, `isPenaltyShot`,
`isEmptyNetGoal`, `goalStatus`, `gameUuid`.

Real historical goal example:
- game: `20260415-SAIK-LHF`
- eventId: `48`
- eventUuid: `49fbbbb3-1319-5b87-9749-e8f11c739f8b`
- period: 2
- time: `01:58`
- event type: `goal`
- SAIK scored; score became 2-0
- scorer: Oliver Okuliar (#8)
- assists: Arvid Lundberg (#52), Pontus Johansson (#25)
- goalStatus: `PP1`
- revision: 2
- penalty shot: false
- empty net: false

Important: treat `eventUuid` as event identity, use `eventId` for ordering and
handle `revision`. The observed array may be newest-first.

## Team stats
`GET /api/gameday/team-stats/{gameUuid}`

Observed statistic keys include:
`G`, `PIM`, `FOW`, `SOG`, `SPG`, `PPSOG`, `Saves`, `GA`, `SavesPerShot`,
`PP_perc`, `SH_perc`, `PPG`, `SHGA`, `SHG`, `PPGA`, `NumPP`, `NumSH`, `Hits`,
`BkS`, `SiBk`.

## Other
`GET /api/gameday/post-game-data/team-stats/{gameUuid}?ssgtUuid=...&homeTeamUuid=...&awayTeamUuid=...`

Prefer fresh browser Network captures over assumptions when API behaviour is
unclear. Do not assume a Game Center URL segment is the gameUuid; verify the
actual API request.
