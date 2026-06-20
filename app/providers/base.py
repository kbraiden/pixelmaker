"""Pluggable AI image-provider interface.

A provider turns a text prompt into raw image bytes (PNG/JPEG). The pixelation
engine then converts those bytes into retro pixel art, so providers do not need
to produce pixel art themselves -- though prompting for it helps.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """Raised when image generation fails or is unavailable."""


class ImageProvider(ABC):
    """Abstract base class for text-to-image providers."""

    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str, size: int = 512) -> bytes:
        """Generate an image from a text prompt and return raw image bytes."""
        raise NotImplementedError


def get_provider() -> ImageProvider:
    """Return the configured provider, or raise ProviderError if unavailable.

    Selection is based on configuration; today only OpenAI is implemented, but
    a local model could be wired in here without touching the API layer.
    """
    from ..config import settings
    from .openai_provider import OpenAIProvider

    if not settings.ai_enabled:
        raise ProviderError(
            "AI text-to-image is not configured. Set OPENAI_API_KEY in your .env "
            "to enable the 'From text' mode. Image upload conversion still works."
        )
    return OpenAIProvider()
