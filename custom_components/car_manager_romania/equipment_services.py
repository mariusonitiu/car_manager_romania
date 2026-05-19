"""Servicii pentru gestionarea echipamentelor auto de siguranță."""

from __future__ import annotations

from datetime import date as dt_date
from typing import Any, Callable
from uuid import uuid4

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_VEHICLE_ID,
    CONF_VEHICLES,
    DOMAIN,
    EQUIPMENT_TYPES,
    SERVICE_ADD_EQUIPMENT_ITEM,
    SERVICE_DELETE_EQUIPMENT_ITEM,
    SERVICE_UPDATE_EQUIPMENT_ITEM,
)
from .equipment import normalize_equipment_item
from .storage import merge_vehicle_sources


ADD_EQUIPMENT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("equipment_type"): vol.In(list(EQUIPMENT_TYPES.keys())),
        vol.Optional("name", default=""): str,
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("expiry_date", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("present", default=True): bool,
        vol.Optional("ignored", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_EQUIPMENT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("item_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("equipment_type"): vol.In(list(EQUIPMENT_TYPES.keys())),
        vol.Optional("name", default=""): str,
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("expiry_date", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("present", default=True): bool,
        vol.Optional("ignored", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

DELETE_EQUIPMENT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("item_id"): str,
    }
)


def _validate_equipment_dates(call: ServiceCall) -> None:
    """Validează datele calendaristice pentru un echipament auto."""

    for field_name in ("purchase_date", "expiry_date"):
        value = str(call.data.get(field_name, "") or "").strip()
        if value:
            try:
                dt_date.fromisoformat(value)
            except ValueError as err:
                raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err


async def async_register_equipment_services(
    hass: HomeAssistant,
    find_loaded_config_entry: Callable[[HomeAssistant, str | None], Any],
    find_vehicle_by_reference: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    vehicle_internal_id: Callable[[dict[str, Any]], str],
) -> None:
    """Înregistrează serviciile pentru echipamentele auto de siguranță."""

    async def async_add_equipment_item(call: ServiceCall) -> None:
        """Adaugă un echipament auto pentru un autovehicul."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        _validate_equipment_dates(call)
        item = normalize_equipment_item(
            {
                "item_id": f"equipment_{uuid4().hex[:12]}",
                CONF_VEHICLE_ID: vehicle_internal_id(found_vehicle),
                "equipment_type": call.data.get("equipment_type"),
                "name": call.data.get("name", ""),
                "purchase_date": call.data.get("purchase_date", ""),
                "expiry_date": call.data.get("expiry_date", ""),
                "cost": call.data.get("cost", 0),
                "present": call.data.get("present", True),
                "ignored": call.data.get("ignored", False),
                "storage_location": call.data.get("storage_location", ""),
                "notes": call.data.get("notes", ""),
            }
        )
        await entry.runtime_data.equipment_item_store.async_add_item(item)
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_equipment_item(call: ServiceCall) -> None:
        """Actualizează un echipament auto existent."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        item_id = str(call.data.get("item_id", "")).strip()
        if not item_id:
            raise HomeAssistantError("Echipamentul nu are ID valid.")

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        _validate_equipment_dates(call)
        item = normalize_equipment_item(
            {
                "item_id": item_id,
                CONF_VEHICLE_ID: vehicle_internal_id(found_vehicle),
                "equipment_type": call.data.get("equipment_type"),
                "name": call.data.get("name", ""),
                "purchase_date": call.data.get("purchase_date", ""),
                "expiry_date": call.data.get("expiry_date", ""),
                "cost": call.data.get("cost", 0),
                "present": call.data.get("present", True),
                "ignored": call.data.get("ignored", False),
                "storage_location": call.data.get("storage_location", ""),
                "notes": call.data.get("notes", ""),
            }
        )
        if not await entry.runtime_data.equipment_item_store.async_update_item(item_id, item):
            raise HomeAssistantError("Echipamentul nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_equipment_item(call: ServiceCall) -> None:
        """Șterge un echipament auto existent."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        item_id = str(call.data.get("item_id", "")).strip()
        if not item_id:
            raise HomeAssistantError("Echipamentul nu are ID valid.")
        if not await entry.runtime_data.equipment_item_store.async_delete_item(item_id):
            raise HomeAssistantError("Echipamentul nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_EQUIPMENT_ITEM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_EQUIPMENT_ITEM,
            async_add_equipment_item,
            schema=ADD_EQUIPMENT_ITEM_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_EQUIPMENT_ITEM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_EQUIPMENT_ITEM,
            async_update_equipment_item,
            schema=UPDATE_EQUIPMENT_ITEM_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_EQUIPMENT_ITEM):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_EQUIPMENT_ITEM,
            async_delete_equipment_item,
            schema=DELETE_EQUIPMENT_ITEM_SCHEMA,
        )
