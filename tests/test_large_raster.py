import io

import pytest
from PIL import Image

from picview import raster
from picview.editing import transform_image


def jpeg_header(width, height):
    """Exercise real JPEG header checks without allocating a giant bitmap."""
    buffer = io.BytesIO()
    Image.new("L", (8, 8), 127).save(buffer, format="JPEG")
    data = bytearray(buffer.getvalue())
    marker = data.index(b"\xff\xc0")
    data[marker + 5:marker + 9] = height.to_bytes(2, "big") + width.to_bytes(2, "big")
    return io.BytesIO(data)


def test_print_sheet_header_is_accepted_but_pixel_limit_remains():
    with Image.open(jpeg_header(18248, 13996)) as source:
        assert source.size == (18248, 13996)
    with pytest.warns(Image.DecompressionBombWarning):
        with Image.open(jpeg_header(20000, 15000)) as source:
            assert source.size == (20000, 15000)
    with pytest.raises(Image.DecompressionBombError):
        Image.open(jpeg_header(30000, 30000))


@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA"])
def test_large_frames_remain_detached_and_preserve_pixels(monkeypatch, mode):
    monkeypatch.setattr(raster, "LARGE_IMAGE_PIXELS", 10)
    source = Image.new(mode, (12, 8), 127)
    source.getexif()[274] = 6
    expected = source.rotate(-90, expand=True)
    frame = raster.decoded_frame(source)
    source.close()
    assert frame.mode == mode
    assert frame.size == (8, 12)
    assert frame.tobytes() == expected.tobytes()
    edited = transform_image(frame, 90, True, False, (1, 1, 7, 7))
    assert edited.size == (6, 6)
    output = io.BytesIO()
    edited.save(output, format="PNG")
    output.seek(0)
    with Image.open(output) as saved:
        assert saved.tobytes() == edited.tobytes()


def test_small_frames_keep_existing_rgba_behavior():
    frame = raster.decoded_frame(Image.new("L", (12, 8), 127))
    assert frame.mode == "RGBA"
    assert frame.getpixel((0, 0)) == (127, 127, 127, 255)
