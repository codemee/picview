from test_tabs import browser, wait_until

from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview import qt_app
from picview.qt_app import COMPARISON_IMAGE_MIME, COMPARISON_TAB_MIME


def comparison_mime(page, image=None):
    mime = QMimeData()
    mime.setData(COMPARISON_TAB_MIME, str(id(page)).encode("ascii"))
    if image is not None:
        mime.setData(COMPARISON_IMAGE_MIME, str(image).encode("utf-8"))
    return mime


def add(window, source, target=None, image=None):
    target = target or window.current_tab()
    assert window.add_comparison_drop(target.image, comparison_mime(source, image))


def test_drag_sources_keep_the_original_image_as_target(browser, monkeypatch):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    tab_drags = []
    monkeypatch.setattr(qt_app, "start_tab_comparison_drag", lambda widget, page: tab_drags.append(page))
    bar = window.tabs.bar
    start = bar.tabRect(window.tabs.indexOf(first)).center()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
    assert window.current_tab() is second
    assert second.image.isVisible()
    QTest.mouseMove(bar, QPoint(start.x(), bar.height() + 20))
    assert window.current_tab() is second
    assert tab_drags == [first]
    # Real QDrag consumes the release; the tab bar must already be ready to switch.
    assert not bar._comparison_dragged
    window.tabs.setCurrentWidget(first)
    assert window.current_tab() is first
    window.tabs.setCurrentWidget(second)
    assert window.current_tab() is second
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(start.x(), bar.height() + 20))

    drags = []

    class CapturedDrag:
        def __init__(self, parent): self.mime = None
        def setMimeData(self, mime): self.mime = mime
        def setPixmap(self, pixmap): pass
        def setHotSpot(self, point): pass
        def exec(self, *args): drags.append(self.mime)

    monkeypatch.setattr(qt_app, "QDrag", CapturedDrag)
    tile = second.thumbs.buttons[second.files[1]]
    selected = second.image.path
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    QTest.mouseMove(tile, QPoint(60, 60))
    QTest.mouseRelease(tile, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
    assert len(drags) == 1
    assert window.comparison_drag_source(drags[0]) == (second, second.files[1])
    assert second.image.path == selected

    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
    assert window.current_tab() is second
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=start)
    assert window.current_tab() is first


def test_reordering_a_tab_does_not_switch_the_displayed_folder(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    window.open_folder(folders[1])
    current = window.open_folder(folders[0])
    bar = window.tabs.bar
    start = bar.tabRect(window.tabs.indexOf(first)).center()
    end = bar.tabRect(1).center()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
    assert window.current_tab() is current
    QTest.mouseMove(bar, QPoint(start.x() + 60, start.y()))
    assert window.current_tab() is current
    QTest.mouseMove(bar, end)
    assert window.current_tab() is current
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=end)
    assert window.current_tab() is current
    assert window.tabs.indexOf(first) != 0


def test_drop_on_image_starts_comparison_and_close_button_restores_view(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    mime = comparison_mime(first)
    viewport = second.image.scroll.viewport()
    enter = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewport, enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted()
    assert window.compare_enabled
    assert window.comparison_area.pages == [second, first]
    assert first.image.comparison_close.isVisible()
    assert second.image.comparison_close.isVisible()
    first.thumbs.select(first.files[1])
    first.image.rotate()
    assert first.image.path == first.files[1] and second.image.rotation == 0
    first.image.comparison_close.click()
    assert not window.compare_enabled
    assert first.image.parentWidget() is first.image_slot
    assert second.image.parentWidget() is second.image_slot
    assert first.image.rotation == 90


def test_repeated_thumbnail_drop_creates_independent_tabs_until_too_small(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    original = first.image.path
    add(window, first, image=first.files[1])
    second = window.comparison_area.pages[1]
    assert second is not first and second.folder == first.folder
    assert first.image.path == original
    assert second.image.path == first.files[1]
    add(window, first, image=first.files[0])
    assert len(window.comparison_area.pages) == 3
    assert window.comparison_area.pages[-1].image.path == first.files[0]
    count = 3
    while window.can_add_comparison(first.image):
        add(window, first)
        count += 1
        assert count < 12
    assert not window.add_comparison_drop(first.image, comparison_mime(first))
    assert len(window.comparison_area.pages) == count
    assert window.notification_bar.currentMessage() == window.t["compare_too_small"]


def test_sync_button_applies_image_tools_only_when_enabled(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    assert second.image.sync_button.isEnabled()
    second.image.rotate_b.click()
    assert second.image.rotation == 90 and first.image.rotation == 0
    second.image.sync_button.click()
    assert window.sync_enabled and first.image.sync_button.isChecked()
    second.image.rotate_b.click()
    second.image.mh.click()
    second.image.mv.click()
    assert first.image.rotation == 90 and second.image.rotation == 180
    assert first.image.fh and first.image.fv and second.image.fh and second.image.fv
    second.image.slider.setValue(1500)
    assert first.image.zoom == second.image.zoom == 1.5
    second.image.fit_b.click()
    assert first.image.fit_to_pane and second.image.fit_to_pane
    second.image.choose_background("black")
    assert first.image.background_mode == second.image.background_mode == "black"
    first.image.sync_button.click()
    assert not window.sync_enabled
    second.image.rotate_b.click()
    assert first.image.rotation == 90 and second.image.rotation == 270


def test_sync_button_scrolls_comparison_panes_proportionally(browser):
    window, folders = browser
    window.resize(700, 500)
    Image.new("RGB", (900, 700), "red").save(folders[0] / "image0.png")
    Image.new("RGB", (1300, 1100), "blue").save(folders[1] / "image0.png")
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    for page in (first, second): page.image.set_zoom_percent(1000)
    QTest.qWait(100)
    first_x = first.image.scroll.horizontalScrollBar()
    first_y = first.image.scroll.verticalScrollBar()
    second_x = second.image.scroll.horizontalScrollBar()
    second_y = second.image.scroll.verticalScrollBar()
    assert all(bar.maximum() > 0 for bar in (first_x, first_y, second_x, second_y))
    second.image.sync_button.click()
    first_x.setValue(first_x.maximum() // 3)
    first_y.setValue(first_y.maximum() * 2 // 3)
    assert abs(second_x.value() / second_x.maximum() - first_x.value() / first_x.maximum()) < .01
    assert abs(second_y.value() / second_y.maximum() - first_y.value() / first_y.maximum()) < .01
    second_x.setValue(second_x.maximum())
    second_y.setValue(0)
    assert first_x.value() == first_x.maximum()
    assert first_y.value() == 0
    wheel = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.ScrollUpdate, False)
    QApplication.sendEvent(first.image.scroll.viewport(), wheel)
    assert first_y.value() > 0
    assert second_y.value() > 0
    second.image.sync_button.click()
    previous = second_x.value()
    first_x.setValue(0)
    assert second_x.value() == previous


def test_image_navigation_keys_follow_the_selected_comparison_pane(browser):
    window, folders = browser
    for index in range(2, 18):
        Image.new("RGB", (40, 30), "blue").save(folders[0] / f"image{index}.png")
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    assert window.current_tab() is second
    host_at_switch = []
    window.tabs.stack.currentChanged.connect(lambda *_: host_at_switch.append(
        (window.comparison_area.parentWidget() is window.tabs.stack.currentWidget().image_slot,
         not window.tabs.updatesEnabled())))
    QTest.mouseClick(first.image.label, Qt.MouseButton.LeftButton)
    wait_until(lambda: window.current_tab() is first)
    assert host_at_switch == [(True, True)]
    assert window.tabs.strip.parentWidget() is first.thumbs.tab_slot
    assert first.image.comparison_selected
    assert window.comparison_area.pages == [second, first]
    QTest.mouseClick(second.image.scroll.viewport(), Qt.MouseButton.LeftButton)
    wait_until(lambda: window.current_tab() is second)
    assert host_at_switch == [(True, True), (True, True)]
    assert window.tabs.strip.parentWidget() is second.thumbs.tab_slot
    QTest.mouseClick(first.image.scroll.viewport(), Qt.MouseButton.LeftButton)
    wait_until(lambda: window.current_tab() is first)
    window.tabs.setCurrentWidget(second)
    assert second.image.comparison_selected
    window.tabs.setCurrentWidget(first)
    assert first.image.comparison_selected
    QTest.keyClick(window, Qt.Key.Key_Right)
    assert first.image.path == first.files[1]
    assert second.image.path == second.files[0]
    QTest.keyClick(window, Qt.Key.Key_End)
    assert first.image.path == first.files[-1]
    QTest.keyClick(window, Qt.Key.Key_Home)
    assert first.image.path == first.files[0]
    QTest.keyClick(window, Qt.Key.Key_Space)
    assert first.image.path == first.files[1]
    QTest.keyClick(window, Qt.Key.Key_Backspace)
    assert first.image.path == first.files[0]
    first.thumbs.select(first.files[1])
    first.thumbs.scroll.setFocus()
    QTest.keyClick(first.thumbs.scroll, Qt.Key.Key_Down)
    assert first.image.path == first.files[1 + first.thumbs.columns]
    assert second.image.path == second.files[0]
    QTest.keyClick(first.thumbs.scroll, Qt.Key.Key_Up)
    assert first.image.path == first.files[1]
    QTest.keyClick(window, Qt.Key.Key_PageDown)
    assert first.image.path == first.files[2]
    QTest.keyClick(window, Qt.Key.Key_PageUp)
    assert first.image.path == first.files[1]


def test_comparison_order_layout_shared_toolbar_and_close_one(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    third = window.duplicate_page(first, activate=False, add_to_compare=False)
    add(window, third, second)
    assert window.comparison_area.pages == [second, first, third]
    for orientation in (Qt.Orientation.Horizontal, Qt.Orientation.Vertical):
        window.set_orientation(orientation)
        QTest.qWait(100)
        expected = Qt.Orientation.Vertical if orientation == Qt.Orientation.Horizontal else Qt.Orientation.Horizontal
        assert window.comparison_area.split.orientation() == expected
        sizes = window.comparison_area.split.sizes()
        assert max(sizes) - min(sizes) <= 1
    window.tabs.bar.moveTab(window.tabs.indexOf(third), 0)
    assert window.comparison_area.pages == [second, first, third]
    QTest.mouseClick(first.image.scroll.viewport(), Qt.MouseButton.LeftButton)
    assert window.comparison_area.toolbar_image is first.image
    first.image.max_button.click()
    assert first.image.isVisible() and not second.image.isVisible()
    first.image.max_button.click()
    third.image.comparison_close.click()
    assert window.comparison_area.pages == [second, first]
    window.toggle_theme()
    window.toggle_lang()
    assert QKeySequence("Alt+C").toString(QKeySequence.SequenceFormat.NativeText) in first.image.rotate_b.toolTip()


def test_compared_image_updates_and_deletion(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    path = first.image.path
    Image.new("RGB", (180, 90), "blue").save(path)
    wait_until(lambda: first.image.frames[0][0].size == (180, 90))
    wait_until(lambda: first.thumbs.buttons[path].preview.pixmap().toImage().pixelColor(0, 0).name() == "#0000ff")
    path.unlink()
    wait_until(lambda: first.image.path == first.files[0] and first.image.path != path)
    assert first.pending_notification
    assert second.image.path == second.files[0]
