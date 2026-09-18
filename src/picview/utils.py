from __future__ import annotations

import re
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def image_files(folder: Path) -> list[Path]:
    try:
        return sorted((item for item in folder.iterdir() if is_image_file(item)), key=natural_key)
    except OSError:
        return []


def fit_size(image_size: tuple[int, int], available: tuple[int, int], zoom: float = 1.0) -> tuple[int, int]:
    """Return the largest aspect-preserving size contained in available."""
    width, height = image_size
    available_width, available_height = available
    if width <= 0 or height <= 0 or available_width <= 0 or available_height <= 0:
        return (1, 1)
    scale = min(available_width / width, available_height / height) * zoom
    return (max(1, round(width * scale)), max(1, round(height * scale)))
