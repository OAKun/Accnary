# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:11
# @Modified  : 2026-10-25 19:11
# @Python    : 3.14.9
# @Description: Virtualized account rows with local category icons and elided public summaries.
"""Paint visible rows only; credentials never enter display roles."""

from urllib.parse import urlsplit

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from app.ui import icons, theme
from app.ui.labels import LICENSE_MODE_LABELS, LOGIN_METHOD_LABELS, SERVICE_TYPE_LABELS
from app.ui.categories import categories, main_category

pair_role = Qt.ItemDataRole.UserRole
summary_role = int(pair_role) + 1


def category_icon(service, account):
    return categories[main_category(service, account)]


def public_summary(service, account):
    """Only the same public account attributes already shown by the UI."""
    identity = account.username or account.email
    if not identity:
        identity = " / ".join(dict.fromkeys(
            LOGIN_METHOD_LABELS.get(method.type, method.type.value)
            for method in account.login_methods
        )) or "无密码账户"
    subtitle = " · ".join(part for part in (account.alias, identity) if part)
    url = account.primary_url or next(iter(service.urls), "")
    try:
        host = urlsplit(url if "://" in url else "//" + url).hostname if url else ""
    except ValueError:  # Existing free-text URLs may be incomplete while editing.
        host = ""
    meta = main_category(service, account)
    if account.license.mode.value != "none":
        meta += " · " + LICENSE_MODE_LABELS.get(account.license.mode, "授权")
    elif host:
        meta += " · " + host
    return service.name, subtitle, meta


class AccountDelegate(QStyledItemDelegate):
    """One shared delegate instead of thousands of QLabel/QWidget objects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icons = {}

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(300, 72)

    def _icon(self, name, color):
        key = name, color
        if key not in self._icons:
            self._icons[key] = icons.line_icon(name, color)
        return self._icons[key]

    def paint(self, painter, option, index):
        data = index.data(summary_role)
        if not data:
            return
        title, subtitle, meta, icon_name = data
        colors = theme.PALETTES[theme.current_theme()]
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        row = option.rect.adjusted(6, 2, -6, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors["selected" if selected else "hover"]))
            painter.drawRoundedRect(row, 8, 8)
        icon_box = QRect(row.left() + 12, row.top() + 18, 24, 24)
        self._icon(icon_name, colors["accent"] if selected else colors["muted"]).paint(painter, icon_box)
        left, right = row.left() + 48, row.right() - 12
        font = QFont(option.font)
        font.setPixelSize(theme.TYPE["body"])
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(colors["text"]))
        painter.drawText(QRect(left, row.top() + 8, right - left, 22), Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(font).elidedText(title, Qt.TextElideMode.ElideRight, right - left))
        font.setPixelSize(theme.TYPE["small"])
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(colors["muted"]))
        width = row.right() - 12 - left
        secondary = " · ".join(part for part in (subtitle, meta) if part)
        painter.drawText(QRect(left, row.top() + 34, width, 18), Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(font).elidedText(secondary, Qt.TextElideMode.ElideRight, width))
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_color = QColor(colors["accent"])
            focus_color.setAlpha(150)
            painter.setPen(QPen(focus_color, 1, Qt.PenStyle.SolidLine))
            painter.drawRoundedRect(row.adjusted(1, 1, -1, -1), 8, 8)
        painter.restore()
