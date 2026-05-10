"""Sensor platform for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .device import build_vehicle_device_info

from . import CarManagerConfigEntry
from .const import (
    ATTR_INTEGRATION_VERSION,
    CONF_KM,
    CONF_LICENSE_PLATE,
    LEGAL_END_DATE,
    LEGAL_OPTION_IGNORED,
    LEGAL_START_DATE,
    LEGAL_TYPES,
    LEGAL_STATUS_EXPIRED,
    LEGAL_STATUS_SOON,
    LEGAL_STATUS_UNKNOWN,
    LEGAL_STATUS_VALID,
    LEGAL_TYPE_CASCO,
    CONF_NAME,
    CONF_REMOVED,
    CONF_VEHICLE_ID,
    CONF_VIN,
    DOMAIN,
    MAINTENANCE_INTERVAL_DAYS,
    MAINTENANCE_INTERVAL_KM,
    MAINTENANCE_LAST_DATE,
    MAINTENANCE_LAST_KM,
    MAINTENANCE_TYPES,
    MAINTENANCE_TIME_ONLY_TYPES,
    MAINTENANCE_TYPE_SERVICE,
    MAINTENANCE_STATUS_OK,
    MAINTENANCE_STATUS_OVERDUE,
    MAINTENANCE_STATUS_SOON,
    SIGNAL_VEHICLES_UPDATED,
    VERSION,
)
from .legal import legal_days_remaining, legal_status, get_legal_value, is_legal_ignored
from .maintenance import (
    calculate_days_remaining,
    calculate_km_remaining,
    calculate_maintenance_status,
    get_maintenance_value,
    maintenance_remaining_values,
    maintenance_status,
)
from .costs import annual_history_total, expense_total, upcoming_expense_items
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
        entities.append(CarVehicleUpcomingExpensesSensor(entry, vehicle, 30))
        entities.append(CarVehicleUpcomingExpensesSensor(entry, vehicle, 90))
        entities.append(CarVehicleAnnualCostsSensor(entry, vehicle))

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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes."""

        all_vehicles = getattr(self._entry.runtime_data, "all_vehicles", self._entry.runtime_data.vehicles)
        inactive_vehicles: list[dict[str, Any]] = []
        for vehicle in all_vehicles:
            if not isinstance(vehicle, dict) or not bool(vehicle.get(CONF_REMOVED)):
                continue

            inactive_vehicles.append(
                {
                    CONF_VEHICLE_ID: vehicle.get(CONF_VEHICLE_ID, ""),
                    CONF_NAME: vehicle.get(CONF_NAME, "Autovehicul"),
                    CONF_LICENSE_PLATE: vehicle.get(CONF_LICENSE_PLATE, ""),
                    CONF_VIN: vehicle.get(CONF_VIN, ""),
                    CONF_KM: vehicle.get(CONF_KM, 0),
                }
            )

        return {
            ATTR_INTEGRATION_VERSION: VERSION,
            "inactive_vehicles": inactive_vehicles,
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

    async def async_added_to_hass(self) -> None:
        """Subscribe to vehicle data updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VEHICLES_UPDATED,
                self._handle_vehicles_updated,
            )
        )

    def _handle_vehicles_updated(self, vehicles: list[dict[str, Any]]) -> None:
        """Refresh cached vehicle data and update the entity state."""

        for vehicle in vehicles:
            if vehicle.get("vehicle_id") == self._vehicle_id:
                self._vehicle = vehicle
                self.async_write_ha_state()
                break

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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return vehicle attributes."""

        attributes = {
            CONF_VEHICLE_ID: self._vehicle_id,
            CONF_NAME: self._vehicle.get(CONF_NAME, ""),
            CONF_LICENSE_PLATE: self._vehicle.get(CONF_LICENSE_PLATE, ""),
        }

        if self._vehicle.get(CONF_VIN):
            attributes[CONF_VIN] = self._vehicle[CONF_VIN]

        records = getattr(self._entry.runtime_data.service_history_store, "_records", [])
        vehicle_records: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            if str(record.get(CONF_VEHICLE_ID, "")) != self._vehicle_id:
                continue
            vehicle_records.append(
                {
                    "record_id": record.get("record_id", ""),
                    "record_type": record.get("record_type", "custom"),
                    "record_type_label": _service_history_type_label(str(record.get("record_type", "custom"))),
                    "date": record.get("date", ""),
                    CONF_KM: record.get(CONF_KM, 0),
                    "title": record.get("title", ""),
                    "service_name": record.get("service_name", ""),
                    "cost": record.get("cost", 0),
                    "invoice_number": record.get("invoice_number", ""),
                    "notes": record.get("notes", ""),
                    "update_maintenance": bool(record.get("update_maintenance", False)),
                    "restored": bool(record.get("restored", False)),
                    "restored_at": record.get("restored_at", ""),
                    "updated_at": record.get("updated_at", ""),
                }
            )

        vehicle_records.sort(key=lambda item: str(item.get("date", "")), reverse=True)
        attributes["service_history"] = vehicle_records[:10]
        attributes.update(_vehicle_overall_summary(self._vehicle))

        return attributes


class CarVehicleUpcomingExpensesSensor(CarVehicleBaseSensor):
    """Upcoming expenses total sensor."""

    _attr_icon = "mdi:cash-clock"
    _attr_native_unit_of_measurement = "RON"

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
        horizon_days: int,
    ) -> None:
        """Initialize upcoming expenses sensor."""

        super().__init__(entry, vehicle)
        self._horizon_days = horizon_days
        self._attr_name = f"Cheltuieli următoarele {horizon_days} zile"
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._vehicle_id}_upcoming_expenses_{horizon_days}_days"
        )

    @property
    def native_value(self) -> float:
        """Return total upcoming expenses."""

        return expense_total(
            upcoming_expense_items(
                self._entry,
                self._vehicle,
                self._horizon_days,
                only_with_cost=True,
            )
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return upcoming expense details."""

        items = upcoming_expense_items(
            self._entry,
            self._vehicle,
            self._horizon_days,
            only_with_cost=False,
        )
        items_with_cost = [item for item in items if float(item.get("cost", 0) or 0) > 0]
        return {
            "horizon_days": self._horizon_days,
            "currency": "RON",
            "total_cost": expense_total(items_with_cost),
            "items": items,
            "items_with_cost": items_with_cost,
        }


class CarVehicleAnnualCostsSensor(CarVehicleBaseSensor):
    """Current-year historic costs sensor."""

    _attr_name = "Costuri anul curent"
    _attr_icon = "mdi:cash-multiple"
    _attr_native_unit_of_measurement = "RON"

    def __init__(
        self,
        entry: CarManagerConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Initialize annual costs sensor."""

        super().__init__(entry, vehicle)
        self._attr_unique_id = f"{entry.entry_id}_{self._vehicle_id}_annual_costs_current_year"

    @property
    def native_value(self) -> float:
        """Return current-year historic costs."""

        return annual_history_total(self._entry, self._vehicle)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return annual cost metadata."""

        from datetime import date as dt_date

        return {
            "year": dt_date.today().year,
            "currency": "RON",
        }


def _vehicle_overall_summary(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Build an aggregated health summary for one vehicle."""

    critical_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []
    ok_items: list[dict[str, Any]] = []
    unknown_items: list[dict[str, Any]] = []

    for maintenance_type, label in MAINTENANCE_TYPES.items():
        status = maintenance_status(vehicle, maintenance_type)
        km_remaining, days_remaining = maintenance_remaining_values(vehicle, maintenance_type)
        item = _build_overall_item(
            category="maintenance",
            key=maintenance_type,
            label=label,
            status=status,
            days_remaining=days_remaining,
            km_remaining=km_remaining,
        )

        if status == MAINTENANCE_STATUS_OVERDUE:
            critical_items.append(item)
        elif status == MAINTENANCE_STATUS_SOON:
            warning_items.append(item)
        elif status == MAINTENANCE_STATUS_OK:
            ok_items.append(item)
        else:
            unknown_items.append(item)

    for legal_type, label in LEGAL_TYPES.items():
        if legal_type == LEGAL_TYPE_CASCO and is_legal_ignored(vehicle, legal_type):
            continue

        status = legal_status(vehicle, legal_type)
        days_remaining = legal_days_remaining(vehicle, legal_type)
        item = _build_overall_item(
            category="legal",
            key=legal_type,
            label=label,
            status=status,
            days_remaining=days_remaining,
            km_remaining=None,
        )

        if legal_type == LEGAL_TYPE_CASCO and status == LEGAL_STATUS_UNKNOWN:
            item["summary"] = "neconfigurat"
            item["can_ignore"] = True
            critical_items.append(item)
        elif status == LEGAL_STATUS_EXPIRED:
            critical_items.append(item)
        elif status == LEGAL_STATUS_SOON:
            warning_items.append(item)
        elif status == LEGAL_STATUS_VALID:
            ok_items.append(item)
        else:
            unknown_items.append(item)

    if critical_items:
        overall_status = "critic"
        overall_status_label = "Critic"
    elif warning_items:
        overall_status = "atenție"
        overall_status_label = "Atenție"
    elif unknown_items:
        overall_status = "atenție"
        overall_status_label = "Atenție"
    else:
        overall_status = "ok"
        overall_status_label = "OK"

    return {
        "overall_status": overall_status,
        "overall_status_label": overall_status_label,
        "critical_items": critical_items,
        "warning_items": warning_items + unknown_items,
        "ok_items": ok_items,
        "unknown_items": unknown_items,
        "critical_count": len(critical_items),
        "warning_count": len(warning_items) + len(unknown_items),
        "ok_count": len(ok_items),
    }


def _build_overall_item(
    *,
    category: str,
    key: str,
    label: str,
    status: str,
    days_remaining: int | None,
    km_remaining: int | None,
) -> dict[str, Any]:
    """Build one compact aggregated summary item."""

    parts: list[str] = [status]
    if days_remaining is not None:
        parts.append(f"{days_remaining} zile")
    if km_remaining is not None:
        parts.append(f"{km_remaining} km")

    return {
        "category": category,
        "key": key,
        "label": label,
        "status": status,
        "days_remaining": days_remaining,
        "km_remaining": km_remaining,
        "summary": " · ".join(parts),
    }


def _service_history_type_label(record_type: str) -> str:
    """Return a human label for a service history record type."""

    if record_type in MAINTENANCE_TYPES:
        return MAINTENANCE_TYPES[record_type]

    return {
        "rca": "RCA",
        "casco": "CASCO",
        "itp": "ITP",
        "rovinieta": "Rovinietă",
        "custom": "Altă intervenție",
    }.get(record_type, record_type or "Intervenție")


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
            "ignored": bool(get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_OPTION_IGNORED,
            )),
            "legal_ignored": bool(get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_OPTION_IGNORED,
            )),
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
            "ignored": bool(get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_OPTION_IGNORED,
            )),
            "legal_ignored": bool(get_legal_value(
                self._vehicle,
                self._legal_type,
                LEGAL_OPTION_IGNORED,
            )),
        }
