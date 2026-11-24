"""Bounded, asynchronous viewport rendering for large raster images.

Only PIL/QImage work runs in workers. The source remains at its native
resolution; scroll canvas dimensions never imply a canvas-sized bitmap.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math
import threading
import weakref

from PIL import Image
from PySide6.QtCore import QEvent, QObject, QRect, QRectF, QTimer, Qt
from PySide6.QtGui import QImage, QRegion


VIRTUAL_IMAGE_PIXELS = 4_000_000
REDUCTION_STRIP_PIXELS = 1_000_000
RENDER_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="picview-render")


class PyramidCache:
    """Shared LRU budget, excluding native source pixels owned by the editor."""
    def __init__(self, max_bytes=128 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self.images = OrderedDict()
        self.lock = threading.Lock()

    @staticmethod
    def cost(image):
        return image.width * image.height * (1 if image.mode == "L" else 4)

    def level(self, source, factor):
        if factor <= 1: return source
        key = id(source), factor
        with self.lock:
            # Do not retain original images after a tab/edit releases them.
            for stale, (reference, image) in list(self.images.items()):
                if reference() is None:
                    self.bytes_used -= self.cost(image)
                    del self.images[stale]
            entry = self.images.get(key)
            if entry is not None and entry[0]() is source:
                self.images.move_to_end(key)
                return entry[1]
            base, divisor = source, factor
            for (identifier, smaller), (reference, image) in reversed(self.images.items()):
                if identifier == id(source) and reference() is source and smaller < factor and factor % smaller == 0:
                    base, divisor = image, factor // smaller
                    break
        estimate = math.ceil(source.width / factor) * math.ceil(source.height / factor)
        if estimate * (1 if source.mode == "L" else 4) > self.max_bytes:
            return source
        if base.mode in ("RGBA", "LA"):
            # Pillow premultiplies alpha before reducing. Bound those temporary
            # copies to strips instead of converting the entire native bitmap.
            reduced = Image.new(base.mode, (math.ceil(base.width / divisor), math.ceil(base.height / divisor)))
            step = max(divisor, (REDUCTION_STRIP_PIXELS // base.width // divisor) * divisor)
            for top in range(0, base.height, step):
                strip = base.crop((0, top, base.width, min(base.height, top + step)))
                reduced.paste(strip.reduce(divisor), (0, top // divisor))
        else:
            reduced = base.reduce(divisor)
        cost = self.cost(reduced)
        with self.lock:
            old = self.images.pop(key, None)
            if old is not None: self.bytes_used -= self.cost(old[1])
            while self.images and self.bytes_used + cost > self.max_bytes:
                _, (_, removed) = self.images.popitem(last=False)
                self.bytes_used -= self.cost(removed)
            self.images[key] = weakref.ref(source), reduced
            self.bytes_used += cost
        return reduced


PYRAMIDS = PyramidCache()


@dataclass(frozen=True)
class RasterState:
    source: object
    rotation: int
    horizontal: bool
    vertical: bool
    box: tuple

    @property
    def key(self):
        return id(self.source), self.rotation, self.horizontal, self.vertical, self.box


def render_region(state, canvas, region, dpr=1., *, precise=True, cache=PYRAMIDS):
    """Inverse-map a viewport through crop/mirrors/quarter-turns to source pixels."""
    left, top, right, bottom = state.box
    width, height = state.source.size
    rotated_width, rotated_height = (height, width) if state.rotation % 180 else (width, height)
    x, y, rw, rh = region
    output = max(1, round(rw * dpr)), max(1, round(rh * dpr))
    scale = min(canvas[0] / (right - left), canvas[1] / (bottom - top)) * dpr
    factor = 1
    while factor * 2 <= 1 / max(scale, 1e-9): factor *= 2
    if not precise and factor > 1: factor *= 2
    level = cache.level(state.source, factor)

    def inverse(dx, dy):
        # Coordinates describe pixel edges, so reflections use width, not width-1.
        px = left + (x + dx * rw / output[0]) * (right - left) / canvas[0]
        py = top + (y + dy * rh / output[1]) * (bottom - top) / canvas[1]
        if state.horizontal: px = rotated_width - px
        if state.vertical: py = rotated_height - py
        rotation = state.rotation % 360
        if rotation == 90: px, py = py, height - px
        elif rotation == 180: px, py = width - px, height - py
        elif rotation == 270: px, py = width - py, px
        return px * level.width / width, py * level.height / height

    origin, along_x, along_y = inverse(0, 0), inverse(1, 0), inverse(0, 1)
    matrix = (along_x[0] - origin[0], along_y[0] - origin[0], origin[0],
              along_x[1] - origin[1], along_y[1] - origin[1], origin[1])
    corners = [inverse(dx, dy) for dx, dy in ((0, 0), (output[0], 0), (0, output[1]), output)]
    box = (max(0, math.floor(min(point[0] for point in corners)) - 3),
           max(0, math.floor(min(point[1] for point in corners)) - 3),
           min(level.width, math.ceil(max(point[0] for point in corners)) + 3),
           min(level.height, math.ceil(max(point[1] for point in corners)) + 3))
    region_source = level.crop(box)
    matrix = (*matrix[:2], matrix[2] - box[0], *matrix[3:5], matrix[5] - box[1])
    sampling = Image.Resampling.BICUBIC if precise else Image.Resampling.BILINEAR
    # Native pixels need no interpolation or premultiplied-alpha round trip.
    coefficients = (matrix[0], matrix[1], matrix[3], matrix[4])
    if (all(abs(value - round(value)) < 1e-7 for value in matrix)
            and sum(abs(value) for value in coefficients) == 2
            and all(abs(value) <= 1 for value in coefficients)):
        sampling = Image.Resampling.NEAREST
    result = region_source.transform(output, Image.Transform.AFFINE, matrix, sampling)
    rgba = result.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()


def render_request(state, canvas, region, dpr, precise, need_preview):
    preview = None
    if need_preview:
        left, top, right, bottom = state.box
        scale = min(1., 1024 / max(right - left, bottom - top))
        size = max(1, round((right - left) * scale)), max(1, round((bottom - top) * scale))
        preview = render_region(state, size, (0, 0, *size), precise=False)
    image = render_region(state, canvas, region, dpr, precise=precise)
    return preview, image


class RasterView(QObject):
    """One running job and one replaceable request; only the latest tile is shown."""
    def __init__(self, label, scroll):
        super().__init__(label)
        self.label, self.scroll = label, scroll
        self.state = None
        self.canvas = (1, 1)
        self.padding = 0
        self.preview = None
        self.tile = None
        self.tile_rect = QRect()
        self.serial = 0
        self.pending = None
        self.future = None
        self.running = None
        self.request_key = None
        self.last_error = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(10)
        self.poll_timer.timeout.connect(self.collect)
        self.fast_timer = QTimer(self)
        self.fast_timer.setSingleShot(True)
        self.fast_timer.setInterval(16)
        self.fast_timer.timeout.connect(lambda: self.request(False))
        self.detail_timer = QTimer(self)
        self.detail_timer.setSingleShot(True)
        self.detail_timer.setInterval(120)
        self.detail_timer.timeout.connect(lambda: self.request(True))
        for bar in (scroll.horizontalScrollBar(), scroll.verticalScrollBar()):
            bar.valueChanged.connect(self.changed)
        scroll.viewport().installEventFilter(self)
        label.installEventFilter(self)

    @property
    def active(self):
        return self.state is not None

    def clear(self):
        self.serial += 1
        self.state = self.preview = self.tile = self.pending = self.request_key = None
        self.last_error = None
        self.fast_timer.stop()
        self.detail_timer.stop()
        if self.future is not None and self.future.cancel():
            self.future = None
            self.running = None
            self.poll_timer.stop()

    def set_image(self, state, canvas, padding=0):
        key = state.key
        if self.state is None or self.state.key != key:
            self.preview = self.tile = None
            self.request_key = None
            self.last_error = None
        elif self.canvas != canvas:
            self.tile = None
        self.state, self.canvas, self.padding = state, canvas, padding
        self.label.setFixedSize(canvas[0] + 2 * padding, canvas[1] + 2 * padding)
        self.changed()
        self.label.update()

    def eventFilter(self, watched, event):
        if self.active and event.type() in (QEvent.Type.Resize, QEvent.Type.Show): self.changed()
        return False

    def changed(self, *_):
        if not self.active: return
        # Invalidate immediately, including the debounce period before a new job.
        self.serial += 1
        self.pending = None
        self.request_key = None
        if self.future is not None and self.future.cancel():
            self.future = None
            self.running = None
            self.poll_timer.stop()
        if not self.fast_timer.isActive(): self.fast_timer.start()
        self.detail_timer.start()
        self.label.update()

    def visible_rect(self):
        top_left = self.label.mapFrom(self.scroll.viewport(), self.scroll.viewport().rect().topLeft())
        viewport = QRect(top_left, self.scroll.viewport().size())
        image = QRect(self.padding, self.padding, *self.canvas)
        # A small border lets ordinary scrolling reuse pixels while a job runs.
        return viewport.adjusted(-48, -48, 48, 48).intersected(image).translated(-self.padding, -self.padding)

    def request(self, precise):
        if not self.active or not self.label.isVisible(): return
        rect = self.visible_rect()
        if rect.isEmpty(): return
        region, dpr = rect.getRect(), self.label.devicePixelRatioF()
        key = self.state.key, self.canvas, region, dpr, precise
        if key == self.request_key: return
        self.serial += 1
        self.request_key = key
        self.pending = (self.serial, self.state, self.canvas, rect, dpr, precise)
        self.start_pending()

    def start_pending(self):
        if self.future is not None or self.pending is None: return
        self.running, self.pending = self.pending, None
        serial, state, canvas, rect, dpr, precise = self.running
        self.future = RENDER_POOL.submit(render_request, state, canvas, rect.getRect(), dpr, precise, self.preview is None)
        self.poll_timer.start()

    def collect(self):
        if self.future is None or not self.future.done(): return
        future, self.future = self.future, None
        running, self.running = self.running, None
        serial, state, canvas, rect, dpr, precise = running
        try:
            preview, image = future.result()
        except Exception as error:
            self.last_error = error
        else:
            if self.active and self.state.key == state.key:
                if preview is not None: self.preview = preview
                if serial == self.serial:
                    self.tile, self.tile_rect = image, rect
                self.label.update()
        self.poll_timer.stop()
        self.start_pending()

    def paint(self, painter):
        full = QRectF(self.padding, self.padding, *self.canvas)
        tile_rect = QRectF(self.tile_rect.translated(self.padding, self.padding))
        if self.preview is not None:
            painter.save()
            if self.tile is not None:
                painter.setClipRegion(QRegion(self.label.rect()).subtracted(QRegion(tile_rect.toRect())),
                                      Qt.ClipOperation.IntersectClip)
            painter.drawImage(full, self.preview)
            painter.restore()
        if self.tile is not None: painter.drawImage(tile_rect, self.tile)
