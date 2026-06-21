"""Tests for the isometric tile generator (offline, no AI)."""
import io

import numpy as np
import pytest
from PIL import Image

from app.isometric import (
    HEIGHT_VARIANTS,
    VALID_ISO_WIDTHS,
    make_isometric_tiles,
    project_top,
)


def _texture(color=(90, 170, 70), n=96) -> bytes:
    rng = np.random.default_rng(0)
    arr = np.clip(np.array(color) + rng.integers(-20, 20, (n, n, 3)), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("width", VALID_ISO_WIDTHS)
def test_top_is_2to1_diamond(width):
    tex = np.zeros((32, 32, 3), np.uint8)
    tex[:] = (100, 180, 80)
    top, bottom_row = project_top(tex, width)
    assert top.shape == (width // 2, width, 4)
    # widest row is the vertical middle (a true 2:1 diamond)
    widths = [(top[y, :, 3] > 0).sum() for y in range(width // 2)]
    assert max(widths) == max(widths)  # sanity
    assert np.argmax(widths) in (width // 4 - 1, width // 4)  # middle row
    # corners of the bounding box must be transparent (diamond, not square)
    assert top[0, 0, 3] == 0 and top[0, -1, 3] == 0


def test_invalid_width_raises():
    with pytest.raises(ValueError):
        make_isometric_tiles(_texture(), width=48)


def test_all_variants_share_identical_top():
    res = make_isometric_tiles(_texture(), width=64, variants=HEIGHT_VARIANTS)
    tiles = {n: np.array(Image.open(io.BytesIO(b)).convert("RGBA"))
             for n, b in res["tiles"].items()}
    # The upper half of the diamond (above the side vertices) is pure top surface
    # for every variant, so it must match exactly -> tiles align on one grid.
    pure_top = 64 // 4
    ref = tiles["full"][:pure_top]
    for name, t in tiles.items():
        assert np.array_equal(t[:pure_top], ref), f"{name} top differs from full"


def test_atlas_is_uniform_grid():
    res = make_isometric_tiles(_texture(), width=64)
    atlas = Image.open(io.BytesIO(res["atlas_png"]))
    w, ch = res["cell_size"]
    assert atlas.size == (w * len(res["variants"]), ch)


def test_tres_is_wellformed_for_godot():
    res = make_isometric_tiles(_texture(), width=64, basename="grass")
    tres = res["tres_text"]
    assert tres.startswith('[gd_resource type="TileSet"')
    assert "tile_shape = 1" in tres                      # isometric
    assert f"tile_size = Vector2i(64, 32)" in tres       # 2:1 base
    assert "TileSetAtlasSource" in tres
    # atlas path points inside the export folder
    assert f"res://grass/{res['atlas_name']}" in tres


def test_zip_contains_folder_with_all_files():
    import io as _io
    import zipfile
    res = make_isometric_tiles(_texture(), width=64, variants=("full", "half"),
                               basename="grass")
    assert res["zip_name"] == "grass.zip"
    names = zipfile.ZipFile(_io.BytesIO(res["zip_bytes"])).namelist()
    # everything lives under one folder
    assert all(n.startswith("grass/") for n in names), names
    assert "grass/grass_atlas.png" in names
    assert "grass/grass_tileset.tres" in names
    assert any(n.endswith("_godot_notes.txt") for n in names)
    assert "grass/grass_full.png" in names and "grass/grass_half.png" in names


def test_side_variants_get_shorter():
    res = make_isometric_tiles(_texture(), width=64)
    heights = {n: Image.open(io.BytesIO(b)).size[1] for n, b in res["tiles"].items()}
    assert heights["full"] > heights["half"] > heights["quarter"] >= heights["slab"]


def test_rim_toggle_changes_side_faces():
    """Enabling the top-material rim must change the side-face pixels."""
    tex = _texture()
    on = make_isometric_tiles(tex, width=64, variants=("full",), rim=True)
    off = make_isometric_tiles(tex, width=64, variants=("full",), rim=False)
    a = np.array(Image.open(io.BytesIO(on["tiles"]["full"])).convert("RGBA"))
    b = np.array(Image.open(io.BytesIO(off["tiles"]["full"])).convert("RGBA"))
    htop = 64 // 2
    assert not np.array_equal(a[htop:], b[htop:]), "rim toggle had no effect on sides"
