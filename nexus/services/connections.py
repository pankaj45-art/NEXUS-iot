"""Safe, one-step chat-provider setup. A failed test never replaces working settings."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

from .. import config, db
from ..errors import ApiError
from ..providers import registry
from . import jobs
from ..providers.base import ChatMessage, ProviderError
from ..providers.gemini import DEFAULT_BASE_URL as GEMINI_BASE, DEFAULT_MODEL as GEMINI_MODEL, valid_base_url

CHECKS_KEY = 'ai_connection_checks'
FRESH_SECONDS = 300


def _fingerprint(settings):
    """Private configuration identity; neither the key nor this hash is returned."""
    fields = {k: settings.get(k) for k in ('provider', 'base_url', 'model', 'api_key', 'enabled', 'capabilities', 'timeout', 'max_retries')}
    return hmac.new(config.APP_SECRET, b'nexus.connection.v1\0' + json.dumps(fields, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def last_check(conn, kind='chat'):
    check = (db.get_setting(conn, CHECKS_KEY, {}) or {}).get(kind)
    if not check:
        return None
    current = registry._decrypt(registry.load(conn).get(kind, {}))
    if not hmac.compare_digest(str(check.get('fingerprint', '')), _fingerprint(current)):
        return None
    return {'ok': bool(check['ok']), 'checked_at': check['checked_at'],
            'provider': check['provider'], 'model': check['model'],
            'recent': time.time() - check['checked_at'] < FRESH_SECONDS}


def _base_url(value, provider):
    value = str(value).strip().rstrip('/')
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError:
        raise ApiError(400, 'Enter a valid provider URL and port.', 'invalid_provider_url')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ApiError(400, 'Use a provider base URL without a key, username, query or fragment.', 'invalid_provider_url')
    if provider in ('openai_compatible', 'gemini') and parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ApiError(400, 'Use HTTPS for a remote API-key provider. HTTP is allowed only for local testing or a local Ollama server.', 'insecure_provider_url')
    if value.endswith('/chat/completions'):
        value = value[:-len('/chat/completions')]
    if provider == 'ollama' and value.endswith('/api/chat'):
        value = value[:-len('/api/chat')]
    if provider == 'gemini' and not valid_base_url(value):
        raise ApiError(400, 'Use the Google Gemini endpoint: ' + GEMINI_BASE, 'invalid_provider_url')
    return value


def _prepare(conn, ent, body):
    """Build candidate -> real optional probe -> encrypted atomic save -> safe status.

    The HTTP route enforces admin + CSRF. No credential is ever put into a job,
    message, event, URL, response, audit detail, or browser storage.
    """
    if not ent.get('is_admin'):
        raise ApiError(403, 'Only administrators can change platform API keys.', 'admin_required')
    allowed = {'provider', 'api_key', 'model', 'base_url', 'streaming', 'verify', 'enable_images', 'image_model'}
    if not isinstance(body, dict) or set(body) - allowed:
        raise ApiError(400, 'Unexpected connection setting.', 'invalid_input')
    for key in ('verify', 'streaming', 'enable_images'):
        if key in body and not isinstance(body[key], bool):
            raise ApiError(400, key + ' must be boolean.', 'invalid_input')
    for key in ('provider', 'api_key', 'model', 'base_url', 'image_model'):
        if key in body and not isinstance(body[key], str):
            raise ApiError(400, key + ' must be text.', 'invalid_input')
    current = registry._decrypt(registry.load(conn)['chat'])
    secret = body.get('api_key', '').strip()
    if secret.lower().startswith('bearer '):
        secret = secret[7:].strip()
    if len(secret) > 4096 or any(c.isspace() or ord(c) < 32 for c in secret):
        raise ApiError(400, 'Paste only the API key, not a JSON object or a multiline header.', 'invalid_api_key')
    provider = body.get('provider') or ('openai_compatible' if secret else current.get('provider', 'none'))
    if provider not in ('openai_compatible', 'gemini', 'ollama'):
        raise ApiError(400, 'Choose Google Gemini, OpenAI / a compatible API, or Ollama, to enable online AI.', 'provider_required')
    same = provider == current.get('provider')
    base = body.get('base_url') or (current.get('base_url') if same else '') or (config.OLLAMA_BASE_URL if provider == 'ollama' else GEMINI_BASE if provider == 'gemini' else 'https://api.openai.com/v1')
    model = (body.get('model') or (current.get('model') if same else '') or ('llama3.2' if provider == 'ollama' else GEMINI_MODEL if provider == 'gemini' else 'gpt-4o-mini')).strip()
    if not model or len(model) > 160 or '\n' in model:
        raise ApiError(400, 'Enter the actual model or deployment ID (up to 160 characters).', 'invalid_model')
    base = _base_url(base, provider)
    same_scope = registry.credential_scope(provider, base) == registry.credential_scope(current.get('provider'), current.get('base_url'))
    key = secret or (current.get('api_key', '') if same_scope else '')
    if provider in ('openai_compatible', 'gemini') and not key:
        raise ApiError(400, 'Paste your provider API key in the API key field. It is encrypted on the server and is never returned.', 'api_key_required')
    if body.get('enable_images') and provider != 'openai_compatible':
        raise ApiError(400, 'This chat connection does not activate image generation. Configure a separate image provider below.', 'unsupported_capability')
    image_model = str(body.get('image_model') or 'gpt-image-1').strip()
    if body.get('enable_images') and (not image_model or len(image_model) > 160):
        raise ApiError(400, 'Enter the actual image model ID.', 'invalid_model')
    caps = dict(registry.DEFAULT_CAPS[provider])
    caps['streaming'] = body.get('streaming', current.get('capabilities', {}).get('streaming', True) if same else True)
    candidate = {'provider': provider, 'model': model, 'base_url': base,
                 'api_key': key, 'enabled': True, 'timeout': 90 if provider == 'gemini' else 25, 'max_retries': 0, 'capabilities': caps}
    expected = {kind: _fingerprint(registry._decrypt(registry.load(conn)[kind]))
                for kind in ('chat', 'image') if kind == 'chat' or body.get('enable_images')}
    return {'candidate': candidate, 'verify': body.get('verify', True),
            'enable_images': bool(body.get('enable_images')), 'image_model': image_model, 'expected': expected}


def _reserve_check(conn, ent, provider):
    conn.execute('BEGIN IMMEDIATE')
    try:
        if db.count_usage(conn, ent['user_id'], 'provider_check', 3600) >= 20:
            raise ApiError(429, 'Connection-test limit reached (20 per hour). Retry later.', 'limit_reached')
        db.record_usage(conn, ent['user_id'], 'provider_check', meta={'provider': provider})
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise


def _apply(conn, ent, plan, cancel=None):
    if not ent.get('is_admin'):
        raise ApiError(403, 'Only administrators can change platform API keys.', 'admin_required')
    candidate, verify = plan['candidate'], plan['verify']
    provider, key, caps = candidate['provider'], candidate['api_key'], candidate['capabilities']
    model = candidate['model']
    image_model = plan['image_model']
    if verify:
        _reserve_check(conn, ent, provider)
        # This is a real call with the candidate credential, before any settings
        # are changed. Never mistake a configured flag for successful access.
        try:
            adapter = registry.PROVIDERS[provider](candidate)
            messages = [ChatMessage('user', 'Reply with one word: connected.')]
            options = {'cancel': cancel, 'system': 'This is a connectivity test. Return one brief word.', 'max_tokens': 32, 'temperature': 0}
            if caps['streaming']:
                text = ''.join(adapter.chat_stream(messages, **options)).strip()
                if not text:
                    raise ProviderError('empty_response', 'The model returned no streaming content. Disable streaming for a non-streaming compatible gateway, or check the model ID.', retryable=True, provider=provider)
            else:
                adapter.chat(messages, **options)
        except ProviderError as exc:
            exc.detail = {**exc.detail, 'saved': False, 'previous_configuration_preserved': True}
            if key:
                exc.message = exc.message.replace(key, '[REDACTED]')
            db.audit(conn, ent['user_id'], 'admin.ai_connect_failed', 'chat', {'code': exc.code})
            raise
    patch = {'chat': {**candidate, 'max_retries': 1}}
    # Explicit opt-in only. Chat access does not prove image-model entitlement.
    if plan['enable_images']:
        patch['image'] = {'provider': 'openai_compatible', 'base_url': candidate['base_url'],
                          'model': image_model, 'api_key': key, 'enabled': True, 'timeout': 90, 'max_retries': 0}
    if cancel and cancel():
        raise ProviderError('cancelled', 'Connection check cancelled; settings were not changed.', provider=provider)
    conn.execute('BEGIN IMMEDIATE')
    try:
        if cancel and cancel():
            raise ProviderError('cancelled', 'Connection check cancelled; settings were not changed.', provider=provider)
        if not jobs.current_ent(conn, ent['user_id']).get('is_admin'):
            raise ApiError(403, 'Administrator access was removed; settings were not changed.', 'admin_required')
        for kind, expected in plan['expected'].items():
            current = _fingerprint(registry._decrypt(registry.load(conn)[kind]))
            if not hmac.compare_digest(current, expected):
                raise ProviderError('configuration_changed', 'Settings changed while the test was running. The newer settings were preserved.', provider=provider)
        registry.save(conn, patch)
        checks = db.get_setting(conn, CHECKS_KEY, {}) or {}
        checks.pop('chat', None)
        if verify:
            actual = registry._decrypt(registry.load(conn)['chat'])
            checks['chat'] = {'fingerprint': _fingerprint(actual), 'ok': True, 'checked_at': time.time(),
                              'provider': provider, 'model': model}
        db.set_setting(conn, CHECKS_KEY, checks)
        db.audit(conn, ent['user_id'], 'admin.ai_connected' if verify else 'admin.ai_connection_saved', 'chat',
                 {'provider': provider, 'verified': verify, 'images_configured': plan['enable_images']})
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    return {'ok': True, 'saved': True, 'connected': verify, 'requires_restart': False,
            'last_test': last_check(conn), 'provider': provider, 'model': model,
            'images_configured': plan['enable_images'], 'images_verified': False,
            'message': ('Connected and saved. Online AI is ready. Open AI Assistant to start.' if verify else
                        'Saved securely and enabled. Connectivity is not yet verified; use Save & Connect or Test chat connection.'),
            'image_message': ('Image Studio is configured separately with the selected key/model. Image generation is verified only when a real image request succeeds.' if plan['enable_images'] else
                              'Image generation and web search are optional, separate services. They do not block ordinary chat.')}


def _preserved(exc):
    details = {'saved': False, 'previous_configuration_preserved': True}
    if isinstance(exc, ProviderError):
        exc.detail = {**exc.detail, **details}
    else:
        exc.extra['detail'] = {**exc.extra.get('detail', {}), **details}
    return exc


def connect_chat(conn, ent, body):
    """Backward-compatible synchronous API; the SPA uses start_chat instead."""
    try:
        return _apply(conn, ent, _prepare(conn, ent, body))
    except (ApiError, ProviderError) as e:
        raise _preserved(e)


def start_chat(conn, ent, body):
    """Return 202 immediately; candidate secrets stay in worker RAM, not jobs.

    The job stores only states, typed errors and safe completion metadata. A
    restart interrupts the check, notifies the user, and leaves saved keys alone.
    """
    try:
        plan = _prepare(conn, ent, body)
        if not plan['verify']:
            raise ApiError(400, 'Use the save-only endpoint to save without a test.', 'invalid_input')
        def run(c, fresh, jid):
            try:
                jobs.event(c, jid, 'status', {'state': 'testing', 'provider': plan['candidate']['provider'], 'model': plan['candidate']['model']})
                return _apply(c, fresh, plan, cancel=lambda: jobs.cancelled(c, jid))
            except (ApiError, ProviderError) as e:
                raise _preserved(e)
            finally:
                plan['candidate']['api_key'] = ''
        jid = jobs.launch(conn, ent, 'provider_connect', run)
        return {'job_id': jid, 'state': 'queued', 'saved': False, 'connected': False,
                'message': 'Connection check started. Settings are activated only after a real model response.'}
    except (ApiError, ProviderError) as e:
        raise _preserved(e)


def start_health(conn, ent):
    if not ent.get('is_admin'):
        raise ApiError(403, 'Administrator access required.', 'admin_required')
    def run(c, fresh, jid):
        if not fresh.get('is_admin'):
            raise ApiError(403, 'Administrator access required.', 'admin_required')
        return registry.health(c, force=True)
    return {'job_id': jobs.launch(conn, ent, 'provider_health', run), 'state': 'queued'}
