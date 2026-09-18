from __future__ import annotations

import locale
import sys
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QPolygon, QPalette
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSlider, QSplitter, QStyle, QStyleOptionSlider, QToolButton, QVBoxLayout, QWidget, QSizePolicy,
)

from .settings import load_settings, save_settings
from .utils import image_files


PALETTE = {"surface": "#f4f7f8", "card": "#ffffff", "edge": "#c7d3d8", "accent": "#188a9a", "text": "#172a31", "muted": "#526a73"}


def use_system_palette(app: QApplication) -> None:
    """Derive every custom colour from the active OS/Qt palette."""
    pal = app.palette()
    PALETTE.update({
        "surface": pal.color(QPalette.ColorRole.Window).name(),
        "card": pal.color(QPalette.ColorRole.Base).name(),
        "edge": pal.color(QPalette.ColorRole.Mid).name(),
        "accent": pal.color(QPalette.ColorRole.Highlight).name(),
        "text": pal.color(QPalette.ColorRole.Text).name(),
        "muted": pal.color(QPalette.ColorRole.PlaceholderText).name(),
    })
TEXT = {
    "en": {"open": "Open folder", "vertical": "Top / bottom", "horizontal": "Left / right", "lang": "中文", "thumb": "Thumbnails", "max": "Maximize pane", "restore": "Restore panes", "rotate": "Rotate clockwise", "mh": "Mirror horizontally", "mv": "Mirror vertically", "full": "Full screen", "zoom": "Zoom", "empty": "Open a folder to view images"},
    "zh": {"open": "開啟資料夾", "vertical": "上下窗格", "horizontal": "左右窗格", "lang": "En", "thumb": "縮圖", "max": "最大化窗格", "restore": "還原窗格", "rotate": "順時針旋轉", "mh": "水平鏡射", "mv": "垂直鏡射", "full": "全螢幕", "zoom": "縮放", "empty": "開啟資料夾以檢視圖片"},
}


def qimage(image: Image.Image) -> QImage:
    image = image.convert("RGBA")
    return QImage(image.tobytes(), image.width, image.height, QImage.Format.Format_RGBA8888).copy()


class IconButton(QToolButton):
    """Fixed 36px square vector icon button; each glyph shares a 18px grid."""
    def __init__(self, icon: str, tip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = icon
        self.setToolTip(tip); self.setFixedSize(36, 36); self.setIconSize(self.size())
        self.setStyleSheet(f"QToolButton{{background:{PALETTE['card']};border:1px solid {PALETTE['edge']};border-radius:10px;}}QToolButton:hover{{border-color:{PALETTE['accent']};}}QToolButton:pressed{{background:{PALETTE['accent']};}}")
        self.refresh_icon()

    def set_kind(self, icon: str, tip: str) -> None:
        self.kind = icon; self.setToolTip(tip); self.refresh_icon()

    def refresh_icon(self) -> None:
        pm = QPixmap(36, 36); pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(QPen(QColor(PALETTE["text"]), 2))
        r = 9, 9, 18, 18
        if self.kind == "folder":
            p.drawRoundedRect(9, 14, 18, 11, 2, 2); p.drawLine(10, 14, 15, 14); p.drawLine(15, 14, 17, 11); p.drawLine(17, 11, 23, 11)
        elif self.kind.startswith("split"):
            p.drawRect(9, 11, 18, 14); p.drawLine(18, 12, 18, 24) if self.kind == "split-v" else p.drawLine(10, 18, 26, 18)
        elif self.kind == "rotate":
            p.drawArc(*r, 40 * 16, 285 * 16); p.drawLine(26, 9, 27, 15); p.drawLine(27, 15, 21, 12)
        elif self.kind in {"mirror-h", "mirror-v"}:
            if self.kind == "mirror-h":
                p.setPen(QPen(QColor(PALETTE["text"]), 1, Qt.PenStyle.DashLine)); p.drawLine(18, 9, 18, 27); p.setBrush(QColor(PALETTE["text"])); p.drawPolygon(QPolygon([QPoint(9,25),QPoint(15,12),QPoint(15,25)])); p.drawPolygon(QPolygon([QPoint(27,25),QPoint(21,12),QPoint(21,25)]))
            else:
                p.setPen(QPen(QColor(PALETTE["text"]), 1, Qt.PenStyle.DashLine)); p.drawLine(9, 18, 27, 18); p.setBrush(QColor(PALETTE["text"])); p.drawPolygon(QPolygon([QPoint(12,9),QPoint(25,15),QPoint(12,15)])); p.drawPolygon(QPolygon([QPoint(12,27),QPoint(25,21),QPoint(12,21)]))
        elif self.kind in {"expand", "shrink"}:
            p.drawRect(9, 9, 18, 18)
            if self.kind == "expand": p.drawLine(15,15,10,10); p.drawLine(10,10,14,10); p.drawLine(10,10,10,14); p.drawLine(21,21,26,26); p.drawLine(26,26,22,26); p.drawLine(26,26,26,22)
            else: p.drawLine(10,10,15,15); p.drawLine(15,15,11,15); p.drawLine(15,15,15,11); p.drawLine(26,26,21,21); p.drawLine(21,21,25,21); p.drawLine(21,21,21,25)
        elif self.kind == "fullscreen":
            for x,y,dx,dy in ((9,9,1,1),(27,9,-1,1),(9,27,1,-1),(27,27,-1,-1)): p.drawLine(x,y,x+6*dx,y); p.drawLine(x,y,x,y+6*dy)
        else:
            p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, self.kind)
        p.end(); self.setIcon(QIcon(pm))


class ZoomSlider(QSlider):
    """Zoom control with a permanent, visible 100% reference tick."""
    def reference_x(self) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderHandle, self)
        travel = max(0, groove.width() - handle.width())
        return groove.x() + self.style().sliderPositionFromValue(self.minimum(), self.maximum(), 100, travel) + handle.width() // 2

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option, QStyle.SubControl.SC_SliderGroove, self)
        x = self.reference_x()
        painter = QPainter(self)
        # A labelled downward triangle is an unambiguous reference marker.
        painter.setPen(QPen(QColor(PALETTE["muted"]), 1))
        painter.drawText(x - 22, 1, 44, 10, Qt.AlignmentFlag.AlignCenter, "100%")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PALETTE["accent"]))
        tip_y = groove.top() - 1
        painter.drawPolygon(QPolygon([QPoint(x - 5, tip_y - 6), QPoint(x + 5, tip_y - 6), QPoint(x, tip_y)]))
        painter.end()

    def mousePressEvent(self, event) -> None:
        x = self.reference_x()
        if 1 <= event.position().y() <= 11 and x - 22 <= event.position().x() <= x + 22:
            self.setValue(100)
            event.accept()
            return
        super().mousePressEvent(event)


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
        color = PALETTE["accent"] if self.selected else PALETTE["card"]
        text = PALETTE["card"] if self.selected else PALETTE["text"]
        self.setStyleSheet(f"ThumbnailTile{{background:{color};border:1px solid {PALETTE['edge']};border-radius:9px;}}ThumbnailTile:hover{{border-color:{PALETTE['accent']};}} QLabel{{color:{text};}}")
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked_path.emit(self.path)
        super().mousePressEvent(event)


class ThumbnailPane(QFrame):
    selected = Signal(Path)
    def __init__(self, labels: dict[str, str], parent=None):
        super().__init__(parent); self.labels=labels; self.files=[]; self.size=140; self.buttons={}
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,8,10,10)
        header=QHBoxLayout(); header.addWidget(QLabel(labels["thumb"])); self.max_button=IconButton("expand",labels["max"]); header.addWidget(self.max_button); header.addStretch(); self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(72,260); self.slider.setValue(self.size); self.slider.valueChanged.connect(self._resize); header.addWidget(self.slider); layout.addLayout(header)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.grid_host=QWidget(); self.grid=QGridLayout(self.grid_host); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft); self.scroll.setWidget(self.grid_host); layout.addWidget(self.scroll)
    def set_files(self, files, selected=None): self.files=files; self.selected_path=selected if selected in files else (files[0] if files else None); self.build(); self.selected.emit(self.selected_path) if self.selected_path else None
    def _resize(self,v): self.size=v; self.build()
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
        self.selected_path=path
        for p,b in self.buttons.items(): b.selected = p == path; b.apply_style()
        self.selected.emit(path)


class ImagePane(QFrame):
    def __init__(self, labels, parent=None):
        super().__init__(parent); self.labels=labels; self.path=None; self.frames=[]; self.index=0; self.rotation=0; self.fh=False; self.fv=False; self.zoom=1.0; self.timer=QTimer(self); self.timer.timeout.connect(self.next_frame)
        self.setObjectName("card"); layout=QVBoxLayout(self); layout.setContentsMargins(10,8,10,10)
        bar=QHBoxLayout(); self.rotate_b=IconButton("rotate",labels["rotate"]); self.mh=IconButton("mirror-h",labels["mh"]); self.mv=IconButton("mirror-v",labels["mv"]); self.max_button=IconButton("expand",labels["max"]); self.full=IconButton("fullscreen",labels["full"])
        for b,fn in ((self.rotate_b,self.rotate),(self.mh,self.mirror_h),(self.mv,self.mirror_v)): b.clicked.connect(fn); bar.addWidget(b)
        bar.addStretch(); self.zoom_label=QLabel("100%"); self.zoom_label.setMinimumWidth(42); bar.addWidget(self.zoom_label); self.slider=ZoomSlider(Qt.Orientation.Horizontal); self.slider.setRange(10,400); self.slider.setValue(100); self.slider.setToolTip("100% reference mark"); self.slider.valueChanged.connect(self.set_zoom_percent); self.slider.setFixedSize(160,44); bar.addWidget(self.slider); bar.addWidget(self.max_button); self.full.clicked.connect(self.open_full); bar.addWidget(self.full); layout.addLayout(bar)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(False); self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.label=QLabel(labels["empty"]); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.label.setStyleSheet(f"color:{PALETTE['muted']};background:{PALETTE['surface']};"); self.scroll.setWidget(self.label); layout.addWidget(self.scroll)
    def load(self,path):
        self.path=path; self.rotation=0; self.fh=self.fv=False; self.zoom=1.0; self.slider.blockSignals(True); self.slider.setValue(100); self.slider.blockSignals(False); self.zoom_label.setText("100%"); self.frames=[]; self.timer.stop()
        try:
            with Image.open(path) as im:
                for i in range(getattr(im,"n_frames",1)): im.seek(i); self.frames.append((ImageOps.exif_transpose(im).convert("RGBA").copy(),max(20,int(im.info.get("duration",100)))))
            self.index=0; self.render();
            if len(self.frames)>1:self.timer.start(self.frames[0][1])
        except Exception: self.frames=[]; self.label.setText(self.labels["empty"])
    def next_frame(self): self.index=(self.index+1)%len(self.frames); self.timer.start(self.frames[self.index][1]); self.render()
    def image(self):
        im=self.frames[self.index][0]
        if self.rotation: im=im.rotate(-self.rotation,expand=True)
        if self.fh: im=ImageOps.mirror(im)
        if self.fv: im=ImageOps.flip(im)
        return im
    def render(self):
        if not self.frames:return
        im=self.image(); vw=max(1,self.scroll.viewport().width()-8); vh=max(1,self.scroll.viewport().height()-8); scale=min(vw/im.width,vh/im.height)*self.zoom; size=(max(1,round(im.width*scale)),max(1,round(im.height*scale))); pix=QPixmap.fromImage(qimage(im.resize(size,Image.Resampling.LANCZOS))); self.label.setPixmap(pix); self.label.setFixedSize(pix.size())
    def resizeEvent(self,e): super().resizeEvent(e); QTimer.singleShot(0,self.render)
    def wheelEvent(self,e): self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().value()-e.angleDelta().y()); e.accept()
    def rotate(self): self.rotation=(self.rotation+90)%360; self.render()
    def mirror_h(self): self.fh=not self.fh; self.render()
    def mirror_v(self): self.fv=not self.fv; self.render()
    def set_zoom_percent(self, percent):
        self.zoom = percent / 100
        self.zoom_label.setText(f"{percent}%")
        self.render()
    def open_full(self):
        w=QMainWindow(self); w.setWindowState(Qt.WindowState.WindowFullScreen); label=QLabel(); label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setStyleSheet("background:#111820;"); w.setCentralWidget(label); w.keyPressEvent=lambda e: w.close() if e.key()==Qt.Key.Key_Escape else None; im=self.image(); label.setPixmap(QPixmap.fromImage(qimage(im))); w.show(); self.full_window=w


class PicView(QMainWindow):
    def __init__(self):
        super().__init__(); self.settings=load_settings(); syslang=(locale.getlocale()[0] or "en").lower(); self.lang="zh" if self.settings.get("language")=="system" and syslang.startswith("zh") else self.settings.get("language","en"); self.lang=self.lang if self.lang in TEXT else "en"; self.t=TEXT[self.lang]; self.folder=None; self.files=[]; self.saved_sizes=None
        self.setMinimumSize(720,500); self.resize(1100,780); self.setAcceptDrops(True); self.build(); self.restore()

    def refresh_system_theme(self, _palette=None) -> None:
        selected = getattr(self.thumbs, "selected_path", None)
        orientation = self.split.orientation()
        sizes = self.split.sizes()
        use_system_palette(QApplication.instance())
        self.build()
        self.split.setOrientation(orientation)
        if self.folder:
            self.open_folder(self.folder, selected)
        QTimer.singleShot(0, lambda: self.split.setSizes(sizes))
    def build(self):
        root=QWidget(); root.setObjectName("root"); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(8,8,8,8); outer.setSpacing(8)
        tool=QFrame(); tool.setObjectName("toolbar"); tool.setFixedHeight(52); tool.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed); tl=QHBoxLayout(tool); tl.setContentsMargins(8,6,8,6)
        for kind,key,fn in (("folder","open",self.choose), ("split-h","vertical",lambda:self.set_orientation(Qt.Orientation.Vertical)), ("split-v","horizontal",lambda:self.set_orientation(Qt.Orientation.Horizontal)), (self.t["lang"],"lang",self.toggle_lang)):
            b=IconButton(kind,self.t[key]); b.clicked.connect(fn); tl.addWidget(b)
        tl.addStretch(); outer.addWidget(tool)
        self.split=QSplitter(Qt.Orientation.Vertical); self.split.setChildrenCollapsible(False); self.split.setHandleWidth(7); self.thumbs=ThumbnailPane(self.t); self.image=ImagePane(self.t); self.split.addWidget(self.thumbs); self.split.addWidget(self.image); self.thumbs.selected.connect(self.image.load); self.thumbs.max_button.clicked.connect(lambda:self.maximize("thumb")); self.image.max_button.clicked.connect(lambda:self.maximize("image")); outer.addWidget(self.split)
        self.setStyleSheet(f"#root{{background:{PALETTE['surface']};}} #toolbar{{background:{PALETTE['card']};border:1px solid {PALETTE['edge']};border-radius:12px;}} #card{{background:{PALETTE['card']};border:1px solid {PALETTE['edge']};border-radius:12px;}} QLabel{{color:{PALETTE['text']};}} QSlider::groove:horizontal{{height:5px;background:{PALETTE['edge']};border-radius:2px}} QSlider::handle:horizontal{{background:{PALETTE['accent']};width:15px;margin:-5px 0;border-radius:7px}} QScrollBar:vertical{{background:{PALETTE['surface']};width:12px}} QScrollBar::handle:vertical{{background:{PALETTE['edge']};border-radius:6px;min-height:25px}}")
    def choose(self):
        d=QFileDialog.getExistingDirectory(self,self.t["open"],str(self.folder) if self.folder else "")
        if d:self.open_folder(Path(d))
    def open_folder(self,folder,selected=None): self.folder=folder.resolve(); self.files=image_files(self.folder); self.thumbs.set_files(self.files,selected); self.setWindowTitle(f"PicView — {self.folder}")
    def set_orientation(self,o):
        if self.split.orientation()==o:return
        sizes=self.split.sizes(); self.split.setOrientation(o); QTimer.singleShot(0,lambda:self.split.setSizes(sizes))
    def maximize(self,which):
        if self.saved_sizes is None:
            self.saved_sizes=self.split.sizes(); hide=self.image if which=="thumb" else self.thumbs; hide.hide(); b=self.thumbs.max_button if which=="thumb" else self.image.max_button; b.set_kind("shrink",self.t["restore"])
        else:
            self.thumbs.show(); self.image.show(); self.split.setSizes(self.saved_sizes); self.saved_sizes=None; self.thumbs.max_button.set_kind("expand",self.t["max"]); self.image.max_button.set_kind("expand",self.t["max"])
    def toggle_lang(self): self.settings["language"]="en" if self.lang=="zh" else "zh"; self.lang=self.settings["language"]; self.t=TEXT[self.lang]; self.build(); self.open_folder(self.folder) if self.folder else None
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self,e):
        path=Path(e.mimeData().urls()[0].toLocalFile()); self.open_folder(path if path.is_dir() else path.parent,path if path.is_file() else None)
    def restore(self):
        f=Path(self.settings["folder"]) if self.settings.get("folder") else None
        if f and f.is_dir(): self.open_folder(f,Path(self.settings.get("selected_file","")))
        QTimer.singleShot(0,lambda:self.split.setSizes([max(100,int(self.height()*float(self.settings.get("sash_fraction",.45)))),max(100,int(self.height()*(1-float(self.settings.get("sash_fraction",.45)))))]))
    def closeEvent(self,e):
        sizes=self.split.sizes(); fraction=sizes[0]/sum(sizes) if len(sizes)==2 and sum(sizes) else .45; save_settings({"folder":str(self.folder) if self.folder else "","selected_file":str(self.thumbs.selected_path) if getattr(self.thumbs,"selected_path",None) else "","orientation":"vertical" if self.split.orientation()==Qt.Orientation.Vertical else "horizontal","sash_fraction":fraction,"maximized_pane":"","thumbnail_size":self.thumbs.size,"image_zoom":self.image.zoom,"language":self.lang}); e.accept()


def main():
    app=QApplication(sys.argv); app.setApplicationName("PicView"); use_system_palette(app); w=PicView(); app.paletteChanged.connect(w.refresh_system_theme); icon=Path(__file__).parent/"assets"/"picview-icon.png"; w.setWindowIcon(QIcon(str(icon))); w.show(); sys.exit(app.exec())
