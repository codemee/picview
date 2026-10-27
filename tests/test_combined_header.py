from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolButton
import pytest

from picview.qt_app import FolderTabBar

from test_tabs import browser, wait_until


def visible_controls(window):
    return [button for button in (window.open_button, window.vertical_button,
            window.horizontal_button, window.compare_button, window.language_button,
            window.theme_button) if not button.isHidden()]


def current_tab_visible(window):
    bar = window.tabs.bar
    rect = bar.tabRect(bar.currentIndex())
    arrows = [button for button in bar.findChildren(QToolButton)
              if button.isVisible() and button.objectName().startswith("Scroll")]
    right = min((button.x() for button in arrows), default=bar.width())
    return rect.left() >= 0 and rect.right() < right


@pytest.mark.parametrize("count", [2, 3, 4])
def test_tabs_absorb_one_pixel_overflow_without_obscuring_current_tab(browser, count):
    bar = FolderTabBar()
    bar.setExpanding(False)
    bar.setUsesScrollButtons(True)
    for index in range(count): bar.addTab(f"Folder {index}")
    bar.setCurrentIndex(count - 1)
    bar.resize(count * 150 - 1, 34)
    bar.show()
    try:
        QTest.qWait(50)
        assert bar.tabRect(count - 1).right() < bar.width()
        assert not any(button.isVisible() for button in bar.findChildren(QToolButton)
                       if button.objectName().startswith("Scroll"))
    finally:
        bar.close()
        bar.deleteLater()


def test_tabs_share_thumbnail_header_below_main_toolbar(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    wait_until(lambda: len(visible_controls(window)) == 6)
    assert window.main_toolbar.height() == 42
    assert window.tabs.strip.parentWidget() is page.thumbs.tab_slot
    assert window.tabs.layout().count() == 1
    assert window.tabs.strip.mapTo(window, QPoint(window.tabs.strip.width(), 0)).x() <= page.thumbs.max_button.mapTo(window, QPoint()).x()
    assert window.language_button.geometry().right() < window.theme_button.geometry().left()
    assert window.modified_button.geometry().right() < window.language_button.geometry().left()
    assert window.theme_button.geometry().right() == window.main_toolbar.width() - 9
    assert window.language_button.x() > window.compare_button.geometry().right() + 100
    toolbar_bottom = window.main_toolbar.mapTo(window, QPoint(0, window.main_toolbar.height())).y()
    page_top = page.mapTo(window, QPoint(0, 0)).y()
    assert page_top == toolbar_bottom
    assert window.tabs.strip.mapTo(window, QPoint()).y() == page_top + 4
    assert window.tabs.strip.height() == 34
    assert window.open_button.y() == 4
    assert window.open_button.x() == 8
    assert window.open_button.height() == 34


def test_many_tabs_scroll_without_continuing_to_hide_tools(browser):
    window, folders = browser
    window.resize(650, 500)
    for _ in range(3): window.open_folder(folders[0])
    wait_until(lambda: window.tabs.count() == 3 and current_tab_visible(window))
    window.toolbar_overflow.update()
    controls = visible_controls(window)
    assert window.open_button in controls and window.compare_button in controls
    for _ in range(12): window.open_folder(folders[1])
    wait_until(lambda: current_tab_visible(window))
    window.toolbar_overflow.update()
    assert visible_controls(window) == controls
    assert window.tabs.bar.usesScrollButtons()
    assert any(button.isVisible() for button in window.tabs.bar.findChildren(QToolButton)
               if button.objectName().startswith("Scroll"))


def test_switching_reordering_and_resizing_keep_current_tab_visible(browser):
    window, folders = browser
    for _ in range(12): window.open_folder(folders[0])
    for width in (850, 420, 260, 1100):
        window.resize(width, 500)
        wait_until(lambda: window.width() == width and current_tab_visible(window))
        for index in (0, 7, window.tabs.count() - 1):
            window.tabs.setCurrentIndex(index)
            wait_until(lambda: current_tab_visible(window))
        if width == 420:
            assert not window.open_button.isHidden()
            assert not window.compare_button.isHidden()
        if width == 260:
            assert window.toolbar_overflow.more_button.isVisible()
            assert window.tabs.strip.width() >= 180
    page = window.current_tab()
    window.tabs.bar.moveTab(window.tabs.currentIndex(), 0)
    assert window.current_tab() is page
    wait_until(lambda: current_tab_visible(window))
