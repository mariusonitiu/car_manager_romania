"""Modul pentru bonurile și calculele de combustibil."""

from __future__ import annotations

from datetime import date as dt_date
from typing import Any

from .const import (
    CONF_FUEL_PROFILE,
    FUEL_LIQUID_TYPES,
    FUEL_PROFILE_DIESEL,
    FUEL_PROFILES,
    FUEL_TYPES,
    FUEL_TYPES_BY_PROFILE,
)


def vehicle_fuel_profile(vehicle: dict[str, Any]) -> str:
    """Funcție pentru vehicul combustibil profil."""

    profile = str(vehicle.get(CONF_FUEL_PROFILE, "") or "").strip()
    if profile in FUEL_PROFILES:
        return profile
    return FUEL_PROFILE_DIESEL


def allowed_fuel_types(vehicle: dict[str, Any]) -> list[str]:
    """Funcție pentru permise combustibil tipuri."""

    return list(FUEL_TYPES_BY_PROFILE.get(vehicle_fuel_profile(vehicle), FUEL_TYPES_BY_PROFILE[FUEL_PROFILE_DIESEL]))


def fuel_type_label(fuel_type: str) -> str:
    """Funcție pentru combustibil tip etichetă."""

    return FUEL_TYPES.get(fuel_type, fuel_type.replace("_", " ").title())


def is_liquid_fuel(fuel_type: str) -> bool:
    """Funcție pentru is lichid combustibil."""

    return fuel_type in FUEL_LIQUID_TYPES


def fuel_receipts_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Funcție pentru combustibil bonuri for vehicul."""

    vehicle_id = str(vehicle.get("vehicle_id", ""))
    store = getattr(entry.runtime_data, "fuel_receipt_store", None)
    records = getattr(store, "_receipts", []) if store is not None else []
    receipts = [record for record in records if isinstance(record, dict) and str(record.get("vehicle_id", "")) == vehicle_id]
    receipts.sort(key=lambda item: (str(item.get("date", "")), int(item.get("km", 0) or 0), str(item.get("receipt_id", ""))))
    return receipts


def fuel_current_year_total(entry: Any, vehicle: dict[str, Any]) -> float:
    """Funcție pentru combustibil curent an total."""

    year = dt_date.today().year
    total = 0.0
    for receipt in fuel_receipts_for_vehicle(entry, vehicle):
        try:
            if dt_date.fromisoformat(str(receipt.get("date", ""))).year != year:
                continue
        except ValueError:
            continue
        total += float(receipt.get("total_cost", 0) or 0)
    return round(total, 2)


def fuel_current_month_total(entry: Any, vehicle: dict[str, Any]) -> float:
    """Funcție pentru combustibil curent lună total."""

    today = dt_date.today()
    total = 0.0
    for receipt in fuel_receipts_for_vehicle(entry, vehicle):
        try:
            receipt_date = dt_date.fromisoformat(str(receipt.get("date", "")))
        except ValueError:
            continue
        if receipt_date.year == today.year and receipt_date.month == today.month:
            total += float(receipt.get("total_cost", 0) or 0)
    return round(total, 2)


def enrich_fuel_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Funcție pentru enrich combustibil bon."""

    enriched = dict(receipt)
    quantity = float(enriched.get("quantity", 0) or 0)
    total_cost = float(enriched.get("total_cost", 0) or 0)
    fuel_type = str(enriched.get("fuel_type", ""))
    enriched["fuel_type_label"] = fuel_type_label(fuel_type)
    enriched["unit"] = "L" if is_liquid_fuel(fuel_type) else "kWh"
    enriched["unit_price"] = round(total_cost / quantity, 3) if quantity > 0 else 0
    return enriched


def enriched_fuel_receipts_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Funcție pentru enriched combustibil bonuri for vehicul."""

    receipts = [enrich_fuel_receipt(receipt) for receipt in fuel_receipts_for_vehicle(entry, vehicle)]
    receipts.sort(key=lambda item: (str(item.get("date", "")), int(item.get("km", 0) or 0), str(item.get("receipt_id", ""))), reverse=True)
    return receipts


def fuel_consumption_intervals(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    """Funcție pentru combustibil consum intervals."""

    receipts = [receipt for receipt in fuel_receipts_for_vehicle(entry, vehicle) if is_liquid_fuel(str(receipt.get("fuel_type", "")))]
    receipts.sort(key=lambda item: (str(item.get("date", "")), int(item.get("km", 0) or 0), str(item.get("receipt_id", ""))))

    intervals: list[dict[str, Any]] = []
    baseline: dict[str, Any] | None = None
    liters_since_baseline = 0.0
    cost_since_baseline = 0.0

    for receipt in receipts:
        km = int(receipt.get("km", 0) or 0)
        liters = float(receipt.get("quantity", 0) or 0)
        total_cost = float(receipt.get("total_cost", 0) or 0)
        is_full = bool(receipt.get("full_tank", False))

        if baseline is None:
            if is_full and km > 0:
                baseline = receipt
                liters_since_baseline = 0.0
                cost_since_baseline = 0.0
            continue

        liters_since_baseline += liters
        cost_since_baseline += total_cost

        if not is_full:
            continue

        start_km = int(baseline.get("km", 0) or 0)
        distance = km - start_km
        if distance > 0 and liters_since_baseline > 0:
            intervals.append(
                {
                    "start_date": baseline.get("date", ""),
                    "end_date": receipt.get("date", ""),
                    "start_km": start_km,
                    "end_km": km,
                    "distance_km": distance,
                    "liters": round(liters_since_baseline, 2),
                    "cost": round(cost_since_baseline, 2),
                    "consumption_l_100km": round((liters_since_baseline / distance) * 100, 2),
                    "cost_per_km": round(cost_since_baseline / distance, 3),
                }
            )

        baseline = receipt
        liters_since_baseline = 0.0
        cost_since_baseline = 0.0

    intervals.sort(key=lambda item: (str(item.get("end_date", "")), int(item.get("end_km", 0))), reverse=True)
    return intervals


def latest_average_consumption(entry: Any, vehicle: dict[str, Any]) -> float | None:
    """Funcție pentru ultim mediu consum."""

    intervals = fuel_consumption_intervals(entry, vehicle)
    if not intervals:
        return None
    return float(intervals[0]["consumption_l_100km"])
