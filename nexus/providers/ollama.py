"""Ollama (local model server) provider adapter.

A genuinely reachable provider for users who cannot or will not use a cloud
API key.  It calls the real Ollama HTTP API; it does not emulate a model.  If
no Ollama server is running, health reports unreachable and chat raises a
truthful ``provider_unavailable`` error.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Iterator

from .base import ChatMessage, ChatProvider, ChatResult, ProviderError


class OllamaProvider(ChatProvider):
    name = "ollama"
    supports = ("chat", "streaming")
    requires_key = False

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.base_url = (str(settings.get("base_url")) or "http://127.0.0.1:11434").rstrip("/")
        self.model = self.model or "llama3.2"

    def _post(self, path: str, payload: dict, timeout: float | None = None):
        req = urllib.request.Request(
            self.base_url + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            return urllib.request.urlopen(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            raise ProviderError("provider_rejected",
                                f"Ollama returned HTTP {exc.code}: {body}",
                                status=exc.code, provider=self.name) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError("provider_unavailable",
                                f"Could not reach Ollama at {self.base_url} ({type(exc).__name__}). "
                                "Start Ollama or configure a cloud provider.",
                                retryable=True, provider=self.name) from exc

    def chat(self, messages: list[ChatMessage], *, system: str = "",
             max_tokens: int = 900, temperature: float = 0.3,
             cancel: Callable[[], bool] | None = None) -> ChatResult:
        if not self.configured():
            raise ProviderError("provider_disabled", "Ollama provider is disabled.", provider=self.name)
        msgs = ([{"role": "system", "content": system}] if system else []) + [m.as_dict() for m in messages]
        payload = {"model": self.model, "messages": msgs, "stream": False,
                   "options": {"temperature": temperature, "num_predict": max_tokens}}
        with self._post("/api/chat", payload) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = str((data.get("message") or {}).get("content", "")).strip()
        if not text:
            raise ProviderError("empty_response", "Ollama returned an empty answer.", provider=self.name)
        return ChatResult(text=text, provider=self.name, model=data.get("model", self.model),
                          usage={"eval_count": data.get("eval_count", 0)},
                          finish_reason="stop" if data.get("done") else "length")

    def chat_stream(self, messages: list[ChatMessage], *, system: str = "",
                    max_tokens: int = 900, temperature: float = 0.3,
                    cancel: Callable[[], bool] | None = None) -> Iterator[str]:
        if not self.configured():
            raise ProviderError("provider_disabled", "Ollama provider is disabled.", provider=self.name)
        msgs = ([{"role": "system", "content": system}] if system else []) + [m.as_dict() for m in messages]
        payload = {"model": self.model, "messages": msgs, "stream": True,
                   "options": {"temperature": temperature, "num_predict": max_tokens}}
        with self._post("/api/chat", payload) as resp:
            for raw in resp:
                if cancel and cancel():
                    raise ProviderError("cancelled", "Stream cancelled.", provider=self.name)
                try:
                    data = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                piece = (data.get("message") or {}).get("content")
                if piece:
                    yield str(piece)
                if data.get("done"):
                    break

    def health(self) -> dict:
        h = super().health()
        h["checked_at"] = time.time()
        if not self.configured():
            h["reachable"] = False
            h["error"] = {"code": "provider_disabled", "message": "Ollama provider is disabled."}
            return h
        req = urllib.request.Request(self.base_url + "/api/tags", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 6)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models", [])]
            h["reachable"] = True
            h["models_available"] = names[:20]
            h["model_installed"] = any(n == self.model or n.startswith(self.model + ":") for n in names)
            if not h["model_installed"]:
                h["error"] = {"code": "model_not_installed",
                              "message": f"Model '{self.model}' is not installed. Run: ollama pull {self.model}"}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            h["reachable"] = False
            h["error"] = {"code": "provider_unavailable",
                          "message": f"Ollama is not reachable at {self.base_url} ({type(exc).__name__})."}
        return h
