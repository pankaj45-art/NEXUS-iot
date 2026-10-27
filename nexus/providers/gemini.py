"""Native Google Gemini generateContent + SSE; no OpenAI account or SDK.

Legacy /v1beta/openai configuration URLs remain accepted and are mapped to
Google's native /v1beta endpoint. Keys are sent only in x-goog-api-key headers.
"""
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from .base import ChatProvider, ChatResult, ProviderError, ChatMessage
from .openai_compat import NoRedirect, _error_from_http, _network_error

DEFAULT_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta'
DEFAULT_MODEL = 'gemini-3.5-flash-lite'


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
        model = quote(self.model.removeprefix('models/'), safe='-._')
        url = base + '/models/' + model + (':streamGenerateContent?alt=sse' if stream else ':generateContent')
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': self.api_key,
                   'Accept': 'text/event-stream' if stream else 'application/json'}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        last = None
        for attempt in range(self.max_retries + 1):
            try:
                return urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())).open(req, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                last = _error_from_http(exc, self.name)
                if exc.code == 400 and any(x in last.message.lower() for x in ('api key', 'api_key')):
                    last.code, last.retryable = 'auth_failed', False
                last.message = last.message.replace(self.api_key, '[REDACTED]')
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
        if model.startswith(('gemini-2.5', 'gemini-3', 'gemini-4')):
            generation['thinkingConfig'] = {'thinkingBudget': 1024} if model.startswith('gemini-2.5') else {'thinkingLevel': 'LOW'}
            generation['maxOutputTokens'] = min(65536, max(256, int(max_tokens)) + 1024)
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
