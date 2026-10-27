from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, QMimeDatabase, Qt, QUrl
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout


def copy_file(path: Path) -> None:
    if not path.is_file(): return
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path.resolve()))])
    QApplication.clipboard().setMimeData(data)


def show_native_properties(path: Path, parent) -> bool:
    """Invoke the same Windows shell property sheet used by Explorer."""
    if sys.platform != "win32": return False
    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    initialized = False
    try:
        try:
            initialized = ole.CoInitializeEx(None, 0x2 | 0x4) in (0, 1)
        except OSError:
            pass  # Qt may already have initialized this thread's COM apartment.
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
        shell.ShellExecuteExW.restype = wintypes.BOOL
        info = ShellExecuteInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = 0x0000000C | 0x00000400  # INVOKEIDLIST | FLAG_NO_UI
        info.hwnd = int(parent.window().winId())
        info.lpVerb = "properties"
        info.lpFile = str(path.resolve())
        info.nShow = 1
        return bool(shell.ShellExecuteExW(ctypes.byref(info)))
    except OSError:
        return False
    finally:
        if initialized: ole.CoUninitialize()


def file_details(path: Path, labels: dict[str, str]) -> list[tuple[str, str]]:
    stat = path.stat()
    rows = [
        (labels["file_name"], path.name),
        (labels["file_type"], QMimeDatabase().mimeTypeForFile(str(path)).comment()),
        (labels["file_location"], str(path.parent)),
        (labels["file_size"], f"{stat.st_size:,} {labels['bytes']}"),
        (labels["modified"], datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    created = getattr(stat, "st_birthtime", None)
    if created is not None:
        rows.append((labels["created"], datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S")))
    size = QImageReader(str(path)).size()
    if size.isValid(): rows.append((labels["dimensions"], f"{size.width()} × {size.height()} px"))
    return rows


def show_properties(path: Path, parent, labels: dict[str, str]):
    if not path.is_file(): return None
    if show_native_properties(path, parent): return None
    try:
        rows = file_details(path, labels)
    except OSError:
        return None
    dialog = QDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowTitle(f"{path.name} — {labels['properties']}")
    dialog.resize(480, 300)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    for title, value in rows:
        label = QLabel(value)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(f"{title}:", label)
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText(labels["file_close"])
    buttons.rejected.connect(dialog.close)
    layout.addWidget(buttons)
    dialog.show()
    return dialog
