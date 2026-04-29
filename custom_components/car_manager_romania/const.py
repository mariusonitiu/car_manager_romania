"""Constants for Car Manager România."""

from __future__ import annotations

DOMAIN = "car_manager_romania"

DEFAULT_NAME = "Car Manager România"
VERSION = "0.4.0"

PLATFORMS: list[str] = ["sensor", "number", "date"]

ATTR_INTEGRATION_VERSION = "integration_version"

CONF_VEHICLES = "vehicles"

CONF_NAME = "name"
CONF_LICENSE_PLATE = "license_plate"
CONF_VIN = "vin"
CONF_KM = "km"

# Câmpuri existente pentru revizia generală.
# Le păstrăm pentru compatibilitate cu datele și entitățile deja create.
CONF_LAST_SERVICE_KM = "last_service_km"
CONF_SERVICE_INTERVAL_KM = "service_interval_km"
CONF_SERVICE_INTERVAL_DAYS = "service_interval_days"
CONF_LAST_SERVICE_DATE = "last_service_date"

# Model generic pentru mentenanța mecanică.
MAINTENANCE_TYPE_SERVICE = "service"
MAINTENANCE_TYPE_GEARBOX_OIL = "gearbox_oil"
MAINTENANCE_TYPE_TIMING_BELT = "timing_belt"
MAINTENANCE_TYPE_BRAKE_FLUID = "brake_fluid"
MAINTENANCE_TYPE_COOLANT = "coolant"

MAINTENANCE_TYPES: dict[str, str] = {
    MAINTENANCE_TYPE_SERVICE: "Revizie generală",
    MAINTENANCE_TYPE_GEARBOX_OIL: "Ulei cutie viteze",
    MAINTENANCE_TYPE_TIMING_BELT: "Distribuție",
    MAINTENANCE_TYPE_BRAKE_FLUID: "Lichid frână",
    MAINTENANCE_TYPE_COOLANT: "Lichid antigel",
}

MAINTENANCE_LAST_KM = "last_km"
MAINTENANCE_LAST_DATE = "last_date"
MAINTENANCE_INTERVAL_KM = "interval_km"
MAINTENANCE_INTERVAL_DAYS = "interval_days"

MAINTENANCE_STATUS_UNKNOWN = "necunoscut"
MAINTENANCE_STATUS_OK = "ok"
MAINTENANCE_STATUS_SOON = "în curând"
MAINTENANCE_STATUS_OVERDUE = "depășit"

MAINTENANCE_SOON_KM_THRESHOLD = 1000
MAINTENANCE_SOON_DAYS_THRESHOLD = 30