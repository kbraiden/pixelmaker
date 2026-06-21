"""Procedural walk-cycle engine.

Turns a single pixel-art sprite into a looping walk cycle entirely locally
(no AI). It is intentionally generic so it works on arbitrary uploaded sprites,
not just one character:

  1. Find the opaque bounding box.
  2. Treat the bottom band as the "feet" and split it into left/right feet at
     the gap between them (or at the horizontal midpoint if there is no gap).
  3. Everything above the feet is the "body" (head, torso, hat, ...).
  4. For each frame, bob the body up a little on the step poses and alternately
     lift each foot, filling the waist seam so the body stays connected.
  5. Auto-pad the top by the bob amount so a hat/antenna at the very top edge is
     never clipped off (this is done uniformly across frames so the sheet stays
     rectangular).

Outputs: individual frame PNGs (true size), a horizontal sprite sheet PNG, and
an animated GIF preview.
"""
from __future__ import annotations

import io
from typing import List, Tuple

import numpy as np
from PIL import Image

# Public limits / defaults (mirrored by the API + UI).
VALID_FRAME_COUNTS = (4, 6)
DEFAULT_FRAMES = 6
MIN_FPS_MS = 40
MAX_FPS_MS = 500
DEFAULT_FPS_MS = 120
GIF_SCALE = 8  # nearest-neighbour upscale factor for the GIF preview


def _load_rgba(data: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(data)).convert("RGBA"))


def _bbox(alpha: np.ndarray) -> Tuple[int, int, int, int]:
    """Return (top, bottom, left, right) inclusive of opaque pixels."""
    ys, xs = np.where(alpha > 0)
    if ys.size == 0:
        raise ValueError("sprite is fully transparent")
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def _foot_split_x(alpha: np.ndarray, foot_top: int, foot_bottom: int,
                  left: int, right: int) -> int:
    """Find the x to split the foot band into left/right feet.

    Look only at the actual horizontal extent of the feet within the band and
    pick the centre of the widest *interior* empty column run (the gap between
    the two feet). Leading/trailing empty margins (e.g. a tail sitting above the
    band) are ignored. Falls back to the midpoint of the foot extent.
    """
    band = alpha[foot_top:foot_bottom + 1, left:right + 1]
    col_filled = band.any(axis=0)
    filled_idx = np.where(col_filled)[0]
    if filled_idx.size == 0:
        return (left + right) // 2
    first, last = int(filled_idx[0]), int(filled_idx[-1])

    # Widest empty run strictly inside [first, last].
    best_start, best_len = -1, 0
    run_start = None
    for i in range(first, last + 1):
        if not col_filled[i]:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                run_len = i - run_start
                if run_len > best_len:
                    best_start, best_len = run_start, run_len
                run_start = None
    if best_len >= 1:
        return left + best_start + best_len // 2
    return left + (first + last) // 2


def _paste(dst: np.ndarray, src: np.ndarray, dy: int = 0, dx: int = 0) -> None:
    """Alpha-aware paste: copy only opaque pixels of src onto dst, clipped."""
    H, W = dst.shape[:2]
    ys, xs = np.where(src[..., 3] > 0)
    for y, x in zip(ys, xs):
        ty, tx = y + dy, x + dx
        if 0 <= ty < H and 0 <= tx < W:
            dst[ty, tx] = src[y, x]


def _frame_specs(frames: int, foot_lift: int) -> List[dict]:
    """Return per-frame motion params for a 4- or 6-frame loop.

    body_dy is negative = up. Feet lift on alternating step poses; a small
    inward stride (dx) adds life. The 6-frame variant inserts a 'rise' pose
    before each 'peak' for a smoother glide.
    """
    if frames == 4:
        return [
            dict(body_dy=0,  l_dy=0,          l_dx=0, r_dy=0,          r_dx=0),
            dict(body_dy=-1, l_dy=-foot_lift, l_dx=1, r_dy=0,          r_dx=0),
            dict(body_dy=0,  l_dy=0,          l_dx=0, r_dy=0,          r_dx=0),
            dict(body_dy=-1, l_dy=0,          l_dx=0, r_dy=-foot_lift, r_dx=-1),
        ]
    # 6-frame: contact, L-rise, L-peak, contact, R-rise, R-peak
    return [
        dict(body_dy=0,  l_dy=0,            l_dx=0, r_dy=0,            r_dx=0),
        dict(body_dy=-1, l_dy=-1,           l_dx=1, r_dy=0,            r_dx=0),
        dict(body_dy=-1, l_dy=-foot_lift,   l_dx=1, r_dy=0,            r_dx=0),
        dict(body_dy=0,  l_dy=0,            l_dx=0, r_dy=0,            r_dx=0),
        dict(body_dy=-1, l_dy=0,            l_dx=0, r_dy=-1,           r_dx=-1),
        dict(body_dy=-1, l_dy=0,            l_dx=0, r_dy=-foot_lift,   r_dx=-1),
    ]


def detect_regions(base: np.ndarray) -> dict:
    """Detect the sprite's anatomy for procedural animation.

    Returns the opaque bounding box, the bottom "foot" band, the x that splits
    the band into left/right feet, the last body row (for waist seam fills), and
    a sensible foot-lift amplitude. Shared by all animation generators.
    """
    alpha = base[:, :, 3]
    top, bottom, left, right = _bbox(alpha)
    bbox_h = bottom - top + 1
    # Foot band: bottom ~12% of the subject, at least 2 rows, at most ~1/3.
    foot_h = max(2, min(round(bbox_h * 0.12), bbox_h // 3))
    foot_top = bottom - foot_h + 1
    foot_bottom = bottom
    body_bottom = foot_top - 1
    split_x = _foot_split_x(alpha, foot_top, foot_bottom, left, right)
    foot_lift = 2 if bbox_h >= 16 else 1
    return {
        "top": top, "bottom": bottom, "left": left, "right": right,
        "bbox_h": bbox_h, "bbox_w": right - left + 1,
        "foot_top": foot_top, "foot_bottom": foot_bottom,
        "body_bottom": body_bottom, "split_x": split_x, "foot_lift": foot_lift,
    }


def build_frames(data: bytes, frames: int = DEFAULT_FRAMES) -> List[np.ndarray]:
    """Build the walk-cycle frames as a list of RGBA numpy arrays.

    All frames share the same dimensions: the source size, plus extra top
    padding so the upward body bob never clips content at the top edge.
    """
    if frames not in VALID_FRAME_COUNTS:
        raise ValueError(f"frames must be one of {list(VALID_FRAME_COUNTS)}")

    base = _load_rgba(data)
    H, W = base.shape[:2]
    R = detect_regions(base)
    top = R["top"]
    foot_top, foot_bottom = R["foot_top"], R["foot_bottom"]
    body_bottom = R["body_bottom"]
    split_x = R["split_x"]
    foot_lift = R["foot_lift"]

    # The body bobs up by at most 1px in these rigs; pad the top so a hat sitting
    # at the very edge isn't clipped. top has `top` rows of existing headroom.
    bob_amp = 1
    pad_top = max(0, bob_amp - top)
    out_h = H + pad_top

    def shifted(layer_full: np.ndarray) -> np.ndarray:
        out = np.zeros((out_h, W, 4), dtype=base.dtype)
        out[pad_top:pad_top + H] = layer_full
        return out

    # Region layers in the padded coordinate space.
    body_full = base.copy()
    body_full[foot_top:foot_bottom + 1] = 0  # body excludes feet
    body_layer = shifted(body_full)

    feet_full = np.zeros_like(base)
    feet_full[foot_top:foot_bottom + 1] = base[foot_top:foot_bottom + 1]
    lfoot = shifted(np.where(
        (np.arange(W)[None, :, None] <= split_x), feet_full, 0))
    rfoot = shifted(np.where(
        (np.arange(W)[None, :, None] > split_x), feet_full, 0))

    seam_full = np.zeros_like(base)
    if 0 <= body_bottom < H:
        seam_full[body_bottom] = base[body_bottom]
    seam_layer = shifted(seam_full)
    seam_row = pad_top + body_bottom  # padded-space row index of the seam

    out_frames: List[np.ndarray] = []
    for spec in _frame_specs(frames, foot_lift):
        canvas = np.zeros((out_h, W, 4), dtype=base.dtype)
        _paste(canvas, body_layer, dy=spec["body_dy"])
        # Waist seam fill: when the body lifts, replicate its bottom row down so
        # there's no gap between the body and the planted foot.
        if spec["body_dy"] < 0:
            for k in range(-spec["body_dy"]):
                _paste(canvas, seam_layer, dy=-k)
        _paste(canvas, lfoot, dy=spec["l_dy"], dx=spec["l_dx"])
        _paste(canvas, rfoot, dy=spec["r_dy"], dx=spec["r_dx"])
        out_frames.append(canvas)
    return out_frames


def _png_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _sheet_bytes(frames: List[np.ndarray]) -> bytes:
    n = len(frames)
    h, w = frames[0].shape[:2]
    sheet = Image.new("RGBA", (w * n, h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(Image.fromarray(f, "RGBA"), (i * w, 0))
    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()


def _gif_bytes(frames: List[np.ndarray], fps_ms: int, scale: int = GIF_SCALE) -> bytes:
    h, w = frames[0].shape[:2]
    imgs = [Image.fromarray(f, "RGBA").resize((w * scale, h * scale), Image.NEAREST)
            for f in frames]
    buf = io.BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=fps_ms, loop=0, disposal=2, transparency=0)
    return buf.getvalue()


def make_walk_cycle(data: bytes, frames: int = DEFAULT_FRAMES,
                    fps_ms: int = DEFAULT_FPS_MS) -> dict:
    """Build a walk cycle and return ready-to-serve assets.

    Returns a dict with:
      width, height   - per-frame dimensions (may be +1px taller than source)
      frame_count     - number of frames
      frames          - list[bytes]: true-size frame PNGs (for the live preview)
      sheet_png       - bytes: horizontal sprite sheet (for LibreSprite import)
      gif_png         - bytes: animated GIF preview
    """
    fps_ms = max(MIN_FPS_MS, min(MAX_FPS_MS, int(fps_ms)))
    arrs = build_frames(data, frames=frames)
    h, w = arrs[0].shape[:2]
    return {
        "width": w,
        "height": h,
        "frame_count": len(arrs),
        "frames": [_png_bytes(a) for a in arrs],
        "sheet_png": _sheet_bytes(arrs),
        "gif_png": _gif_bytes(arrs, fps_ms),
    }
