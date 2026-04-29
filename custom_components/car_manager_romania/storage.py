"""Storage helpers for Car Manager România."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_NOTIFICATIONS, STORAGE_VERSION_NOTIFICATIONS


class CarManagerNotificationStore:
    """Store notified maintenance statuses."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize notification store."""

        self._store: Store = Store(
            hass,
            STORAGE_VERSION_NOTIFICATIONS,
            STORAGE_KEY_NOTIFICATIONS,
        )
        self._data: dict[str, Any] = {"notified": {}}
        self._loaded = False

    async def async_load(self) -> None:
        """Load stored data."""

        if self._loaded:
            return

        data = await self._store.async_load()
        if isinstance(data, dict):
            notified = data.get("notified")
            if isinstance(notified, dict):
                self._data = {"notified": notified}

        self._loaded = True

    async def async_get_notified_status(self, key: str) -> str | None:
        """Return notified status for key."""

        await self.async_load()
        value = self._data["notified"].get(key)
        return str(value) if value else None

    async def async_set_notified_status(self, key: str, status: str) -> None:
        """Persist notified status."""

        await self.async_load()
        self._data["notified"][key] = status
        await self._store.async_save(self._data)

    async def async_clear_notified_status(self, key: str) -> None:
        """Clear notified status."""

        await self.async_load()
        if key not in self._data["notified"]:
            return

        self._data["notified"].pop(key, None)
        await self._store.async_save(self._data)
