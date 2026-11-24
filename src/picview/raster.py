"""Raster decoding policy for local, high-resolution image files."""
from PIL import Image, ImageOps


# Accommodate large print sheets while retaining Pillow's bounded pixel check:
# warn above 256 MP and reject above 512 MP, rather than disabling the limit.
Image.MAX_IMAGE_PIXELS = 256_000_000
LARGE_IMAGE_PIXELS = 89_478_485


def decoded_frame(source):
    """Detach a frame, keeping large grayscale images in their compact mode."""
    image = ImageOps.exif_transpose(source)
    if image.width * image.height > LARGE_IMAGE_PIXELS and image.mode in ("L", "RGB", "RGBA"):
        return image
    return image.convert("RGBA")
