"""The Car Manager România integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

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
from .storage import CarManagerVehicleStore, merge_vehicle_sources

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CarManagerRuntimeData:
    """Runtime data for Car Manager România."""

    integration_version: str
    vehicles: list[dict[str, Any]]
    vehicle_store: CarManagerVehicleStore
    rovinieta_coordinator: CarManagerRovinietaCoordinator | None = None


type CarManagerConfigEntry = ConfigEntry[CarManagerRuntimeData]


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and notify the user how to add it."""

    frontend_path = Path(__file__).parent / "frontend"
    if not frontend_path.exists():
        return

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/car_manager_romania",
                    str(frontend_path),
                    True,
                )
            ]
        )
    except Exception:  # noqa: BLE001
        try:
            hass.http.async_register_static_path(
                "/car_manager_romania",
                str(frontend_path),
                True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Nu am putut publica fișierul cardului Lovelace: %s", err)
            return

    try:
        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            hass,
            "Cardul Lovelace Car Manager România este disponibil.\n\n"
            "Dacă nu apare automat în interfață, adaugă manual resursa:\n\n"
            "URL: `/car_manager_romania/car-manager-romania-card.js`\n\n"
            "Tip: `JavaScript Module`\n\n"
            "Apoi adaugă un card manual cu:\n\n"
            "`type: custom:car-manager-romania-card`",
            title="Car Manager România - card Lovelace",
            notification_id="car_manager_romania_lovelace_card",
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Nu am putut crea notificarea pentru cardul Lovelace: %s", err)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Set up Car Manager România from a config entry."""

    vehicle_store = CarManagerVehicleStore(hass)
    stored_vehicles = await vehicle_store.async_get_vehicles()

    option_vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
    normalized_vehicles, changed = normalize_vehicles(list(vehicles))

    if changed or normalized_vehicles != stored_vehicles:
        await vehicle_store.async_save_vehicles(normalized_vehicles)

    rovinieta_coordinator = await _async_setup_rovinieta_coordinator(hass, entry)

    entry.runtime_data = CarManagerRuntimeData(
        integration_version=VERSION,
        vehicles=normalized_vehicles,
        vehicle_store=vehicle_store,
        rovinieta_coordinator=rovinieta_coordinator,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await _async_register_frontend(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    from .notify import async_check_maintenance_notifications

    await async_check_maintenance_notifications(hass, entry)

    def _schedule_notification_check(*_: Any) -> None:
        """Schedule a notification check without blocking Home Assistant."""

        hass.async_create_task(async_check_maintenance_notifications(hass, entry))

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _schedule_notification_check,
            timedelta(hours=6),
        )
    )

    if rovinieta_coordinator is not None:
        entry.async_on_unload(
            rovinieta_coordinator.async_add_listener(_schedule_notification_check)
        )

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
