from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QToolButton

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


def test_tools_and_tabs_share_one_row_with_no_empty_header(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    wait_until(lambda: len(visible_controls(window)) == 6)
    assert window.main_toolbar.height() == 42
    assert window.tabs.strip.parentWidget() is window.main_toolbar
    assert window.tabs.layout().count() == 1
    assert all(window.tabs.strip.geometry().right() < button.geometry().left()
               for button in visible_controls(window))
    assert window.language_button.geometry().right() < window.theme_button.geometry().left()
    toolbar_bottom = window.main_toolbar.mapTo(window, QPoint(0, window.main_toolbar.height())).y()
    page_top = page.mapTo(window, QPoint(0, 0)).y()
    assert page_top == toolbar_bottom
    assert window.tabs.strip.mapTo(window, QPoint(0, window.tabs.strip.height())).y() == page_top
    assert window.open_button.y() == 4
    assert window.open_button.height() == 34


def test_many_tabs_scroll_without_continuing_to_hide_tools(browser):
    window, folders = browser
    window.resize(650, 500)
    for _ in range(3): window.open_folder(folders[0])
    wait_until(lambda: window.tabs.count() == 3 and window.toolbar_overflow.overflowed)
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
            assert window.tabs.strip.width() >= 190
    page = window.current_tab()
    window.tabs.bar.moveTab(window.tabs.currentIndex(), 0)
    assert window.current_tab() is page
    wait_until(lambda: current_tab_visible(window))
