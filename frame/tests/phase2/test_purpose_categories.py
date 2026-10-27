# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:45
# @Modified  : 2026-10-25 11:45
# @Python    : 3.14.9
# @Description: Account-purpose compatibility, explicit-only writes, global search and adaptive workspace.
from pathlib import Path
import json
import subprocess

import pytest
from PySide6.QtWidgets import QLabel

from app.models import Account, CustomField, Service, ServiceType
from app.services import CatalogService
from app.ui.account_editor import AccountEditor
from app.ui.categories import category_key, main_category
from app.ui.main_window import MainWindow

from .conftest import TEST_PASSWORD


@pytest.mark.parametrize("kind,old,expected", [
    (ServiceType.RESEARCH_PLATFORM, "", "科研与学术"),
    (ServiceType.JOURNAL_SYSTEM, "", "科研与学术"),
    (ServiceType.DEV_PLATFORM, "", "开发与云服务"),
    (ServiceType.SERVER, "", "设备与服务器"),
    (ServiceType.WEBSITE, "", "未分类"),
    (ServiceType.DESKTOP_APP, "", "未分类"),
    (ServiceType.RESEARCH_PLATFORM, "unknown-legacy-category", "未分类"),
])
def test_conservative_read_only_legacy_mapping(kind, old, expected):
    assert main_category(Service(name="Fictional", type=kind, category=old), Account()) == expected


def test_two_accounts_on_one_platform_have_independent_purposes(catalog, qapp):
    service = catalog.catalog.services[0]
    first = service.accounts[0]
    second = catalog.add_account(service, Account(username="another"))
    catalog.set_custom_field(first.uuid, category_key, "社交与通讯")
    catalog.set_custom_field(second.uuid, category_key, "邮箱")
    catalog.save()
    window = MainWindow(catalog)
    for category in ("社交与通讯", "邮箱"):
        row = next(i for i in range(window.nav_list.count()) if window.nav_list.item(i).text() == category)
        window.nav_list.setCurrentRow(row)
        assert window.account_list.count() == 1
    assert "金融与支付" not in [window.nav_list.item(i).text() for i in range(window.nav_list.count())]
    assert len(catalog.catalog.services) == 1
    window.close()


def test_opening_legacy_ui_does_not_write_or_classify_accounts(catalog, qapp):
    service = catalog.catalog.services[0]
    service.category = "old-unknown-category"
    catalog.update_account(service.accounts[0])
    catalog.save()
    before = catalog.path.read_bytes()
    window = MainWindow(catalog)
    assert "未分类" in [window.nav_list.item(i).text() for i in range(window.nav_list.count())]
    window.close()
    assert catalog.path.read_bytes() == before
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    assert reopened.catalog.services[0].category == "old-unknown-category"
    assert all(field.key != category_key for field in reopened.catalog.all_accounts()[0].custom_fields)


def test_explicit_category_edit_preserves_uuid_schema_relations_and_old_category(catalog, qapp):
    service = catalog.catalog.services[0]
    account = service.accounts[0]
    service.category = "legacy-platform-value"
    catalog.update_account(account)
    catalog.save()
    uuid = account.uuid
    binding_ids = [binding.identity_ref for binding in account.identity_bindings]
    editor = AccountEditor(catalog, service, account)
    editor.purpose_combo.setCurrentIndex(editor.purpose_combo.findData("科研与学术"))
    editor._on_accept()
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert loaded.uuid == uuid
    assert main_category(reopened.catalog.services[0], loaded) == "科研与学术"
    assert reopened.catalog.services[0].category == "legacy-platform-value"
    assert [binding.identity_ref for binding in loaded.identity_bindings] == binding_ids
    assert loaded.license.license_key == "UI-KEY-1"
    entry = reopened.vault.kp.find_entries(first=True, title=service.name)
    assert json.loads(entry.custom_properties["Accnary.Meta"])["schema_version"] == 1
    assert entry.custom_properties[category_key] == "科研与学术"


@pytest.mark.parametrize("protected", [False, True])
def test_unknown_or_protected_same_name_field_survives_normal_edit(catalog, qapp, protected):
    service = catalog.catalog.services[0]
    account = service.accounts[0]
    catalog.set_custom_field(account.uuid, category_key, "unknown-existing-value", protected=protected)
    catalog.save()
    editor = AccountEditor(catalog, service, account)
    assert editor.purpose_combo.isEnabled() is (not protected)
    editor.username_edit.setText("ordinary-edit")
    editor._on_accept()
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    field = next(f for f in reopened.catalog.all_accounts()[0].custom_fields if f.key == category_key)
    assert field.value == "unknown-existing-value" and field.protected is protected


def test_cancel_category_edit_does_not_write(catalog, qapp):
    before = catalog.path.read_bytes()
    editor = AccountEditor(catalog, catalog.catalog.services[0], catalog.catalog.all_accounts()[0])
    editor.purpose_combo.setCurrentIndex(editor.purpose_combo.findData("金融与支付"))
    editor.reject()
    assert catalog.path.read_bytes() == before
    assert all(f.key != category_key for f in catalog.catalog.all_accounts()[0].custom_fields)


def test_new_account_saves_explicit_purpose_via_existing_custom_field(catalog, qapp):
    editor = AccountEditor(catalog)
    editor.service_combo.setCurrentText("Purpose New Platform")
    editor.username_edit.setText("fictional-new-purpose")
    editor.purpose_combo.setCurrentIndex(editor.purpose_combo.findData("社交与通讯"))
    editor._on_accept()
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    service = reopened.catalog.find_service("Purpose New Platform")
    assert main_category(service, service.accounts[0]) == "社交与通讯"


def test_duplicate_purpose_field_is_rejected_without_overwriting_old_value(catalog, qapp):
    account = catalog.catalog.all_accounts()[0]
    catalog.set_custom_field(account.uuid, category_key, "邮箱")
    catalog.save()
    before = catalog.path.read_bytes()
    editor = AccountEditor(catalog, catalog.catalog.services[0], account)
    editor._add_field_row(category_key, "do-not-overwrite", False)
    editor._on_accept()
    assert editor.error_label.text()
    assert catalog.path.read_bytes() == before
    editor.reject()


def test_global_search_explicitly_crosses_selected_category(catalog, qapp):
    first = catalog.catalog.all_accounts()[0]
    second = catalog.add_account("Separate Mail", Account(username="find-across-categories"))
    catalog.set_custom_field(first.uuid, category_key, "社交与通讯")
    catalog.set_custom_field(second.uuid, category_key, "邮箱")
    catalog.save()
    window = MainWindow(catalog)
    row = next(i for i in range(window.nav_list.count()) if window.nav_list.item(i).text() == "社交与通讯")
    window.nav_list.setCurrentRow(row)
    assert window.account_list.count() == 1
    window.search_edit.setText("find-across-categories")
    assert window.account_list.count() == 1
    assert window._selected_pair()[1].uuid == second.uuid
    assert "全部账户" in window.search_scope.text()
    assert not window.sort_combo.isEnabled()
    window.close()


def test_responsive_layout_switches_without_squeezing_three_panes(catalog, qapp):
    window = MainWindow(catalog)
    window.show()
    window.resize(900, 600)
    qapp.processEvents()
    assert window.sidebar.isHidden()
    assert not window.middle_pane.isHidden() and not window.detail_panel.isHidden()
    window.resize(600, 560)
    qapp.processEvents()
    assert window.detail_panel.isHidden() and not window.middle_pane.isHidden()
    window._activate_detail()
    assert window.middle_pane.isHidden() and not window.detail_panel.isHidden()
    window._back_to_list()
    assert not window.middle_pane.isHidden() and window.detail_panel.isHidden()
    window._toggle_navigation()
    assert not window.sidebar.isHidden()
    window.resize(1220, 850)
    qapp.processEvents()
    assert not window.sidebar.isHidden() and not window.detail_panel.isHidden()
    window.close()


def test_purpose_field_survives_keepassxc_save(catalog, qapp):
    cli = next((Path(__file__).resolve().parents[2] / "tools/keepassxc-portable").glob("**/keepassxc-cli.exe"), None)
    assert cli is not None, "Existing project verification tool must be available"
    account = catalog.catalog.all_accounts()[0]
    uuid = account.uuid
    catalog.set_custom_field(uuid, category_key, "科研与学术")
    catalog.save()
    result = subprocess.run([str(cli), "edit", "--notes", "fictional-purpose-roundtrip", str(catalog.path), "UI云盘"],
                            input=(TEST_PASSWORD + "\n").encode(), capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    reopened = CatalogService.open(catalog.path, TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    assert loaded.uuid == uuid and main_category(reopened.catalog.services[0], loaded) == "科研与学术"
    assert loaded.notes == "fictional-purpose-roundtrip"
    assert loaded.license.license_key == "UI-KEY-1"
