"""Servicii pentru gestionarea istoricului de intervenții."""

from __future__ import annotations

from datetime import date as dt_date, datetime
import logging
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
    LEGAL_COST_TYPES,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_LAST_KM,
    MAINTENANCE_TYPES,
    SERVICE_ADD_SERVICE_RECORD,
    SERVICE_DELETE_SERVICE_RECORD,
    SERVICE_RESTORE_LAST_SERVICE_RECORD,
    SERVICE_RESTORE_SERVICE_RECORD,
    SERVICE_UPDATE_SERVICE_RECORD,
    SIGNAL_VEHICLES_UPDATED,
)
from .maintenance import get_maintenance_value, normalize_vehicles, set_maintenance_value
from .storage import merge_vehicle_sources

_LOGGER = logging.getLogger(__name__)


ADD_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Required("record_type"): vol.In(list(MAINTENANCE_TYPES.keys()) + list(LEGAL_COST_TYPES.keys()) + ["custom"]),
        vol.Optional("date"): str,
        vol.Optional(CONF_KM): vol.Coerce(int),
        vol.Optional("title", default=""): str,
        vol.Optional("service_name", default=""): str,
        vol.Optional("cost", default=0): vol.Coerce(float),
        vol.Optional("invoice_number", default=""): str,
        vol.Optional("notes", default=""): str,
        vol.Optional("update_maintenance", default=True): bool,
    }
)

RESTORE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("record_id"): str,
    }
)

DELETE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("record_id"): str,
    }
)

UPDATE_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("record_id"): str,
        vol.Optional("title"): str,
        vol.Optional("service_name"): str,
        vol.Optional("cost"): vol.Coerce(float),
        vol.Optional("invoice_number"): str,
        vol.Optional("notes"): str,
    }
)

RESTORE_LAST_SERVICE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required(CONF_VEHICLE_ID): str,
        vol.Optional("record_type"): vol.In(list(MAINTENANCE_TYPES.keys())),
    }
)


def _find_vehicle_by_id(vehicles: list[dict[str, Any]], vehicle_id: str) -> dict[str, Any] | None:
    """Funcție internă pentru căutare vehicul by ID."""

    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        if str(vehicle.get(CONF_VEHICLE_ID, "")) == vehicle_id:
            return vehicle
    return None



def _maintenance_snapshot(vehicle: dict[str, Any], maintenance_type: str) -> dict[str, Any]:
    """Funcție internă pentru mentenanță instantaneu."""

    return {
        "maintenance_type": maintenance_type,
        MAINTENANCE_LAST_DATE: get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_DATE),
        MAINTENANCE_LAST_KM: get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_KM),
        CONF_KM: vehicle.get(CONF_KM),
    }




def _is_service_record_newer_than_current(
    vehicle: dict[str, Any],
    maintenance_type: str,
    record_date: str,
    km_value: int,
) -> bool:
    """Funcție internă pentru verificarea unei intervenții mai noi decât valorile curente."""

    current_date_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_DATE)
    current_km_raw = get_maintenance_value(vehicle, maintenance_type, MAINTENANCE_LAST_KM)

    try:
        new_date = dt_date.fromisoformat(str(record_date))
    except (TypeError, ValueError):
        return False

    current_date = None
    if current_date_raw:
        try:
            current_date = dt_date.fromisoformat(str(current_date_raw))
        except (TypeError, ValueError):
            current_date = None

    if current_date is None:
        return True

    if new_date > current_date:
        return True

    if new_date < current_date:
        return False

    if km_value <= 0:
        return False

    try:
        current_km = int(current_km_raw or 0)
    except (TypeError, ValueError):
        current_km = 0

    return km_value > current_km


def _apply_maintenance_snapshot(vehicle: dict[str, Any], snapshot: dict[str, Any]) -> None:
    """Funcție internă pentru apply mentenanță instantaneu."""

    maintenance_type = str(snapshot.get("maintenance_type", "")).strip()
    if maintenance_type not in MAINTENANCE_TYPES:
        raise HomeAssistantError("Snapshotul nu conține un tip de mentenanță valid.")

    set_maintenance_value(
        vehicle,
        maintenance_type,
        MAINTENANCE_LAST_DATE,
        snapshot.get(MAINTENANCE_LAST_DATE),
    )
    set_maintenance_value(
        vehicle,
        maintenance_type,
        MAINTENANCE_LAST_KM,
        snapshot.get(MAINTENANCE_LAST_KM),
    )

    if CONF_KM in snapshot and snapshot.get(CONF_KM) is not None:
        vehicle[CONF_KM] = snapshot.get(CONF_KM)


async def _async_restore_service_record_snapshot(
    hass: HomeAssistant,
    entry: Any,
    record: dict[str, Any],
    active_vehicles: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    """Funcție internă pentru restaurarea instantaneului unei intervenții."""

    vehicle_store = entry.runtime_data.vehicle_store
    history_store = entry.runtime_data.service_history_store

    record_id = str(record.get("record_id", "")).strip()
    if not record_id:
        raise HomeAssistantError("Intervenția selectată nu are record_id valid.")

    if bool(record.get("restored")):
        raise HomeAssistantError("Această intervenție a fost deja restaurată.")

    previous_maintenance = record.get("previous_maintenance")
    if not isinstance(previous_maintenance, dict):
        raise HomeAssistantError(
            "Intervenția selectată nu are snapshot anterior. A fost probabil creată înainte de versiunea cu restore."
        )

    vehicle_id = str(record.get(CONF_VEHICLE_ID, "")).strip()
    if not vehicle_id:
        raise HomeAssistantError("Intervenția selectată nu are autovehicul asociat.")

    stored_vehicles = await vehicle_store.async_get_vehicles()
    option_vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
    found_vehicle = _find_vehicle_by_id(vehicles, vehicle_id)
    if found_vehicle is None:
        raise HomeAssistantError("Autovehiculul intervenției nu a fost găsit în Car Manager România.")

    _apply_maintenance_snapshot(found_vehicle, previous_maintenance)

    normalized_vehicles, _ = normalize_vehicles(vehicles)
    active_vehicle_list = active_vehicles(normalized_vehicles)
    await vehicle_store.async_save_vehicles(normalized_vehicles)
    await history_store.async_update_record(
        record_id,
        {
            "restored": True,
            "restored_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    entry.runtime_data.vehicles = active_vehicle_list
    entry.runtime_data.all_vehicles = normalized_vehicles
    dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicle_list)

    from .notify import async_check_maintenance_notifications

    hass.async_create_task(async_check_maintenance_notifications(hass, entry))
    await hass.config_entries.async_reload(entry.entry_id)



async def async_register_history_services(
    hass: HomeAssistant,
    find_loaded_config_entry: Callable[[HomeAssistant, str | None], Any],
    find_vehicle_by_reference: Callable[[list[dict[str, Any]], str], dict[str, Any] | None],
    vehicle_internal_id: Callable[[dict[str, Any]], str],
    active_vehicles: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    """Înregistrează serviciile pentru istoricul intervențiilor."""

    async def async_add_service_record(call: ServiceCall) -> None:
        """Gestionează asincron adăugarea unei intervenții în istoric."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        vehicle_store = entry.runtime_data.vehicle_store
        history_store = entry.runtime_data.service_history_store
        fuel_store = entry.runtime_data.fuel_receipt_store
        tire_store = entry.runtime_data.tire_set_store
        equipment_store = entry.runtime_data.equipment_item_store
        battery_store = entry.runtime_data.battery_store

        vehicle_id = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_id:
            raise HomeAssistantError("ID-ul intern al autovehiculului este obligatoriu.")

        record_type = str(call.data["record_type"]).strip()
        if not record_type:
            raise HomeAssistantError("Tipul intervenției este obligatoriu.")

        record_date = str(call.data.get("date") or dt_date.today().isoformat()).strip()
        try:
            dt_date.fromisoformat(record_date)
        except ValueError as err:
            raise HomeAssistantError("Data intervenției trebuie să fie în format YYYY-MM-DD.") from err

        km_value = int(call.data.get(CONF_KM, 0) or 0)
        if km_value < 0:
            raise HomeAssistantError("Kilometrajul nu poate fi negativ.")

        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)

        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_id)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )

        vehicle_id = vehicle_internal_id(found_vehicle)

        requested_maintenance_update = bool(call.data.get("update_maintenance", True))
        update_maintenance = False
        maintenance_update_skipped_reason = ""
        previous_maintenance = None
        updated_maintenance = None

        if requested_maintenance_update and record_type in MAINTENANCE_TYPES:
            if _is_service_record_newer_than_current(
                found_vehicle,
                record_type,
                record_date,
                km_value,
            ):
                update_maintenance = True
                previous_maintenance = _maintenance_snapshot(found_vehicle, record_type)

                set_maintenance_value(found_vehicle, record_type, MAINTENANCE_LAST_DATE, record_date)
                if km_value > 0:
                    set_maintenance_value(found_vehicle, record_type, MAINTENANCE_LAST_KM, km_value)
                    if int(found_vehicle.get(CONF_KM, 0) or 0) < km_value:
                        found_vehicle[CONF_KM] = km_value

                updated_maintenance = _maintenance_snapshot(found_vehicle, record_type)

                normalized_vehicles, _ = normalize_vehicles(vehicles)
                active_vehicle_list = active_vehicles(normalized_vehicles)
                await vehicle_store.async_save_vehicles(normalized_vehicles)
                entry.runtime_data.vehicles = active_vehicle_list
                entry.runtime_data.all_vehicles = normalized_vehicles
                dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicle_list)

                from .notify import async_check_maintenance_notifications

                hass.async_create_task(async_check_maintenance_notifications(hass, entry))
            else:
                maintenance_update_skipped_reason = (
                    "Intervenția este mai veche decât mentenanța curentă sau nu are "
                    "kilometraj mai mare pentru aceeași dată. A fost salvată doar în istoric."
                )

        record = {
            "record_id": f"rec_{uuid4().hex[:12]}",
            CONF_VEHICLE_ID: vehicle_id,
            "record_type": record_type,
            "date": record_date,
            CONF_KM: km_value,
            "title": str(call.data.get("title", "")).strip(),
            "service_name": str(call.data.get("service_name", "")).strip(),
            "cost": float(call.data.get("cost", 0) or 0),
            "invoice_number": str(call.data.get("invoice_number", "")).strip(),
            "notes": str(call.data.get("notes", "")).strip(),
            "update_maintenance": update_maintenance,
            "requested_update_maintenance": requested_maintenance_update,
        }
        if maintenance_update_skipped_reason:
            record["maintenance_update_skipped_reason"] = maintenance_update_skipped_reason
        if previous_maintenance is not None:
            record["previous_maintenance"] = previous_maintenance
        if updated_maintenance is not None:
            record["updated_maintenance"] = updated_maintenance

        await history_store.async_add_record(record)

        await hass.config_entries.async_reload(entry.entry_id)

        _LOGGER.info(
            "Intervenție adăugată în istoricul Car Manager România: %s pentru %s",
            record_type,
            vehicle_id,
        )


    async def async_restore_service_record(call: ServiceCall) -> None:
        """Gestionează asincron restaurarea unei intervenții din istoric."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        record_id = str(call.data["record_id"]).strip()
        if not record_id:
            raise HomeAssistantError("ID-ul intervenției este obligatoriu.")

        record = await history_store.async_get_record(record_id)
        if record is None:
            raise HomeAssistantError("Intervenția selectată nu a fost găsită în istoric.")

        await _async_restore_service_record_snapshot(hass, entry, record, active_vehicles)

    async def async_restore_last_service_record(call: ServiceCall) -> None:
        """Gestionează asincron restaurarea ultimei intervenții din istoric."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        vehicle_id = str(call.data[CONF_VEHICLE_ID]).strip()
        if not vehicle_id:
            raise HomeAssistantError("Referința autovehiculului este obligatorie.")

        vehicle_store = entry.runtime_data.vehicle_store
        stored_vehicles = await vehicle_store.async_get_vehicles()
        option_vehicles = entry.options.get(
            CONF_VEHICLES,
            entry.data.get(CONF_VEHICLES, []),
        )
        vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
        found_vehicle = find_vehicle_by_reference(vehicles, vehicle_id)
        if found_vehicle is None:
            raise HomeAssistantError(
                "Autovehiculul selectat nu a fost găsit în Car Manager România. "
                "Poți folosi ID-ul intern, VIN-ul, numărul de înmatriculare sau numele mașinii."
            )
        vehicle_id = vehicle_internal_id(found_vehicle)

        requested_type = call.data.get("record_type")
        if requested_type is not None:
            requested_type = str(requested_type).strip()

        records = await history_store.async_get_records()
        selected_record: dict[str, Any] | None = None
        for record in reversed(records):
            if str(record.get(CONF_VEHICLE_ID, "")) != vehicle_id:
                continue
            if requested_type and str(record.get("record_type", "")) != requested_type:
                continue
            if bool(record.get("restored")):
                continue
            if not isinstance(record.get("previous_maintenance"), dict):
                continue
            selected_record = record
            break

        if selected_record is None:
            raise HomeAssistantError(
                "Nu există nicio intervenție restaurabilă pentru autovehiculul selectat."
            )

        await _async_restore_service_record_snapshot(hass, entry, selected_record, active_vehicles)

    async def async_update_service_record(call: ServiceCall) -> None:
        """Gestionează asincron actualizarea unei intervenții din istoric."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        record_id = str(call.data["record_id"]).strip()
        if not record_id:
            raise HomeAssistantError("ID-ul intervenției este obligatoriu.")

        existing_record = await history_store.async_get_record(record_id)
        if existing_record is None:
            raise HomeAssistantError("Intervenția selectată nu a fost găsită în istoric.")

        changes: dict[str, Any] = {}
        if "title" in call.data:
            changes["title"] = str(call.data.get("title", "")).strip()
        if "service_name" in call.data:
            changes["service_name"] = str(call.data.get("service_name", "")).strip()
        if "invoice_number" in call.data:
            changes["invoice_number"] = str(call.data.get("invoice_number", "")).strip()
        if "notes" in call.data:
            changes["notes"] = str(call.data.get("notes", "")).strip()
        if "cost" in call.data:
            cost_value = float(call.data.get("cost", 0) or 0)
            if cost_value < 0:
                raise HomeAssistantError("Costul nu poate fi negativ.")
            changes["cost"] = cost_value

        if not changes:
            raise HomeAssistantError("Nu există câmpuri de actualizat pentru intervenția selectată.")

        changes["updated_at"] = datetime.now().isoformat(timespec="seconds")

        await history_store.async_update_record(record_id, changes)
        await hass.config_entries.async_reload(entry.entry_id)

        _LOGGER.info("Intervenție actualizată în istoricul Car Manager România: %s", record_id)

    async def async_delete_service_record(call: ServiceCall) -> None:
        """Gestionează asincron ștergerea unei intervenții din istoric."""

        entry = find_loaded_config_entry(hass, call.data.get("entry_id"))
        history_store = entry.runtime_data.service_history_store

        record_id = str(call.data["record_id"]).strip()
        if not record_id:
            raise HomeAssistantError("ID-ul intervenției este obligatoriu.")

        deleted = await history_store.async_delete_record(record_id)
        if not deleted:
            raise HomeAssistantError("Intervenția selectată nu a fost găsită în istoric.")

        await hass.config_entries.async_reload(entry.entry_id)

        _LOGGER.info("Intervenție ștearsă din istoricul Car Manager România: %s", record_id)


    if not hass.services.has_service(DOMAIN, SERVICE_ADD_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_SERVICE_RECORD,
            async_add_service_record,
            schema=ADD_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_SERVICE_RECORD,
            async_restore_service_record,
            schema=RESTORE_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE_SERVICE_RECORD,
            async_update_service_record,
            schema=UPDATE_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_DELETE_SERVICE_RECORD,
            async_delete_service_record,
            schema=DELETE_SERVICE_RECORD_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_LAST_SERVICE_RECORD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESTORE_LAST_SERVICE_RECORD,
            async_restore_last_service_record,
            schema=RESTORE_LAST_SERVICE_RECORD_SCHEMA,
        )
