from __future__ import annotations

import tkinter as tk
from tkinter import ttk


TEXT = {
    "en": {"open": "Open folder", "vertical": "Top / bottom", "horizontal": "Left / right", "language": "中文", "thumbnails": "Thumbnails", "maximize": "Maximize pane", "restore": "Restore panes", "rotate": "Rotate clockwise", "flip_h": "Mirror horizontally", "flip_v": "Mirror vertically", "fullscreen": "Full screen", "zoom": "Zoom", "empty": "Open a folder to view images", "exit_full": "Exit full screen (Esc)"},
    "zh": {"open": "開啟資料夾", "vertical": "上下窗格", "horizontal": "左右窗格", "language": "English", "thumbnails": "縮圖", "maximize": "最大化窗格", "restore": "還原窗格", "rotate": "順時針旋轉", "flip_h": "水平鏡射", "flip_v": "垂直鏡射", "fullscreen": "全螢幕", "zoom": "縮放", "empty": "開啟資料夾以檢視圖片", "exit_full": "離開全螢幕 (Esc)"},
}


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add=True)
        widget.bind("<Leave>", self.hide, add=True)

    def show(self, _event: tk.Event | None = None) -> None:
        if self.tip or not self.text:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        x, y = self.widget.winfo_rootx() + 4, self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.tip, text=self.text, padding=(7, 3), style="Tooltip.TLabel").pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.tip:
            self.tip.destroy()
        self.tip = None


def configure_flat_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#edf3f5")
    style.configure("Flat.Horizontal.TScale", background="#edf3f5", troughcolor="#c7dadd", sliderlength=18, borderwidth=0)
    style.map("Flat.Horizontal.TScale", background=[("active", "#147d8a")])
    style.configure("Tooltip.TLabel", background="#20252b", foreground="white")


class IconButton(tk.Canvas):
    """Small rounded flat button with a deliberately familiar, drawn icon."""
    def __init__(self, parent: tk.Misc, icon: str, tooltip: str, command, width: int = 36, height: int = 36) -> None:
        super().__init__(parent, width=width, height=height, highlightthickness=0, background="#eaf1f4", cursor="hand2")
        self.icon, self.command, self.width, self.height = icon, command, width, height
        self.hover = False
        self.bind("<Enter>", self._enter); self.bind("<Leave>", self._leave); self.bind("<Button-1>", self._click)
        ToolTip(self, tooltip)
        self.draw()

    def set_icon(self, icon: str, tooltip: str) -> None:
        self.icon = icon
        ToolTip(self, tooltip)
        self.draw()

    def _rounded_box(self, color: str) -> None:
        r, w, h = 8, self.width - 2, self.height - 2
        self.create_rectangle(r, 1, w-r, h, fill=color, outline="")
        self.create_rectangle(1, r, w, h-r, fill=color, outline="")
        for x, y in ((r, r), (w-r, r), (r, h-r), (w-r, h-r)):
            self.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="")

    def draw(self) -> None:
        self.delete("all")
        self._rounded_box("#d8eef0" if self.hover else "#f8fbfc")
        # Every glyph is constrained to the same centred 18×18 icon grid.
        c, w, h = "#176f7a", self.width, self.height
        left, top, right, bottom = 9, 9, 27, 27
        cx, cy = 18, 18
        if self.icon == "folder":
            self.create_polygon(9,14,14,14,16,11,23,11,27,14,27,24,9,24, fill="", outline=c, width=2)
        elif self.icon in {"split_v", "split_h"}:
            self.create_rectangle(9,11,27,25, outline=c, width=2)
            if self.icon == "split_v": self.create_line(cx,12,cx,24, fill=c, width=2)
            else: self.create_line(10,cy,26,cy, fill=c, width=2)
        elif self.icon == "mirror_h":
            self.create_polygon(9,25,15,12,15,25, fill=c)
            self.create_line(cx,9,cx,27, fill=c, dash=(2,2))
            self.create_polygon(27,25,21,12,21,25, fill=c)
        elif self.icon == "mirror_v":
            self.create_polygon(12,9,25,15,12,15, fill=c)
            self.create_line(9,cy,27,cy, fill=c, dash=(2,2))
            self.create_polygon(12,27,25,21,12,21, fill=c)
        elif self.icon == "rotate":
            self.create_arc(left,top,right,bottom, start=38, extent=285, style="arc", outline=c, width=2)
            self.create_polygon(26,9,27,15,21,12, fill=c)
        elif self.icon in {"expand", "shrink"}:
            # Pane maximize: box plus diagonal, outward/inward-facing arrows.
            self.create_rectangle(left,top,right,bottom, outline=c, width=1)
            if self.icon == "expand":
                self.create_line(15,15,10,10, fill=c, width=2); self.create_line(10,10,10,14, fill=c, width=2); self.create_line(10,10,14,10, fill=c, width=2)
                self.create_line(21,21,26,26, fill=c, width=2); self.create_line(26,26,22,26, fill=c, width=2); self.create_line(26,26,26,22, fill=c, width=2)
            else:
                self.create_line(10,10,15,15, fill=c, width=2); self.create_line(15,15,15,11, fill=c, width=2); self.create_line(15,15,11,15, fill=c, width=2)
                self.create_line(26,26,21,21, fill=c, width=2); self.create_line(21,21,21,25, fill=c, width=2); self.create_line(21,21,25,21, fill=c, width=2)
        elif self.icon == "fullscreen":
            # Screen mode: only the four outward corners, deliberately no box.
            for x, y, dx, dy in ((9,9,1,1),(27,9,-1,1),(9,27,1,-1),(27,27,-1,-1)):
                self.create_line(x,y,x + 6*dx,y,fill=c,width=2)
                self.create_line(x,y,x,y + 6*dy,fill=c,width=2)
        else:
            self.create_text(cx,cy,text=self.icon, fill=c, font=("Segoe UI",10,"bold"), anchor="center")

    def _enter(self, _event) -> None: self.hover = True; self.draw()
    def _leave(self, _event) -> None: self.hover = False; self.draw()
    def _click(self, _event) -> None: self.command()
