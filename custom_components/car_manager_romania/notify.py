"""Notification logic for Car Manager România."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from . import CarManagerConfigEntry
from .const import (
    CONF_LICENSE_PLATE,
    CONF_NAME,
    MAINTENANCE_STATUS_OK,
    MAINTENANCE_STATUS_OVERDUE,
    MAINTENANCE_STATUS_SOON,
    MAINTENANCE_STATUS_UNKNOWN,
    MAINTENANCE_TYPES,
    LEGAL_STATUS_EXPIRED,
    LEGAL_STATUS_SOON,
    LEGAL_TYPE_RCA,
)
from .legal import legal_days_remaining, legal_status
from .maintenance import maintenance_remaining_values, maintenance_status
from .storage import CarManagerNotificationStore


def _notification_key(vehicle_id: str, maintenance_type: str) -> str:
    """Return storage notification key."""

    return f"{vehicle_id}:{maintenance_type}"


def _notification_id(vehicle_id: str, maintenance_type: str) -> str:
    """Return Home Assistant persistent notification ID."""

    safe_vehicle_id = vehicle_id.replace(".", "_").replace("/", "_")
    return f"car_manager_romania_{safe_vehicle_id}_{maintenance_type}"


def _vehicle_label(vehicle: dict) -> str:
    """Return human readable vehicle label."""

    name = vehicle.get(CONF_NAME) or "Autovehicul"
    plate = vehicle.get(CONF_LICENSE_PLATE)
    return f"{name} ({plate})" if plate else str(name)


def _build_message(
    vehicle: dict,
    maintenance_label: str,
    status: str,
    km_remaining: int | None,
    days_remaining: int | None,
) -> str:
    """Build notification message."""

    vehicle_name = _vehicle_label(vehicle)
    parts = [f"{maintenance_label} pentru {vehicle_name}: {status}."]

    if km_remaining is not None:
        parts.append(f"Km rămași: {km_remaining} km.")

    if days_remaining is not None:
        parts.append(f"Zile rămase: {days_remaining} zile.")

    return "\n".join(parts)


def _build_legal_message(
    vehicle: dict,
    label: str,
    status: str,
    days_remaining: int | None,
) -> str:
    """Build legal term notification message."""

    vehicle_name = _vehicle_label(vehicle)
    parts = [f"{label} pentru {vehicle_name}: {status}."]

    if days_remaining is not None:
        parts.append(f"Zile rămase: {days_remaining} zile.")

    return "\n".join(parts)


def _legal_notification_key(vehicle_id: str, legal_type: str) -> str:
    """Return storage notification key for a legal term."""

    return f"{vehicle_id}:legal:{legal_type}"


def _legal_notification_id(vehicle_id: str, legal_type: str) -> str:
    """Return persistent notification ID for a legal term."""

    safe_vehicle_id = vehicle_id.replace(".", "_").replace("/", "_")
    return f"car_manager_romania_{safe_vehicle_id}_legal_{legal_type}"


async def async_check_maintenance_notifications(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Create persistent notifications for soon/overdue maintenance and legal terms."""

    store = CarManagerNotificationStore(hass)

    for vehicle in entry.runtime_data.vehicles:
        vehicle_id = vehicle["vehicle_id"]

        for maintenance_type, maintenance_label in MAINTENANCE_TYPES.items():
            status = maintenance_status(vehicle, maintenance_type)
            key = _notification_key(vehicle_id, maintenance_type)
            notification_id = _notification_id(vehicle_id, maintenance_type)

            if status in (MAINTENANCE_STATUS_OK, MAINTENANCE_STATUS_UNKNOWN):
                await store.async_clear_notified_status(key)
                persistent_notification.async_dismiss(hass, notification_id)
                continue

            if status not in (MAINTENANCE_STATUS_SOON, MAINTENANCE_STATUS_OVERDUE):
                continue

            already_notified_status = await store.async_get_notified_status(key)
            if already_notified_status == status:
                continue

            km_remaining, days_remaining = maintenance_remaining_values(
                vehicle,
                maintenance_type,
            )

            persistent_notification.async_create(
                hass,
                _build_message(
                    vehicle,
                    maintenance_label,
                    status,
                    km_remaining,
                    days_remaining,
                ),
                title="Car Manager România",
                notification_id=notification_id,
            )

            await store.async_set_notified_status(key, status)

        rca_status = legal_status(vehicle, LEGAL_TYPE_RCA)
        rca_key = _legal_notification_key(vehicle_id, LEGAL_TYPE_RCA)
        rca_notification_id = _legal_notification_id(vehicle_id, LEGAL_TYPE_RCA)

        if rca_status not in (LEGAL_STATUS_SOON, LEGAL_STATUS_EXPIRED):
            await store.async_clear_notified_status(rca_key)
            persistent_notification.async_dismiss(hass, rca_notification_id)
            continue

        already_notified_rca_status = await store.async_get_notified_status(rca_key)
        if already_notified_rca_status == rca_status:
            continue

        persistent_notification.async_create(
            hass,
            _build_legal_message(
                vehicle,
                "RCA",
                rca_status,
                legal_days_remaining(vehicle, LEGAL_TYPE_RCA),
            ),
            title="Car Manager România",
            notification_id=rca_notification_id,
        )

        await store.async_set_notified_status(rca_key, rca_status)
