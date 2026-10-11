"""Pure polling-interval decisions, kept free of Home Assistant imports."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .discovery import ScheduleGame, normalize_state

LEAGUE_STANDINGS_ACTIVE_WINDOW = timedelta(hours=4)


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
        state = normalize_state(game.state)
        if "cancelled" in state or "postponed" in state:
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
