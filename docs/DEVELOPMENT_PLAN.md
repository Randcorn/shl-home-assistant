# Development plan

## Status after API capture work (2026-09-26)

- Prototype inspection is complete.
- Schedule filter discovery and team game selection are implemented against
  real filter and schedule captures. The implementation handles both `SAIK`
  (schedule) and `SKE` (play-by-play) for Skellefteå.
- Coordinator polling from game-overview and play-by-play, stored event revision cursors, deterministic event
  ordering, duplicate suppression, correction-aware `shl_event`, and
  `shl_goal` emission are implemented. Current score, period, and clock can be
  sourced from the newest play-by-play item when `game-info` lacks them.
- Game, score, last-goal, points, league-position, and individual standings
  statistic sensors are implemented. Lifecycle events are
  inferred from game-overview state and period transitions when those fields
  are present.
- Parser and event tests cover real captured filter, schedule, and
  play-by-play responses. A live-game test is still outstanding.

Remaining work: run this in Home Assistant during a live SHL game, verify
actual live state strings and event timing, then extend lifecycle/edge-case
tests for overtime, shootout, postponed/cancelled, failures, and restart
recovery.

1. **Inspect prototype** — run tests, understand current architecture, avoid
   unnecessary rewrites.
2. **Game discovery** — use schedule + season/series/game-type endpoints to
   find current/next games for a configured team; never hard-code game UUIDs.
3. **Live coordinator** — poll game-info and play-by-play with faster polling
   during live games and slower polling otherwise; handle failures/state changes.
4. **Event processing** — normalize GoalEvent/GenericGameEvent; dedupe by
   eventUuid; handle revisions; deterministic ordering; restart safety.
5. **HA entities** — game state, opponent, home/away teams and scores, period,
   clock, current/next game, last goal as appropriate.
6. **HA events** — document and implement shl_goal and game/period lifecycle
   events where the data supports them.
7. **Tests** — pre-game, live, goals, duplicates, revisions, overtime,
   shootout, end, postponed/cancelled and API failures.
8. **Real-world test** — compare SHL website, game-info, play-by-play and HA
   state/events during an actual live game.
