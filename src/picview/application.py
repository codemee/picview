"""Receive macOS document-open requests, including during startup."""
import sys
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication


class PicViewApplication(QApplication):
    def __init__(self, arguments):
        if sys.platform == "win32":
            import ctypes
            shell = ctypes.WinDLL("shell32")
            shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
            shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
            # Stable across versions and source/frozen launches. Set before Qt
            # creates any native windows so Explorer does not group us as Python.
            shell.SetCurrentProcessExplicitAppUserModelID("codemee.PicView")
        self._pending_paths = []
        self._open_paths = None
        super().__init__(arguments)

    def set_open_paths_handler(self, handler):
        self._open_paths = handler
        paths, self._pending_paths = self._pending_paths, []
        if paths:
            QTimer.singleShot(0, lambda: handler(paths))

    def event(self, event):
        if event.type() == QEvent.Type.FileOpen:
            path = event.file() or event.url().toLocalFile()
            if path:
                if self._open_paths is None:
                    self._pending_paths.append(path)
                else:
                    handler = self._open_paths
                    QTimer.singleShot(0, lambda: handler([path]))
                event.accept()
                return True
        return super().event(event)
