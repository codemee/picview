import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from picview.qt_app import ImagePane
from test_crop import move_drag
from test_tabs import browser

pytestmark = pytest.mark.usefixtures("real_unsaved_checks")


@pytest.fixture(autouse=True)
def fail_on_unexpected_save_error(monkeypatch):
    original = ImagePane.message_box
    def check(self, *args):
        if args[0] == QMessageBox.Icon.Critical: raise AssertionError(args[2])
        return original(self, *args)
    monkeypatch.setattr(ImagePane, "message_box", check)


def pattern(path):
    image = Image.new("RGBA", (120, 80))
    image.putdata([(x * 2, y * 3, (x + y) % 255, 255) for y in range(80) for x in range(120)])
    image.save(path)


def assert_saved(path, expected):
    with Image.open(path) as saved:
        assert saved.size == expected.size
        assert saved.convert("RGBA").tobytes() == expected.convert("RGBA").tobytes()


def test_multilevel_undo_redo_shortcuts_and_drag_grouping(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    original = pane.image()
    pane.rotate()
    rotated = pane.image()
    pane.mirror_h()
    mirrored = pane.image()
    pane.crop_button.click()
    label = pane.label
    start = label.handles()["tl"].toPoint()
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    for distance in range(1, 20): move_drag(label, start + QPoint(distance, distance))
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=start + QPoint(19, 19))
    assert len(pane.undo_stack) == 3
    cropped = pane.image()
    assert pane.is_modified and "*" in pane.filename_label.text()
    for expected in (mirrored, rotated, original):
        QTest.keySequence(pane.scroll, QKeySequence(QKeySequence.StandardKey.Undo))
        assert pane.image().tobytes() == expected.tobytes()
    assert not pane.is_modified
    for expected in (rotated, mirrored, cropped):
        QTest.keySequence(pane.scroll, QKeySequence(QKeySequence.StandardKey.Redo))
        assert pane.image().tobytes() == expected.tobytes()
    pane.undo()
    pane.mirror_v()
    assert not pane.redo_stack


def test_save_native_pixels_watcher_and_undo_after_save(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    pane.rotate(); pane.mirror_h(); pane.set_crop((.25, .25, .75, .75))
    expected = pane.image()
    pane.choose_zoom(2000)
    QTest.keySequence(pane.scroll, QKeySequence(QKeySequence.StandardKey.Save))
    assert_saved(path, expected)
    assert not pane.is_modified
    assert pane.image().tobytes() == expected.tobytes()
    pane.owner_page.refresh_folder()
    assert pane.reload_preserving_view()
    assert pane.image().tobytes() == expected.tobytes()
    pane.undo()
    assert pane.is_modified and pane.image_size() == (80, 120)
    pane.redo()
    assert not pane.is_modified
    assert pane.save_image()
    assert_saved(path, expected)


def test_save_as_updates_document_and_retains_undo(browser, monkeypatch, tmp_path):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    source = pane.path
    original = source.read_bytes()
    pane.rotate(); pane.set_crop((.25, 0, .75, 1))
    expected = pane.image()
    target_folder = tmp_path / "export"
    target_folder.mkdir()
    target = target_folder / "result"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), "PNG (*.png)"))
    QTest.keySequence(pane.scroll, QKeySequence(QKeySequence.StandardKey.SaveAs))
    target = target.with_suffix(".png")
    assert pane.path == target
    assert pane.owner_page.folder == target_folder
    assert pane.owner_page.thumbs.selected_path == target
    assert_saved(target, expected)
    assert source.read_bytes() == original
    assert not pane.is_modified
    pane.undo()
    assert pane.is_modified
    assert pane.image_size() == (80, 120)
    assert pane.save_image()
    assert Image.open(target).size == (80, 120)
    assert source.read_bytes() == original


def test_failed_save_is_atomic_and_does_not_clear_edits(browser, monkeypatch):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    original = pane.path.read_bytes()
    pane.rotate()
    errors = []
    monkeypatch.setattr(pane, "message_box", lambda *args: errors.append(args))
    def fail(*args, **kwargs): raise OSError("disk full")
    monkeypatch.setattr(Image.Image, "save", fail)
    assert not pane.save_image()
    assert errors and "disk full" in errors[0][2]
    assert pane.path.read_bytes() == original
    assert pane.is_modified and len(pane.undo_stack) == 1
    assert not list(pane.path.parent.glob(".picview-*"))


@pytest.mark.parametrize("suffix", [".gif", ".webp", ".png", ".tiff"])
def test_save_animation_all_frames_and_timing(browser, suffix):
    window, folders = browser
    source = folders[0] / "animated.gif"
    Image.new("RGBA", (120, 80), "red").save(source, save_all=True,
        append_images=[Image.new("RGBA", (120, 80), "blue")], duration=[80, 160], loop=3)
    pane = window.open_folder(folders[0], source).image
    pane.timer.stop()
    pane.rotate(); pane.set_crop((.25, .25, .75, .75))
    target = folders[0] / ("result" + suffix)
    assert pane.save_to(target)
    with Image.open(target) as saved:
        assert saved.n_frames == 2
        assert saved.size == (40, 60)
        if suffix in {".gif", ".png"}:
            assert saved.info["loop"] == 3
            assert saved.info["duration"] == 80
            saved.seek(1)
            assert saved.info["duration"] == 160
    pane.undo()
    assert pane.animation_loop == 3
    assert pane.timer.isActive()


def test_svg_save_preserves_vector_geometry(browser):
    window, folders = browser
    path = folders[0] / "source.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">'
                    '<path fill="red" d="M0 0h60v80H0z"/><path fill="blue" d="M60 0h60v80H60z"/></svg>')
    pane = window.open_folder(folders[0], path).image
    pane.rotate(); pane.mirror_v(); pane.set_crop((0, .5, 1, 1))
    expected = pane.svg_image(pane.image_size())
    assert pane.save_image()
    assert b"<path" in path.read_bytes()
    assert pane.image_size() == (80, 60)
    actual = pane.svg_image((80, 60))
    assert actual == expected, [(actual.pixelColor(x, y).getRgb(), expected.pixelColor(x, y).getRgb())
                                for x, y in ((1, 1), (40, 30), (79, 59))]


@pytest.mark.parametrize("choice", [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Save])
def test_switch_image_prompts_and_obeys_choice(browser, monkeypatch, choice):
    window, folders = browser
    page = window.open_folder(folders[0])
    pane = page.image
    original_path = pane.path
    original_bytes = original_path.read_bytes()
    pane.rotate()
    expected = pane.image()
    prompts = []
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: prompts.append(self.path) or choice)
    page.thumbs.select(page.files[1])
    assert prompts == [original_path]
    if choice == QMessageBox.StandardButton.Cancel:
        assert pane.path == original_path
        assert page.thumbs.selected_path == original_path
        assert pane.is_modified
        assert pane.image().tobytes() == expected.tobytes()
        monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Discard)
    else:
        assert pane.path == page.files[1]
        assert not pane.is_modified
    if choice == QMessageBox.StandardButton.Save: assert_saved(original_path, expected)
    else: assert original_path.read_bytes() == original_bytes


def test_cancel_protects_folder_tab_and_window_and_failed_save_stays_put(browser, monkeypatch):
    window, folders = browser
    page = window.open_folder(folders[0])
    pane = page.image
    pane.mirror_v()
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Cancel)
    assert not window.navigate_folder(page, folders[1])
    assert page.folder == folders[0]
    window.close_tab()
    assert page in window.pages() and pane.is_modified
    assert not window.close()
    assert window.isVisible() and pane.is_modified
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(pane, "save_image", lambda: False)
    page.thumbs.select(page.files[1])
    assert pane.path == page.files[0] and page.thumbs.selected_path == page.files[0]
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Discard)


def test_clean_zoom_and_undone_changes_do_not_prompt(browser, monkeypatch):
    window, folders = browser
    page = window.open_folder(folders[0])
    pane = page.image
    def unexpected(self): raise AssertionError("clean image prompted")
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", unexpected)
    pane.choose_zoom(2000)
    pane.crop_button.click()
    assert not pane.is_modified
    pane.mirror_h(); pane.undo()
    assert not pane.is_modified
    page.thumbs.select(page.files[1])
    assert pane.path == page.files[1]


def test_external_reload_keeps_unsaved_edits_and_tab_switch_can_cancel(browser, monkeypatch):
    window, folders = browser
    first = window.open_folder(folders[0])
    first.image.rotate()
    expected = first.image.image()
    Image.new("RGBA", (130, 90), "blue").save(first.image.path)
    assert not first.image.reload_preserving_view()
    assert first.image.image().tobytes() == expected.tobytes()
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Cancel)
    second = window.open_folder(folders[1])
    assert first is window.current_tab()
    assert second in window.pages()
    assert first.image.is_modified
    assert first.image.image().tobytes() == expected.tobytes()
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Discard)
    window.tabs.setCurrentWidget(second)
    assert second is window.current_tab()
    assert not first.image.is_modified


def test_jpeg_export_fills_transparency_and_cancelled_dialog_keeps_edits(browser, monkeypatch):
    window, folders = browser
    path = folders[0] / "transparent.png"
    Image.new("RGBA", (120, 80), (255, 0, 0, 0)).save(path)
    pane = window.open_folder(folders[0], path).image
    pane.rotate()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", "PNG (*.png)"))
    assert not pane.save_image_as()
    assert pane.path == path and pane.is_modified
    target = folders[0] / "result.jpg"
    assert pane.save_to(target)
    with Image.open(target) as image:
        assert image.size == (80, 120)
        assert image.getpixel((0, 0)) == (255, 255, 255)
    assert not pane.is_modified


def test_animation_flatten_can_cancel_without_writing(browser, monkeypatch):
    window, folders = browser
    path = folders[0] / "animated.gif"
    Image.new("RGB", (120, 80), "red").save(path, save_all=True,
        append_images=[Image.new("RGB", (120, 80), "blue")], duration=100)
    pane = window.open_folder(folders[0], path).image
    pane.rotate()
    monkeypatch.setattr(pane, "message_box", lambda *args: QMessageBox.StandardButton.Cancel)
    target = folders[0] / "result.jpg"
    assert not pane.save_to(target)
    assert not target.exists()
    assert pane.path == path and pane.is_modified
