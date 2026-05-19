"""Servicii pentru gestionarea bateriilor auto."""

from __future__ import annotations

from datetime import date as dt_date
from typing import Any, Callable
from uuid import uuid4

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .battery import normalize_battery_item
from .const import (
    BATTERY_TYPES,
    CONF_VEHICLE_ID,
    CONF_VEHICLES,
    DOMAIN,
    SERVICE_ADD_BATTERY,
    SERVICE_DELETE_BATTERY,
    SERVICE_UPDATE_BATTERY,
)
from .storage import merge_vehicle_sources


ADD_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("installed", default=True): bool,
        vol.Optional("brand_model", default=""): str,
        vol.Optional("battery_type", default="lead_acid"): vol.In(list(BATTERY_TYPES.keys())),
        vol.Optional("capacity_ah", default=0): vol.Coerce(int),
        vol.Optional("cca", default=0): vol.Coerce(int),
        vol.Optional("polarity", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("install_date", default=""): str,
        vol.Optional("install_km", default=0): vol.Coerce(int),
        vol.Optional("warranty_until", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("battery_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("installed", default=True): bool,
        vol.Optional("brand_model", default=""): str,
        vol.Optional("battery_type", default="lead_acid"): vol.In(list(BATTERY_TYPES.keys())),
        vol.Optional("capacity_ah", default=0): vol.Coerce(int),
        vol.Optional("cca", default=0): vol.Coerce(int),
        vol.Optional("polarity", default=""): str,
        vol.Optional("size", default=""): str,
        vol.Optional("install_date", default=""): str,
        vol.Optional("install_km", default=0): vol.Coerce(int),
        vol.Optional("warranty_until", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("notes", default=""): str,
    }
)

DELETE_BATTERY_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("battery_id"): str,
    }
)


def _validate_battery_dates(call: ServiceCall) -> None:
    """Validează datele calendaristice pentru o baterie auto."""

    for field_name in ("install_date", "warranty_until"):
        value = str(call.data.get(field_name, "") or "").strip()
        if value:
            try:
                dt_date.fromisoformat(value)
            except ValueError as err:
                raise HomeAssistantError(f"Câmpul {field_name} trebuie să fie în format YYYY-MM-DD.") from err


async def async_register_battery_services(
    hass: HomeAssistant,
    find_loaded_config_entry: Callable[[HomeAssistant, str | None], Any],
    find_vehicle_by_reference: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    vehicle_internal_id: Callable[[dict[str, Any]], str],
) -> None:
    """Înregistrează serviciile pentru bateriile auto."""

    async def async_add_battery(call: ServiceCall) -> None:
        """Adaugă o baterie pentru un autovehicul."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        _validate_battery_dates(call)
        item = normalize_battery_item(
            {
                "battery_id": f"battery_{uuid4().hex[:12]}",
                CONF_VEHICLE_ID: vehicle_internal_id(found_vehicle),
                "installed": call.data.get("installed", True),
                "brand_model": call.data.get("brand_model", ""),
                "battery_type": call.data.get("battery_type", "lead_acid"),
                "capacity_ah": call.data.get("capacity_ah", 0),
                "cca": call.data.get("cca", 0),
                "polarity": call.data.get("polarity", ""),
                "size": call.data.get("size", ""),
                "install_date": call.data.get("install_date", ""),
                "install_km": call.data.get("install_km", 0),
                "warranty_until": call.data.get("warranty_until", ""),
                "cost": call.data.get("cost", 0),
                "notes": call.data.get("notes", ""),
            }
        )
        await entry.runtime_data.battery_store.async_add_item(item)
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_battery(call: ServiceCall) -> None:
        """Actualizează o baterie existentă."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        battery_id = str(call.data.get("battery_id", "")).strip()
        if not battery_id:
            raise HomeAssistantError("Bateria nu are ID valid.")

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        stored_vehicles = await entry.runtime_data.vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(CONF_VEHICLES, entry.data.get(CONF_VEHICLES, []))
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError("Autovehiculul selectat nu a fost găsit în Car Manager România.")

        _validate_battery_dates(call)
        item = normalize_battery_item(
            {
                "battery_id": battery_id,
                CONF_VEHICLE_ID: vehicle_internal_id(found_vehicle),
                "installed": call.data.get("installed", True),
                "brand_model": call.data.get("brand_model", ""),
                "battery_type": call.data.get("battery_type", "lead_acid"),
                "capacity_ah": call.data.get("capacity_ah", 0),
                "cca": call.data.get("cca", 0),
                "polarity": call.data.get("polarity", ""),
                "size": call.data.get("size", ""),
                "install_date": call.data.get("install_date", ""),
                "install_km": call.data.get("install_km", 0),
                "warranty_until": call.data.get("warranty_until", ""),
                "cost": call.data.get("cost", 0),
                "notes": call.data.get("notes", ""),
            }
        )
        if not await entry.runtime_data.battery_store.async_update_item(battery_id, item):
            raise HomeAssistantError("Bateria nu a fost găsită.")
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_battery(call: ServiceCall) -> None:
        """Șterge o baterie existentă."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        battery_id = str(call.data.get("battery_id", "")).strip()
        if not battery_id:
            raise HomeAssistantError("Bateria nu are ID valid.")
        if not await entry.runtime_data.battery_store.async_delete_item(battery_id):
            raise HomeAssistantError("Bateria nu a fost găsită.")
        await hass.config_entries.async_reload(entry.entry_id)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_BATTERY,
            async_add_battery,
            schema=ADD_BATTERY_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_BATTERY,
            async_update_battery,
            schema=UPDATE_BATTERY_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_BATTERY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_BATTERY,
            async_delete_battery,
            schema=DELETE_BATTERY_SCHEMA,
        )
