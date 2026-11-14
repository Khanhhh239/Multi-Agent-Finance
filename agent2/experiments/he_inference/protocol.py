"""Bounded, authenticated envelopes. Signatures do not prove correct computation."""
import base64
import hashlib
import json
import math
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = 'he-inference/0.1.0'
PROFILE = 'experimental-ckks-mahalanobis-2d/1.0.0'
CONTRACT = 'experimental-numeric-pair/1.0.0'
MAX_ROWS = 8
MAX_PACKET = 16 * 1024 * 1024
MAX_CONTEXT = 3 * 1024 * 1024
MAX_CIPHER = 1024 * 1024
MAX_NORMALIZED = 8.0
MAX_WEIGHT = 64.0
ABS_TOLERANCE = 1e-3
REL_TOLERANCE = 1e-5
PAIRS = ((0, 0), (0, 1), (1, 1))
BINDING = ('version', 'profile', 'contract', 'tenant_id', 'company_id',
           'session_id', 'model_id', 'key_epoch', 'context_sha256')


class HEUnavailable(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise HEUnavailable(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(',', ':')).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_FIELD')
        result[key] = value
    return result


def read_json(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_PACKET + 1)
    require(len(raw) <= MAX_PACKET, 'PACKET_TOO_LARGE')
    try:
        return json.loads(raw, object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(HEUnavailable('NONFINITE_JSON')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HEUnavailable('INVALID_JSON') from exc


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


def unb64(value, maximum):
    require(isinstance(value, str) and 0 < len(value) <= 4 * ((maximum + 2) // 3), 'BLOB_SIZE')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise HEUnavailable('INVALID_BASE64') from exc
    require(0 < len(raw) <= maximum, 'BLOB_SIZE')
    return raw


def sign(payload, key):
    return dict(payload=payload, signature=key.sign(canonical(payload)).hex())


def verify(packet, public_hex):
    require(isinstance(packet, dict) and set(packet) == {'payload', 'signature'}, 'ENVELOPE_FIELDS')
    try:
        signature = bytes.fromhex(packet['signature'])
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(signature, canonical(packet['payload']))
    except Exception as exc:
        raise HEUnavailable('SIGNATURE_INVALID') from exc
    require(isinstance(packet['payload'], dict), 'PAYLOAD_TYPE')
    require(len(canonical(packet)) <= MAX_PACKET, 'PACKET_TOO_LARGE')
    return packet['payload']


def public_hex(key):
    return key.public_key().public_bytes_raw().hex()


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,96}', value) is not None


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)
