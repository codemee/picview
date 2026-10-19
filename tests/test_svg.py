import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from picview.svg import SvgDocument
from picview.utils import image_files
from test_tabs import browser, wait_until


def write_svg(path, color="red"):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><rect x="10" y="10" width="30" height="20" fill="{color}"/><circle cx="75" cy="55" r="10" fill="blue"/></svg>', encoding="utf-8")


def test_svg_thumbnail_zoom_transforms_and_fullscreen(browser):
    window, folders = browser
    path = folders[0] / "vector.SVG"
    write_svg(path)
    assert path in image_files(folders[0])
    page = window.open_folder(folders[0], path)
    wait_until(lambda: not page.thumbs.buttons[path].preview.pixmap().isNull())
    assert isinstance(page.image.frames[0][0], SvgDocument)
    assert not page.image.timer.isActive()
    assert not page.image.frames[0][0].renderer.isAnimationEnabled()
    assert page.thumbs.buttons[path].preview.pixmap().toImage().pixelColor(0, 0).alpha() == 0
    page.image.choose_zoom(2000)
    assert page.image.label.size().width() == 200
    pixmap = page.image.label.pixmap()
    assert pixmap.width() == round(200 * page.image.devicePixelRatioF())
    assert pixmap.toImage().pixelColor(round(40 * pixmap.devicePixelRatio()), round(30 * pixmap.devicePixelRatio())).red() == 255
    page.image.rotate()
    assert page.image.image_size() == (80, 100)
    assert page.image.label.width() == 160
    page.image.mirror_h()
    image = page.image.image()
    assert image.pixelColor(15, 20).red() == 255
    page.image.open_full()
    QTest.qWait(50)
    assert not page.image.full_window.centralWidget().pixmap().isNull()
    page.image.open_full()
    raster = page.files[0]
    page.thumbs.select(raster)
    assert not page.image.label.hasScaledContents()


def test_svg_live_reload_preserves_view_and_last_complete_document(browser):
    window, folders = browser
    path = folders[0] / "vector.svg"
    write_svg(path)
    page = window.open_folder(folders[0], path)
    page.image.choose_zoom(1500)
    page.image.rotate()
    original = page.image.frames[0][0]
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><', encoding="utf-8")
    assert not page.reload_current_image()
    assert page.image.frames[0][0] is original
    write_svg(path, "lime")
    wait_until(lambda: page.image.frames[0][0] is not original)
    wait_until(lambda: page.thumbs.buttons[path].preview.pixmap().toImage().pixelColor(28, 21).green() == 255)
    assert page.image.zoom == 1.5 and page.image.rotation == 90
    assert page.image.frames[0][0].render((100, 80)).pixelColor(20, 15).green() == 255


def test_svg_compare_independent_document_and_delete_notification(browser):
    window, folders = browser
    path = folders[0] / "vector.svg"
    write_svg(path)
    first = window.open_folder(folders[0], path)
    window.set_compare(True)
    second = window.duplicate_page(first)
    second.image.rotate()
    second.image.choose_zoom(2000)
    assert first.image.rotation == 0 and second.image.rotation == 90
    assert first.image.frames[0][0] is not second.image.frames[0][0]
    for orientation in (Qt.Orientation.Vertical, Qt.Orientation.Horizontal):
        window.set_orientation(orientation)
        QTest.qWait(30)
        assert all(not page.image.label.pixmap().isNull() for page in (first, second))
    path.unlink()
    wait_until(lambda: first.image.path != path and second.image.path != path)
    assert window.notification_bar.currentMessage()


def test_invalid_svg_and_large_intrinsic_dimensions(browser):
    window, folders = browser
    invalid = folders[0] / "broken.svg"
    invalid.write_text("not an svg", encoding="utf-8")
    with pytest.raises(ValueError): SvgDocument(invalid)
    page = window.open_folder(folders[0], invalid)
    wait_until(lambda: invalid in page.thumbs.failed_paths)
    assert not page.image.frames
    huge = folders[0] / "huge.svg"
    huge.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100000 100000"><rect width="100000" height="100000" fill="red"/></svg>', encoding="utf-8")
    document = SvgDocument(huge)
    image = document.render((100, 100))
    assert image.size().width() == 100 and image.pixelColor(50, 50).red() == 255
