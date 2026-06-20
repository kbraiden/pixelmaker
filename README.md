# PixelMaker

Turn words and photos into retro, old-video-game-style pixel art PNGs.

Two modes:

- **From text** — type a subject (e.g. `alligator`) and an AI image model generates
  a retro sprite, which is then pixelated/quantized locally. Requires an OpenAI API key.
- **From image** — upload a photo and convert it to pixel art entirely locally
  (downscale + palette quantization). No API key or network required.

## How it works

The core engine (`app/pixelate.py`) is the same for both modes:

1. **Remove background** (optional): detect the flat border color and flood-fill it to
   transparency, so the subject sits on a transparent background.
2. **Fill frame** (optional): trim to the subject's bounding box and pad to a square so it
   fills the grid edge-to-edge (no wasted blank space; aspect ratio preserved).
3. Downscale to a small grid (16/32/64/128, default **32×32**).
4. Quantize colors — either an **adaptive** palette (choose color count) or a fixed
   retro palette (**NES**, **Game Boy**, **CGA**, **PICO-8**). Alpha is preserved.
5. Upscale back with nearest-neighbor sampling so pixels stay crisp.

Both options are on by default and exposed as checkboxes in the UI
("Transparent background" and "Fill frame"). The exported sprite PNG is RGBA, so the
transparency carries straight into LibreSprite/Aseprite.

## Setup

```powershell
cd "C:\AI Projects\pixelmaker"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For the **From text** mode, copy `.env.example` to `.env` and set your key:

```
OPENAI_API_KEY=sk-...
```

(Skip this for image-only use.)

## Run

```powershell
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 in your browser.

## API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Status + whether AI is enabled |
| `/api/generate` | POST (form: `prompt`, `size`, `palette`, `colors`, `remove_bg`, `fill`) | Text → pixel art |
| `/api/convert` | POST (multipart: `file`, `size`, `palette`, `colors`, `remove_bg`, `fill`) | Image → pixel art |

Both image endpoints return JSON: `{ "size", "preview_png", "sprite_png" }`, where the
two PNG fields are base64-encoded. `preview_png` is a large (512px) crisp upscale for
display; `sprite_png` is the **true-size** grid (e.g. 32×32) for editing.

## Editing in a sprite editor (LibreSprite / Aseprite)

The result panel offers two downloads:

- **Download sprite (true size)** — the raw `size×size` PNG (e.g. `pixelart_32x32.png`).
  Open this directly in **LibreSprite** or Aseprite; one image pixel maps to one editor
  pixel, so you can paint/edit cleanly. This is the file to keep working on.
- **Download large preview** — the 512px upscaled PNG, handy for sharing or thumbnails.

## Tests

```powershell
pip install pytest
pytest
```

Tests cover the pixelation engine and palettes offline (no network/AI).

## Notes

- Built for a Snapdragon X (ARM64) machine — uses a hosted image API instead of local
  Stable Diffusion (no CUDA GPU). All image processing is local and ARM64-friendly.
- Secrets live only in `.env`, which is gitignored.
