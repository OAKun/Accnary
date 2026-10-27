# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 19:12
# @Modified  : 2026-10-25 20:44
# @Python    : 3.14.9
# @Description: Account editor create/edit flows against the real storage layer.
"""Account editor: create + edit flows against the real storage layer."""

from __future__ import annotations

import uuid as uuidlib

from PySide6.QtWidgets import QLabel

from app.models import (
    Account,
    Binding,
    BindingRole,
    IdentityKind,
    LicenseMode,
    LoginMethod,
    LoginMethodType,
)
from app.services import CatalogService
from app.ui.account_editor import AccountEditor, NewIdentityDialog

from .conftest import TEST_PASSWORD


def test_create_account_via_editor_persists(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.service_combo.setCurrentText("期刊投稿")
    idx = editor.primary_method_combo.findData(LoginMethodType.PASSWORD.value)
    editor.username_edit.setText("author-1")
    editor.password_input.set_text("paper-pass-1")
    editor.url_edit.setText("https://journals.example.com/submit")
    editor.primary_method_combo.setCurrentIndex(idx)
    editor.notes_edit.setPlainText("投稿系统账号")
    editor._on_accept()

    assert editor.result() == AccountEditor.DialogCode.Accepted
    reopened = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    names = {a.username for a in reopened.catalog.all_accounts()}
    assert names == {"ui-user", "author-1"}
    service = reopened.catalog.find_service("期刊投稿")
    assert service is not None
    account = service.accounts[0]
    assert account.notes == "投稿系统账号"
    assert account.login_methods[0].type == LoginMethodType.PASSWORD


def test_editor_validates_empty_platform(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.service_combo.setCurrentText("   ")
    editor._on_accept()
    assert editor.result() != AccountEditor.DialogCode.Accepted
    assert "平台名称" in editor.error_label.text()


def test_edit_preserves_primary_method_identity(catalog, qapp):
    """The seeded account's wechat OAuth method (with identity_ref + note)
    must survive an edit round-trip - the regression for the editor's
    primary-method handling."""
    service, account = next(
        (s, a) for s in catalog.catalog.services for a in s.accounts
    )
    editor = AccountEditor(catalog, service=service, account=account)
    assert editor.methods_layout.count() == 2  # all methods loaded as rows
    editor.username_edit.setText("ui-user-renamed")
    editor._on_accept()

    reopened = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert loaded.username == "ui-user-renamed"
    types = [lm.type for lm in loaded.login_methods]
    assert types == [LoginMethodType.PASSWORD, LoginMethodType.WECHAT_OAUTH]
    wechat = loaded.login_methods[1]
    assert reopened.identity_label(wechat.identity_ref) == "微信主号"
    assert wechat.note == "扫码"
    assert loaded.identity_bindings[0].role == BindingRole.LOGIN_PHONE
    assert loaded.license.license_key == "UI-KEY-1"


def test_add_second_method_and_license_via_editor(catalog, qapp):
    service, account = next(
        (s, a) for s in catalog.catalog.services for a in s.accounts
    )
    editor = AccountEditor(catalog, service=service, account=account)
    editor._add_method_row(LoginMethodType.PHONE_SMS, None, "短信登录")
    editor.license_mode_combo.setCurrentIndex(
        editor.license_mode_combo.findData(LicenseMode.PERPETUAL.value)
    )
    editor.license_key_edit.setText("NEW-LICENSE-9")
    editor._on_accept()

    reopened = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert {lm.type for lm in loaded.login_methods} == {
        LoginMethodType.PASSWORD,
        LoginMethodType.WECHAT_OAUTH,
        LoginMethodType.PHONE_SMS,
    }
    assert loaded.license.mode == LicenseMode.PERPETUAL
    assert loaded.license.license_key == "NEW-LICENSE-9"


def test_custom_field_add_and_remove_via_editor(catalog, qapp):
    service, account = next(
        (s, a) for s in catalog.catalog.services for a in s.accounts
    )
    editor = AccountEditor(catalog, service=service, account=account)
    editor._add_field_row("API Token", "tok-abc", protected=True)
    editor._on_accept()

    reopened = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    fields = {f.key: f for f in loaded.custom_fields}
    assert fields["API Token"].value == "tok-abc"
    assert fields["API Token"].protected is True

    # second edit session: remove the field again
    editor2 = AccountEditor(reopened, service=reopened.catalog.services[0], account=loaded)
    for i in reversed(range(editor2.fields_layout.count())):
        row = editor2.fields_layout.itemAt(i)
        if hasattr(row, "remove_btn"):
            row.remove_btn.click()
    editor2._on_accept()
    final = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    final_fields = {f.key for f in final.catalog.all_accounts()[0].custom_fields}
    assert "API Token" not in final_fields


def test_license_dates_keep_explicit_labels_when_values_are_entered(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.tabs.setCurrentIndex(3)
    editor.license_purchase_edit.setText("2026-01-15")
    editor.license_expires_edit.setText("2027-01-15")

    labels = {
        label.objectName(): label for label in editor.findChildren(QLabel)
    }
    assert labels["licensePurchaseDateLabel"].text() == "购买日期"
    assert labels["licensePurchaseDateLabel"].buddy() is editor.license_purchase_edit
    assert labels["licenseExpiryDateLabel"].text() == "有效期至"
    assert labels["licenseExpiryDateLabel"].buddy() is editor.license_expires_edit


def test_new_identity_dialog_collects_data(qapp):
    dialog = NewIdentityDialog()
    idx = dialog.kind_combo.findData(IdentityKind.QQ.value)
    dialog.kind_combo.setCurrentIndex(idx)
    dialog.label_edit.setText("QQ 备用号")
    dialog.value_edit.setText("12345678")
    kind, label, value = dialog.identity_data()
    assert (kind, label, value) == (IdentityKind.QQ, "QQ 备用号", "12345678")


def test_editor_registers_identity_via_catalog(catalog, qapp):
    """The '新建身份' flow: register + save + reference from a new binding."""
    identity = catalog.register_identity(
        IdentityKind.EMAIL, label="工作邮箱", value="work@example.com"
    )
    catalog.save()
    service, account = next(
        (s, a) for s in catalog.catalog.services for a in s.accounts
    )
    editor = AccountEditor(catalog, service=service, account=account)
    editor._add_binding_row(BindingRole.RECOVERY_EMAIL, identity.uuid)
    editor._on_accept()

    reopened = CatalogService.open(str(catalog.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    roles = {b.role: b.identity_ref for b in loaded.identity_bindings}
    assert reopened.identity_label(roles[BindingRole.RECOVERY_EMAIL]) == "工作邮箱"
