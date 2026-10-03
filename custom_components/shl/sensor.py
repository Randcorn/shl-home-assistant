"""Home Assistant sensors backed by the SHL coordinator."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShlCoordinator
from .discovery import team_codes


def _team_name(team: dict[str, Any]) -> str | None:
    names = team.get("names") if isinstance(team.get("names"), dict) else {}
    return (
        names.get("full") or names.get("fullName") or team.get("teamName")
        or team.get("name") or team.get("teamCode") or team.get("code")
    )


def _game_score(game: dict[str, Any]) -> tuple[Any, Any]:
    home = game.get("home_team") or game.get("homeTeam") or {}
    away = game.get("away_team") or game.get("awayTeam") or {}
    return home.get("score", game.get("homeGoals")), away.get("score", game.get("awayGoals"))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class ShlSensor(CoordinatorEntity[ShlCoordinator], SensorEntity):
    """Shared device metadata for a configured SHL team."""

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.team_code)},
            name=self.coordinator.team_name,
            manufacturer="SHL",
            model="Team game tracker",
        )


class ShlGameSensor(ShlSensor):
    """Game state with teams and arena as attributes."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:hockey-puck"

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_game"
        self._attr_name = "Game"

    @property
    def native_value(self) -> str:
        game = (self.coordinator.data or {}).get("game")
        return "No game" if not game else str(game.get("state", "unknown"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        game = data.get("game") or {}
        home = game.get("home_team") or {}
        away = game.get("away_team") or {}
        venue = game.get("venueInfo") if isinstance(game.get("venueInfo"), dict) else {}
        if self.coordinator.team_code in team_codes(home):
            opponent = _team_name(away)
        elif self.coordinator.team_code in team_codes(away):
            opponent = _team_name(home)
        else:
            opponent = None
        next_game = data.get("next_game") or {}
        attributes = {
            "game_uuid": self.coordinator.current_game_uuid,
            "team_code": self.coordinator.team_code,
            "home_team": _team_name(home),
            "away_team": _team_name(away),
            "opponent": opponent,
            "home_score": _game_score(game)[0],
            "away_score": _game_score(game)[1],
            "period": game.get("period"),
            "clock": game.get("time") or game.get("gameTime"),
            "arena": game.get("arenaName") or venue.get("name"),
            "round": game.get("roundNumber"),
            "start_time": game.get("startDateTime"),
            "last_goal": data.get("last_goal"),
        }
        if next_game.get("gameUuid") != game.get("gameUuid"):
            attributes["next_game_uuid"] = next_game.get("gameUuid")
            attributes["next_game_start"] = next_game.get("startDateTime")
        return attributes


class ShlScoreSensor(ShlSensor):
    """Current match score for the configured team's game."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:scoreboard"

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_score"
        self._attr_name = "Score"

    @property
    def native_value(self) -> str:
        game = (self.coordinator.data or {}).get("game") or {}
        if not game:
            return "No game"
        home, away = _game_score(game)
        if home is None or away is None:
            return "-"
        return f"{home} - {away}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        game = (self.coordinator.data or {}).get("game") or {}
        home_team = game.get("home_team") or {}
        away_team = game.get("away_team") or {}
        return {
            "home_team": _team_name(home_team),
            "away_team": _team_name(away_team),
            "home_score": _game_score(game)[0],
            "away_score": _game_score(game)[1],
        }


class ShlLastGoalSensor(ShlSensor):
    """Most recent goal in the selected game."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bullseye-arrow"

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_last_goal"
        self._attr_name = "Last goal"

    @property
    def native_value(self) -> str | None:
        goal = (self.coordinator.data or {}).get("last_goal")
        if not goal:
            return None
        return goal.get("player_name") or goal.get("team_name") or "Goal"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("last_goal") or {}


class ShlShotsOnGoalSensor(ShlSensor):
    """Home and away shots on goal for the selected game."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_shots_on_goal"
        self._attr_name = "Shots on goal"
        self._attr_icon = "mdi:target"

    @property
    def native_value(self) -> str:
        shots = (self.coordinator.data or {}).get("shots_on_goal") or {}
        home, away = _int_or_none(shots.get("home")), _int_or_none(shots.get("away"))
        return f"{home} - {away}" if home is not None and away is not None else "-"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        game = (self.coordinator.data or {}).get("game") or {}
        shots = (self.coordinator.data or {}).get("shots_on_goal") or {}
        return {
            "home_team": _team_name(game.get("home_team") or {}),
            "away_team": _team_name(game.get("away_team") or {}),
            "home_shots_on_goal": shots.get("home"),
            "away_shots_on_goal": shots.get("away"),
        }


class ShlPointsSensor(ShlSensor):
    """Current regular-season league points for the configured team."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:star-circle"

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_points"
        self._attr_name = "Points"

    @property
    def native_value(self) -> int | None:
        return _int_or_none(((self.coordinator.data or {}).get("standings") or {}).get("points"))


class ShlLeaguePositionSensor(ShlSensor):
    """Current position in the SHL league table."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:trophy"

    def __init__(self, coordinator: ShlCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_league_position"
        self._attr_name = "League position"

    @property
    def native_value(self) -> int | None:
        return _int_or_none(((self.coordinator.data or {}).get("standings") or {}).get("rank"))


STANDING_METRICS = (
    ("games_played", "Games played", "mdi:calendar-check"),
    ("wins", "Wins", "mdi:check-circle"),
    ("overtime_wins", "Overtime wins", "mdi:clock-check"),
    ("overtime_losses", "Overtime losses", "mdi:clock-alert"),
    ("losses", "Losses", "mdi:close-circle"),
    ("goals_for", "Goals for", "mdi:target"),
    ("goals_against", "Goals against", "mdi:shield-outline"),
    ("goal_difference", "Goal difference", "mdi:plus-minus-variant"),
    ("rank_diff", "Position change", "mdi:swap-vertical"),
    ("teams", "Teams in league", "mdi:account-group"),
)


class ShlStandingMetricSensor(ShlSensor):
    """One numeric standings field exposed as its own sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ShlCoordinator, key: str, name: str, icon: str
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{DOMAIN}_{coordinator.team_code}_{key}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def native_value(self) -> int | None:
        standings = (self.coordinator.data or {}).get("standings") or {}
        return _int_or_none(standings.get(self._key))


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator: ShlCoordinator = entry.runtime_data
    entity_registry = er.async_get(hass)
    for side in ("home", "away"):
        old_unique_id = f"{DOMAIN}_{coordinator.team_code}_{side}_shots_on_goal"
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)
    async_add_entities([
        ShlGameSensor(coordinator),
        ShlScoreSensor(coordinator),
        ShlLastGoalSensor(coordinator),
        ShlShotsOnGoalSensor(coordinator),
        ShlPointsSensor(coordinator),
        ShlLeaguePositionSensor(coordinator),
        *(ShlStandingMetricSensor(coordinator, key, name, icon)
          for key, name, icon in STANDING_METRICS),
    ])
