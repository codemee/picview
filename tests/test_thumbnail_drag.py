import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview.qt_app import PicView, ThumbnailTile
from test_tabs import wait_until


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
    wait_until(lambda: not window.thumbs.buttons[path].preview.pixmap().isNull())
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
    assert drag.actions == Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    assert drag.default == Qt.DropAction.IgnoreAction
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


def test_ctrl_shift_and_select_all_drag_multiple_files(drag_setup):
    import sys
    selection_modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
    window, first, drags = drag_setup
    second = first.parent / "second.png"
    third = first.parent / "third.png"
    for path in (second, third): Image.new("RGB", (20, 20), "blue").save(path)
    window.refresh_folder()
    files = window.thumbs.files
    window.thumbs.select(files[0])
    QTest.mouseClick(window.thumbs.buttons[files[1]], Qt.MouseButton.LeftButton,
                     selection_modifier)
    assert window.thumbs.selected_paths == {files[0], files[1]}
    QTest.mouseClick(window.thumbs.buttons[files[2]], Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.ShiftModifier)
    assert window.thumbs.selected_paths == {files[1], files[2]}
    window.thumbs.select(files[0])
    QTest.keyClick(window.thumbs.scroll, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert window.thumbs.selected_paths == {files[0], files[1]}
    QTest.keyClick(window.thumbs.scroll, Qt.Key.Key_A, selection_modifier)
    assert window.thumbs.selected_paths == set(files)
    tile = window.thumbs.buttons[files[1]]
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
    move_with_left_button(tile, QPoint(60, 30))
    assert len(drags) == 1
    assert {url.toLocalFile() for url in drags[0].data.urls()} == {str(path).replace("\\", "/") for path in files}


def test_drag_empty_thumbnail_area_selects_tiles_and_click_clears(drag_setup):
    window, first, _ = drag_setup
    second = first.parent / "second.png"
    Image.new("RGB", (20, 20), "blue").save(second)
    window.refresh_folder()
    pane = window.thumbs
    host = pane.grid_host
    pane.grid.activate()
    first_tile = pane.buttons[pane.files[0]]
    second_tile = pane.buttons[pane.files[1]]
    start = QPoint(1, 1)
    end = second_tile.geometry().bottomRight() + QPoint(2, 2)
    QTest.mousePress(host, Qt.MouseButton.LeftButton, pos=start)
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(end), QPointF(host.mapToGlobal(end)),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(host, move)
    QTest.mouseRelease(host, Qt.MouseButton.LeftButton, pos=end)
    assert pane.selected_paths == set(pane.files)
    assert not pane.selection_band.isVisible()
    QTest.mouseClick(host, Qt.MouseButton.LeftButton, pos=start)
    assert pane.selected_paths == set()
    assert pane.selected_path in pane.files


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
