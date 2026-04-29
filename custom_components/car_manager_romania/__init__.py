"""The Car Manager România integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS, VERSION


@dataclass(slots=True)
class CarManagerRuntimeData:
    """Runtime data for Car Manager România."""

    integration_version: str
    vehicle_count: int = 0


type CarManagerConfigEntry = ConfigEntry[CarManagerRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Set up Car Manager România from a config entry."""

    entry.runtime_data = CarManagerRuntimeData(
        integration_version=VERSION,
        vehicle_count=0,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Unload Car Manager România."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)