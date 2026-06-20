"""OpenAI image-generation provider."""
from __future__ import annotations

import base64

from ..config import settings
from .base import ImageProvider, ProviderError

# OpenAI image API supports a fixed set of square sizes; we request the smallest
# reasonable one and let the pixelation engine downscale to the target grid.
_SUPPORTED_API_SIZES = ("1024x1024",)

_PROMPT_TEMPLATE = (
    "{subject}, retro 8-bit pixel art video game sprite, "
    "limited color palette, crisp pixels, centered, flat solid background"
)


class OpenAIProvider(ImageProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.openai_api_key
        if not key:
            raise ProviderError("No OpenAI API key provided.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - import guard
            raise ProviderError(
                "The 'openai' package is not installed. Run 'pip install openai'."
            ) from exc
        self._client = OpenAI(api_key=key)
        self._model = settings.openai_image_model

    def generate(self, prompt: str, size: int = 512) -> bytes:
        clean = prompt.strip()
        if not clean:
            raise ProviderError("Prompt must not be empty.")
        full_prompt = _PROMPT_TEMPLATE.format(subject=clean)
        try:
            result = self._client.images.generate(
                model=self._model,
                prompt=full_prompt,
                size=_SUPPORTED_API_SIZES[0],
                n=1,
            )
        except Exception as exc:  # noqa: BLE001 - surface any API error cleanly
            raise ProviderError(f"Image generation failed: {exc}") from exc

        data = result.data[0]
        b64 = getattr(data, "b64_json", None)
        if b64:
            return base64.b64decode(b64)

        url = getattr(data, "url", None)
        if url:
            import urllib.request

            with urllib.request.urlopen(url) as resp:  # noqa: S310 - trusted API URL
                return resp.read()

        raise ProviderError("Image API returned no image data.")
