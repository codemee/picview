"""Background thumbnail decoding and a bounded, shared memory cache."""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage

from .svg import SvgDocument


def file_version(path: Path):
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino
    except OSError:
        return None


@contextmanager
def image_source(path):
    """Allow Windows editors to replace/delete a file during decoding."""
    if os.name != "nt":
        with open(path, "rb") as stream: yield stream
        return
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x80000000, 1 | 2 | 4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "rb") as stream: yield stream


def thumbnail_image(path: Path, size: int, dpr: float, version) -> QImage:
    """Create only QImage data here; QPixmap and widgets stay on the UI thread."""
    if path.suffix.lower() == ".svg":
        document = SvgDocument(path)
        target = QSize(*document.size).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio)
        result = document.render((max(1, round(target.width() * dpr)), max(1, round(target.height() * dpr))))
        result.setDevicePixelRatio(dpr)
    else:
        with image_source(path) as stream, Image.open(stream) as source:
            # JPEG decoders can reduce resolution before allocating the full image.
            source.draft("RGB", (size, size))
            image = ImageOps.exif_transpose(source)
            image.thumbnail((size, size))
            image = image.convert("RGBA")
            result = QImage(image.tobytes(), image.width, image.height, QImage.Format.Format_RGBA8888).copy()
    if file_version(path) != version:
        raise OSError("Image changed while its thumbnail was being decoded")
    return result


class ThumbnailCache:
    """All bookkeeping runs on the GUI thread; workers only decode images."""
    def __init__(self, max_bytes=64 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self.images = OrderedDict()
        self.inflight = {}
        self.revisions = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="picview-thumbnail")

    def key(self, path, size, dpr):
        return path, size, dpr, file_version(path), self.revisions.get(path, 0)

    def get(self, key):
        image = self.images.get(key)
        if image is not None: self.images.move_to_end(key)
        return image

    def collect(self):
        for key, future in list(self.inflight.items()):
            if not future.done(): continue
            del self.inflight[key]
            if future.cancelled() or future.exception() is not None: continue
            if key != self.key(*key[:3]): continue
            image = future.result()
            cost = image.sizeInBytes()
            if cost > self.max_bytes: continue
            old = self.images.pop(key, None)
            if old is not None: self.bytes_used -= old.sizeInBytes()
            self.images[key] = image
            self.bytes_used += cost
            while self.bytes_used > self.max_bytes:
                _, removed = self.images.popitem(last=False)
                self.bytes_used -= removed.sizeInBytes()

    def request(self, key):
        existing = self.inflight.get(key)
        self.collect()
        if existing is not None: return existing
        cached = self.get(key)
        if cached is not None:
            ready = Future()
            ready.set_result(cached)
            return ready
        if key not in self.inflight:
            path, size, dpr, version, _ = key
            self.inflight[key] = self.pool.submit(thumbnail_image, path, size, dpr, version)
        return self.inflight[key]

    def invalidate(self, path):
        self.revisions[path] = self.revisions.get(path, 0) + 1
        for key in list(self.images):
            if key[0] == path:
                self.bytes_used -= self.images.pop(key).sizeInBytes()


THUMBNAILS = ThumbnailCache()
