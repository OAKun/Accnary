# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 22:13
# @Modified  : 2026-10-27 11:15
# @Python    : 3.14.9
# @Description: Accnary app / ui / main_window
"""Main window: three-pane layout per the spec.

left   - navigation: 全部账户 / 最近使用 + 按平台类型分类
middle - account list; the top search box switches it to scored smart-search
         results (spec section 5) whenever a query is typed
right  - detail panel (collapsible via splitter)

All data access goes through CatalogService - no direct KDBX access here.
The smart-search index lives in the catalog service (RAM only, cleared on
lock); copying a credential records 最近使用 and persists it.
"""

from __future__ import annotations

import ctypes
import html
import sys
import time

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QEvent,
    QSize,
    QObject,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.errors import (
    AccnaryError,
    BadCredentialsError,
    ConflictError,
    SafeSaveError,
    VaultError,
    VaultFormatError,
)
from app.models import Account, Service, ServiceType
from app.services import CatalogService
from app.ui import icons, theme
from app.security.clipboard import clear_owned_clipboard
from app.ui.account_editor import AccountEditor
from app.ui.account_list import AccountDelegate, category_icon, pair_role, public_summary, summary_role
from app.ui.backup_dialog import BackupDialog
from app.ui.detail_panel import DetailPanel
from app.ui.labels import NAV_ALL
from app.ui.master_password_dialog import MasterPasswordDialog
from app.ui.categories import categories, main_category
from app.ui.recycle_bin_dialog import RecycleBinDialog
from app.ui.settings import app_settings
from app.ui.settings_dialog import SettingsDialog
from app.ui.storage_task import execute_storage_task
from app.ui.update_flow import UpdateFlow

WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x0007
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
_SEARCH_RESULT_LIMIT = 50


class _SessionSignals(QObject):
    session_locked = Signal()


class SessionLockFilter(QAbstractNativeEventFilter):
    """Locks the vault when the Windows session is locked (Win+L).

    Registers for WTS session notifications on the main window handle;
    silently degrades on platforms where that is unavailable.
    """

    def __init__(self, hwnd: int):
        super().__init__()
        self._signals = _SessionSignals()
        self.session_locked = self._signals.session_locked
        self._hwnd = hwnd
        self._registered = False
        try:
            import ctypes

            result = ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                hwnd, 0  # NOTIFY_FOR_THIS_SESSION
            )
            self._registered = bool(result)
        except Exception:
            self._registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt naming)
        if not self._registered:
            return False, 0
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                import ctypes.wintypes as wintypes

                msg = wintypes.MSG.from_address(int(message))
                if ((msg.message == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_LOCK)
                        or (msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMSUSPEND)):
                    self.session_locked.emit()
        except Exception:
            pass
        return False, 0

    def shutdown(self) -> None:
        if self._registered:
            try:
                ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(self._hwnd)
            except Exception:
                pass
            self._registered = False


class _ActivityMonitor(QObject):
    """Tracks last user activity by filtering application events."""

    def __init__(self, app: QApplication):
        QObject.__init__(self)
        self._last_activity = time.monotonic()
        app.installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        if event.type() in (
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
        ):
            self._last_activity = time.monotonic()
        return False

    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity


class MainWindow(QMainWindow):
    def __init__(self, catalog: CatalogService, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle("Accnary")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(560, 480)
        screen = QApplication.instance().primaryScreen()
        available = screen.availableGeometry() if screen else None
        self.resize(min(1220, available.width() - 40) if available else 1220,
                    min(850, available.height() - 60) if available else 850)

        self._session_filter: SessionLockFilter | None = None
        self._activity = _ActivityMonitor(QApplication.instance())
        self._storage_busy = False
        self._lock_after_storage = False
        self._close_after_storage = False
        self._shortcuts = []
        self._locked_vault_path: str | None = None
        self.update_flow = UpdateFlow(self)

        self._nav_open = False
        self._mobile_detail = False
        self._responsive_signature = None
        self._desktop_splitter_sizes: list[int] | None = None
        self._pending_splitter_state = None
        self._build_header()
        self._build_central()
        self._setup_native_filters()
        self._setup_idle_timer()

        self._update_context()
        self._refresh_accounts()
        self._update_responsive()

    # ------------------------------------------------------------------ chrome

    def _build_header(self) -> None:
        self.app_header = QWidget()
        self.app_header.setObjectName("appHeader")
        self.app_header.setFixedHeight(64)
        header = QHBoxLayout(self.app_header)
        header.setContentsMargins(22, 0, 18, 0)
        header.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(26, 26))
        header.addWidget(logo)
        brand = QLabel("Accnary")
        brand.setProperty("brand", True)
        header.addWidget(brand)
        separator = QWidget()
        separator.setObjectName("headerSeparator")
        separator.setFixedSize(1, 24)
        header.addWidget(separator)
        self.vault_label = QLabel()
        self.vault_label.setObjectName("vaultLabel")
        self.vault_label.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(self.vault_label)
        header.addStretch(1)

        self.nav_button = QToolButton()
        self.nav_button.setObjectName("navigationToggle")
        self.nav_button.setText("分类")
        self.nav_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.nav_button.setToolTip("显示账户分类")
        self.nav_button.clicked.connect(self._toggle_navigation)
        header.addWidget(self.nav_button)

        self.back_button = QToolButton()
        self.back_button.setObjectName("backToList")
        self.back_button.setText("返回列表")
        self.back_button.clicked.connect(self._back_to_list)
        header.addWidget(self.back_button)

        self.new_action = QAction(icons.line_icon("add", "#ffffff"), "新建账户", self)
        self.new_action.triggered.connect(self._new_account)
        self.edit_action = QAction("编辑账户", self)
        self.edit_action.triggered.connect(self._edit_selected)
        self.delete_action = QAction("移入回收站", self)
        self.delete_action.triggered.connect(self._delete_selected)

        self.lock_button = QToolButton()
        self.lock_button.setObjectName("lockButton")
        self.lock_button.setText("锁定")
        self.lock_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.lock_button.setToolTip("锁定密码库")
        self.lock_button.setAccessibleName("锁定密码库")
        self.lock_button.clicked.connect(self.lock_and_unlock)
        header.addWidget(self.lock_button)

        self.more_button = QToolButton()
        self.more_button.setObjectName("moreMenuButton")
        self.more_button.setToolTip("更多操作")
        self.more_button.setAccessibleName("更多操作")
        self.more_menu = QMenu(self.more_button)
        self.recycle_action = self.more_menu.addAction("回收站")
        self.recycle_action.triggered.connect(self._open_recycle_bin)
        self.backup_action = self.more_menu.addAction("备份与恢复")
        self.backup_action.triggered.connect(self._open_backups)
        self.more_menu.addSeparator()
        self.update_action = self.more_menu.addAction("检查更新")
        self.update_action.triggered.connect(
            lambda: self.update_flow.check(manual=True)
        )
        self.update_flow.busy_changed.connect(self.update_action.setDisabled)
        self.settings_action = self.more_menu.addAction("设置")
        self.settings_action.triggered.connect(self._open_settings)
        self.more_button.setMenu(self.more_menu)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(self.more_button)

        self._shortcuts.extend((
            _add_shortcut(self, "Ctrl+F", self._focus_search),
            _add_shortcut(self, "Ctrl+N", self._new_account),
            _add_shortcut(self, "Ctrl+E", self._edit_selected),
            _add_shortcut(self, "Ctrl+L", self.lock_and_unlock),
            _add_shortcut(self, "Esc", lambda: self.search_edit.clear()),
        ))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.theme_changed.connect(self._set_theme)
        dialog.change_master_password_requested.connect(self._change_master_password)
        dialog.exec()
        dialog.deleteLater()

    def _change_master_password(self) -> None:
        dialog = MasterPasswordDialog(self.catalog, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            QMessageBox.information(
                self,
                "主密码已修改",
                "此后请使用新主密码解锁。已有加密备份仍需使用生成时的主密码。",
            )

    def _toggle_theme(self) -> None:
        self._set_theme("dark" if theme.current_theme() == "light" else "light")

    def _set_theme(self, name: str) -> None:
        theme.apply_theme(QApplication.instance(), name)
        app_settings().setValue("theme", name)
        self.account_list.viewport().update()
        self._refresh_icons()
        pair = self._selected_pair()
        if pair:
            self.detail_panel.show_account(*pair)

    def _refresh_icons(self) -> None:
        color = theme.PALETTES[theme.current_theme()]["muted"]
        for index in range(self.nav_list.count()):
            item = self.nav_list.item(index)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name:
                item.setIcon(icons.line_icon(name, color))
        self.nav_button.setIcon(icons.line_icon("grid", color))
        self.back_button.setIcon(icons.line_icon("back", color))
        self.lock_button.setIcon(icons.line_icon("lock", color))
        self.more_button.setIcon(icons.line_icon("more", color))
        self.recycle_action.setIcon(icons.line_icon("recycle", color))
        self.backup_action.setIcon(icons.line_icon("backup", color))
        self.settings_action.setIcon(icons.line_icon("settings", color))
        self.app_header.update()

    def _focus_search(self) -> None:
        if self.width() < 760 and self._mobile_detail:
            self._back_to_list()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ------------------------------------------------------------------ central

    def _build_central(self) -> None:
        central = QWidget()
        central.setObjectName("workspaceRoot")
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.app_header)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        central_layout.addWidget(self.splitter, 1)
        self.workspace_page = central
        self.lock_page = self._build_lock_page()
        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self.workspace_page)
        self.page_stack.addWidget(self.lock_page)
        self.setCentralWidget(self.page_stack)

        sidebar = QWidget()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 24, 12, 16)
        side.setSpacing(8)
        vault_title = QLabel("我的密码库")
        vault_title.setProperty("paneTitle", True)
        side.addWidget(vault_title)
        side.addSpacing(16)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navigation")
        self.nav_list.setIconSize(QSize(18, 18))
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.currentRowChanged.connect(
            lambda _i: self._refresh_accounts(update_navigation=False)
        )
        self.nav_list.itemClicked.connect(self._on_navigation_clicked)
        side.addWidget(self.nav_list, 1)
        local = QLabel("本地加密 · 关闭即退出")
        local.setObjectName("localHint")
        side.addWidget(local)
        self.splitter.addWidget(sidebar)

        middle = QWidget()
        self.middle_pane = middle
        middle.setObjectName("listPane")
        middle.setMinimumWidth(310)
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(0)
        list_header = QWidget()
        list_header.setObjectName("listHeader")
        header = QVBoxLayout(list_header)
        header.setContentsMargins(18, 22, 18, 16)
        header.setSpacing(12)
        title_row = QHBoxLayout()
        self.list_title = QLabel(NAV_ALL)
        self.list_title.setProperty("paneTitle", True)
        title_row.addWidget(self.list_title, 1)
        self.result_count = QLabel()
        self.result_count.setProperty("muted", True)
        title_row.addWidget(self.result_count)
        self.new_button = QToolButton()
        self.new_button.setDefaultAction(self.new_action)
        self.new_button.setText("新建")
        self.new_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.new_button.setProperty("variant", "primary")
        title_row.addWidget(self.new_button)
        header.addLayout(title_row)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("globalSearch")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("搜索账号、网址、邮箱或绑定信息")
        self.search_edit.setToolTip("支持名称、邮箱、身份与长网址片段 · Ctrl+F")
        self.search_edit.addAction(icons.line_icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_edit.textChanged.connect(
            lambda _text: self._refresh_accounts(update_navigation=False)
        )
        header.addWidget(self.search_edit)
        order_row = QHBoxLayout()
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("accountSort")
        self.sort_combo.addItem("最近使用", "recent")
        self.sort_combo.addItem("按名称", "name")
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(app_settings().value("account_sort", "recent"))))
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)
        order_row.addWidget(self.sort_combo)
        self.search_scope = QLabel("全部账户 · 按匹配度排序")
        self.search_scope.setProperty("muted", True)
        order_row.addWidget(self.search_scope)
        order_row.addStretch(1)
        header.addLayout(order_row)
        middle_layout.addWidget(list_header)
        self.account_list = QListWidget()
        self.account_list.setObjectName("accountList")
        self.account_list.setUniformItemSizes(True)
        self.account_list.setMouseTracking(True)
        self.account_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.account_list.setItemDelegate(AccountDelegate(self.account_list))
        self.account_list.currentItemChanged.connect(self._on_selection)
        self.account_list.itemClicked.connect(self._activate_detail)
        self.account_list.itemActivated.connect(self._activate_detail)
        self.account_list.itemDoubleClicked.connect(lambda *_args: self._edit_selected() if self.width() >= 760 else None)
        middle_layout.addWidget(self.account_list, 1)
        self.list_empty = QLabel("暂无账户")
        self.list_empty.setObjectName("listEmpty")
        self.list_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_empty.setWordWrap(True)
        middle_layout.addWidget(self.list_empty, 1)
        self.splitter.addWidget(middle)

        self.detail_panel = self._make_detail_panel()
        self.splitter.addWidget(self.detail_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setSizes([188, 328, 704])
        self._pending_splitter_state = app_settings().value("workspace_splitter")
        self._refresh_icons()

    def _build_lock_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("lockPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("lockCard")
        card.setProperty("card", True)
        card.setMaximumWidth(460)
        content = QVBoxLayout(card)
        content.setContentsMargins(32, 28, 32, 28)
        content.setSpacing(14)

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(38, 38))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(logo)

        title = QLabel("密码库已锁定")
        title.setProperty("title", True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(title)

        subtitle = QLabel("重新输入主密码以继续使用当前密码库")
        subtitle.setProperty("muted", True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        content.addWidget(subtitle)

        path_heading = QLabel("当前密码库")
        path_heading.setProperty("section", True)
        content.addWidget(path_heading)
        self.lock_vault_path = QLabel()
        self.lock_vault_path.setObjectName("lockVaultPath")
        self.lock_vault_path.setProperty("muted", True)
        self.lock_vault_path.setWordWrap(True)
        self.lock_vault_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        content.addWidget(self.lock_vault_path)

        password_label = QLabel("主密码")
        password_label.setProperty("section", True)
        content.addWidget(password_label)
        self.lock_password_edit = QLineEdit()
        self.lock_password_edit.setObjectName("inlineUnlockPassword")
        self.lock_password_edit.setAccessibleName("主密码")
        self.lock_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.lock_password_edit.setPlaceholderText("输入主密码")
        self.lock_password_edit.returnPressed.connect(self._unlock_locked_vault)
        content.addWidget(self.lock_password_edit)

        self.lock_error_label = QLabel()
        self.lock_error_label.setProperty("error", True)
        self.lock_error_label.setAccessibleName("解锁错误提示")
        self.lock_error_label.setWordWrap(True)
        content.addWidget(self.lock_error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        exit_button = QPushButton("退出")
        exit_button.clicked.connect(self.close)
        buttons.addWidget(exit_button)
        self.lock_unlock_button = QPushButton("解锁")
        self.lock_unlock_button.setProperty("variant", "primary")
        self.lock_unlock_button.clicked.connect(self._unlock_locked_vault)
        buttons.addWidget(self.lock_unlock_button)
        content.addLayout(buttons)

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        return page

    def _make_detail_panel(self) -> DetailPanel:
        panel = DetailPanel(self.catalog)
        panel.credential_copied.connect(self._on_credential_copied)
        panel.account_changed.connect(self._after_data_change)
        panel.edit_requested.connect(self._edit_selected)
        panel.delete_requested.connect(self._delete_selected)
        return panel

    def _run_storage_task(self, title, operation, parent=None):
        """Keep the UI responsive while serializing access to this catalog."""
        if self._storage_busy:
            raise RuntimeError("another password-vault operation is already running")
        self._storage_busy = True
        self._idle_timer.stop()
        try:
            return execute_storage_task(parent or self, title, operation)
        finally:
            self._storage_busy = False
            self._idle_timer.start()
            if self._close_after_storage:
                self._close_after_storage = False
                self._lock_after_storage = False
                QTimer.singleShot(0, self.close)
            elif self._lock_after_storage:
                self._lock_after_storage = False
                QTimer.singleShot(0, self.lock_and_unlock)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._storage_busy:
            self._close_after_storage = True
            event.ignore()
            return
        if not self.catalog.is_locked and self.catalog.has_unsaved_changes:
            try:
                self._run_storage_task("正在安全保存密码库…", self.catalog.save)
            except Exception as exc:
                answer = QMessageBox.question(
                    self, "退出前保存失败",
                    f"数据尚未保存（{type(exc).__name__}）。\n"
                    "是否放弃未保存的修改并退出？选择“否”可取消退出。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
        if self.width() >= 1000:
            app_settings().setValue("workspace_splitter", self.splitter.saveState())
        self._idle_timer.stop()
        self._shutdown_native()
        QApplication.instance().removeEventFilter(self._activity)
        self._clear_sensitive_views()
        self.catalog.lock()
        clear_owned_clipboard()
        event.accept()
        super().closeEvent(event)

    def _clear_sensitive_views(self) -> None:
        for dialog in self.findChildren(QDialog):
            if dialog.isVisible():
                dialog.reject()
        self.search_edit.clear()
        self.account_list.clear()
        self.detail_panel.show_empty("已锁定")
        self.list_title.setText("已锁定")
        self.result_count.clear()
        self.vault_label.clear()
        self.list_empty.setText("密码库已锁定")
        self.lock_password_edit.clear()
        self.lock_error_label.clear()
        self.lock_vault_path.clear()

    # ------------------------------------------------------------------ native

    def _setup_native_filters(self) -> None:
        if sys.platform != "win32" or not self.winId():
            return
        hwnd = int(self.winId())
        try:
            self._session_filter = SessionLockFilter(hwnd)
            self._session_filter.session_locked.connect(self._on_session_locked)
            QApplication.instance().installNativeEventFilter(self._session_filter)
        except Exception:
            self._session_filter = None

    def _shutdown_native(self) -> None:
        app = QApplication.instance()
        if self._session_filter is not None:
            self._session_filter.shutdown()
            app.removeNativeEventFilter(self._session_filter)

    def _on_session_locked(self) -> None:
        if not self.catalog.is_locked:
            self.lock_and_unlock()

    # ------------------------------------------------------------------ idle

    def _setup_idle_timer(self) -> None:
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start()

    def _check_idle(self) -> None:
        minutes = int(app_settings().value("idle_lock_minutes", 10))
        if minutes <= 0 or self.catalog.is_locked:
            return
        if self._activity.idle_seconds() >= minutes * 60:
            self.lock_and_unlock()

    # ------------------------------------------------------------------ model

    def _update_navigation(self) -> None:
        selected = self._selected_nav()
        counts = {label: 0 for label in categories}
        for service in self.catalog.catalog.services:
            for account in service.accounts:
                counts[main_category(service, account)] += 1
        self.nav_list.blockSignals(True)
        self.nav_list.clear()
        all_item = QListWidgetItem(NAV_ALL)
        all_item.setData(Qt.ItemDataRole.UserRole, "grid")
        self.nav_list.addItem(all_item)
        if any(counts.values()):
            heading = QListWidgetItem("账号分类")
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            heading.setSizeHint(QSize(100, 40))
            self.nav_list.addItem(heading)
        for label, name in categories.items():
            if not counts[label]:
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.nav_list.addItem(item)
        row = next((i for i in range(self.nav_list.count()) if self.nav_list.item(i).text() == selected), 0)
        self.nav_list.setCurrentRow(row)
        self.nav_list.blockSignals(False)
        self._refresh_icons()

    def _sort_changed(self, _index) -> None:
        app_settings().setValue("account_sort", self.sort_combo.currentData())
        self._refresh_accounts(update_navigation=False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "detail_panel"):
            self._update_responsive()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._pending_splitter_state is not None:
            state = self._pending_splitter_state
            self._pending_splitter_state = None
            QTimer.singleShot(0, lambda: self._restore_splitter_state(state))

    def _restore_splitter_state(self, state) -> None:
        if self.width() >= 1000 and self.splitter.restoreState(state):
            self._desktop_splitter_sizes = self.splitter.sizes()

    def _update_responsive(self) -> None:
        width = self.width()
        if width >= 1000:
            self._nav_open = False
        single = width < 760
        sidebar_visible = width >= 1000 or self._nav_open
        signature = (single, self._mobile_detail if single else False, sidebar_visible)
        if signature != self._responsive_signature:
            previous = self._responsive_signature
            if previous is not None and not previous[0] and single:
                sizes = self.splitter.sizes()
                if len(sizes) == 3 and sum(sizes) > 0:
                    self._desktop_splitter_sizes = sizes

            self.sidebar.setVisible(sidebar_visible)
            self.middle_pane.setVisible(not single or not self._mobile_detail)
            self.detail_panel.setVisible(not single or self._mobile_detail)
            if single:
                self.splitter.setSizes(
                    [0, max(0, self.splitter.width() - 2), 0]
                    if not self._mobile_detail
                    else [0, 0, max(0, self.splitter.width() - 2)]
                )
            elif previous is not None and previous[0] and self._desktop_splitter_sizes:
                self.splitter.setSizes(self._desktop_splitter_sizes)
            elif sidebar_visible:
                left = 188 if width >= 1000 else 164
                middle = 328 if width >= 1000 else 272
                self.splitter.setSizes([left, middle, max(320, width - left - middle)])
            else:
                middle = min(328, max(310, round(width * 0.34)))
                self.splitter.setSizes([0, middle, max(320, width - middle)])
            self._responsive_signature = signature

        self.nav_button.setVisible(width < 1000)
        self.back_button.setVisible(single and self._mobile_detail)
        self.lock_button.setText("锁定" if width >= 760 else "")
        self.vault_label.setVisible(width >= 760)

    def _toggle_navigation(self) -> None:
        self._nav_open = not self._nav_open
        self._update_responsive()

    def _on_navigation_clicked(self, _item) -> None:
        self._mobile_detail = False
        # Keep the category pane open while the account list is filtered.
        # Hiding it here shifts the list under the stationary pointer on narrow windows.
        self._update_responsive()

    def _activate_detail(self, _item=None) -> None:
        if self.width() < 760 and self._selected_pair():
            self._mobile_detail = True
            self._nav_open = False
            self._update_responsive()

    def _back_to_list(self) -> None:
        self._mobile_detail = False
        self._update_responsive()

    def _selected_nav(self) -> str:
        item = self.nav_list.currentItem()
        return item.text() if item is not None else NAV_ALL

    def _filtered_accounts(self) -> list[tuple[Service, Account]]:
        query = self.search_edit.text().strip()
        if query:
            return [(h.service, h.account) for h in self.catalog.search_index.search(query)]
        return self._nav_filtered()

    def _nav_filtered(self) -> list[tuple[Service, Account]]:
        nav = self._selected_nav()
        pairs: list[tuple[Service, Account]] = []
        for service in self.catalog.catalog.services:
            for account in service.accounts:
                pairs.append((service, account))

        if nav in categories:
            pairs = [(service, account) for service, account in pairs if main_category(service, account) == nav]
        pairs.sort(key=lambda pair: (pair[0].name.casefold(), pair[1].alias.casefold(), pair[1].username.casefold()))
        if self.sort_combo.currentData() == "recent":
            pairs.sort(key=lambda pair: pair[1].last_used_at or "", reverse=True)
        return pairs

    def _refresh_accounts(self, update_navigation: bool = True) -> None:
        if self.catalog.is_locked:
            return
        if update_navigation:
            self._update_navigation()
        current_uuid = self._selected_uuid()
        query = self.search_edit.text().strip()
        hits = (
            self.catalog.search_index.search(query, limit=_SEARCH_RESULT_LIMIT + 1)
            if query else []
        )
        more_results = len(hits) > _SEARCH_RESULT_LIMIT
        if more_results:
            hits = hits[:_SEARCH_RESULT_LIMIT]
        if query:
            pairs = [(h.service, h.account, h.matched) for h in hits]
        else:
            pairs = [(s, a, "") for s, a in self._nav_filtered()]
        self.account_list.setUpdatesEnabled(False)
        try:
            self.account_list.clear()
            for service, account, hint in pairs:
                title, subtitle, meta = public_summary(service, account)
                item = QListWidgetItem(" · ".join((title, subtitle, meta)))
                item.setData(pair_role, (service, account))
                item.setData(summary_role, (title, subtitle, meta, category_icon(service, account)))
                tooltip = [title, subtitle, meta]
                if hint:
                    tooltip.append(f"命中字段：{hint}")
                    item.setData(
                        Qt.ItemDataRole.AccessibleDescriptionRole,
                        f"搜索命中字段：{hint}",
                    )
                item.setToolTip("<br>".join(html.escape(part, quote=True) for part in tooltip if part))
                item.setSizeHint(QSize(300, 72))
                self.account_list.addItem(item)
                if account.uuid == current_uuid:
                    self.account_list.setCurrentItem(item)
        finally:
            self.account_list.setUpdatesEnabled(True)
        count = self.account_list.count()
        self.account_list.setVisible(bool(count))
        self.list_empty.setVisible(not count)
        self.list_empty.setText("没有搜索结果\n试试名称、网址片段或邮箱" if query else "这里还没有账户\n使用列表标题旁“新建”添加")
        self.list_title.setText("搜索结果" if query else self._selected_nav())
        self.search_scope.setVisible(bool(query))
        self.sort_combo.setVisible(not query)
        self.sort_combo.setEnabled(not query)
        if query and more_results:
            self.result_count.setText(f"{_SEARCH_RESULT_LIMIT}+ 个结果")
        else:
            self.result_count.setText(f"{count} 个结果" if query else f"{count} 个账户")
        if self.account_list.currentItem() is None and self.account_list.count():
            self.account_list.setCurrentRow(0)
        if not self.account_list.count():
            if query:
                self.detail_panel.show_empty(f"没有匹配 “{query}” 的账户")
            else:
                self.detail_panel.show_empty(
                    "此分类下没有账户"
                    if self._selected_nav() != NAV_ALL
                    else "还没有账户，点击“新建账户”开始"
                )
        self._update_context()
        self.edit_action.setEnabled(self.account_list.currentItem() is not None)
        self.delete_action.setEnabled(self.account_list.currentItem() is not None)

    def _selected_uuid(self) -> str | None:
        pair = self._selected_pair()
        return pair[1].uuid if pair else None

    def _selected_pair(self) -> tuple[Service, Account] | None:
        item = self.account_list.currentItem()
        return item.data(pair_role) if item is not None else None

    def _on_selection(self, current: QListWidgetItem | None, _previous=None) -> None:
        self.edit_action.setEnabled(current is not None)
        self.delete_action.setEnabled(current is not None)
        if current is None:
            self.detail_panel.show_empty()
            return
        pair = current.data(pair_role)
        if pair:
            self.detail_panel.show_account(*pair)

    def _update_context(self) -> None:
        if self.catalog.is_locked:
            self.vault_label.clear()
            return
        self.vault_label.setText(self.catalog.path.stem[:32])
        self.vault_label.setToolTip(str(self.catalog.path))

    # ------------------------------------------------------------------ actions

    def _new_account(self) -> None:
        if self.catalog.is_locked:
            return
        editor = AccountEditor(self.catalog, parent=self)
        if editor.exec() == AccountEditor.DialogCode.Accepted:
            self._after_data_change()
        editor.deleteLater()

    def _edit_selected(self, *_args) -> None:
        pair = self._selected_pair()
        if pair is None:
            return
        service, account = pair
        editor = AccountEditor(self.catalog, service=service, account=account, parent=self)
        if editor.exec() == AccountEditor.DialogCode.Accepted:
            self._after_data_change()
        editor.deleteLater()

    def _delete_selected(self) -> None:
        pair = self._selected_pair()
        if pair is None:
            return
        service, account = pair
        name = account.alias or account.username or service.name
        answer = QMessageBox.question(
            self,
            "删除账户",
            f"确定删除 {service.name} 的「{name}」吗？\n\n"
            "条目会移入密码库回收站，可通过恢复功能找回。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.catalog.mutation():
                self.catalog.delete_account(account.uuid)
                self._run_storage_task("正在安全保存密码库…", self.catalog.save)
        except AccnaryError as exc:
            self._show_save_error(exc)
            return
        self._after_data_change()

    def _open_recycle_bin(self) -> None:
        dialog = RecycleBinDialog(
            self.catalog, parent=self, on_changed=self._after_data_change
        )
        dialog.exec()
        dialog.deleteLater()

    def _open_backups(self) -> None:
        dialog = BackupDialog(self.catalog, self)
        dialog.exec()
        if dialog.restored_catalog is not None:
            self.catalog.lock()
            self.catalog = dialog.restored_catalog
            dialog.restored_catalog = None
            self._rebuild_detail_panel()
            self._refresh_accounts()
        dialog.deleteLater()

    def _on_credential_copied(self, account_uuid: str) -> None:
        """Track recent use in memory; the next lock/exit persists it."""
        try:
            self.catalog.touch_last_used(account_uuid)
        except Exception:
            return  # recency is best-effort; copying the credential already succeeded
        self._update_context()
        if self.sort_combo.currentData() == "recent":
            self._refresh_accounts()

    def _after_data_change(self) -> None:
        """Reload the catalog model from disk and refresh all panes."""
        try:
            self._run_storage_task("正在重新读取密码库…", self.catalog.reopen)
        except Exception as exc:  # vault file vanished / undecryptable
            QMessageBox.critical(self, "重新加载失败", str(exc))
        self._rebuild_detail_panel()
        self._refresh_accounts()

    def _rebuild_detail_panel(self) -> None:
        sizes = self.splitter.sizes()
        index = self.splitter.indexOf(self.detail_panel) if self.detail_panel else 2
        if self.detail_panel is not None:
            self.detail_panel.hide()
            self.detail_panel.setParent(None)
            self.detail_panel.deleteLater()
        self.detail_panel = self._make_detail_panel()
        self.splitter.insertWidget(max(index, 0), self.detail_panel)
        self.splitter.setStretchFactor(max(index, 0), 1)
        self.splitter.setSizes(sizes)
        self._update_responsive()

    def _show_save_error(self, exc: Exception) -> None:
        if isinstance(exc, ConflictError):
            answer = QMessageBox.question(
                self,
                "文件已被修改",
                str(exc) + "\n\n现在重新加载磁盘上的最新数据吗？\n（未保存的修改会丢失）",
            )
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    self._run_storage_task(
                        "正在重新读取密码库…", self.catalog.reopen
                    )
                    self._rebuild_detail_panel()
                    self._refresh_accounts()
                except Exception as reload_exc:
                    QMessageBox.critical(self, "重新加载失败", str(reload_exc))
        else:
            QMessageBox.critical(self, "保存失败", str(exc))

    # ------------------------------------------------------------------ lock

    def lock_and_unlock(self) -> None:
        """Lock the vault and request its password in the current window."""
        if self._storage_busy:
            self._lock_after_storage = True
            return
        if self.catalog.is_locked:
            return
        # Save pending committed commands, or retain the session if that fails.
        if self.catalog.has_unsaved_changes:
            try:
                self._run_storage_task("正在安全保存密码库…", self.catalog.save)
            except Exception as exc:
                self._show_save_error(exc)
                return
        self._locked_vault_path = str(self.catalog.path)
        self._clear_sensitive_views()
        self.catalog.lock()
        clear_owned_clipboard()
        self.lock_vault_path.setText(self._locked_vault_path)
        self.lock_vault_path.setToolTip(self._locked_vault_path)
        self.lock_password_edit.clear()
        self.lock_error_label.clear()
        self.workspace_page.setEnabled(False)
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
        self.page_stack.setCurrentWidget(self.lock_page)
        self.lock_password_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _unlock_locked_vault(self) -> None:
        if not self.catalog.is_locked or self._storage_busy:
            return
        password = self.lock_password_edit.text()
        if not password:
            self.lock_error_label.setText("请输入主密码。")
            self.lock_password_edit.setFocus()
            return
        vault_path = self._locked_vault_path
        if not vault_path:
            self.lock_error_label.setText("当前密码库路径不可用，请退出后重新打开。")
            return

        self.lock_unlock_button.setEnabled(False)
        try:
            catalog = self._run_storage_task(
                "正在解锁密码库…",
                lambda: CatalogService.open(vault_path, password),
            )
        except BadCredentialsError:
            self.lock_error_label.setText("主密码不正确，请重试。")
            self.lock_password_edit.selectAll()
            self.lock_password_edit.setFocus()
            return
        except VaultFormatError:
            self.lock_error_label.setText(
                "密码库文件无法读取，可能已损坏或不是受支持的 KDBX 格式。"
            )
            self.lock_password_edit.clear()
            self.lock_password_edit.setFocus()
            return
        except VaultError:
            self.lock_error_label.setText("密码库无法打开，请检查文件状态和访问权限。")
            self.lock_password_edit.clear()
            self.lock_password_edit.setFocus()
            return
        except Exception as exc:
            self.lock_error_label.setText(
                f"解锁失败（{type(exc).__name__}），请检查密码库文件。"
            )
            self.lock_password_edit.clear()
            self.lock_password_edit.setFocus()
            return
        finally:
            self.lock_unlock_button.setEnabled(True)

        self.catalog = catalog
        self._locked_vault_path = None
        self.lock_password_edit.clear()
        self.lock_error_label.clear()
        self.workspace_page.setEnabled(True)
        for shortcut in self._shortcuts:
            shortcut.setEnabled(True)
        self._activity._last_activity = time.monotonic()
        self._rebuild_detail_panel()
        self._refresh_accounts()
        self.page_stack.setCurrentWidget(self.workspace_page)
        self.search_edit.setFocus(Qt.FocusReason.OtherFocusReason)


def _add_shortcut(parent: QWidget, sequence: str, callback):
    from PySide6.QtGui import QKeySequence, QShortcut

    shortcut = QShortcut(QKeySequence(sequence), parent)
    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    shortcut.activated.connect(callback)
    return shortcut
