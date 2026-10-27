# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 23:43
# @Modified  : 2026-10-25 23:52
# @Python    : 3.14.9
# @Description: Run blocking encrypted-vault operations without freezing the Qt event loop.
"""Small modal worker for KDBX operations that can take noticeable time."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class _StorageWorker(QObject):
    finished = Signal(object, object)

    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self._operation = operation

    @Slot()
    def run(self) -> None:
        operation = self._operation
        self._operation = None
        try:
            result = operation()
        except BaseException as exc:
            pending = [exc]
            seen = set()
            while pending:
                error = pending.pop()
                if error is None or id(error) in seen:
                    continue
                seen.add(id(error))
                error.__traceback__ = None
                pending.extend((error.__cause__, error.__context__))
            self.finished.emit(None, exc)
        else:
            self.finished.emit(result, None)
        finally:
            operation = None


class _ProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str):
        super().__init__(parent)
        self._completed = False
        self.result_value: Any = None
        self.error: BaseException | None = None
        self.setWindowTitle("Accnary")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        label = QLabel(title)
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setFixedHeight(7)
        layout.addWidget(progress)

    @Slot(object, object)
    def complete(self, result: Any, error: BaseException | None) -> None:
        self.result_value = result
        self.error = error
        self._completed = True
        self.accept()

    def reject(self) -> None:
        if self._completed:
            super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._completed:
            event.accept()
        else:
            event.ignore()


def execute_storage_task(
    parent: QWidget | None,
    title: str,
    operation: Callable[[], Any],
) -> Any:
    """Run one serialized storage operation on a worker and show progress."""
    dialog = _ProgressDialog(parent, title)
    thread = QThread(parent)
    worker = _StorageWorker(operation)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.finished.connect(dialog.complete)
    thread.finished.connect(worker.deleteLater)

    thread.start()
    dialog.exec()
    thread.wait()
    thread.deleteLater()
    result = dialog.result_value
    error = dialog.error
    dialog.result_value = None
    dialog.error = None
    dialog.deleteLater()
    if error is not None:
        raise error
    return result


def run_storage_task(
    parent: QWidget | None,
    title: str,
    operation: Callable[[], Any],
) -> Any:
    """Use the main-window guard when present, otherwise run the worker directly."""
    owner = parent
    while owner is not None:
        runner = getattr(owner, "_run_storage_task", None)
        if callable(runner):
            return runner(title, operation, parent)
        owner = owner.parentWidget()
    return execute_storage_task(parent, title, operation)
