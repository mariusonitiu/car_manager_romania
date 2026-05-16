"""Modul pentru butoanele integrației Car Manager România."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CarManagerConfigEntry
from .const import CONF_NAME, DOMAIN, SIGNAL_LICENSE_UPDATED, VERSION
from .license import (
    async_obtine_context_licenta,
    async_salveaza_licenta_globala,
    async_valideaza_licenta,
)


LICENSE_TEXT_UNIQUE_SUFFIX = "license_v2_key_text"


def _license_text_entity_id(hass: HomeAssistant, entry: CarManagerConfigEntry) -> str | None:
    """Funcție internă pentru licență text entitate ID."""

    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_{LICENSE_TEXT_UNIQUE_SUFFIX}"
    return registry.async_get_entity_id("text", DOMAIN, unique_id)


def _hub_device_info(entry: CarManagerConfigEntry) -> DeviceInfo:
    """Funcție internă pentru hub dispozitiv informații."""

    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, "Car Manager România"),
        manufacturer="Car Manager România",
        model="Hub",
        sw_version=VERSION,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează componentele integrației în Home Assistant."""

    entities: list[ButtonEntity] = [
        CarManagerApplyLicenseButton(entry),
        CarManagerRefreshLicenseStatusButton(entry),
    ]

    if entry.runtime_data.rovinieta_coordinator is not None:
        entities.append(CarManagerRovinietaRefreshButton(entry))

    async_add_entities(entities)


class CarManagerApplyLicenseButton(ButtonEntity):
    """Clasă pentru apply licență buton."""

    _attr_has_entity_name = True
    _attr_name = "Aplică licență"
    _attr_icon = "mdi:key-chain-variant"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Funcție internă pentru init."""

        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_license_v2_apply"
        self._attr_suggested_object_id = f"{DOMAIN}_aplica_licenta"

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return _hub_device_info(self._entry)

    async def async_press(self) -> None:
        """Gestionează asincron operațiunea pentru press."""

        text_entity_id = _license_text_entity_id(self.hass, self._entry)
        if not text_entity_id:
            raise HomeAssistantError("Nu am găsit câmpul text pentru introducerea licenței.")

        state = self.hass.states.get(text_entity_id)
        license_key = str(state.state).strip() if state else ""
        if not license_key:
            raise HomeAssistantError("Introdu mai întâi un cod de licență sau TRIAL.")

        username, _current_key, _storage = await async_obtine_context_licenta(self.hass, intrare=self._entry)

        notification_id = "car_manager_romania_aplica_licenta"
        result = await async_valideaza_licenta(self.hass, license_key, username)

        await async_salveaza_licenta_globala(self.hass, license_key, username, result)

        await self.hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": text_entity_id, "value": license_key},
            blocking=True,
        )

        dispatcher_send(self.hass, SIGNAL_LICENSE_UPDATED)

        if not result.valid:
            message = result.message or "Codul de licență nu a putut fi validat."
            persistent_notification.async_create(
                self.hass,
                f"Aplicarea licenței a eșuat.\n\nMotiv: **{message}**",
                title="Car Manager România – Licență",
                notification_id=notification_id,
            )
            raise HomeAssistantError(message)

        persistent_notification.async_create(
            self.hass,
            (
                "Licența a fost actualizată cu succes.\n\n"
                f"- Utilizator: **{result.username or username or '-'}**\n"
                f"- Plan: **{result.plan or '-'}**\n"
                f"- Expiră la: **{result.expires_at or '-'}**"
            ),
            title="Car Manager România – Licență",
            notification_id=notification_id,
        )


class CarManagerRefreshLicenseStatusButton(ButtonEntity):
    """Clasă pentru butonul de actualizare a statusului licenței."""

    _attr_has_entity_name = True
    _attr_name = "Actualizează status licență"
    _attr_icon = "mdi:shield-sync-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Funcție internă pentru init."""

        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_license_v2_refresh"
        self._attr_suggested_object_id = f"{DOMAIN}_actualizeaza_status_licenta"

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return _hub_device_info(self._entry)

    async def async_press(self) -> None:
        """Gestionează asincron operațiunea pentru press."""

        username, license_key, _storage = await async_obtine_context_licenta(self.hass, intrare=self._entry)
        license_key = str(license_key or "").strip() or "TRIAL"

        result = await async_valideaza_licenta(self.hass, license_key, username)
        await async_salveaza_licenta_globala(self.hass, license_key, username, result)
        dispatcher_send(self.hass, SIGNAL_LICENSE_UPDATED)

        notification_id = "car_manager_romania_actualizeaza_licenta"
        if not result.valid:
            message = result.message or "Licența nu este validă."
            persistent_notification.async_create(
                self.hass,
                f"Statusul licenței a fost verificat.\n\nMotiv: **{message}**",
                title="Car Manager România – Licență",
                notification_id=notification_id,
            )
            raise HomeAssistantError(message)

        persistent_notification.async_create(
            self.hass,
            (
                "Statusul licenței a fost actualizat cu succes.\n\n"
                f"- Utilizator: **{result.username or username or '-'}**\n"
                f"- Plan: **{result.plan or '-'}**\n"
                f"- Expiră la: **{result.expires_at or '-'}**"
            ),
            title="Car Manager România – Licență",
            notification_id=notification_id,
        )


class CarManagerRovinietaRefreshButton(ButtonEntity):
    """Clasă pentru rovinietă refresh buton."""

    _attr_has_entity_name = True
    _attr_name = "Actualizează rovinieta"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Funcție internă pentru init."""

        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_rovinieta_refresh"

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return _hub_device_info(self._entry)

    async def async_press(self) -> None:
        """Gestionează asincron operațiunea pentru press."""

        coordinator = self._entry.runtime_data.rovinieta_coordinator
        if coordinator is None:
            raise HomeAssistantError("Modulul rovinietă nu este configurat.")

        await coordinator.async_request_refresh()
