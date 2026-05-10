"""Text entities for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import dispatcher_send

from . import CarManagerConfigEntry
from .const import (
    CONF_CONSUMABLES,
    CONSUMABLE_TYPES,
    CASCO_TEXT_FIELDS,
    ITP_TEXT_FIELDS,
    LEGAL_TYPE_CASCO,
    LEGAL_TYPE_ITP,
    LEGAL_TYPE_RCA,
    RCA_TEXT_FIELDS,
    CONF_REMOVED,
    SIGNAL_VEHICLES_UPDATED,
)
from .device import build_vehicle_device_info
from .legal import get_legal_value, set_legal_value


LEGAL_TEXT_FIELDS: dict[str, dict[str, str]] = {
    LEGAL_TYPE_RCA: RCA_TEXT_FIELDS,
    LEGAL_TYPE_CASCO: CASCO_TEXT_FIELDS,
    LEGAL_TYPE_ITP: ITP_TEXT_FIELDS,
}


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

        for legal_type, fields in LEGAL_TEXT_FIELDS.items():
            for field, label in fields.items():
                entities.append(
                    VehicleLegalText(
                        hass,
                        entry,
                        vehicle,
                        legal_type,
                        field,
                        label,
                    )
                )

    async_add_entities(entities)


class VehicleBaseText(TextEntity):
    """Base text entity for vehicle values."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize base vehicle text."""

        self._hass = hass
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return build_vehicle_device_info(self._vehicle)

    def _get_vehicles_for_update(self) -> list[dict[str, Any]]:
        """Return the current runtime vehicles for safe incremental updates.

        Values edited from entities are persisted in Home Assistant storage, not in
        config_entry.options. Using entry.options here can reload stale vehicle data
        and overwrite fields previously edited from other entities.
        """

        return deepcopy(getattr(self._entry.runtime_data, "all_vehicles", self._entry.runtime_data.vehicles))

    async def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Persist vehicles in Home Assistant storage and refresh runtime data."""

        await self._entry.runtime_data.vehicle_store.async_save_vehicles(vehicles)

        active_vehicles = [
            vehicle for vehicle in vehicles
            if isinstance(vehicle, dict) and not bool(vehicle.get(CONF_REMOVED))
        ]
        self._entry.runtime_data.all_vehicles = list(vehicles)
        self._entry.runtime_data.vehicles = active_vehicles
        dispatcher_send(self._hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)
        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                self._vehicle = vehicle
                break

        self.async_write_ha_state()


class VehicleConsumableText(VehicleBaseText):
    """Editable vehicle consumable/specification text."""

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

        super().__init__(hass, entry, vehicle)
        self._consumable_key = consumable_key

        self._attr_name = label
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_consumable_{consumable_key}"
        )

    @property
    def native_value(self) -> str | None:
        """Return consumable value."""

        consumables = self._vehicle.get(CONF_CONSUMABLES, {})
        value = consumables.get(self._consumable_key) if isinstance(consumables, dict) else ""
        return str(value) if value is not None else ""

    async def async_set_value(self, value: str) -> None:
        """Set and persist consumable value."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                vehicle.setdefault(CONF_CONSUMABLES, {})[self._consumable_key] = value
                break

        await self._persist_vehicles(vehicles)


class VehicleLegalText(VehicleBaseText):
    """Editable legal term text field."""

    _attr_icon = "mdi:shield-car"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        legal_type: str,
        field: str,
        label: str,
    ) -> None:
        """Initialize legal term text entity."""

        super().__init__(hass, entry, vehicle)
        self._legal_type = legal_type
        self._field = field
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{legal_type}_{field}"

    @property
    def native_value(self) -> str | None:
        """Return legal term text value."""

        value = get_legal_value(self._vehicle, self._legal_type, self._field)
        return str(value) if value is not None else ""

    async def async_set_value(self, value: str) -> None:
        """Set and persist legal term text value."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_legal_value(vehicle, self._legal_type, self._field, value)
                break

        await self._persist_vehicles(vehicles)
