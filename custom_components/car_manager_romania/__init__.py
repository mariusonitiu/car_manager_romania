"""The Car Manager România integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ROVINIETA_PASSWORD,
    CONF_ROVINIETA_SCAN_INTERVAL,
    CONF_ROVINIETA_USERNAME,
    CONF_VEHICLES,
    DEFAULT_ROVINIETA_SCAN_INTERVAL,
    PLATFORMS,
    VERSION,
)
from .maintenance import normalize_vehicles
from .rovinieta.api import ERovinietaApiClient
from .rovinieta.coordinator import CarManagerRovinietaCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CarManagerRuntimeData:
    """Runtime data for Car Manager România."""

    integration_version: str
    vehicles: list[dict[str, Any]]
    rovinieta_coordinator: CarManagerRovinietaCoordinator | None = None


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

    rovinieta_coordinator = await _async_setup_rovinieta_coordinator(hass, entry)

    entry.runtime_data = CarManagerRuntimeData(
        integration_version=VERSION,
        vehicles=normalized_vehicles,
        rovinieta_coordinator=rovinieta_coordinator,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    from .notify import async_check_maintenance_notifications

    await async_check_maintenance_notifications(hass, entry)

    return True


async def _async_setup_rovinieta_coordinator(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> CarManagerRovinietaCoordinator | None:
    """Create and refresh the internal rovinieta coordinator if configured."""

    options = {**dict(entry.data), **dict(entry.options)}
    username = (options.get(CONF_ROVINIETA_USERNAME) or "").strip()
    password = options.get(CONF_ROVINIETA_PASSWORD) or ""

    if not username or not password:
        return None

    session = async_get_clientsession(hass)
    client = ERovinietaApiClient(session, username, password)
    coordinator = CarManagerRovinietaCoordinator(
        hass=hass,
        client=client,
        scan_interval_seconds=int(
            options.get(CONF_ROVINIETA_SCAN_INTERVAL, DEFAULT_ROVINIETA_SCAN_INTERVAL)
            or DEFAULT_ROVINIETA_SCAN_INTERVAL
        ),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Nu am putut actualiza datele e-rovinieta.ro la pornire: %s",
            err,
        )

    return coordinator


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
