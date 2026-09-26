# Development plan

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
