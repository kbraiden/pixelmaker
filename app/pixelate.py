"""Core pixelation engine.

Converts an arbitrary source image into retro pixel-art by:
  1. (optionally) cropping to a square,
  2. downscaling to a small grid (e.g. 32x32),
  3. quantizing colors to a limited palette (adaptive or a fixed retro palette),
  4. upscaling back with NEAREST sampling so the pixels stay crisp.
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image

from .palettes import NAMED_PALETTES, flatten

VALID_SIZES = (16, 32, 64, 128)
MIN_COLORS = 2
MAX_COLORS = 256


def _crop_to_square(img: Image.Image) -> Image.Image:
    """Center-crop the image to a square."""
    w, h = img.size
    if w == h:
        return img
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _quantize(small: Image.Image, palette_name: str, colors: int) -> Image.Image:
    """Reduce the small image to a limited palette. Returns an RGB image."""
    if palette_name in NAMED_PALETTES:
        pal = NAMED_PALETTES[palette_name]
        pal_img = Image.new("P", (1, 1))
        flat = flatten(pal)
        # Pad palette to 256*3 entries as Pillow expects.
        flat = flat + [0] * (768 - len(flat))
        pal_img.putpalette(flat)
        quantized = small.convert("RGB").quantize(
            palette=pal_img, dither=Image.Dither.NONE
        )
    else:  # adaptive
        n = max(MIN_COLORS, min(MAX_COLORS, colors))
        quantized = small.convert("RGB").quantize(
            colors=n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
    return quantized.convert("RGB")


def pixelate(
    image_bytes: bytes,
    size: int = 32,
    palette: str = "adaptive",
    colors: int = 16,
    upscale_to: Optional[int] = 512,
    crop_square: bool = True,
) -> tuple[bytes, bytes]:
    """Pixelate an image.

    Args:
        image_bytes: raw source image bytes (any Pillow-readable format).
        size: target pixel grid (width/height), one of VALID_SIZES.
        palette: "adaptive" or a named palette key (e.g. "nes").
        colors: number of colors for the adaptive palette.
        upscale_to: final crisp PNG size in pixels; None to skip upscaling.
        crop_square: center-crop to a square before downscaling.

    Returns:
        (large_png_bytes, grid_png_bytes) where grid_png is the raw size x size art.
    """
    if size not in VALID_SIZES:
        raise ValueError(f"size must be one of {VALID_SIZES}, got {size}")

    src = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if crop_square:
        src = _crop_to_square(src)

    small = src.resize((size, size), Image.Resampling.LANCZOS)
    small = _quantize(small, palette, colors)

    grid_buf = io.BytesIO()
    small.save(grid_buf, format="PNG")

    if upscale_to:
        large = small.resize((upscale_to, upscale_to), Image.Resampling.NEAREST)
    else:
        large = small
    large_buf = io.BytesIO()
    large.save(large_buf, format="PNG")

    return large_buf.getvalue(), grid_buf.getvalue()
