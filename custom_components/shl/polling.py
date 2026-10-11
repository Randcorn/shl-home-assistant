"""Pure polling-interval decisions, kept free of Home Assistant imports."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .discovery import ScheduleGame, is_cancelled_state

LEAGUE_STANDINGS_ACTIVE_WINDOW = timedelta(hours=4)

# SHL intermissions last about 18 minutes (observed 17m57s and 18m02s).
PERIOD_BREAK_LENGTH = timedelta(minutes=18)
# Resume live-rate polling this long before the expected next puck drop.
PERIOD_BREAK_RESUME_LEAD = timedelta(minutes=1)
# Never pause longer than this without re-checking the game state.
PERIOD_BREAK_MAX_PAUSE = timedelta(minutes=5)


def next_idle_poll_interval(
    now: datetime,
    game_starts: Iterable[datetime | None],
    idle_interval: timedelta,
) -> timedelta:
    """Wake at the next known league game start if it falls inside idle time."""
    upcoming_starts = [
        game_start for game_start in game_starts
        if game_start is not None and game_start > now
    ]
    if not upcoming_starts:
        return idle_interval
    until_start = min(upcoming_starts) - now
    if timedelta(0) < until_start <= idle_interval:
        return max(timedelta(seconds=15), until_start)
    return idle_interval


def standings_should_poll_frequently(now: datetime, games: Iterable[ScheduleGame]) -> bool:
    """Poll standings at their configured cadence while any SHL game is active."""
    for game in games:
        if is_cancelled_state(game.state):
            continue
        if game.is_live or game.started_recently(now):
            return True
        if (
            game.start_time is not None
            and timedelta(0) <= now - game.start_time <= LEAGUE_STANDINGS_ACTIVE_WINDOW
        ):
            return True
    return False


def effective_standings_interval(
    now: datetime,
    games: Iterable[ScheduleGame],
    active_interval: timedelta,
    idle_interval: timedelta,
) -> timedelta:
    """Select the league-table interval for the current league schedule."""
    return (
        active_interval
        if standings_should_poll_frequently(now, games)
        else idle_interval
    )


def period_break_poll_interval(
    now: datetime,
    break_started: datetime | None,
    live_interval: timedelta,
) -> timedelta:
    """Pause polling during a period break without missing the next period.

    When the break start is known, sleep until shortly before the expected
    puck drop, but never pause longer than PERIOD_BREAK_MAX_PAUSE without
    re-checking. Without a known break start, re-check at least every
    PERIOD_BREAK_MAX_PAUSE so a delayed period is never missed for long.
    """
    if break_started is None:
        return max(live_interval, PERIOD_BREAK_MAX_PAUSE)
    until_resume = break_started + PERIOD_BREAK_LENGTH - now
    if until_resume <= PERIOD_BREAK_RESUME_LEAD:
        # At or past the expected puck drop: poll at the live rate.
        return live_interval
    pause = min(until_resume - PERIOD_BREAK_RESUME_LEAD, PERIOD_BREAK_MAX_PAUSE)
    return max(live_interval, pause)
