from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QEvent, QEventLoop, QFileSystemWatcher, QLocale, QMimeData, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDrag, QIcon, QImage, QKeySequence, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QPalette, QRegion, QShortcut, QTransform
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QMainWindow,
    QMenu, QMessageBox, QPushButton, QProgressDialog, QProxyStyle, QRubberBand, QScrollArea, QScrollBar, QSlider, QSplitter, QStackedWidget, QTabBar, QStyle, QStyleOptionSlider, QStyleOptionTab, QToolButton, QVBoxLayout, QWidget, QWidgetAction, QSizePolicy,
)

from . import __version__
from .application import PicViewApplication
from .instance import InstanceReceiver, forward_paths
from .about import AboutDialog
from .file_actions import copy_file, show_properties
from .settings import IMAGE_BACKGROUND_COLORS, load_settings, normalize_tab_state, save_settings
from . import shell_integration
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
THEME_REVISION = 0
SLIDER_WIDTH = 160
THUMBNAIL_BASE_SIZE = 140
COMPARISON_TAB_MIME = "application/x-picview-tab"
COMPARISON_IMAGE_MIME = "application/x-picview-image"
COMPARISON_REORDER_MIME = "application/x-picview-compare-reorder"
THUMBNAIL_FILES_MIME = "application/x-picview-thumbnail-files"
DROP_DECODER = ThreadPoolExecutor(max_workers=2, thread_name_prefix="picview-drop")
DROP_FRAMES = {}
LOADING_OVERLAY = None
LOADING_CHECKPOINT_ACTIVE = False


def loading_checkpoint():
    global LOADING_CHECKPOINT_ACTIVE
    if LOADING_OVERLAY is not None and not LOADING_CHECKPOINT_ACTIVE:
        LOADING_CHECKPOINT_ACTIVE = True
        try:
            LOADING_OVERLAY.advance()
            LOADING_OVERLAY.repaint()
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 2)
        finally:
            LOADING_CHECKPOINT_ACTIVE = False


class ComparisonLoadingOverlay(QWidget):
    def __init__(self, parent, text):
        super().__init__(parent)
        self.text = text
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.advance)
        self.timer.start()

    def advance(self):
        self.angle = (self.angle + 7) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(PALETTE["card"])
        color.setAlpha(195)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()), 12, 12)
        center = self.rect().center()
        painter.setPen(QPen(QColor(PALETTE["accent"]), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(center.x() - 16, center.y() - 32, 32, 32), -self.angle * 16, 260 * 16)
        painter.setPen(QColor(PALETTE["text"]))
        painter.drawText(self.rect().adjusted(8, 40, -8, 0), Qt.AlignmentFlag.AlignCenter, self.text)


def start_tab_comparison_drag(widget, page):
    drag = QDrag(widget)
    data = QMimeData()
    data.setData(COMPARISON_TAB_MIME, str(id(page)).encode("ascii"))
    drag.setMimeData(data)
    drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)


def shortcut_tooltip(text, *bindings):
    keys = []
    for binding in bindings:
        sequence = QKeySequence(binding)
        key = sequence.toString(QKeySequence.SequenceFormat.NativeText)
        if key and key not in keys:
            keys.append(key)
    return f"{text} ({' / '.join(keys)})" if keys else text


def set_widget_background(widget, color):
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


def paint_card_background(widget):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(PALETTE["card"]))
    painter.drawRoundedRect(QRectF(widget.rect()), 12, 12)
    if widget.property("inputFocused"):
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(PALETTE["accent"]), 2))
        painter.drawRoundedRect(QRectF(widget.rect()).adjusted(1, 1, -1, -1), 11, 11)
    painter.end()


class ViewportInteraction(QObject):
    """Keep drag coordinates in screen space while the scrolled label moves."""
    def __init__(self, scroll, label, zoom, interacted=lambda: None, pan=True):
        super().__init__(scroll)
        self.scroll, self.zoom, self.interacted, self.pan = scroll, zoom, interacted, pan
        self.start = None
        scroll.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for widget in (scroll.viewport(), label): widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            self.scroll.setFocus(Qt.FocusReason.MouseFocusReason)
            self.zoom(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return True
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.scroll.setFocus(Qt.FocusReason.MouseFocusReason)
            bars = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
            if self.pan and any(bar.maximum() > bar.minimum() for bar in bars):
                self.start = event.globalPosition().toPoint()
                self.values = tuple(bar.value() for bar in bars)
                watched.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return True
        if self.start is not None:
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                delta = event.globalPosition().toPoint() - self.start
                self.scroll.horizontalScrollBar().setValue(self.values[0] - delta.x())
                self.scroll.verticalScrollBar().setValue(self.values[1] - delta.y())
                return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self.start = None
                watched.unsetCursor()
                self.interacted()
                return True
        return super().eventFilter(watched, event)


def use_system_palette(app: QApplication) -> None:
    """Resolve surfaces and state colors, including the Unit-01 dark palette."""
    global THEME_REVISION
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
    THEME_REVISION += 1


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
    "compare": "Compare images", "compare_folder": "Drag a tab or thumbnail onto an image to compare", "compare_empty": "Drag a tab or thumbnail here to compare images", "image_tools": "Image tools",
    "compare_mode": "Comparison mode",
    "compare_loading": "Adding images to comparison…",
    "compare_close": "Remove from comparison", "compare_exit": "End comparison", "compare_too_small": "The image panes are too small for another comparison.",
    "file_conflict": "A file named {name} already exists in the destination folder.", "replace_file": "Replace", "keep_both": "Keep both", "skip_file": "Skip", "cancel_transfer": "Cancel",
    "sync_tools": "Apply image tools to every comparison pane",
    "drag_pane": "Drag this pane to a window edge to change the layout",
    "drag_toolbar": "Drag to move the full-screen toolbar",
    "settings": "Settings", "shell_integration": "File Explorer context menu", "finder_integration": "Finder Services menu",
    "shell_on": "On (click to turn off)", "shell_off": "Off (click to turn on)",
    "shell_open": "Open in PicView", "shell_unavailable": "Finder integration requires the packaged PicView.app",
    "shell_error": "Could not change File Explorer/Finder integration:\n{error}",
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
    "compare": "比圖", "compare_folder": "拖曳標籤或縮圖到單圖窗格進行比圖", "compare_empty": "拖曳標籤或縮圖到這裡進行比圖", "image_tools": "圖片工具",
    "compare_mode": "比圖模式",
    "compare_loading": "正在加入比圖…",
    "compare_close": "移出比圖", "compare_exit": "取消比圖", "compare_too_small": "單圖窗格太小，無法再加入比圖。",
    "file_conflict": "目標資料夾已有同名檔案：{name}", "replace_file": "取代", "keep_both": "保留兩者", "skip_file": "略過", "cancel_transfer": "取消",
    "sync_tools": "同步操作所有比圖窗格",
    "drag_pane": "拖曳窗格到視窗邊緣以調整版面",
    "drag_toolbar": "拖曳以移動全螢幕工具列",
    "settings": "設定", "shell_integration": "檔案總管右鍵選單", "finder_integration": "Finder 服務選單",
    "shell_on": "已開啟（點擊關閉）", "shell_off": "已關閉（點擊開啟）",
    "shell_open": "使用 PicView 開啟", "shell_unavailable": "Finder 整合需使用封裝版 PicView.app",
    "shell_error": "無法變更檔案總管／Finder 整合：\n{error}",
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
        self.setStyleSheet(
            f"QToolButton{{background:transparent;border:0;border-radius:8px;padding:4px;}}"
            f"QToolButton:hover,QToolButton:checked{{background:{toolbar_hover_color()};}}"
            f"QToolButton:pressed,QToolButton:checked:hover{{background:{PALETTE['pressed']};}}"
            "QToolButton::menu-indicator{image:none;width:0;height:0;}")
        # Keep a 2x raster of the 24 px source artwork. Qt reduces it to the
        # button's 20 px icon size when the icon is displayed.
        pm = QPixmap(48, 48)
        pm.fill(Qt.GlobalColor.transparent)
        icon_color = QColor(PALETTE["text"])
        if self.kind == "rotate": icon_color = QColor(PALETTE["warm"])
        if self.kind.startswith(("lang-", "theme-")) or self.kind in ("中", "A", "shell-integration"):
            icon_color = QColor(PALETTE["muted"])
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(2, 2)
        # Use a 1 px outline in the 24 px source artwork.
        stroke = 1.0
        p.setPen(QPen(icon_color, stroke))
        def line(x1, y1, x2, y2):
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        def polygon(*points):
            path = QPainterPath(QPointF(*points[0]))
            for point in points[1:]: path.lineTo(QPointF(*point))
            path.closeSubpath()
            p.drawPath(path)

        if self.kind == "folder":
            back = QPainterPath(QPointF(4, 19))
            back.lineTo(4, 6); back.quadTo(4, 5, 5, 5)
            back.lineTo(10, 5); back.lineTo(12, 8)
            back.lineTo(19, 8); back.quadTo(20, 8, 20, 9)
            back.lineTo(20, 11)
            p.drawPath(back)
            polygon((4, 19), (7, 11), (21, 11), (18, 19))
        elif self.kind.startswith("split"):
            p.drawRect(QRectF(4, 5, 16, 14))
            if self.kind == "split-v": line(12, 5.5, 12, 18.5)
            else: line(4.5, 12, 19.5, 12)
        elif self.kind == "rotate":
            p.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 285 * 16)
            line(19.5, 4, 20.5, 10); line(20.5, 10, 14.5, 7)
        elif self.kind in {"mirror-h", "mirror-v"}:
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Longer, lighter marks survive the 48 -> 20 px reduction as dashes,
            # unlike Qt's default DashLine pattern, which becomes square dots.
            p.setPen(QPen(icon_color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            if self.kind == "mirror-h":
                for start in (4, 8.5, 13, 17.5): line(12, start, 12, start + 2.5)
                p.setPen(QPen(icon_color, stroke))
                polygon((4, 19), (9, 6), (9, 19))
                polygon((20, 19), (15, 6), (15, 19))
            else:
                for start in (4, 8.5, 13, 17.5): line(start, 12, start + 2.5, 12)
                p.setPen(QPen(icon_color, stroke))
                polygon((6, 4), (19, 9), (6, 9))
                polygon((6, 20), (19, 15), (6, 15))
        elif self.kind in {"expand", "shrink"}:
            p.drawRect(QRectF(4, 4, 16, 16))
            if self.kind == "expand":
                line(10, 10, 5, 5); line(5, 5, 9, 5); line(5, 5, 5, 9)
                line(14, 14, 19, 19); line(19, 19, 15, 19); line(19, 19, 19, 15)
            else:
                line(5, 5, 10, 10); line(10, 10, 6, 10); line(10, 10, 10, 6)
                line(19, 19, 14, 14); line(14, 14, 18, 14); line(14, 14, 14, 18)
        elif self.kind == "fit":
            p.drawRect(QRectF(4, 4, 16, 16)); p.drawRect(QRectF(8, 9, 8, 6))
        elif self.kind == "background":
            p.fillRect(QRectF(4, 4, 8, 8), icon_color)
            p.fillRect(QRectF(12, 12, 8, 8), icon_color)
            p.drawRect(QRectF(4, 4, 16, 16))
        elif self.kind == "more":
            p.setBrush(icon_color)
            for x in (6, 12, 18): p.drawEllipse(QRectF(x - 1.2, 10.8, 2.4, 2.4))
        elif self.kind == "shell-integration":
            folder = QPainterPath(QPointF(4, 17))
            folder.lineTo(4, 7); folder.quadTo(4, 6, 5, 6)
            folder.lineTo(9, 6); folder.lineTo(11, 8)
            folder.lineTo(16, 8); folder.quadTo(17, 8, 17, 9)
            folder.lineTo(17, 17); folder.closeSubpath()
            p.drawPath(folder)
            menu = QPainterPath()
            menu.addRoundedRect(QRectF(10, 11, 11, 10), 1, 1)
            p.setBrush(QColor(PALETTE["card"]))
            p.drawPath(menu)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for y in (13.5, 16, 18.5):
                line(12, y, 19, y)
        elif self.kind == "sort-name":
            font = self.font(); font.setPixelSize(12); p.setFont(font)
            p.drawText(QRectF(2, 2, 9, 10), Qt.AlignmentFlag.AlignCenter, "A")
            p.drawText(QRectF(2, 12, 9, 10), Qt.AlignmentFlag.AlignCenter, "1")
            line(14, 7, 21, 7); line(14, 17, 19, 17)
        elif self.kind == "sort-date":
            p.drawEllipse(QRectF(4, 4, 16, 16))
            line(12, 7, 12, 12); line(12, 12, 17, 12)
        elif self.kind in ("sort-ascending", "sort-descending"):
            line(12, 4, 12, 20)
            end, wing = (4, 9) if self.kind == "sort-ascending" else (20, 15)
            line(7, wing, 12, end); line(12, end, 17, wing)
        elif self.kind == "modified-visible":
            p.drawRoundedRect(QRectF(4, 6, 16, 14), 2, 2)
            line(4, 11, 20, 11); line(8, 4, 8, 8); line(16, 4, 16, 8)
            line(8, 14, 11, 14); line(8, 17, 16, 17)
        elif self.kind == "tab-list":
            p.setPen(QPen(QColor(PALETTE["muted"]), stroke))
            line(8, 10, 12, 14); line(12, 14, 16, 10)
        elif self.kind == "compare":
            p.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
            line(12, 5, 12, 19)
            for x in (3, 12):
                line(x + 1.5, 16, x + 4.5, 12)
                line(x + 4.5, 12, x + 7.5, 16)
                p.drawEllipse(QRectF(x + 2.5, 8, 1.5, 1.5))
        elif self.kind == "compare-exit":
            p.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
            line(12, 5, 12, 19)
            line(7, 9, 17, 15); line(17, 9, 7, 15)
        elif self.kind == "sync":
            p.drawRoundedRect(QRectF(3, 5, 7, 14), 1, 1)
            p.drawRoundedRect(QRectF(14, 5, 7, 14), 1, 1)
            line(10, 12, 14, 12)
        elif self.kind == "fullscreen":
            for x,y,dx,dy in ((4,4,1,1),(20,4,-1,1),(4,20,1,-1),(20,20,-1,-1)):
                line(x, y, x + 6 * dx, y); line(x, y, x, y + 6 * dy)
        elif self.kind == "lang-system":
            p.drawEllipse(QRectF(4, 4, 16, 16))
            p.drawEllipse(QRectF(9, 4, 6, 16))
            line(4, 12, 20, 12)
        elif self.kind in ("中", "A"):
            font = self.font()
            font.setPixelSize(21 if self.kind == "A" else 19)
            font.setBold(False)
            p.setFont(font)
            p.drawText(QRectF(2, 2, 20, 20), Qt.AlignmentFlag.AlignCenter, self.kind)
        elif self.kind == "theme-system":
            half = QPainterPath()
            half.moveTo(12, 4)
            half.arcTo(QRectF(4, 4, 16, 16), 90, -180)
            half.closeSubpath()
            p.fillPath(half, icon_color)
            p.drawEllipse(QRectF(4, 4, 16, 16))
        elif self.kind == "theme-light":
            p.drawEllipse(QRectF(8.5, 8.5, 7, 7))
            for x1,y1,x2,y2 in ((12,3,12,6),(12,18,12,21),(3,12,6,12),(18,12,21,12),
                                (5,5,7,7),(17,17,19,19),(5,19,7,17),(17,7,19,5)):
                line(x1, y1, x2, y2)
        elif self.kind == "theme-dark":
            outer = QPainterPath(); outer.addEllipse(QRectF(4, 4, 16, 16))
            cutout = QPainterPath(); cutout.addEllipse(QRectF(9, 1, 16, 16))
            p.drawPath(outer.subtracted(cutout))
        else:
            p.drawText(QRectF(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, self.kind)
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


class FullscreenToolbarGrip(QToolButton):
    def __init__(self, toolbar):
        super().__init__(toolbar)
        self.setFixedSize(28, 34)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press = None
        self._origin = None
        self.setStyleSheet(
            f"QToolButton{{background:transparent;border:0;border-radius:6px;}}"
            f"QToolButton:hover{{background:{PALETTE['hover']};}}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self.parentWidget().pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self.parentWidget().move_within_parent(self._origin + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        self._origin = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["muted"]))
        for y in (12, 17, 22):
            for x in (9, 14):
                painter.drawEllipse(QRectF(x, y, 2, 2))


class FullscreenImageToolbar(QFrame):
    """Image-pane controls shared by single-image and comparison full screen."""

    def __init__(self, owner, pages, parent):
        super().__init__(parent)
        self.owner = owner
        self.pages = list(pages)
        self.page = self.pages[0]
        self.user_positioned = False
        self.setObjectName("fullscreenToolbar")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)
        self.drag_grip = FullscreenToolbarGrip(self)
        row.addWidget(self.drag_grip)
        self.rotate_button = IconButton("rotate", "")
        self.mirror_h_button = IconButton("mirror-h", "")
        self.mirror_v_button = IconButton("mirror-v", "")
        for button, action in ((self.rotate_button, "rotate"), (self.mirror_h_button, "mirror_h"),
                               (self.mirror_v_button, "mirror_v")):
            button.clicked.connect(lambda _checked=False, method=action: getattr(self.page.image, method)())
            row.addWidget(button)
        row.addWidget(self.separator())
        self.sync_button = IconButton("sync", "")
        self.sync_button.setCheckable(True)
        self.sync_button.clicked.connect(self.owner.set_sync)
        if len(self.pages) > 1:
            row.addWidget(self.sync_button)
        self.background_button = IconButton("background", "")
        self.background_button.clicked.connect(self.show_background_menu)
        row.addWidget(self.background_button)
        self.background_menu = QMenu(self)
        row.addWidget(self.separator())
        self.fit_button = IconButton("fit", "")
        self.fit_button.setCheckable(True)
        self.fit_button.clicked.connect(self.toggle_fit)
        row.addWidget(self.fit_button)
        self.zoom_label = ScaleValueButton(1000, 1, 4000, 1000, 10, "%", "")
        self.zoom_label.valueChosen.connect(self.set_zoom)
        row.addWidget(self.zoom_label)
        self.zoom_slider = ReferenceSlider(Qt.Orientation.Horizontal, 1000, self)
        self.zoom_slider.setRange(1, 4000)
        self.zoom_slider.setFixedSize(110, 30)
        self.zoom_slider.logicalValueChanged.connect(self.set_zoom)
        row.addWidget(self.zoom_slider)
        self.setStyleSheet(
            f"#fullscreenToolbar{{background:{PALETTE['card']};border:1px solid {PALETTE['edge']};border-radius:10px;}}"
            "QSlider{background:transparent;border:0;}"
            f"QSlider::groove:horizontal{{height:5px;background:{PALETTE['edge']};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{PALETTE['accent']};width:15px;margin:-5px 0;border-radius:7px;}}")
        for page in self.pages:
            page.image.operationApplied.connect(self.refresh)
            page.image.fit_b.toggled.connect(self.refresh)
        self.refresh()

    def move_within_parent(self, position):
        parent = self.parentWidget()
        x = min(max(8, position.x()), max(8, parent.width() - self.width() - 8))
        y = min(max(8, position.y()), max(8, parent.height() - self.height() - 8))
        self.move(x, y)
        self.user_positioned = True

    def reposition(self):
        parent = self.parentWidget()
        if self.user_positioned:
            self.move_within_parent(self.pos())
        else:
            self.move(max(8, (parent.width() - self.width()) // 2),
                      max(8, parent.height() - self.height() - 20))
        self.raise_()

    def separator(self):
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color:{PALETTE['edge']};")
        line.setFixedHeight(24)
        return line

    def toggle_fit(self, checked):
        pane = self.page.image
        pane.fullscreen_zoom = None if checked else 1.0
        pane.fit_b.setChecked(checked)
        if not checked: pane.set_zoom_percent(1000)
        pane.operationApplied.emit("fit", checked)
        self.refresh()
        self.refresh_fullscreen()

    def set_zoom(self, ticks):
        pane = self.page.image
        pane.fullscreen_zoom = ticks / 1000
        pane.set_zoom_percent(ticks)
        self.refresh()

    def show_background_menu(self):
        pane = self.page.image
        self.background_menu.clear()
        panel = QWidget(self.background_menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(4)
        for index, (mode, color) in enumerate(IMAGE_BACKGROUND_COLORS.items()):
            swatch = color or PALETTE["pane"]
            button = QPushButton(pane.labels[f"bg_{mode}"], panel) if mode == "default" else QPushButton(panel)
            button.setToolTip(pane.labels[f"bg_{mode}"])
            button.setFixedSize(172, 34) if mode == "default" else button.setFixedSize(40, 30)
            button.setStyleSheet(
                f"background:{swatch};color:{'#fff' if QColor(swatch).lightness() < 128 else '#172a31'};"
                f"border:{'2px' if mode == pane.background_mode else '1px'} solid "
                f"{PALETTE['focus'] if mode == pane.background_mode else PALETTE['edge']};border-radius:4px;")
            button.clicked.connect(lambda _checked=False, chosen=mode: self.choose_background(chosen))
            grid.addWidget(button, 0, 0, 1, 4) if mode == "default" else grid.addWidget(button, 1 + (index - 1) // 4, (index - 1) % 4)
        action = QWidgetAction(self.background_menu)
        action.setDefaultWidget(panel)
        self.background_menu.addAction(action)
        self.background_menu.popup(self.background_button.mapToGlobal(QPoint(0, -self.background_menu.sizeHint().height())))

    def choose_background(self, mode):
        self.page.image.choose_background(mode)
        self.background_menu.hide()

    def refresh_fullscreen(self):
        full = self.window()
        if isinstance(full, ComparisonFullscreen): full.update_page(self.page)
        elif isinstance(full, SingleImageFullscreen): self.page.image.update_full_image()

    def refresh(self, *_):
        pane = self.page.image
        for button, label, key in ((self.rotate_button, "rotate", "Alt+C"),
                                   (self.mirror_h_button, "mh", "Alt+H"),
                                   (self.mirror_v_button, "mv", "Alt+V")):
            button.setToolTip(shortcut_tooltip(pane.labels[label], key))
        self.background_button.setToolTip(pane.labels["background"])
        self.sync_button.blockSignals(True)
        self.sync_button.setChecked(self.owner.sync_enabled)
        self.sync_button.blockSignals(False)
        self.sync_button.setToolTip(pane.labels["sync_tools"])
        self.fit_button.blockSignals(True)
        self.fit_button.setChecked(pane.fullscreen_zoom is None)
        self.fit_button.blockSignals(False)
        self.fit_button.setToolTip(shortcut_tooltip(pane.labels["fit"], "Alt+F"))
        ticks = round((pane.fullscreen_zoom if pane.fullscreen_zoom is not None else pane.fullscreen_display_scale) * 1000)
        ticks = max(1, min(4000, ticks))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(ticks)
        self.zoom_slider.blockSignals(False)
        self.zoom_label.set_value(ticks)
        self.zoom_label.setToolTip(pane.labels["edit_zoom"])
        self.zoom_slider.setToolTip(pane.labels["zoom"])
        self.drag_grip.setToolTip(pane.labels["drag_toolbar"])
        self.adjustSize()


class ThumbnailTile(QFrame):
    """A thumbnail card with its name above and optional modified time below."""
    clicked_path = Signal(Path, object)
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
        color = QColor(PALETTE["selection"] if self.selected else PALETTE["thumbnail_card"])
        text = QColor(PALETTE["selection_text"] if self.selected else PALETTE["text"])
        for label in (self.name, self.preview, self.modified_label):
            palette = label.palette()
            palette.setColor(QPalette.ColorRole.Window, color)
            palette.setColor(QPalette.ColorRole.WindowText, text)
            label.setPalette(palette)
            label.setAutoFillBackground(True)
        self._theme_revision = THEME_REVISION
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = PALETTE["selection"] if self.selected else PALETTE["thumbnail_card"]
        if not self.selected:
            painter.setPen(QPen(QColor(PALETTE["thumbnail_edge"]), 1))
        elif QColor(PALETTE["surface"]).lightness() < 128:
            painter.setPen(QPen(QColor(PALETTE["accent"]), 1))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 9, 9)
        painter.end()
    def mousePressEvent(self, event):
        self._drag_start = None
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._drag_start).manhattanLength() >= QApplication.startDragDistance():
                self._drag_start = None
                if self.path.is_file():
                    pane = self.parentWidget()
                    while pane is not None and not isinstance(pane, ThumbnailPane):
                        pane = pane.parentWidget()
                    paths = pane.drag_paths_for(self.path) if pane is not None else [self.path]
                    # Keep the drag source alive if a folder update rebuilds the tiles.
                    drag = QDrag(self.window())
                    data = QMimeData()
                    data.setUrls([QUrl.fromLocalFile(str(path.resolve())) for path in paths])
                    page = self.parentWidget()
                    while page is not None and not isinstance(page, FolderTab):
                        page = page.parentWidget()
                    if page is not None:
                        data.setData(COMPARISON_TAB_MIME, str(id(page)).encode("ascii"))
                        data.setData(COMPARISON_IMAGE_MIME, str(self.path.resolve()).encode("utf-8"))
                        data.setData(THUMBNAIL_FILES_MIME, json.dumps([str(path) for path in paths], ensure_ascii=False).encode("utf-8"))
                    drag.setMimeData(data)
                    pixmap = self.preview.pixmap()
                    if pixmap is not None and not pixmap.isNull():
                        pixmap = pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        drag.setPixmap(pixmap)
                        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
                    drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.IgnoreAction)
            event.accept()
            return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        if self._drag_start is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked_path.emit(self.path, event.modifiers())
        self._drag_start = None
        super().mouseReleaseEvent(event)


PANE_DOCK_MIME = "application/x-picview-pane-dock"


class PaneDragHandle(QToolButton):
    def __init__(self, kind, tip, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.page = None
        self._drag_start = None
        self.setFixedSize(22, 34)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.refresh_style()

    def refresh_style(self):
        self.setStyleSheet(f"QToolButton{{background:transparent;border:0;border-radius:6px;}}"
                           f"QToolButton:hover{{background:{PALETTE['hover']};}}"
                           f"QToolButton:pressed{{background:{PALETTE['pressed']};}}")
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._drag_start).manhattanLength() >= QApplication.startDragDistance():
                self._drag_start = None
                if self.page is not None:
                    window = self.window()
                    if self.kind == "image" and getattr(window, "compare_enabled", False):
                        self.page = window.current_tab()
                    drag = QDrag(self)
                    mime = QMimeData()
                    mime.setData(PANE_DOCK_MIME, self.kind.encode("ascii"))
                    drag.setMimeData(mime)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    drag.exec(Qt.DropAction.MoveAction)
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                    self.page.hide_dock_preview()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["muted"]))
        for y in (12, 17, 22):
            for x in (8, 13):
                painter.drawEllipse(QRectF(x, y, 2, 2))
        painter.end()


class ThumbnailPane(QFrame):
    selected = Signal(Path)
    rowRequested = Signal(int)
    def __init__(self, labels: dict[str, str], parent=None):
        self.columns = 1
        super().__init__(parent); self.labels=labels; self.files=[]; self.selected_path=None; self.selected_paths=set(); self.selection_anchor=None; self.size=THUMBNAIL_BASE_SIZE; self.buttons={}; self.failed_paths=set()
        self.sort_mode = "natural"
        self.sort_descending = False
        self.show_modified = True
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,4,10,8); layout.setSpacing(4)
        header=QHBoxLayout(); header.setSpacing(4); self.drag_handle=PaneDragHandle("thumb", labels["drag_pane"]); header.addWidget(self.drag_handle); header.addStretch(); self.size_label=ScaleValueButton(self.size,72,260,THUMBNAIL_BASE_SIZE,1,"px",labels["edit_thumb"]); header.addWidget(self.size_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,THUMBNAIL_BASE_SIZE); self.slider.setRange(72,260); self.slider.setValue(self.size); self.slider.setFixedSize(SLIDER_WIDTH,30); self.slider.logicalValueChanged.connect(self._resize); self.size_label.valueChosen.connect(self.slider.setValue); header.addWidget(self.slider); layout.addLayout(header)
        self.tab_slot = QWidget()
        self.tab_slot.setObjectName("thumbnailTabSlot")
        self.tab_slot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.tab_slot.setFixedHeight(34)
        self.tab_slot.setMaximumWidth(0)
        tab_layout = QHBoxLayout(self.tab_slot)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        header.insertWidget(1, self.tab_slot, 1)
        header.takeAt(2)  # The tab slot supplies the flexible space.
        self.context_menu = QMenu(self)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); set_widget_background(self.scroll.viewport(), PALETTE["pane"]); self.grid_host=QWidget(); self.grid_host.setObjectName("thumbnailGrid"); set_widget_background(self.grid_host, PALETTE["pane"]); self.grid=QGridLayout(self.grid_host); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft); self.scroll.setWidget(self.grid_host); layout.addWidget(self.scroll)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumSize(54, 50)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.selection_band = QRubberBand(QRubberBand.Shape.Rectangle, self.grid_host)
        self._selection_start = None
        self._selection_base = set()
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
        self.scroll.verticalScrollBar().valueChanged.connect(self.refresh_visible_tile_styles)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.refresh_visible_tile_styles)
        self.toolbar_overflow = ToolbarOverflow(self, header, [self.slider, self.size_label, self.drag_handle],
            lambda: self.labels["more_tools"], {self.slider: self.size_label},
            self.toolbar_width, flex_widgets=(self.tab_slot,))
        for widget in (self.scroll, self.scroll.viewport(), self.grid_host,
                       self.scroll.verticalScrollBar(), self.scroll.horizontalScrollBar()):
            widget.installEventFilter(self)
        self.scroll.viewport().setAcceptDrops(True)
        self.grid_host.setAcceptDrops(True)
        self.viewport_interaction = ViewportInteraction(self.scroll, self.grid_host,
            lambda direction: self.slider.setValue(self.slider.value() + direction * 10), pan=False)

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_card_background(self)

    def set_show_modified(self, show):
        self.show_modified = bool(show)
        self.build()

    def show_file_menu(self, path, position):
        if path not in self.selected_paths: self.select_clicked(path)
        menu = self.context_menu
        menu.clear()
        copy = menu.addAction(shortcut_tooltip(self.labels["copy"], QKeySequence.StandardKey.Copy))
        copy.triggered.connect(lambda checked=False: copy_file([item for item in self.files if item in self.selected_paths]))
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
        if watched in (self.scroll.viewport(), self.grid_host) and event.type() in (
                QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            if event.mimeData().hasFormat(THUMBNAIL_FILES_MIME):
                window = self.window()
                page = getattr(self, "owner_page", None)
                if page is not None and hasattr(window, "transfer_thumbnails_to_tab"):
                    copy_modifier = Qt.KeyboardModifier.AltModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
                    action = Qt.DropAction.CopyAction if event.modifiers() & copy_modifier else Qt.DropAction.MoveAction
                    if event.type() != QEvent.Type.Drop or window.transfer_thumbnails_to_tab(event.mimeData(), page, action):
                        event.setDropAction(action)
                        event.accept()
                        return True
        if watched is self.grid_host:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.scroll.setFocus(Qt.FocusReason.MouseFocusReason)
                self._selection_start = event.position().toPoint()
                modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
                self._selection_base = set(self.selected_paths) if event.modifiers() & modifier else set()
                self.selected_paths = self._selection_base.copy()
                self.selection_anchor = None
                self.refresh_selection_styles()
                return True
            if event.type() == QEvent.Type.MouseMove and self._selection_start is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    rect = QRect(self._selection_start, event.position().toPoint()).normalized()
                    self.selection_band.setGeometry(rect)
                    self.selection_band.show()
                    self.selected_paths = self._selection_base | {
                        path for path, tile in self.buttons.items() if rect.intersects(tile.geometry())
                    }
                    self.refresh_selection_styles()
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._selection_start is not None:
                self._selection_start = None
                self.selection_band.hide()
                if self.selected_paths:
                    path = next(path for path in self.files if path in self.selected_paths)
                    self.selection_anchor = path
                    if path != self.selected_path:
                        self.selected_path = path
                        self.selected.emit(path)
                return True
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            selection_modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
            if event.key() == Qt.Key.Key_A and event.modifiers() == selection_modifier:
                if event.type() == QEvent.Type.KeyPress: self.select_all()
                event.accept()
                return True
            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier and event.key() in (
                    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.selected_path in self.files:
                if event.type() == QEvent.Type.KeyPress:
                    offset = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1,
                              Qt.Key.Key_Up: -self.columns, Qt.Key.Key_Down: self.columns}[event.key()]
                    target = self.files[max(0, min(len(self.files) - 1, self.files.index(self.selected_path) + offset))]
                    self.select_clicked(target, Qt.KeyboardModifier.ShiftModifier)
                event.accept()
                return True
            if event.modifiers() == Qt.KeyboardModifier.NoModifier and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                if event.type() == QEvent.Type.KeyPress:
                    self.rowRequested.emit(-1 if event.key() == Qt.Key.Key_Up else 1)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def select_clicked(self, path, modifiers=Qt.KeyboardModifier.NoModifier):
        self.scroll.setFocus(Qt.FocusReason.MouseFocusReason)
        if path not in self.files: return
        selection_modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
        if modifiers & Qt.KeyboardModifier.ShiftModifier and self.selection_anchor in self.files:
            start, end = sorted((self.files.index(self.selection_anchor), self.files.index(path)))
            selection = set(self.files[start:end + 1])
            self.selected_paths = self.selected_paths | selection if modifiers & selection_modifier else selection
        elif modifiers & selection_modifier:
            if path in self.selected_paths: self.selected_paths.remove(path)
            else: self.selected_paths.add(path)
            self.selection_anchor = path
        else:
            self.selected_paths = {path}
            self.selection_anchor = path
        if path in self.selected_paths:
            self.selected_path = path
            self.selected.emit(path)
        elif self.selected_path == path:
            self.selected_path = next((item for item in self.files if item in self.selected_paths), path)
            self.selected.emit(self.selected_path)
        self.refresh_selection_styles()

    def select_all(self):
        self.selected_paths = set(self.files)
        self.selection_anchor = self.selected_path
        self.refresh_selection_styles()

    def drag_paths_for(self, path):
        if path not in self.selected_paths:
            self.selected_paths = {path}
            self.selection_anchor = path
            self.refresh_selection_styles()
        return [item for item in self.files if item in self.selected_paths and item.is_file()]

    def refresh_selection_styles(self):
        for path, tile in self.buttons.items():
            selected = path in self.selected_paths
            if tile.selected != selected:
                tile.selected = selected
                tile.apply_style()

    def set_files(self, files, selected=None, *, emit_selection=True):
        previous = self.selected_path
        self.files=files; self.selected_path=selected if selected in files else (files[0] if files else None)
        self.selected_paths.intersection_update(files)
        if self.selected_path != previous or not self.selected_paths:
            self.selected_paths = {self.selected_path} if self.selected_path else set()
        if self.selection_anchor not in files: self.selection_anchor = self.selected_path
        self.build()
        if emit_selection and self.selected_path: self.selected.emit(self.selected_path)
    def _resize(self,v): self.size=v; self.size_label.set_value(v); self.build()
    def build(self):
        if self._stopped or getattr(self, "defer_build", False): return
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
            if index % 32 == 0: loading_checkpoint()
            tile = self.buttons.get(path)
            new = tile is None
            if new:
                tile = ThumbnailTile(path, None, self.size, path in self.selected_paths, self.show_modified)
                tile.clicked_path.connect(self.select_clicked)
                tile.contextRequested.connect(self.show_file_menu)
                self.buttons[path] = tile
            selected = path in self.selected_paths
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
        self.refresh_visible_tile_styles()

    def refresh_visible_tile_styles(self, *_):
        if not self.isVisible() or not self.files: return
        viewport = self.scroll.viewport()
        row_height = max(1, self.tile_height() + max(0, self.grid.verticalSpacing()))
        first_row = max(0, self.scroll.verticalScrollBar().value() // row_height - 1)
        last_row = (self.scroll.verticalScrollBar().value() + viewport.height()) // row_height + 2
        for path in self.files[first_row * self.columns:last_row * self.columns]:
            tile = self.buttons.get(path)
            if tile is not None and getattr(tile, "_theme_revision", -1) != THEME_REVISION:
                tile.apply_style()

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
        self.selected_paths = {path}
        self.selection_anchor = path
        self.refresh_selection_styles()
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
    layout.addWidget(ToolbarSeparator())


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
        visible = {widget for widget in self.widgets if not isinstance(widget, ToolbarSeparator)
                   and widget.property("toolbar_available") is not False}
        hidden = []
        if self.required_width(visible, False) > width:
            for widget in self.hide_order:
                if widget not in visible: continue
                visible.discard(widget)
                hidden.append(widget)
                if self.required_width(visible, True) <= width: break
            if self.required_width(visible, True) > width:
                visible = {widget for widget in visible if widget.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Ignored}
        if width < 120:
            visible = {widget for widget in visible if widget in self.flex_widgets or
                       (widget.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Ignored
                        and not isinstance(widget, PaneDragHandle))}
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
            if isinstance(widget, PaneDragHandle): continue
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
    operationApplied = Signal(str, object)
    comparisonCloseRequested = Signal()

    def __init__(self, labels, parent=None):
        super().__init__(parent); self.labels=labels; self.path=None; self.frames=[]; self.index=0; self.rotation=0; self.fh=False; self.fv=False; self.zoom=1.0; self.fit_to_pane=False; self.auto_scale=False; self._applying_auto_scale=False; self.display_scale=1.0; self.fullscreen_zoom=None; self.fullscreen_display_scale=1.0; self.full_window=None; self.timer=QTimer(self); self.timer.timeout.connect(self.next_frame)
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,4,10,8); layout.setSpacing(4)
        self.comparison_title = None
        self.comparison_selected = False
        self._comparison_reorder_start = None
        self._comparison_reorder_dragging = False
        self._comparison_reorder_target = None
        self._drag_ghost = None
        self._drag_placeholder = None
        self.resize_refresh_timer = QTimer(self)
        self.resize_refresh_timer.setSingleShot(True)
        self.resize_refresh_timer.timeout.connect(self.refresh_after_resize)
        self.background_mode = "default"
        bar=QHBoxLayout(); self.drag_handle=PaneDragHandle("image", labels["drag_pane"]); bar.addWidget(self.drag_handle); self.rotate_b=IconButton("rotate",labels["rotate"]); self.mh=IconButton("mirror-h",labels["mh"]); self.mv=IconButton("mirror-v",labels["mv"]); self.fit_b=IconButton("fit",labels["fit"]); self.fit_b.setCheckable(True); self.fit_b.toggled.connect(self.set_fit); self.full=IconButton("fullscreen",labels["full"])
        self.fit_b.clicked.connect(lambda checked: self.operationApplied.emit("fit", self.fit_to_pane))
        for b,fn in ((self.rotate_b,self.rotate),(self.mh,self.mirror_h),(self.mv,self.mirror_v)): b.clicked.connect(fn); bar.addWidget(b)
        bar.setSpacing(4)
        separate_tools(bar)
        self.full.clicked.connect(self.open_full)
        self.background_button = IconButton("background", labels["background"])
        self.background_button.clicked.connect(self.show_background_menu)
        bar.addWidget(self.background_button)
        self.sync_button = IconButton("sync", labels["sync_tools"])
        self.sync_button.setCheckable(True)
        self.sync_button.setEnabled(False)
        bar.addWidget(self.sync_button)
        self.end_compare_button = IconButton("compare-exit", labels["compare_exit"])
        self.end_compare_button.clicked.connect(lambda: self.window().set_compare(False))
        self.end_compare_button.setProperty("toolbar_available", False)
        self.end_compare_button.hide()
        bar.addWidget(self.end_compare_button)
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
        for button in (self.fit_b,self.full): bar.addWidget(button)
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
            [self.slider, self.zoom_label, self.end_compare_button, self.sync_button, self.background_button, self.full, self.mv, self.mh, self.rotate_b, self.fit_b, self.filename_label, self.drag_handle],
            lambda: self.labels["more_tools"], {self.slider: self.zoom_label})
        layout.addWidget(self.toolbar_widget)
        self.comparison_header = QWidget(self)
        comparison_row = QHBoxLayout(self.comparison_header)
        comparison_row.setContentsMargins(4, 0, 4, 0)
        comparison_row.setSpacing(4)
        self.comparison_label = QLabel(self.comparison_header)
        self.comparison_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        comparison_row.addWidget(self.comparison_label, 1)
        self.comparison_close = TabCloseButton(self.comparison_header)
        self.comparison_close.setToolTip(labels["compare_close"])
        self.comparison_close.clicked.connect(self.comparisonCloseRequested.emit)
        comparison_row.addWidget(self.comparison_close)
        self.comparison_header.setFixedHeight(24)
        self.comparison_header.hide()
        layout.addWidget(self.comparison_header)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(False); self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.label=QLabel(labels["empty"]); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.label.setStyleSheet(f"color:{PALETTE['muted']};background:transparent;"); self.scroll.setWidget(self.label); layout.addWidget(self.scroll)
        for target in (self, self.comparison_header, self.scroll, self.scroll.viewport(), self.label):
            target.setAcceptDrops(True)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.toolbar = bar
        self.update_shortcut_tooltips()
        self.apply_background()
        for widget in self.findChildren(QWidget): widget.installEventFilter(self)
        self.viewport_interaction = ViewportInteraction(self.scroll, self.label,
            lambda direction: self.adjust_zoom(direction * 10), self.interacted.emit)

    def update_shortcut_tooltips(self):
        for button, label, keys in ((self.fit_b, "fit", "Alt+F"), (self.rotate_b, "rotate", "Alt+C"),
                                    (self.mv, "mv", "Alt+V"), (self.mh, "mh", "Alt+H")):
            button.setToolTip(shortcut_tooltip(self.labels[label], keys))
        self.full.setToolTip(shortcut_tooltip(self.labels["full"], "F11"))
        self.zoom_label.setToolTip(shortcut_tooltip(self.labels["edit_zoom"], "+", "-", "0"))
        self.slider.setToolTip(shortcut_tooltip(self.labels["zoom"], "+", "-", "0"))
        self.zoom_label.reset_button.setToolTip(shortcut_tooltip("100%", "0"))
        self.sync_button.setToolTip(self.labels["sync_tools"])
        self.comparison_close.setToolTip(self.labels["compare_close"])
        self.end_compare_button.setToolTip(self.labels["compare_exit"])

    def background_color(self):
        return IMAGE_BACKGROUND_COLORS[self.background_mode] or PALETTE["pane"]

    def apply_background(self):
        color = self.background_color()
        self.scroll.viewport().setStyleSheet(f"background:{color};")
        if self.full_window is not None:
            self.full_window.set_background(color)
        self.update_comparison_fullscreen()
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
        self.operationApplied.emit("background", mode)

    def show_background_menu(self):
        self.apply_background()
        anchor = self.background_button if self.background_button.isVisible() else self.toolbar_overflow.more_button
        QTimer.singleShot(0, self, lambda: self.background_menu.popup(anchor.mapToGlobal(QPoint(0, anchor.height()))))

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_card_background(self)
        if self.comparison_selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(PALETTE["accent"]), 2))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 10, 10)
            painter.end()

    def eventFilter(self, watched, event):
        if watched in (self.comparison_header, self.comparison_label, self.scroll.viewport(), self.label):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._comparison_reorder_start = event.globalPosition().toPoint() if self.comparison_title else None
                self._comparison_reorder_dragging = False
                self._comparison_reorder_target = None
                if self._comparison_reorder_start is not None:
                    # QLabel normally ignores presses and lets the scroll area
                    # take them. Own the press so Qt keeps the pointer grab on
                    # this image throughout a cross-pane drag.
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease and self._comparison_reorder_start is not None:
                if self._comparison_reorder_dragging:
                    self.finish_comparison_reorder(event.globalPosition().toPoint())
                    self.end_drag_visual()
                    self._comparison_reorder_start = None
                    self._comparison_reorder_dragging = False
                    self.interacted.emit()
                    return True
                self._comparison_reorder_start = None
                self.interacted.emit()
            elif (event.type() == QEvent.Type.MouseMove and self._comparison_reorder_start is not None
                  and event.buttons() & Qt.MouseButton.LeftButton):
                if not self._comparison_reorder_dragging and (
                        event.globalPosition().toPoint() - self._comparison_reorder_start).manhattanLength() >= QApplication.startDragDistance():
                    self._comparison_reorder_dragging = True
                    self.begin_drag_visual()
                if self._comparison_reorder_dragging:
                    self.preview_comparison_reorder_at(event.globalPosition().toPoint())
                    self.move_drag_visual(event.globalPosition().toPoint())
                    return True
        if event.type() == QEvent.Type.DragLeave and getattr(self.window(), "compare_enabled", False):
            self.window().restore_comparison_order()
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            if self.handle_comparison_drag(event, watched): return True
        if event.type() == QEvent.Type.Wheel or (
                event.type() == QEvent.Type.MouseButtonPress
                and not (self.comparison_title and self._comparison_reorder_start is not None)):
            self.interacted.emit()
        return super().eventFilter(watched, event)

    def begin_drag_visual(self):
        snapshot = self.grab().scaled(240, 180, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        self._drag_ghost = QLabel(self.window().centralWidget())
        self._drag_ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drag_ghost.setPixmap(snapshot)
        self._drag_ghost.setFixedSize(snapshot.size() + QSize(8, 8))
        self._drag_ghost.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drag_ghost.setStyleSheet(f"background:{PALETTE['card']};border:2px solid {PALETTE['accent']};border-radius:8px;")
        self._drag_placeholder = QFrame(self)
        self._drag_placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drag_placeholder.setStyleSheet(f"background:{PALETTE['pane']};border:3px dashed {PALETTE['accent']};border-radius:10px;")
        self._drag_placeholder.setGeometry(self.rect().adjusted(2, 2, -2, -2))
        self._drag_placeholder.show()
        self._drag_placeholder.raise_()

    def move_drag_visual(self, position):
        ghost = self._drag_ghost
        if ghost is None: return
        point = ghost.parentWidget().mapFromGlobal(position) + QPoint(18, 18)
        ghost.move(min(max(0, point.x()), max(0, ghost.parentWidget().width() - ghost.width())),
                   min(max(0, point.y()), max(0, ghost.parentWidget().height() - ghost.height())))
        ghost.show()
        ghost.raise_()
        self._drag_placeholder.setGeometry(self.rect().adjusted(2, 2, -2, -2))
        self._drag_placeholder.raise_()

    def end_drag_visual(self):
        for widget in (self._drag_ghost, self._drag_placeholder):
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._drag_ghost = self._drag_placeholder = None

    def comparison_reorder_target(self, global_position):
        window = self.window()
        if not getattr(window, "compare_enabled", False) or self.owner_page not in window.comparison_order:
            return None
        horizontal = window.comparison_area.split.orientation() == Qt.Orientation.Horizontal
        for page in window.comparison_order:
            target = page.image
            point = target.mapFromGlobal(global_position)
            if target.rect().contains(point):
                after = point.x() >= target.width() / 2 if horizontal else point.y() >= target.height() / 2
                return page, after
        return None

    def preview_comparison_reorder_at(self, global_position):
        target = self.comparison_reorder_target(global_position)
        if target is None:
            self._comparison_reorder_target = None
            self.window().restore_comparison_order()
        elif target[0] is not self.owner_page:
            self._comparison_reorder_target = target
            self.window().preview_comparison_reorder(self.owner_page, *target)

    def finish_comparison_reorder(self, global_position):
        target = self.comparison_reorder_target(global_position)
        if target is not None and target[0] is self.owner_page:
            target = self._comparison_reorder_target
        self._comparison_reorder_target = None
        if target is None or not self.window().reorder_comparison_page(self.owner_page, *target):
            self.window().restore_comparison_order()

    def handle_comparison_drag(self, event, watched=None):
        window = self.window()
        if event.mimeData().hasFormat(COMPARISON_REORDER_MIME) and getattr(window, "compare_enabled", False):
            try: identifier = int(bytes(event.mimeData().data(COMPARISON_REORDER_MIME)).decode("ascii"))
            except (ValueError, UnicodeDecodeError): return False
            source = next((page for page in window.comparison_order if id(page) == identifier), None)
            if source is None or self.owner_page not in window.comparison_order: return False
            position = self.mapFrom(watched, event.position().toPoint()) if watched is not None else event.position().toPoint()
            horizontal = window.comparison_area.split.orientation() == Qt.Orientation.Horizontal
            after = (position.x() >= self.width() / 2) if horizontal else (position.y() >= self.height() / 2)
            if event.type() == QEvent.Type.DragMove:
                window.preview_comparison_reorder(source, self.owner_page, after)
            elif event.type() == QEvent.Type.Drop:
                window.reorder_comparison_page(source, self.owner_page, after)
            event.acceptProposedAction()
            return True
        if not hasattr(window, "comparison_drag_source") or window.comparison_drag_source(event.mimeData()) is None:
            return False
        if event.type() == QEvent.Type.Drop:
            # Finish the native drag loop before opening images or building panes.
            payload = QMimeData()
            for name in event.mimeData().formats(): payload.setData(name, event.mimeData().data(name))
            window.queue_comparison_drop(self, payload)
        event.acceptProposedAction()
        return True

    def dragEnterEvent(self, event):
        if not self.handle_comparison_drag(event): super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if not self.handle_comparison_drag(event): super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not self.handle_comparison_drag(event): super().dropEvent(event)

    def dragLeaveEvent(self, event):
        if getattr(self.window(), "compare_enabled", False): self.window().restore_comparison_order()
        super().dragLeaveEvent(event)

    def update_filename(self):
        name = self.path.name if self.path else ""
        self.filename_label.setText(self.labels["compare_mode"] if self.comparison_title else name)
        self.filename_label.setStyleSheet("font-weight:600;" if self.comparison_title else "")
        self.comparison_label.setText(f"{self.comparison_title} / {name}" if self.comparison_title else "")
        self.update_comparison_fullscreen()

    def update_comparison_fullscreen(self):
        full = getattr(self.window(), "compare_full_window", None)
        if full is not None and self.owner_page in full.labels:
            full.update_page(self.owner_page)

    def set_comparison_mode(self, title=None):
        self.comparison_title = title
        comparing = title is not None
        self.toolbar_widget.setVisible(not comparing)
        self.end_compare_button.setProperty("toolbar_available", comparing)
        self.end_compare_button.setVisible(comparing)
        self.toolbar_overflow.update()
        self.comparison_header.setVisible(comparing)
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
        if path in DROP_FRAMES: return DROP_FRAMES[path]
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
        self.auto_scale=False; self.path=path; self.rotation=0; self.fh=self.fv=False; self.zoom=1.0; self.fullscreen_zoom=None; self.frames=[]; self.timer.stop(); self.fit_b.setChecked(False)
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
        self.update_comparison_fullscreen()
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
        self.update_comparison_fullscreen()
    def resizeEvent(self,e):
        super().resizeEvent(e)
        if hasattr(self, "resize_refresh_timer"): self.resize_refresh_timer.start(0)
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
    def rotate(self):
        self.rotation=(self.rotation+90)%360; self.render()
        self.operationApplied.emit("rotate", None)
    def mirror_h(self):
        self.fh=not self.fh; self.render()
        self.operationApplied.emit("mirror_h", None)
    def mirror_v(self):
        self.fv=not self.fv; self.render()
        self.operationApplied.emit("mirror_v", None)
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
        self.operationApplied.emit("zoom", ticks)
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
        self.operationApplied.emit("zoom", 1000)
    def open_full(self):
        window = self.window()
        if getattr(window, "compare_enabled", False) and self.owner_page in window.checked_pages:
            window.open_comparison_fullscreen()
            return
        if self.full_window is not None:
            self.full_window.close()
            self.full_window = None
            return
        if not self.frames: return
        w = SingleImageFullscreen(self)
        w.destroyed.connect(lambda: setattr(self, "full_window", None) if self.full_window is w else None)
        self.full_window=w
        self.apply_background()
        w.showFullScreen()
        QTimer.singleShot(0, self, self.update_full_image)

    def update_full_image(self):
        if self.full_window is None or not self.frames: return
        full = self.full_window
        label = full.image_label
        available = full.image_scroll.viewport().size()
        pixmap = self.fullscreen_pixmap(available, label.devicePixelRatioF())
        label.setPixmap(pixmap)
        label.resize(pixmap.deviceIndependentSize().toSize())
        full.image_toolbar.refresh()

    def fullscreen_pixmap(self, available: QSize, dpr: float) -> QPixmap:
        if not self.frames: return QPixmap()
        original = QSize(*self.image_size())
        size = (original.scaled(available, Qt.AspectRatioMode.KeepAspectRatio).boundedTo(original)
                if self.fullscreen_zoom is None else original * self.fullscreen_zoom)
        self.fullscreen_display_scale = size.width() / max(1, original.width())
        pixels = (max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)))
        if isinstance(self.frames[self.index][0], SvgDocument):
            pixmap = QPixmap.fromImage(self.svg_image(pixels))
        else:
            image = self.image()
            if image.size != pixels: image = image.resize(pixels, Image.Resampling.LANCZOS)
            pixmap = QPixmap.fromImage(qimage(image))
        pixmap.setDevicePixelRatio(dpr)
        return pixmap


class SingleImageFullscreen(QMainWindow):
    def __init__(self, pane):
        super().__init__(pane)
        self.pane = pane
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        self.image_scroll = QScrollArea(root)
        self.image_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(0, 0)
        self.image_scroll.setWidget(self.image_label)
        layout.addWidget(self.image_scroll)
        self.setCentralWidget(root)
        self.image_toolbar = FullscreenImageToolbar(pane.window(), [pane.owner_page], root)
        self.viewport_interaction = ViewportInteraction(self.image_scroll, self.image_label,
            lambda direction: self.image_toolbar.set_zoom(self.image_toolbar.zoom_slider.value() + direction * 100))
        for bar in (self.image_scroll.horizontalScrollBar(), self.image_scroll.verticalScrollBar()):
            bar.setStyleSheet(pane.window().scrollbar_style)
        self.set_background(pane.background_color())

    def set_background(self, color):
        self.centralWidget().setStyleSheet(f"background:{color};")
        self.image_scroll.viewport().setStyleSheet(f"background:{color};")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_toolbar()
        self.pane.update_full_image()
        QTimer.singleShot(0, self.pane, self.pane.update_full_image)

    def position_toolbar(self):
        self.image_toolbar.reposition()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.pane.fullscreen_zoom = None
        super().closeEvent(event)


class FolderTab(QWidget):
    notification = Signal(str)
    attentionChanged = Signal()
    layoutChanged = Signal(object)
    sortChanged = Signal()

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.t = labels
        self.folder = None
        self.files = []
        self.active = False
        self.comparison_visible = False
        self.pending_notification = ""
        self._pending_restyle = None
        self.image_dirty = False
        self._selection_pending = None
        self._restore_selected = None
        self._initial_view = None
        self._pending_scroll = None
        self._scroll_restore_attempts = 0
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
        self.thumbs.drag_handle.page = self
        self.image.drag_handle.page = self
        self.drop_preview = QFrame(self)
        self.drop_preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.drop_preview.hide()
        QApplication.instance().installEventFilter(self)
        self.thumbs.selected.connect(self.select_image)
        self.thumbs.rowRequested.connect(self.navigate_row)
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
        source = state.get("_source_page") if state else None
        self._shared_folder_source = source
        self.thumbs.defer_build = bool(state and state.get("_defer_thumbnails"))
        self.files = source.files.copy() if source is not None else self.ordered_files(image_files(self.folder))
        self._layout_pending = True
        if state:
            self.image.set_background(state.get("image_background", "default"))
            self.thumbs.slider.setValue(state["thumbnail_size"])
            orientation = Qt.Orientation.Horizontal if state["orientation"] == "horizontal" else Qt.Orientation.Vertical
            self.split.setOrientation(orientation)
            self.split.insertWidget(0, self.thumbs if state.get("thumbnail_first", True) else self.image_slot)
            self._sash_fraction = state["sash_fraction"]
        self.thumbs.set_files(self.files, selected)
        self._pending_image_versions = self.pending_image_versions()
        self._pending_image_retries = dict.fromkeys(self.thumbs.failed_paths, 8)
        self._image_versions = source._image_versions.copy() if source is not None else self.image_versions(self.files)
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
        self.sortChanged.emit()
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
        if getattr(self.thumbs, "defer_build", False):
            self.thumbs.defer_build = False
            self.thumbs.build()
        if self._pending_restyle is not None:
            self.restyle(self.t, palette_changed=self._pending_restyle)
        self.folder_refresh_timer.start(0)
        self.activate_image()
        self.thumbs.refresh_visible_tile_styles()
        if self._layout_pending: QTimer.singleShot(0, self, self.apply_layout)
        if self._pending_scroll is not None: self.scroll_restore_timer.start()

    def set_comparison_visible(self, visible):
        self.comparison_visible = visible
        if self._closing: return
        if visible:
            self.folder_refresh_timer.start(0)
            self.activate_image()
        elif not self.active:
            self.image.timer.stop()

    def cancel_scroll_restore(self):
        self._pending_scroll = None
        self.scroll_restore_timer.stop()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.DragLeave and self.drop_preview.isVisible():
            self.hide_dock_preview()
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            source = event.source()
            if (isinstance(source, PaneDragHandle) and source.page is self
                    and event.mimeData().hasFormat(PANE_DOCK_MIME) and isinstance(watched, QWidget)):
                position = self.mapFromGlobal(watched.mapToGlobal(event.position().toPoint()))
                edge = self.dock_edge(position)
                if event.type() == QEvent.Type.Drop:
                    self.hide_dock_preview()
                    if edge is not None: self.dock_pane(source.kind, edge)
                    event.acceptProposedAction()
                else:
                    self.show_dock_preview(edge)
                    event.acceptProposedAction()
                return True
        if event.type() in (QEvent.Type.Wheel, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress):
            self.cancel_scroll_restore()
        return super().eventFilter(watched, event)

    def dock_edge(self, position):
        window = self.window()
        if not window.rect().contains(self.mapTo(window, position)): return None
        position = QPoint(min(max(position.x(), 0), self.width() - 1),
                          min(max(position.y(), 0), self.height() - 1))
        limit = min(100, max(40, min(self.width(), self.height()) // 5))
        distances = {"left": position.x(), "right": self.width() - 1 - position.x(),
                     "top": position.y(), "bottom": self.height() - 1 - position.y()}
        edge = min(distances, key=distances.get)
        return edge if distances[edge] <= limit else None

    def show_dock_preview(self, edge):
        if edge is None:
            self.hide_dock_preview()
            return
        width, height = self.width(), self.height()
        regions = {"left": QRect(0, 0, width // 2, height),
                   "right": QRect(width // 2, 0, width - width // 2, height),
                   "top": QRect(0, 0, width, height // 2),
                   "bottom": QRect(0, height // 2, width, height - height // 2)}
        color = QColor(PALETTE["focus"])
        color.setAlpha(55)
        self.drop_preview.setStyleSheet(
            f"background:{color.name(QColor.NameFormat.HexArgb)};border:2px solid {PALETTE['focus']};border-radius:8px;")
        self.drop_preview.setGeometry(regions[edge].adjusted(4, 4, -4, -4))
        self.drop_preview.raise_()
        self.drop_preview.show()

    def hide_dock_preview(self):
        self.drop_preview.hide()

    def layout_spec(self):
        sizes = self.split.sizes()
        fraction = sizes[0] / sum(sizes) if sum(sizes) and not self._layout_pending else self._sash_fraction
        return (self.split.orientation(), self.split.widget(0) is self.thumbs, fraction)

    def apply_layout_spec(self, spec):
        orientation, thumbnail_first, fraction = spec
        self.split.setUpdatesEnabled(False)
        try:
            self.split.setOrientation(orientation)
            self.split.insertWidget(0, self.thumbs if thumbnail_first else self.image_slot)
            self._sash_fraction = fraction
            self._layout_pending = True
        finally:
            self.split.setUpdatesEnabled(True)
        if self.active: QTimer.singleShot(0, self, self.apply_layout)

    def dock_pane(self, kind, edge):
        if kind not in ("thumb", "image") or edge not in ("top", "bottom", "left", "right"):
            return
        orientation = (Qt.Orientation.Vertical if edge in ("top", "bottom") else Qt.Orientation.Horizontal)
        leading = self.thumbs if kind == "thumb" else self.image_slot
        if edge in ("bottom", "right"):
            leading = self.image_slot if kind == "thumb" else self.thumbs
        self.split.setUpdatesEnabled(False)
        try:
            self.split.setOrientation(orientation)
            self.split.insertWidget(0, leading)
            length = self.split.height() if orientation == Qt.Orientation.Vertical else self.split.width()
            self.split.setSizes([length // 2, length - length // 2])
            self._sash_fraction = .5
            self._layout_pending = False
        finally:
            self.split.setUpdatesEnabled(True)
            self.split.update()
        self.layoutChanged.emit(orientation)

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
        sizes = self.split.sizes()
        fraction = sizes[0] / sum(sizes) if sum(sizes) and not self._layout_pending else self._sash_fraction
        state = {"folder": str(self.folder) if self.folder else "", "selected_file": str(self.thumbs.selected_path or self._restore_selected or ""),
                 "orientation": "horizontal" if self.split.orientation() == Qt.Orientation.Horizontal else "vertical",
                 "thumbnail_first": self.split.widget(0) is self.thumbs,
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
        return state

    def restyle(self, labels, *, palette_changed=True):
        self._pending_restyle = None
        self.t = labels
        self.thumbs.labels = labels
        self.image.labels = labels
        for pane in (self.thumbs, self.image):
            pane.drag_handle.setToolTip(labels["drag_pane"])
            if palette_changed: pane.drag_handle.refresh_style()
        if palette_changed:
            set_widget_background(self.thumbs.scroll.viewport(), PALETTE["pane"])
        self.image.apply_background()
        if palette_changed:
            set_widget_background(self.thumbs.grid_host, PALETTE["pane"])
            self.thumbs.refresh_visible_tile_styles()
        for button, key in ((self.image.rotate_b, "rotate"), (self.image.mh, "mh"), (self.image.mv, "mv"), (self.image.fit_b, "fit"), (self.image.full, "full")):
            button.setToolTip(labels[key])
        self.thumbs.size_label.setToolTip(labels["edit_thumb"])
        self.image.zoom_label.setToolTip(labels["edit_zoom"])
        self.image.update_shortcut_tooltips()
        if palette_changed:
            self.thumbs.size_label.apply_style()
            self.image.zoom_label.apply_style()
            self.image.label.setStyleSheet(f"color:{PALETTE['muted']};background:transparent;")
            for button in self.findChildren(IconButton) + self.image.findChildren(IconButton): button.refresh_icon()
        if self.comparison_visible: self.image.set_comparison_mode(self.folder.name or str(self.folder))
        self.update_empty_message()

    def shutdown(self):
        self._closing = True
        QApplication.instance().removeEventFilter(self)
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
        if getattr(self, "_shared_folder_source", None) is not None: return
        watched = set(self.folder_watcher.files())
        wanted = {str(path) for path in files}
        removed = watched - wanted
        if removed: self.folder_watcher.removePaths(list(removed))
        added = wanted - watched
        if added: self.folder_watcher.addPaths(list(added))

    @staticmethod
    def image_versions(files):
        versions = {}
        for index, path in enumerate(files):
            if index % 32 == 0: loading_checkpoint()
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
        self.layoutChanged.emit(o)

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

    def navigate_row(self, direction):
        window = self.window()
        target = window.navigation_page() if hasattr(window, "navigation_page") else self
        if target is not None: target.select_row(direction)

    def select_boundary(self, last):
        if self.files: self.thumbs.select(self.files[-1 if last else 0])

    def copy_selected_file(self):
        paths = [path for path in self.files if path in self.thumbs.selected_paths]
        if paths: copy_file(paths)



class TabFolderControl(QCheckBox):
    """Paint at native widget resolution, including on high-DPI displays."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.comparing = False
        self.page = None
        self._drag_start = None
        self.setFixedSize(28, 20)

    def hitButton(self, pos):
        return self.comparing and self.rect().contains(pos)

    def mousePressEvent(self, event):
        if not self.comparing:
            if event.button() == Qt.MouseButton.LeftButton and self.page is not None:
                self._drag_start = event.position().toPoint()
                event.accept()
            else: event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._drag_start).manhattanLength() >= QApplication.startDragDistance():
                self._drag_start = None
                start_tab_comparison_drag(self, self.page)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_start is not None and self.page is not None:
            bar = self.parentWidget()
            index = next((index for index in range(bar.count()) if bar.tabData(index) is self.page), -1)
            if index >= 0: bar.setCurrentIndex(index)
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(PALETTE["text"]), 1))
        painter.save()
        painter.translate(8, 0)
        if self.comparing:
            if self.isChecked():
                painter.setBrush(QColor(PALETTE["focus"]))
                painter.setPen(QPen(QColor(PALETTE["focus"]), 1))
            painter.drawRoundedRect(QRectF(3.5, 3.5, 13, 13), 2, 2)
            if self.isChecked():
                painter.setPen(QPen(QColor(PALETTE["active_text"]), 1))
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
        self.toolbar_image = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        self.header = QFrame()
        self.header.setObjectName("comparisonToolbar")
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
        base, accent = QColor(PALETTE["card"]), QColor(PALETTE["accent"])
        tint = QColor(*(round(a * .86 + b * .14) for a, b in zip(
            (base.red(), base.green(), base.blue()), (accent.red(), accent.green(), accent.blue()))))
        self.header.setStyleSheet(f"#comparisonToolbar{{background:{tint.name()};border-radius:9px;}}")
        self.update()
        if self.toolbar_image is not image:
            self.release_toolbar()
            self.toolbar_image = image
            if image is not None: self.header_layout.addWidget(image.toolbar_widget)
        self.header.setVisible(image is not None)
        if image is not None: image.toolbar_widget.show()
        for page in self.pages:
            page.image.comparison_selected = page.image is image
            page.image.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(PALETTE["card"]))
        painter.setPen(QPen(QColor(PALETTE["accent"]), 1.5))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.75, .75, -.75, -.75), 12, 12)

    def set_layout_orientation(self, orientation):
        target = Qt.Orientation.Horizontal if orientation == Qt.Orientation.Vertical else Qt.Orientation.Vertical
        if self.split.orientation() != target:
            self.split.setOrientation(target)
            self.equalize()

    def equalize(self):
        self.split.setSizes([1000] * len(self.pages))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.equalize()

class ComparisonFullscreen(QMainWindow):
    def __init__(self, owner, pages):
        super().__init__(owner)
        self.owner = owner
        self.pages = list(pages)
        self.frames = {}
        self.labels = {}
        self.scrollers = {}
        self.titles = {}
        self._page_for_widget = {}
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        self.split = QSplitter(root)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(12)
        root_layout.addWidget(self.split)
        self.setCentralWidget(root)
        self.setStyleSheet(f"background:{PALETTE['surface']};color:{PALETTE['text']};")
        for page in self.pages:
            frame = QFrame(self.split)
            frame.setObjectName("comparisonFullscreenPane")
            content = QVBoxLayout(frame)
            content.setContentsMargins(6, 6, 6, 6)
            content.setSpacing(4)
            title = QLabel(frame)
            title.setFixedHeight(24)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll = QScrollArea(frame)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image = QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setMinimumSize(0, 0)
            scroll.setWidget(image)
            content.addWidget(title)
            content.addWidget(scroll, 1)
            self.split.addWidget(frame)
            self.frames[page] = frame
            self.labels[page] = image
            self.scrollers[page] = scroll
            self.titles[page] = title
            for widget in (frame, title, scroll, scroll.viewport(), image,
                           scroll.horizontalScrollBar(), scroll.verticalScrollBar()):
                self._page_for_widget[widget] = page
                widget.installEventFilter(self)
        for index in range(1, self.split.count()): self.split.handle(index).setEnabled(False)
        self.image_toolbar = FullscreenImageToolbar(owner, self.pages, root)
        self.viewport_interactions = []
        for page in self.pages:
            scroll = self.scrollers[page]
            self.viewport_interactions.append(ViewportInteraction(scroll, self.labels[page],
                lambda direction, page=page: (self.set_active_page(page), self.image_toolbar.set_zoom(
                    self.image_toolbar.zoom_slider.value() + direction * 100)),
                lambda page=page: self.set_active_page(page)))
            for bar in (scroll.horizontalScrollBar(), scroll.verticalScrollBar()):
                bar.setStyleSheet(owner.scrollbar_style)
        self.set_active_page(owner.focused_compare_page if owner.focused_compare_page in self.pages else self.pages[0])

    def cycle_page(self, offset):
        current = self.image_toolbar.page
        index = self.pages.index(current) if current in self.pages else 0
        self.set_active_page(self.pages[(index + offset) % len(self.pages)])

    def focusNextPrevChild(self, next):
        self.cycle_page(1 if next else -1)
        return True

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            page = self._page_for_widget.get(watched)
            if page is not None: self.set_active_page(page)
        return super().eventFilter(watched, event)

    def set_active_page(self, page):
        if page not in self.frames: return
        self.owner.focused_compare_page = page
        self.image_toolbar.page = page
        for tab, frame in self.frames.items():
            active = tab is page
            frame.setStyleSheet(
                f"QFrame#comparisonFullscreenPane{{border:2px solid "
                f"{PALETTE['accent'] if active else 'transparent'};border-radius:8px;}}")
            self.titles[tab].setStyleSheet(
                f"color:{PALETTE['accent'] if active else PALETTE['text']};"
                f"font-weight:{'600' if active else '400'};")
        self.image_toolbar.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        orientation = Qt.Orientation.Horizontal if self.width() >= self.height() else Qt.Orientation.Vertical
        if self.split.orientation() != orientation:
            self.split.setOrientation(orientation)
        self.split.setSizes([1000] * len(self.pages))
        self.image_toolbar.reposition()
        self.refresh_all()
        QTimer.singleShot(0, self, self.refresh_all)

    def refresh_all(self):
        for page in self.pages: self.update_page(page)

    def update_page(self, page):
        if page not in self.labels: return
        label = self.labels[page]
        pane = page.image
        name = pane.path.name if pane.path else ""
        self.titles[page].setText(f"{page.folder.name if page.folder else ''} / {name}")
        scroll = self.scrollers[page]
        scroll.viewport().setStyleSheet(f"background:{pane.background_color()};")
        pixmap = pane.fullscreen_pixmap(scroll.viewport().size(), label.devicePixelRatioF())
        if pixmap.isNull(): label.clear()
        else:
            label.setPixmap(pixmap)
            label.resize(pixmap.deviceIndependentSize().toSize())
        if self.image_toolbar.page is page: self.image_toolbar.refresh()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11): self.close()
        else: super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.owner.compare_full_window is self: self.owner.compare_full_window = None
        for shortcut in self.owner.compare_tab_shortcuts:
            shortcut.setEnabled(self.owner.compare_enabled)
        for page in self.pages: page.image.fullscreen_zoom = None
        super().closeEvent(event)


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


class FolderTabStyle(QProxyStyle):
    """Keep Qt's scrolling behavior with navigation at opposite ends."""
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_TabBarScrollButtonWidth:
            return 16
        return super().pixelMetric(metric, option, widget)

    def subElementRect(self, element, option, widget=None):
        if element in (QStyle.SubElement.SE_TabBarTearIndicatorLeft,
                       QStyle.SubElement.SE_TabBarTearIndicatorRight):
            return QRect()
        if element in (QStyle.SubElement.SE_TabBarScrollLeftButton,
                       QStyle.SubElement.SE_TabBarScrollRightButton):
            width = self.pixelMetric(QStyle.PixelMetric.PM_TabBarScrollButtonWidth, option, widget)
            x = option.rect.left() if element == QStyle.SubElement.SE_TabBarScrollLeftButton else option.rect.right() - width + 1
            return QRect(x, option.rect.top(), width, option.rect.height())
        return super().subElementRect(element, option, widget)

    def drawComplexControl(self, control, option, painter, widget=None):
        if (control == QStyle.ComplexControl.CC_ToolButton
                and isinstance(widget, QToolButton) and widget.objectName().startswith("Scroll")):
            painter.fillRect(option.rect, QColor(PALETTE["hover"] if option.state & QStyle.StateFlag.State_MouseOver else PALETTE["surface"]))
            element = (QStyle.PrimitiveElement.PE_IndicatorArrowLeft
                       if widget.objectName() == "ScrollLeftButton"
                       else QStyle.PrimitiveElement.PE_IndicatorArrowRight)
            self.drawPrimitive(element, option, painter, widget)
            return
        super().drawComplexControl(control, option, painter, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if (isinstance(widget, QToolButton) and widget.objectName().startswith("Scroll")
                and element in (QStyle.PrimitiveElement.PE_IndicatorArrowLeft,
                                QStyle.PrimitiveElement.PE_IndicatorArrowRight)):
            color = QColor(PALETTE["muted"])
            if not option.state & QStyle.StateFlag.State_Enabled:
                color.setAlpha(80)
            direction = -1 if element == QStyle.PrimitiveElement.PE_IndicatorArrowLeft else 1
            center = option.rect.center()
            path = QPainterPath()
            path.moveTo(center.x() - direction * 2, center.y() - 4)
            path.lineTo(center.x() + direction * 2, center.y())
            path.lineTo(center.x() - direction * 2, center.y() + 4)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)


class FolderTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._comparison_drag_start = None
        self._comparison_drag_page = None
        self._comparison_drag_target = None
        self._comparison_dragged = False
        self._external_drag_finished = False
        self.display_current_index = None
        self._hover_page = None
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(350)
        self.hover_timer.timeout.connect(self.activate_hovered_tab)
        self._scroll_button = None
        self.drag_scroll_timer = QTimer(self)
        self.drag_scroll_timer.setInterval(160)
        self.drag_scroll_timer.timeout.connect(self.scroll_drag_tabs)
        self.navigation_style = FolderTabStyle()
        self.navigation_style.setParent(self)
        self.setStyle(self.navigation_style)
        self.setAcceptDrops(True)

    def thumbnail_drop_target(self, event):
        if not event.mimeData().hasFormat(COMPARISON_IMAGE_MIME): return None
        index = self.tabAt(event.position().toPoint())
        page = self.tabData(index) if index >= 0 else None
        return page if page is not None and page.folder is not None else None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for button in self.findChildren(QToolButton):
            if button.objectName().startswith("Scroll"):
                button.setAcceptDrops(True)
                button.installEventFilter(self)

    def scroll_drag_tabs(self):
        button = self._scroll_button
        if button is not None and button.isVisible() and button.isEnabled(): button.click()

    def eventFilter(self, watched, event):
        if isinstance(watched, QToolButton) and watched.objectName().startswith("Scroll"):
            if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasFormat(THUMBNAIL_FILES_MIME):
                    self.hover_timer.stop()
                    self._hover_page = None
                    self._scroll_button = watched
                    if not self.drag_scroll_timer.isActive():
                        self.scroll_drag_tabs()
                        self.drag_scroll_timer.start()
                    event.acceptProposedAction()
                    return True
            elif event.type() in (QEvent.Type.DragLeave, QEvent.Type.Drop):
                self.drag_scroll_timer.stop()
                self._scroll_button = None
                if event.type() == QEvent.Type.Drop:
                    event.ignore()
                    return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(THUMBNAIL_FILES_MIME):
            event.setDropAction(event.proposedAction())
            event.accept()
        else: super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        page = self.thumbnail_drop_target(event)
        if page is not None:
            if page is not self._hover_page:
                self._hover_page = page
                self.hover_timer.start()
            event.setDropAction(event.proposedAction())
            event.accept()
        else: super().dragMoveEvent(event)

    def activate_hovered_tab(self):
        window = self.window()
        if self._hover_page is not None and hasattr(window, "tabs"):
            window.tabs.setCurrentWidget(self._hover_page)

    def dragLeaveEvent(self, event):
        self.hover_timer.stop()
        self._hover_page = None
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.hover_timer.stop()
        self._hover_page = None
        page = self.thumbnail_drop_target(event)
        window = self.window()
        if page is not None and hasattr(window, "transfer_thumbnails_to_tab") and window.transfer_thumbnails_to_tab(event.mimeData(), page, event.proposedAction()):
            event.setDropAction(event.proposedAction())
            event.accept()
        else: super().dropEvent(event)

    def mousePressEvent(self, event):
        self._external_drag_finished = False
        self._comparison_drag_target = self.tabData(self.currentIndex()) if self.currentIndex() >= 0 else None
        self._comparison_drag_start = event.position().toPoint() if event.button() == Qt.MouseButton.LeftButton else None
        index = self.tabAt(self._comparison_drag_start) if self._comparison_drag_start is not None else -1
        self._comparison_drag_page = self.tabData(index) if index >= 0 else None
        self._comparison_dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        start = self._comparison_drag_start
        if (start is not None and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - start).manhattanLength() >= QApplication.startDragDistance()):
            self._comparison_dragged = True
        if (start is not None and self._comparison_drag_page is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and not self.rect().contains(event.position().toPoint())
                and (event.position().toPoint() - start).manhattanLength() >= QApplication.startDragDistance()):
            page = self._comparison_drag_page
            target = self._comparison_drag_target
            # Qt's built-in movable-tab drag may already have drawn a floating
            # copy of the tab. End it before QDrag takes over the mouse release.
            release = QMouseEvent(QEvent.Type.MouseButtonRelease, event.position(),
                                  event.globalPosition(), Qt.MouseButton.LeftButton,
                                  Qt.MouseButton.NoButton, event.modifiers())
            blocked = self.blockSignals(True)
            try:
                super().mouseReleaseEvent(release)
                if target is not None:
                    index = next((index for index in range(self.count()) if self.tabData(index) is target), -1)
                    if index >= 0: self.setCurrentIndex(index)
            finally:
                self.blockSignals(blocked)
            self._comparison_drag_start = None
            self._comparison_drag_page = None
            self._comparison_drag_target = None
            self._comparison_dragged = False
            self._external_drag_finished = True
            start_tab_comparison_drag(self, page)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._external_drag_finished:
            self._external_drag_finished = False
            event.accept()
            return
        source = self._comparison_drag_page
        target = self._comparison_drag_target
        dragged = self._comparison_dragged
        blocked = self.blockSignals(True)
        try:
            super().mouseReleaseEvent(event)
            if target is not None:
                index = next((index for index in range(self.count()) if self.tabData(index) is target), -1)
                if index >= 0: self.setCurrentIndex(index)
        finally:
            self.blockSignals(blocked)
        self._comparison_drag_start = None
        self._comparison_drag_page = None
        self._comparison_drag_target = None
        self._comparison_dragged = False
        if source is not None and not dragged and event.button() == Qt.MouseButton.LeftButton:
            index = next((index for index in range(self.count()) if self.tabData(index) is source), -1)
            if index >= 0: self.setCurrentIndex(index)

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
        display_index = self.display_current_index if self.display_current_index is not None else self.currentIndex()
        order = [index for index in range(self.count()) if self.isTabVisible(index) and index != display_index]
        if display_index >= 0 and self.isTabVisible(display_index): order.append(display_index)
        for index in order:
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            selected = index == display_index
            if selected:
                painter.fillRect(option.rect, QColor(PALETTE["card"]))
                painter.fillRect(option.rect.left(), option.rect.bottom() - 1, option.rect.width(), 2, QColor(PALETTE["accent"]))
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
        self.bar.tabMoved.connect(lambda *_: self.stack.setCurrentWidget(
            self.bar._comparison_drag_target or self.currentWidget()))

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
        if self.bar._comparison_drag_page is not None or self.bar._comparison_dragged:
            target = self.bar._comparison_drag_target
            if target is not None:
                target_index = self.indexOf(target)
                if target_index >= 0 and index != target_index:
                    blocked = self.bar.blockSignals(True)
                    self.bar.setCurrentIndex(target_index)
                    self.bar.blockSignals(blocked)
                    return
        page = self.widget(index)
        if page is not None: self.stack.setCurrentWidget(page)
        self.currentChanged.emit(index)

    def removeTab(self, index):
        page = self.widget(index)
        previous = self.currentWidget()
        self.bar.blockSignals(True)
        self.bar.removeTab(index)
        self.bar.blockSignals(False)
        if page is not None: self.stack.removeWidget(page)
        if self.currentWidget() is not previous:
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
        self.comparison_order = []
        self.focused_compare_page = None
        self._compare_layout = None
        self._compare_original_layouts = {}
        self.compare_full_window = None
        self._pane_layout = None
        self._restoring_layout = True
        self.sync_enabled = False
        self._syncing_tools = False
        app = QApplication.instance()
        self.input_pane = "image"
        app.focusChanged.connect(self.track_input_focus)
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

    def refresh_shell_integration_button(self):
        button = self.integration_button
        active = shell_integration.enabled()
        available = shell_integration.available()
        button.blockSignals(True)
        button.setChecked(active)
        button.blockSignals(False)
        button.setEnabled(available)
        label = self.t["finder_integration" if sys.platform == "darwin" else "shell_integration"]
        tip = f"{label}：{self.t['shell_on' if active else 'shell_off']}" if available else self.t["shell_unavailable"]
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.refresh_icon()

    def set_shell_integration(self, enabled):
        try:
            shell_integration.set_enabled(bool(enabled), self.t["shell_open"])
        except OSError as error:
            QMessageBox.warning(self, self.t["settings"], self.t["shell_error"].format(error=error))
        self.refresh_shell_integration_button()

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
        self.sort_button = IconButton("sort-name", self.t["sort_method"])
        self.sort_button.setCheckable(True)
        self.sort_button.clicked.connect(self.toggle_sort_mode)
        self.direction_button = IconButton("sort-ascending", self.t["sort_direction"])
        self.direction_button.setCheckable(True)
        self.direction_button.clicked.connect(self.toggle_sort_direction)
        self.language_button = IconButton(LANGUAGE_ICONS[self.language_mode], self.t[f"lang_{self.language_mode}"])
        self.modified_button = IconButton("modified-visible", self.t["show_modified"])
        self.modified_button.setCheckable(True)
        self.modified_button.setChecked(self.show_modified)
        self.modified_button.toggled.connect(self.set_show_modified)
        self.theme_button = IconButton(f"theme-{self.theme_mode}", self.t[f"theme_{self.theme_mode}"])
        self.integration_button = IconButton("shell-integration", "")
        self.integration_button.setCheckable(True)
        self.integration_button.clicked.connect(self.set_shell_integration)
        self.refresh_shell_integration_button()
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
        self.open_button.clicked.connect(self.choose)
        layout.addWidget(self.open_button)
        separate_tools(layout)
        layout.addWidget(self.sort_button)
        layout.addWidget(self.direction_button)
        layout.addStretch(1)
        separate_tools(layout)
        layout.addWidget(self.modified_button)
        for button, action in ((self.language_button, self.toggle_lang), (self.theme_button, self.toggle_theme)):
            button.clicked.connect(action)
        for button in (self.integration_button, self.language_button, self.theme_button):
            button.setParent(tool)
            button.hide()
        self.settings_menu = QMenu(self)
        self.settings_menu.aboutToShow.connect(self.populate_settings_menu)
        self.settings_button = IconButton("more", self.t["more_tools"])
        self.settings_button.setMenu(self.settings_menu)
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(self.settings_button)
        self.toolbar_overflow = ToolbarOverflow(tool, layout,
            [self.settings_button, self.modified_button,
             self.direction_button, self.sort_button, self.open_button],
            lambda: self.t["more_tools"])
        outer.addWidget(self.tabs, 1)
        self.apply_styles()

    def populate_settings_menu(self):
        self.settings_menu.clear()
        for button in (self.integration_button, self.language_button, self.theme_button):
            action = self.settings_menu.addAction(button.icon(), button.toolTip())
            action.setEnabled(button.isEnabled())
            action.setCheckable(button.isCheckable())
            action.setChecked(button.isChecked())
            action.triggered.connect(lambda checked=False, button=button: button.click())

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
        set_widget_background(self.centralWidget(), PALETTE["surface"])
        self.main_toolbar.setStyleSheet("#toolbar{background:transparent;border:0;}")
        for card in self.findChildren(QFrame, "card"):
            if isinstance(card, (ThumbnailPane, ImagePane)):
                card.update()
            else:
                card.setStyleSheet(f"#card{{background:{PALETTE['card']};border:0;border-radius:12px;}}")
        self.notification_bar.setStyleSheet(
            f"color:{PALETTE['warm']};background:{PALETTE['card']};")
        self.slider_style = (
            f"QSlider::groove:horizontal{{height:5px;background:{PALETTE['edge']};border-radius:2px;}}"
            f"QSlider::handle:horizontal{{background:{PALETTE['accent']};width:15px;margin:-5px 0;border-radius:7px;}}")
        self.scrollbar_style = (
            f"QScrollBar{{background:{PALETTE['surface']};border:0;margin:0;}}"
            "QScrollBar:vertical{width:12px;}QScrollBar:horizontal{height:12px;}"
            f"QScrollBar::handle{{background:{PALETTE['edge']};border-radius:6px;}}"
            "QScrollBar::handle:vertical{min-height:25px;}"
            "QScrollBar::handle:horizontal{min-width:25px;}"
            f"QScrollBar::add-page,QScrollBar::sub-page{{background:{PALETTE['surface']};}}"
            "QScrollBar::add-line,QScrollBar::sub-line{width:0;height:0;border:0;background:none;}")
        for page in self.pages(): self.style_pane_controls(page)
        self.tabs.strip.setStyleSheet(f"#tabStrip{{background:{strip};border:0;}}")
        self.tabs.tabBar().setStyleSheet(f"""
            QTabBar{{background:transparent;}}
            QTabBar::tab{{background:transparent;color:{PALETTE['muted']};border:0;padding:0 12px;margin:0;}}
            QTabBar::tab:selected{{background:{PALETTE['card']};color:{PALETTE['text']};}}
            QTabBar::tab:!selected:hover{{background:{hover};}}
            QTabBar QToolButton{{background:{strip};color:{PALETTE['text']};border:0;border-radius:4px;}}
            QTabBar QToolButton:hover{{background:{hover};}}
            #tabCloseButton:hover{{background:{hover};}}
            #tabCloseButton{{background:transparent;border:0;border-radius:4px;}}
        """)

    def style_pane_controls(self, page):
        for slider in page.findChildren(QSlider): slider.setStyleSheet(self.slider_style)
        for bar in page.findChildren(QScrollBar): bar.setStyleSheet(self.scrollbar_style)

    def add_page(self, layout_spec=None):
        page = FolderTab(self.t)
        if layout_spec is not None: page.apply_layout_spec(layout_spec)
        page.image.owner_page = page
        page.thumbs.owner_page = page
        page.thumbs.show_modified = self.show_modified
        page.notification.connect(lambda message, tab=page: self.show_notification(tab, message))
        page.attentionChanged.connect(self.update_tab_titles)
        self.tabs.addTab(page, self.t["empty_tab"])
        control = TabFolderControl(self.tabs.tabBar())
        control.page = page
        control.toggled.connect(lambda checked, tab=page: self.check_compare_page(tab, checked))
        self.tabs.tabBar().setTabButton(self.tabs.indexOf(page), QTabBar.ButtonPosition.LeftSide, control)
        page.image.interacted.connect(lambda tab=page: self.focus_compare_page(tab))
        page.image.comparisonCloseRequested.connect(lambda tab=page: self.remove_comparison_page(tab))
        page.image.operationApplied.connect(lambda action, value, tab=page: self.apply_comparison_tool(tab, action, value))
        for action, bar in (("scroll_x", page.image.scroll.horizontalScrollBar()),
                            ("scroll_y", page.image.scroll.verticalScrollBar())):
            bar.valueChanged.connect(lambda value, tab=page, operation=action:
                                     self.apply_comparison_tool(tab, operation, value))
        page.image.sync_button.clicked.connect(self.set_sync)
        page.sortChanged.connect(lambda tab=page: self.refresh_sort_buttons() if tab is self.current_tab() else None)
        page.layoutChanged.connect(lambda orientation, tab=page: self.comparison_layout_changed(tab))
        page.split.splitterMoved.connect(lambda _position, _index, tab=page: self.comparison_layout_changed(tab))
        button = self.tabs.tabBar().tabButton(self.tabs.indexOf(page), QTabBar.ButtonPosition.RightSide)
        button.setToolTip(shortcut_tooltip(self.t["close_tab"], QKeySequence.StandardKey.Close))
        button.setAccessibleName(self.t["close_tab"])
        self.style_pane_controls(page)
        return page

    def open_folder(self, folder, selected=None, *, state=None, restoring=False):
        folder = Path(folder).resolve()
        if not restoring and not folder.is_dir():
            self.notification_bar.showMessage(self.t["folder_missing"] + ": " + str(folder), 8000)
            return None
        page = next((tab for tab in self.pages() if tab.folder is None), None)
        if page is None:
            current = self.current_tab()
            layout_spec = (self._compare_layout if self.compare_enabled else current.layout_spec() if current is not None else None)
            if not self.compare_enabled and layout_spec is not None and not self._restoring_layout:
                self._pane_layout = layout_spec
            page = self.add_page(layout_spec if state is None else None)
        page.open_folder(folder, selected, state)
        if not restoring: self.tabs.setCurrentWidget(page)
        if page is self.current_tab(): page.set_active(True)
        self.refresh_sort_buttons()
        self.update_tab_titles()
        self.update_title()
        if self.compare_enabled and not getattr(self, "_batch_comparison_drop", False): self.sync_comparison()
        return page

    def choose(self):
        current = self.folder
        initial = current.parent if current and current.parent != current and current.parent.is_dir() else current
        folder = QFileDialog.getExistingDirectory(self, self.t["open"], str(initial) if initial else "")
        if folder: self.open_folder(Path(folder))

    def resolve_transfer_conflict(self, destination):
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(self.t["file_conflict"].format(name=destination.name))
        dialog.setText(self.t["file_conflict"].format(name=destination.name))
        buttons = {choice: dialog.addButton(self.t[label], QMessageBox.ButtonRole.ActionRole)
                   for choice, label in (("replace", "replace_file"), ("keep_both", "keep_both"),
                                         ("skip", "skip_file"), ("cancel", "cancel_transfer"))}
        dialog.exec()
        return next((choice for choice, button in buttons.items() if dialog.clickedButton() is button), "cancel")

    def transfer_thumbnails_to_tab(self, mime, target, action):
        source = self.comparison_drag_source(mime)
        if source is None or source[1] is None or target not in self.pages() or target.folder is None:
            return False
        source_page, focused = source
        paths = [focused]
        if mime.hasFormat(THUMBNAIL_FILES_MIME):
            try:
                requested = json.loads(bytes(mime.data(THUMBNAIL_FILES_MIME)).decode("utf-8"))
                if isinstance(requested, list):
                    paths = [path for path in source_page.files if str(path) in requested]
            except (UnicodeDecodeError, ValueError): return False
        if not paths: return False
        move = action == Qt.DropAction.MoveAction
        last_destination = None
        for image in paths:
            if image.parent == target.folder:
                last_destination = image
                continue
            destination = target.folder / image.name
            suffix = 2
            choice = None
            if destination.exists():
                choice = self.resolve_transfer_conflict(destination)
                if choice == "cancel": break
                if choice == "skip": continue
                if choice == "keep_both":
                    while destination.exists():
                        destination = target.folder / f"{image.stem} ({suffix}){image.suffix}"
                        suffix += 1
            try:
                if choice == "replace":
                    with tempfile.NamedTemporaryFile(dir=target.folder, delete=False) as temporary:
                        staged = Path(temporary.name)
                    try:
                        shutil.copy2(image, staged)
                        staged.replace(destination)
                    finally:
                        staged.unlink(missing_ok=True)
                    if move: image.unlink()
                elif move:
                    shutil.move(image, destination)
                else:
                    shutil.copy2(image, destination)
            except OSError as error:
                self.notification_bar.showMessage(str(error), 8000)
                continue
            last_destination = destination
        if move: source_page.refresh_folder()
        if last_destination is not None:
            target.refresh_folder()
            self.tabs.setCurrentWidget(target)
            target.thumbs.select(last_destination)
        return True

    def populate_tab_list(self):
        self.tab_list_menu.clear()
        current = self.current_tab()
        for index, page in enumerate(self.pages()):
            if not self.tabs.bar.isTabVisible(index): continue
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

    def duplicate_page(self, source, *, activate=True, add_to_compare=True, selected=None):
        if source not in self.pages() or source.folder is None: return None
        state = source.snapshot()
        state["_source_page"] = source
        state["_defer_thumbnails"] = not activate and not add_to_compare
        if selected is None: selected = Path(state["selected_file"]) if state["selected_file"] else None
        self._batch_comparison_drop = True
        try:
            page = self.open_folder(source.folder, selected, state=state, restoring=True)
        finally:
            self._batch_comparison_drop = False
        self.tabs.tabBar().moveTab(self.tabs.indexOf(page), self.tabs.indexOf(source) + 1)
        if add_to_compare and self.compare_enabled and source in self.checked_pages:
            self.checked_pages.add(page)
            self.comparison_order.append(page)
            if activate: self.focused_compare_page = page
            self.sync_comparison()
        if activate: self.tabs.setCurrentWidget(page)
        self.update_tab_titles()
        return page

    def tab_changed(self, index):
        page = self.tabs.widget(index) if index >= 0 else None
        self.tabs.bar.display_current_index = (
            self.tabs.indexOf(page.comparison_source_page)
            if page is not None and hasattr(page, "comparison_source_page") else None)
        self.tabs.bar.update()
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
        self.refresh_sort_buttons()
        self.update_tab_titles()
        self.update_title()
        if self.compare_enabled:
            if page in self.checked_pages: self.focused_compare_page = page
            self.sync_comparison()
        elif page is not None and not self._restoring_layout:
            if self._pane_layout is None:
                self._pane_layout = page.layout_spec()
            elif page.layout_spec() != self._pane_layout:
                self.tabs.setUpdatesEnabled(False)
                page.apply_layout_spec(self._pane_layout)
                page.apply_layout()
                QTimer.singleShot(0, self.tabs, lambda: self.tabs.setUpdatesEnabled(True))

    def close_tab(self, index=None):
        if index is None: index = self.tabs.currentIndex()
        if index < 0 or index >= self.tabs.count(): return
        page = self.tabs.widget(index)
        if page.folder is not None and not hasattr(page, "comparison_source_page"):
            self.closed_tabs.append((index, page.snapshot()))
            self.closed_tabs = self.closed_tabs[-20:]
        self.checked_pages.discard(page)
        self._compare_original_layouts.pop(page, None)
        if page in self.comparison_order: self.comparison_order.remove(page)
        if self.compare_enabled:
            if len(self.comparison_order) < 2: self.set_compare(False)
            else: self.sync_comparison()
        if self.comparison_area.parentWidget() is page.image_slot:
            self.comparison_area.setParent(self.centralWidget())
            self.comparison_area.hide()
        page.shutdown()
        self.tabs.removeTab(index)
        page.deleteLater()
        if not self.tabs.count(): self.add_page()
        self.update_tab_titles()

    def switch_tab(self, offset):
        indices = [index for index in range(self.tabs.count()) if self.tabs.bar.isTabVisible(index)]
        if not indices: return
        current = self.tabs.currentIndex()
        position = indices.index(current) if current in indices else 0
        self.tabs.setCurrentIndex(indices[(position + offset) % len(indices)])

    def cycle_comparison_page(self, offset):
        if not self.compare_enabled: return
        pages = [page for page in self.comparison_order if page in self.checked_pages and page in self.pages()]
        if not pages: return
        current = self.focused_compare_page if self.focused_compare_page in pages else pages[0]
        self.focus_compare_page(pages[(pages.index(current) + offset) % len(pages)])

    def select_tab_number(self, number):
        indices = [index for index in range(self.tabs.count()) if self.tabs.bar.isTabVisible(index)]
        position = len(indices) - 1 if number == 9 else number - 1
        if 0 <= position < len(indices): self.tabs.setCurrentIndex(indices[position])

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
        visible_pages = [page for index, page in enumerate(pages) if self.tabs.bar.isTabVisible(index)]
        names = [(page.folder.name or str(page.folder)) if page.folder else self.t["empty_tab"] for page in visible_pages]
        for index, page in enumerate(pages):
            name = (page.folder.name or str(page.folder)) if page.folder else self.t["empty_tab"]
            if page.folder and len({item.folder for item, title in zip(visible_pages, names) if title.casefold() == name.casefold()}) > 1:
                name += " — " + str(page.folder.parent)
            if page.folder and sum(item.folder == page.folder for item in visible_pages) > 1:
                name += f" ({sum(item.folder == page.folder for item in pages[:index + 1] if item in visible_pages)})"
            if page.pending_notification: name = "● " + name
            self.tabs.setTabText(index, name)
            control = self.tabs.bar.tabButton(index, QTabBar.ButtonPosition.LeftSide)
            if control is not None:
                control.comparing = False
                control.blockSignals(True)
                control.setChecked(False)
                control.blockSignals(False)
                control.setVisible(page.folder is not None)
                control.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                control.setToolTip(self.t["compare_folder"])
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
            if self.current_tab() is not page:
                # Move the shared area while the destination tab is still hidden.
                # Otherwise its empty image slot briefly lets thumbnails fill the page.
                QTimer.singleShot(0, self, lambda: self.show_compare_page(page))

    def show_compare_page(self, page):
        if not (self.compare_enabled and self.focused_compare_page is page and page in self.pages()):
            return
        # Reparenting the shared area and mounting the tab strip can trigger
        # several splitter layouts. Keep the previous frame on screen until
        # the destination has completed its layout.
        self.tabs.setUpdatesEnabled(False)
        try:
            self.rehost_comparison(page)
            self.tabs.setCurrentWidget(page)
            if page._layout_pending: page.apply_layout()
            page.layout().activate()
        finally:
            QTimer.singleShot(0, self.tabs, lambda: self.tabs.setUpdatesEnabled(True))

    def rehost_comparison(self, host):
        area = self.comparison_area
        self.prepare_comparison_host(host)
        if area.parentWidget() is not host.image_slot:
            if host not in area.pages: host.image.hide()
            host.image_slot.layout().addWidget(area)
            area.show()
        area.set_layout_orientation(self._compare_layout[0])

    def prepare_comparison_host(self, host):
        if host not in self._compare_original_layouts:
            self._compare_original_layouts[host] = host.layout_spec()
        if self._compare_layout is not None and host.layout_spec() != self._compare_layout:
            host.apply_layout_spec(self._compare_layout)

    def comparison_layout_changed(self, page):
        if page is not self.current_tab(): return
        if self.compare_enabled:
            self._compare_layout = page.layout_spec()
            self.comparison_area.set_layout_orientation(self._compare_layout[0])
        elif not self._restoring_layout:
            self._pane_layout = page.layout_spec()

    def set_compare(self, enabled):
        if enabled and not self.compare_enabled:
            host = self.current_tab()
            self._compare_layout = host.layout_spec() if host is not None else None
            self._compare_original_layouts = {page: page.layout_spec() for page in self.pages()}
        elif not enabled and self.compare_full_window is not None:
            self.compare_full_window.close()
        last_page = next((page for page in reversed(self.comparison_order) if page in self.pages()), None) if not enabled else None
        last_image = last_page.thumbs.selected_path if last_page is not None else None
        if last_page is not None:
            last_page = getattr(last_page, "comparison_source_page", last_page)
        layout_at_exit = self._compare_layout if not enabled else None
        self.compare_enabled = enabled
        for shortcut in getattr(self, "compare_tab_shortcuts", []): shortcut.setEnabled(enabled)
        self.comparison_order = [self.current_tab()] if enabled and self.current_tab() and self.current_tab().folder else []
        self.checked_pages = set(self.comparison_order)
        self.focused_compare_page = None
        if not enabled: self.set_sync(False)
        self.sync_comparison()
        if not enabled:
            if last_page is not None:
                if last_image in last_page.files and last_page.thumbs.selected_path != last_image:
                    last_page.thumbs.select(last_image)
                self.tabs.setCurrentWidget(last_page)
            for page in [item for item in self.pages() if hasattr(item, "comparison_source_page")]:
                index = self.tabs.indexOf(page)
                self.tabs.removeTab(index)
                page.hide()
                QTimer.singleShot(50, self, lambda page=page: (page.shutdown(), page.deleteLater()))
            target = last_page or self.current_tab()
            if layout_at_exit is not None:
                self._pane_layout = layout_at_exit
                for page in self.pages(): page.apply_layout_spec(layout_at_exit)
            if target is not None:
                if last_image is not None and last_image in target.files and target.thumbs.selected_path != last_image:
                    target.thumbs.select(last_image)
                self.tabs.setCurrentWidget(target)
            self._compare_original_layouts.clear()
            self._compare_layout = None
        self.update_tab_titles()

    def check_compare_page(self, page, checked):
        if not self.compare_enabled: return
        if checked:
            self.checked_pages.add(page)
            if page not in self.comparison_order: self.comparison_order.append(page)
        else:
            self.checked_pages.discard(page)
            if page in self.comparison_order: self.comparison_order.remove(page)
        self.sync_comparison()

    def comparison_drag_source(self, mime):
        if not mime.hasFormat(COMPARISON_TAB_MIME): return None
        try: identifier = int(bytes(mime.data(COMPARISON_TAB_MIME)).decode("ascii"))
        except (ValueError, UnicodeDecodeError): return None
        page = next((item for item in self.pages() if id(item) == identifier and item.folder), None)
        if page is None: return None
        selected = None
        if mime.hasFormat(COMPARISON_IMAGE_MIME):
            try: selected = Path(bytes(mime.data(COMPARISON_IMAGE_MIME)).decode("utf-8"))
            except UnicodeDecodeError: return None
            if selected not in page.files: return None
        return page, selected

    def can_add_comparison(self, target_image):
        target = getattr(target_image, "owner_page", None)
        if target not in self.pages() or target.folder is None: return False
        if self.compare_enabled and target not in self.checked_pages: return False
        count = len(self.comparison_order) if self.compare_enabled else 1
        host = self.current_tab() if self.compare_enabled else target
        if host is None: return False
        available = self.comparison_area.split.size() if self.compare_enabled else host.image_slot.size()
        side_by_side = host.split.orientation() == Qt.Orientation.Vertical
        span = available.width() if side_by_side else available.height() - (0 if self.compare_enabled else 42)
        minimum = 150 if side_by_side else 120
        return span >= minimum * (count + 1)

    def add_comparison_drop(self, target_image, mime):
        source = self.comparison_drag_source(mime)
        if source is None: return False
        page, selected = source
        if selected is not None and mime.hasFormat(THUMBNAIL_FILES_MIME):
            try:
                requested = json.loads(bytes(mime.data(THUMBNAIL_FILES_MIME)).decode("utf-8"))
            except (UnicodeDecodeError, ValueError): return False
            if not isinstance(requested, list): return False
            paths = [path for path in page.files if str(path) in requested]
            if len(paths) > 1:
                return self.add_multiple_comparison_drop(target_image, page, paths)
        if not self.can_add_comparison(target_image):
            self.notification_bar.showMessage(self.t["compare_too_small"], 5000)
            return False
        if not self.compare_enabled:
            self.set_compare(True)
            target = target_image.owner_page
            if target not in self.checked_pages:
                self.checked_pages = {target}
                self.comparison_order = [target]
        if page in self.checked_pages:
            page = self.duplicate_page(page, activate=False, add_to_compare=False, selected=selected)
            if selected is not None and page is not None:
                page.comparison_source_page = getattr(source[0], "comparison_source_page", source[0])
                self.tabs.bar.setTabVisible(self.tabs.indexOf(page), False)
        elif selected is not None:
            page.thumbs.select(selected)
        self.checked_pages.add(page)
        self.comparison_order.append(page)
        self.focused_compare_page = target_image.owner_page
        self.sync_comparison()
        self.update_tab_titles()
        return True

    def queue_comparison_drop(self, target_image, payload):
        source = self.comparison_drag_source(payload)
        if source is None: return
        page, selected = source
        paths = [selected or page.thumbs.selected_path]
        if payload.hasFormat(THUMBNAIL_FILES_MIME):
            try: paths = [Path(path) for path in json.loads(bytes(payload.data(THUMBNAIL_FILES_MIME)).decode())]
            except (ValueError, UnicodeDecodeError, TypeError): return
        paths = [path for path in paths if path is not None and path in page.files]
        progress = ComparisonLoadingOverlay(self.centralWidget(), self.t["compare_loading"])
        progress.setGeometry(QRect(target_image.mapTo(self.centralWidget(), QPoint()), target_image.size()))
        progress.show()
        progress.raise_()

        def decode():
            result = {}
            for path in paths:
                if path.suffix.lower() == ".svg": continue
                try: result[path] = ImagePane.read_frames(path)
                except Exception: pass  # The normal image loader supplies the error view.
            return result

        future = DROP_DECODER.submit(decode)
        poll = QTimer(progress)
        poll.setInterval(16)

        def complete():
            global LOADING_OVERLAY
            if not future.done(): return
            poll.stop()
            decoded = future.result()
            try:
                LOADING_OVERLAY = progress
                DROP_FRAMES.update(decoded)
                if target_image.owner_page in self.pages():
                    self.add_comparison_drop(target_image, payload)
            finally:
                LOADING_OVERLAY = None
                for path in decoded: DROP_FRAMES.pop(path, None)
                progress.close()
                progress.deleteLater()

        poll.timeout.connect(complete)
        poll.start()

    def add_multiple_comparison_drop(self, target_image, source, paths):
        if not self.can_add_comparison(target_image):
            self.notification_bar.showMessage(self.t["compare_too_small"], 5000)
            return False
        target = target_image.owner_page
        if not self.compare_enabled:
            self.set_compare(True)
            if target not in self.checked_pages:
                self.checked_pages = {target}
                self.comparison_order = [target]
        added = False
        existing = {page.thumbs.selected_path for page in self.comparison_order}
        for path in paths:
            loading_checkpoint()
            if path in existing: continue
            if not self.can_add_comparison(target_image):
                self.notification_bar.showMessage(self.t["compare_too_small"], 5000)
                break
            # Each image needs its own navigation and transform state, but these
            # temporary pages must not appear as folder tabs.
            page = self.duplicate_page(source, activate=False, add_to_compare=False, selected=path)
            if page is None: break
            page.comparison_source_page = getattr(source, "comparison_source_page", source)
            self.tabs.bar.setTabVisible(self.tabs.indexOf(page), False)
            self.checked_pages.add(page)
            self.comparison_order.append(page)
            existing.add(path)
            added = True
        if added:
            self.focused_compare_page = target
            self.sync_comparison()
            self.update_tab_titles()
        return added

    def remove_comparison_page(self, page):
        if page not in self.checked_pages: return
        self.checked_pages.discard(page)
        self.comparison_order.remove(page)
        if len(self.comparison_order) < 2:
            self.set_compare(False)
        else:
            if self.focused_compare_page not in self.checked_pages:
                self.focused_compare_page = self.comparison_order[0]
            remaining_focus = self.focused_compare_page
            area = self.comparison_area
            area.setUpdatesEnabled(False)
            try:
                if area.toolbar_image is page.image: area.release_toolbar()
                page.image_slot.layout().addWidget(page.image)
                page.image.hide()
                page.image.set_comparison_mode(None)
                page.set_comparison_visible(False)
                area.pages = self.comparison_order.copy()
                area.select_toolbar(self.focused_compare_page.image)
                area.equalize()
            finally:
                area.setUpdatesEnabled(True)
        if hasattr(page, "comparison_source_page") and page in self.pages():
            if self.compare_enabled and self.current_tab() is page:
                self.show_compare_page(remaining_focus)
            index = self.tabs.indexOf(page)
            self.tabs.removeTab(index)
            page.hide()
            QTimer.singleShot(50, self, lambda page=page: (page.shutdown(), page.deleteLater()))
        if self.compare_enabled:
            self.focus_compare_page(remaining_focus)

    def reorder_comparison_page(self, source, target, after=False):
        if not self.compare_enabled or source not in self.comparison_order or target not in self.comparison_order:
            return False
        if source is target:
            return False
        order = self.comparison_order.copy()
        order.remove(source)
        index = order.index(target) + bool(after)
        order.insert(index, source)
        if order == self.comparison_order:
            self.restore_comparison_order()
            return False
        self.comparison_order = order
        area = self.comparison_area
        area.setUpdatesEnabled(False)
        try:
            for index, page in enumerate(order):
                if area.split.widget(index) is not page.image:
                    area.split.insertWidget(index, page.image)
            area.pages = order.copy()
            area.equalize()
        finally:
            area.setUpdatesEnabled(True)
        return True

    def preview_comparison_reorder(self, source, target, after=False):
        if source is target or source not in self.comparison_order or target not in self.comparison_order:
            return
        split = self.comparison_area.split
        order = [split.widget(index) for index in range(split.count())]
        if source.image not in order or target.image not in order: return
        order.remove(source.image)
        order.insert(order.index(target.image) + bool(after), source.image)
        for index, image in enumerate(order):
            split.insertWidget(index, image)
        self.comparison_area.equalize()

    def restore_comparison_order(self):
        split = self.comparison_area.split
        if not self.compare_enabled or split.count() != len(self.comparison_order): return
        for index, page in enumerate(self.comparison_order):
            split.insertWidget(index, page.image)
        self.comparison_area.equalize()

    def set_sync(self, enabled):
        self.sync_enabled = bool(enabled) and self.compare_enabled and len(self.comparison_order) > 1
        for page in self.pages():
            button = page.image.sync_button
            button.blockSignals(True)
            button.setChecked(self.sync_enabled and page in self.checked_pages)
            button.blockSignals(False)
            button.refresh_icon()
        if self.compare_full_window is not None:
            self.compare_full_window.image_toolbar.refresh()

    def apply_comparison_tool(self, source, action, value):
        if not self.sync_enabled or self._syncing_tools or source not in self.checked_pages: return
        self._syncing_tools = True
        try:
            for page in self.comparison_order:
                if page is source: continue
                image = page.image
                if action in ("rotate", "mirror_h", "mirror_v"):
                    getattr(image, action)()
                elif action == "zoom":
                    if self.compare_full_window is not None:
                        image.fullscreen_zoom = source.image.fullscreen_zoom
                    if image.slider.value() == value: image.set_zoom_percent(value)
                    else: image.slider.setValue(value)
                elif action == "fit":
                    if self.compare_full_window is not None:
                        image.fullscreen_zoom = source.image.fullscreen_zoom
                    image.fit_b.setChecked(value)
                elif action == "background":
                    image.set_background(value)
                elif action in ("scroll_x", "scroll_y"):
                    horizontal = action == "scroll_x"
                    source_bar = (source.image.scroll.horizontalScrollBar() if horizontal
                                  else source.image.scroll.verticalScrollBar())
                    target_bar = (image.scroll.horizontalScrollBar() if horizontal
                                  else image.scroll.verticalScrollBar())
                    source_span = source_bar.maximum() - source_bar.minimum()
                    if source_span > 0:
                        fraction = (value - source_bar.minimum()) / source_span
                        target_span = target_bar.maximum() - target_bar.minimum()
                        target_bar.setValue(round(target_bar.minimum() + fraction * target_span))
        finally:
            self._syncing_tools = False

    def sync_comparison(self):
        area = self.comparison_area
        pages = self.pages()
        if self.compare_enabled:
            for page in pages:
                if page not in self._compare_original_layouts:
                    self._compare_original_layouts[page] = page.layout_spec()
        chosen = [page for page in self.comparison_order if page in pages] if self.compare_enabled else []
        if self.compare_full_window is not None and self.compare_full_window.pages != chosen:
            self.compare_full_window.close()
        host = self.current_tab()
        if (self.compare_enabled and host is not None and area.pages == chosen
                and any(area.parentWidget() is page.image_slot for page in pages)):
            self.rehost_comparison(host)
            area.select_toolbar(self.image_target())
            return
        area.release_toolbar()
        # Return panes to their owners before moving the shared comparison area.
        area.hide()
        area.setParent(self.centralWidget())
        for page in pages:
            if page.image.parentWidget() is not page.image_slot:
                page.image_slot.layout().addWidget(page.image)
            page.image.show()
            visible = page in chosen
            page.image.set_comparison_mode((page.folder.name or str(page.folder)) if visible else None)
            page.image.sync_button.setEnabled(visible and len(chosen) > 1)
            page.image.sync_button.setChecked(visible and len(chosen) > 1 and self.sync_enabled)
            if page.comparison_visible != visible: page.set_comparison_visible(visible)
        area.pages = chosen
        if self.compare_enabled and self.current_tab() is not None:
            host = self.current_tab()
            self.prepare_comparison_host(host)
            host.image.hide()
            host.image_slot.layout().addWidget(area)
            area.set_layout_orientation(self._compare_layout[0])
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
        page = self.navigation_page()
        return page.image if page is not None else None

    def navigation_page(self):
        if self.compare_enabled:
            if self.focused_compare_page in self.checked_pages:
                return self.focused_compare_page
            return next((page for page in self.comparison_order if page in self.checked_pages), None)
        return self.current_tab()

    def navigation_action(self, action, *args):
        page = self.navigation_page()
        if page is not None: getattr(page, action)(*args)

    def image_action(self, action, *args):
        active = QApplication.activeWindow()
        if action == "toggle_fit" and isinstance(active, (SingleImageFullscreen, ComparisonFullscreen)):
            active.image_toolbar.fit_button.click()
            return
        image = self.image_target()
        if image is not None: getattr(image, action)(*args)

    def track_input_focus(self, old, current):
        widget = current
        target = None
        while widget is not None:
            if isinstance(widget, (ThumbnailPane, ImagePane)):
                target = widget
                break
            if hasattr(self, "comparison_area") and widget is self.comparison_area.header:
                target = self.comparison_area.toolbar_image
                break
            widget = widget.parentWidget()
        if target is None: return
        self.input_pane = "thumb" if isinstance(target, ThumbnailPane) else "image"
        for page in self.pages():
            for pane in (page.thumbs, page.image):
                pane.setProperty("inputFocused", pane is target)
                pane.update()

    def zoom_focused(self, direction):
        active = QApplication.activeWindow()
        if isinstance(active, (SingleImageFullscreen, ComparisonFullscreen)):
            toolbar = active.image_toolbar
            toolbar.set_zoom(1000 if direction == 0 else toolbar.zoom_slider.value() + direction * 100)
        elif self.input_pane == "thumb":
            pane = self.current_tab().thumbs
            pane.slider.setValue(THUMBNAIL_BASE_SIZE if direction == 0 else pane.slider.value() + direction * 10)
        elif direction == 0:
            self.image_action("reset_zoom")
        else:
            self.image_action("adjust_zoom", direction * 10)

    def open_comparison_fullscreen(self):
        if self.compare_full_window is not None:
            self.compare_full_window.close()
            return
        if not self.compare_enabled or not self.comparison_area.pages: return
        full = ComparisonFullscreen(self, self.comparison_area.pages)
        self.compare_full_window = full
        for shortcut in self.compare_tab_shortcuts: shortcut.setEnabled(False)
        full.showFullScreen()
        QTimer.singleShot(0, full, full.refresh_all)

    def advance_or_check(self):
        self.navigation_action("select_relative", 1)

    def show_notification(self, page, message):
        if page is self.current_tab(): self.notification_bar.showMessage(message, 8000)

    def setup_shortcuts(self):
        bindings = [(QKeySequence.StandardKey.Open, self.choose), (QKeySequence.StandardKey.AddTab, self.choose),
                    (QKeySequence.StandardKey.Close, lambda: self.close_tab()),
                    (QKeySequence.StandardKey.NextChild, lambda: self.switch_tab(1)),
                    (QKeySequence.StandardKey.PreviousChild, lambda: self.switch_tab(-1)),
                    (QKeySequence.StandardKey.Copy, lambda: self.navigation_action("copy_selected_file")),
                    ("Left", lambda: self.navigation_action("select_relative", -1)), ("Right", lambda: self.navigation_action("select_relative", 1)),
                    ("Up", lambda: self.navigation_action("select_row", -1)), ("Down", lambda: self.navigation_action("select_row", 1)),
                    ("Home", lambda: self.navigation_action("select_boundary", False)), ("End", lambda: self.navigation_action("select_boundary", True)),
                    ("PgUp", lambda: self.navigation_action("select_relative", -1)), ("PgDown", lambda: self.navigation_action("select_relative", 1)),
                    ("Space", self.advance_or_check), ("Backspace", lambda: self.navigation_action("select_relative", -1)),
                    ("Alt+F", lambda: self.image_action("toggle_fit")),
                    ("Alt+C", lambda: self.image_action("rotate")),
                    ("Alt+V", lambda: self.image_action("mirror_v")), ("Alt+H", lambda: self.image_action("mirror_h")),
                    ("+", lambda: self.zoom_focused(1)), ("=", lambda: self.zoom_focused(1)),
                    ("-", lambda: self.zoom_focused(-1)), ("0", lambda: self.zoom_focused(0)), ("F11", lambda: self.image_action("open_full"))]
        modifier = "Meta" if sys.platform == "darwin" else "Ctrl"
        bindings += [(f"{modifier}+{key}", lambda direction=direction: self.zoom_focused(direction))
                     for key, direction in (("+", 1), ("=", 1), ("-", -1), ("0", 0))]
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
        self.compare_tab_shortcuts = []
        for keys, offset in (("Tab", 1), ("Shift+Tab", -1), ("Backtab", -1)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.setEnabled(False)
            shortcut.activated.connect(lambda step=offset: self.cycle_comparison_page(step))
            self.compare_tab_shortcuts.append(shortcut)

    def set_orientation(self, orientation):
        self.current_tab().set_orientation(orientation)

    def toggle_sort_mode(self):
        page = self.current_tab()
        if page is not None and page.folder is not None:
            page.set_sort("modified" if page.thumbs.sort_mode == "natural" else "natural",
                          page.thumbs.sort_descending)

    def toggle_sort_direction(self):
        page = self.current_tab()
        if page is not None and page.folder is not None:
            page.set_sort(page.thumbs.sort_mode, not page.thumbs.sort_descending)

    def refresh_sort_buttons(self):
        page = self.current_tab()
        available = page is not None and page.folder is not None
        mode = page.thumbs.sort_mode if page is not None else "natural"
        descending = page.thumbs.sort_descending if page is not None else False
        for button, active, kind, tip in (
            (self.sort_button, mode == "modified", "sort-date" if mode == "modified" else "sort-name",
             f"{self.t['sort_method']}: {self.t['sort_modified' if mode == 'modified' else 'sort_natural']}"),
            (self.direction_button, descending, "sort-descending" if descending else "sort-ascending",
             f"{self.t['sort_direction']}: {self.t['sort_descending' if descending else 'sort_ascending']}")):
            button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(False)
            button.setEnabled(available)
            button.set_kind(kind, tip)
            button.setAccessibleName(tip)

    def rebuild_ui(self, *, palette_changed=True):
        if self.about_action is not None: self.about_action.setText(self.t["about"])
        self.refresh_sort_buttons()
        self.refresh_shell_integration_button()
        self.modified_button.setToolTip(self.t["show_modified"])
        self.modified_button.setAccessibleName(self.t["show_modified"])
        self.settings_button.set_kind("more", self.t["more_tools"])
        self.settings_button.setAccessibleName(self.t["more_tools"])
        if palette_changed: self.modified_button.refresh_icon()
        self.open_button.setToolTip(shortcut_tooltip(self.t["open"], QKeySequence.StandardKey.Open))
        self.comparison_area.empty.setText(self.t["compare_empty"])
        self.language_button.set_kind(LANGUAGE_ICONS[self.language_mode], self.t[f"lang_{self.language_mode}"])
        self.language_button.setAccessibleName(self.language_button.toolTip())
        self.theme_button.set_kind(f"theme-{self.theme_mode}", self.t[f"theme_{self.theme_mode}"])
        self.tab_list_button.set_kind("tab-list", self.t["tab_list"])
        self.tab_list_button.setAccessibleName(self.t["tab_list"])
        if palette_changed: self.apply_styles()
        for page in self.pages():
            if page.active or page.comparison_visible:
                page.restyle(self.t, palette_changed=palette_changed)
            else:
                page.t = page.thumbs.labels = page.image.labels = self.t
                page._pending_restyle = palette_changed or page._pending_restyle is True
        if self.compare_enabled:
            if palette_changed:
                for button in self.comparison_area.header.findChildren(IconButton): button.refresh_icon()
            self.comparison_area.select_toolbar(self.image_target())
        for index in range(self.tabs.count()):
            button = self.tabs.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
            button.setToolTip(shortcut_tooltip(self.t["close_tab"], QKeySequence.StandardKey.Close))
            button.setAccessibleName(self.t["close_tab"])
            button.update()
        if palette_changed:
            for button in (self.open_button, self.integration_button): button.refresh_icon()
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
        self._pane_layout = self.current_tab().layout_spec()
        for page in self.pages():
            if page is not self.current_tab(): page.apply_layout_spec(self._pane_layout)
        self._restoring_layout = False
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
        self.rebuild_ui(palette_changed=False)


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

    def select_relative(self, *args):
        return self.navigation_action("select_relative", *args)

    def select_boundary(self, *args):
        return self.navigation_action("select_boundary", *args)

    def copy_selected_file(self, *args):
        return self.navigation_action("copy_selected_file", *args)


def set_application_identity(app: QApplication) -> None:
    app.setApplicationName("PicView")
    # macOS uses the application icon for the Dock; a window icon alone
    # leaves Python's icon in place when running outside an .app bundle.
    icon_path = Path(__file__).parent / "assets" / ("picview-icon.ico" if sys.platform == "win32" else "picview-icon.png")
    app.setWindowIcon(QIcon(str(icon_path)))


def open_startup_paths(window: PicView, paths: list[str]) -> None:
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            window.open_folder(path)
        elif path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            window.open_folder(path.parent, path)


def open_received_paths(window: PicView, paths: list[str]) -> None:
    open_startup_paths(window, paths)
    if window.isMinimized():
        window.showNormal()
    window.raise_()
    window.activateWindow()


def main():
    parser = argparse.ArgumentParser(description="PicView image folder viewer")
    parser.add_argument("--version", action="version", version=f"PicView {__version__}")
    parser.add_argument("paths", nargs="*", help="folders or image files to open")
    args = parser.parse_args()
    app = PicViewApplication([sys.argv[0]])
    if forward_paths(args.paths):
        return
    set_application_identity(app)
    use_system_palette(app)
    window = PicView()
    app.paletteChanged.connect(window.refresh_system_theme)
    window.show()
    InstanceReceiver(window, lambda paths: open_received_paths(window, paths))
    open_startup_paths(window, args.paths)
    app.set_open_paths_handler(lambda paths: open_received_paths(window, paths))
    sys.exit(app.exec())
