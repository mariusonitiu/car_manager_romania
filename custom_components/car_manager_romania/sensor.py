"""Sensor platform for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import (
    ATTR_INTEGRATION_VERSION,
    CONF_KM,
    CONF_LICENSE_PLATE,
    CONF_NAME,
    CONF_VIN,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Car Manager România sensors."""

    entities: list[SensorEntity] = [
        CarManagerStatusSensor(entry),
        CarManagerVehicleCountSensor(entry),
    ]

    for vehicle in entry.runtime_data.vehicles:
        entities.append(CarVehicleKmSensor(entry, vehicle))
        entities.append(CarVehicleStatusSensor(entry, vehicle))

    async_add_entities(entities)


class CarManagerBaseSensor(SensorEntity):
    """Base sensor for Car Manager România."""

    _attr_has_entity_name = True

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize base sensor."""

        self._entry = entry
        self._entry_id = entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return hub device information."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._entry.data.get(CONF_NAME, "Car Manager România"),
            manufacturer="Car Manager România",
            model="Hub",
            sw_version=VERSION,
        )


class CarManagerStatusSensor(CarManagerBaseSensor):
    """Status sensor for Car Manager România."""

    _attr_name = "Status"
    _attr_icon = "mdi:car-cog"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize status sensor."""

        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        """Return status."""

        return "activ"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return attributes."""

        return {
            ATTR_INTEGRATION_VERSION: VERSION,
        }


class CarManagerVehicleCountSensor(CarManagerBaseSensor):
    """Vehicle count sensor for Car Manager România."""

    _attr_name = "Număr autovehicule"
    _attr_icon = "mdi:car-multiple"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize vehicle count sensor."""

        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vehicle_count"

    @property
    def native_value(self) -> int:
        """Return vehicle count."""

        return len(self._entry.runtime_data.vehicles)


class CarVehicleBaseSensor(SensorEntity):
    """Base vehicle sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize vehicle base sensor."""

        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._vehicle_id)},
            name=self._vehicle.get(CONF_NAME, "Autovehicul"),
            manufacturer="Car Manager România",
            model="Autovehicul",
            serial_number=self._vehicle.get(CONF_VIN) or None,
        )


class CarVehicleKmSensor(CarVehicleBaseSensor):
    """Vehicle kilometers sensor."""

    _attr_name = "Kilometri"
    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize vehicle kilometers sensor."""

        super().__init__(entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_km"

    @property
    def native_value(self) -> int:
        """Return current kilometers."""

        return int(self._vehicle.get(CONF_KM, 0))


class CarVehicleStatusSensor(CarVehicleBaseSensor):
    """Vehicle status sensor."""

    _attr_name = "Status"
    _attr_icon = "mdi:car-info"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize vehicle status sensor."""

        super().__init__(entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_status"

    @property
    def native_value(self) -> str:
        """Return vehicle status."""

        return "configurat"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return vehicle attributes."""

        attributes = {
            CONF_NAME: self._vehicle.get(CONF_NAME, ""),
            CONF_LICENSE_PLATE: self._vehicle.get(CONF_LICENSE_PLATE, ""),
        }

        if self._vehicle.get(CONF_VIN):
            attributes[CONF_VIN] = self._vehicle[CONF_VIN]

        return attributes