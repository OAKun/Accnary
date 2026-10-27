# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:27
# @Modified  : 2026-10-26 22:58
# @Python    : 3.14.9
# @Description: Accnary app / ui / account_editor
"""Tabbed add/edit account dialog using the existing transactional editor.

The widgets and assembly/save paths are shared with the existing editor;
only their presentation is divided into explicit task-oriented tabs.
"""

from __future__ import annotations

import uuid as uuidlib
from copy import deepcopy

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.errors import AccnaryError, ConflictError
from app.models import (
    Account,
    Binding,
    BindingRole,
    CustomField,
    Identity,
    IdentityKind,
    LicenseInfo,
    LicenseMode,
    LoginMethod,
    LoginMethodType,
    Service,
    ServiceType,
)
from app.services import CatalogService
from app.ui.labels import (
    BINDING_ROLE_LABELS,
    IDENTITY_KIND_LABELS,
    LICENSE_MODE_LABELS,
    LOGIN_METHOD_LABELS,
    SERVICE_TYPE_LABELS,
)
from app.ui.widgets import PasswordInput, SectionHeader
from app.ui.storage_task import run_storage_task
from app.ui.categories import categories, category_key, main_category, uncategorized


def _unique_suggestions(values: list[str]) -> list[str]:
    return list(dict.fromkeys(
        value.strip() for value in values
        if isinstance(value, str) and value.strip()
    ))


def _install_completer(edit: QLineEdit) -> QStringListModel:
    model = QStringListModel(edit)
    completer = QCompleter(model, edit)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setMaxVisibleItems(8)
    edit.setCompleter(completer)
    return model


class NewIdentityDialog(QDialog):
    """Mini dialog to register a new identity (kind/label/value)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建身份")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 16)

        self.kind_combo = QComboBox()
        for kind in IdentityKind:
            self.kind_combo.addItem(IDENTITY_KIND_LABELS[kind], kind.value)
        form.addRow("身份类型", self.kind_combo)

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("如：微信主号、QQ 备用号")
        form.addRow("显示名称", self.label_edit)

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("微信号 / QQ 号 / 手机号 / 邮箱（可留空）")
        form.addRow("身份值", self.value_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def identity_data(self) -> tuple[IdentityKind, str, str]:
        return (
            IdentityKind(self.kind_combo.currentData()),
            self.label_edit.text().strip(),
            self.value_edit.text().strip(),
        )


class _RowBar(QHBoxLayout):
    """Horizontal helper row with a trailing remove button."""

    def __init__(self, on_remove):
        super().__init__()
        self.setSpacing(6)
        self.remove_btn = QToolButton()
        self.remove_btn.setText("✕")
        self.remove_btn.setToolTip("移除此项")
        self.remove_btn.setAccessibleName("移除此项")
        self.remove_btn.setAutoRaise(True)
        self.remove_btn.setFixedSize(32, 32)
        self.remove_btn.clicked.connect(on_remove)


class AccountEditor(QDialog):
    """Create or edit one account through CatalogService."""

    def __init__(
        self,
        catalog: CatalogService,
        service: Service | None = None,
        account: Account | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._catalog = catalog
        self._service = service
        self._account = account
        self.is_edit = account is not None
        self.created_account: Account | None = None
        self._pending_identities: list[Identity] = []
        self._purpose_field = deepcopy(next((field for field in account.custom_fields
                                            if field.key == category_key), None)) if account else None
        self._purpose_changed = False

        self.setWindowTitle("编辑账户" if self.is_edit else "新建账户")
        self.setObjectName("accountEditor")
        self.setMinimumSize(580, 470)
        self.resize(720, 650)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        heading = QWidget()
        heading_layout = QVBoxLayout(heading)
        heading_layout.setContentsMargins(24, 20, 24, 10)
        title = QLabel("编辑账户" if self.is_edit else "新建账户")
        title.setProperty("pageTitle", True)
        heading_layout.addWidget(title)
        hint = QLabel("基本资料快速录入，登录绑定和许可证分组维护。")
        hint.setProperty("muted", True)
        heading_layout.addWidget(hint)
        outer.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("editorBody")
        scroll.setWidget(body)
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(24, 12, 24, 20)
        main_layout.setSpacing(10)

        # ---- basic form ---------------------------------------------------
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.service_combo = QComboBox()
        self.service_combo.setEditable(True)
        self.service_combo.lineEdit().setPlaceholderText("例如：QQ、微信、GitHub 或软件名称")
        self.service_combo.completer().setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.service_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        for existing in catalog.catalog.services:
            self.service_combo.addItem(existing.name)
        if service is not None:
            self.service_combo.setCurrentText(service.name)
        else:
            self.service_combo.setCurrentIndex(-1)
        self.service_combo.setEnabled(not self.is_edit)
        form.addRow("平台名称", self.service_combo)
        self.purpose_combo = QComboBox()
        self.purpose_combo.setObjectName("mainCategory")
        for label in categories:
            self.purpose_combo.addItem(label, label)
        initial = main_category(service, account) if service and account else uncategorized
        if self._purpose_field and not self._purpose_field.protected and self._purpose_field.value not in categories:
            initial = self._purpose_field.value
            self.purpose_combo.addItem("保留原值：" + initial, initial)
        self.purpose_combo.setCurrentIndex(self.purpose_combo.findData(initial))
        self.purpose_combo.setToolTip("按账户用途分类；只在主动更改后保存。旧平台类型与原分类保持兼容。")
        if self._purpose_field and self._purpose_field.protected:
            self.purpose_combo.setEnabled(False)
            self.purpose_combo.setToolTip("已有同名受保护字段，保留原值；如需设置分类，请先在自定义中重命名该字段。")
        self.purpose_combo.currentIndexChanged.connect(self._on_purpose_changed)
        form.addRow("主分类", self.purpose_combo)

        self.service_type_combo = QComboBox()
        for stype in ServiceType:
            self.service_type_combo.addItem(SERVICE_TYPE_LABELS[stype], stype.value)

        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("如：主账号、工作号（可留空）")

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("QQ 号、微信号、邮箱或用户名")
        self.username_edit.setToolTip("可输入新值，也可从密码库已有用户名和身份中选择")
        self._username_suggestions = _install_completer(self.username_edit)
        form.addRow("用户名", self.username_edit)

        self.password_input = PasswordInput()
        form.addRow("密码", self.password_input)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://…")
        self.url_edit.setToolTip("可输入新网址；选择已有平台后可从该平台的网址中选择")
        self._url_suggestions = _install_completer(self.url_edit)
        form.addRow("登录网址", self.url_edit)

        self.primary_method_combo = QComboBox()
        for mtype in LoginMethodType:
            self.primary_method_combo.addItem(LOGIN_METHOD_LABELS[mtype], mtype.value)
        form.addRow("主要登录方式", self.primary_method_combo)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("注册邮箱（可留空）")
        self.email_edit.setToolTip("可输入新邮箱，也可从密码库已有邮箱中选择")
        self._email_suggestions = _install_completer(self.email_edit)

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("注册手机号（可留空）")
        self.phone_edit.setToolTip("可输入新手机号，也可从密码库已有手机号中选择")
        self._phone_suggestions = _install_completer(self.phone_edit)

        accounts = catalog.catalog.all_accounts()
        identities = catalog.catalog.identities
        self._username_suggestions.setStringList(_unique_suggestions(
            [account.username for account in accounts]
            + [identity.value for identity in identities]
        ))
        self._email_suggestions.setStringList(_unique_suggestions(
            [account.email for account in accounts]
            + [identity.value for identity in identities
               if identity.kind == IdentityKind.EMAIL]
        ))
        self._phone_suggestions.setStringList(_unique_suggestions(
            [account.phone for account in accounts]
            + [identity.value for identity in identities
               if identity.kind == IdentityKind.PHONE]
        ))

        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(70)
        self.notes_edit.setPlaceholderText("补充说明（可选）")
        form.addRow("备注", self.notes_edit)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("editorTabs")
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)
        basic = QWidget()
        basic_layout = QVBoxLayout(basic)
        basic_layout.setContentsMargins(0, 24, 0, 0)
        basic_layout.addLayout(form)
        basic_layout.addStretch(1)
        self.tabs.addTab(basic, "基本资料")

        contact_page = QWidget()
        more_layout = QVBoxLayout(contact_page)
        more_layout.setContentsMargins(0, 24, 0, 0)
        more_layout.setSpacing(24)
        account_extra = QWidget()
        extra_form = QFormLayout(account_extra)
        extra_form.setContentsMargins(0, 10, 0, 12)
        extra_form.setSpacing(10)
        extra_form.addRow(SectionHeader("账户补充信息"))
        extra_form.addRow("账户别名", self.alias_edit)
        extra_form.addRow("注册邮箱", self.email_edit)
        extra_form.addRow("手机号", self.phone_edit)
        more_layout.addWidget(account_extra)
        more_layout.addWidget(self._build_service_group())
        more_layout.addStretch(1)
        self.tabs.addTab(contact_page, "平台与联系")
        for title, groups in (
            ("登录与绑定", (self._build_methods_group(), self._build_bindings_group())),
            ("许可证", (self._build_license_group(),)),
            ("自定义", (self._build_fields_group(),)),
        ):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 24, 0, 0)
            page_layout.setSpacing(24)
            for group in groups:
                page_layout.addWidget(group)
            page_layout.addStretch(1)
            self.tabs.addTab(page, title)

        # ---- buttons -------------------------------------------------------
        self.error_label = QLabel("")
        self.error_label.setProperty("error", True)
        self.error_label.setAccessibleName("错误提示")
        self.error_label.setWordWrap(True)
        footer = QWidget()
        footer.setObjectName("dialogFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(24, 10, 24, 14)
        footer_layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        footer_layout.addWidget(buttons)
        outer.addWidget(footer)
        for before, after in zip(
            (self.service_combo, self.username_edit, self.password_input.edit,
             self.url_edit, self.primary_method_combo),
            (self.username_edit, self.password_input.edit, self.url_edit,
             self.primary_method_combo, self.notes_edit),
        ):
            QWidget.setTabOrder(before, after)

        if not self.is_edit:
            self.service_combo.currentTextChanged.connect(self._load_existing_platform)
            self._load_existing_platform(self.service_combo.currentText())
        if self.is_edit:
            self._load(account)
        elif service is not None:
            idx = self.service_type_combo.findData(service.type.value)
            if idx >= 0:
                self.service_type_combo.setCurrentIndex(idx)

    def _load_existing_platform(self, name: str) -> None:
        service = self._catalog.catalog.find_service(name)
        if service is None:
            self._set_url_suggestions(None)
            return
        self.service_type_combo.setCurrentIndex(self.service_type_combo.findData(service.type.value))
        self.category_edit.setText(service.category)
        self.tags_edit.setText(", ".join(service.tags))
        self.aliases_edit.setText(", ".join(service.aliases))
        self.urls_edit.setText(", ".join(service.urls))
        self._set_url_suggestions(service)

    def _set_url_suggestions(self, service: Service | None) -> None:
        urls = []
        if service is not None:
            urls.extend(service.urls)
            urls.extend(account.primary_url for account in service.accounts)
        self._url_suggestions.setStringList(_unique_suggestions(urls))

    # ------------------------------------------------------------------ UI

    def _on_purpose_changed(self, _index) -> None:
        self._purpose_changed = True

    def _build_service_group(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionHeader("平台信息（同平台所有账户共享）"))
        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("平台类型", self.service_type_combo)
        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("如：科研平台 / 云服务")
        self.category_edit.setToolTip("保留旧密码库的平台共享分类；账户主分类在基本资料中单独设置。")
        form.addRow("原平台分类", self.category_edit)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("标签，逗号分隔：网盘, 常用")
        form.addRow("标签", self.tags_edit)
        self.aliases_edit = QLineEdit()
        self.aliases_edit.setPlaceholderText("平台别名，逗号分隔：BaiduPan")
        form.addRow("平台别名", self.aliases_edit)
        self.urls_edit = QLineEdit()
        self.urls_edit.setPlaceholderText("关联网址，逗号分隔：https://a.com, https://b.com")
        form.addRow("平台网址", self.urls_edit)
        layout.addLayout(form)
        return box

    @staticmethod
    def _split_csv(text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def _build_methods_group(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionHeader("其他登录方式"))
        self.methods_layout = QVBoxLayout()
        self.methods_layout.setSpacing(4)
        layout.addLayout(self.methods_layout)
        add_btn = QPushButton("添加登录方式")
        add_btn.setProperty("variant", "ghost")
        add_btn.clicked.connect(lambda: self._add_method_row())
        layout.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        return box

    def _build_bindings_group(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionHeader("绑定身份（微信 / QQ / 手机号 / 邮箱…）"))
        self.bindings_layout = QVBoxLayout()
        self.bindings_layout.setSpacing(4)
        layout.addLayout(self.bindings_layout)
        bar = QHBoxLayout()
        add_btn = QPushButton("添加绑定")
        add_btn.setProperty("variant", "ghost")
        add_btn.clicked.connect(lambda: self._add_binding_row())
        new_identity_btn = QPushButton("新建身份…")
        new_identity_btn.setProperty("variant", "ghost")
        new_identity_btn.clicked.connect(self._create_identity)
        bar.addWidget(add_btn)
        bar.addWidget(new_identity_btn)
        bar.addStretch(1)
        layout.addLayout(bar)
        return box

    def _build_license_group(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionHeader("付费授权 / 许可证"))
        form = QFormLayout()
        form.setSpacing(6)
        self.license_mode_combo = QComboBox()
        for mode in LicenseMode:
            self.license_mode_combo.addItem(LICENSE_MODE_LABELS[mode], mode.value)
        form.addRow("类型", self.license_mode_combo)
        self.license_key_edit = QLineEdit()
        self.license_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.license_key_edit.setPlaceholderText("License Key / 激活码")
        self.license_key_toggle = QToolButton()
        self.license_key_toggle.setText("显示")
        self.license_key_toggle.setAccessibleName("显示激活码")
        self.license_key_toggle.clicked.connect(self._toggle_license_key)
        license_key_row = QWidget()
        license_key_layout = QHBoxLayout(license_key_row)
        license_key_layout.setContentsMargins(0, 0, 0, 0)
        license_key_layout.setSpacing(6)
        license_key_layout.addWidget(self.license_key_edit, 1)
        license_key_layout.addWidget(self.license_key_toggle)
        form.addRow("激活码", license_key_row)
        self.license_order_edit = QLineEdit()
        form.addRow("订单号", self.license_order_edit)
        self.license_channel_edit = QLineEdit()
        form.addRow("购买渠道", self.license_channel_edit)
        dates = QWidget()
        dates_layout = QHBoxLayout(dates)
        dates_layout.setContentsMargins(0, 0, 0, 0)
        dates_layout.setSpacing(8)
        self.license_purchase_edit = QLineEdit()
        self.license_purchase_edit.setPlaceholderText("购买日期 YYYY-MM-DD")
        self.license_expires_edit = QLineEdit()
        self.license_expires_edit.setPlaceholderText("有效期至 YYYY-MM-DD")
        for label_text, edit, object_name in (
            ("购买日期", self.license_purchase_edit, "licensePurchaseDateLabel"),
            ("有效期至", self.license_expires_edit, "licenseExpiryDateLabel"),
        ):
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(4)
            label = QLabel(label_text)
            label.setProperty("muted", True)
            label.setObjectName(object_name)
            label.setBuddy(edit)
            column_layout.addWidget(label)
            column_layout.addWidget(edit)
            dates_layout.addWidget(column, 1)
        form.addRow(dates)
        device_row = QHBoxLayout()
        self.license_device_check = QCheckBox("限制设备数")
        self.license_device_spin = QSpinBox()
        self.license_device_spin.setRange(1, 999)
        self.license_device_spin.setValue(1)
        self.license_device_spin.setEnabled(False)
        self.license_device_check.toggled.connect(self.license_device_spin.setEnabled)
        device_row.addWidget(self.license_device_check)
        device_row.addWidget(self.license_device_spin)
        device_row.addStretch(1)
        form.addRow("设备授权", device_row)
        self.license_notes_edit = QLineEdit()
        form.addRow("授权备注", self.license_notes_edit)
        layout.addLayout(form)
        return box

    def _build_fields_group(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(SectionHeader("自定义字段（API Token / 恢复码…）"))
        self.fields_layout = QVBoxLayout()
        self.fields_layout.setSpacing(4)
        layout.addLayout(self.fields_layout)
        add_btn = QPushButton("添加字段")
        add_btn.setProperty("variant", "ghost")
        add_btn.clicked.connect(lambda: self._add_field_row())
        layout.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignLeft)
        return box

    # --------------------------------------------------------- dynamic rows

    def _add_method_row(
        self,
        method_type: LoginMethodType = LoginMethodType.PASSWORD,
        identity_ref: str | None = None,
        note: str = "",
        method: LoginMethod | None = None,
    ) -> None:
        bar = _RowBar(on_remove=lambda: self._remove_row(self.methods_layout, bar))
        bar.method = deepcopy(method)
        type_combo = QComboBox()
        for mtype in LoginMethodType:
            type_combo.addItem(LOGIN_METHOD_LABELS[mtype], mtype.value)
        type_combo.setCurrentIndex(max(0, list(LoginMethodType).index(method_type)))
        identity_combo = self._identity_combo(identity_ref)
        note_edit = QLineEdit(note)
        note_edit.setPlaceholderText("备注")
        type_combo.setAccessibleName("其他登录方式")
        identity_combo.setAccessibleName("登录方式关联身份")
        note_edit.setAccessibleName("登录方式备注")
        bar.addWidget(type_combo, 2)
        bar.addWidget(identity_combo, 2)
        bar.addWidget(note_edit, 2)
        bar.addWidget(bar.remove_btn)
        self.methods_layout.addLayout(bar)

    def _add_binding_row(
        self,
        role: BindingRole = BindingRole.LINKED_IDENTITY,
        identity_ref: str | None = None,
    ) -> None:
        bar = _RowBar(on_remove=lambda: self._remove_row(self.bindings_layout, bar))
        role_combo = QComboBox()
        for r in BindingRole:
            role_combo.addItem(BINDING_ROLE_LABELS[r], r.value)
        role_combo.setCurrentIndex(max(0, list(BindingRole).index(role)))
        identity_combo = self._identity_combo(identity_ref)
        role_combo.setAccessibleName("绑定身份用途")
        identity_combo.setAccessibleName("绑定身份")
        bar.addWidget(role_combo, 2)
        bar.addWidget(identity_combo, 3)
        bar.addWidget(bar.remove_btn)
        self.bindings_layout.addLayout(bar)

    def _add_field_row(self, key: str = "", value: str = "", protected: bool = False) -> None:
        bar = _RowBar(on_remove=lambda: self._remove_row(self.fields_layout, bar))
        key_edit = QLineEdit(key)
        key_edit.setPlaceholderText("字段名（不得以 Accnary. 开头）")
        value_edit = QLineEdit(value)
        value_edit.setPlaceholderText("值")
        key_edit.setAccessibleName("自定义字段名称")
        value_edit.setAccessibleName("自定义字段值")
        protected_check = QCheckBox("隐藏")
        protected_check.setAccessibleName("隐藏自定义字段值")
        protected_check.setChecked(protected)
        value_edit.setEchoMode(QLineEdit.EchoMode.Password if protected else QLineEdit.EchoMode.Normal)
        protected_check.toggled.connect(lambda hidden: value_edit.setEchoMode(
            QLineEdit.EchoMode.Password if hidden else QLineEdit.EchoMode.Normal))
        bar.addWidget(key_edit, 2)
        bar.addWidget(value_edit, 3)
        bar.addWidget(protected_check)
        bar.addWidget(bar.remove_btn)
        self.fields_layout.addLayout(bar)

    @staticmethod
    def _remove_row(parent_layout, bar: _RowBar) -> None:
        for i in range(parent_layout.count()):
            if parent_layout.itemAt(i) is bar:
                while bar.count():
                    item = bar.takeAt(0)
                    if item.widget() is not None:
                        item.widget().deleteLater()
                parent_layout.removeItem(bar)
                return

    def _identity_combo(self, selected_ref: str | None = None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("（不关联身份）", None)
        for identity in self._catalog.catalog.identities + self._pending_identities:
            label = identity.label or identity.value or identity.uuid
            combo.addItem(f"{label}（{IDENTITY_KIND_LABELS.get(identity.kind, '')}）", identity.uuid)
        if selected_ref is not None:
            index = combo.findData(selected_ref)
            if index < 0:
                combo.addItem(f"（缺失身份：{selected_ref}）", selected_ref)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
        return combo

    def _toggle_license_key(self) -> None:
        visible = self.license_key_edit.echoMode() == QLineEdit.EchoMode.Password
        self.license_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        label = "隐藏" if visible else "显示"
        self.license_key_toggle.setText(label)
        self.license_key_toggle.setAccessibleName(f"{label}激活码")

    def _create_identity(self) -> None:
        dialog = NewIdentityDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kind, label, value = dialog.identity_data()
        if not label and not value:
            self.error_label.setText("身份需要至少填写显示名称或身份值。")
            return
        identity = Identity(uuid=str(uuidlib.uuid4()), kind=kind, label=label, value=value)
        self._pending_identities.append(identity)
        dialog.label_edit.clear()
        dialog.value_edit.clear()
        dialog.deleteLater()
        # refresh every identity combo in place
        for layout in (self.methods_layout, self.bindings_layout):
            for i in range(layout.count()):
                row = layout.itemAt(i)
                if not isinstance(row, _RowBar):
                    continue
                combo = row.itemAt(1).widget() if row.count() > 1 else None
                if isinstance(combo, QComboBox) and combo.itemData(0) is None and combo is not None:
                    current = combo.currentData()
                    combo.clear()
                    combo.addItem("（不关联身份）", None)
                    for ident in self._catalog.catalog.identities + self._pending_identities:
                        text = ident.label or ident.value or ident.uuid
                        combo.addItem(
                            f"{text}（{IDENTITY_KIND_LABELS.get(ident.kind, '')}）", ident.uuid
                        )
                    if current:
                        idx = combo.findData(current)
                        if idx < 0:
                            combo.addItem(f"（缺失身份：{current}）", current)
                            idx = combo.count() - 1
                        combo.setCurrentIndex(idx)

    # ---------------------------------------------------------------- data

    def _load(self, account: Account) -> None:
        self.alias_edit.setText(account.alias)
        self.username_edit.setText(account.username)
        self.password_input.set_text(account.password)
        self.url_edit.setText(account.primary_url)
        self.email_edit.setText(account.email)
        self.phone_edit.setText(account.phone)
        self.notes_edit.setPlainText(account.notes)
        # Edit mode: ALL methods (including the first) live in the advanced
        # rows so identity refs and notes can never be lost; the basic combo
        # is display-only. New mode: the basic combo creates the first method.
        for lm in account.login_methods:
            self._add_method_row(lm.type, lm.identity_ref, lm.note, method=lm)
        if account.login_methods:
            first = account.login_methods[0]
            self.primary_method_combo.setCurrentIndex(
                max(0, list(LoginMethodType).index(first.type))
            )
            self.primary_method_combo.setEnabled(False)
            self.primary_method_combo.setToolTip(
                "编辑模式下请直接调整下方的登录方式列表"
            )
        for binding in account.identity_bindings:
            self._add_binding_row(binding.role, binding.identity_ref)
        lic = account.license
        self.license_mode_combo.setCurrentIndex(
            max(0, list(LicenseMode).index(lic.mode))
        )
        self.license_key_edit.setText(lic.license_key)
        self.license_order_edit.setText(lic.order_no)
        self.license_channel_edit.setText(lic.channel)
        self.license_purchase_edit.setText(lic.purchase_date)
        self.license_expires_edit.setText(lic.expires)
        if lic.device_limit is not None:
            self.license_device_check.setChecked(True)
            self.license_device_spin.setValue(lic.device_limit)
        self.license_notes_edit.setText(lic.notes)
        for field in account.custom_fields:
            if not field.key.startswith("Accnary."):
                if field.key == category_key and not field.protected:
                    continue
                self._add_field_row(field.key, field.value, field.protected)
        # platform attributes (shared by all accounts of this service)
        service = self._service
        if service is not None:
            self._set_url_suggestions(service)
            self.service_type_combo.setCurrentIndex(self.service_type_combo.findData(service.type.value))
            self.category_edit.setText(service.category)
            self.tags_edit.setText(", ".join(service.tags))
            self.aliases_edit.setText(", ".join(service.aliases))
            self.urls_edit.setText(", ".join(service.urls))

    @staticmethod
    def _coerce(enum_cls, raw_value, default):
        """Combo data round-trips through QVariant as a plain string (the
        enums are str subclasses) - coerce it back to a real enum member."""
        try:
            return enum_cls(raw_value)
        except ValueError:
            return default

    def _assemble(self) -> tuple[Service, Account]:
        service_name = self.service_combo.currentText().strip()
        if not service_name:
            raise AccnaryError("平台名称不能为空。")
        service_type = self._coerce(
            ServiceType, self.service_type_combo.currentData(), ServiceType.WEBSITE
        )
        service_attrs = {
            "type": service_type,
            "category": self.category_edit.text().strip(),
            "tags": self._split_csv(self.tags_edit.text()),
            "aliases": self._split_csv(self.aliases_edit.text()),
            "urls": self._split_csv(self.urls_edit.text()),
        }

        basic_method = LoginMethod(
            uuid=str(uuidlib.uuid4()),
            type=self._coerce(
                LoginMethodType,
                self.primary_method_combo.currentData(),
                LoginMethodType.PASSWORD,
            ),
        )
        rows: list[LoginMethod] = []
        for i in range(self.methods_layout.count()):
            row = self.methods_layout.itemAt(i)
            if not isinstance(row, _RowBar):
                continue
            type_combo = row.itemAt(0).widget()
            identity_combo = row.itemAt(1).widget()
            note_edit = row.itemAt(2).widget()
            rows.append(
                LoginMethod(
                    uuid=row.method.uuid if row.method else str(uuidlib.uuid4()),
                    type=self._coerce(
                        LoginMethodType, type_combo.currentData(), LoginMethodType.CUSTOM
                    ),
                    identity_ref=identity_combo.currentData(),
                    note=note_edit.text().strip(),
                    extra=row.method.extra if row.method else "",
                )
            )
        # edit mode: the advanced rows hold the complete, lossless method list;
        # new mode: the basic combo creates the first method
        methods = rows if self.is_edit else [basic_method] + rows

        bindings = []
        for i in range(self.bindings_layout.count()):
            row = self.bindings_layout.itemAt(i)
            if not isinstance(row, _RowBar):
                continue
            role_combo = row.itemAt(0).widget()
            identity_combo = row.itemAt(1).widget()
            if identity_combo.currentData() is not None:
                bindings.append(
                    Binding(
                        identity_ref=identity_combo.currentData(),
                        role=self._coerce(
                            BindingRole,
                            role_combo.currentData(),
                            BindingRole.LINKED_IDENTITY,
                        ),
                    )
                )

        device_limit = (
            self.license_device_spin.value() if self.license_device_check.isChecked() else None
        )
        license_info = LicenseInfo(
            mode=self._coerce(
                LicenseMode,
                self.license_mode_combo.currentData(),
                LicenseMode.NONE,
            ),
            license_key=self.license_key_edit.text(),
            order_no=self.license_order_edit.text().strip(),
            channel=self.license_channel_edit.text().strip(),
            purchase_date=self.license_purchase_edit.text().strip(),
            expires=self.license_expires_edit.text().strip(),
            device_limit=device_limit,
            notes=self.license_notes_edit.text().strip(),
            evidence=self._account.license.evidence if self.is_edit else "",
        )

        fields = self._editor_fields()

        if self.is_edit:
            service = deepcopy(self._service)
            # platform attributes are shared by every account of this service;
            # save() rewrites each entry's Accnary.Meta service block
            service.type = service_attrs["type"]
            service.category = service_attrs["category"]
            service.tags = service_attrs["tags"]
            service.aliases = service_attrs["aliases"]
            service.urls = service_attrs["urls"]
            account = deepcopy(self._account)
            account.username = self.username_edit.text().strip()
            account.password = self.password_input.text()
            account.primary_url = self.url_edit.text().strip()
            account.alias = self.alias_edit.text().strip()
            account.email = self.email_edit.text().strip()
            account.phone = self.phone_edit.text().strip()
            account.notes = self.notes_edit.toPlainText().strip()
            account.login_methods = methods
            account.identity_bindings = bindings
            account.license = license_info
            # custom fields are NOT touched here - _sync_custom_fields owns
            # them and compares against the still-loaded field list
        else:
            service = Service(name=service_name, **service_attrs)
            account = Account(
                username=self.username_edit.text().strip(),
                password=self.password_input.text(),
                primary_url=self.url_edit.text().strip(),
                alias=self.alias_edit.text().strip(),
                email=self.email_edit.text().strip(),
                phone=self.phone_edit.text().strip(),
                notes=self.notes_edit.toPlainText().strip(),
                login_methods=methods,
                identity_bindings=bindings,
                license=license_info,
                custom_fields=fields,
            )
        return service, account

    def _on_accept(self) -> None:
        try:
            service, account = self._assemble()
        except AccnaryError as exc:
            self.error_label.setText(str(exc))
            return

        try:
            with self._catalog.mutation():
                self._catalog._check_writable()
                self._catalog.catalog.identities.extend(self._pending_identities)
                if self.is_edit:
                    stored_service, _stored = self._catalog.catalog.find_account(account.uuid)
                    for key in ("type", "category", "tags", "aliases", "urls"):
                        setattr(stored_service, key, getattr(service, key))
                    self._sync_custom_fields(account)
                    self._catalog.update_account(account)
                else:
                    self._catalog.add_account(service, account)
                    self._write_custom_fields(account)
                run_storage_task(self, "正在安全保存密码库…", self._catalog.save)
        except ConflictError as exc:
            self._reset_edit_reference()
            QMessageBox.warning(
                self,
                "文件已被修改",
                str(exc) + "\n\n请在主窗口选择“重新加载”后再试。",
            )
            return
        except AccnaryError as exc:
            self._reset_edit_reference()
            self.error_label.setText(f"保存失败：{exc}")
            return
        self.created_account = account if not self.is_edit else None
        self.accept()

    def _reset_edit_reference(self) -> None:
        if self.is_edit:
            located = self._catalog.catalog.find_account(self._account.uuid)
            if located:
                self._service, self._account = located

    def done(self, result) -> None:
        self._pending_identities.clear()
        self._account = None
        self._service = None
        self._purpose_field = None
        for edit in self.findChildren(QLineEdit):
            edit.clear()
        for edit in self.findChildren(QTextEdit):
            edit.clear()
        super().done(result)

    def _write_custom_fields(self, account: Account) -> None:
        for field in account.custom_fields:
            self._catalog.set_custom_field(
                account.uuid, field.key, field.value, protected=field.protected
            )

    def _sync_custom_fields(self, account: Account) -> None:
        """Editor owns the field set in edit mode: apply adds/updates/removals."""
        existing = {f.key: f for f in account.custom_fields}
        wanted = {f.key: f for f in self._editor_fields()}
        for key, field in wanted.items():
            old = existing.get(key)
            if old is None or old.value != field.value or old.protected != field.protected:
                self._catalog.set_custom_field(
                    account.uuid, key, field.value, protected=field.protected
                )
        for key in existing.keys() - wanted.keys():
            if not key.startswith("Accnary."):
                self._catalog.remove_custom_field(account.uuid, key)
        account.custom_fields = list(wanted.values())

    def _editor_fields(self) -> list[CustomField]:
        fields = []
        for i in range(self.fields_layout.count()):
            row = self.fields_layout.itemAt(i)
            if not isinstance(row, _RowBar):
                continue
            key_edit = row.itemAt(0).widget()
            value_edit = row.itemAt(1).widget()
            protected_check = row.itemAt(2).widget()
            key = key_edit.text().strip()
            if key:
                fields.append(
                    CustomField(
                        key=key, value=value_edit.text(), protected=protected_check.isChecked()
                    )
                )
        if self._purpose_changed:
            if any(field.key == category_key for field in fields):
                raise AccnaryError("主分类请在基本资料中设置，自定义字段不能重复使用该名称。")
            fields.append(CustomField(key=category_key, value=self.purpose_combo.currentData(), protected=False))
        elif self._purpose_field and not self._purpose_field.protected:
            fields.append(deepcopy(self._purpose_field))
        if len({field.key for field in fields}) != len(fields):
            raise AccnaryError("自定义字段名称不能重复；主分类请在基本资料中设置。")
        return fields
