"""Phase 1 T1: Accnary.Meta serialization - schema v1 roundtrips, migrations,
unknown-key preservation, and enum tolerance."""

from __future__ import annotations

import json

import pytest

from app.errors import MetaFormatError
from app.models import (
    SCHEMA_VERSION,
    Account,
    Binding,
    BindingRole,
    Identity,
    IdentityKind,
    LicenseInfo,
    LicenseMode,
    LoginMethod,
    LoginMethodType,
    Service,
    ServiceType,
    entry_meta_from_json,
    entry_meta_to_json,
    read_schema_version,
    register_migration,
    registry_meta_from_json,
    registry_meta_to_json,
)


def _rich_objects():
    service = Service(
        name="DemoCloud",
        aliases=["DC"],
        type=ServiceType.CLOUD_SERVICE,
        urls=["https://cloud.example.com"],
        login_urls=["https://cloud.example.com/login"],
        category="云服务",
        tags=["网盘", "常用"],
        notes="svc notes",
    )
    account = Account(
        username="demo-user",
        user_id="u-123",
        alias="主账号",
        email="a@example.com",
        phone="+86-130-0000-0000",
        favorite=True,
        last_used_at="2026-10-24T10:00:00+00:00",
        login_methods=[
            LoginMethod(uuid="lm-1", type=LoginMethodType.PASSWORD),
            LoginMethod(
                uuid="lm-2",
                type=LoginMethodType.WECHAT_OAUTH,
                identity_ref="wechat-1",
                note="扫码",
            ),
        ],
        identity_bindings=[
            Binding(identity_ref="phone-1", role=BindingRole.LOGIN_PHONE),
            Binding(identity_ref="mail-1", role=BindingRole.RECOVERY_EMAIL),
        ],
        license=LicenseInfo(
            mode=LicenseMode.SUBSCRIPTION,
            purchase_date="2026-01-01",
            channel="官网",
            order_no="T-1",
            license_key="KEY-XYZ",
            expires="2027-01-01",
            device_limit=3,
            evidence="订单邮件",
            notes="lic notes",
        ),
    )
    return service, account


def test_entry_meta_roundtrip_is_lossless():
    service, account = _rich_objects()
    text = entry_meta_to_json(service, account)
    loaded_service, loaded_account = entry_meta_from_json(text)
    assert entry_meta_to_json(loaded_service, loaded_account) == text
    assert json.loads(text)["schema_version"] == SCHEMA_VERSION


def test_unknown_keys_survive_roundtrip():
    service, account = _rich_objects()
    raw = json.loads(entry_meta_to_json(service, account))
    raw["service"]["future_service_field"] = {"whatever": [1, 2, 3]}
    raw["account"]["future_account_field"] = "new in 1.x"
    text = json.dumps(raw, ensure_ascii=False)

    loaded_service, loaded_account = entry_meta_from_json(text)
    re_emitted = json.loads(entry_meta_to_json(loaded_service, loaded_account))
    assert re_emitted["service"]["future_service_field"] == {"whatever": [1, 2, 3]}
    assert re_emitted["account"]["future_account_field"] == "new in 1.x"


def test_unknown_enum_values_fall_back():
    service, account = _rich_objects()
    raw = json.loads(entry_meta_to_json(service, account))
    raw["service"]["type"] = "hoverboard"
    raw["account"]["login_methods"][0]["type"] = "carrier_pigeon"
    text = json.dumps(raw, ensure_ascii=False)

    loaded_service, loaded_account = entry_meta_from_json(text)
    assert loaded_service.type == ServiceType.OTHER
    assert loaded_account.login_methods[0].type == LoginMethodType.CUSTOM


def test_license_device_limit_none_and_bool_rejected():
    account = Account()
    account.license = LicenseInfo(mode=LicenseMode.PERPETUAL, device_limit=None)
    text = entry_meta_to_json(Service(name="S"), account)
    loaded = entry_meta_from_json(text)[1]
    assert loaded.license.device_limit is None

    raw = json.loads(text)
    raw["account"]["license"]["device_limit"] = True  # bool must not become 1
    loaded2 = entry_meta_from_json(json.dumps(raw))[1]
    assert loaded2.license.device_limit is None


def test_schema_too_new_refused():
    service, account = _rich_objects()
    raw = json.loads(entry_meta_to_json(service, account))
    raw["schema_version"] = SCHEMA_VERSION + 999
    with pytest.raises(MetaFormatError):
        entry_meta_from_json(json.dumps(raw))


def test_migration_hook_applied():
    applied = []

    def migrate_v0(raw: dict) -> dict:
        applied.append(True)
        raw = dict(raw)
        raw["schema_version"] = 1
        raw.setdefault("service", {"name": "migrated"})
        raw.setdefault("account", {"uuid": "x"})
        return raw

    register_migration(0, migrate_v0)
    try:
        # no "account" key: the migration must supply it
        text = json.dumps(
            {"schema_version": 0, "service": {"name": "Old"}},
            ensure_ascii=False,
        )
        service, account = entry_meta_from_json(text)
        assert applied == [True]
        assert service.name == "Old"
        assert account.uuid == "x"
    finally:
        # do not leak the fake migration into other tests
        from app.models import serialization

        serialization._MIGRATIONS.pop(0, None)


def test_registry_roundtrip():
    identities = [
        Identity(uuid="i-1", kind=IdentityKind.WECHAT, label="微信主号", value="wx_01"),
        Identity(uuid="i-2", kind=IdentityKind.EMAIL, label="找回邮箱", value="r@x.com"),
    ]
    text = registry_meta_to_json(identities)
    loaded = registry_meta_from_json(text)
    assert [(i.uuid, i.kind, i.value) for i in loaded] == [
        ("i-1", IdentityKind.WECHAT, "wx_01"),
        ("i-2", IdentityKind.EMAIL, "r@x.com"),
    ]
    assert json.loads(text)["schema_version"] == SCHEMA_VERSION


def test_registry_unknown_keys_survive():
    raw = {
        "schema_version": 1,
        "identities": [{"uuid": "i-1", "kind": "wechat", "future": [1]}],
    }
    loaded = registry_meta_from_json(json.dumps(raw))
    assert loaded[0]._extra == {"future": [1]}
    re_emitted = json.loads(registry_meta_to_json(loaded))
    assert re_emitted["identities"][0]["future"] == [1]


def test_read_schema_version():
    assert read_schema_version({"Accnary.SchemaVersion": "1"}) == 1
    assert read_schema_version({"Accnary.SchemaVersion": "x"}) is None
    assert read_schema_version({}) is None


def test_invalid_json_raises_meta_format_error():
    with pytest.raises(MetaFormatError):
        entry_meta_from_json("{not json")
