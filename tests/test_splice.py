import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from picview.qt_app import ImagePane
from test_crop import move_drag
from test_editing import assert_saved, pattern
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
@pytest.mark.parametrize("axis", ["x", "y"])
def test_splice_gestures_join_original_pixels_at_any_zoom(browser, axis, reverse, zoom):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    original, data = pane.image().copy(), path.read_bytes()
    pane.choose_zoom(zoom)
    pane.splice_button.click()
    start, end = ((20, 20), (60, 28)) if axis == "x" else ((30, 16), (35, 56))
    start = QPoint(*(round(value * zoom / 1000) for value in start))
    end = QPoint(*(round(value * zoom / 1000) for value in end))
    if reverse: start, end = end, start
    QTest.mousePress(pane.label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(pane.label, end)
    assert pane.label.splice_axis == axis
    rect = pane.label.splice_rect()
    if axis == "x":
        assert rect.top() == 0 and rect.height() == pane.label.height()
    else:
        assert rect.left() == 0 and rect.width() == pane.label.width()
    assert pane.image().tobytes() == original.tobytes() and not pane.is_modified
    QTest.mouseRelease(pane.label, Qt.MouseButton.LeftButton, pos=end)
    result = pane.image()
    if axis == "x":
        assert result.size == (80, 80)
        assert result.crop((0, 0, 20, 80)).tobytes() == original.crop((0, 0, 20, 80)).tobytes()
        assert result.crop((20, 0, 80, 80)).tobytes() == original.crop((60, 0, 120, 80)).tobytes()
    else:
        assert result.size == (120, 40)
        assert result.crop((0, 0, 120, 16)).tobytes() == original.crop((0, 0, 120, 16)).tobytes()
        assert result.crop((0, 16, 120, 40)).tobytes() == original.crop((0, 56, 120, 80)).tobytes()
    assert pane.is_modified and len(pane.undo_stack) == 1
    assert pane.splice_button.isChecked() and path.read_bytes() == data
    assert window.image_status.details.startswith(path.name + " *")
    pane.undo()
    assert pane.image().tobytes() == original.tobytes() and not pane.is_modified
    pane.redo()
    assert pane.image().tobytes() == result.tobytes()


def test_preview_changes_direction_and_spans_image_before_release(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    pane.choose_zoom(1000)
    pane.splice_button.click()
    label = pane.label
    original_color = label.grab().toImage().pixelColor(40, 10)
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    move_drag(label, QPoint(60, 25))
    assert label.splice_axis == "x"
    assert label.splice_rect().getRect() == pytest.approx((20., 0., 40., 80.))
    assert label.grab().toImage().pixelColor(40, 10) != original_color
    move_drag(label, QPoint(25, 60))
    assert label.splice_axis == "y"
    assert label.splice_rect().getRect() == pytest.approx((0., 20., 120., 40.))
    assert label.grab().toImage().pixelColor(40, 10) == original_color
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=QPoint(25, 60))
    assert pane.image_size() == (120, 40)


@pytest.mark.parametrize("size,delta,axis", [((400, 40), (20, 10), "x"), ((40, 400), (10, 20), "y")])
def test_direction_uses_display_distance_on_wide_and_tall_images(browser, size, delta, axis):
    window, folders = browser
    path = folders[0] / "wide.png"
    Image.new("RGBA", size, "red").save(path)
    pane = window.open_folder(folders[0], path).image
    pane.choose_zoom(1000)
    pane.splice_button.click()
    start, end = QPoint(5, 5), QPoint(5 + delta[0], 5 + delta[1])
    QTest.mousePress(pane.label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(pane.label, end)
    assert pane.label.splice_axis == axis
    QTest.keyClick(pane.scroll, Qt.Key.Key_Escape)
    QTest.mouseRelease(pane.label, Qt.MouseButton.LeftButton, pos=end)
    assert pane.image_size() == size and not pane.is_modified


def test_splice_exclusion_cancel_edges_and_unsaved_warning(browser, monkeypatch):
    window, folders = browser
    page = window.open_folder(folders[0])
    pane = page.image
    pane.choose_zoom(1000)
    pane.crop_button.click()
    pane.splice_button.click()
    assert not pane.crop_button.isChecked() and pane.label.splice_active
    pane.mosaic_button.click()
    assert not pane.splice_button.isChecked() and pane.label.mosaic_active
    pane.splice_button.click()
    assert not pane.mosaic_button.isChecked()
    QTest.mouseClick(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    assert not pane.is_modified
    drag(pane.label, QPoint(0, 10), QPoint(500, 10))
    assert pane.image_size() == (120, 80) and not pane.is_modified
    drag(pane.label, QPoint(0, 10), QPoint(20, 10))
    assert pane.image_size() == (100, 80)
    drag(pane.label, QPoint(80, 10), QPoint(500, 10))
    assert pane.image_size() == (80, 80) and len(pane.undo_stack) == 2
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Cancel)
    page.thumbs.select(page.files[1])
    assert pane.path == page.files[0] and pane.is_modified
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Discard)
    QTest.keyClick(pane.scroll, Qt.Key.Key_Escape)
    assert not pane.splice_button.isChecked()
    pane.splice_button.click()
    window.set_compare(True)
    assert not pane.splice_button.isEnabled() and not pane.splice_button.isChecked()
    window.set_compare(False)
    pane.clear()
    assert not pane.splice_button.isEnabled()


def test_splice_after_other_edits_and_save_with_history(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    pane.rotate(); pane.mirror_h(); pane.set_crop((.25, .25, .75, .75))
    before = pane.image().copy()
    pane.choose_zoom(2000)
    pane.splice_button.click()
    drag(pane.label, QPoint(20, 20), QPoint(60, 25))
    result = pane.image().copy()
    assert result.size == (20, 60) and len(pane.undo_stack) == 4
    assert result.crop((0, 0, 10, 60)).tobytes() == before.crop((0, 0, 10, 60)).tobytes()
    assert result.crop((10, 0, 20, 60)).tobytes() == before.crop((30, 0, 40, 60)).tobytes()
    assert pane.save_image()
    assert_saved(path, result)
    pane.undo()
    assert pane.image().tobytes() == before.tobytes()
    pane.redo()
    assert pane.image().tobytes() == result.tobytes() and not pane.is_modified


def test_splice_fullscreen_and_overflow(browser):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    window.set_orientation(Qt.Orientation.Horizontal)
    window.resize(260, 350)
    controller = pane.toolbar_overflow
    wait_until(lambda: pane.splice_button in controller.overflowed)
    controller.populate_menu()
    controller.panel_controls[pane.splice_button].click()
    assert pane.label.splice_active
    pane.open_full()
    full = pane.full_window
    full.activateWindow()
    wait_until(lambda: QApplication.activeWindow() is full)
    full.image_toolbar.set_zoom(2000)
    assert full.image_label.splice_active and full.image_toolbar.splice_button.isChecked()
    QTest.keyClick(full, Qt.Key.Key_J, Qt.KeyboardModifier.AltModifier)
    assert not full.image_label.splice_active and not full.image_toolbar.splice_button.isChecked()
    QTest.keyClick(full, Qt.Key.Key_J, Qt.KeyboardModifier.AltModifier)
    assert full.image_label.splice_active and full.image_toolbar.splice_button.isChecked()
    drag(full.image_label, QPoint(40, 20), QPoint(160, 25))
    assert pane.image_size() == (60, 80)
    QTest.keyClick(full, Qt.Key.Key_Escape)
    assert pane.full_window is full and not pane.splice_button.isChecked()
    full.close()


def test_splice_animation_and_svg_output(browser):
    window, folders = browser
    path = folders[0] / "animation.gif"
    Image.new("RGB", (120, 80), "red").save(path, save_all=True,
        append_images=[Image.new("RGB", (120, 80), "blue")], duration=[80, 160], loop=3)
    pane = window.open_folder(folders[0], path).image
    pane.splice_button.click()
    pane.apply_splice("y", .25, .75)
    assert all(source.size == (120, 40) for source, _ in pane.frames)
    assert pane.save_image()
    with Image.open(path) as saved:
        assert saved.n_frames == 2 and saved.size == (120, 40) and saved.info["loop"] == 3
        assert saved.info["duration"] == 80
        saved.seek(1)
        assert saved.info["duration"] == 160
    svg = folders[0] / "source.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">'
                   '<path fill="red" d="M0 0h60v80H0z"/><path fill="blue" d="M60 0h60v80H60z"/></svg>')
    pane.load(svg)
    pane.splice_button.click()
    pane.apply_splice("x", 1 / 3, 2 / 3)
    assert pane.image_size() == (80, 80)
    assert pane.save_image()
    actual = pane.image()
    assert actual.pixelColor(20, 40).red() == 255 and actual.pixelColor(60, 40).blue() == 255


def test_splice_preserves_transparency(browser):
    window, folders = browser
    path = folders[0] / "alpha.png"
    original = Image.new("RGBA", (120, 80))
    original.putdata([(x, y, 100, (x + y) % 256) for y in range(80) for x in range(120)])
    original.save(path)
    pane = window.open_folder(folders[0], path).image
    pane.apply_splice("x", .25, .75)
    result = pane.image()
    assert result.mode == "RGBA" and result.size == (60, 80)
    assert result.crop((0, 0, 30, 80)).tobytes() == original.crop((0, 0, 30, 80)).tobytes()
    assert result.crop((30, 0, 60, 80)).tobytes() == original.crop((90, 0, 120, 80)).tobytes()
