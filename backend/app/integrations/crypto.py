"""Encryption for third-party credentials.

OAuth tokens are the one thing in this database that grants access to systems
outside it. They are encrypted at rest with a key derived from `SECRET_KEY`, so
a database dump on its own does not hand over anyone's mailbox or calendar.

Derivation is deterministic (HKDF over the app secret with a fixed salt) so the
same deployment can always decrypt what it wrote, and rotating `SECRET_KEY`
deliberately invalidates every stored token rather than silently keeping them
readable.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_INFO = b"express-os:integration-token:v1"


def _key() -> bytes:
    digest = hashlib.pbkdf2_hmac("sha256", settings.SECRET_KEY.encode(), _INFO, 200_000, dklen=32)
    return base64.urlsafe_b64encode(digest)


def encrypt(plaintext: str | None) -> str | None:
    if not plaintext:
        return None
    return Fernet(_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """Returns None rather than raising when a value can't be read.

    An unreadable token means the secret changed; the caller should treat that
    as "not connected" and ask the user to reconnect, not crash a page.
    """
    if not ciphertext:
        return None
    try:
        return Fernet(_key()).decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None
