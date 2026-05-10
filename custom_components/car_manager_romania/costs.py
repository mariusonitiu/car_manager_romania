"""Cost and upcoming expense helpers for Car Manager România."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .const import (
    CONF_KM,
    CONF_LEGAL_TERMS,
    COST_AMOUNT,
    LEGAL_END_DATE,
    LEGAL_TYPE_ROVINIETA,
    LEGAL_TYPE_CASCO,
    LEGAL_TYPES,
    MAINTENANCE_TYPES,
)
from .legal import get_legal_value, legal_days_remaining, legal_status, is_legal_ignored
from .maintenance import (
    get_maintenance_value,
    maintenance_remaining_values,
    maintenance_status,
    parse_date,
)


def safe_cost(value: Any) -> float:
    """Return a safe positive cost value."""

    try:
        cost = float(value or 0)
    except (TypeError, ValueError):
        return 0.0

    return max(round(cost, 2), 0.0)


def maintenance_cost(vehicle: dict[str, Any], maintenance_type: str) -> float:
    """Return estimated cost for one maintenance type."""

    return safe_cost(get_maintenance_value(vehicle, maintenance_type, COST_AMOUNT))


def legal_cost(vehicle: dict[str, Any], legal_type: str) -> float:
    """Return estimated cost for one legal term."""

    return safe_cost(get_legal_value(vehicle, legal_type, COST_AMOUNT))


def _format_due_date(days_remaining: int | None) -> str:
    """Return ISO due date calculated from remaining days."""

    if days_remaining is None:
        return ""

    return (date.today() + timedelta(days=max(days_remaining, 0))).isoformat()


def _plate_key(plate: str | None) -> str:
    """Normalize a license plate for matching."""

    return (plate or "").replace(" ", "").upper()


def _rovinieta_expense_from_coordinator(entry: Any, vehicle: dict[str, Any]) -> dict[str, Any] | None:
    """Build rovinieta expense item from the e-rovinieta coordinator, when available."""

    coordinator = getattr(entry.runtime_data, "rovinieta_coordinator", None)
    if coordinator is None or coordinator.data is None:
        return None

    wanted = _plate_key(vehicle.get("license_plate"))
    if not wanted:
        return None

    for rovinieta_vehicle in coordinator.data.vehicles:
        if _plate_key(rovinieta_vehicle.plate_no) != wanted:
            continue

        days_remaining = rovinieta_vehicle.days_remaining
        due_date = ""
        if rovinieta_vehicle.expiry is not None:
            local_dt: datetime = rovinieta_vehicle.expiry.astimezone()
            due_date = local_dt.date().isoformat()

        return {
            "category": "legal",
            "key": LEGAL_TYPE_ROVINIETA,
            "label": "Rovinietă",
            "status": "expiră" if rovinieta_vehicle.has_active_vignette else "expirată",
            "days_remaining": days_remaining,
            "km_remaining": None,
            "due_date": due_date,
            "cost": legal_cost(vehicle, LEGAL_TYPE_ROVINIETA),
        }

    return None


def _manual_rovinieta_expense(vehicle: dict[str, Any]) -> dict[str, Any] | None:
    """Build fallback manual rovinieta expense item, if a manual expiry date exists."""

    legal_terms = vehicle.get(CONF_LEGAL_TERMS, {})
    if not isinstance(legal_terms, dict):
        return None

    rovinieta_data = legal_terms.get(LEGAL_TYPE_ROVINIETA, {})
    if not isinstance(rovinieta_data, dict):
        return None

    end_date = parse_date(rovinieta_data.get(LEGAL_END_DATE))
    if end_date is None:
        return None

    days_remaining = max((end_date - date.today()).days, 0)
    return {
        "category": "legal",
        "key": LEGAL_TYPE_ROVINIETA,
        "label": "Rovinietă",
        "status": "expirată" if end_date < date.today() else "expiră",
        "days_remaining": days_remaining,
        "km_remaining": None,
        "due_date": end_date.isoformat(),
        "cost": legal_cost(vehicle, LEGAL_TYPE_ROVINIETA),
    }


def upcoming_expense_items(
    entry: Any,
    vehicle: dict[str, Any],
    horizon_days: int,
    *,
    only_with_cost: bool = False,
) -> list[dict[str, Any]]:
    """Return upcoming expenses for a vehicle within the requested horizon."""

    items: list[dict[str, Any]] = []

    for maintenance_type, label in MAINTENANCE_TYPES.items():
        km_remaining, days_remaining = maintenance_remaining_values(vehicle, maintenance_type)
        cost = maintenance_cost(vehicle, maintenance_type)
        if days_remaining is None:
            continue
        if days_remaining > horizon_days:
            continue
        if only_with_cost and cost <= 0:
            continue

        items.append(
            {
                "category": "maintenance",
                "key": maintenance_type,
                "label": label,
                "status": maintenance_status(vehicle, maintenance_type),
                "days_remaining": days_remaining,
                "km_remaining": km_remaining,
                "due_date": _format_due_date(days_remaining),
                "cost": cost,
            }
        )

    for legal_type, label in LEGAL_TYPES.items():
        if legal_type == LEGAL_TYPE_CASCO and is_legal_ignored(vehicle, legal_type):
            continue

        days_remaining = legal_days_remaining(vehicle, legal_type)
        cost = legal_cost(vehicle, legal_type)
        if days_remaining is None:
            continue
        if days_remaining > horizon_days:
            continue
        if only_with_cost and cost <= 0:
            continue

        items.append(
            {
                "category": "legal",
                "key": legal_type,
                "label": label,
                "status": legal_status(vehicle, legal_type),
                "days_remaining": days_remaining,
                "km_remaining": None,
                "due_date": str(get_legal_value(vehicle, legal_type, LEGAL_END_DATE) or ""),
                "cost": cost,
            }
        )

    rovinieta_item = _rovinieta_expense_from_coordinator(entry, vehicle) or _manual_rovinieta_expense(vehicle)
    if rovinieta_item is not None:
        days_remaining = rovinieta_item.get("days_remaining")
        cost = safe_cost(rovinieta_item.get("cost"))
        if days_remaining is not None and int(days_remaining) <= horizon_days:
            if not only_with_cost or cost > 0:
                rovinieta_item["cost"] = cost
                items.append(rovinieta_item)

    items.sort(
        key=lambda item: (
            int(item.get("days_remaining") if item.get("days_remaining") is not None else 999999),
            str(item.get("label", "")),
        )
    )
    return items


def expense_total(items: list[dict[str, Any]]) -> float:
    """Return total cost for a list of expense items."""

    return round(sum(safe_cost(item.get("cost")) for item in items), 2)


def annual_history_total(entry: Any, vehicle: dict[str, Any], year: int | None = None) -> float:
    """Return total historic costs for one vehicle in a year."""

    wanted_year = year or date.today().year
    vehicle_id = str(vehicle.get("vehicle_id", ""))
    records = getattr(entry.runtime_data.service_history_store, "_records", [])
    total = 0.0

    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("vehicle_id", "")) != vehicle_id:
            continue

        record_date = parse_date(record.get("date"))
        if record_date is None or record_date.year != wanted_year:
            continue

        total += safe_cost(record.get(COST_AMOUNT))

    return round(total, 2)
