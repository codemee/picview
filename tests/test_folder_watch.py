import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview.qt_app import PicView


def wait_until(condition, timeout=3000):
    deadline = time.monotonic() + timeout / 1000
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(25)
    assert condition()


@pytest.fixture
def viewer(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folder = tmp_path / "images"
    folder.mkdir()
    paths = [folder / name for name in ("image1.png", "image2.png", "image10.png")]
    for path in paths:
        Image.new("RGB", (120, 80), "red").save(path)
    app = QApplication.instance() or QApplication([])
    window = PicView()
    window.show()
    window.open_folder(folder)
    app.processEvents()
    QTest.qWait(50)
    yield window, folder, paths
    window.close()
    window.deleteLater()
    app.processEvents()


def test_new_images_appear_without_resetting_current_view(viewer):
    window, folder, paths = viewer
    window.thumbs.select(paths[1])
    window.image.rotate()
    window.image.mirror_h()
    window.image.slider.setValue(1400)
    original_frames = window.image.frames
    added = folder / "image0.png"
    Image.new("RGB", (90, 60), "blue").save(added)
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")
    wait_until(lambda: added in window.thumbs.buttons and window.thumbs.buttons[added].isVisible())
    assert window.files == [added, *paths]
    assert window.thumbs.selected_path == paths[1]
    assert window.image.path == paths[1]
    assert window.image.frames is original_frames
    assert window.image.rotation == 90 and window.image.fh
    assert window.image.slider.value() == 1400
    assert not window.notification_bar.currentMessage()


@pytest.mark.parametrize("selected_index, next_index", [(0, 1), (1, 2), (2, 0)])
def test_deleted_current_image_notifies_and_selects_next(viewer, selected_index, next_index):
    window, folder, paths = viewer
    removed = paths[selected_index]
    window.thumbs.select(removed)
    removed.unlink()
    wait_until(lambda: window.image.path == paths[next_index])
    assert removed not in window.files
    assert removed not in window.thumbs.buttons
    assert window.thumbs.selected_path == paths[next_index]
    message = window.notification_bar.currentMessage()
    assert removed.name in message and paths[next_index].name in message
    assert window.notification_bar.isVisible()


def test_deleting_other_image_does_not_notify_or_reload(viewer):
    window, folder, paths = viewer
    frames = window.image.frames
    paths[2].unlink()
    wait_until(lambda: paths[2] not in window.files)
    assert window.image.path == paths[0]
    assert window.image.frames is frames
    assert not window.notification_bar.currentMessage()


def test_deleting_all_images_clears_view_and_notifies_once(viewer):
    window, folder, paths = viewer
    for path in paths:
        path.unlink()
    wait_until(lambda: not window.files)
    assert window.thumbs.selected_path is None
    assert window.image.path is None
    assert not window.image.frames
    assert not window.image.filename_label.text()
    assert paths[0].name in window.notification_bar.currentMessage()
    window.notification_bar.clearMessage()
    window.refresh_folder()
    assert not window.notification_bar.currentMessage()


def test_switching_folders_replaces_watch_and_ignores_old_changes(viewer):
    window, folder, paths = viewer
    other = folder.parent / "other"
    other.mkdir()
    window.open_folder(other)
    assert window.folder_watcher.directories() == [str(other)]
    old_added = folder / "new.png"
    Image.new("RGB", (90, 60), "blue").save(old_added)
    window.schedule_folder_refresh(str(folder))
    assert not window.folder_refresh_timer.isActive()
    new_added = other / "new.png"
    Image.new("RGB", (90, 60), "blue").save(new_added)
    wait_until(lambda: window.image.path == new_added)
    assert window.files == [new_added]


def test_watch_survives_theme_and_language_rebuild(viewer):
    window, folder, paths = viewer
    window.toggle_theme()
    window.toggle_lang()
    QApplication.instance().processEvents()
    added = folder / "image3.png"
    Image.new("RGB", (90, 60), "blue").save(added)
    wait_until(lambda: added in window.thumbs.buttons)
    assert window.files == [paths[0], paths[1], added, paths[2]]
    assert window.thumbs.selected_path == paths[0]


def test_partial_image_is_retried_when_copy_finishes(viewer):
    window, folder, paths = viewer
    partial = folder / "copy.png"
    partial.write_bytes(b"partial")
    wait_until(lambda: partial in window.thumbs.failed_paths)
    window.thumbs.select(partial)
    assert not window.image.frames
    Image.new("RGB", (90, 60), "blue").save(partial)
    wait_until(lambda: partial not in window.thumbs.failed_paths and bool(window.image.frames))
    assert window.image.path == partial
    assert window.thumbs.buttons[partial].preview.pixmap() is not None


def test_folder_removal_and_recreation_resumes_monitoring(viewer):
    window, folder, paths = viewer
    for path in paths:
        path.unlink()
    folder.rmdir()
    wait_until(lambda: not window.files)
    folder.mkdir()
    replacement = folder / "replacement.png"
    Image.new("RGB", (90, 60), "blue").save(replacement)
    wait_until(lambda: window.image.path == replacement)
    assert window.folder_watcher.directories() == [str(folder)]


def test_temporary_scan_error_preserves_images(viewer, monkeypatch):
    import picview.qt_app as ui
    window, folder, paths = viewer
    frames = window.image.frames
    def denied(*args, **kwargs):
        raise PermissionError("temporary access failure")
    monkeypatch.setattr(ui, "image_files", denied)
    window.refresh_folder()
    assert window.files == paths
    assert window.image.frames is frames
    assert not window.notification_bar.currentMessage()


def test_close_stops_folder_monitoring(viewer):
    window, folder, paths = viewer
    window.close()
    assert not window.folder_poll_timer.isActive()
    assert not window.folder_refresh_timer.isActive()
    assert not window.folder_watcher.directories()
    assert not window.folder_watcher.files()


def test_locked_thumbnail_retries_without_rebuilding_other_tiles(viewer, monkeypatch):
    import picview.qt_app as ui
    window, folder, paths = viewer
    added = folder / "locked.png"
    Image.new("RGB", (90, 60), "blue").save(added)
    original_open = ui.Image.open
    locked = True
    def open_image(path, *args, **kwargs):
        if path == added and locked:
            raise OSError("file is still being copied")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(ui.Image, "open", open_image)
    window.refresh_folder()
    assert added in window.thumbs.failed_paths
    versions = window.pending_image_versions()
    tile = window.thumbs.buttons[paths[0]]
    frames = window.image.frames
    locked = False
    window.refresh_folder()
    assert added not in window.thumbs.failed_paths
    assert window.thumbs.buttons[paths[0]] is tile
    assert window.image.frames is frames
    assert versions[added] == (added.stat().st_size, added.stat().st_mtime_ns)


def test_multiple_deletions_choose_next_surviving_image(viewer):
    window, folder, paths = viewer
    paths[0].unlink()
    paths[1].unlink()
    wait_until(lambda: window.image.path == paths[2])
    assert window.files == [paths[2]]


def test_poll_detects_changes_when_filesystem_event_is_missed(viewer):
    window, folder, paths = viewer
    window.folder_watcher.directoryChanged.disconnect(window.schedule_folder_refresh)
    window.folder_refresh_timer.stop()
    added = folder / "new.png"
    Image.new("RGB", (90, 60), "blue").save(added)
    wait_until(lambda: added in window.thumbs.buttons)
    assert window.image.path == paths[0]


def thumbnail_color(window, path):
    pixmap = window.thumbs.buttons[path].preview.pixmap()
    return pixmap.toImage().pixelColor(pixmap.width() // 2, pixmap.height() // 2).name()


def test_current_image_modification_updates_both_panes_and_keeps_view(viewer):
    window, folder, paths = viewer
    path = paths[0]
    tile = window.thumbs.buttons[path]
    window.image.rotate()
    window.image.mirror_h()
    window.image.slider.setValue(1400)
    Image.new("RGB", (160, 100), "blue").save(path)
    wait_until(lambda: window.image.frames[0][0].size == (160, 100) and thumbnail_color(window, path) == "#0000ff")
    assert window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255)
    assert window.image.rotation == 90 and window.image.fh
    assert window.image.slider.value() == 1400
    assert window.thumbs.buttons[path] is tile
    assert window.thumbs.selected_path == path
    assert not window.notification_bar.currentMessage()


def test_modifying_other_image_only_updates_its_thumbnail(viewer):
    window, folder, paths = viewer
    frames = window.image.frames
    tile = window.thumbs.buttons[paths[1]]
    Image.new("RGB", (120, 80), "blue").save(paths[1])
    wait_until(lambda: thumbnail_color(window, paths[1]) == "#0000ff")
    assert window.image.frames is frames
    assert window.thumbs.buttons[paths[1]] is tile
    assert window.thumbs.selected_path == paths[0]


def test_atomic_replacement_reinstates_file_watch(viewer):
    window, folder, paths = viewer
    path = paths[0]
    for color, rgb in (("blue", (0, 0, 255, 255)), ("green", (0, 128, 0, 255))):
        temporary = folder / "replacement.tmp"
        Image.new("RGB", (120, 80), color).save(temporary, format="PNG")
        os.replace(temporary, path)
        wait_until(lambda: window.image.frames[0][0].getpixel((0, 0)) == rgb)
        assert str(path) in window.folder_watcher.files()
        assert thumbnail_color(window, path) == ("#0000ff" if color == "blue" else "#008000")


def test_partial_overwrite_keeps_last_complete_image(viewer):
    window, folder, paths = viewer
    path = paths[0]
    frames = window.image.frames
    path.write_bytes(b"incomplete image")
    window.refresh_folder()
    assert window.image.frames is frames
    assert thumbnail_color(window, path) == "#ff0000"
    assert path in window.thumbs.failed_paths
    Image.new("RGB", (120, 80), "blue").save(path)
    wait_until(lambda: window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255))
    assert thumbnail_color(window, path) == "#0000ff"
    assert path not in window.thumbs.failed_paths


def test_same_size_overwrite_is_detected_by_polling(viewer):
    window, folder, paths = viewer
    path = folder / "same_size.bmp"
    Image.new("RGB", (120, 80), "red").save(path)
    window.open_folder(folder, path)
    window.folder_watcher.fileChanged.disconnect(window.schedule_image_refresh)
    window.folder_watcher.directoryChanged.disconnect(window.schedule_folder_refresh)
    window.folder_refresh_timer.stop()
    size = path.stat().st_size
    Image.new("RGB", (120, 80), "blue").save(path)
    assert path.stat().st_size == size
    wait_until(lambda: window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255))
    assert thumbnail_color(window, path) == "#0000ff"


def test_modification_and_addition_in_same_update(viewer):
    window, folder, paths = viewer
    added = folder / "new.png"
    Image.new("RGB", (120, 80), "blue").save(paths[0])
    Image.new("RGB", (120, 80), "green").save(added)
    wait_until(lambda: added in window.thumbs.buttons and window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255))
    assert thumbnail_color(window, paths[0]) == "#0000ff"
    assert window.thumbs.selected_path == paths[0]


def test_full_image_decode_failure_retries_without_new_file_change(viewer, monkeypatch):
    window, folder, paths = viewer
    frames = window.image.frames
    read_frames = window.image.read_frames
    locked = True
    def read(path):
        if locked: raise OSError("file is still being written")
        return read_frames(path)
    monkeypatch.setattr(window.image, "read_frames", read)
    Image.new("RGB", (120, 80), "blue").save(paths[0])
    window.refresh_folder()
    assert thumbnail_color(window, paths[0]) == "#0000ff"
    assert window.image.frames is frames
    locked = False
    window.refresh_folder()
    assert window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255)


def test_file_change_event_updates_without_waiting_for_poll(viewer):
    window, folder, paths = viewer
    window.folder_poll_timer.stop()
    window.folder_refresh_timer.stop()
    window.folder_watcher.directoryChanged.disconnect(window.schedule_folder_refresh)
    Image.new("RGB", (120, 80), "blue").save(paths[0])
    wait_until(lambda: window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255))
    assert thumbnail_color(window, paths[0]) == "#0000ff"


def test_modified_image_preserves_fit_and_updates_fullscreen(viewer):
    window, folder, paths = viewer
    window.image.fit_b.setChecked(True)
    window.image.open_full()
    Image.new("RGB", (160, 100), "blue").save(paths[0])
    wait_until(lambda: window.image.frames[0][0].size == (160, 100))
    assert window.image.fit_to_pane and window.image.fit_b.isChecked()
    pixmap = window.image.full_window.centralWidget().pixmap()
    assert pixmap.toImage().pixelColor(0, 0).name() == "#0000ff"
    window.image.open_full()


@pytest.mark.parametrize("updated_size", [(1600, 1200), (1800, 1400)])
def test_modified_image_preserves_scroll_position(viewer, updated_size):
    window, folder, paths = viewer
    Image.new("RGB", (1600, 1200), "red").save(paths[0])
    window.image.load(paths[0])
    window.image.slider.setValue(1500)
    QTest.qWait(50)
    horizontal = window.image.scroll.horizontalScrollBar()
    vertical = window.image.scroll.verticalScrollBar()
    horizontal.setValue(35)
    vertical.setValue(75)
    assert horizontal.value() == 35 and vertical.value() == 75
    Image.new("RGB", updated_size, "blue").save(paths[0])
    wait_until(lambda: window.image.frames[0][0].getpixel((0, 0)) == (0, 0, 255, 255))
    QTest.qWait(25)
    assert horizontal.value() == 35 and vertical.value() == 75
    assert window.image.slider.value() == 1500


def test_reload_does_not_override_subsequent_user_scroll(viewer):
    window, folder, paths = viewer
    Image.new("RGB", (1600, 1200), "red").save(paths[0])
    window.image.load(paths[0])
    window.image.slider.setValue(1500)
    QTest.qWait(50)
    horizontal = window.image.scroll.horizontalScrollBar()
    vertical = window.image.scroll.verticalScrollBar()
    horizontal.setValue(20)
    vertical.setValue(40)
    assert window.image.reload_preserving_view()
    horizontal.setValue(35)
    vertical.setValue(75)
    QTest.qWait(25)
    assert horizontal.value() == 35 and vertical.value() == 75
