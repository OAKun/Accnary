# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 18:52
# @Modified  : 2026-10-25 18:09
# @Python    : 3.14.9
# @Description: Accnary app / ui / icons
"""Application icon loading (assets/app-icon.png - 蓝色钥匙孔字母 A)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_icon: QIcon | None = None


def app_icon() -> QIcon:
    global _icon
    if _icon is None:
        path = _ASSETS / "app-icon.png"
        _icon = QIcon(str(path)) if path.is_file() else QIcon()
    return _icon


def line_icon(name: str, color: str = "#607087") -> QIcon:
    """Small native line icons; no SVG engine or icon-font dependency."""
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    painter.setPen(QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == "add":
        painter.drawLine(10, 4, 10, 16)
        painter.drawLine(4, 10, 16, 10)
    elif name == "search":
        painter.drawEllipse(QRectF(3, 3, 10, 10))
        painter.drawLine(12, 12, 17, 17)
    elif name == "lock":
        painter.drawRoundedRect(QRectF(4, 9, 12, 8), 2, 2)
        painter.drawArc(QRectF(6, 2, 8, 12), 0, 180 * 16)
        painter.drawLine(10, 12, 10, 14)
    elif name == "edit":
        path = QPainterPath()
        path.moveTo(4, 12); path.lineTo(12, 4); path.lineTo(16, 8)
        path.lineTo(8, 16); path.lineTo(4, 16); path.closeSubpath()
        painter.drawPath(path)
    elif name in ("trash", "recycle"):
        painter.drawLine(3, 5, 17, 5)
        painter.drawLine(7, 3, 13, 3)
        painter.drawRoundedRect(QRectF(5, 5, 10, 12), 1, 1)
        painter.drawLine(8, 8, 8, 14); painter.drawLine(12, 8, 12, 14)
    elif name == "clock":
        painter.drawEllipse(QRectF(3, 3, 14, 14))
        painter.drawLine(10, 6, 10, 10); painter.drawLine(10, 10, 13, 12)
    elif name == "theme":
        painter.drawEllipse(QRectF(3, 3, 14, 14))
        painter.setBrush(QColor(color))
        painter.drawChord(QRectF(3, 3, 14, 14), 90 * 16, 180 * 16)
    elif name == "settings":
        for y in (5, 10, 15):
            painter.drawLine(3, y, 17, y)
        painter.setBrush(QColor(color))
        for x, y in ((7, 5), (13, 10), (8, 15)):
            painter.drawEllipse(QRectF(x - 1.5, y - 1.5, 3, 3))
    elif name == "globe":
        painter.drawEllipse(QRectF(3, 3, 14, 14))
        painter.drawEllipse(QRectF(7, 3, 6, 14))
        painter.drawLine(3, 10, 17, 10)
    elif name == "desktop":
        painter.drawRoundedRect(QRectF(2, 3, 16, 11), 1.5, 1.5)
        painter.drawLine(10, 14, 10, 18)
        painter.drawLine(6, 18, 14, 18)
    elif name == "phone":
        painter.drawRoundedRect(QRectF(5, 2, 10, 16), 2, 2)
        painter.drawLine(9, 15, 11, 15)
    elif name == "server":
        for y in (3, 11):
            painter.drawRoundedRect(QRectF(2, y, 16, 6), 1, 1)
            painter.drawLine(5, y + 3, 6, y + 3)
            painter.drawLine(10, y + 3, 15, y + 3)
    elif name == "code":
        painter.drawLine(6, 5, 2, 10)
        painter.drawLine(2, 10, 6, 15)
        painter.drawLine(14, 5, 18, 10)
        painter.drawLine(18, 10, 14, 15)
        painter.drawLine(12, 3, 8, 17)
    elif name == "research":
        painter.drawLine(7, 2, 13, 2)
        path = QPainterPath()
        path.moveTo(8, 2); path.lineTo(8, 8); path.lineTo(3, 16)
        path.lineTo(4, 18); path.lineTo(16, 18); path.lineTo(17, 16)
        path.lineTo(12, 8); path.lineTo(12, 2)
        painter.drawPath(path)
        painter.drawLine(6, 13, 14, 13)
    elif name == "cloud":
        path = QPainterPath()
        path.moveTo(5, 16); path.cubicTo(-1, 16, 0, 8, 6, 8)
        path.cubicTo(5, 0, 17, 1, 16, 9)
        path.cubicTo(21, 9, 20, 16, 15, 16); path.closeSubpath()
        painter.drawPath(path)
    elif name == "backup":
        painter.drawRoundedRect(QRectF(3, 3, 14, 14), 2, 2)
        painter.drawLine(6, 7, 14, 7)
        painter.drawLine(10, 10, 10, 15)
        painter.drawLine(7, 12, 10, 15); painter.drawLine(10, 15, 13, 12)
    elif name == "more":
        painter.setBrush(QColor(color))
        for x in (4, 10, 16):
            painter.drawEllipse(QRectF(x - 1, 9, 2, 2))
    elif name == "copy":
        painter.drawRoundedRect(QRectF(7, 2, 10, 12), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(3, 6, 10, 12), 1.5, 1.5)
    elif name in ("eye", "eye_off"):
        path = QPainterPath()
        path.moveTo(2, 10)
        path.cubicTo(6, 4, 14, 4, 18, 10)
        path.cubicTo(14, 16, 6, 16, 2, 10)
        painter.drawPath(path)
        painter.drawEllipse(QRectF(8, 8, 4, 4))
        if name == "eye_off":
            painter.drawLine(3, 17, 17, 3)
    elif name == "back":
        painter.drawLine(4, 10, 11, 4)
        painter.drawLine(4, 10, 11, 16)
        painter.drawLine(5, 10, 18, 10)
    elif name == "chat":
        path = QPainterPath()
        path.moveTo(4, 4); path.lineTo(16, 4); path.lineTo(16, 13)
        path.lineTo(9, 13); path.lineTo(5, 17); path.lineTo(5, 13)
        path.lineTo(3, 13); path.lineTo(3, 4); path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(6, 8, 13, 8)
    elif name == "mail":
        painter.drawRoundedRect(QRectF(2, 4, 16, 12), 2, 2)
        painter.drawLine(3, 5, 10, 11); painter.drawLine(10, 11, 17, 5)
    elif name == "wallet":
        painter.drawRoundedRect(QRectF(2, 4, 16, 13), 2, 2)
        painter.drawRoundedRect(QRectF(12, 8, 7, 6), 1, 1)
        painter.drawPoint(15, 11)
    else:
        for x in (3, 11):
            for y in (3, 11):
                painter.drawRoundedRect(QRectF(x, y, 6, 6), 1, 1)
    painter.end()
    return QIcon(pixmap)
