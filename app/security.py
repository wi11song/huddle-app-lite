"""Password and edit-token helpers built from the Python standard library."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
PASSWORD_SALT_BYTES = 16
EDIT_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Hash a password with a random salt and encoded scrypt parameters."""
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _encode_bytes(salt),
            _encode_bytes(digest),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password, returning false for malformed stored hashes."""
    try:
        algorithm, encoded_n, encoded_r, encoded_p, encoded_salt, encoded_digest = (
            encoded_hash.split("$")
        )
        if algorithm != "scrypt":
            return False

        expected_digest = _decode_bytes(encoded_digest)
        actual_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode_bytes(encoded_salt),
            n=int(encoded_n),
            r=int(encoded_r),
            p=int(encoded_p),
            dklen=len(expected_digest),
        )
    except (binascii.Error, TypeError, ValueError):
        return False

    return hmac.compare_digest(actual_digest, expected_digest)


def create_edit_token() -> str:
    """Create a high-entropy token safe for JSON and local storage."""
    return secrets.token_urlsafe(EDIT_TOKEN_BYTES)


def hash_edit_token(edit_token: str) -> str:
    """Return the one-way representation stored for an edit token."""
    return hashlib.sha256(edit_token.encode("utf-8")).hexdigest()


def verify_edit_token(edit_token: str, stored_hash: str) -> bool:
    """Compare an edit token with a stored hash in constant time."""
    return hmac.compare_digest(hash_edit_token(edit_token), stored_hash)


def _encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        value + padding,
        altchars=b"-_",
        validate=True,
    )
