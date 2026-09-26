# Codex handoff

The important prior project context is distilled into:
- `AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/SHL_API.md`
- `docs/DEVELOPMENT_PLAN.md`

The base project is prototype v0.1.0.

Some live API URLs could not be directly fetched by the previous web tooling,
so fresh browser Network captures should be treated as the source of truth.

Recommended capture workflow:
1. Open a live/recent SHL Game Center.
2. DevTools -> Network.
3. Reload.
4. Find `/api/sports-v2/game-schedule`, `/api/gameday/game-info/`,
   `/api/gameday/play-by-play/`, and `/api/gameday/team-stats/`.
5. Save representative JSON under `tests/fixtures/`.

Suggested first Codex prompt:

Read `AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/SHL_API.md`,
`docs/DEVELOPMENT_PLAN.md`, and inspect the complete repository. Run the
existing tests. Do not rewrite anything yet. Summarize the current architecture,
implemented functionality, incomplete functionality, and concrete next steps
for game discovery and live play-by-play. Use real fixtures as the source of
truth for API response shapes.
