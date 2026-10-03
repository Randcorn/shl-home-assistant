# SHL Home Assistant integration

A Home Assistant custom integration that discovers current and upcoming SHL
games and follows a configured team's live game. Skellefteå AIK is the default
team, but the integration accepts any SHL team code.

## Current features

- Discovers season, series, and game-type identifiers from the SHL filter API.
- Finds the configured team's active or next game from the SHL schedule.
- Polls game-overview and play-by-play during a game, with slower schedule polling
  outside live play (15 seconds during a live game; 5 minutes otherwise).
- Exposes game, score, last-goal, points, league-position, and individual
  standings-statistic sensors. The game sensor includes matchup and next-game
  details in its attributes.
- Fires `shl_goal` once per newly observed goal and `shl_event` for new or
  corrected play-by-play events. It also emits game and period lifecycle events
  when the response has enough state information.
- Persists play-by-play event revisions so a Home Assistant restart does not
  replay already processed events.

## Installation and configuration

Copy `custom_components/shl` into Home Assistant's `custom_components` folder,
restart Home Assistant, and add **SHL** from Settings → Devices & services.
Choose the team by name from the current SHL team list.

## Events

`shl_goal` includes the normalized scorer, scoring team, period, game time,
score-after-goal, assists, goal status, and penalty-shot/empty-net flags.
`shl_event` carries the raw changed event fields, stable `eventUuid`, revision,
and an `is_correction` flag. Lifecycle event names are `shl_game_started`,
`shl_period_started`, `shl_period_ended`, and `shl_game_ended`.

The SHL website endpoints are first-party website APIs, not a formally
versioned public API. Real response captures used during development are in
`tests/fixtures/`; see `docs/SHL_API.md` for observed response shapes and
remaining live-game verification.
