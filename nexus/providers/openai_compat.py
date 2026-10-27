"""Real OpenAI-compatible chat / image provider adapter.

Uses only the Python standard library.  It performs genuine HTTP requests to a
configured ``/chat/completions`` and ``/images/generations`` endpoint, parses
SSE streaming deltas, and converts every failure into a truthful
:class:`ProviderError`.  It never manufactures an answer.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable, Iterator
from urllib.parse import urlparse

from .base import (ChatMessage, ChatProvider, ChatResult, ImageResult,
                   ProviderError)

MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _error_from_http(exc: urllib.error.HTTPError, provider: str) -> ProviderError:
    body = ""
    try:
        body = exc.read().decode("utf-8", "replace")[:2000]
    except Exception:
        pass
    message = f"Provider returned HTTP {exc.code}."
    try:
        parsed = json.loads(body)
        message = (parsed.get("error") or {}).get("message") or parsed.get("message") or message
    except (ValueError, AttributeError):
        if body:
            message = f"Provider returned HTTP {exc.code}: {body[:240]}"
    low = (message + " " + body[:400]).lower()
    if any(term in low for term in ('credit_balance_exhausted', 'insufficient_quota', 'no credits remaining', 'insufficient credits')):
        return ProviderError("quota_exhausted", f"AI provider has no available API credits or billing quota: {message}",
                             status=exc.code, retryable=False, provider=provider, detail={'billing_required': True})
    if exc.code in (401, 403):
        return ProviderError("auth_failed", f"AI provider rejected the API key: {message}",
                             status=exc.code, provider=provider)
    if exc.code == 429:
        return ProviderError("rate_limited", f"AI provider quota or rate limit reached: {message}",
                             status=exc.code, retryable=True, provider=provider)
    if exc.code in (400, 404) and ("model" in low or "deployment" in low):
        return ProviderError("invalid_model", f"Model name rejected by provider: {message}",
                             status=exc.code, provider=provider)
    if exc.code >= 500:
        return ProviderError("provider_unavailable", f"AI provider is unavailable (HTTP {exc.code}).",
                             status=exc.code, retryable=True, provider=provider)
    return ProviderError("provider_rejected", f"AI provider rejected the request: {message}",
                         status=exc.code, provider=provider)


def _network_error(exc: Exception, provider: str, timeout: float) -> ProviderError:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return ProviderError("timeout", f"AI provider timed out after {timeout:g}s.",
                             retryable=True, provider=provider)
    return ProviderError("provider_unavailable",
                         f"Could not reach the AI provider ({type(exc).__name__}).",
                         retryable=True, provider=provider)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward API credentials or fetch image redirect targets implicitly."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenAICompatProvider(ChatProvider):
    name = "openai_compatible"
    supports = ("chat", "streaming", "image_generation")

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def _request(self, path: str, payload: dict, *, stream: bool = False,
                 cancel: Callable[[], bool] | None = None):
        if cancel and cancel():
            raise ProviderError("cancelled", "Request cancelled before it started.", provider=self.name)
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        last: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())).open(req, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                last = _error_from_http(exc, self.name)
                if self.api_key:
                    last.message = last.message.replace(self.api_key, '[REDACTED]')
                if not last.retryable:
                    raise last
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                last = _network_error(exc, self.name, self.timeout)
            if cancel and cancel():
                raise ProviderError("cancelled", "Request cancelled during retry.", provider=self.name)
            if attempt < self.max_retries:
                time.sleep(min(0.5 * (attempt + 1), 2.0))
        raise last or ProviderError("provider_unavailable", "AI provider call failed.", provider=self.name)

    # ------------------------------------------------------------------ chat
    def _messages(self, messages: list[ChatMessage], system: str) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(m.as_dict() for m in messages)
        return out

    def chat(self, messages: list[ChatMessage], *, system: str = "",
             max_tokens: int = 900, temperature: float = 0.3,
             cancel: Callable[[], bool] | None = None) -> ChatResult:
        if not self.configured():
            raise ProviderError("provider_disabled", "The chat provider is disabled.",
                                provider=self.name)
        missing = self.missing()
        if missing:
            raise ProviderError("missing_credentials",
                                "AI provider is missing: " + ", ".join(missing) + ".",
                                provider=self.name, detail={"missing": missing})
        payload = {
            "model": self.model,
            "messages": self._messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        resp = self._request("/chat/completions", payload, cancel=cancel)
        try:
            with resp:
                raw = resp.read(2_000_001)
                if len(raw)>2_000_000: raise ProviderError('response_too_large','Chat response exceeded 2 MB.',provider=self.name)
                data = json.loads(raw.decode("utf-8"))
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if isinstance(content, list):
                content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
            text = str(content or "").strip()
            if not text:
                raise ProviderError("empty_response", "AI provider returned an empty answer.",
                                    retryable=True, provider=self.name)
            return ChatResult(text=text, provider=self.name, model=data.get("model", self.model),
                              usage=data.get("usage", {}), finish_reason=choice.get("finish_reason", "stop"),
                              raw_id=str(data.get("id", "")))
        except ProviderError:
            raise
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ProviderError("bad_response",
                                f"Could not parse the AI provider response ({type(exc).__name__}).",
                                retryable=True, provider=self.name) from exc

    def chat_stream(self, messages: list[ChatMessage], *, system: str = "",
                    max_tokens: int = 900, temperature: float = 0.3,
                    cancel: Callable[[], bool] | None = None) -> Iterator[str]:
        if not self.configured():
            raise ProviderError("provider_disabled", "The chat provider is disabled.", provider=self.name)
        missing = self.missing()
        if missing:
            raise ProviderError("missing_credentials",
                                "AI provider is missing: " + ", ".join(missing) + ".",
                                provider=self.name, detail={"missing": missing})
        payload = {
            "model": self.model,
            "messages": self._messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        resp = self._request("/chat/completions", payload, stream=True, cancel=cancel)
        count, started = 0, time.monotonic()
        try:
            with resp:
                for raw in resp:
                    if time.monotonic()-started>180:
                        raise ProviderError('timeout','Streaming response exceeded 180 seconds.',provider=self.name,retryable=True)
                    if cancel and cancel():
                        raise ProviderError("cancelled", "Stream cancelled.", provider=self.name)
                    line = raw.decode("utf-8", "replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        chunk = json.loads(body)
                    except ValueError:
                        continue
                    if chunk.get('error'):
                        raise ProviderError('provider_stream_error', 'Provider reported a streaming error; partial text is preserved. Retry or inspect provider configuration.', retryable=True, provider=self.name)
                    try:
                        delta = chunk["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, AttributeError, TypeError):
                        delta = None
                    if delta:
                        count+=len(str(delta))
                        if count>100000: raise ProviderError('response_too_large','Streaming response exceeded 100,000 characters.',provider=self.name)
                        yield str(delta)
        except ProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise _network_error(exc, self.name, self.timeout) from exc

    # ----------------------------------------------------------------- images
    def _fetch_url(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ProviderError("unsafe_image_url", "Image provider returned a non-HTTPS URL.",
                                provider=self.name)
        try:
            infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
            for info in infos:
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    raise ProviderError("unsafe_image_url",
                                        "Image provider returned a URL resolving to a private address.",
                                        provider=self.name)
        except socket.gaierror as exc:
            raise ProviderError("provider_unavailable", "Could not resolve the image host.",
                                provider=self.name) from exc
        req = urllib.request.Request(url, headers={"User-Agent": "NEXUS-IoT/2"},
                                     method="GET")
        with urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())).open(req, timeout=self.timeout) as r:
            ctype = (r.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            if not ctype.startswith("image/"):
                raise ProviderError("bad_response", "Image URL did not return an image.", provider=self.name)
            raw = r.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ProviderError("image_too_large", "Generated image exceeds 15 MB.", provider=self.name)
        return base64.b64encode(raw).decode("ascii"), ctype

    def generate_image(self, prompt: str, *, size: str = "1024x1024",
                       quality: str = "standard", n: int = 1) -> list[ImageResult]:
        if not self.configured():
            raise ProviderError("provider_disabled", "The image provider is disabled.", provider=self.name)
        missing = self.missing()
        if missing:
            raise ProviderError("missing_credentials",
                                "Image provider is missing: " + ", ".join(missing) + ".",
                                provider=self.name, detail={"missing": missing})
        base = {
            "model": self.model, "prompt": prompt[:3800], "n": max(1, min(n, 4)),
            "size": size, "quality": quality,
        }
        # GPT image models always return base64 and reject response_format;
        # DALL·E / compatible models may require it explicitly.
        payload = base if 'gpt-image' in self.model.lower() else dict(base, response_format="b64_json")
        resp = self._request("/images/generations", payload)
        try:
            with resp:
                raw=resp.read(22_000_001)
                if len(raw)>22_000_000: raise ProviderError('response_too_large','Image response exceeded the bounded payload size.',provider=self.name)
                data = json.loads(raw.decode("utf-8"))
        except (ValueError, OSError) as exc:
            raise ProviderError("bad_response", "Could not parse the image provider response.",
                                provider=self.name, retryable=True) from exc
        items = data.get("data") or []
        if not items:
            raise ProviderError("empty_response", "Image provider returned no images.",
                                provider=self.name, retryable=True)
        results: list[ImageResult] = []
        for item in items:
            if item.get("b64_json"):
                b64, mime = str(item["b64_json"]), "image/png"
            elif item.get("url"):
                b64, mime = self._fetch_url(str(item["url"]))
            else:
                raise ProviderError("bad_response", "Image result has neither b64_json nor url.",
                                    provider=self.name)
            results.append(ImageResult(b64=b64, mime=mime, provider=self.name,
                                       model=self.model,
                                       revised_prompt=str(item.get("revised_prompt", "")),
                                       width=int(str(size).split("x")[0]) if "x" in size else 0,
                                       height=int(str(size).split("x")[-1]) if "x" in size else 0))
        return results

    # ----------------------------------------------------------------- health
    def health(self) -> dict:
        h = super().health()
        h["checked_at"] = time.time()
        if h["missing"] or not self.configured():
            h["reachable"] = False
            h["error"] = {"code": "provider_not_configured" if h["missing"] else "provider_disabled",
                          "message": ("Missing configuration: " + ", ".join(h["missing"])) if h["missing"]
                          else "Provider is disabled."}
            return h
        # Real reachability probe: a single-token chat completion.  This is a
        # genuine provider call, not a local guess.
        try:
            r = self.chat([ChatMessage("user", "ping")], system="Reply with one word.",
                          max_tokens=4, temperature=0)
            h["reachable"] = bool(r.text)
            h["model_reported"] = r.model
        except ProviderError as exc:
            h["reachable"] = False
            h["error"] = exc.payload()
        return h
