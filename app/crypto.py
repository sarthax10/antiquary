"""Symmetric encryption for third-party credentials at rest (SocialAccount's access/
refresh tokens) — real access to a user's YouTube/Instagram account, meaningfully more
sensitive than anything else this app stores, so unlike password_hash (one-way) these
need to be reversible but still never sit in plaintext in the database.

TOKEN_ENCRYPTION_KEY must be a Fernet key (urlsafe-base64, 32 bytes). Generate one with:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    return Fernet(os.environ["TOKEN_ENCRYPTION_KEY"].encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
