"""Phase 1 T8: KeePassXC regression against the real storage layer.

Builds a vault through CatalogService (identity registry + full account),
lets KeePassXC read/edit/save it, then verifies Accnary sees everything
intact. Skipped when the portable build is absent.
"""

from __future__ import annotations

import subprocess
import uuid as uuidlib
from pathlib import Path

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

from .conftest import TEST_PASSWORD

_CLI = Path(__file__).resolve().parents[2] / "tools" / "keepassxc-portable"

pytestmark = pytest.mark.skipif(
    not any(_CLI.glob("**/keepassxc-cli.exe")),
    reason="KeePassXC portable build not present under tools/",
)


def _cli() -> str:
    return str(next(_CLI.glob("**/keepassxc-cli.exe")))


def _run(*args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [_cli(), *args],
        input=f"{TEST_PASSWORD}\n".encode(),
        capture_output=True,
        timeout=120,
    )
    return result


def _out(result: subprocess.CompletedProcess) -> str:
    return (result.stdout + result.stderr).decode("utf-8", errors="replace")


def test_keepassxc_roundtrip_preserves_catalog(tmp_path):
    # 1. Accnary builds the vault through the real storage layer
    svc = CatalogService.create_vault(str(tmp_path / "regression.kdbx"), TEST_PASSWORD)
    wechat = svc.register_identity(
        IdentityKind.WECHAT, label="微信主号", value="wx_reg_01"
    )
    phone = svc.register_identity(
        IdentityKind.PHONE, label="手机号", value="+86-139-0000-0000"
    )
    service = svc.add_service("RegCloud")
    account = Account(
        username="reg-user",
        password="reg-pass-1",
        primary_url="https://reg.example.com",
        alias="回归账号",
        email="reg@example.com",
    )
    account.login_methods = [
        LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.PASSWORD),
        LoginMethod(uuid=str(uuidlib.uuid4()), type=LoginMethodType.WECHAT_OAUTH,
                    identity_ref=wechat.uuid),
    ]
    account.identity_bindings = [
        Binding(identity_ref=phone.uuid, role=BindingRole.LOGIN_PHONE)
    ]
    account.license = LicenseInfo(mode=LicenseMode.SUBSCRIPTION,
                                  license_key="REG-KEY-1", expires="2027-12-31")
    svc.add_account(service, account)
    svc.save()
    original_uuid = account.uuid

    # 2. KeePassXC sees both the account and the registry entry
    listing = _run("ls", str(svc.path))
    assert listing.returncode == 0, _out(listing)
    listing_text = _out(listing)
    assert "RegCloud" in listing_text
    assert "Accnary Identity Registry" in listing_text

    meta_view = _run("show", "-a", "Accnary.Meta", str(svc.path), "RegCloud")
    assert meta_view.returncode == 0, _out(meta_view)
    assert "wechat_oauth" in _out(meta_view)

    # 3. KeePassXC edits and re-saves the whole database
    edited = _run("edit", "--notes", "edited-by-keepassxc", str(svc.path), "RegCloud")
    assert edited.returncode == 0, _out(edited)

    # 4. Accnary reopens: everything intact
    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded_service = reopened.catalog.services[0]
    loaded = loaded_service.accounts[0]
    assert loaded.uuid == original_uuid
    assert loaded.notes == "edited-by-keepassxc"
    assert loaded.license.license_key == "REG-KEY-1"
    assert [lm.type.value for lm in loaded.login_methods] == ["password", "wechat_oauth"]
    assert reopened.identity_label(loaded.login_methods[1].identity_ref) == "微信主号"
    assert reopened.catalog.identities  # registry survived KeePassXC save
    assert reopened.catalog.unmanaged_entries == 0
    assert reopened.vault.format_info.version == (4, 0), \
        "KeePassXC must not silently upgrade the format"

    # 5. Accnary writes again; KeePassXC still reads it
    reopened.set_favorite(loaded.uuid, True)
    reopened.save()
    check = _run("show", "-a", "Accnary.Meta", str(svc.path), "RegCloud")
    assert check.returncode == 0, _out(check)
    assert '"favorite": true' in _out(check)
