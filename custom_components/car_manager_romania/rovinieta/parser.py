"""Modul pentru normalizarea datelor brute."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .helpers import clean_text, parse_date_string, parse_unix_timestamp, safe_float
from .models import AccountData, OrderData, VehicleData


def _vehicle_from_raw(raw: dict[str, Any]) -> VehicleData:
    active_items = raw.get("vignette_active_status") or []
    active_item = active_items[0] if active_items else None

    expiry = None
    if active_item:
        expiry = (
            parse_unix_timestamp(active_item.get("oProdTransactionEndDate"))
            or parse_date_string(active_item.get("date_stop_availability"))
            or parse_unix_timestamp(raw.get("end_date"))
        )
    else:
        expiry = parse_unix_timestamp(raw.get("end_date"))

    days_remaining = None
    if expiry:
        days_remaining = (expiry.date() - datetime.now(UTC).date()).days

    return VehicleData(
        id=int(raw["id"]),
        plate_no=str(raw.get("_plateNo", "")),
        chasis_no=clean_text(raw.get("_chasisNo")),
        country_name=clean_text((raw.get("country") or {}).get("country")),
        country_code=clean_text((raw.get("country") or {}).get("ccode")),
        category_vignette_title=clean_text((raw.get("category_vignette") or {}).get("title")),
        category_vignette_desc=clean_text((raw.get("category_vignette") or {}).get("desc")),
        category_toll_title=clean_text((raw.get("category_toll") or {}).get("title")),
        category_toll_desc=clean_text((raw.get("category_toll") or {}).get("desc")),
        active_count=int(raw.get("vignette_active_status_count") or 0),
        all_time_count=int(raw.get("vignette_all_time_status_count") or 0),
        has_active_vignette=bool(raw.get("vignette_active_status_count")),
        expiry=expiry,
        days_remaining=days_remaining,
        active_vignette=active_item,
        raw=raw,
    )


def _extract_plate_numbers(order: dict[str, Any]) -> list[str]:
    numbers: list[str] = []

    for candidate in (
        order.get("plate_numbers"),
        order.get("plates"),
        order.get("vehicles"),
    ):
        if isinstance(candidate, list):
            for value in candidate:
                if value:
                    numbers.append(str(value))

    for key, value in order.items():
        if "plate" in key.lower() and value:
            if isinstance(value, list):
                numbers.extend(str(item) for item in value if item)
            else:
                numbers.append(str(value))

    deduped: list[str] = []
    seen: set[str] = set()
    for number in numbers:
        normalized = number.strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)

    return deduped


def _order_from_raw(raw: dict[str, Any], order_type: str) -> OrderData:
    return OrderData(
        id=int(raw["id"]),
        order_type=order_type,
        status_name=clean_text((raw.get("status") or {}).get("name")) or "Necunoscută",
        date=clean_text(raw.get("date")),
        emitted_at=parse_unix_timestamp(raw.get("orderEmittedTime")) or parse_unix_timestamp(raw.get("orderSaveTime")),
        total_lei=safe_float(raw.get("orderTotalLei")),
        total_euro=safe_float(raw.get("orderTotalEuro")),
        value_total=safe_float(raw.get("valueTotal")),
        plate_numbers=_extract_plate_numbers(raw),
        invoice=clean_text(raw.get("orderInvoice")),
        raw=raw,
    )


def normalize_payload(payload: dict[str, Any]) -> AccountData:
    """Funcție pentru normalizare payload."""
    raw_vehicles = ((payload.get("vehicles") or {}).get("data") or {}).get("vehicles") or []
    raw_orders = (payload.get("orders") or {}).get("orders") or {}
    raw_profiles = (payload.get("profiles") or {}).get("profiles") or []
    raw_tokens = (payload.get("tokens") or {}).get("tokens") or []

    vehicles = [_vehicle_from_raw(item) for item in raw_vehicles]

    orders: list[OrderData] = []
    orders.extend(_order_from_raw(item, "rovinieta") for item in (raw_orders.get("orders_vignette") or []))
    orders.extend(_order_from_raw(item, "taxa_pod") for item in (raw_orders.get("orders_toll") or []))
    orders.sort(key=lambda item: item.emitted_at or datetime.min.replace(tzinfo=UTC), reverse=True)

    return AccountData(
        account=payload.get("account") or {},
        vehicles=vehicles,
        orders=orders[:10],
        profiles=list(raw_profiles),
        tokens=list(raw_tokens),
        fetched_at=datetime.now(UTC),
    )
