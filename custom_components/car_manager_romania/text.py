"""Modul pentru entitățile text editabile."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send

from . import CarManagerConfigEntry
from .const import (
    CONF_CONSUMABLES,
    CONF_FUEL_PROFILE,
    CONSUMABLE_TYPES,
    CASCO_TEXT_FIELDS,
    ITP_TEXT_FIELDS,
    LEGAL_TYPE_CASCO,
    LEGAL_TYPE_ITP,
    LEGAL_TYPE_RCA,
    RCA_TEXT_FIELDS,
    CONF_REMOVED,
    DOMAIN,
    VERSION,
    SIGNAL_VEHICLES_UPDATED,
    SIGNAL_LICENSE_UPDATED,
)
from .device import build_vehicle_device_info
from .license_access import async_license_allows_all_vehicles, vehicle_allowed_by_license
from .legal import get_legal_value, set_legal_value
from .license import async_obtine_licenta_globala




def _hub_device_info(entry: CarManagerConfigEntry) -> DeviceInfo:
    """Funcție internă pentru hub dispozitiv informații."""

    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get("name", "Car Manager România"),
        manufacturer="Car Manager România",
        model="Hub",
        sw_version=VERSION,
    )


LEGAL_TEXT_FIELDS: dict[str, dict[str, str]] = {
    LEGAL_TYPE_RCA: RCA_TEXT_FIELDS,
    LEGAL_TYPE_CASCO: CASCO_TEXT_FIELDS,
    LEGAL_TYPE_ITP: ITP_TEXT_FIELDS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează componentele integrației în Home Assistant."""

    entities: list[TextEntity] = [CarManagerLicenseKeyText(entry)]

    for vehicle in entry.runtime_data.vehicles:
        entities.append(VehicleFuelProfileText(hass, entry, vehicle))

        for consumable_key, label in CONSUMABLE_TYPES.items():
            entities.append(
                VehicleConsumableText(
                    hass,
                    entry,
                    vehicle,
                    consumable_key,
                    label,
                )
            )

        for legal_type, fields in LEGAL_TEXT_FIELDS.items():
            for field, label in fields.items():
                entities.append(
                    VehicleLegalText(
                        hass,
                        entry,
                        vehicle,
                        legal_type,
                        field,
                        label,
                    )
                )

    async_add_entities(entities)


class CarManagerLicenseKeyText(RestoreEntity, TextEntity):
    """Clasă pentru licență cheie text."""

    _attr_has_entity_name = True
    _attr_name = "Cod licență nou"
    _attr_icon = "mdi:key-outline"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 0
    _attr_native_max = 128
    _attr_mode = "text"

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Funcție internă pentru init."""

        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_license_v2_key_text"
        self._attr_suggested_object_id = f"{DOMAIN}_cod_licenta_noua"
        self._attr_native_value = "TRIAL"

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return _hub_device_info(self._entry)

    async def async_added_to_hass(self) -> None:
        """Gestionează asincron operațiunea pentru added to hass."""

        await super().async_added_to_hass()

        storage = await async_obtine_licenta_globala(self.hass)
        storage_key = str(storage.get("cheie_licenta", "")).strip() if isinstance(storage, dict) else ""

        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last_state.state
        elif storage_key:
            self._attr_native_value = storage_key
        else:
            self._attr_native_value = "TRIAL"

    async def async_set_value(self, value: str) -> None:
        """Gestionează asincron operațiunea pentru set valoare."""

        self._attr_native_value = str(value or "")[: self._attr_native_max]
        self.async_write_ha_state()


class VehicleBaseText(TextEntity):
    """Clasă pentru vehicul de bază text."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Funcție internă pentru init."""

        self._hass = hass
        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]
        self._license_allows_all_vehicles = False

    async def async_added_to_hass(self) -> None:
        """Gestionează asincron operațiunea pentru added to hass."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VEHICLES_UPDATED,
                self._handle_vehicles_updated,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LICENSE_UPDATED,
                self._schedule_license_refresh,
            )
        )
        await self._async_refresh_license_gate(write_state=False)

    @callback
    def _schedule_license_refresh(self) -> None:
        """Funcție internă pentru schedule licență refresh."""

        self.hass.async_create_task(self._async_refresh_license_gate())

    async def _async_refresh_license_gate(self, write_state: bool = True) -> None:
        """Funcție internă pentru refresh licență gate."""

        self._license_allows_all_vehicles = await async_license_allows_all_vehicles(self.hass)
        if write_state:
            self.async_write_ha_state()

    def _handle_vehicles_updated(self, vehicles: list[dict[str, Any]]) -> None:
        """Funcție internă pentru gestionare vehicule updated."""

        for vehicle in vehicles:
            if vehicle.get("vehicle_id") == self._vehicle_id:
                self._vehicle = vehicle
                self.async_write_ha_state()
                break

    @property
    def _blocked_by_license(self) -> bool:
        """Funcție internă pentru blocate by licență."""

        return not vehicle_allowed_by_license(
            self._entry,
            self._vehicle_id,
            self._license_allows_all_vehicles,
        )

    @property
    def available(self) -> bool:
        """Funcție pentru disponibil."""

        return not self._blocked_by_license

    def _raise_if_blocked_by_license(self) -> None:
        """Funcție internă pentru raise if blocate by licență."""

        if self._blocked_by_license:
            raise HomeAssistantError("Autovehicul dezactivat fără licență activă.")

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return build_vehicle_device_info(self._vehicle)

    def _get_vehicles_for_update(self) -> list[dict[str, Any]]:
        """Funcție internă pentru get vehicule for actualizare."""

        return deepcopy(getattr(self._entry.runtime_data, "all_vehicles", self._entry.runtime_data.vehicles))

    async def _persist_vehicles(self, vehicles: list[dict[str, Any]]) -> None:
        """Funcție internă pentru persistare vehicule."""

        self._raise_if_blocked_by_license()

        await self._entry.runtime_data.vehicle_store.async_save_vehicles(vehicles)

        active_vehicles = [
            vehicle for vehicle in vehicles
            if isinstance(vehicle, dict) and not bool(vehicle.get(CONF_REMOVED))
        ]
        self._entry.runtime_data.all_vehicles = list(vehicles)
        self._entry.runtime_data.vehicles = active_vehicles
        dispatcher_send(self._hass, SIGNAL_VEHICLES_UPDATED, active_vehicles)
        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                self._vehicle = vehicle
                break

        self.async_write_ha_state()


class VehicleFuelProfileText(VehicleBaseText):
    """Clasă pentru vehicul combustibil profil text."""

    _attr_name = "Motorizare"
    _attr_icon = "mdi:gas-station"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Funcție internă pentru init."""

        super().__init__(hass, entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{CONF_FUEL_PROFILE}"

    @property
    def native_value(self) -> str | None:
        """Funcție pentru native valoare."""

        return str(self._vehicle.get(CONF_FUEL_PROFILE, "diesel") or "diesel")

    async def async_set_value(self, value: str) -> None:
        """Gestionează asincron operațiunea pentru set valoare."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                vehicle[CONF_FUEL_PROFILE] = value
                break

        await self._persist_vehicles(vehicles)


class VehicleConsumableText(VehicleBaseText):
    """Clasă pentru vehicul consumable text."""

    _attr_icon = "mdi:car-wrench"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        consumable_key: str,
        label: str,
    ) -> None:
        """Funcție internă pentru init."""

        super().__init__(hass, entry, vehicle)
        self._consumable_key = consumable_key

        self._attr_name = label
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_consumable_{consumable_key}"
        )

    @property
    def native_value(self) -> str | None:
        """Funcție pentru native valoare."""

        consumables = self._vehicle.get(CONF_CONSUMABLES, {})
        value = consumables.get(self._consumable_key) if isinstance(consumables, dict) else ""
        return str(value) if value is not None else ""

    async def async_set_value(self, value: str) -> None:
        """Gestionează asincron operațiunea pentru set valoare."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                vehicle.setdefault(CONF_CONSUMABLES, {})[self._consumable_key] = value
                break

        await self._persist_vehicles(vehicles)


class VehicleLegalText(VehicleBaseText):
    """Clasă pentru vehicul legal text."""

    _attr_icon = "mdi:shield-car"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        legal_type: str,
        field: str,
        label: str,
    ) -> None:
        """Funcție internă pentru init."""

        super().__init__(hass, entry, vehicle)
        self._legal_type = legal_type
        self._field = field
        self._attr_name = label
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{legal_type}_{field}"

    @property
    def native_value(self) -> str | None:
        """Funcție pentru native valoare."""

        value = get_legal_value(self._vehicle, self._legal_type, self._field)
        return str(value) if value is not None else ""

    async def async_set_value(self, value: str) -> None:
        """Gestionează asincron operațiunea pentru set valoare."""

        vehicles = self._get_vehicles_for_update()

        for vehicle in vehicles:
            if vehicle["vehicle_id"] == self._vehicle_id:
                set_legal_value(vehicle, self._legal_type, self._field, value)
                break

        await self._persist_vehicles(vehicles)
