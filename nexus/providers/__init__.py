"""NEXUS AI provider adapters.

Import from :mod:`nexus.providers.registry` for configuration-aware access;
import :mod:`nexus.providers.base` for the adapter contracts.
"""
from .base import (CAPABILITIES, ChatMessage, ChatProvider, ChatResult,
                   ImageResult, NullProvider, ProviderError)
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

__all__ = [
    "CAPABILITIES", "ChatMessage", "ChatProvider", "ChatResult", "ImageResult",
    "NullProvider", "ProviderError", "OpenAICompatProvider", "OllamaProvider",
]
