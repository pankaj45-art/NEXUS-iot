"""Security primitives: password hashing, sessions, CSRF, secret encryption.

Uses only the Python standard library.  Passwords are PBKDF2-HMAC-SHA256
with a per-user random salt; session tokens are random 256-bit values stored
only as SHA-256 digests; admin-entered API keys are encrypted at rest with an
HMAC-SHA256 based authenticated stream cipher keyed by the app secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any

from . import config


def pbkdf2(password: str, salt: bytes | None = None, iterations: int | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    iterations = iterations or config.PBKDF2_ITERATIONS
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_hex, digest_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def validate_password_policy(password: str) -> str | None:
    """Return an error message, or None when the password is acceptable."""
    if not isinstance(password, str) or len(password) < 10:
        return "Password must be at least 10 characters long."
    if len(password) > 200:
        return "Password is too long."
    if not any(c.islower() for c in password) or not any(c.isupper() for c in password):
        return "Password must contain both upper and lower case letters."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    return None


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(str(a), str(b))


def _keystream(nonce: bytes, length: int, key: bytes | None = None) -> bytes:
    key = key or config.APP_SECRET
    out = bytearray()
    counter = 0
    while len(out) < length:
        msg = nonce + counter.to_bytes(8, "big")
        out.extend(hmac.new(key, msg, hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plaintext: str) -> str:
    """Authenticated encryption of a small secret (API keys, tokens)."""
    if not plaintext:
        return ""
    raw = plaintext.encode("utf-8")
    nonce = secrets.token_bytes(16)
    # Versioned domain-separated encryption/MAC subkeys. Legacy encrypted
    # settings remain readable; new values never reuse the same HMAC domain.
    enc_key = hmac.new(config.APP_SECRET, b'nexus.secret.enc.v2', hashlib.sha256).digest()
    mac_key = hmac.new(config.APP_SECRET, b'nexus.secret.mac.v2', hashlib.sha256).digest()
    stream = _keystream(nonce, len(raw), enc_key)
    ciphertext = bytes(a ^ b for a, b in zip(raw, stream))
    mac = hmac.new(mac_key, b'v2\0' + nonce + ciphertext, hashlib.sha256).digest()
    return "v2." + base64.urlsafe_b64encode(nonce + mac + ciphertext).decode("ascii")


def decrypt_secret(blob: str) -> str:
    if not blob:
        return ""
    try:
        modern=blob.startswith('v2.')
        data = base64.urlsafe_b64decode((blob[3:] if modern else blob).encode("ascii"))
        if len(data)<48: raise ValueError('truncated')
        nonce, mac, ciphertext = data[:16], data[16:48], data[48:]
        mac_key=hmac.new(config.APP_SECRET,b'nexus.secret.mac.v2',hashlib.sha256).digest() if modern else config.APP_SECRET
        expected = hmac.new(mac_key, (b'v2\0' if modern else b'') + nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("bad mac")
        enc_key=hmac.new(config.APP_SECRET,b'nexus.secret.enc.v2',hashlib.sha256).digest() if modern else config.APP_SECRET
        stream = _keystream(nonce, len(ciphertext),enc_key)
        return bytes(a ^ b for a, b in zip(ciphertext, stream)).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - never leak details to callers
        raise ValueError("Stored secret could not be decrypted") from exc


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "…" + value[-4:]


def sign_cookie(value: str) -> str:
    sig = hmac.new(config.APP_SECRET, value.encode(), hashlib.sha256).hexdigest()[:32]
    return value + "." + sig


def verify_cookie(signed: str) -> str | None:
    if not signed or "." not in signed:
        return None
    value, sig = signed.rsplit(".", 1)
    expected = hmac.new(config.APP_SECRET, value.encode(), hashlib.sha256).hexdigest()[:32]
    return value if hmac.compare_digest(sig, expected) else None


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def redact(obj: Any) -> Any:
    """Remove sensitive keys before anything is logged or returned."""
    sensitive = {"password", "api_key", "apikey", "secret", "token", "authorization",
                 "stripe_secret_key", "webhook_secret", "password_hash", "csrf"}
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in sensitive else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def random_device_token() -> str:
    return "nxd_" + secrets.token_urlsafe(24)
