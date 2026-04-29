"""Sensor platform for Car Manager România."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import ATTR_INTEGRATION_VERSION, DOMAIN, VERSION


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Car Manager România sensors."""

    async_add_entities(
        [
            CarManagerStatusSensor(entry),
            CarManagerVehicleCountSensor(entry),
        ]
    )


class CarManagerBaseSensor(SensorEntity):
    """Base sensor for Car Manager România."""

    _attr_has_entity_name = True

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize the base sensor."""

        self._entry = entry
        self._entry_id = entry.entry_id
        self._entry_name = entry.data.get("name", "Car Manager România")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._entry_name,
            manufacturer="Car Manager România",
            model="Integration Hub",
            sw_version=VERSION,
        )


class CarManagerStatusSensor(CarManagerBaseSensor):
    """Status sensor for Car Manager România."""

    _attr_name = "Status"
    _attr_icon = "mdi:car-cog"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize the status sensor."""

        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        """Return the status."""

        return "activ"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra attributes."""

        return {
            ATTR_INTEGRATION_VERSION: VERSION,
        }


class CarManagerVehicleCountSensor(CarManagerBaseSensor):
    """Vehicle count sensor for Car Manager România."""

    _attr_name = "Număr autovehicule"
    _attr_icon = "mdi:car-multiple"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize the vehicle count sensor."""

        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vehicle_count"

    @property
    def native_value(self) -> int:
        """Return vehicle count."""

        return self._entry.runtime_data.vehicle_count