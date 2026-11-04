# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 19:12
# @Modified  : 2026-10-25 20:44
# @Python    : 3.14.9
# @Description: Account editor create/edit flows against the real storage layer.
"""Account editor: create + edit flows against the real storage layer."""

from __future__ import annotations

import uuid as uuidlib

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMessageBox, QPushButton

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


def test_duplicate_account_shows_error_and_keeps_form(catalog, qapp):
    service = catalog.catalog.services[0]
    editor = AccountEditor(catalog, service=service)
    editor.username_edit.setText(service.accounts[0].username)
    editor.password_input.edit.setText("fictional-retry-password")
    editor._on_accept()
    assert editor.result() != QDialog.DialogCode.Accepted
    assert "相同用户名" in editor.error_label.text()
    assert editor.password_input.edit.text() == "fictional-retry-password"
    assert len(catalog.catalog.all_accounts()) == 1
    editor.done(QDialog.DialogCode.Rejected)


def test_username_completion_prioritizes_current_platform(catalog, qapp):
    first_service = catalog.catalog.services[0]
    second = catalog.add_service("示例平台", login_urls=["https://example.invalid/login"])
    catalog.add_account(second, Account(username="ui-second", password="fictional-password"))
    catalog.add_account(second, Account(username="ui-user"))
    editor = AccountEditor(catalog)
    completer = editor.username_edit.completer()

    def matching_usernames():
        completer.setCompletionPrefix("ui-")
        matches = completer.completionModel()
        return [matches.index(row, 0).data() for row in range(matches.rowCount())]

    editor.service_combo.setCurrentText(second.name)
    assert matching_usernames() == ["ui-second", "ui-user"]
    assert "https://example.invalid/login" in editor._url_suggestions.stringList()
    assert not editor.username_edit.text()
    assert not editor.password_input.edit.text()
    editor.service_combo.setCurrentText(first_service.name)
    assert matching_usernames() == ["ui-user", "ui-second"]
    editor.service_combo.setCurrentText("新平台")
    assert matching_usernames() == ["ui-user", "ui-second"]
    assert not editor._url_suggestions.stringList()
    editor.done(QDialog.DialogCode.Rejected)
    assert not editor._username_suggestions.stringList()


def test_duplicate_field_selects_offending_row(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.service_combo.setCurrentText("示例平台")
    editor._add_field_row("重复字段", "甲")
    editor._add_field_row("重复字段", "乙")
    field = editor.fields_layout.itemAt(1).itemAt(0).widget()
    editor.tabs.setCurrentIndex(0)
    editor.show()
    qapp.processEvents()
    editor._on_accept()
    assert editor.tabs.tabText(editor.tabs.currentIndex()) == "自定义"
    assert field.hasFocus()
    assert field.selectedText() == "重复字段"
    assert "不能重复" in editor.error_label.text()
    editor.done(QDialog.DialogCode.Rejected)


def test_editor_tabs_and_save_stay_visible_when_fields_scroll(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.resize(580, 470)
    for index in range(24):
        editor._add_field_row(f"字段 {index}", "示例值")
    editor.show()
    editor.tabs.setCurrentIndex(editor.tabs.count() - 1)
    QTest.qWait(100)
    fields_scroll = editor.tabs.currentWidget()
    scrollbar = fields_scroll.verticalScrollBar()
    assert scrollbar.maximum() > 0
    tab_bar = editor.tabs.tabBar()
    save = editor.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    tab_position = tab_bar.mapTo(editor, tab_bar.rect().topLeft())
    save_position = save.mapTo(editor, save.rect().topLeft())

    scrollbar.setValue(scrollbar.maximum())
    qapp.processEvents()
    assert tab_bar.mapTo(editor, tab_bar.rect().topLeft()) == tab_position
    assert save.mapTo(editor, save.rect().topLeft()) == save_position
    assert save.isVisible()
    editor.tabs.setCurrentIndex(0)
    assert editor.tabs.currentWidget().verticalScrollBar().value() == 0
    editor.tabs.setCurrentWidget(fields_scroll)
    QTest.qWait(100)
    assert scrollbar.value() == scrollbar.maximum()
    editor.done(QDialog.DialogCode.Rejected)


def test_add_field_focuses_new_row_in_scroll_view(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.resize(580, 470)
    for index in range(24):
        editor._add_field_row(f"字段 {index}", "示例值")
    editor.tabs.setCurrentIndex(editor.tabs.count() - 1)
    editor.show()
    QTest.qWait(100)
    scroll = editor.tabs.currentWidget()
    add_button = next(button for button in scroll.findChildren(QPushButton) if button.text() == "添加字段")
    scroll.ensureWidgetVisible(add_button)
    add_button.click()
    QTest.qWait(100)
    field = editor.fields_layout.itemAt(24).itemAt(0).widget()
    assert field.hasFocus()
    top = field.mapTo(scroll.viewport(), field.rect().topLeft()).y()
    assert 0 <= top < scroll.viewport().height() - field.height()
    editor.done(QDialog.DialogCode.Rejected)


def test_escape_and_close_confirm_unsaved_edits(catalog, qapp, monkeypatch):
    editor = AccountEditor(catalog)
    editor.show()
    qapp.processEvents()
    editor.username_edit.setText("未保存的账户")
    answers = iter((QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: next(answers))
    QTest.keyClick(editor.username_edit, Qt.Key.Key_Escape)
    assert editor.isVisible()
    assert editor.username_edit.text() == "未保存的账户"
    editor.close()
    assert not editor.isVisible()
    assert not editor.username_edit.text()


def test_unchanged_editor_closes_without_confirmation(catalog, qapp, monkeypatch):
    editor = AccountEditor(catalog)
    editor.show()
    qapp.processEvents()
    editor.username_edit.setText("临时修改")
    editor.username_edit.clear()
    editor.tabs.setCurrentIndex(editor.tabs.count() - 1)

    def unexpected_prompt(*args):
        raise AssertionError("unchanged form should close directly")

    monkeypatch.setattr(QMessageBox, "question", unexpected_prompt)
    editor.close()
    assert not editor.isVisible()


def test_edit_assembles_metadata_without_copying_sibling_accounts(catalog, qapp):
    class SiblingAccount(Account):
        def __deepcopy__(self, memo):
            raise AssertionError("editing must not copy sibling credentials")

    service = catalog.catalog.services[0]
    account = service.accounts[0]
    sibling = SiblingAccount(uuid="fictional-sibling", password="fictional-secret")
    service.accounts.append(sibling)
    service._extra = {"extension": {"values": [1]}}
    editor = AccountEditor(catalog, service=service, account=account)
    assembled_service, assembled_account = editor._assemble()
    assert assembled_service.accounts == []
    assert assembled_account.uuid == account.uuid
    assembled_service._extra["extension"]["values"].append(2)
    assert service._extra == {"extension": {"values": [1]}}
    assert service.accounts[-1] is sibling
    editor.reject()
    editor.deleteLater()


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
