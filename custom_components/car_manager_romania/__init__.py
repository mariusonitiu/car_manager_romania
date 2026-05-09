"""The Car Manager România integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import timedelta
import inspect
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
    DOMAIN,
    PLATFORMS,
    VERSION,
)
from .maintenance import normalize_vehicles
from .rovinieta.api import ERovinietaApiClient
from .rovinieta.coordinator import CarManagerRovinietaCoordinator
from .storage import CarManagerVehicleStore, merge_vehicle_sources

_LOGGER = logging.getLogger(__name__)

LOVELACE_CARD_URL = "/car_manager_romania/car-manager-romania-card.js"
LOVELACE_CARD_NOTIFICATION_ID = "car_manager_romania_lovelace_card"


@dataclass(slots=True)
class CarManagerRuntimeData:
    """Runtime data for Car Manager România."""

    integration_version: str
    vehicles: list[dict[str, Any]]
    vehicle_store: CarManagerVehicleStore
    rovinieta_coordinator: CarManagerRovinietaCoordinator | None = None


type CarManagerConfigEntry = ConfigEntry[CarManagerRuntimeData]


def _normalize_resource_url(value: Any) -> str:
    """Normalize a Lovelace resource URL for comparison."""

    if value is None:
        return ""

    normalized = str(value).strip()
    if not normalized:
        return ""

    # Lovelace resources are often versioned with query strings such as ?v=0.7.1.
    normalized = normalized.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return normalized


def _resource_url_matches(value: Any) -> bool:
    """Return True if a Lovelace resource URL points to this integration card."""

    normalized = _normalize_resource_url(value)
    expected = _normalize_resource_url(LOVELACE_CARD_URL)
    return normalized == expected or normalized.endswith(expected)


async def _maybe_await(value: Any) -> Any:
    """Await a value only when it is awaitable."""

    if inspect.isawaitable(value):
        return await value
    return value


def _extract_resource_urls(value: Any) -> list[str]:
    """Extract resource URLs from common Lovelace resource structures."""

    urls: list[str] = []

    if value is None:
        return urls

    if isinstance(value, str):
        return [value]

    if isinstance(value, dict):
        resource_url = value.get("url")
        if resource_url is not None:
            urls.append(str(resource_url))

        for item in value.values():
            urls.extend(_extract_resource_urls(item))

        return urls

    if isinstance(value, (list, tuple, set)):
        for item in value:
            urls.extend(_extract_resource_urls(item))
        return urls

    resource_url = getattr(value, "url", None)
    if resource_url is not None:
        urls.append(str(resource_url))

    return urls


async def _async_lovelace_card_resource_exists(hass: HomeAssistant) -> bool:
    """Check whether the Lovelace resource for the bundled card is already registered."""

    try:
        lovelace_data = hass.data.get("lovelace")
        candidates: list[Any] = []

        if lovelace_data is not None:
            if isinstance(lovelace_data, dict):
                candidates.extend(
                    candidate
                    for candidate in (
                        lovelace_data.get("resources"),
                        lovelace_data.get("resource_collection"),
                    )
                    if candidate is not None
                )
            else:
                candidates.extend(
                    candidate
                    for candidate in (
                        getattr(lovelace_data, "resources", None),
                        getattr(lovelace_data, "resource_collection", None),
                    )
                    if candidate is not None
                )

        # Fallbackuri defensive pentru schimbări interne Home Assistant.
        for key, value in hass.data.items():
            if "lovelace" in str(key).lower() and "resource" in str(key).lower():
                candidates.append(value)

        seen_candidate_ids: set[int] = set()
        for candidate in candidates:
            candidate_id = id(candidate)
            if candidate_id in seen_candidate_ids:
                continue
            seen_candidate_ids.add(candidate_id)

            for url in _extract_resource_urls(candidate):
                if _resource_url_matches(url):
                    return True

            for method_name in ("async_items", "items", "async_get_info"):
                method = getattr(candidate, method_name, None)
                if method is None or not callable(method):
                    continue

                try:
                    result = await _maybe_await(method())
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug(
                        "Nu am putut citi resursele Lovelace prin %s: %s",
                        method_name,
                        err,
                    )
                    continue

                for url in _extract_resource_urls(result):
                    if _resource_url_matches(url):
                        return True

    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Nu am putut verifica resursa Lovelace a cardului: %s", err)

    return False


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and notify the user only when the resource is missing."""

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

        if await _async_lovelace_card_resource_exists(hass):
            persistent_notification.async_dismiss(hass, LOVELACE_CARD_NOTIFICATION_ID)
            return

        persistent_notification.async_create(
            hass,
            "Cardul Lovelace Car Manager România este disponibil.\n\n"
            "Dacă nu apare automat în interfață, adaugă manual resursa:\n\n"
            f"URL: `{LOVELACE_CARD_URL}`\n\n"
            "Tip: `JavaScript Module`\n\n"
            "Apoi adaugă un card manual cu:\n\n"
            "`type: custom:car-manager-romania-card`",
            title="Car Manager România - card Lovelace",
            notification_id=LOVELACE_CARD_NOTIFICATION_ID,
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

    scan_interval_days = options.get(
        CONF_ROVINIETA_SCAN_INTERVAL,
        DEFAULT_ROVINIETA_SCAN_INTERVAL,
    )
    try:
        scan_interval_days = int(scan_interval_days)
    except (TypeError, ValueError):
        scan_interval_days = DEFAULT_ROVINIETA_SCAN_INTERVAL

    scan_interval_days = max(1, scan_interval_days)

    client = ERovinietaApiClient(
        async_get_clientsession(hass),
        username=username,
        password=password,
    )
    coordinator = CarManagerRovinietaCoordinator(
        hass,
        client,
        scan_interval=timedelta(days=scan_interval_days),
    )

    await coordinator.async_config_entry_first_refresh()
    return coordinator


async def async_update_options(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Handle options update."""

    vehicle_store = entry.runtime_data.vehicle_store
    stored_vehicles = await vehicle_store.async_get_vehicles()
    option_vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    merged_vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
    normalized_vehicles, changed = normalize_vehicles(list(merged_vehicles))

    if changed or normalized_vehicles != stored_vehicles:
        await vehicle_store.async_save_vehicles(normalized_vehicles)

    entry.runtime_data.vehicles = normalized_vehicles

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Unload a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
