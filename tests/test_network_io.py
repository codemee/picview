import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview import network_io, qt_app, thumbnails
from test_tabs import browser, wait_until


def remote_folder(monkeypatch, folder):
    def remote(path): return path == folder or folder in Path(path).parents
    for module in (network_io, qt_app, thumbnails): monkeypatch.setattr(module, "is_network_path", remote)


def ready(page):
    return bool(page.image.frames) and not page.thumbs._pending_paths and not page.thumbs._jobs


def test_network_open_uses_snapshot_metadata_without_gui_stats(browser, monkeypatch):
    window, folders = browser
    folder = folders[0]
    remote_folder(monkeypatch, folder)
    main = threading.get_ident()
    stat = Path.stat
    def guarded(path, *args, **kwargs):
        if (path == folder or folder in path.parents) and threading.get_ident() == main:
            raise AssertionError("Network metadata read on GUI thread")
        return stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", guarded)
    page = window.open_folder(folder)
    wait_until(lambda: ready(page))
    assert page.folder_poll_timer.interval() == 5000
    assert not page.folder_watcher.files() and not page.folder_watcher.directories()
    assert page.thumbs.file_versions == page._network_snapshot.versions
    page.thumbs.build()
    page.refresh_subfolders()
    page.refresh_folder()
    wait_until(lambda: page.network_scan.future is None)
    assert not page.thumbs.failed_paths
    assert "120 × 80" in window.image_status.details


def test_slow_directory_scan_leaves_ui_responsive_and_navigation_discards_result(browser, monkeypatch):
    window, folders = browser
    remote_folder(monkeypatch, folders[0])
    release, started = threading.Event(), threading.Event()
    original = qt_app.scan_directory
    calls = []
    def slow(folder):
        calls.append(folder)
        started.set()
        assert release.wait(5)
        return original(folder)
    monkeypatch.setattr(qt_app, "scan_directory", slow)
    page = window.open_folder(folders[0])
    try:
        wait_until(started.is_set)
        beats = []
        QTimer.singleShot(0, lambda: beats.append(True))
        for _ in range(5): page.refresh_folder()
        wait_until(lambda: beats)
        assert len(calls) == 1 and not page.files
        page.open_folder(folders[1])
        release.set()
        wait_until(lambda: page.network_scan.future is None)
        assert page.folder == folders[1]
        assert all(path.parent == folders[1] for path in page.files)
        assert page.thumbs.file_versions is None
    finally:
        release.set()


def test_network_changes_retry_preserve_edits_and_recover_after_disconnect(browser, monkeypatch):
    window, folders = browser
    folder = folders[0]
    remote_folder(monkeypatch, folder)
    page = window.open_folder(folder)
    wait_until(lambda: ready(page))
    page.folder_poll_timer.stop()
    selected = page.image.path
    frame = page.image.frames
    pane = page.image
    pane.rotate()
    Image.new("RGB", (90, 70), "blue").save(selected)
    added = folder / "image10.png"
    Image.new("RGB", (70, 50), "green").save(added)
    page.refresh_folder()
    wait_until(lambda: added in page.files and page.network_scan.future is None)
    assert pane.frames is frame and pane.is_modified
    original = qt_app.scan_directory
    def unavailable(_): raise OSError("Share disconnected")
    monkeypatch.setattr(qt_app, "scan_directory", unavailable)
    page.refresh_folder()
    wait_until(lambda: page.network_scan.future is None)
    assert added in page.files and pane.frames is frame
    monkeypatch.setattr(qt_app, "scan_directory", original)
    pane.undo()
    added.unlink()
    page.refresh_folder()
    wait_until(lambda: added not in page.files)


def test_network_image_switch_only_displays_latest_selection(browser, monkeypatch):
    window, folders = browser
    folder = folders[0]
    remote_folder(monkeypatch, folder)
    release, started = threading.Event(), threading.Event()
    original = qt_app.decode_network_image
    calls = []
    def slow(path):
        calls.append(path)
        started.set()
        assert release.wait(5)
        return original(path)
    monkeypatch.setattr(qt_app, "decode_network_image", slow)
    page = window.open_folder(folder)
    try:
        wait_until(started.is_set)
        target = page.files[1]
        for _ in range(5):
            page.thumbs.select(page.files[0])
            page.thumbs.select(target)
        QTest.qWait(50)
        assert len(calls) == 1
        release.set()
        wait_until(lambda: ready(page))
        assert page.image.path == target and page.image._loading_path is None
        assert calls == [page.files[0], target]
    finally:
        release.set()


def test_payload_cache_deduplicates_transfers_and_obeys_budget(tmp_path, monkeypatch):
    path = tmp_path / "photo.jpg"
    entered, release = threading.Event(), threading.Event()
    transfers = []
    @contextmanager
    def source(path):
        transfers.append(path)
        entered.set()
        assert release.wait(5)
        yield io.BytesIO(b"12345678")
    monkeypatch.setattr(thumbnails, "image_source", source)
    cache = network_io.NetworkPayloadCache(max_bytes=12)
    version = (8, 1, 1, 0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cache.read, path, version)
        assert entered.wait(2)
        second = pool.submit(cache.read, path, version)
        release.set()
        assert first.result(2) == second.result(2) == b"12345678"
    assert transfers == [path]
    assert cache.read(path, version) == b"12345678"
    cache.read(tmp_path / "other.jpg", version)
    assert cache.bytes_used == 8 and len(cache.items) == 1
    cache.max_bytes = 4
    cache.items.clear(); cache.bytes_used = 0
    cache.read(path, version)
    assert cache.bytes_used == 0


def test_network_svg_load_and_refresh(browser, monkeypatch):
    window, folders = browser
    folder = folders[0]
    remote_folder(monkeypatch, folder)
    path = folder / "a.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="60" height="40"><rect width="60" height="40" fill="red"/></svg>')
    page = window.open_folder(folder, path)
    wait_until(lambda: ready(page))
    assert page.image.image_size() == (60, 40)
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="70" height="50"><rect width="70" height="50" fill="blue"/></svg>')
    page.refresh_folder()
    wait_until(lambda: page.image.image_size() == (70, 50))


def test_network_restores_view_after_async_image_load(browser, monkeypatch):
    window, folders = browser
    state = window.open_folder(folders[1]).snapshot()
    state.update(image_zoom=2., fit_to_pane=False, rotation=90, fh=True)
    remote_folder(monkeypatch, folders[0])
    target = folders[0] / "image1.png"
    page = window.open_folder(folders[0], target, state=state)
    wait_until(lambda: ready(page))
    assert page.image.path == target
    assert page.image.rotation == 90 and page.image.fh
    assert page.image.zoom == 2. and not page.image.fit_to_pane
    assert page._initial_view is None


def test_network_failed_reload_retries_without_losing_previous_image(browser, monkeypatch):
    window, folders = browser
    folder = folders[0]
    remote_folder(monkeypatch, folder)
    page = window.open_folder(folder)
    wait_until(lambda: ready(page))
    previous = page.image.frames
    original = qt_app.decode_network_image
    def unavailable(_): raise OSError("Temporarily incomplete")
    monkeypatch.setattr(qt_app, "decode_network_image", unavailable)
    page.image.reload_preserving_view()
    wait_until(lambda: page.image._network_load_failed)
    assert page.image.frames is previous and page.image_dirty
    monkeypatch.setattr(qt_app, "decode_network_image", original)
    page.refresh_folder()
    wait_until(lambda: not page.image_dirty and page.image._loading_path is None)
    assert page.image.frames is not previous
