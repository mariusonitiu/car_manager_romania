"""Modul pentru funcții ajutătoare."""

from __future__ import annotations

from datetime import UTC, datetime
from html import unescape
from typing import Any


def parse_unix_timestamp(value: Any) -> datetime | None:
    """Funcție pentru parse unix timestamp."""
    if value in (None, "", 0, "0"):
        return None

    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OSError):
        return None


def parse_date_string(value: Any) -> datetime | None:
    """Funcție pentru parse dată string."""
    if not value:
        return None

    if isinstance(value, (int, float)):
        return parse_unix_timestamp(value)

    text = str(value).strip()
    if not text:
        return None

    formats = (
        "%d.%m.%Y %H:%M:%S",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
    )

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue

    return None


def safe_float(value: Any) -> float | None:
    """Funcție pentru safe float."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_text(value: Any) -> str | None:
    """Funcție pentru clean text."""
    if value in (None, ""):
        return None
    return unescape(str(value)).strip() or None


def slugify_plate(plate: str) -> str:
    """Funcție pentru slugify număr de înmatriculare."""
    return (
        plate.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def redact_token(value: str | None) -> str | None:
    """Funcție pentru redact token."""
    if not value:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"
