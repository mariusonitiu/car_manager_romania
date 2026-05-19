"""Statistici agregate pentru vehicule.

Acest modul nu modifică datele salvate. El citește istoricul existent
și pregătește structuri curate, ușor de consumat de cardul Lovelace sau
de alți senzori interni ai integrării.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from .const import CONF_KM, CONF_VEHICLE_ID
from .costs import annual_history_total, safe_cost
from .fuel import (
    fuel_consumption_intervals,
    fuel_current_month_total,
    fuel_current_year_total,
    fuel_receipts_for_vehicle,
    is_liquid_fuel,
    latest_average_consumption,
)
from .maintenance import parse_date


MAX_CHART_POINTS = 36


def _safe_float(value: Any) -> float:
    """Convertește sigur o valoare numerică în float."""

    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    """Convertește sigur o valoare numerică în int."""

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _vehicle_id(vehicle: dict[str, Any]) -> str:
    """Returnează identificatorul intern al vehiculului."""

    return str(vehicle.get(CONF_VEHICLE_ID, vehicle.get("vehicle_id", "")) or "")


def _receipt_date(receipt: dict[str, Any]) -> date | None:
    """Parsează data unui bon de combustibil."""

    return parse_date(receipt.get("date"))


def _history_records_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Returnează intervențiile salvate pentru vehicul."""

    wanted_vehicle_id = _vehicle_id(vehicle)
    records = getattr(entry.runtime_data.service_history_store, "_records", [])
    result: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get(CONF_VEHICLE_ID, record.get("vehicle_id", "")) or "") != wanted_vehicle_id:
            continue
        result.append(record)

    return result


def mileage_points(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Construiește puncte cronologice pentru evoluția kilometrajului."""

    points_by_key: dict[tuple[str, int], dict[str, Any]] = {}

    for receipt in fuel_receipts_for_vehicle(entry, vehicle):
        receipt_date = _receipt_date(receipt)
        km_value = _safe_int(receipt.get(CONF_KM))
        if receipt_date is None or km_value <= 0:
            continue
        key = (receipt_date.isoformat(), km_value)
        points_by_key[key] = {
            "date": receipt_date.isoformat(),
            "km": km_value,
            "source": "fuel_receipt",
        }

    for record in _history_records_for_vehicle(entry, vehicle):
        record_date = parse_date(record.get("date"))
        km_value = _safe_int(record.get(CONF_KM))
        if record_date is None or km_value <= 0:
            continue
        key = (record_date.isoformat(), km_value)
        points_by_key.setdefault(
            key,
            {
                "date": record_date.isoformat(),
                "km": km_value,
                "source": "service_history",
            },
        )

    current_km = _safe_int(vehicle.get(CONF_KM))
    if current_km > 0:
        today = date.today().isoformat()
        points_by_key[(today, current_km)] = {
            "date": today,
            "km": current_km,
            "source": "current_vehicle_km",
        }

    points = sorted(points_by_key.values(), key=lambda item: (str(item.get("date", "")), _safe_int(item.get("km"))))
    return points[-MAX_CHART_POINTS:]


def fuel_monthly_costs(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Grupează costurile de combustibil pe luni calendaristice."""

    totals: dict[str, float] = defaultdict(float)
    quantities: dict[str, float] = defaultdict(float)

    for receipt in fuel_receipts_for_vehicle(entry, vehicle):
        receipt_date = _receipt_date(receipt)
        if receipt_date is None:
            continue

        month_key = f"{receipt_date.year:04d}-{receipt_date.month:02d}"
        totals[month_key] += safe_cost(receipt.get("total_cost"))
        quantities[month_key] += _safe_float(receipt.get("quantity"))

    rows = [
        {
            "month": month,
            "cost": round(totals[month], 2),
            "quantity": round(quantities[month], 2),
        }
        for month in sorted(totals)
    ]
    return rows[-MAX_CHART_POINTS:]


def consumption_chart_points(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Pregătește punctele pentru graficul evoluției consumului."""

    intervals = fuel_consumption_intervals(entry, vehicle)
    intervals.sort(key=lambda item: (str(item.get("end_date", "")), _safe_int(item.get("end_km"))))

    points: list[dict[str, Any]] = []
    for interval in intervals[-MAX_CHART_POINTS:]:
        points.append(
            {
                "date": interval.get("end_date", ""),
                "value": _safe_float(interval.get("consumption_l_100km")),
                "distance_km": _safe_int(interval.get("distance_km")),
                "liters": round(_safe_float(interval.get("liters")), 2),
                "cost": round(_safe_float(interval.get("cost")), 2),
                "cost_per_km": round(_safe_float(interval.get("cost_per_km")), 3),
            }
        )

    return points


def fuel_statistics(entry: Any, vehicle: dict[str, Any]) -> dict[str, Any]:
    """Calculează sumarul de combustibil pentru vehicul."""

    receipts = fuel_receipts_for_vehicle(entry, vehicle)
    intervals = fuel_consumption_intervals(entry, vehicle)
    latest_interval = intervals[0] if intervals else {}

    total_cost = 0.0
    total_quantity = 0.0
    liquid_quantity = 0.0

    for receipt in receipts:
        quantity = _safe_float(receipt.get("quantity"))
        total_cost += safe_cost(receipt.get("total_cost"))
        total_quantity += quantity
        if is_liquid_fuel(str(receipt.get("fuel_type", ""))):
            liquid_quantity += quantity

    return {
        "receipts_count": len(receipts),
        "total_cost": round(total_cost, 2),
        "total_quantity": round(total_quantity, 2),
        "liquid_quantity_l": round(liquid_quantity, 2),
        "current_month_cost": fuel_current_month_total(entry, vehicle),
        "current_year_cost": fuel_current_year_total(entry, vehicle),
        "average_consumption_l_100km": latest_average_consumption(entry, vehicle),
        "last_consumption_l_100km": latest_interval.get("consumption_l_100km") if latest_interval else None,
        "last_cost_per_km": latest_interval.get("cost_per_km") if latest_interval else None,
        "valid_consumption_intervals": len(intervals),
    }


def mileage_statistics(entry: Any, vehicle: dict[str, Any]) -> dict[str, Any]:
    """Calculează statistici simple pentru kilometraj."""

    points = mileage_points(entry, vehicle)
    current_km = _safe_int(vehicle.get(CONF_KM))

    if len(points) < 2:
        return {
            "current_km": current_km,
            "first_known_km": points[0]["km"] if points else None,
            "last_known_km": points[-1]["km"] if points else current_km,
            "known_distance_km": 0,
            "average_km_per_day": None,
            "average_km_per_month": None,
        }

    first = points[0]
    last = points[-1]
    first_date = parse_date(first.get("date"))
    last_date = parse_date(last.get("date"))
    distance = max(_safe_int(last.get("km")) - _safe_int(first.get("km")), 0)

    if first_date is None or last_date is None:
        days = 0
    else:
        days = max((last_date - first_date).days, 0)

    average_per_day = round(distance / days, 2) if days > 0 and distance > 0 else None
    average_per_month = round(average_per_day * 30.44, 1) if average_per_day is not None else None

    return {
        "current_km": current_km,
        "first_known_date": first.get("date"),
        "first_known_km": first.get("km"),
        "last_known_date": last.get("date"),
        "last_known_km": last.get("km"),
        "known_distance_km": distance,
        "known_period_days": days,
        "average_km_per_day": average_per_day,
        "average_km_per_month": average_per_month,
    }


def vehicle_statistics(entry: Any, vehicle: dict[str, Any]) -> dict[str, Any]:
    """Returnează statisticile agregate ale vehiculului."""

    return {
        "fuel": fuel_statistics(entry, vehicle),
        "mileage": mileage_statistics(entry, vehicle),
        "service_history_current_year_cost": annual_history_total(entry, vehicle),
    }


def vehicle_chart_data(entry: Any, vehicle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Returnează date curate pentru graficele viitoare din card."""

    return {
        "consumption": consumption_chart_points(entry, vehicle),
        "mileage": mileage_points(entry, vehicle),
        "fuel_monthly_costs": fuel_monthly_costs(entry, vehicle),
    }
