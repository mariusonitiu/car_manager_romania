"""Constants for Car Manager România."""

from __future__ import annotations

DOMAIN = "car_manager_romania"

DEFAULT_NAME = "Car Manager România"
VERSION = "0.3.0"

PLATFORMS: list[str] = ["sensor", "number", "date"]

ATTR_INTEGRATION_VERSION = "integration_version"

CONF_VEHICLES = "vehicles"

CONF_NAME = "name"
CONF_LICENSE_PLATE = "license_plate"
CONF_VIN = "vin"
CONF_KM = "km"

# Revizie
CONF_LAST_SERVICE_KM = "last_service_km"
CONF_SERVICE_INTERVAL_KM = "service_interval_km"
CONF_SERVICE_INTERVAL_DAYS = "service_interval_days"
CONF_LAST_SERVICE_DATE = "last_service_date"