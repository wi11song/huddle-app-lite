"""Security helper tests."""

from app.security import (
    create_edit_token,
    hash_edit_token,
    hash_password,
    verify_edit_token,
    verify_password,
)


def test_password_hash_uses_random_salt_and_verifies():
    first_hash = hash_password("meeting-secret")
    second_hash = hash_password("meeting-secret")

    assert first_hash.startswith("scrypt$")
    assert first_hash != second_hash
    assert "meeting-secret" not in first_hash
    assert verify_password("meeting-secret", first_hash)
    assert not verify_password("different-secret", first_hash)


def test_password_verification_rejects_malformed_hashes():
    assert not verify_password("secret", "")
    assert not verify_password("secret", "sha256$not-scrypt")
    assert not verify_password("secret", "scrypt$bad$8$1$salt$digest")
    assert not verify_password("secret", "scrypt$16384$8$1$!$!")


def test_edit_tokens_are_random_and_stored_as_hashes():
    first_token = create_edit_token()
    second_token = create_edit_token()

    assert first_token != second_token
    assert len(first_token) >= 43
    assert hash_edit_token(first_token) != first_token
    assert hash_edit_token(first_token) == hash_edit_token(first_token)
    assert verify_edit_token(first_token, hash_edit_token(first_token))
    assert not verify_edit_token(second_token, hash_edit_token(first_token))
