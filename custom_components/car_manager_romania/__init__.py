"""The Car Manager România integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import timedelta
import inspect
import logging
from typing import Any

import voluptuous as vol


from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import slugify

from .const import (
    CONF_KM,
    CONF_LICENSE_PLATE,
    CONF_NAME,
    CONF_REMOVED,
    CONF_ROVINIETA_PASSWORD,
    CONF_ROVINIETA_SCAN_INTERVAL,
    CONF_ROVINIETA_USERNAME,
    CONF_VEHICLES,
    CONF_VEHICLE_ID,
    CONF_VIN,
    DEFAULT_ROVINIETA_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_ADD_VEHICLE,
    SERVICE_REMOVE_VEHICLE,
    SERVICE_RESTORE_VEHICLE,
    SERVICE_RESTORE_ALL_VEHICLES,
    SIGNAL_VEHICLES_UPDATED,
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
    all_vehicles: list[dict[str, Any]]
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

    candidates: list[Any] = []

    try:
        lovelace_data = hass.data.get("lovelace")

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

        # Cea mai importantă verificare: resursele Lovelace în mod storage sunt
        # persistate în .storage/lovelace_resources și nu sunt întotdeauna încărcate
        # în hass.data în momentul în care se setează integrarea.
        try:
            from homeassistant.helpers.storage import Store

            stored_resources = await Store(
                hass,
                1,
                "lovelace_resources",
            ).async_load()
            if stored_resources is not None:
                candidates.append(stored_resources)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "Nu am putut citi .storage/lovelace_resources pentru verificarea cardului: %s",
                err,
            )

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



ADD_VEHICLE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_LICENSE_PLATE, default=""): str,
        vol.Optional(CONF_VIN, default=""): str,
        vol.Optional(CONF_KM, default=0): vol.Coerce(int),
    }
)

REMOVE_VEHICLE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
    }
)

RESTORE_VEHICLE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
    }
)

RESTORE_ALL_VEHICLES_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
    }
)


def _active_vehicles(vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return vehicles that are not marked as removed."""

    return [
        vehicle
        for vehicle in vehicles
        if isinstance(vehicle, dict) and not bool(vehicle.get(CONF_REMOVED))
    ]


def _generate_vehicle_id(vehicles: list[dict[str, Any]], license_plate: str, vehicle_name: str) -> str:
    """Generate a stable internal vehicle ID."""

    base_id = slugify(license_plate) or slugify(vehicle_name) or "autovehicul"
    existing_ids = {str(vehicle.get("vehicle_id")) for vehicle in vehicles if vehicle.get("vehicle_id")}

    if base_id not in existing_ids:
        return base_id

    counter = 2
    while f"{base_id}_{counter}" in existing_ids:
        counter += 1

    return f"{base_id}_{counter}"


def _find_loaded_config_entry(hass: HomeAssistant, entry_id: str | None = None) -> CarManagerConfigEntry:
    """Return the loaded config entry that should receive service changes."""

    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        entries = [entry for entry in entries if entry.entry_id == entry_id]

    for entry in entries:
        runtime_data = getattr(entry, "runtime_data", None)
        if runtime_data is not None and isinstance(runtime_data, CarManagerRuntimeData):
            return entry  # type: ignore[return-value]

    raise HomeAssistantError(
        "Nu există nicio instanță Car Manager România încărcată pentru adăugarea autovehiculului."
    )


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    hass.data.setdefault(DOMAIN, {})
    if (
        hass.data[DOMAIN].get("services_registered")
        and hass.services.has_service(DOMAIN, SERVICE_ADD_VEHICLE)
        and hass.services.has_service(DOMAIN, SERVICE_REMOVE_VEHICLE)
        and hass.services.has_service(DOMAIN, SERVICE_RESTORE_VEHICLE)
        and hass.services.has_service(DOMAIN, SERVICE_RESTORE_ALL_VEHICLES)
    ):
        return

    async def async_add_vehicle(call: ServiceCall) -> None:
        """Add a vehicle from a Home Assistant service call."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store

        current_vehicles = await vehicle_store.async_get_vehicles()
        if not current_vehicles:
            current_vehicles = list(entry.runtime_data.vehicles)

        vehicle_name = str(call.data[CONF_NAME]).strip()
        if not vehicle_name:
            raise HomeAssistantError("Numele autovehiculului este obligatoriu.")

        license_plate = str(call.data.get(CONF_LICENSE_PLATE, "")).strip().upper()
        vin = str(call.data.get(CONF_VIN, "")).strip().upper()
        km = max(0, int(call.data.get(CONF_KM, 0) or 0))

        vehicle_id = _generate_vehicle_id(current_vehicles, license_plate, vehicle_name)
        vehicles = list(current_vehicles)
        vehicles.append(
            {
                CONF_VEHICLE_ID: vehicle_id,
                CONF_NAME: vehicle_name,
                CONF_LICENSE_PLATE: license_plate,
                CONF_VIN: vin,
                CONF_KM: km,
            }
        )

        normalized_vehicles, _ = normalize_vehicles(vehicles)
        active_vehicles = _active_vehicles(normalized_vehicles)
        await vehicle_store.async_save_vehicles(normalized_vehicles)
        entry.runtime_data.vehicles = active_vehicles
        entry.runtime_data.all_vehicles = normalized_vehicles
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        _LOGGER.info(
            "Autovehicul adăugat în Car Manager România: %s (%s)",
            vehicle_name,
            license_plate or "fără număr",
        )

        # Reîncărcăm integrarea ca Home Assistant să creeze entitățile noului autovehicul.
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_remove_vehicle(call: ServiceCall) -> None:
        """Mark a vehicle as removed from a Home Assistant service call."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store

        vehicle_id = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_id:
            raise HomeAssistantError("ID-ul intern al autovehiculului este obligatoriu.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)

        found = False
        updated_vehicles: list[dict[str, Any]] = []
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue

            vehicle_copy = dict(vehicle)
            if str(vehicle_copy.get(CONF_VEHICLE_ID, "")) == vehicle_id:
                vehicle_copy[CONF_REMOVED] = True
                found = True
            updated_vehicles.append(vehicle_copy)

        if not found:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        normalized_vehicles, _ = normalize_vehicles(updated_vehicles)
        active_vehicles = _active_vehicles(normalized_vehicles)
        await vehicle_store.async_save_vehicles(normalized_vehicles)
        entry.runtime_data.vehicles = active_vehicles
        entry.runtime_data.all_vehicles = normalized_vehicles
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        _LOGGER.info(
            "Autovehicul dezactivat în Car Manager România: %s",
            vehicle_id,
        )

        # Reîncărcăm integrarea ca Home Assistant să elimine entitățile autovehiculului din runtime.
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_restore_vehicle(call: ServiceCall) -> None:
        """Restore a previously disabled vehicle from a Home Assistant service call."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store

        vehicle_id = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_id:
            raise HomeAssistantError("ID-ul intern al autovehiculului este obligatoriu.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)

        found = False
        updated_vehicles: list[dict[str, Any]] = []
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue

            vehicle_copy = dict(vehicle)
            if str(vehicle_copy.get(CONF_VEHICLE_ID, "")) == vehicle_id:
                vehicle_copy[CONF_REMOVED] = False
                found = True
            updated_vehicles.append(vehicle_copy)

        if not found:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        normalized_vehicles, _ = normalize_vehicles(updated_vehicles)
        active_vehicles = _active_vehicles(normalized_vehicles)
        await vehicle_store.async_save_vehicles(normalized_vehicles)
        entry.runtime_data.vehicles = active_vehicles
        entry.runtime_data.all_vehicles = normalized_vehicles
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        _LOGGER.info(
            "Autovehicul reactivat în Car Manager România: %s",
            vehicle_id,
        )

        # Reîncărcăm integrarea ca Home Assistant să creeze din nou entitățile autovehiculului.
        await hass.config_entries.async_reload(entry.entry_id)


    async def async_restore_all_vehicles(call: ServiceCall) -> None:
        """Restore all disabled vehicles from a Home Assistant service call."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)

        updated_vehicles: list[dict[str, Any]] = []
        changed = False
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue

            vehicle_copy = dict(vehicle)
            if bool(vehicle_copy.get(CONF_REMOVED)):
                vehicle_copy[CONF_REMOVED] = False
                changed = True
            updated_vehicles.append(vehicle_copy)

        if not changed:
            raise HomeAssistantError("Nu există autovehicule dezactivate de reactivat.")

        normalized_vehicles, _ = normalize_vehicles(updated_vehicles)
        active_vehicles = _active_vehicles(normalized_vehicles)
        await vehicle_store.async_save_vehicles(normalized_vehicles)
        entry.runtime_data.vehicles = active_vehicles
        entry.runtime_data.all_vehicles = normalized_vehicles
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        _LOGGER.info("Toate autovehiculele dezactivate au fost reactivate în Car Manager România.")

        await hass.config_entries.async_reload(entry.entry_id)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_VEHICLE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_VEHICLE,
            async_add_vehicle,
            schema=ADD_VEHICLE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_REMOVE_VEHICLE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REMOVE_VEHICLE,
            async_remove_vehicle,
            schema=REMOVE_VEHICLE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_VEHICLE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_VEHICLE,
            async_restore_vehicle,
            schema=RESTORE_VEHICLE_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_ALL_VEHICLES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_ALL_VEHICLES,
            async_restore_all_vehicles,
            schema=RESTORE_ALL_VEHICLES_SERVICE_SCHEMA,
        )
    hass.data[DOMAIN]["services_registered"] = True

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
    active_vehicles = _active_vehicles(normalized_vehicles)

    if changed or normalized_vehicles != stored_vehicles:
        await vehicle_store.async_save_vehicles(normalized_vehicles)

    rovinieta_coordinator = await _async_setup_rovinieta_coordinator(hass, entry)

    entry.runtime_data = CarManagerRuntimeData(
        integration_version=VERSION,
        vehicles=active_vehicles,
        all_vehicles=normalized_vehicles,
        vehicle_store=vehicle_store,
        rovinieta_coordinator=rovinieta_coordinator,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await _async_register_services(hass)
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
        scan_interval_seconds=scan_interval_days * 24 * 60 * 60,
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
    active_vehicles = _active_vehicles(normalized_vehicles)

    if changed or normalized_vehicles != stored_vehicles:
        await vehicle_store.async_save_vehicles(normalized_vehicles)

    entry.runtime_data.vehicles = active_vehicles
    entry.runtime_data.all_vehicles = normalized_vehicles

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Unload a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
