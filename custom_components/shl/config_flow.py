from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_TEAM_CODE, CONF_TEAM_NAME, DEFAULT_TEAM_CODE, DEFAULT_TEAM_NAME

class ShlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_TEAM_NAME], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_TEAM_CODE, default=DEFAULT_TEAM_CODE): str,
                vol.Required(CONF_TEAM_NAME, default=DEFAULT_TEAM_NAME): str,
            }),
        )
