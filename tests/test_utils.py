from pathlib import Path

from picview.utils import fit_size, natural_key


def test_natural_key_orders_numeric_names() -> None:
    files = [Path("img10.png"), Path("img2.png"), Path("IMG1.png")]
    assert [item.name for item in sorted(files, key=natural_key)] == ["IMG1.png", "img2.png", "img10.png"]


def test_fit_size_preserves_aspect_and_zoom() -> None:
    assert fit_size((400, 200), (100, 100)) == (100, 50)
    assert fit_size((400, 200), (100, 100), 2) == (200, 100)


def test_fit_size_handles_invalid_space() -> None:
    assert fit_size((10, 10), (0, 100)) == (1, 1)
