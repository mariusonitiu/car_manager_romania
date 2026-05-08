"""Date entities for Car Manager România."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import (
    LEGAL_END_DATE,
    LEGAL_START_DATE,
    LEGAL_TYPE_RCA,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_TYPES,
    MAINTENANCE_TYPE_SERVICE,
)
from .device import build_vehicle_device_info
from .legal import get_legal_value, set_legal_value
from .maintenance import get_maintenance_value, parse_date, set_maintenance_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up date entities."""

    entities: list[DateEntity] = []

    for vehicle in entry.runtime_data.vehicles:
        for maintenance_type, label in MAINTENANCE_TYPES.items():
            entities.append(
                VehicleMaintenanceDate(
                    hass,
                    entry,
                    vehicle,
                    maintenance_type,
                    label,
                )
            )

        entities.extend(
            [
                VehicleLegalDate(
                    hass,
                    entry,
                    vehicle,
                    LEGAL_TYPE_RCA,
                    LEGAL_START_DATE,
                    "RCA începe la",
                    "rca_start_date",
                ),
                VehicleLegalDate(
                    hass,
                    entry,
                    vehicle,
                    LEGAL_TYPE_RCA,
                    LEGAL_END_DATE,
                    "RCA expiră la",
                    "rca_end_date",
                ),
            ]
        )

    async_add_entities(entities)


class VehicleBaseDate(DateEntity):
    """Base date entity for vehicle values."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize base vehicle date."""

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

        return [dict(vehicle) for vehicle in self._entry.runtime_data.vehicles]

    async def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Persist vehicles in Home Assistant storage and refresh runtime data."""

        await self._entry.runtime_data.vehicle_store.async_save_vehicles(vehicles)

        self._entry.runtime_data.vehicles = list(vehicles)
        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                self._vehicle = vehicle
                break

        self.async_write_ha_state()


class VehicleMaintenanceDate(VehicleBaseDate):
    """Editable maintenance date."""

    _attr_icon = "mdi:calendar-wrench"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        label: str,
    ) -> None:
        """Initialize maintenance date."""

        super().__init__(hass, entry, vehicle)
        self._maintenance_type = maintenance_type

        self._attr_name = f"{label} - ultima dată"

        if maintenance_type == MAINTENANCE_TYPE_SERVICE:
            unique_suffix = "service_date"
        else:
            unique_suffix = f"maintenance_{maintenance_type}_last_date"

        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{unique_suffix}"

    @property
    def native_value(self) -> date | None:
        """Return maintenance date."""

        return parse_date(
            get_maintenance_value(
                self._vehicle,
                self._maintenance_type,
                MAINTENANCE_LAST_DATE,
            )
        )

    async def async_set_value(self, value: date) -> None:
        """Set and persist maintenance date."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_maintenance_value(
                    vehicle,
                    self._maintenance_type,
                    MAINTENANCE_LAST_DATE,
                    value.isoformat(),
                )
                break

        await self._persist_vehicles(vehicles)


class VehicleLegalDate(VehicleBaseDate):
    """Editable legal term date."""

    _attr_icon = "mdi:shield-car"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        legal_type: str,
        field: str,
        name: str,
        unique_suffix: str,
    ) -> None:
        """Initialize legal term date."""

        super().__init__(hass, entry, vehicle)
        self._legal_type = legal_type
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{unique_suffix}"

    @property
    def native_value(self) -> date | None:
        """Return legal term date."""

        return parse_date(get_legal_value(self._vehicle, self._legal_type, self._field))

    async def async_set_value(self, value: date) -> None:
        """Set and persist legal term date."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_legal_value(
                    vehicle,
                    self._legal_type,
                    self._field,
                    value.isoformat(),
                )
                break

        await self._persist_vehicles(vehicles)
