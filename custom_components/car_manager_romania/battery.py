"""Battery helpers for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from datetime import date as dt_date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    BATTERY_TYPES,
    CONF_VEHICLE_ID,
    STORAGE_KEY_BATTERIES,
    STORAGE_VERSION_BATTERIES,
)


class CarManagerBatteryStore:
    """Store vehicle batteries separately from vehicles."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION_BATTERIES, STORAGE_KEY_BATTERIES)
        self._items: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        data = await self._store.async_load()
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                self._items = [deepcopy(item) for item in items if isinstance(item, dict)]
        self._loaded = True

    async def async_get_items(self) -> list[dict[str, Any]]:
        await self.async_load()
        return deepcopy(self._items)

    async def async_save_items(self, items: list[dict[str, Any]]) -> None:
        await self.async_load()
        self._items = [deepcopy(item) for item in items if isinstance(item, dict)]
        await self._store.async_save({"items": self._items})

    async def async_add_item(self, item: dict[str, Any]) -> None:
        await self.async_load()
        self._items.append(deepcopy(item))
        await self._store.async_save({"items": self._items})

    async def async_update_item(self, battery_id: str, updated_item: dict[str, Any]) -> bool:
        await self.async_load()
        for index, item in enumerate(self._items):
            if str(item.get("battery_id", "")) == battery_id:
                self._items[index] = deepcopy(updated_item)
                await self._store.async_save({"items": self._items})
                return True
        return False

    async def async_delete_item(self, battery_id: str) -> bool:
        await self.async_load()
        original_count = len(self._items)
        self._items = [item for item in self._items if str(item.get("battery_id", "")) != battery_id]
        if len(self._items) == original_count:
            return False
        await self._store.async_save({"items": self._items})
        return True


def battery_type_label(battery_type: str) -> str:
    return BATTERY_TYPES.get(battery_type, battery_type.replace("_", " ").title())


def _parse_date(value: Any) -> dt_date | None:
    if not value:
        return None
    try:
        return dt_date.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_float(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(round(number, 2), 0.0)


def _safe_int(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def _battery_age_days(install_date: dt_date | None) -> int | None:
    if install_date is None:
        return None
    return max((dt_date.today() - install_date).days, 0)


def _battery_status(install_date: dt_date | None, warranty_until: dt_date | None, installed: bool) -> tuple[str, str, int | None, int | None]:
    """Return machine status, label, warranty days remaining and age days."""

    if not installed:
        return "not_installed", "Nemontată", None, _battery_age_days(install_date)

    today = dt_date.today()
    age_days = _battery_age_days(install_date)
    warranty_days = None
    if warranty_until is not None:
        warranty_days = (warranty_until - today).days
        if warranty_days < 0:
            return "warranty_expired", "Garanție expirată", warranty_days, age_days
        if warranty_days <= 90:
            return "warranty_soon", "Garanție expiră curând", warranty_days, age_days

    if age_days is None:
        return "unknown", "Necunoscut", warranty_days, age_days
    if age_days >= 5 * 365:
        return "very_old", "Foarte veche", warranty_days, age_days
    if age_days >= 4 * 365:
        return "old", "Veche", warranty_days, age_days
    if age_days >= int(3.5 * 365):
        return "attention", "Atenție", warranty_days, age_days
    return "ok", "OK", warranty_days, age_days


def normalize_battery_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a safe battery dictionary."""

    battery_type = str(raw.get("battery_type") or "").strip()
    if battery_type not in BATTERY_TYPES:
        battery_type = "lead_acid"

    install_date = _parse_date(raw.get("install_date"))
    warranty_until = _parse_date(raw.get("warranty_until"))
    installed = bool(raw.get("installed", True))
    status, status_label, warranty_days_remaining, age_days = _battery_status(install_date, warranty_until, installed)

    return {
        "battery_id": str(raw.get("battery_id") or "").strip(),
        CONF_VEHICLE_ID: str(raw.get(CONF_VEHICLE_ID) or "").strip(),
        "installed": installed,
        "brand_model": str(raw.get("brand_model") or "").strip(),
        "battery_type": battery_type,
        "battery_type_label": battery_type_label(battery_type),
        "capacity_ah": _safe_int(raw.get("capacity_ah")),
        "cca": _safe_int(raw.get("cca")),
        "polarity": str(raw.get("polarity") or "").strip(),
        "size": str(raw.get("size") or "").strip(),
        "install_date": str(raw.get("install_date") or "").strip(),
        "install_km": _safe_int(raw.get("install_km")),
        "warranty_until": str(raw.get("warranty_until") or "").strip(),
        "cost": _safe_float(raw.get("cost")),
        "notes": str(raw.get("notes") or "").strip(),
        "status": status,
        "status_label": status_label,
        "warranty_days_remaining": warranty_days_remaining,
        "age_days": age_days,
        "age_years": round(age_days / 365, 1) if age_days is not None else None,
    }


def battery_items_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, ""))
    store = getattr(entry.runtime_data, "battery_store", None)
    records = getattr(store, "_items", []) if store is not None else []
    result = [normalize_battery_item(item) for item in records if isinstance(item, dict) and str(item.get(CONF_VEHICLE_ID, "")) == vehicle_id]
    result.sort(key=lambda item: (not bool(item.get("installed", False)), str(item.get("install_date") or "0000-00-00")), reverse=True)
    return result


def current_battery_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> dict[str, Any] | None:
    items = battery_items_for_vehicle(entry, vehicle)
    for item in items:
        if item.get("installed"):
            return item
    return items[0] if items else None


def current_year_battery_cost_total(entry: Any, vehicle: dict[str, Any]) -> float:
    year = dt_date.today().year
    total = 0.0
    for item in battery_items_for_vehicle(entry, vehicle):
        install_date = _parse_date(item.get("install_date"))
        if install_date and install_date.year == year:
            total += _safe_float(item.get("cost"))
    return round(total, 2)


def battery_issues_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return critical and warning battery issues for one vehicle."""

    critical: list[dict[str, Any]] = []
    warning: list[dict[str, Any]] = []
    battery = current_battery_for_vehicle(entry, vehicle)
    if battery is None:
        warning.append({
            "category": "battery",
            "key": "battery_missing",
            "label": "Baterie auto",
            "status": "neconfigurat",
            "days_remaining": None,
            "km_remaining": None,
            "detail": "bateria nu este introdusă în evidență",
        })
        return critical, warning

    status = str(battery.get("status") or "")
    issue = {
        "category": "battery",
        "key": str(battery.get("battery_id") or "battery"),
        "label": "Baterie auto",
        "status": str(battery.get("status_label") or status),
        "days_remaining": battery.get("warranty_days_remaining"),
        "km_remaining": None,
        "detail": str(battery.get("status_label") or status),
    }
    if status in {"warranty_expired", "very_old"}:
        critical.append(issue)
    elif status in {"warranty_soon", "old", "attention", "unknown", "not_installed"}:
        warning.append(issue)
    return critical, warning
