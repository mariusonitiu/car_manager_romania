"""Servicii pentru exportul, validarea și importul backup-urilor Car Manager România."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Callable

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import dispatcher_send

from .const import (
    CONF_NAME,
    CONF_REMOVED,
    CONF_VEHICLES,
    CONF_VEHICLE_ID,
    SIGNAL_VEHICLES_UPDATED,
    STORAGE_KEY_NOTIFICATIONS,
    STORAGE_VERSION_NOTIFICATIONS,
    VERSION,
)
from .maintenance import normalize_vehicles
from .storage import merge_vehicle_sources

_LOGGER = logging.getLogger(__name__)

EntryFinder = Callable[[HomeAssistant, str | None], Any]


EXPORT_DATA_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename", default="car_manager_romania_backup.json"): str,
    }
)

VALIDATE_BACKUP_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename", default="car_manager_romania_backup.json"): str,
    }
)

IMPORT_DATA_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename", default="car_manager_romania_backup.json"): str,
        vol.Optional("mode", default="merge"): vol.In(["merge"]),
        vol.Optional("dry_run", default=True): bool,
    }
)


def _backup_active_vehicles(vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returnează doar autovehiculele active dintr-o listă de backup/import."""

    return [vehicle for vehicle in vehicles if not bool(vehicle.get(CONF_REMOVED))]


def _normalize_backup_filename(raw_filename: Any) -> str:
    """Normalizează și validează numele fișierului de backup."""

    filename = str(raw_filename or "car_manager_romania_backup.json").strip()
    if not filename:
        filename = "car_manager_romania_backup.json"
    if "/" in filename or "\\" in filename:
        raise HomeAssistantError("Numele fișierului de backup nu trebuie să conțină cale sau directoare.")
    if not filename.lower().endswith(".json"):
        filename = f"{filename}.json"
    return filename


async def async_export_data(hass: HomeAssistant, call: ServiceCall, find_entry: EntryFinder) -> None:
    """Gestionează asincron operațiunea pentru export date."""

    entry = find_entry(hass, call.data.get("entry_id"))
    vehicle_store = entry.runtime_data.vehicle_store
    history_store = entry.runtime_data.service_history_store
    fuel_store = entry.runtime_data.fuel_receipt_store
    tire_store = entry.runtime_data.tire_set_store
    equipment_store = entry.runtime_data.equipment_item_store
    battery_store = entry.runtime_data.battery_store

    filename = _normalize_backup_filename(call.data.get("filename"))

    stored_vehicles = await vehicle_store.async_get_vehicles()
    option_vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    vehicles = merge_vehicle_sources(list(option_vehicles), stored_vehicles)
    normalized_vehicles, _ = normalize_vehicles(list(vehicles))
    service_history = await history_store.async_get_records()
    fuel_receipts = await fuel_store.async_get_receipts()
    tire_sets = await tire_store.async_get_sets()
    equipment_items = await equipment_store.async_get_items()
    battery_items = await battery_store.async_get_items()

    notification_data: dict[str, Any] = {}
    try:
        from homeassistant.helpers.storage import Store

        raw_notification_data = await Store(
            hass,
            STORAGE_VERSION_NOTIFICATIONS,
            STORAGE_KEY_NOTIFICATIONS,
        ).async_load()
        if isinstance(raw_notification_data, dict):
            notification_data = raw_notification_data
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Nu am putut include starea notificărilor în export: %s", err)

    backup_data = {
        "schema": "car_manager_romania_backup",
        "schema_version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "integration_version": VERSION,
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
        },
        "vehicles": normalized_vehicles,
        "service_history": service_history,
        "fuel_receipts": fuel_receipts,
        "tire_sets": tire_sets,
        "equipment_items": equipment_items,
        "battery_items": battery_items,
        "notification_state": notification_data,
    }

    backup_path = Path(hass.config.path(filename))
    backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2, default=str)

    def _write_backup() -> None:
        backup_path.write_text(backup_json, encoding="utf-8")

    await hass.async_add_executor_job(_write_backup)

    from homeassistant.components import persistent_notification

    persistent_notification.async_create(
        hass,
        "Exportul Car Manager România a fost salvat local.\n\n"
        f"Fișier: `{backup_path}`\n\n"
        "Fișierul conține datele autovehiculelor, istoricul intervențiilor, bonurile de combustibil, seturile de anvelope, echipamentele auto, bateriile și starea notificărilor. "
        "Păstrează-l în siguranță, deoarece poate include VIN, numere de înmatriculare și observații de service.",
        title="Car Manager România - export date finalizat",
        notification_id="car_manager_romania_export_data",
    )

    _LOGGER.info("Export Car Manager România salvat în %s", backup_path)

async def async_validate_backup(hass: HomeAssistant, call: ServiceCall, find_entry: EntryFinder) -> None:
    """Gestionează asincron operațiunea pentru validare backup."""

    # Găsim intrarea de configurare doar ca să validăm contextul. Nu modificăm datele integrației.
    find_entry(hass, call.data.get("entry_id"))

    filename = _normalize_backup_filename(call.data.get("filename"))

    backup_path = Path(hass.config.path(filename))

    def _read_backup() -> str:
        if not backup_path.exists():
            raise FileNotFoundError(str(backup_path))
        return backup_path.read_text(encoding="utf-8")

    try:
        backup_text = await hass.async_add_executor_job(_read_backup)
    except FileNotFoundError as err:
        raise HomeAssistantError(f"Fișierul de backup nu există: {backup_path}") from err
    except Exception as err:  # noqa: BLE001
        raise HomeAssistantError(f"Nu am putut citi fișierul de backup: {err}") from err

    try:
        backup_data = json.loads(backup_text)
    except json.JSONDecodeError as err:
        raise HomeAssistantError(f"Fișierul nu este JSON valid: {err}") from err

    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(backup_data, dict):
        errors.append("Structura principală trebuie să fie obiect JSON.")
        backup_data = {}

    if backup_data.get("schema") != "car_manager_romania_backup":
        errors.append("Schema backup-ului nu este car_manager_romania_backup.")

    schema_version = backup_data.get("schema_version")
    if schema_version != 1:
        errors.append(f"Versiune schemă nesuportată: {schema_version!r}. Versiunea acceptată este 1.")

    vehicles = backup_data.get("vehicles")
    if not isinstance(vehicles, list):
        errors.append("Câmpul vehicles lipsește sau nu este listă.")
        vehicles = []

    service_history = backup_data.get("service_history")
    if not isinstance(service_history, list):
        errors.append("Câmpul service_history lipsește sau nu este listă.")
        service_history = []

    fuel_receipts = backup_data.get("fuel_receipts", [])
    if not isinstance(fuel_receipts, list):
        warnings.append("Câmpul fuel_receipts nu este listă și va fi ignorat la import.")
        fuel_receipts = []

    tire_sets = backup_data.get("tire_sets", [])
    if not isinstance(tire_sets, list):
        warnings.append("Câmpul tire_sets nu este listă și va fi ignorat la import.")
        tire_sets = []

    equipment_items = backup_data.get("equipment_items", [])
    if not isinstance(equipment_items, list):
        warnings.append("Câmpul equipment_items nu este listă și va fi ignorat la import.")
        equipment_items = []

    battery_items = backup_data.get("battery_items", [])
    if not isinstance(battery_items, list):
        warnings.append("Câmpul battery_items nu este listă și va fi ignorat la import.")
        battery_items = []

    notification_state = backup_data.get("notification_state")
    if notification_state is not None and not isinstance(notification_state, dict):
        warnings.append("Câmpul notification_state nu este obiect JSON și va trebui ignorat la un import viitor.")

    vehicle_ids: set[str] = set()
    duplicate_vehicle_ids: set[str] = set()
    active_count = 0
    removed_count = 0
    missing_vehicle_id_count = 0

    for index, vehicle in enumerate(vehicles, start=1):
        if not isinstance(vehicle, dict):
            warnings.append(f"Autovehiculul #{index} nu este obiect JSON.")
            continue

        vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        if not vehicle_id:
            missing_vehicle_id_count += 1
        elif vehicle_id in vehicle_ids:
            duplicate_vehicle_ids.add(vehicle_id)
        else:
            vehicle_ids.add(vehicle_id)

        if bool(vehicle.get(CONF_REMOVED)):
            removed_count += 1
        else:
            active_count += 1

        if not str(vehicle.get(CONF_NAME, "")).strip():
            warnings.append(f"Autovehiculul #{index} nu are nume.")

    if missing_vehicle_id_count:
        warnings.append(f"{missing_vehicle_id_count} autovehicul(e) nu au vehicle_id.")
    if duplicate_vehicle_ids:
        warnings.append("Există vehicle_id duplicate: " + ", ".join(sorted(duplicate_vehicle_ids)))

    history_vehicle_refs: set[str] = set()
    missing_record_id_count = 0
    missing_record_vehicle_count = 0
    restorable_count = 0

    for index, record in enumerate(service_history, start=1):
        if not isinstance(record, dict):
            warnings.append(f"Intervenția #{index} nu este obiect JSON.")
            continue

        if not str(record.get("record_id", "")).strip():
            missing_record_id_count += 1

        record_vehicle_id = str(record.get(CONF_VEHICLE_ID, "")).strip()
        if not record_vehicle_id:
            missing_record_vehicle_count += 1
        else:
            history_vehicle_refs.add(record_vehicle_id)

        if isinstance(record.get("previous_maintenance"), dict) and not bool(record.get("restored")):
            restorable_count += 1

    if missing_record_id_count:
        warnings.append(f"{missing_record_id_count} intervenție/intervenții nu au record_id.")
    if missing_record_vehicle_count:
        warnings.append(f"{missing_record_vehicle_count} intervenție/intervenții nu au vehicle_id.")

    unknown_history_refs = sorted(ref for ref in history_vehicle_refs if ref not in vehicle_ids)
    if unknown_history_refs:
        warnings.append(
            "Există intervenții care referă autovehicule inexistente în backup: "
            + ", ".join(unknown_history_refs[:5])
            + ("..." if len(unknown_history_refs) > 5 else "")
        )

    exported_at = str(backup_data.get("exported_at", "necunoscut"))
    backup_version = str(backup_data.get("integration_version", "necunoscut"))

    from homeassistant.components import persistent_notification

    if errors:
        message = (
            "Backup-ul Car Manager România NU este valid pentru import. Nu s-a modificat nimic.\n\n"
            f"Fișier: `{backup_path}`\n\n"
            "Erori:\n"
            + "\n".join(f"- {error}" for error in errors)
        )
        title = "Car Manager România - backup invalid"
        notification_id = "car_manager_romania_validate_backup_invalid"
        _LOGGER.warning("Backup Car Manager România invalid: %s", "; ".join(errors))
    else:
        summary_lines = [
            "Backup-ul Car Manager România este valid. Nu s-a modificat nimic.",
            "",
            f"Fișier: `{backup_path}`",
            f"Exportat la: `{exported_at}`",
            f"Versiune integrare la export: `{backup_version}`",
            "",
            "Conținut:",
            f"- Autovehicule: {len(vehicles)} total, {active_count} active, {removed_count} dezactivate",
            f"- Intervenții în istoric: {len(service_history)}",
            f"- Intervenții restaurabile: {restorable_count}",
            f"- Bonuri combustibil: {len(fuel_receipts)}",
            f"- Seturi anvelope: {len(tire_sets)}",
            f"- Echipamente auto: {len(equipment_items)}",
            f"- Baterii auto: {len(battery_items)}",
        ]
        if warnings:
            summary_lines.extend(["", "Avertizări:"])
            summary_lines.extend(f"- {warning}" for warning in warnings[:10])
            if len(warnings) > 10:
                summary_lines.append(f"- ... încă {len(warnings) - 10} avertizări")
        message = "\n".join(summary_lines)
        title = "Car Manager România - backup valid"
        notification_id = "car_manager_romania_validate_backup_valid"
        _LOGGER.info(
            "Backup Car Manager România validat: %s vehicule, %s intervenții",
            len(vehicles),
            len(service_history),
        )

    persistent_notification.async_create(
        hass,
        message,
        title=title,
        notification_id=notification_id,
    )

async def async_import_data(hass: HomeAssistant, call: ServiceCall, find_entry: EntryFinder) -> None:
    """Gestionează asincron operațiunea pentru import date."""

    entry = find_entry(hass, call.data.get("entry_id"))
    vehicle_store = entry.runtime_data.vehicle_store
    history_store = entry.runtime_data.service_history_store
    fuel_store = entry.runtime_data.fuel_receipt_store
    tire_store = entry.runtime_data.tire_set_store
    equipment_store = entry.runtime_data.equipment_item_store
    battery_store = entry.runtime_data.battery_store

    filename = _normalize_backup_filename(call.data.get("filename"))

    mode = str(call.data.get("mode") or "merge").strip().lower()
    if mode != "merge":
        raise HomeAssistantError("Momentan importul permite doar modul sigur merge.")

    dry_run = bool(call.data.get("dry_run", True))
    backup_path = Path(hass.config.path(filename))

    def _read_backup() -> str:
        if not backup_path.exists():
            raise FileNotFoundError(str(backup_path))
        return backup_path.read_text(encoding="utf-8")

    try:
        backup_text = await hass.async_add_executor_job(_read_backup)
    except FileNotFoundError as err:
        raise HomeAssistantError(f"Fișierul de backup nu există: {backup_path}") from err
    except Exception as err:  # noqa: BLE001
        raise HomeAssistantError(f"Nu am putut citi fișierul de backup: {err}") from err

    try:
        backup_data = json.loads(backup_text)
    except json.JSONDecodeError as err:
        raise HomeAssistantError(f"Fișierul nu este JSON valid: {err}") from err

    if not isinstance(backup_data, dict):
        raise HomeAssistantError("Backup-ul nu are structură JSON validă.")
    if backup_data.get("schema") != "car_manager_romania_backup":
        raise HomeAssistantError("Schema backup-ului nu este car_manager_romania_backup.")
    if backup_data.get("schema_version") != 1:
        raise HomeAssistantError("Versiunea schemei de backup nu este suportată. Versiunea acceptată este 1.")

    backup_vehicles_raw = backup_data.get("vehicles")
    backup_history_raw = backup_data.get("service_history")
    backup_fuel_raw = backup_data.get("fuel_receipts", [])
    backup_tire_raw = backup_data.get("tire_sets", [])
    backup_equipment_raw = backup_data.get("equipment_items", [])
    backup_battery_raw = backup_data.get("battery_items", [])
    if not isinstance(backup_vehicles_raw, list):
        raise HomeAssistantError("Câmpul vehicles lipsește sau nu este listă.")
    if not isinstance(backup_history_raw, list):
        raise HomeAssistantError("Câmpul service_history lipsește sau nu este listă.")
    if not isinstance(backup_fuel_raw, list):
        backup_fuel_raw = []
    if not isinstance(backup_tire_raw, list):
        backup_tire_raw = []
    if not isinstance(backup_equipment_raw, list):
        backup_equipment_raw = []
    if not isinstance(backup_battery_raw, list):
        backup_battery_raw = []

    backup_vehicles, _ = normalize_vehicles([
        deepcopy(vehicle)
        for vehicle in backup_vehicles_raw
        if isinstance(vehicle, dict)
    ])
    backup_history = [
        deepcopy(record)
        for record in backup_history_raw
        if isinstance(record, dict)
    ]
    backup_fuel = [
        deepcopy(receipt)
        for receipt in backup_fuel_raw
        if isinstance(receipt, dict)
    ]
    backup_tires = [
        deepcopy(tire_set)
        for tire_set in backup_tire_raw
        if isinstance(tire_set, dict)
    ]
    backup_equipment = [
        deepcopy(item)
        for item in backup_equipment_raw
        if isinstance(item, dict)
    ]
    backup_batteries = [
        deepcopy(item)
        for item in backup_battery_raw
        if isinstance(item, dict)
    ]

    current_stored_vehicles = await vehicle_store.async_get_vehicles()
    option_vehicles = entry.options.get(
        CONF_VEHICLES,
        entry.data.get(CONF_VEHICLES, []),
    )
    current_vehicles = merge_vehicle_sources(list(option_vehicles), current_stored_vehicles)
    current_vehicles, _ = normalize_vehicles(current_vehicles)
    current_history = await history_store.async_get_records()
    current_fuel = await fuel_store.async_get_receipts()
    current_tires = await tire_store.async_get_sets()
    current_equipment = await equipment_store.async_get_items()
    current_batteries = await battery_store.async_get_items()

    merged_vehicles = [deepcopy(vehicle) for vehicle in current_vehicles if isinstance(vehicle, dict)]
    vehicle_index_by_id = {
        str(vehicle.get(CONF_VEHICLE_ID, "")).strip(): index
        for index, vehicle in enumerate(merged_vehicles)
        if isinstance(vehicle, dict) and str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
    }

    vehicles_added = 0
    vehicles_updated = 0
    vehicles_skipped = 0
    for vehicle in backup_vehicles:
        vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        if not vehicle_id:
            vehicles_skipped += 1
            continue
        if vehicle_id in vehicle_index_by_id:
            merged_vehicles[vehicle_index_by_id[vehicle_id]].update(deepcopy(vehicle))
            vehicles_updated += 1
        else:
            merged_vehicles.append(deepcopy(vehicle))
            vehicle_index_by_id[vehicle_id] = len(merged_vehicles) - 1
            vehicles_added += 1

    merged_vehicles, _ = normalize_vehicles(merged_vehicles)
    active_vehicles = _backup_active_vehicles(merged_vehicles)

    merged_history = [deepcopy(record) for record in current_history if isinstance(record, dict)]
    history_index_by_id = {
        str(record.get("record_id", "")).strip(): index
        for index, record in enumerate(merged_history)
        if isinstance(record, dict) and str(record.get("record_id", "")).strip()
    }

    history_added = 0
    history_updated = 0
    history_skipped = 0
    unknown_history_refs: set[str] = set()
    merged_vehicle_ids = {
        str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        for vehicle in merged_vehicles
        if isinstance(vehicle, dict) and str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
    }
    for record in backup_history:
        record_id = str(record.get("record_id", "")).strip()
        record_vehicle_id = str(record.get(CONF_VEHICLE_ID, "")).strip()
        if not record_id:
            history_skipped += 1
            continue
        if record_vehicle_id and record_vehicle_id not in merged_vehicle_ids:
            unknown_history_refs.add(record_vehicle_id)
        if record_id in history_index_by_id:
            merged_history[history_index_by_id[record_id]].update(deepcopy(record))
            history_updated += 1
        else:
            merged_history.append(deepcopy(record))
            history_index_by_id[record_id] = len(merged_history) - 1
            history_added += 1


    merged_fuel = [deepcopy(receipt) for receipt in current_fuel if isinstance(receipt, dict)]
    fuel_index_by_id = {
        str(receipt.get("receipt_id", "")).strip(): index
        for index, receipt in enumerate(merged_fuel)
        if isinstance(receipt, dict) and str(receipt.get("receipt_id", "")).strip()
    }
    fuel_added = 0
    fuel_updated = 0
    fuel_skipped = 0
    for receipt in backup_fuel:
        receipt_id = str(receipt.get("receipt_id", "")).strip()
        if not receipt_id:
            fuel_skipped += 1
            continue
        if receipt_id in fuel_index_by_id:
            merged_fuel[fuel_index_by_id[receipt_id]].update(deepcopy(receipt))
            fuel_updated += 1
        else:
            merged_fuel.append(deepcopy(receipt))
            fuel_index_by_id[receipt_id] = len(merged_fuel) - 1
            fuel_added += 1

    merged_tires = [deepcopy(tire_set) for tire_set in current_tires if isinstance(tire_set, dict)]
    tire_index_by_id = {
        str(tire_set.get("set_id", "")).strip(): index
        for index, tire_set in enumerate(merged_tires)
        if isinstance(tire_set, dict) and str(tire_set.get("set_id", "")).strip()
    }
    tire_added = 0
    tire_updated = 0
    tire_skipped = 0
    for tire_set in backup_tires:
        set_id = str(tire_set.get("set_id", "")).strip()
        if not set_id:
            tire_skipped += 1
            continue
        if set_id in tire_index_by_id:
            merged_tires[tire_index_by_id[set_id]].update(deepcopy(tire_set))
            tire_updated += 1
        else:
            merged_tires.append(deepcopy(tire_set))
            tire_index_by_id[set_id] = len(merged_tires) - 1
            tire_added += 1

    merged_equipment = [deepcopy(item) for item in current_equipment if isinstance(item, dict)]
    equipment_index_by_id = {
        str(item.get("item_id", "")).strip(): index
        for index, item in enumerate(merged_equipment)
        if isinstance(item, dict) and str(item.get("item_id", "")).strip()
    }
    equipment_added = 0
    equipment_updated = 0
    equipment_skipped = 0
    for item in backup_equipment:
        item_id = str(item.get("item_id", "")).strip()
        if not item_id:
            equipment_skipped += 1
            continue
        if item_id in equipment_index_by_id:
            merged_equipment[equipment_index_by_id[item_id]].update(deepcopy(item))
            equipment_updated += 1
        else:
            merged_equipment.append(deepcopy(item))
            equipment_index_by_id[item_id] = len(merged_equipment) - 1
            equipment_added += 1

    merged_batteries = [deepcopy(item) for item in current_batteries if isinstance(item, dict)]
    battery_index_by_id = {
        str(item.get("battery_id", "")).strip(): index
        for index, item in enumerate(merged_batteries)
        if isinstance(item, dict) and str(item.get("battery_id", "")).strip()
    }
    battery_added = 0
    battery_updated = 0
    battery_skipped = 0
    for item in backup_batteries:
        battery_id = str(item.get("battery_id", "")).strip()
        if not battery_id:
            battery_skipped += 1
            continue
        if battery_id in battery_index_by_id:
            merged_batteries[battery_index_by_id[battery_id]].update(deepcopy(item))
            battery_updated += 1
        else:
            merged_batteries.append(deepcopy(item))
            battery_index_by_id[battery_id] = len(merged_batteries) - 1
            battery_added += 1

    notification_merged = False
    notification_state = backup_data.get("notification_state")
    if isinstance(notification_state, dict) and isinstance(notification_state.get("notified"), dict):
        notification_merged = True

    if not dry_run:
        await vehicle_store.async_save_vehicles(merged_vehicles)
        await history_store.async_save_records(merged_history)
        await fuel_store.async_save_receipts(merged_fuel)
        await tire_store.async_save_sets(merged_tires)
        await equipment_store.async_save_items(merged_equipment)
        await battery_store.async_save_items(merged_batteries)

        if notification_merged and isinstance(notification_state, dict):
            try:
                from homeassistant.helpers.storage import Store

                notification_store = Store(
                    hass,
                    STORAGE_VERSION_NOTIFICATIONS,
                    STORAGE_KEY_NOTIFICATIONS,
                )
                current_notification_state = await notification_store.async_load()
                if not isinstance(current_notification_state, dict):
                    current_notification_state = {"notified": {}}
                current_notified = current_notification_state.get("notified")
                if not isinstance(current_notified, dict):
                    current_notified = {}
                incoming_notified = notification_state.get("notified")
                if isinstance(incoming_notified, dict):
                    current_notified.update(deepcopy(incoming_notified))
                await notification_store.async_save({"notified": current_notified})
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Nu am putut importa starea notificărilor Car Manager România: %s", err)

        entry.runtime_data.vehicles = active_vehicles
        entry.runtime_data.all_vehicles = merged_vehicles
        dispatcher_send(hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)

    exported_at = str(backup_data.get("exported_at", "necunoscut"))
    backup_version = str(backup_data.get("integration_version", "necunoscut"))
    from homeassistant.components import persistent_notification

    summary_lines = [
        "Importul Car Manager România a fost simulat. Nu s-a modificat nimic." if dry_run else "Importul Car Manager România a fost aplicat în modul merge.",
        "",
        f"Fișier: `{backup_path}`",
        f"Exportat la: `{exported_at}`",
        f"Versiune integrare la export: `{backup_version}`",
        "Mod import: `merge`",
        f"Dry run: `{str(dry_run).lower()}`",
        "",
        "Rezultat:",
        f"- Autovehicule adăugate: {vehicles_added}",
        f"- Autovehicule actualizate: {vehicles_updated}",
        f"- Autovehicule ignorate: {vehicles_skipped}",
        f"- Intervenții adăugate: {history_added}",
        f"- Intervenții actualizate: {history_updated}",
        f"- Intervenții ignorate: {history_skipped}",
        f"- Bonuri combustibil adăugate: {fuel_added}",
        f"- Bonuri combustibil actualizate: {fuel_updated}",
        f"- Bonuri combustibil ignorate: {fuel_skipped}",
        f"- Seturi anvelope adăugate: {tire_added}",
        f"- Seturi anvelope actualizate: {tire_updated}",
        f"- Seturi anvelope ignorate: {tire_skipped}",
        f"- Echipamente auto adăugate: {equipment_added}",
        f"- Echipamente auto actualizate: {equipment_updated}",
        f"- Echipamente auto ignorate: {equipment_skipped}",
        f"- Baterii auto adăugate: {battery_added}",
        f"- Baterii auto actualizate: {battery_updated}",
        f"- Baterii auto ignorate: {battery_skipped}",
        f"- Stare notificări: {'inclusă în merge' if notification_merged else 'neinclusă / lipsă'}",
    ]
    if unknown_history_refs:
        summary_lines.extend([
            "",
            "Avertizări:",
            "- Există intervenții cu vehicle_id necunoscut după import: "
            + ", ".join(sorted(unknown_history_refs)[:5])
            + ("..." if len(unknown_history_refs) > 5 else ""),
        ])
    if dry_run:
        summary_lines.extend([
            "",
            "Pentru aplicare reală, rulează din nou serviciul cu `dry_run: false`.",
        ])
    else:
        summary_lines.extend([
            "",
            "Integrarea se reîncarcă pentru actualizarea entităților și a cardului.",
        ])

    persistent_notification.async_create(
        hass,
        "\n".join(summary_lines),
        title="Car Manager România - import backup" if not dry_run else "Car Manager România - simulare import backup",
        notification_id="car_manager_romania_import_data",
    )

    _LOGGER.info(
        "Import Car Manager România %s din %s: vehicule +%s/~%s, istoric +%s/~%s",
        "dry-run" if dry_run else "aplicat",
        backup_path,
        vehicles_added,
        vehicles_updated,
        history_added,
        history_updated,
    )

    if not dry_run:
        await hass.config_entries.async_reload(entry.entry_id)

