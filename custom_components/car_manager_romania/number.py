"""Number entities for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.device_registry import DeviceInfo

from . import CarManagerConfigEntry
from .const import (
    CONF_KM,
    CONF_LAST_SERVICE_KM,
    CONF_SERVICE_INTERVAL_KM,
    CONF_SERVICE_INTERVAL_DAYS,
    CONF_VEHICLES,
    DOMAIN,
)


async def async_setup_entry(hass, entry: CarManagerConfigEntry, async_add_entities):
    entities = []

    for vehicle in entry.runtime_data.vehicles:
        entities.extend(
            [
                VehicleNumber(entry, vehicle, CONF_KM, "Kilometri actuali", 0, 1_000_000),
                VehicleNumber(entry, vehicle, CONF_LAST_SERVICE_KM, "Ultima revizie km", 0, 1_000_000),
                VehicleNumber(entry, vehicle, CONF_SERVICE_INTERVAL_KM, "Interval revizie km", 1000, 50000),
                VehicleNumber(entry, vehicle, CONF_SERVICE_INTERVAL_DAYS, "Interval revizie zile", 30, 1000),
            ]
        )

    async_add_entities(entities)


class VehicleNumber(NumberEntity):
    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        key: str,
        name: str,
        min_v: int,
        max_v: int,
    ):
        self._entry = entry
        self._vehicle = vehicle
        self._key = key
        self._vehicle_id = vehicle["vehicle_id"]

        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{key}"
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_step = 1

    @property
    def native_value(self):
        return int(self._vehicle.get(self._key, 0) or 0)

    async def async_set_native_value(self, value):
        """Persist value in config entry."""

        vehicles = list(
            self._entry.options.get(CONF_VEHICLES, self._entry.runtime_data.vehicles)
        )

        for v in vehicles:
            if v["vehicle_id"] == self._vehicle_id:
                v[self._key] = int(value)

        self._entry.hass.config_entries.async_update_entry(
            self._entry,
            options={CONF_VEHICLES: vehicles},
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._vehicle_id)},
        )