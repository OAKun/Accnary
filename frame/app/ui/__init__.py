"""Qt user interface (PySide6 widgets - no QML, no WebView)."""

__all__ = ["MainWindow", "UnlockDialog"]


def __getattr__(name: str):
    """Load the workspace only when requested, after the vault is unlocked."""
    if name == "MainWindow":
        from .main_window import MainWindow

        globals()[name] = MainWindow
        return MainWindow
    if name == "UnlockDialog":
        from .unlock_dialog import UnlockDialog

        globals()[name] = UnlockDialog
        return UnlockDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
