"""Constants for Car Manager România."""

from __future__ import annotations

DOMAIN = "car_manager_romania"

DEFAULT_NAME = "Car Manager România"
VERSION = "1.0.61b3"

PLATFORMS: list[str] = ["sensor", "number", "date", "text", "button"]

ATTR_INTEGRATION_VERSION = "1.0.61b3"

SIGNAL_VEHICLES_UPDATED = f"{DOMAIN}_vehicles_updated"
SIGNAL_LICENSE_UPDATED = f"{DOMAIN}_license_updated"

CONF_VEHICLES = "vehicles"


# Licențiere Car Manager România.
CONF_LICENSE_KEY = "cheie_licenta"
CONF_LICENSE_USER = "utilizator"
DATE_VERIFICARE_LICENTA = "date_verificare_licenta"
URL_API_LICENTA = "https://license-api.marius-onitiu.workers.dev"
DEFAULT_LICENSE_GRACE_DAYS = 7

LICENSE_STATUS_ACTIVE = "active"
LICENSE_STATUS_TRIAL = "trial"
LICENSE_STATUS_EXPIRED = "expired"
LICENSE_STATUS_INVALID = "invalid"
LICENSE_STATUS_REVOKED = "revoked"
LICENSE_STATUS_INVALID_PRODUCT = "invalid_product"
LICENSE_STATUS_ACTIVATION_LIMIT = "activation_limit"
LICENSE_STATUS_UNKNOWN = "unknown"

SERVICE_ADD_VEHICLE = "add_vehicle"
SERVICE_REMOVE_VEHICLE = "remove_vehicle"
SERVICE_RESTORE_VEHICLE = "restore_vehicle"
SERVICE_RESTORE_ALL_VEHICLES = "restore_all_vehicles"
SERVICE_ADD_SERVICE_RECORD = "add_service_record"
SERVICE_RESTORE_SERVICE_RECORD = "restore_service_record"
SERVICE_RESTORE_LAST_SERVICE_RECORD = "restore_last_service_record"
SERVICE_DELETE_SERVICE_RECORD = "delete_service_record"
SERVICE_UPDATE_SERVICE_RECORD = "update_service_record"
SERVICE_EXPORT_DATA = "export_data"
SERVICE_VALIDATE_BACKUP = "validate_backup"
SERVICE_IMPORT_DATA = "import_data"
SERVICE_SET_LEGAL_OPTION = "set_legal_option"
SERVICE_CLEANUP_ORPHAN_ENTITIES = "cleanup_orphan_entities"
SERVICE_REFRESH_LICENSE_STATUS = "refresh_license_status"
SERVICE_ADD_FUEL_RECEIPT = "add_fuel_receipt"
SERVICE_UPDATE_FUEL_RECEIPT = "update_fuel_receipt"
SERVICE_DELETE_FUEL_RECEIPT = "delete_fuel_receipt"

SERVICE_ADD_TIRE_SET = "add_tire_set"
SERVICE_UPDATE_TIRE_SET = "update_tire_set"
SERVICE_DELETE_TIRE_SET = "delete_tire_set"
SERVICE_ADD_EQUIPMENT_ITEM = "add_equipment_item"
SERVICE_UPDATE_EQUIPMENT_ITEM = "update_equipment_item"
SERVICE_DELETE_EQUIPMENT_ITEM = "delete_equipment_item"
SERVICE_ADD_BATTERY = "add_battery"
SERVICE_UPDATE_BATTERY = "update_battery"
SERVICE_DELETE_BATTERY = "delete_battery"

TIRE_TYPE_SUMMER = "summer"
TIRE_TYPE_WINTER = "winter"
TIRE_TYPE_ALL_SEASON = "all_season"

TIRE_TYPES: dict[str, str] = {
    TIRE_TYPE_SUMMER: "Vară",
    TIRE_TYPE_WINTER: "Iarnă",
    TIRE_TYPE_ALL_SEASON: "All season",
}

TIRE_MOUNT_TYPE_TIRES_ONLY = "tires_only"
TIRE_MOUNT_TYPE_ON_RIMS = "on_rims"

TIRE_MOUNT_TYPES: dict[str, str] = {
    TIRE_MOUNT_TYPE_TIRES_ONLY: "Doar cauciucuri",
    TIRE_MOUNT_TYPE_ON_RIMS: "Pe jante",
}

CONF_VEHICLE_ID = "vehicle_id"
CONF_REMOVED = "removed"

CONF_NAME = "name"
CONF_LICENSE_PLATE = "license_plate"
CONF_VIN = "vin"
CONF_KM = "km"
CONF_FUEL_PROFILE = "fuel_profile"

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

COST_AMOUNT = "cost"

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


# Profil combustibil / motorizare și alimentări.
FUEL_PROFILE_GASOLINE = "gasoline"
FUEL_PROFILE_DIESEL = "diesel"
FUEL_PROFILE_LPG = "lpg"
FUEL_PROFILE_ELECTRIC = "electric"
FUEL_PROFILE_HYBRID_GASOLINE = "hybrid_gasoline"
FUEL_PROFILE_HYBRID_DIESEL = "hybrid_diesel"
FUEL_PROFILE_PHEV_GASOLINE = "phev_gasoline"
FUEL_PROFILE_PHEV_DIESEL = "phev_diesel"

FUEL_PROFILES: dict[str, str] = {
    FUEL_PROFILE_GASOLINE: "Benzină",
    FUEL_PROFILE_DIESEL: "Motorină",
    FUEL_PROFILE_LPG: "GPL",
    FUEL_PROFILE_ELECTRIC: "Electric",
    FUEL_PROFILE_HYBRID_GASOLINE: "Hibrid benzină",
    FUEL_PROFILE_HYBRID_DIESEL: "Hibrid motorină",
    FUEL_PROFILE_PHEV_GASOLINE: "Plug-in hybrid benzină",
    FUEL_PROFILE_PHEV_DIESEL: "Plug-in hybrid motorină",
}

FUEL_TYPE_GASOLINE_STANDARD = "gasoline_standard"
FUEL_TYPE_GASOLINE_PREMIUM = "gasoline_premium"
FUEL_TYPE_DIESEL_STANDARD = "diesel_standard"
FUEL_TYPE_DIESEL_PREMIUM = "diesel_premium"
FUEL_TYPE_LPG = "lpg"
FUEL_TYPE_ELECTRIC_CHARGE = "electric_charge"

FUEL_TYPES: dict[str, str] = {
    FUEL_TYPE_GASOLINE_STANDARD: "Benzină standard",
    FUEL_TYPE_GASOLINE_PREMIUM: "Benzină premium",
    FUEL_TYPE_DIESEL_STANDARD: "Motorină standard",
    FUEL_TYPE_DIESEL_PREMIUM: "Motorină premium",
    FUEL_TYPE_LPG: "GPL",
    FUEL_TYPE_ELECTRIC_CHARGE: "Încărcare electrică",
}

FUEL_TYPES_BY_PROFILE: dict[str, list[str]] = {
    FUEL_PROFILE_GASOLINE: [FUEL_TYPE_GASOLINE_STANDARD, FUEL_TYPE_GASOLINE_PREMIUM],
    FUEL_PROFILE_DIESEL: [FUEL_TYPE_DIESEL_STANDARD, FUEL_TYPE_DIESEL_PREMIUM],
    FUEL_PROFILE_LPG: [FUEL_TYPE_LPG, FUEL_TYPE_GASOLINE_STANDARD, FUEL_TYPE_GASOLINE_PREMIUM],
    FUEL_PROFILE_ELECTRIC: [FUEL_TYPE_ELECTRIC_CHARGE],
    FUEL_PROFILE_HYBRID_GASOLINE: [FUEL_TYPE_GASOLINE_STANDARD, FUEL_TYPE_GASOLINE_PREMIUM],
    FUEL_PROFILE_HYBRID_DIESEL: [FUEL_TYPE_DIESEL_STANDARD, FUEL_TYPE_DIESEL_PREMIUM],
    FUEL_PROFILE_PHEV_GASOLINE: [FUEL_TYPE_GASOLINE_STANDARD, FUEL_TYPE_GASOLINE_PREMIUM, FUEL_TYPE_ELECTRIC_CHARGE],
    FUEL_PROFILE_PHEV_DIESEL: [FUEL_TYPE_DIESEL_STANDARD, FUEL_TYPE_DIESEL_PREMIUM, FUEL_TYPE_ELECTRIC_CHARGE],
}

FUEL_LIQUID_TYPES: set[str] = {
    FUEL_TYPE_GASOLINE_STANDARD,
    FUEL_TYPE_GASOLINE_PREMIUM,
    FUEL_TYPE_DIESEL_STANDARD,
    FUEL_TYPE_DIESEL_PREMIUM,
    FUEL_TYPE_LPG,
}

STORAGE_KEY_NOTIFICATIONS = f"{DOMAIN}_notifications"
STORAGE_VERSION_NOTIFICATIONS = 1

STORAGE_KEY_LICENSE = f"{DOMAIN}_licenta"
STORAGE_VERSION_LICENSE = 1

STORAGE_KEY_VEHICLES = f"{DOMAIN}_vehicles"
STORAGE_VERSION_VEHICLES = 1

STORAGE_KEY_SERVICE_HISTORY = f"{DOMAIN}_service_history"
STORAGE_VERSION_SERVICE_HISTORY = 1

STORAGE_KEY_FUEL_RECEIPTS = f"{DOMAIN}_fuel_receipts"
STORAGE_VERSION_FUEL_RECEIPTS = 1

STORAGE_KEY_TIRE_SETS = f"{DOMAIN}_tire_sets"
STORAGE_VERSION_TIRE_SETS = 1

STORAGE_KEY_EQUIPMENT_ITEMS = f"{DOMAIN}_equipment_items"
STORAGE_VERSION_EQUIPMENT_ITEMS = 1

STORAGE_KEY_BATTERIES = f"{DOMAIN}_batteries"
STORAGE_VERSION_BATTERIES = 1

EQUIPMENT_TYPE_FIRST_AID_KIT = "first_aid_kit"
EQUIPMENT_TYPE_FIRE_EXTINGUISHER = "fire_extinguisher"
EQUIPMENT_TYPE_WARNING_TRIANGLES = "warning_triangles"
EQUIPMENT_TYPE_REFLECTIVE_VEST = "reflective_vest"
EQUIPMENT_TYPE_SPARE_WHEEL = "spare_wheel"
EQUIPMENT_TYPE_PUNCTURE_KIT = "puncture_kit"
EQUIPMENT_TYPE_COMPRESSOR = "compressor"
EQUIPMENT_TYPE_JACK = "jack"
EQUIPMENT_TYPE_WHEEL_WRENCH = "wheel_wrench"
EQUIPMENT_TYPE_JUMP_CABLES = "jump_cables"
EQUIPMENT_TYPE_SNOW_CHAINS = "snow_chains"
EQUIPMENT_TYPE_OTHER = "other"

EQUIPMENT_TYPES: dict[str, str] = {
    EQUIPMENT_TYPE_FIRST_AID_KIT: "Trusă medicală",
    EQUIPMENT_TYPE_FIRE_EXTINGUISHER: "Stingător",
    EQUIPMENT_TYPE_WARNING_TRIANGLES: "Triunghiuri reflectorizante",
    EQUIPMENT_TYPE_REFLECTIVE_VEST: "Vestă reflectorizantă",
    EQUIPMENT_TYPE_SPARE_WHEEL: "Roată de rezervă",
    EQUIPMENT_TYPE_PUNCTURE_KIT: "Kit pană",
    EQUIPMENT_TYPE_COMPRESSOR: "Compresor",
    EQUIPMENT_TYPE_JACK: "Cric",
    EQUIPMENT_TYPE_WHEEL_WRENCH: "Cheie roți",
    EQUIPMENT_TYPE_JUMP_CABLES: "Cabluri pornire",
    EQUIPMENT_TYPE_SNOW_CHAINS: "Lanțuri antiderapante",
    EQUIPMENT_TYPE_OTHER: "Alt echipament",
}

BATTERY_TYPE_LEAD_ACID = "lead_acid"
BATTERY_TYPE_AGM = "agm"
BATTERY_TYPE_EFB = "efb"
BATTERY_TYPE_GEL = "gel"
BATTERY_TYPE_LITHIUM = "lithium"
BATTERY_TYPE_OTHER = "other"

BATTERY_TYPES: dict[str, str] = {
    BATTERY_TYPE_LEAD_ACID: "Plumb-acid clasică",
    BATTERY_TYPE_AGM: "AGM",
    BATTERY_TYPE_EFB: "EFB",
    BATTERY_TYPE_GEL: "Gel",
    BATTERY_TYPE_LITHIUM: "Litiu",
    BATTERY_TYPE_OTHER: "Alt tip",
}

# Modul intern e-rovinieta.ro.
CONF_ROVINIETA_USERNAME = "rovinieta_username"
CONF_ROVINIETA_PASSWORD = "rovinieta_password"
CONF_ROVINIETA_SCAN_INTERVAL = "rovinieta_scan_interval"

DEFAULT_ROVINIETA_SCAN_INTERVAL = 6 * 60 * 60
MIN_ROVINIETA_SCAN_INTERVAL = 15 * 60


# Termene legale gestionate manual.
# RCA, ITP și alte termene legale sunt separate de mentenanța mecanică.
CONF_LEGAL_TERMS = "legal_terms"

LEGAL_TYPE_RCA = "rca"
LEGAL_TYPE_CASCO = "casco"
LEGAL_TYPE_ITP = "itp"
LEGAL_TYPE_ROVINIETA = "rovinieta"

# Termene legale cu perioadă de valabilitate editabilă manual.
# Rovinieta poate fi urmărită și manual, pentru utilizatorii fără cont e-rovinieta.ro.
# Dacă modulul e-rovinieta.ro este configurat și găsește autovehiculul, cardul preferă datele automate.
LEGAL_TYPES: dict[str, str] = {
    LEGAL_TYPE_RCA: "RCA",
    LEGAL_TYPE_CASCO: "CASCO",
    LEGAL_TYPE_ITP: "ITP",
    LEGAL_TYPE_ROVINIETA: "Rovinietă",
}

LEGAL_COST_TYPES: dict[str, str] = {
    LEGAL_TYPE_RCA: "RCA",
    LEGAL_TYPE_CASCO: "CASCO",
    LEGAL_TYPE_ITP: "ITP",
    LEGAL_TYPE_ROVINIETA: "Rovinietă",
}

LEGAL_START_DATE = "start_date"
LEGAL_END_DATE = "end_date"
LEGAL_OPTION_IGNORED = "ignored"

LEGAL_DATA_SOURCE = "source"
LEGAL_SOURCE_MANUAL = "manual"
LEGAL_SOURCE_EROVINIETA = "e-rovinieta.ro"

LEGAL_STATUS_UNKNOWN = "neconfigurat"
LEGAL_STATUS_VALID = "valid"
LEGAL_STATUS_SOON = "expiră în curând"
LEGAL_STATUS_EXPIRED = "expirat"

LEGAL_SOON_DAYS_THRESHOLD = 30

# Câmpuri RCA introduse manual. Nu se interoghează AIDA/BAAR și nu se face scraping.
RCA_INSURER = "insurer"
RCA_POLICY_NUMBER = "policy_number"
RCA_NOTES = "notes"

RCA_TEXT_FIELDS: dict[str, str] = {
    RCA_INSURER: "RCA - asigurător",
    RCA_POLICY_NUMBER: "RCA - număr poliță",
    RCA_NOTES: "RCA - observații",
}

# Câmpuri CASCO introduse manual.
CASCO_INSURER = "insurer"
CASCO_POLICY_NUMBER = "policy_number"
CASCO_COVERAGE = "coverage"
CASCO_NOTES = "notes"

CASCO_TEXT_FIELDS: dict[str, str] = {
    CASCO_INSURER: "CASCO - asigurător",
    CASCO_POLICY_NUMBER: "CASCO - număr poliță",
    CASCO_COVERAGE: "CASCO - acoperire",
    CASCO_NOTES: "CASCO - observații",
}

# Câmpuri ITP introduse manual. Verificarea automată se va trata separat ulterior.
ITP_STATION = "station"
ITP_REPORT_NUMBER = "report_number"
ITP_NOTES = "notes"

ITP_TEXT_FIELDS: dict[str, str] = {
    ITP_STATION: "ITP - stație",
    ITP_REPORT_NUMBER: "ITP - număr raport",
    ITP_NOTES: "ITP - observații",
}
