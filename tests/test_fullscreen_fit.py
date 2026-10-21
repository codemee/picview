import pytest
from PIL import Image
from PySide6.QtCore import QSize, Qt

from test_tabs import browser, wait_until
from test_svg import write_svg


def fits_screen(pane):
    label = pane.full_window.centralWidget()
    pixmap = label.pixmap()
    if pixmap.isNull(): return False
    original = QSize(*pane.image_size())
    expected = original.scaled(label.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio).boundedTo(original)
    logical = pixmap.deviceIndependentSize()
    return abs(logical.width() - expected.width()) <= 1 and abs(logical.height() - expected.height()) <= 1


@pytest.mark.parametrize("size,rotation", [((2400, 1600), 0), ((500, 1800), 90), ((20, 10), 0)])
def test_fullscreen_fits_large_portrait_and_small_images_without_changing_view(browser, size, rotation):
    window, folders = browser
    path = folders[0] / "full.png"
    Image.new("RGBA", size, (255, 0, 0, 128)).save(path)
    pane = window.open_folder(folders[0], path).image
    pane.choose_zoom(1500)
    if rotation: pane.rotate()
    pane.mirror_h()
    state = (pane.zoom, pane.fit_to_pane, pane.rotation, pane.fh, pane.fv)
    pane.open_full()
    wait_until(lambda: pane.full_window.isFullScreen() and fits_screen(pane))
    if size == (20, 10):
        assert pane.full_window.centralWidget().pixmap().deviceIndependentSize().toSize() == QSize(20, 10)
    assert pane.full_window.centralWidget().alignment() == Qt.AlignmentFlag.AlignCenter
    assert (pane.zoom, pane.fit_to_pane, pane.rotation, pane.fh, pane.fv) == state
    # A screen-size change must update the raster too, without a new image load.
    pane.full_window.setWindowState(Qt.WindowState.WindowNoState)
    pane.full_window.resize(640, 360)
    wait_until(lambda: pane.full_window.centralWidget().width() == 640 and fits_screen(pane))
    pane.open_full()
    assert pane.full_window is None
    assert (pane.zoom, pane.fit_to_pane, pane.rotation, pane.fh, pane.fv) == state


@pytest.mark.parametrize("svg", [False, True])
def test_fullscreen_fit_tracks_file_changes_and_device_pixel_ratio(browser, monkeypatch, svg):
    window, folders = browser
    path = folders[0] / ("full.svg" if svg else "full.png")
    if svg: write_svg(path)
    else: Image.new("RGB", (120, 80), "red").save(path)
    pane = window.open_folder(folders[0], path).image
    pane.open_full()
    wait_until(lambda: fits_screen(pane))
    label = pane.full_window.centralWidget()
    rendered = []
    set_pixmap = label.setPixmap

    def capture(pixmap):
        rendered.append((pixmap.size(), pixmap.devicePixelRatio()))
        set_pixmap(pixmap)

    monkeypatch.setattr(label, "setPixmap", capture)
    monkeypatch.setattr(label, "devicePixelRatioF", lambda: 2.0)
    pane.update_full_image()
    assert rendered[-1][1] == 2
    original_size = QSize(*pane.image_size())
    expected = original_size.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio).boundedTo(original_size)
    assert rendered[-1][0] == expected * 2
    assert fits_screen(pane)
    if svg: write_svg(path, "lime")
    else: Image.new("RGB", (80, 200), "blue").save(path)
    original = pane.frames
    wait_until(lambda: pane.frames is not original)
    wait_until(lambda: fits_screen(pane))
    pane.open_full()
