"""Tests for the pixelation engine."""
import io

import pytest
from PIL import Image

from app.pixelate import VALID_SIZES, pixelate


def _make_image(w=200, h=200, color=(120, 60, 200)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    # add a second color block so quantization has something to do
    for x in range(w // 2):
        for y in range(h // 2):
            img.putpixel((x, y), (20, 200, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("size", VALID_SIZES)
def test_grid_dimensions(size):
    _, grid = pixelate(_make_image(), size=size, upscale_to=256)
    grid_img = Image.open(io.BytesIO(grid))
    assert grid_img.size == (size, size)


def test_upscale_dimensions():
    large, _ = pixelate(_make_image(), size=32, upscale_to=512)
    large_img = Image.open(io.BytesIO(large))
    assert large_img.size == (512, 512)


def test_invalid_size_raises():
    with pytest.raises(ValueError):
        pixelate(_make_image(), size=99)


def test_named_palette_limits_colors():
    _, grid = pixelate(_make_image(), size=32, palette="gameboy")
    grid_img = Image.open(io.BytesIO(grid)).convert("RGB")
    unique = {grid_img.getpixel((x, y)) for x in range(32) for y in range(32)}
    # Game Boy palette has 4 colors; result must not exceed that.
    assert len(unique) <= 4


def test_adaptive_color_count():
    _, grid = pixelate(_make_image(), size=64, palette="adaptive", colors=8)
    grid_img = Image.open(io.BytesIO(grid)).convert("RGB")
    unique = {grid_img.getpixel((x, y)) for x in range(64) for y in range(64)}
    assert len(unique) <= 8


def test_rejects_non_image_bytes():
    with pytest.raises(Exception):
        pixelate(b"not an image", size=32)
