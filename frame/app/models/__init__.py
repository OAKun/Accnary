"""Accnary data model: Service -> Account -> LoginMethod / Identity / License."""

from .account import Account
from .binding import Binding, CustomField
from .catalog import Catalog
from .enums import (
    BindingRole,
    IdentityKind,
    LicenseMode,
    LoginMethodType,
    ServiceType,
)
from .identity import Identity
from .license_info import LicenseInfo
from .login_method import LoginMethod
from .service import Service
from .serialization import (
    META_CUSTOM_KEY,
    RESERVED_CUSTOM_PREFIX,
    SCHEMA_CUSTOM_KEY,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    SYSTEM_MARKER_KEY,
    entry_meta_from_json,
    entry_meta_to_json,
    read_schema_version,
    register_migration,
    registry_meta_from_json,
    registry_meta_to_json,
)

__all__ = [
    "Account",
    "Binding",
    "BindingRole",
    "Catalog",
    "CustomField",
    "Identity",
    "IdentityKind",
    "LicenseInfo",
    "LicenseMode",
    "LoginMethod",
    "LoginMethodType",
    "META_CUSTOM_KEY",
    "RESERVED_CUSTOM_PREFIX",
    "SCHEMA_CUSTOM_KEY",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SYSTEM_MARKER_KEY",
    "Service",
    "ServiceType",
    "entry_meta_from_json",
    "entry_meta_to_json",
    "read_schema_version",
    "register_migration",
    "registry_meta_from_json",
    "registry_meta_to_json",
]
