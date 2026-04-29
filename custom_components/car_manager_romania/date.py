"""Date entities for Car Manager România."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.date import DateEntity
from homeassistant.helpers.device_registry import DeviceInfo

from . import CarManagerConfigEntry
from .const import CONF_LAST_SERVICE_DATE, CONF_VEHICLES, DOMAIN


async def async_setup_entry(hass, entry: CarManagerConfigEntry, async_add_entities):
    entities = []

    for vehicle in entry.runtime_data.vehicles:
        entities.append(VehicleServiceDate(entry, vehicle))

    async_add_entities(entities)


class VehicleServiceDate(DateEntity):
    def __init__(self, entry: CarManagerConfigEntry, vehicle: dict[str, Any]):
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]

        self._attr_name = "Ultima revizie dată"
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_service_date"

    @property
    def native_value(self):
        raw = self._vehicle.get(CONF_LAST_SERVICE_DATE)
        if not raw:
            return None

        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            return None

    async def async_set_value(self, value: date):
        """Persist date."""

        vehicles = list(
            self._entry.options.get(CONF_VEHICLES, self._entry.runtime_data.vehicles)
        )

        for v in vehicles:
            if v["vehicle_id"] == self._vehicle_id:
                v[CONF_LAST_SERVICE_DATE] = value.isoformat()

        self._entry.hass.config_entries.async_update_entry(
            self._entry,
            options={CONF_VEHICLES: vehicles},
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._vehicle_id)},
        )