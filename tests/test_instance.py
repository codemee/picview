import uuid

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
