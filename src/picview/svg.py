"""Static SVG documents rendered at the requested display resolution."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


class SvgDocument:
    def __init__(self, path: Path):
        self.renderer = QSvgRenderer()
        self.renderer.setAnimationEnabled(False)
        if not self.renderer.load(str(path)):
            raise ValueError(f"Invalid SVG: {path.name}")
        size = self.renderer.defaultSize()
        if size.isEmpty(): size = self.renderer.viewBoxF().size().toSize()
        if size.isEmpty(): raise ValueError(f"SVG has no usable dimensions: {path.name}")
        self.size = (size.width(), size.height())

    def render(self, size: tuple[int, int]) -> QImage:
        width, height = size
        # Bound temporary raster memory even for documents with enormous view boxes.
        scale = min(1.0, math.sqrt(16_000_000 / (width * height)), 16384 / max(width, height))
        image = QImage(QSize(max(1, round(width * scale)), max(1, round(height * scale))), QImage.Format.Format_ARGB32_Premultiplied)
        if image.isNull(): raise ValueError("Unable to allocate SVG preview")
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.renderer.render(painter)
        finally:
            painter.end()
        return image
