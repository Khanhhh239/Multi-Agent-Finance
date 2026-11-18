"""Signed immutable training envelopes; no plaintext training fields on cloud APIs."""
import base64
import hashlib
import json
import re
from . import VERSION, TARGET, PROFILE, SUPPORTED_PROFILES
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_PACKET = 24 * 1024 * 1024
ID = re.compile(r'[A-Za-z0-9_.-]{1,100}\Z')


class TrainingError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(ok, code):
    if not ok:
        raise TrainingError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def unique(items):
        result = {}
        for k, v in items:
            require(k not in result, 'DUPLICATE_FIELD')
            result[k] = v
        return result
    require(len(raw) <= MAX_PACKET, 'PACKET_LIMIT')
    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(TrainingError('NONFINITE_JSON')),
    )


def sign(value, key):
    return dict(payload=value, signature=key.sign(canonical(value)).hex())


def verify(packet, key):
    require(isinstance(packet, dict) and set(packet) == {'payload', 'signature'}, 'ENVELOPE_FIELDS')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(
            bytes.fromhex(packet['signature']),
            canonical(packet['payload']),
        )
    except Exception as error:
        raise TrainingError('SIGNATURE_INVALID') from error
    return packet['payload']


def encode(raw):
    return base64.b64encode(raw).decode('ascii')


def decode(value):
    require(isinstance(value, str) and 0 < len(value) <= MAX_PACKET, 'CIPHERTEXT_LIMIT')
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as error:
        raise TrainingError('CIPHERTEXT_ENCODING') from error
    require(0 < len(raw) <= MAX_PACKET, 'CIPHERTEXT_LIMIT')
    return raw


def fields(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected), 'REQUEST_FIELDS')


def common(value, *, expected_profile=PROFILE):
    if value.get('profile') in SUPPORTED_PROFILES and value.get('profile') != expected_profile:
        raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
    require(
        value['version'] == VERSION and value['profile'] == expected_profile and value['target'] == TARGET,
        'CONTRACT_MISMATCH',
    )
    for k in ('tenant_id', 'company_id', 'key_epoch', 'dataset_id'):
        require(isinstance(value[k], str) and ID.fullmatch(value[k]), 'IDENTITY_INVALID')


def blob(value, name):
    raw = decode(value[name])
    require(sha(raw) == value[name + '_sha256'], 'CIPHERTEXT_HASH')
    return raw


def atomic(path, raw):
    import os, uuid
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.pending-' + uuid.uuid4().hex)
    with temp.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
