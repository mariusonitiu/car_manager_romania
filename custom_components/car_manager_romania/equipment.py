"""Equipment/safety kit helpers for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from datetime import date as dt_date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_VEHICLE_ID,
    EQUIPMENT_TYPES,
    STORAGE_KEY_EQUIPMENT_ITEMS,
    STORAGE_VERSION_EQUIPMENT_ITEMS,
)


class CarManagerEquipmentItemStore:
    """Store vehicle equipment/safety kit items separately from vehicles."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION_EQUIPMENT_ITEMS, STORAGE_KEY_EQUIPMENT_ITEMS)
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

    async def async_update_item(self, item_id: str, updated_item: dict[str, Any]) -> bool:
        await self.async_load()
        for index, item in enumerate(self._items):
            if str(item.get("item_id", "")) == item_id:
                self._items[index] = deepcopy(updated_item)
                await self._store.async_save({"items": self._items})
                return True
        return False

    async def async_delete_item(self, item_id: str) -> bool:
        await self.async_load()
        original_count = len(self._items)
        self._items = [item for item in self._items if str(item.get("item_id", "")) != item_id]
        if len(self._items) == original_count:
            return False
        await self._store.async_save({"items": self._items})
        return True


def equipment_type_label(equipment_type: str) -> str:
    return EQUIPMENT_TYPES.get(equipment_type, equipment_type.replace("_", " ").title())


def _parse_date(value: Any) -> dt_date | None:
    if not value:
        return None
    try:
        return dt_date.fromisoformat(str(value))
    except ValueError:
        return None


def _equipment_status(expiry_date: str) -> tuple[str, int | None]:
    parsed = _parse_date(expiry_date)
    if parsed is None:
        return "fără expirare", None
    days = (parsed - dt_date.today()).days
    if days < 0:
        return "expirat", days
    if days <= 30:
        return "critic", days
    if days <= 90:
        return "în curând", days
    return "ok", days


def normalize_equipment_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a safe equipment item dictionary."""

    equipment_type = str(raw.get("equipment_type") or "").strip()
    if equipment_type not in EQUIPMENT_TYPES:
        equipment_type = "first_aid_kit"

    cost = float(raw.get("cost", 0) or 0)
    if cost < 0:
        cost = 0.0

    status, days_remaining = _equipment_status(str(raw.get("expiry_date") or "").strip())

    return {
        "item_id": str(raw.get("item_id") or "").strip(),
        CONF_VEHICLE_ID: str(raw.get(CONF_VEHICLE_ID) or "").strip(),
        "equipment_type": equipment_type,
        "equipment_type_label": equipment_type_label(equipment_type),
        "name": str(raw.get("name") or "").strip(),
        "purchase_date": str(raw.get("purchase_date") or "").strip(),
        "expiry_date": str(raw.get("expiry_date") or "").strip(),
        "cost": round(cost, 2),
        "present": bool(raw.get("present", True)),
        "storage_location": str(raw.get("storage_location") or "").strip(),
        "notes": str(raw.get("notes") or "").strip(),
        "status": status,
        "days_remaining": days_remaining,
    }


def equipment_items_for_vehicle(entry: Any, vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, ""))
    store = getattr(entry.runtime_data, "equipment_item_store", None)
    records = getattr(store, "_items", []) if store is not None else []
    result = [normalize_equipment_item(item) for item in records if isinstance(item, dict) and str(item.get(CONF_VEHICLE_ID, "")) == vehicle_id]
    result.sort(key=lambda item: (str(item.get("expiry_date") or "9999-12-31"), str(item.get("equipment_type_label", ""))))
    return result


def current_year_equipment_cost_total(entry: Any, vehicle: dict[str, Any]) -> float:
    year = dt_date.today().year
    total = 0.0
    for item in equipment_items_for_vehicle(entry, vehicle):
        purchase_date = _parse_date(item.get("purchase_date"))
        if purchase_date and purchase_date.year == year:
            total += float(item.get("cost", 0) or 0)
    return round(total, 2)
