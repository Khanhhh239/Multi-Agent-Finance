import json, re, base64
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag
from agent1.adaptive.training_report import encrypt_report


def test_report_is_encrypted_and_wrong_password_fails():
    html = encrypt_report(
        {"selected_method": "secret-model", "train_n": 1234}, "test-secret"
    )
    assert "secret-model" not in html and "test-secret" not in html
    packed = json.loads(re.search(r"const encrypted=(.*);", html).group(1))
    b = {k: base64.b64decode(v) for k, v in packed.items()}

    def decrypt(password):
        key = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=b["salt"], iterations=600000
        ).derive(password.encode())
        return AESGCM(key).decrypt(b["nonce"], b["ciphertext"], None)

    assert json.loads(decrypt("test-secret"))["train_n"] == 1234
    with pytest.raises(InvalidTag):
        decrypt("wrong")
