from __future__ import annotations

import tkinter as tk
import locale
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # Allows unit-level imports if optional UI dependency is absent.
    DND_FILES = "DND_Files"
    TkinterDnD = None

from .image_pane import ImagePane
from .settings import load_settings, save_settings
from .thumbnail_pane import ThumbnailPane
from .utils import image_files
from .ui import TEXT, IconButton, configure_flat_style


class PicViewApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = load_settings()
        self.folder: Path | None = None
        self.files: list[Path] = []
        self.orientation = self.settings["orientation"]
        # A maximized pane is a transient viewing mode. Restoring it before a
        # ttk PanedWindow has completed geometry produces an orphaned sash and
        # hides the other pane, so startup always restores the normal layout.
        self.maximized_pane = ""
        self.sash_fraction = float(self.settings["sash_fraction"])
        self.language_mode = self.settings["language"]
        system_language = (locale.getlocale()[0] or "en").lower()
        self.language = "zh" if self.language_mode == "system" and system_language.startswith("zh") else (self.language_mode if self.language_mode in TEXT else "en")
        self.labels = TEXT[self.language]
        self._build_window()
        self._restore_state()

    def _build_window(self) -> None:
        self.root.title("PicView")
        self.root.minsize(720, 500)
        self.root.geometry("1100x780")
        configure_flat_style(self.root)
        icon_path = Path(__file__).parent / "assets" / "picview-icon.png"
        if icon_path.exists():
            self.icon_image = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self.icon_image)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self._on_drop)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        toolbar = ctk.CTkFrame(self.root, height=48, corner_radius=0, fg_color=("#eaf1f4", "#16232c"))
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        self._icon_button(toolbar, "folder", "open", self.choose_folder).pack(side="left")
        ctk.CTkFrame(toolbar, width=1, fg_color=("#c9d8dd", "#36505d")).pack(side="left", fill="y", pady=9, padx=8)
        self._icon_button(toolbar, "split_h", "vertical", lambda: self.set_orientation("vertical")).pack(side="left")
        self._icon_button(toolbar, "split_v", "horizontal", lambda: self.set_orientation("horizontal")).pack(side="left", padx=2)
        ctk.CTkFrame(toolbar, width=1, fg_color=("#c9d8dd", "#36505d")).pack(side="left", fill="y", pady=9, padx=8)
        self._icon_button(toolbar, "En" if self.language == "zh" else "文", "language", self.toggle_language).pack(side="left")

        self.pane_host = ctk.CTkFrame(self.root, corner_radius=0, fg_color=("#dce7eb", "#101820"))
        self.pane_host.pack(fill="both", expand=True, padx=8, pady=8)
        self._create_panes()

    def _create_panes(self) -> None:
        old_thumbnail_size = int(self.settings["thumbnail_size"])
        old_image_zoom = float(self.settings["image_zoom"])
        selected = None
        if hasattr(self, "thumbnails"):
            old_thumbnail_size = self.thumbnails.thumbnail_size
            old_image_zoom = self.image.zoom_var.get()
            selected = self.thumbnails.selected
            self.paned.destroy()
        orient = tk.VERTICAL if self.orientation == "vertical" else tk.HORIZONTAL
        self.paned = ttk.Panedwindow(self.pane_host, orient=orient)
        self.paned.pack(fill="both", expand=True)
        self.thumbnails = ThumbnailPane(self.paned, self.select_image, self.labels, self.toggle_maximize, old_thumbnail_size)
        self.image = ImagePane(self.paned, self.labels, self.toggle_maximize, old_image_zoom)
        self.paned.add(self.thumbnails, weight=1)
        self.paned.add(self.image, weight=2)
        self.thumbnails.set_files(self.files, selected)
        if self.maximized_pane:
            self.root.after_idle(lambda: self._apply_maximized(self.maximized_pane))
        else:
            self.root.after_idle(self._restore_sash)

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self.root, title="Open image folder", initialdir=str(self.folder) if self.folder else None)
        if chosen:
            self.open_folder(Path(chosen))

    def open_folder(self, folder: Path, selected: Path | None = None) -> None:
        try:
            folder = folder.resolve()
            if not folder.is_dir():
                raise OSError
        except OSError:
            messagebox.showerror("PicView", "That folder cannot be opened.", parent=self.root)
            return
        self.folder = folder
        self.files = image_files(folder)
        self._create_panes()
        target = selected if selected in self.files else (self.files[0] if self.files else None)
        if target:
            self.thumbnails.select(target)
        else:
            self.image.load_empty()
        self._update_title()

    def select_image(self, path: Path) -> None:
        self.image.load(path)

    def current_selection(self) -> Path | None:
        return getattr(self, "thumbnails", None).selected if hasattr(self, "thumbnails") else None

    def set_orientation(self, orientation: str) -> None:
        if orientation == self.orientation:
            return
        # Layout switches are always two-pane layouts; do not route through
        # the maximize restore path, which can leave a stale sash in ttk.
        self.sash_fraction = self._current_sash_fraction()
        self.maximized_pane = ""
        self.orientation = orientation
        self._create_panes()
        self.root.after(40, self._ensure_two_panes)

    def _ensure_two_panes(self) -> None:
        """Repair a deferred ttk PanedWindow layout after orientation changes."""
        if self.maximized_pane:
            return
        current = set(self.paned.panes())
        wanted = {str(self.thumbnails), str(self.image)}
        if current != wanted:
            for pane in current:
                self.paned.forget(pane)
            self.paned.add(self.thumbnails, weight=1)
            self.paned.add(self.image, weight=2)
        self.thumbnails.set_maximized(False)
        self.image.set_maximized(False)
        self._restore_sash()

    def toggle_maximize(self, pane: str) -> None:
        if pane == self.maximized_pane or not pane:
            self.maximized_pane = ""
            self._apply_maximized("")
        else:
            if self.maximized_pane:
                self.maximized_pane = ""
                self._apply_maximized("")
            self.sash_fraction = self._current_sash_fraction()
            self.maximized_pane = pane
            self._apply_maximized(pane)

    def _apply_maximized(self, pane: str) -> None:
        panes = list(self.paned.panes())
        target = str(self.thumbnails if pane == "thumbnails" else self.image)
        if pane:
            for item in panes:
                if item != target:
                    self.paned.forget(item)
            self.thumbnails.set_maximized(pane == "thumbnails")
            self.image.set_maximized(pane == "image")
        else:
            for item in panes:
                self.paned.forget(item)
            self.paned.add(self.thumbnails, weight=1)
            self.paned.add(self.image, weight=2)
            self.thumbnails.set_maximized(False)
            self.image.set_maximized(False)
            self.root.after(20, self._restore_sash)

    def _restore_sash(self, attempts: int = 0) -> None:
        if not self.paned.panes() or self.maximized_pane:
            return
        try:
            dimension = self.paned.winfo_height() if self.orientation == "vertical" else self.paned.winfo_width()
            # `after_idle` can run before the PanedWindow receives its final
            # geometry (dimension == 1). Setting sashpos then collapses the
            # first pane to zero, which looks like a false maximized image.
            if dimension <= 1 and attempts < 10:
                self.root.after(50, lambda: self._restore_sash(attempts + 1))
                return
            if dimension <= 1:
                return
            self.paned.sashpos(0, int(dimension * self.sash_fraction))
        except tk.TclError:
            pass

    def _on_drop(self, event: tk.Event) -> str:
        items = self.root.tk.splitlist(event.data)
        if not items:
            return "break"
        path = Path(items[0])
        if path.is_dir():
            self.open_folder(path)
        elif path.is_file():
            self.open_folder(path.parent, path)
        return "break"

    def _restore_state(self) -> None:
        folder = Path(self.settings["folder"]) if self.settings["folder"] else None
        if folder and folder.is_dir():
            saved = Path(self.settings["selected_file"])
            self.open_folder(folder, saved if saved.is_file() else None)

    def _update_title(self) -> None:
        self.root.title(f"PicView — {self.folder}" if self.folder else "PicView")

    def close(self) -> None:
        sash_fraction = self._current_sash_fraction()
        selected = self.current_selection()
        save_settings({
            "folder": str(self.folder) if self.folder else "",
            "selected_file": str(selected) if selected else "",
            "orientation": self.orientation,
            "sash_fraction": sash_fraction,
            "maximized_pane": "",
            "thumbnail_size": self.thumbnails.thumbnail_size,
            "image_zoom": self.image.zoom_var.get(),
            "language": self.language_mode,
        })
        self.image.close_fullscreen()
        self.root.destroy()

    def _current_sash_fraction(self) -> float:
        if self.maximized_pane or not self.paned.panes():
            return self.sash_fraction
        try:
            dimension = self.paned.winfo_height() if self.orientation == "vertical" else self.paned.winfo_width()
            return self.paned.sashpos(0) / dimension if dimension else self.sash_fraction
        except tk.TclError:
            return self.sash_fraction

    def toggle_language(self) -> None:
        selected = self.current_selection()
        thumbnail_size = self.thumbnails.thumbnail_size
        image_zoom = self.image.zoom_var.get()
        self.language_mode = "en" if self.language == "zh" else "zh"
        self.language = self.language_mode
        self.labels = TEXT[self.language]
        self.settings["thumbnail_size"] = thumbnail_size
        self.settings["image_zoom"] = image_zoom
        for child in self.root.winfo_children():
            child.destroy()
        del self.thumbnails, self.image, self.paned, self.pane_host
        self._build_window()
        if selected:
            self.thumbnails.select(selected)

    def _icon_button(self, parent: tk.Misc, icon: str, label_key: str, command) -> ttk.Button:
        return IconButton(parent, icon, self.labels[label_key], command)


def main() -> None:
    if TkinterDnD is None:
        raise RuntimeError("tkinterdnd2 is required. Run `uv sync` before launching PicView.")
    root = TkinterDnD.Tk()
    PicViewApp(root)
    root.mainloop()
