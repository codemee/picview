import uuid
import os
import subprocess
import sys

from picview import instance
from test_tabs import browser


def test_forward_paths_reuses_running_window(browser, monkeypatch):
    window, _ = browser
    monkeypatch.setattr(instance, "SERVER_NAME", "picview-test-" + uuid.uuid4().hex)
    received = []
    receiver = instance.InstanceReceiver(window, received.append)
    assert receiver.listening
    paths = [r"C:\圖片\一.png", r"C:\圖片\二.png"]
    assert instance.forward_paths(paths)
    assert received == [paths]
    receiver.server.close()


def test_early_forward_opens_multiple_unicode_paths(browser, monkeypatch):
    window, _ = browser
    monkeypatch.setattr(instance, "SERVER_NAME", "picview-test-" + uuid.uuid4().hex)
    received = []
    receiver = instance.InstanceReceiver(window, received.append)
    assert receiver.listening
    paths = [r"C:\圖片\檔案 one.png", r"C:\圖片\二.svg"]
    result = instance.forward_paths_early(paths)
    try:
        assert result
        assert received == [paths]
    finally:
        receiver.server.close()


def test_early_forward_allows_cold_gui_start():
    script = """from picview import instance
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
instance.SERVER_NAME = 'picview-absent-' + __import__('uuid').uuid4().hex
assert not instance.forward_paths_early(['C:/missing.png'])
assert QCoreApplication.instance() is None
app = QApplication([])
assert QCoreApplication.instance() is app
"""
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
