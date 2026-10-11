import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview.qt_app import PicView, ThumbnailTile


@pytest.fixture
def drag_setup(tmp_path, monkeypatch):
    import picview.qt_app as ui
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = tmp_path / "圖片 with spaces.png"
    Image.new("RGB", (120, 80), "red").save(path)
    app = QApplication.instance() or QApplication([])
    window = PicView()
    window.show()
    window.open_folder(tmp_path, path)
    app.processEvents()
    drags = []
    class FakeDrag:
        def __init__(self, source):
            self.source = source
            self.pixmap = None
            self.hotspot = None
            drags.append(self)
        def setMimeData(self, data): self.data = data
        def setPixmap(self, pixmap): self.pixmap = pixmap
        def setHotSpot(self, point): self.hotspot = point
        def exec(self, actions, default):
            self.actions = actions
            self.default = default
            return Qt.DropAction.IgnoreAction
    monkeypatch.setattr(ui, "QDrag", FakeDrag)
    yield window, path, drags
    window.close()
    window.deleteLater()
    app.processEvents()


def move_with_left_button(tile, position):
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(position), QPointF(tile.mapToGlobal(position)), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(tile, event)


@pytest.mark.parametrize("area", ["name", "preview"])
def test_drag_exports_original_file_url_and_copy_action(drag_setup, area):
    window, path, drags = drag_setup
    tile = window.thumbs.buttons[path]
    label = getattr(tile, area)
    assert label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    start = label.mapTo(tile, label.rect().center())
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=start)
    move_with_left_button(tile, start + QPoint(QApplication.startDragDistance() + 1, 0))
    assert len(drags) == 1
    drag = drags[0]
    assert drag.source is window
    assert drag.data.hasUrls()
    assert drag.data.urls()[0].isLocalFile()
    assert drag.data.urls()[0].toLocalFile() == str(path.resolve()).replace("\\", "/")
    assert drag.actions == Qt.DropAction.CopyAction
    assert drag.default == Qt.DropAction.CopyAction
    assert drag.pixmap.width() <= 96 and drag.pixmap.height() <= 96
    assert drag.hotspot == QPoint(drag.pixmap.width() // 2, drag.pixmap.height() // 2)
    assert path.is_file()
    assert window.thumbs.selected_path == path
    # Continuing the same gesture must not start a second drag.
    move_with_left_button(tile, start + QPoint(50, 0))
    assert len(drags) == 1


def test_click_and_small_movement_do_not_start_drag(drag_setup):
    window, path, drags = drag_setup
    tile = window.thumbs.buttons[path]
    start = QPoint(20, 30)
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=start)
    move_with_left_button(tile, start + QPoint(1, 0))
    QTest.mouseRelease(tile, Qt.MouseButton.LeftButton, pos=start)
    move_with_left_button(tile, start + QPoint(50, 0))
    assert not drags
    assert window.image.path == path


def test_deleted_file_is_not_dragged(drag_setup):
    window, path, drags = drag_setup
    tile = window.thumbs.buttons[path]
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
    path.unlink()
    move_with_left_button(tile, QPoint(60, 30))
    assert not drags


def test_drag_still_works_when_thumbnail_cannot_be_decoded(drag_setup):
    window, path, drags = drag_setup
    tile = ThumbnailTile(path, None, 140, False)
    tile.setParent(window)
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
    move_with_left_button(tile, QPoint(60, 30))
    assert len(drags) == 1
    assert drags[0].data.hasUrls()
    assert drags[0].pixmap is None
    tile.deleteLater()


def test_own_drag_is_not_treated_as_folder_drop(drag_setup):
    window, path, drags = drag_setup
    class OwnDrop:
        ignored = False
        def source(self): return window
        def ignore(self): self.ignored = True
        def mimeData(self): raise AssertionError("Own drag must be ignored")
    for handler in (window.dragEnterEvent, window.dropEvent):
        event = OwnDrop()
        handler(event)
        assert event.ignored
    assert window.image.path == path
