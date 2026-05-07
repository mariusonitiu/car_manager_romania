"""Number entities for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .device import build_vehicle_device_info

from . import CarManagerConfigEntry
from .const import (
    CONF_KM,
    CONF_VEHICLES,
    DOMAIN,
    MAINTENANCE_INTERVAL_DAYS,
    MAINTENANCE_INTERVAL_KM,
    MAINTENANCE_LAST_KM,
    MAINTENANCE_TYPES,
    MAINTENANCE_TIME_ONLY_TYPES,
    MAINTENANCE_TYPE_SERVICE,
)
from .maintenance import get_maintenance_value, set_maintenance_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""

    entities: list[NumberEntity] = []

    for vehicle in entry.runtime_data.vehicles:
        entities.append(
            VehicleKmNumber(
                hass,
                entry,
                vehicle,
            )
        )

        for maintenance_type, label in MAINTENANCE_TYPES.items():
            if maintenance_type not in MAINTENANCE_TIME_ONLY_TYPES:
                entities.extend(
                    [
                        VehicleMaintenanceNumber(
                            hass,
                            entry,
                            vehicle,
                            maintenance_type,
                            MAINTENANCE_LAST_KM,
                            f"{label} - ultimul schimb km",
                            0,
                            1_000_000,
                        ),
                        VehicleMaintenanceNumber(
                            hass,
                            entry,
                            vehicle,
                            maintenance_type,
                            MAINTENANCE_INTERVAL_KM,
                            f"{label} - interval km",
                            0,
                            1_000_000,
                        ),
                    ]
                )

            entities.append(
                VehicleMaintenanceNumber(
                    hass,
                    entry,
                    vehicle,
                    maintenance_type,
                    MAINTENANCE_INTERVAL_DAYS,
                    f"{label} - interval zile",
                    0,
                    5000,
                )
            )

    async_add_entities(entities)


class VehicleBaseNumber(NumberEntity):
    """Base number entity for vehicle values."""

    _attr_has_entity_name = True
    _attr_native_step = 1

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize base vehicle number."""

        self._hass = hass
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return build_vehicle_device_info(
            self._vehicle,
        )

    def _get_vehicles_for_update(self) -> list[dict[str, Any]]:
        """Return vehicles from options or runtime data."""

        return list(
            self._entry.options.get(
                CONF_VEHICLES,
                self._entry.runtime_data.vehicles,
            )
        )

    def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Persist vehicles in config entry options and update runtime data."""

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


class VehicleKmNumber(VehicleBaseNumber):
    """Editable current vehicle kilometers."""

    _attr_name = "Kilometri actuali"
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = 0
    _attr_native_max_value = 1_000_000

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize current km number."""

        super().__init__(hass, entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{CONF_KM}"

    @property
    def native_value(self) -> int:
        """Return current kilometers."""

        return int(self._vehicle.get(CONF_KM, 0) or 0)

    async def async_set_native_value(self, value: float) -> None:
        """Set and persist current kilometers."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                vehicle[CONF_KM] = int(value)
                break

        self._persist_vehicles(vehicles)


class VehicleMaintenanceNumber(VehicleBaseNumber):
    """Editable maintenance number."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        field: str,
        name: str,
        min_value: int,
        max_value: int,
    ) -> None:
        """Initialize maintenance number."""

        super().__init__(hass, entry, vehicle)

        self._maintenance_type = maintenance_type
        self._field = field

        self._attr_name = name
        self._attr_icon = "mdi:wrench"
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value

        if maintenance_type == MAINTENANCE_TYPE_SERVICE:
            legacy_unique_id_map = {
                MAINTENANCE_LAST_KM: "last_service_km",
                MAINTENANCE_INTERVAL_KM: "service_interval_km",
                MAINTENANCE_INTERVAL_DAYS: "service_interval_days",
            }
            unique_suffix = legacy_unique_id_map[field]
        else:
            unique_suffix = f"maintenance_{maintenance_type}_{field}"

        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{unique_suffix}"

    @property
    def native_value(self) -> int:
        """Return maintenance number value."""

        return int(
            get_maintenance_value(
                self._vehicle,
                self._maintenance_type,
                self._field,
            )
            or 0
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set and persist maintenance number value."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_maintenance_value(
                    vehicle,
                    self._maintenance_type,
                    self._field,
                    int(value),
                )
                break

        self._persist_vehicles(vehicles)
