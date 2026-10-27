"""Accnary.Meta serialization - schema v1 wire format.

Mapping rules (see docs/DATA_FORMAT.md for the full contract):

- One KDBX entry per account; standard fields carry username/password/url/
  notes/title; everything structured lives in the "Accnary.Meta" custom
  attribute (encrypted like the rest of the KDBX XML payload).
- "Accnary.SchemaVersion" custom attribute carries the schema version as a
  decimal string so other tools (and humans in KeePassXC) can see it.
- Unknown keys are preserved: when a future Accnary adds keys we do not know
  about (within a version we support), they round-trip instead of being
  dropped. Structures nested inside a version are considered fixed; a change
  there requires a version bump and a migration function.
"""

from __future__ import annotations

import json
from typing import Callable

from app.errors import MetaFormatError

from .account import Account
from .binding import Binding
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

META_CUSTOM_KEY = "Accnary.Meta"
SCHEMA_CUSTOM_KEY = "Accnary.SchemaVersion"
SYSTEM_MARKER_KEY = "Accnary.System"
RESERVED_CUSTOM_PREFIX = "Accnary."

SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def register_migration(from_version: int, transform: Callable[[dict], dict]) -> None:
    """Register raw-dict migration from ``from_version`` to the next version.

    The callable receives the raw Accnary.Meta dict (already JSON-decoded)
    and must return the upgraded raw dict, including the bumped
    ``schema_version``.
    """
    _MIGRATIONS[from_version] = transform


def migrate_raw_meta(raw: dict, from_version: int) -> dict:
    version = from_version
    while version < SCHEMA_VERSION:
        transform = _MIGRATIONS.get(version)
        if transform is None:
            raise MetaFormatError(
                f"no migration path from Accnary schema version {version}"
            )
        raw = transform(raw)
        if not isinstance(raw, dict):
            raise MetaFormatError(f"migration from schema {version} returned non-dict")
        version = int(raw.get("schema_version", version + 1))
    return raw


# ---------------------------------------------------------------------------
# Low-level coercion helpers - tolerant on read, strict on write
# ---------------------------------------------------------------------------

def _as_str(value, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_opt_str(value) -> str | None:
    return value if isinstance(value, str) else None


def _as_list_str(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, str)]


def _as_bool(value, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _as_opt_int(value) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass; reject it
        return None
    return value if isinstance(value, int) else None


def _enum_or(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Service block
# ---------------------------------------------------------------------------

_SERVICE_KEYS = frozenset(
    {"name", "aliases", "type", "urls", "login_urls", "category", "tags", "notes"}
)


def service_to_block(service) -> dict:
    block = {
        "name": service.name,
        "aliases": list(service.aliases),
        "type": service.type.value,
        "urls": list(service.urls),
        "login_urls": list(service.login_urls),
        "category": service.category,
        "tags": list(service.tags),
        "notes": service.notes,
    }
    extra = getattr(service, "_extra", {})
    block.update({k: v for k, v in extra.items() if k not in block})
    return block


def service_from_block(block: dict) -> Service:
    if not isinstance(block, dict):
        raise MetaFormatError("service block is not an object")
    extra = {k: v for k, v in block.items() if k not in _SERVICE_KEYS}
    return Service(
        name=_as_str(block.get("name")),
        aliases=_as_list_str(block.get("aliases")),
        type=_enum_or(ServiceType, block.get("type"), ServiceType.OTHER),
        urls=_as_list_str(block.get("urls")),
        login_urls=_as_list_str(block.get("login_urls")),
        category=_as_str(block.get("category")),
        tags=_as_list_str(block.get("tags")),
        notes=_as_str(block.get("notes")),
        _extra=extra,
    )


# ---------------------------------------------------------------------------
# Account sub-blocks
# ---------------------------------------------------------------------------

def login_method_to_block(lm: LoginMethod) -> dict:
    return {
        "uuid": lm.uuid,
        "type": lm.type.value,
        "note": lm.note,
        "identity_ref": lm.identity_ref,
        "extra": lm.extra,
    }


def login_method_from_block(block: dict) -> LoginMethod:
    if not isinstance(block, dict):
        raise MetaFormatError("login_method block is not an object")
    return LoginMethod(
        uuid=_as_str(block.get("uuid")),
        type=_enum_or(LoginMethodType, block.get("type"), LoginMethodType.CUSTOM),
        note=_as_str(block.get("note")),
        identity_ref=_as_opt_str(block.get("identity_ref")),
        extra=_as_str(block.get("extra")),
    )


def binding_to_block(binding: Binding) -> dict:
    return {"identity_ref": binding.identity_ref, "role": binding.role.value}


def binding_from_block(block: dict) -> Binding:
    if not isinstance(block, dict):
        raise MetaFormatError("binding block is not an object")
    return Binding(
        identity_ref=_as_str(block.get("identity_ref")),
        role=_enum_or(BindingRole, block.get("role"), BindingRole.LINKED_IDENTITY),
    )


def license_to_block(lic: LicenseInfo) -> dict:
    return {
        "mode": lic.mode.value,
        "purchase_date": lic.purchase_date,
        "channel": lic.channel,
        "order_no": lic.order_no,
        "license_key": lic.license_key,
        "expires": lic.expires,
        "device_limit": lic.device_limit,
        "evidence": lic.evidence,
        "notes": lic.notes,
    }


def license_from_block(block: dict) -> LicenseInfo:
    if not isinstance(block, dict):
        raise MetaFormatError("license block is not an object")
    return LicenseInfo(
        mode=_enum_or(LicenseMode, block.get("mode"), LicenseMode.NONE),
        purchase_date=_as_str(block.get("purchase_date")),
        channel=_as_str(block.get("channel")),
        order_no=_as_str(block.get("order_no")),
        license_key=_as_str(block.get("license_key")),
        expires=_as_str(block.get("expires")),
        device_limit=_as_opt_int(block.get("device_limit")),
        evidence=_as_str(block.get("evidence")),
        notes=_as_str(block.get("notes")),
    )


_ACCOUNT_KEYS = frozenset(
    {
        "uuid",
        "user_id",
        "alias",
        "email",
        "phone",
        "favorite",
        "last_used_at",
        "login_methods",
        "identity_bindings",
        "license",
    }
)


def account_to_block(account: Account) -> dict:
    block = {
        "uuid": account.uuid,
        "user_id": account.user_id,
        "alias": account.alias,
        "email": account.email,
        "phone": account.phone,
        "favorite": account.favorite,
        "last_used_at": account.last_used_at,
        "login_methods": [login_method_to_block(x) for x in account.login_methods],
        "identity_bindings": [binding_to_block(x) for x in account.identity_bindings],
        "license": license_to_block(account.license),
    }
    extra = getattr(account, "_extra", {})
    block.update({k: v for k, v in extra.items() if k not in block})
    return block


def account_from_block(block: dict) -> Account:
    if not isinstance(block, dict):
        raise MetaFormatError("account block is not an object")
    extra = {k: v for k, v in block.items() if k not in _ACCOUNT_KEYS}
    methods_raw = block.get("login_methods", [])
    bindings_raw = block.get("identity_bindings", [])
    if not isinstance(methods_raw, list) or not isinstance(bindings_raw, list):
        raise MetaFormatError("login_methods/identity_bindings must be lists")
    return Account(
        uuid=_as_str(block.get("uuid")),
        user_id=_as_str(block.get("user_id")),
        alias=_as_str(block.get("alias")),
        email=_as_str(block.get("email")),
        phone=_as_str(block.get("phone")),
        favorite=_as_bool(block.get("favorite")),
        last_used_at=_as_opt_str(block.get("last_used_at")),
        login_methods=[login_method_from_block(x) for x in methods_raw],
        identity_bindings=[binding_from_block(x) for x in bindings_raw],
        license=license_from_block(block.get("license") or {}),
        _extra=extra,
    )


# ---------------------------------------------------------------------------
# Entry-level Accnary.Meta
# ---------------------------------------------------------------------------

def entry_meta_to_json(service, account: Account) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "service": service_to_block(service),
        "account": account_to_block(account),
    }
    return json.dumps(payload, ensure_ascii=False)


def entry_meta_from_json(text: str) -> tuple[Service, Account]:
    """Parse Accnary.Meta; apply migrations for older supported versions."""
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MetaFormatError(f"Accnary.Meta is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise MetaFormatError("Accnary.Meta is not a JSON object")

    version = raw.get("schema_version")
    if not isinstance(version, int):
        raise MetaFormatError("Accnary.Meta has no integer schema_version")
    if version > SCHEMA_VERSION:
        raise MetaFormatError(
            f"Accnary.Meta schema {version} is newer than supported "
            f"{SCHEMA_VERSION} - refusing to load as writable"
        )
    if version < SCHEMA_VERSION:
        raw = migrate_raw_meta(raw, version)

    service_block = raw.get("service")
    account_block = raw.get("account")
    if not isinstance(service_block, dict) or not isinstance(account_block, dict):
        raise MetaFormatError("Accnary.Meta misses service/account blocks")
    return service_from_block(service_block), account_from_block(account_block)


# ---------------------------------------------------------------------------
# Identity registry entry
# ---------------------------------------------------------------------------

_IDENTITY_KEYS = frozenset({"uuid", "kind", "label", "value", "notes"})


def registry_meta_to_json(identities: list[Identity]) -> str:
    items = []
    for i in identities:
        item = {
            "uuid": i.uuid,
            "kind": i.kind.value,
            "label": i.label,
            "value": i.value,
            "notes": i.notes,
        }
        extra = getattr(i, "_extra", {})
        item.update({k: v for k, v in extra.items() if k not in item})
        items.append(item)
    payload = {"schema_version": SCHEMA_VERSION, "identities": items}
    return json.dumps(payload, ensure_ascii=False)


def registry_meta_from_json(text: str) -> list[Identity]:
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MetaFormatError(f"registry Accnary.Meta is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise MetaFormatError("registry Accnary.Meta is not a JSON object")
    version = raw.get("schema_version")
    if not isinstance(version, int):
        raise MetaFormatError("registry Accnary.Meta has no integer schema_version")
    if version > SCHEMA_VERSION:
        raise MetaFormatError(
            f"registry schema {version} is newer than supported {SCHEMA_VERSION}"
        )
    if version < SCHEMA_VERSION:
        raw = migrate_raw_meta(raw, version)
    items = raw.get("identities", [])
    if not isinstance(items, list):
        raise MetaFormatError("identities must be a list")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise MetaFormatError("identity entry is not an object")
        extra = {k: v for k, v in item.items() if k not in _IDENTITY_KEYS}
        result.append(
            Identity(
                uuid=_as_str(item.get("uuid")),
                kind=_enum_or(IdentityKind, item.get("kind"), IdentityKind.OTHER),
                label=_as_str(item.get("label")),
                value=_as_str(item.get("value")),
                notes=_as_str(item.get("notes")),
                _extra=extra,
            )
        )
    return result


def read_schema_version(properties: dict) -> int | None:
    """Schema version from a custom-properties dict; None when absent/invalid."""
    raw = properties.get(SCHEMA_CUSTOM_KEY)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None
