import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QEventLoop, QMimeData, QPoint, QTimer, QUrl, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QTabBar

from picview.qt_app import FolderTab, PicView
from picview.settings import load_settings, save_settings


def wait_until(condition):
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        # A real event loop releases the GIL for background Python decoders.
        loop = QEventLoop()
        QTimer.singleShot(25, loop.quit)
        loop.exec()
    assert condition()


@pytest.fixture
def browser(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folders = [tmp_path / name for name in ("one", "two")]
    for folder in folders:
        folder.mkdir()
        for index in range(2):
            Image.new("RGB", (120, 80), "red").save(folder / f"image{index}.png")
    app = QApplication.instance() or QApplication([])
    window = PicView()
    window.show()
    window.activateWindow()
    QTest.qWait(50)
    yield window, folders
    window.close()
    window.deleteLater()
    app.processEvents()


def test_new_tabs_allow_duplicate_folders(browser):
    window, folders = browser
    assert window.tabs.count() == 1 and window.folder is None
    first = window.open_folder(folders[0])
    assert isinstance(first, FolderTab)
    assert window.tabs.count() == 1
    first.image.rotate()
    second = window.open_folder(folders[1])
    assert window.tabs.count() == 2 and window.current_tab() is second
    third = window.open_folder(folders[0] / ".")
    assert third is not first and third.folder == first.folder
    assert window.tabs.count() == 3 and first.image.rotation == 90
    assert third.image.rotation == 0
    assert window.tabs.tabText(0) != window.tabs.tabText(2)


def test_folder_dialog_cancel_does_not_create_tab(browser, monkeypatch):
    window, folders = browser
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: "")
    window.add_tab_button.click()
    assert window.tabs.count() == 1 and window.folder is None


def test_each_tab_keeps_its_own_view_and_global_styles(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    QTest.qWait(50)
    first.thumbs.select(first.files[1])
    first.thumbs.slider.setValue(180)
    first.image.slider.setValue(1500)
    first.image.rotate()
    first.image.mirror_h()
    first.set_orientation(Qt.Orientation.Horizontal)
    frames = first.image.frames
    second = window.open_folder(folders[1])
    QTest.qWait(50)
    second.image.slider.setValue(800)
    assert second.thumbs.size == 140
    assert second.split.orientation() == Qt.Orientation.Vertical
    window.toggle_theme()
    window.toggle_lang()
    assert first.image.frames is frames
    assert first.image.rotation == 90 and first.image.fh
    assert first.thumbs.size == 180 and first.image.slider.value() == 1500
    assert second.image.slider.value() == 800
    assert first.t is window.t and second.t is window.t
    window.tabs.setCurrentWidget(first)
    assert first.thumbs.selected_path == first.files[1]
    assert first.split.orientation() == Qt.Orientation.Horizontal
    assert first.image.frames is frames


def test_background_modification_is_loaded_on_activation(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    original_frames = first.image.frames
    first.image.slider.setValue(1500)
    second = window.open_folder(folders[1])
    Image.new("RGB", (120, 80), "blue").save(first.files[0])
    wait_until(lambda: first.thumbs.buttons[first.files[0]].preview.pixmap().toImage().pixelColor(0, 0).name() == "#0000ff")
    assert window.current_tab() is second
    wait_until(lambda: first.image_dirty)
    assert first.image.frames is original_frames
    window.tabs.setCurrentWidget(first)
    assert first.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255)
    assert first.image.slider.value() == 1500


def test_background_delete_marks_tab_without_switching(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    removed, successor = first.files
    second = window.open_folder(folders[1])
    removed.unlink()
    wait_until(lambda: first.thumbs.selected_path == successor)
    assert window.current_tab() is second
    assert first.pending_notification
    assert window.tabs.tabText(window.tabs.indexOf(first)).startswith("● ")
    assert not window.notification_bar.currentMessage()
    window.tabs.setCurrentWidget(first)
    assert first.image.path == successor
    assert removed.name in window.notification_bar.currentMessage()
    assert not first.pending_notification
    assert not window.tabs.tabText(window.tabs.indexOf(first)).startswith("● ")


def test_all_tabs_watch_new_files(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    new_file = folders[0] / "new.png"
    Image.new("RGB", (120, 80), "blue").save(new_file)
    wait_until(lambda: new_file in first.thumbs.buttons)
    assert window.current_tab() is second
    assert first.folder_poll_timer.isActive() and second.folder_poll_timer.isActive()


def test_close_tab_releases_resources_and_last_tab_becomes_empty(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.close_tab(window.tabs.indexOf(first))
    assert first._closing and not first.folder_poll_timer.isActive()
    assert not first.folder_watcher.files() and not first.folder_watcher.directories()
    assert not first.image.frames
    assert window.current_tab() is second
    window.close_tab()
    assert window.tabs.count() == 1 and window.folder is None


def test_animation_pauses_and_fullscreen_closes_on_switch(browser):
    window, folders = browser
    gif = folders[0] / "animated.gif"
    Image.new("RGB", (120, 80), "red").save(gif, save_all=True, append_images=[Image.new("RGB", (120, 80), "blue")], duration=100, loop=0)
    first = window.open_folder(folders[0], gif)
    assert first.image.timer.isActive()
    first.image.open_full()
    second = window.open_folder(folders[1])
    assert not first.image.timer.isActive() and first.image.full_window is None
    assert second.active and not first.active
    window.tabs.setCurrentWidget(first)
    assert first.image.timer.isActive()


def test_tab_shortcuts_route_to_active_page(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    QTest.qWait(50)
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.PreviousChild))
    assert window.current_tab() is first
    QTest.keyClick(window, Qt.Key.Key_Right)
    assert first.thumbs.selected_path == first.files[1]
    assert second.thumbs.selected_path == second.files[0]
    QTest.keySequence(window, QKeySequence(QKeySequence.StandardKey.Close))
    assert window.current_tab() is second and window.tabs.count() == 1


@pytest.mark.parametrize("focus", ["thumbnail", "image", "tab"])
@pytest.mark.parametrize("tab_key", [Qt.Key.Key_Tab, Qt.Key.Key_Backtab])
def test_literal_close_and_previous_tab_shortcuts(browser, focus, tab_key):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    third = window.open_folder(folders[0])

    def focus_target():
        page = window.current_tab()
        target = {"thumbnail": page.thumbs.scroll, "image": page.image.scroll, "tab": window.tabs.tabBar()}[focus]
        target.setFocus()
        QTest.qWait(25)
        return target

    QTest.keyClick(focus_target(), tab_key, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert window.current_tab() is second
    modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
    QTest.keyClick(focus_target(), Qt.Key.Key_W, modifier)
    assert window.tabs.count() == 2
    assert second not in window.pages() and first in window.pages() and third in window.pages()
    QTest.keyClick(focus_target(), Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
    assert window.current_tab() is first


def test_numbered_tab_shortcuts_follow_visual_order(browser):
    window, folders = browser
    pages = [window.open_folder(folders[index % 2]) for index in range(10)]
    modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
    window.tabs.tabBar().moveTab(9, 0)
    window.current_tab().thumbs.scroll.setFocus()
    QTest.qWait(50)
    for number in range(1, 10):
        QTest.keySequence(QApplication.focusWidget(), QKeySequence(f"{modifier}+{number}"))
        expected = window.tabs.widget(window.tabs.count() - 1 if number == 9 else number - 1)
        assert window.current_tab() is expected
    assert window.tabs.widget(0) is pages[9]
    while window.tabs.count() > 2:
        window.close_tab(2)
    QTest.keySequence(window, QKeySequence(f"{modifier}+8"))
    assert window.tabs.currentIndex() == 1


def test_page_tab_shortcuts_wrap_without_changing_images(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    QTest.qWait(50)
    for key, expected in [("Ctrl+PgDown", first), ("Ctrl+PgUp", second)]:
        QTest.keySequence(window, QKeySequence(key))
        assert window.current_tab() is expected
        assert first.thumbs.selected_path == first.files[0]
        assert second.thumbs.selected_path == second.files[0]


def test_reopen_tab_shortcut_restores_state_position_and_last_tab(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    first.thumbs.select(first.files[1])
    first.image.rotate()
    second = window.open_folder(folders[1])
    window.close_tab(0)
    modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
    QTest.qWait(50)
    QTest.keySequence(window, QKeySequence(f"{modifier}+Shift+T"))
    restored = window.current_tab()
    assert restored is not first and restored.folder == folders[0]
    assert restored.thumbs.selected_path == restored.files[1]
    assert restored.image.rotation == 90
    assert window.tabs.widget(0) is restored and window.tabs.widget(1) is second
    window.close_tab(1)
    window.close_tab(0)
    assert window.folder is None
    QTest.keySequence(window, QKeySequence(f"{modifier}+Shift+T"))
    assert window.tabs.count() == 1 and window.folder == folders[0]
    QTest.keySequence(window, QKeySequence(f"{modifier}+Shift+T"))
    assert window.folder == folders[1]
    QTest.keySequence(window, QKeySequence(f"{modifier}+Shift+T"))
    assert window.tabs.count() == 2


def test_restore_order_active_tab_and_independent_states(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    QTest.qWait(50)
    first.thumbs.select(first.files[1])
    first.thumbs.slider.setValue(190)
    first.image.slider.setValue(1250)
    first.image.rotate()
    first.image.mirror_v()
    first.set_orientation(Qt.Orientation.Horizontal)
    second = window.open_folder(folders[1])
    second.image.slider.setValue(750)
    window.tabs.tabBar().moveTab(0, 1)
    assert window.pages() == [second, first]
    window.close()
    loaded = load_settings()
    assert [state["folder"] for state in loaded["tabs"]] == [str(folder) for folder in reversed(folders)]
    assert loaded["active_tab"] == 0 and loaded["folder"] == str(folders[1])
    restored = PicView()
    restored.show()
    QTest.qWait(50)
    try:
        assert restored.folder == folders[1]
        assert restored.image.slider.value() == 750
        other = restored.pages()[1]
        restored.tabs.setCurrentWidget(other)
        QTest.qWait(50)
        assert other.thumbs.selected_path.name == "image1.png"
        assert other.thumbs.size == 190
        assert other.split.orientation() == Qt.Orientation.Horizontal
        assert other.image.slider.value() == 1250
        assert other.image.rotation == 90 and other.image.fv
    finally:
        restored.close()
        restored.deleteLater()


def test_missing_restored_folder_is_retained_and_resumes(browser):
    window, folders = browser
    missing = folders[0] / "missing"
    save_settings({"tabs": [{"folder": str(missing), "selected_file": str(missing / "saved.png")}], "active_tab": 0})
    restored = PicView()
    restored.show()
    try:
        page = restored.current_tab()
        assert page.folder == missing and not page.files
        assert page.image.label.text() == restored.t["folder_missing"]
        missing.mkdir()
        Image.new("RGB", (120, 80), "blue").save(missing / "saved.png")
        wait_until(lambda: page.image.path == missing / "saved.png")
        assert page.image.frames
    finally:
        restored.close()
        restored.deleteLater()


def test_duplicate_folder_names_have_distinct_titles(browser):
    window, folders = browser
    first = folders[0] / "photos"
    second = folders[1] / "photos"
    first.mkdir()
    second.mkdir()
    window.open_folder(first)
    window.open_folder(second)
    assert window.tabs.tabText(0) != window.tabs.tabText(1)
    assert window.tabs.tabToolTip(0) == str(first)
    assert window.tabs.tabToolTip(1) == str(second)


def test_drop_multiple_folders_and_images(browser):
    window, folders = browser
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(folders[0])), QUrl.fromLocalFile(str(folders[1] / "image1.png")), QUrl("https://example.com/image.png")])
    class Drop:
        def source(self): return None
        def mimeData(self): return data
    window.dropEvent(Drop())
    assert window.tabs.count() == 2
    assert window.folder == folders[1]
    assert window.thumbs.selected_path.name == "image1.png"


def test_legacy_settings_restore_one_tab(browser):
    window, folders = browser
    save_settings({"folder": str(folders[0]), "selected_file": str(folders[0] / "image1.png"), "thumbnail_size": 200, "orientation": "horizontal"})
    restored = PicView()
    restored.show()
    QTest.qWait(50)
    try:
        assert restored.tabs.count() == 1
        assert restored.folder == folders[0]
        assert restored.thumbs.selected_path.name == "image1.png"
        assert restored.thumbs.size == 200
        assert restored.split.orientation() == Qt.Orientation.Horizontal
    finally:
        restored.close()
        restored.deleteLater()


def test_restore_scroll_split_ratio_and_normal_panes(browser):
    window, folders = browser
    for index in range(20):
        Image.new("RGB", (120, 80), "blue").save(folders[0] / f"thumb{index}.png")
    Image.new("RGB", (1600, 1200), "red").save(folders[0] / "image0.png")
    page = window.open_folder(folders[0])
    page.image.slider.setValue(1500)
    QTest.qWait(75)
    page.split.setSizes([300, 450])
    wait_until(lambda: page.thumbs.scroll.verticalScrollBar().maximum() >= 60)
    page.thumbs.scroll.verticalScrollBar().setValue(60)
    page.image.scroll.horizontalScrollBar().setValue(35)
    page.image.scroll.verticalScrollBar().setValue(75)
    assert page.thumbs.scroll.verticalScrollBar().value() == 60
    page.maximize("thumb")
    window.close()
    assert load_settings()["tabs"][0]["thumbnail_scroll"] == 60
    restored = PicView()
    restored.show()
    QTest.qWait(100)
    try:
        other = restored.current_tab()
        wait_until(lambda: other._pending_scroll is None)
        assert other.saved_sizes is None and not other.image.isHidden()
        assert abs(other.snapshot()["sash_fraction"] - .4) < .03
        assert other.thumbs.scroll.verticalScrollBar().value() == 60
        assert other.image.scroll.horizontalScrollBar().value() == 35
        assert other.image.scroll.verticalScrollBar().value() == 75
    finally:
        restored.close()
        restored.deleteLater()


def test_opening_same_folder_with_new_image_creates_independent_tab(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    window.open_folder(folders[1])
    added = folders[0] / "new.png"
    Image.new("RGB", (120, 80), "blue").save(added)
    opened = window.open_folder(folders[0], added)
    assert opened is not first
    assert opened.image.path == added and opened.thumbs.selected_path == added
    assert first.thumbs.selected_path != added


def test_foreground_deletion_supersedes_old_background_notice(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    first.pending_notification = "old notification"
    first.notify("new notification")
    assert not first.pending_notification
    assert window.notification_bar.currentMessage() == "new notification"


def test_user_interaction_cancels_pending_scroll_restore(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    page._pending_scroll = {"thumbnail_scroll": 60, "image_scroll_x": 35, "image_scroll_y": 75}
    page.scroll_restore_timer.start()
    QTest.mouseClick(page.image.scroll.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(1, 1))
    assert page._pending_scroll is None
    assert not page.scroll_restore_timer.isActive()


def test_close_buttons_keep_page_identity_after_reorder(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    third_folder = folders[0].parent / "three"
    third_folder.mkdir()
    third = window.open_folder(third_folder)
    bar = window.tabs.tabBar()
    bar.moveTab(0, 2)
    assert window.pages() == [second, third, first]
    button = bar.tabButton(window.tabs.indexOf(first), QTabBar.ButtonPosition.RightSide)
    button.click()
    assert window.pages() == [second, third]
    assert window.current_tab() is third and window.tabs.stack.currentWidget() is third
    assert first._closing
    bar.tabButton(window.tabs.indexOf(third), QTabBar.ButtonPosition.RightSide).click()
    assert window.current_tab() is second and window.tabs.stack.currentWidget() is second


def test_duplicate_tab_preserves_view_and_is_independent(browser):
    window, folders = browser
    source = window.open_folder(folders[0])
    source.thumbs.select(source.files[1])
    source.image.rotate()
    source.image.mirror_h()
    source.image.slider.setValue(1500)
    source.thumbs.slider.setValue(180)
    window.set_orientation(Qt.Orientation.Horizontal)
    window.open_folder(folders[1])
    copied = window.duplicate_page(source)
    QTest.qWait(100)
    assert window.pages()[1] is copied and window.current_tab() is copied
    assert copied.folder == source.folder and copied.image.path == source.image.path
    assert copied.image.rotation == 90 and copied.image.fh
    assert copied.image.zoom == source.image.zoom == 1.5
    assert copied.thumbs.size == 180
    assert copied.split.orientation() == Qt.Orientation.Horizontal
    assert window.tabs.tabText(0) == "one (1)"
    assert window.tabs.tabText(1) == "one (2)"
    copied.thumbs.select(copied.files[0])
    copied.image.rotate()
    assert source.image.path == source.files[1]
    assert source.image.rotation == 90
    window.close_tab(window.tabs.indexOf(copied))
    assert not source._closing and source.folder_poll_timer.isActive()


def test_duplicate_folder_tabs_restore_separate_images(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.duplicate_page(first)
    second.thumbs.select(second.files[1])
    second.image.rotate()
    window.close()
    restored = PicView()
    restored.show()
    try:
        assert restored.tabs.count() == 2
        assert restored.pages()[0].folder == restored.pages()[1].folder
        assert restored.current_tab().image.path.name == "image1.png"
        assert restored.current_tab().image.rotation == 90
        restored.tabs.setCurrentIndex(0)
        assert restored.image.path.name == "image0.png"
        assert restored.image.rotation == 0
    finally:
        restored.close()
        restored.deleteLater()


def test_tab_context_menu_targets_right_clicked_tab_after_reorder(browser, monkeypatch):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.tabs.bar.moveTab(0, 1)
    menus = []
    monkeypatch.setattr(QMenu, "popup", lambda menu, pos: menus.append(menu))
    window.tabs.bar.customContextMenuRequested.emit(window.tabs.bar.tabRect(window.tabs.indexOf(first)).center())
    assert window.current_tab() is second
    assert menus[0].actions()[0].text() == window.t["duplicate_tab"]
    menus[0].actions()[0].trigger()
    assert window.current_tab().folder == first.folder
    assert window.pages() == [second, first, window.current_tab()]


def test_empty_tab_context_menu_disables_duplication(browser, monkeypatch):
    window, _ = browser
    menus = []
    monkeypatch.setattr(QMenu, "popup", lambda menu, pos: menus.append(menu))
    window.show_tab_menu(window.tabs.bar.tabRect(0).center())
    assert not menus[0].actions()[0].isEnabled()
    assert window.duplicate_page(window.current_tab()) is None
