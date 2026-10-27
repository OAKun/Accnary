# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:13
# @Modified  : 2026-10-26 01:18
# @Python    : 3.14.9
# @Description: Accnary app / ui / detail_panel
"""Right-hand account detail panel (read view with copy/reveal actions)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models import Account, LicenseMode, Service
from app.ui.labels import (
    BINDING_ROLE_LABELS,
    IDENTITY_KIND_LABELS,
    LICENSE_MODE_LABELS,
    LOGIN_METHOD_LABELS,
    SERVICE_TYPE_LABELS,
)
from app.ui import icons, theme
from app.ui.categories import categories, category_key, main_category
from app.ui.widgets import Card, CopyRow, SecretRow, SectionHeader

_EMPTY_HINT = "从中间列表选择一个账户查看详情"


def _local_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value[:19].replace("T", " ")


class DetailPanel(QWidget):
    #: emitted whenever any credential/value of ``account_uuid`` was copied
    credential_copied = Signal(str)
    account_changed = Signal()
    edit_requested = Signal()
    delete_requested = Signal()

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.setObjectName("detailPane")
        self.setMinimumWidth(320)
        self._catalog = catalog
        self._current_uuid: str | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        self._content = QWidget()
        self._content.setObjectName("detailContent")
        shell = QWidget()
        shell.setObjectName("detailShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(24, 0, 24, 0)
        # Keep the scroll area's child at least as tall as the dynamic detail
        # content. Without this constraint Qt compresses long account cards
        # into the viewport instead of exposing a vertical scrollbar.
        shell_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        shell_layout.addStretch(1)
        # Let the reading column use the available width up to its maximum;
        # the side stretches then keep the capped column centered.
        shell_layout.addWidget(self._content, 100)
        shell_layout.addStretch(1)
        self._content.setMaximumWidth(616)
        self._content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(28, 30, 28, 30)
        self._content_layout.setSpacing(20)
        self._content_layout.addStretch(1)
        self._scroll.setWidget(shell)

        self.show_empty()

    # -- public ------------------------------------------------------------

    def show_empty(self, hint: str = _EMPTY_HINT) -> None:
        self._clear()
        self._current_uuid = None
        hint_label = QLabel(hint)
        hint_label.setProperty("muted", True)
        hint_label.setTextFormat(Qt.TextFormat.PlainText)
        hint_label.setWordWrap(True)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel("账户详情")
        heading.setProperty("title", True)
        heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._content_layout.addStretch(1)
        self._content_layout.addWidget(heading)
        self._content_layout.addWidget(hint_label)
        self._content_layout.addStretch(1)

    def show_account(self, service: Service, account: Account) -> None:
        self._clear()
        self._current_uuid = account.uuid
        on_copied = (lambda: self.credential_copied.emit(self._current_uuid))

        self._scroll.verticalScrollBar().setValue(0)
        # Keep account identity and its actions together in one compact header.
        header = QHBoxLayout()
        avatar = QLabel()
        avatar.setProperty("avatar", True)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(44, 44)
        palette = theme.PALETTES[theme.current_theme()]
        icon_name = categories.get(main_category(service, account), "grid")
        avatar.setPixmap(icons.line_icon(icon_name, palette["accent"]).pixmap(22, 22))
        header.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)

        title_group = QWidget()
        title_layout = QVBoxLayout(title_group)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)
        title = QLabel(service.name + (f" · {account.alias}" if account.alias else ""))
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setProperty("title", True)
        title.setWordWrap(True)
        title_layout.addWidget(title)
        category = QLabel(main_category(service, account))
        category.setProperty("muted", True)
        title_layout.addWidget(category)
        header.addWidget(title_group, 1, Qt.AlignmentFlag.AlignVCenter)

        icon_color = palette["muted"]
        edit = QToolButton()
        edit.setIcon(icons.line_icon("edit", icon_color))
        edit.setObjectName("editAccount")
        edit.setToolTip("编辑账户")
        edit.setAccessibleName("编辑账户")
        edit.setAutoRaise(True)
        edit.clicked.connect(self.edit_requested.emit)
        header.addWidget(edit)
        more = QToolButton()
        more.setIcon(icons.line_icon("more", icon_color))
        more.setToolTip("更多账户操作")
        more.setAccessibleName("更多账户操作")
        more.setObjectName("accountMore")
        more.setAutoRaise(True)
        menu = QMenu(more)
        delete = menu.addAction("移入回收站")
        delete.triggered.connect(self.delete_requested.emit)
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(more)
        self._content_layout.addLayout(header)

        # credentials card
        if account.username or account.password:
            cred = Card()
            cred.setObjectName("credentials")
            cred.add_row(SectionHeader("登录凭据"))
            if account.username:
                cred.add_row(CopyRow("账号", account.username, on_copied=on_copied))
            if account.password:
                cred.add_row(SecretRow("密码", account.password, on_copied=on_copied))
            self._content_layout.addWidget(cred)
        urls = list(dict.fromkeys(url for url in [account.primary_url, *service.urls, *service.login_urls] if url))
        if urls:
            sites = Card()
            sites.add_row(SectionHeader("登录网址"))
            for index, url in enumerate(urls):
                sites.add_row(CopyRow("主网址" if index == 0 else "关联网址", url, on_copied=on_copied))
            self._content_layout.addWidget(sites)
        contact = Card()
        contact.add_row(SectionHeader("邮箱与手机"))
        if account.email:
            contact.add_row(CopyRow("注册邮箱", account.email, on_copied=on_copied))
        if account.phone:
            contact.add_row(CopyRow("手机号", account.phone, on_copied=on_copied))
        if account.email or account.phone:
            self._content_layout.addWidget(contact)
        else:
            contact.deleteLater()

        # login methods
        if account.login_methods:
            methods = Card()
            methods.add_row(SectionHeader("登录方式"))
            for lm in account.login_methods:
                label = LOGIN_METHOD_LABELS.get(lm.type, lm.type.value)
                identity = self._catalog.identity_label(lm.identity_ref)
                text = label + (f" · {identity}" if identity else "")
                if lm.note:
                    text += f"（{lm.note}）"
                methods.add_row(self._plain_row(text))
            self._content_layout.addWidget(methods)

        # identity bindings
        if account.identity_bindings:
            bindings = Card()
            bindings.add_row(SectionHeader("绑定身份"))
            for binding in account.identity_bindings:
                role = BINDING_ROLE_LABELS.get(binding.role, binding.role.value)
                identity = self._catalog.identity(binding.identity_ref)
                desc = role
                if identity is not None:
                    desc += f" · {identity.label or identity.value}"
                    if identity.kind is not None:
                        desc += f"（{IDENTITY_KIND_LABELS.get(identity.kind, identity.kind.value)}）"
                bindings.add_row(self._plain_row(desc))
            self._content_layout.addWidget(bindings)

        # license
        if account.license.mode != LicenseMode.NONE:
            lic = account.license
            license_card = Card()
            license_card.add_row(SectionHeader("付费授权"))
            license_card.add_row(
                CopyRow("类型", LICENSE_MODE_LABELS.get(lic.mode, lic.mode.value))
            )
            if lic.license_key:
                license_card.add_row(SecretRow("激活码", lic.license_key, on_copied=on_copied))
            if lic.order_no:
                license_card.add_row(CopyRow("订单号", lic.order_no, on_copied=on_copied))
            if lic.expires:
                license_card.add_row(CopyRow("有效期至", lic.expires))
            if lic.purchase_date:
                license_card.add_row(CopyRow("购买日期", lic.purchase_date))
            if lic.channel:
                license_card.add_row(CopyRow("渠道", lic.channel))
            if lic.device_limit is not None:
                license_card.add_row(CopyRow("设备数限制", str(lic.device_limit)))
            if lic.evidence:
                license_card.add_row(CopyRow("购买凭据", lic.evidence))
            if lic.notes:
                license_card.add_row(CopyRow("授权备注", lic.notes))
            self._content_layout.addWidget(license_card)

        # custom fields
        visible_fields = [field for field in account.custom_fields if not (
            field.key == category_key and not field.protected and field.value in categories)]
        if visible_fields:
            fields_card = Card()
            fields_card.add_row(SectionHeader("自定义字段"))
            for field in visible_fields:
                if field.protected:
                    fields_card.add_row(SecretRow(field.key, field.value, on_copied=on_copied))
                else:
                    fields_card.add_row(CopyRow(field.key, field.value, on_copied=on_copied))
            self._content_layout.addWidget(fields_card)

        # notes
        if account.notes:
            notes = Card()
            notes.add_row(SectionHeader("备注"))
            notes_label = QLabel(account.notes)
            notes_label.setTextFormat(Qt.TextFormat.PlainText)
            notes_label.setWordWrap(True)
            notes_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            notes.add_row(notes_label)
            self._content_layout.addWidget(notes)

        # timestamps
        times = []
        if account.created_at:
            times.append("创建 " + _local_time(account.created_at))
        if account.modified_at:
            times.append("修改 " + _local_time(account.modified_at))
        if times:
            stamp = QLabel("   ".join(times))
            stamp.setProperty("muted", True)
            self._content_layout.addWidget(stamp)

        self._content_layout.addStretch(1)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _plain_row(text: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _divider() -> QWidget:
        line = QWidget()
        line.setProperty("divider", True)
        line.setFixedHeight(1)
        return line

    def _clear(self) -> None:
        for row in self._content.findChildren(SecretRow):
            row.set_value("")
            row._on_copied = None
        for row in self._content.findChildren(CopyRow):
            row.set_value("")
            row._on_copied = None
        for label in self._content.findChildren(QLabel):
            label.clear()
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif item.layout() is not None:
                layout = item.layout()
                while layout.count():
                    sub = layout.takeAt(0)
                    if sub.widget() is not None:
                        sub.widget().hide()
                        sub.widget().deleteLater()
