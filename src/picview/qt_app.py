from __future__ import annotations

import locale
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygon, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPushButton, QScrollArea, QSlider, QSplitter, QStyle, QStyleOptionSlider, QToolButton, QVBoxLayout, QWidget, QWidgetAction, QSizePolicy,
)

from . import __version__
from .settings import load_settings, save_settings
from .utils import image_files


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
        elif self.kind == "fullscreen":
            for x,y,dx,dy in ((9,9,1,1),(27,9,-1,1),(9,27,1,-1),(27,27,-1,-1)): p.drawLine(x,y,x+6*dx,y); p.drawLine(x,y,x,y+6*dy)
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
        layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5); layout.setSpacing(2)
        self.name = QLabel(path.name); self.name.setAlignment(Qt.AlignmentFlag.AlignCenter); self.name.setFixedHeight(20); self.name.setWordWrap(False)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setFixedHeight(size)
        if pixmap: self.preview.setPixmap(pixmap)
        layout.addWidget(self.name); layout.addWidget(self.preview); self.apply_style()
    def apply_style(self) -> None:
        color = THUMBNAIL_SELECTED if self.selected else PALETTE["card"]
        text = "#153047" if self.selected else PALETTE["text"]
        self.setStyleSheet(f"ThumbnailTile{{background:{color};border:0;border-radius:9px;}} QLabel{{background:{color};color:{text};}}")
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked_path.emit(self.path)
        super().mousePressEvent(event)


class ThumbnailPane(QFrame):
    selected = Signal(Path)
    def __init__(self, labels: dict[str, str], parent=None):
        super().__init__(parent); self.labels=labels; self.files=[]; self.size=THUMBNAIL_BASE_SIZE; self.buttons={}
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,6,10,8)
        header=QHBoxLayout(); header.addWidget(QLabel(labels["thumb"])); self.max_button=IconButton("expand",labels["max"]); header.addWidget(self.max_button); header.addStretch(); self.size_label=ScaleValueButton(self.size,72,260,THUMBNAIL_BASE_SIZE,1,"px",labels["edit_thumb"]); header.addWidget(self.size_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,THUMBNAIL_BASE_SIZE); self.slider.setRange(72,260); self.slider.setValue(self.size); self.slider.setFixedSize(SLIDER_WIDTH,30); self.slider.logicalValueChanged.connect(self._resize); self.size_label.valueChosen.connect(self.slider.setValue); header.addWidget(self.slider); layout.addLayout(header)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.grid_host=QWidget(); self.grid_host.setObjectName("thumbnailGrid"); self.grid_host.setStyleSheet(f"#thumbnailGrid{{background:{PALETTE['pane']};}}"); self.grid=QGridLayout(self.grid_host); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft); self.scroll.setWidget(self.grid_host); layout.addWidget(self.scroll)
    def set_files(self, files, selected=None): self.files=files; self.selected_path=selected if selected in files else (files[0] if files else None); self.build(); self.selected.emit(self.selected_path) if self.selected_path else None
    def _resize(self,v): self.size=v; self.size_label.set_value(v); self.build()
    def build(self):
        while self.grid.count(): item=self.grid.takeAt(0); item.widget().deleteLater() if item.widget() else None
        cols=max(1,self.scroll.viewport().width()//(self.size+20)); self.buttons={}
        for i,path in enumerate(self.files):
            try:
                with Image.open(path) as im: im=ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((self.size,self.size)); pix=QPixmap.fromImage(qimage(im.copy()))
                b=ThumbnailTile(path, pix, self.size, path == self.selected_path)
            except Exception: b=ThumbnailTile(path, None, self.size, path == self.selected_path)
            b.clicked_path.connect(self.select)
            self.grid.addWidget(b,i//cols,i%cols); self.buttons[path]=b
    def resizeEvent(self,event): super().resizeEvent(event); QTimer.singleShot(0,self.build)
    def select(self,path):
        if path not in self.files: return
        self.selected_path=path
        for p,b in self.buttons.items(): b.selected = p == path; b.apply_style()
        if path in self.buttons: self.scroll.ensureWidgetVisible(self.buttons[path])
        self.selected.emit(path)


class ImagePane(QFrame):
    def __init__(self, labels, parent=None):
        super().__init__(parent); self.labels=labels; self.path=None; self.frames=[]; self.index=0; self.rotation=0; self.fh=False; self.fv=False; self.zoom=1.0; self.fit_to_pane=False; self.auto_scale=False; self._applying_auto_scale=False; self.display_scale=1.0; self.full_window=None; self.timer=QTimer(self); self.timer.timeout.connect(self.next_frame)
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,6,10,8)
        bar=QHBoxLayout(); self.rotate_b=IconButton("rotate",labels["rotate"]); self.mh=IconButton("mirror-h",labels["mh"]); self.mv=IconButton("mirror-v",labels["mv"]); self.fit_b=IconButton("fit",labels["fit"]); self.fit_b.setCheckable(True); self.fit_b.toggled.connect(self.set_fit); self.max_button=IconButton("expand",labels["max"]); self.full=IconButton("fullscreen",labels["full"])
        for b,fn in ((self.rotate_b,self.rotate),(self.mh,self.mirror_h),(self.mv,self.mirror_v)): b.clicked.connect(fn); bar.addWidget(b)
        divider=QFrame(); divider.setFixedSize(1,22); divider.setStyleSheet(f"background:{PALETTE['edge']};"); bar.addSpacing(6); bar.addWidget(divider); bar.addSpacing(6)
        self.full.clicked.connect(self.open_full)
        for button in (self.fit_b,self.max_button,self.full): bar.addWidget(button)
        self.filename_label=QLabel(); self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.filename_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed); bar.addWidget(self.filename_label,1)
        self.zoom_label=ScaleValueButton(1000,1,4000,1000,10,"%",labels["edit_zoom"]); bar.addWidget(self.zoom_label); self.slider=ReferenceSlider(Qt.Orientation.Horizontal,1000); self.slider.setRange(1,4000); self.slider.setValue(1000); self.slider.logicalValueChanged.connect(self.set_zoom_percent); self.zoom_label.valueChosen.connect(self.choose_zoom); self.slider.setFixedSize(SLIDER_WIDTH,30); bar.addWidget(self.slider); layout.addLayout(bar)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(False); self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.viewport().setStyleSheet(f"background:{PALETTE['pane']};"); self.label=QLabel(labels["empty"]); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.label.setStyleSheet(f"color:{PALETTE['muted']};background:transparent;"); self.scroll.setWidget(self.label); layout.addWidget(self.scroll)
    def load(self,path):
        self.auto_scale=False; self.path=path; self.rotation=0; self.fh=self.fv=False; self.zoom=1.0; self.frames=[]; self.timer.stop(); self.fit_b.setChecked(False)
        self.slider.blockSignals(True); self.slider.setMaximum(4000); self.slider.setValue(1000); self.slider.blockSignals(False); self.zoom_label.set_value(1000)
        self.filename_label.setText(path.name); self.filename_label.setToolTip(str(path))
        try:
            with Image.open(path) as im:
                for i in range(getattr(im,"n_frames",1)): im.seek(i); self.frames.append((ImageOps.exif_transpose(im).convert("RGBA").copy(),max(20,int(im.info.get("duration",100)))))
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


class PicView(QMainWindow):
    def __init__(self):
        super().__init__(); self.settings=load_settings(); syslang=(locale.getlocale()[0] or "en").lower(); self.lang="zh" if self.settings.get("language")=="system" and syslang.startswith("zh") else self.settings.get("language","en"); self.lang=self.lang if self.lang in TEXT else "en"; self.t=TEXT[self.lang]; self.folder=None; self.files=[]; self.saved_sizes=None
        app=QApplication.instance(); self.system_palette=QPalette(app.palette()); self.theme_mode=self.settings.get("theme","system"); self.theme_mode=self.theme_mode if self.theme_mode in ("system","light","dark") else "system"; self._applying_theme=False
        if self.theme_mode != "system": app.setPalette(themed_palette(self.system_palette,self.theme_mode))
        use_system_palette(app)
        self.setWindowTitle(f"PicView v{__version__}")
        self.setMinimumSize(720,500); self.resize(1100,780); self.setAcceptDrops(True); self.build(); self.setup_shortcuts(); self.restore()

    def setup_shortcuts(self):
        bindings = [
            (QKeySequence.StandardKey.Open, self.choose),
            (QKeySequence.StandardKey.Copy, self.copy_selected_file),
            ("Left", lambda: self.select_relative(-1)),
            ("Right", lambda: self.select_relative(1)),
            ("Home", lambda: self.select_boundary(False)),
            ("End", lambda: self.select_boundary(True)),
            ("PgUp", lambda: self.select_relative(-1)),
            ("PgDown", lambda: self.select_relative(1)),
            ("Space", lambda: self.select_relative(1)),
            ("Backspace", lambda: self.select_relative(-1)),
            ("+", lambda: self.image.adjust_zoom(10)),
            ("=", lambda: self.image.adjust_zoom(10)),
            ("-", lambda: self.image.adjust_zoom(-10)),
            ("0", self.image.reset_zoom),
            ("F11", self.image.open_full),
        ]
        self.shortcuts = []
        for keys, action in bindings:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)

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

    def refresh_system_theme(self, _palette=None) -> None:
        if self._applying_theme or self.theme_mode != "system": return
        self.system_palette=QPalette(QApplication.instance().palette())
        use_system_palette(QApplication.instance())
        self.rebuild_ui()

    def rebuild_ui(self):
        selected = getattr(self.thumbs, "selected_path", None)
        orientation = self.split.orientation()
        maximized = None if self.saved_sizes is None else ("thumb" if self.image.isHidden() else "image")
        sizes = self.saved_sizes if self.saved_sizes is not None else self.split.sizes()
        thumb_size = self.thumbs.size
        image_zoom = self.image.slider.value()
        image_fit = self.image.fit_to_pane
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.build()
        self.setup_shortcuts()
        self.saved_sizes = None
        self.split.setOrientation(orientation)
        if self.folder:
            self.open_folder(self.folder, selected)
        self.thumbs.slider.setValue(thumb_size)
        if image_fit:
            self.image.fit_b.setChecked(True)
        elif self.image.fit_to_pane:
            self.image.fit_b.setChecked(False)
        if not image_fit and image_zoom != 1000:
            self.image.slider.setValue(image_zoom)
        def restore_layout():
            self.split.setSizes(sizes)
            if maximized: self.maximize(maximized)
        QTimer.singleShot(0, restore_layout)

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

    def build(self):
        root=QWidget(); root.setObjectName("root"); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(8,8,8,8); outer.setSpacing(8)
        tool=QFrame(); tool.setObjectName("toolbar"); tool.setFixedHeight(42); tool.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed); tl=QHBoxLayout(tool); tl.setContentsMargins(8,6,8,6)
        for kind,key,fn in (("folder","open",self.choose), ("split-h","vertical",lambda:self.set_orientation(Qt.Orientation.Vertical)), ("split-v","horizontal",lambda:self.set_orientation(Qt.Orientation.Horizontal)), (self.t["lang"],"lang",self.toggle_lang)):
            b=IconButton(kind,self.t[key]); b.clicked.connect(fn); tl.addWidget(b)
        self.theme_button=IconButton(f"theme-{self.theme_mode}",self.t[f"theme_{self.theme_mode}"]); self.theme_button.clicked.connect(self.toggle_theme); tl.addWidget(self.theme_button)
        tl.addStretch(); outer.addWidget(tool)
        self.split=QSplitter(Qt.Orientation.Vertical); self.split.setChildrenCollapsible(False); self.split.setHandleWidth(7); self.thumbs=ThumbnailPane(self.t); self.image=ImagePane(self.t); self.split.addWidget(self.thumbs); self.split.addWidget(self.image); self.thumbs.selected.connect(self.image.load); self.thumbs.max_button.clicked.connect(lambda:self.maximize("thumb")); self.image.max_button.clicked.connect(lambda:self.maximize("image")); outer.addWidget(self.split)
        self.setStyleSheet(f"#root{{background:{PALETTE['surface']};}} #toolbar{{background:transparent;border:0;}} #card{{background:{PALETTE['card']};border:0;border-radius:12px;}} QLabel{{color:{PALETTE['text']};}} QSlider::groove:horizontal{{height:5px;background:{PALETTE['edge']};border-radius:2px}} QSlider::handle:horizontal{{background:{PALETTE['accent']};width:15px;margin:-5px 0;border-radius:7px}} QScrollBar:vertical{{background:{PALETTE['surface']};width:12px}} QScrollBar::handle:vertical{{background:{PALETTE['edge']};border-radius:6px;min-height:25px}}")
    def choose(self):
        d=QFileDialog.getExistingDirectory(self,self.t["open"],str(self.folder) if self.folder else "")
        if d:self.open_folder(Path(d))
    def open_folder(self,folder,selected=None):
        self.folder=folder.resolve(); self.files=image_files(self.folder); self.thumbs.set_files(self.files,selected)
        if not self.files: self.image.clear()
        self.setWindowTitle(f"PicView v{__version__} — {self.folder}")
    def set_orientation(self,o):
        if self.split.orientation()==o:return
        sizes=self.split.sizes(); self.split.setOrientation(o); QTimer.singleShot(0,lambda:self.split.setSizes(sizes))
    def maximize(self,which):
        if self.saved_sizes is None:
            self.saved_sizes=self.split.sizes(); hide=self.image if which=="thumb" else self.thumbs; hide.hide(); b=self.thumbs.max_button if which=="thumb" else self.image.max_button; b.set_kind("shrink",self.t["restore"])
        else:
            self.thumbs.show(); self.image.show(); self.split.setSizes(self.saved_sizes); self.saved_sizes=None; self.thumbs.max_button.set_kind("expand",self.t["max"]); self.image.max_button.set_kind("expand",self.t["max"])
    def toggle_lang(self): self.settings["language"]="en" if self.lang=="zh" else "zh"; self.lang=self.settings["language"]; self.t=TEXT[self.lang]; self.rebuild_ui()
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e):
        path=Path(e.mimeData().urls()[0].toLocalFile()); self.open_folder(path if path.is_dir() else path.parent,path if path.is_file() else None)
    def restore(self):
        f=Path(self.settings["folder"]) if self.settings.get("folder") else None
        if f and f.is_dir(): self.open_folder(f,Path(self.settings.get("selected_file","")))
        QTimer.singleShot(0,lambda:self.split.setSizes([max(100,int(self.height()*float(self.settings.get("sash_fraction",.45)))),max(100,int(self.height()*(1-float(self.settings.get("sash_fraction",.45)))))]))
    def closeEvent(self,e):
        sizes=self.split.sizes(); fraction=sizes[0]/sum(sizes) if len(sizes)==2 and sum(sizes) else .45; save_settings({"folder":str(self.folder) if self.folder else "","selected_file":str(self.thumbs.selected_path) if getattr(self.thumbs,"selected_path",None) else "","orientation":"vertical" if self.split.orientation()==Qt.Orientation.Vertical else "horizontal","sash_fraction":fraction,"maximized_pane":"","thumbnail_size":self.thumbs.size,"image_zoom":self.image.zoom,"language":self.lang,"theme":self.theme_mode}); e.accept()


def main():
    parser = argparse.ArgumentParser(description="PicView image folder viewer")
    parser.add_argument("--version", action="version", version=f"PicView {__version__}")
    parser.parse_args()
    app=QApplication(sys.argv); app.setApplicationName("PicView"); use_system_palette(app); w=PicView(); app.paletteChanged.connect(w.refresh_system_theme); icon=Path(__file__).parent/"assets"/"picview-icon.png"; w.setWindowIcon(QIcon(str(icon))); w.show(); sys.exit(app.exec())
