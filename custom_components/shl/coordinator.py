"""Schedule discovery, game polling, and idempotent event delivery."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ShlApi, ShlApiError
from .const import (
    DOMAIN,
    EVENT_GOAL,
    EVENT_PLAY_BY_PLAY,
    CONF_DISCOVERY_INTERVAL,
    CONF_IDLE_POLL_INTERVAL,
    CONF_IDLE_POLL_INTERVAL_MINUTES,
    CONF_LIVE_POLL_INTERVAL,
    CONF_STANDINGS_INTERVAL,
    CONF_STANDINGS_IDLE_INTERVAL,
    DEFAULT_DISCOVERY_INTERVAL,
    DEFAULT_IDLE_POLL_INTERVAL,
    DEFAULT_IDLE_POLL_INTERVAL_MINUTES,
    DEFAULT_LIVE_POLL_INTERVAL,
    DEFAULT_STANDINGS_INTERVAL,
    DEFAULT_STANDINGS_IDLE_INTERVAL,
)
from .discovery import (
    ScheduleGame, choose_next_game, discover_team_game, is_finished_state, is_live_state,
    normalize_state, parse_team_standing,
)
from .events import process_play_by_play
from .models import (
    GoalEvent, parse_game_overview, parse_goal, parse_live_snapshot,
    parse_shots_on_goal,
)
from .polling import effective_standings_interval, next_idle_poll_interval

PERSISTENCE_VERSION = 1


class ShlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Find games and poll SHL data at a rate appropriate to game state."""

    def __init__(
        self, hass, api: ShlApi, team_code: str, store: Store, team_name: str = "",
        options: dict[str, Any] | None = None,
    ) -> None:
        self.api = api
        self.team_code = team_code.strip().upper()
        self.team_name = team_name.strip() or self.team_code
        self.store = store
        options = options or {}
        self.live_poll_interval = timedelta(seconds=self._bounded_option(
            options, CONF_LIVE_POLL_INTERVAL, DEFAULT_LIVE_POLL_INTERVAL, 5, 120
        ))
        if CONF_IDLE_POLL_INTERVAL_MINUTES in options:
            idle_minutes = self._bounded_option(
                options,
                CONF_IDLE_POLL_INTERVAL_MINUTES,
                DEFAULT_IDLE_POLL_INTERVAL_MINUTES,
                1,
                360,
            )
            self.idle_poll_interval = timedelta(minutes=idle_minutes)
        elif CONF_IDLE_POLL_INTERVAL in options:
            # Keep existing entries' saved seconds-based option working.
            idle_seconds = self._bounded_option(
                options, CONF_IDLE_POLL_INTERVAL, DEFAULT_IDLE_POLL_INTERVAL, 60, 21600
            )
            self.idle_poll_interval = timedelta(seconds=idle_seconds)
        else:
            self.idle_poll_interval = timedelta(
                minutes=DEFAULT_IDLE_POLL_INTERVAL_MINUTES
            )
        self.discovery_interval = timedelta(minutes=self._bounded_option(
            options, CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL, 1, 60
        ))
        self.standings_interval = timedelta(minutes=self._bounded_option(
            options, CONF_STANDINGS_INTERVAL, DEFAULT_STANDINGS_INTERVAL, 1, 240
        ))
        self.standings_idle_interval = timedelta(minutes=self._bounded_option(
            options,
            CONF_STANDINGS_IDLE_INTERVAL,
            DEFAULT_STANDINGS_IDLE_INTERVAL,
            1,
            360,
        ))
        self.current_game_uuid: str | None = None
        self._selected_game: ScheduleGame | None = None
        self._all_games: list[ScheduleGame] = []
        self._last_discovery: datetime | None = None
        self._last_standings_refresh: datetime | None = None
        self._standings: dict[str, Any] | None = None
        self._seen_revisions: dict[str, int] = {}
        self._event_baseline_ready = False
        self._shots_on_goal: dict[str, int | None] = {"home": None, "away": None}
        self._last_details: tuple[str, dict[str, Any]] | None = None
        super().__init__(
            hass, logging.getLogger(__name__), name=DOMAIN,
            update_interval=self.idle_poll_interval,
        )

    @staticmethod
    def _bounded_option(options: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
        """Read an interval option and keep stored values within safe bounds."""
        try:
            value = int(options.get(key, default))
        except (TypeError, ValueError):
            return default
        return min(max(value, minimum), maximum)

    async def async_load_state(self) -> None:
        """Restore the active game's event cursor across Home Assistant restarts."""
        saved = await self.store.async_load()
        if not isinstance(saved, dict):
            return
        game_uuid = saved.get("game_uuid")
        revisions = saved.get("seen_revisions")
        if isinstance(game_uuid, str) and isinstance(revisions, dict):
            self.current_game_uuid = game_uuid
            self._seen_revisions = {
                str(uid): int(revision)
                for uid, revision in revisions.items()
                if isinstance(revision, (int, str)) and str(revision).isdigit()
            }
            self._event_baseline_ready = True

    async def _discover(self, now: datetime) -> None:
        game, games = await discover_team_game(self.api, self.team_code)
        previous_uuid = self.current_game_uuid
        previous_game = (self.data or {}).get("game") or {}
        previous_schedule = next(
            (item for item in games if item.game_uuid == previous_uuid),
            self._selected_game,
        )
        if (
            previous_uuid
            and previous_game.get("gameUuid") == previous_uuid
            and is_live_state(previous_game.get("state"))
            and previous_schedule
            and previous_schedule.is_finished
            and (not game or game.game_uuid != previous_uuid)
        ):
            self.hass.bus.async_fire("shl_game_ended", {
                "game_uuid": previous_uuid,
                "team_code": self.team_code,
                "home_team": previous_game.get("home_team"),
                "away_team": previous_game.get("away_team"),
            })
        self._all_games = games
        self._selected_game = game
        self._last_discovery = now
        new_uuid = game.game_uuid if game else None
        if new_uuid != self.current_game_uuid:
            self.current_game_uuid = new_uuid
            self._seen_revisions = {}
            self._event_baseline_ready = False
            self._shots_on_goal = {"home": None, "away": None}
            self._last_details = None

    def _details_cached(self, game_uuid: str) -> bool:
        return self._last_details is not None and self._last_details[0] == game_uuid

    def _next_game(self, now: datetime) -> ScheduleGame | None:
        return choose_next_game(
            self._all_games, self.team_code, now, self._selected_game
        )

    def _idle_update_interval(self, now: datetime) -> timedelta:
        """Choose the next idle poll around league starts and active matches."""
        interval = next_idle_poll_interval(
            now,
            (game.start_time for game in self._all_games),
            self.idle_poll_interval,
        )
        interval = min(
            interval,
            effective_standings_interval(
                now,
                self._all_games,
                self.standings_interval,
                self.standings_idle_interval,
            ),
        )
        return interval

    async def _refresh_standings(self, selected: ScheduleGame, now: datetime) -> None:
        """Refresh standings independently so their outage does not block game data."""
        ssgt_uuid = selected.raw.get("ssgtUuid")
        if not ssgt_uuid:
            return
        refresh_interval = effective_standings_interval(
            now,
            self._all_games,
            self.standings_interval,
            self.standings_idle_interval,
        )
        if (
            self._standings is not None
            and self._last_standings_refresh is not None
            and now - self._last_standings_refresh < refresh_interval
        ):
            return
        try:
            response = await self.api.team_standings(str(ssgt_uuid))
        except ShlApiError as err:
            logging.getLogger(__name__).warning("Unable to refresh SHL standings: %s", err)
            self._last_standings_refresh = now
            return
        self._standings = parse_team_standing(response, self.team_code)
        self._last_standings_refresh = now

    @staticmethod
    def _schedule_game_data(game: ScheduleGame | None) -> dict[str, Any] | None:
        if game is None:
            return None
        return {
            **game.raw,
            "gameUuid": game.game_uuid,
            "state": game.state,
            "startDateTime": game.start_time.isoformat() if game.start_time else None,
            "home_team": game.home_team,
            "away_team": game.away_team,
        }

    async def _persist_revisions(self) -> None:
        await self.store.async_save({
            "game_uuid": self.current_game_uuid,
            "seen_revisions": self._seen_revisions,
        })

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _async_update_data(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        try:
            if (
                self._last_discovery is None
                or now - self._last_discovery >= self.discovery_interval
                or (self._selected_game and self._selected_game.is_finished)
            ):
                await self._discover(now)

            selected = self._selected_game
            standings_game = selected or next(
                (game for game in self._all_games if game.raw.get("ssgtUuid")),
                None,
            )
            if standings_game is not None:
                await self._refresh_standings(standings_game, now)
            if selected is None:
                self.update_interval = self._idle_update_interval(now)
                return {
                    "game": None, "next_game": self._schedule_game_data(self._next_game(now)),
                    "standings": self._standings, "events": [],
                    "new_events": [], "goals": [], "last_goal": None,
                    "shots_on_goal": {"home": None, "away": None},
                }

            game_data = self._schedule_game_data(selected) or {}
            next_game = self._schedule_game_data(self._next_game(now))
            changed_events: list[dict[str, Any]] = []
            goals: list[dict[str, Any]] = []
            all_events: list[dict[str, Any]] = []
            last_goal: GoalEvent | None = None
            shots_on_goal: dict[str, int | None] = {"home": None, "away": None}
            live = selected.is_live or selected.started_recently(now)
            # Keep fetching a finished game briefly so its final data is
            # authoritative, and fetch once if it was never cached (for
            # example when Home Assistant was off during the game).
            active = live or (
                selected.is_finished
                and (
                    selected.within_active_window(now)
                    or not self._details_cached(selected.game_uuid)
                )
            )

            if active:
                overview, all_events = await self._fetch_live_data(selected.game_uuid)
                try:
                    stats = await self.api.team_stats(selected.game_uuid)
                    self._shots_on_goal = parse_shots_on_goal(stats)
                except ShlApiError as err:
                    logging.getLogger(__name__).debug(
                        "Unable to refresh SHL shots on goal: %s", err
                    )
                overview_data = parse_game_overview(overview)
                game_data.update(overview_data)
                game_data["home_team"] = {
                    **selected.home_team, **(game_data.get("home_team") or {})
                }
                game_data["away_team"] = {
                    **selected.away_team, **(game_data.get("away_team") or {})
                }
                snapshot = parse_live_snapshot(all_events)
                for key in ("period", "time", "realWorldTime", "updatedTime"):
                    if game_data.get(key) is None and snapshot.get(key) is not None:
                        game_data[key] = snapshot[key]
                for key in ("home_team", "away_team"):
                    if snapshot.get(key):
                        current_team = game_data.get(key) or {}
                        live_team = snapshot[key]
                        overview_team = overview_data.get(key) or {}
                        game_data[key] = {
                            **live_team, **current_team,
                            "score": overview_team.get("score", live_team.get("score", current_team.get("score"))),
                        }
                state = game_data.get("state") or snapshot.get("state") or selected.state
                game_data["state"] = state
                live = is_live_state(state) or (
                    selected.started_recently(now) and not is_finished_state(state)
                )
                self._fire_lifecycle_events(selected.game_uuid, game_data, state)
                changed_events, goals = process_play_by_play(all_events, self._seen_revisions)
                establish_baseline = not self._event_baseline_ready
                if establish_baseline:
                    # On setup or game switch, seed the cursor without replaying
                    # every goal already present in the live feed.
                    changed_events = []
                    goals = []
                    self._event_baseline_ready = True
                if changed_events or establish_baseline:
                    await self._persist_revisions()
                for event in changed_events:
                    payload = {
                        **event,
                        "configured_team_code": self.team_code,
                        "game_uuid": selected.game_uuid,
                        "is_correction": bool(event.get("isCorrection")),
                    }
                    self.hass.bus.async_fire(EVENT_PLAY_BY_PLAY, payload)
                for raw_goal in goals:
                    goal = parse_goal(raw_goal)
                    if goal:
                        self.hass.bus.async_fire(EVENT_GOAL, {
                            **goal.as_dict(),
                            "team_code": goal.team_code or self.team_code,
                            "configured_team_code": self.team_code,
                        })
                goal_models: list[GoalEvent] = [
                    goal for event in all_events if (goal := parse_goal(event)) is not None
                ]
                last_goal = max(
                    goal_models, key=lambda goal: (goal.event_id, goal.revision), default=None
                )
                shots_on_goal = self._shots_on_goal
                self._last_details = (
                    selected.game_uuid,
                    {"game": game_data, "last_goal": last_goal, "shots_on_goal": shots_on_goal},
                )
            elif self._details_cached(selected.game_uuid) and self._last_details is not None:
                # A finished game outside the active window keeps its cached
                # final score, shots, and last goal until the next game starts.
                cached = self._last_details[1]
                game_data = dict(cached["game"])
                last_goal = cached["last_goal"]
                shots_on_goal = cached["shots_on_goal"]

            self.update_interval = (
                self.live_poll_interval
                if live
                else self._idle_update_interval(now)
            )
            return {
                "game": game_data,
                "next_game": next_game,
                "standings": self._standings,
                "events": all_events,
                "new_events": changed_events,
                "goals": goals,
                "last_goal": last_goal.as_dict() if last_goal else None,
                "shots_on_goal": shots_on_goal,
            }
        except ShlApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch_live_data(self, game_uuid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Fetch the overview and full event list concurrently."""
        overview, events = await asyncio.gather(
            self.api.game_overview(game_uuid),
            self.api.play_by_play(game_uuid),
        )
        return overview, events

    def _fire_lifecycle_events(
        self, game_uuid: str, game: dict[str, Any], new_state: Any
    ) -> None:
        """Emit lifecycle events only when the selected game's state changes."""
        if self.data is None:
            # First update after setup or restart: establish a baseline
            # without replaying lifecycle transitions.
            return
        previous = self.data.get("game") or {}
        context = {
            "game_uuid": game_uuid,
            "team_code": self.team_code,
            "home_team": game.get("home_team"),
            "away_team": game.get("away_team"),
        }
        if previous.get("gameUuid") != game_uuid:
            # The selection switched to a newly started game.
            old_state = None
            old_period = 0
        else:
            old_state = previous.get("state")
            old_period = self._int(previous.get("period"))
        new_period = self._int(game.get("period"))
        if old_state != new_state:
            if not is_live_state(old_state) and is_live_state(new_state):
                self.hass.bus.async_fire("shl_game_started", context)
            if is_live_state(old_state) and is_finished_state(new_state):
                self.hass.bus.async_fire("shl_game_ended", context)
                if old_period > 0 and not self._is_period_break(old_state):
                    self.hass.bus.async_fire(
                        "shl_period_ended", {**context, "period": old_period}
                    )
        if new_period > old_period:
            if old_period > 0 and not self._is_period_break(previous.get("state")):
                self.hass.bus.async_fire("shl_period_ended", {**context, "period": old_period})
            self.hass.bus.async_fire("shl_period_started", {**context, "period": new_period})
        elif old_period > 0 and self._is_period_break(new_state) and not self._is_period_break(old_state):
            self.hass.bus.async_fire("shl_period_ended", {**context, "period": old_period})

    @staticmethod
    def _is_period_break(value: Any) -> bool:
        state = normalize_state(value)
        return "break" in state or "intermission" in state
