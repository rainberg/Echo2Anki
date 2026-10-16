import pytest

from app.crypto import encrypt_credential, decrypt_credential


class TestEncryptDecrypt:
    def test_roundtrip_ascii(self):
        plain = "my-secret-password"
        encrypted = encrypt_credential(plain)
        assert encrypted != plain
        decrypted = decrypt_credential(encrypted)
        assert decrypted == plain

    def test_roundtrip_unicode(self):
        plain = "密码123!@#"
        encrypted = encrypt_credential(plain)
        assert encrypted != plain
        decrypted = decrypt_credential(encrypted)
        assert decrypted == plain

    def test_roundtrip_long_string(self):
        plain = "A" * 1000
        encrypted = encrypt_credential(plain)
        decrypted = decrypt_credential(encrypted)
        assert decrypted == plain

    def test_roundtrip_empty_string(self):
        encrypted = encrypt_credential("")
        assert encrypted == ""
        decrypted = decrypt_credential("")
        assert decrypted == ""

    def test_encryption_is_deterministic_per_iv(self):
        plain = "test-password"
        encrypted1 = encrypt_credential(plain)
        encrypted2 = encrypt_credential(plain)
        assert encrypted1 != encrypted2

    def test_encrypted_is_base64(self):
        import base64
        encrypted = encrypt_credential("test")
        try:
            base64.b64decode(encrypted)
        except Exception:
            pytest.fail("Encrypted output is not valid base64")

    def test_tampered_ciphertext_raises(self):
        encrypted = encrypt_credential("test-password")
        tampered = encrypted[:-4] + "AAAA"
        with pytest.raises(Exception):
            decrypt_credential(tampered)

    def test_special_characters(self):
        plain = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        encrypted = encrypt_credential(plain)
        decrypted = decrypt_credential(encrypted)
        assert decrypted == plain

    def test_newlines(self):
        plain = "line1\nline2\r\nline3"
        encrypted = encrypt_credential(plain)
        decrypted = decrypt_credential(encrypted)
        assert decrypted == plain