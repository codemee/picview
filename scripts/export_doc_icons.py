"""Export README button images from the application's icon painter.

Run with: uv run python scripts/export_doc_icons.py
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from picview.qt_app import IconButton, PALETTE, themed_palette, use_system_palette


ICONS = {
    "folder": "folder", "split-h": "split-h", "split-v": "split-v",
    "compare": "compare", "rotate": "rotate", "mirror-h": "mirror-h",
    "mirror-v": "mirror-v", "fit": "fit", "expand": "expand",
    "shrink": "shrink", "fullscreen": "fullscreen", "more": "more", "background": "background",
    "lang-system": "lang-system", "lang-zh": "中", "lang-en": "A",
    "theme-system": "theme-system", "theme-light": "theme-light",
    "theme-dark": "theme-dark",
}


class DocumentationButton(IconButton):
    def devicePixelRatioF(self):
        return 3.0


def main():
    app = QApplication.instance() or QApplication([])
    # The offscreen Windows plugin does not populate the system font database.
    if os.name == "nt":
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msjh.ttc"
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families: app.setFont(QFont(families[0], 9))
    metrics = QFontMetrics(app.font())
    if not all(metrics.inFontUcs4(ord(char)) for char in "中A"):
        raise RuntimeError("Install a font supporting Chinese and Latin before exporting documentation icons")
    system_palette = app.palette()
    output = Path(__file__).resolve().parents[1] / "docs" / "icons"
    output.mkdir(parents=True, exist_ok=True)
    for mode in ("light", "dark"):
        app.setPalette(themed_palette(system_palette, mode))
        use_system_palette(app)
        for name, kind in ICONS.items():
            button = DocumentationButton(kind, name)
            image = QImage(102, 102, QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(3)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(PALETTE["edge"]), 1))
            painter.setBrush(QColor(PALETTE["surface"]))
            painter.drawRoundedRect(QRectF(.5, .5, 33, 33), 6, 6)
            icon = button.icon().pixmap(60, 60)
            icon.setDevicePixelRatio(3)
            painter.drawPixmap(QPoint(7, 7), icon)
            painter.end()
            if not image.save(str(output / f"{name}-{mode}.png")):
                raise RuntimeError(f"Could not export {name} ({mode})")
            button.deleteLater()
    print(f"Exported {len(ICONS) * 2} icons to {output}")


if __name__ == "__main__":
    main()
