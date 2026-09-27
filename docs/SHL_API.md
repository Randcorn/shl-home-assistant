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

Verified response on 2026-09-26 had top-level keys `gameInfo`, `teamList`, and
`ssgtUuid`. For the 2026/2027 SHL regular season, the filter's default values
were `season=ndcf81nlb3`, `series=qQ9-bb0bzEWUk`, and
`gameType=qQ9-af37Ti40B`. A schedule request returned 364 games. The schedule
uses `homeTeamInfo.code` / `awayTeamInfo.code`; Skellefteå was `SAIK` there.
Prefer `rawStartDateTime`, which is UTC, over the timezone-less local
`startDateTime` value.

## Season/series/game-type filter
`GET /api/sports-v2/season-series-game-types-filter?series=...&season=...`

Useful for discovering current identifiers instead of hard-coding them.
Verified 2026-09-26 response keys were `series`, `season`, `gameType`,
`defaultSsgtFilter`, and `ssgtUuid`. The `series` and `season` query values
selected a `defaultSsgtFilter` object containing `season`, `series`, and
`gameType` identifiers. `ssgtUuid` is the combined season/series/game-type
identifier and is distinct from `gameType`. The initial selector request uses
`series=SHL&season=2026/2027`; the follow-up uses the returned UUIDs, e.g.
`series=qQ9-bb0bzEWUk&season=ndcf81nlb3`, to populate `gameType`. Enumerate all
returned game types so postseason games can be discovered when available.
The schedule endpoint returned HTTP 400 when `gameTypeUuid` was omitted.

The SHL frontend also calls `/api/sports-v2/latest-ssgt/{seriesUuid}`. The
verified SHL response included `uuid` (the combined SSGT ID), `season`,
`series`, and `gameType` objects. This is now the preferred source for the
current schedule identifiers after discovering the SHL series UUID.

## Game info
`GET /api/gameday/game-info/{gameUuid}`

Observed shape includes:
- `gameInfo.gameUuid`, `extId`, `startDateTime`, `arenaName`, `state`,
  `overtime`, `shootout`, `seriesCode`, `seriesName`, `roundNumber`
- `homeTeam` and `awayTeam`, each with names, uuid and score
- `ssgtUuid`
- `seriesUuid`

The response is not consistent across game states. A request for the finished
2026-09-26 Örebro–Skellefteå game (`u0ribje54r`) returned `teamHead2Head`,
`teamPeriod`, and `bestScorers`, with no `gameInfo`, `homeTeam`, or `awayTeam`.
Use schedule and play-by-play data as the base for those fields and tolerate
this aggregate-only response.

## Game overview (additional endpoint found in frontend)

`GET /api/gameday/game-overview/{gameUuid}`

Verified for `u0ribje54r` on 2026-09-26. It returned `gameUuid`, `homeTeam`,
`awayTeam`, `homeGoals`, `awayGoals`, `state`, and `time` (`period` and
`periodTime`). The nested team `score` values were both zero despite
`homeGoals=3` and `awayGoals=0`; use the top-level goal totals as authoritative.
This endpoint supplies the coordinator's current scoreboard, state, and clock.
Before puck drop, both this endpoint and `play-by-play/{gameUuid}` returned
HTTP 200 with an empty body for the next SKE game. Treat an empty body as an
empty snapshot/event list and continue the short polling cadence around the
scheduled start instead of treating it as malformed JSON.

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

Verified on 2026-09-26: the completed Örebro–Skellefteå game returned a list of
136 newest-first events with three goals. The latest event carried the final
score, period 3, clock `20:00`, and `gameState=GameEnded`. Play-by-play used
Skellefteå's team code `SKE`, despite the schedule's `SAIK` code.

Requests succeeded with `Accept: application/json`, `Origin: https://www.shl.se`,
`Referer: https://www.shl.se/`, and a user agent. Plain requests without those
website headers returned HTTP 403 in the development environment.

## Other frontend endpoints checked

The minified public frontend bundle also declares `/api/gameday/boxscore`,
`/api/gameday/player-stats`, `/api/gameday/periodstats`,
`/api/gameday/play-by-play/initial-events`, and `/api/sports-v2/upcoming-live-games`.
The boxscore and global upcoming-live endpoints returned data, but they are
not needed for current game sensors. `initial-events/{gameUuid}` returned
HTTP 500 for the finished test game and needs a live-game capture before use.

The frontend also opens a server-sent event stream at
`https://game-broadcaster.s8y.se/live/game?gameUuid=...`. A request for the
finished test game returned HTTP 200 with `text/event-stream` but no initial
payload. Capturing a live stream would show whether this can replace 15-second
polling or provide faster goal notifications.

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
