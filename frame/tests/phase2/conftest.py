"""Phase 2 UI test fixtures - everything runs offscreen against real vaults."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
)
from app.services import CatalogService

TEST_PASSWORD = "ui-test-pass-1"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def catalog(tmp_path):
    """CatalogService with one service + one rich account, saved on disk."""
    svc = CatalogService.create_vault(str(tmp_path / "ui.kdbx"), TEST_PASSWORD)
    wechat = svc.register_identity(IdentityKind.WECHAT, label="微信主号", value="wx_ui_01")
    phone = svc.register_identity(IdentityKind.PHONE, label="手机号", value="+86-138-0000-0000")
    service = svc.add_service("UI云盘", urls=["https://ui.example.com"])
    account = Account(
        username="ui-user",
        password="ui-pass-9",
        primary_url="https://ui.example.com/login",
        alias="主账号",
        email="ui@example.com",
    )
    account.login_methods = [
        LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.PASSWORD),
        LoginMethod(
            uuid=str(uuidlib.uuid4()),
            type=LoginMethodType.WECHAT_OAUTH,
            identity_ref=wechat.uuid,
            note="扫码",
        ),
    ]
    account.identity_bindings = [
        Binding(identity_ref=phone.uuid, role=BindingRole.LOGIN_PHONE)
    ]
    account.license = LicenseInfo(
        mode=LicenseMode.SUBSCRIPTION, license_key="UI-KEY-1", expires="2027-12-31"
    )
    svc.add_account(service, account)
    svc.save()
    return svc


@pytest.fixture
def no_recent_vaults(monkeypatch):
    """Keep QSettings untouched: recent list empty, remember becomes no-op."""
    import app.ui.unlock_dialog as ud

    monkeypatch.setattr(ud, "load_recent_paths", lambda: [])
    remembered: list[str] = []
    monkeypatch.setattr(ud, "remember_recent_path", remembered.append)
    return remembered
