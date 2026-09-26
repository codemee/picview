import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from picview.qt_app import IMAGE_BACKGROUND, PALETTE, THUMBNAIL_SELECTED, PicView


def test_original_size_navigation_and_file_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folder = tmp_path / "images"
    folder.mkdir()
    paths = [folder / f"image{i}.png" for i in range(3)]
    for index, path in enumerate(paths):
        Image.new("RGB", (200, 100) if index == 1 else (1200, 800), "red").save(path)

    app = QApplication.instance() or QApplication([])
    window = PicView()
    app.paletteChanged.connect(window.refresh_system_theme)
    window.show()
    window.activateWindow()
    window.open_folder(folder)
    app.processEvents()

    toolbar = window.image.layout().itemAt(0).layout()
    widgets = [toolbar.itemAt(i).widget() for i in range(toolbar.count()) if toolbar.itemAt(i).widget()]
    assert widgets[:3] == [window.image.rotate_b, window.image.mh, window.image.mv]
    assert widgets[3].width() == 1
    assert widgets[4:7] == [window.image.fit_b, window.image.max_button, window.image.full]
    assert widgets[-3:] == [window.image.filename_label, window.image.zoom_label, window.image.slider]
    assert window.image.slider.width() == window.thumbs.slider.width()
    for slider in (window.image.slider, window.thumbs.slider):
        assert abs(slider.reference_x() - slider.width() / 2) <= 2
        assert slider.height() == 30
    thumbnail_toolbar = window.thumbs.layout().itemAt(0).layout()
    assert thumbnail_toolbar.itemAt(thumbnail_toolbar.count() - 2).widget() is window.thumbs.size_label
    assert window.thumbs.size_label.text() == "140px"
    window.thumbs.size_label.click()
    window.thumbs.size_label.spin.selectAll()
    QTest.keyClicks(window.thumbs.size_label.spin, "190")
    QTest.keyClick(window.thumbs.size_label.spin, Qt.Key.Key_Escape)
    assert not window.thumbs.size_label.editor_menu.isVisible()
    assert window.thumbs.slider.value() == 140
    window.thumbs.size_label.click()
    window.thumbs.size_label.spin.selectAll()
    QTest.keyClicks(window.thumbs.size_label.spin, "200")
    window.thumbs.size_label.editor_menu.hide()
    app.processEvents()
    assert window.thumbs.slider.value() == 140
    window.thumbs.slider.setValue(72)
    assert window.thumbs.slider.sliderPosition() == 0
    window.thumbs.slider.setValue(260)
    assert window.thumbs.slider.sliderPosition() == window.thumbs.slider.HALF_RANGE * 2
    window.thumbs.slider.setValue(210)
    assert window.thumbs.size_label.text() == "210px"
    window.thumbs.size_label.click()
    assert window.thumbs.size_label.editor_menu.isVisible()
    window.thumbs.size_label.spin.selectAll()
    QTest.keyClicks(window.thumbs.size_label.spin, "180")
    QTest.keyClick(window.thumbs.size_label.spin, Qt.Key.Key_Return)
    assert window.thumbs.slider.value() == 180
    window.thumbs.size_label.click()
    window.thumbs.size_label.reset_button.click()
    assert window.thumbs.slider.value() == 140
    assert window.thumbs.slider.sliderPosition() == window.thumbs.slider.HALF_RANGE
    assert window.thumbs.size_label.text() == "140px"
    assert window.image.filename_label.text() == "image0.png"
    assert window.image.fit_b.isChecked()
    assert PALETTE["accent"] == THUMBNAIL_SELECTED
    assert IMAGE_BACKGROUND in window.image.scroll.viewport().styleSheet()
    assert window.image.scroll.viewport().grab().toImage().pixelColor(2, 2).name() == IMAGE_BACKGROUND
    assert IMAGE_BACKGROUND in window.thumbs.grid_host.styleSheet()
    grid_image = window.thumbs.grid_host.grab().toImage()
    thumbnail_background = grid_image.pixelColor(grid_image.width() - 2, grid_image.height() - 2)
    expected_background = QColor(IMAGE_BACKGROUND)
    assert all(abs(a - b) <= 1 for a, b in zip(thumbnail_background.getRgb()[:3], expected_background.getRgb()[:3]))
    assert THUMBNAIL_SELECTED in window.thumbs.buttons[paths[0]].styleSheet()
    assert "border:0" in window.thumbs.buttons[paths[0]].styleSheet()
    assert window.thumbs.buttons[paths[0]].name.grab().toImage().pixelColor(2, 2).name() == THUMBNAIL_SELECTED
    assert "#toolbar{background:transparent;border:0;}" in window.styleSheet()
    assert f"#card{{background:{PALETTE['card']};border:0;border-radius:12px;}}" in window.styleSheet()
    assert PALETTE["accent"] in window.image.fit_b.styleSheet()
    assert PALETTE["accent"] in window.styleSheet()
    checked_icon = window.image.fit_b.icon().pixmap(window.image.fit_b.iconSize()).toImage()
    assert any(
        checked_icon.pixelColor(x, y).alpha() and checked_icon.pixelColor(x, y).name() == "#ffffff"
        for x in range(checked_icon.width()) for y in range(checked_icon.height())
    )
    assert window.image.slider.value() < 1000
    assert window.image.label.pixmap().width() <= window.image.scroll.viewport().width()
    assert window.image.label.pixmap().height() <= window.image.scroll.viewport().height()
    window.image.fit_b.click()
    assert window.image.zoom_label.text() == "100%"
    assert window.image.slider.sliderPosition() == window.image.slider.HALF_RANGE
    assert window.image.label.pixmap().size().width() == 1200
    assert window.image.label.pixmap().size().height() == 800
    window.image.fit_b.click()
    app.processEvents()
    assert window.image.fit_b.isChecked()
    fit_ticks = window.image.slider.value()
    assert fit_ticks == max(1, round(window.image.display_scale * 1000))
    assert fit_ticks < 1000
    assert window.image.slider.isEnabled()
    assert window.image.label.pixmap().width() <= window.image.scroll.viewport().width()
    assert window.image.label.pixmap().height() <= window.image.scroll.viewport().height()
    assert window.image.label.pixmap().width() < 1200
    window.image.fit_b.click()
    assert not window.image.fit_b.isChecked()
    assert window.image.slider.value() == 1000
    assert window.image.zoom_label.text() == "100%"
    assert window.image.label.pixmap().width() == 1200
    window.image.fit_b.click()
    app.processEvents()
    fit_ticks = window.image.slider.value()
    window.image.slider.setValue(fit_ticks + 100)
    assert not window.image.fit_b.isChecked()
    unchecked_icon = window.image.fit_b.icon().pixmap(window.image.fit_b.iconSize()).toImage()
    assert any(
        unchecked_icon.pixelColor(x, y).alpha() and unchecked_icon.pixelColor(x, y).name() == PALETTE["text"]
        for x in range(unchecked_icon.width()) for y in range(unchecked_icon.height())
    )
    assert window.image.label.pixmap().width() == round(1200 * (fit_ticks + 100) / 1000)
    window.image.fit_b.click()
    app.processEvents()
    fit_ticks = window.image.slider.value()
    window.image.adjust_zoom(10)
    assert not window.image.fit_b.isChecked()
    assert window.image.slider.value() == fit_ticks + 100
    window.image.fit_b.click()
    QTest.keyClick(window, Qt.Key.Key_0)
    assert not window.image.fit_b.isChecked()
    assert window.image.slider.value() == 1000
    assert window.image.label.pixmap().size().width() == 1200
    QTest.keyClick(window, Qt.Key.Key_Minus)
    assert window.image.zoom_label.text() == "90%"
    assert window.image.label.pixmap().size().width() == 1080
    QTest.keyClick(window, Qt.Key.Key_0)
    assert window.image.label.pixmap().size().width() == 1200
    window.image.zoom_label.click()
    assert window.image.zoom_label.editor_menu.isVisible()
    window.image.zoom_label.spin.selectAll()
    QTest.keyClicks(window.image.zoom_label.spin, "125")
    QTest.keyClick(window.image.zoom_label.spin, Qt.Key.Key_Return)
    assert window.image.slider.value() == 1250
    assert window.image.zoom_label.text() == "125%"
    window.image.zoom_label.click()
    window.image.zoom_label.reset_button.click()
    assert window.image.slider.value() == 1000
    assert window.image.zoom_label.text() == "100%"

    QTest.keyClick(window, Qt.Key.Key_Right)
    assert window.thumbs.selected_path == paths[1]
    assert window.image.filename_label.text() == "image1.png"
    assert not window.image.fit_b.isChecked()
    assert window.image.zoom_label.text() == "100%"
    assert window.image.label.pixmap().width() == 200
    QTest.keyClick(window, Qt.Key.Key_End)
    assert window.thumbs.selected_path == paths[2]
    assert window.image.filename_label.text() == "image2.png"
    assert window.image.fit_b.isChecked()
    QTest.keyClick(window, Qt.Key.Key_Home)
    assert window.thumbs.selected_path == paths[0]
    QTest.keyClick(window, Qt.Key.Key_Left)
    assert window.thumbs.selected_path == paths[0]

    QTest.keyClick(window, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert Path(QApplication.clipboard().mimeData().urls()[0].toLocalFile()) == paths[0]

    assert window.theme_mode == "system"
    window.toggle_theme()
    app.processEvents()
    assert window.theme_mode == "light"
    assert window.theme_button.kind == "theme-light"
    assert window.thumbs.selected_path == paths[0]
    QTest.keyClick(window, Qt.Key.Key_Right)
    assert window.thumbs.selected_path == paths[1]
    window.toggle_theme()
    app.processEvents()
    assert window.theme_mode == "dark"
    assert PALETTE["pane"] != IMAGE_BACKGROUND
    assert PALETTE["pane"] in window.image.scroll.viewport().styleSheet()
    assert window.thumbs.selected_path == paths[1]
    window.toggle_theme()
    app.processEvents()
    assert window.theme_mode == "system"
    assert window.theme_button.kind == "theme-system"
    assert window.thumbs.selected_path == paths[1]

    empty_folder = tmp_path / "empty"
    empty_folder.mkdir()
    window.open_folder(empty_folder)
    assert window.image.filename_label.text() == ""

    QApplication.clipboard().clear()
    app.paletteChanged.disconnect(window.refresh_system_theme)
    window.close()
    window.deleteLater()
    app.processEvents()
