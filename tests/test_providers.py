"""Tests for the pluggable provider layer and per-request API key."""
from types import SimpleNamespace

import pytest

from app.providers import ProviderError, get_provider
from app.providers.openai_provider import OpenAIProvider


def test_per_request_key_builds_openai_provider():
    provider = get_provider("sk-test-key-123")
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"
    assert hasattr(provider, "generate")


def test_empty_key_without_fallback_raises(monkeypatch):
    # Simulate a host with no configured key so there is nothing to fall back to.
    monkeypatch.setattr(
        "app.providers.openai_provider.settings",
        SimpleNamespace(openai_api_key=None, openai_image_model="gpt-image-1"),
    )
    with pytest.raises(ProviderError):
        OpenAIProvider(api_key="")
