"""Core pixelation engine.

Converts an arbitrary source image into retro pixel-art by:
  1. (optionally) removing a flat background and making it transparent,
  2. (optionally) trimming to the subject and padding to a square so it fills
     the frame edge-to-edge,
  3. downscaling to a small grid (e.g. 32x32),
  4. quantizing colors to a limited palette (adaptive or a fixed retro palette),
  5. upscaling back with NEAREST sampling so the pixels stay crisp.
"""
from __future__ import annotations

import io
from collections import deque
from typing import Optional

import numpy as np
from PIL import Image

from .palettes import NAMED_PALETTES, flatten

VALID_SIZES = (16, 32, 64, 128)
MIN_COLORS = 2
MAX_COLORS = 256
_WORK_MAX = 512  # cap working resolution for background/flood-fill cost


def _crop_to_square(img: Image.Image) -> Image.Image:
    """Center-crop the image to a square."""
    w, h = img.size
    if w == h:
        return img
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _fit_working(img: Image.Image) -> Image.Image:
    """Downscale (never upscale) so the longest side is at most _WORK_MAX."""
    w, h = img.size
    longest = max(w, h)
    if longest <= _WORK_MAX:
        return img
    scale = _WORK_MAX / longest
    return img.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)


def _remove_background(img_rgb: Image.Image, tolerance: int) -> Image.Image:
    """Flood-fill from the borders to make a flat background transparent.

    Detects the background color from the image border, then makes every pixel
    that is both (a) within `tolerance` of that color and (b) connected to the
    border transparent. Connectivity prevents punching holes in the subject when
    it happens to share a color with the background.
    """
    arr = np.asarray(img_rgb, dtype=np.int16)
    h, w = arr.shape[:2]

    border = np.concatenate(
        [arr[0, :], arr[-1, :], arr[:, 0], arr[:, -1]], axis=0
    )
    bg = np.median(border, axis=0)
    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    candidate = dist <= tolerance

    visited = np.zeros((h, w), dtype=bool)
    dq: deque[tuple[int, int]] = deque()

    def _seed(y: int, x: int) -> None:
        if candidate[y, x] and not visited[y, x]:
            visited[y, x] = True
            dq.append((y, x))

    for x in range(w):
        _seed(0, x)
        _seed(h - 1, x)
    for y in range(h):
        _seed(y, 0)
        _seed(y, w - 1)

    while dq:
        y, x = dq.popleft()
        if y > 0:
            _seed(y - 1, x)
        if y < h - 1:
            _seed(y + 1, x)
        if x > 0:
            _seed(y, x - 1)
        if x < w - 1:
            _seed(y, x + 1)

    alpha = np.where(visited, 0, 255).astype(np.uint8)
    rgba = np.dstack([np.asarray(img_rgb, dtype=np.uint8), alpha])
    return Image.fromarray(rgba, "RGBA")


def _trim_to_content(rgba: Image.Image) -> Image.Image:
    """Crop to the bounding box of non-transparent pixels."""
    alpha = np.asarray(rgba)[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if xs.size == 0:
        return rgba
    return rgba.crop(
        (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    )


def _pad_square(rgba: Image.Image) -> Image.Image:
    """Center the subject on a transparent square canvas (aspect preserved)."""
    w, h = rgba.size
    side = max(w, h)
    if w == h:
        return rgba
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(rgba, ((side - w) // 2, (side - h) // 2))
    return canvas


def _quantize(small: Image.Image, palette_name: str, colors: int) -> Image.Image:
    """Reduce the small image to a limited palette. Returns an RGB image."""
    if palette_name in NAMED_PALETTES:
        pal = NAMED_PALETTES[palette_name]
        pal_img = Image.new("P", (1, 1))
        flat = flatten(pal)
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


def _quantize_rgba(small: Image.Image, palette_name: str, colors: int) -> Image.Image:
    """Quantize the RGB channels while preserving a binary alpha mask."""
    alpha = small.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    quantized = _quantize(small.convert("RGB"), palette_name, colors).convert("RGBA")
    quantized.putalpha(alpha)
    return quantized


def pixelate(
    image_bytes: bytes,
    size: int = 32,
    palette: str = "adaptive",
    colors: int = 16,
    upscale_to: Optional[int] = 512,
    remove_bg: bool = False,
    fill: bool = False,
    bg_tolerance: int = 30,
    crop_square: bool = False,
) -> tuple[bytes, bytes]:
    """Pixelate an image.

    Args:
        image_bytes: raw source image bytes (any Pillow-readable format).
        size: target pixel grid (width/height), one of VALID_SIZES.
        palette: "adaptive" or a named palette key (e.g. "nes").
        colors: number of colors for the adaptive palette.
        upscale_to: final crisp PNG size in pixels; None to skip upscaling.
        remove_bg: detect a flat background and make it transparent.
        fill: trim to the subject and pad to a square so it fills the frame
            (uses the transparency mask; implies remove_bg).
        bg_tolerance: color distance threshold for background detection.
        crop_square: center-crop to a square (only used when not removing bg).

    Returns:
        (large_png_bytes, grid_png_bytes) where grid_png is the raw size x size art.
    """
    if size not in VALID_SIZES:
        raise ValueError(f"size must be one of {VALID_SIZES}, got {size}")

    src = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    use_alpha = remove_bg or fill
    if use_alpha:
        work = _fit_working(src)
        rgba = _remove_background(work, bg_tolerance)
        if fill:
            rgba = _trim_to_content(rgba)
            rgba = _pad_square(rgba)
        small = rgba.resize((size, size), Image.Resampling.LANCZOS)
        small = _quantize_rgba(small, palette, colors)
    else:
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
