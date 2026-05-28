"""At-rest encryption for stored secrets (Fernet / AES-128-CBC + HMAC).

Used for per-tenant channel-sending credentials (e.g. ICS WABA passwords)
persisted in Mongo. The key comes from env ``CHANNEL_CRED_KEY`` — a Fernet key
(generate with ``python -c "from cryptography.fernet import Fernet;
print(Fernet.generate_key().decode())"``).

Contract:
- ``encrypt_secret`` RAISES if no key is configured, so a plaintext credential
  is never persisted by accident.
- ``decrypt_secret`` returns None on a missing key or an undecryptable token
  (e.g. key rotated/unset), so callers degrade gracefully to env defaults
  rather than crashing the hot path.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _key() -> Optional[bytes]:
    k = os.environ.get("CHANNEL_CRED_KEY", "").strip()
    return k.encode() if k else None


def is_configured() -> bool:
    """True when a key is set so callers can fail fast before collecting a secret."""
    return _key() is not None


def encrypt_secret(plaintext: str) -> str:
    """Fernet-encrypt a secret for at-rest storage. Raises RuntimeError if no
    key is configured — we must never persist a plaintext credential."""
    from cryptography.fernet import Fernet

    key = _key()
    if not key:
        raise RuntimeError(
            "CHANNEL_CRED_KEY is not set — refusing to store a channel credential "
            "in plaintext. Set CHANNEL_CRED_KEY (a Fernet key) in the environment."
        )
    return Fernet(key).encrypt((plaintext or "").encode()).decode()


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    """Decrypt a stored secret. Returns None on a missing key or an invalid
    token (caller falls back to env credentials)."""
    if not token:
        return None
    key = _key()
    if not key:
        logger.warning("CHANNEL_CRED_KEY not set — cannot decrypt a stored channel credential.")
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(token.encode()).decode()
    except Exception as e:
        logger.warning("channel credential decrypt failed: %s", type(e).__name__)
        return None
