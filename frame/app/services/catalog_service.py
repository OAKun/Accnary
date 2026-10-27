# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:10
# @Modified  : 2026-10-25 20:08
# @Python    : 3.14.9
# @Description: Accnary app / services / catalog_service
"""CatalogService: the single facade between the (future) UI and storage.

Owns the mapping between the Accnary data model and KDBX structures:

- KDBX group (under root)  == Service (platform); group name is the
  authoritative service name
- KDBX entry               == Account (one per login identity on the platform)
- entry standard fields    == username / password / URL / notes / title
- entry custom attribute   == "Accnary.Meta" JSON (schema v1) + schema marker
- root-level entry marked  == identity registry (all Identity objects once,
  with "Accnary.System" == "identity-registry"); accounts reference
  identities by stable UUID

Safety rules enforced here:
- entries/groups without Accnary structure are counted as unmanaged and
  preserved untouched (never rewritten or deleted by Accnary)
- a too-new Accnary schema version flips the catalog read-only and refuses
  saving so newer fields cannot be dropped
- identities are never auto-merged; reverse lookup works by UUID
"""

from __future__ import annotations

import uuid as uuidlib
import json
import hashlib
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from pykeepass.entry import Entry
from pykeepass.group import Group

from app.errors import (
    AccountNotFoundError,
    BadCredentialsError,
    CatalogError,
    IdentityInUseError,
    MetaFormatError,
    ReservedKeyError,
    ServiceExistsError,
    ServiceNotFoundError,
    SchemaTooNewError,
    UnsupportedFormatError,
)
from app.models import (
    META_CUSTOM_KEY,
    RESERVED_CUSTOM_PREFIX,
    SCHEMA_CUSTOM_KEY,
    SCHEMA_VERSION,
    SYSTEM_MARKER_KEY,
    Account,
    Catalog,
    CustomField,
    Identity,
    IdentityKind,
    Service,
    ServiceType,
    entry_meta_from_json,
    entry_meta_to_json,
    read_schema_version,
    registry_meta_from_json,
    registry_meta_to_json,
)
from app.storage.vault import KdbxVault
from app.services.search_service import SearchIndex

_REGISTRY_TITLE = "Accnary Identity Registry"
_REGISTRY_NOTES = (
    "Accnary 系统条目：身份注册表（微信/QQ/手机号/邮箱等身份的唯一登记处，"
    "账户通过 UUID 引用这些身份）。请勿删除或重命名。"
)

_STANDARD_ENTRY_KEYS = frozenset({"Title", "UserName", "Password", "URL", "Notes"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_uuid() -> str:
    # uuid4 (random) for Accnary-generated identifiers; pykeepass entry/group
    # UUIDs come from the library itself.
    return str(uuidlib.uuid4())


class CatalogService:
    """High-level account catalog on top of one unlocked KdbxVault."""

    def __init__(self, vault: KdbxVault):
        self._vault = vault
        self.catalog = Catalog()
        self.search_index = SearchIndex()
        self._registry_entry: Entry | None = None
        self._entries_by_uuid: dict[str, Entry] = {}
        self._service_groups_by_uuid: dict[str, Group] = {}
        self._service_groups_by_name: dict[str, Group] = {}
        self._services_by_name: dict[str, Service] = {}
        self.load()

    # -- lifecycle -----------------------------------------------------------

    @classmethod
    def create_vault(cls, path: str | Path, password: str) -> "CatalogService":
        service = cls(KdbxVault.create(path, password))
        service._ensure_registry()
        service.save()
        return service

    @classmethod
    def open(cls, path: str | Path, password: str) -> "CatalogService":
        return cls(KdbxVault.unlock(path, password))

    @property
    def vault(self) -> KdbxVault:
        return self._vault

    @property
    def path(self) -> Path:
        return self._vault.path

    def lock(self) -> None:
        self._vault.lock()
        # spec: 锁定时清除搜索索引（RAM only）
        self.search_index.clear()
        self._registry_entry = None
        self.catalog = Catalog()
        self._entries_by_uuid.clear()
        self._service_groups_by_uuid.clear()
        self._service_groups_by_name.clear()
        self._services_by_name.clear()

    @property
    def is_locked(self) -> bool:
        return self._vault.is_locked

    def reopen(self) -> None:
        """Discard unsaved state and re-read the file from disk.

        The intended recovery path after ConflictError: reload the external
        changes, then redo edits on top. Requires the vault to be unlocked so
        the master password is available.
        """
        password = self._vault.kp.password
        self._vault = KdbxVault.unlock(self._vault.path, password)
        self.load()

    def save(self) -> None:
        """Write the whole catalog back (registry + all managed entries).

        The in-memory catalog is authoritative: every model mutation made
        through this facade (favorites, login methods, license edits, ...)
        is flushed here. Custom KDBX attributes are owned by their explicit
        set/remove methods and are not touched by the bulk sync.
        """
        self._check_writable()
        self._sync_registry()
        for service in self.catalog.services:
            for account in service.accounts:
                entry = self._entry_for_account(account.uuid)
                self._sync_entry(entry, service, account)
        self._vault.save(validator=self._check_writable)
        self.search_index.build(self.catalog)
        self._saved_digest = self._state_digest()

    def change_master_password(self, current_password: str, new_password: str) -> None:
        """Rotate the KDBX password after validating and flushing catalog state."""
        if current_password != self._vault.kp.password:
            raise BadCredentialsError("current master password is incorrect")
        if len(new_password) < 8:
            raise CatalogError("master password must be at least 8 characters")
        if new_password == current_password:
            raise CatalogError("new master password must differ from the current password")

        self._check_writable()
        if self.has_unsaved_changes:
            self.save()
        self._vault.change_master_password(new_password)
        self._saved_digest = self._state_digest()

    def _state_digest(self) -> bytes:
        digest = hashlib.sha256(self._vault.kp.xml())
        models = {"services": [asdict(s) for s in self.catalog.services],
                  "identities": [asdict(i) for i in self.catalog.identities]}
        digest.update(json.dumps(models, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for binary in self._vault.kp.binaries:
            digest.update(binary)
        return digest.digest()

    @property
    def has_unsaved_changes(self) -> bool:
        return not self.is_locked and self._state_digest() != self._saved_digest

    @contextmanager
    def mutation(self):
        """Roll back a failed UI command so a later save cannot commit it."""
        kp = self._vault.kp
        tree = deepcopy(kp.tree)
        catalog = deepcopy(self.catalog)
        registry_uuid = (
            str(self._registry_entry.uuid) if self._registry_entry is not None else None
        )
        try:
            yield
        except Exception:
            kp.payload.xml = tree
            self.catalog = catalog
            self._rebuild_lookup_indexes()
            self._registry_entry = (
                self._entries_by_uuid.get(registry_uuid) if registry_uuid else None
            )
            self.search_index.build(catalog)
            raise

    def _check_writable(self) -> None:
        """Veto for every mutating operation and every save.

        Refuses (a) vaults whose Accnary schema is newer than supported and
        (b) KDBX formats Accnary does not write (3.x legacy, 4.1+ features).
        Both refuse BEFORE any in-memory mutation happens.
        """
        if self.catalog.read_only:
            raise SchemaTooNewError(
                "vault metadata is newer than supported, malformed or ambiguous; "
                "saving is refused to avoid data loss"
            )
        if not self._vault.format_info.writable:
            fmt = self._vault.format_info
            raise UnsupportedFormatError(
                f"vault is KDBX {fmt.version[0]}.{fmt.version[1]} / {fmt.kdf} - "
                "read-only (Accnary only writes KDBX 4.0)"
            )

    # -- loading ---------------------------------------------------------------

    def load(self) -> None:
        kp = self._vault.kp
        root = kp.groups[0]
        catalog = Catalog()
        self._registry_entry = None
        # Inspect version guards before parsing: a future JSON payload cannot
        # be parsed by this version and must never be silently skipped writable.
        for entry in kp.entries:
            props = entry.custom_properties
            marker = read_schema_version(props)
            if marker is not None:
                catalog.schema_versions_seen.add(marker)
            meta = props.get(META_CUSTOM_KEY)
            if meta is not None:
                try:
                    raw = json.loads(meta)
                except (json.JSONDecodeError, TypeError):
                    continue  # preserved unmanaged; registry guard below is stricter
                version = raw.get("schema_version") if isinstance(raw, dict) else None
                if isinstance(version, int) and not isinstance(version, bool):
                    catalog.schema_versions_seen.add(version)
        entry_ids = [str(e.uuid) for e in kp.entries]
        group_ids = [str(g.uuid) for g in kp.groups]
        if len(set(entry_ids + group_ids)) != len(entry_ids + group_ids):
            catalog.read_only = True

        # identity registry: root-level entry carrying the system marker
        for entry in root.entries:
            if entry.custom_properties.get(SYSTEM_MARKER_KEY) == "identity-registry":
                if self._registry_entry is not None:
                    catalog.read_only = True
                    catalog.malformed_entries += 1
                    continue
                self._load_registry_entry(entry, catalog)
            else:
                catalog.unmanaged_entries += 1

        # services: every root subgroup except the recycle bin
        recycle_bin = kp.recyclebin_group
        for group in root.subgroups:
            if recycle_bin is not None and group.uuid == recycle_bin.uuid:
                continue
            catalog.services.append(self._load_service_group(group, catalog))

        self._postprocess_references(catalog)
        self.catalog = catalog
        self._rebuild_lookup_indexes()
        self.search_index.build(catalog)
        self._saved_digest = self._state_digest()

    def _rebuild_lookup_indexes(self) -> None:
        """Rebuild unlocked-session lookup maps from the current KDBX tree."""
        kp = self._vault.kp
        groups = kp.groups
        self._entries_by_uuid = {str(entry.uuid): entry for entry in kp.entries}
        self._service_groups_by_uuid = {str(group.uuid): group for group in groups}
        self._service_groups_by_name = {}
        for group in groups:
            self._service_groups_by_name.setdefault(group.name, group)
        self._services_by_name = {}
        for service in self.catalog.services:
            self._services_by_name.setdefault(service.name, service)

    def _load_registry_entry(self, entry: Entry, catalog: Catalog) -> None:
        self._registry_entry = entry
        meta = entry.custom_properties.get(META_CUSTOM_KEY)
        if meta is None:
            return  # marker survived but meta was wiped; keep empty registry
        try:
            catalog.identities = registry_meta_from_json(meta)
        except MetaFormatError:
            catalog.malformed_entries += 1
            catalog.read_only = True

    def _load_service_group(self, group: Group, catalog: Catalog) -> Service:
        service = Service(name=group.name, uuid=str(group.uuid), notes=group.notes or "")
        for entry in group.entries:
            meta_json = entry.custom_properties.get(META_CUSTOM_KEY)
            if meta_json is None:
                catalog.unmanaged_entries += 1
                continue
            try:
                meta_service, account = entry_meta_from_json(meta_json)
            except MetaFormatError:
                catalog.malformed_entries += 1
                continue

            catalog.schema_versions_seen.add(
                read_schema_version(entry.custom_properties) or 0
            )
            # The group name wins for the service name (KeePassXC renames stay
            # meaningful). Other service attributes come from the first entry
            # that carries meta; later entries in the same group keep their own
            # meta blocks (per-entry authority) but do not overwrite the group.
            if not service.accounts:
                service.aliases = meta_service.aliases
                service.type = meta_service.type
                service.urls = meta_service.urls
                service.login_urls = meta_service.login_urls
                service.category = meta_service.category
                service.tags = meta_service.tags
                if not service.notes:
                    service.notes = meta_service.notes
                service._extra = meta_service._extra or service._extra

            self._hydrate_account_from_entry(entry, account)
            service.accounts.append(account)
        return service

    def _hydrate_account_from_entry(self, entry: Entry, account: Account) -> None:
        """Fill account attributes whose source of truth is the entry itself."""
        account.username = entry.username or ""
        account.password = entry.password or ""
        account.primary_url = entry.url or ""
        account.notes = entry.notes or ""
        if account.uuid != str(entry.uuid):
            # entry UUID is authoritative for identity across software
            account.uuid = str(entry.uuid)
        account.created_at = entry.ctime.isoformat() if entry.ctime else None
        account.modified_at = entry.mtime.isoformat() if entry.mtime else None
        reserved = {META_CUSTOM_KEY, SCHEMA_CUSTOM_KEY, SYSTEM_MARKER_KEY}
        account.custom_fields = [
            CustomField(
                key=key,
                value=value,
                protected=bool(entry.is_custom_property_protected(key)),
            )
            for key, value in sorted(entry.custom_properties.items())
            if key not in reserved
        ]

    def _postprocess_references(self, catalog: Catalog) -> None:
        """Flag too-new schemas and dangling identity references."""
        if catalog.schema_versions_seen and max(catalog.schema_versions_seen) > SCHEMA_VERSION:
            catalog.read_only = True
        known = {i.uuid for i in catalog.identities}
        if len(known) != len(catalog.identities):
            catalog.read_only = True
        for account in catalog.all_accounts():
            refs = {lm.identity_ref for lm in account.login_methods if lm.identity_ref}
            refs |= {b.identity_ref for b in account.identity_bindings if b.identity_ref}
            catalog.dangling_identity_refs |= refs - known

    # -- registry ---------------------------------------------------------------

    def _ensure_registry(self) -> None:
        if self._registry_entry is not None:
            return
        root = self._vault.kp.groups[0]
        entry = self._vault.kp.add_entry(
            root,
            _REGISTRY_TITLE,
            username="",
            password="",
            notes=_REGISTRY_NOTES,
        )
        entry.set_custom_property(SYSTEM_MARKER_KEY, "identity-registry")
        entry.set_custom_property(SCHEMA_CUSTOM_KEY, str(SCHEMA_VERSION))
        entry.set_custom_property(META_CUSTOM_KEY, registry_meta_to_json([]))
        self._registry_entry = entry
        self._entries_by_uuid[str(entry.uuid)] = entry

    def _sync_registry(self) -> None:
        self._ensure_registry()
        current = self._registry_entry.custom_properties.get(META_CUSTOM_KEY)
        payload = json.loads(current) if current else {}
        payload.update(json.loads(registry_meta_to_json(self.catalog.identities)))
        self._registry_entry.set_custom_property(
            META_CUSTOM_KEY, json.dumps(payload, ensure_ascii=False)
        )
        self._registry_entry.set_custom_property(SCHEMA_CUSTOM_KEY, str(SCHEMA_VERSION))

    # -- account/entry sync ------------------------------------------------------

    def _entry_for_account(self, account_uuid: str) -> Entry:
        normalized_uuid = str(uuidlib.UUID(account_uuid))
        entry = self._entries_by_uuid.get(normalized_uuid)
        if entry is None:
            entry = self._vault.kp.find_entries(
                uuid=uuidlib.UUID(normalized_uuid), first=True
            )
            if entry is not None:
                self._entries_by_uuid[normalized_uuid] = entry
        if entry is None:
            raise AccountNotFoundError(f"no KDBX entry for account {account_uuid}")
        return entry

    def _service_group(self, service: Service) -> Group:
        kp = self._vault.kp
        if service.uuid:
            group = self._service_groups_by_uuid.get(service.uuid)
            if group is None:
                group = kp.find_groups(
                    uuid=uuidlib.UUID(service.uuid), first=True
                )
            if group is not None:
                self._service_groups_by_uuid[str(group.uuid)] = group
                self._service_groups_by_name.setdefault(group.name, group)
                return group
        group = self._service_groups_by_name.get(service.name)
        if group is None:
            raise ServiceNotFoundError(f"no group for service {service.name!r}")
        service.uuid = str(group.uuid)
        return group

    def _sync_entry(self, entry: Entry, service: Service, account: Account) -> None:
        """Write one account into its entry (standard fields + meta)."""
        current = entry.custom_properties.get(META_CUSTOM_KEY)
        payload = json.loads(current) if current else {}
        updated = json.loads(entry_meta_to_json(service, account))
        old_service = payload.get("service", {})
        # Keep per-entry extensions even when other platform fields are shared.
        service_block = dict(old_service)
        service_block.update({k: v for k, v in updated["service"].items()
                              if k not in service._extra or k not in old_service})
        updated["service"] = service_block
        old_account = payload.get("account", {})
        old_methods = {lm.get("uuid"): lm for lm in old_account.get("login_methods", [])}
        updated["account"]["login_methods"] = [
            {**old_methods.get(lm["uuid"], {}), **lm} for lm in updated["account"]["login_methods"]
        ]
        updated["account"]["license"] = {
            **old_account.get("license", {}), **updated["account"]["license"]
        }
        payload.update(updated)
        if entry.password != account.password or entry.username != account.username:
            entry.save_history()
        entry.title = service.name
        entry.username = account.username
        entry.password = account.password
        entry.url = account.primary_url
        entry.notes = account.notes
        entry.set_custom_property(META_CUSTOM_KEY, json.dumps(payload, ensure_ascii=False))
        entry.set_custom_property(SCHEMA_CUSTOM_KEY, str(SCHEMA_VERSION))

    # -- service operations --------------------------------------------------------

    def add_service(
        self,
        name: str,
        *,
        type: ServiceType = ServiceType.WEBSITE,
        aliases: list[str] | None = None,
        urls: list[str] | None = None,
        login_urls: list[str] | None = None,
        category: str = "",
        tags: list[str] | None = None,
        notes: str = "",
    ) -> Service:
        self._check_writable()
        name = name.strip()
        if not name:
            raise CatalogError("service name must not be empty")
        if name in self._services_by_name:
            raise ServiceExistsError(f"service {name!r} already exists")
        group = self._vault.kp.add_group(self._vault.kp.groups[0], name, notes=notes)
        service = Service(
            name=name,
            aliases=list(aliases or []),
            type=type,
            urls=list(urls or []),
            login_urls=list(login_urls or []),
            category=category,
            tags=list(tags or []),
            notes=notes,
            uuid=str(group.uuid),
        )
        self.catalog.services.append(service)
        self._services_by_name[name] = service
        self._service_groups_by_uuid[str(group.uuid)] = group
        self._service_groups_by_name.setdefault(group.name, group)
        return service

    def rename_service(self, service: Service, new_name: str) -> None:
        """Rename a service: group title + every entry title/meta block."""
        self._check_writable()
        new_name = new_name.strip()
        if not new_name:
            raise CatalogError("service name must not be empty")
        other = self._services_by_name.get(new_name)
        if other is not None and other is not service:
            raise ServiceExistsError(f"service {new_name!r} already exists")
        group = self._service_group(service)
        service.name = new_name
        group.name = new_name
        for account in service.accounts:
            entry = self._entry_for_account(account.uuid)
            self._sync_entry(entry, service, account)
        self._rebuild_lookup_indexes()

    # -- account operations ------------------------------------------------------

    def add_account(self, service: Service | str, account: Account) -> Account:
        """Add an account under a service (creating the service when given a name).

        ``account.login_methods`` / ``identity_bindings`` / ``license`` are taken
        as-is; ``account.uuid`` is assigned from the new KDBX entry.
        """
        self._check_writable()
        if isinstance(service, Service):
            existing = self._services_by_name.get(service.name)
            if existing is not None:
                service = existing
        if isinstance(service, str):
            existing = self._services_by_name.get(service)
            service = existing or self.add_service(service)
        try:
            group = self._service_group(service)
        except ServiceNotFoundError:
            # a freshly assembled Service object (e.g. from the editor):
            # create its group on first account
            group = self._vault.kp.add_group(
                self._vault.kp.groups[0], service.name, notes=service.notes
            )
            service.uuid = str(group.uuid)
            self.catalog.services.append(service)
            self._services_by_name[service.name] = service
            self._service_groups_by_uuid[str(group.uuid)] = group
            self._service_groups_by_name.setdefault(group.name, group)
        self._validate_custom_keys(account)
        entry = self._vault.kp.add_entry(
            group,
            service.name,
            username=account.username,
            password=account.password,
            url=account.primary_url,
            notes=account.notes,
        )
        account.uuid = str(entry.uuid)
        self._entries_by_uuid[account.uuid] = entry
        for field in account.custom_fields:
            self._write_custom_field(entry, field)
        self._sync_entry(entry, service, account)
        service.accounts.append(account)
        return account

    def update_account(self, account: Account) -> None:
        """Persist changes to an account's standard fields / meta structures."""
        self._check_writable()
        located = self.catalog.find_account(account.uuid)
        if located is None:
            raise AccountNotFoundError(account.uuid)
        service, stored = located
        if stored is not account:
            # keep the model object graph pointing at the stored instance
            self._copy_into(account, stored)
            account = stored
        entry = self._entry_for_account(account.uuid)
        self._sync_entry(entry, service, account)
        self._hydrate_account_from_entry(entry, account)

    def delete_account(self, account_uuid: str) -> None:
        """Send an account to the vault's recycle bin (recoverable)."""
        self._check_writable()
        located = self.catalog.find_account(account_uuid)
        if located is None:
            raise AccountNotFoundError(account_uuid)
        service, account = located
        entry = self._entry_for_account(account_uuid)
        self._vault.kp.trash_entry(entry)
        service.accounts.remove(account)

    def restore_account(self, account_uuid: str) -> Account:
        """Bring a trashed account back into its service group."""
        self._check_writable()
        kp = self._vault.kp
        recycle_bin = kp.recyclebin_group
        if recycle_bin is None:
            raise AccountNotFoundError(f"{account_uuid} (recycle bin is empty)")
        entry = kp.find_entries(
            uuid=uuidlib.UUID(account_uuid), first=True, group=recycle_bin
        )
        if entry is None:
            raise AccountNotFoundError(f"{account_uuid} not found in recycle bin")
        meta_json = entry.custom_properties.get(META_CUSTOM_KEY)
        if meta_json is None:
            raise CatalogError("refusing to restore a non-Accnary entry")
        meta_service, account = entry_meta_from_json(meta_json)
        service = self.catalog.find_service(meta_service.name)
        if service is None:
            service = self.add_service(
                meta_service.name,
                type=meta_service.type,
                aliases=meta_service.aliases,
                urls=meta_service.urls,
                login_urls=meta_service.login_urls,
                category=meta_service.category,
                tags=meta_service.tags,
            )
        kp.move_entry(entry, self._service_group(service))
        self._hydrate_account_from_entry(entry, account)
        service.accounts.append(account)
        return account

    def set_favorite(self, account_uuid: str, favorite: bool) -> None:
        self._check_writable()
        located = self.catalog.find_account(account_uuid)
        if located is None:
            raise AccountNotFoundError(account_uuid)
        located[1].favorite = bool(favorite)

    def touch_last_used(self, account_uuid: str) -> None:
        self._check_writable()
        located = self.catalog.find_account(account_uuid)
        if located is None:
            raise AccountNotFoundError(account_uuid)
        located[1].last_used_at = _now_iso()

    def mark_used_and_save(self, account_uuid: str) -> None:
        """Record a use (e.g. credential copied) and persist it immediately.

        Raises whatever save() raises on conflict/format problems - callers
        in the UI treat a failed recency write as non-fatal.
        """
        self.touch_last_used(account_uuid)
        self.save()

    # -- custom fields (standard KDBX attributes, KeePassXC-visible) -----------

    def set_custom_field(
        self, account_uuid: str, key: str, value: str, *, protected: bool = False
    ) -> None:
        self._check_writable()
        key = key.strip()
        if not key:
            raise ReservedKeyError("custom field key must not be empty")
        if key.startswith(RESERVED_CUSTOM_PREFIX) or key in _STANDARD_ENTRY_KEYS:
            raise ReservedKeyError(f"{key!r} is a reserved key")
        entry = self._entry_for_account(account_uuid)
        entry.set_custom_property(key, value, protect=protected)
        located = self.catalog.find_account(account_uuid)
        assert located is not None
        account = located[1]
        account.custom_fields = [
            f for f in account.custom_fields if f.key != key
        ]
        account.custom_fields.append(CustomField(key=key, value=value, protected=protected))

    def remove_custom_field(self, account_uuid: str, key: str) -> None:
        self._check_writable()
        if key.startswith(RESERVED_CUSTOM_PREFIX) or key in _STANDARD_ENTRY_KEYS:
            raise ReservedKeyError(f"{key!r} is a reserved key")
        entry = self._entry_for_account(account_uuid)
        if entry.custom_properties.get(key) is None:
            raise CatalogError(f"custom field {key!r} does not exist")
        entry.delete_custom_property(key)
        located = self.catalog.find_account(account_uuid)
        assert located is not None
        located[1].custom_fields = [
            f for f in located[1].custom_fields if f.key != key
        ]

    @staticmethod
    def _validate_custom_keys(account: Account) -> None:
        for field in account.custom_fields:
            if field.key.startswith(RESERVED_CUSTOM_PREFIX) or field.key in _STANDARD_ENTRY_KEYS:
                raise ReservedKeyError(f"{field.key!r} is a reserved key")

    @staticmethod
    def _write_custom_field(entry: Entry, field: CustomField) -> None:
        entry.set_custom_property(field.key, field.value, protect=field.protected)

    # -- identities ---------------------------------------------------------------

    def register_identity(
        self,
        kind: IdentityKind,
        label: str = "",
        value: str = "",
        notes: str = "",
    ) -> Identity:
        """Register an identity once; accounts reference it by UUID."""
        self._check_writable()
        identity = Identity(
            uuid=_new_uuid(), kind=kind, label=label, value=value, notes=notes
        )
        self.catalog.identities.append(identity)
        return identity

    def remove_identity(self, identity_uuid: str, *, force: bool = False) -> None:
        """Remove an identity; refuses while accounts still reference it.

        ``force=True`` is for the UI's explicit "detach references" confirmation
        path - references then dangle and are reported on next load.
        """
        self._check_writable()
        identity = self.catalog.identity(identity_uuid)
        if identity is None:
            raise AccountNotFoundError(f"identity {identity_uuid}")
        referencing = self.catalog.accounts_referencing_identity(identity_uuid)
        recycle_bin = self._vault.kp.recyclebin_group
        if recycle_bin is not None:
            for entry in recycle_bin.entries:
                meta = entry.custom_properties.get(META_CUSTOM_KEY)
                if meta is None:
                    continue
                try:
                    _service, account = entry_meta_from_json(meta)
                except MetaFormatError:
                    continue
                refs = {m.identity_ref for m in account.login_methods}
                refs.update(b.identity_ref for b in account.identity_bindings)
                if identity_uuid in refs:
                    referencing.append(account)
        if referencing and not force:
            raise IdentityInUseError(
                f"{len(referencing)} account(s) still reference this identity: "
                + ", ".join(sorted(a.alias or a.username or a.uuid for a in referencing))
            )
        self.catalog.identities.remove(identity)

    def identity(self, identity_uuid: str):
        """Identity object by UUID, or None (facade over the catalog)."""
        return self.catalog.identity(identity_uuid)

    def accounts_referencing_identity(self, identity_uuid: str) -> list[Account]:
        return self.catalog.accounts_referencing_identity(identity_uuid)

    def identity_label(self, identity_ref: str | None) -> str:
        """Human-readable label for an identity reference (UI helper)."""
        if not identity_ref:
            return ""
        identity = self.catalog.identity(identity_ref)
        if identity is None:
            return f"<missing identity {identity_ref}>"
        return identity.label or identity.value or identity.uuid

    # -- helpers ----------------------------------------------------------------

    @staticmethod
    def _copy_into(source: Account, target: Account) -> None:
        for name in (
            "username",
            "password",
            "primary_url",
            "notes",
            "user_id",
            "alias",
            "email",
            "phone",
            "favorite",
            "last_used_at",
            "login_methods",
            "identity_bindings",
            "license",
            "_extra",
        ):
            setattr(target, name, getattr(source, name))
