import os
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from picview import file_actions, qt_app
from picview.settings import normalize_tab_state, save_settings, load_settings
from test_tabs import browser, wait_until


def populate_folder(folder):
    for name, modified in (("image1.png", 1_600_000_300), ("image2.png", 1_600_000_100), ("image10.png", 1_600_000_200)):
        path = folder / name
        Image.new("RGB", (120, 80), "blue").save(path)
        os.utime(path, (modified, modified))
    (folder / "image0.png").unlink(missing_ok=True)


@pytest.mark.parametrize("mode,descending,names", [
    ("natural", False, ["image1.png", "image2.png", "image10.png"]),
    ("natural", True, ["image10.png", "image2.png", "image1.png"]),
    ("modified", False, ["image2.png", "image10.png", "image1.png"]),
    ("modified", True, ["image1.png", "image10.png", "image2.png"]),
])
def test_sorting_preserves_selection_and_image_view(browser, mode, descending, names):
    window, folders = browser
    populate_folder(folders[0])
    page = window.open_folder(folders[0])
    selected = folders[0] / "image2.png"
    page.thumbs.select(selected)
    page.image.rotate()
    frames = page.image.frames
    page.set_sort(mode, descending)
    assert [path.name for path in page.files] == names
    assert page.thumbs.files == page.files
    assert page.thumbs.selected_path == selected and page.image.path == selected
    assert page.image.frames is frames and page.image.rotation == 90
    assert [page.thumbs.grid.itemAtPosition(0, index).widget().path.name for index in range(3)] == names


def test_sort_buttons_global_dates_settings_and_duplicate_tab(browser):
    window, folders = browser
    populate_folder(folders[0])
    first = window.open_folder(folders[0])
    assert first.thumbs.sort_button.kind == "sort-name"
    assert first.thumbs.direction_button.kind == "sort-ascending"
    first.thumbs.sort_button.click()
    first.thumbs.direction_button.click()
    assert first.thumbs.sort_button.kind == "sort-date" and first.thumbs.sort_button.isChecked()
    assert first.thumbs.direction_button.kind == "sort-descending" and first.thumbs.direction_button.isChecked()
    tile = first.thumbs.buttons[first.files[0]]
    assert not tile.modified_label.isHidden()
    shown_height = tile.height()
    window.modified_button.click()
    assert tile.modified_label.isHidden() and tile.height() == shown_height - 20
    window.toggle_lang()
    assert window.t["sort_modified"] in first.thumbs.sort_button.toolTip()
    assert window.modified_button.toolTip() == window.t["show_modified"]
    duplicate = window.duplicate_page(first)
    assert duplicate.thumbs.sort_mode == "modified" and duplicate.thumbs.sort_descending
    assert not duplicate.thumbs.show_modified
    other = window.open_folder(folders[1])
    assert other.thumbs.sort_mode == "natural" and not other.thumbs.show_modified
    window.modified_button.click()
    assert all(page.thumbs.show_modified for page in window.pages())
    window.modified_button.click()
    assert all(not page.thumbs.show_modified for page in window.pages())
    state = first.snapshot()
    save_settings({"tabs": [state], "show_modified": window.show_modified})
    restored = load_settings()["tabs"][0]
    assert restored["sort_mode"] == "modified" and restored["sort_descending"]
    assert "show_modified" not in restored and not load_settings()["show_modified"]
    invalid = normalize_tab_state({"folder": str(folders[0]), "sort_mode": [], "sort_descending": "yes", "show_modified": "no"})
    assert invalid["sort_mode"] == "natural" and not invalid["sort_descending"] and "show_modified" not in invalid
    replacement = qt_app.PicView()
    try:
        assert not replacement.modified_button.isChecked()
        assert all(not page.thumbs.show_modified for page in replacement.pages())
    finally:
        replacement.close()
        replacement.deleteLater()


def test_modified_order_and_date_update_live_and_deleted_selection_uses_sorted_successor(browser):
    window, folders = browser
    populate_folder(folders[0])
    page = window.open_folder(folders[0])
    page.set_sort("modified", True)
    path = folders[0] / "image2.png"
    os.utime(path, (1_700_000_000, 1_700_000_000))
    wait_until(lambda: page.files[0] == path)
    expected = datetime.fromtimestamp(1_700_000_000).strftime("%Y-%m-%d %H:%M:%S")
    assert page.thumbs.buttons[path].modified_label.toolTip() == expected
    page.thumbs.select(path)
    successor = page.files[1]
    path.unlink()
    wait_until(lambda: page.thumbs.selected_path == successor)
    assert page.image.path == successor
    added = folders[0] / "image3.png"
    Image.new("RGB", (20, 20), "green").save(added)
    wait_until(lambda: added in page.files)
    assert page.files[0] == added


def test_card_context_copy_and_properties_target_clicked_file(browser, monkeypatch):
    window, folders = browser
    page = window.open_folder(folders[0])
    path = page.files[1]
    tile = page.thumbs.buttons[path]
    tile.customContextMenuRequested.emit(QPoint(8, 8))
    assert page.thumbs.selected_path == path
    actions = page.thumbs.context_menu.actions()
    assert actions[0].text().startswith(window.t["copy"])
    assert actions[1].text() == window.t["properties"]
    actions[0].trigger()
    try:
        assert Path(QApplication.clipboard().mimeData().urls()[0].toLocalFile()) == path
    finally:
        # Like the existing copy test, release file MIME data before the
        # offscreen Qt clipboard is destroyed at interpreter shutdown.
        QApplication.clipboard().clear()
    calls = []
    monkeypatch.setattr(qt_app, "show_properties", lambda file, parent, labels: calls.append(file))
    actions[1].trigger()
    assert calls == [path]
    page.thumbs.context_menu.hide()
    path.unlink()
    page.thumbs.show_file_menu(path, tile.mapToGlobal(QPoint()))
    assert all(not action.isEnabled() for action in page.thumbs.context_menu.actions())
    page.thumbs.context_menu.hide()


def test_properties_fallback_has_real_file_metadata(browser, monkeypatch):
    window, folders = browser
    path = folders[0] / "image0.png"
    monkeypatch.setattr(file_actions, "show_native_properties", lambda *args: False)
    dialog = file_actions.show_properties(path, window, window.t)
    values = [label.text() for label in dialog.findChildren(QLabel)]
    assert path.name in values and str(path.parent) in values
    assert "120 × 80 px" in values
    assert f"{path.stat().st_size:,} {window.t['bytes']}" in values
    dialog.close()


def test_sort_and_date_state_buttons_work_from_narrow_overflow(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    window.resize(260, 300)
    QTest.qWait(100)
    overflow = page.thumbs.toolbar_overflow
    assert page.thumbs.sort_button in overflow.overflowed
    overflow.populate_menu()
    for button in (page.thumbs.sort_button, page.thumbs.direction_button):
        action = next(item for item in overflow.menu.actions() if item.text() == button.toolTip())
        assert action.isCheckable() and not action.isChecked()
        action.trigger()
        assert button.isChecked()
    assert page.thumbs.sort_mode == "modified" and page.thumbs.sort_descending
    main = window.toolbar_overflow
    main.populate_menu()
    action = next(item for item in main.menu.actions() if item.text() == window.modified_button.toolTip())
    assert action.isChecked()
    action.trigger()
    assert not window.show_modified and not page.thumbs.show_modified
