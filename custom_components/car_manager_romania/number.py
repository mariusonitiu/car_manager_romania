"""Number entities for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from .device import build_vehicle_device_info
from .license_access import async_license_allows_all_vehicles, vehicle_allowed_by_license

from . import CarManagerConfigEntry
from .const import (
    CONF_KM,
    COST_AMOUNT,
    LEGAL_COST_TYPES,
    MAINTENANCE_INTERVAL_DAYS,
    MAINTENANCE_INTERVAL_KM,
    MAINTENANCE_LAST_KM,
    MAINTENANCE_TYPES,
    MAINTENANCE_TIME_ONLY_TYPES,
    MAINTENANCE_TYPE_SERVICE,
    CONF_REMOVED,
    SIGNAL_VEHICLES_UPDATED,
    SIGNAL_LICENSE_UPDATED,
)
from .legal import get_legal_value, set_legal_value
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
            entities.append(
                VehicleMaintenanceCostNumber(
                    hass,
                    entry,
                    vehicle,
                    maintenance_type,
                    f"{label} - cost estimat",
                )
            )

        for legal_type, label in LEGAL_COST_TYPES.items():
            entities.append(
                VehicleLegalCostNumber(
                    hass,
                    entry,
                    vehicle,
                    legal_type,
                    f"{label} - cost estimat",
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
        self._license_allows_all_vehicles = False

    async def async_added_to_hass(self) -> None:
        """Subscribe to vehicle and license data updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VEHICLES_UPDATED,
                self._handle_vehicles_updated,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LICENSE_UPDATED,
                self._schedule_license_refresh,
            )
        )
        await self._async_refresh_license_gate(write_state=False)

    @callback
    def _schedule_license_refresh(self) -> None:
        """Schedule a license-gate refresh."""

        self.hass.async_create_task(self._async_refresh_license_gate())

    async def _async_refresh_license_gate(self, write_state: bool = True) -> None:
        """Refresh the cached license gate used by sync entity properties."""

        self._license_allows_all_vehicles = await async_license_allows_all_vehicles(self.hass)
        if write_state:
            self.async_write_ha_state()

    def _handle_vehicles_updated(self, vehicles: list[dict[str, Any]]) -> None:
        """Refresh cached vehicle data and update the entity state."""

        for vehicle in vehicles:
            if vehicle.get("vehicle_id") == self._vehicle_id:
                self._vehicle = vehicle
                self.async_write_ha_state()
                break

    @property
    def _blocked_by_license(self) -> bool:
        """Return True if this vehicle may not expose or edit data."""

        return not vehicle_allowed_by_license(
            self._entry,
            self._vehicle_id,
            self._license_allows_all_vehicles,
        )

    @property
    def available(self) -> bool:
        """Return availability."""

        return not self._blocked_by_license

    def _raise_if_blocked_by_license(self) -> None:
        """Reject edits for vehicles locked by license."""

        if self._blocked_by_license:
            raise HomeAssistantError("Autovehicul dezactivat fără licență activă.")

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return build_vehicle_device_info(
            self._vehicle,
        )

    def _get_vehicles_for_update(self) -> list[dict[str, Any]]:
        """Return the current runtime vehicles for safe incremental updates.

        Values edited from entities are persisted in Home Assistant storage, not in
        config_entry.options. Using entry.options here can reload stale vehicle data
        and overwrite fields previously edited from other entities.
        """

        return deepcopy(getattr(self._entry.runtime_data, "all_vehicles", self._entry.runtime_data.vehicles))

    async def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Persist vehicles in Home Assistant storage and update runtime data."""

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

        from .notify import async_check_maintenance_notifications

        self._hass.async_create_task(
            async_check_maintenance_notifications(self._hass, self._entry)
        )


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

        await self._persist_vehicles(vehicles)


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

        await self._persist_vehicles(vehicles)


class VehicleMaintenanceCostNumber(VehicleBaseNumber):
    """Editable estimated maintenance cost."""

    _attr_icon = "mdi:cash"
    _attr_native_min_value = 0
    _attr_native_max_value = 1_000_000
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "RON"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        name: str,
    ) -> None:
        """Initialize maintenance cost number."""

        super().__init__(hass, entry, vehicle)
        self._maintenance_type = maintenance_type
        self._attr_name = name
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_maintenance_{maintenance_type}_cost"
        )

    @property
    def native_value(self) -> float:
        """Return estimated maintenance cost."""

        return float(get_maintenance_value(self._vehicle, self._maintenance_type, COST_AMOUNT) or 0)

    async def async_set_native_value(self, value: float) -> None:
        """Set and persist estimated maintenance cost."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_maintenance_value(vehicle, self._maintenance_type, COST_AMOUNT, round(float(value), 2))
                break

        await self._persist_vehicles(vehicles)


class VehicleLegalCostNumber(VehicleBaseNumber):
    """Editable estimated legal cost."""

    _attr_icon = "mdi:cash-clock"
    _attr_native_min_value = 0
    _attr_native_max_value = 1_000_000
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "RON"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        legal_type: str,
        name: str,
    ) -> None:
        """Initialize legal cost number."""

        super().__init__(hass, entry, vehicle)
        self._legal_type = legal_type
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_legal_{legal_type}_cost"

    @property
    def native_value(self) -> float:
        """Return estimated legal cost."""

        return float(get_legal_value(self._vehicle, self._legal_type, COST_AMOUNT) or 0)

    async def async_set_native_value(self, value: float) -> None:
        """Set and persist estimated legal cost."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_legal_value(vehicle, self._legal_type, COST_AMOUNT, round(float(value), 2))
                break

        await self._persist_vehicles(vehicles)
