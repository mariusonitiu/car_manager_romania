"""Maintenance helpers for Car Manager România."""

from __future__ import annotations

from datetime import date
from typing import Any

from .const import (
    CONF_LAST_SERVICE_DATE,
    CONF_LAST_SERVICE_KM,
    CONF_SERVICE_INTERVAL_DAYS,
    CONF_SERVICE_INTERVAL_KM,
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
)


def maintenance_storage_key(maintenance_type: str) -> str:
    """Return storage key for a maintenance type."""

    return f"maintenance_{maintenance_type}"


def get_maintenance_value(
    vehicle: dict[str, Any],
    maintenance_type: str,
    field: str,
) -> Any:
    """Return maintenance value with compatibility for old service fields."""

    if maintenance_type == MAINTENANCE_TYPE_SERVICE:
        legacy_map = {
            MAINTENANCE_LAST_KM: CONF_LAST_SERVICE_KM,
            MAINTENANCE_LAST_DATE: CONF_LAST_SERVICE_DATE,
            MAINTENANCE_INTERVAL_KM: CONF_SERVICE_INTERVAL_KM,
            MAINTENANCE_INTERVAL_DAYS: CONF_SERVICE_INTERVAL_DAYS,
        }

        legacy_key = legacy_map.get(field)
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
        legacy_map = {
            MAINTENANCE_LAST_KM: CONF_LAST_SERVICE_KM,
            MAINTENANCE_LAST_DATE: CONF_LAST_SERVICE_DATE,
            MAINTENANCE_INTERVAL_KM: CONF_SERVICE_INTERVAL_KM,
            MAINTENANCE_INTERVAL_DAYS: CONF_SERVICE_INTERVAL_DAYS,
        }

        legacy_key = legacy_map.get(field)
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