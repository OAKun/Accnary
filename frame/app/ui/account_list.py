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
    alias = account.alias.strip()
    title = alias or service.name
    subtitle = f"{service.name} · {identity}" if alias and alias != service.name else identity
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
    return title, subtitle, meta


class AccountDelegate(QStyledItemDelegate):
    """One shared delegate instead of thousands of QLabel/QWidget objects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icons = {}
        self._base_font = None
        self._theme_name = None

    def sizeHint(self, option, index):  # noqa: N802
        return QSize(300, 60)

    def _icon(self, name, color):
        key = name, color
        if key not in self._icons:
            self._icons[key] = icons.line_icon(name, color)
        return self._icons[key]

    def _update_fonts(self, font: QFont) -> None:
        self._base_font = QFont(font)
        self._title_font = QFont(font)
        self._title_font.setPixelSize(theme.TYPE["body"])
        self._title_font.setWeight(QFont.Weight.DemiBold)
        self._title_metrics = QFontMetrics(self._title_font)
        self._subtitle_font = QFont(font)
        self._subtitle_font.setPixelSize(theme.TYPE["small"])
        self._subtitle_font.setWeight(QFont.Weight.Normal)
        self._subtitle_metrics = QFontMetrics(self._subtitle_font)

    def _update_palette(self, name: str) -> None:
        self._theme_name = name
        self._palette = theme.PALETTES[name]
        self._colors = {
            role: QColor(self._palette[role])
            for role in ("text", "muted", "accent", "hover", "selected")
        }
        focus_color = QColor(self._colors["accent"])
        focus_color.setAlpha(150)
        self._focus_pen = QPen(focus_color, 1, Qt.PenStyle.SolidLine)

    def paint(self, painter, option, index):
        data = index.data(summary_role)
        if not data:
            return
        title, subtitle, meta, icon_name = data
        theme_name = theme.current_theme()
        if self._theme_name != theme_name:
            self._update_palette(theme_name)
        if self._base_font != option.font:
            self._update_fonts(option.font)
        colors = self._colors
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        row = option.rect.adjusted(6, 2, -6, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colors["selected" if selected else "hover"])
            painter.drawRoundedRect(row, 8, 8)
        if selected:
            painter.setBrush(colors["accent"])
            painter.drawRoundedRect(QRect(row.left() + 3, row.center().y() - 10, 3, 20), 1, 1)
        icon_box = QRect(row.left() + 10, row.center().y() - 10, 20, 20)
        self._icon(icon_name, self._palette["accent" if selected else "muted"]).paint(painter, icon_box)
        left, right = row.left() + 42, row.right() - 10
        painter.setFont(self._title_font)
        painter.setPen(colors["text"])
        painter.drawText(QRect(left, row.top() + 6, right - left, 21), Qt.AlignmentFlag.AlignVCenter,
                         self._title_metrics.elidedText(title, Qt.TextElideMode.ElideRight, right - left))
        painter.setFont(self._subtitle_font)
        painter.setPen(colors["muted"])
        width = row.right() - 12 - left
        secondary = subtitle or meta
        painter.drawText(QRect(left, row.top() + 29, width, 18), Qt.AlignmentFlag.AlignVCenter,
                         self._subtitle_metrics.elidedText(secondary, Qt.TextElideMode.ElideRight, width))
        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(self._focus_pen)
            painter.drawRoundedRect(row.adjusted(1, 1, -1, -1), 8, 8)
        painter.restore()
