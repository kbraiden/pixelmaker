"""Tests for the procedural walk-cycle engine."""
import io

import numpy as np
import pytest
from PIL import Image

from app.walkcycle import (
    DEFAULT_FRAMES,
    VALID_FRAME_COUNTS,
    build_frames,
    make_walk_cycle,
)


def _biped_sprite(w=32, h=32) -> bytes:
    """A tiny opaque 'character' with a head at the top edge and two feet."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    # body block rows 0..27 (head touches the very top edge)
    for y in range(0, 28):
        for x in range(10, 22):
            px[x, y] = (200, 80, 80, 255)
    # two feet rows 28..30 with a gap in the middle
    for y in range(28, 31):
        for x in range(10, 15):
            px[x, y] = (60, 60, 60, 255)
        for x in range(17, 22):
            px[x, y] = (60, 60, 60, 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _opaque_count(arr: np.ndarray) -> int:
    return int((arr[:, :, 3] > 0).sum())


@pytest.mark.parametrize("frames", VALID_FRAME_COUNTS)
def test_frame_count(frames):
    out = build_frames(_biped_sprite(), frames=frames)
    assert len(out) == frames


def test_invalid_frame_count_raises():
    with pytest.raises(ValueError):
        build_frames(_biped_sprite(), frames=5)


def test_transparent_sprite_raises():
    blank = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    buf = io.BytesIO()
    blank.save(buf, format="PNG")
    with pytest.raises(ValueError):
        build_frames(buf.getvalue())


def test_top_padding_prevents_clip():
    """A head at the top edge must not lose pixels to the upward bob."""
    src = _biped_sprite()
    base = np.array(Image.open(io.BytesIO(src)).convert("RGBA"))
    frames = build_frames(src)
    # output is padded by 1px so the bob has headroom
    assert frames[0].shape[0] == base.shape[0] + 1
    # no frame should drop body pixels (each frame keeps >= the base body count)
    base_count = _opaque_count(base)
    for f in frames:
        assert _opaque_count(f) >= base_count


def test_make_walk_cycle_outputs():
    res = make_walk_cycle(_biped_sprite(), frames=DEFAULT_FRAMES, fps_ms=120)
    assert res["frame_count"] == DEFAULT_FRAMES
    assert len(res["frames"]) == DEFAULT_FRAMES
    # sheet is N frames wide
    sheet = Image.open(io.BytesIO(res["sheet_png"]))
    assert sheet.size == (res["width"] * DEFAULT_FRAMES, res["height"])
    # gif is a real animated GIF
    gif = Image.open(io.BytesIO(res["gif_png"]))
    assert gif.format == "GIF"
    assert getattr(gif, "n_frames", 1) == DEFAULT_FRAMES


def test_feet_actually_move():
    """At least one step frame must differ from the contact frame in the feet."""
    frames = build_frames(_biped_sprite(), frames=4)
    contact = frames[0]
    step = frames[1]
    foot_band_contact = contact[-4:, :, 3]
    foot_band_step = step[-4:, :, 3]
    assert not np.array_equal(foot_band_contact, foot_band_step)


def _biped_with_tail() -> bytes:
    """Like _biped_sprite but with an off-centre appendage (tail) on the left,
    above the foot band. Regression guard: the foot split must ignore the empty
    left margin and split at the real gap between the two feet."""
    w = h = 32
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y in range(0, 28):
        for x in range(10, 22):
            px[x, y] = (200, 80, 80, 255)
    # tail blob on the far left, rows 12..20 (not in the foot band)
    for y in range(12, 21):
        px[3, y] = (150, 90, 60, 255)
        px[4, y] = (150, 90, 60, 255)
    # two feet with a gap, rows 28..30
    for y in range(28, 31):
        for x in range(10, 15):
            px[x, y] = (60, 60, 60, 255)
        for x in range(17, 22):
            px[x, y] = (60, 60, 60, 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_both_feet_animate_with_offset_appendage():
    """With a tail on one side, both the left- and right-step frames must move
    their respective foot (the split must not dump both feet on one side)."""
    frames = build_frames(_biped_with_tail(), frames=6)
    contact = frames[0][-4:, :, 3]
    # 6-frame order: contact, L-rise, L-peak, contact, R-rise, R-peak
    l_peak = frames[2][-4:, :, 3]
    r_peak = frames[5][-4:, :, 3]
    assert not np.array_equal(contact, l_peak), "left foot never moved"
    assert not np.array_equal(contact, r_peak), "right foot never moved"
    assert not np.array_equal(l_peak, r_peak), "both steps moved the same foot"

