"""Exceptions for e-rovinieta.ro."""


class ERovinietaError(Exception):
    """Base error for the integration."""


class ERovinietaAuthError(ERovinietaError):
    """Raised when authentication fails."""


class ERovinietaApiError(ERovinietaError):
    """Raised when the API returns an unexpected response."""


class ERovinietaLicenseError(ERovinietaError):
    """Base license error."""


class ERovinietaLicenseInvalidError(ERovinietaLicenseError):
    """Raised when license is invalid."""


class ERovinietaLicenseExpiredError(ERovinietaLicenseError):
    """Raised when license is expired."""


class ERovinietaLicenseRevokedError(ERovinietaLicenseError):
    """Raised when license is revoked."""


class ERovinietaLicenseInvalidProductError(ERovinietaLicenseError):
    """Raised when license is not valid for this product."""


class ERovinietaLicenseActivationLimitError(ERovinietaLicenseError):
    """Raised when license activation limit is reached."""


class ERovinietaLicenseConnectionError(ERovinietaLicenseError):
    """Raised when license server cannot be reached."""