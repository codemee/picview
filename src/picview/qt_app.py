from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QEvent, QFileSystemWatcher, QLocale, QMimeData, QPoint, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygon, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QMainWindow,
    QMenu, QPushButton, QScrollArea, QSlider, QSplitter, QStackedWidget, QTabBar, QStyle, QStyleOptionSlider, QStyleOptionTab, QToolButton, QVBoxLayout, QWidget, QWidgetAction, QSizePolicy,
)

from . import __version__
from .settings import load_settings, normalize_tab_state, save_settings
from .utils import IMAGE_SUFFIXES, image_files, natural_key


IMAGE_BACKGROUND = "#e9edf2"
DARK_IMAGE_BACKGROUND = "#303a47"
THUMBNAIL_SELECTED = "#6ec8ff"
PALETTE = {"surface": "#f4f7f8", "card": "#ffffff", "edge": "#c7d3d8", "accent": THUMBNAIL_SELECTED, "text": "#172a31", "muted": "#526a73", "pane": IMAGE_BACKGROUND}
SLIDER_WIDTH = 160
THUMBNAIL_BASE_SIZE = 140


def use_system_palette(app: QApplication) -> None:
    """Use the system palette for surfaces and text while keeping the blue accent."""
    pal = app.palette()
    PALETTE.update({
        "surface": pal.color(QPalette.ColorRole.Window).name(),
        "card": pal.color(QPalette.ColorRole.Base).name(),
        "edge": pal.color(QPalette.ColorRole.Mid).name(),
        "text": pal.color(QPalette.ColorRole.Text).name(),
        "muted": pal.color(QPalette.ColorRole.PlaceholderText).name(),
        "pane": DARK_IMAGE_BACKGROUND if pal.color(QPalette.ColorRole.Window).lightness() < 128 else IMAGE_BACKGROUND,
    })


def themed_palette(system_palette: QPalette, mode: str) -> QPalette:
    palette = QPalette(system_palette)
    if mode == "system":
        return palette
    if mode == "dark":
        colors = {
            QPalette.ColorRole.Window: "#202833",
            QPalette.ColorRole.Base: "#293442",
            QPalette.ColorRole.AlternateBase: "#303d4c",
            QPalette.ColorRole.Text: "#edf3f8",
            QPalette.ColorRole.WindowText: "#edf3f8",
            QPalette.ColorRole.Button: "#293442",
            QPalette.ColorRole.ButtonText: "#edf3f8",
            QPalette.ColorRole.PlaceholderText: "#aab9c7",
            QPalette.ColorRole.Mid: "#536477",
        }
    else:
        colors = {
            QPalette.ColorRole.Window: "#f4f7fa",
            QPalette.ColorRole.Base: "#ffffff",
            QPalette.ColorRole.AlternateBase: "#e9edf2",
            QPalette.ColorRole.Text: "#172a31",
            QPalette.ColorRole.WindowText: "#172a31",
            QPalette.ColorRole.Button: "#ffffff",
            QPalette.ColorRole.ButtonText: "#172a31",
            QPalette.ColorRole.PlaceholderText: "#526a73",
            QPalette.ColorRole.Mid: "#c7d3d8",
        }
    colors[QPalette.ColorRole.Highlight] = THUMBNAIL_SELECTED
    colors[QPalette.ColorRole.HighlightedText] = "#153047"
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    return palette

TEXT = {
    "en": {"open": "Open folder", "vertical": "Top / bottom", "horizontal": "Left / right", "lang": "中文", "theme_system": "Theme: follow system (click to switch)", "theme_light": "Theme: light (click to switch)", "theme_dark": "Theme: dark (click to switch)", "thumb": "Thumbnails", "max": "Maximize pane", "restore": "Restore panes", "rotate": "Rotate clockwise", "mh": "Mirror horizontally", "mv": "Mirror vertically", "fit": "Fit to pane", "full": "Full screen", "zoom": "Zoom", "edit_zoom": "Edit zoom", "edit_thumb": "Edit thumbnail size", "apply": "Apply", "empty": "Open a folder to view images"},
    "zh": {"open": "開啟資料夾", "vertical": "上下窗格", "horizontal": "左右窗格", "lang": "En", "theme_system": "配色：跟隨系統（點擊切換）", "theme_light": "配色：淺色（點擊切換）", "theme_dark": "配色：深色（點擊切換）", "thumb": "縮圖", "max": "最大化窗格", "restore": "還原窗格", "rotate": "順時針旋轉", "mh": "水平鏡射", "mv": "垂直鏡射", "fit": "符合窗格", "full": "全螢幕", "zoom": "縮放", "edit_zoom": "編輯顯示比例", "edit_thumb": "編輯縮圖大小", "apply": "套用", "empty": "開啟資料夾以檢視圖片"},
}

LANGUAGE_MODES = ("system", "zh", "en")
LANGUAGE_ICONS = {"system": "lang-system", "zh": "中", "en": "En"}
TEXT["en"].update({
    "compare": "Compare images", "compare_folder": "Compare this folder", "compare_empty": "Check folder tabs to compare images", "image_tools": "Image tools",
    "close_tab": "Close tab",
    "new_tab": "Open folder in a new tab", "empty_tab": "New tab", "folder_missing": "Folder unavailable; waiting for it to return", "duplicate_tab": "Duplicate tab",
    "image_deleted": "The image being viewed was deleted: {name}. Now viewing {next}.",
    "image_deleted_empty": "The image being viewed was deleted: {name}. No images remain in this folder.",
    "lang_system": "Language: follow system (click to switch)",
    "lang_zh": "Language: Chinese (click to switch)",
    "lang_en": "Language: English (click to switch)",
})
TEXT["zh"].update({
    "compare": "比圖", "compare_folder": "勾選此資料夾進行比圖", "compare_empty": "勾選資料夾標籤以比較圖片", "image_tools": "圖片工具",
    "close_tab": "關閉標籤",
    "new_tab": "在新標籤開啟資料夾", "empty_tab": "新標籤", "folder_missing": "資料夾不存在，等待重新連線", "duplicate_tab": "複製標籤",
    "image_deleted": "正在檢視的圖片已被刪除：{name}。已切換至 {next}。",
    "image_deleted_empty": "正在檢視的圖片已被刪除：{name}。資料夾中已沒有圖片。",
    "lang_system": "語言：跟隨系統（點擊切換）",
    "lang_zh": "語言：中文（點擊切換）",
    "lang_en": "語言：英文（點擊切換）",
})


def resolve_language(mode: str) -> str:
    if mode == "system":
        return "zh" if QLocale.system().language() == QLocale.Language.Chinese else "en"
    return mode


def qimage(image: Image.Image) -> QImage:
    image = image.convert("RGBA")
    return QImage(image.tobytes(), image.width, image.height, QImage.Format.Format_RGBA8888).copy()


class IconButton(QToolButton):
    """Compact, frameless vector icon button."""
    def __init__(self, icon: str, tip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = icon
        self.setToolTip(tip); self.setFixedSize(30, 30); self.setIconSize(self.size())
        self.setStyleSheet(f"QToolButton{{background:transparent;border:0;border-radius:6px;}}QToolButton:hover{{background:rgba(110,200,255,36);border-radius:6px;}}QToolButton:pressed{{background:rgba(110,200,255,62);border-radius:6px;}}QToolButton:checked{{background:{PALETTE['accent']};border-radius:6px;}}")
        self.toggled.connect(lambda _checked: self.refresh_icon())
        self.refresh_icon()

    def set_kind(self, icon: str, tip: str) -> None:
        self.kind = icon; self.setToolTip(tip); self.refresh_icon()

    def refresh_icon(self) -> None:
        icon_size = self.iconSize().width()
        pixel_size = round(icon_size * self.devicePixelRatioF())
        pm = QPixmap(pixel_size, pixel_size)
        pm.setDevicePixelRatio(pixel_size / icon_size)
        pm.fill(Qt.GlobalColor.transparent)
        icon_color = QColor("#ffffff" if self.isChecked() else PALETTE["text"])
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(QPen(icon_color, 1))
        p.translate(-3.5, -3.5)
        r = 9, 9, 18, 18
        if self.kind == "folder":
            back = QPainterPath()
            back.moveTo(9, 25)
            back.lineTo(9, 12)
            back.quadTo(9, 11, 10, 11)
            back.lineTo(15, 11)
            back.lineTo(17, 14)
            back.lineTo(25, 14)
            back.quadTo(26, 14, 26, 15)
            back.lineTo(26, 17)
            p.drawPath(back)
            p.drawPolygon(QPolygon([QPoint(9,25), QPoint(12,17), QPoint(28,17), QPoint(25,25)]))
        elif self.kind.startswith("split"):
            p.drawRect(9, 11, 18, 14); p.drawLine(18, 12, 18, 24) if self.kind == "split-v" else p.drawLine(10, 18, 26, 18)
        elif self.kind == "rotate":
            p.drawArc(*r, 40 * 16, 285 * 16); p.drawLine(26, 9, 27, 15); p.drawLine(27, 15, 21, 12)
        elif self.kind in {"mirror-h", "mirror-v"}:
            p.setBrush(Qt.BrushStyle.NoBrush)
            if self.kind == "mirror-h":
                p.setPen(QPen(icon_color, 1, Qt.PenStyle.DashLine)); p.drawLine(18, 9, 18, 27)
                p.setPen(QPen(icon_color, 1)); p.drawPolygon(QPolygon([QPoint(9,25),QPoint(15,12),QPoint(15,25)])); p.drawPolygon(QPolygon([QPoint(27,25),QPoint(21,12),QPoint(21,25)]))
            else:
                p.setPen(QPen(icon_color, 1, Qt.PenStyle.DashLine)); p.drawLine(9, 18, 27, 18)
                p.setPen(QPen(icon_color, 1)); p.drawPolygon(QPolygon([QPoint(12,9),QPoint(25,15),QPoint(12,15)])); p.drawPolygon(QPolygon([QPoint(12,27),QPoint(25,21),QPoint(12,21)]))
        elif self.kind in {"expand", "shrink"}:
            p.drawRect(9, 9, 18, 18)
            if self.kind == "expand": p.drawLine(15,15,10,10); p.drawLine(10,10,14,10); p.drawLine(10,10,10,14); p.drawLine(21,21,26,26); p.drawLine(26,26,22,26); p.drawLine(26,26,26,22)
            else: p.drawLine(10,10,15,15); p.drawLine(15,15,11,15); p.drawLine(15,15,15,11); p.drawLine(26,26,21,21); p.drawLine(21,21,25,21); p.drawLine(21,21,21,25)
        elif self.kind == "fit":
            p.drawRect(9, 9, 18, 18); p.drawRect(13, 14, 10, 8)
        elif self.kind == "more":
            p.setBrush(icon_color)
            for x in (12, 18, 24): p.drawEllipse(QPoint(x, 18), 1, 1)
        elif self.kind == "compare":
            p.drawRoundedRect(QRectF(6, 9, 25, 18), 2, 2)
            for x in (8, 20):
                p.drawRoundedRect(QRectF(x, 12, 9, 12), 1, 1)
                landscape = QPainterPath()
                landscape.moveTo(x + 1, 22)
                landscape.lineTo(x + 3, 19)
                landscape.lineTo(x + 5, 21)
                landscape.lineTo(x + 7, 18)
                landscape.lineTo(x + 8, 20)
                p.drawPath(landscape)
                p.drawEllipse(QRectF(x + 2, 15, 1.5, 1.5))
        elif self.kind == "fullscreen":
            for x,y,dx,dy in ((9,9,1,1),(27,9,-1,1),(9,27,1,-1),(27,27,-1,-1)): p.drawLine(x,y,x+6*dx,y); p.drawLine(x,y,x,y+6*dy)
        elif self.kind == "lang-system":
            p.drawLine(24, 10, 12, 26)
            for glyph, x, y in ((LANGUAGE_ICONS["zh"], 13, 12), (LANGUAGE_ICONS["en"], 24, 24)):
                p.save()
                p.translate(x, y)
                p.scale(0.65, 0.65)
                p.drawText(-18, -18, 36, 36, Qt.AlignmentFlag.AlignCenter, glyph)
                p.restore()
        elif self.kind == "theme-system":
            moon = QPainterPath()
            moon.moveTo(15, 9)
            moon.cubicTo(12, 9, 10, 11, 10, 13)
            moon.cubicTo(10, 15, 12, 17, 15, 16)
            moon.cubicTo(12, 15, 12, 12, 15, 9)
            p.drawPath(moon)
            p.drawLine(24, 10, 12, 26)
            p.drawEllipse(22, 22, 3, 3)
            for x1,y1,x2,y2 in ((23,20,23,21),(23,26,23,27),(20,23,21,23),(26,23,27,23),(20,20,21,21),(26,26,27,27),(20,27,21,26),(26,21,27,20)):
                p.drawLine(x1,y1,x2,y2)
        elif self.kind == "theme-light":
            p.drawEllipse(14, 14, 8, 8)
            for x1,y1,x2,y2 in ((18,9,18,12),(18,24,18,27),(9,18,12,18),(24,18,27,18),(11,11,13,13),(23,23,25,25),(11,25,13,23),(23,13,25,11)):
                p.drawLine(x1,y1,x2,y2)
        elif self.kind == "theme-dark":
            p.drawArc(10, 9, 17, 18, 65 * 16, 265 * 16)
            p.drawArc(15, 7, 12, 18, 120 * 16, 150 * 16)
        else:
            p.drawText(0, 0, 36, 36, Qt.AlignmentFlag.AlignCenter, self.kind)
        p.end(); self.setIcon(QIcon(pm))


class ReferenceSlider(QSlider):
    """Slider whose reference value stays centered while both ranges remain available."""
    logicalValueChanged = Signal(int)
    HALF_RANGE = 100_000

    def __init__(self, orientation, reference_value, parent=None):
        super().__init__(orientation, parent)
        self.reference_value = reference_value
        self._logical_minimum = reference_value - 1
        self._logical_maximum = reference_value + 1
        super().setRange(0, self.HALF_RANGE * 2)
        super().setValue(self.HALF_RANGE)
        self.setSingleStep(1_000)
        self.setPageStep(10_000)
        self.valueChanged.connect(lambda _position: self.logicalValueChanged.emit(self.value()))

    def setRange(self, minimum, maximum):
        current = self.value()
        self._logical_minimum = minimum
        self._logical_maximum = maximum
        self.setValue(current)

    def setMinimum(self, minimum):
        self.setRange(minimum, self._logical_maximum)

    def setMaximum(self, maximum):
        self.setRange(self._logical_minimum, maximum)

    def minimum(self):
        return self._logical_minimum

    def maximum(self):
        return self._logical_maximum

    def setValue(self, value):
        value = max(self.minimum(), min(self.maximum(), value))
        if value <= self.reference_value:
            position = round((value - self.minimum()) * self.HALF_RANGE / (self.reference_value - self.minimum()))
        else:
            position = self.HALF_RANGE + round((value - self.reference_value) * self.HALF_RANGE / (self.maximum() - self.reference_value))
        super().setValue(position)

    def value(self):
        position = super().value()
        if position <= self.HALF_RANGE:
            return self.minimum() + round(position * (self.reference_value - self.minimum()) / self.HALF_RANGE)
        return self.reference_value + round((position - self.HALF_RANGE) * (self.maximum() - self.reference_value) / self.HALF_RANGE)

    def reference_x(self) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        travel = max(0, groove.width() - handle.width())
        return groove.x() + self.style().sliderPositionFromValue(0, self.HALF_RANGE * 2, self.HALF_RANGE, travel) + handle.width() // 2

class ScaleValueButton(QToolButton):
    """The slider value opens a compact editor with a reference reset button."""
    valueChosen = Signal(int)

    def __init__(self, value: int, minimum: int, maximum: int, reference: int,
                 divisor: int, suffix: str, tip: str, parent=None):
        super().__init__(parent)
        self.divisor = divisor
        self.suffix = suffix
        self.current_value = value
        self.setFixedHeight(30)
        self.setMinimumWidth(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        self.setStyleSheet("QToolButton{background:transparent;border:0;border-radius:6px;padding:0 3px;}QToolButton:hover{background:rgba(110,200,255,36);}")

        self.editor_menu = QMenu(self)
        editor = QWidget(self.editor_menu)
        row = QHBoxLayout(editor)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        self.spin = QDoubleSpinBox(editor)
        self.spin.setDecimals(0 if divisor == 1 else 1)
        self.spin.setRange(minimum / divisor, maximum / divisor)
        self.spin.setSingleStep(1 if divisor == 1 else 10)
        self.spin.setSuffix(suffix)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(88)
        row.addWidget(self.spin)
        self.reset_button = QPushButton(self._format(reference), editor)
        row.addWidget(self.reset_button)
        action = QWidgetAction(self.editor_menu)
        action.setDefaultWidget(editor)
        self.editor_menu.addAction(action)
        self.clicked.connect(self.open_editor)
        self.spin.lineEdit().returnPressed.connect(self.apply_value)
        self.reset_button.clicked.connect(lambda: self.choose(reference))
        self.set_value(value)

    def _format(self, value: int) -> str:
        return f"{value / self.divisor:g}{self.suffix}"

    def set_value(self, value: int) -> None:
        self.current_value = value
        self.setText(self._format(value))
        if not self.editor_menu.isVisible():
            self.spin.setValue(value / self.divisor)

    def open_editor(self) -> None:
        self.spin.setValue(self.current_value / self.divisor)
        self.editor_menu.popup(self.mapToGlobal(QPoint(0, self.height())))
        QTimer.singleShot(0, self.spin.setFocus)

    def choose(self, value: int) -> None:
        self.valueChosen.emit(value)
        self.editor_menu.hide()

    def apply_value(self) -> None:
        self.spin.interpretText()
        self.choose(round(self.spin.value() * self.divisor))


class ThumbnailTile(QFrame):
    """A uniform two-row thumbnail card: filename always precedes image."""
    clicked_path = Signal(Path)
    def __init__(self, path: Path, pixmap: QPixmap | None, size: int, selected: bool) -> None:
        super().__init__(); self.path = path; self.selected = selected; self.setFixedSize(size + 12, size + 38)
        self._drag_start = None
        layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5); layout.setSpacing(2)
        self.name = QLabel(path.name); self.name.setAlignment(Qt.AlignmentFlag.AlignCenter); self.name.setFixedHeight(20); self.name.setWordWrap(False)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setFixedHeight(size)
        for label in (self.name, self.preview):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if pixmap: self.preview.setPixmap(pixmap)
        layout.addWidget(self.name); layout.addWidget(self.preview); self.apply_style()
    def apply_style(self) -> None:
        color = THUMBNAIL_SELECTED if self.selected else PALETTE["card"]
        text = "#153047" if self.selected else PALETTE["text"]
        self.setStyleSheet(f"ThumbnailTile{{background:{color};border:0;border-radius:9px;}} QLabel{{background:{color};color:{text};}}")
    def mousePressEvent(self, event):
        self._drag_start = None
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.clicked_path.emit(self.path)
            event.accept()
            return
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._drag_start).manhattanLength() >= QApplication.startDragDistance():
                self._drag_start = None
                if self.path.is_file():
                    # Keep the drag source alive if a folder update rebuilds the tiles.
                    drag = QDrag(self.window())
                    data = QMimeData()
                    data.setUrls([QUrl.fromLocalFile(str(self.path.resolve()))])
                    drag.setMimeData(data)
                    pixmap = self.preview.pixmap()
                    if pixmap is not None and not pixmap.isNull():
                        pixmap = pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        drag.setPixmap(pixmap)
                        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
                    drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
            event.accept()
            return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)


class ThumbnailPane(QFrame):
    selected = Signal(Path)
    def __init__(self, labels: dict[str, str], parent=None):
        super().__init__(parent); self.labels=labels; self.files=[]; self.selected_path=None; self.size=THUMBNAIL_BASE_SIZE; self.buttons={}; self.failed_paths=set()
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,6,10,8)
        header=QHBoxLayout(); self.max_button=IconButton("expand",labels["max"]); header.addWidget(self.max_button); header.addStretch(); self.size_label=ScaleValueButton(self.size,72,260,THUMBNAIL_BASE_SIZE,1,"px",labels["edit_thumb"]); header.addWidget(self.size_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,THUMBNAIL_BASE_SIZE); self.slider.setRange(72,260); self.slider.setValue(self.size); self.slider.setFixedSize(SLIDER_WIDTH,30); self.slider.logicalValueChanged.connect(self._resize); self.size_label.valueChosen.connect(self.slider.setValue); header.addWidget(self.slider); layout.addLayout(header)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.grid_host=QWidget(); self.grid_host.setObjectName("thumbnailGrid"); self.grid_host.setStyleSheet(f"#thumbnailGrid{{background:{PALETTE['pane']};}}"); self.grid=QGridLayout(self.grid_host); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft); self.scroll.setWidget(self.grid_host); layout.addWidget(self.scroll)
    def set_files(self, files, selected=None, *, emit_selection=True):
        self.files=files; self.selected_path=selected if selected in files else (files[0] if files else None); self.build()
        if emit_selection and self.selected_path: self.selected.emit(self.selected_path)
    def _resize(self,v): self.size=v; self.size_label.set_value(v); self.build()
    def build(self):
        while self.grid.count(): item=self.grid.takeAt(0); item.widget().deleteLater() if item.widget() else None
        cols=max(1,self.scroll.viewport().width()//(self.size+20)); self.buttons={}; self.failed_paths=set()
        for i,path in enumerate(self.files):
            try:
                with Image.open(path) as im: im=ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((self.size,self.size)); pix=QPixmap.fromImage(qimage(im.copy()))
                b=ThumbnailTile(path, pix, self.size, path == self.selected_path)
            except Exception:
                self.failed_paths.add(path)
                b=ThumbnailTile(path, None, self.size, path == self.selected_path)
            b.clicked_path.connect(self.select)
            self.grid.addWidget(b,i//cols,i%cols); self.buttons[path]=b
    def resizeEvent(self,event): super().resizeEvent(event); QTimer.singleShot(0,self.build)
    def refresh_previews(self, paths):
        completed = set()
        for path in paths:
            if path not in self.buttons: continue
            try:
                with Image.open(path) as image:
                    image=ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((self.size, self.size))
                    pixmap=QPixmap.fromImage(qimage(image.copy()))
            except Exception:
                self.failed_paths.add(path)
                continue
            self.buttons[path].preview.setPixmap(pixmap)
            self.failed_paths.discard(path)
            completed.add(path)
        return completed
    def select(self,path):
        if path not in self.files: return
        self.selected_path=path
        for p,b in self.buttons.items(): b.selected = p == path; b.apply_style()
        if path in self.buttons: self.scroll.ensureWidgetVisible(self.buttons[path])
        self.selected.emit(path)


class ToolbarSeparator(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedSize(1, 18)

    def paintEvent(self, event):
        painter = QPainter(self)
        color = QColor(PALETTE["edge"])
        color.setAlpha(110)
        painter.setPen(color)
        painter.drawLine(0, 0, 0, self.height() - 1)
        painter.end()


def separate_tools(layout):
    layout.addSpacing(6)
    layout.addWidget(ToolbarSeparator())
    layout.addSpacing(6)


class ImagePane(QFrame):
    interacted = Signal()

    def __init__(self, labels, parent=None):
        super().__init__(parent); self.labels=labels; self.path=None; self.frames=[]; self.index=0; self.rotation=0; self.fh=False; self.fv=False; self.zoom=1.0; self.fit_to_pane=False; self.auto_scale=False; self._applying_auto_scale=False; self.display_scale=1.0; self.full_window=None; self.timer=QTimer(self); self.timer.timeout.connect(self.next_frame)
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,6,10,8)
        self.comparison_title = None
        self.comparison_selected = False
        bar=QHBoxLayout(); self.rotate_b=IconButton("rotate",labels["rotate"]); self.mh=IconButton("mirror-h",labels["mh"]); self.mv=IconButton("mirror-v",labels["mv"]); self.fit_b=IconButton("fit",labels["fit"]); self.fit_b.setCheckable(True); self.fit_b.toggled.connect(self.set_fit); self.max_button=IconButton("expand",labels["max"]); self.full=IconButton("fullscreen",labels["full"])
        for b,fn in ((self.rotate_b,self.rotate),(self.mh,self.mirror_h),(self.mv,self.mirror_v)): b.clicked.connect(fn); bar.addWidget(b)
        separate_tools(bar)
        self.full.clicked.connect(self.open_full)
        for button in (self.fit_b,self.max_button,self.full): bar.addWidget(button)
        self.filename_label=QLabel(); self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.filename_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed); bar.addWidget(self.filename_label,1)
        self.zoom_label=ScaleValueButton(1000,1,4000,1000,10,"%",labels["edit_zoom"]); bar.addWidget(self.zoom_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,1000); self.slider.setRange(1,4000); self.slider.setValue(1000); self.slider.logicalValueChanged.connect(self.set_zoom_percent); self.zoom_label.valueChosen.connect(self.choose_zoom); self.slider.setFixedSize(SLIDER_WIDTH,30); bar.addWidget(self.slider)
        self.toolbar_widget = QWidget(self)
        self.toolbar_widget.setLayout(bar)
        bar.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar_widget)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(False); self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.label=QLabel(labels["empty"]); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.label.setStyleSheet(f"color:{PALETTE['muted']};background:transparent;"); self.scroll.setWidget(self.label); layout.addWidget(self.scroll)
        self.toolbar = bar
        for widget in self.findChildren(QWidget): widget.installEventFilter(self)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.comparison_selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#1677ff"), 2))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 10, 10)
            painter.end()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel): self.interacted.emit()
        return super().eventFilter(watched, event)

    def update_filename(self):
        name = self.path.name if self.path else ""
        self.filename_label.setText(f"{self.comparison_title} / {name}" if self.comparison_title else name)

    def set_comparison_mode(self, title=None):
        self.comparison_title = title
        comparing = title is not None
        self.toolbar_widget.setVisible(not comparing)
        if comparing:
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            self.setMinimumSize(0, 0)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        else:
            self.comparison_selected = False
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.update_filename()
        self.update()
    @staticmethod
    def read_frames(path):
        frames = []
        with Image.open(path) as image:
            for index in range(getattr(image, "n_frames", 1)):
                image.seek(index)
                frames.append((ImageOps.exif_transpose(image).convert("RGBA").copy(), max(20, int(image.info.get("duration", 100)))))
        return frames

    def reload_preserving_view(self):
        if self.path is None: return False
        try:
            frames = self.read_frames(self.path)
        except Exception:
            # Keep displaying the last complete image while a writer is active.
            return False
        scroll_x = self.scroll.horizontalScrollBar().value()
        scroll_y = self.scroll.verticalScrollBar().value()
        was_empty = not self.frames
        self.timer.stop()
        self.frames = frames
        self.index = min(self.index, len(frames) - 1)
        if was_empty:
            self.auto_scale = True
            self.apply_default_zoom()
        self.render()
        self.scroll.horizontalScrollBar().setValue(scroll_x)
        self.scroll.verticalScrollBar().setValue(scroll_y)
        if len(frames) > 1: self.timer.start(frames[self.index][1])
        return True

    def load(self,path):
        self.auto_scale=False; self.path=path; self.rotation=0; self.fh=self.fv=False; self.zoom=1.0; self.frames=[]; self.timer.stop(); self.fit_b.setChecked(False)
        self.slider.blockSignals(True); self.slider.setMaximum(4000); self.slider.setValue(1000); self.slider.blockSignals(False); self.zoom_label.set_value(1000)
        self.update_filename(); self.filename_label.setToolTip(str(path))
        try:
            self.frames = self.read_frames(path)
            self.index=0; self.auto_scale=True
            if self.isVisible():
                self.apply_default_zoom()
                if not self.fit_to_pane: self.render()
            else:
                QTimer.singleShot(0,self.refresh_after_resize)
            QTimer.singleShot(0,self.apply_default_zoom)
            if len(self.frames)>1:self.timer.start(self.frames[0][1])
        except Exception: self.frames=[]; self.label.clear(); self.label.setText(self.labels["empty"]); self.label.setFixedSize(self.label.sizeHint())
    def clear(self):
        self.auto_scale=False; self.timer.stop(); self.frames=[]; self.path=None; self.fit_b.setChecked(False)
        self.filename_label.clear(); self.filename_label.setToolTip("")
        self.update_filename()
        self.label.clear(); self.label.setText(self.labels["empty"]); self.label.setFixedSize(self.label.sizeHint())
        if self.full_window is not None: self.open_full()
    def next_frame(self): self.index=(self.index+1)%len(self.frames); self.timer.start(self.frames[self.index][1]); self.render()
    def image(self):
        im=self.frames[self.index][0]
        if self.rotation: im=im.rotate(-self.rotation,expand=True)
        if self.fh: im=ImageOps.mirror(im)
        if self.fv: im=ImageOps.flip(im)
        return im
    def render(self):
        if not self.frames:return
        im=self.image()
        scale=min(max(1,self.scroll.viewport().width()-8)/im.width,max(1,self.scroll.viewport().height()-8)/im.height) if self.fit_to_pane else self.zoom
        self.display_scale=scale
        if self.fit_to_pane:
            ticks=max(1,round(scale*1000))
            self.slider.blockSignals(True)
            self.slider.setMaximum(max(4000,ticks))
            self.slider.setValue(ticks)
            self.slider.blockSignals(False)
            self.zoom_label.set_value(ticks)
        size=(max(1,round(im.width*scale)),max(1,round(im.height*scale)))
        if size != im.size: im=im.resize(size,Image.Resampling.LANCZOS)
        pix=QPixmap.fromImage(qimage(im)); self.label.setPixmap(pix); self.label.setFixedSize(pix.size())
        if self.full_window is not None:
            self.full_window.centralWidget().setPixmap(QPixmap.fromImage(qimage(self.image())))
    def resizeEvent(self,e): super().resizeEvent(e); QTimer.singleShot(0,self.refresh_after_resize)
    def refresh_after_resize(self):
        self.apply_default_zoom()
        self.render()
    def apply_default_zoom(self):
        if not self.auto_scale or not self.frames or not self.isVisible(): return
        im=self.image()
        oversized=im.width>max(1,self.scroll.width()-8) or im.height>max(1,self.scroll.height()-8)
        if oversized != self.fit_to_pane:
            self._applying_auto_scale=True
            try: self.fit_b.setChecked(oversized)
            finally: self._applying_auto_scale=False
    def wheelEvent(self,e): self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().value()-e.angleDelta().y()); e.accept()
    def rotate(self): self.rotation=(self.rotation+90)%360; self.render()
    def mirror_h(self): self.fh=not self.fh; self.render()
    def mirror_v(self): self.fv=not self.fv; self.render()
    def set_zoom_percent(self, ticks):
        self.auto_scale=False
        if self.fit_to_pane:
            self.fit_b.blockSignals(True); self.fit_b.setChecked(False); self.fit_b.blockSignals(False)
            self.fit_b.refresh_icon()
            self.fit_to_pane=False
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.zoom = ticks / 1000
        self.zoom_label.set_value(ticks)
        self.render()
    def set_fit(self, checked):
        if checked and not self.frames:
            self.fit_b.blockSignals(True); self.fit_b.setChecked(False); self.fit_b.blockSignals(False)
            self.fit_b.refresh_icon()
            return
        if not self._applying_auto_scale: self.auto_scale=False
        self.fit_to_pane=checked
        if not checked:
            self.zoom=1.0
            self.slider.blockSignals(True); self.slider.setMaximum(4000); self.slider.setValue(1000); self.slider.blockSignals(False)
            self.zoom_label.set_value(1000)
        policy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff if checked else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        self.scroll.setHorizontalScrollBarPolicy(policy); self.scroll.setVerticalScrollBarPolicy(policy)
        self.render()
        if checked: QTimer.singleShot(0,self.render)
    def adjust_zoom(self, amount):
        target=max(self.slider.minimum(), min(self.slider.maximum(), self.slider.value() + amount*10))
        if target == self.slider.value() and self.fit_to_pane: self.set_zoom_percent(target)
        else: self.slider.setValue(target)
    def choose_zoom(self, ticks):
        if ticks == 1000:
            self.reset_zoom()
        elif ticks == self.slider.value() and self.fit_to_pane:
            self.set_zoom_percent(ticks)
        else:
            self.slider.setValue(ticks)
    def reset_zoom(self):
        if self.fit_to_pane: self.fit_b.setChecked(False)
        self.slider.setValue(1000)
    def open_full(self):
        if self.full_window is not None:
            self.full_window.close()
            self.full_window = None
            return
        if not self.frames: return
        w=QMainWindow(self); w.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose); w.destroyed.connect(lambda: setattr(self, "full_window", None)); w.setWindowState(Qt.WindowState.WindowFullScreen); label=QLabel(); label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setStyleSheet("background:#111820;"); w.setCentralWidget(label); w.keyPressEvent=lambda e: self.open_full() if e.key()==Qt.Key.Key_Escape else None; im=self.image(); label.setPixmap(QPixmap.fromImage(qimage(im))); w.show(); self.full_window=w


class FolderTab(QWidget):
    notification = Signal(str)
    attentionChanged = Signal()

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.t = labels
        self.folder = None
        self.files = []
        self.saved_sizes = None
        self.active = False
        self.comparison_visible = False
        self.pending_notification = ""
        self.image_dirty = False
        self._selection_pending = None
        self._restore_selected = None
        self._initial_view = None
        self._pending_scroll = None
        self._scroll_restore_attempts = 0
        self._normal_scroll = None
        self._layout_pending = False
        self._sash_fraction = .45
        self._closing = False
        self._pending_image_versions = {}
        self._pending_image_retries = {}
        self._image_versions = {}
        self._changed_image_paths = set()
        self._image_reload_retries = 0
        self.folder_watcher = QFileSystemWatcher(self)
        self.folder_watcher.directoryChanged.connect(self.schedule_folder_refresh)
        self.folder_watcher.fileChanged.connect(self.schedule_image_refresh)
        self.folder_refresh_timer = QTimer(self)
        self.folder_refresh_timer.setSingleShot(True)
        self.folder_refresh_timer.setInterval(100)
        self.folder_refresh_timer.timeout.connect(self.refresh_folder)
        self.folder_poll_timer = QTimer(self)
        self.folder_poll_timer.setInterval(750)
        self.folder_poll_timer.timeout.connect(self.refresh_folder)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(7)
        self.thumbs = ThumbnailPane(labels)
        self.image = ImagePane(labels)
        self.split.addWidget(self.thumbs)
        self.image_slot = QWidget()
        slot_layout = QVBoxLayout(self.image_slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.addWidget(self.image)
        self.split.addWidget(self.image_slot)
        layout.addWidget(self.split)
        self.thumbs.selected.connect(self.select_image)
        self.thumbs.max_button.clicked.connect(lambda: self.maximize("thumb"))
        self.image.max_button.clicked.connect(self.maximize_image)
        self.scroll_restore_timer = QTimer(self)
        self.scroll_restore_timer.setSingleShot(True)
        self.scroll_restore_timer.setInterval(50)
        self.scroll_restore_timer.timeout.connect(self.restore_scroll)
        for bar in (self.thumbs.scroll.verticalScrollBar(), self.image.scroll.horizontalScrollBar(), self.image.scroll.verticalScrollBar()):
            bar.rangeChanged.connect(lambda *_: self.scroll_restore_timer.start() if self._pending_scroll is not None else None)
            bar.sliderPressed.connect(self.cancel_scroll_restore)
            bar.installEventFilter(self)
        for pane in (self.thumbs, self.image):
            pane.scroll.viewport().installEventFilter(self)
            pane.slider.logicalValueChanged.connect(self.cancel_scroll_restore)

    def open_folder(self, folder, selected=None, state=None):
        self.folder_refresh_timer.stop()
        watched = self.folder_watcher.directories() + self.folder_watcher.files()
        if watched: self.folder_watcher.removePaths(watched)
        self._changed_image_paths.clear()
        self._image_reload_retries = 0
        self.image.clear()
        self.folder = folder.resolve()
        self._initial_view = state
        self._restore_selected = selected
        self.files = image_files(self.folder)
        self._layout_pending = True
        if state:
            self.thumbs.slider.setValue(state["thumbnail_size"])
            orientation = Qt.Orientation.Horizontal if state["orientation"] == "horizontal" else Qt.Orientation.Vertical
            self.split.setOrientation(orientation)
            self._sash_fraction = state["sash_fraction"]
        self.thumbs.set_files(self.files, selected)
        self._pending_image_versions = self.pending_image_versions()
        self._pending_image_retries = dict.fromkeys(self.thumbs.failed_paths, 8)
        self._image_versions = self.image_versions(self.files)
        self.watch_current_folder()
        self.watch_image_files(self.files)
        self.folder_poll_timer.start()
        if not self.files:
            self.image.clear()
            self.update_empty_message()
        if self.active or self.comparison_visible: self.activate_image()

    def update_empty_message(self):
        if not self.files:
            key = "folder_missing" if self.folder and not self.folder.is_dir() else "empty"
            self.image.label.setText(self.t[key])
            self.image.label.setFixedSize(self.image.label.sizeHint())

    def select_image(self, path):
        if self._initial_view is None: self.cancel_scroll_restore()
        self._selection_pending = path
        self.image_dirty = True
        if self.active or self.comparison_visible: self.activate_image()

    def activate_image(self):
        path = self.thumbs.selected_path
        if path is None:
            self.image.clear()
            self.update_empty_message()
            return
        if self.image.path != path:
            self.image.load(path)
            self.image_dirty = not bool(self.image.frames)
        elif self.image_dirty:
            self.image_dirty = not self.image.reload_preserving_view()
        self._selection_pending = None
        if self._initial_view is not None and self.image.frames:
            state = self._initial_view
            self._initial_view = None
            self.image.rotation = state.get("rotation", 0)
            self.image.fh = state.get("fh", False)
            self.image.fv = state.get("fv", False)
            fit = state.get("fit_to_pane")
            if fit is not None:
                self.image.fit_b.setChecked(fit)
                self.image.auto_scale = False
            if fit is not True and (fit is False or state["image_zoom"] != 1):
                self.image.slider.setValue(round(state["image_zoom"] * 1000))
            self.image.render()
            self._pending_scroll = {key: state.get(key, 0) for key in ("thumbnail_scroll", "image_scroll_x", "image_scroll_y")}
            self._scroll_restore_attempts = 0
            self.scroll_restore_timer.start()
        if (self.active or self.comparison_visible) and len(self.image.frames) > 1:
            self.image.timer.start(self.image.frames[self.image.index][1])

    def reload_current_image(self):
        if not self.active and not self.comparison_visible:
            self.image_dirty = True
            return True
        result = self.image.reload_preserving_view()
        self.image_dirty = not result
        return result

    def set_active(self, active):
        self.active = active
        if self._closing: return
        if not active:
            if not self.comparison_visible: self.image.timer.stop()
            if self.image.full_window is not None: self.image.open_full()
            return
        self.refresh_folder()
        self.activate_image()
        if self._layout_pending: QTimer.singleShot(0, self, self.apply_layout)
        if self._pending_scroll is not None: self.scroll_restore_timer.start()

    def set_comparison_visible(self, visible):
        self.comparison_visible = visible
        if self._closing: return
        if visible:
            self.refresh_folder()
            self.activate_image()
        elif not self.active:
            self.image.timer.stop()

    def maximize_image(self):
        window = self.window()
        if self.comparison_visible and hasattr(window, "comparison_area"):
            window.comparison_area.maximize_page(self)
        else:
            self.maximize("image")

    def cancel_scroll_restore(self):
        self._pending_scroll = None
        self.scroll_restore_timer.stop()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Wheel, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress):
            self.cancel_scroll_restore()
        return super().eventFilter(watched, event)

    def restore_scroll(self):
        if self._closing or not self.active or self._pending_scroll is None: return
        state = self._pending_scroll
        bars = ((self.thumbs.scroll.verticalScrollBar(), state["thumbnail_scroll"]),
                (self.image.scroll.horizontalScrollBar(), state["image_scroll_x"]),
                (self.image.scroll.verticalScrollBar(), state["image_scroll_y"]))
        if any(value > bar.maximum() for bar, value in bars) and self._scroll_restore_attempts < 10:
            self._scroll_restore_attempts += 1
            self.scroll_restore_timer.start()
            return
        self._pending_scroll = None
        self.thumbs.scroll.verticalScrollBar().setValue(state["thumbnail_scroll"])
        self.image.scroll.horizontalScrollBar().setValue(state["image_scroll_x"])
        self.image.scroll.verticalScrollBar().setValue(state["image_scroll_y"])

    def apply_layout(self):
        if self._closing or not self.active or not self._layout_pending: return
        length = self.split.width() if self.split.orientation() == Qt.Orientation.Horizontal else self.split.height()
        if length <= 0: return
        self.split.setSizes([round(length * self._sash_fraction), round(length * (1 - self._sash_fraction))])
        self._layout_pending = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._layout_pending and self.active: QTimer.singleShot(0, self, self.apply_layout)

    def notify(self, message):
        if self.active:
            self.pending_notification = ""
            self.notification.emit(message)
        else:
            self.pending_notification = message
            self.attentionChanged.emit()

    def snapshot(self):
        sizes = self.saved_sizes if self.saved_sizes is not None else self.split.sizes()
        fraction = sizes[0] / sum(sizes) if sum(sizes) and not self._layout_pending else self._sash_fraction
        state = {"folder": str(self.folder) if self.folder else "", "selected_file": str(self.thumbs.selected_path or self._restore_selected or ""),
                 "orientation": "horizontal" if self.split.orientation() == Qt.Orientation.Horizontal else "vertical",
                 "sash_fraction": fraction, "thumbnail_size": self.thumbs.size,
                 "image_zoom": self.image.zoom, "fit_to_pane": self.image.fit_to_pane,
                 "rotation": self.image.rotation, "fh": self.image.fh, "fv": self.image.fv,
                 "thumbnail_scroll": self.thumbs.scroll.verticalScrollBar().value(),
                 "image_scroll_x": self.image.scroll.horizontalScrollBar().value(),
                 "image_scroll_y": self.image.scroll.verticalScrollBar().value()}
        if self._initial_view is not None:
            state.update({key: self._initial_view[key] for key in ("image_zoom", "fit_to_pane", "rotation", "fh", "fv", "thumbnail_scroll", "image_scroll_x", "image_scroll_y") if key in self._initial_view})
        if self._pending_scroll is not None: state.update(self._pending_scroll)
        if self.saved_sizes is not None and self._normal_scroll is not None: state.update(self._normal_scroll)
        return state

    def restyle(self, labels):
        self.t = labels
        self.thumbs.labels = labels
        self.image.labels = labels
        for pane in (self.thumbs, self.image):
            pane.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};")
            pane.max_button.setToolTip(labels["restore" if pane.max_button.kind == "shrink" else "max"])
        self.thumbs.grid_host.setStyleSheet(f"#thumbnailGrid{{background:{PALETTE['pane']};}}")
        for tile in self.thumbs.buttons.values(): tile.apply_style()
        for button, key in ((self.image.rotate_b, "rotate"), (self.image.mh, "mh"), (self.image.mv, "mv"), (self.image.fit_b, "fit"), (self.image.full, "full")):
            button.setToolTip(labels[key])
        self.thumbs.size_label.setToolTip(labels["edit_thumb"])
        self.image.zoom_label.setToolTip(labels["edit_zoom"])
        self.image.label.setStyleSheet(f"color:{PALETTE['muted']};background:transparent;")
        for button in self.findChildren(IconButton) + self.image.findChildren(IconButton): button.refresh_icon()
        if self.comparison_visible: self.image.set_comparison_mode(self.folder.name or str(self.folder))
        self.update_empty_message()

    def shutdown(self):
        self._closing = True
        self.active = False
        self.folder_refresh_timer.stop()
        self.folder_poll_timer.stop()
        self.scroll_restore_timer.stop()
        self.image.timer.stop()
        if self.image.full_window is not None: self.image.open_full()
        self.image.clear()
        watched = self.folder_watcher.directories() + self.folder_watcher.files()
        if watched: self.folder_watcher.removePaths(watched)

    @property
    def notification_bar(self):
        return self.window().notification_bar

    def closeEvent(self, event):
        self.shutdown()
        event.accept()

    def watch_current_folder(self):
        if self.folder and self.folder.is_dir() and str(self.folder) not in self.folder_watcher.directories():
            self.folder_watcher.addPath(str(self.folder))

    def schedule_folder_refresh(self, folder):
        if not self._closing and self.folder == Path(folder):
            self.folder_refresh_timer.start()

    def schedule_image_refresh(self, filename):
        path = Path(filename)
        if not self._closing and self.folder == path.parent:
            self._changed_image_paths.add(path)
            self.folder_refresh_timer.start()

    def watch_image_files(self, files):
        watched = set(self.folder_watcher.files())
        wanted = {str(path) for path in files}
        removed = watched - wanted
        if removed: self.folder_watcher.removePaths(list(removed))
        added = wanted - watched
        if added: self.folder_watcher.addPaths(list(added))

    @staticmethod
    def image_versions(files):
        versions = {}
        for path in files:
            try:
                stat = path.stat()
                versions[path] = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
            except OSError:
                versions[path] = None
        return versions

    def pending_image_versions(self):
        versions = {}
        for path in self.thumbs.failed_paths:
            try:
                stat = path.stat()
                versions[path] = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                versions[path] = None
        return versions

    def refresh_folder(self):
        if self._closing or self.folder is None: return
        self.watch_current_folder()
        try:
            files = image_files(self.folder, strict=True)
        except (FileNotFoundError, NotADirectoryError):
            files = []
        except OSError:
            # A temporary access failure does not mean the images were deleted.
            return
        versions = self.image_versions(files)
        changed = {path for path in files if path in self._image_versions and versions[path] != self._image_versions[path]}
        changed.update(self._changed_image_paths.intersection(files))
        self._changed_image_paths.clear()
        self._image_versions = versions
        # Atomic replacement can remove a native file watch; reattach it here.
        self.watch_image_files(files)
        pending = self.pending_image_versions()
        for path, version in pending.items():
            if path not in self._pending_image_retries or version != self._pending_image_versions.get(path):
                self._pending_image_retries[path] = 8
        if files == self.files:
            retry_paths = {path for path in self.thumbs.failed_paths if self._pending_image_retries.get(path, 0) > 0}
            retry_paths.update(changed)
            for path in changed: self._pending_image_retries[path] = 8
            selected = self.thumbs.selected_path
            if selected in changed: self._image_reload_retries = 8
            if self._image_reload_retries and selected == self.image.path:
                retry_paths.add(selected)
            if not retry_paths: return
            # Retry only incomplete thumbnails, including files briefly locked by a copy.
            completed = self.thumbs.refresh_previews(retry_paths)
            for path in retry_paths:
                self._pending_image_retries[path] = max(0, self._pending_image_retries.get(path, 8) - 1)
            self._pending_image_versions = self.pending_image_versions()
            self._pending_image_retries = {path: self._pending_image_retries[path] for path in self.thumbs.failed_paths}
            if selected in completed and (selected in changed or self._image_reload_retries or not self.image.frames):
                if self.reload_current_image(): self._image_reload_retries = 0
                else: self._image_reload_retries = max(0, self._image_reload_retries - 1)
            elif selected in retry_paths:
                self._image_reload_retries = max(0, self._image_reload_retries - 1)
            return
        previous = self.thumbs.selected_path
        removed = previous is not None and previous not in files
        selected = previous
        if removed:
            selected = next((path for path in files if natural_key(path) > natural_key(previous)), files[0] if files else None)
        elif selected is None and files:
            selected = self._restore_selected if self._restore_selected in files else files[0]
        thumbs = self.thumbs
        scroll_position = thumbs.scroll.verticalScrollBar().value()
        self.files = files
        reload_image = selected != previous or (selected is not None and not self.image.frames)
        thumbs.set_files(files, selected, emit_selection=reload_image)
        self._image_reload_retries = 0
        if selected == previous and selected in changed and not reload_image:
            if not self.reload_current_image(): self._image_reload_retries = 8
        self._pending_image_versions = self.pending_image_versions()
        self._pending_image_retries = {path: self._pending_image_retries.get(path, 8) for path in self.thumbs.failed_paths}
        if not files:
            self.image.clear()
            self.update_empty_message()
        def restore_scroll():
            if self._closing or self.thumbs is not thumbs: return
            thumbs.scroll.verticalScrollBar().setValue(scroll_position)
            if removed and selected in thumbs.buttons:
                thumbs.scroll.ensureWidgetVisible(thumbs.buttons[selected])
        QTimer.singleShot(0, restore_scroll)
        if removed:
            key = "image_deleted" if selected else "image_deleted_empty"
            self.notify(self.t[key].format(name=previous.name, next=selected.name if selected else ""))

    def set_orientation(self,o):
        if self.split.orientation()==o:return
        sizes=self.split.sizes(); self.split.setOrientation(o); QTimer.singleShot(0,self,lambda:self.split.setSizes(sizes))

    def maximize(self,which):
        if self.saved_sizes is None:
            self._normal_scroll = {"thumbnail_scroll": self.thumbs.scroll.verticalScrollBar().value(), "image_scroll_x": self.image.scroll.horizontalScrollBar().value(), "image_scroll_y": self.image.scroll.verticalScrollBar().value()}
            self.saved_sizes=self.split.sizes(); hide=self.image_slot if which=="thumb" else self.thumbs; hide.hide(); b=self.thumbs.max_button if which=="thumb" else self.image.max_button; b.set_kind("shrink",self.t["restore"])
        else:
            self.thumbs.show(); self.image_slot.show(); self.split.setSizes(self.saved_sizes); self.saved_sizes=None; self.thumbs.max_button.set_kind("expand",self.t["max"]); self.image.max_button.set_kind("expand",self.t["max"])
            self._pending_scroll = self._normal_scroll
            self._scroll_restore_attempts = 0
            self._normal_scroll = None
            self.scroll_restore_timer.start()

    def select_relative(self, offset):
        if not self.files: return
        selected = self.thumbs.selected_path
        index = self.files.index(selected) if selected in self.files else 0
        self.thumbs.select(self.files[max(0, min(len(self.files) - 1, index + offset))])

    def select_boundary(self, last):
        if self.files: self.thumbs.select(self.files[-1 if last else 0])

    def copy_selected_file(self):
        path = self.thumbs.selected_path
        if path is None or not path.is_file(): return
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(path))])
        QApplication.clipboard().setMimeData(data)



class TabFolderControl(QCheckBox):
    """Paint at native widget resolution, including on high-DPI displays."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.comparing = False
        self.setFixedSize(28, 20)

    def hitButton(self, pos):
        return self.comparing and self.rect().contains(pos)

    def mousePressEvent(self, event):
        if not self.comparing:
            event.ignore()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(PALETTE["text"]), 1.25))
        painter.save()
        painter.translate(8, 0)
        if self.comparing:
            if self.isChecked():
                painter.setBrush(QColor("#1677ff"))
                painter.setPen(QPen(QColor("#1677ff"), 1))
            painter.drawRoundedRect(QRectF(3.5, 3.5, 13, 13), 2, 2)
            if self.isChecked():
                painter.setPen(QPen(QColor("white"), 1.5))
                painter.drawLine(QPoint(6, 10), QPoint(9, 13))
                painter.drawLine(QPoint(9, 13), QPoint(14, 7))
        else:
            painter.drawPolyline([QPoint(3, 7), QPoint(3, 4), QPoint(8, 4), QPoint(10, 6), QPoint(17, 6), QPoint(17, 8)])
            painter.drawPolyline([QPoint(3, 8), QPoint(18, 8), QPoint(15, 16), QPoint(2, 16), QPoint(3, 8)])
        painter.restore()
        if self.hasFocus():
            painter.setPen(QPen(QColor("#1677ff"), 1, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class ComparisonArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pages = []
        self.maximized_page = None
        self.toolbar_image = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.header = QFrame()
        self.header.setObjectName("card")
        self.header_layout = QVBoxLayout(self.header)
        self.header_layout.setContentsMargins(10, 6, 10, 6)
        layout.addWidget(self.header)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.split = QSplitter()
        self.split.setChildrenCollapsible(False)
        layout.addWidget(self.empty)
        layout.addWidget(self.split, 1)

    def release_toolbar(self):
        image = self.toolbar_image
        if image is not None:
            image.layout().insertWidget(0, image.toolbar_widget)
            image.toolbar_widget.setVisible(image.comparison_title is None)
        self.toolbar_image = None

    def select_toolbar(self, image):
        if self.toolbar_image is not image:
            self.release_toolbar()
            self.toolbar_image = image
            if image is not None: self.header_layout.addWidget(image.toolbar_widget)
        self.header.setVisible(image is not None)
        if image is not None: image.toolbar_widget.show()
        for page in self.pages:
            page.image.comparison_selected = page.image is image
            page.image.update()

    def set_layout_orientation(self, orientation):
        self.split.setOrientation(Qt.Orientation.Horizontal if orientation == Qt.Orientation.Vertical else Qt.Orientation.Vertical)
        self.equalize()

    def equalize(self):
        self.split.setSizes([1000] * len(self.pages))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.equalize()

    def maximize_page(self, page):
        self.maximized_page = None if self.maximized_page is page else page
        for item in self.pages:
            item.image.setVisible(self.maximized_page is None or item is self.maximized_page)
        self.equalize()


class TabCloseButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tabCloseButton")
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(PALETTE["text"] if self.underMouse() else PALETTE["muted"]), 1))
        center = self.rect().center()
        painter.drawLine(center + QPoint(-3, -3), center + QPoint(3, 3))
        painter.drawLine(center + QPoint(-3, 3), center + QPoint(3, -3))
        painter.end()


class FolderTabBar(QTabBar):
    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        return QSize(min(200, max(150, size.width())), 36)

    def paintEvent(self, event):
        painter = QPainter(self)
        order = [index for index in range(self.count()) if index != self.currentIndex()]
        if self.currentIndex() >= 0: order.append(self.currentIndex())
        for index in order:
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            selected = index == self.currentIndex()
            if selected:
                painter.fillRect(option.rect, QColor(PALETTE["card"]))
                painter.fillRect(option.rect.left(), option.rect.bottom() - 1, option.rect.width(), 2, QColor("#1677ff"))
            elif option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, QColor(PALETTE["pane"]))
            font = self.font()
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(PALETTE["text"] if selected else PALETTE["muted"]))
            rect = option.rect.adjusted(12, 0, -30, -2)
            control = self.tabButton(index, QTabBar.ButtonPosition.LeftSide)
            if control is not None and not control.isHidden():
                rect.setLeft(max(rect.left(), control.geometry().right() + 8))
            text = painter.fontMetrics().elidedText(option.text, Qt.TextElideMode.ElideRight, max(0, rect.width()))
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        separator = QColor(PALETTE["edge"])
        separator.setAlpha(90)
        painter.setPen(QPen(separator, 1))
        for index in range(self.count() - 1):
            rect = self.tabRect(index)
            painter.drawLine(rect.right(), rect.top() + 3, rect.right(), rect.bottom() - 3)
        painter.end()


class FolderTabs(QWidget):
    """A compact tab strip with the add button directly after the last tab."""
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.strip = QFrame()
        self.strip.setObjectName("tabStrip")
        self.header = QHBoxLayout(self.strip)
        self.header.setContentsMargins(4, 0, 4, 0)
        self.header.setSpacing(4)
        self.bar = FolderTabBar()
        self._closable = True
        self.bar.setExpanding(False)
        self.bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.header.addWidget(self.bar)
        self.header.addStretch(1)
        self.stack = QStackedWidget()
        layout.addWidget(self.strip)
        layout.addWidget(self.stack, 1)
        self.bar.currentChanged.connect(self.select_index)
        self.bar.tabMoved.connect(lambda *_: self.stack.setCurrentWidget(self.currentWidget()))

    def tabBar(self): return self.bar
    def count(self): return self.bar.count()
    def currentIndex(self): return self.bar.currentIndex()
    def widget(self, index): return self.bar.tabData(index) if 0 <= index < self.count() else None
    def currentWidget(self): return self.widget(self.currentIndex())
    def indexOf(self, widget): return next((index for index in range(self.count()) if self.widget(index) is widget), -1)
    def setCurrentIndex(self, index): self.bar.setCurrentIndex(index)
    def setCurrentWidget(self, widget): self.setCurrentIndex(self.indexOf(widget))
    def setTabsClosable(self, closable):
        self._closable = bool(closable)
        for index in range(self.count()):
            self.bar.tabButton(index, QTabBar.ButtonPosition.RightSide).setVisible(self._closable)
    def setMovable(self, movable): self.bar.setMovable(movable)
    def setDocumentMode(self, mode): self.bar.setDocumentMode(mode)
    def setUsesScrollButtons(self, enabled): self.bar.setUsesScrollButtons(enabled)
    def setElideMode(self, mode): self.bar.setElideMode(mode)
    def setTabText(self, index, text): self.bar.setTabText(index, text)
    def setTabIcon(self, index, icon): self.bar.setTabIcon(index, icon)
    def tabText(self, index): return self.bar.tabText(index)
    def setTabToolTip(self, index, text): self.bar.setTabToolTip(index, text)
    def tabToolTip(self, index): return self.bar.tabToolTip(index)

    def setCornerWidget(self, widget):
        self.header.insertWidget(1, widget)

    def addTab(self, page, title):
        first = not self.count()
        self.stack.addWidget(page)
        self.bar.blockSignals(True)
        index = self.bar.addTab(title)
        self.bar.setTabData(index, page)
        button = TabCloseButton(self.bar)
        button.setVisible(self._closable)
        button.clicked.connect(lambda: self.tabCloseRequested.emit(self.indexOf(page)))
        self.bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, button)
        self.bar.blockSignals(False)
        if first: self.select_index(index)
        return index

    def select_index(self, index):
        page = self.widget(index)
        if page is not None: self.stack.setCurrentWidget(page)
        self.currentChanged.emit(index)

    def removeTab(self, index):
        page = self.widget(index)
        self.bar.blockSignals(True)
        self.bar.removeTab(index)
        self.bar.blockSignals(False)
        if page is not None: self.stack.removeWidget(page)
        self.select_index(self.currentIndex())


class PicView(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.language_mode = self.settings.get("language", "system")
        if self.language_mode not in LANGUAGE_MODES: self.language_mode = "system"
        self.lang = resolve_language(self.language_mode)
        self.t = TEXT[self.lang]
        self._closing = False
        self._previous_tab = None
        self.compare_enabled = False
        self.checked_pages = set()
        self.focused_compare_page = None
        app = QApplication.instance()
        self.system_palette = QPalette(app.palette())
        self.theme_mode = self.settings.get("theme", "system")
        if self.theme_mode not in ("system", "light", "dark"): self.theme_mode = "system"
        self._applying_theme = False
        if self.theme_mode != "system": app.setPalette(themed_palette(self.system_palette, self.theme_mode))
        use_system_palette(app)
        self.setMinimumSize(720, 500)
        self.resize(1100, 780)
        self.setAcceptDrops(True)
        self.notification_bar = self.statusBar()
        self.notification_bar.hide()
        self.notification_bar.messageChanged.connect(lambda message: self.notification_bar.setVisible(bool(message)))
        self.build()
        self.setup_shortcuts()
        self.restore()

    def current_tab(self):
        return self.tabs.currentWidget()

    def pages(self):
        return [self.tabs.widget(index) for index in range(self.tabs.count())]

    def build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        tool = QFrame()
        tool.setObjectName("toolbar")
        tool.setFixedHeight(42)
        layout = QHBoxLayout(tool)
        layout.setContentsMargins(8, 6, 8, 6)
        self.open_button = IconButton("folder", self.t["open"])
        self.vertical_button = IconButton("split-h", self.t["vertical"])
        self.horizontal_button = IconButton("split-v", self.t["horizontal"])
        self.compare_button = IconButton("compare", self.t["compare"])
        self.compare_button.setCheckable(True)
        self.compare_button.toggled.connect(self.set_compare)
        self.language_button = IconButton(LANGUAGE_ICONS[self.language_mode], self.t[f"lang_{self.language_mode}"])
        self.theme_button = IconButton(f"theme-{self.theme_mode}", self.t[f"theme_{self.theme_mode}"])
        for button, action in ((self.open_button, self.choose), (self.vertical_button, lambda: self.set_orientation(Qt.Orientation.Vertical)),
                               (self.horizontal_button, lambda: self.set_orientation(Qt.Orientation.Horizontal)),
                               (self.compare_button, lambda: None),
                               (self.language_button, self.toggle_lang), (self.theme_button, self.toggle_theme)):
            if button in (self.vertical_button, self.compare_button, self.language_button): separate_tools(layout)
            button.clicked.connect(action)
            layout.addWidget(button)
        layout.addStretch()
        outer.addWidget(tool)
        self.tabs = FolderTabs()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBar().tabMoved.connect(self.tabs_reordered)
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self.show_tab_menu)
        self.comparison_area = ComparisonArea(root)
        self.comparison_area.hide()
        self.add_tab_button = QToolButton()
        self.add_tab_button.setObjectName("addTabButton")
        self.add_tab_button.setText("+")
        self.add_tab_button.setFixedSize(30, 30)
        self.add_tab_button.setToolTip(self.t["new_tab"])
        self.add_tab_button.clicked.connect(self.choose)
        self.tabs.setCornerWidget(self.add_tab_button)
        outer.addWidget(self.tabs)
        self.apply_styles()

    def apply_styles(self):
        strip = PALETTE["surface"]
        hover = PALETTE["pane"]
        self.setStyleSheet(f"""
            #root{{background:{PALETTE['surface']};}}
            #toolbar{{background:transparent;border:0;}}
            #card{{background:{PALETTE['card']};border:0;border-radius:12px;}}
            QLabel{{color:{PALETTE['text']};}}
            QSlider::groove:horizontal{{height:5px;background:{PALETTE['edge']};border-radius:2px}}
            QSlider::handle:horizontal{{background:{PALETTE['accent']};width:15px;margin:-5px 0;border-radius:7px}}
            QScrollBar{{background:{PALETTE['surface']};border:0;margin:0;}}
            QScrollBar:vertical{{width:12px;}}
            QScrollBar:horizontal{{height:12px;}}
            QScrollBar::handle{{background:{PALETTE['edge']};border-radius:6px;}}
            QScrollBar::handle:vertical{{min-height:25px;}}
            QScrollBar::handle:horizontal{{min-width:25px;}}
            QScrollBar::add-page,QScrollBar::sub-page{{background:{PALETTE['surface']};}}
            QScrollBar::add-line,QScrollBar::sub-line{{width:0;height:0;border:0;background:none;}}
            QScrollArea::corner{{background:{PALETTE['surface']};}}
            #tabStrip{{background:{strip};border:0;}}
            QTabBar{{background:transparent;}}
            QTabBar::tab{{background:transparent;color:{PALETTE['muted']};border:0;padding:0 12px;margin:0;}}
            QTabBar::tab:selected{{background:{PALETTE['card']};color:{PALETTE['text']};}}
            QTabBar::tab:!selected:hover{{background:{hover};}}
            QTabBar QToolButton{{background:{strip};color:{PALETTE['text']};border:0;border-radius:4px;}}
            QTabBar QToolButton:hover{{background:{hover};}}
            #addTabButton{{background:transparent;color:{PALETTE['text']};border:0;border-radius:5px;font-size:20px;}}
            #addTabButton:hover,#tabCloseButton:hover{{background:{hover};}}
            #tabCloseButton{{background:transparent;border:0;border-radius:4px;}}
        """)
    def add_page(self):
        page = FolderTab(self.t)
        page.notification.connect(lambda message, tab=page: self.show_notification(tab, message))
        page.attentionChanged.connect(self.update_tab_titles)
        self.tabs.addTab(page, self.t["empty_tab"])
        control = TabFolderControl(self.tabs.tabBar())
        control.toggled.connect(lambda checked, tab=page: self.check_compare_page(tab, checked))
        self.tabs.tabBar().setTabButton(self.tabs.indexOf(page), QTabBar.ButtonPosition.LeftSide, control)
        page.image.interacted.connect(lambda tab=page: self.focus_compare_page(tab))
        button = self.tabs.tabBar().tabButton(self.tabs.indexOf(page), QTabBar.ButtonPosition.RightSide)
        button.setToolTip(self.t["close_tab"])
        button.setAccessibleName(self.t["close_tab"])
        return page

    def open_folder(self, folder, selected=None, *, state=None, restoring=False):
        folder = Path(folder).resolve()
        if not restoring and not folder.is_dir():
            self.notification_bar.showMessage(self.t["folder_missing"] + ": " + str(folder), 8000)
            return None
        page = next((tab for tab in self.pages() if tab.folder is None), None)
        if page is None: page = self.add_page()
        page.open_folder(folder, selected, state)
        if not restoring: self.tabs.setCurrentWidget(page)
        if page is self.current_tab(): page.set_active(True)
        self.update_tab_titles()
        self.update_title()
        if self.compare_enabled: self.sync_comparison()
        return page

    def choose(self):
        folder = QFileDialog.getExistingDirectory(self, self.t["open"], str(self.folder) if self.folder else "")
        if folder: self.open_folder(Path(folder))

    def show_tab_menu(self, position):
        bar = self.tabs.tabBar()
        page = self.tabs.widget(bar.tabAt(position))
        if page is None: return
        menu = QMenu(bar)
        action = menu.addAction(self.t["duplicate_tab"])
        action.setEnabled(page.folder is not None)
        action.triggered.connect(lambda: self.duplicate_page(page))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(bar.mapToGlobal(position))

    def duplicate_page(self, source):
        if source not in self.pages() or source.folder is None: return None
        state = source.snapshot()
        selected = Path(state["selected_file"]) if state["selected_file"] else None
        page = self.open_folder(source.folder, selected, state=state, restoring=True)
        self.tabs.tabBar().moveTab(self.tabs.indexOf(page), self.tabs.indexOf(source) + 1)
        self.tabs.setCurrentWidget(page)
        if self.compare_enabled and source in self.checked_pages:
            self.checked_pages.add(page)
            self.sync_comparison()
        self.update_tab_titles()
        return page

    def tab_changed(self, index):
        page = self.tabs.widget(index) if index >= 0 else None
        if self._previous_tab is not None and self._previous_tab is not page:
            self._previous_tab.set_active(False)
        self._previous_tab = page
        self.notification_bar.clearMessage()
        if page is not None:
            page.set_active(True)
            if page.pending_notification:
                message = page.pending_notification
                page.pending_notification = ""
                self.notification_bar.showMessage(message, 8000)
        self.update_tab_titles()
        self.update_title()
        if self.compare_enabled: self.sync_comparison()

    def close_tab(self, index=None):
        if index is None: index = self.tabs.currentIndex()
        if index < 0 or index >= self.tabs.count(): return
        page = self.tabs.widget(index)
        self.checked_pages.discard(page)
        if self.compare_enabled: self.sync_comparison()
        if self.comparison_area.parentWidget() is page.image_slot:
            self.comparison_area.setParent(self.centralWidget())
            self.comparison_area.hide()
        page.shutdown()
        self.tabs.removeTab(index)
        page.deleteLater()
        if not self.tabs.count(): self.add_page()
        self.update_tab_titles()

    def switch_tab(self, offset):
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + offset) % self.tabs.count())

    def update_title(self):
        page = self.current_tab()
        folder = page.folder if page is not None else None
        self.setWindowTitle(f"PicView v{__version__}" + (f" — {folder}" if folder else ""))

    def update_tab_titles(self):
        pages = self.pages()
        names = [(page.folder.name or str(page.folder)) if page.folder else self.t["empty_tab"] for page in pages]
        for index, page in enumerate(pages):
            name = names[index]
            if page.folder and len({item.folder for item, title in zip(pages, names) if title.casefold() == name.casefold()}) > 1:
                name += " — " + str(page.folder.parent)
            if page.folder and sum(item.folder == page.folder for item in pages) > 1:
                name += f" ({sum(item.folder == page.folder for item in pages[:index + 1])})"
            if page.pending_notification: name = "● " + name
            self.tabs.setTabText(index, name)
            control = self.tabs.bar.tabButton(index, QTabBar.ButtonPosition.LeftSide)
            if control is not None:
                control.comparing = self.compare_enabled
                control.blockSignals(True)
                control.setChecked(page in self.checked_pages)
                control.blockSignals(False)
                control.setVisible(page.folder is not None)
                control.setFocusPolicy(Qt.FocusPolicy.StrongFocus if self.compare_enabled else Qt.FocusPolicy.NoFocus)
                control.setToolTip(self.t["compare_folder"] if self.compare_enabled else self.t["open"])
                control.setAccessibleName(control.toolTip())
                control.update()
            self.tabs.setTabToolTip(index, str(page.folder) if page.folder else self.t["empty"])

    def tabs_reordered(self, *_):
        self.update_tab_titles()
        if self.compare_enabled: self.sync_comparison()

    def focus_compare_page(self, page):
        if page in self.checked_pages:
            self.focused_compare_page = page
            self.comparison_area.select_toolbar(page.image)

    def set_compare(self, enabled):
        if enabled:
            for page in self.pages():
                if page.saved_sizes is not None: page.maximize("image")
        self.compare_enabled = enabled
        self.compare_button.blockSignals(True)
        self.compare_button.setChecked(enabled)
        self.compare_button.blockSignals(False)
        self.checked_pages = {self.current_tab()} if enabled and self.current_tab() and self.current_tab().folder else set()
        self.focused_compare_page = None
        self.sync_comparison()
        self.update_tab_titles()

    def check_compare_page(self, page, checked):
        if not self.compare_enabled: return
        if checked: self.checked_pages.add(page)
        else: self.checked_pages.discard(page)
        self.sync_comparison()

    def sync_comparison(self):
        area = self.comparison_area
        area.release_toolbar()
        pages = self.pages()
        chosen = [page for page in pages if page in self.checked_pages] if self.compare_enabled else []
        # Return panes to their owners before moving the shared comparison area.
        area.hide()
        area.setParent(self.centralWidget())
        for page in pages:
            if page.image.parentWidget() is not page.image_slot:
                page.image_slot.layout().addWidget(page.image)
            page.image.show()
            visible = page in chosen
            page.image.set_comparison_mode((page.folder.name or str(page.folder)) if visible else None)
            if page.comparison_visible != visible: page.set_comparison_visible(visible)
        area.pages = chosen
        area.maximized_page = None
        if self.compare_enabled and self.current_tab() is not None:
            host = self.current_tab()
            host.image.hide()
            host.image_slot.layout().addWidget(area)
            area.set_layout_orientation(host.split.orientation())
            for page in chosen:
                area.split.addWidget(page.image)
                page.image.show()
            for index in range(1, area.split.count()): area.split.handle(index).setEnabled(False)
            area.empty.setText(self.t["compare_empty"])
            area.empty.setVisible(not chosen)
            area.split.setVisible(bool(chosen))
            if self.focused_compare_page not in chosen:
                self.focused_compare_page = host if host in chosen else (chosen[0] if chosen else None)
            area.select_toolbar(self.image_target())
            area.show()
            area.equalize()
            QTimer.singleShot(0, area, area.equalize)

    def image_target(self):
        if self.compare_enabled:
            page = self.focused_compare_page
            if page not in self.checked_pages:
                page = next((item for item in self.pages() if item in self.checked_pages), None)
            return page.image if page else None
        return self.image

    def image_action(self, action, *args):
        image = self.image_target()
        if image is not None: getattr(image, action)(*args)

    def advance_or_check(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, TabFolderControl) and focus.comparing: focus.toggle()
        else: self.current_tab().select_relative(1)

    def show_notification(self, page, message):
        if page is self.current_tab(): self.notification_bar.showMessage(message, 8000)

    def setup_shortcuts(self):
        bindings = [(QKeySequence.StandardKey.Open, self.choose), (QKeySequence.StandardKey.AddTab, self.choose),
                    (QKeySequence.StandardKey.Close, lambda: self.close_tab()),
                    (QKeySequence.StandardKey.NextChild, lambda: self.switch_tab(1)),
                    (QKeySequence.StandardKey.PreviousChild, lambda: self.switch_tab(-1)),
                    (QKeySequence.StandardKey.Copy, lambda: self.current_tab().copy_selected_file()),
                    ("Left", lambda: self.current_tab().select_relative(-1)), ("Right", lambda: self.current_tab().select_relative(1)),
                    ("Home", lambda: self.current_tab().select_boundary(False)), ("End", lambda: self.current_tab().select_boundary(True)),
                    ("PgUp", lambda: self.current_tab().select_relative(-1)), ("PgDown", lambda: self.current_tab().select_relative(1)),
                    ("Space", self.advance_or_check), ("Backspace", lambda: self.current_tab().select_relative(-1)),
                    ("+", lambda: self.image_action("adjust_zoom", 10)), ("=", lambda: self.image_action("adjust_zoom", 10)),
                    ("-", lambda: self.image_action("adjust_zoom", -10)), ("0", lambda: self.image_action("reset_zoom")), ("F11", lambda: self.image_action("open_full"))]
        self.shortcuts = []
        for keys, action in bindings:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

    def set_orientation(self, orientation):
        self.current_tab().set_orientation(orientation)
        if self.compare_enabled:
            self.comparison_area.set_layout_orientation(orientation)

    def rebuild_ui(self):
        self.open_button.setToolTip(self.t["open"])
        self.vertical_button.setToolTip(self.t["vertical"])
        self.horizontal_button.setToolTip(self.t["horizontal"])
        self.compare_button.setToolTip(self.t["compare"])
        self.compare_button.refresh_icon()
        self.comparison_area.empty.setText(self.t["compare_empty"])
        self.language_button.set_kind(LANGUAGE_ICONS[self.language_mode], self.t[f"lang_{self.language_mode}"])
        self.language_button.setAccessibleName(self.language_button.toolTip())
        self.theme_button.set_kind(f"theme-{self.theme_mode}", self.t[f"theme_{self.theme_mode}"])
        self.add_tab_button.setToolTip(self.t["new_tab"])
        self.apply_styles()
        for page in self.pages(): page.restyle(self.t)
        if self.compare_enabled:
            for button in self.comparison_area.header.findChildren(IconButton): button.refresh_icon()
            self.comparison_area.select_toolbar(self.image_target())
        for index in range(self.tabs.count()):
            button = self.tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
            button.setToolTip(self.t["close_tab"])
            button.setAccessibleName(self.t["close_tab"])
            button.update()
        for button in (self.open_button, self.vertical_button, self.horizontal_button): button.refresh_icon()
        self.update_tab_titles()

    def restore(self):
        states = self.settings.get("tabs", [])
        if not states:
            legacy = normalize_tab_state(self.settings)
            states = [legacy] if legacy else []
        for state in states:
            selected = Path(state["selected_file"]) if state["selected_file"] else None
            self.open_folder(Path(state["folder"]), selected, state=state, restoring=True)
        if not self.tabs.count(): self.add_page()
        self.tabs.setCurrentIndex(min(self.settings.get("active_tab", 0), self.tabs.count() - 1))
        self.current_tab().set_active(True)
        self.update_title()

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.ignore()
            return
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        if event.source() is self:
            event.ignore()
            return
        for url in event.mimeData().urls():
            if not url.isLocalFile(): continue
            path = Path(url.toLocalFile())
            if path.is_dir(): self.open_folder(path)
            elif path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES: self.open_folder(path.parent, path)

    def closeEvent(self, event):
        self._closing = True
        if self.compare_enabled: self.set_compare(False)
        pages = self.pages()
        states = [page.snapshot() for page in pages if page.folder is not None]
        current = self.current_tab()
        active = sum(page.folder is not None for page in pages[:self.tabs.currentIndex()]) if current and current.folder else 0
        values = current.snapshot() if current is not None else {}
        values.update(tabs=states, active_tab=active, language=self.language_mode, theme=self.theme_mode, maximized_pane="")
        save_settings(values)
        for page in pages: page.shutdown()
        event.accept()

    def toggle_theme(self):
        modes=("system","light","dark")
        self.theme_mode=modes[(modes.index(self.theme_mode)+1)%len(modes)]
        self.settings["theme"]=self.theme_mode
        app=QApplication.instance()
        self._applying_theme=True
        try: app.setPalette(themed_palette(self.system_palette,self.theme_mode))
        finally: self._applying_theme=False
        use_system_palette(app)
        self.rebuild_ui()

    def refresh_system_theme(self, _palette=None) -> None:
        if self._applying_theme or self.theme_mode != "system": return
        self.system_palette=QPalette(QApplication.instance().palette())
        use_system_palette(QApplication.instance())
        self.rebuild_ui()

    def toggle_lang(self):
        self.language_mode = LANGUAGE_MODES[(LANGUAGE_MODES.index(self.language_mode) + 1) % len(LANGUAGE_MODES)]
        self.settings["language"] = self.language_mode
        self.lang = resolve_language(self.language_mode)
        self.t = TEXT[self.lang]
        self.rebuild_ui()


    @property
    def folder(self):
        return self.current_tab().folder

    @property
    def files(self):
        return self.current_tab().files

    @property
    def thumbs(self):
        return self.current_tab().thumbs

    @property
    def image(self):
        return self.current_tab().image

    @property
    def split(self):
        return self.current_tab().split

    @property
    def saved_sizes(self):
        return self.current_tab().saved_sizes

    @property
    def folder_watcher(self):
        return self.current_tab().folder_watcher

    @property
    def folder_refresh_timer(self):
        return self.current_tab().folder_refresh_timer

    @property
    def folder_poll_timer(self):
        return self.current_tab().folder_poll_timer

    def refresh_folder(self, *args):
        return self.current_tab().refresh_folder(*args)

    def schedule_folder_refresh(self, *args):
        return self.current_tab().schedule_folder_refresh(*args)

    def schedule_image_refresh(self, *args):
        return self.current_tab().schedule_image_refresh(*args)

    def pending_image_versions(self, *args):
        return self.current_tab().pending_image_versions(*args)

    def maximize(self, *args):
        return self.current_tab().maximize(*args)

    def select_relative(self, *args):
        return self.current_tab().select_relative(*args)

    def select_boundary(self, *args):
        return self.current_tab().select_boundary(*args)

    def copy_selected_file(self, *args):
        return self.current_tab().copy_selected_file(*args)


def main():
    parser = argparse.ArgumentParser(description="PicView image folder viewer")
    parser.add_argument("--version", action="version", version=f"PicView {__version__}")
    parser.parse_args()
    app=QApplication(sys.argv); app.setApplicationName("PicView"); use_system_palette(app); w=PicView(); app.paletteChanged.connect(w.refresh_system_theme); icon=Path(__file__).parent/"assets"/"picview-icon.png"; w.setWindowIcon(QIcon(str(icon))); w.show(); sys.exit(app.exec())
