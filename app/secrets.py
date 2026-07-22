"""Encryption for secret settings (API keys, tokens).

Hard constraint: secrets live in env vars or the encrypted-at-rest config table,
and are never logged. A per-install NaCl SecretBox key is generated on first boot
under the data dir with 0600 permissions.
"""

import base64
import os
from pathlib import Path

import nacl.secret
import nacl.utils

from app.db import data_dir

_KEY_FILE = "secret.key"


def _load_key() -> bytes:
    path: Path = data_dir() / _KEY_FILE
    if path.exists():
        return base64.b64decode(path.read_bytes())
    key = nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE)
    path.write_bytes(base64.b64encode(key))
    os.chmod(path, 0o600)
    return key


def encrypt(plaintext: str) -> str:
    box = nacl.secret.SecretBox(_load_key())
    return base64.b64encode(box.encrypt(plaintext.encode())).decode()


def decrypt(ciphertext: str) -> str:
    box = nacl.secret.SecretBox(_load_key())
    return box.decrypt(base64.b64decode(ciphertext)).decode()


def mask(secret: str | None) -> str | None:
    """Display form of a secret — never return the raw value to the UI."""
    if not secret:
        return None
    if len(secret) <= 8:
        return "•" * len(secret)
    return f"{secret[:4]}…{secret[-4:]}"
