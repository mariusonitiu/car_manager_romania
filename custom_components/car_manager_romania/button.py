"""Button platform for Car Manager România."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import CONF_NAME, DOMAIN, VERSION


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""

    entities: list[ButtonEntity] = []

    if entry.runtime_data.rovinieta_coordinator is not None:
        entities.append(CarManagerRovinietaRefreshButton(entry))

    async_add_entities(entities)


class CarManagerRovinietaRefreshButton(ButtonEntity):
    """Button for manual rovinieta refresh."""

    _attr_has_entity_name = True
    _attr_name = "Actualizează rovinieta"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize button."""

        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_rovinieta_refresh"

    @property
    def device_info(self) -> DeviceInfo:
        """Return hub device information."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data.get(CONF_NAME, "Car Manager România"),
            manufacturer="Car Manager România",
            model="Hub",
            sw_version=VERSION,
        )

    async def async_press(self) -> None:
        """Refresh rovinieta data."""

        coordinator = self._entry.runtime_data.rovinieta_coordinator
        if coordinator is None:
            raise HomeAssistantError("Modulul rovinietă nu este configurat.")

        await coordinator.async_request_refresh()
