"""Image crop handles, mosaic rectangles, and full-span splice selections."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel


class CropLabel(QLabel):
    cropChanged = Signal(object)
    cropStarted = Signal()
    cropFinished = Signal()
    mosaicSelected = Signal(object)
    spliceSelected = Signal(str, float, float)
    margin = 8

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.crop_active = False
        self.mosaic_active = False
        self.mosaic_start = None
        self.mosaic_end = None
        self.splice_active = False
        self.splice_start = None
        self.splice_end = None
        self.splice_axis = "x"
        self.crop = (0., 0., 1., 1.)
        self.source_size = (1, 1)
        self.drag_handle = None
        self.setMouseTracking(True)

    def crop_rect(self):
        pix = self.pixmap()
        size = pix.deviceIndependentSize()
        x0, y0, x1, y1 = self.crop
        return QRectF(self.margin + x0 * size.width(), self.margin + y0 * size.height(),
                      (x1 - x0) * size.width(), (y1 - y0) * size.height())

    def handles(self):
        rect = self.crop_rect()
        return {"tl": rect.topLeft(), "t": QPointF(rect.center().x(), rect.top()),
                "tr": rect.topRight(), "r": QPointF(rect.right(), rect.center().y()),
                "br": rect.bottomRight(), "b": QPointF(rect.center().x(), rect.bottom()),
                "bl": rect.bottomLeft(), "l": QPointF(rect.left(), rect.center().y())}

    def hit_handle(self, point):
        # Nearest first also works for a one-pixel crop with overlapping handles.
        distances = [(abs(point.x() - p.x()) + abs(point.y() - p.y()), key)
                     for key, p in self.handles().items()
                     if abs(point.x() - p.x()) <= 7 and abs(point.y() - p.y()) <= 7]
        return min(distances)[1] if distances else None

    def paintEvent(self, event):
        if self.splice_active:
            super().paintEvent(event)
            if self.splice_start is not None:
                painter = QPainter(self)
                painter.setPen(QPen(QColor("#e05a47"), 1.5, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(224, 90, 71, 85))
                painter.drawRect(self.splice_rect())
            return
        if self.mosaic_active:
            super().paintEvent(event)
            if self.mosaic_start is not None:
                size = self.pixmap().deviceIndependentSize()
                start, end = self.mosaic_start, self.mosaic_end
                rect = QRectF(QPointF(start.x() * size.width(), start.y() * size.height()),
                              QPointF(end.x() * size.width(), end.y() * size.height())).normalized()
                painter = QPainter(self)
                painter.setPen(QPen(QColor("#1677ff"), 1.5, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(22, 119, 255, 40))
                painter.drawRect(rect)
            return
        if not self.crop_active or self.pixmap().isNull():
            return super().paintEvent(event)
        painter = QPainter(self)
        rect = self.crop_rect()
        painter.save()
        painter.setClipRect(rect)
        painter.drawPixmap(QPointF(self.margin, self.margin), self.pixmap())
        painter.restore()
        painter.setPen(QPen(QColor("#1677ff"), 1.5))
        painter.drawRect(rect)
        painter.setBrush(QColor("#ffffff"))
        for point in self.handles().values():
            painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))

    def mousePressEvent(self, event):
        if self.splice_active and event.button() == Qt.MouseButton.LeftButton and not self.pixmap().isNull():
            self.splice_start = self.splice_end = self.selection_point(event.position())
            self.splice_axis = "x"
            self.update()
            event.accept()
            return
        if self.mosaic_active and event.button() == Qt.MouseButton.LeftButton and not self.pixmap().isNull():
            self.mosaic_start = self.mosaic_end = self.selection_point(event.position())
            self.update()
            event.accept()
            return
        if self.crop_active and event.button() == Qt.MouseButton.LeftButton:
            self.drag_handle = self.hit_handle(event.position())
            if self.drag_handle:
                self.cropStarted.emit()
                self.drag_start = event.position()
                self.drag_crop = self.crop
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.splice_active:
            if self.splice_start is not None: self.update_splice_selection(event.position())
            event.accept()
            return
        if self.mosaic_active:
            if self.mosaic_start is not None:
                self.mosaic_end = self.selection_point(event.position())
                self.update()
            event.accept()
            return
        if self.crop_active:
            handle = self.drag_handle or self.hit_handle(event.position())
            cursor = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                      "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                      "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                      "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor}
            self.setCursor(cursor.get(handle, Qt.CursorShape.ArrowCursor))
            if self.drag_handle:
                size = self.pixmap().deviceIndependentSize()
                delta = event.position() - self.drag_start
                dx, dy = delta.x() / size.width(), delta.y() / size.height()
                left, top, right, bottom = self.drag_crop
                min_w, min_h = 1 / self.source_size[0], 1 / self.source_size[1]
                if "l" in handle: left = max(0., min(right - min_w, left + dx))
                if "r" in handle: right = min(1., max(left + min_w, right + dx))
                if "t" in handle: top = max(0., min(bottom - min_h, top + dy))
                if "b" in handle: bottom = min(1., max(top + min_h, bottom + dy))
                self.cropChanged.emit((left, top, right, bottom))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.splice_active and self.splice_start is not None and event.button() == Qt.MouseButton.LeftButton:
            self.update_splice_selection(event.position())
            axis = self.splice_axis
            start = self.splice_start.x() if axis == "x" else self.splice_start.y()
            end = self.splice_end.x() if axis == "x" else self.splice_end.y()
            size = self.pixmap().deviceIndependentSize()
            extent = size.width() if axis == "x" else size.height()
            self.cancel_splice_selection()
            if abs(end - start) * extent >= 3:
                self.spliceSelected.emit(axis, min(start, end), max(start, end))
            event.accept()
            return
        if self.mosaic_active and self.mosaic_start is not None and event.button() == Qt.MouseButton.LeftButton:
            start, end = self.mosaic_start, self.selection_point(event.position())
            size = self.pixmap().deviceIndependentSize()
            self.cancel_mosaic_selection()
            if abs(end.x() - start.x()) * size.width() >= 3 and abs(end.y() - start.y()) * size.height() >= 3:
                self.mosaicSelected.emit((min(start.x(), end.x()), min(start.y(), end.y()),
                                          max(start.x(), end.x()), max(start.y(), end.y())))
            event.accept()
            return
        if self.drag_handle and event.button() == Qt.MouseButton.LeftButton:
            self.drag_handle = None
            self.cropFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def selection_point(self, position):
        size = self.pixmap().deviceIndependentSize()
        return QPointF(max(0., min(1., position.x() / max(1., size.width()))),
                       max(0., min(1., position.y() / max(1., size.height()))))

    def cancel_mosaic_selection(self):
        self.mosaic_start = self.mosaic_end = None
        self.update()

    def update_splice_selection(self, position):
        self.splice_end = self.selection_point(position)
        size = self.pixmap().deviceIndependentSize()
        # Compare display pixels, not normalized distances: tall and wide
        # images must respond to the same mouse gesture in the same way.
        dx = position.x() - self.splice_start.x() * size.width()
        dy = position.y() - self.splice_start.y() * size.height()
        self.splice_axis = "x" if abs(dx) >= abs(dy) else "y"
        self.update()

    def splice_rect(self):
        size = self.pixmap().deviceIndependentSize()
        if self.splice_axis == "x":
            left, right = sorted((self.splice_start.x(), self.splice_end.x()))
            return QRectF(left * size.width(), 0, (right - left) * size.width(), size.height())
        top, bottom = sorted((self.splice_start.y(), self.splice_end.y()))
        return QRectF(0, top * size.height(), size.width(), (bottom - top) * size.height())

    def cancel_splice_selection(self):
        self.splice_start = self.splice_end = None
        self.update()
