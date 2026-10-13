from test_tabs import browser, wait_until

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTabBar


def control(window, page):
    return window.tabs.bar.tabButton(window.tabs.indexOf(page), QTabBar.ButtonPosition.LeftSide)


def test_compare_independent_selection_and_view(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.compare_button.click()
    assert window.checked_pages == {second}
    control(window, first).click()
    assert window.current_tab() is second
    assert window.comparison_area.pages == [first, second]
    window.tabs.setCurrentWidget(first)
    first.thumbs.select(first.files[1])
    first.image.rotate()
    first.image.choose_zoom(1700)
    assert first.image.path == first.files[1]
    assert second.image.path == second.files[0]
    assert first.image.rotation == 90 and second.image.rotation == 0
    first.image.interacted.emit()
    assert window.image_target() is first.image
    window.compare_button.click()
    for page in (first, second):
        assert page.image.parentWidget() is page.image_slot
        assert not page.comparison_visible
        assert page.image.comparison_title is None
    assert first.image.rotation == 90


def test_equal_layout_reorder_unchecked_host_and_close(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    control(window, first).click()
    for orientation in (Qt.Orientation.Horizontal, Qt.Orientation.Vertical):
        window.set_orientation(orientation)
        QTest.qWait(100)
        expected = Qt.Orientation.Vertical if orientation == Qt.Orientation.Horizontal else Qt.Orientation.Horizontal
        assert window.comparison_area.split.orientation() == expected
        sizes = window.comparison_area.split.sizes()
        assert abs(sizes[0] - sizes[1]) <= 1
    window.tabs.bar.moveTab(0, 1)
    assert window.comparison_area.pages == [second, first]
    control(window, first).click()
    window.tabs.setCurrentWidget(first)
    assert window.comparison_area.parentWidget() is first.image_slot
    assert window.comparison_area.pages == [second]
    assert second.image.isVisible() and not first.image.isVisible()
    window.close_tab(window.tabs.indexOf(second))
    assert not window.checked_pages
    assert window.comparison_area.empty.isVisible()
    window.close_tab()
    assert window.tabs.count() == 1
    window.set_compare(False)


def test_background_compared_image_updates_and_deletion(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    control(window, first).click()
    path = first.image.path
    Image.new("RGB", (180, 90), "blue").save(path)
    wait_until(lambda: first.image.frames[0][0].size == (180, 90))
    assert first.image.frames[0][0].getpixel((0, 0))[:3] == (0, 0, 255)
    pixel = first.thumbs.buttons[path].preview.pixmap().toImage().pixelColor(0, 0)
    assert (pixel.red(), pixel.green(), pixel.blue()) == (0, 0, 255)
    path.unlink()
    wait_until(lambda: first.image.path == first.files[0] and first.image.path != path)
    assert first.pending_notification
    assert second.image.path == second.files[0]


def test_comparison_maximize_and_theme(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    control(window, first).click()
    first.image.max_button.click()
    assert first.image.isVisible() and not second.image.isVisible()
    first.image.max_button.click()
    assert first.image.isVisible() and second.image.isVisible()
    window.toggle_theme()
    window.toggle_lang()
    assert first.image.rotate_b.toolTip() == window.t["rotate"]
    assert control(window, first).isChecked()


def test_shared_toolbar_targets_clicked_pane_and_restores(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    control(window, first).click()
    area = window.comparison_area
    assert area.toolbar_image is second.image
    assert second.image.toolbar_widget.parentWidget() is area.header
    assert first.image.toolbar_widget.isHidden()
    second.image.rotate_b.click()
    assert second.image.rotation == 90 and first.image.rotation == 0
    QTest.mouseClick(first.image.scroll.viewport(), Qt.MouseButton.LeftButton)
    assert area.toolbar_image is first.image
    assert first.image.comparison_selected and not second.image.comparison_selected
    assert second.image.toolbar_widget.isHidden()
    first.image.rotate_b.click()
    first.image.slider.setValue(1500)
    assert first.image.rotation == 90 and second.image.rotation == 90
    assert first.image.zoom == 1.5 and second.image.zoom != 1.5
    control(window, first).click()
    assert area.toolbar_image is second.image
    window.set_compare(False)
    assert area.toolbar_image is None
    for page in (first, second):
        assert page.image.toolbar_widget.parentWidget() is page.image
        assert not page.image.toolbar_widget.isHidden()


def test_duplicate_same_folder_compares_independent_images_and_watches(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    window.set_compare(True)
    second = window.duplicate_page(first)
    assert window.checked_pages == {first, second}
    assert window.comparison_area.pages == [first, second]
    second.thumbs.select(second.files[1])
    second.image.rotate()
    assert first.image.path == first.files[0] and first.image.rotation == 0
    assert second.image.path == second.files[1] and second.image.rotation == 90
    second.thumbs.select(second.files[0])
    path = first.image.path
    Image.new("RGB", (180, 90), "blue").save(path)
    wait_until(lambda: all(page.image.frames[0][0].size == (180, 90) for page in (first, second)))
    path.unlink()
    wait_until(lambda: all(page.image.path != path for page in (first, second)))
    assert first.image.path == second.image.path
