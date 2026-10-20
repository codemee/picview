from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

IMAGE_BACKGROUND_COLORS = {
    "default": None, "white": "#ffffff", "black": "#000000",
    "gray": "#808080", "light_gray": "#d9d9d9", "cream": "#fff1d6",
    "blue": "#dceeff", "green": "#e3f4df", "pink": "#ffe4e8",
    "dark_gray": "#30343b", "slate": "#465568", "dark_blue": "#14243b", "dark_green": "#18362b",
    "dark_purple": "#30223d", "dark_red": "#45232c", "dark_brown": "#3d3026", "dark_teal": "#0f3440",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "folder": "",
    "selected_file": "",
    "orientation": "vertical",
    "sash_fraction": 0.45,
    "maximized_pane": "",
    "thumbnail_size": 140,
    "image_zoom": 1.0,
    "image_background": "default",
    "language": "system",
    "theme": "system",
    "tabs": [],
    "active_tab": 0,
}


def normalize_tab_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("folder"), str) or not value["folder"]:
        return None
    state = {key: value.get(key, default) for key, default in DEFAULT_SETTINGS.items()
             if key in ("folder", "selected_file", "orientation", "sash_fraction", "thumbnail_size", "image_zoom")}
    if not isinstance(state["selected_file"], str): state["selected_file"] = ""
    if state["orientation"] not in ("vertical", "horizontal"): state["orientation"] = "vertical"
    for key, minimum, maximum, default in (("sash_fraction", .05, .95, .45), ("thumbnail_size", 72, 260, 140), ("image_zoom", .001, 4, 1.0)):
        item = state[key]
        state[key] = min(maximum, max(minimum, item)) if isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) else default
    state["thumbnail_size"] = int(state["thumbnail_size"])
    state["rotation"] = value.get("rotation", 0) if value.get("rotation", 0) in (0, 90, 180, 270) else 0
    for key in ("fh", "fv"):
        state[key] = value.get(key) is True
    state["fit_to_pane"] = value.get("fit_to_pane") if isinstance(value.get("fit_to_pane"), bool) else None
    background = value.get("image_background", "default")
    state["image_background"] = background if isinstance(background, str) and background in IMAGE_BACKGROUND_COLORS else "default"
    for key in ("thumbnail_scroll", "image_scroll_x", "image_scroll_y"):
        item = value.get(key, 0)
        state[key] = max(0, item) if isinstance(item, int) and not isinstance(item, bool) else 0
    return state


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return base / "PicView" / "settings.json"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != DEFAULT_SETTINGS["version"]:
            return DEFAULT_SETTINGS.copy()
        settings = DEFAULT_SETTINGS | {key: value for key, value in data.items() if key in DEFAULT_SETTINGS}
        tabs = settings["tabs"]
        settings["tabs"] = [state for item in tabs if (state := normalize_tab_state(item)) is not None] if isinstance(tabs, list) else []
        active = settings["active_tab"]
        settings["active_tab"] = min(max(0, active), max(0, len(settings["tabs"]) - 1)) if isinstance(active, int) and not isinstance(active, bool) else 0
        return settings
    except (OSError, ValueError, TypeError):
        return DEFAULT_SETTINGS.copy()


def save_settings(values: dict[str, Any], path: Path | None = None) -> None:
    path = path or settings_path()
    data = DEFAULT_SETTINGS | {key: value for key, value in values.items() if key in DEFAULT_SETTINGS}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
