"""Modul pentru senzorii Car Manager România."""

from __future__ import annotations

from datetime import UTC
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .. import CarManagerConfigEntry
from ..const import CONF_LICENSE_PLATE, CONF_NAME, CONF_VIN, DOMAIN, VERSION, SIGNAL_LICENSE_UPDATED
from .coordinator import CarManagerRovinietaCoordinator
from ..license_access import async_license_allows_all_vehicles, locked_vehicle_attributes, vehicle_allowed_by_license
from .helpers import slugify_plate
from .models import VehicleData


def _iso(dt):
    return dt.astimezone(UTC).isoformat() if dt else None


def _format_datetime(dt) -> str | None:
    """Funcție internă pentru formatare datetime."""

    if dt is None:
        return None

    local_dt = dt.astimezone()
    return local_dt.strftime("%d.%m.%Y %H:%M")


async def async_setup_rovinieta_sensors(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează componentele integrației în Home Assistant."""

    coordinator = entry.runtime_data.rovinieta_coordinator
    if coordinator is None or coordinator.data is None:
        return

    entities: list[SensorEntity] = []

    for vehicle in entry.runtime_data.vehicles:
        license_plate = (vehicle.get(CONF_LICENSE_PLATE) or "").strip().upper()
        if not license_plate:
            continue

        rovinieta_vehicle = _find_rovinieta_vehicle(coordinator, license_plate)
        if rovinieta_vehicle is None:
            continue

        entities.extend(
            [
                CarRovinietaStatusSensor(entry, coordinator, vehicle, rovinieta_vehicle.id),
                CarRovinietaExpirySensor(entry, coordinator, vehicle, rovinieta_vehicle.id),
                CarRovinietaDaysRemainingSensor(entry, coordinator, vehicle, rovinieta_vehicle.id),
                CarRovinietaSeriesSensor(entry, coordinator, vehicle, rovinieta_vehicle.id),
                CarRovinietaCategorySensor(entry, coordinator, vehicle, rovinieta_vehicle.id),
                CarRovinietaPeriodSensor(entry, coordinator, vehicle, rovinieta_vehicle.id),
            ]
        )

    async_add_entities(entities)


def _find_rovinieta_vehicle(
    coordinator: CarManagerRovinietaCoordinator,
    license_plate: str,
) -> VehicleData | None:
    """Funcție internă pentru căutare rovinietă vehicul."""

    wanted = license_plate.replace(" ", "").upper()
    for vehicle in coordinator.data.vehicles:
        candidate = vehicle.plate_no.replace(" ", "").upper()
        if candidate == wanted:
            return vehicle
    return None


class CarRovinietaBaseSensor(SensorEntity):
    """Clasă pentru rovinietă de bază senzor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        coordinator: CarManagerRovinietaCoordinator,
        car_vehicle: dict[str, Any],
        rovinieta_vehicle_id: int,
    ) -> None:
        """Funcție internă pentru init."""

        self._entry = entry
        self.coordinator = coordinator
        self._car_vehicle = car_vehicle
        self._vehicle_id = car_vehicle["vehicle_id"]
        self._rovinieta_vehicle_id = rovinieta_vehicle_id
        self._license_allows_all_vehicles = False

    async def async_added_to_hass(self) -> None:
        """Gestionează asincron operațiunea pentru added to hass."""

        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
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

        return not self._blocked_by_license and self.rovinieta_vehicle is not None

    @property
    def rovinieta_vehicle(self) -> VehicleData | None:
        """Funcție pentru rovinietă vehicul."""

        if self.coordinator.data is None:
            return None

        for vehicle in self.coordinator.data.vehicles:
            if vehicle.id == self._rovinieta_vehicle_id:
                return vehicle

        license_plate = (self._car_vehicle.get(CONF_LICENSE_PLATE) or "").strip().upper()
        return _find_rovinieta_vehicle(self.coordinator, license_plate)

    @property
    def device_info(self) -> DeviceInfo:
        """Funcție pentru dispozitiv informații."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._vehicle_id)},
            name=self._car_vehicle.get(CONF_NAME, "Autovehicul"),
            manufacturer="Car Manager România",
            model="Autovehicul",
            serial_number=self._car_vehicle.get(CONF_VIN) or None,
            sw_version=VERSION,
        )

    @property
    def common_attributes(self) -> dict[str, Any]:
        """Funcție pentru comune atribute."""

        if self._blocked_by_license:
            return locked_vehicle_attributes(self._vehicle_id)

        vehicle = self.rovinieta_vehicle
        if vehicle is None:
            return {}

        attrs = {
            "vehicle_id": vehicle.id,
            "numar_inmatriculare": vehicle.plate_no,
            "serie_sasiu": vehicle.chasis_no,
            "tara": vehicle.country_name,
            "cod_tara": vehicle.country_code,
            "categorie_rovinieta": vehicle.category_vignette_title,
            "descriere_categorie_rovinieta": vehicle.category_vignette_desc,
            "categorie_taxa_pod": vehicle.category_toll_title,
            "descriere_categorie_taxa_pod": vehicle.category_toll_desc,
            "numar_total_roviniete": vehicle.all_time_count,
            "numar_roviniete_active": vehicle.active_count,
            "expira_la": _iso(vehicle.expiry),
            "expira_la_formatat": _format_datetime(vehicle.expiry),
            "zile_ramase": vehicle.days_remaining,
        }

        if vehicle.active_vignette:
            attrs.update(
                {
                    "detalii_rovinieta_activa": vehicle.active_vignette,
                    "serie_rovinieta": vehicle.active_vignette.get("oProdVignetteSerie"),
                    "perioada": vehicle.active_vignette.get("oProdPeriodName"),
                    "pret_lei": vehicle.active_vignette.get("oProdPrice"),
                    "pret_euro": vehicle.active_vignette.get("oProdPriceEuro"),
                    "data_start": vehicle.active_vignette.get("date_start_availability"),
                    "data_stop": vehicle.active_vignette.get("date_stop_availability"),
                    "transaction_id": vehicle.active_vignette.get("oProdTransactionID"),
                }
            )

        return attrs


class CarRovinietaStatusSensor(CarRovinietaBaseSensor):
    """Clasă pentru senzorul de status al rovinietei."""

    _attr_name = "Rovinietă"
    _attr_icon = "mdi:shield-car"

    def __init__(self, entry, coordinator, car_vehicle, rovinieta_vehicle_id: int) -> None:
        super().__init__(entry, coordinator, car_vehicle, rovinieta_vehicle_id)
        slug = slugify_plate(car_vehicle.get(CONF_LICENSE_PLATE, self._vehicle_id))
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{slug}_rovinieta_status"

    @property
    def native_value(self) -> str | None:
        vehicle = self.rovinieta_vehicle
        if vehicle is None:
            return None

        if vehicle.has_active_vignette and vehicle.days_remaining is not None and vehicle.days_remaining >= 0:
            return "activă"
        if vehicle.has_active_vignette and vehicle.days_remaining is not None and vehicle.days_remaining < 0:
            return "expirată"
        return "fără rovinietă activă"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.common_attributes


class CarRovinietaExpirySensor(CarRovinietaBaseSensor):
    """Clasă pentru rovinietă expirare senzor."""

    _attr_name = "Rovinietă expiră la"
    _attr_icon = "mdi:calendar-end"

    def __init__(self, entry, coordinator, car_vehicle, rovinieta_vehicle_id: int) -> None:
        super().__init__(entry, coordinator, car_vehicle, rovinieta_vehicle_id)
        slug = slugify_plate(car_vehicle.get(CONF_LICENSE_PLATE, self._vehicle_id))
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{slug}_rovinieta_expiry"

    @property
    def native_value(self):
        vehicle = self.rovinieta_vehicle
        return _format_datetime(vehicle.expiry) if vehicle else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.common_attributes


class CarRovinietaDaysRemainingSensor(CarRovinietaBaseSensor):
    """Clasă pentru rovinietă zile rămași senzor."""

    _attr_name = "Zile rămase rovinietă"
    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = "zile"

    def __init__(self, entry, coordinator, car_vehicle, rovinieta_vehicle_id: int) -> None:
        super().__init__(entry, coordinator, car_vehicle, rovinieta_vehicle_id)
        slug = slugify_plate(car_vehicle.get(CONF_LICENSE_PLATE, self._vehicle_id))
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{slug}_rovinieta_days_remaining"

    @property
    def native_value(self):
        vehicle = self.rovinieta_vehicle
        return vehicle.days_remaining if vehicle else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.common_attributes


class CarRovinietaSeriesSensor(CarRovinietaBaseSensor):
    """Clasă pentru rovinietă series senzor."""

    _attr_name = "Serie rovinietă"
    _attr_icon = "mdi:identifier"

    def __init__(self, entry, coordinator, car_vehicle, rovinieta_vehicle_id: int) -> None:
        super().__init__(entry, coordinator, car_vehicle, rovinieta_vehicle_id)
        slug = slugify_plate(car_vehicle.get(CONF_LICENSE_PLATE, self._vehicle_id))
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{slug}_rovinieta_series"

    @property
    def native_value(self):
        vehicle = self.rovinieta_vehicle
        if vehicle is None or not vehicle.active_vignette:
            return None
        return vehicle.active_vignette.get("oProdVignetteSerie")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.common_attributes


class CarRovinietaCategorySensor(CarRovinietaBaseSensor):
    """Clasă pentru rovinietă category senzor."""

    _attr_name = "Categorie rovinietă"
    _attr_icon = "mdi:car-info"

    def __init__(self, entry, coordinator, car_vehicle, rovinieta_vehicle_id: int) -> None:
        super().__init__(entry, coordinator, car_vehicle, rovinieta_vehicle_id)
        slug = slugify_plate(car_vehicle.get(CONF_LICENSE_PLATE, self._vehicle_id))
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{slug}_rovinieta_category"

    @property
    def native_value(self):
        vehicle = self.rovinieta_vehicle
        return vehicle.category_vignette_title if vehicle else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.common_attributes


class CarRovinietaPeriodSensor(CarRovinietaBaseSensor):
    """Clasă pentru rovinietă period senzor."""

    _attr_name = "Perioadă rovinietă"
    _attr_icon = "mdi:calendar-range"

    def __init__(self, entry, coordinator, car_vehicle, rovinieta_vehicle_id: int) -> None:
        super().__init__(entry, coordinator, car_vehicle, rovinieta_vehicle_id)
        slug = slugify_plate(car_vehicle.get(CONF_LICENSE_PLATE, self._vehicle_id))
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{slug}_rovinieta_period"

    @property
    def native_value(self):
        vehicle = self.rovinieta_vehicle
        if vehicle is None or not vehicle.active_vignette:
            return None
        return vehicle.active_vignette.get("oProdPeriodName")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.common_attributes
