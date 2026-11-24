import gc
import threading
import weakref

import pytest
from PIL import Image
from PIL.ImageQt import fromqimage
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview import qt_app, raster_view
from picview.editing import transform_image
from picview.raster_view import PyramidCache, RasterState, render_region
from test_tabs import browser, wait_until
from test_crop import move_drag
from test_editing import pattern, assert_saved


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("horizontal,vertical", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("mode", ["L", "RGBA"])
def test_viewport_pixels_match_native_edits(rotation, horizontal, vertical, mode):
    source = Image.new("RGBA", (64, 48))
    source.putdata([(x * 3, y * 4, (x + y) * 2, 255) for y in range(48) for x in range(64)])
    source = source.convert(mode)
    full = (48, 64) if rotation % 180 else (64, 48)
    box = (4, 6, full[0] - 4, full[1] - 6)
    canvas = box[2] - box[0], box[3] - box[1]
    state = RasterState(source, rotation, horizontal, vertical, box)
    result = fromqimage(render_region(state, canvas, (5, 7, 11, 13))).convert("RGBA")
    expected = transform_image(source, rotation, horizontal, vertical, box).crop((5, 7, 16, 20)).convert("RGBA")
    assert result.tobytes() == expected.tobytes()


def test_pyramid_budget_reuse_and_source_lifetime():
    cache = PyramidCache(1024)
    source = Image.new("L", (64, 64), 90)
    half = cache.level(source, 2)
    assert half.size == (32, 32) and cache.bytes_used == 1024
    assert cache.level(source, 2) is half
    quarter = cache.level(source, 4)
    assert quarter.size == (16, 16) and cache.bytes_used <= cache.max_bytes
    del source
    gc.collect()
    other = Image.new("L", (32, 32), 40)
    cache.level(other, 2)
    assert len(cache.images) == 1 and cache.bytes_used == 256
    assert cache.level(Image.new("RGBA", (100, 100)), 2).size == (100, 100)
    assert cache.bytes_used <= cache.max_bytes


@pytest.mark.parametrize("dpr", [1., 2.])
def test_tile_allocations_follow_viewport_not_canvas(dpr):
    source = Image.new("L", (100, 80), 120)
    state = RasterState(source, 0, False, False, (0, 0, 100, 80))
    image = render_region(state, (100000, 80000), (40000, 30000, 200, 150), dpr)
    assert (image.width(), image.height()) == (round(200 * dpr), round(150 * dpr))
    assert image.pixelColor(100, 100).red() == 120


def test_native_transparency_is_preserved_without_whole_source_conversion(monkeypatch):
    source = Image.new("RGBA", (100, 80), (93, 127, 211, 67))
    def forbidden(*args, **kwargs): raise AssertionError("Whole-source alpha conversion")
    monkeypatch.setattr(source, "convert", forbidden)
    state = RasterState(source, 0, False, False, (0, 0, 100, 80))
    image = render_region(state, (100, 80), (30, 20, 10, 10))
    color = image.pixelColor(5, 5)
    assert color.getRgb() == (93, 127, 211, 67)


def test_alpha_pyramid_strip_reduction_matches_pillow(monkeypatch):
    monkeypatch.setattr(raster_view, "REDUCTION_STRIP_PIXELS", 512)
    source = Image.new("RGBA", (111, 83))
    source.putdata([(x % 255, y % 255, 100, (x * y) % 255) for y in range(83) for x in range(111)])
    cache = PyramidCache()
    assert cache.level(source, 4).tobytes() == source.reduce(4).tobytes()


@pytest.fixture
def virtual_browser(browser, monkeypatch):
    monkeypatch.setattr(qt_app, "VIRTUAL_IMAGE_PIXELS", 1)
    return browser


def settled(label):
    view = label.raster_view
    return view is not None and view.tile is not None and view.future is None and not view.detail_timer.isActive()


def test_zoom_pan_uses_virtual_geometry_and_bounded_tiles(virtual_browser, monkeypatch):
    window, folders = virtual_browser
    pane = window.open_folder(folders[0]).image
    source = pane.frames[0][0]
    def forbidden(*args, **kwargs): raise AssertionError("Full-image resize on UI thread")
    monkeypatch.setattr(source, "resize", forbidden)
    pane.choose_zoom(4000)
    wait_until(lambda: settled(pane.label))
    view = pane.label.raster_view
    assert view.last_error is None
    assert view.canvas == (480, 320)
    pane.scroll.horizontalScrollBar().setValue(pane.scroll.horizontalScrollBar().maximum())
    wait_until(lambda: settled(pane.label))
    assert view.tile.width() <= (pane.scroll.viewport().width() + 96) * pane.devicePixelRatioF()
    assert view.tile.height() <= (pane.scroll.viewport().height() + 96) * pane.devicePixelRatioF()
    assert pane.image_size() == (120, 80) and not pane.is_modified
    assert pane.label.pixmap().isNull()


def test_slow_worker_does_not_block_ui_and_discards_obsolete_requests(virtual_browser, monkeypatch):
    window, folders = virtual_browser
    release, started = threading.Event(), threading.Event()
    original = raster_view.render_request
    calls = []
    def slow(*args):
        calls.append(args[1])
        started.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(raster_view, "render_request", slow)
    pane = window.open_folder(folders[0]).image
    try:
        wait_until(started.is_set)
        heartbeat = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        for zoom in (500, 1000, 2000, 3000, 4000): pane.choose_zoom(zoom)
        wait_until(lambda: heartbeat)
        QTest.qWait(180)
        assert len(calls) == 1
        assert pane.label.raster_view.pending is not None
        release.set()
        wait_until(lambda: settled(pane.label))
        view = pane.label.raster_view
        assert view.canvas == (480, 320) and view.running is None
        assert len(calls) == 2
        assert view.last_error is None
    finally:
        release.set()


def test_edit_overlays_fullscreen_comparison_and_source_switch(virtual_browser):
    window, folders = virtual_browser
    path = folders[0] / "image0.png"
    page = window.open_folder(folders[0], path)
    pane = page.image
    pane.choose_zoom(1000)
    wait_until(lambda: settled(pane.label))
    pane.crop_button.click()
    wait_until(lambda: settled(pane.label))
    label = pane.label
    start = label.handles()["l"].toPoint()
    end = start + QPoint(30, 0)
    QTest.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    move_drag(label, end)
    assert pane.image_size() == (90, 80)
    assert 60 <= label.grab().toImage().pixelColor(20, 35).alpha() <= 90
    QTest.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
    assert label.grab().toImage().pixelColor(20, 35).alpha() == 0
    pane.undo()
    pane.crop_button.click()
    pane.open_full()
    wait_until(lambda: pane.full_window is not None and settled(pane.full_window.image_label))
    assert pane.full_window.image_label.raster_view.state.source is pane.frames[0][0]
    pane.open_full()
    window.set_compare(True)
    window.open_comparison_fullscreen()
    wait_until(lambda: window.compare_full_window is not None)
    full = window.compare_full_window
    wait_until(lambda: settled(full.labels[page]))
    full.close()
    window.set_compare(False)
    Image.new("RGB", (120, 80), "blue").save(folders[0] / "blue.png")
    pane.load(folders[0] / "blue.png")
    wait_until(lambda: settled(pane.label))
    assert pane.label.raster_view.tile.pixelColor(5, 5).blue() == 255
    pane.clear()
    assert not pane.label.raster_view.active


def test_virtual_edit_tools_save_native_pixels_and_undo(virtual_browser):
    window, folders = virtual_browser
    path = folders[0] / "image0.png"
    pattern(path)
    pane = window.open_folder(folders[0], path).image
    original = pane.image().copy()
    pane.choose_zoom(2000)
    wait_until(lambda: settled(pane.label))
    pane.mosaic_button.click()
    QTest.mousePress(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(40, 32))
    move_drag(pane.label, QPoint(200, 128))
    QTest.mouseRelease(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(200, 128))
    mosaic = pane.image().copy()
    assert mosaic.size == original.size and mosaic.tobytes() != original.tobytes()
    assert mosaic.crop((0, 0, 20, 80)).tobytes() == original.crop((0, 0, 20, 80)).tobytes()
    pane.splice_button.click()
    QTest.mousePress(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(40, 20))
    move_drag(pane.label, QPoint(80, 24))
    QTest.mouseRelease(pane.label, Qt.MouseButton.LeftButton, pos=QPoint(80, 24))
    assert pane.image_size() == (100, 80)
    expected = Image.new("RGBA", (100, 80))
    expected.paste(mosaic.crop((0, 0, 20, 80)), (0, 0))
    expected.paste(mosaic.crop((40, 0, 120, 80)), (20, 0))
    assert pane.image().tobytes() == expected.tobytes()
    target = folders[0] / "virtual-edited.png"
    assert pane.save_to(target)
    assert_saved(target, expected)
    pane.undo()
    assert pane.image().tobytes() == mosaic.tobytes()
    pane.undo()
    assert pane.image().tobytes() == original.tobytes()


def test_clearing_view_releases_native_source(virtual_browser):
    window, folders = virtual_browser
    pane = window.open_folder(folders[0]).image
    wait_until(lambda: settled(pane.label))
    reference = weakref.ref(pane.frames[0][0])
    pane.clear()
    QApplication.processEvents()
    gc.collect()
    assert reference() is None
