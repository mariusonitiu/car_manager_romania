"""Text entities for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .device import build_vehicle_device_info

from . import CarManagerConfigEntry
from .const import CONF_CONSUMABLES, CONF_VEHICLES, CONSUMABLE_TYPES, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text entities."""

    entities: list[TextEntity] = []

    for vehicle in entry.runtime_data.vehicles:
        for consumable_key, label in CONSUMABLE_TYPES.items():
            entities.append(
                VehicleConsumableText(
                    hass,
                    entry,
                    vehicle,
                    consumable_key,
                    label,
                )
            )

    async_add_entities(entities)


class VehicleConsumableText(TextEntity):
    """Editable vehicle consumable/specification text."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:car-wrench"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        consumable_key: str,
        label: str,
    ) -> None:
        """Initialize consumable text entity."""

        self._hass = hass
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]
        self._consumable_key = consumable_key

        self._attr_name = label
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_consumable_{consumable_key}"
        )

    @property
    def native_value(self) -> str | None:
        """Return consumable value."""

        consumables = self._vehicle.get(CONF_CONSUMABLES, {})
        value = consumables.get(self._consumable_key)
        return str(value) if value is not None else ""

    async def async_set_value(self, value: str) -> None:
        """Set and persist consumable value."""

        vehicles = list(
            self._entry.options.get(
                CONF_VEHICLES,
                self._entry.runtime_data.vehicles,
            )
        )

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                vehicle.setdefault(CONF_CONSUMABLES, {})[self._consumable_key] = value
                break

        self._hass.config_entries.async_update_entry(
            self._entry,
            options={
                **dict(self._entry.options),
                CONF_VEHICLES: vehicles,
            },
        )
        self._entry.runtime_data.vehicles = list(vehicles)
        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                self._vehicle = vehicle
                break

        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return build_vehicle_device_info(
            self._vehicle,
        )
