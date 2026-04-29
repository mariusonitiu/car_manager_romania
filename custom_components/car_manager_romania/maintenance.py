"""Maintenance helpers for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

from .const import (
    CONF_CONSUMABLES,
    CONF_LAST_SERVICE_DATE,
    CONF_LAST_SERVICE_KM,
    CONF_SERVICE_INTERVAL_DAYS,
    CONF_SERVICE_INTERVAL_KM,
    DEFAULT_CONSUMABLE_VALUES,
    DEFAULT_MAINTENANCE_INTERVALS,
    MAINTENANCE_INTERVAL_DAYS,
    MAINTENANCE_INTERVAL_KM,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_LAST_KM,
    MAINTENANCE_SOON_DAYS_THRESHOLD,
    MAINTENANCE_SOON_KM_THRESHOLD,
    MAINTENANCE_STATUS_OK,
    MAINTENANCE_STATUS_OVERDUE,
    MAINTENANCE_STATUS_SOON,
    MAINTENANCE_STATUS_UNKNOWN,
    MAINTENANCE_TYPE_SERVICE,
    MAINTENANCE_TYPES,
)


def maintenance_storage_key(maintenance_type: str) -> str:
    """Return storage key for a maintenance type."""

    return f"maintenance_{maintenance_type}"


def _legacy_service_key(field: str) -> str | None:
    """Return legacy key for the general service maintenance type."""

    legacy_map = {
        MAINTENANCE_LAST_KM: CONF_LAST_SERVICE_KM,
        MAINTENANCE_LAST_DATE: CONF_LAST_SERVICE_DATE,
        MAINTENANCE_INTERVAL_KM: CONF_SERVICE_INTERVAL_KM,
        MAINTENANCE_INTERVAL_DAYS: CONF_SERVICE_INTERVAL_DAYS,
    }

    return legacy_map.get(field)


def get_maintenance_value(
    vehicle: dict[str, Any],
    maintenance_type: str,
    field: str,
) -> Any:
    """Return maintenance value with compatibility for old service fields."""

    if maintenance_type == MAINTENANCE_TYPE_SERVICE:
        legacy_key = _legacy_service_key(field)
        if legacy_key and legacy_key in vehicle:
            return vehicle.get(legacy_key)

    storage_key = maintenance_storage_key(maintenance_type)
    return vehicle.get(storage_key, {}).get(field)


def set_maintenance_value(
    vehicle: dict[str, Any],
    maintenance_type: str,
    field: str,
    value: Any,
) -> None:
    """Set maintenance value with compatibility for old service fields."""

    if maintenance_type == MAINTENANCE_TYPE_SERVICE:
        legacy_key = _legacy_service_key(field)
        if legacy_key:
            vehicle[legacy_key] = value
            return

    storage_key = maintenance_storage_key(maintenance_type)
    vehicle.setdefault(storage_key, {})[field] = value


def parse_date(value: Any) -> date | None:
    """Parse date value safely."""

    if not value:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def calculate_km_remaining(
    current_km: int,
    last_km: int | None,
    interval_km: int | None,
) -> int | None:
    """Calculate remaining kilometers."""

    if last_km is None or interval_km is None or interval_km <= 0:
        return None

    return max((last_km + interval_km) - current_km, 0)


def calculate_days_remaining(
    last_date_raw: Any,
    interval_days: int | None,
) -> int | None:
    """Calculate remaining days."""

    if interval_days is None or interval_days <= 0:
        return None

    last_date = parse_date(last_date_raw)
    if last_date is None:
        return None

    elapsed_days = (date.today() - last_date).days
    return max(interval_days - elapsed_days, 0)


def calculate_maintenance_status(
    km_remaining: int | None,
    days_remaining: int | None,
) -> str:
    """Calculate maintenance status."""

    if km_remaining is None and days_remaining is None:
        return MAINTENANCE_STATUS_UNKNOWN

    if (km_remaining is not None and km_remaining <= 0) or (
        days_remaining is not None and days_remaining <= 0
    ):
        return MAINTENANCE_STATUS_OVERDUE

    if (km_remaining is not None and km_remaining <= MAINTENANCE_SOON_KM_THRESHOLD) or (
        days_remaining is not None and days_remaining <= MAINTENANCE_SOON_DAYS_THRESHOLD
    ):
        return MAINTENANCE_STATUS_SOON

    return MAINTENANCE_STATUS_OK


def normalize_vehicle(vehicle: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Normalize a vehicle without overwriting existing user values."""

    normalized = deepcopy(vehicle)
    changed = False

    for maintenance_type in MAINTENANCE_TYPES:
        defaults = DEFAULT_MAINTENANCE_INTERVALS.get(maintenance_type, {})

        if maintenance_type == MAINTENANCE_TYPE_SERVICE:
            for field, legacy_key in {
                MAINTENANCE_LAST_KM: CONF_LAST_SERVICE_KM,
                MAINTENANCE_LAST_DATE: CONF_LAST_SERVICE_DATE,
                MAINTENANCE_INTERVAL_KM: CONF_SERVICE_INTERVAL_KM,
                MAINTENANCE_INTERVAL_DAYS: CONF_SERVICE_INTERVAL_DAYS,
            }.items():
                if legacy_key not in normalized:
                    default_value = defaults.get(field)
                    if default_value is not None:
                        normalized[legacy_key] = default_value
                        changed = True
                elif field in defaults and not normalized.get(legacy_key):
                    default_value = defaults[field]
                    if default_value:
                        normalized[legacy_key] = default_value
                        changed = True
            continue

        storage_key = maintenance_storage_key(maintenance_type)
        if storage_key not in normalized or not isinstance(normalized[storage_key], dict):
            normalized[storage_key] = {}
            changed = True

        for field, default_value in defaults.items():
            if field not in normalized[storage_key]:
                normalized[storage_key][field] = default_value
                changed = True
            elif field in (MAINTENANCE_INTERVAL_KM, MAINTENANCE_INTERVAL_DAYS):
                if not normalized[storage_key].get(field) and default_value:
                    normalized[storage_key][field] = default_value
                    changed = True

    if CONF_CONSUMABLES not in normalized or not isinstance(normalized[CONF_CONSUMABLES], dict):
        normalized[CONF_CONSUMABLES] = {}
        changed = True

    for consumable_key, default_value in DEFAULT_CONSUMABLE_VALUES.items():
        if consumable_key not in normalized[CONF_CONSUMABLES]:
            normalized[CONF_CONSUMABLES][consumable_key] = default_value
            changed = True

    return normalized, changed


def normalize_vehicles(vehicles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Normalize all vehicles."""

    normalized_vehicles: list[dict[str, Any]] = []
    changed = False

    for vehicle in vehicles:
        normalized_vehicle, vehicle_changed = normalize_vehicle(vehicle)
        normalized_vehicles.append(normalized_vehicle)
        changed = changed or vehicle_changed

    return normalized_vehicles, changed


def maintenance_remaining_values(
    vehicle: dict[str, Any],
    maintenance_type: str,
) -> tuple[int | None, int | None]:
    """Return remaining kilometers and days for a maintenance type."""

    current_km = int(vehicle.get("km", 0) or 0)

    last_km_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_KM)
    interval_km_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_INTERVAL_KM)
    last_date = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_DATE)
    interval_days_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_INTERVAL_DAYS)

    last_km = int(last_km_raw) if last_km_raw is not None else None
    interval_km = int(interval_km_raw) if interval_km_raw is not None else None
    interval_days = int(interval_days_raw) if interval_days_raw is not None else None

    return (
        calculate_km_remaining(current_km, last_km, interval_km),
        calculate_days_remaining(last_date, interval_days),
    )


def maintenance_status(vehicle: dict[str, Any], maintenance_type: str) -> str:
    """Return calculated status for a maintenance type."""

    km_remaining, days_remaining = maintenance_remaining_values(vehicle, maintenance_type)
    return calculate_maintenance_status(km_remaining, days_remaining)
