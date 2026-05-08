"""Sensor platform for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .device import build_vehicle_device_info

from . import CarManagerConfigEntry
from .const import (
    ATTR_INTEGRATION_VERSION,
    CONF_KM,
    CONF_LICENSE_PLATE,
    LEGAL_END_DATE,
    LEGAL_START_DATE,
    LEGAL_TYPES,
    CONF_NAME,
    CONF_VIN,
    DOMAIN,
    MAINTENANCE_INTERVAL_DAYS,
    MAINTENANCE_INTERVAL_KM,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_LAST_KM,
    MAINTENANCE_TYPES,
    MAINTENANCE_TIME_ONLY_TYPES,
    MAINTENANCE_TYPE_SERVICE,
    VERSION,
)
from .legal import legal_days_remaining, legal_status, get_legal_value
from .maintenance import (
    calculate_days_remaining,
    calculate_km_remaining,
    calculate_maintenance_status,
    get_maintenance_value,
)
from .rovinieta.sensor import async_setup_rovinieta_sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CarManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Car Manager România sensors."""

    entities: list[SensorEntity] = [
        CarManagerStatusSensor(entry),
        CarManagerVehicleCountSensor(entry),
    ]

    for vehicle in entry.runtime_data.vehicles:
        entities.append(CarVehicleKmSensor(entry, vehicle))
        entities.append(CarVehicleStatusSensor(entry, vehicle))

        for maintenance_type, label in MAINTENANCE_TYPES.items():
            if maintenance_type not in MAINTENANCE_TIME_ONLY_TYPES:
                entities.append(
                    CarVehicleMaintenanceKmRemainingSensor(
                        entry,
                        vehicle,
                        maintenance_type,
                        label,
                    )
                )

            entities.append(
                CarVehicleMaintenanceDaysRemainingSensor(
                    entry,
                    vehicle,
                    maintenance_type,
                    label,
                )
            )
            entities.append(
                CarVehicleMaintenanceStatusSensor(
                    entry,
                    vehicle,
                    maintenance_type,
                    label,
                )
            )

        for legal_type, label in LEGAL_TYPES.items():
            entities.extend(
                [
                    CarVehicleLegalDaysRemainingSensor(entry, vehicle, legal_type, label),
                    CarVehicleLegalStatusSensor(entry, vehicle, legal_type, label),
                ]
            )

    async_add_entities(entities)

    await async_setup_rovinieta_sensors(hass, entry, async_add_entities)


class CarManagerBaseSensor(SensorEntity):
    """Base sensor for Car Manager România."""

    _attr_has_entity_name = True

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize base sensor."""

        self._entry = entry
        self._entry_id = entry.entry_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return hub device information."""

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._entry.data.get(CONF_NAME, "Car Manager România"),
            manufacturer="Car Manager România",
            model="Hub",
            sw_version=VERSION,
        )


class CarManagerStatusSensor(CarManagerBaseSensor):
    """Status sensor for Car Manager România."""

    _attr_name = "Status"
    _attr_icon = "mdi:car-cog"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize status sensor."""

        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str:
        """Return status."""

        return "activ"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return attributes."""

        return {
            ATTR_INTEGRATION_VERSION: VERSION,
        }


class CarManagerVehicleCountSensor(CarManagerBaseSensor):
    """Vehicle count sensor for Car Manager România."""

    _attr_name = "Număr autovehicule"
    _attr_icon = "mdi:car-multiple"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CarManagerConfigEntry) -> None:
        """Initialize vehicle count sensor."""

        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_vehicle_count"

    @property
    def native_value(self) -> int:
        """Return vehicle count."""

        return len(self._entry.runtime_data.vehicles)


class CarVehicleBaseSensor(SensorEntity):
    """Base vehicle sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize vehicle base sensor."""

        self._entry = entry
        self._vehicle = vehicle
        self._vehicle_id = vehicle["vehicle_id"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return vehicle device information."""

        return build_vehicle_device_info(
            self._vehicle,
        )


class CarVehicleKmSensor(CarVehicleBaseSensor):
    """Vehicle kilometers sensor."""

    _attr_name = "Kilometri"
    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize vehicle kilometers sensor."""

        super().__init__(entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_km"

    @property
    def native_value(self) -> int:
        """Return current kilometers."""

        return int(self._vehicle.get(CONF_KM, 0) or 0)


class CarVehicleStatusSensor(CarVehicleBaseSensor):
    """Vehicle status sensor."""

    _attr_name = "Status"
    _attr_icon = "mdi:car-info"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize vehicle status sensor."""

        super().__init__(entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_status"

    @property
    def native_value(self) -> str:
        """Return vehicle status."""

        return "configurat"

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return vehicle attributes."""

        attributes = {
            CONF_NAME: self._vehicle.get(CONF_NAME, ""),
            CONF_LICENSE_PLATE: self._vehicle.get(CONF_LICENSE_PLATE, ""),
        }

        if self._vehicle.get(CONF_VIN):
            attributes[CONF_VIN] = self._vehicle[CONF_VIN]

        return attributes


class CarVehicleMaintenanceBaseSensor(CarVehicleBaseSensor):
    """Base maintenance sensor."""

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        label: str,
    ) -> None:
        """Initialize maintenance base sensor."""

        super().__init__(entry, vehicle)
        self._maintenance_type = maintenance_type
        self._label = label

    def _current_km(self) -> int:
        """Return current vehicle kilometers."""

        return int(self._vehicle.get(CONF_KM, 0) or 0)

    def _last_km(self) -> int | None:
        """Return last maintenance kilometers."""

        value = get_maintenance_value(
            self._vehicle,
            self._maintenance_type,
            MAINTENANCE_LAST_KM,
        )

        if value is None:
            return None

        return int(value or 0)

    def _interval_km(self) -> int | None:
        """Return maintenance interval kilometers."""

        value = get_maintenance_value(
            self._vehicle,
            self._maintenance_type,
            MAINTENANCE_INTERVAL_KM,
        )

        if value is None:
            return None

        return int(value or 0)

    def _last_date(self) -> Any:
        """Return last maintenance date."""

        return get_maintenance_value(
            self._vehicle,
            self._maintenance_type,
            MAINTENANCE_LAST_DATE,
        )

    def _interval_days(self) -> int | None:
        """Return maintenance interval days."""

        value = get_maintenance_value(
            self._vehicle,
            self._maintenance_type,
            MAINTENANCE_INTERVAL_DAYS,
        )

        if value is None:
            return None

        return int(value or 0)

    def _km_remaining(self) -> int | None:
        """Return remaining kilometers."""

        return calculate_km_remaining(
            self._current_km(),
            self._last_km(),
            self._interval_km(),
        )

    def _days_remaining(self) -> int | None:
        """Return remaining days."""

        return calculate_days_remaining(
            self._last_date(),
            self._interval_days(),
        )

    def _unique_suffix(self, suffix: str) -> str:
        """Return unique suffix, preserving old service entity IDs."""

        if self._maintenance_type == MAINTENANCE_TYPE_SERVICE:
            service_suffix_map = {
                "km_remaining": "service_km_remaining",
                "days_remaining": "service_days_remaining",
                "status": "service_status",
            }
            return service_suffix_map[suffix]

        return f"maintenance_{self._maintenance_type}_{suffix}"


class CarVehicleMaintenanceKmRemainingSensor(CarVehicleMaintenanceBaseSensor):
    """Maintenance remaining kilometers sensor."""

    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        label: str,
    ) -> None:
        """Initialize maintenance remaining kilometers sensor."""

        super().__init__(entry, vehicle, maintenance_type, label)

        if maintenance_type == MAINTENANCE_TYPE_SERVICE:
            self._attr_name = "Km rămași până la revizie"
        else:
            self._attr_name = f"{label} - km rămași"

        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_{self._unique_suffix('km_remaining')}"
        )

    @property
    def native_value(self) -> int | None:
        """Return remaining kilometers."""

        return self._km_remaining()


class CarVehicleMaintenanceDaysRemainingSensor(CarVehicleMaintenanceBaseSensor):
    """Maintenance remaining days sensor."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        label: str,
    ) -> None:
        """Initialize maintenance remaining days sensor."""

        super().__init__(entry, vehicle, maintenance_type, label)

        if maintenance_type == MAINTENANCE_TYPE_SERVICE:
            self._attr_name = "Zile rămase până la revizie"
        else:
            self._attr_name = f"{label} - zile rămase"

        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_{self._unique_suffix('days_remaining')}"
        )

    @property
    def native_value(self) -> int | None:
        """Return remaining days."""

        return self._days_remaining()


class CarVehicleMaintenanceStatusSensor(CarVehicleMaintenanceBaseSensor):
    """Maintenance status sensor."""

    _attr_icon = "mdi:wrench-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        maintenance_type: str,
        label: str,
    ) -> None:
        """Initialize maintenance status sensor."""

        super().__init__(entry, vehicle, maintenance_type, label)

        if maintenance_type == MAINTENANCE_TYPE_SERVICE:
            self._attr_name = "Status revizie"
        else:
            self._attr_name = f"{label} - status"

        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_{self._unique_suffix('status')}"
        )

    @property
    def native_value(self) -> str:
        """Return maintenance status."""

        return calculate_maintenance_status(
            self._km_remaining(),
            self._days_remaining(),
        )

class CarVehicleLegalDaysRemainingSensor(CarVehicleBaseSensor):
    """Legal term remaining days sensor."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        legal_type: str,
        label: str,
    ) -> None:
        """Initialize legal term remaining days sensor."""

        super().__init__(entry, vehicle)
        self._legal_type = legal_type
        self._label = label
        self._attr_name = f"Zile rămase până la {label}"
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_{legal_type}_days_remaining"
        )

    @property
    def native_value(self) -> int | None:
        """Return remaining days until legal term expiration."""

        return legal_days_remaining(self._vehicle, self._legal_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return legal term date attributes."""

        return {
            "tip": self._label,
            "incepe_la": get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_START_DATE,
            ),
            "expira_la": get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_END_DATE,
            ),
        }


class CarVehicleLegalStatusSensor(CarVehicleBaseSensor):
    """Legal term status sensor."""

    _attr_icon = "mdi:shield-car"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        legal_type: str,
        label: str,
    ) -> None:
        """Initialize legal term status sensor."""

        super().__init__(entry, vehicle)
        self._legal_type = legal_type
        self._label = label
        self._attr_name = f"Status {label}"
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_{legal_type}_status"

    @property
    def native_value(self) -> str:
        """Return calculated legal term status."""

        return legal_status(self._vehicle, self._legal_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return legal term attributes without external lookups."""

        return {
            "tip": self._label,
            "incepe_la": get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_START_DATE,
            ),
            "expira_la": get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_END_DATE,
            ),
            "zile_ramase": legal_days_remaining(self._vehicle, self._legal_type),
        }
