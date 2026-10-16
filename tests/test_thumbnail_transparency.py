import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from picview import qt_app
from test_tabs import browser, wait_until


@pytest.mark.parametrize("mode", ["RGBA", "P"])
def test_transparent_thumbnail_uses_card_background_in_all_states(browser, mode):
    window, folders = browser
    path = folders[0] / "image0.png"
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 20, 100, 60), fill="red")
    if mode == "P": image = image.convert("P", palette=Image.Palette.ADAPTIVE)
    image.save(path)
    page = window.open_folder(folders[0])
    for theme in ("light", "dark"):
        window.theme_mode = "system" if theme == "light" else "light"
        window.toggle_theme()
        for selected in (True, False):
            page.thumbs.select(page.files[0 if selected else 1])
            QTest.qWait(30)
            preview = page.thumbs.buttons[path].preview
            pixmap = preview.pixmap()
            assert pixmap.toImage().pixelColor(0, 0).alpha() == 0
            assert pixmap.toImage().pixelColor(60, 40).red() == 255
            point = preview.rect().center() - QPoint(pixmap.width() // 2, pixmap.height() // 2) + QPoint(2, 2)
            background = qt_app.PALETTE["selection"] if selected else qt_app.PALETTE["card"]
            assert preview.grab().toImage().pixelColor(point) == QColor(background)


def test_modified_thumbnail_keeps_full_and_partial_transparency(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    path = page.files[0]
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 20, 100, 60), fill=(0, 0, 255, 128))
    image.save(path)
    def updated():
        pixmap = page.thumbs.buttons[path].preview.pixmap().toImage()
        return pixmap.pixelColor(0, 0).alpha() == 0 and pixmap.pixelColor(60, 40).alpha() == 128
    wait_until(updated)
    wait_until(lambda: page.image.frames[0][0].getpixel((0, 0))[3] == 0)
