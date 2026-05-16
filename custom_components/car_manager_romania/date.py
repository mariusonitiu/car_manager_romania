"""Modul pentru entitățile de tip dată."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send

from . import CarManagerConfigEntry
from .const import (
    LEGAL_DATA_SOURCE,
    LEGAL_END_DATE,
    LEGAL_SOURCE_MANUAL,
    LEGAL_START_DATE,
    LEGAL_TYPE_ROVINIETA,
    LEGAL_TYPES,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_TYPES,
    MAINTENANCE_TYPE_SERVICE,
    CONF_REMOVED,
    SIGNAL_VEHICLES_UPDATED,
    SIGNAL_LICENSE_UPDATED,
)
from .device import build_vehicle_device_info
from .license_access import async_license_allows_all_vehicles, vehicle_allowed_by_license
from .legal import get_legal_value, set_legal_value
from .maintenance import get_maintenance_value, parse_date, set_maintenance_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează componentele integrației în Home Assistant."""

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

        for legal_type, label in LEGAL_TYPES.items():
            entities.extend(
                [
                    VehicleLegalDate(
                        hass,
                        entry,
                        vehicle,
                        legal_type,
                        LEGAL_START_DATE,
                        f"{label} începe la",
                        f"{legal_type}_start_date",
                    ),
                    VehicleLegalDate(
                        hass,
                        entry,
                        vehicle,
                        legal_type,
                        LEGAL_END_DATE,
                        f"{label} expiră la",
                        f"{legal_type}_end_date",
                    ),
                ]
            )

    async_add_entities(entities)


class VehicleBaseDate(DateEntity):
    """Clasă pentru vehicul de bază dată."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Funcție internă pentru init."""

        self._hass = hass
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]
        self._license_allows_all_vehicles = False

    async def async_added_to_hass(self) -> None:
        """Gestionează asincron operațiunea pentru added to hass."""

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
        """Funcție internă pentru schedule licență refresh."""

        self.hass.async_create_task(self._async_refresh_license_gate())

    async def _async_refresh_license_gate(self, write_state: bool = True) -> None:
        """Funcție internă pentru refresh licență gate."""

        self._license_allows_all_vehicles = await async_license_allows_all_vehicles(self.hass)
        if write_state:
            self.async_write_ha_state()

    def _handle_vehicles_updated(self, vehicles: list[dict[str, Any]]) -> None:
        """Funcție internă pentru gestionare vehicule updated."""

        for vehicle in vehicles:
            if vehicle.get("vehicle_id") == self._vehicle_id:
                self._vehicle = vehicle
                self.async_write_ha_state()
                break

    @property
    def _blocked_by_license(self) -> bool:
        """Funcție internă pentru blocate by licență."""

        return not vehicle_allowed_by_license(
            self._entry,
            self._vehicle_id,
            self._license_allows_all_vehicles,
        )

    @property
    def available(self) -> bool:
        """Funcție pentru disponibil."""

        return not self._blocked_by_license

    def _raise_if_blocked_by_license(self) -> None:
        """Funcție internă pentru raise if blocate by licență."""

        if self._blocked_by_license:
            raise HomeAssistantError("Autovehicul dezactivat fără licență activă.")

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return build_vehicle_device_info(self._vehicle)

    def _get_vehicles_for_update(self) -> list[dict[str, Any]]:
        """Funcție internă pentru get vehicule for actualizare."""

        return deepcopy(getattr(self._entry.runtime_data, "all_vehicles", self._entry.runtime_data.vehicles))

    async def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Funcție internă pentru persistare vehicule."""

        self._raise_if_blocked_by_license()

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


class VehicleMaintenanceDate(VehicleBaseDate):
    """Clasă pentru vehicul mentenanță dată."""

    _attr_icon = "mdi:calendar-wrench"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        label: str,
    ) -> None:
        """Funcție internă pentru init."""

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
        """Funcție pentru native valoare."""

        return parse_date(
            get_maintenance_value(
                self._vehicle,
                self._maintenance_type,
                MAINTENANCE_LAST_DATE,
            )
        )

    async def async_set_value(self, value: date) -> None:
        """Gestionează asincron operațiunea pentru set valoare."""

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
    """Clasă pentru vehicul legal dată."""

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
        """Funcție internă pentru init."""

        super().__init__(hass, entry, vehicle)
        self._legal_type = legal_type
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{unique_suffix}"

    @property
    def native_value(self) -> date | None:
        """Funcție pentru native valoare."""

        return parse_date(get_legal_value(self._vehicle, self._legal_type, self._field))

    async def async_set_value(self, value: date) -> None:
        """Gestionează asincron operațiunea pentru set valoare."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_legal_value(
                    vehicle,
                    self._legal_type,
                    self._field,
                    value.isoformat(),
                )
                if self._legal_type == LEGAL_TYPE_ROVINIETA:
                    set_legal_value(
                        vehicle,
                        self._legal_type,
                        LEGAL_DATA_SOURCE,
                        LEGAL_SOURCE_MANUAL,
                    )
                break

        await self._persist_vehicles(vehicles)
