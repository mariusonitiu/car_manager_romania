"""Modul pentru aplicarea accesului permis de licență."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_REMOVED, CONF_VEHICLE_ID, CONF_VEHICLES, DATE_VERIFICARE_LICENTA
from .license import async_obtine_licenta_globala, licenta_este_acceptata


def _first_vehicle_id_from_list(vehicles: Any, allowed_ids: set[str] | None = None) -> str | None:
    """Funcție internă pentru primul ID de vehicul din listă."""

    for vehicle in list(vehicles or []):
        if not isinstance(vehicle, dict) or bool(vehicle.get(CONF_REMOVED)):
            continue
        vehicle_id = str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        if not vehicle_id:
            continue
        if allowed_ids is not None and vehicle_id not in allowed_ids:
            continue
        return vehicle_id
    return None


def first_enabled_vehicle_id(entry: Any) -> str | None:
    """Funcție pentru first enabled vehicul ID."""

    runtime_data = getattr(entry, "runtime_data", None)
    all_vehicles = list(getattr(runtime_data, "all_vehicles", []) or [])
    active_ids = {
        str(vehicle.get(CONF_VEHICLE_ID, "")).strip()
        for vehicle in all_vehicles
        if isinstance(vehicle, dict) and not bool(vehicle.get(CONF_REMOVED)) and vehicle.get(CONF_VEHICLE_ID)
    }

    original_data_vehicles = (getattr(entry, "data", {}) or {}).get(CONF_VEHICLES, [])
    vehicle_id = _first_vehicle_id_from_list(original_data_vehicles, active_ids or None)
    if vehicle_id:
        return vehicle_id

    option_vehicles = (getattr(entry, "options", {}) or {}).get(CONF_VEHICLES, [])
    vehicle_id = _first_vehicle_id_from_list(option_vehicles, active_ids or None)
    if vehicle_id:
        return vehicle_id

    runtime_vehicles = list(getattr(runtime_data, "vehicles", []) or [])
    vehicle_id = _first_vehicle_id_from_list(runtime_vehicles, active_ids or None)
    if vehicle_id:
        return vehicle_id

    return _first_vehicle_id_from_list(all_vehicles)


def vehicle_allowed_by_license(entry: Any, vehicle_id: str, license_allows_all: bool) -> bool:
    """Funcție pentru vehicul permise by licență."""

    if license_allows_all:
        return True

    first_vehicle_id = first_enabled_vehicle_id(entry)
    if not first_vehicle_id:
        return True

    return str(vehicle_id or "").strip() == first_vehicle_id


def locked_vehicle_attributes(vehicle_id: str) -> dict[str, Any]:
    """Funcție pentru blocate vehicul atribute."""

    return {
        "vehicle_id": str(vehicle_id or ""),
        "license_blocked": True,
        "motiv": "Autovehicul dezactivat fără licență activă.",
    }


async def async_license_allows_all_vehicles(hass: HomeAssistant) -> bool:
    """Gestionează asincron operațiunea pentru licență allows all vehicule."""

    storage = await async_obtine_licenta_globala(hass)
    storage = storage if isinstance(storage, dict) else {}
    info = storage.get(DATE_VERIFICARE_LICENTA)
    info = info if isinstance(info, dict) else {}
    return licenta_este_acceptata(info)
