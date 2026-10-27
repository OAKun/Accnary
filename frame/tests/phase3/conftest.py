"""Phase 3 fixtures: rich catalog for search testing (all fictional)."""

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
    ServiceType,
)
from app.services import CatalogService

TEST_PASSWORD = "phase3-test-pass"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def search_catalog(tmp_path):
    svc = CatalogService.create_vault(str(tmp_path / "s3.kdbx"), TEST_PASSWORD)
    wechat = svc.register_identity(IdentityKind.WECHAT, label="微信主号", value="wx_zhang_01")
    phone = svc.register_identity(IdentityKind.PHONE, label="手机号", value="+86-138-0000-0000")

    nasa = svc.add_service(
        "NASA Earthdata",
        type=ServiceType.RESEARCH_PLATFORM,
        urls=["https://earthdata.nasa.gov/search"],
        category="科研数据",
        tags=["科研", "遥感"],
    )
    nasa_account = Account(
        username="researcher-1",
        password="Secret-1",
        primary_url="https://urs.earthdata.nasa.gov/home",
        email="acc@recovery.com",
        notes="投稿与数据下载",
    )
    nasa_account.login_methods = [
        LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.PASSWORD),
        LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.WECHAT_OAUTH,
                    identity_ref=wechat.uuid),
    ]
    nasa_account.identity_bindings = [
        Binding(identity_ref=phone.uuid, role=BindingRole.LOGIN_PHONE)
    ]
    nasa_account.license = LicenseInfo(
        mode=LicenseMode.SUBSCRIPTION, order_no="ORD-7788", license_key="LIC-SECRET-XYZ"
    )
    svc.add_account(nasa, nasa_account)
    svc.set_custom_field(nasa_account.uuid, "API Token", "tok-secret-value", protected=True)

    pan = svc.add_service("百度网盘", type=ServiceType.CLOUD_SERVICE, urls=["https://pan.baidu.com"])
    pan_account = Account(username="pan-user", password="Pan-Pass-2")
    pan_account.license = LicenseInfo(mode=LicenseMode.PERPETUAL, license_key="PAN-KEY-9")
    svc.add_account(pan, pan_account)
    svc.save()
    return svc, nasa, nasa_account, pan, pan_account
