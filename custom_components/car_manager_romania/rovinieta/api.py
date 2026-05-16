"""Modul API pentru e-rovinieta.ro."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import API_BASE_URL
from .exceptions import ERovinietaApiError, ERovinietaAuthError

_LOGGER = logging.getLogger(__name__)


class ERovinietaApiClient:
    """Clasă pentru erovinieta API client."""

    def __init__(self, session: ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    @property
    def headers(self) -> dict[str, str]:
        """Funcție pentru headere."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://e-rovinieta.ro",
            "Referer": "https://e-rovinieta.ro/ro/login",
            "User-Agent": "Home Assistant e-rovinieta.ro custom integration",
            "X-Device": "desktop",
            "X-Lang": "ro",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def async_login(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru login."""
        payload = {"username": self._username, "password": self._password}
        data = await self._request("POST", "/auth/login", json=payload, auth_call=True)

        token = data.get("access_token")
        if not token:
            raise ERovinietaAuthError("Login succeeded but no access token was returned")

        self._token = token
        return data

    async def async_get_account(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru get cont."""
        return await self._ensure_auth_then_request("GET", "/auth/me")

    async def async_get_vehicles(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru get vehicule."""
        return await self._ensure_auth_then_request(
            "GET",
            "/vehicles?sort_car_vignette_expiry_date=vignette_expiry&page=1",
            referer="https://e-rovinieta.ro/ro/contul-meu/masinile-mele",
        )

    async def async_get_orders(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru get comenzi."""
        return await self._ensure_auth_then_request(
            "GET",
            "/orders?page_erv=1",
            referer="https://e-rovinieta.ro/ro/contul-meu/comenzile-mele",
        )

    async def async_get_order_statuses(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru get order statuses."""
        return await self._ensure_auth_then_request("GET", "/ordersSts")

    async def async_get_profiles(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru get profiles."""
        return await self._ensure_auth_then_request(
            "GET",
            "/profiles",
            referer="https://e-rovinieta.ro/ro/contul-meu/profile",
        )

    async def async_get_tokens(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru get tokenuri."""
        return await self._ensure_auth_then_request(
            "GET",
            "/tokens",
            referer="https://e-rovinieta.ro/ro/contul-meu/carduri",
        )

    async def async_fetch_all(self) -> dict[str, Any]:
        """Gestionează asincron operațiunea pentru fetch all."""
        if not self._token:
            await self.async_login()

        account, vehicles, orders, profiles, tokens = await asyncio.gather(
            self.async_get_account(),
            self.async_get_vehicles(),
            self.async_get_orders(),
            self.async_get_profiles(),
            self.async_get_tokens(),
        )

        return {
            "account": account,
            "vehicles": vehicles,
            "orders": orders,
            "profiles": profiles,
            "tokens": tokens,
        }

    async def _ensure_auth_then_request(
        self,
        method: str,
        path: str,
        *,
        referer: str | None = None,
    ) -> dict[str, Any]:
        """Funcție internă pentru ensure auth then cerere."""
        try:
            return await self._request(method, path, referer=referer)
        except ERovinietaAuthError:
            _LOGGER.debug("Authentication expired, trying to log in again")
            await self.async_login()
            return await self._request(method, path, referer=referer)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        referer: str | None = None,
        auth_call: bool = False,
    ) -> dict[str, Any]:
        """Funcție internă pentru cerere."""
        headers = dict(self.headers)
        if referer:
            headers["Referer"] = referer

        url = f"{API_BASE_URL}{path}"

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=30,
            ) as response:
                response.raise_for_status()
                data: dict[str, Any] = await response.json(content_type=None)

        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ERovinietaAuthError("Invalid credentials or expired session") from err
            raise ERovinietaApiError(f"HTTP error {err.status} while calling {path}") from err
        except (ClientError, asyncio.TimeoutError) as err:
            raise ERovinietaApiError(f"Communication error while calling {path}") from err
        except ValueError as err:
            raise ERovinietaApiError(f"Invalid JSON received from {path}") from err

        if not isinstance(data, dict):
            raise ERovinietaApiError(f"Unexpected response type from {path}")

        if auth_call and "access_token" not in data:
            raise ERovinietaAuthError("Login failed")

        return data
