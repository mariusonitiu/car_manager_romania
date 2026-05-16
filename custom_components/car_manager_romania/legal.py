"""Modul pentru termene legale ale vehiculelor."""

from __future__ import annotations

from datetime import date
from typing import Any

from .const import (
    CONF_LEGAL_TERMS,
    LEGAL_END_DATE,
    LEGAL_OPTION_IGNORED,
    LEGAL_SOON_DAYS_THRESHOLD,
    LEGAL_START_DATE,
    LEGAL_STATUS_EXPIRED,
    LEGAL_STATUS_SOON,
    LEGAL_STATUS_UNKNOWN,
    LEGAL_STATUS_VALID,
)
from .maintenance import parse_date


def get_legal_term(vehicle: dict[str, Any], legal_type: str) -> dict[str, Any]:
    """Funcție pentru get legal termen."""

    legal_terms = vehicle.get(CONF_LEGAL_TERMS, {})
    if not isinstance(legal_terms, dict):
        return {}

    value = legal_terms.get(legal_type, {})
    return value if isinstance(value, dict) else {}


def get_legal_value(vehicle: dict[str, Any], legal_type: str, field: str) -> Any:
    """Funcție pentru get legal valoare."""

    return get_legal_term(vehicle, legal_type).get(field)


def set_legal_value(
    vehicle: dict[str, Any],
    legal_type: str,
    field: str,
    value: Any,
) -> None:
    """Funcție pentru set legal valoare."""

    if CONF_LEGAL_TERMS not in vehicle or not isinstance(vehicle[CONF_LEGAL_TERMS], dict):
        vehicle[CONF_LEGAL_TERMS] = {}

    if legal_type not in vehicle[CONF_LEGAL_TERMS] or not isinstance(
        vehicle[CONF_LEGAL_TERMS][legal_type], dict
    ):
        vehicle[CONF_LEGAL_TERMS][legal_type] = {}

    vehicle[CONF_LEGAL_TERMS][legal_type][field] = value



def is_legal_ignored(vehicle: dict[str, Any], legal_type: str) -> bool:
    """Funcție pentru is legal ignored."""

    return bool(get_legal_value(vehicle, legal_type, LEGAL_OPTION_IGNORED))


def set_legal_ignored(vehicle: dict[str, Any], legal_type: str, ignored: bool) -> None:
    """Funcție pentru set legal ignored."""

    set_legal_value(vehicle, legal_type, LEGAL_OPTION_IGNORED, bool(ignored))


def legal_is_configured(vehicle: dict[str, Any], legal_type: str) -> bool:
    """Funcție pentru legal is configured."""

    return parse_date(get_legal_value(vehicle, legal_type, LEGAL_END_DATE)) is not None

def legal_days_remaining(vehicle: dict[str, Any], legal_type: str) -> int | None:
    """Funcție pentru legal zile rămași."""

    end_date = parse_date(get_legal_value(vehicle, legal_type, LEGAL_END_DATE))
    if end_date is None:
        return None

    return max((end_date - date.today()).days, 0)


def legal_status(vehicle: dict[str, Any], legal_type: str) -> str:
    """Funcție pentru statusul termenului legal."""

    end_date = parse_date(get_legal_value(vehicle, legal_type, LEGAL_END_DATE))
    if end_date is None:
        return LEGAL_STATUS_UNKNOWN

    today = date.today()
    if end_date < today:
        return LEGAL_STATUS_EXPIRED

    remaining_days = (end_date - today).days
    if remaining_days <= LEGAL_SOON_DAYS_THRESHOLD:
        return LEGAL_STATUS_SOON

    start_date = parse_date(get_legal_value(vehicle, legal_type, LEGAL_START_DATE))
    if start_date is not None and start_date > today:
        return LEGAL_STATUS_UNKNOWN

    return LEGAL_STATUS_VALID
