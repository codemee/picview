from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QEvent, QFileSystemWatcher, QLocale, QMimeData, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygon, QPalette, QRegion, QShortcut, QTransform
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QMainWindow,
    QMenu, QPushButton, QScrollArea, QSlider, QSplitter, QStackedWidget, QTabBar, QStyle, QStyleOptionSlider, QStyleOptionTab, QToolButton, QVBoxLayout, QWidget, QWidgetAction, QSizePolicy,
)

from . import __version__
from .about import AboutDialog
from .file_actions import copy_file, show_properties
from .settings import IMAGE_BACKGROUND_COLORS, load_settings, normalize_tab_state, save_settings
from .svg import SvgDocument
from .thumbnails import THUMBNAILS
from .system_menu import install_about_item, is_about_message
from .utils import IMAGE_SUFFIXES, image_files, natural_key


IMAGE_BACKGROUND = "#e9edf2"
DARK_IMAGE_BACKGROUND = "#1c1729"
THUMBNAIL_SELECTED = "#6ec8ff"
PALETTE = {"surface": "#f4f7f8", "card": "#ffffff", "edge": "#c7d3d8", "accent": THUMBNAIL_SELECTED, "text": "#172a31", "muted": "#526a73", "pane": IMAGE_BACKGROUND,
           "thumbnail_card": "#f6f8fb", "thumbnail_edge": "#cbd3df",
           "focus": "#1677ff", "selection": THUMBNAIL_SELECTED, "selection_text": "#153047", "active_text": "#ffffff", "hover": "#e2e6ed", "pressed": "#d5dbe4", "warm": "#172a31"}
SLIDER_WIDTH = 160
THUMBNAIL_BASE_SIZE = 140


def shortcut_tooltip(text, *bindings):
    keys = []
    for binding in bindings:
        sequence = QKeySequence(binding)
        key = sequence.toString(QKeySequence.SequenceFormat.NativeText)
        if key and key not in keys:
            keys.append(key)
    return f"{text} ({' / '.join(keys)})" if keys else text


def use_system_palette(app: QApplication) -> None:
    """Resolve surfaces and state colors, including the Unit-01 dark palette."""
    pal = app.palette()
    dark = pal.color(QPalette.ColorRole.Window).lightness() < 128
    if dark: pal = themed_palette(pal, "dark")
    PALETTE.update({
        "surface": pal.color(QPalette.ColorRole.Window).name(),
        "card": pal.color(QPalette.ColorRole.Base).name(),
        "thumbnail_card": "#302344" if dark else "#f6f8fb",
        "thumbnail_edge": "#70568b" if dark else "#cbd3df",
        "edge": pal.color(QPalette.ColorRole.Mid).name(),
        "text": pal.color(QPalette.ColorRole.Text).name(),
        "muted": pal.color(QPalette.ColorRole.PlaceholderText).name(),
        "pane": DARK_IMAGE_BACKGROUND if dark else IMAGE_BACKGROUND,
        "accent": "#a5ef4b" if dark else THUMBNAIL_SELECTED,
        "focus": "#a5ef4b" if dark else "#1677ff",
        "selection": "#3b2a53" if dark else THUMBNAIL_SELECTED,
        "selection_text": "#f0eaf8" if dark else "#153047",
        "active_text": "#17220c" if dark else "#ffffff",
        "hover": "#503c68" if dark else "#e2e6ed",
        "pressed": "#60477d" if dark else "#d5dbe4",
        "warm": "#ff9b45" if dark else pal.color(QPalette.ColorRole.Text).name(),
    })


def themed_palette(system_palette: QPalette, mode: str) -> QPalette:
    palette = QPalette(system_palette)
    if mode == "system":
        return palette
    if mode == "dark":
        colors = {
            QPalette.ColorRole.Window: "#171321",
            QPalette.ColorRole.Base: "#251c36",
            QPalette.ColorRole.AlternateBase: "#302344",
            QPalette.ColorRole.Text: "#f0eaf8",
            QPalette.ColorRole.WindowText: "#f0eaf8",
            QPalette.ColorRole.Button: "#302344",
            QPalette.ColorRole.ButtonText: "#f0eaf8",
            QPalette.ColorRole.PlaceholderText: "#b7a7cf",
            QPalette.ColorRole.Mid: "#70568b",
            QPalette.ColorRole.ToolTipBase: "#302344",
            QPalette.ColorRole.ToolTipText: "#f0eaf8",
            QPalette.ColorRole.Link: "#a5ef4b",
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
    colors[QPalette.ColorRole.Highlight] = "#a5ef4b" if mode == "dark" else THUMBNAIL_SELECTED
    colors[QPalette.ColorRole.HighlightedText] = "#17220c" if mode == "dark" else "#153047"
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    return palette

TEXT = {
    "en": {"open": "Open folder", "vertical": "Top / bottom", "horizontal": "Left / right", "lang": "中文", "theme_system": "Theme: follow system (click to switch)", "theme_light": "Theme: light (click to switch)", "theme_dark": "Theme: dark (click to switch)", "thumb": "Thumbnails", "max": "Maximize pane", "restore": "Restore panes", "rotate": "Rotate clockwise", "mh": "Mirror horizontally", "mv": "Mirror vertically", "fit": "Fit to pane", "full": "Full screen", "zoom": "Zoom", "edit_zoom": "Edit zoom", "edit_thumb": "Edit thumbnail size", "apply": "Apply", "empty": "Open a folder to view images"},
    "zh": {"open": "開啟資料夾", "vertical": "上下窗格", "horizontal": "左右窗格", "lang": "En", "theme_system": "配色：跟隨系統（點擊切換）", "theme_light": "配色：淺色（點擊切換）", "theme_dark": "配色：深色（點擊切換）", "thumb": "縮圖", "max": "最大化窗格", "restore": "還原窗格", "rotate": "順時針旋轉", "mh": "水平鏡射", "mv": "垂直鏡射", "fit": "符合窗格", "full": "全螢幕", "zoom": "縮放", "edit_zoom": "編輯顯示比例", "edit_thumb": "編輯縮圖大小", "apply": "套用", "empty": "開啟資料夾以檢視圖片"},
}

LANGUAGE_MODES = ("system", "zh", "en")
LANGUAGE_ICONS = {"system": "lang-system", "zh": "中", "en": "A"}
TEXT["en"].update({
    "about": "About PicView", "about_description": "Fast image viewing and multi-folder comparison.",
    "about_license": "GNU General Public License, version 3 or later",
    "about_style": "Interface style", "about_home": "Project home", "about_releases": "Releases and downloads",
    "about_license_full": "Full license text", "about_license_missing": "The license text is unavailable locally. Use the GNU GPL link above to read the terms.",
    "sort": "Sort thumbnails", "sort_method": "Sort by", "sort_direction": "Sort direction", "sort_natural": "Name (natural order)", "sort_modified": "Date modified",
    "sort_ascending": "Ascending (A–Z / oldest first)", "sort_descending": "Descending (Z–A / newest first)",
    "show_modified": "Show date modified", "copy": "Copy", "properties": "Properties", "file_close": "Close",
    "file_name": "Name", "file_type": "Type", "file_location": "Location", "file_size": "Size",
    "modified": "Modified", "created": "Created", "dimensions": "Dimensions", "bytes": "bytes",
    "background": "Image background", "bg_default": "Default (follow theme)",
    "bg_white": "White", "bg_black": "Black", "bg_gray": "Gray", "bg_light_gray": "Light gray",
    "bg_cream": "Cream", "bg_blue": "Light blue", "bg_green": "Light green", "bg_pink": "Light pink",
    "bg_dark_gray": "Dark gray", "bg_slate": "Slate", "bg_dark_blue": "Dark blue", "bg_dark_green": "Dark green",
    "bg_dark_purple": "Dark purple", "bg_dark_red": "Dark red", "bg_dark_brown": "Dark brown", "bg_dark_teal": "Dark teal",
    "more_tools": "More tools",
    "compare": "Compare images", "compare_folder": "Compare this folder", "compare_empty": "Check folder tabs to compare images", "image_tools": "Image tools",
    "close_tab": "Close tab",
    "new_tab": "Open folder in a new tab", "tab_list": "Select tab", "empty_tab": "New tab", "folder_missing": "Folder unavailable; waiting for it to return", "duplicate_tab": "Duplicate tab",
    "image_deleted": "The image being viewed was deleted: {name}. Now viewing {next}.",
    "image_deleted_empty": "The image being viewed was deleted: {name}. No images remain in this folder.",
    "lang_system": "Language: follow system (click to switch)",
    "lang_zh": "Language: Chinese (click to switch)",
    "lang_en": "Language: English (click to switch)",
})
TEXT["zh"].update({
    "about": "關於 PicView", "about_description": "快速載圖與多資料夾比圖工具。",
    "about_license": "GNU General Public License 第 3 版或更新版本",
    "about_style": "介面樣式", "about_home": "專案首頁", "about_releases": "版本與下載",
    "about_license_full": "授權全文", "about_license_missing": "無法讀取本機授權文件，請使用上方 GNU GPL 連結閱讀條款。",
    "sort": "縮圖排序", "sort_method": "排序方式", "sort_direction": "排序方向", "sort_natural": "檔名（自然排序）", "sort_modified": "修改時間",
    "sort_ascending": "順向（A–Z／舊到新）", "sort_descending": "逆向（Z–A／新到舊）",
    "show_modified": "顯示修改日期時間", "copy": "複製", "properties": "內容", "file_close": "關閉",
    "file_name": "檔名", "file_type": "類型", "file_location": "位置", "file_size": "大小",
    "modified": "修改時間", "created": "建立時間", "dimensions": "圖片尺寸", "bytes": "位元組",
    "background": "圖片背景色", "bg_default": "預設（跟隨主題）",
    "bg_white": "白色", "bg_black": "黑色", "bg_gray": "灰色", "bg_light_gray": "淺灰色",
    "bg_cream": "米色", "bg_blue": "淺藍色", "bg_green": "淺綠色", "bg_pink": "淺粉色",
    "bg_dark_gray": "深灰色", "bg_slate": "灰藍色", "bg_dark_blue": "深藍色", "bg_dark_green": "深綠色",
    "bg_dark_purple": "深紫色", "bg_dark_red": "深紅色", "bg_dark_brown": "深棕色", "bg_dark_teal": "深青色",
    "more_tools": "更多工具",
    "compare": "比圖", "compare_folder": "勾選此資料夾進行比圖", "compare_empty": "勾選資料夾標籤以比較圖片", "image_tools": "圖片工具",
    "close_tab": "關閉標籤",
    "new_tab": "在新標籤開啟資料夾", "tab_list": "選取標籤", "empty_tab": "新標籤", "folder_missing": "資料夾不存在，等待重新連線", "duplicate_tab": "複製標籤",
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


def qimage(image: Image.Image | QImage) -> QImage:
    if isinstance(image, QImage): return image.copy()
    image = image.convert("RGBA")
    return QImage(image.tobytes(), image.width, image.height, QImage.Format.Format_RGBA8888).copy()


def toolbar_hover_color():
    return PALETTE["hover"]


class IconButton(QToolButton):
    """Compact, frameless vector icon button."""
    def __init__(self, icon: str, tip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = icon
        self.setToolTip(tip); self.setFixedSize(34, 34); self.setIconSize(QSize(20, 20))
        self.toggled.connect(lambda _checked: self.refresh_icon())
        self.refresh_icon()

    def set_kind(self, icon: str, tip: str) -> None:
        self.kind = icon; self.setToolTip(tip); self.refresh_icon()

    def refresh_icon(self) -> None:
        self.setStyleSheet(f"QToolButton{{background:transparent;border:0;border-radius:8px;padding:4px;}}QToolButton:hover{{background:{toolbar_hover_color()};}}QToolButton:pressed{{background:{PALETTE['pressed']};}}QToolButton:checked{{background:{toolbar_hover_color()};}}QToolButton::menu-indicator{{image:none;width:0;height:0;}}")
        icon_size = self.iconSize().width()
        pixel_size = round(icon_size * self.devicePixelRatioF())
        pm = QPixmap(pixel_size, pixel_size)
        pm.setDevicePixelRatio(pixel_size / icon_size)
        pm.fill(Qt.GlobalColor.transparent)
        icon_color = QColor(PALETTE["text"])
        if self.kind == "rotate": icon_color = QColor(PALETTE["warm"])
        if self.kind.startswith(("lang-", "theme-")) or self.kind in ("中", "A"):
            icon_color = QColor(PALETTE["muted"])
        if self.isChecked(): icon_color = QColor(PALETTE["focus"])
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Map the existing vector coordinates into the 20 px icon canvas.
        # Leave space inside the icon canvas for the stroke and antialiasing.
        drawing_scale = .84
        p.translate(icon_size / 2, icon_size / 2)
        p.scale(drawing_scale, drawing_scale)
        p.translate(-18.5 if self.kind == "folder" else -18, -18)
        p.setPen(QPen(icon_color, 1 / drawing_scale))
        if self.kind.startswith(("lang-", "theme-")):
            scale = 1.125 if self.kind == "theme-light" else 18 / 14
            p.translate(18, 18)
            p.scale(scale, scale)
            p.translate(-18, -18)
            preference_pen = QPen(icon_color, 1 / (scale * drawing_scale))
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
        elif self.kind == "background":
            p.fillRect(QRectF(9, 9, 9, 9), icon_color)
            p.fillRect(QRectF(18, 18, 9, 9), icon_color)
            p.drawRect(9, 9, 18, 18)
        elif self.kind == "more":
            p.setBrush(icon_color)
            for x in (12, 18, 24): p.drawEllipse(QPoint(x, 18), 1, 1)
        elif self.kind == "sort-name":
            font = self.font(); font.setPixelSize(12); p.setFont(font)
            p.drawText(QRectF(7, 7, 11, 14), Qt.AlignmentFlag.AlignCenter, "A")
            p.drawText(QRectF(7, 18, 11, 14), Qt.AlignmentFlag.AlignCenter, "1")
            p.drawLine(20, 13, 28, 13); p.drawLine(20, 24, 25, 24)
        elif self.kind == "sort-date":
            p.drawEllipse(QRectF(9, 9, 18, 18))
            p.drawLine(18, 12, 18, 18); p.drawLine(18, 18, 23, 18)
        elif self.kind in ("sort-ascending", "sort-descending"):
            p.drawLine(18, 9, 18, 27)
            end, wing = (9, 14) if self.kind == "sort-ascending" else (27, 22)
            p.drawLine(13, wing, 18, end); p.drawLine(18, end, 23, wing)
        elif self.kind == "modified-visible":
            p.drawRoundedRect(QRectF(9, 11, 18, 16), 1.5, 1.5)
            p.drawLine(9, 16, 27, 16)
            p.drawLine(13, 9, 13, 13); p.drawLine(23, 9, 23, 13)
            p.drawLine(13, 20, 17, 20); p.drawLine(13, 23, 22, 23)
        elif self.kind == "tab-list":
            p.drawLine(14, 16, 18, 20); p.drawLine(18, 20, 22, 16)
        elif self.kind == "compare":
            p.drawRoundedRect(QRectF(8, 10, 20, 16), 1.5, 1.5)
            p.drawLine(18, 10, 18, 26)
            for x in (9, 19):
                landscape = QPainterPath()
                landscape.moveTo(x + 1, 23)
                landscape.lineTo(x + 4, 19)
                landscape.lineTo(x + 7, 23)
                p.drawPath(landscape)
                p.drawEllipse(QRectF(x + 2, 14, 1.5, 1.5))
        elif self.kind == "fullscreen":
            for x,y,dx,dy in ((9,9,1,1),(27,9,-1,1),(9,27,1,-1),(27,27,-1,-1)): p.drawLine(x,y,x+6*dx,y); p.drawLine(x,y,x,y+6*dy)
        elif self.kind == "lang-system":
            p.setPen(preference_pen)
            p.drawEllipse(QRectF(11, 11, 14, 14))
            p.drawEllipse(QRectF(15, 11, 6, 14))
            p.drawLine(QPoint(11, 18), QPoint(25, 18))
        elif self.kind in ("中", "A"):
            font = self.font()
            font.setPixelSize(22 if self.kind == "A" else 20)
            font.setBold(False)
            p.setFont(font)
            p.drawText(QRectF(4, 4, 28, 28), Qt.AlignmentFlag.AlignCenter, self.kind)
        elif self.kind == "theme-system":
            half = QPainterPath()
            half.moveTo(18, 11)
            half.arcTo(QRectF(11, 11, 14, 14), 90, -180)
            half.closeSubpath()
            p.fillPath(half, icon_color)
            p.setPen(preference_pen)
            p.drawEllipse(QRectF(11, 11, 14, 14))
        elif self.kind == "theme-light":
            p.setPen(preference_pen)
            p.drawEllipse(QRectF(14.5, 14.5, 7, 7))
            for x1,y1,x2,y2 in ((18,10,18,12),(18,24,18,26),(10,18,12,18),(24,18,26,18),(12,12,13.5,13.5),(22.5,22.5,24,24),(12,24,13.5,22.5),(22.5,13.5,24,12)):
                ray = QPainterPath()
                ray.moveTo(x1, y1); ray.lineTo(x2, y2)
                p.drawPath(ray)
        elif self.kind == "theme-dark":
            outer = QPainterPath(); outer.addEllipse(QRectF(11, 11, 14, 14))
            cutout = QPainterPath(); cutout.addEllipse(QRectF(15, 8, 14, 14))
            p.setPen(preference_pen)
            p.drawPath(outer.subtracted(cutout))
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
        self.apply_style()

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

    def apply_style(self):
        self.setStyleSheet(f"QToolButton{{background:transparent;border:0;border-radius:6px;padding:0 3px;}}QToolButton:hover{{background:{toolbar_hover_color()};}}")

    def _format(self, value: int) -> str:
        return f"{value / self.divisor:g}{self.suffix}"

    def set_value(self, value: int) -> None:
        self.current_value = value
        self.setText(self._format(value))
        if not self.editor_menu.isVisible():
            self.spin.setValue(value / self.divisor)

    def open_editor(self, anchor=None) -> None:
        self.spin.setValue(self.current_value / self.divisor)
        anchor = anchor if isinstance(anchor, QWidget) else self
        self.editor_menu.popup(anchor.mapToGlobal(QPoint(0, anchor.height())))
        QTimer.singleShot(0, self.spin.setFocus)

    def choose(self, value: int) -> None:
        self.valueChosen.emit(value)
        self.editor_menu.hide()

    def apply_value(self) -> None:
        self.spin.interpretText()
        self.choose(round(self.spin.value() * self.divisor))


class ThumbnailTile(QFrame):
    """A thumbnail card with its name above and optional modified time below."""
    clicked_path = Signal(Path)
    contextRequested = Signal(Path, QPoint)
    def __init__(self, path: Path, pixmap: QPixmap | None, size: int, selected: bool, show_modified=True) -> None:
        super().__init__(); self.path = path; self.selected = selected; self.setFixedSize(size + 12, size + 38)
        self._drag_start = None
        layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5); layout.setSpacing(2)
        self.name = QLabel(path.name); self.name.setAlignment(Qt.AlignmentFlag.AlignCenter); self.name.setFixedHeight(20); self.name.setWordWrap(False)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setFixedHeight(size)
        self.modified_label = QLabel()
        self.modified_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.modified_label.setFixedHeight(18)
        font = self.modified_label.font(); font.setPixelSize(10); self.modified_label.setFont(font)
        for label in (self.name, self.preview, self.modified_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if pixmap: self.preview.setPixmap(pixmap)
        layout.addWidget(self.name); layout.addWidget(self.preview); layout.addWidget(self.modified_label)
        self.set_size(size, show_modified)
        self.update_modified()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self.contextRequested.emit(self.path, self.mapToGlobal(pos)))
        self.apply_style()

    def set_size(self, size, show_modified):
        self.setFixedSize(size + 12, size + 38 + (20 if show_modified else 0))
        self.preview.setFixedHeight(size)
        self.modified_label.setVisible(show_modified)
        self.elide_modified()

    def update_modified(self, mtime_ns=None):
        try:
            if mtime_ns is None: mtime_ns = self.path.stat().st_mtime_ns
            text = datetime.fromtimestamp(mtime_ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError, OverflowError):
            text = ""
        self.modified_label.setToolTip(text)
        self.elide_modified()

    def elide_modified(self):
        self.modified_label.setText(self.modified_label.fontMetrics().elidedText(
            self.modified_label.toolTip(), Qt.TextElideMode.ElideRight, max(0, self.width() - 12)))
    def apply_style(self) -> None:
        color = PALETTE["selection"] if self.selected else PALETTE["thumbnail_card"]
        text = PALETTE["selection_text"] if self.selected else PALETTE["text"]
        border = f"1px solid {PALETTE['accent']}" if self.selected and QColor(PALETTE["surface"]).lightness() < 128 else "0"
        if not self.selected:
            border = f"1px solid {PALETTE['thumbnail_edge']}"
        self.setStyleSheet(f"ThumbnailTile{{background:{color};border:{border};border-radius:9px;}} QLabel{{background:{color};color:{text};}}")
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
    rowRequested = Signal(int)
    sortRequested = Signal(str, bool)
    def __init__(self, labels: dict[str, str], parent=None):
        self.columns = 1
        super().__init__(parent); self.labels=labels; self.files=[]; self.selected_path=None; self.size=THUMBNAIL_BASE_SIZE; self.buttons={}; self.failed_paths=set()
        self.sort_mode = "natural"
        self.sort_descending = False
        self.show_modified = True
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,4,10,8); layout.setSpacing(4)
        header=QHBoxLayout(); header.setSpacing(4); self.max_button=IconButton("expand",labels["max"]); header.addWidget(self.max_button); header.addStretch(); self.size_label=ScaleValueButton(self.size,72,260,THUMBNAIL_BASE_SIZE,1,"px",labels["edit_thumb"]); header.addWidget(self.size_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,THUMBNAIL_BASE_SIZE); self.slider.setRange(72,260); self.slider.setValue(self.size); self.slider.setFixedSize(SLIDER_WIDTH,30); self.slider.logicalValueChanged.connect(self._resize); self.size_label.valueChosen.connect(self.slider.setValue); header.addWidget(self.slider); layout.addLayout(header)
        self.tab_slot = QWidget()
        self.tab_slot.setObjectName("thumbnailTabSlot")
        self.tab_slot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.tab_slot.setFixedHeight(34)
        self.tab_slot.setMaximumWidth(0)
        tab_layout = QHBoxLayout(self.tab_slot)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        header.insertWidget(0, self.tab_slot, 1)
        header.takeAt(2)  # The tab slot supplies the flexible space.
        self.sort_button = IconButton("sort-name", labels["sort_method"])
        self.sort_button.setCheckable(True)
        self.direction_button = IconButton("sort-ascending", labels["sort_direction"])
        self.direction_button.setCheckable(True)
        header.insertWidget(1, self.sort_button)
        header.insertWidget(2, self.direction_button)
        self.context_menu = QMenu(self)
        self.sort_button.clicked.connect(lambda: self.sortRequested.emit(
            "modified" if self.sort_mode == "natural" else "natural", self.sort_descending))
        self.direction_button.clicked.connect(lambda: self.sortRequested.emit(self.sort_mode, not self.sort_descending))
        self.update_sort_buttons()
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.grid_host=QWidget(); self.grid_host.setObjectName("thumbnailGrid"); self.grid_host.setStyleSheet(f"#thumbnailGrid{{background:{PALETTE['pane']};}}"); self.grid=QGridLayout(self.grid_host); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft); self.scroll.setWidget(self.grid_host); layout.addWidget(self.scroll)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumSize(54, 50)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._loaded = {}
        self._pending_paths = set()
        self._jobs = {}
        self._stopped = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(10)
        self.preview_timer.timeout.connect(self.load_previews)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.build)
        self.scroll.verticalScrollBar().valueChanged.connect(self.schedule_previews)
        self.toolbar_overflow = ToolbarOverflow(self, header, [self.slider, self.size_label, self.max_button, self.direction_button, self.sort_button],
            lambda: self.labels["more_tools"], {self.slider: self.size_label},
            self.toolbar_width, flex_widgets=(self.tab_slot,))
        for widget in (self.scroll, self.scroll.viewport(), self.grid_host,
                       self.scroll.verticalScrollBar(), self.scroll.horizontalScrollBar()):
            widget.installEventFilter(self)

    def update_sort_buttons(self):
        modified = self.sort_mode == "modified"
        self.sort_button.setChecked(modified)
        self.sort_button.set_kind("sort-date" if modified else "sort-name",
            f"{self.labels['sort_method']}: {self.labels['sort_modified' if modified else 'sort_natural']}")
        self.direction_button.setChecked(self.sort_descending)
        direction = "sort-descending" if self.sort_descending else "sort-ascending"
        self.direction_button.set_kind(direction,
            f"{self.labels['sort_direction']}: {self.labels['sort_descending' if self.sort_descending else 'sort_ascending']}")
        for button in (self.sort_button, self.direction_button): button.setAccessibleName(button.toolTip())

    def set_show_modified(self, show):
        self.show_modified = bool(show)
        self.build()

    def show_file_menu(self, path, position):
        self.select_clicked(path)
        menu = self.context_menu
        menu.clear()
        copy = menu.addAction(shortcut_tooltip(self.labels["copy"], QKeySequence.StandardKey.Copy))
        copy.triggered.connect(lambda checked=False: copy_file(path))
        properties = menu.addAction(self.labels["properties"])
        properties.triggered.connect(lambda checked=False: self.open_properties(path))
        for action in (copy, properties): action.setEnabled(path.is_file())
        menu.popup(position)

    def open_properties(self, path):
        self.properties_dialog = show_properties(path, self, self.labels)

    def toolbar_width(self):
        margins = self.layout().contentsMargins()
        width = self.width() - margins.left() - margins.right()
        if self.tab_slot.layout().count():
            strip = self.tab_slot.layout().itemAt(0).widget()
            target = min(420, max(1, strip.findChild(QTabBar).count()) * 150 + 42)
            reserved = max(0, min(target, max(190, round(width * .6)), width - 38))
            self.tab_slot.setMinimumWidth(reserved)
        return width

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            if event.modifiers() == Qt.KeyboardModifier.NoModifier and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                if event.type() == QEvent.Type.KeyPress:
                    self.rowRequested.emit(-1 if event.key() == Qt.Key.Key_Up else 1)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def select_clicked(self, path):
        self.scroll.setFocus(Qt.FocusReason.MouseFocusReason)
        self.select(path)

    def set_files(self, files, selected=None, *, emit_selection=True):
        self.files=files; self.selected_path=selected if selected in files else (files[0] if files else None); self.build()
        if emit_selection and self.selected_path: self.selected.emit(self.selected_path)
    def _resize(self,v): self.size=v; self.size_label.set_value(v); self.build()
    def build(self):
        if self._stopped: return
        wanted = set(self.files)
        for path in list(self.buttons):
            if path not in wanted:
                tile = self.buttons.pop(path)
                self.grid.removeWidget(tile)
                tile.deleteLater()
                self._loaded.pop(path, None)
        self.failed_paths.intersection_update(wanted)
        self._pending_paths.intersection_update(wanted)
        cols = max(1, self.scroll.viewport().width() // (self.size + 20))
        signature = (cols, self.size, self.show_modified, tuple(self.files))
        rearrange = signature != getattr(self, "_layout_signature", None)
        self._layout_signature = signature
        self.columns = cols
        for index, path in enumerate(self.files):
            tile = self.buttons.get(path)
            new = tile is None
            if new:
                tile = ThumbnailTile(path, None, self.size, path == self.selected_path, self.show_modified)
                tile.clicked_path.connect(self.select_clicked)
                tile.contextRequested.connect(self.show_file_menu)
                self.buttons[path] = tile
            selected = path == self.selected_path
            if tile.selected != selected:
                tile.selected = selected
                tile.apply_style()
            resized = tile.size() != QSize(self.size + 12, self.tile_height())
            if resized:
                tile.set_size(self.size, self.show_modified)
            if new or rearrange or resized:
                self.grid.addWidget(tile, index // cols, index % cols)
            if self._loaded.get(path) != THUMBNAILS.key(path, self.size, self.devicePixelRatioF()):
                self._pending_paths.add(path)
        self.schedule_previews()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "layout_timer"): self.layout_timer.start(0)

    def schedule_previews(self, *_):
        if not self._stopped and not self.preview_timer.isActive() and (self._pending_paths or self._jobs):
            self.preview_timer.start()

    def preview_order(self):
        # Prioritize the viewport and one nearby row, then decode the rest.
        row_height = self.tile_height() + max(0, self.grid.verticalSpacing())
        first_row = max(0, self.scroll.verticalScrollBar().value() // row_height - 1)
        last_row = (self.scroll.verticalScrollBar().value() + self.scroll.viewport().height()) // row_height + 2
        visible = self.files[first_row * self.columns:last_row * self.columns]
        priority = list(dict.fromkeys(visible + ([self.selected_path] if self.selected_path else [])))
        seen = set(priority)
        return [path for path in priority + [p for p in self.files if p not in seen] if path in self._pending_paths]

    def tile_height(self):
        return self.size + 38 + (20 if self.show_modified else 0)

    def apply_preview(self, key, image):
        path = key[0]
        if path not in self.buttons: return
        self.buttons[path].preview.setPixmap(QPixmap.fromImage(image))
        self._loaded[path] = key
        self.failed_paths.discard(path)
        self._pending_paths.discard(path)

    def load_previews(self):
        if self._stopped: return
        THUMBNAILS.collect()
        for key, future in list(self._jobs.items()):
            if not future.done(): continue
            del self._jobs[key]
            path = key[0]
            if path not in self.buttons: continue
            if key != THUMBNAILS.key(path, self.size, self.devicePixelRatioF()):
                self._pending_paths.add(path)
                continue
            if future.cancelled():
                self._pending_paths.add(path)
            elif future.exception() is not None:
                self.failed_paths.add(path)
                self._pending_paths.discard(path)
            else:
                self.apply_preview(key, future.result())
        if len(self._jobs) >= 2: return
        busy = {key[0] for key in self._jobs}
        applied = 0
        for path in self.preview_order():
            if path in busy: continue
            key = THUMBNAILS.key(path, self.size, self.devicePixelRatioF())
            image = THUMBNAILS.get(key)
            if image is not None:
                self.apply_preview(key, image)
                applied += 1
                if applied >= 12: break
            elif len(self._jobs) < 2:
                self._jobs[key] = THUMBNAILS.request(key)
            else:
                break
        if not self._pending_paths and not self._jobs: self.preview_timer.stop()

    def refresh_previews(self, paths):
        requested = set(paths).intersection(self.buttons)
        for path in requested:
            THUMBNAILS.invalidate(path)
            self._pending_paths.add(path)
        self.schedule_previews()
        # Full-image reloads can proceed independently of thumbnail decoding.
        return requested

    def shutdown(self):
        self._stopped = True
        self.preview_timer.stop()
        self.layout_timer.stop()
        self._pending_paths.clear()
        for future in self._jobs.values(): future.cancel()
        self._jobs.clear()

    def select(self,path):
        if path not in self.files: return
        self.selected_path=path
        for p,b in self.buttons.items(): b.selected = p == path; b.apply_style()
        if path in self.buttons: self.scroll.ensureWidgetVisible(self.buttons[path])
        self.selected.emit(path)
        QTimer.singleShot(0, self, self.ensure_selection_visible)

    def ensure_selection_visible(self):
        if self.selected_path in self.buttons:
            self.grid.activate()
            self.scroll.ensureWidgetVisible(self.buttons[self.selected_path])


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


class ToolbarOverflow(QObject):
    """Keep the existing controls and expose hidden ones through a live menu."""
    def __init__(self, host, layout, hide_order, title, slider_editors=None, available_width=None, flex_widgets=()):
        super().__init__(host)
        self.host, self.layout = host, layout
        self.hide_order, self.title = hide_order, title
        self.slider_editors = slider_editors or {}
        self.flex_widgets = set(flex_widgets)
        self.available_width = available_width or (lambda: host.width() - layout.contentsMargins().left() - layout.contentsMargins().right())
        self.items = [layout.itemAt(index) for index in range(layout.count())]
        self.widgets = [item.widget() for item in self.items if item.widget() is not None]
        self.spaces = {index: item.spacerItem().sizeHint().width() for index, item in enumerate(self.items)
                       if item.spacerItem() is not None and layout.stretch(index) == 0}
        self.separators = [index for index, item in enumerate(self.items) if isinstance(item.widget(), ToolbarSeparator)]
        self.overflowed = []
        self.more_button = IconButton("more", title(), host)
        self.more_button.setAccessibleName(title())
        self.menu = QMenu(self.more_button)
        self.menu.aboutToShow.connect(self.populate_menu)
        self.more_button.setMenu(self.menu)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.hide()
        layout.addWidget(self.more_button)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update)
        host.installEventFilter(self)
        self.timer.start(0)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.update()
        elif event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.FontChange):
            self.timer.start(0)
        return super().eventFilter(watched, event)

    def decoration_state(self, visible):
        shown = set()
        spaces = dict(self.spaces)
        pending = []
        has_content = False
        for index, item in enumerate(self.items):
            widget = item.widget()
            if isinstance(widget, ToolbarSeparator):
                pending.append(index)
            elif widget in visible:
                if has_content and pending: shown.add(self.items[pending[-1]].widget())
                has_content = True
                pending.clear()
        for index in self.separators:
            if self.items[index].widget() not in shown:
                for neighbor in (index - 1, index + 1):
                    if neighbor in spaces: spaces[neighbor] = 0
        return shown, spaces

    def required_width(self, visible, more):
        separators, spaces = self.decoration_state(visible)
        shown = [widget for widget in self.widgets if widget in visible or widget in separators]
        widths = [widget.minimumWidth() if widget in self.flex_widgets else
                  0 if widget.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored else
                  min(widget.maximumWidth(), max(widget.minimumWidth(), widget.sizeHint().width())) for widget in shown]
        count = len(shown) + int(more)
        return sum(widths) + sum(spaces.values()) + (self.more_button.width() if more else 0) + max(0, count - 1) * self.layout.spacing()

    def update(self):
        width = self.available_width()
        if width <= 0: return
        visible = {widget for widget in self.widgets if not isinstance(widget, ToolbarSeparator)}
        hidden = []
        if self.required_width(visible, False) > width:
            for widget in self.hide_order:
                visible.discard(widget)
                hidden.append(widget)
                if self.required_width(visible, True) <= width: break
            if self.required_width(visible, True) > width:
                visible = {widget for widget in visible if widget.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Ignored}
        separators, spaces = self.decoration_state(visible)
        changed = False
        for widget in self.widgets:
            show = widget in visible or widget in separators
            if widget.isHidden() == show:
                widget.setVisible(show)
                changed = True
        for index, value in spaces.items():
            spacer = self.items[index].spacerItem()
            if spacer.sizeHint().width() != value:
                spacer.changeSize(value, 0)
                changed = True
        self.overflowed = [widget for widget in self.widgets if widget in hidden]
        if self.more_button.isHidden() == bool(hidden):
            self.more_button.setVisible(bool(hidden))
            changed = True
        self.more_button.setToolTip(self.title())
        self.more_button.setAccessibleName(self.title())
        if changed: self.layout.invalidate()

    def populate_menu(self):
        self.menu.clear()
        added = set()
        for widget in self.overflowed:
            control = self.slider_editors.get(widget, widget)
            if control in added: continue
            added.add(control)
            if isinstance(control, ScaleValueButton):
                action = self.menu.addAction(f"{control.toolTip()} ({control.text()})")
                action.triggered.connect(lambda checked=False, button=control:
                    QTimer.singleShot(0, self.host, lambda: button.open_editor(self.more_button)))
            elif isinstance(control, QToolButton):
                action = self.menu.addAction(control.icon(), control.toolTip() or control.text())
                action.setCheckable(control.isCheckable())
                action.setChecked(control.isChecked())
                action.triggered.connect(lambda checked=False, button=control: button.click())
            else: continue
            action.setEnabled(control.isEnabled())


class ImagePane(QFrame):
    interacted = Signal()

    def __init__(self, labels, parent=None):
        super().__init__(parent); self.labels=labels; self.path=None; self.frames=[]; self.index=0; self.rotation=0; self.fh=False; self.fv=False; self.zoom=1.0; self.fit_to_pane=False; self.auto_scale=False; self._applying_auto_scale=False; self.display_scale=1.0; self.full_window=None; self.timer=QTimer(self); self.timer.timeout.connect(self.next_frame)
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,4,10,8); layout.setSpacing(4)
        self.comparison_title = None
        self.comparison_selected = False
        self.background_mode = "default"
        bar=QHBoxLayout(); self.rotate_b=IconButton("rotate",labels["rotate"]); self.mh=IconButton("mirror-h",labels["mh"]); self.mv=IconButton("mirror-v",labels["mv"]); self.fit_b=IconButton("fit",labels["fit"]); self.fit_b.setCheckable(True); self.fit_b.toggled.connect(self.set_fit); self.max_button=IconButton("expand",labels["max"]); self.full=IconButton("fullscreen",labels["full"])
        for b,fn in ((self.rotate_b,self.rotate),(self.mh,self.mirror_h),(self.mv,self.mirror_v)): b.clicked.connect(fn); bar.addWidget(b)
        bar.setSpacing(4)
        separate_tools(bar)
        self.full.clicked.connect(self.open_full)
        self.background_button = IconButton("background", labels["background"])
        self.background_button.clicked.connect(self.show_background_menu)
        bar.addWidget(self.background_button)
        self.background_menu = QMenu(self)
        self.background_panel = QWidget()
        choices = QGridLayout(self.background_panel)
        choices.setContentsMargins(8, 8, 8, 8)
        choices.setSpacing(4)
        self.background_choices = {}
        for index, mode in enumerate(IMAGE_BACKGROUND_COLORS):
            button = QPushButton()
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, mode=mode: self.choose_background(mode))
            self.background_choices[mode] = button
            if mode == "default":
                button.setMinimumHeight(34)
                choices.addWidget(button, 0, 0, 1, 4)
            else:
                button.setFixedSize(40, 30)
                choices.addWidget(button, 1 + (index - 1) // 4, (index - 1) % 4)
        background_action = QWidgetAction(self.background_menu)
        background_action.setDefaultWidget(self.background_panel)
        self.background_menu.addAction(background_action)
        self.filename_label=QLabel(); self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.filename_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed); bar.addWidget(self.filename_label,1)
        for button in (self.fit_b,self.max_button,self.full): bar.addWidget(button)
        self.zoom_label=ScaleValueButton(1000,1,4000,1000,10,"%",labels["edit_zoom"]); bar.addWidget(self.zoom_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,1000); self.slider.setRange(1,4000); self.slider.setValue(1000); self.slider.logicalValueChanged.connect(self.set_zoom_percent); self.zoom_label.valueChosen.connect(self.choose_zoom); self.slider.setFixedSize(SLIDER_WIDTH,30); bar.addWidget(self.slider)
        self.toolbar_widget = QWidget(self)
        self.toolbar_widget.setLayout(bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self.toolbar_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        bar.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumSize(54, 50)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.toolbar_overflow = ToolbarOverflow(self.toolbar_widget, bar,
            [self.slider, self.zoom_label, self.background_button, self.full, self.max_button, self.mv, self.mh, self.rotate_b, self.fit_b],
            lambda: self.labels["more_tools"], {self.slider: self.zoom_label})
        layout.addWidget(self.toolbar_widget)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(False); self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.label=QLabel(labels["empty"]); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.label.setStyleSheet(f"color:{PALETTE['muted']};background:transparent;"); self.scroll.setWidget(self.label); layout.addWidget(self.scroll)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.toolbar = bar
        self.update_shortcut_tooltips()
        self.apply_background()
        for widget in self.findChildren(QWidget): widget.installEventFilter(self)

    def update_shortcut_tooltips(self):
        for button, label, keys in ((self.fit_b, "fit", "Alt+F"), (self.rotate_b, "rotate", "Alt+C"),
                                    (self.mv, "mv", "Alt+V"), (self.mh, "mh", "Alt+H")):
            button.setToolTip(shortcut_tooltip(self.labels[label], keys))
        self.full.setToolTip(shortcut_tooltip(self.labels["full"], "F11"))
        self.zoom_label.setToolTip(shortcut_tooltip(self.labels["edit_zoom"], "+", "-", "0"))
        self.slider.setToolTip(shortcut_tooltip(self.labels["zoom"], "+", "-", "0"))
        self.zoom_label.reset_button.setToolTip(shortcut_tooltip("100%", "0"))

    def background_color(self):
        return IMAGE_BACKGROUND_COLORS[self.background_mode] or PALETTE["pane"]

    def apply_background(self):
        color = self.background_color()
        self.scroll.viewport().setStyleSheet(f"background:{color};")
        if self.full_window is not None:
            self.full_window.centralWidget().setStyleSheet(f"background:{color};")
        self.background_button.setToolTip(self.labels["background"])
        self.background_button.setAccessibleName(self.labels["background"])
        self.background_panel.setStyleSheet(f"background:{PALETTE['card']};")
        for mode, button in self.background_choices.items():
            swatch = IMAGE_BACKGROUND_COLORS[mode] or PALETTE["pane"]
            text = "#ffffff" if QColor(swatch).lightness() < 128 else "#172a31"
            name = self.labels[f"bg_{mode}"]
            button.setText(name if mode == "default" else "")
            button.setAccessibleName(name)
            button.setToolTip(name if mode == "default" else f"{name} ({swatch})")
            button.setChecked(mode == self.background_mode)
            button.setStyleSheet(
                f"QPushButton{{background:{swatch};color:{text};border:1px solid {PALETTE['edge']};border-radius:4px;padding:3px 6px;}}"
                f"QPushButton:hover,QPushButton:checked{{border:2px solid {PALETTE['focus']};padding:2px 5px;}}")

    def set_background(self, mode):
        self.background_mode = mode if isinstance(mode, str) and mode in IMAGE_BACKGROUND_COLORS else "default"
        self.apply_background()

    def choose_background(self, mode):
        self.set_background(mode)
        self.background_menu.hide()

    def show_background_menu(self):
        self.apply_background()
        anchor = self.background_button if self.background_button.isVisible() else self.toolbar_overflow.more_button
        QTimer.singleShot(0, self, lambda: self.background_menu.popup(anchor.mapToGlobal(QPoint(0, anchor.height()))))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.comparison_selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(PALETTE["focus"]), 2))
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
            self.setMinimumSize(54, 50)
            self.layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.update_filename()
        self.update()
    @staticmethod
    def read_frames(path):
        if path.suffix.lower() == ".svg": return [(SvgDocument(path), 100)]
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
        if isinstance(im, SvgDocument): return self.svg_image(self.image_size())
        if self.rotation: im=im.rotate(-self.rotation,expand=True)
        if self.fh: im=ImageOps.mirror(im)
        if self.fv: im=ImageOps.flip(im)
        return im
    def image_size(self):
        width, height = self.frames[self.index][0].size
        return (height, width) if self.rotation % 180 else (width, height)

    def svg_image(self, size):
        source_size = (size[1], size[0]) if self.rotation % 180 else size
        image = self.frames[self.index][0].render(source_size)
        if self.rotation: image = image.transformed(QTransform().rotate(self.rotation), Qt.TransformationMode.SmoothTransformation)
        if self.fh or self.fv: image = image.transformed(QTransform().scale(-1 if self.fh else 1, -1 if self.fv else 1))
        return image

    def render(self):
        if not self.frames:return
        width, height = self.image_size()
        scale=min(max(1,self.scroll.viewport().width()-8)/width,max(1,self.scroll.viewport().height()-8)/height) if self.fit_to_pane else self.zoom
        self.display_scale=scale
        if self.fit_to_pane:
            ticks=max(1,round(scale*1000))
            self.slider.blockSignals(True)
            self.slider.setMaximum(max(4000,ticks))
            self.slider.setValue(ticks)
            self.slider.blockSignals(False)
            self.zoom_label.set_value(ticks)
        size=(max(1,round(width*scale)),max(1,round(height*scale)))
        svg = isinstance(self.frames[self.index][0], SvgDocument)
        self.label.setScaledContents(svg)
        if svg:
            dpr = self.devicePixelRatioF()
            pix = QPixmap.fromImage(self.svg_image(tuple(max(1, round(value * dpr)) for value in size)))
            pix.setDevicePixelRatio(dpr)
        else:
            im=self.image()
            if size != im.size: im=im.resize(size,Image.Resampling.LANCZOS)
            pix=QPixmap.fromImage(qimage(im))
        self.label.setPixmap(pix); self.label.setFixedSize(*size)
        if self.full_window is not None:
            self.update_full_image()
    def resizeEvent(self,e): super().resizeEvent(e); QTimer.singleShot(0,self.refresh_after_resize)
    def refresh_after_resize(self):
        self.apply_default_zoom()
        self.render()
    def apply_default_zoom(self):
        if not self.auto_scale or not self.frames or not self.isVisible(): return
        width, height = self.image_size()
        oversized=width>max(1,self.scroll.width()-8) or height>max(1,self.scroll.height()-8)
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
    def toggle_fit(self):
        self.fit_b.click()

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
        w = QMainWindow(self)
        w.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        w.destroyed.connect(lambda: setattr(self, "full_window", None) if self.full_window is w else None)
        w.setWindowState(Qt.WindowState.WindowFullScreen)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        label.setMinimumSize(0, 0)
        label.setStyleSheet(f"background:{self.background_color()};")
        w.setCentralWidget(label)
        w.keyPressEvent = lambda e: self.open_full() if e.key() == Qt.Key.Key_Escape else None
        self.full_window=w
        self.apply_background()
        label.resizeEvent = lambda event: self.update_full_image()
        w.show(); self.update_full_image()

    def update_full_image(self):
        if self.full_window is None or not self.frames: return
        label = self.full_window.centralWidget()
        original = QSize(*self.image_size())
        size = original.scaled(label.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio).boundedTo(original)
        dpr = label.devicePixelRatioF()
        pixels = (max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)))
        if isinstance(self.frames[self.index][0], SvgDocument):
            pixmap = QPixmap.fromImage(self.svg_image(pixels))
        else:
            image = self.image()
            if image.size != pixels: image = image.resize(pixels, Image.Resampling.LANCZOS)
            pixmap = QPixmap.fromImage(qimage(image))
        pixmap.setDevicePixelRatio(dpr)
        label.setPixmap(pixmap)


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
        self.image_slot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_slot.setMinimumSize(54, 50)
        slot_layout = QVBoxLayout(self.image_slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        slot_layout.addWidget(self.image)
        self.split.addWidget(self.image_slot)
        layout.addWidget(self.split)
        self.thumbs.selected.connect(self.select_image)
        self.thumbs.rowRequested.connect(self.select_row)
        self.thumbs.sortRequested.connect(self.set_sort)
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
        self.thumbs.sort_mode = state.get("sort_mode", "natural") if state else "natural"
        self.thumbs.sort_descending = state.get("sort_descending", False) if state else False
        self.thumbs.update_sort_buttons()
        self.files = self.ordered_files(image_files(self.folder))
        self._layout_pending = True
        if state:
            self.image.set_background(state.get("image_background", "default"))
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

    def ordered_files(self, files, versions=None):
        if self.thumbs.sort_mode == "modified":
            versions = self.image_versions(files) if versions is None else versions
            return sorted(files, key=lambda path: ((versions.get(path) or (0, 0))[1], natural_key(path)),
                          reverse=self.thumbs.sort_descending)
        return sorted(files, key=natural_key, reverse=self.thumbs.sort_descending)

    def set_sort(self, mode, descending):
        if mode not in ("natural", "modified"): return
        self.cancel_scroll_restore()
        self.thumbs.sort_mode = mode
        self.thumbs.sort_descending = bool(descending)
        self.thumbs.update_sort_buttons()
        selected = self.thumbs.selected_path
        self.files = self.ordered_files(self.files)
        self.thumbs.set_files(self.files, selected, emit_selection=False)
        if selected in self.thumbs.buttons:
            QTimer.singleShot(0, self.thumbs, lambda: self.thumbs.scroll.ensureWidgetVisible(self.thumbs.buttons[selected])
                              if selected in self.thumbs.buttons else None)

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
                 "sort_mode": self.thumbs.sort_mode, "sort_descending": self.thumbs.sort_descending,
                 "image_zoom": self.image.zoom, "fit_to_pane": self.image.fit_to_pane,
                 "image_background": self.image.background_mode,
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
        self.thumbs.update_sort_buttons()
        for pane in (self.thumbs, self.image):
            pane.max_button.setToolTip(labels["restore" if pane.max_button.kind == "shrink" else "max"])
        self.thumbs.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};")
        self.image.apply_background()
        self.thumbs.grid_host.setStyleSheet(f"#thumbnailGrid{{background:{PALETTE['pane']};}}")
        for tile in self.thumbs.buttons.values(): tile.apply_style()
        for button, key in ((self.image.rotate_b, "rotate"), (self.image.mh, "mh"), (self.image.mv, "mv"), (self.image.fit_b, "fit"), (self.image.full, "full")):
            button.setToolTip(labels[key])
        self.thumbs.size_label.setToolTip(labels["edit_thumb"])
        self.image.zoom_label.setToolTip(labels["edit_zoom"])
        self.image.update_shortcut_tooltips()
        self.thumbs.size_label.apply_style()
        self.image.zoom_label.apply_style()
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
        self.thumbs.shutdown()
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
        files = self.ordered_files(files, versions)
        changed = {path for path in files if path in self._image_versions and versions[path] != self._image_versions[path]}
        changed.update(self._changed_image_paths.intersection(files))
        self._changed_image_paths.clear()
        self._image_versions = versions
        for path in changed:
            if path in self.thumbs.buttons and versions.get(path) is not None:
                self.thumbs.buttons[path].update_modified(versions[path][1])
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
            self._pending_image_retries = {path: self._pending_image_retries.get(path, 8) for path in self.thumbs.failed_paths}
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
            index = self.files.index(previous) if previous in self.files else -1
            successors = self.files[index + 1:] + self.files[:max(0, index)]
            remaining = set(files)
            selected = next((path for path in successors if path in remaining), files[0] if files else None)
        elif selected is None and files:
            selected = self._restore_selected if self._restore_selected in files else files[0]
        thumbs = self.thumbs
        scroll_position = thumbs.scroll.verticalScrollBar().value()
        self.files = files
        reload_image = selected != previous or (selected is not None and not self.image.frames)
        thumbs.set_files(files, selected, emit_selection=reload_image)
        if changed: thumbs.refresh_previews(changed)
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

    def select_row(self, direction):
        if not self.files: return
        selected = self.thumbs.selected_path
        index = self.files.index(selected) if selected in self.files else 0
        columns = self.thumbs.columns
        target_row = index // columns + direction
        if target_row < 0 or target_row * columns >= len(self.files): return
        self.thumbs.select(self.files[min(len(self.files) - 1, index + direction * columns)])

    def select_boundary(self, last):
        if self.files: self.thumbs.select(self.files[-1 if last else 0])

    def copy_selected_file(self):
        path = self.thumbs.selected_path
        if path is not None: copy_file(path)



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
                painter.setBrush(QColor(PALETTE["focus"]))
                painter.setPen(QPen(QColor(PALETTE["focus"]), 1))
            painter.drawRoundedRect(QRectF(3.5, 3.5, 13, 13), 2, 2)
            if self.isChecked():
                painter.setPen(QPen(QColor(PALETTE["active_text"]), 1.5))
                painter.drawLine(QPoint(6, 10), QPoint(9, 13))
                painter.drawLine(QPoint(9, 13), QPoint(14, 7))
        else:
            painter.drawPolyline([QPoint(3, 7), QPoint(3, 4), QPoint(8, 4), QPoint(10, 6), QPoint(17, 6), QPoint(17, 8)])
            painter.drawPolyline([QPoint(3, 8), QPoint(18, 8), QPoint(15, 16), QPoint(2, 16), QPoint(3, 8)])
        painter.restore()
        if self.hasFocus():
            painter.setPen(QPen(QColor(PALETTE["focus"]), 1, Qt.PenStyle.DotLine))
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
        self.header.setFixedHeight(42)
        self.header_layout = QVBoxLayout(self.header)
        self.header_layout.setContentsMargins(10, 4, 10, 4)
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
        return QSize(min(200, max(150, size.width())), 34)

    def minimumTabSizeHint(self, index):
        width = 108 if self.width() < 182 else 150
        # Qt shows arrows for a one-pixel overflow but treats the last tab as
        # fully visible. Absorb that pixel in the first tab instead.
        if index == 0 and self.count() * width == self.width() + 1:
            width -= 1
        return QSize(width, 34)

    def paintEvent(self, event):
        painter = QPainter(self)
        visible = QRegion(self.rect())
        for button in self.findChildren(QToolButton):
            if button.isVisible() and button.objectName().startswith("Scroll"):
                # Native arrow buttons can be shorter than the tab strip.
                # Reserve their full-height columns, including the underline.
                visible -= QRegion(QRect(button.x(), 0, button.width(), self.height()))
        painter.setClipRegion(visible)
        order = [index for index in range(self.count()) if index != self.currentIndex()]
        if self.currentIndex() >= 0: order.append(self.currentIndex())
        for index in order:
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            selected = index == self.currentIndex()
            if selected:
                painter.fillRect(option.rect, QColor(PALETTE["card"]))
                painter.fillRect(option.rect.left(), option.rect.bottom() - 1, option.rect.width(), 2, QColor(PALETTE["focus"]))
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
    """A compact tab strip with a trailing control and separate page stack."""
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.strip = QFrame()
        self.strip.setObjectName("tabStrip")
        self.strip.setFixedHeight(34)
        self.strip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header = QHBoxLayout(self.strip)
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header.setSpacing(4)
        self.bar = FolderTabBar()
        self._closable = True
        self.bar.setExpanding(False)
        self.bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.header.addWidget(self.bar)
        self.header.addStretch(1)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
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
        self.header.addWidget(widget)

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
        self.show_modified = self.settings.get("show_modified", True) is not False
        self.language_mode = self.settings.get("language", "system")
        if self.language_mode not in LANGUAGE_MODES: self.language_mode = "system"
        self.lang = resolve_language(self.language_mode)
        self.t = TEXT[self.lang]
        self._closing = False
        self._previous_tab = None
        self.about_dialog = None
        self.about_action = None
        self._system_menu_hwnd = None
        self.closed_tabs = []
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
        self.setMinimumSize(260, 220)
        self.resize(1100, 780)
        self.setAcceptDrops(True)
        self.notification_bar = self.statusBar()
        self.notification_bar.hide()
        self.notification_bar.messageChanged.connect(lambda message: self.notification_bar.setVisible(bool(message)))
        self.build()
        if sys.platform == "darwin": self.setup_application_menu()
        self.setup_shortcuts()
        self.restore()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_system_menu()

    def setup_application_menu(self):
        if self.about_action is not None: return
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(True)
        self.application_menu = menu_bar.addMenu("PicView")
        self.about_action = QAction(self.t["about"], self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self.show_about)
        self.application_menu.addAction(self.about_action)

    def refresh_system_menu(self):
        if sys.platform == "win32" and self.isVisible():
            self._system_menu_hwnd = int(self.winId())
            install_about_item(self._system_menu_hwnd, self.t["about"] + "…")

    def nativeEvent(self, event_type, message):
        if is_about_message(event_type, message, getattr(self, "_system_menu_hwnd", None)):
            QTimer.singleShot(0, self, self.show_about)
            return True, 0
        return super().nativeEvent(event_type, message)

    def show_about(self):
        if self._closing: return
        if self.about_dialog is None:
            self.about_dialog = AboutDialog(self.t, self)
            self.about_dialog.finished.connect(lambda: setattr(self, "about_dialog", None))
        self.about_dialog.show()
        self.about_dialog.raise_()
        self.about_dialog.activateWindow()

    def current_tab(self):
        return self.tabs.currentWidget()

    def pages(self):
        return [self.tabs.widget(index) for index in range(self.tabs.count())]

    def build(self):
        root = QWidget()
        root.setObjectName("root")
        root.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 0, 8, 8)
        outer.setSpacing(0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        tool = QFrame()
        tool.setObjectName("toolbar")
        tool.setFixedHeight(42)
        layout = QHBoxLayout(tool)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        self.open_button = IconButton("folder", shortcut_tooltip(self.t["open"], QKeySequence.StandardKey.Open))
        self.vertical_button = IconButton("split-h", shortcut_tooltip(self.t["vertical"], "Alt+Shift+V"))
        self.horizontal_button = IconButton("split-v", shortcut_tooltip(self.t["horizontal"], "Alt+Shift+H"))
        self.compare_button = IconButton("compare", self.t["compare"])
        self.compare_button.setCheckable(True)
        self.compare_button.toggled.connect(self.set_compare)
        self.language_button = IconButton(LANGUAGE_ICONS[self.language_mode], self.t[f"lang_{self.language_mode}"])
        self.modified_button = IconButton("modified-visible", self.t["show_modified"])
        self.modified_button.setCheckable(True)
        self.modified_button.setChecked(self.show_modified)
        self.modified_button.toggled.connect(self.set_show_modified)
        self.theme_button = IconButton(f"theme-{self.theme_mode}", self.t[f"theme_{self.theme_mode}"])
        self.main_toolbar = tool
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
        self.tab_list_button = IconButton("tab-list", self.t["tab_list"])
        self.tab_list_button.setAccessibleName(self.t["tab_list"])
        self.tab_list_menu = QMenu(self.tab_list_button)
        self.tab_list_menu.setToolTipsVisible(True)
        self.tab_list_menu.aboutToShow.connect(self.populate_tab_list)
        self.tab_list_button.setMenu(self.tab_list_menu)
        self.tab_list_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tabs.setCornerWidget(self.tab_list_button)
        self.tabs.layout().removeWidget(self.tabs.strip)
        for button, action in ((self.open_button, self.choose), (self.vertical_button, lambda: self.set_orientation(Qt.Orientation.Vertical)),
                               (self.horizontal_button, lambda: self.set_orientation(Qt.Orientation.Horizontal)),
                               (self.compare_button, lambda: None)):
            if button in (self.vertical_button, self.compare_button): separate_tools(layout)
            button.clicked.connect(action)
            layout.addWidget(button)
        layout.addStretch(1)
        separate_tools(layout)
        layout.addWidget(self.modified_button)
        for button, action in ((self.language_button, self.toggle_lang), (self.theme_button, self.toggle_theme)):
            button.clicked.connect(action)
            layout.addWidget(button)
        self.toolbar_overflow = ToolbarOverflow(tool, layout,
            [self.theme_button, self.language_button, self.modified_button, self.horizontal_button, self.vertical_button, self.compare_button, self.open_button],
            lambda: self.t["more_tools"])
        outer.addWidget(self.tabs, 1)
        self.apply_styles()

    def mount_tab_strip(self, page):
        strip = self.tabs.strip
        old_slot = strip.parentWidget()
        slot = page.thumbs.tab_slot
        if old_slot is not slot:
            if old_slot is not None and old_slot.objectName() == "thumbnailTabSlot":
                old_slot.layout().removeWidget(strip)
                old_slot.setMinimumWidth(0)
                old_slot.setMaximumWidth(0)
            slot.setMaximumWidth(16777215)
            slot.layout().addWidget(strip)
            strip.show()
        page.thumbs.toolbar_overflow.update()

    def apply_styles(self):
        strip = PALETTE["card"]
        hover = PALETTE["pane"]
        self.setStyleSheet(f"""
            #root{{background:{PALETTE['surface']};}}
            #toolbar{{background:transparent;border:0;}}
            #card{{background:{PALETTE['card']};border:0;border-radius:12px;}}
            QLabel{{color:{PALETTE['text']};}}
            QStatusBar{{color:{PALETTE['warm']};background:{PALETTE['card']};}}
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
            #tabCloseButton:hover{{background:{hover};}}
            #tabCloseButton{{background:transparent;border:0;border-radius:4px;}}
        """)
    def add_page(self):
        page = FolderTab(self.t)
        page.thumbs.show_modified = self.show_modified
        page.notification.connect(lambda message, tab=page: self.show_notification(tab, message))
        page.attentionChanged.connect(self.update_tab_titles)
        self.tabs.addTab(page, self.t["empty_tab"])
        control = TabFolderControl(self.tabs.tabBar())
        control.toggled.connect(lambda checked, tab=page: self.check_compare_page(tab, checked))
        self.tabs.tabBar().setTabButton(self.tabs.indexOf(page), QTabBar.ButtonPosition.LeftSide, control)
        page.image.interacted.connect(lambda tab=page: self.focus_compare_page(tab))
        button = self.tabs.tabBar().tabButton(self.tabs.indexOf(page), QTabBar.ButtonPosition.RightSide)
        button.setToolTip(shortcut_tooltip(self.t["close_tab"], QKeySequence.StandardKey.Close))
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

    def populate_tab_list(self):
        self.tab_list_menu.clear()
        current = self.current_tab()
        for index, page in enumerate(self.pages()):
            action = self.tab_list_menu.addAction(self.tabs.tabText(index).replace("&", "&&"))
            action.setCheckable(page is current)
            action.setChecked(page is current)
            action.setToolTip(self.tabs.tabToolTip(index))
            action.triggered.connect(lambda checked=False, page=page: self.select_listed_tab(page))

    def select_listed_tab(self, page):
        if self.tabs.indexOf(page) >= 0:
            self.tabs.setCurrentWidget(page)

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
            self.mount_tab_strip(page)
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
        if page.folder is not None:
            self.closed_tabs.append((index, page.snapshot()))
            self.closed_tabs = self.closed_tabs[-20:]
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

    def select_tab_number(self, number):
        index = self.tabs.count() - 1 if number == 9 else number - 1
        if 0 <= index < self.tabs.count(): self.tabs.setCurrentIndex(index)

    def reopen_closed_tab(self):
        if not self.closed_tabs: return
        index, state = self.closed_tabs.pop()
        selected = Path(state["selected_file"]) if state["selected_file"] else None
        page = self.open_folder(Path(state["folder"]), selected, state=state, restoring=True)
        self.tabs.tabBar().moveTab(self.tabs.indexOf(page), min(index, self.tabs.count() - 1))
        self.tabs.setCurrentWidget(page)

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
        self.toolbar_overflow.timer.start(0)

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
                    ("Up", lambda: self.current_tab().select_row(-1)), ("Down", lambda: self.current_tab().select_row(1)),
                    ("Home", lambda: self.current_tab().select_boundary(False)), ("End", lambda: self.current_tab().select_boundary(True)),
                    ("PgUp", lambda: self.current_tab().select_relative(-1)), ("PgDown", lambda: self.current_tab().select_relative(1)),
                    ("Space", self.advance_or_check), ("Backspace", lambda: self.current_tab().select_relative(-1)),
                    ("Alt+F", lambda: self.image_action("toggle_fit")),
                    ("Alt+C", lambda: self.image_action("rotate")),
                    ("Alt+V", lambda: self.image_action("mirror_v")), ("Alt+H", lambda: self.image_action("mirror_h")),
                    ("Alt+Shift+V", lambda: self.set_orientation(Qt.Orientation.Vertical)),
                    ("Alt+Shift+H", lambda: self.set_orientation(Qt.Orientation.Horizontal)),
                    ("+", lambda: self.image_action("adjust_zoom", 10)), ("=", lambda: self.image_action("adjust_zoom", 10)),
                    ("-", lambda: self.image_action("adjust_zoom", -10)), ("0", lambda: self.image_action("reset_zoom")), ("F11", lambda: self.image_action("open_full"))]
        modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
        bindings += [("Ctrl+PgDown", lambda: self.switch_tab(1)),
                     ("Ctrl+PgUp", lambda: self.switch_tab(-1)),
                     ("Ctrl+Tab", lambda: self.switch_tab(1)),
                     ("Ctrl+Shift+Tab", lambda: self.switch_tab(-1)),
                     (f"{modifier}+W", lambda: self.close_tab()),
                     (f"{modifier}+Shift+T", self.reopen_closed_tab)]
        bindings += [(f"{modifier}+{number}", lambda number=number: self.select_tab_number(number))
                     for number in range(1, 10)]
        self.shortcuts = []
        registered = set()
        for keys, action in bindings:
            sequences = QKeySequence.keyBindings(keys) if isinstance(keys, QKeySequence.StandardKey) else [QKeySequence(keys)]
            for sequence in sequences:
                if sequence.toString() in registered: continue
                registered.add(sequence.toString())
                shortcut = QShortcut(sequence, self)
                shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
                shortcut.activated.connect(action)
                self.shortcuts.append(shortcut)

    def set_orientation(self, orientation):
        self.current_tab().set_orientation(orientation)
        if self.compare_enabled:
            self.comparison_area.set_layout_orientation(orientation)

    def rebuild_ui(self):
        if self.about_action is not None: self.about_action.setText(self.t["about"])
        self.modified_button.setToolTip(self.t["show_modified"])
        self.modified_button.setAccessibleName(self.t["show_modified"])
        self.modified_button.refresh_icon()
        self.open_button.setToolTip(shortcut_tooltip(self.t["open"], QKeySequence.StandardKey.Open))
        self.vertical_button.setToolTip(shortcut_tooltip(self.t["vertical"], "Alt+Shift+V"))
        self.horizontal_button.setToolTip(shortcut_tooltip(self.t["horizontal"], "Alt+Shift+H"))
        self.compare_button.setToolTip(self.t["compare"])
        self.compare_button.refresh_icon()
        self.comparison_area.empty.setText(self.t["compare_empty"])
        self.language_button.set_kind(LANGUAGE_ICONS[self.language_mode], self.t[f"lang_{self.language_mode}"])
        self.language_button.setAccessibleName(self.language_button.toolTip())
        self.theme_button.set_kind(f"theme-{self.theme_mode}", self.t[f"theme_{self.theme_mode}"])
        self.tab_list_button.set_kind("tab-list", self.t["tab_list"])
        self.tab_list_button.setAccessibleName(self.t["tab_list"])
        self.apply_styles()
        for page in self.pages(): page.restyle(self.t)
        if self.compare_enabled:
            for button in self.comparison_area.header.findChildren(IconButton): button.refresh_icon()
            self.comparison_area.select_toolbar(self.image_target())
        for index in range(self.tabs.count()):
            button = self.tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
            button.setToolTip(shortcut_tooltip(self.t["close_tab"], QKeySequence.StandardKey.Close))
            button.setAccessibleName(self.t["close_tab"])
            button.update()
        for button in (self.open_button, self.vertical_button, self.horizontal_button): button.refresh_icon()
        self.update_tab_titles()
        self.refresh_system_menu()

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
        values.update(tabs=states, active_tab=active, language=self.language_mode, theme=self.theme_mode,
                      show_modified=self.show_modified, maximized_pane="")
        save_settings(values)
        for page in pages: page.shutdown()
        event.accept()

    def set_show_modified(self, show):
        self.show_modified = bool(show)
        self.settings["show_modified"] = self.show_modified
        if self.modified_button.isChecked() != self.show_modified:
            self.modified_button.setChecked(self.show_modified)
            return
        for page in self.pages(): page.thumbs.set_show_modified(self.show_modified)

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
