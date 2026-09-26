from __future__ import annotations
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .api import ShlApi
from .const import DOMAIN, EVENT_GOAL, EVENT_PLAY_BY_PLAY
from .coordinator import ShlCoordinator

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp.ClientSession()
    api = ShlApi(session)
    coordinator = ShlCoordinator(hass, api, entry.data.get("team_code", "SKE"))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = (coordinator, session)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator, session = entry.runtime_data
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await session.close()
    return ok
