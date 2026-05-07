"""Dataclasses used by the e-rovinieta.ro integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    """Return a timezone aware UTC datetime."""
    return datetime.now(UTC)


@dataclass(slots=True)
class VehicleData:
    """Normalized vehicle data."""

    id: int
    plate_no: str
    chasis_no: str | None
    country_name: str | None
    country_code: str | None
    category_vignette_title: str | None
    category_vignette_desc: str | None
    category_toll_title: str | None
    category_toll_desc: str | None
    active_count: int
    all_time_count: int
    has_active_vignette: bool
    expiry: datetime | None
    days_remaining: int | None
    active_vignette: dict[str, Any] | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


@dataclass(slots=True)
class OrderData:
    """Normalized order data."""

    id: int
    order_type: str
    status_name: str
    date: str | None
    emitted_at: datetime | None
    total_lei: float | None
    total_euro: float | None
    value_total: float | None
    plate_numbers: list[str]
    invoice: str | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


@dataclass(slots=True)
class AccountData:
    """Aggregated account data."""

    account: dict[str, Any]
    vehicles: list[VehicleData]
    orders: list[OrderData]
    profiles: list[dict[str, Any]]
    tokens: list[dict[str, Any]]
    fetched_at: datetime

    @property
    def active_vignettes(self) -> int:
        return sum(1 for vehicle in self.vehicles if vehicle.has_active_vignette)

    @property
    def expiring_soon(self) -> int:
        return sum(
            1
            for vehicle in self.vehicles
            if vehicle.days_remaining is not None and 0 <= vehicle.days_remaining <= 30
        )
