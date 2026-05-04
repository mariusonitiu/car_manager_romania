"""Constants for Car Manager România."""

from __future__ import annotations

DOMAIN = "car_manager_romania"

DEFAULT_NAME = "Car Manager România"
VERSION = "0.5.2"

PLATFORMS: list[str] = ["sensor", "number", "date", "text"]

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

# Jaloane urmărite doar după timp. Pentru acestea nu generăm câmpuri/senzori de km,
# deoarece kilometriajul nu este criteriul relevant de înlocuire.
MAINTENANCE_TIME_ONLY_TYPES: set[str] = {
    MAINTENANCE_TYPE_BRAKE_FLUID,
    MAINTENANCE_TYPE_COOLANT,
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

# Defaulturi inițiale, aplicate doar când valoarea lipsește sau este 0.
# Nu suprascriu valori introduse deja de utilizator.
DEFAULT_MAINTENANCE_INTERVALS: dict[str, dict[str, int]] = {
    MAINTENANCE_TYPE_SERVICE: {
        MAINTENANCE_INTERVAL_KM: 12_000,
        MAINTENANCE_INTERVAL_DAYS: 365,
    },
    MAINTENANCE_TYPE_GEARBOX_OIL: {
        MAINTENANCE_INTERVAL_KM: 90_000,
        MAINTENANCE_INTERVAL_DAYS: 1825,
    },
    MAINTENANCE_TYPE_TIMING_BELT: {
        MAINTENANCE_INTERVAL_KM: 100_000,
        MAINTENANCE_INTERVAL_DAYS: 1825,
    },
    MAINTENANCE_TYPE_BRAKE_FLUID: {
        MAINTENANCE_INTERVAL_KM: 0,
        MAINTENANCE_INTERVAL_DAYS: 730,
    },
    MAINTENANCE_TYPE_COOLANT: {
        MAINTENANCE_INTERVAL_KM: 0,
        MAINTENANCE_INTERVAL_DAYS: 1460,
    },
}

# Consumabile / specificații tehnice editabile.
CONF_CONSUMABLES = "consumables"

CONSUMABLE_ENGINE_OIL = "engine_oil"
CONSUMABLE_ENGINE_OIL_CAPACITY = "engine_oil_capacity"
CONSUMABLE_OIL_FILTER = "oil_filter"
CONSUMABLE_AIR_FILTER = "air_filter"
CONSUMABLE_CABIN_FILTER = "cabin_filter"
CONSUMABLE_FUEL_FILTER = "fuel_filter"
CONSUMABLE_GEARBOX_OIL = "gearbox_oil"
CONSUMABLE_BRAKE_FLUID = "brake_fluid"
CONSUMABLE_COOLANT = "coolant"
CONSUMABLE_TIMING_KIT = "timing_kit"

CONSUMABLE_TYPES: dict[str, str] = {
    CONSUMABLE_ENGINE_OIL: "Ulei motor",
    CONSUMABLE_ENGINE_OIL_CAPACITY: "Cantitate ulei motor",
    CONSUMABLE_OIL_FILTER: "Filtru ulei",
    CONSUMABLE_AIR_FILTER: "Filtru aer",
    CONSUMABLE_CABIN_FILTER: "Filtru habitaclu",
    CONSUMABLE_FUEL_FILTER: "Filtru combustibil",
    CONSUMABLE_GEARBOX_OIL: "Ulei cutie viteze",
    CONSUMABLE_BRAKE_FLUID: "Lichid frână",
    CONSUMABLE_COOLANT: "Lichid antigel",
    CONSUMABLE_TIMING_KIT: "Kit distribuție",
}

DEFAULT_CONSUMABLE_VALUES: dict[str, str] = {
    CONSUMABLE_ENGINE_OIL: "",
    CONSUMABLE_ENGINE_OIL_CAPACITY: "",
    CONSUMABLE_OIL_FILTER: "",
    CONSUMABLE_AIR_FILTER: "",
    CONSUMABLE_CABIN_FILTER: "",
    CONSUMABLE_FUEL_FILTER: "",
    CONSUMABLE_GEARBOX_OIL: "",
    CONSUMABLE_BRAKE_FLUID: "DOT 4",
    CONSUMABLE_COOLANT: "",
    CONSUMABLE_TIMING_KIT: "",
}

STORAGE_KEY_NOTIFICATIONS = f"{DOMAIN}_notifications"
STORAGE_VERSION_NOTIFICATIONS = 1
