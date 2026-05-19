"""Data coordinator for the internal rovinieta module."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ERovinietaApiClient
from .exceptions import ERovinietaApiError, ERovinietaAuthError
from .models import AccountData
from .parser import normalize_payload

_LOGGER = logging.getLogger(__name__)


class CarManagerRovinietaCoordinator(DataUpdateCoordinator[AccountData]):
    """Coordinator for e-rovinieta.ro data inside Car Manager România."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ERovinietaApiClient,
        scan_interval_seconds: int,
    ) -> None:
        """Initialize coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            name="car_manager_romania_rovinieta",
            update_interval=timedelta(seconds=scan_interval_seconds),
            always_update=True,
        )
        self.client = client

    async def _async_update_data(self) -> AccountData:
        """Fetch and normalize rovinieta data."""

        try:
            payload = await self.client.async_fetch_all()
            return normalize_payload(payload)
        except ERovinietaAuthError as err:
            raise UpdateFailed(f"Autentificarea e-rovinieta.ro a eșuat: {err}") from err
        except ERovinietaApiError as err:
            raise UpdateFailed(str(err)) from err
