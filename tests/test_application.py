import os
import subprocess
import sys
import textwrap


def test_document_open_events_before_and_after_window_ready():
    # Qt allows only one QApplication per process. Use the real subclass in a
    # fresh process, independent of the other GUI tests' shared QApplication.
    subprocess.run(
        [sys.executable, "-c", textwrap.dedent('''
            from PySide6.QtCore import QEvent, QUrl
            from PySide6.QtGui import QFileOpenEvent
            from picview.application import PicViewApplication

            app = PicViewApplication([])
            received = []
            first = "/tmp/圖片 one.png"
            second = "/tmp/圖片 two.svg"
            assert app.sendEvent(app, QFileOpenEvent(first))
            app.processEvents()
            assert received == []
            app.set_open_paths_handler(received.append)
            app.processEvents()
            assert received == [[first]]
            assert app.sendEvent(app, QFileOpenEvent(QUrl.fromLocalFile(second)))
            app.processEvents()
            assert received == [[first], [second]]
            app.sendEvent(app, QFileOpenEvent(QUrl("https://example.com/image.png")))
            app.sendEvent(app, QEvent(QEvent.Type.User))
            app.processEvents()
            assert received == [[first], [second]]
        ''')],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=True,
        timeout=30,
    )


def test_windows_taskbar_identity_before_any_window():
    import pytest
    if sys.platform != "win32": pytest.skip("Windows taskbar identity")
    subprocess.run([sys.executable, "-c", textwrap.dedent('''
        import ctypes
        from picview.application import PicViewApplication
        app = PicViewApplication([])
        identifier = ctypes.c_wchar_p()
        shell = ctypes.WinDLL("shell32")
        shell.GetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.POINTER(ctypes.c_wchar_p)]
        shell.GetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        assert shell.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(identifier)) == 0
        try:
            assert identifier.value == "codemee.PicView"
        finally:
            free = ctypes.WinDLL("ole32").CoTaskMemFree
            free.argtypes = [ctypes.c_void_p]
            free(ctypes.cast(identifier, ctypes.c_void_p))
    ''')], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, check=True, timeout=30)
