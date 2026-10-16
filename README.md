# SHL Home Assistant integration

A Home Assistant custom integration that discovers current and upcoming SHL
games and follows a configured team's live game.

## Current features

- Discovers season, series, and game-type identifiers from the SHL filter API.
- Finds the configured team's current game (live, or the most recently
  started one) and its next game from the SHL schedule.
- Polls game-overview, play-by-play, and team statistics during a game, with
  configurable live and idle polling intervals. When a known game start is
  within the idle interval, it schedules a poll for puck drop and switches to
  the live interval from then on. During a period break it pauses polling
  until shortly before the expected next puck drop, re-checking at least
  every five minutes so a delayed period is never missed for long.
- Uses the league schedule to wake at other SHL game starts as well, refreshing
  standings at their active-game cadence during and shortly after league games,
  and at a separately configurable cadence when no league games are active.
- Exposes game, next-game, score, last-goal, points, league-position, and
  individual standings-statistic sensors, plus one combined home-away
  shots-on-goal sensor. The game sensor tracks the previous/current game and
  keeps its final score, shots, and last goal until the next game starts;
  the next-game sensor shows the upcoming fixture with its matchup details.
- Fires `shl_goal` once per newly observed goal and `shl_event` for new or
  corrected play-by-play events. It also emits game and period lifecycle events
  when the response has enough state information.
- Persists play-by-play event revisions so a Home Assistant restart does not
  replay already processed events.

## Installation

### HACS (recommended)

1. Install [HACS](https://hacs.xyz/) if you have not already.
2. In HACS, open the three-dot menu at the top right and choose
   **Custom repositories**.
3. Add `https://github.com/Randcorn/shl-home-assistant` with the category
   **Integration**, then install **SHL**.
4. Restart Home Assistant and add the integration from
   Settings → Devices & services → Add integration → **SHL**.

### Manual

Copy `custom_components/shl` into Home Assistant's `custom_components` folder,
restart Home Assistant, and add **SHL** from Settings → Devices & services.

## Configuration

Choose the team by name from the current SHL team list.
Configure refresh intervals through the integration's **Configure** option.

## Development

Run the tests (they do not require Home Assistant to be installed):

```bash
py -m pip install -r requirements_test.txt
py -m pytest tests/ -q
```

The SHL website endpoints are first-party website APIs, not a formally
versioned public API. Real response captures used during development are in
`tests/fixtures/`; see `docs/SHL_API.md` for observed response shapes and
remaining live-game verification.
