from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from picview.qt_app import PicView
from picview.settings import load_settings
from test_tabs import browser, wait_until


def test_subfolders_are_first_and_never_enter_image_selection_or_preview_queue(browser):
    window, folders = browser
    root = folders[0]
    children = [root / name for name in ("child10", "child2")]
    for child in children:
        child.mkdir()
    (children[0] / "nested").mkdir()
    page = window.open_folder(root)
    thumbs = page.thumbs
    assert thumbs.directories == [children[1], children[0]]
    assert len(thumbs.files) == 2
    assert len(thumbs.folder_buttons) == 2
    assert thumbs.grid.itemAtPosition(0, 0).widget() is thumbs.folder_buttons[children[1]]
    assert not set(children).intersection(thumbs._pending_paths)
    original_image = page.image.path
    QTest.mouseClick(thumbs.folder_buttons[children[0]], Qt.MouseButton.LeftButton)
    assert thumbs.selected_directory == children[0]
    assert not thumbs.selected_paths
    assert page.image.path == original_image
    thumbs.select_all()
    assert thumbs.selected_paths == set(thumbs.files)
    assert not thumbs.selected_directory


def test_double_click_browses_in_same_tab_and_back_restores_selection_and_scroll(browser):
    window, folders = browser
    root = folders[0]
    child = root / "child"
    child.mkdir()
    Image.new("RGB", (120, 80), "blue").save(child / "child.png")
    for index in range(30):
        Image.new("RGB", (20, 20), "green").save(root / f"extra{index}.png")
    page = window.open_folder(root)
    window.resize(650, 500)
    wait_until(lambda: page.thumbs.scroll.verticalScrollBar().maximum() > 100)
    selected = page.files[-1]
    page.thumbs.select(selected)
    page.thumbs.scroll.verticalScrollBar().setValue(150)
    position = page.thumbs.scroll.verticalScrollBar().value()
    count = window.tabs.count()
    QTest.mouseDClick(page.thumbs.folder_buttons[child], Qt.MouseButton.LeftButton)
    assert page.folder == child
    assert window.current_tab() is page and window.tabs.count() == count
    assert page.image.path == child / "child.png"
    assert window.folder_back_button.isEnabled()
    window.folder_back_button.click()
    assert page.folder == root
    wait_until(lambda: page.thumbs.selected_path == selected and page.thumbs.scroll.verticalScrollBar().value() == position)
    assert not page.folder_history


def test_parent_navigation_and_empty_folders_and_missing_history_target(browser):
    window, folders = browser
    child = folders[0] / "empty"
    child.mkdir()
    page = window.open_folder(child)
    window.folder_up_button.click()
    assert page.folder == folders[0]
    window.folder_back_button.click()
    assert page.folder == child and not page.files
    window.folder_up_button.click()
    child.rmdir()
    window.folder_back_button.click()
    assert page.folder == folders[0]
    assert len(page.folder_history) == 1
    assert str(child) in window.notification_bar.currentMessage()


def test_subfolders_and_navigation_are_hidden_during_comparison(browser):
    window, folders = browser
    child = folders[0] / "child"
    child.mkdir()
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    assert first.thumbs.directories == [child]
    window.set_compare(True)
    window.check_compare_page(first, True)
    for button in (window.folder_back_button, window.folder_up_button, window.subfolders_button):
        assert button.isHidden()
        assert button.property("toolbar_available") is False
        assert button not in window.toolbar_overflow.overflowed
    assert not first.thumbs.directories
    assert not window.navigate_folder(second, folders[0])
    window.set_compare(False)
    assert first.thumbs.directories == [child]
    assert window.subfolders_button.property("toolbar_available") is True


def test_subfolder_toggle_persists_and_watch_updates_cards(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    child = folders[0] / "new"
    child.mkdir()
    page.refresh_folder()
    assert child in page.thumbs.folder_buttons
    window.subfolders_button.click()
    assert not page.thumbs.directories
    for button in (window.folder_back_button, window.folder_up_button):
        assert button.isHidden()
        assert button.property("toolbar_available") is False
    assert window.folder_back_button not in window.toolbar_overflow.overflowed
    assert window.folder_up_button not in window.toolbar_overflow.overflowed
    window.close()
    assert load_settings()["show_subfolders"] is False
    fresh = PicView()
    try:
        assert not fresh.show_subfolders
        assert not fresh.current_tab().thumbs.directories
        for button in (fresh.folder_back_button, fresh.folder_up_button):
            assert button.property("toolbar_available") is False
        fresh.set_show_subfolders(True)
        assert child in fresh.current_tab().thumbs.folder_buttons
        for button in (fresh.folder_back_button, fresh.folder_up_button):
            assert button.property("toolbar_available") is True
        child.rmdir()
        fresh.current_tab().refresh_folder()
        assert child not in fresh.current_tab().thumbs.folder_buttons
    finally:
        fresh.close()
        fresh.deleteLater()


def test_navigation_tools_work_from_narrow_toolbar_and_relabel(browser):
    window, folders = browser
    child = folders[0] / "child"
    child.mkdir()
    page = window.open_folder(child)
    window.resize(260, 220)
    QTest.qWait(100)
    controller = window.toolbar_overflow
    controller.populate_menu()
    assert window.folder_up_button in controller.panel_controls
    controller.panel_controls[window.folder_up_button].click()
    assert page.folder == folders[0]
    window.toggle_lang()
    assert window.folder_back_button.toolTip() == window.t["folder_back"]
    assert window.subfolders_button.toolTip() == window.t["show_subfolders"]


def test_image_row_navigation_accounts_for_folder_cards(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    window.resize(1100, 780)
    QTest.qWait(100)
    columns = page.thumbs.columns
    for index in range(columns - 1):
        (folders[0] / f"child{index}").mkdir()
    page.refresh_folder()
    page.thumbs.select(page.files[0])
    page.select_row(1)
    assert page.thumbs.selected_path == page.files[1]
    page.select_row(-1)
    assert page.thumbs.selected_path == page.files[0]
