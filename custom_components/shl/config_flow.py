"""Config flow for selecting an SHL team by its display name."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ShlApi, ShlApiError
from .const import (
    CONF_TEAM,
    CONF_TEAM_CODE,
    CONF_TEAM_NAME,
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
    DEFAULT_TEAM_CODE,
    DEFAULT_TEAM_NAME,
    DOMAIN,
)
from .discovery import discover_team_options

_LOGGER = logging.getLogger(__name__)


class ShlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add an SHL team by selecting its name from the current SHL team list."""

    VERSION = 1

    def __init__(self) -> None:
        self._team_options: list[dict[str, str]] = []

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        try:
            self._team_options = await discover_team_options(
                ShlApi(async_get_clientsession(self.hass))
            )
        except ShlApiError as err:
            _LOGGER.warning("Unable to load SHL teams for configuration: %s", err)
            errors["base"] = "cannot_connect"

        teams = self._team_options or [
            {"code": DEFAULT_TEAM_CODE, "name": DEFAULT_TEAM_NAME}
        ]
        if user_input is not None:
            selected_code = str(user_input.get(CONF_TEAM, "")).strip().upper()
            selected_team = next(
                (team for team in teams if team["code"] == selected_code), None
            )
            if selected_team is None:
                errors["base"] = "invalid_team"
            else:
                await self.async_set_unique_id(selected_team["code"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=selected_team["name"],
                    data={
                        CONF_TEAM_CODE: selected_team["code"],
                        CONF_TEAM_NAME: selected_team["name"],
                    },
                )

        options = [
            SelectOptionDict(value=team["code"], label=team["name"])
            for team in teams
        ]
        default_team = next(
            (team["code"] for team in teams if team["code"] == DEFAULT_TEAM_CODE),
            teams[0]["code"],
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_TEAM, default=default_team): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Create the options flow for an SHL entry."""
        return ShlOptionsFlow()


class ShlOptionsFlow(config_entries.OptionsFlow):
    """Configure SHL data refresh intervals."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        if CONF_IDLE_POLL_INTERVAL_MINUTES in options:
            try:
                idle_interval_default = int(options[CONF_IDLE_POLL_INTERVAL_MINUTES])
            except (TypeError, ValueError):
                idle_interval_default = DEFAULT_IDLE_POLL_INTERVAL_MINUTES
            idle_interval_default = min(360, max(1, idle_interval_default))
        elif CONF_IDLE_POLL_INTERVAL in options:
            try:
                legacy_idle_seconds = int(
                    options.get(CONF_IDLE_POLL_INTERVAL, DEFAULT_IDLE_POLL_INTERVAL)
                )
            except (TypeError, ValueError):
                legacy_idle_seconds = DEFAULT_IDLE_POLL_INTERVAL
            idle_interval_default = min(
                360,
                max(1, round(legacy_idle_seconds / 60)),
            )
        else:
            idle_interval_default = DEFAULT_IDLE_POLL_INTERVAL_MINUTES
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_LIVE_POLL_INTERVAL,
                    default=options.get(CONF_LIVE_POLL_INTERVAL, DEFAULT_LIVE_POLL_INTERVAL),
                ): NumberSelector(NumberSelectorConfig(
                    min=5, max=120, step=5, unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )),
                vol.Required(
                    CONF_IDLE_POLL_INTERVAL_MINUTES,
                    default=idle_interval_default,
                ): NumberSelector(NumberSelectorConfig(
                    min=1, max=360, step=1, unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )),
                vol.Required(
                    CONF_DISCOVERY_INTERVAL,
                    default=options.get(CONF_DISCOVERY_INTERVAL, DEFAULT_DISCOVERY_INTERVAL),
                ): NumberSelector(NumberSelectorConfig(
                    min=1, max=60, step=1, unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )),
                vol.Required(
                    CONF_STANDINGS_INTERVAL,
                    default=options.get(CONF_STANDINGS_INTERVAL, DEFAULT_STANDINGS_INTERVAL),
                ): NumberSelector(NumberSelectorConfig(
                    min=1, max=240, step=1, unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )),
                vol.Required(
                    CONF_STANDINGS_IDLE_INTERVAL,
                    default=options.get(
                        CONF_STANDINGS_IDLE_INTERVAL,
                        DEFAULT_STANDINGS_IDLE_INTERVAL,
                    ),
                ): NumberSelector(NumberSelectorConfig(
                    min=1, max=360, step=1, unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )),
            }),
        )
