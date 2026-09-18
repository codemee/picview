from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable
import customtkinter as ctk

from PIL import Image, ImageOps, ImageTk
from .ui import IconButton


class ThumbnailPane(ctk.CTkFrame):
    """Scrollable thumbnail browser for one flat folder."""

    def __init__(self, parent: tk.Misc, on_select: Callable[[Path], None], labels: dict[str, str], on_toggle_maximize, size: int = 140) -> None:
        super().__init__(parent, corner_radius=12, fg_color=("#f8fafc", "#1b2630"))
        self.on_select = on_select
        self.files: list[Path] = []
        self.selected: Path | None = None
        self.thumbnail_size = size
        self.labels = labels
        self._images: list[ctk.CTkImage] = []
        self._buttons: dict[Path, ctk.CTkButton] = {}

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x")
        ctk.CTkLabel(controls, text=labels["thumbnails"], font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=10, pady=8)
        self.max_button = IconButton(controls, "expand", labels["maximize"], lambda: on_toggle_maximize("thumbnails"))
        self.max_button.pack(side="left", padx=(4, 0))
        self.size_var = tk.IntVar(value=size)
        ctk.CTkSlider(controls, from_=72, to=260, variable=self.size_var, command=self._resize, width=135).pack(
            side="right", fill="x", expand=True, padx=(8, 0)
        )

        self.canvas = tk.Canvas(self, highlightthickness=0, background="#1b2630")
        scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview, width=12)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.content = ctk.CTkFrame(self.canvas, fg_color="transparent")
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._resize_canvas)
        self.canvas.bind("<Enter>", lambda _event: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _event: self.canvas.unbind_all("<MouseWheel>"))

    def set_files(self, files: list[Path], selected: Path | None = None) -> None:
        self.files = files
        self.selected = selected if selected in files else (files[0] if files else None)
        self._build()
        if self.selected:
            self.on_select(self.selected)

    def select(self, path: Path, notify: bool = True) -> None:
        if path not in self.files:
            return
        self.selected = path
        for item, button in self._buttons.items():
            button.configure(fg_color=("#b8e3e8", "#176f7a") if item == path else ("#e7eef2", "#25333e"))
        if notify:
            self.on_select(path)

    def _resize(self, _value: str) -> None:
        new_size = self.size_var.get()
        if new_size != self.thumbnail_size:
            self.thumbnail_size = new_size
            self._build()

    def _build(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self._images.clear()
        self._buttons.clear()
        columns = max(1, self.canvas.winfo_width() // (self.thumbnail_size + 20))
        for index, path in enumerate(self.files):
            row, column = divmod(index, columns)
            button = self._make_button(path)
            button.grid(row=row, column=column, padx=4, pady=4, sticky="n")
            self._buttons[path] = button
        for column in range(columns):
            self.content.columnconfigure(column, weight=1)

    def _make_button(self, path: Path) -> ctk.CTkButton:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image.thumbnail((self.thumbnail_size, self.thumbnail_size), Image.Resampling.LANCZOS)
                photo = ctk.CTkImage(light_image=image.copy(), dark_image=image.copy(), size=image.size)
            self._images.append(photo)
            button = ctk.CTkButton(self.content, image=photo, text=path.name, compound="top", width=self.thumbnail_size + 12, height=self.thumbnail_size + 38, corner_radius=9, fg_color=("#e7eef2", "#25333e"), hover_color=("#d1e5e9", "#35515c"), text_color=("#18313a", "#e5f0f2"), command=lambda p=path: self.select(p))
        except (OSError, ValueError):
            button = ctk.CTkButton(self.content, text=path.name, command=lambda p=path: self.select(p))
        if path == self.selected:
            button.configure(fg_color=("#b8e3e8", "#176f7a"))
        return button

    def _update_scrollregion(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.content_window, width=event.width)
        self.after_idle(self._build)

    def _wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def set_maximized(self, maximized: bool) -> None:
        self.max_button.set_icon("shrink" if maximized else "expand", self.labels["restore"] if maximized else self.labels["maximize"])
