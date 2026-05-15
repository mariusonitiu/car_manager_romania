"""The Car Manager România integration."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from datetime import date as dt_date, datetime, timedelta
import inspect
import json
import logging
from uuid import uuid4
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
    SERVICE_ADD_FUEL_RECEIPT,
    SERVICE_UPDATE_FUEL_RECEIPT,
    SERVICE_DELETE_FUEL_RECEIPT,
    SERVICE_ADD_TIRE_SET,
    SERVICE_UPDATE_TIRE_SET,
    SERVICE_DELETE_TIRE_SET,
    SERVICE_ADD_EQUIPMENT_ITEM,
    SERVICE_UPDATE_EQUIPMENT_ITEM,
    SERVICE_DELETE_EQUIPMENT_ITEM,
    SERVICE_ADD_BATTERY,
    SERVICE_UPDATE_BATTERY,
    SERVICE_DELETE_BATTERY,
    TIRE_TYPES,
    TIRE_MOUNT_TYPES,
    EQUIPMENT_TYPES,
    BATTERY_TYPES,
    LEGAL_OPTION_IGNORED,
    LEGAL_TYPE_CASCO,
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
from .tire import CarManagerTireSetStore, normalize_tire_set
from .equipment import CarManagerEquipmentItemStore, normalize_equipment_item
from .battery import CarManagerBatteryStore, normalize_battery_item

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
    service_history_store: CarManagerServiceHistoryStore
    fuel_receipt_store: CarManagerFuelReceiptStore
    tire_set_store: CarManagerTireSetStore
    equipment_item_store: CarManagerEquipmentItemStore
    battery_store: CarManagerBatteryStore
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

ADD_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("record_type"): vol.In(list(MAINTENANCE_TYPES.keys()) + list(LEGAL_COST_TYPES.keys()) + ["custom"]),
        vol.Optional("date"): str,
        vol.Optional(CONF_KM): vol.Coerce(int),
        vol.Optional("title", default=""): str,
        vol.Optional("service_name", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("invoice_number", default=""): str,
        vol.Optional("notes", default=""): str,
        vol.Optional("update_maintenance", default=True): bool,
    }
)

RESTORE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("record_id"): str,
    }
)

DELETE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("record_id"): str,
    }
)

UPDATE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("record_id"): str,
        vol.Optional("title"): str,
        vol.Optional("service_name"): str,
        vol.Optional("cost"): vol.Coerce(float),
        vol.Optional("invoice_number"): str,
        vol.Optional("notes"): str,
    }
)

RESTORE_LAST_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("record_type"): vol.In(list(MAINTENANCE_TYPES.keys())),
    }
)

EXPORT_DATA_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename", default="car_manager_romania_backup.json"): str,
    }
)

VALIDATE_BACKUP_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename", default="car_manager_romania_backup.json"): str,
    }
)

IMPORT_DATA_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename", default="car_manager_romania_backup.json"): str,
        vol.Optional("mode", default="merge"): vol.In(["merge"]),
        vol.Optional("dry_run", default=True): bool,
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


ADD_FUEL_RECEIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("date"): str,
        vol.Required(CONF_KM): vol.Coerce(int),
        vol.Required("fuel_type"): str,
        vol.Required("quantity"): vol.Coerce(float),
        vol.Required("total_cost"): vol.Coerce(float),
        vol.Optional("full_tank", default=True): bool,
        vol.Optional("station", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_FUEL_RECEIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("receipt_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("date"): str,
        vol.Required(CONF_KM): vol.Coerce(int),
        vol.Required("fuel_type"): str,
        vol.Required("quantity"): vol.Coerce(float),
        vol.Required("total_cost"): vol.Coerce(float),
        vol.Optional("full_tank", default=True): bool,
        vol.Optional("station", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

DELETE_FUEL_RECEIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("receipt_id"): str,
    }
)

ADD_TIRE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("tire_type"): vol.In(list(TIRE_TYPES.keys())),
        vol.Optional("wheel_mount_type", default="tires_only"): vol.In(list(TIRE_MOUNT_TYPES.keys())),
        vol.Optional("brand_model", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("dot", default=""): str,
        vol.Optional("quantity", default=4): vol.Coerce(int),
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("last_mount_date", default=""): str,
        vol.Optional("last_mount_km", default=0): vol.Coerce(int),
        vol.Optional("total_km", default=0): vol.Coerce(int),
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("installed", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("pressure_front", default=""): str,
        vol.Optional("pressure_rear", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_TIRE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("set_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("tire_type"): vol.In(list(TIRE_TYPES.keys())),
        vol.Optional("wheel_mount_type", default="tires_only"): vol.In(list(TIRE_MOUNT_TYPES.keys())),
        vol.Optional("brand_model", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("dot", default=""): str,
        vol.Optional("quantity", default=4): vol.Coerce(int),
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("last_mount_date", default=""): str,
        vol.Optional("last_mount_km", default=0): vol.Coerce(int),
        vol.Optional("total_km", default=0): vol.Coerce(int),
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("installed", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("pressure_front", default=""): str,
        vol.Optional("pressure_rear", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

DELETE_TIRE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("set_id"): str,
    }
)

ADD_EQUIPMENT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("equipment_type"): vol.In(list(EQUIPMENT_TYPES.keys())),
        vol.Optional("name", default=""): str,
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("expiry_date", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("present", default=True): bool,
        vol.Optional("ignored", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_EQUIPMENT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("item_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("equipment_type"): vol.In(list(EQUIPMENT_TYPES.keys())),
        vol.Optional("name", default=""): str,
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("expiry_date", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("present", default=True): bool,
        vol.Optional("ignored", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

DELETE_EQUIPMENT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("item_id"): str,
    }
)

ADD_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("installed", default=True): bool,
        vol.Optional("brand_model", default=""): str,
        vol.Optional("battery_type", default="lead_acid"): vol.In(list(BATTERY_TYPES.keys())),
        vol.Optional("capacity_ah", default=0): vol.Coerce(int),
        vol.Optional("cca", default=0): vol.Coerce(int),
        vol.Optional("polarity", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("install_date", default=""): str,
        vol.Optional("install_km", default=0): vol.Coerce(int),
        vol.Optional("warranty_until", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("battery_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("installed", default=True): bool,
        vol.Optional("brand_model", default=""): str,
        vol.Optional("battery_type", default="lead_acid"): vol.In(list(BATTERY_TYPES.keys())),
        vol.Optional("capacity_ah", default=0): vol.Coerce(int),
        vol.Optional("cca", default=0): vol.Coerce(int),
        vol.Optional("polarity", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("install_date", default=""): str,
        vol.Optional("install_km", default=0): vol.Coerce(int),
        vol.Optional("warranty_until", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("notes", default=""): str,
    }
)

DELETE_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("battery_id"): str,
    }
)


def _active_vehicles(vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return vehicles that are not marked as removed."""

    return [
        vehicle
        for vehicle in vehicles
        if isinstance(vehicle, dict) and not bool(vehicle.get(CONF_REMOVED))
    ]


def _expected_entity_unique_ids(entry: CarManagerConfigEntry) -> set[str]:
    """Build the set of entity unique IDs that should exist for the current entry.

    This is used only for registry cleanup. It intentionally follows the unique_id
    rules used by the entity classes, including legacy IDs kept for the first
    general service entities.
    """

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
    """Remove registry entities that belong to this entry but are no longer generated."""

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

        # Rovinieta can be temporarily unavailable if the external portal or login fails.
        # Do not delete these entities automatically unless they are explicitly expected.
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


def _find_vehicle_by_id(vehicles: list[dict[str, Any]], vehicle_id: str) -> dict[str, Any] | None:
    """Return a mutable vehicle dictionary by internal ID."""

    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        if str(vehicle.get(CONF_VEHICLE_ID, "")) == vehicle_id:
            return vehicle
    return None


def _normalize_vehicle_reference(value: Any) -> str:
    """Normalize a vehicle reference for tolerant service matching."""

    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _find_vehicle_by_reference(vehicles: list[dict[str, Any]], reference: str) -> dict[str, Any] | None:
    """Return a mutable vehicle dictionary by vehicle_id, VIN, plate or name."""

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
    """Return the stable internal ID from a vehicle dictionary."""

    vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
    if not vehicle_id:
        raise HomeAssistantError("Autovehiculul selectat nu are ID intern stabil.")
    return vehicle_id


def _maintenance_snapshot(vehicle: dict[str, Any], maintenance_type: str) -> dict[str, Any]:
    """Return the current maintenance values that may be changed by a service record."""

    return {
        "maintenance_type": maintenance_type,
        MAINTENANCE_LAST_DATE: get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_DATE),
        MAINTENANCE_LAST_KM: get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_KM),
        CONF_KM: vehicle.get(CONF_KM),
    }




def _is_service_record_newer_than_current(
    vehicle: dict[str, Any],
    maintenance_type: str,
    record_date: str,
    km_value: int,
) -> bool:
    """Return True only when a history record should become the current maintenance baseline."""

    current_date_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_DATE)
    current_km_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_KM)

    try:
        new_date = dt_date.fromisoformat(str(record_date))
    except (TypeError, ValueError):
        return False

    current_date = None
    if current_date_raw:
        try:
            current_date = dt_date.fromisoformat(str(current_date_raw))
        except (TypeError, ValueError):
            current_date = None

    if current_date is None:
        return True

    if new_date > current_date:
        return True

    if new_date < current_date:
        return False

    if km_value <= 0:
        return False

    try:
        current_km = int(current_km_raw or 0)
    except (TypeError, ValueError):
        current_km = 0

    return km_value > current_km


def _apply_maintenance_snapshot(vehicle: dict[str, Any], snapshot: dict[str, Any]) -> None:
    """Restore maintenance values from a previous snapshot."""

    maintenance_type = str(snapshot.get("maintenance_type", "")).strip()
    if maintenance_type not in MAINTENANCE_TYPES:
        raise HomeAssistantError("Snapshotul nu conține un tip de mentenanță valid.")

    set_maintenance_value(
        vehicle,
        maintenance_type,
        MAINTENANCE_LAST_DATE,
        snapshot.get(MAINTENANCE_LAST_DATE),
    )
    set_maintenance_value(
        vehicle,
        maintenance_type,
        MAINTENANCE_LAST_KM,
        snapshot.get(MAINTENANCE_LAST_KM),
    )

    if CONF_KM in snapshot and snapshot.get(CONF_KM) is not None:
        vehicle[CONF_KM] = snapshot.get(CONF_KM)


async def _async_restore_service_record_snapshot(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    record: dict[str, Any],
) -> None:
    """Restore vehicle maintenance values using a history record snapshot."""

    vehicle_store = entry.runtime_data.vehicle_store
    history_store = entry.runtime_data.service_history_store

    record_id = str(record.get("record_id", "")).strip()
    if not record_id:
        raise HomeAssistantError("Intervenția selectată nu are record_id valid.")

    if bool(record.get("restored")):
        raise HomeAssistantError("Această intervenție a fost deja restaurată.")

    previous_maintenance = record.get("previous_maintenance")
    if not isinstance(previous_maintenance, dict):
        raise HomeAssistantError(
            "Intervenția selectată nu are snapshot anterior. A fost probabil creată înainte de versiunea cu restore."
        )

    vehicle_id = str(record.get(CONF_VEHICLE_ID, "")).strip()
    if not vehicle_id:
        raise HomeAssistantError("Intervenția selectată nu are autovehicul asociat.")

    stored_vehicles = await vehicle_store.async_get_vehicles()
    option_vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
    found_vehicle = _find_vehicle_by_id(vehicles, vehicle_id)
    if found_vehicle is None:
        raise HomeAssistantError("Autovehiculul intervenției nu a fost găsit în Car Manager România.")

    _apply_maintenance_snapshot(found_vehicle, previous_maintenance)

    normalized_vehicles, _ = normalize_vehicles(vehicles)
    active_vehicles = _active_vehicles(normalized_vehicles)
    await vehicle_store.async_save_vehicles(normalized_vehicles)
    await history_store.async_update_record(
        record_id,
        {
            "restored": True,
            "restored_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    entry.runtime_data.vehicles = active_vehicles
    entry.runtime_data.all_vehicles = normalized_vehicles
    dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

    from .notify import async_check_maintenance_notifications

    hass.async_create_task(async_check_maintenance_notifications(hass, entry))
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

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
        and hass.services.has_service(DOMAIN, SERVICE_ADD_FUEL_RECEIPT)
        and hass.services.has_service(DOMAIN, SERVICE_UPDATE_FUEL_RECEIPT)
        and hass.services.has_service(DOMAIN, SERVICE_DELETE_FUEL_RECEIPT)
        and hass.services.has_service(DOMAIN, SERVICE_ADD_TIRE_SET)
        and hass.services.has_service(DOMAIN, SERVICE_UPDATE_TIRE_SET)
        and hass.services.has_service(DOMAIN, SERVICE_DELETE_TIRE_SET)
    ):
        return

    async def async_refresh_license_status(call: ServiceCall) -> None:
        """Force an online license validation from a Home Assistant service call."""

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

    async def async_add_service_record(call: ServiceCall) -> None:
        """Add a service/intervention history record from a Home Assistant service call."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        history_store = entry.runtime_data.service_history_store
        fuel_store = entry.runtime_data.fuel_receipt_store
        tire_store = entry.runtime_data.tire_set_store
        equipment_store = entry.runtime_data.equipment_item_store
        battery_store = entry.runtime_data.battery_store

        vehicle_id = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_id:
            raise HomeAssistantError("ID-ul intern al autovehiculului este obligatoriu.")

        record_type = str(call.data["record_type"]).strip()
        if not record_type:
            raise HomeAssistantError("Tipul intervenției este obligatoriu.")

        record_date = str(call.data.get("date") or dt_date.today().isoformat()).strip()
        try:
            dt_date.fromisoformat(record_date)
        except ValueError as err:
            raise HomeAssistantError("Data intervenției trebuie să fie în format YYYY-MM-DD.") from err

        km_value = int(call.data.get(CONF_KM, 0) or 0)
        if km_value < 0:
            raise HomeAssistantError("Kilometrajul nu poate fi negativ.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)

        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_id)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )

        vehicle_id = _vehicle_internal_id(found_vehicle)

        requested_maintenance_update = bool(call.data.get("update_maintenance", True))
        update_maintenance = False
        maintenance_update_skipped_reason = ""
        previous_maintenance = None
        updated_maintenance = None

        if requested_maintenance_update and record_type in MAINTENANCE_TYPES:
            if _is_service_record_newer_than_current(
                found_vehicle,
                record_type,
                record_date,
                km_value,
            ):
                update_maintenance = True
                previous_maintenance = _maintenance_snapshot(found_vehicle, record_type)

                set_maintenance_value(found_vehicle, record_type, MAINTENANCE_LAST_DATE, record_date)
                if km_value > 0:
                    set_maintenance_value(found_vehicle, record_type, MAINTENANCE_LAST_KM, km_value)
                    if int(found_vehicle.get(CONF_KM, 0) or 0) < km_value:
                        found_vehicle[CONF_KM] = km_value

                updated_maintenance = _maintenance_snapshot(found_vehicle, record_type)

                normalized_vehicles, _ = normalize_vehicles(vehicles)
                active_vehicles = _active_vehicles(normalized_vehicles)
                await vehicle_store.async_save_vehicles(normalized_vehicles)
                entry.runtime_data.vehicles = active_vehicles
                entry.runtime_data.all_vehicles = normalized_vehicles
                dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

                from .notify import async_check_maintenance_notifications

                hass.async_create_task(async_check_maintenance_notifications(hass, entry))
            else:
                maintenance_update_skipped_reason = (
                    "Intervenția este mai veche decât mentenanța curentă sau nu are "
                    "kilometraj mai mare pentru aceeași dată. A fost salvată doar în istoric."
                )

        record = {
            "record_id": f"rec_{uuid4().hex[:12]}",
            CONF_VEHICLE_ID: vehicle_id,
            "record_type": record_type,
            "date": record_date,
            CONF_KM: km_value,
            "title": str(call.data.get("title", "")).strip(),
            "service_name": str(call.data.get("service_name", "")).strip(),
            "cost": float(call.data.get("cost", 0) or 0),
            "invoice_number": str(call.data.get("invoice_number", "")).strip(),
            "notes": str(call.data.get("notes", "")).strip(),
            "update_maintenance": update_maintenance,
            "requested_update_maintenance": requested_maintenance_update,
        }
        if maintenance_update_skipped_reason:
            record["maintenance_update_skipped_reason"] = maintenance_update_skipped_reason
        if previous_maintenance is not None:
            record["previous_maintenance"] = previous_maintenance
        if updated_maintenance is not None:
            record["updated_maintenance"] = updated_maintenance

        await history_store.async_add_record(record)

        await hass.config_entries.async_reload(entry.entry_id)

        _LOGGER.info(
            "Intervenție adăugată în istoricul Car Manager România: %s pentru %s",
            record_type,
            vehicle_id,
        )


    async def async_add_fuel_receipt(call: ServiceCall) -> None:
        """Add a fuel receipt from a Home Assistant service call."""

        from .fuel import allowed_fuel_types, enrich_fuel_receipt, is_liquid_fuel

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        fuel_store = entry.runtime_data.fuel_receipt_store

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_ref:
            raise HomeAssistantError("Autovehiculul este obligatoriu.")

        receipt_date = str(call.data.get("date") or dt_date.today().isoformat()).strip()
        try:
            dt_date.fromisoformat(receipt_date)
        except ValueError as err:
            raise HomeAssistantError("Data alimentării trebuie să fie în format YYYY-MM-DD.") from err

        km_value = int(call.data.get(CONF_KM, 0) or 0)
        if km_value <= 0:
            raise HomeAssistantError("Kilometrajul din bord este obligatoriu și trebuie să fie mai mare decât 0.")

        fuel_type = str(call.data.get("fuel_type", "")).strip()
        quantity = float(call.data.get("quantity", 0) or 0)
        total_cost = float(call.data.get("total_cost", 0) or 0)
        if quantity <= 0:
            raise HomeAssistantError("Numărul de litri/kWh trebuie să fie mai mare decât 0.")
        if total_cost <= 0:
            raise HomeAssistantError("Valoarea bonului trebuie să fie mai mare decât 0.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )

        allowed_types = allowed_fuel_types(found_vehicle)
        if fuel_type not in allowed_types:
            raise HomeAssistantError("Tipul de combustibil nu este permis pentru motorizarea configurată a autovehiculului.")

        vehicle_id = _vehicle_internal_id(found_vehicle)
        full_tank = bool(call.data.get("full_tank", True)) if is_liquid_fuel(fuel_type) else False
        receipt = enrich_fuel_receipt(
            {
                "receipt_id": f"fuel_{uuid4().hex[:12]}",
                CONF_VEHICLE_ID: vehicle_id,
                "date": receipt_date,
                CONF_KM: km_value,
                "fuel_type": fuel_type,
                "quantity": round(quantity, 3),
                "total_cost": round(total_cost, 2),
                "full_tank": full_tank,
                "station": str(call.data.get("station", "")).strip(),
                "notes": str(call.data.get("notes", "")).strip(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

        await fuel_store.async_add_receipt(receipt)

        # Kilometrajul actual al mașinii crește automat dacă bonul este mai nou ca valoare de bord.
        changed_vehicle = False
        for vehicle in vehicles:
            if _vehicle_internal_id(vehicle) == vehicle_id and int(vehicle.get(CONF_KM, 0) or 0) < km_value:
                vehicle[CONF_KM] = km_value
                changed_vehicle = True
                break

        if changed_vehicle:
            normalized_vehicles, _ = normalize_vehicles(vehicles)
            active_vehicles = _active_vehicles(normalized_vehicles)
            await vehicle_store.async_save_vehicles(normalized_vehicles)
            entry.runtime_data.vehicles = active_vehicles
            entry.runtime_data.all_vehicles = normalized_vehicles
            dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_fuel_receipt(call: ServiceCall) -> None:
        """Update an existing fuel receipt from a Home Assistant service call."""

        from .fuel import allowed_fuel_types, enrich_fuel_receipt, is_liquid_fuel

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        fuel_store = entry.runtime_data.fuel_receipt_store

        receipt_id = str(call.data["receipt_id"]).strip()
        if not receipt_id:
            raise HomeAssistantError("ID-ul bonului este obligatoriu.")

        existing_receipts = await fuel_store.async_get_receipts()
        existing_receipt = next((receipt for receipt in existing_receipts if str(receipt.get("receipt_id", "")) == receipt_id), None)
        if existing_receipt is None:
            raise HomeAssistantError("Bonul de combustibil nu a fost găsit.")

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_ref:
            raise HomeAssistantError("Autovehiculul este obligatoriu.")

        receipt_date = str(call.data.get("date") or dt_date.today().isoformat()).strip()
        try:
            dt_date.fromisoformat(receipt_date)
        except ValueError as err:
            raise HomeAssistantError("Data alimentării trebuie să fie în format YYYY-MM-DD.") from err

        km_value = int(call.data.get(CONF_KM, 0) or 0)
        if km_value <= 0:
            raise HomeAssistantError("Kilometrajul din bord este obligatoriu și trebuie să fie mai mare decât 0.")

        fuel_type = str(call.data.get("fuel_type", "")).strip()
        quantity = float(call.data.get("quantity", 0) or 0)
        total_cost = float(call.data.get("total_cost", 0) or 0)
        if quantity <= 0:
            raise HomeAssistantError("Numărul de litri/kWh trebuie să fie mai mare decât 0.")
        if total_cost <= 0:
            raise HomeAssistantError("Valoarea bonului trebuie să fie mai mare decât 0.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )

        allowed_types = allowed_fuel_types(found_vehicle)
        if fuel_type not in allowed_types:
            raise HomeAssistantError("Tipul de combustibil nu este permis pentru motorizarea configurată a autovehiculului.")

        vehicle_id = _vehicle_internal_id(found_vehicle)
        full_tank = bool(call.data.get("full_tank", True)) if is_liquid_fuel(fuel_type) else False

        updated_receipt = enrich_fuel_receipt(
            {
                "receipt_id": receipt_id,
                CONF_VEHICLE_ID: vehicle_id,
                "date": receipt_date,
                CONF_KM: km_value,
                "fuel_type": fuel_type,
                "quantity": round(quantity, 3),
                "total_cost": round(total_cost, 2),
                "full_tank": full_tank,
                "station": str(call.data.get("station", "")).strip(),
                "notes": str(call.data.get("notes", "")).strip(),
                "created_at": str(existing_receipt.get("created_at") or datetime.now().isoformat(timespec="seconds")),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

        updated = await fuel_store.async_update_receipt(receipt_id, updated_receipt)
        if not updated:
            raise HomeAssistantError("Bonul de combustibil nu a fost găsit.")

        changed_vehicle = False
        for vehicle in vehicles:
            if _vehicle_internal_id(vehicle) == vehicle_id and int(vehicle.get(CONF_KM, 0) or 0) < km_value:
                vehicle[CONF_KM] = km_value
                changed_vehicle = True
                break

        if changed_vehicle:
            normalized_vehicles, _ = normalize_vehicles(vehicles)
            active_vehicles = _active_vehicles(normalized_vehicles)
            await vehicle_store.async_save_vehicles(normalized_vehicles)
            entry.runtime_data.vehicles = active_vehicles
            entry.runtime_data.all_vehicles = normalized_vehicles
            dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_fuel_receipt(call: ServiceCall) -> None:
        """Delete a fuel receipt."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        receipt_id = str(call.data["receipt_id"]).strip()
        if not receipt_id:
            raise HomeAssistantError("ID-ul bonului este obligatoriu.")

        deleted = await entry.runtime_data.fuel_receipt_store.async_delete_receipt(receipt_id)
        if not deleted:
            raise HomeAssistantError("Bonul de combustibil nu a fost găsit.")

        await hass.config_entries.async_reload(entry.entry_id)

    async def async_restore_service_record(call: ServiceCall) -> None:
        """Restore maintenance values changed by one service history record."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        record_id = str(call.data["record_id"]).strip()
        if not record_id:
            raise HomeAssistantError("ID-ul intervenției este obligatoriu.")

        record = await history_store.async_get_record(record_id)
        if record is None:
            raise HomeAssistantError("Intervenția selectată nu a fost găsită în istoric.")

        await _async_restore_service_record_snapshot(hass, entry, record)

    async def async_restore_last_service_record(call: ServiceCall) -> None:
        """Restore the last restorable maintenance update for a vehicle."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        vehicle_id = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_id:
            raise HomeAssistantError("Referința autovehiculului este obligatorie.")

        vehicle_store = entry.runtime_data.vehicle_store
        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_id)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )
        vehicle_id = _vehicle_internal_id(found_vehicle)

        requested_type = call.data.get("record_type")
        if requested_type is not None:
            requested_type = str(requested_type).strip()

        records = await history_store.async_get_records()
        selected_record: dict[str, Any] | None = None
        for record in reversed(records):
            if str(record.get(CONF_VEHICLE_ID, "")) != vehicle_id:
                continue
            if requested_type and str(record.get("record_type", "")) != requested_type:
                continue
            if bool(record.get("restored")):
                continue
            if not isinstance(record.get("previous_maintenance"), dict):
                continue
            selected_record = record
            break

        if selected_record is None:
            raise HomeAssistantError(
                "Nu există nicio intervenție restaurabilă pentru autovehiculul selectat."
            )

        await _async_restore_service_record_snapshot(hass, entry, selected_record)

    async def async_update_service_record(call: ServiceCall) -> None:
        """Update safe informational fields for one service/intervention history record."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        record_id = str(call.data["record_id"]).strip()
        if not record_id:
            raise HomeAssistantError("ID-ul intervenției este obligatoriu.")

        existing_record = await history_store.async_get_record(record_id)
        if existing_record is None:
            raise HomeAssistantError("Intervenția selectată nu a fost găsită în istoric.")

        changes: dict[str, Any] = {}
        if "title" in call.data:
            changes["title"] = str(call.data.get("title", "")).strip()
        if "service_name" in call.data:
            changes["service_name"] = str(call.data.get("service_name", "")).strip()
        if "invoice_number" in call.data:
            changes["invoice_number"] = str(call.data.get("invoice_number", "")).strip()
        if "notes" in call.data:
            changes["notes"] = str(call.data.get("notes", "")).strip()
        if "cost" in call.data:
            cost_value = float(call.data.get("cost", 0) or 0)
            if cost_value < 0:
                raise HomeAssistantError("Costul nu poate fi negativ.")
            changes["cost"] = cost_value

        if not changes:
            raise HomeAssistantError("Nu există câmpuri de actualizat pentru intervenția selectată.")

        changes["updated_at"] = datetime.now().isoformat(timespec="seconds")

        await history_store.async_update_record(record_id, changes)
        await hass.config_entries.async_reload(entry.entry_id)

        _LOGGER.info("Intervenție actualizată în istoricul Car Manager România: %s", record_id)

    async def async_delete_service_record(call: ServiceCall) -> None:
        """Delete one service/intervention history record only."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        record_id = str(call.data["record_id"]).strip()
        if not record_id:
            raise HomeAssistantError("ID-ul intervenției este obligatoriu.")

        deleted = await history_store.async_delete_record(record_id)
        if not deleted:
            raise HomeAssistantError("Intervenția selectată nu a fost găsită în istoric.")

        await hass.config_entries.async_reload(entry.entry_id)

        _LOGGER.info("Intervenție ștearsă din istoricul Car Manager România: %s", record_id)

    async def async_export_data(call: ServiceCall) -> None:
        """Export Car Manager România data to a local JSON backup file."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        history_store = entry.runtime_data.service_history_store
        fuel_store = entry.runtime_data.fuel_receipt_store
        tire_store = entry.runtime_data.tire_set_store
        equipment_store = entry.runtime_data.equipment_item_store
        battery_store = entry.runtime_data.battery_store

        filename = str(call.data.get("filename") or "car_manager_romania_backup.json").strip()
        if not filename:
            filename = "car_manager_romania_backup.json"
        if "/" in filename or "\\" in filename:
            raise HomeAssistantError("Numele fișierului de backup nu trebuie să conțină cale sau directoare.")
        if not filename.lower().endswith(".json"):
            filename = f"{filename}.json"

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        normalized_vehicles, _ = normalize_vehicles(list(vehicles))
        service_history = await history_store.async_get_records()
        fuel_receipts = await fuel_store.async_get_receipts()
        tire_sets = await entry.runtime_data.tire_set_store.async_get_sets()
        equipment_items = await entry.runtime_data.equipment_item_store.async_get_items()
        battery_items = await entry.runtime_data.battery_store.async_get_items()

        notification_data: dict[str, Any] = {}
        try:
            from homeassistant.helpers.storage import Store

            raw_notification_data = await Store(
                hass,
                STORAGE_VERSION_NOTIFICATIONS,
                STORAGE_KEY_NOTIFICATIONS,
            ).async_load()
            if isinstance(raw_notification_data, dict):
                notification_data = raw_notification_data
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Nu am putut include starea notificărilor în export: %s", err)

        backup_data = {
            "schema": "car_manager_romania_backup",
            "schema_version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "integration_version": VERSION,
            "entry": {
                "entry_id": entry.entry_id,
                "title": entry.title,
            },
            "vehicles": normalized_vehicles,
            "service_history": service_history,
            "fuel_receipts": fuel_receipts,
            "tire_sets": tire_sets,
            "equipment_items": equipment_items,
            "battery_items": battery_items,
            "notification_state": notification_data,
        }

        backup_path = Path(hass.config.path(filename))
        backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2, default=str)

        def _write_backup() -> None:
            backup_path.write_text(backup_json, encoding="utf-8")

        await hass.async_add_executor_job(_write_backup)

        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            hass,
            "Exportul Car Manager România a fost salvat local.\n\n"
            f"Fișier: `{backup_path}`\n\n"
            "Fișierul conține datele autovehiculelor, istoricul intervențiilor, bonurile de combustibil, seturile de anvelope, echipamentele auto, bateriile și starea notificărilor. "
            "Păstrează-l în siguranță, deoarece poate include VIN, numere de înmatriculare și observații de service.",
            title="Car Manager România - export date finalizat",
            notification_id="car_manager_romania_export_data",
        )

        _LOGGER.info("Export Car Manager România salvat în %s", backup_path)

    async def async_validate_backup(call: ServiceCall) -> None:
        """Validate a local Car Manager România JSON backup without importing it."""

        # Găsim entry-ul doar ca să validăm contextul. Nu modificăm datele integrației.
        _find_loaded_config_entry(hass, call.data.get("entry_id"))

        filename = str(call.data.get("filename") or "car_manager_romania_backup.json").strip()
        if not filename:
            filename = "car_manager_romania_backup.json"
        if "/" in filename or "\\" in filename:
            raise HomeAssistantError("Numele fișierului de backup nu trebuie să conțină cale sau directoare.")
        if not filename.lower().endswith(".json"):
            filename = f"{filename}.json"

        backup_path = Path(hass.config.path(filename))

        def _read_backup() -> str:
            if not backup_path.exists():
                raise FileNotFoundError(str(backup_path))
            return backup_path.read_text(encoding="utf-8")

        try:
            backup_text = await hass.async_add_executor_job(_read_backup)
        except FileNotFoundError as err:
            raise HomeAssistantError(f"Fișierul de backup nu există: {backup_path}") from err
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Nu am putut citi fișierul de backup: {err}") from err

        try:
            backup_data = json.loads(backup_text)
        except json.JSONDecodeError as err:
            raise HomeAssistantError(f"Fișierul nu este JSON valid: {err}") from err

        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(backup_data, dict):
            errors.append("Structura principală trebuie să fie obiect JSON.")
            backup_data = {}

        if backup_data.get("schema") != "car_manager_romania_backup":
            errors.append("Schema backup-ului nu este car_manager_romania_backup.")

        schema_version = backup_data.get("schema_version")
        if schema_version != 1:
            errors.append(f"Versiune schemă nesuportată: {schema_version!r}. Versiunea acceptată este 1.")

        vehicles = backup_data.get("vehicles")
        if not isinstance(vehicles, list):
            errors.append("Câmpul vehicles lipsește sau nu este listă.")
            vehicles = []

        service_history = backup_data.get("service_history")
        if not isinstance(service_history, list):
            errors.append("Câmpul service_history lipsește sau nu este listă.")
            service_history = []

        fuel_receipts = backup_data.get("fuel_receipts", [])
        if not isinstance(fuel_receipts, list):
            warnings.append("Câmpul fuel_receipts nu este listă și va fi ignorat la import.")
            fuel_receipts = []

        tire_sets = backup_data.get("tire_sets", [])
        if not isinstance(tire_sets, list):
            warnings.append("Câmpul tire_sets nu este listă și va fi ignorat la import.")
            tire_sets = []

        equipment_items = backup_data.get("equipment_items", [])
        if not isinstance(equipment_items, list):
            warnings.append("Câmpul equipment_items nu este listă și va fi ignorat la import.")
            equipment_items = []

        battery_items = backup_data.get("battery_items", [])
        if not isinstance(battery_items, list):
            warnings.append("Câmpul battery_items nu este listă și va fi ignorat la import.")
            battery_items = []

        notification_state = backup_data.get("notification_state")
        if notification_state is not None and not isinstance(notification_state, dict):
            warnings.append("Câmpul notification_state nu este obiect JSON și va trebui ignorat la un import viitor.")

        vehicle_ids: set[str] = set()
        duplicate_vehicle_ids: set[str] = set()
        active_count = 0
        removed_count = 0
        missing_vehicle_id_count = 0

        for index, vehicle in enumerate(vehicles, start=1):
            if not isinstance(vehicle, dict):
                warnings.append(f"Autovehiculul #{index} nu este obiect JSON.")
                continue

            vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
            if not vehicle_id:
                missing_vehicle_id_count += 1
            elif vehicle_id in vehicle_ids:
                duplicate_vehicle_ids.add(vehicle_id)
            else:
                vehicle_ids.add(vehicle_id)

            if bool(vehicle.get(CONF_REMOVED)):
                removed_count += 1
            else:
                active_count += 1

            if not str(vehicle.get(CONF_NAME, "")).strip():
                warnings.append(f"Autovehiculul #{index} nu are nume.")

        if missing_vehicle_id_count:
            warnings.append(f"{missing_vehicle_id_count} autovehicul(e) nu au vehicle_id.")
        if duplicate_vehicle_ids:
            warnings.append("Există vehicle_id duplicate: " + ", ".join(sorted(duplicate_vehicle_ids)))

        history_vehicle_refs: set[str] = set()
        missing_record_id_count = 0
        missing_record_vehicle_count = 0
        restorable_count = 0

        for index, record in enumerate(service_history, start=1):
            if not isinstance(record, dict):
                warnings.append(f"Intervenția #{index} nu este obiect JSON.")
                continue

            if not str(record.get("record_id", "")).strip():
                missing_record_id_count += 1

            record_vehicle_id = str(record.get(CONF_VEHICLE_ID, "")).strip()
            if not record_vehicle_id:
                missing_record_vehicle_count += 1
            else:
                history_vehicle_refs.add(record_vehicle_id)

            if isinstance(record.get("previous_maintenance"), dict) and not bool(record.get("restored")):
                restorable_count += 1

        if missing_record_id_count:
            warnings.append(f"{missing_record_id_count} intervenție/intervenții nu au record_id.")
        if missing_record_vehicle_count:
            warnings.append(f"{missing_record_vehicle_count} intervenție/intervenții nu au vehicle_id.")

        unknown_history_refs = sorted(ref for ref in history_vehicle_refs if ref not in vehicle_ids)
        if unknown_history_refs:
            warnings.append(
                "Există intervenții care referă autovehicule inexistente în backup: "
                + ", ".join(unknown_history_refs[:5])
                + ("..." if len(unknown_history_refs) > 5 else "")
            )

        exported_at = str(backup_data.get("exported_at", "necunoscut"))
        backup_version = str(backup_data.get("integration_version", "necunoscut"))

        from homeassistant.components import persistent_notification

        if errors:
            message = (
                "Backup-ul Car Manager România NU este valid pentru import. Nu s-a modificat nimic.\n\n"
                f"Fișier: `{backup_path}`\n\n"
                "Erori:\n"
                + "\n".join(f"- {error}" for error in errors)
            )
            title = "Car Manager România - backup invalid"
            notification_id = "car_manager_romania_validate_backup_invalid"
            _LOGGER.warning("Backup Car Manager România invalid: %s", "; ".join(errors))
        else:
            summary_lines = [
                "Backup-ul Car Manager România este valid. Nu s-a modificat nimic.",
                "",
                f"Fișier: `{backup_path}`",
                f"Exportat la: `{exported_at}`",
                f"Versiune integrare la export: `{backup_version}`",
                "",
                "Conținut:",
                f"- Autovehicule: {len(vehicles)} total, {active_count} active, {removed_count} dezactivate",
                f"- Intervenții în istoric: {len(service_history)}",
                f"- Intervenții restaurabile: {restorable_count}",
                f"- Bonuri combustibil: {len(fuel_receipts)}",
                f"- Seturi anvelope: {len(tire_sets)}",
                f"- Echipamente auto: {len(equipment_items)}",
                f"- Baterii auto: {len(battery_items)}",
            ]
            if warnings:
                summary_lines.extend(["", "Avertizări:"])
                summary_lines.extend(f"- {warning}" for warning in warnings[:10])
                if len(warnings) > 10:
                    summary_lines.append(f"- ... încă {len(warnings) - 10} avertizări")
            message = "\n".join(summary_lines)
            title = "Car Manager România - backup valid"
            notification_id = "car_manager_romania_validate_backup_valid"
            _LOGGER.info(
                "Backup Car Manager România validat: %s vehicule, %s intervenții",
                len(vehicles),
                len(service_history),
            )

        persistent_notification.async_create(
            hass,
            message,
            title=title,
            notification_id=notification_id,
        )

    async def async_import_data(call: ServiceCall) -> None:
        """Import Car Manager România data from a local JSON backup in merge mode."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        history_store = entry.runtime_data.service_history_store
        fuel_store = entry.runtime_data.fuel_receipt_store
        tire_store = entry.runtime_data.tire_set_store
        equipment_store = entry.runtime_data.equipment_item_store

        filename = str(call.data.get("filename") or "car_manager_romania_backup.json").strip()
        if not filename:
            filename = "car_manager_romania_backup.json"
        if "/" in filename or "\\" in filename:
            raise HomeAssistantError("Numele fișierului de backup nu trebuie să conțină cale sau directoare.")
        if not filename.lower().endswith(".json"):
            filename = f"{filename}.json"

        mode = str(call.data.get("mode") or "merge").strip().lower()
        if mode != "merge":
            raise HomeAssistantError("Momentan importul permite doar modul sigur merge.")

        dry_run = bool(call.data.get("dry_run", True))
        backup_path = Path(hass.config.path(filename))

        def _read_backup() -> str:
            if not backup_path.exists():
                raise FileNotFoundError(str(backup_path))
            return backup_path.read_text(encoding="utf-8")

        try:
            backup_text = await hass.async_add_executor_job(_read_backup)
        except FileNotFoundError as err:
            raise HomeAssistantError(f"Fișierul de backup nu există: {backup_path}") from err
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Nu am putut citi fișierul de backup: {err}") from err

        try:
            backup_data = json.loads(backup_text)
        except json.JSONDecodeError as err:
            raise HomeAssistantError(f"Fișierul nu este JSON valid: {err}") from err

        if not isinstance(backup_data, dict):
            raise HomeAssistantError("Backup-ul nu are structură JSON validă.")
        if backup_data.get("schema") != "car_manager_romania_backup":
            raise HomeAssistantError("Schema backup-ului nu este car_manager_romania_backup.")
        if backup_data.get("schema_version") != 1:
            raise HomeAssistantError("Versiunea schemei de backup nu este suportată. Versiunea acceptată este 1.")

        backup_vehicles_raw = backup_data.get("vehicles")
        backup_history_raw = backup_data.get("service_history")
        backup_fuel_raw = backup_data.get("fuel_receipts", [])
        backup_tire_raw = backup_data.get("tire_sets", [])
        backup_equipment_raw = backup_data.get("equipment_items", [])
        backup_battery_raw = backup_data.get("battery_items", [])
        if not isinstance(backup_vehicles_raw, list):
            raise HomeAssistantError("Câmpul vehicles lipsește sau nu este listă.")
        if not isinstance(backup_history_raw, list):
            raise HomeAssistantError("Câmpul service_history lipsește sau nu este listă.")
        if not isinstance(backup_fuel_raw, list):
            backup_fuel_raw = []
        if not isinstance(backup_tire_raw, list):
            backup_tire_raw = []
        if not isinstance(backup_equipment_raw, list):
            backup_equipment_raw = []
        if not isinstance(backup_battery_raw, list):
            backup_battery_raw = []

        backup_vehicles, _ = normalize_vehicles([
            deepcopy(vehicle)
            for vehicle in backup_vehicles_raw
            if isinstance(vehicle, dict)
        ])
        backup_history = [
            deepcopy(record)
            for record in backup_history_raw
            if isinstance(record, dict)
        ]
        backup_fuel = [
            deepcopy(receipt)
            for receipt in backup_fuel_raw
            if isinstance(receipt, dict)
        ]
        backup_tires = [
            deepcopy(tire_set)
            for tire_set in backup_tire_raw
            if isinstance(tire_set, dict)
        ]
        backup_equipment = [
            deepcopy(item)
            for item in backup_equipment_raw
            if isinstance(item, dict)
        ]
        backup_batteries = [
            deepcopy(item)
            for item in backup_battery_raw
            if isinstance(item, dict)
        ]

        current_stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        current_vehicles = merge_vehicle_sources(list(option_vehicles), current_stored_vehicles)
        current_vehicles, _ = normalize_vehicles(current_vehicles)
        current_history = await history_store.async_get_records()
        current_fuel = await fuel_store.async_get_receipts()
        current_tires = await tire_store.async_get_sets()
        current_equipment = await equipment_store.async_get_items()
        current_batteries = await battery_store.async_get_items()

        merged_vehicles = [deepcopy(vehicle) for vehicle in current_vehicles if isinstance(vehicle, dict)]
        vehicle_index_by_id = {
            str(vehicle.get(CONF_VEHICLE_ID, "")).strip(): index
            for index, vehicle in enumerate(merged_vehicles)
            if isinstance(vehicle, dict) and str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        }

        vehicles_added = 0
        vehicles_updated = 0
        vehicles_skipped = 0
        for vehicle in backup_vehicles:
            vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
            if not vehicle_id:
                vehicles_skipped += 1
                continue
            if vehicle_id in vehicle_index_by_id:
                merged_vehicles[vehicle_index_by_id[vehicle_id]].update(deepcopy(vehicle))
                vehicles_updated += 1
            else:
                merged_vehicles.append(deepcopy(vehicle))
                vehicle_index_by_id[vehicle_id] = len(merged_vehicles) - 1
                vehicles_added += 1

        merged_vehicles, _ = normalize_vehicles(merged_vehicles)
        active_vehicles = _active_vehicles(merged_vehicles)

        merged_history = [deepcopy(record) for record in current_history if isinstance(record, dict)]
        history_index_by_id = {
            str(record.get("record_id", "")).strip(): index
            for index, record in enumerate(merged_history)
            if isinstance(record, dict) and str(record.get("record_id", "")).strip()
        }

        history_added = 0
        history_updated = 0
        history_skipped = 0
        unknown_history_refs: set[str] = set()
        merged_vehicle_ids = {
            str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
            for vehicle in merged_vehicles
            if isinstance(vehicle, dict) and str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        }
        for record in backup_history:
            record_id = str(record.get("record_id", "")).strip()
            record_vehicle_id = str(record.get(CONF_VEHICLE_ID, "")).strip()
            if not record_id:
                history_skipped += 1
                continue
            if record_vehicle_id and record_vehicle_id not in merged_vehicle_ids:
                unknown_history_refs.add(record_vehicle_id)
            if record_id in history_index_by_id:
                merged_history[history_index_by_id[record_id]].update(deepcopy(record))
                history_updated += 1
            else:
                merged_history.append(deepcopy(record))
                history_index_by_id[record_id] = len(merged_history) - 1
                history_added += 1


        merged_fuel = [deepcopy(receipt) for receipt in current_fuel if isinstance(receipt, dict)]
        fuel_index_by_id = {
            str(receipt.get("receipt_id", "")).strip(): index
            for index, receipt in enumerate(merged_fuel)
            if isinstance(receipt, dict) and str(receipt.get("receipt_id", "")).strip()
        }
        fuel_added = 0
        fuel_updated = 0
        fuel_skipped = 0
        for receipt in backup_fuel:
            receipt_id = str(receipt.get("receipt_id", "")).strip()
            if not receipt_id:
                fuel_skipped += 1
                continue
            if receipt_id in fuel_index_by_id:
                merged_fuel[fuel_index_by_id[receipt_id]].update(deepcopy(receipt))
                fuel_updated += 1
            else:
                merged_fuel.append(deepcopy(receipt))
                fuel_index_by_id[receipt_id] = len(merged_fuel) - 1
                fuel_added += 1

        merged_tires = [deepcopy(tire_set) for tire_set in current_tires if isinstance(tire_set, dict)]
        tire_index_by_id = {
            str(tire_set.get("set_id", "")).strip(): index
            for index, tire_set in enumerate(merged_tires)
            if isinstance(tire_set, dict) and str(tire_set.get("set_id", "")).strip()
        }
        tire_added = 0
        tire_updated = 0
        tire_skipped = 0
        for tire_set in backup_tires:
            set_id = str(tire_set.get("set_id", "")).strip()
            if not set_id:
                tire_skipped += 1
                continue
            if set_id in tire_index_by_id:
                merged_tires[tire_index_by_id[set_id]].update(deepcopy(tire_set))
                tire_updated += 1
            else:
                merged_tires.append(deepcopy(tire_set))
                tire_index_by_id[set_id] = len(merged_tires) - 1
                tire_added += 1

        merged_equipment = [deepcopy(item) for item in current_equipment if isinstance(item, dict)]
        equipment_index_by_id = {
            str(item.get("item_id", "")).strip(): index
            for index, item in enumerate(merged_equipment)
            if isinstance(item, dict) and str(item.get("item_id", "")).strip()
        }
        equipment_added = 0
        equipment_updated = 0
        equipment_skipped = 0
        for item in backup_equipment:
            item_id = str(item.get("item_id", "")).strip()
            if not item_id:
                equipment_skipped += 1
                continue
            if item_id in equipment_index_by_id:
                merged_equipment[equipment_index_by_id[item_id]].update(deepcopy(item))
                equipment_updated += 1
            else:
                merged_equipment.append(deepcopy(item))
                equipment_index_by_id[item_id] = len(merged_equipment) - 1
                equipment_added += 1

        merged_batteries = [deepcopy(item) for item in current_batteries if isinstance(item, dict)]
        battery_index_by_id = {
            str(item.get("battery_id", "")).strip(): index
            for index, item in enumerate(merged_batteries)
            if isinstance(item, dict) and str(item.get("battery_id", "")).strip()
        }
        battery_added = 0
        battery_updated = 0
        battery_skipped = 0
        for item in backup_batteries:
            battery_id = str(item.get("battery_id", "")).strip()
            if not battery_id:
                battery_skipped += 1
                continue
            if battery_id in battery_index_by_id:
                merged_batteries[battery_index_by_id[battery_id]].update(deepcopy(item))
                battery_updated += 1
            else:
                merged_batteries.append(deepcopy(item))
                battery_index_by_id[battery_id] = len(merged_batteries) - 1
                battery_added += 1

        notification_merged = False
        notification_state = backup_data.get("notification_state")
        if isinstance(notification_state, dict) and isinstance(notification_state.get("notified"), dict):
            notification_merged = True

        if not dry_run:
            await vehicle_store.async_save_vehicles(merged_vehicles)
            await history_store.async_save_records(merged_history)
            await fuel_store.async_save_receipts(merged_fuel)
            await tire_store.async_save_sets(merged_tires)
            await equipment_store.async_save_items(merged_equipment)
            await battery_store.async_save_items(merged_batteries)

            if notification_merged and isinstance(notification_state, dict):
                try:
                    from homeassistant.helpers.storage import Store

                    notification_store = Store(
                        hass,
                        STORAGE_VERSION_NOTIFICATIONS,
                        STORAGE_KEY_NOTIFICATIONS,
                    )
                    current_notification_state = await notification_store.async_load()
                    if not isinstance(current_notification_state, dict):
                        current_notification_state = {"notified": {}}
                    current_notified = current_notification_state.get("notified")
                    if not isinstance(current_notified, dict):
                        current_notified = {}
                    incoming_notified = notification_state.get("notified")
                    if isinstance(incoming_notified, dict):
                        current_notified.update(deepcopy(incoming_notified))
                    await notification_store.async_save({"notified": current_notified})
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Nu am putut importa starea notificărilor Car Manager România: %s", err)

            entry.runtime_data.vehicles = active_vehicles
            entry.runtime_data.all_vehicles = merged_vehicles
            dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

        exported_at = str(backup_data.get("exported_at", "necunoscut"))
        backup_version = str(backup_data.get("integration_version", "necunoscut"))
        from homeassistant.components import persistent_notification

        summary_lines = [
            "Importul Car Manager România a fost simulat. Nu s-a modificat nimic." if dry_run else "Importul Car Manager România a fost aplicat în modul merge.",
            "",
            f"Fișier: `{backup_path}`",
            f"Exportat la: `{exported_at}`",
            f"Versiune integrare la export: `{backup_version}`",
            "Mod import: `merge`",
            f"Dry run: `{str(dry_run).lower()}`",
            "",
            "Rezultat:",
            f"- Autovehicule adăugate: {vehicles_added}",
            f"- Autovehicule actualizate: {vehicles_updated}",
            f"- Autovehicule ignorate: {vehicles_skipped}",
            f"- Intervenții adăugate: {history_added}",
            f"- Intervenții actualizate: {history_updated}",
            f"- Intervenții ignorate: {history_skipped}",
            f"- Bonuri combustibil adăugate: {fuel_added}",
            f"- Bonuri combustibil actualizate: {fuel_updated}",
            f"- Bonuri combustibil ignorate: {fuel_skipped}",
            f"- Seturi anvelope adăugate: {tire_added}",
            f"- Seturi anvelope actualizate: {tire_updated}",
            f"- Seturi anvelope ignorate: {tire_skipped}",
            f"- Echipamente auto adăugate: {equipment_added}",
            f"- Echipamente auto actualizate: {equipment_updated}",
            f"- Echipamente auto ignorate: {equipment_skipped}",
            f"- Baterii auto adăugate: {battery_added}",
            f"- Baterii auto actualizate: {battery_updated}",
            f"- Baterii auto ignorate: {battery_skipped}",
            f"- Stare notificări: {'inclusă în merge' if notification_merged else 'neinclusă / lipsă'}",
        ]
        if unknown_history_refs:
            summary_lines.extend([
                "",
                "Avertizări:",
                "- Există intervenții cu vehicle_id necunoscut după import: "
                + ", ".join(sorted(unknown_history_refs)[:5])
                + ("..." if len(unknown_history_refs) > 5 else ""),
            ])
        if dry_run:
            summary_lines.extend([
                "",
                "Pentru aplicare reală, rulează din nou serviciul cu `dry_run: false`.",
            ])
        else:
            summary_lines.extend([
                "",
                "Integrarea se reîncarcă pentru actualizarea entităților și a cardului.",
            ])

        persistent_notification.async_create(
            hass,
            "\n".join(summary_lines),
            title="Car Manager România - import backup" if not dry_run else "Car Manager România - simulare import backup",
            notification_id="car_manager_romania_import_data",
        )

        _LOGGER.info(
            "Import Car Manager România %s din %s: vehicule +%s/~%s, istoric +%s/~%s",
            "dry-run" if dry_run else "aplicat",
            backup_path,
            vehicles_added,
            vehicles_updated,
            history_added,
            history_updated,
        )

        if not dry_run:
            await hass.config_entries.async_reload(entry.entry_id)

    async def async_set_legal_option(call: ServiceCall) -> None:
        """Set optional legal-term visibility flags for one vehicle."""

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
        """Clean registry entities that are no longer generated by this integration."""

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


    async def async_add_tire_set(call: ServiceCall) -> None:
        """Add a tire set."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_ref:
            raise HomeAssistantError("Autovehiculul este obligatoriu.")

        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        for field_name in ("purchase_date", "last_mount_date"):
            value = str(call.data.get(field_name, "") or "").strip()
            if value:
                try:
                    dt_date.fromisoformat(value)
                except ValueError as err:
                    raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err

        tire_set = normalize_tire_set({
            "set_id": f"tire_{uuid4().hex[:12]}",
            CONF_VEHICLE_ID: _vehicle_internal_id(found_vehicle),
            "tire_type": call.data.get("tire_type"),
            "wheel_mount_type": call.data.get("wheel_mount_type", "tires_only"),
            "brand_model": call.data.get("brand_model", ""),
            "size": call.data.get("size", ""),
            "dot": call.data.get("dot", ""),
            "quantity": call.data.get("quantity", 4),
            "purchase_date": call.data.get("purchase_date", ""),
            "last_mount_date": call.data.get("last_mount_date", ""),
            "last_mount_km": call.data.get("last_mount_km", 0),
            "total_km": call.data.get("total_km", 0),
            "cost": call.data.get("cost", 0),
            "installed": call.data.get("installed", False),
            "storage_location": call.data.get("storage_location", ""),
            "pressure_front": call.data.get("pressure_front", ""),
            "pressure_rear": call.data.get("pressure_rear", ""),
            "notes": call.data.get("notes", ""),
        })
        await entry.runtime_data.tire_set_store.async_add_set(tire_set)
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_tire_set(call: ServiceCall) -> None:
        """Update an existing tire set."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        set_id = str(call.data.get("set_id", "")).strip()
        if not set_id:
            raise HomeAssistantError("Setul de anvelope nu are ID valid.")

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        for field_name in ("purchase_date", "last_mount_date"):
            value = str(call.data.get(field_name, "") or "").strip()
            if value:
                try:
                    dt_date.fromisoformat(value)
                except ValueError as err:
                    raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err

        updated_set = normalize_tire_set({
            "set_id": set_id,
            CONF_VEHICLE_ID: _vehicle_internal_id(found_vehicle),
            "tire_type": call.data.get("tire_type"),
            "wheel_mount_type": call.data.get("wheel_mount_type", "tires_only"),
            "brand_model": call.data.get("brand_model", ""),
            "size": call.data.get("size", ""),
            "dot": call.data.get("dot", ""),
            "quantity": call.data.get("quantity", 4),
            "purchase_date": call.data.get("purchase_date", ""),
            "last_mount_date": call.data.get("last_mount_date", ""),
            "last_mount_km": call.data.get("last_mount_km", 0),
            "total_km": call.data.get("total_km", 0),
            "cost": call.data.get("cost", 0),
            "installed": call.data.get("installed", False),
            "storage_location": call.data.get("storage_location", ""),
            "pressure_front": call.data.get("pressure_front", ""),
            "pressure_rear": call.data.get("pressure_rear", ""),
            "notes": call.data.get("notes", ""),
        })
        if not await entry.runtime_data.tire_set_store.async_update_set(set_id, updated_set):
            raise HomeAssistantError("Setul de anvelope nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_tire_set(call: ServiceCall) -> None:
        """Delete a tire set."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        set_id = str(call.data.get("set_id", "")).strip()
        if not set_id:
            raise HomeAssistantError("Setul de anvelope nu are ID valid.")
        if not await entry.runtime_data.tire_set_store.async_delete_set(set_id):
            raise HomeAssistantError("Setul de anvelope nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    def _validate_equipment_dates(call: ServiceCall) -> None:
        for field_name in ("purchase_date", "expiry_date"):
            value = str(call.data.get(field_name, "") or "").strip()
            if value:
                try:
                    dt_date.fromisoformat(value)
                except ValueError as err:
                    raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err

    async def async_add_equipment_item(call: ServiceCall) -> None:
        """Add one vehicle equipment/safety item."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")
        _validate_equipment_dates(call)
        item = normalize_equipment_item({
            "item_id": f"equipment_{uuid4().hex[:12]}",
            CONF_VEHICLE_ID: _vehicle_internal_id(found_vehicle),
            "equipment_type": call.data.get("equipment_type"),
            "name": call.data.get("name", ""),
            "purchase_date": call.data.get("purchase_date", ""),
            "expiry_date": call.data.get("expiry_date", ""),
            "cost": call.data.get("cost", 0),
            "present": call.data.get("present", True),
            "ignored": call.data.get("ignored", False),
            "storage_location": call.data.get("storage_location", ""),
            "notes": call.data.get("notes", ""),
        })
        await entry.runtime_data.equipment_item_store.async_add_item(item)
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_equipment_item(call: ServiceCall) -> None:
        """Update one vehicle equipment/safety item."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        item_id = str(call.data.get("item_id", "")).strip()
        if not item_id:
            raise HomeAssistantError("Echipamentul nu are ID valid.")
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")
        _validate_equipment_dates(call)
        item = normalize_equipment_item({
            "item_id": item_id,
            CONF_VEHICLE_ID: _vehicle_internal_id(found_vehicle),
            "equipment_type": call.data.get("equipment_type"),
            "name": call.data.get("name", ""),
            "purchase_date": call.data.get("purchase_date", ""),
            "expiry_date": call.data.get("expiry_date", ""),
            "cost": call.data.get("cost", 0),
            "present": call.data.get("present", True),
            "ignored": call.data.get("ignored", False),
            "storage_location": call.data.get("storage_location", ""),
            "notes": call.data.get("notes", ""),
        })
        if not await entry.runtime_data.equipment_item_store.async_update_item(item_id, item):
            raise HomeAssistantError("Echipamentul nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_equipment_item(call: ServiceCall) -> None:
        """Delete one vehicle equipment/safety item."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        item_id = str(call.data.get("item_id", "")).strip()
        if not item_id:
            raise HomeAssistantError("Echipamentul nu are ID valid.")
        if not await entry.runtime_data.equipment_item_store.async_delete_item(item_id):
            raise HomeAssistantError("Echipamentul nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)


    def _validate_battery_dates(call: ServiceCall) -> None:
        for field_name in ("install_date", "warranty_until"):
            value = str(call.data.get(field_name, "") or "").strip()
            if value:
                try:
                    dt_date.fromisoformat(value)
                except ValueError as err:
                    raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err

    async def async_add_battery(call: ServiceCall) -> None:
        """Add one vehicle battery."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")
        _validate_battery_dates(call)
        item = normalize_battery_item({
            "battery_id": f"battery_{uuid4().hex[:12]}",
            CONF_VEHICLE_ID: _vehicle_internal_id(found_vehicle),
            "installed": call.data.get("installed", True),
            "brand_model": call.data.get("brand_model", ""),
            "battery_type": call.data.get("battery_type", "lead_acid"),
            "capacity_ah": call.data.get("capacity_ah", 0),
            "cca": call.data.get("cca", 0),
            "polarity": call.data.get("polarity", ""),
            "size": call.data.get("size", ""),
            "install_date": call.data.get("install_date", ""),
            "install_km": call.data.get("install_km", 0),
            "warranty_until": call.data.get("warranty_until", ""),
            "cost": call.data.get("cost", 0),
            "notes": call.data.get("notes", ""),
        })
        await entry.runtime_data.battery_store.async_add_item(item)
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_battery(call: ServiceCall) -> None:
        """Update one vehicle battery."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        battery_id = str(call.data.get("battery_id", "")).strip()
        if not battery_id:
            raise HomeAssistantError("Bateria nu are ID valid.")
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = _find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")
        _validate_battery_dates(call)
        item = normalize_battery_item({
            "battery_id": battery_id,
            CONF_VEHICLE_ID: _vehicle_internal_id(found_vehicle),
            "installed": call.data.get("installed", True),
            "brand_model": call.data.get("brand_model", ""),
            "battery_type": call.data.get("battery_type", "lead_acid"),
            "capacity_ah": call.data.get("capacity_ah", 0),
            "cca": call.data.get("cca", 0),
            "polarity": call.data.get("polarity", ""),
            "size": call.data.get("size", ""),
            "install_date": call.data.get("install_date", ""),
            "install_km": call.data.get("install_km", 0),
            "warranty_until": call.data.get("warranty_until", ""),
            "cost": call.data.get("cost", 0),
            "notes": call.data.get("notes", ""),
        })
        if not await entry.runtime_data.battery_store.async_update_item(battery_id, item):
            raise HomeAssistantError("Bateria nu a fost găsită.")
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_battery(call: ServiceCall) -> None:
        """Delete one vehicle battery."""

        entry = _find_loaded_config_entry(hass, call.data.get("entry_id"))
        battery_id = str(call.data.get("battery_id", "")).strip()
        if not battery_id:
            raise HomeAssistantError("Bateria nu are ID valid.")
        if not await entry.runtime_data.battery_store.async_delete_item(battery_id):
            raise HomeAssistantError("Bateria nu a fost găsită.")
        await hass.config_entries.async_reload(entry.entry_id)


    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_LICENSE_STATUS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_LICENSE_STATUS,
            async_refresh_license_status,
            schema=REFRESH_LICENSE_STATUS_SCHEMA,
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
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_SERVICE_RECORD,
            async_add_service_record,
            schema=ADD_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_SERVICE_RECORD,
            async_restore_service_record,
            schema=RESTORE_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_SERVICE_RECORD,
            async_update_service_record,
            schema=UPDATE_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_SERVICE_RECORD,
            async_delete_service_record,
            schema=DELETE_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_LAST_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_LAST_SERVICE_RECORD,
            async_restore_last_service_record,
            schema=RESTORE_LAST_SERVICE_RECORD_SCHEMA,
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

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_FUEL_RECEIPT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_FUEL_RECEIPT,
            async_add_fuel_receipt,
            schema=ADD_FUEL_RECEIPT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_FUEL_RECEIPT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_FUEL_RECEIPT,
            async_update_fuel_receipt,
            schema=UPDATE_FUEL_RECEIPT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_FUEL_RECEIPT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_FUEL_RECEIPT,
            async_delete_fuel_receipt,
            schema=DELETE_FUEL_RECEIPT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_TIRE_SET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_TIRE_SET,
            async_add_tire_set,
            schema=ADD_TIRE_SET_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_TIRE_SET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_TIRE_SET,
            async_update_tire_set,
            schema=UPDATE_TIRE_SET_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_TIRE_SET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_TIRE_SET,
            async_delete_tire_set,
            schema=DELETE_TIRE_SET_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_EQUIPMENT_ITEM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_EQUIPMENT_ITEM,
            async_add_equipment_item,
            schema=ADD_EQUIPMENT_ITEM_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_EQUIPMENT_ITEM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_EQUIPMENT_ITEM,
            async_update_equipment_item,
            schema=UPDATE_EQUIPMENT_ITEM_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_EQUIPMENT_ITEM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_EQUIPMENT_ITEM,
            async_delete_equipment_item,
            schema=DELETE_EQUIPMENT_ITEM_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_BATTERY,
            async_add_battery,
            schema=ADD_BATTERY_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_BATTERY,
            async_update_battery,
            schema=UPDATE_BATTERY_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_BATTERY,
            async_delete_battery,
            schema=DELETE_BATTERY_SCHEMA,
        )
    hass.data[DOMAIN]["services_registered"] = True


async def _async_revalidate_license_non_blocking(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Revalidate the stored license after startup without blocking setup.

    This task intentionally runs after the integration has finished loading. It
    updates the local license status when the server answers clearly, but keeps
    the cached value when the licensing server is temporarily unreachable.
    """

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

        # If the licensing server is unreachable, do not overwrite the last
        # known local status. A clear revoked/expired/invalid response is saved.
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
    """Set up Car Manager România from a config entry."""

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

    entry.async_on_unload(entry.add_update_listener(async_update_options))

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

    license_revalidation_task = hass.async_create_task(
        _async_revalidate_license_non_blocking(hass, entry)
    )
    entry.async_on_unload(license_revalidation_task.cancel)

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
