"""Config flow for Car Manager România."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.util import slugify

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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> CarManagerOptionsFlow:
        """Create the options flow."""

        return CarManagerOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Initial setup."""

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            name = user_input.get(CONF_NAME, DEFAULT_NAME).strip() or DEFAULT_NAME

            return self.async_create_entry(
                title=name,
                data={
                    CONF_NAME: name,
                    CONF_VEHICLES: [],
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }
            ),
        )


class CarManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Car Manager România."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        self._entry = entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Show options menu."""

        return self.async_show_menu(
            step_id="init",
            menu_options=["add_vehicle"],
        )

    async def async_step_add_vehicle(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Add a vehicle."""

        if user_input is not None:
            existing_vehicles = list(
                self._entry.options.get(
                    CONF_VEHICLES,
                    self._entry.data.get(CONF_VEHICLES, []),
                )
            )

            vehicle_name = user_input[CONF_NAME].strip()
            license_plate = user_input[CONF_LICENSE_PLATE].strip().upper()
            vin = (user_input.get(CONF_VIN) or "").strip().upper()
            km = user_input.get(CONF_KM, 0)

            vehicle_id = self._generate_vehicle_id(
                existing_vehicles,
                license_plate,
                vehicle_name,
            )

            existing_vehicles.append(
                {
                    "vehicle_id": vehicle_id,
                    CONF_NAME: vehicle_name,
                    CONF_LICENSE_PLATE: license_plate,
                    CONF_VIN: vin,
                    CONF_KM: km,
                }
            )

            return self.async_create_entry(
                title="",
                data={
                    **dict(self._entry.options),
                    CONF_VEHICLES: existing_vehicles,
                },
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

    @staticmethod
    def _generate_vehicle_id(
        vehicles: list[dict[str, Any]],
        license_plate: str,
        vehicle_name: str,
    ) -> str:
        """Generate a stable vehicle ID."""

        base_id = slugify(license_plate) or slugify(vehicle_name) or "autovehicul"
        existing_ids = {vehicle.get("vehicle_id") for vehicle in vehicles}

        if base_id not in existing_ids:
            return base_id

        counter = 2
        while f"{base_id}_{counter}" in existing_ids:
            counter += 1

        return f"{base_id}_{counter}"