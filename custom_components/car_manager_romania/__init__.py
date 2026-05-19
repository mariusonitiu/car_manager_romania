"""Modul principal pentru integrarea Car Manager România."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
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
    CONF_FUEL_PROFILE,
    CONF_LEGAL_TERMS,
    CONF_LICENSE_PLATE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_MAINTENANCE,
    CONF_NOTIFY_LEGAL,
    CONF_NOTIFY_EQUIPMENT,
    CONF_NOTIFY_BATTERY,
    CONF_NOTIFY_EXPENSES,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_NOTIFY_MAINTENANCE,
    DEFAULT_NOTIFY_LEGAL,
    DEFAULT_NOTIFY_EQUIPMENT,
    DEFAULT_NOTIFY_BATTERY,
    DEFAULT_NOTIFY_EXPENSES,
    CONF_NAME,
    CONF_REMOVED,
    CONF_ROVINIETA_PASSWORD,
    CONF_ROVINIETA_SCAN_INTERVAL,
    CONF_ROVINIETA_USERNAME,
    CONF_VEHICLES,
    CONF_VEHICLE_ID,
    CONF_VIN,
    COST_AMOUNT,
    DEFAULT_ROVINIETA_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_ADD_VEHICLE,
    SERVICE_REMOVE_VEHICLE,
    SERVICE_RESTORE_VEHICLE,
    SERVICE_RESTORE_ALL_VEHICLES,
    SERVICE_ADD_SERVICE_RECORD,
    SERVICE_RESTORE_SERVICE_RECORD,
    SERVICE_RESTORE_LAST_SERVICE_RECORD,
    SERVICE_DELETE_SERVICE_RECORD,
    SERVICE_UPDATE_SERVICE_RECORD,
    SERVICE_EXPORT_DATA,
    SERVICE_VALIDATE_BACKUP,
    SERVICE_IMPORT_DATA,
    SERVICE_SET_LEGAL_OPTION,
    SERVICE_CLEANUP_ORPHAN_ENTITIES,
    SERVICE_REFRESH_LICENSE_STATUS,
    SERVICE_SET_NOTIFICATION_OPTIONS,
    SERVICE_ADD_FUEL_RECEIPT,
    SERVICE_UPDATE_FUEL_RECEIPT,
    SERVICE_DELETE_FUEL_RECEIPT,
    SERVICE_ADD_TIRE_SET,
    SERVICE_UPDATE_TIRE_SET,
    SERVICE_DELETE_TIRE_SET,
    LEGAL_DATA_SOURCE,
    LEGAL_END_DATE,
    LEGAL_OPTION_IGNORED,
    LEGAL_SOURCE_EROVINIETA,
    LEGAL_START_DATE,
    LEGAL_TYPE_CASCO,
    LEGAL_TYPE_ROVINIETA,
    STORAGE_KEY_NOTIFICATIONS,
    STORAGE_VERSION_NOTIFICATIONS,
    FUEL_TYPES,
    FUEL_TYPES_BY_PROFILE,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_LAST_KM,
    LEGAL_COST_TYPES,
    MAINTENANCE_TYPES,
    SIGNAL_VEHICLES_UPDATED,
    SIGNAL_LICENSE_UPDATED,
    VERSION,
)
from .maintenance import get_maintenance_value, normalize_vehicles, set_maintenance_value
from .legal import set_legal_ignored
from .rovinieta.api import ERovinietaApiClient
from .rovinieta.coordinator import CarManagerRovinietaCoordinator
from .storage import CarManagerFuelReceiptStore, CarManagerServiceHistoryStore, CarManagerVehicleStore, merge_vehicle_sources
from .tire import CarManagerTireSetStore
from .equipment import CarManagerEquipmentItemStore
from .battery import CarManagerBatteryStore
from .backup import (
    EXPORT_DATA_SERVICE_SCHEMA,
    IMPORT_DATA_SERVICE_SCHEMA,
    VALIDATE_BACKUP_SERVICE_SCHEMA,
    async_export_data as _async_backup_export_data,
    async_import_data as _async_backup_import_data,
    async_validate_backup as _async_backup_validate_backup,
)
from .fuel_services import async_register_fuel_services
from .history_services import async_register_history_services
from .equipment_services import async_register_equipment_services
from .tire_services import async_register_tire_services
from .battery_services import async_register_battery_services

_LOGGER = logging.getLogger(__name__)

LOVELACE_CARD_URL = "/car_manager_romania/car-manager-romania-card.js"
LOVELACE_CARD_NOTIFICATION_ID = "car_manager_romania_lovelace_card"


@dataclass(slots=True)
class CarManagerRuntimeData:
    """Clasă pentru runtime date."""

    integration_version: str
    vehicles: list[dict[str, Any]]
    all_vehicles: list[dict[str, Any]]
    vehicle_store: CarManagerVehicleStore
    service_history_store: CarManagerServiceHistoryStore
    fuel_receipt_store: CarManagerFuelReceiptStore
    tire_set_store: CarManagerTireSetStore
    equipment_item_store: CarManagerEquipmentItemStore
    battery_store: CarManagerBatteryStore
    rovinieta_coordinator: CarManagerRovinietaCoordinator | None = None


type CarManagerConfigEntry = ConfigEntry[CarManagerRuntimeData]


def _normalize_resource_url(value: Any) -> str:
    """Funcție internă pentru normalizare resursă URL."""

    if value is None:
        return ""

    normalized = str(value).strip()
    if not normalized:
        return ""

    # Resursele Lovelace sunt adesea versionate cu parametri de tip ?v=0.7.1.
    normalized = normalized.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return normalized


def _resource_url_matches(value: Any) -> bool:
    """Funcție internă pentru resursă URL matches."""

    normalized = _normalize_resource_url(value)
    expected = _normalize_resource_url(LOVELACE_CARD_URL)
    return normalized == expected or normalized.endswith(expected)


async def _maybe_await(value: Any) -> Any:
    """Funcție internă pentru maybe await."""

    if inspect.isawaitable(value):
        return await value
    return value


def _extract_resource_urls(value: Any) -> list[str]:
    """Funcție internă pentru extract resursă URL-uri."""

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
    """Funcție internă pentru Lovelace card resursă exists."""

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

        # Cea mai importantă verificare: resursele Lovelace în modul de stocare sunt
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
    """Funcție internă pentru înregistrare frontend."""

    base_path = Path(__file__).parent
    frontend_path = base_path / "frontend"
    brand_path = base_path / "brand"
    if not frontend_path.exists():
        return

    try:
        from homeassistant.components.http import StaticPathConfig

        static_paths = [
            StaticPathConfig(
                "/car_manager_romania",
                str(frontend_path),
                True,
            )
        ]
        if brand_path.exists():
            static_paths.append(
                StaticPathConfig(
                    "/car_manager_romania_brand",
                    str(brand_path),
                    True,
                )
            )

        await hass.http.async_register_static_paths(static_paths)
    except Exception:  # noqa: BLE001
        try:
            hass.http.async_register_static_path(
                "/car_manager_romania",
                str(frontend_path),
                True,
            )
            if brand_path.exists():
                hass.http.async_register_static_path(
                    "/car_manager_romania_brand",
                    str(brand_path),
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

SET_LEGAL_OPTION_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("legal_type"): vol.In([LEGAL_TYPE_CASCO]),
        vol.Required(LEGAL_OPTION_IGNORED): bool,
    }
)

CLEANUP_ORPHAN_ENTITIES_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("dry_run", default=False): bool,
    }
)

REFRESH_LICENSE_STATUS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
    }
)


def _active_vehicles(vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Funcție internă pentru active vehicule."""

    return [
        vehicle
        for vehicle in vehicles
        if isinstance(vehicle, dict) and not bool(vehicle.get(CONF_REMOVED))
    ]


def _expected_entity_unique_ids(entry: CarManagerConfigEntry) -> set[str]:
    """Funcție internă pentru așteptate entitate unic ID-uri."""

    from .const import (
        CASCO_TEXT_FIELDS,
        CONF_FUEL_PROFILE,
        CONSUMABLE_TYPES,
        COST_AMOUNT,
        ITP_TEXT_FIELDS,
        LEGAL_END_DATE,
        LEGAL_START_DATE,
        LEGAL_COST_TYPES,
        LEGAL_TYPES,
        LEGAL_TYPE_ITP,
        LEGAL_TYPE_RCA,
        MAINTENANCE_INTERVAL_DAYS,
        MAINTENANCE_INTERVAL_KM,
        MAINTENANCE_LAST_DATE,
        MAINTENANCE_LAST_KM,
        MAINTENANCE_TIME_ONLY_TYPES,
        MAINTENANCE_TYPE_SERVICE,
        RCA_TEXT_FIELDS,
    )
    from .rovinieta.helpers import slugify_plate

    entry_id = entry.entry_id
    expected: set[str] = {
        f"{entry_id}_status",
        f"{entry_id}_vehicle_count",
        # Entități globale pentru licențiere.
        # Sunt create pe hub, nu pe autovehicule, deci trebuie păstrate explicit
        # de mecanismul de cleanup al registry-ului. Fără aceste unique_id-uri,
        # cleanup-ul automat le șterge imediat după ce platformele le creează.
        f"{entry_id}_license_v2_status",
        f"{entry_id}_license_v2_plan",
        f"{entry_id}_license_v2_expires_at",
        f"{entry_id}_license_v2_checked_at",
        f"{entry_id}_license_v2_utilizator",
        f"{entry_id}_license_v2_masked_key",
        f"{entry_id}_license_v2_message",
        f"{entry_id}_license_v2_key_text",
        f"{entry_id}_license_v2_apply",
        f"{entry_id}_license_v2_refresh",
    }

    if entry.runtime_data.rovinieta_coordinator is not None:
        expected.add(f"{entry_id}_rovinieta_refresh")

    legal_text_fields = {
        LEGAL_TYPE_RCA: RCA_TEXT_FIELDS,
        LEGAL_TYPE_CASCO: CASCO_TEXT_FIELDS,
        LEGAL_TYPE_ITP: ITP_TEXT_FIELDS,
    }

    coordinator = entry.runtime_data.rovinieta_coordinator
    rovinieta_plates: set[str] = set()
    if coordinator is not None and coordinator.data is not None:
        for item in getattr(coordinator.data, "vehicles", []) or []:
            plate = str(getattr(item, "plate_no", "") or "").replace(" ", "").upper()
            if plate:
                rovinieta_plates.add(plate)

    for vehicle in entry.runtime_data.vehicles:
        vehicle_id = str(vehicle.get(CONF_VEHICLE_ID) or vehicle.get("vehicle_id") or "").strip()
        if not vehicle_id:
            continue

        expected.update(
            {
                f"{entry_id}_{vehicle_id}_km",
                f"{entry_id}_{vehicle_id}_status",
                f"{entry_id}_{vehicle_id}_upcoming_expenses_30_days",
                f"{entry_id}_{vehicle_id}_upcoming_expenses_90_days",
                f"{entry_id}_{vehicle_id}_annual_costs_current_year",
                f"{entry_id}_{vehicle_id}_fuel_costs_current_year",
                f"{entry_id}_{vehicle_id}_fuel_costs_current_month",
                f"{entry_id}_{vehicle_id}_fuel_average_consumption",
            }
        )

        for maintenance_type in MAINTENANCE_TYPES:
            if maintenance_type == MAINTENANCE_TYPE_SERVICE:
                expected.update(
                    {
                        f"{entry_id}_{vehicle_id}_service_date",
                        f"{entry_id}_{vehicle_id}_last_service_km",
                        f"{entry_id}_{vehicle_id}_service_interval_km",
                        f"{entry_id}_{vehicle_id}_service_interval_days",
                        f"{entry_id}_{vehicle_id}_service_km_remaining",
                        f"{entry_id}_{vehicle_id}_service_days_remaining",
                        f"{entry_id}_{vehicle_id}_service_status",
                        f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_{COST_AMOUNT}",
                    }
                )
                continue

            expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_last_date")
            expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_interval_days")
            expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_cost")
            expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_days_remaining")
            expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_status")

            if maintenance_type not in MAINTENANCE_TIME_ONLY_TYPES:
                expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_last_km")
                expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_interval_km")
                expected.add(f"{entry_id}_{vehicle_id}_maintenance_{maintenance_type}_km_remaining")

        for legal_type in LEGAL_TYPES:
            expected.update(
                {
                    f"{entry_id}_{vehicle_id}_{legal_type}_start_date",
                    f"{entry_id}_{vehicle_id}_{legal_type}_end_date",
                    f"{entry_id}_{vehicle_id}_{legal_type}_days_remaining",
                    f"{entry_id}_{vehicle_id}_{legal_type}_status",
                }
            )

        for legal_type in LEGAL_COST_TYPES:
            expected.add(f"{entry_id}_{vehicle_id}_legal_{legal_type}_cost")

        expected.add(f"{entry_id}_{vehicle_id}_{CONF_FUEL_PROFILE}")

        for consumable_key in CONSUMABLE_TYPES:
            expected.add(f"{entry_id}_{vehicle_id}_consumable_{consumable_key}")

        for legal_type, fields in legal_text_fields.items():
            for field in fields:
                expected.add(f"{entry_id}_{vehicle_id}_{legal_type}_{field}")

        plate = str(vehicle.get(CONF_LICENSE_PLATE) or "").replace(" ", "").upper()
        if plate and plate in rovinieta_plates:
            slug = slugify_plate(vehicle.get(CONF_LICENSE_PLATE, vehicle_id))
            expected.update(
                {
                    f"{entry_id}_{vehicle_id}_{slug}_rovinieta_status",
                    f"{entry_id}_{vehicle_id}_{slug}_rovinieta_expiry",
                    f"{entry_id}_{vehicle_id}_{slug}_rovinieta_days_remaining",
                    f"{entry_id}_{vehicle_id}_{slug}_rovinieta_series",
                    f"{entry_id}_{vehicle_id}_{slug}_rovinieta_category",
                    f"{entry_id}_{vehicle_id}_{slug}_rovinieta_period",
                }
            )

    return expected


async def _async_cleanup_orphan_entities(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    *,
    dry_run: bool = False,
) -> list[dict[str, str]]:
    """Funcție internă pentru curățare orfane entități."""

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    expected = _expected_entity_unique_ids(entry)
    removed: list[dict[str, str]] = []

    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = str(getattr(registry_entry, "unique_id", "") or "")
        entity_id = str(getattr(registry_entry, "entity_id", "") or "")

        if not unique_id or not entity_id:
            continue
        if unique_id in expected:
            continue
        if not unique_id.startswith(f"{entry.entry_id}_"):
            continue

        # Rovinieta poate fi temporar indisponibilă dacă portalul extern sau autentificarea eșuează.
        # Nu ștergem automat aceste entități decât dacă nu mai sunt generate explicit.
        if "rovinieta" in unique_id:
            continue

        removed.append({"entity_id": entity_id, "unique_id": unique_id})
        if not dry_run:
            registry.async_remove(entity_id)

    if removed:
        action = "ar fi curățate" if dry_run else "curățate"
        _LOGGER.info(
            "Car Manager România: %s entități orfane %s din registry: %s",
            len(removed),
            action,
            ", ".join(item["entity_id"] for item in removed),
        )

    return removed


def _generate_vehicle_id(vehicles: list[dict[str, Any]], license_plate: str, vehicle_name: str) -> str:
    """Funcție internă pentru generate vehicul ID."""

    base_id = slugify(license_plate) or slugify(vehicle_name) or "autovehicul"
    existing_ids = {str(vehicle.get("vehicle_id")) for vehicle in vehicles if vehicle.get("vehicle_id")}

    if base_id not in existing_ids:
        return base_id

    counter = 2
    while f"{base_id}_{counter}" in existing_ids:
        counter += 1

    return f"{base_id}_{counter}"


def _find_loaded_config_entry(hass: HomeAssistant, entry_id: str | None = None) -> CarManagerConfigEntry:
    """Funcție internă pentru căutare loaded configurare intrare."""

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


def _normalize_vehicle_reference(value: Any) -> str:
    """Funcție internă pentru normalizare vehicul referință."""

    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _find_vehicle_by_reference(vehicles: list[dict[str, Any]], reference: str) -> dict[str, Any] | None:
    """Funcție internă pentru căutare vehicul by referință."""

    wanted = _normalize_vehicle_reference(reference)
    if not wanted:
        return None

    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue

        candidates = (
            vehicle.get(CONF_VEHICLE_ID),
            vehicle.get(CONF_VIN),
            vehicle.get(CONF_LICENSE_PLATE),
            vehicle.get(CONF_NAME),
        )
        if any(_normalize_vehicle_reference(candidate) == wanted for candidate in candidates):
            return vehicle

    return None


def _vehicle_internal_id(vehicle: dict[str, Any]) -> str:
    """Funcție internă pentru vehicul intern ID."""

    vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
    if not vehicle_id:
        raise HomeAssistantError("Autovehiculul selectat nu are ID intern stabil.")
    return vehicle_id


SET_NOTIFICATION_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional(CONF_NOTIFICATIONS_ENABLED): bool,
        vol.Optional(CONF_NOTIFY_MAINTENANCE): bool,
        vol.Optional(CONF_NOTIFY_LEGAL): bool,
        vol.Optional(CONF_NOTIFY_EQUIPMENT): bool,
        vol.Optional(CONF_NOTIFY_BATTERY): bool,
        vol.Optional(CONF_NOTIFY_EXPENSES): bool,
    }
)

async def _async_register_services(hass: HomeAssistant) -> None:
    """Funcție internă pentru înregistrare services."""

    hass.data.setdefault(DOMAIN, {})
    if (
        hass.data[DOMAIN].get("services_registered")
        and hass.services.has_service(DOMAIN, SERVICE_ADD_VEHICLE)
        and hass.services.has_service(DOMAIN, SERVICE_REMOVE_VEHICLE)
        and hass.services.has_service(DOMAIN, SERVICE_RESTORE_VEHICLE)
        and hass.services.has_service(DOMAIN, SERVICE_RESTORE_ALL_VEHICLES)
        and hass.services.has_service(DOMAIN, SERVICE_ADD_SERVICE_RECORD)
        and hass.services.has_service(DOMAIN, SERVICE_RESTORE_SERVICE_RECORD)
        and hass.services.has_service(DOMAIN, SERVICE_RESTORE_LAST_SERVICE_RECORD)
        and hass.services.has_service(DOMAIN, SERVICE_DELETE_SERVICE_RECORD)
        and hass.services.has_service(DOMAIN, SERVICE_UPDATE_SERVICE_RECORD)
        and hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA)
        and hass.services.has_service(DOMAIN, SERVICE_VALIDATE_BACKUP)
        and hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA)
        and hass.services.has_service(DOMAIN, SERVICE_SET_LEGAL_OPTION)
        and hass.services.has_service(DOMAIN, SERVICE_CLEANUP_ORPHAN_ENTITIES)
        and hass.services.has_service(DOMAIN, SERVICE_REFRESH_LICENSE_STATUS)
        and hass.services.has_service(DOMAIN, SERVICE_SET_NOTIFICATION_OPTIONS)
        and hass.services.has_service(DOMAIN, SERVICE_ADD_FUEL_RECEIPT)
        and hass.services.has_service(DOMAIN, SERVICE_UPDATE_FUEL_RECEIPT)
        and hass.services.has_service(DOMAIN, SERVICE_DELETE_FUEL_RECEIPT)
        and hass.services.has_service(DOMAIN, SERVICE_ADD_TIRE_SET)
        and hass.services.has_service(DOMAIN, SERVICE_UPDATE_TIRE_SET)
        and hass.services.has_service(DOMAIN, SERVICE_DELETE_TIRE_SET)
    ):
        return

    async def async_refresh_license_status(call: ServiceCall) -> None:
        """Gestionează asincron actualizarea statusului licenței."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))

        from .license import (
            async_obtine_context_licenta,
            async_salveaza_licenta_globala,
            async_valideaza_licenta,
        )

        username, license_key, _storage = await async_obtine_context_licenta(hass, intrare=entry)
        license_key = str(license_key or "").strip() or "TRIAL"
        result = await async_valideaza_licenta(hass, license_key, username)

        await async_salveaza_licenta_globala(hass, license_key, username, result)
        dispatcher_send(hass, SIGNAL_LICENSE_UPDATED)

        if result.connection_error:
            raise HomeAssistantError(result.message or "Serverul de licențiere nu a putut fi contactat.")

        if not result.valid:
            raise HomeAssistantError(result.message or "Licența nu este validă.")


    async def async_set_notification_options(call: ServiceCall) -> None:
        """Actualizează opțiunile de notificare dintr-un apel de service."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        options = dict(entry.options or {})

        fields = {
            CONF_NOTIFICATIONS_ENABLED: DEFAULT_NOTIFICATIONS_ENABLED,
            CONF_NOTIFY_MAINTENANCE: DEFAULT_NOTIFY_MAINTENANCE,
            CONF_NOTIFY_LEGAL: DEFAULT_NOTIFY_LEGAL,
            CONF_NOTIFY_EQUIPMENT: DEFAULT_NOTIFY_EQUIPMENT,
            CONF_NOTIFY_BATTERY: DEFAULT_NOTIFY_BATTERY,
            CONF_NOTIFY_EXPENSES: DEFAULT_NOTIFY_EXPENSES,
        }

        changed = False
        for key, default in fields.items():
            if key not in call.data:
                continue
            value = bool(call.data.get(key, default))
            if bool(options.get(key, default)) != value:
                options[key] = value
                changed = True

        if not changed:
            return

        hass.config_entries.async_update_entry(entry, options=options)

        try:
            from .notify import async_check_maintenance_notifications

            await async_check_maintenance_notifications(hass, entry)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Nu am putut reevalua notificările după actualizarea setărilor: %s", err)

    async def async_add_vehicle(call: ServiceCall) -> None:
        """Gestionează asincron operațiunea pentru adăugare vehicul."""

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
        """Gestionează asincron operațiunea pentru eliminare vehicul."""

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
        """Gestionează asincron operațiunea pentru restaurare vehicul."""

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
        """Gestionează asincron operațiunea pentru restaurare all vehicule."""

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

    async def async_export_data(call: ServiceCall) -> None:
        """Delegă exportul de date către modulul dedicat pentru backup."""

        await _async_backup_export_data(hass, call, _find_loaded_config_entry)

    async def async_validate_backup(call: ServiceCall) -> None:
        """Delegă validarea backup-ului către modulul dedicat pentru backup."""

        await _async_backup_validate_backup(hass, call, _find_loaded_config_entry)

    async def async_import_data(call: ServiceCall) -> None:
        """Delegă importul de date către modulul dedicat pentru backup."""

        await _async_backup_import_data(hass, call, _find_loaded_config_entry)

    async def async_set_legal_option(call: ServiceCall) -> None:
        """Gestionează asincron operațiunea pentru set legal option."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store

        legal_type = str(call.data["legal_type"]).strip()
        vehicle_reference = str(call.data[CONF_VEHICLE_ID]).strip()
        ignored = bool(call.data[LEGAL_OPTION_IGNORED])

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)

        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_reference)
        if found_vehicle is None:
            raise HomeAssistantError(
                f"Nu am găsit autovehiculul '{vehicle_reference}' pentru actualizarea opțiunii."
            )

        set_legal_ignored(found_vehicle, legal_type, ignored)

        normalized_vehicles, _ = normalize_vehicles(vehicles)
        active_vehicles = _active_vehicles(normalized_vehicles)
        await vehicle_store.async_save_vehicles(normalized_vehicles)
        entry.runtime_data.vehicles = active_vehicles
        entry.runtime_data.all_vehicles = normalized_vehicles
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        await hass.config_entries.async_reload(entry.entry_id)

    async def async_cleanup_orphan_entities(call: ServiceCall) -> None:
        """Gestionează asincron operațiunea pentru curățare orfane entități."""

        target_entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        dry_run = bool(call.data.get("dry_run", False))
        cleaned = await _async_cleanup_orphan_entities(hass, target_entry, dry_run=dry_run)

        try:
            from homeassistant.components import persistent_notification

            if cleaned:
                sample = "\n".join(f"- `{item['entity_id']}`" for item in cleaned[:20])
                extra = "" if len(cleaned) <= 20 else f"\n... încă {len(cleaned) - 20} entități."
                persistent_notification.async_create(
                    hass,
                    f"Entități {'găsite' if dry_run else 'curățate'}: {len(cleaned)}\n\n{sample}{extra}",
                    title="Car Manager România - curățare entități orfane",
                    notification_id="car_manager_romania_cleanup_orphan_entities",
                )
            else:
                persistent_notification.async_create(
                    hass,
                    "Nu am găsit entități orfane pentru Car Manager România.",
                    title="Car Manager România - curățare entități orfane",
                    notification_id="car_manager_romania_cleanup_orphan_entities",
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Nu am putut crea notificarea pentru curățarea entităților: %s", err)

        if cleaned and not dry_run:
            await hass.config_entries.async_reload(target_entry.entry_id)


    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_LICENSE_STATUS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_LICENSE_STATUS,
            async_refresh_license_status,
            schema=REFRESH_LICENSE_STATUS_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_NOTIFICATION_OPTIONS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_NOTIFICATION_OPTIONS,
            async_set_notification_options,
            schema=SET_NOTIFICATION_OPTIONS_SCHEMA,
        )

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
    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_DATA,
            async_export_data,
            schema=EXPORT_DATA_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_VALIDATE_BACKUP):
        hass.services.async_register(
            DOMAIN,
            SERVICE_VALIDATE_BACKUP,
            async_validate_backup,
            schema=VALIDATE_BACKUP_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_IMPORT_DATA):
        hass.services.async_register(
            DOMAIN,
            SERVICE_IMPORT_DATA,
            async_import_data,
            schema=IMPORT_DATA_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_LEGAL_OPTION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_LEGAL_OPTION,
            async_set_legal_option,
            schema=SET_LEGAL_OPTION_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEANUP_ORPHAN_ENTITIES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEANUP_ORPHAN_ENTITIES,
            async_cleanup_orphan_entities,
            schema=CLEANUP_ORPHAN_ENTITIES_SERVICE_SCHEMA,
        )

    await async_register_fuel_services(
        hass,
        _find_loaded_config_entry,
        _find_vehicle_by_reference,
        _vehicle_internal_id,
        _active_vehicles,
    )

    await async_register_history_services(
        hass,
        _find_loaded_config_entry,
        _find_vehicle_by_reference,
        _vehicle_internal_id,
        _active_vehicles,
    )
    await async_register_tire_services(
        hass,
        _find_loaded_config_entry,
        _find_vehicle_by_reference,
        _vehicle_internal_id,
    )

    await async_register_equipment_services(
        hass,
        _find_loaded_config_entry,
        _find_vehicle_by_reference,
        _vehicle_internal_id,
    )

    await async_register_battery_services(
        hass,
        _find_loaded_config_entry,
        _find_vehicle_by_reference,
        _vehicle_internal_id,
    )
    hass.data[DOMAIN]["services_registered"] = True


async def _async_revalidate_license_non_blocking(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Funcție internă pentru revalidare licență non blocking."""

    await asyncio.sleep(15)

    try:
        from .license import (
            async_obtine_context_licenta,
            async_salveaza_licenta_globala,
            async_valideaza_licenta,
        )

        username, license_key, _storage = await async_obtine_context_licenta(hass, intrare=entry)
        license_key = str(license_key or "").strip() or "TRIAL"
        result = await async_valideaza_licenta(hass, license_key, username)

        # Dacă serverul de licențiere nu poate fi contactat, nu suprascriem ultimul
        # status local cunoscut. Un răspuns clar revoked/expired/invalid se salvează.
        if result.connection_error:
            _LOGGER.warning(
                "Car Manager România: revalidarea licenței după pornire nu a reușit: %s",
                result.message or result.status,
            )
            return

        await async_salveaza_licenta_globala(hass, license_key, username, result)
        dispatcher_send(hass, SIGNAL_LICENSE_UPDATED)
    except asyncio.CancelledError:
        raise
    except Exception as err:  # noqa: BLE001 - startup helper must never block HA
        _LOGGER.warning(
            "Car Manager România: revalidarea licenței după pornire a eșuat: %s",
            err,
        )

async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> bool:
    """Configurează componentele integrației în Home Assistant."""

    vehicle_store = CarManagerVehicleStore(hass)
    service_history_store = CarManagerServiceHistoryStore(hass)
    fuel_receipt_store = CarManagerFuelReceiptStore(hass)
    tire_set_store = CarManagerTireSetStore(hass)
    equipment_item_store = CarManagerEquipmentItemStore(hass)
    battery_store = CarManagerBatteryStore(hass)
    await service_history_store.async_load()
    await fuel_receipt_store.async_load()
    await tire_set_store.async_load()
    await equipment_item_store.async_load()
    await battery_store.async_load()
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
        service_history_store=service_history_store,
        fuel_receipt_store=fuel_receipt_store,
        tire_set_store=tire_set_store,
        equipment_item_store=equipment_item_store,
        battery_store=battery_store,
        rovinieta_coordinator=rovinieta_coordinator,
    )

    def _register_unload_callback(callback: Any) -> None:
        """Înregistrează curățarea la unload fără să returneze valori booleene către Home Assistant."""

        if not callable(callback):
            return

        def _safe_unload_callback() -> None:
            callback()

        entry.async_on_unload(_safe_unload_callback)

    if rovinieta_coordinator is not None:
        await _async_sync_rovinieta_manual_terms(hass, entry, dispatch_updates=False)

        def _schedule_rovinieta_manual_sync() -> None:
            hass.async_create_task(_async_sync_rovinieta_manual_terms(hass, entry))

        remove_rovinieta_manual_sync = rovinieta_coordinator.async_add_listener(
            _schedule_rovinieta_manual_sync
        )
        _register_unload_callback(remove_rovinieta_manual_sync)

    # Înregistrăm listener-ul pentru actualizarea opțiunilor într-un mod compatibil
    # cu versiunile Home Assistant în care callback-urile pot întoarce valori
    # booleene. Wrapper-ul de mai sus aruncă rezultatul și păstrează unload-ul sigur.
    remove_update_listener = entry.add_update_listener(async_update_options)
    _register_unload_callback(remove_update_listener)

    await _async_register_services(hass)
    await _async_register_frontend(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    cleaned_entities = await _async_cleanup_orphan_entities(hass, entry, dry_run=False)
    if cleaned_entities:
        _LOGGER.info(
            "Car Manager România: am curățat automat %s entități orfane după încărcarea platformelor.",
            len(cleaned_entities),
        )

    from .notify import async_check_maintenance_notifications

    await async_check_maintenance_notifications(hass, entry)

    def _schedule_notification_check(*_: Any) -> None:
        """Funcție internă pentru schedule notificare verificare."""

        hass.async_create_task(async_check_maintenance_notifications(hass, entry))

    remove_notification_interval = async_track_time_interval(
        hass,
        _schedule_notification_check,
        timedelta(hours=6),
    )
    _register_unload_callback(remove_notification_interval)

    if rovinieta_coordinator is not None:
        remove_rovinieta_notification_listener = rovinieta_coordinator.async_add_listener(
            _schedule_notification_check
        )
        _register_unload_callback(remove_rovinieta_notification_listener)

    license_revalidation_task = hass.async_create_task(
        _async_revalidate_license_non_blocking(hass, entry)
    )
    _register_unload_callback(license_revalidation_task.cancel)

    return True




def _rovinieta_plate_key(value: Any) -> str:
    """Funcție internă pentru rovinietă număr de înmatriculare cheie."""

    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _rovinieta_date_value(value: Any) -> str | None:
    """Funcție internă pentru rovinietă dată valoare."""

    if value is None:
        return None

    if hasattr(value, "astimezone"):
        return value.astimezone().date().isoformat()

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return None


def _active_rovinieta_start_date(rovinieta_vehicle: Any) -> str | None:
    """Funcție internă pentru active rovinietă început dată."""

    active_vignette = getattr(rovinieta_vehicle, "active_vignette", None)
    if not isinstance(active_vignette, dict):
        return None

    for key in ("date_start_availability", "oProdTransactionStartDate"):
        raw_value = active_vignette.get(key)
        if not raw_value:
            continue

        if isinstance(raw_value, str):
            candidate = raw_value.strip()
            if len(candidate) >= 10:
                return candidate[:10]

    return None


def _active_rovinieta_price(rovinieta_vehicle: Any) -> float | None:
    """Funcție internă pentru active rovinietă preț."""

    active_vignette = getattr(rovinieta_vehicle, "active_vignette", None)
    if not isinstance(active_vignette, dict):
        return None

    raw_value = active_vignette.get("oProdPrice")
    if raw_value in (None, ""):
        return None

    try:
        return round(float(str(raw_value).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


async def _async_sync_rovinieta_manual_terms(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    *,
    dispatch_updates: bool = True,
) -> bool:
    """Funcție internă pentru sync rovinietă manual termene."""

    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        return False

    coordinator = getattr(runtime_data, "rovinieta_coordinator", None)
    if coordinator is None or coordinator.data is None:
        return False

    all_vehicles = deepcopy(getattr(runtime_data, "all_vehicles", []))
    if not all_vehicles:
        return False

    rovinieta_by_plate = {
        _rovinieta_plate_key(getattr(rovinieta_vehicle, "plate_no", "")): rovinieta_vehicle
        for rovinieta_vehicle in coordinator.data.vehicles
        if _rovinieta_plate_key(getattr(rovinieta_vehicle, "plate_no", ""))
    }

    changed = False
    for vehicle in all_vehicles:
        if not isinstance(vehicle, dict):
            continue

        plate_key = _rovinieta_plate_key(vehicle.get(CONF_LICENSE_PLATE))
        rovinieta_vehicle = rovinieta_by_plate.get(plate_key)
        if rovinieta_vehicle is None:
            continue

        end_date = _rovinieta_date_value(getattr(rovinieta_vehicle, "expiry", None))
        if not end_date:
            continue

        legal_terms = vehicle.setdefault(CONF_LEGAL_TERMS, {})
        if not isinstance(legal_terms, dict):
            legal_terms = {}
            vehicle[CONF_LEGAL_TERMS] = legal_terms

        rovinieta_term = legal_terms.setdefault(LEGAL_TYPE_ROVINIETA, {})
        if not isinstance(rovinieta_term, dict):
            rovinieta_term = {}
            legal_terms[LEGAL_TYPE_ROVINIETA] = rovinieta_term

        current_source = rovinieta_term.get(LEGAL_DATA_SOURCE)
        current_end_date = rovinieta_term.get(LEGAL_END_DATE)
        may_update_from_auto = not current_end_date or current_source == LEGAL_SOURCE_EROVINIETA
        if not may_update_from_auto:
            continue

        start_date = _active_rovinieta_start_date(rovinieta_vehicle)
        price = _active_rovinieta_price(rovinieta_vehicle)

        updates: dict[str, Any] = {
            LEGAL_END_DATE: end_date,
            LEGAL_DATA_SOURCE: LEGAL_SOURCE_EROVINIETA,
        }
        if start_date:
            updates[LEGAL_START_DATE] = start_date
        if price is not None:
            updates[COST_AMOUNT] = price

        for key, value in updates.items():
            if rovinieta_term.get(key) != value:
                rovinieta_term[key] = value
                changed = True

    if not changed:
        return False

    active_vehicles = _active_vehicles(all_vehicles)
    runtime_data.all_vehicles = all_vehicles
    runtime_data.vehicles = active_vehicles
    await runtime_data.vehicle_store.async_save_vehicles(all_vehicles)

    if dispatch_updates:
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

    return True

async def _async_setup_rovinieta_coordinator(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> CarManagerRovinietaCoordinator | None:
    """Funcție internă pentru configurare rovinietă coordonator."""

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
    """Gestionează asincron operațiunea pentru actualizare opțiuni."""

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
    """Descarcă integrarea din Home Assistant."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
