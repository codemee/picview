import pytest
from PIL import Image, ImageOps
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from test_tabs import browser, wait_until


def move_drag(label, end):
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(end), QPointF(label.mapToGlobal(end)),
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(label, event)


@pytest.mark.parametrize("handle,delta,expected", [
    ("tl", (20, 10), (100, 70)), ("t", (0, 10), (120, 70)),
    ("tr", (-20, 10), (100, 70)), ("r", (-20, 0), (100, 80)),
    ("br", (-20, -10), (100, 70)), ("b", (0, -10), (120, 70)),
    ("bl", (20, -10), (100, 70)), ("l", (20, 0), (100, 80)),
])
def test_handles_crop_live_without_repositioning_or_changing_file(browser, handle, delta, expected):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    original = pane.path.read_bytes()
    pane.choose_zoom(1000)
    pane.crop_button.click()
    QApplication.processEvents()
    label = pane.label
    start = label.handles()[handle].toPoint()
    end = start + QPoint(*delta)
    position, size = label.pos(), label.size()
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(label, end)
    # Verify before releasing: crop changes immediately and drag geometry stays fixed.
    assert pane.image().size == expected
    assert pane.image_size() == expected
    assert label.pos() == position and label.size() == size
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
    pane.crop_button.click()
    assert not label.crop_active
    assert (label.width(), label.height()) == expected
    assert pane.path.read_bytes() == original
    pane.undo()
    assert pane.image().size == (120, 80)
    assert not pane.undo_stack


def test_crop_pixels_zoom_bounds_navigation_and_comparison(browser):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    pane.choose_zoom(2000)
    pane.crop_button.click()
    label = pane.label
    start = label.handles()["l"].toPoint()
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(label, start + QPoint(60, 0))
    assert pane.image_size() == (90, 80)
    # During the drag, discarded pixels remain visible at reduced opacity.
    rendered = label.grab().toImage()
    discarded = rendered.pixelColor(24, 35)
    retained = rendered.pixelColor(100, 35)
    assert discarded.red() == 255
    assert 60 <= discarded.alpha() <= 90
    assert retained.red() == 255 and retained.alpha() == 255
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=start + QPoint(60, 0))
    assert label.grab().toImage().pixelColor(24, 35).alpha() == 0
    assert pane.image_size() == (90, 80)
    # The committed edge can be dragged again to reveal and adjust the source.
    start = label.handles()["l"].toPoint()
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(label, start + QPoint(1000, 0))
    assert pane.image_size() == (1, 80)
    move_drag(label, start - QPoint(1000, 0))
    assert pane.image_size() == (120, 80)
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=start)
    pane.set_crop((.25, .25, .75, .75))
    pane.open_full()
    assert pane.fullscreen_pixmap(pane.full_window.size(), 1).size().width() == 60
    pane.open_full()
    window.set_compare(True)
    assert not pane.crop_button.isChecked()
    assert not label.crop_active
    assert not pane.crop_button.isEnabled()
    assert pane.crop_button.property("toolbar_available") is False
    window.set_compare(False)
    assert pane.crop_button.isEnabled()
    pane.load(folders[0] / "image1.png")
    assert pane.image_size() == (120, 80)
    assert not pane.undo_stack
    pane.clear()
    assert not pane.crop_button.isEnabled()


@pytest.mark.parametrize("horizontal,vertical", [(False, False), (True, False), (False, True), (True, True)])
def test_crop_follows_rotations_and_mirrors(browser, horizontal, vertical):
    window, folders = browser
    path = folders[0] / "pattern.png"
    image = Image.new("RGBA", (120, 80))
    image.putdata([(x * 2, y * 3, (x + y) % 255, 255) for y in range(80) for x in range(120)])
    image.save(path)
    pane = window.open_folder(folders[0], path).image
    if horizontal: pane.mirror_h()
    if vertical: pane.mirror_v()
    pane.set_crop((.25, .125, .75, .75))
    expected = pane.image()
    pane.rotate()
    # With the existing post-rotation mirror axes, rotation reverses under one mirror.
    expected = expected.rotate(90 if horizontal != vertical else -90, expand=True)
    assert pane.image().tobytes() == expected.tobytes()
    pane.mirror_h()
    expected = ImageOps.mirror(expected)
    assert pane.image().tobytes() == expected.tobytes()
    pane.mirror_v()
    expected = ImageOps.flip(expected)
    assert pane.image().tobytes() == expected.tobytes()


def test_svg_and_animation_crop(browser):
    window, folders = browser
    path = folders[0] / "crop.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">'
                    '<path fill="red" d="M0 0h60v80H0z"/><path fill="blue" d="M60 0h60v80H60z"/></svg>')
    pane = window.open_folder(folders[0], path).image
    pane.crop_button.click()
    pane.set_crop((.5, 0., 1., 1.))
    pane.crop_button.click()
    assert pane.image_size() == (60, 80)
    assert pane.label.pixmap().toImage().pixelColor(30, 40).blue() == 255
    pane.rotate()
    assert pane.image_size() == (80, 60)
    assert pane.svg_image((160, 120)).pixelColor(80, 60).blue() == 255
    gif = folders[0] / "crop.gif"
    Image.new("RGB", (120, 80), "red").save(gif, save_all=True,
        append_images=[Image.new("RGB", (120, 80), "blue")], duration=100)
    pane.load(gif)
    pane.crop_button.click()
    pane.set_crop((.25, .25, .75, .75))
    pane.next_frame()
    assert pane.image().size == (60, 40)
    assert pane.image().getpixel((0, 0)) == (0, 0, 255, 255)


def test_crop_fit_remains_stable_and_tools_work_in_overflow(browser):
    window, folders = browser
    path = folders[0] / "large.png"
    Image.new("RGB", (1800, 1200), "blue").save(path)
    pane = window.open_folder(folders[0], path).image
    window.set_orientation(Qt.Orientation.Horizontal)
    window.resize(260, 350)
    controller = pane.toolbar_overflow
    wait_until(lambda: pane.crop_button in controller.overflowed)
    controller.populate_menu()
    controller.panel_controls[pane.crop_button].click()
    assert pane.label.crop_active
    assert pane.fit_to_pane
    pane.set_crop((.4, .4, .6, .6))
    window.resize(800, 700)
    QApplication.processEvents()
    pane.refresh_after_resize()
    assert pane.fit_to_pane
    assert pane.label.width() < pane.scroll.viewport().width()
    assert pane.label.height() < pane.scroll.viewport().height()
    window.resize(260, 350)
    pane.undo()
    assert pane.image_size() == (1800, 1200)
    assert pane.label.crop_active
    window.set_compare(True)
    controller.populate_menu()
    assert pane.crop_button not in controller.panel_controls
