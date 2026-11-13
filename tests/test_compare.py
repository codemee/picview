from test_tabs import browser, wait_until

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QMouseEvent, QWheelEvent
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


def test_comparison_panes_reorder_and_end_from_shared_toolbar(browser):
    window, folders = browser
    third_folder = folders[0].parent / "three"
    third_folder.mkdir()
    Image.new("RGB", (40, 30), "green").save(third_folder / "third.png")
    first, second, third = (window.open_folder(folder) for folder in (*folders, third_folder))
    add(window, first, second)
    add(window, third, second)
    assert window.comparison_order == [second, first, third]
    mime = QMimeData()
    mime.setData(qt_app.COMPARISON_REORDER_MIME, str(id(third)).encode("ascii"))
    target = second.image
    event = QDropEvent(QPointF(target.width() / 4, target.height() / 2),
                       Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    assert target.handle_comparison_drag(event, target)
    assert window.comparison_order == window.comparison_area.pages == [third, second, first]
    assert window.focused_compare_page is second
    assert second.image.end_compare_button.isVisible()
    second.image.end_compare_button.click()
    assert not window.compare_enabled
    assert window.current_tab() is first


def test_comparison_toolbar_names_mode_and_exit_restores_filename(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    for page in window.comparison_order:
        assert page.image.filename_label.text() == window.t["compare_mode"]
        assert page.image.path.name in page.image.comparison_label.text()
    window.focus_compare_page(first)
    wait_until(lambda: window.current_tab() is first)
    assert window.comparison_area.toolbar_image.filename_label.text() == window.t["compare_mode"]
    window.set_compare(False)
    for page in (first, second):
        assert page.image.filename_label.text() == page.image.path.name


def test_comparison_focus_border_follows_input_pane(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    second.thumbs.scroll.setFocus()
    wait_until(lambda: bool(second.thumbs.property("inputFocused")))
    assert not window.comparison_area.property("inputFocused")
    window.focus_compare_page(first)
    wait_until(lambda: bool(window.comparison_area.property("inputFocused")))
    assert first.image.property("inputFocused")
    assert not any(page.thumbs.property("inputFocused") for page in window.pages())
    assert window.comparison_area.toolbar_image is first.image
    assert window.comparison_area.isVisible()
    assert window.tabs.updatesEnabled()


def test_switching_fitted_comparison_image_keeps_scrollbar_policy(browser):
    window, folders = browser
    for index in range(2):
        Image.new("RGB", (1600, 1200), "blue").save(folders[0] / f"large{index}.png")
    first = window.open_folder(folders[0], folders[0] / "large0.png")
    second = window.open_folder(folders[1])
    add(window, first, second)
    window.focus_compare_page(first)
    wait_until(lambda: first.image.fit_to_pane)
    QTest.qWait(100)  # Settle the initial comparison layout and resize renders.
    fit_changes = []
    first.image.fit_b.toggled.connect(fit_changes.append)
    other_pixmap = second.image.label.pixmap().cacheKey()
    first.thumbs.select(folders[0] / "large1.png")
    QTest.qWait(30)
    assert first.image.path == folders[0] / "large1.png"
    assert first.image.fit_to_pane
    assert fit_changes == []
    assert first.image.scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert first.image.scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert second.image.label.pixmap().cacheKey() == other_pixmap


def test_thumbnail_drop_on_another_tab_copies_without_overwriting(browser):
    window, folders = browser
    source = window.open_folder(folders[0])
    target = window.open_folder(folders[1])
    image = source.files[0]
    original = target.folder / image.name
    before = original.read_bytes()
    mime = comparison_mime(source, image)
    window.resolve_transfer_conflict = lambda _destination: "keep_both"
    bar = window.tabs.bar
    event = QDropEvent(QPointF(bar.tabRect(window.tabs.indexOf(target)).center()),
                       Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    bar.dropEvent(event)
    copied = target.folder / f"{image.stem} (2){image.suffix}"
    assert event.isAccepted()
    assert copied.read_bytes() == image.read_bytes()
    assert original.read_bytes() == before
    assert target.thumbs.selected_path == copied


def test_multiple_thumbnails_move_to_another_tab(browser):
    window, folders = browser
    source = window.open_folder(folders[0])
    target = window.open_folder(folders[1])
    for path in target.files: path.unlink()
    target.refresh_folder()
    source.thumbs.select_all()
    original_paths = source.files.copy()
    mime = comparison_mime(source, source.files[0])
    mime.setData(qt_app.THUMBNAIL_FILES_MIME,
                 __import__("json").dumps([str(path) for path in original_paths]).encode("utf-8"))
    assert window.transfer_thumbnails_to_tab(mime, target, Qt.DropAction.MoveAction)
    assert all(not path.exists() for path in original_paths)
    assert len(target.files) == 2
    assert target.thumbs.selected_path == target.files[-1]


def test_name_conflict_requires_choice_before_move(browser):
    window, folders = browser
    source = window.open_folder(folders[0])
    target = window.open_folder(folders[1])
    image = source.files[0]
    destination = target.folder / image.name
    image.write_bytes(b"replacement")
    destination.write_bytes(b"original")
    mime = comparison_mime(source, image)
    window.resolve_transfer_conflict = lambda _destination: "skip"
    assert window.transfer_thumbnails_to_tab(mime, target, Qt.DropAction.MoveAction)
    assert image.read_bytes() == b"replacement"
    assert destination.read_bytes() == b"original"
    window.resolve_transfer_conflict = lambda _destination: "replace"
    assert window.transfer_thumbnails_to_tab(mime, target, Qt.DropAction.MoveAction)
    assert not image.exists()
    assert destination.read_bytes() == b"replacement"


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
    assert not window.compare_enabled  # Native drop returns before image loading.
    wait_until(lambda: window.compare_enabled)
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


def test_loading_overlay_animates_while_background_decode_waits(browser, monkeypatch):
    import threading
    window, folders = browser
    source = window.open_folder(folders[0])
    target = window.open_folder(folders[1])
    original = qt_app.ImagePane.read_frames
    release = threading.Event()

    def slow_decode(path):
        release.wait(2)
        return original(path)

    monkeypatch.setattr(qt_app.ImagePane, "read_frames", staticmethod(slow_decode))
    window.queue_comparison_drop(target.image, comparison_mime(source, source.files[0]))
    overlay = window.findChild(qt_app.ComparisonLoadingOverlay)
    assert overlay.isVisible()
    initial = overlay.angle
    try:
        wait_until(lambda: overlay.angle != initial)
        assert not window.compare_enabled
    finally:
        release.set()
    wait_until(lambda: window.compare_enabled)


def test_repeated_thumbnail_drop_keeps_one_visible_folder_tab_until_too_small(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    original = first.image.path
    visible_before = sum(window.tabs.bar.isTabVisible(i) for i in range(window.tabs.count()))
    add(window, first, image=first.files[1])
    second = window.comparison_area.pages[1]
    assert second is not first and second.folder == first.folder
    assert first.image.path == original
    assert second.image.path == first.files[1]
    assert sum(window.tabs.bar.isTabVisible(i) for i in range(window.tabs.count())) == visible_before
    window.focus_compare_page(second)
    QApplication.processEvents()
    assert window.tabs.bar.display_current_index == window.tabs.indexOf(first)
    assert window.current_tab().thumbs.selected_path == first.files[1]
    add(window, first, image=first.files[0])
    assert len(window.comparison_area.pages) == 3
    assert window.comparison_area.pages[-1].image.path == first.files[0]
    assert sum(window.tabs.bar.isTabVisible(i) for i in range(window.tabs.count())) == visible_before
    count = 3
    while window.can_add_comparison(first.image):
        add(window, first)
        count += 1
        assert count < 12
    assert not window.add_comparison_drop(first.image, comparison_mime(first))
    assert len(window.comparison_area.pages) == count
    assert window.notification_bar.currentMessage() == window.t["compare_too_small"]


def test_multiple_thumbnail_drop_compares_each_image_without_visible_tabs(browser):
    import json

    window, folders = browser
    window.resize(1400, 900)
    QApplication.processEvents()
    source = window.open_folder(folders[0])
    target = window.open_folder(folders[1])
    visible_before = sum(window.tabs.bar.isTabVisible(i) for i in range(window.tabs.count()))
    mime = comparison_mime(source, source.files[0])
    mime.setData(qt_app.THUMBNAIL_FILES_MIME,
                 json.dumps([str(path) for path in source.files]).encode("utf-8"))
    assert window.add_comparison_drop(target.image, mime)
    assert [page.image.path for page in window.comparison_order] == [target.image.path, *source.files]
    assert sum(window.tabs.bar.isTabVisible(i) for i in range(window.tabs.count())) == visible_before
    assert all(path.exists() for path in source.files)
    transient = window.comparison_order[-1]
    window.focus_compare_page(transient)
    QApplication.processEvents()
    assert window.navigation_page() is transient
    window.remove_comparison_page(transient)
    assert transient not in window.pages()
    assert sum(window.tabs.bar.isTabVisible(i) for i in range(window.tabs.count())) == visible_before
    window.set_compare(False)
    assert window.tabs.count() == visible_before


def test_closing_comparison_panes_keeps_last_image_selected_in_thumbnails(browser):
    window, folders = browser
    source = window.open_folder(folders[0])
    first, second = source.files[:2]
    assert source.thumbs.selected_path == first
    add(window, source, image=second)
    last_page = window.comparison_order[-1]
    assert last_page.thumbs.selected_path == second
    assert not window.tabs.bar.isTabVisible(window.tabs.indexOf(last_page))
    window.remove_comparison_page(source)
    assert not window.compare_enabled
    assert window.current_tab() is source
    assert source.thumbs.selected_path == second
    assert source.thumbs.selected_paths == {second}
    assert source.image.path == second
    assert window.tabs.count() == 1


def test_multiple_drop_skips_image_already_in_comparison(browser):
    import json
    window, folders = browser
    source = window.open_folder(folders[0])
    paths = source.files.copy()
    mime = comparison_mime(source, paths[0])
    mime.setData(qt_app.THUMBNAIL_FILES_MIME, json.dumps([str(p) for p in paths]).encode())
    assert window.add_comparison_drop(source.image, mime)
    assert [page.image.path for page in window.comparison_order] == paths


def test_drag_hover_activates_folder_tab(browser):
    from PySide6.QtGui import QDragMoveEvent
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    bar = window.tabs.bar
    mime = comparison_mime(second, second.files[0])
    event = QDragMoveEvent(bar.tabRect(window.tabs.indexOf(first)).center(),
                           Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
    bar.dragMoveEvent(event)
    wait_until(lambda: window.current_tab() is first)


def test_drop_into_thumbnail_area_moves_files_without_new_tabs(browser):
    window, folders = browser
    source = window.open_folder(folders[0])
    target = window.open_folder(folders[1])
    image = source.files[0]
    destination = target.folder / image.name
    destination.unlink()
    mime = comparison_mime(source, image)
    mime.setData(qt_app.THUMBNAIL_FILES_MIME, b"[]")
    mime.setData(qt_app.THUMBNAIL_FILES_MIME, __import__("json").dumps([str(image)]).encode())
    event = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
                       mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    assert target.thumbs.eventFilter(target.thumbs.grid_host, event)
    assert event.dropAction() == Qt.DropAction.MoveAction
    assert not image.exists() and destination.exists()
    assert window.tabs.count() == 2


def test_close_focused_comparison_aligns_thumbnail_tab_with_remaining_image(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    add(window, first, second, first.files[1])
    transient = window.comparison_order[-1]
    window.focus_compare_page(transient)
    wait_until(lambda: window.current_tab() is transient)
    window.remove_comparison_page(transient)
    wait_until(lambda: window.current_tab() is window.navigation_page())
    assert window.current_tab().image.comparison_selected


def test_drag_hover_scroll_arrow_repeats_until_pointer_leaves(browser):
    from PySide6.QtWidgets import QToolButton
    window, _ = browser
    bar = qt_app.FolderTabBar()
    for index in range(15): bar.addTab(f"Folder {index}")
    bar.resize(300, 34)
    bar.show()
    QApplication.processEvents()
    button = next(button for button in bar.findChildren(QToolButton)
                  if button.objectName().startswith("Scroll") and button.isEnabled())
    mime = QMimeData()
    mime.setData(qt_app.THUMBNAIL_FILES_MIME, b"[]")
    enter = QDragEnterEvent(button.rect().center(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(button, enter)
    assert enter.isAccepted()
    assert bar.drag_scroll_timer.isActive()
    QApplication.sendEvent(button, QEvent(QEvent.Type.DragLeave))
    assert not bar.drag_scroll_timer.isActive()
    bar.close()


def test_closing_three_same_folder_comparison_images_keeps_survivor(browser):
    window, folders = browser
    third = folders[0] / "third.png"
    Image.new("RGB", (40, 30), "green").save(third)
    source = window.open_folder(folders[0])
    second = source.files[1]
    add(window, source, image=second)
    middle = window.comparison_order[-1]
    add(window, source, image=third)
    window.remove_comparison_page(source)
    assert window.compare_enabled
    window.remove_comparison_page(middle)
    assert not window.compare_enabled
    assert window.current_tab() is source
    assert source.image.path == third
    assert source.thumbs.selected_paths == {third}
    assert window.tabs.count() == 1


def test_comparison_drag_preview_pushes_panes_and_restores_on_leave(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    split = window.comparison_area.split
    assert [split.widget(i) for i in range(split.count())] == [second.image, first.image]
    window.preview_comparison_reorder(first, second, False)
    assert [split.widget(i) for i in range(split.count())] == [first.image, second.image]
    window.restore_comparison_order()
    assert [split.widget(i) for i in range(split.count())] == [second.image, first.image]
    assert window.reorder_comparison_page(first, second, False)
    assert window.comparison_order == [first, second]


@pytest.mark.parametrize("drag_area", ["comparison_label", "label", "viewport"])
def test_dragging_comparison_header_reorders_with_live_preview(browser, drag_area):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    label = (first.image.scroll.viewport() if drag_area == "viewport"
             else getattr(first.image, drag_area))
    start = label.rect().center()
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    QApplication.processEvents()
    assert window.current_tab() is second
    target = second.image
    horizontal = window.comparison_area.split.orientation() == Qt.Orientation.Horizontal
    target_point = QPoint(target.width() // 4, target.height() // 2) if horizontal else QPoint(target.width() // 2, target.height() // 4)
    global_end = target.mapToGlobal(target_point)
    end = label.mapFromGlobal(global_end)
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(end), QPointF(global_end),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(label, move)
    assert [window.comparison_area.split.widget(i) for i in range(2)] == [first.image, second.image]
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(end), QPointF(global_end),
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                          Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(label, release)
    assert window.comparison_order == [first, second]


def test_clicking_other_comparison_image_focuses_after_release(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    QTest.mousePress(first.image.label, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert window.current_tab() is second
    QTest.mouseRelease(first.image.label, Qt.MouseButton.LeftButton)
    wait_until(lambda: window.current_tab() is first)


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


@pytest.mark.parametrize("selected_index", [0, 1])
@pytest.mark.parametrize("ticks", [1000, 1750, 6500])
def test_enabling_sync_uses_selected_images_current_zoom(browser, selected_index, ticks):
    window, folders = browser
    pages = [window.open_folder(folder) for folder in folders]
    add(window, *pages)
    source = pages[selected_index]
    target = pages[1 - selected_index]
    target.image.slider.setValue(800)
    source.image.slider.setMaximum(max(4000, ticks))
    source.image.slider.setValue(ticks)
    window.focus_compare_page(source)
    window.set_sync(True)
    assert source.image.zoom == target.image.zoom == ticks / 1000
    assert source.image.slider.value() == target.image.slider.value() == ticks
    window.set_sync(False)
    target.image.slider.setValue(900)
    assert source.image.zoom == ticks / 1000


def test_enabling_sync_copies_selected_images_fitted_scale(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    window.focus_compare_page(first)
    first.image.fit_b.setChecked(True)
    first.image.render()
    ticks = first.image.slider.value()
    window.set_sync(True)
    assert first.image.zoom == second.image.zoom == ticks / 1000
    assert first.image.slider.value() == second.image.slider.value() == ticks


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
    assert first.image.isVisible() and second.image.isVisible()
    third.image.comparison_close.click()
    assert window.comparison_area.pages == [second, first]
    window.toggle_theme()
    window.toggle_lang()
    assert QKeySequence("Alt+C").toString(QKeySequence.SequenceFormat.NativeText) in first.image.rotate_b.toolTip()


def test_comparison_switch_keeps_outer_layout_and_exit_keeps_current_layout(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.tabs.setCurrentWidget(first)
    first.dock_pane("image", "left")
    first.split.setSizes([300, 700])
    window.comparison_layout_changed(first)
    add(window, second, first)
    fraction = first.layout_spec()[2]
    QTest.mouseClick(second.image.scroll.viewport(), Qt.MouseButton.LeftButton)
    wait_until(lambda: window.current_tab() is second)
    assert second.split.orientation() == Qt.Orientation.Horizontal
    assert second.split.widget(0) is second.image_slot
    assert abs(second.layout_spec()[2] - fraction) < .03
    assert window.comparison_area.split.orientation() == Qt.Orientation.Vertical
    window.set_compare(False)
    assert window.current_tab() is second
    assert second.split.orientation() == Qt.Orientation.Horizontal
    assert second.split.widget(0) is second.image_slot
    assert abs(second.layout_spec()[2] - fraction) < .03
    window.tabs.setCurrentWidget(first)
    assert first.split.orientation() == Qt.Orientation.Horizontal
    assert first.split.widget(0) is first.image_slot


def test_switching_tabs_during_comparison_keeps_shared_layout(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    third = window.duplicate_page(second)
    window.tabs.setCurrentWidget(first)
    first.dock_pane("image", "left")
    second.dock_pane("thumb", "top")
    third.dock_pane("image", "bottom")
    first.split.setSizes([300, 700])
    second.split.setSizes([700, 300])
    window.tabs.setCurrentWidget(first)
    add(window, second, first)
    expected = first.layout_spec()
    for page in (second, third, first, second, third, first):
        window.tabs.setCurrentWidget(page)
        QTest.qWait(30)
        assert page.split.orientation() == expected[0]
        assert (page.split.widget(0) is page.thumbs) == expected[1]
        assert abs(page.layout_spec()[2] - expected[2]) < .03
        assert window._compare_layout[0:2] == expected[0:2]
        assert abs(window._compare_layout[2] - expected[2]) < .03


def test_fullscreen_comparison_follows_screen_aspect_ratio(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    second.image.open_full()
    full = window.compare_full_window
    assert full is not None and full.isFullScreen()
    assert full.pages == [second, first]
    full.setWindowState(Qt.WindowState.WindowNoState)
    full.resize(800, 400)
    wait_until(lambda: full.split.orientation() == Qt.Orientation.Horizontal)
    full.resize(400, 800)
    wait_until(lambda: full.split.orientation() == Qt.Orientation.Vertical)
    for page in (first, second):
        label = full.labels[page]
        assert not label.pixmap().isNull()
        assert label.pixmap().deviceIndependentSize().width() <= page.image.image_size()[0]
        assert label.pixmap().deviceIndependentSize().height() <= page.image.image_size()[1]
    QTest.keyClick(full, Qt.Key.Key_Escape)
    assert window.compare_full_window is None and window.compare_enabled


def test_fullscreen_comparison_toolbar_targets_chosen_image(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    second.image.open_full()
    full = window.compare_full_window
    toolbar = full.image_toolbar
    assert toolbar.isVisible() and not hasattr(toolbar, "folder_choice")
    QTest.mouseClick(full.scrollers[first].viewport(), Qt.MouseButton.LeftButton)
    assert toolbar.page is first
    QTest.mouseClick(toolbar.rotate_button, Qt.MouseButton.LeftButton)
    assert first.image.rotation == 90 and second.image.rotation == 0
    toolbar.set_zoom(1500)
    assert first.image.fullscreen_zoom == 1.5
    assert full.labels[first].pixmap().deviceIndependentSize().width() > first.image.image_size()[0]
    assert second.image.fullscreen_zoom is None
    QTest.mouseClick(toolbar.sync_button, Qt.MouseButton.LeftButton)
    assert first.image.fullscreen_zoom == second.image.fullscreen_zoom == 1.5
    toolbar.set_zoom(1800)
    assert first.image.fullscreen_zoom == second.image.fullscreen_zoom == 1.8
    QTest.mouseClick(toolbar.fit_button, Qt.MouseButton.LeftButton)
    assert first.image.fullscreen_zoom is None and second.image.fullscreen_zoom is None
    QTest.keyClick(full, Qt.Key.Key_Escape)
    assert window.compare_full_window is None


def test_fullscreen_comparison_marks_the_active_image(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    second.image.open_full()
    full = window.compare_full_window
    active = full.image_toolbar.page
    assert window.focused_compare_page is active
    other = first if active is second else second
    QTest.mouseClick(full.scrollers[other].viewport(), Qt.MouseButton.LeftButton)
    assert full.image_toolbar.page is other
    assert qt_app.PALETTE["accent"] in full.frames[other].styleSheet()
    assert "transparent" in full.frames[active].styleSheet()
    assert full.centralWidget().layout().contentsMargins().left() == 16
    assert full.centralWidget().layout().contentsMargins().top() == 16
    assert full.split.handleWidth() == 12
    QTest.mouseClick(full.scrollers[active].viewport(), Qt.MouseButton.LeftButton)
    assert full.image_toolbar.page is active
    assert "transparent" not in full.frames[active].styleSheet()
    assert "transparent" in full.frames[other].styleSheet()
    QTest.keyClick(full, Qt.Key.Key_Tab)
    assert full.image_toolbar.page is other
    QTest.keyClick(full, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert full.image_toolbar.page is active


def test_leaving_comparison_activates_last_compared_folder_with_current_layout(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    second.dock_pane("image", "right")
    add(window, first, second)
    assert window.comparison_order == [second, first]
    expected = second.layout_spec()
    window.set_compare(False)
    assert window.current_tab() is first
    assert first.layout_spec()[0:2] == expected[0:2]
    assert abs(first.layout_spec()[2] - expected[2]) < .03


def test_tab_and_shift_tab_cycle_compared_panes(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    add(window, first, second)
    assert window.focused_compare_page is second
    QTest.keyClick(second.image.scroll.viewport(), Qt.Key.Key_Tab)
    wait_until(lambda: window.focused_compare_page is first and window.current_tab() is first)
    QTest.keyClick(first.image.scroll.viewport(), Qt.Key.Key_Tab)
    wait_until(lambda: window.focused_compare_page is second and window.current_tab() is second)
    QTest.keyClick(second.image.scroll.viewport(), Qt.Key.Key_Backtab)
    wait_until(lambda: window.focused_compare_page is first and window.current_tab() is first)
    window.set_compare(False)
    assert all(not shortcut.isEnabled() for shortcut in window.compare_tab_shortcuts)


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
