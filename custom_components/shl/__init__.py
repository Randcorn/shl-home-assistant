from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import ShlApi
from .const import DOMAIN, DEFAULT_TEAM_NAME
from .coordinator import PERSISTENCE_VERSION, ShlCoordinator

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = ShlApi(async_get_clientsession(hass))
    store = Store(hass, PERSISTENCE_VERSION, f"{DOMAIN}_{entry.entry_id}_events")
    coordinator = ShlCoordinator(
        hass, api, entry.data.get("team_code", "SKE"), store,
        entry.data.get("team_name", DEFAULT_TEAM_NAME),
        entry.options,
    )
    await coordinator.async_load_state()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so updated polling options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)
