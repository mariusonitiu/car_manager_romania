"""Servicii pentru gestionarea bonurilor de combustibil."""

from __future__ import annotations

from datetime import date as dt_date, datetime
from typing import Any, Callable
from uuid import uuid4

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import dispatcher_send

from .const import (
    CONF_KM,
    CONF_VEHICLE_ID,
    CONF_VEHICLES,
    DOMAIN,
    SERVICE_ADD_FUEL_RECEIPT,
    SERVICE_DELETE_FUEL_RECEIPT,
    SERVICE_UPDATE_FUEL_RECEIPT,
    SIGNAL_VEHICLES_UPDATED,
)
from .fuel import allowed_fuel_types, enrich_fuel_receipt, is_liquid_fuel
from .maintenance import normalize_vehicles
from .storage import merge_vehicle_sources


ADD_FUEL_RECEIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("date"): str,
        vol.Required(CONF_KM): vol.Coerce(int),
        vol.Required("fuel_type"): str,
        vol.Required("quantity"): vol.Coerce(float),
        vol.Required("total_cost"): vol.Coerce(float),
        vol.Optional("full_tank", default=True): bool,
        vol.Optional("station", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

UPDATE_FUEL_RECEIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("receipt_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("date"): str,
        vol.Required(CONF_KM): vol.Coerce(int),
        vol.Required("fuel_type"): str,
        vol.Required("quantity"): vol.Coerce(float),
        vol.Required("total_cost"): vol.Coerce(float),
        vol.Optional("full_tank", default=True): bool,
        vol.Optional("station", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)

DELETE_FUEL_RECEIPT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("receipt_id"): str,
    }
)


async def async_register_fuel_services(
    hass: HomeAssistant,
    find_loaded_config_entry: Callable[[HomeAssistant, str | None], Any],
    find_vehicle_by_reference: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    vehicle_internal_id: Callable[[dict[str, Any]], str],
    active_vehicles: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    """Înregistrează serviciile pentru bonurile de combustibil."""

    async def async_add_fuel_receipt(call: ServiceCall) -> None:
        """Adaugă un bon de combustibil pentru un autovehicul."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        fuel_store = entry.runtime_data.fuel_receipt_store

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_ref:
            raise HomeAssistantError("Autovehiculul este obligatoriu.")

        receipt_date = str(call.data.get("date") or dt_date.today().isoformat()).strip()
        try:
            dt_date.fromisoformat(receipt_date)
        except ValueError as err:
            raise HomeAssistantError("Data alimentării trebuie să fie în format YYYY-MM-DD.") from err

        km_value = int(call.data.get(CONF_KM, 0) or 0)
        if km_value <= 0:
            raise HomeAssistantError("Kilometrajul din bord este obligatoriu și trebuie să fie mai mare decât 0.")

        fuel_type = str(call.data.get("fuel_type", "")).strip()
        quantity = float(call.data.get("quantity", 0) or 0)
        total_cost = float(call.data.get("total_cost", 0) or 0)
        if quantity <= 0:
            raise HomeAssistantError("Numărul de litri/kWh trebuie să fie mai mare decât 0.")
        if total_cost <= 0:
            raise HomeAssistantError("Valoarea bonului trebuie să fie mai mare decât 0.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )

        allowed_types = allowed_fuel_types(found_vehicle)
        if fuel_type not in allowed_types:
            raise HomeAssistantError("Tipul de combustibil nu este permis pentru motorizarea configurată a autovehiculului.")

        vehicle_id = vehicle_internal_id(found_vehicle)
        full_tank = bool(call.data.get("full_tank", True)) if is_liquid_fuel(fuel_type) else False
        receipt = enrich_fuel_receipt(
            {
                "receipt_id": f"fuel_{uuid4().hex[:12]}",
                CONF_VEHICLE_ID: vehicle_id,
                "date": receipt_date,
                CONF_KM: km_value,
                "fuel_type": fuel_type,
                "quantity": round(quantity, 3),
                "total_cost": round(total_cost, 2),
                "full_tank": full_tank,
                "station": str(call.data.get("station", "")).strip(),
                "notes": str(call.data.get("notes", "")).strip(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

        await fuel_store.async_add_receipt(receipt)

        # Actualizăm kilometrajul mașinii doar dacă bonul are o valoare mai mare decât cea salvată.
        changed_vehicle = False
        for vehicle in vehicles:
            if vehicle_internal_id(vehicle) == vehicle_id and int(vehicle.get(CONF_KM, 0) or 0) < km_value:
                vehicle[CONF_KM] = km_value
                changed_vehicle = True
                break

        if changed_vehicle:
            normalized_vehicles, _ = normalize_vehicles(vehicles)
            active_vehicle_list = active_vehicles(normalized_vehicles)
            await vehicle_store.async_save_vehicles(normalized_vehicles)
            entry.runtime_data.vehicles = active_vehicle_list
            entry.runtime_data.all_vehicles = normalized_vehicles
            dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicle_list)

        await hass.config_entries.async_reload(entry.entry_id)

    async def async_update_fuel_receipt(call: ServiceCall) -> None:
        """Actualizează un bon de combustibil existent."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        fuel_store = entry.runtime_data.fuel_receipt_store

        receipt_id = str(call.data["receipt_id"]).strip()
        if not receipt_id:
            raise HomeAssistantError("ID-ul bonului este obligatoriu.")

        existing_receipts = await fuel_store.async_get_receipts()
        existing_receipt = next((receipt for receipt in existing_receipts if str(receipt.get("receipt_id", "")) == receipt_id), None)
        if existing_receipt is None:
            raise HomeAssistantError("Bonul de combustibil nu a fost găsit.")

        vehicle_ref = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_ref:
            raise HomeAssistantError("Autovehiculul este obligatoriu.")

        receipt_date = str(call.data.get("date") or dt_date.today().isoformat()).strip()
        try:
            dt_date.fromisoformat(receipt_date)
        except ValueError as err:
            raise HomeAssistantError("Data alimentării trebuie să fie în format YYYY-MM-DD.") from err

        km_value = int(call.data.get(CONF_KM, 0) or 0)
        if km_value <= 0:
            raise HomeAssistantError("Kilometrajul din bord este obligatoriu și trebuie să fie mai mare decât 0.")

        fuel_type = str(call.data.get("fuel_type", "")).strip()
        quantity = float(call.data.get("quantity", 0) or 0)
        total_cost = float(call.data.get("total_cost", 0) or 0)
        if quantity <= 0:
            raise HomeAssistantError("Numărul de litri/kWh trebuie să fie mai mare decât 0.")
        if total_cost <= 0:
            raise HomeAssistantError("Valoarea bonului trebuie să fie mai mare decât 0.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_ref)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )

        allowed_types = allowed_fuel_types(found_vehicle)
        if fuel_type not in allowed_types:
            raise HomeAssistantError("Tipul de combustibil nu este permis pentru motorizarea configurată a autovehiculului.")

        vehicle_id = vehicle_internal_id(found_vehicle)
        full_tank = bool(call.data.get("full_tank", True)) if is_liquid_fuel(fuel_type) else False

        updated_receipt = enrich_fuel_receipt(
            {
                "receipt_id": receipt_id,
                CONF_VEHICLE_ID: vehicle_id,
                "date": receipt_date,
                CONF_KM: km_value,
                "fuel_type": fuel_type,
                "quantity": round(quantity, 3),
                "total_cost": round(total_cost, 2),
                "full_tank": full_tank,
                "station": str(call.data.get("station", "")).strip(),
                "notes": str(call.data.get("notes", "")).strip(),
                "created_at": str(existing_receipt.get("created_at") or datetime.now().isoformat(timespec="seconds")),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

        updated = await fuel_store.async_update_receipt(receipt_id, updated_receipt)
        if not updated:
            raise HomeAssistantError("Bonul de combustibil nu a fost găsit.")

        changed_vehicle = False
        for vehicle in vehicles:
            if vehicle_internal_id(vehicle) == vehicle_id and int(vehicle.get(CONF_KM, 0) or 0) < km_value:
                vehicle[CONF_KM] = km_value
                changed_vehicle = True
                break

        if changed_vehicle:
            normalized_vehicles, _ = normalize_vehicles(vehicles)
            active_vehicle_list = active_vehicles(normalized_vehicles)
            await vehicle_store.async_save_vehicles(normalized_vehicles)
            entry.runtime_data.vehicles = active_vehicle_list
            entry.runtime_data.all_vehicles = normalized_vehicles
            dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicle_list)

        await hass.config_entries.async_reload(entry.entry_id)

    async def async_delete_fuel_receipt(call: ServiceCall) -> None:
        """Șterge un bon de combustibil existent."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        receipt_id = str(call.data["receipt_id"]).strip()
        if not receipt_id:
            raise HomeAssistantError("ID-ul bonului este obligatoriu.")

        deleted = await entry.runtime_data.fuel_receipt_store.async_delete_receipt(receipt_id)
        if not deleted:
            raise HomeAssistantError("Bonul de combustibil nu a fost găsit.")

        await hass.config_entries.async_reload(entry.entry_id)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_FUEL_RECEIPT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_FUEL_RECEIPT,
            async_add_fuel_receipt,
            schema=ADD_FUEL_RECEIPT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_FUEL_RECEIPT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_FUEL_RECEIPT,
            async_update_fuel_receipt,
            schema=UPDATE_FUEL_RECEIPT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_FUEL_RECEIPT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_FUEL_RECEIPT,
            async_delete_fuel_receipt,
            schema=DELETE_FUEL_RECEIPT_SCHEMA,
        )
