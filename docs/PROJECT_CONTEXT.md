# Project context

The goal is a Home Assistant integration that reacts to live SHL games,
particularly Skellefteå AIK goals.

The legacy SHL Open API was investigated and rejected as the target. The current
SHL website exposes first-party REST APIs. The useful architecture is:

SHL schedule -> game discovery -> active game -> game-overview + play-by-play ->
normalized models -> HA coordinator -> entities/events -> automations.

A historical SAIK vs Luleå playoff game demonstrated that play-by-play goal
events contain scoring team/player, assists, score-after-event, period, game
time, power-play status, penalty-shot/empty-net flags and event revision.

Idempotency is essential: polling must not repeatedly trigger the same goal.

## Implementation status (2026-09-26)

The prototype now has a schedule-discovery path, team-specific active/next-game
selection, live play-by-play polling, revision-aware event processing, stored
event cursors, event emission, and game/score/last-goal, points,
league-position, and standings-statistic sensors. Schedule, standings, and
play-by-play parsing is kept outside the entity definitions. SHL schedule rows
identify Skellefteå as `SAIK`; play-by-play uses `SKE`, so the default `SKE`
configuration matches both.

Real responses have been captured in `tests/fixtures/`. The initial filter
response's `defaultSsgtFilter` supplies season/series identifiers. The
frontend's `/api/sports-v2/latest-ssgt/{seriesUuid}` endpoint returns the
current active season, series, and game type for schedule requests. The
frontend's `/api/gameday/game-overview/{gameUuid}` endpoint returns score,
state, period, and clock. A finished game's `game-info` response currently
contains period/team aggregates instead of the `gameInfo` shape previously
observed, so the coordinator uses schedule metadata plus game-overview and
play-by-play.

The endpoints and request headers were verified directly on 2026-09-26, and
parser/event tests use those captures. A test against a live SHL game is still
needed to validate state transitions and in-game event timing. These APIs are
first-party website APIs, so their response shape may change without notice.
