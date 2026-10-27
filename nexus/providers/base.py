"""Provider-independent contracts for NEXUS AI services.

A provider adapter owns exactly one external API family.  Nothing in this
module knows about HTTP routes, the database, or the UI, so new models can be
added by implementing :class:`ChatProvider` without touching the application.

Design rules:
  * Every failure raises :class:`ProviderError` with a stable machine code.
    No adapter may fabricate an answer or return a "successful" fallback.
  * Capabilities are declared per provider and per configured model.  The
    orchestrator never assumes that a provider supports vision, images,
    streaming, browsing or tool calls.
  * Secrets are passed in at construction time and never logged or returned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator


@dataclass
class ProviderError(Exception):
    """A truthful, typed external-provider failure."""

    code: str
    message: str
    status: int | None = None
    retryable: bool = False
    provider: str = ""
    detail: dict = field(default_factory=dict)

    def __post_init__(self):
        super().__init__(self.message)

    def payload(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "status": self.status,
            "retryable": self.retryable,
            "provider": self.provider,
            "detail": self.detail,
        }


@dataclass
class ChatMessage:
    role: str                       # system | user | assistant | tool
    content: str
    name: str | None = None

    def as_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    usage: dict = field(default_factory=dict)
    finish_reason: str = "stop"
    raw_id: str = ""

    def as_dict(self) -> dict:
        return {
            "text": self.text, "provider": self.provider, "model": self.model,
            "usage": self.usage, "finish_reason": self.finish_reason,
            "raw_id": self.raw_id,
        }


@dataclass
class ImageResult:
    """A real generated image.  ``b64`` is raw base64 (no data: prefix)."""

    b64: str
    mime: str
    provider: str
    model: str
    revised_prompt: str = ""
    width: int = 0
    height: int = 0

    def as_dict(self) -> dict:
        return {
            "b64": self.b64, "mime": self.mime, "provider": self.provider,
            "model": self.model, "revised_prompt": self.revised_prompt,
            "width": self.width, "height": self.height,
        }


CAPABILITIES = (
    "chat", "streaming", "vision", "image_generation", "embeddings",
    "tool_calls", "web_search",
)


class ChatProvider:
    """Base adapter.  Subclasses implement the calls they actually support."""

    name: str = "base"
    supports: tuple[str, ...] = ()

    def __init__(self, settings: dict):
        self.settings = settings
        self.base_url = str(settings.get("base_url", "")).rstrip("/")
        self.model = str(settings.get("model", ""))
        self.api_key = str(settings.get("api_key", ""))
        self.timeout = float(settings.get("timeout", 30) or 30)
        self.max_retries = int(settings.get("max_retries", 1) or 0)

    def capabilities(self) -> dict[str, bool]:
        declared = self.settings.get("capabilities") or {}
        out = {c: c in self.supports for c in CAPABILITIES}
        for c in CAPABILITIES:
            if c in declared and out[c]:
                out[c] = bool(declared[c])
        return out

    def configured(self) -> bool:
        return bool(self.settings.get("enabled", True))

    def missing(self) -> list[str]:
        """Exact list of configuration items that are absent."""
        out = []
        if not self.base_url:
            out.append("base_url")
        if not self.model:
            out.append("model")
        if not self.api_key and self.requires_key:
            out.append("api_key")
        return out

    requires_key = True

    def chat(self, messages: list[ChatMessage], *, system: str = "",
             max_tokens: int = 900, temperature: float = 0.3,
             cancel: Callable[[], bool] | None = None) -> ChatResult:
        raise ProviderError("unsupported_capability",
                            f"{self.name} does not implement chat.", provider=self.name)

    def chat_stream(self, messages: list[ChatMessage], *, system: str = "",
                    max_tokens: int = 900, temperature: float = 0.3,
                    cancel: Callable[[], bool] | None = None) -> Iterator[str]:
        raise ProviderError("unsupported_capability",
                            f"{self.name} does not implement streaming chat.", provider=self.name)
        yield ""  # pragma: no cover - makes the signature a generator

    def generate_image(self, prompt: str, *, size: str = "1024x1024",
                       quality: str = "standard", n: int = 1) -> list[ImageResult]:
        raise ProviderError("unsupported_capability",
                            f"{self.name} does not implement image generation.", provider=self.name)

    def health(self) -> dict:
        """Report configuration and, where possible, real reachability."""
        missing = self.missing()
        return {
            "provider": self.name,
            "model": self.model,
            "configured": not missing and self.configured(),
            "enabled": self.configured(),
            "missing": missing,
            "reachable": None,          # None = not tested, True/False = tested
            "checked_at": None,
            "error": None,
            "capabilities": self.capabilities(),
        }


class NullProvider(ChatProvider):
    """Explicitly unconfigured provider.  Never returns an answer."""

    name = "none"
    supports = ()
    requires_key = False

    def configured(self) -> bool:
        return False

    def missing(self) -> list[str]:
        return ["provider", "model", "api_key"]

    def chat(self, *args, **kwargs):
        raise ProviderError("provider_not_configured", "Online AI is not configured. An administrator must configure a provider, model and server-held API key.", provider=self.name)

    def health(self) -> dict:
        h = super().health()
        h["error"] = {
            "code": "provider_not_configured",
            "message": self.settings.get("configuration_error") or "No AI provider is configured. Set the provider, model and API key "
                       "in Admin > AI Providers or via environment variables.",
        }
        h["reachable"] = False
        return h
