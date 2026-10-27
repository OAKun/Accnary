"""Phase 1 T6: CatalogService functional suite - services, accounts,
identities, reverse lookup, recycle bin, favorites, schema guard."""

from __future__ import annotations

import uuid as uuidlib

import pytest

from app.errors import (
    AccountNotFoundError,
    CatalogError,
    IdentityInUseError,
    ReservedKeyError,
    SchemaTooNewError,
    ServiceExistsError,
)
from app.models import (
    Account,
    Binding,
    BindingRole,
    IdentityKind,
    LicenseInfo,
    LicenseMode,
    LoginMethod,
    LoginMethodType,
    ServiceType,
)
from app.services import CatalogService

from .conftest import TEST_PASSWORD


# ---------------------------------------------------------------------------
# services & accounts
# ---------------------------------------------------------------------------

def test_duplicate_service_rejected(make_empty_catalog):
    svc = make_empty_catalog()
    svc.add_service("Cloud")
    with pytest.raises(ServiceExistsError):
        svc.add_service("Cloud")


def test_add_account_by_service_name_autocreates_service(make_empty_catalog):
    svc = make_empty_catalog()
    account = Account(username="u1")
    svc.add_account("AutoCreated", account)
    assert svc.catalog.find_service("AutoCreated") is not None
    svc.save()
    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert [a.username for a in reopened.catalog.all_accounts()] == ["u1"]


def test_two_accounts_same_service_roundtrip(make_full_catalog):
    svc, first = make_full_catalog()
    service = svc.catalog.services[0]
    second = Account(username="second", password="pw2", alias="备用号")
    svc.add_account(service, second)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.services[0].accounts
    assert {a.username for a in loaded} == {"demo-user", "second"}
    assert len({a.uuid for a in loaded}) == 2
    assert first.uuid != second.uuid


def test_account_without_password_is_valid(make_empty_catalog):
    svc = make_empty_catalog()
    account = Account(username="sso-only-user")  # no password, no url
    svc.add_account("CorpSSO", account)
    svc.save()
    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert loaded.password == ""
    assert loaded.primary_url == ""


def test_update_account_persists_all_sections(full_catalog):
    svc, account = full_catalog
    account.username = "renamed-user"
    account.primary_url = "https://new.example.com"
    account.license = LicenseInfo(
        mode=LicenseMode.PERPETUAL, license_key="NEW-KEY", order_no="ORD-9"
    )
    account.login_methods.append(
        LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.PHONE_SMS)
    )
    svc.update_account(account)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert loaded.username == "renamed-user"
    assert loaded.primary_url == "https://new.example.com"
    assert loaded.license.mode == LicenseMode.PERPETUAL
    assert loaded.license.license_key == "NEW-KEY"
    assert {lm.type for lm in loaded.login_methods} == {
        LoginMethodType.PASSWORD,
        LoginMethodType.WECHAT_OAUTH,
        LoginMethodType.PHONE_SMS,
    }


def test_rename_service_updates_group_and_entries(full_catalog):
    svc, account = full_catalog
    service = svc.catalog.services[0]
    svc.rename_service(service, "RenamedCloud")
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert reopened.catalog.services[0].name == "RenamedCloud"
    entry = reopened.vault.kp.find_entries(
        uuid=uuidlib.UUID(account.uuid), first=True
    )
    assert entry.title == "RenamedCloud"
    # meta block service name follows too
    assert "RenamedCloud" in entry.custom_properties["Accnary.Meta"]


def test_rename_to_existing_name_rejected(full_catalog):
    svc, _ = full_catalog
    svc.add_service("Other")
    with pytest.raises(ServiceExistsError):
        svc.rename_service(svc.catalog.services[0], "Other")


# ---------------------------------------------------------------------------
# identities
# ---------------------------------------------------------------------------

def test_identity_registry_and_reverse_lookup(full_catalog):
    svc, account = full_catalog
    wechat_uuid = account.login_methods[1].identity_ref

    # a second account on a different service binds the same WeChat identity
    other = Account(username="editor-user")
    other.login_methods = [
        LoginMethod(
            uuid=str(uuidlib.uuid4()),
            type=LoginMethodType.WECHAT_OAUTH,
            identity_ref=wechat_uuid,
        )
    ]
    svc.add_account("EditorApp", other)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    hits = reopened.accounts_referencing_identity(wechat_uuid)
    assert {a.username for a in hits} == {"demo-user", "editor-user"}
    assert reopened.identity_label(wechat_uuid) == "微信主号"


def test_remove_identity_blocked_while_referenced(full_catalog):
    svc, account = full_catalog
    wechat_uuid = account.login_methods[1].identity_ref
    with pytest.raises(IdentityInUseError):
        svc.remove_identity(wechat_uuid)


def test_remove_identity_force_leaves_dangling_flag(full_catalog):
    svc, account = full_catalog
    wechat_uuid = account.login_methods[1].identity_ref
    svc.remove_identity(wechat_uuid, force=True)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert wechat_uuid in reopened.catalog.dangling_identity_refs
    # account data itself is untouched
    assert reopened.catalog.all_accounts()[0].username == "demo-user"


def test_dangling_ref_does_not_break_load(full_catalog):
    svc, account = full_catalog
    # simulate the registry meta being wiped by raw KDBX access; a plain
    # vault save (no catalog sync) persists the damage
    registry = None
    for entry in svc.vault.kp.groups[0].entries:
        if entry.custom_properties.get("Accnary.System") == "identity-registry":
            registry = entry
    assert registry is not None
    registry.delete_custom_property("Accnary.Meta")
    svc.vault.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert reopened.catalog.identities == []
    assert account.login_methods[1].identity_ref in reopened.catalog.dangling_identity_refs
    # a wiped registry reads as "empty", not malformed - the dangling refs
    # above are the signal that something is wrong
    assert reopened.catalog.malformed_entries == 0


# ---------------------------------------------------------------------------
# recycle bin
# ---------------------------------------------------------------------------

def test_delete_and_restore_account(full_catalog):
    svc, account = full_catalog
    svc.delete_account(account.uuid)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert reopened.catalog.all_accounts() == []
    restored = reopened.restore_account(account.uuid)
    assert restored.uuid == account.uuid
    reopened.save()

    final = CatalogService.open(str(reopened.path), TEST_PASSWORD)
    assert {a.username for a in final.catalog.all_accounts()} == {"demo-user"}
    # relationships survived the trip
    loaded = final.catalog.all_accounts()[0]
    assert loaded.license.order_no == "TEST-ORDER-0001"
    assert len(loaded.login_methods) == 2


def test_delete_unknown_account_raises(full_catalog):
    svc, _ = full_catalog
    with pytest.raises(AccountNotFoundError):
        svc.delete_account(str(uuidlib.uuid4()))


# ---------------------------------------------------------------------------
# favorites / custom fields / misc
# ---------------------------------------------------------------------------

def test_favorite_and_last_used_persist(full_catalog):
    svc, account = full_catalog
    svc.set_favorite(account.uuid, True)
    svc.touch_last_used(account.uuid)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert loaded.favorite is True
    assert loaded.last_used_at is not None


def test_custom_fields_set_remove_and_persistence(full_catalog):
    svc, account = full_catalog
    svc.set_custom_field(account.uuid, "API Token", "tok-123", protected=True)
    svc.set_custom_field(account.uuid, "备注二", "中文值")
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    fields = {f.key: f for f in loaded.custom_fields}
    assert fields["API Token"].value == "tok-123"
    assert fields["API Token"].protected is True
    assert fields["备注二"].value == "中文值"
    assert fields["备注二"].protected is False

    reopened.remove_custom_field(loaded.uuid, "API Token")
    reopened.save()
    final = CatalogService.open(str(reopened.path), TEST_PASSWORD)
    keys = {f.key for f in final.catalog.all_accounts()[0].custom_fields}
    assert "API Token" not in keys
    assert "备注二" in keys


def test_custom_field_reserved_and_missing(full_catalog):
    svc, account = full_catalog
    with pytest.raises(ReservedKeyError):
        svc.set_custom_field(account.uuid, "Accnary.Custom", "x")
    with pytest.raises(CatalogError):
        svc.remove_custom_field(account.uuid, "NotExists")


# ---------------------------------------------------------------------------
# schema guard
# ---------------------------------------------------------------------------

def test_too_new_schema_flips_read_only(full_catalog):
    svc, account = full_catalog
    entry = svc.vault.kp.find_entries(uuid=uuidlib.UUID(account.uuid), first=True)
    entry.set_custom_property("Accnary.SchemaVersion", "999")
    # bypass the catalog sync (which would rewrite the marker) and let the
    # vault write the tampered marker to disk
    svc.vault.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert reopened.catalog.read_only is True
    with pytest.raises(SchemaTooNewError):
        reopened.save()
    with pytest.raises(SchemaTooNewError):
        reopened.add_service("Blocked")


def test_lock_clears_access(full_catalog):
    svc, account = full_catalog
    svc.lock()
    with pytest.raises(Exception):
        _ = svc.vault.kp
