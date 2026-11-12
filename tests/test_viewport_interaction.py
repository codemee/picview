from PIL import Image
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from test_tabs import browser, wait_until


def drag_left(widget, start, end):
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=start)
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(end), QPointF(widget.mapToGlobal(end)),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=end)


def test_image_and_fullscreen_drag_pan_scrollbars(browser):
    window, folders = browser
    path = folders[0] / "large.png"
    Image.new("RGB", (1800, 1400), "blue").save(path)
    pane = window.open_folder(folders[0], path).image
    pane.choose_zoom(1000)
    wait_until(lambda: pane.scroll.horizontalScrollBar().maximum() > 100)
    pane.scroll.horizontalScrollBar().setValue(0)
    drag_left(pane.scroll.viewport(), QPoint(160, 80), QPoint(60, 80))
    assert pane.scroll.horizontalScrollBar().value() == 100
    pane.open_full()
    full = pane.full_window
    full.image_toolbar.set_zoom(2000)
    wait_until(lambda: full.image_scroll.horizontalScrollBar().maximum() > 100)
    full.image_scroll.horizontalScrollBar().setValue(0)
    drag_left(full.image_scroll.viewport(), QPoint(160, 80), QPoint(60, 80))
    assert full.image_scroll.horizontalScrollBar().value() == 100
    assert full.image_scroll.horizontalScrollBar().styleSheet() == window.scrollbar_style
    full.close()


def test_zoom_shortcuts_follow_thumbnail_and_image_focus(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    page.thumbs.scroll.setFocus()
    wait_until(lambda: window.input_pane == "thumb")
    previous = page.thumbs.size
    QTest.keyClick(page.thumbs.scroll, Qt.Key.Key_Plus)
    assert page.thumbs.size == previous + 10
    assert page.thumbs.property("inputFocused")
    page.image.scroll.setFocus()
    wait_until(lambda: window.input_pane == "image")
    assert page.image.property("inputFocused")
    assert not page.thumbs.property("inputFocused")
    previous = page.image.slider.value()
    QTest.keyClick(page.image.scroll, Qt.Key.Key_Plus)
    assert page.image.slider.value() == previous + 100


def test_fullscreen_zoom_shortcut_changes_fullscreen_scale(browser):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    pane.open_full()
    wait_until(lambda: pane.full_window.isFullScreen())
    pane.full_window.activateWindow()
    wait_until(lambda: QApplication.activeWindow() is pane.full_window)
    QTest.keyClick(pane.full_window, Qt.Key.Key_Plus)
    assert pane.fullscreen_zoom is not None
    QTest.keyClick(pane.full_window, Qt.Key.Key_0)
    assert pane.fullscreen_zoom == 1.0
    pane.full_window.close()


@pytest.mark.parametrize("compare", [False, True])
def test_alt_f_fits_active_fullscreen_image(browser, compare):
    window, folders = browser
    first = window.open_folder(folders[0])
    if compare:
        second = window.open_folder(folders[1])
        window.set_compare(True)
        window.check_compare_page(first, True)
        window.open_comparison_fullscreen()
        full = window.compare_full_window
    else:
        first.image.open_full()
        full = first.image.full_window
    full.activateWindow()
    wait_until(lambda: QApplication.activeWindow() is full)
    toolbar = full.image_toolbar
    pane = toolbar.page.image
    toolbar.set_zoom(2000)
    assert pane.fullscreen_zoom == 2.0
    QTest.keyClick(full, Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier)
    assert pane.fullscreen_zoom is None
    assert toolbar.fit_button.isChecked()
    QTest.keyClick(full, Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier)
    assert pane.fullscreen_zoom == 1.0
    full.close()
