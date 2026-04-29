"""Config flow for Car Manager România."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_KM,
    CONF_LICENSE_PLATE,
    CONF_NAME,
    CONF_VEHICLES,
    CONF_VIN,
    DEFAULT_NAME,
    DOMAIN,
)


class CarManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Car Manager România."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Initial setup."""

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", DEFAULT_NAME),
                data={
                    "name": user_input.get("name", DEFAULT_NAME),
                    CONF_VEHICLES: [],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional("name", default=DEFAULT_NAME): str,
                }
            ),
        )


class CarManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Car Manager România."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_vehicle"],
        )

    async def async_step_add_vehicle(self, user_input=None):
        if user_input is not None:
            vehicles = list(self._entry.data.get(CONF_VEHICLES, []))

            vehicles.append(
                {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_LICENSE_PLATE: user_input[CONF_LICENSE_PLATE],
                    CONF_VIN: user_input.get(CONF_VIN),
                    CONF_KM: user_input.get(CONF_KM, 0),
                }
            )

            return self.async_create_entry(
                title="OK",
                data={CONF_VEHICLES: vehicles},
            )

        return self.async_show_form(
            step_id="add_vehicle",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_LICENSE_PLATE): str,
                    vol.Optional(CONF_VIN): str,
                    vol.Optional(CONF_KM, default=0): int,
                }
            ),
        )


async def async_get_options_flow(entry):
    return CarManagerOptionsFlow(entry)