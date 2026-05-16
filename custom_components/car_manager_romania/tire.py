"""Modul pentru seturile de anvelope."""

from __future__ import annotations

from copy import deepcopy
from datetime import date as dt_date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_VEHICLE_ID,
    STORAGE_KEY_TIRE_SETS,
    STORAGE_VERSION_TIRE_SETS,
    TIRE_MOUNT_TYPES,
    TIRE_TYPES,
)


class CarManagerTireSetStore:
    """Clasă pentru stocarea seturilor de anvelope."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION_TIRE_SETS, STORAGE_KEY_TIRE_SETS)
        self._sets: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        data = await self._store.async_load()
        if isinstance(data, dict):
            sets = data.get("sets")
            if isinstance(sets, list):
                self._sets = [deepcopy(item) for item in sets if isinstance(item, dict)]
        self._loaded = True

    async def async_get_sets(self) -> list[dict[str, Any]]:
        await self.async_load()
        return deepcopy(self._sets)

    async def async_save_sets(self, sets: list[dict[str, Any]]) -> None:
        await self.async_load()
        self._sets = [deepcopy(item) for item in sets if isinstance(item, dict)]
        await self._store.async_save({"sets": self._sets})

    async def async_add_set(self, tire_set: dict[str, Any]) -> None:
        await self.async_load()
        self._sets.append(deepcopy(tire_set))
        await self._store.async_save({"sets": self._sets})

    async def async_update_set(self, set_id: str, updated_set: dict[str, Any]) -> bool:
        await self.async_load()
        for index, tire_set in enumerate(self._sets):
            if str(tire_set.get("set_id", "")) == set_id:
                self._sets[index] = deepcopy(updated_set)
                await self._store.async_save({"sets": self._sets})
                return True
        return False

    async def async_delete_set(self, set_id: str) -> bool:
        await self.async_load()
        original_count = len(self._sets)
        self._sets = [item for item in self._sets if str(item.get("set_id", "")) != set_id]
        if len(self._sets) == original_count:
            return False
        await self._store.async_save({"sets": self._sets})
        return True


def tire_type_label(tire_type: str) -> str:
    return TIRE_TYPES.get(tire_type, tire_type.replace("_", " ").title())


def tire_mount_type_label(mount_type: str) -> str:
    return TIRE_MOUNT_TYPES.get(mount_type, mount_type.replace("_", " ").title())


def _parse_date(value: Any) -> dt_date | None:
    if not value:
        return None
    try:
        return dt_date.fromisoformat(str(value))
    except ValueError:
        return None


def normalize_tire_set(raw: dict[str, Any]) -> dict[str, Any]:
    """Funcție pentru normalizare anvelopă set."""

    tire_type = str(raw.get("tire_type") or "").strip()
    if tire_type not in TIRE_TYPES:
        tire_type = "summer"

    quantity = int(raw.get("quantity", 4) or 4)
    if quantity <= 0:
        quantity = 4

    wheel_mount_type = str(raw.get("wheel_mount_type") or "").strip()
    if wheel_mount_type not in TIRE_MOUNT_TYPES:
        wheel_mount_type = "tires_only"

    total_km = int(raw.get("total_km", 0) or 0)
    if total_km < 0:
        total_km = 0

    last_mount_km = int(raw.get("last_mount_km", 0) or 0)
    if last_mount_km < 0:
        last_mount_km = 0

    cost = float(raw.get("cost", 0) or 0)
    if cost < 0:
        cost = 0.0

    return {
        "set_id": str(raw.get("set_id") or "").strip(),
        CONF_VEHICLE_ID: str(raw.get(CONF_VEHICLE_ID) or "").strip(),
        "tire_type": tire_type,
        "tire_type_label": tire_type_label(tire_type),
        "wheel_mount_type": wheel_mount_type,
        "wheel_mount_type_label": tire_mount_type_label(wheel_mount_type),
        "brand_model": str(raw.get("brand_model") or "").strip(),
        "size": str(raw.get("size") or "").strip(),
        "dot": str(raw.get("dot") or "").strip(),
        "quantity": quantity,
        "purchase_date": str(raw.get("purchase_date") or "").strip(),
        "last_mount_date": str(raw.get("last_mount_date") or "").strip(),
        "last_mount_km": last_mount_km,
        "total_km": total_km,
        "cost": round(cost, 2),
        "installed": bool(raw.get("installed", False)),
        "storage_location": str(raw.get("storage_location") or "").strip(),
        "pressure_front": str(raw.get("pressure_front") or "").strip(),
        "pressure_rear": str(raw.get("pressure_rear") or "").strip(),
        "notes": str(raw.get("notes") or "").strip(),
    }


def tire_sets_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, ""))
    store = getattr(entry.runtime_data, "tire_set_store", None)
    records = getattr(store, "_sets", []) if store is not None else []
    result = [normalize_tire_set(item) for item in records if isinstance(item, dict) and str(item.get(CONF_VEHICLE_ID, "")) == vehicle_id]
    result.sort(key=lambda item: (not bool(item.get("installed")), str(item.get("tire_type_label", "")), str(item.get("brand_model", ""))))
    return result


def current_year_tire_cost_total(entry: Any, vehicle: dict[str, Any]) -> float:
    year = dt_date.today().year
    total = 0.0
    for item in tire_sets_for_vehicle(entry, vehicle):
        purchase_date = _parse_date(item.get("purchase_date"))
        if purchase_date and purchase_date.year == year:
            total += float(item.get("cost", 0) or 0)
    return round(total, 2)
