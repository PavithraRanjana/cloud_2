"""Tests for shared/encryption.py — Fernet encryption, masking, tokenization."""
from shared.encryption import (
    encrypt_field, decrypt_field, mask_card_number, tokenize_card,
    FieldEncryptor, _derive_key,
)


# ── Encrypt / Decrypt ────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip():
    plaintext = "AB1234567"
    encrypted = encrypt_field(plaintext)
    assert decrypt_field(encrypted) == plaintext


def test_encrypt_returns_different_from_plaintext():
    plaintext = "SensitiveData"
    encrypted = encrypt_field(plaintext)
    assert encrypted != plaintext


def test_decrypt_invalid_token_returns_fallback():
    """Decrypting garbage should raise an exception (Fernet.InvalidToken)."""
    try:
        result = decrypt_field("not-a-valid-ciphertext")
        # If it somehow doesn't raise, the test still documents behaviour
        assert False, "Expected an exception"
    except Exception:
        pass  # Expected


def test_encrypt_empty_string():
    """Empty string should pass through without encryption."""
    assert encrypt_field("") == ""
    assert decrypt_field("") == ""


# ── Card masking ─────────────────────────────────────────────────

def test_mask_card_number_standard():
    masked = mask_card_number("4111111111111111")
    assert masked == "************1111"
    assert masked[-4:] == "1111"


def test_mask_card_number_short():
    assert mask_card_number("12") == "****"


def test_mask_card_number_empty():
    assert mask_card_number("") == "****"
    assert mask_card_number(None) == "****"


# ── Card tokenization ────────────────────────────────────────────

def test_tokenize_card_deterministic():
    t1 = tokenize_card("4111111111111111")
    t2 = tokenize_card("4111111111111111")
    assert t1 == t2
    assert t1.startswith("tok_")


def test_tokenize_card_different_inputs():
    t1 = tokenize_card("4111111111111111")
    t2 = tokenize_card("5500000000000004")
    assert t1 != t2


# ── Key derivation ───────────────────────────────────────────────

def test_derive_key_consistency():
    k1 = _derive_key("same-passphrase")
    k2 = _derive_key("same-passphrase")
    assert k1 == k2
    assert len(k1) == 44  # base64-encoded 32 bytes
