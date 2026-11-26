from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QToolButton
import pytest

from picview.qt_app import FolderTabBar, PaneDragHandle, PALETTE, themed_palette, use_system_palette

from test_tabs import browser, wait_until


def visible_controls(window):
    return [button for button in (window.open_button, window.sort_button,
            window.direction_button,
            window.settings_button) if not button.isHidden()]


def current_tab_visible(window):
    bar = window.tabs.bar
    rect = bar.tabRect(bar.currentIndex())
    arrows = [button for button in bar.findChildren(QToolButton)
              if button.isVisible() and button.objectName().startswith("Scroll")]
    left = max((button.geometry().right() + 1 for button in arrows
                if button.objectName() == "ScrollLeftButton"), default=0)
    right = min((button.x() for button in arrows
                 if button.objectName() == "ScrollRightButton"), default=bar.width())
    return rect.left() >= left and rect.right() < right


def test_scroll_arrows_stay_at_opposite_edges(browser):
    window, folders = browser
    for _ in range(20): window.open_folder(folders[0])
    bar = window.tabs.bar
    for width in (1100, 650, 260):
        window.resize(width, 500)
        QTest.qWait(50)
        left = bar.findChild(QToolButton, "ScrollLeftButton")
        right = bar.findChild(QToolButton, "ScrollRightButton")
        assert left.isVisible() and right.isVisible()
        assert left.x() == 0
        assert right.geometry().right() == bar.width() - 1
        bar.setCurrentIndex(0)
        wait_until(lambda: current_tab_visible(window))
        left.click()
        right.click()
        bar.setCurrentIndex(bar.count() - 1)
        wait_until(lambda: current_tab_visible(window))


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_selected_underline_does_not_leak_below_scroll_arrows(browser, theme):
    app = QApplication.instance()
    original_palette = QPalette(app.palette())
    bar = FolderTabBar()
    try:
        app.setPalette(themed_palette(original_palette, theme))
        use_system_palette(app)
        bar.setStyleSheet(f"QTabBar{{background:{PALETTE['card']};}}")
        bar.setExpanding(False)
        bar.setUsesScrollButtons(True)
        for index in range(8): bar.addTab(f"Folder {index}")
        bar.resize(450, bar.sizeHint().height())
        bar.setCurrentIndex(7)
        bar.show()
        QTest.qWait(50)
        selected = bar.tabRect(bar.currentIndex())
        left = bar.findChild(QToolButton, "ScrollLeftButton")
        right = bar.findChild(QToolButton, "ScrollRightButton")
        assert left.isVisible() and right.isVisible()
        # Exercise native styles with arrows at both ends and vertical insets:
        # painting only behind each button rectangle leaves the bottom exposed.
        left.setGeometry(selected.left() + 2, 3, 16, bar.height() - 6)
        right.setGeometry(selected.right() - 15, 3, 16, bar.height() - 6)
        pixels = bar.grab().toImage()
        accent = QColor(PALETTE["accent"])
        for button in (left, right):
            for x in range(button.x(), button.x() + button.width()):
                assert pixels.pixelColor(x, bar.height() - 1) != accent
        assert pixels.pixelColor(selected.center().x(), bar.height() - 1) == accent
    finally:
        bar.close()
        bar.deleteLater()
        app.setPalette(original_palette)
        use_system_palette(app)


@pytest.mark.parametrize("count", [2, 3, 4])
def test_tabs_absorb_one_pixel_overflow_without_obscuring_current_tab(browser, count):
    bar = FolderTabBar()
    bar.setExpanding(False)
    bar.setUsesScrollButtons(True)
    for index in range(count): bar.addTab(f"Folder {index}")
    bar.setCurrentIndex(count - 1)
    bar.resize(count * 150 - 1, bar.sizeHint().height())
    bar.show()
    try:
        QTest.qWait(50)
        assert bar.tabRect(count - 1).right() < bar.width()
        assert not any(button.isVisible() for button in bar.findChildren(QToolButton)
                       if button.objectName().startswith("Scroll"))
    finally:
        bar.close()
        bar.deleteLater()


def test_folder_tools_use_main_toolbar_and_tabs_stay_in_thumbnail_pane(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    wait_until(lambda: len(visible_controls(window)) == 4)
    assert window.centralWidget().layout().count() == 2
    assert window.open_button.height() == 28
    assert window.open_button.parentWidget() is window.folder_toolbar
    assert window.folder_toolbar.parentWidget() is window.folder_toolbar_host
    assert page.thumbs.header_widget.parentWidget() is page.thumbs
    assert page.thumbs.layout().indexOf(page.thumbs.header_widget) == 0
    assert not window.folder_toolbar_host.findChildren(PaneDragHandle)
    assert page.thumbs.drag_handle.parentWidget() is page.thumbs.header_widget
    assert window.tabs.strip.parentWidget() is page.thumbs.tab_slot
    assert window.tabs.layout().count() == 1
    assert page.thumbs.drag_handle.mapTo(window, QPoint(page.thumbs.drag_handle.width(), 0)).x() <= window.tabs.strip.mapTo(window, QPoint()).x()
    assert window.modified_button.isHidden()
    assert window.settings_button.geometry().right() == window.folder_toolbar.width() - 1
    assert window.sort_button.geometry().right() < window.direction_button.x()
    assert window.direction_button.geometry().right() < window.settings_button.x()
    page_top = page.mapTo(window, QPoint(0, 0)).y()
    assert page_top > window.folder_toolbar_host.mapTo(window, QPoint(0, window.folder_toolbar_host.height())).y()
    assert window.tabs.strip.mapTo(window, QPoint()).y() == page.thumbs.mapTo(window, QPoint()).y() + 4
    assert window.tabs.strip.height() == 28
    assert window.open_button.y() == 0
    assert window.open_button.x() == 0
    assert window.open_button.height() == 28
    assert page.image.toolbar_widget.height() == 28
    assert page.image.save_button.height() == 28
    assert page.thumbs.drag_handle.height() == 28


@pytest.mark.parametrize("orientation", [Qt.Orientation.Horizontal, Qt.Orientation.Vertical])
def test_folder_toolbar_stays_full_width_when_thumbnail_pane_shrinks(browser, orientation):
    window, folders = browser
    page = window.open_folder(folders[0])
    window.resize(1100, 780)
    window.set_orientation(orientation)
    wait_until(lambda: not page._layout_pending)
    page.split.setSizes([100, 900])
    QTest.qWait(100)
    assert (page.thumbs.width() if orientation == Qt.Orientation.Horizontal else page.thumbs.height()) < 200
    assert window.folder_toolbar_host.width() == window.centralWidget().width() - 16
    assert window.folder_toolbar.width() == window.folder_toolbar_host.width() - 20
    assert window.open_button.isVisible() and window.direction_button.isVisible()
    assert page.image.toolbar_widget.parentWidget() is page.image
    assert window.tabs.strip.parentWidget() is page.thumbs.tab_slot
    assert page.thumbs.header_widget.parentWidget() is page.thumbs


def test_many_tabs_scroll_without_continuing_to_hide_tools(browser):
    window, folders = browser
    window.resize(650, 500)
    for _ in range(3): window.open_folder(folders[0])
    wait_until(lambda: window.tabs.count() == 3 and current_tab_visible(window))
    window.toolbar_overflow.update()
    controls = visible_controls(window)
    assert window.open_button in controls and window.direction_button in controls
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
            assert not window.open_button.isHidden() or window.open_button in window.toolbar_overflow.overflowed
            assert not window.direction_button.isHidden() or window.direction_button in window.toolbar_overflow.overflowed
        if width == 260:
            assert window.settings_button.isVisible() or window.toolbar_overflow.more_button.isVisible()
            assert window.tabs.strip.width() >= 180
    page = window.current_tab()
    window.tabs.bar.moveTab(window.tabs.currentIndex(), 0)
    assert window.current_tab() is page
    wait_until(lambda: current_tab_visible(window))
