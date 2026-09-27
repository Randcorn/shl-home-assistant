# API fixtures

The files below are real responses from `https://www.shl.se/api/`, retrieved
2026-09-26 with the same `Origin`, `Referer`, `Accept`, and `User-Agent` headers
now used by the integration.

- `season_series_game_types_filter.json`: `/api/sports-v2/season-series-game-types-filter?series=SHL&season=2026/2027`. It contains the current season and series options plus `defaultSsgtFilter`.
- `season_series_game_types_filter_selected.json`: the same endpoint with the selected season and series UUIDs. This response contains the available game-type options.
- `latest_ssgt_shl_2026-2027.json`: `/api/sports-v2/latest-ssgt/qQ9-bb0bzEWUk`, which identifies the active SHL season/series/game type and is used by the current frontend.
- `game_schedule_2026-2027_saik.json`: `/api/sports-v2/game-schedule` for that filter's season, series, and game-type identifiers. The fixture keeps the 52 2026/27 rows that include Skellefteå (`SAIK` in schedule rows, `SKE` in play-by-play).
- `play_by_play_20260926_OHK_SAIK.json`: `/api/gameday/play-by-play/u0ribje54r`, Örebro Hockey–Skellefteå AIK on 2026-09-26. It has 136 newest-first events and three goals.
- `game_info_20260926_OHK_SAIK.json`: `/api/gameday/game-info/u0ribje54r` for the same finished game. This current response contains period/team aggregates rather than `gameInfo`; game metadata therefore comes from the schedule and live score/clock can be read from the newest play-by-play event.
- `game_overview_20260926_OHK_SAIK.json`: `/api/gameday/game-overview/u0ribje54r` for the same game. It provides the final score, state, period, and clock. Its nested team score fields were zero, so use top-level `homeGoals`/`awayGoals` as the authoritative scores.

The live API is not formally versioned. Keep captures tied to their endpoint,
query, game, and capture date so response changes are visible in tests.
