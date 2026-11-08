"""Pass file and folder requests to an already running PicView window."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "picview-" + hashlib.sha256(str(Path.home()).encode("utf-8")).hexdigest()[:16]


def forward_paths(paths: list[str]) -> bool:
    if not paths:
        return False
    socket = QLocalSocket()
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    acknowledged = []
    payload = json.dumps(paths, ensure_ascii=False).encode("utf-8") + b"\n"

    def receive():
        if socket.canReadLine():
            acknowledged.append(bytes(socket.readLine()).strip() == b"OK")
            loop.quit()

    socket.connected.connect(lambda: socket.write(payload))
    socket.readyRead.connect(receive)
    socket.errorOccurred.connect(lambda _: loop.quit())
    socket.connectToServer(SERVER_NAME)
    timeout.start(2000)
    loop.exec()
    timeout.stop()
    socket.disconnectFromServer()
    return acknowledged == [True]


def forward_paths_early(paths: list[str]) -> bool:
    """Forward before importing Qt Widgets or the image viewer."""
    if not paths:
        return False
    app = None
    if QCoreApplication.instance() is None:
        app = QCoreApplication([])
    try:
        return forward_paths(paths)
    finally:
        if app is not None:
            import shiboken6

            shiboken6.delete(app)


class InstanceReceiver(QObject):
    def __init__(self, parent: QObject, on_paths):
        super().__init__(parent)
        self.on_paths = on_paths
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._accept)
        self.listening = self.server.listen(SERVER_NAME)

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda socket=socket: self._read(socket))
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self._read(socket)

    def _read(self, socket: QLocalSocket):
        if not socket.canReadLine():
            return
        try:
            paths = json.loads(bytes(socket.readLine()).decode("utf-8"))
            if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
                return
        except (UnicodeDecodeError, ValueError):
            return
        socket.write(b"OK\n")
        socket.flush()
        QTimer.singleShot(0, lambda: self.on_paths(paths))
