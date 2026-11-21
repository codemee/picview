"""Write image edits at source resolution, replacing destinations atomically."""
import os
import base64
import io
import math
import time
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageOps
from PIL.ImageQt import fromqimage

from .svg import SvgDocument


FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP",
           ".bmp": "BMP", ".gif": "GIF", ".tif": "TIFF", ".tiff": "TIFF", ".svg": "SVG"}
SAVE_FILTERS = "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp);;BMP (*.bmp);;GIF (*.gif);;TIFF (*.tif *.tiff)"


def transform_image(source, rotation, horizontal, vertical, box):
    if isinstance(source, SvgDocument):
        rendered = source.render(source.size)
        if (rendered.width(), rendered.height()) != source.size:
            raise ValueError("SVG is too large to export as a bitmap at its original resolution")
        source = fromqimage(rendered).convert("RGBA")
    if rotation: source = source.rotate(-rotation, expand=True)
    if horizontal: source = ImageOps.mirror(source)
    if vertical: source = ImageOps.flip(source)
    return source.crop(box)


def mosaic_image(image, box):
    """Average the selected pixels into blocks without retaining hidden detail."""
    result = image.copy()
    region = result.crop(box)
    block = max(8, min(image.size) // 40)
    small = region.resize((max(1, math.ceil(region.width / block)), max(1, math.ceil(region.height / block))), Image.Resampling.BOX)
    result.paste(small.resize(region.size, Image.Resampling.NEAREST), box[:2])
    return result


def svg_bytes(source, rotation, horizontal, vertical, box):
    if not isinstance(source, SvgDocument):
        # A raster edit must not leave the unmodified vector content underneath.
        image = transform_image(source, rotation, horizontal, vertical, box)
        output = io.BytesIO()
        image.save(output, format="PNG")
        data = base64.b64encode(output.getvalue()).decode("ascii")
        width, height = image.size
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
                f'<image width="{width}" height="{height}" href="data:image/png;base64,{data}"/></svg>').encode("utf-8")
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    original = ET.fromstring(source.data)
    width, height = source.size
    view = source.renderer.viewBoxF()
    sx, sy = width / view.width(), height / view.height()
    aspect = original.attrib.get("preserveAspectRatio", "xMidYMid meet")
    offset_x = offset_y = 0
    if "none" not in aspect:
        scale = max(sx, sy) if "slice" in aspect else min(sx, sy)
        sx = sy = scale
        offset_x = (width - view.width() * scale) * (0 if "xMin" in aspect else 1 if "xMax" in aspect else .5)
        offset_y = (height - view.height() * scale) * (0 if "YMin" in aspect else 1 if "YMax" in aspect else .5)
    # Flatten the outer SVG viewport into a group; nested SVG viewports are not
    # rendered consistently by all viewers when their parent is transformed.
    original.tag = f"{{{namespace}}}g"
    for key in ("width", "height", "x", "y", "viewBox", "preserveAspectRatio"):
        original.attrib.pop(key, None)
    matrix = {0: (1, 0, 0, 1, 0, 0), 90: (0, 1, -1, 0, height, 0),
              180: (-1, 0, 0, -1, width, height), 270: (0, -1, 1, 0, 0, width)}[rotation]
    a, b, c, d, e, f = matrix
    if rotation % 180: width, height = height, width
    if horizontal: a, c, e = -a, -c, width - e
    if vertical: b, d, f = -b, -d, height - f
    left, top, right, bottom = box
    root = ET.Element(f"{{{namespace}}}svg", width=str(right - left), height=str(bottom - top),
                      viewBox=f"{left} {top} {right - left} {bottom - top}")
    group = ET.SubElement(root, f"{{{namespace}}}g", transform=f"matrix({a} {b} {c} {d} {e} {f})")
    viewport = ET.SubElement(group, f"{{{namespace}}}g",
        transform=f"translate({offset_x} {offset_y}) scale({sx} {sy}) translate({-view.x()} {-view.y()})")
    viewport.append(original)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_edits(destination, frames, index, rotation, horizontal, vertical, box, loop=0):
    destination = Path(destination)
    fmt = FORMATS.get(destination.suffix.lower())
    if fmt is None: raise ValueError(f"Unsupported image format: {destination.suffix}")
    fd, name = tempfile.mkstemp(prefix=".picview-", suffix=destination.suffix, dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        if fmt == "SVG":
            temporary.write_bytes(svg_bytes(frames[index][0], rotation, horizontal, vertical, box))
        else:
            animated = len(frames) > 1 and fmt in {"GIF", "WEBP", "TIFF", "PNG"}
            chosen = frames if animated else [frames[index]]
            images = [transform_image(source, rotation, horizontal, vertical, box) for source, _ in chosen]
            options = {}
            if fmt == "WEBP": options.update(lossless=True)
            if fmt == "JPEG":
                background = Image.new("RGB", images[0].size, "white")
                background.paste(images[0], mask=images[0].getchannel("A"))
                images = [background]
                options.update(quality=95, subsampling=0)
            if animated:
                options.update(save_all=True, append_images=images[1:])
                if fmt != "TIFF": options.update(duration=[delay for _, delay in chosen], loop=loop)
                if fmt == "GIF": options.update(disposal=2)
            images[0].save(temporary, format=fmt, **options)
        for attempt in range(6):
            try:
                os.replace(temporary, destination)
                break
            except PermissionError as error:
                # Windows thumbnail readers and scanners can briefly hold the
                # destination. Never remove it before a successful replacement.
                if attempt == 5 or getattr(error, "winerror", None) not in (5, 32, 33): raise
                time.sleep(.03 * 2 ** attempt)
    finally:
        temporary.unlink(missing_ok=True)
