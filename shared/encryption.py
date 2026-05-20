"""
Field-level encryption for PII and PCI-sensitive data.
Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
In production, set ENCRYPTION_KEY env var (any passphrase; use Secrets Manager).
"""
import base64
import hashlib
import os
import warnings
from cryptography.fernet import Fernet

_DEFAULT_PASSPHRASE = "aerolink-encryption-key-change-in-production"
_passphrase = os.environ.get("ENCRYPTION_KEY", "")
if not _passphrase:
    warnings.warn(
        "ENCRYPTION_KEY env var is not set — using insecure default passphrase. "
        "Set ENCRYPTION_KEY in production.",
        stacklevel=1,
    )
    _passphrase = _DEFAULT_PASSPHRASE


def _derive_key(passphrase: str) -> bytes:
    digest = hashlib.sha256(passphrase.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class FieldEncryptor:
    """Encrypts/decrypts individual fields for at-rest protection."""

    def __init__(self, passphrase: str):
        self.fernet = Fernet(_derive_key(passphrase))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string field. Returns base64-encoded ciphertext."""
        if not plaintext:
            return plaintext
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext back to plaintext."""
        if not ciphertext:
            return ciphertext
        return self.fernet.decrypt(ciphertext.encode()).decode()


# Singleton instance — key comes from env var at import time
_encryptor = FieldEncryptor(_passphrase)


def encrypt_field(value: str) -> str:
    return _encryptor.encrypt(value)


def decrypt_field(value: str) -> str:
    return _encryptor.decrypt(value)


def mask_card_number(card_number: str) -> str:
    """PCI-DSS: mask card number, keep only last 4 digits."""
    if not card_number or len(card_number) < 4:
        return "****"
    return "*" * (len(card_number) - 4) + card_number[-4:]


def tokenize_card(card_number: str) -> str:
    """
    PCI-DSS tokenization: generate a token representing the card.
    In production, this would call Stripe/Adyen tokenization API.
    We never store the raw card number.
    """
    if not card_number:
        return ""
    digest = hashlib.sha256(card_number.encode()).hexdigest()[:24]
    return f"tok_{digest}"
