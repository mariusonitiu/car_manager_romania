"""Licensing helpers for Car Manager România."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    CONF_LICENSE_KEY,
    CONF_LICENSE_USER,
    DATE_VERIFICARE_LICENTA,
    DOMAIN,
    DEFAULT_LICENSE_GRACE_DAYS,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_ACTIVATION_LIMIT,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_INVALID,
    LICENSE_STATUS_INVALID_PRODUCT,
    LICENSE_STATUS_REVOKED,
    LICENSE_STATUS_TRIAL,
    LICENSE_STATUS_UNKNOWN,
    STORAGE_KEY_LICENSE,
    STORAGE_VERSION_LICENSE,
    URL_API_LICENTA,
)

_LOGGER = logging.getLogger(__name__)

ACCEPTED_LICENSE_STATUSES = {LICENSE_STATUS_ACTIVE, LICENSE_STATUS_TRIAL}


@dataclass(slots=True)
class LicenseResult:
    """Normalized result returned by the licensing endpoint."""

    valid: bool
    status: str
    plan: str | None = None
    expires_at: str | None = None
    message: str | None = None
    checked_at: str | None = None
    connection_error: bool = False
    username: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "valid": self.valid,
            "status": self.status,
            "plan": self.plan,
            "expires_at": self.expires_at,
            "message": self.message,
            "checked_at": self.checked_at,
            "connection_error": self.connection_error,
            "username": self.username,
        }


# Compat aliases with the Romanian naming used in Utilități România.
RezultatLicenta = LicenseResult


def build_instance_fingerprint(hass: HomeAssistant) -> str:
    """Build a stable fingerprint for the Home Assistant instance."""

    parts = [
        DOMAIN,
        getattr(hass.config, "config_dir", "") or "",
        getattr(hass.config, "location_name", "") or "",
        getattr(hass.config, "internal_url", "") or "",
        getattr(hass.config, "external_url", "") or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def construieste_fingerprint_instanta(hass: HomeAssistant) -> str:
    """Compatibility wrapper for Utilități România naming."""

    return build_instance_fingerprint(hass)


async def async_get_global_license(hass: HomeAssistant) -> dict[str, Any]:
    """Load globally stored license data."""

    store = Store[dict[str, Any]](hass, STORAGE_VERSION_LICENSE, STORAGE_KEY_LICENSE)
    data = await store.async_load()
    return data if isinstance(data, dict) else {}


async def async_obtine_licenta_globala(hass: HomeAssistant) -> dict[str, Any]:
    """Compatibility wrapper for Utilități România naming."""

    return await async_get_global_license(hass)


async def async_save_global_license(
    hass: HomeAssistant,
    license_key: str,
    username: str,
    result: LicenseResult | None = None,
) -> None:
    """Save license key and, when available, the last validation result."""

    store = Store[dict[str, Any]](hass, STORAGE_VERSION_LICENSE, STORAGE_KEY_LICENSE)

    final_username = str((result.username if result and result.username else username) or "").strip()
    payload: dict[str, Any] = {
        CONF_LICENSE_KEY: str(license_key).strip() or "TRIAL",
        CONF_LICENSE_USER: final_username,
    }

    if result is not None:
        payload[DATE_VERIFICARE_LICENTA] = result.as_dict()

    await store.async_save(payload)


async def async_salveaza_licenta_globala(
    hass: HomeAssistant,
    cheie_licenta: str,
    utilizator: str,
    rezultat: LicenseResult | None = None,
) -> None:
    """Compatibility wrapper for Utilități România naming."""

    await async_save_global_license(hass, cheie_licenta, utilizator, rezultat)


def _default_license_username(hass: HomeAssistant) -> str:
    """Return a non-sensitive default account label for the license server."""

    return str(getattr(hass.config, "location_name", "") or DOMAIN).strip()


async def async_get_license_context(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
    username: str | None = None,
    license_key: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Return username, key and raw storage data for validation."""

    storage = await async_get_global_license(hass)
    storage_username = str(storage.get(CONF_LICENSE_USER, "")).strip()
    storage_key = str(storage.get(CONF_LICENSE_KEY, "")).strip()

    entry_username = ""
    entry_key = ""
    if entry is not None:
        entry_username = str(entry.options.get(CONF_LICENSE_USER, entry.data.get(CONF_LICENSE_USER, ""))).strip()
        entry_key = str(entry.options.get(CONF_LICENSE_KEY, entry.data.get(CONF_LICENSE_KEY, ""))).strip()

    final_username = (
        str(username).strip()
        if username is not None
        else (storage_username or entry_username or _default_license_username(hass))
    )
    final_key = (
        str(license_key).strip()
        if license_key is not None
        else (storage_key or entry_key or "TRIAL")
    )
    return final_username, final_key, storage


async def async_obtine_context_licenta(
    hass: HomeAssistant,
    intrare: ConfigEntry | None = None,
    utilizator: str | None = None,
    cheie_licenta: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Compatibility wrapper for Utilități România naming."""

    return await async_get_license_context(hass, intrare, utilizator, cheie_licenta)


def _stored_license_matches_context(storage: dict[str, Any], license_key: str, username: str) -> bool:
    key_ok = str(storage.get(CONF_LICENSE_KEY, "")).strip() == str(license_key).strip()
    stored_user = str(storage.get(CONF_LICENSE_USER, "")).strip()
    if not username or not stored_user:
        return key_ok
    return key_ok and stored_user == str(username).strip()


def _date_licenta_din_storage_sunt_pentru_contextul_curent(
    date_licenta_globala: dict[str, Any],
    cheie_licenta: str,
    utilizator: str,
) -> bool:
    """Compatibility wrapper for Utilități România naming."""

    return _stored_license_matches_context(date_licenta_globala, cheie_licenta, utilizator)


async def async_validate_license(
    hass: HomeAssistant,
    license_key: str,
    username: str,
) -> LicenseResult:
    """Validate a license using the shared Cloudflare Worker."""

    session = async_get_clientsession(hass)
    payload = {
        "license_key": str(license_key or "").strip() or "TRIAL",
        "fingerprint": build_instance_fingerprint(hass),
        "product": DOMAIN,
        "username": str(username or "").strip(),
    }

    try:
        async with session.post(URL_API_LICENTA, json=payload, timeout=20) as response:
            try:
                data = await response.json(content_type=None)
            except Exception:  # noqa: BLE001 - response body may be plain text
                data = {"message": await response.text()}

            if not isinstance(data, dict):
                data = {"message": "Răspuns invalid de la serverul de licențiere."}

            raw_status = str(data.get("status", LICENSE_STATUS_UNKNOWN)).strip().lower()
            valid = bool(data.get("valid", False) or data.get("active", False))

            response_product = str(data.get("product") or data.get("domain") or "").strip()
            if valid and response_product and response_product != DOMAIN:
                valid = False
                raw_status = LICENSE_STATUS_INVALID_PRODUCT
                data["message"] = "Licența este validă, dar aparține altei integrări."

            if response.status >= 400 and not valid:
                if response.status in (400, 401, 403, 404):
                    status = raw_status if raw_status in LICENSE_STATUS_LABELS else LICENSE_STATUS_INVALID
                else:
                    status = LICENSE_STATUS_UNKNOWN
            elif valid:
                status = LICENSE_STATUS_TRIAL if raw_status == LICENSE_STATUS_TRIAL else LICENSE_STATUS_ACTIVE
            else:
                status = raw_status if raw_status in LICENSE_STATUS_LABELS else LICENSE_STATUS_INVALID

            return LicenseResult(
                valid=valid,
                status=status,
                plan=data.get("plan") or data.get("license_plan"),
                expires_at=data.get("expires_at") or data.get("valid_until") or data.get("expires"),
                message=data.get("message") or data.get("error"),
                checked_at=_now_utc_iso(),
                connection_error=False,
                username=str(data.get("username", "")).strip() or None,
            )

    except (ClientError, TimeoutError, ValueError) as err:
        _LOGGER.warning("Validarea licenței Car Manager România a eșuat: %s", err)
        return LicenseResult(
            valid=False,
            status=LICENSE_STATUS_UNKNOWN,
            message=str(err),
            checked_at=_now_utc_iso(),
            connection_error=True,
        )


async def async_valideaza_licenta(
    hass: HomeAssistant,
    cheie_licenta: str,
    utilizator: str,
) -> LicenseResult:
    """Compatibility wrapper for Utilități România naming."""

    return await async_validate_license(hass, cheie_licenta, utilizator)


def extract_stored_license_result(entry: ConfigEntry | None = None, storage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract the latest validation result from an entry or global storage."""

    if storage is not None:
        value = storage.get(DATE_VERIFICARE_LICENTA)
        return value if isinstance(value, dict) else {}

    if entry is None:
        return {}

    value = entry.options.get(DATE_VERIFICARE_LICENTA) or entry.data.get(DATE_VERIFICARE_LICENTA) or {}
    return value if isinstance(value, dict) else {}


def extrage_date_licenta_stocate(intrare: ConfigEntry) -> dict[str, Any]:
    """Compatibility wrapper for Utilități România naming."""

    return extract_stored_license_result(intrare)


def license_is_accepted(license_data: dict[str, Any]) -> bool:
    """Return True when stored validation data allows the integration to operate."""

    return bool(license_data.get("valid")) and license_data.get("status") in ACCEPTED_LICENSE_STATUSES


def licenta_este_acceptata(date_licenta: dict[str, Any]) -> bool:
    """Compatibility wrapper for Utilități România naming."""

    return license_is_accepted(date_licenta)


def can_use_cached_license(
    license_data: dict[str, Any],
    grace_days: int = DEFAULT_LICENSE_GRACE_DAYS,
) -> bool:
    """Return True if cached license data is still within the grace period."""

    if not license_is_accepted(license_data):
        return False

    checked_at = license_data.get("checked_at")
    if not checked_at:
        return False

    try:
        checked_dt = datetime.fromisoformat(str(checked_at).replace("Z", "+00:00"))
    except ValueError:
        return False

    return datetime.now(UTC) <= checked_dt + timedelta(days=grace_days)


def se_poate_folosi_licenta_din_cache(
    date_licenta: dict[str, Any],
    zile_gratie: int = DEFAULT_LICENSE_GRACE_DAYS,
) -> bool:
    """Compatibility wrapper for Utilități România naming."""

    return can_use_cached_license(date_licenta, zile_gratie)


def mask_license_key(key: str | None) -> str:
    """Return a safe masked representation of a license key."""

    if not key:
        return ""
    key = str(key).strip()
    if len(key) <= 4:
        return "*" * len(key)
    return f"{key[:4]}***{key[-2:]}"


def mascheaza_cheia_licenta(cheie: str | None) -> str:
    """Compatibility wrapper for Utilități România naming."""

    return mask_license_key(cheie)


async def async_check_license(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
) -> LicenseResult:
    """Validate current license and fall back to recently cached data on connection errors."""

    username, key, storage = await async_get_license_context(hass, entry=entry)
    result = await async_validate_license(hass, key, username)

    if result.valid:
        return result

    if result.connection_error:
        entry_cache = extract_stored_license_result(entry) if entry is not None else {}
        if can_use_cached_license(entry_cache):
            return LicenseResult(
                valid=True,
                status=entry_cache.get("status", LICENSE_STATUS_UNKNOWN),
                plan=entry_cache.get("plan"),
                expires_at=entry_cache.get("expires_at"),
                message=entry_cache.get("message"),
                checked_at=entry_cache.get("checked_at"),
                username=entry_cache.get("username"),
            )

        global_cache = extract_stored_license_result(storage=storage)
        if _stored_license_matches_context(storage, key, username) and can_use_cached_license(global_cache):
            return LicenseResult(
                valid=True,
                status=global_cache.get("status", LICENSE_STATUS_UNKNOWN),
                plan=global_cache.get("plan"),
                expires_at=global_cache.get("expires_at"),
                message=global_cache.get("message"),
                checked_at=global_cache.get("checked_at"),
                username=global_cache.get("username"),
            )

    return result


async def async_verifica_licenta(
    hass: HomeAssistant,
    intrare: ConfigEntry | None = None,
) -> LicenseResult:
    """Compatibility wrapper for Utilități România naming."""

    return await async_check_license(hass, intrare)


def validate_license_result(result: LicenseResult) -> None:
    """Raise ValueError when the license result is not accepted."""

    if result.valid:
        return

    if result.connection_error:
        raise ValueError(result.message or "server_licenta_indisponibil")
    if result.status == LICENSE_STATUS_INVALID:
        raise ValueError("licenta_invalida")
    if result.status == LICENSE_STATUS_EXPIRED:
        raise ValueError("licenta_expirata")
    if result.status == LICENSE_STATUS_REVOKED:
        raise ValueError("licenta_revocata")
    if result.status == LICENSE_STATUS_INVALID_PRODUCT:
        raise ValueError("licenta_produs_invalid")
    if result.status == LICENSE_STATUS_ACTIVATION_LIMIT:
        raise ValueError("licenta_limita_activari")

    raise ValueError(result.message or "licenta_necunoscuta")


def valideaza_rezultat_licenta(rezultat: LicenseResult) -> None:
    """Compatibility wrapper for Utilități România naming."""

    validate_license_result(rezultat)


async def async_save_license_in_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    result: LicenseResult,
) -> None:
    """Persist latest validation result in global storage and in the config entry."""

    username, key, _storage = await async_get_license_context(hass, entry=entry)
    await async_save_global_license(hass, key, username, result)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, DATE_VERIFICARE_LICENTA: result.as_dict()},
    )


async def async_salveaza_licenta_in_intrare(
    hass: HomeAssistant,
    intrare: ConfigEntry,
    rezultat: LicenseResult,
) -> None:
    """Compatibility wrapper for Utilități România naming."""

    await async_save_license_in_entry(hass, intrare, rezultat)


def _now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


# Labels are defined at the end so async_validate_license can use the final map.
LICENSE_STATUS_LABELS: dict[str, str] = {
    LICENSE_STATUS_ACTIVE: "Activă",
    LICENSE_STATUS_TRIAL: "Trial activ",
    LICENSE_STATUS_EXPIRED: "Expirată",
    LICENSE_STATUS_INVALID: "Invalidă",
    LICENSE_STATUS_REVOKED: "Revocată",
    LICENSE_STATUS_INVALID_PRODUCT: "Produs invalid",
    LICENSE_STATUS_ACTIVATION_LIMIT: "Limită activări atinsă",
    LICENSE_STATUS_UNKNOWN: "Necunoscută",
}
