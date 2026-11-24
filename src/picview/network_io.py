"""Background directory snapshots and buffered reads for network shares."""
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
import ntpath
import io
import os
import shutil
import tempfile
import threading

from PIL import Image
from PySide6.QtCore import QObject, QTimer

from .raster import decoded_frame
from .utils import IMAGE_SUFFIXES, natural_key


SCAN_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="picview-directory")
IMAGE_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="picview-network-image")


@lru_cache(maxsize=32)
def remote_drive(drive):
    if os.name != "nt": return False
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(str(drive) + "\\") == 4


def is_network_path(path):
    name = str(path)
    return name.startswith(("\\\\", "//")) or remote_drive(ntpath.splitdrive(name)[0])


def stat_version(stat):
    # Windows directory enumeration does not supply the same inode as stat().
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, 0


@dataclass
class DirectorySnapshot:
    files: list
    directories: list
    versions: dict


def scan_directory(folder):
    files, directories, versions = [], [], {}
    with os.scandir(folder) as entries:
        for entry in entries:
            path = folder / entry.name
            try:
                if entry.is_dir():
                    directories.append(path)
                    versions[path] = stat_version(entry.stat())
                elif path.suffix.lower() in IMAGE_SUFFIXES and entry.is_file():
                    files.append(path)
                    versions[path] = stat_version(entry.stat())
            except FileNotFoundError:
                continue
    return DirectorySnapshot(sorted(files, key=natural_key), sorted(directories, key=natural_key), versions)


class NetworkPayloadCache:
    """Reuse compressed bytes across thumbnails/views, with one transfer per key."""
    def __init__(self, max_bytes=64 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self.items = OrderedDict()
        self.inflight = {}
        self.lock = threading.Lock()

    def invalidate(self, path, version):
        with self.lock:
            removed = self.items.pop((path, version), None)
            if removed is not None: self.bytes_used -= len(removed)

    def read(self, path, version):
        key = path, version
        with self.lock:
            if key in self.items:
                self.items.move_to_end(key)
                return self.items[key]
            future = self.inflight.get(key)
            owner = future is None
            if owner:
                future = self.inflight[key] = Future()
        if not owner: return future.result()
        try:
            from .thumbnails import image_source
            with image_source(path) as stream: data = stream.read(version[0] + 1)
            if len(data) != version[0]: raise OSError("Image changed during network transfer")
            if len(data) <= self.max_bytes:
                with self.lock:
                    while self.items and self.bytes_used + len(data) > self.max_bytes:
                        _, removed = self.items.popitem(last=False)
                        self.bytes_used -= len(removed)
                    self.items[key] = data
                    self.bytes_used += len(data)
            future.set_result(data)
            return data
        except Exception as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock: self.inflight.pop(key, None)


PAYLOADS = NetworkPayloadCache()


@contextmanager
def buffered_source(path, version=None):
    # Imported lazily because thumbnails also use this buffering policy.
    from .thumbnails import image_source, file_version
    if is_network_path(path):
        if version is None: version = file_version(path)
        if version is not None and version[0] <= min(32 * 1024 * 1024, PAYLOADS.max_bytes):
            try:
                with io.BytesIO(PAYLOADS.read(path, version)) as local: yield local
            except Exception:
                PAYLOADS.invalidate(path, version)
                raise
            return
    with image_source(path) as stream:
        if not is_network_path(path):
            yield stream
            return
        # Pillow performs many small reads/seeks. Fetch in 1 MiB blocks once;
        # large payloads spill into a temporary file instead of growing RAM.
        with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as local:
            shutil.copyfileobj(stream, local, length=1024 * 1024)
            local.seek(0)
            yield local


@dataclass
class NetworkSvg:
    data: bytes
    version: tuple


def decode_network_image(path):
    from .thumbnails import file_version
    before = file_version(path)
    if path.suffix.lower() == ".svg":
        with buffered_source(path, before) as stream: data = stream.read()
        after = file_version(path)
        if before != after: raise OSError("Image changed while it was being read")
        return NetworkSvg(data, after)
    frames = []
    with buffered_source(path, before) as stream, Image.open(stream) as image:
        loop = image.info.get("loop", 0)
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            frames.append((decoded_frame(image), max(20, int(image.info.get("duration", 100)))))
    after = file_version(path)
    if before != after: raise OSError("Image changed while it was being read")
    return frames, loop, after


class LatestRequest(QObject):
    """Keep one running task and replace queued work when the selection changes."""
    def __init__(self, parent, pool):
        super().__init__(parent)
        self.pool = pool
        self.serial = 0
        self.future = self.running = self.pending = None
        self.timer = QTimer(self)
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.collect)
        parent.destroyed.connect(self.stop)

    def invalidate(self):
        self.serial += 1
        self.pending = None
        if self.future is not None and self.future.cancel():
            self.future = self.running = None
            self.timer.stop()

    def submit(self, function, callback, *args):
        self.invalidate()
        self.pending = self.serial, function, callback, args
        self.start()

    def start(self):
        if self.future is not None or self.pending is None: return
        self.running, self.pending = self.pending, None
        _, function, _, args = self.running
        self.future = self.pool.submit(function, *args)
        self.timer.start()

    def collect(self):
        if self.future is None or not self.future.done(): return
        future, self.future = self.future, None
        running, self.running = self.running, None
        serial, _, callback, _ = running
        self.timer.stop()
        try:
            value, error = future.result(), None
        except Exception as failure:
            value, error = None, failure.with_traceback(None)
        if serial == self.serial: callback(value, error)
        self.start()

    def stop(self, *_):
        self.invalidate()
        self.timer.stop()
        self.running = self.future = None
