from __future__ import annotations

import tkinter as tk
from pathlib import Path
import customtkinter as ctk

from PIL import Image, ImageOps, ImageTk

from .utils import fit_size
from .ui import IconButton


class ImagePane(ctk.CTkFrame):
    """Image display with non-destructive view transforms and GIF playback."""

    def __init__(self, parent: tk.Misc, labels: dict[str, str], on_toggle_maximize, zoom: float = 1.0) -> None:
        super().__init__(parent, corner_radius=12, fg_color=("#f8fafc", "#1b2630"))
        self.path: Path | None = None
        self.source: Image.Image | None = None
        self.frames: list[Image.Image] = []
        self.frame_delays: list[int] = []
        self.frame_index = 0
        self.animation_id: str | None = None
        self.rotation = 0
        self.flip_horizontal = False
        self.flip_vertical = False
        self.photo: ImageTk.PhotoImage | None = None
        self.zoom_var = tk.DoubleVar(value=zoom)
        self.fullscreen: tk.Toplevel | None = None
        self.fullscreen_label: ttk.Label | None = None
        self.labels, self.on_toggle_maximize = labels, on_toggle_maximize

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x")
        self._icon_button(controls, "rotate", labels["rotate"], self.rotate).pack(side="left")
        self._icon_button(controls, "mirror_h", labels["flip_h"], self.mirror_horizontal).pack(side="left", padx=2)
        self._icon_button(controls, "mirror_v", labels["flip_v"], self.mirror_vertical).pack(side="left")
        self.max_button = self._icon_button(controls, "expand", labels["maximize"], lambda: on_toggle_maximize("image"))
        self.max_button.pack(side="right", padx=(2, 0))
        self._icon_button(controls, "fullscreen", labels["fullscreen"], self.open_fullscreen).pack(side="right")
        ctk.CTkLabel(controls, text=labels["zoom"]).pack(side="right", padx=(0, 4))
        self.zoom_scale = ctk.CTkSlider(controls, from_=0.1, to=4.0, variable=self.zoom_var, command=lambda _v: self.render(), width=160)
        self.zoom_scale.pack(side="right", fill="x", expand=True, padx=(8, 8))

        view = ctk.CTkFrame(self, fg_color="transparent")
        view.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(view, background="#202020", highlightthickness=0)
        self.xscroll = ctk.CTkScrollbar(view, orientation="horizontal", command=self.canvas.xview, height=12)
        self.yscroll = ctk.CTkScrollbar(view, orientation="vertical", command=self.canvas.yview, width=12)
        self.canvas.configure(xscrollcommand=self.xscroll.set, yscrollcommand=self.yscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.yscroll.grid(row=0, column=1, sticky="ns")
        self.xscroll.grid(row=1, column=0, sticky="ew")
        view.rowconfigure(0, weight=1); view.columnconfigure(0, weight=1)
        self.image_item = self.canvas.create_image(0, 0, anchor="center")
        self.empty_item = self.canvas.create_text(0, 0, fill="#d0d0d0", text=labels["empty"])
        self.canvas.bind("<Configure>", lambda _event: self.render())
        self.canvas.bind("<Enter>", self._bind_zoom_shortcuts)
        self.canvas.bind("<Leave>", self._unbind_zoom_shortcuts)
        self.canvas.bind("<MouseWheel>", self._wheel_scroll)

    def load(self, path: Path) -> None:
        self._stop_animation()
        self.path = path
        self.rotation = 0
        self.flip_horizontal = False
        self.flip_vertical = False
        self.frame_index = 0
        self.frames = []
        self.frame_delays = []
        try:
            with Image.open(path) as opened:
                frame_count = getattr(opened, "n_frames", 1)
                for index in range(frame_count):
                    opened.seek(index)
                    self.frames.append(ImageOps.exif_transpose(opened).convert("RGBA").copy())
                    self.frame_delays.append(max(20, int(opened.info.get("duration", 100))))
            self.source = self.frames[0]
        except (OSError, ValueError):
            self.source = None
        self.render()
        if len(self.frames) > 1:
            self._animate()

    def load_empty(self) -> None:
        self._stop_animation()
        self.path = None
        self.source = None
        self.frames = []
        self.render()

    def rotate(self) -> None:
        self.rotation = (self.rotation + 90) % 360
        self.render()

    def mirror_horizontal(self) -> None:
        self.flip_horizontal = not self.flip_horizontal
        self.render()

    def mirror_vertical(self) -> None:
        self.flip_vertical = not self.flip_vertical
        self.render()

    def reset_fit(self, _event: tk.Event | None = None) -> str | None:
        self.zoom_var.set(1.0)
        self.render()
        return "break" if _event else None

    def adjust_zoom(self, amount: float) -> None:
        self.zoom_var.set(min(4.0, max(0.1, self.zoom_var.get() + amount)))
        self.render()

    def render(self) -> None:
        if not self.source:
            self.canvas.itemconfigure(self.empty_item, state="normal")
            self.canvas.coords(self.empty_item, self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
            return
        self.canvas.itemconfigure(self.empty_item, state="hidden")
        frame = self._transformed_frame()
        size = fit_size(frame.size, (self.canvas.winfo_width() - 8, self.canvas.winfo_height() - 8), self.zoom_var.get())
        image = frame.resize(size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.itemconfigure(self.image_item, image=self.photo)
        width, height = size
        viewport_w, viewport_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        scroll_w, scroll_h = max(viewport_w, width), max(viewport_h, height)
        self.canvas.configure(scrollregion=(0, 0, scroll_w, scroll_h))
        self.canvas.coords(self.image_item, scroll_w / 2, scroll_h / 2)
        self._render_fullscreen(frame)

    def open_fullscreen(self) -> None:
        if self.fullscreen is not None or self.source is None:
            return
        window = tk.Toplevel(self)
        window.attributes("-fullscreen", True)
        window.configure(background="#101010")
        window.bind("<Escape>", lambda _event: self.close_fullscreen())
        window.protocol("WM_DELETE_WINDOW", self.close_fullscreen)
        window.bind("<Configure>", lambda _event: self.render())
        label = ctk.CTkLabel(window, text="", anchor="center")
        label.pack(fill="both", expand=True)
        ctk.CTkButton(window, text=self.labels["exit_full"], command=self.close_fullscreen, corner_radius=10).place(relx=0.5, rely=0.97, anchor="s")
        self.fullscreen = window
        self.fullscreen_label = label
        self.render()

    def close_fullscreen(self) -> None:
        if self.fullscreen:
            self.fullscreen.destroy()
        self.fullscreen = None
        self.fullscreen_label = None

    def _render_fullscreen(self, frame: Image.Image) -> None:
        if not self.fullscreen or not self.fullscreen_label or not self.fullscreen.winfo_exists():
            return
        size = fit_size(frame.size, (self.fullscreen.winfo_width() - 20, self.fullscreen.winfo_height() - 50), self.zoom_var.get())
        photo = ImageTk.PhotoImage(frame.resize(size, Image.Resampling.LANCZOS))
        self.fullscreen_label.configure(image=photo)
        self.fullscreen_label.image = photo

    def _transformed_frame(self) -> Image.Image:
        frame = self.frames[self.frame_index] if self.frames else self.source
        assert frame is not None
        if self.rotation:
            frame = frame.rotate(-self.rotation, expand=True)
        if self.flip_horizontal:
            frame = ImageOps.mirror(frame)
        if self.flip_vertical:
            frame = ImageOps.flip(frame)
        return frame

    def _animate(self) -> None:
        if not self.winfo_exists() or len(self.frames) < 2:
            return
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.render()
        self.animation_id = self.after(self.frame_delays[self.frame_index], self._animate)

    def _stop_animation(self) -> None:
        if self.animation_id:
            self.after_cancel(self.animation_id)
        self.animation_id = None

    def _bind_zoom_shortcuts(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<Control-MouseWheel>", self._wheel_zoom)
        self.canvas.bind_all("<plus>", lambda _e: self._key_zoom(0.1))
        self.canvas.bind_all("<minus>", lambda _e: self._key_zoom(-0.1))
        self.canvas.bind_all("<Key-0>", self.reset_fit)

    def _unbind_zoom_shortcuts(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<Control-MouseWheel>")
        self.canvas.unbind_all("<plus>")
        self.canvas.unbind_all("<minus>")
        self.canvas.unbind_all("<Key-0>")

    def _wheel_zoom(self, event: tk.Event) -> str:
        self.adjust_zoom(0.1 if event.delta > 0 else -0.1)
        return "break"

    def _wheel_scroll(self, event: tk.Event) -> str:
        """Plain wheel pans an enlarged image; Ctrl+wheel remains zoom."""
        if event.state & 0x0004:
            return self._wheel_zoom(event)
        self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _key_zoom(self, amount: float) -> str:
        self.adjust_zoom(amount)
        return "break"

    def _icon_button(self, parent: tk.Misc, icon: str, tooltip: str, command) -> IconButton:
        return IconButton(parent, icon, tooltip, command)

    def set_maximized(self, maximized: bool) -> None:
        self.max_button.set_icon("shrink" if maximized else "expand", self.labels["restore"] if maximized else self.labels["maximize"])
