"""Modul pentru informațiile de dispozitiv."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_NAME, CONF_VIN, DOMAIN, VERSION


def build_vehicle_device_info(vehicle: dict[str, Any]) -> DeviceInfo:
    """Funcție pentru build vehicul dispozitiv informații."""

    vehicle_id = vehicle["vehicle_id"]

    return DeviceInfo(
        identifiers={(DOMAIN, vehicle_id)},
        name=vehicle.get(CONF_NAME, "Autovehicul"),
        manufacturer="Car Manager România",
        model="Autovehicul",
        serial_number=vehicle.get(CONF_VIN) or None,
        sw_version=VERSION,
    )
