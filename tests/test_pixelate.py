"""Tests for the pixelation engine."""
import io

import numpy as np
import pytest
from PIL import Image

from app.pixelate import VALID_SIZES, make_background, pixelate


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


def _portrait_subject(bg=(12, 12, 12)) -> bytes:
    """A flat-bg image with a tall (portrait) colored subject centered."""
    img = Image.new("RGB", (200, 200), bg)
    for x in range(80, 120):       # 40 wide
        for y in range(20, 180):   # 160 tall
            img.putpixel((x, y), (220, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_remove_bg_produces_transparency():
    _, grid = pixelate(_portrait_subject(), size=32, remove_bg=True, fill=False)
    grid_img = Image.open(io.BytesIO(grid))
    assert grid_img.mode == "RGBA"
    alpha = grid_img.getchannel("A")
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((31, 31)) == 0
    assert any(
        alpha.getpixel((x, y)) == 255 for x in range(32) for y in range(32)
    )


def test_fill_makes_subject_span_full_axis():
    _, grid = pixelate(_portrait_subject(), size=32, remove_bg=True, fill=True)
    alpha = Image.open(io.BytesIO(grid)).getchannel("A")
    col_opaque = [y for y in range(32) if alpha.getpixel((16, y)) == 255]
    assert min(col_opaque) <= 1
    assert max(col_opaque) >= 30
    assert alpha.getpixel((0, 16)) == 0
    assert alpha.getpixel((31, 16)) == 0


def test_no_bg_removal_is_opaque_rgb():
    _, grid = pixelate(_make_image(), size=32, remove_bg=False, fill=False)
    grid_img = Image.open(io.BytesIO(grid))
    assert grid_img.mode == "RGB"


def _gradient_image(w=400, h=300) -> bytes:
    """A horizontal color gradient so left and right edges differ strongly."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        arr[:, x] = (int(255 * x / (w - 1)), 80, 255 - int(255 * x / (w - 1)))
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_background_dimensions_and_no_tile_when_full():
    bg, tile = make_background(
        _gradient_image(), width=640, height=360, pixel_size=8,
        tileable=True, tile_div=1,
    )
    bg_img = Image.open(io.BytesIO(bg))
    assert bg_img.size == (640, 360)
    assert tile is None  # full-width unique -> no separate tile


def test_background_tile_returned_and_sized_when_divided():
    bg, tile = make_background(
        _gradient_image(), width=640, height=360, pixel_size=8,
        tileable=True, tile_div=2,
    )
    assert Image.open(io.BytesIO(bg)).size == (640, 360)
    assert tile is not None
    assert Image.open(io.BytesIO(tile)).size == (320, 360)


def test_background_horizontally_seamless():
    bg, _ = make_background(
        _gradient_image(), width=640, height=360, pixel_size=8,
        tileable=True, tile_div=1, colors=64,
    )
    arr = np.asarray(Image.open(io.BytesIO(bg)).convert("RGB")).astype(int)
    # When tiled, the right edge sits next to the left edge: they must match closely.
    edge_diff = np.abs(arr[:, 0] - arr[:, -1]).mean()
    assert edge_diff < 24, f"seam too large: {edge_diff}"


def test_background_not_seamless_skips_healing():
    bg, tile = make_background(
        _gradient_image(), width=512, height=288, pixel_size=8, tileable=False,
    )
    assert Image.open(io.BytesIO(bg)).size == (512, 288)
    assert tile is None
