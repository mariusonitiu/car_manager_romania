"""Sensor platform for Car Manager România."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import (
    ATTR_INTEGRATION_VERSION,
    CONF_KM,
    CONF_LICENSE_PLATE,
    CONF_NAME,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""

    entities = []

    # Hub sensors
    entities.append(CarManagerStatusSensor(entry))
    entities.append(CarManagerVehicleCountSensor(entry))

    # Vehicle sensors
    for idx, vehicle in enumerate(entry.runtime_data.vehicles):
        entities.append(CarVehicleKmSensor(entry, vehicle, idx))

    async_add_entities(entities)


class BaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: CarManagerConfigEntry):
        self._entry = entry
        self._entry_id = entry.entry_id


class CarManagerStatusSensor(BaseSensor):
    _attr_name = "Status"
    _attr_icon = "mdi:car-cog"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self):
        return "activ"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Car Manager România",
            manufacturer="Car Manager România",
            model="Hub",
            sw_version=VERSION,
        )


class CarManagerVehicleCountSensor(BaseSensor):
    _attr_name = "Număr autovehicule"
    _attr_icon = "mdi:car-multiple"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vehicle_count"

    @property
    def native_value(self):
        return len(self._entry.runtime_data.vehicles)

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
        )


class CarVehicleKmSensor(BaseSensor):
    def __init__(self, entry, vehicle, idx):
        super().__init__(entry)

        self._vehicle = vehicle
        self._idx = idx

        name = vehicle.get(CONF_NAME)

        self._attr_name = f"{name} - Kilometri"
        self._attr_unique_id = f"{entry.entry_id}_{idx}_km"
        self._attr_icon = "mdi:speedometer"

    @property
    def native_value(self):
        return self._vehicle.get(CONF_KM, 0)

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._idx}")},
            name=self._vehicle.get(CONF_NAME),
            manufacturer="Car Manager România",
            model="Autovehicul",
        )