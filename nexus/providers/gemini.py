"""Native Google Gemini generateContent + SSE; no OpenAI account or SDK.

Legacy /v1beta/openai configuration URLs remain accepted and are mapped to
Google's native /v1beta endpoint. Keys are sent only in x-goog-api-key headers.
"""
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from .base import ChatProvider, ChatResult, ProviderError, ChatMessage
from .openai_compat import NoRedirect, _error_from_http, _network_error

DEFAULT_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta'
DEFAULT_MODEL = 'gemini-2.0-flash-lite'


def valid_base_url(value):
    try:
        p = urlparse(str(value).rstrip('/'))
        if p.username or p.password or p.query or p.fragment:
            return False
        if p.hostname in ('localhost', '127.0.0.1', '::1'):
            return p.scheme in ('http', 'https')
        return (p.scheme == 'https' and p.hostname == 'generativelanguage.googleapis.com'
                and p.port in (None, 443) and p.path in ('/v1beta', '/v1beta/openai'))
    except ValueError:
        return False


class GeminiProvider(ChatProvider):
    name = 'gemini'
    supports = ('chat', 'streaming')

    def _fetch_supported_models(self, base):
        try:
            url = base + '/models'
            headers = {'x-goog-api-key': self.api_key, 'Accept': 'application/json'}
            req = urllib.request.Request(url, headers=headers, method='GET')
            opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            with opener.open(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            models = []
            for item in data.get('models', []):
                methods = item.get('supportedGenerationMethods', [])
                if 'generateContent' in methods:
                    name = item.get('name', '').removeprefix('models/')
                    if name:
                        models.append(name)
            return models
        except Exception:
            return []

    def _request(self, payload, *, stream=False, cancel=None):
        if not self.configured():
            raise ProviderError('provider_disabled', 'The Gemini provider is disabled.', provider=self.name)
        if self.missing():
            raise ProviderError('missing_credentials', 'Gemini is missing: ' + ', '.join(self.missing()), provider=self.name)
        if not valid_base_url(self.base_url):
            raise ProviderError('invalid_provider_url', 'Use the Google Gemini endpoint: ' + DEFAULT_BASE_URL, provider=self.name)
        if cancel and cancel():
            raise ProviderError('cancelled', 'Connection check cancelled.', provider=self.name)
        base = self.base_url[:-7] if self.base_url.endswith('/openai') else self.base_url
        raw_model = self.model.removeprefix('models/')
        if 'generativelanguage.googleapis.com' in base and raw_model in ('gemini-1.5-flash', 'gemini-2.0-flash'):
            target_model = 'gemini-3.8-flash'
        else:
            target_model = raw_model

        def _make_req(m, p=None):
            model = quote(m, safe='-._')
            url = base + '/models/' + model + (':streamGenerateContent?alt=sse' if stream else ':generateContent')
            headers = {'Content-Type': 'application/json', 'x-goog-api-key': self.api_key,
                       'Accept': 'text/event-stream' if stream else 'application/json'}
            return urllib.request.Request(url, data=json.dumps(p if p is not None else payload).encode(), headers=headers, method='POST')

        req = _make_req(target_model)
        last = None
        for attempt in range(self.max_retries + 1):
            try:
                opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
                return opener.open(req, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                last = _error_from_http(exc, self.name)
                if exc.code == 400 and any(x in last.message.lower() for x in ('api key', 'api_key')):
                    last.code, last.retryable = 'auth_failed', False
                last.message = last.message.replace(self.api_key, '[REDACTED]')

                # If thinkingConfig was rejected by this model version for any reason,
                # immediately retry without it — zero latency penalty.
                if exc.code == 400 and 'thinkingConfig' in payload.get('generationConfig', {}):
                    p_no_think = json.loads(json.dumps(payload))
                    p_no_think.get('generationConfig', {}).pop('thinkingConfig', None)
                    try:
                        return opener.open(_make_req(target_model, p_no_think), timeout=self.timeout)
                    except Exception:
                        pass

                is_quota = exc.code == 429 or any(w in last.message.lower() for w in ('quota', 'rate limit', 'resource_exhausted', 'limit exceeded', 'exceeded your current quota'))
                is_compat_error = exc.code in (400, 404, 500, 502, 503, 504) or any(w in last.message.lower() for w in ('not found for api version', 'not supported for generatecontent', 'no longer available', 'invalid_model', 'models/', 'overloaded', 'unavailable', '503'))

                # Automatic recovery if requested model is quota-exhausted (429), deprecated, overloaded (503), or not found on Google API
                if ('generativelanguage.googleapis.com' in base and (is_quota or is_compat_error)):
                    # Check if Google's error message explicitly recommends a specific model
                    rec_match = re.search(r'use\s+models/([a-zA-Z0-9_.-]+)', last.message, re.I)
                    rec_model = rec_match.group(1) if rec_match else None

                    # If model is quota exhausted (429), immediately switch to alternative model buckets:
                    if is_quota:
                        preferred = ['gemini-3.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-1.5-flash-latest', 'gemini-1.5-pro']
                    elif exc.code in (500, 502, 503, 504) or 'overloaded' in last.message.lower() or '503' in last.message:
                        preferred = ['gemini-3.5-flash-lite', 'gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-1.5-pro']
                    else:
                        preferred = ['gemini-3.8-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-pro', 'gemini-pro']

                    supported = self._fetch_supported_models(base)
                    candidates = []
                    if rec_model and rec_model != target_model:
                        candidates.append(rec_model)
                    for m in preferred:
                        if m not in candidates and m != target_model and (not supported or m in supported):
                            candidates.append(m)
                    for m in supported:
                        if m not in candidates and m != target_model:
                            candidates.append(m)

                    for alt in candidates:
                        try:
                            if exc.code in (500, 502, 503, 504):
                                time.sleep(0.5)
                            alt_payload = json.loads(json.dumps(payload))
                            gen_cfg = alt_payload.get('generationConfig', {})
                            if alt.startswith('gemini-2.5'):
                                gen_cfg['thinkingConfig'] = {'thinkingBudget': 0}
                            else:
                                gen_cfg.pop('thinkingConfig', None)
                            alt_req = _make_req(alt, alt_payload)
                            resp = opener.open(alt_req, timeout=self.timeout)
                            self.model = alt
                            return resp
                        except Exception:
                            continue

                if not last.retryable:
                    raise last
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
                last = _network_error(exc, self.name, self.timeout)
            if cancel and cancel():
                raise ProviderError('cancelled', 'Connection check cancelled.', provider=self.name)
            if attempt < self.max_retries:
                time.sleep(0.5)
        raise last or ProviderError('provider_unavailable', 'Could not reach Google Gemini.', provider=self.name)

    def _payload(self, messages, system, max_tokens, temperature):
        contents, instructions = [], [system] if system else []
        for m in messages:
            if m.role == 'system':
                instructions.append(m.content)
                continue
            role = 'model' if m.role == 'assistant' else 'user'
            part = {'text': m.content}
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'].append(part)
            else:
                contents.append({'role': role, 'parts': [part]})
        generation = {'temperature': temperature, 'maxOutputTokens': max_tokens}
        model = self.model.removeprefix('models/')
        # thinkingBudget=0 is a valid token cap that disables internal reasoning on Gemini 2.5 Flash.
        # Gemini 3.x and 4.x do NOT support thinkingLevel='NONE' — that value is rejected (HTTP 400).
        # For those models we simply omit thinkingConfig; they stream immediately by default.
        if model.startswith('gemini-2.5'):
            generation['thinkingConfig'] = {'thinkingBudget': 0}
        payload = {'contents': contents, 'generationConfig': generation}
        if instructions:
            payload['systemInstruction'] = {'parts': [{'text': '\n\n'.join(instructions)}]}
        return payload

    def _text(self, data):
        if data.get('error'):
            raise ProviderError('provider_stream_error', 'Google reported a generation error; no successful answer was substituted.', provider=self.name)
        if (data.get('promptFeedback') or {}).get('blockReason'):
            raise ProviderError('content_blocked', 'Google blocked this prompt under its content policy.', provider=self.name)
        candidates = data.get('candidates') or []
        c = candidates[0] if candidates else {}
        if c.get('finishReason') in ('SAFETY', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'RECITATION'):
            raise ProviderError('content_blocked', 'Google did not return this answer under its content policy.', provider=self.name)
        return ''.join(str(p.get('text', '')) for p in (c.get('content') or {}).get('parts', []) if not p.get('thought'))

    def chat(self, messages, *, system='', max_tokens=900, temperature=0.3, cancel=None):
        resp = self._request(self._payload(messages, system, max_tokens, temperature), cancel=cancel)
        try:
            with resp:
                raw = resp.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError('response_too_large', 'Gemini response exceeded 2 MB.', provider=self.name)
            data = json.loads(raw)
            text = self._text(data).strip()
            if not text:
                raise ProviderError('empty_response', 'Gemini returned no answer. Check the model, thinking/output budget and provider policy.', provider=self.name)
            usage = data.get('usageMetadata', {})
            return ChatResult(text, self.name, data.get('modelVersion', self.model),
                              {'input_tokens': usage.get('promptTokenCount', 0), 'output_tokens': usage.get('candidatesTokenCount', 0),
                               'total_tokens': usage.get('totalTokenCount', 0)},
                              (data.get('candidates') or [{}])[0].get('finishReason', 'STOP'))
        except ProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
            raise _network_error(e, self.name, self.timeout)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise ProviderError('bad_response', 'Google returned an unreadable generation response.', provider=self.name)

    def chat_stream(self, messages, *, system='', max_tokens=900, temperature=0.3, cancel=None):
        resp = self._request(self._payload(messages, system, max_tokens, temperature), stream=True, cancel=cancel)
        count, start = 0, time.monotonic()
        try:
            with resp:
                for raw in resp:
                    if cancel and cancel():
                        raise ProviderError('cancelled', 'Gemini request cancelled.', provider=self.name)
                    if time.monotonic() - start > 180:
                        raise ProviderError('timeout', 'Gemini stream exceeded 180 seconds.', provider=self.name, retryable=True)
                    line = raw.decode('utf-8', 'replace').strip()
                    if not line.startswith('data:'):
                        continue
                    body = line[5:].strip()
                    if body == '[DONE]':
                        break
                    data = json.loads(body)
                    text = self._text(data)
                    count += len(text)
                    if count > 100000:
                        raise ProviderError('response_too_large', 'Gemini stream exceeded 100,000 characters.', provider=self.name)
                    if text:
                        yield text
                    if any(c.get('finishReason') for c in data.get('candidates', [])):
                        break
            if not count:
                raise ProviderError('empty_response', 'Gemini returned no streaming text. Check the selected model and output budget.', provider=self.name)
        except ProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
            raise _network_error(e, self.name, self.timeout)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ProviderError('bad_response', 'Google returned an unreadable streaming response.', provider=self.name)

    def health(self):
        h = super().health()
        if not h['configured']:
            h.update(reachable=False, error={'code': 'missing_credentials' if h['missing'] else 'provider_disabled',
                     'message': 'Missing Gemini settings or provider disabled.'})
            return h
        try:
            r = self.chat([ChatMessage('user', 'Reply with one word: connected.')], max_tokens=32, temperature=0)
            h.update(reachable=bool(r.text), model_reported=r.model)
        except ProviderError as e:
            h.update(reachable=False, error=e.payload())
        return h
