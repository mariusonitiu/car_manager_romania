"""Servicii pentru gestionarea seturilor de anvelope."""

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
    SERVICE_ADD_TIRE_SET,
    SERVICE_DELETE_TIRE_SET,
    SERVICE_UPDATE_TIRE_SET,
    TIRE_MOUNT_TYPES,
    TIRE_TYPES,
)
from .storage import merge_vehicle_sources
from .tire import normalize_tire_set


ADD_TIRE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("tire_type"): vol.In(list(TIRE_TYPES.keys())),
        vol.Optional("wheel_mount_type", default="tires_only"): vol.In(list(TIRE_MOUNT_TYPES.keys())),
        vol.Optional("brand_model", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("dot", default=""): str,
        vol.Optional("quantity", default=4): vol.Coerce(int),
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("last_mount_date", default=""): str,
        vol.Optional("last_mount_km", default=0): vol.Coerce(int),
        vol.Optional("total_km", default=0): vol.Coerce(int),
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("installed", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("pressure_front", default=""): str,
        vol.Optional("pressure_rear", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_TIRE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("set_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("tire_type"): vol.In(list(TIRE_TYPES.keys())),
        vol.Optional("wheel_mount_type", default="tires_only"): vol.In(list(TIRE_MOUNT_TYPES.keys())),
        vol.Optional("brand_model", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("dot", default=""): str,
        vol.Optional("quantity", default=4): vol.Coerce(int),
        vol.Optional("purchase_date", default=""): str,
        vol.Optional("last_mount_date", default=""): str,
        vol.Optional("last_mount_km", default=0): vol.Coerce(int),
        vol.Optional("total_km", default=0): vol.Coerce(int),
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("installed", default=False): bool,
        vol.Optional("storage_location", default=""): str,
        vol.Optional("pressure_front", default=""): str,
        vol.Optional("pressure_rear", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

DELETE_TIRE_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("set_id"): str,
    }
)


def _validate_tire_dates(call: ServiceCall) -> None:
    """Validează datele calendaristice pentru un set de anvelope."""

    for field_name in ("purchase_date", "last_mount_date"):
        value = str(call.data.get(field_name, "") or "").strip()
        if value:
            try:
                dt_date.fromisoformat(value)
            except ValueError as err:
                raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err


async def async_register_tire_services(
    hass: HomeAssistant,
    find_loaded_config_entry: Callable[[HomeAssistant, str | None], Any],
    find_vehicle_by_reference: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    vehicle_internal_id: Callable[[dict[str, Any]], str],
) -> None:
    """Înregistrează serviciile pentru seturile de anvelope."""

    async def async_add_tire_set(call: ServiceCall) -> None:
        """Adaugă un set de anvelope pentru un autovehicul."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_ref:
            raise HomeAssistantError("Autovehiculul este obligatoriu.")

        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        _validate_tire_dates(call)
        tire_set = normalize_tire_set(
            {
                "set_id": f"tire_{uuid4().hex[:12]}",
                CONF_VEHICLE_ID: vehicle_internal_id(found_vehicle),
                "tire_type": call.data.get("tire_type"),
                "wheel_mount_type": call.data.get("wheel_mount_type", "tires_only"),
                "brand_model": call.data.get("brand_model", ""),
                "size": call.data.get("size", ""),
                "dot": call.data.get("dot", ""),
                "quantity": call.data.get("quantity", 4),
                "purchase_date": call.data.get("purchase_date", ""),
                "last_mount_date": call.data.get("last_mount_date", ""),
                "last_mount_km": call.data.get("last_mount_km", 0),
                "total_km": call.data.get("total_km", 0),
                "cost": call.data.get("cost", 0),
                "installed": call.data.get("installed", False),
                "storage_location": call.data.get("storage_location", ""),
                "pressure_front": call.data.get("pressure_front", ""),
                "pressure_rear": call.data.get("pressure_rear", ""),
                "notes": call.data.get("notes", ""),
            }
        )
        await entry.runtime_data.tire_set_store.async_add_set(tire_set)
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_tire_set(call: ServiceCall) -> None:
        """Actualizează un set de anvelope existent."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        set_id = str(call.data.get("set_id", "")).strip()
        if not set_id:
            raise HomeAssistantError("Setul de anvelope nu are ID valid.")

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        _validate_tire_dates(call)
        updated_set = normalize_tire_set(
            {
                "set_id": set_id,
                CONF_VEHICLE_ID: vehicle_internal_id(found_vehicle),
                "tire_type": call.data.get("tire_type"),
                "wheel_mount_type": call.data.get("wheel_mount_type", "tires_only"),
                "brand_model": call.data.get("brand_model", ""),
                "size": call.data.get("size", ""),
                "dot": call.data.get("dot", ""),
                "quantity": call.data.get("quantity", 4),
                "purchase_date": call.data.get("purchase_date", ""),
                "last_mount_date": call.data.get("last_mount_date", ""),
                "last_mount_km": call.data.get("last_mount_km", 0),
                "total_km": call.data.get("total_km", 0),
                "cost": call.data.get("cost", 0),
                "installed": call.data.get("installed", False),
                "storage_location": call.data.get("storage_location", ""),
                "pressure_front": call.data.get("pressure_front", ""),
                "pressure_rear": call.data.get("pressure_rear", ""),
                "notes": call.data.get("notes", ""),
            }
        )
        if not await entry.runtime_data.tire_set_store.async_update_set(set_id, updated_set):
            raise HomeAssistantError("Setul de anvelope nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_tire_set(call: ServiceCall) -> None:
        """Șterge un set de anvelope existent."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        set_id = str(call.data.get("set_id", "")).strip()
        if not set_id:
            raise HomeAssistantError("Setul de anvelope nu are ID valid.")
        if not await entry.runtime_data.tire_set_store.async_delete_set(set_id):
            raise HomeAssistantError("Setul de anvelope nu a fost găsit.")
        await hass.config_entries.async_reload(entry.entry_id)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_TIRE_SET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_TIRE_SET,
            async_add_tire_set,
            schema=ADD_TIRE_SET_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_TIRE_SET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_TIRE_SET,
            async_update_tire_set,
            schema=UPDATE_TIRE_SET_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_TIRE_SET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_TIRE_SET,
            async_delete_tire_set,
            schema=DELETE_TIRE_SET_SCHEMA,
        )
