"""Accnary error hierarchy.

One shared module so models, storage, and services can raise/inspect the
same types without circular imports.
"""

from __future__ import annotations


class AccnaryError(Exception):
    """Base class for all Accnary errors."""


# ---------------------------------------------------------------------------
# Storage / vault
# ---------------------------------------------------------------------------

class VaultError(AccnaryError):
    """Base class for vault (KDBX file) errors."""


class VaultLockedError(VaultError):
    """Operation requires an unlocked vault."""


class VaultNotFoundError(VaultError):
    """The vault file does not exist."""


class BadCredentialsError(VaultError):
    """Wrong master password (or key file)."""


class VaultFormatError(VaultError):
    """The file could not be parsed as a KDBX database (corrupt/foreign)."""


class ConflictError(VaultError):
    """The vault file changed on disk after it was opened.

    Saving over it would clobber external modifications; the caller must
    reload (losing unsaved in-memory changes) or export them elsewhere.
    """


class SafeSaveError(VaultError):
    """A save attempt failed; the previous file version is intact."""


class UnsupportedFormatError(VaultError):
    """Refusing to write back a KDBX format Accnary does not fully own.

    Covers KDBX 3.x (legacy) and 4.1+ (features pykeepass only partially
    models). Reading stays allowed; writing is refused to avoid data loss.
    """


class SchemaTooNewError(VaultError):
    """A Accnary.Meta schema version newer than supported was found.

    Saving is refused so that fields defined by a newer Accnary are not
    silently dropped.
    """


class BackupError(VaultError):
    """Encrypted backup export/restore failed."""


# ---------------------------------------------------------------------------
# Catalog / services
# ---------------------------------------------------------------------------

class CatalogError(AccnaryError):
    """Base class for catalog/service-layer errors."""


class ServiceExistsError(CatalogError):
    """A service group with this name already exists."""


class ServiceNotFoundError(CatalogError):
    """Referenced service does not exist."""


class AccountNotFoundError(CatalogError):
    """Referenced account UUID does not exist (or is not an Accnary account)."""


class MetaFormatError(CatalogError):
    """Accnary.Meta payload is not valid JSON or violates schema v1 shape."""


class IdentityInUseError(CatalogError):
    """Identity removal refused because accounts still reference it."""


class ReservedKeyError(CatalogError):
    """Refusing to use a reserved key (Accnary.* namespace / standard fields)."""
