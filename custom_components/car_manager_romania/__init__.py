"""The Car Manager România integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_VEHICLES, PLATFORMS, VERSION
from .maintenance import normalize_vehicles


@dataclass(slots=True)
class CarManagerRuntimeData:
    """Runtime data for Car Manager România."""

    integration_version: str
    vehicles: list[dict[str, Any]]


type CarManagerConfigEntry = ConfigEntry[CarManagerRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Set up Car Manager România from a config entry."""

    vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    normalized_vehicles, changed = normalize_vehicles(list(vehicles))

    if changed:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **dict(entry.options),
                CONF_VEHICLES: normalized_vehicles,
            },
        )

    entry.runtime_data = CarManagerRuntimeData(
        integration_version=VERSION,
        vehicles=normalized_vehicles,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    from .notify import async_check_maintenance_notifications

    await async_check_maintenance_notifications(hass, entry)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Unload Car Manager România."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Reload integration when options are updated."""

    await hass.config_entries.async_reload(entry.entry_id)
