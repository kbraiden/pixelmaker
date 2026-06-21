"""Tests for the pluggable animation system (idle / jump / attack)."""
import io

import numpy as np
import pytest
from PIL import Image

from app.animations import ACTIONS, make_animation


def _biped_sprite(w=32, h=32) -> bytes:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y in range(2, 28):           # body (leave a little headroom)
        for x in range(10, 22):
            px[x, y] = (200, 80, 80, 255)
    for y in range(28, 31):          # two feet with a gap
        for x in range(10, 15):
            px[x, y] = (60, 60, 60, 255)
        for x in range(17, 22):
            px[x, y] = (60, 60, 60, 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("action", ACTIONS)
def test_each_action_produces_frames(action):
    res = make_animation(_biped_sprite(), action=action, fps_ms=120)
    assert res["action"] == action
    assert res["frame_count"] >= 2
    assert len(res["frames"]) == res["frame_count"]


@pytest.mark.parametrize("action", ACTIONS)
def test_frames_are_uniform_size(action):
    res = make_animation(_biped_sprite(), action=action)
    sizes = {Image.open(io.BytesIO(f)).size for f in res["frames"]}
    assert len(sizes) == 1, f"{action} frames differ in size: {sizes}"
    # sheet width == frame_width * frame_count
    sheet = Image.open(io.BytesIO(res["sheet_png"]))
    assert sheet.size == (res["width"] * res["frame_count"], res["height"])


@pytest.mark.parametrize("action", ACTIONS)
def test_gif_is_animated(action):
    res = make_animation(_biped_sprite(), action=action)
    gif = Image.open(io.BytesIO(res["gif_png"]))
    assert gif.format == "GIF"
    assert getattr(gif, "n_frames", 1) >= 2


def test_invalid_action_raises():
    with pytest.raises(ValueError):
        make_animation(_biped_sprite(), action="fly")


def test_jump_leaves_the_ground():
    """A mid-jump frame must lift content higher than the resting frame."""
    res = make_animation(_biped_sprite(), action="jump")
    frames = [np.array(Image.open(io.BytesIO(f)).convert("RGBA")) for f in res["frames"]]

    def top_opaque_row(a):
        ys = np.where(a[:, :, 3] > 0)[0]
        return int(ys.min())

    tops = [top_opaque_row(f) for f in frames]
    assert min(tops) < tops[0], "no frame rises above the resting pose"


def test_attack_extends_horizontally():
    """An attack frame must reach further in x than the resting frame."""
    res = make_animation(_biped_sprite(), action="attack")
    frames = [np.array(Image.open(io.BytesIO(f)).convert("RGBA")) for f in res["frames"]]

    def right_edge(a):
        xs = np.where(a[:, :, 3] > 0)[1]
        return int(xs.max())

    edges = [right_edge(f) for f in frames]
    assert max(edges) > edges[-1], "attack never reaches past the neutral pose"
