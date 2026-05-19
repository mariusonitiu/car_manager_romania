"""Storage helpers for Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    STORAGE_KEY_NOTIFICATIONS,
    STORAGE_KEY_SERVICE_HISTORY,
    STORAGE_KEY_FUEL_RECEIPTS,
    STORAGE_KEY_VEHICLES,
    STORAGE_VERSION_NOTIFICATIONS,
    STORAGE_VERSION_SERVICE_HISTORY,
    STORAGE_VERSION_FUEL_RECEIPTS,
    STORAGE_VERSION_VEHICLES,
)


class CarManagerNotificationStore:
    """Store notified maintenance statuses."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize notification store."""

        self._store: Store = Store(
            hass,
            STORAGE_VERSION_NOTIFICATIONS,
            STORAGE_KEY_NOTIFICATIONS,
        )
        self._data: dict[str, Any] = {"notified": {}}
        self._loaded = False

    async def async_load(self) -> None:
        """Load stored data."""

        if self._loaded:
            return

        data = await self._store.async_load()
        if isinstance(data, dict):
            notified = data.get("notified")
            if isinstance(notified, dict):
                self._data = {"notified": notified}

        self._loaded = True

    async def async_get_notified_status(self, key: str) -> str | None:
        """Return notified status for key."""

        await self.async_load()
        value = self._data["notified"].get(key)
        return str(value) if value else None

    async def async_set_notified_status(self, key: str, status: str) -> None:
        """Persist notified status."""

        await self.async_load()
        self._data["notified"][key] = status
        await self._store.async_save(self._data)

    async def async_clear_notified_status(self, key: str) -> None:
        """Clear notified status."""

        await self.async_load()
        if key not in self._data["notified"]:
            return

        self._data["notified"].pop(key, None)
        await self._store.async_save(self._data)


class CarManagerServiceHistoryStore:
    """Store service/intervention history records."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize service history store."""

        self._store: Store = Store(
            hass,
            STORAGE_VERSION_SERVICE_HISTORY,
            STORAGE_KEY_SERVICE_HISTORY,
        )
        self._records: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        """Load service history records."""

        if self._loaded:
            return

        data = await self._store.async_load()
        if isinstance(data, dict):
            records = data.get("records")
            if isinstance(records, list):
                self._records = [
                    deepcopy(record)
                    for record in records
                    if isinstance(record, dict)
                ]

        self._loaded = True

    async def async_get_records(self) -> list[dict[str, Any]]:
        """Return all stored service history records."""

        await self.async_load()
        return deepcopy(self._records)

    async def async_save_records(self, records: list[dict[str, Any]]) -> None:
        """Persist service history records."""

        await self.async_load()
        self._records = [deepcopy(record) for record in records if isinstance(record, dict)]
        await self._store.async_save({"records": self._records})

    async def async_add_record(self, record: dict[str, Any]) -> None:
        """Append and persist a new service history record."""

        await self.async_load()
        self._records.append(deepcopy(record))
        await self._store.async_save({"records": self._records})

    async def async_get_record(self, record_id: str) -> dict[str, Any] | None:
        """Return one service history record by ID."""

        await self.async_load()
        for record in self._records:
            if str(record.get("record_id", "")) == record_id:
                return deepcopy(record)
        return None

    async def async_update_record(self, record_id: str, changes: dict[str, Any]) -> None:
        """Update one service history record and persist history."""

        await self.async_load()
        for index, record in enumerate(self._records):
            if str(record.get("record_id", "")) == record_id:
                updated_record = deepcopy(record)
                updated_record.update(deepcopy(changes))
                self._records[index] = updated_record
                await self._store.async_save({"records": self._records})
                return

    async def async_delete_record(self, record_id: str) -> bool:
        """Delete one service history record and persist history.

        This only removes the history row. It does not change vehicle maintenance
        values. Use restore_service_record before deletion when the maintenance
        update must be reverted.
        """

        await self.async_load()
        original_count = len(self._records)
        self._records = [
            record
            for record in self._records
            if str(record.get("record_id", "")) != record_id
        ]
        if len(self._records) == original_count:
            return False

        await self._store.async_save({"records": self._records})
        return True


class CarManagerFuelReceiptStore:
    """Store fuel receipts separately from service history."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize fuel receipt store."""

        self._store: Store = Store(
            hass,
            STORAGE_VERSION_FUEL_RECEIPTS,
            STORAGE_KEY_FUEL_RECEIPTS,
        )
        self._receipts: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        """Load fuel receipts."""

        if self._loaded:
            return

        data = await self._store.async_load()
        if isinstance(data, dict):
            receipts = data.get("receipts")
            if isinstance(receipts, list):
                self._receipts = [
                    deepcopy(receipt)
                    for receipt in receipts
                    if isinstance(receipt, dict)
                ]

        self._loaded = True

    async def async_get_receipts(self) -> list[dict[str, Any]]:
        """Return all fuel receipts."""

        await self.async_load()
        return deepcopy(self._receipts)

    async def async_save_receipts(self, receipts: list[dict[str, Any]]) -> None:
        """Persist fuel receipts."""

        await self.async_load()
        self._receipts = [deepcopy(receipt) for receipt in receipts if isinstance(receipt, dict)]
        await self._store.async_save({"receipts": self._receipts})

    async def async_add_receipt(self, receipt: dict[str, Any]) -> None:
        """Append and persist a fuel receipt."""

        await self.async_load()
        self._receipts.append(deepcopy(receipt))
        await self._store.async_save({"receipts": self._receipts})

    async def async_update_receipt(self, receipt_id: str, updated_receipt: dict[str, Any]) -> bool:
        """Replace one fuel receipt by ID and persist the change."""

        await self.async_load()
        for index, receipt in enumerate(self._receipts):
            if str(receipt.get("receipt_id", "")) == receipt_id:
                self._receipts[index] = deepcopy(updated_receipt)
                await self._store.async_save({"receipts": self._receipts})
                return True
        return False

    async def async_delete_receipt(self, receipt_id: str) -> bool:
        """Delete a fuel receipt by ID."""

        await self.async_load()
        original_count = len(self._receipts)
        self._receipts = [
            receipt
            for receipt in self._receipts
            if str(receipt.get("receipt_id", "")) != receipt_id
        ]
        if len(self._receipts) == original_count:
            return False

        await self._store.async_save({"receipts": self._receipts})
        return True


class CarManagerVehicleStore:
    """Store editable vehicle data outside the config entry options."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize vehicle store."""

        self._store: Store = Store(
            hass,
            STORAGE_VERSION_VEHICLES,
            STORAGE_KEY_VEHICLES,
        )
        self._vehicles: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        """Load vehicles from Home Assistant storage."""

        if self._loaded:
            return

        data = await self._store.async_load()
        if isinstance(data, dict):
            vehicles = data.get("vehicles")
            if isinstance(vehicles, list):
                self._vehicles = [deepcopy(vehicle) for vehicle in vehicles if isinstance(vehicle, dict)]

        self._loaded = True

    async def async_get_vehicles(self) -> list[dict[str, Any]]:
        """Return stored vehicles."""

        await self.async_load()
        return deepcopy(self._vehicles)

    async def async_save_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Persist vehicles to Home Assistant storage."""

        await self.async_load()
        self._vehicles = [deepcopy(vehicle) for vehicle in vehicles if isinstance(vehicle, dict)]
        await self._store.async_save({"vehicles": self._vehicles})


def merge_vehicle_sources(
    option_vehicles: list[dict[str, Any]],
    stored_vehicles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge config-entry vehicles with stored editable vehicle data.

    Vehicles from the config entry provide the base list, so newly added vehicles are kept.
    Stored vehicles override editable values for matching vehicle_id, so data entered through
    number/date/text entities survives restarts even when config entry options are reloaded.
    """

    merged: list[dict[str, Any]] = []
    stored_by_id = {
        vehicle.get("vehicle_id"): vehicle
        for vehicle in stored_vehicles
        if isinstance(vehicle, dict) and vehicle.get("vehicle_id")
    }
    used_ids: set[str] = set()

    for vehicle in option_vehicles:
        if not isinstance(vehicle, dict):
            continue

        vehicle_id = vehicle.get("vehicle_id")
        result = deepcopy(vehicle)
        if vehicle_id in stored_by_id:
            result.update(deepcopy(stored_by_id[vehicle_id]))
            used_ids.add(vehicle_id)
        merged.append(result)

    for vehicle in stored_vehicles:
        vehicle_id = vehicle.get("vehicle_id") if isinstance(vehicle, dict) else None
        if vehicle_id and vehicle_id not in used_ids and not any(
            existing.get("vehicle_id") == vehicle_id for existing in merged
        ):
            merged.append(deepcopy(vehicle))

    return merged
