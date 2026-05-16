"""Modul pentru excepțiile integrației."""


class ERovinietaError(Exception):
    """Clasă pentru erovinieta eroare."""


class ERovinietaAuthError(ERovinietaError):
    """Clasă pentru erovinieta auth eroare."""


class ERovinietaApiError(ERovinietaError):
    """Clasă pentru erovinieta API eroare."""


class ERovinietaLicenseError(ERovinietaError):
    """Clasă pentru erovinieta licență eroare."""


class ERovinietaLicenseInvalidError(ERovinietaLicenseError):
    """Clasă pentru erovinieta licență invalidă eroare."""


class ERovinietaLicenseExpiredError(ERovinietaLicenseError):
    """Clasă pentru erovinieta licență expirată eroare."""


class ERovinietaLicenseRevokedError(ERovinietaLicenseError):
    """Clasă pentru erovinieta licență revocată eroare."""


class ERovinietaLicenseInvalidProductError(ERovinietaLicenseError):
    """Clasă pentru erovinieta licență invalidă produs eroare."""


class ERovinietaLicenseActivationLimitError(ERovinietaLicenseError):
    """Clasă pentru erovinieta licență activare limită eroare."""


class ERovinietaLicenseConnectionError(ERovinietaLicenseError):
    """Clasă pentru erovinieta licență connection eroare."""
