"""PixelMaker FastAPI application."""
from __future__ import annotations

import base64
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .palettes import palette_names
from .pixelate import MAX_COLORS, MIN_COLORS, VALID_SIZES, pixelate
from .providers import ProviderError, get_provider

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="PixelMaker", version="1.0.0")


def _validate_params(size: int, palette: str, colors: int) -> None:
    if size not in VALID_SIZES:
        raise HTTPException(400, f"size must be one of {list(VALID_SIZES)}")
    if palette not in palette_names():
        raise HTTPException(400, f"palette must be one of {palette_names()}")
    if not (MIN_COLORS <= colors <= MAX_COLORS):
        raise HTTPException(400, f"colors must be between {MIN_COLORS} and {MAX_COLORS}")


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "ai_enabled": settings.ai_enabled,
            "sizes": list(VALID_SIZES),
            "palettes": palette_names(),
        }
    )


def _result_json(large_png: bytes, grid_png: bytes, size: int) -> JSONResponse:
    """Build a JSON response carrying both the preview and the editable sprite."""
    return JSONResponse(
        {
            "size": size,
            "preview_png": base64.b64encode(large_png).decode("ascii"),
            "sprite_png": base64.b64encode(grid_png).decode("ascii"),
        }
    )


@app.post("/api/generate")
def generate(
    prompt: str = Form(...),
    size: int = Form(32),
    palette: str = Form("adaptive"),
    colors: int = Form(16),
    remove_bg: bool = Form(True),
    fill: bool = Form(True),
) -> JSONResponse:
    """Text -> pixel art via the configured AI provider."""
    _validate_params(size, palette, colors)
    if not prompt.strip():
        raise HTTPException(400, "prompt must not be empty")
    try:
        provider = get_provider()
        source = provider.generate(prompt)
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc

    large_png, grid_png = pixelate(
        source,
        size=size,
        palette=palette,
        colors=colors,
        remove_bg=remove_bg,
        fill=fill,
    )
    return _result_json(large_png, grid_png, size)


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    size: int = Form(32),
    palette: str = Form("adaptive"),
    colors: int = Form(16),
    remove_bg: bool = Form(True),
    fill: bool = Form(True),
) -> JSONResponse:
    """Uploaded image -> pixel art (fully local, no AI)."""
    _validate_params(size, palette, colors)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "uploaded file is empty")
    try:
        large_png, grid_png = pixelate(
            raw,
            size=size,
            palette=palette,
            colors=colors,
            remove_bg=remove_bg,
            fill=fill,
        )
    except Exception as exc:  # noqa: BLE001 - bad image -> 400
        raise HTTPException(400, f"could not process image: {exc}") from exc
    return _result_json(large_png, grid_png, size)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
