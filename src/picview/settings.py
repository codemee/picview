from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "folder": "",
    "selected_file": "",
    "orientation": "vertical",
    "sash_fraction": 0.45,
    "maximized_pane": "",
    "thumbnail_size": 140,
    "image_zoom": 1.0,
    "language": "system",
}


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return base / "PicView" / "settings.json"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != DEFAULT_SETTINGS["version"]:
            return DEFAULT_SETTINGS.copy()
        return DEFAULT_SETTINGS | {key: value for key, value in data.items() if key in DEFAULT_SETTINGS}
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
