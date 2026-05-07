"""Base entities for Car Manager România rovinieta."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, CONF_NAME, CONF_LICENSE_PLATE, CONF_VIN


class ERovinietaCoordinatorEntity(CoordinatorEntity):
    """Base coordinator entity for rovinieta."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, vehicle: dict | None = None) -> None:
        super().__init__(coordinator)
        self.vehicle = vehicle or {}
        self._account_id = getattr(coordinator, "account_id", "rovinieta")

    @property
    def account_device_info(self) -> DeviceInfo:
        """Return Car Manager account/device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, "rovinieta_account")},
            name="Rovinietă",
            manufacturer="Car Manager România",
            model="Modul rovinietă",
        )

    def vehicle_device_info(self, vehicle: dict) -> DeviceInfo:
        """Return vehicle device info."""
        vehicle_name = (
            vehicle.get(CONF_NAME)
            or vehicle.get(CONF_LICENSE_PLATE)
            or "Autovehicul"
        )

        identifier = (
            vehicle.get(CONF_VIN)
            or vehicle.get(CONF_LICENSE_PLATE)
            or vehicle_name
        )

        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=vehicle_name,
            manufacturer="Car Manager România",
            model="Autovehicul",
        )