"""Notification logic for Car Manager România."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from . import CarManagerConfigEntry
from .const import (
    CONF_LICENSE_PLATE,
    CONF_NAME,
    LEGAL_STATUS_EXPIRED,
    LEGAL_STATUS_SOON,
    LEGAL_STATUS_UNKNOWN,
    LEGAL_STATUS_VALID,
    LEGAL_TYPES,
    MAINTENANCE_STATUS_OK,
    MAINTENANCE_STATUS_OVERDUE,
    MAINTENANCE_STATUS_SOON,
    MAINTENANCE_STATUS_UNKNOWN,
    MAINTENANCE_TYPES,
)
from .legal import legal_days_remaining, legal_status
from .maintenance import maintenance_remaining_values, maintenance_status
from .rovinieta.models import VehicleData
from .storage import CarManagerNotificationStore

ROVINIETA_SOON_DAYS_THRESHOLD = 30


def _safe_key(value: str) -> str:
    """Return a storage/notification safe key."""

    return value.replace(".", "_").replace("/", "_").replace(" ", "_").lower()


def _vehicle_label(vehicle: dict[str, Any]) -> str:
    """Return human readable vehicle label."""

    name = vehicle.get(CONF_NAME) or "Autovehicul"
    plate = vehicle.get(CONF_LICENSE_PLATE)
    return f"{name} ({plate})" if plate else str(name)


def _plate_key(plate: str | None) -> str:
    """Normalize a license plate for matching."""

    return (plate or "").replace(" ", "").upper()


def _notification_key(vehicle_id: str, category: str, item_type: str) -> str:
    """Return storage notification key."""

    return f"{vehicle_id}:{category}:{item_type}"


def _notification_id(vehicle_id: str, category: str, item_type: str) -> str:
    """Return Home Assistant persistent notification ID."""

    return f"car_manager_romania_{_safe_key(vehicle_id)}_{category}_{_safe_key(item_type)}"


def _format_days(days_remaining: int | None) -> str:
    """Return a clear Romanian phrase for remaining days."""

    if days_remaining is None:
        return "Zile rămase: necunoscut."

    if days_remaining == 0:
        return "Expiră astăzi."

    if days_remaining == 1:
        return "Mai este 1 zi."

    return f"Mai sunt {days_remaining} zile."


def _format_km(km_remaining: int | None) -> str | None:
    """Return a clear Romanian phrase for remaining kilometers."""

    if km_remaining is None:
        return None

    if km_remaining <= 0:
        return f"Kilometraj depășit cu {abs(km_remaining)} km."

    return f"Mai sunt {km_remaining} km."


def _status_title(label: str, status: str) -> str:
    """Return notification title according to status."""

    if status in (MAINTENANCE_STATUS_OVERDUE, LEGAL_STATUS_EXPIRED, "expirată"):
        return f"Car Manager România: {label} expirat/depășit"

    return f"Car Manager România: {label} expiră în curând"


def _build_maintenance_message(
    vehicle: dict[str, Any],
    maintenance_label: str,
    status: str,
    km_remaining: int | None,
    days_remaining: int | None,
) -> str:
    """Build maintenance notification message."""

    vehicle_name = _vehicle_label(vehicle)
    if status == MAINTENANCE_STATUS_OVERDUE:
        first_line = f"{maintenance_label} pentru {vehicle_name} este depășită."
    else:
        first_line = f"{maintenance_label} pentru {vehicle_name} se apropie de termen."

    parts = [first_line]

    km_text = _format_km(km_remaining)
    if km_text:
        parts.append(km_text)

    if days_remaining is not None:
        parts.append(_format_days(days_remaining))

    parts.append("Verifică datele și actualizează intervenția după efectuare.")
    return "\n".join(parts)


def _build_legal_message(
    vehicle: dict[str, Any],
    label: str,
    status: str,
    days_remaining: int | None,
) -> str:
    """Build legal term notification message."""

    vehicle_name = _vehicle_label(vehicle)
    if status == LEGAL_STATUS_EXPIRED:
        first_line = f"{label} pentru {vehicle_name} este expirat."
    else:
        first_line = f"{label} pentru {vehicle_name} expiră în curând."

    return "\n".join(
        [
            first_line,
            _format_days(days_remaining),
            "Actualizează data de expirare după reînnoire.",
        ]
    )


def _find_rovinieta_vehicle(
    entry: CarManagerConfigEntry,
    vehicle: dict[str, Any],
) -> VehicleData | None:
    """Find matching e-rovinieta vehicle for a Car Manager vehicle."""

    coordinator = entry.runtime_data.rovinieta_coordinator
    if coordinator is None or coordinator.data is None:
        return None

    wanted = _plate_key(vehicle.get(CONF_LICENSE_PLATE))
    if not wanted:
        return None

    for rovinieta_vehicle in coordinator.data.vehicles:
        if _plate_key(rovinieta_vehicle.plate_no) == wanted:
            return rovinieta_vehicle

    return None


def _rovinieta_status(rovinieta_vehicle: VehicleData) -> str:
    """Return notification-relevant rovinieta status."""

    if not rovinieta_vehicle.has_active_vignette:
        return "expirată"

    days_remaining = rovinieta_vehicle.days_remaining
    if days_remaining is None:
        return "necunoscut"

    if days_remaining < 0:
        return "expirată"

    if days_remaining <= ROVINIETA_SOON_DAYS_THRESHOLD:
        return "expiră în curând"

    return "validă"


def _format_rovinieta_expiry(rovinieta_vehicle: VehicleData) -> str | None:
    """Return formatted rovinieta expiry date."""

    if rovinieta_vehicle.expiry is None:
        return None

    local_dt: datetime = rovinieta_vehicle.expiry.astimezone()
    return local_dt.strftime("%d.%m.%Y %H:%M")


def _build_rovinieta_message(
    vehicle: dict[str, Any],
    rovinieta_vehicle: VehicleData,
    status: str,
) -> str:
    """Build rovinieta notification message."""

    vehicle_name = _vehicle_label(vehicle)
    if status == "expirată":
        first_line = f"Rovinieta pentru {vehicle_name} nu este activă sau este expirată."
    else:
        first_line = f"Rovinieta pentru {vehicle_name} expiră în curând."

    parts = [first_line]
    parts.append(_format_days(rovinieta_vehicle.days_remaining))

    expiry = _format_rovinieta_expiry(rovinieta_vehicle)
    if expiry:
        parts.append(f"Expiră la: {expiry}.")

    if rovinieta_vehicle.active_vignette:
        serie = rovinieta_vehicle.active_vignette.get("oProdVignetteSerie")
        if serie:
            parts.append(f"Serie rovinietă: {serie}.")

    parts.append("Verifică datele din e-rovinieta.ro înainte de drum.")
    return "\n".join(parts)


async def _handle_notification(
    hass: HomeAssistant,
    store: CarManagerNotificationStore,
    key: str,
    notification_id: str,
    status: str,
    title: str,
    message: str,
) -> None:
    """Create a persistent notification only when the stored status changed."""

    already_notified_status = await store.async_get_notified_status(key)
    if already_notified_status == status:
        return

    persistent_notification.async_create(
        hass,
        message,
        title=title,
        notification_id=notification_id,
    )
    await store.async_set_notified_status(key, status)


async def _clear_notification(
    hass: HomeAssistant,
    store: CarManagerNotificationStore,
    key: str,
    notification_id: str,
) -> None:
    """Clear notification state and dismiss existing persistent notification."""

    await store.async_clear_notified_status(key)
    persistent_notification.async_dismiss(hass, notification_id)


async def async_check_maintenance_notifications(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Create persistent notifications for maintenance, legal terms and rovinieta."""

    store = CarManagerNotificationStore(hass)

    for vehicle in entry.runtime_data.vehicles:
        vehicle_id = vehicle["vehicle_id"]

        for maintenance_type, maintenance_label in MAINTENANCE_TYPES.items():
            status = maintenance_status(vehicle, maintenance_type)
            key = _notification_key(vehicle_id, "maintenance", maintenance_type)
            notification_id = _notification_id(vehicle_id, "maintenance", maintenance_type)

            if status in (MAINTENANCE_STATUS_OK, MAINTENANCE_STATUS_UNKNOWN):
                await _clear_notification(hass, store, key, notification_id)
                continue

            if status not in (MAINTENANCE_STATUS_SOON, MAINTENANCE_STATUS_OVERDUE):
                continue

            km_remaining, days_remaining = maintenance_remaining_values(
                vehicle,
                maintenance_type,
            )
            await _handle_notification(
                hass,
                store,
                key,
                notification_id,
                status,
                _status_title(maintenance_label, status),
                _build_maintenance_message(
                    vehicle,
                    maintenance_label,
                    status,
                    km_remaining,
                    days_remaining,
                ),
            )

        for legal_type, legal_label in LEGAL_TYPES.items():
            current_legal_status = legal_status(vehicle, legal_type)
            key = _notification_key(vehicle_id, "legal", legal_type)
            notification_id = _notification_id(vehicle_id, "legal", legal_type)

            if current_legal_status in (LEGAL_STATUS_VALID, LEGAL_STATUS_UNKNOWN):
                await _clear_notification(hass, store, key, notification_id)
                continue

            if current_legal_status not in (LEGAL_STATUS_SOON, LEGAL_STATUS_EXPIRED):
                continue

            await _handle_notification(
                hass,
                store,
                key,
                notification_id,
                current_legal_status,
                _status_title(legal_label, current_legal_status),
                _build_legal_message(
                    vehicle,
                    legal_label,
                    current_legal_status,
                    legal_days_remaining(vehicle, legal_type),
                ),
            )

        rovinieta_vehicle = _find_rovinieta_vehicle(entry, vehicle)
        rovinieta_key = _notification_key(vehicle_id, "legal", "rovinieta")
        rovinieta_notification_id = _notification_id(vehicle_id, "legal", "rovinieta")

        if rovinieta_vehicle is None:
            await _clear_notification(hass, store, rovinieta_key, rovinieta_notification_id)
            continue

        current_rovinieta_status = _rovinieta_status(rovinieta_vehicle)
        if current_rovinieta_status in ("validă", "necunoscut"):
            await _clear_notification(hass, store, rovinieta_key, rovinieta_notification_id)
            continue

        await _handle_notification(
            hass,
            store,
            rovinieta_key,
            rovinieta_notification_id,
            current_rovinieta_status,
            _status_title("Rovinietă", current_rovinieta_status),
            _build_rovinieta_message(
                vehicle,
                rovinieta_vehicle,
                current_rovinieta_status,
            ),
        )
