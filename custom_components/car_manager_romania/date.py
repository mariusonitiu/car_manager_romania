"""Date entities for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import (
    CONF_VEHICLES,
    DOMAIN,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_TYPES,
    MAINTENANCE_TYPE_SERVICE,
)
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

    async_add_entities(entities)


class VehicleMaintenanceDate(DateEntity):
    """Editable maintenance date."""

    _attr_has_entity_name = True
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

        self._hass = hass
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]
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

    def _get_vehicles_for_update(self) -> list[dict[str, Any]]:
        """Return a safe vehicles copy from options or runtime data."""

        vehicles = self._entry.options.get(
            CONF_VEHICLES,
            self._entry.runtime_data.vehicles,
        )

        return deepcopy(list(vehicles))

    def _sync_current_vehicle_reference(
        self,
        vehicles: list[dict[str, Any]],
    ) -> None:
        """Keep the current entity object in sync after persisting."""

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                self._vehicle = vehicle
                break

    def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Persist vehicles in config entry options and update runtime data."""

        safe_vehicles = deepcopy(vehicles)

        self._hass.config_entries.async_update_entry(
            self._entry,
            options={
                **dict(self._entry.options),
                CONF_VEHICLES: safe_vehicles,
            },
        )

        # Actualizăm imediat runtime_data, pentru ca entitățile calculate să vadă
        # noile valori până la următorul reload/restart al integrării.
        self._entry.runtime_data.vehicles = deepcopy(safe_vehicles)
        self._sync_current_vehicle_reference(self._entry.runtime_data.vehicles)

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

        self._persist_vehicles(vehicles)
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._vehicle_id)},
        )
