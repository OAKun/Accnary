"""Shared fixtures for Phase 1 tests. All data is fictional."""

from __future__ import annotations

import uuid as uuidlib

import pytest

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

TEST_PASSWORD = "phase1-test-pass"


@pytest.fixture
def vault_path(tmp_path):
    return str(tmp_path / "vault.kdbx")


@pytest.fixture
def make_empty_catalog(vault_path):
    """Factory: fresh vault with registry only; returns CatalogService."""

    def _make(path=None, password: str = TEST_PASSWORD) -> CatalogService:
        return CatalogService.create_vault(path or vault_path, password)

    return _make


@pytest.fixture
def make_full_catalog(make_empty_catalog):
    """Factory: vault with one service and one fully-populated account."""

    def _make(password: str = TEST_PASSWORD) -> tuple[CatalogService, Account]:
        svc = make_empty_catalog(password=password)
        wechat = svc.register_identity(
            IdentityKind.WECHAT, label="微信主号", value="wx_acc_01"
        )
        phone = svc.register_identity(
            IdentityKind.PHONE, label="手机号", value="+86-130-0000-0000"
        )
        email = svc.register_identity(
            IdentityKind.EMAIL, label="找回邮箱", value="accnary.test@example.com"
        )
        service = svc.add_service(
            "DemoCloud",
            type=ServiceType.CLOUD_SERVICE,
            urls=["https://cloud.example.com"],
            tags=["网盘"],
        )
        account = Account(
            username="demo-user",
            password="demo-pw-1",
            primary_url="https://cloud.example.com/login",
            alias="主账号",
            email="accnary.test@example.com",
            phone="+86-130-0000-0000",
            notes="demo account - fake data",
        )
        account.login_methods = [
            LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.PASSWORD),
            LoginMethod(
                uuid=str(uuidlib.uuid4()),
                type=LoginMethodType.WECHAT_OAUTH,
                identity_ref=wechat.uuid,
                note="扫码登录",
            ),
        ]
        account.identity_bindings = [
            Binding(identity_ref=phone.uuid, role=BindingRole.LOGIN_PHONE),
            Binding(identity_ref=email.uuid, role=BindingRole.RECOVERY_EMAIL),
        ]
        account.license = LicenseInfo(
            mode=LicenseMode.SUBSCRIPTION,
            order_no="TEST-ORDER-0001",
            license_key="TEST-KEY-0000-1111",
            expires="2027-10-24",
        )
        svc.add_account(service, account)
        svc.save()
        return svc, account

    return _make


@pytest.fixture
def full_catalog(make_full_catalog):
    """(CatalogService, Account) with one fully-populated account."""
    return make_full_catalog()
