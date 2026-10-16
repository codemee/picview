import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from test_tabs import browser, wait_until


@pytest.mark.parametrize("orientation", [Qt.Orientation.Vertical, Qt.Orientation.Horizontal])
def test_up_down_follow_thumbnail_rows_and_boundaries(browser, orientation):
    window, folders = browser
    for index in range(2, 31): Image.new("RGB", (40, 30), "blue").save(folders[0] / f"image{index}.png")
    page = window.open_folder(folders[0])
    window.set_orientation(orientation)
    QTest.qWait(100)
    columns = page.thumbs.columns
    assert columns >= 2
    page.thumbs.select(page.files[1])
    QTest.keyClick(window, Qt.Key.Key_Up)
    assert page.thumbs.selected_path == page.files[1]
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert page.thumbs.selected_path == page.files[1 + columns]
    QTest.keyClick(window, Qt.Key.Key_Up)
    assert page.thumbs.selected_path == page.files[1]
    page.thumbs.select(page.files[-1])
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert page.thumbs.selected_path == page.files[-1]
    last_row = (len(page.files) - 1) // columns
    page.thumbs.select(page.files[last_row * columns - 1])
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert page.thumbs.selected_path == page.files[-1]
    def selection_is_visible():
        button = page.thumbs.buttons[page.thumbs.selected_path]
        viewport = page.thumbs.scroll.viewport()
        return viewport.rect().intersects(button.rect().translated(button.mapTo(viewport, QPoint(0, 0))))
    wait_until(selection_is_visible)


def test_row_navigation_adapts_to_resize_and_routes_to_active_tab(browser):
    window, folders = browser
    for index in range(2, 25): Image.new("RGB", (40, 30), "blue").save(folders[0] / f"image{index}.png")
    first = window.open_folder(folders[0])
    QTest.qWait(50)
    old_columns = first.thumbs.columns
    first.thumbs.slider.setValue(260)
    QTest.qWait(100)
    assert first.thumbs.columns < old_columns
    window.resize(800, 650)
    QTest.qWait(100)
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert first.thumbs.selected_path == first.files[first.thumbs.columns]
    second = window.duplicate_page(first)
    window.set_compare(True)
    window.check_compare_page(first, True)
    QTest.qWait(100)
    selected = first.thumbs.selected_path
    second.thumbs.select(second.files[0])
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert second.thumbs.selected_path == second.files[second.thumbs.columns]
    assert first.thumbs.selected_path == selected


def test_row_navigation_in_empty_and_single_column_folders(browser):
    window, folders = browser
    empty = folders[0] / "empty"
    empty.mkdir()
    page = window.open_folder(empty)
    QTest.keyClick(window, Qt.Key.Key_Up)
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert page.thumbs.selected_path is None
    page.open_folder(folders[0])
    page.thumbs.columns = 1
    page.select_row(1)
    assert page.thumbs.selected_path == page.files[1]
    page.select_row(-1)
    assert page.thumbs.selected_path == page.files[0]


@pytest.mark.parametrize("focus_target", ["scroll", "viewport", "scrollbar", "thumbnail"])
def test_up_down_select_images_when_thumbnail_area_has_focus(browser, focus_target):
    window, folders = browser
    for index in range(2, 31): Image.new("RGB", (40, 30), "blue").save(folders[0] / f"image{index}.png")
    page = window.open_folder(folders[0])
    QTest.qWait(100)
    page.thumbs.select(page.files[1])
    if focus_target == "thumbnail":
        QTest.mouseClick(page.thumbs.buttons[page.files[1]], Qt.MouseButton.LeftButton)
        target = window.focusWidget()
    else:
        target = {"scroll": page.thumbs.scroll, "viewport": page.thumbs.scroll.viewport(), "scrollbar": page.thumbs.scroll.verticalScrollBar()}[focus_target]
        target.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        target.setFocus()
    QTest.qWait(30)
    columns = page.thumbs.columns
    QTest.keyClick(target, Qt.Key.Key_Down)
    assert page.thumbs.selected_path == page.files[1 + columns]
    assert page.image.path == page.thumbs.selected_path
    QTest.keyClick(window.focusWidget(), Qt.Key.Key_Up)
    assert page.thumbs.selected_path == page.files[1]


def test_thumbnail_viewport_handles_keys_without_global_shortcut(browser):
    window, folders = browser
    for index in range(2, 25): Image.new("RGB", (40, 30), "blue").save(folders[0] / f"image{index}.png")
    page = window.open_folder(folders[0])
    QTest.qWait(100)
    for shortcut in window.shortcuts: shortcut.setEnabled(False)
    for target in (page.thumbs.scroll, page.thumbs.scroll.viewport(), page.thumbs.scroll.verticalScrollBar()):
        page.thumbs.select(page.files[1])
        override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, override)
        assert override.isAccepted()
        QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
        assert page.thumbs.selected_path == page.files[1 + page.thumbs.columns]
        assert page.image.path == page.thumbs.selected_path
        QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier))
        assert page.thumbs.selected_path == page.files[1]
