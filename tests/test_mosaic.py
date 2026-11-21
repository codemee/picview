import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from picview.qt_app import ImagePane
from picview import editing
from test_crop import move_drag
from test_editing import pattern, assert_saved
from test_tabs import browser, wait_until

pytestmark = pytest.mark.usefixtures("real_unsaved_checks")


@pytest.fixture(autouse=True)
def fail_on_error(monkeypatch):
    def fail(self, *args): raise AssertionError(args[2])
    monkeypatch.setattr(ImagePane, "message_box", fail)


def drag(label, start, end):
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(label, end)
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)


@pytest.mark.parametrize("zoom", [500, 1000, 2000])
@pytest.mark.parametrize("reverse", [False, True])
def test_mosaic_rectangle_pixels_coordinates_and_undo(browser, zoom, reverse):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    original = pane.image().copy()
    original_bytes = path.read_bytes()
    pane.choose_zoom(zoom)
    QTest.keyClick(pane.scroll, Qt.Key.Key_M, Qt.KeyboardModifier.AltModifier)
    assert pane.mosaic_button.isChecked()
    start = QPoint(round(20 * zoom / 1000), round(16 * zoom / 1000))
    end = QPoint(round(100 * zoom / 1000), round(64 * zoom / 1000))
    drag(pane.label, end if reverse else start, start if reverse else end)
    result = pane.image()
    assert result.size == original.size
    assert result.crop((0, 0, 20, 80)).tobytes() == original.crop((0, 0, 20, 80)).tobytes()
    assert result.crop((100, 0, 120, 80)).tobytes() == original.crop((100, 0, 120, 80)).tobytes()
    assert result.crop((0, 0, 120, 16)).tobytes() == original.crop((0, 0, 120, 16)).tobytes()
    assert result.crop((0, 64, 120, 80)).tobytes() == original.crop((0, 64, 120, 80)).tobytes()
    colors = result.crop((20, 16, 100, 64)).getcolors(maxcolors=100)
    assert colors is not None and len(colors) < 100
    assert result.tobytes() != original.tobytes()
    assert pane.is_modified and len(pane.undo_stack) == 1
    assert path.read_bytes() == original_bytes
    QTest.keySequence(pane.scroll, QKeySequence(QKeySequence.StandardKey.Undo))
    assert pane.image().tobytes() == original.tobytes() and not pane.is_modified
    pane.redo()
    assert pane.image().tobytes() == result.tobytes()
    assert pane.save_image()
    assert_saved(path, result)
    assert not pane.is_modified


def test_mosaic_after_crop_rotation_mirror_and_multiple_regions(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    pane.rotate(); pane.mirror_h(); pane.set_crop((.25, .25, .75, .75))
    before = pane.image()
    pane.mosaic_button.click()
    pane.choose_zoom(2000)
    drag(pane.label, QPoint(1, 1), QPoint(40, 60))
    first = pane.image()
    assert first.size == before.size == (40, 60)
    assert first.crop((20, 0, 40, 60)).tobytes() == before.crop((20, 0, 40, 60)).tobytes()
    assert first.crop((0, 0, 20, 30)).tobytes() != before.crop((0, 0, 20, 30)).tobytes()
    drag(pane.label, QPoint(40, 60), QPoint(80, 120))
    second = pane.image()
    assert len(pane.undo_stack) == 5
    pane.undo()
    assert pane.image().tobytes() == first.tobytes()
    pane.undo()
    assert pane.image().tobytes() == before.tobytes()
    pane.redo(); pane.redo()
    target = folders[0] / "mosaic.png"
    assert pane.save_to(target)
    assert_saved(target, second)


def test_mosaic_tool_exclusion_cancel_bounds_and_navigation_warning(browser, monkeypatch):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    page = window.open_folder(folders[0], path)
    pane = page.image
    pane.crop_button.click()
    pane.mosaic_button.click()
    assert not pane.crop_button.isChecked() and pane.label.mosaic_active
    QTest.mouseClick(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    assert not pane.is_modified
    QTest.mousePress(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    move_drag(pane.label, QPoint(70, 60))
    assert pane.label.mosaic_start is not None and not pane.is_modified
    QTest.keyClick(pane.scroll, Qt.Key.Key_Escape)
    assert pane.label.mosaic_start is None and pane.label.mosaic_active
    QTest.mouseRelease(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(70, 60))
    assert not pane.is_modified
    QTest.keyClick(pane.scroll, Qt.Key.Key_Escape)
    assert not pane.mosaic_button.isChecked()
    pane.mosaic_button.click()
    pane.choose_zoom(1000)
    drag(pane.label, QPoint(10, 10), QPoint(500, 500))
    assert pane.is_modified
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Cancel)
    page.thumbs.select(page.files[1])
    assert pane.path == path and page.thumbs.selected_path == path
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Discard)
    window.set_compare(True)
    assert not pane.mosaic_button.isEnabled() and not pane.mosaic_button.isChecked()
    window.set_compare(False)
    pane.mosaic_button.click()
    pane.crop_button.click()
    assert not pane.mosaic_button.isChecked() and pane.label.crop_active


def test_mosaic_fullscreen_shortcut_and_no_pan(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    pane.open_full()
    full = pane.full_window
    full.activateWindow()
    wait_until(lambda: QApplication.activeWindow() is full)
    full.image_toolbar.set_zoom(2000)
    QTest.keyClick(full, Qt.Key.Key_M, Qt.KeyboardModifier.AltModifier)
    assert full.image_label.mosaic_active and full.image_toolbar.mosaic_button.isChecked()
    drag(full.image_label, QPoint(20, 20), QPoint(180, 120))
    assert pane.is_modified and len(pane.undo_stack) == 1
    QTest.keyClick(full, Qt.Key.Key_Escape)
    assert pane.full_window is full and not pane.mosaic_button.isChecked()
    full.close()


def test_mosaic_scrolled_large_image_does_not_pan(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    with Image.open(path) as source:
        large = source.resize((1800, 1200), Image.Resampling.BILINEAR)
    large.save(path)
    pane = window.open_folder(folders[0], path).image
    pane.choose_zoom(1000)
    wait_until(lambda: pane.scroll.horizontalScrollBar().maximum() > 200)
    pane.scroll.horizontalScrollBar().setValue(200)
    pane.scroll.verticalScrollBar().setValue(120)
    values = pane.scroll.horizontalScrollBar().value(), pane.scroll.verticalScrollBar().value()
    pane.mosaic_button.click()
    before = pane.image()
    drag(pane.label, QPoint(220, 140), QPoint(380, 280))
    assert (pane.scroll.horizontalScrollBar().value(), pane.scroll.verticalScrollBar().value()) == values
    assert pane.image().crop((0, 0, 220, 1200)).tobytes() == before.crop((0, 0, 220, 1200)).tobytes()
    assert pane.image().crop((220, 140, 380, 280)).tobytes() != before.crop((220, 140, 380, 280)).tobytes()


def test_mosaic_available_in_overflow_and_language_updates(browser):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    window.set_orientation(Qt.Orientation.Horizontal)
    window.resize(260, 300)
    controller = pane.toolbar_overflow
    wait_until(lambda: pane.mosaic_button in controller.overflowed)
    controller.populate_menu()
    controller.panel_controls[pane.mosaic_button].click()
    assert pane.label.mosaic_active
    window.toggle_lang()
    binding = QKeySequence("Alt+M").toString(QKeySequence.SequenceFormat.NativeText)
    assert pane.mosaic_button.toolTip() == f"{window.t['mosaic']} ({binding})"


def test_mosaic_animation_all_frames_and_svg_save(browser):
    window, folders = browser
    path = folders[0] / "animated.gif"
    first = Image.new("RGBA", (120, 80))
    first.putdata([(x * 2, y * 3, 0, 255) for y in range(80) for x in range(120)])
    second = first.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    first.save(path, save_all=True, append_images=[second], duration=[80, 160], loop=3)
    pane = window.open_folder(folders[0], path).image
    originals = [source.copy() for source, _ in pane.frames]
    pane.mosaic_button.click()
    pane.apply_mosaic((.25, .25, .75, .75))
    assert all(source.tobytes() != original.tobytes() for (source, _), original in zip(pane.frames, originals))
    target = folders[0] / "result.gif"
    assert pane.save_to(target)
    with Image.open(target) as saved:
        assert saved.n_frames == 2 and saved.info["loop"] == 3
    svg = folders[0] / "source.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">'
                   '<path fill="red" d="M0 0h60v80H0z"/><path fill="blue" d="M60 0h60v80H60z"/></svg>')
    pane.load(svg)
    pane.mosaic_button.click()
    pane.apply_mosaic((.25, .25, .75, .75))
    expected = pane.image()
    assert pane.save_image()
    assert b"<path" not in svg.read_bytes()
    assert b"data:image/png;base64," in svg.read_bytes()
    actual = pane.image()
    assert actual.pixelColor(10, 10).red() == expected.getpixel((10, 10))[0]


def test_save_retries_temporary_windows_file_lock(browser, monkeypatch):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    pane.rotate()
    expected = pane.image()
    original_replace = editing.os.replace
    attempts = []
    def replace(source, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            error = PermissionError("temporarily locked")
            error.winerror = 5
            raise error
        return original_replace(source, destination)
    monkeypatch.setattr(editing.os, "replace", replace)
    assert pane.save_image()
    assert len(attempts) == 3
    assert_saved(pane.path, expected)


def test_save_permanent_lock_preserves_file_and_mosaic(browser, monkeypatch):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    original = pane.path.read_bytes()
    pane.apply_mosaic((.2, .2, .8, .8))
    attempts, errors = [], []
    def locked(*args):
        attempts.append(args)
        error = PermissionError("locked")
        error.winerror = 32
        raise error
    monkeypatch.setattr(editing.os, "replace", locked)
    monkeypatch.setattr(editing.time, "sleep", lambda _: None)
    monkeypatch.setattr(pane, "message_box", lambda *args: errors.append(args))
    assert not pane.save_image()
    assert len(attempts) == 6 and errors
    assert pane.path.read_bytes() == original and pane.is_modified
    assert not list(pane.path.parent.glob(".picview-*"))
