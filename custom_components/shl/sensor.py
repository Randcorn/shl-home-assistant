from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import ShlCoordinator

class ShlGameSensor(CoordinatorEntity[ShlCoordinator], SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_game"
        self._attr_name = "Game"
    @property
    def native_value(self):
        game = (self.coordinator.data or {}).get("game")
        return "No game" if not game else str(game.get("state", "unknown"))
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        game = (self.coordinator.data or {}).get("game") or {}
        home, away = game.get("home_team") or {}, game.get("away_team") or {}
        return {
            "game_uuid": self.coordinator.current_game_uuid,
            "home_team": (home.get("names") or {}).get("full"),
            "away_team": (away.get("names") or {}).get("full"),
            "home_score": home.get("score"), "away_score": away.get("score"),
            "arena": game.get("arenaName"), "round": game.get("roundNumber"),
        }

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator, _session = entry.runtime_data
    async_add_entities([ShlGameSensor(coordinator)])
