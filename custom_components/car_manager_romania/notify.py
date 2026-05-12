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
    LEGAL_TYPE_CASCO,
    LEGAL_TYPES,
    MAINTENANCE_STATUS_OK,
    MAINTENANCE_STATUS_OVERDUE,
    MAINTENANCE_STATUS_SOON,
    MAINTENANCE_STATUS_UNKNOWN,
    MAINTENANCE_TYPES,
)
from .costs import expense_total, upcoming_expense_items
from .equipment import equipment_issues_for_vehicle
from .battery import battery_issues_for_vehicle
from .legal import legal_days_remaining, legal_status, is_legal_ignored
from .maintenance import maintenance_remaining_values, maintenance_status
from .license import async_get_global_license, extract_stored_license_result, license_is_accepted
from .rovinieta.models import VehicleData
from .storage import CarManagerNotificationStore

ROVINIETA_SOON_DAYS_THRESHOLD = 30
MAX_ITEMS_IN_NOTIFICATION = 8


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


def _overall_notification_key(vehicle_id: str) -> str:
    """Return storage key for aggregated vehicle notification."""

    return _notification_key(vehicle_id, "overall", "summary")


def _overall_notification_id(vehicle_id: str) -> str:
    """Return persistent notification id for aggregated vehicle notification."""

    return _notification_id(vehicle_id, "overall", "summary")


def _expenses_notification_key(vehicle_id: str) -> str:
    """Return storage key for upcoming expense notification."""

    return _notification_key(vehicle_id, "expenses", "upcoming_90_days")


def _expenses_notification_id(vehicle_id: str) -> str:
    """Return persistent notification id for upcoming expense notification."""

    return _notification_id(vehicle_id, "expenses", "upcoming_90_days")


def _format_days(days_remaining: int | None) -> str:
    """Return a clear Romanian phrase for remaining days."""

    if days_remaining is None:
        return "Zile rămase: necunoscut."

    if days_remaining < 0:
        return f"Depășit de {abs(days_remaining)} zile."

    if days_remaining == 0:
        return "Expiră astăzi."

    if days_remaining == 1:
        return "Mai este 1 zi."

    return f"Mai sunt {days_remaining} zile."


def _format_item_detail(
    *,
    status: str,
    days_remaining: int | None = None,
    km_remaining: int | None = None,
) -> str:
    """Return a compact item detail for aggregated notifications."""

    parts: list[str] = [status]
    if days_remaining is not None:
        parts.append(f"{days_remaining} zile")
    if km_remaining is not None:
        parts.append(f"{km_remaining} km")
    return " · ".join(parts)


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


async def _handle_notification(
    hass: HomeAssistant,
    store: CarManagerNotificationStore,
    key: str,
    notification_id: str,
    fingerprint: str,
    title: str,
    message: str,
) -> None:
    """Create a persistent notification only when the stored fingerprint changed."""

    already_notified_fingerprint = await store.async_get_notified_status(key)
    if already_notified_fingerprint == fingerprint:
        return

    persistent_notification.async_create(
        hass,
        message,
        title=title,
        notification_id=notification_id,
    )
    await store.async_set_notified_status(key, fingerprint)


async def _clear_notification(
    hass: HomeAssistant,
    store: CarManagerNotificationStore,
    key: str,
    notification_id: str,
) -> None:
    """Clear notification state and dismiss existing persistent notification."""

    await store.async_clear_notified_status(key)
    persistent_notification.async_dismiss(hass, notification_id)


def _build_vehicle_issue_summary(
    entry: CarManagerConfigEntry,
    vehicle: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build critical and warning issue lists for one vehicle."""

    critical_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for maintenance_type, maintenance_label in MAINTENANCE_TYPES.items():
        status = maintenance_status(vehicle, maintenance_type)
        if status in (MAINTENANCE_STATUS_OK, MAINTENANCE_STATUS_UNKNOWN):
            continue
        if status not in (MAINTENANCE_STATUS_SOON, MAINTENANCE_STATUS_OVERDUE):
            continue

        km_remaining, days_remaining = maintenance_remaining_values(
            vehicle,
            maintenance_type,
        )
        item = {
            "category": "maintenance",
            "key": maintenance_type,
            "label": maintenance_label,
            "status": status,
            "days_remaining": days_remaining,
            "km_remaining": km_remaining,
            "detail": _format_item_detail(
                status=status,
                days_remaining=days_remaining,
                km_remaining=km_remaining,
            ),
        }
        if status == MAINTENANCE_STATUS_OVERDUE:
            critical_items.append(item)
        else:
            warning_items.append(item)

    for legal_type, legal_label in LEGAL_TYPES.items():
        if legal_type == LEGAL_TYPE_CASCO and is_legal_ignored(vehicle, legal_type):
            continue

        current_legal_status = legal_status(vehicle, legal_type)
        if current_legal_status in (LEGAL_STATUS_VALID, LEGAL_STATUS_UNKNOWN):
            continue
        if current_legal_status not in (LEGAL_STATUS_SOON, LEGAL_STATUS_EXPIRED):
            continue

        days_remaining = legal_days_remaining(vehicle, legal_type)
        item = {
            "category": "legal",
            "key": legal_type,
            "label": legal_label,
            "status": current_legal_status,
            "days_remaining": days_remaining,
            "km_remaining": None,
            "detail": _format_item_detail(
                status=current_legal_status,
                days_remaining=days_remaining,
            ),
        }
        if current_legal_status == LEGAL_STATUS_EXPIRED:
            critical_items.append(item)
        else:
            warning_items.append(item)

    equipment_critical, equipment_warning = equipment_issues_for_vehicle(entry, vehicle)
    critical_items.extend(equipment_critical)
    warning_items.extend(equipment_warning)

    battery_critical, battery_warning = battery_issues_for_vehicle(entry, vehicle)
    critical_items.extend(battery_critical)
    warning_items.extend(battery_warning)

    rovinieta_vehicle = _find_rovinieta_vehicle(entry, vehicle)
    if rovinieta_vehicle is not None:
        current_rovinieta_status = _rovinieta_status(rovinieta_vehicle)
        if current_rovinieta_status not in ("validă", "necunoscut"):
            detail = _format_item_detail(
                status=current_rovinieta_status,
                days_remaining=rovinieta_vehicle.days_remaining,
            )
            expiry = _format_rovinieta_expiry(rovinieta_vehicle)
            if expiry:
                detail = f"{detail} · expiră la {expiry}"

            item = {
                "category": "legal",
                "key": "rovinieta",
                "label": "Rovinietă",
                "status": current_rovinieta_status,
                "days_remaining": rovinieta_vehicle.days_remaining,
                "km_remaining": None,
                "detail": detail,
            }
            if current_rovinieta_status == "expirată":
                critical_items.append(item)
            else:
                warning_items.append(item)

    return critical_items, warning_items


def _build_fingerprint(
    critical_items: list[dict[str, Any]],
    warning_items: list[dict[str, Any]],
) -> str:
    """Build a stable fingerprint so notifications are not repeated at restart."""

    parts: list[str] = []
    for severity, items in (("critical", critical_items), ("warning", warning_items)):
        for item in sorted(
            items,
            key=lambda current: (
                str(current.get("category", "")),
                str(current.get("key", "")),
            ),
        ):
            parts.append(
                "|".join(
                    [
                        severity,
                        str(item.get("category", "")),
                        str(item.get("key", "")),
                        str(item.get("status", "")),
                        str(item.get("days_remaining", "")),
                        str(item.get("km_remaining", "")),
                    ]
                )
            )

    return "\n".join(parts)




def _format_cost(value: Any) -> str:
    """Return formatted RON cost."""

    try:
        cost = float(value or 0)
    except (TypeError, ValueError):
        cost = 0.0

    if cost == int(cost):
        return f"{int(cost)} lei"

    return f"{cost:.2f} lei"


def _build_expenses_fingerprint(items: list[dict[str, Any]]) -> str:
    """Build stable fingerprint for upcoming expenses."""

    parts: list[str] = []
    for item in items:
        parts.append(
            "|".join(
                [
                    str(item.get("category", "")),
                    str(item.get("key", "")),
                    str(item.get("due_date", "")),
                    str(item.get("days_remaining", "")),
                    str(item.get("cost", "")),
                ]
            )
        )
    return "\n".join(parts)


def _append_expense_lines(lines: list[str], items: list[dict[str, Any]]) -> None:
    """Append upcoming expense lines."""

    for item in items[:MAX_ITEMS_IN_NOTIFICATION]:
        days_remaining = item.get("days_remaining")
        if days_remaining is None:
            when = "termen necunoscut"
        elif int(days_remaining) == 0:
            when = "acum / expirat"
        elif int(days_remaining) == 1:
            when = "în 1 zi"
        else:
            when = f"în {int(days_remaining)} zile"

        due_date = item.get("due_date")
        due_text = f", scadență {due_date}" if due_date else ""
        lines.append(f"- {item.get('label', 'Cheltuială')}: {_format_cost(item.get('cost'))} ({when}{due_text})")

    remaining = len(items) - MAX_ITEMS_IN_NOTIFICATION
    if remaining > 0:
        lines.append(f"- încă {remaining} cheltuială/cheltuieli în senzorul dedicat")


def _build_expenses_message(
    vehicle: dict[str, Any],
    urgent_items: list[dict[str, Any]],
    planning_items: list[dict[str, Any]],
) -> str:
    """Build upcoming expenses notification body."""

    all_items = urgent_items + planning_items
    lines: list[str] = [
        f"Cheltuieli estimate pentru {_vehicle_label(vehicle)} în următoarele 90 de zile:",
        f"Total estimat: {_format_cost(expense_total(all_items))}.",
    ]

    if urgent_items:
        lines.append("")
        lines.append("Următoarele 30 de zile:")
        _append_expense_lines(lines, urgent_items)

    if planning_items:
        lines.append("")
        lines.append("Între 31 și 90 de zile:")
        _append_expense_lines(lines, planning_items)

    lines.append("")
    lines.append("Sunt incluse doar elementele pentru care ai introdus un cost estimat mai mare decât 0.")
    return "\n".join(lines)


def _build_overall_title(
    vehicle: dict[str, Any],
    critical_items: list[dict[str, Any]],
) -> str:
    """Build aggregated notification title."""

    vehicle_name = _vehicle_label(vehicle)
    if critical_items:
        return f"Car Manager România: {vehicle_name} are probleme critice"
    return f"Car Manager România: {vehicle_name} are atenționări"


def _append_item_lines(
    lines: list[str],
    items: list[dict[str, Any]],
) -> None:
    """Append compact item lines to a notification body."""

    for item in items[:MAX_ITEMS_IN_NOTIFICATION]:
        lines.append(f"- {item['label']}: {item['detail']}")

    remaining = len(items) - MAX_ITEMS_IN_NOTIFICATION
    if remaining > 0:
        lines.append(f"- încă {remaining} element(e) în card")


def _build_overall_message(
    vehicle: dict[str, Any],
    critical_items: list[dict[str, Any]],
    warning_items: list[dict[str, Any]],
) -> str:
    """Build aggregated notification message."""

    lines: list[str] = [
        f"Stare generală pentru {_vehicle_label(vehicle)}:",
    ]

    if critical_items:
        lines.append("")
        lines.append("Probleme critice:")
        _append_item_lines(lines, critical_items)

    if warning_items:
        lines.append("")
        lines.append("Atenționări:")
        _append_item_lines(lines, warning_items)

    lines.append("")
    lines.append("Deschide cardul Car Manager România pentru detalii și actualizare.")
    return "\n".join(lines)


async def _clear_legacy_item_notifications(
    hass: HomeAssistant,
    store: CarManagerNotificationStore,
    vehicle_id: str,
) -> None:
    """Dismiss legacy per-item notifications replaced by aggregated notifications."""

    for maintenance_type in MAINTENANCE_TYPES:
        await _clear_notification(
            hass,
            store,
            _notification_key(vehicle_id, "maintenance", maintenance_type),
            _notification_id(vehicle_id, "maintenance", maintenance_type),
        )

    for legal_type in LEGAL_TYPES:
        await _clear_notification(
            hass,
            store,
            _notification_key(vehicle_id, "legal", legal_type),
            _notification_id(vehicle_id, "legal", legal_type),
        )

    await _clear_notification(
        hass,
        store,
        _notification_key(vehicle_id, "legal", "rovinieta"),
        _notification_id(vehicle_id, "legal", "rovinieta"),
    )




async def _license_allows_notifications(hass: HomeAssistant) -> bool:
    """Return True when notifications are allowed by the current license mode."""

    storage = await async_get_global_license(hass)
    license_data = extract_stored_license_result(storage=storage)
    return license_is_accepted(license_data)


async def _clear_vehicle_notifications(
    hass: HomeAssistant,
    store: CarManagerNotificationStore,
    vehicle_id: str,
) -> None:
    """Clear all persistent notifications managed for a vehicle."""

    await _clear_legacy_item_notifications(hass, store, vehicle_id)
    await _clear_notification(
        hass,
        store,
        _overall_notification_key(vehicle_id),
        _overall_notification_id(vehicle_id),
    )
    await _clear_notification(
        hass,
        store,
        _expenses_notification_key(vehicle_id),
        _expenses_notification_id(vehicle_id),
    )


async def async_check_maintenance_notifications(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
) -> None:
    """Create one smart persistent notification per vehicle when its issue list changes."""

    store = CarManagerNotificationStore(hass)

    notifications_allowed = await _license_allows_notifications(hass)
    if not notifications_allowed:
        for vehicle in entry.runtime_data.vehicles:
            vehicle_id = str(vehicle["vehicle_id"])
            await _clear_vehicle_notifications(hass, store, vehicle_id)
        return

    for vehicle in entry.runtime_data.vehicles:
        vehicle_id = str(vehicle["vehicle_id"])
        await _clear_legacy_item_notifications(hass, store, vehicle_id)

        critical_items, warning_items = _build_vehicle_issue_summary(entry, vehicle)
        key = _overall_notification_key(vehicle_id)
        notification_id = _overall_notification_id(vehicle_id)

        if not critical_items and not warning_items:
            await _clear_notification(hass, store, key, notification_id)
        else:
            fingerprint = _build_fingerprint(critical_items, warning_items)
            await _handle_notification(
                hass,
                store,
                key,
                notification_id,
                fingerprint,
                _build_overall_title(vehicle, critical_items),
                _build_overall_message(vehicle, critical_items, warning_items),
            )

        expenses = upcoming_expense_items(entry, vehicle, 90, only_with_cost=True)
        expenses_key = _expenses_notification_key(vehicle_id)
        expenses_notification_id = _expenses_notification_id(vehicle_id)
        if not expenses:
            await _clear_notification(hass, store, expenses_key, expenses_notification_id)
            continue

        urgent_expenses = [
            item for item in expenses
            if item.get("days_remaining") is not None and int(item.get("days_remaining") or 0) <= 30
        ]
        planning_expenses = [
            item for item in expenses
            if item.get("days_remaining") is None or int(item.get("days_remaining") or 0) > 30
        ]
        await _handle_notification(
            hass,
            store,
            expenses_key,
            expenses_notification_id,
            _build_expenses_fingerprint(expenses),
            f"Car Manager România: cheltuieli estimate pentru {_vehicle_label(vehicle)}",
            _build_expenses_message(vehicle, urgent_expenses, planning_expenses),
        )
