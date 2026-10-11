# SHL Home Assistant Integration

Build a Home Assistant custom integration for the Swedish Hockey League (SHL),
especially useful for Skellefteå AIK (SKE).

## Critical architecture decision
Do NOT target the legacy SHL Open API. Target the current SHL website APIs
under `https://www.shl.se/api/`.

Known endpoints:
- `/api/sports-v2/game-schedule`
- `/api/sports-v2/season-series-game-types-filter`
- `/api/gameday/game-info/{gameUuid}`
- `/api/gameday/play-by-play/{gameUuid}`
- `/api/gameday/team-standings/{ssgtUuid}`
- `/api/gameday/team-stats/{gameUuid}`
- `/api/gameday/post-game-data/team-stats/{gameUuid}?ssgtUuid=...&homeTeamUuid=...&awayTeamUuid=...`

See `docs/SHL_API.md`.

## Current state
This repo started from prototype v0.1.0. It contains an API client, coordinator,
models, config flow, sensor platform and tests. Game discovery, live polling,
idempotent event delivery, and the sensor/event surface are implemented and
running in a Home Assistant dev container. The remaining gap is real-world
verification during a live game (see docs/DEVELOPMENT_PLAN.md).

## Event identity
For play-by-play events:
- `eventUuid` is the stable event identity.
- `eventId` is useful for ordering.
- `revision` matters because events can be corrected.
- Never emit the same event repeatedly just because it appears on every poll.
- The observed play-by-play array may be newest-first; don't trust array order.

Goal events can include period, time, eventTeam, player, assists, homeGoals,
awayGoals, goalStatus, isPenaltyShot, isEmptyNetGoal, realWorldTime and revision.

## Intended HA functionality
Potential sensors: game state, opponent, home/away team, home/away score,
period, game clock, current/next game, last goal.

Potential HA events:
`shl_goal`, `shl_game_started`, `shl_period_started`,
`shl_period_ended`, `shl_game_ended`, and possibly generic `shl_event`.

Do not hard-code SKE as the only supported team. SKE is the primary test case.

## Development
Prefer small testable modules. Keep API parsing separate from HA entities.
Use real API captures as fixtures. Handle API failures, restarts, duplicate
events, corrections, overtime and shootouts.
