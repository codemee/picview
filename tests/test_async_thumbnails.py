import threading

from PIL import Image
from PySide6.QtCore import QTimer

from picview import thumbnails
from picview.thumbnails import ThumbnailCache
from test_tabs import browser, wait_until


def ready(pane):
    return not pane._pending_paths and not pane._jobs


def test_slow_decoders_leave_ui_responsive_and_prioritize_scrolled_view(browser, monkeypatch):
    window, folders = browser
    for index in range(60):
        Image.new("RGB", (120, 80), "red").save(folders[0] / f"extra{index:02}.png")
    release = threading.Event()
    calls = []
    original = thumbnails.thumbnail_image

    def decode(path, *args):
        calls.append((path, threading.get_ident()))
        assert release.wait(5)
        return original(path, *args)

    monkeypatch.setattr(thumbnails, "thumbnail_image", decode)
    page = window.open_folder(folders[0])
    pane = page.thumbs
    try:
        # Opening creates placeholders without decoding thumbnails synchronously.
        assert not calls
        wait_until(lambda: len(calls) == 2)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        wait_until(lambda: heartbeat)
        assert len(calls) == 2
        assert all(thread_id != threading.get_ident() for _, thread_id in calls)
        bar = pane.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        priority = pane.preview_order()[0]
        release.set()
        wait_until(lambda: len(calls) >= 4)
        assert priority in {path for path, _ in calls[2:4]}
        wait_until(lambda: ready(pane))
        assert len(calls) == len(page.files)
    finally:
        release.set()


def test_layout_and_duplicate_tabs_reuse_thumbnails_without_decoding(browser, monkeypatch):
    window, folders = browser
    page = window.open_folder(folders[0])
    wait_until(lambda: ready(page.thumbs))
    tiles = dict(page.thumbs.buttons)
    pixmaps = {p: tile.preview.pixmap().cacheKey() for p, tile in tiles.items()}
    calls = []
    original = thumbnails.thumbnail_image

    def decode(path, *args):
        calls.append(path)
        return original(path, *args)

    monkeypatch.setattr(thumbnails, "thumbnail_image", decode)
    window.resize(680, 520)
    page.thumbs.build()
    assert all(page.thumbs.buttons[p] is tile for p, tile in tiles.items())
    assert all(page.thumbs.buttons[p].preview.pixmap().cacheKey() == key for p, key in pixmaps.items())
    duplicate = window.duplicate_page(page)
    wait_until(lambda: ready(duplicate.thumbs))
    assert not calls
    duplicate.thumbs.slider.setValue(180)
    wait_until(lambda: ready(duplicate.thumbs))
    assert len(calls) == len(duplicate.files)
    calls.clear()
    duplicate.thumbs.slider.setValue(140)
    wait_until(lambda: ready(duplicate.thumbs))
    assert not calls


def test_stale_worker_results_are_discarded_after_file_changes(browser, monkeypatch):
    window, folders = browser
    release = threading.Event()
    started = threading.Event()
    original = thumbnails.thumbnail_image

    def decode(path, *args):
        image = original(path, *args)
        started.set()
        assert release.wait(5)
        return image

    monkeypatch.setattr(thumbnails, "thumbnail_image", decode)
    page = window.open_folder(folders[0])
    path = page.files[0]
    pane = page.thumbs
    applied = []
    apply = pane.apply_preview

    def observe(key, image):
        if key[0] == path: applied.append(image.pixelColor(0, 0).name())
        apply(key, image)

    monkeypatch.setattr(pane, "apply_preview", observe)
    try:
        wait_until(started.is_set)
        Image.new("RGB", (120, 80), "blue").save(path)
        pane.refresh_previews([path])
        release.set()
        wait_until(lambda: ready(pane))
        assert applied and set(applied) == {"#0000ff"}
    finally:
        release.set()


def test_closing_tab_cancels_queued_updates(browser, monkeypatch):
    window, folders = browser
    release = threading.Event()
    started = threading.Event()
    original = thumbnails.thumbnail_image

    def decode(path, *args):
        started.set()
        assert release.wait(5)
        return original(path, *args)

    monkeypatch.setattr(thumbnails, "thumbnail_image", decode)
    page = window.open_folder(folders[0])
    try:
        wait_until(started.is_set)
        window.close_tab()
        assert page.thumbs._stopped
        assert not page.thumbs.preview_timer.isActive()
        assert not page.thumbs._jobs
        release.set()
        wait_until(lambda: not any(not f.done() for f in thumbnails.THUMBNAILS.inflight.values()))
    finally:
        release.set()


def test_shared_cache_deduplicates_requests_and_evicts_lru(tmp_path):
    cache = ThumbnailCache(max_bytes=3200)
    paths = [tmp_path / f"{i}.png" for i in range(3)]
    for path in paths: Image.new("RGBA", (20, 20), "red").save(path)
    keys = [cache.key(path, 20, 1.0) for path in paths]
    try:
        first = cache.request(keys[0])
        assert cache.request(keys[0]) is first
        first.result(timeout=3)
        cache.collect()
        cache.request(keys[1]).result(timeout=3)
        cache.collect()
        assert cache.get(keys[0]) is not None
        cache.request(keys[2]).result(timeout=3)
        cache.collect()
        assert cache.bytes_used <= cache.max_bytes
        assert cache.get(keys[1]) is None
        assert cache.get(keys[0]) is not None and cache.get(keys[2]) is not None
        cache.invalidate(paths[0])
        assert cache.get(keys[0]) is None
        assert cache.key(paths[0], 20, 1.0) != keys[0]
    finally:
        cache.pool.shutdown(wait=True, cancel_futures=True)
