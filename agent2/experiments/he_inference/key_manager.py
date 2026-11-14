"""Enterprise-local key files. DPAPI current-user protection, never key export."""
import argparse
import base64
import ctypes
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

from .http_common import ServiceError
from .protocol import _object, canonical

PROVIDER = 'windows-dpapi-current-user'
VERSION = 'he-local-key/1.0.0'
PURPOSES = ('state-wrapping', 'node-signing')


@dataclass(frozen=True)
class LocalKey:
    material: bytes = field(repr=False)
    provider: str
    purpose: str
    key_id: str

    def public_info(self):
        value = dict(provider=self.provider, purpose=self.purpose, key_id=self.key_id, usable=True)
        if self.purpose == 'node-signing':
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            value['verify_key'] = Ed25519PrivateKey.from_private_bytes(self.material).public_key().public_bytes_raw().hex()
        return value


def key_id(raw, purpose):
    return 'key_' + hashlib.sha256(purpose.encode() + b'\x00' + raw).hexdigest()


def dpapi(raw, purpose, *, decrypt=False):
    if os.name != 'nt':
        raise ServiceError(503, 'NODE_KEY_PROVIDER_UNAVAILABLE')
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

    source_buffer = ctypes.create_string_buffer(raw)
    entropy_raw = b'Agent2:enterprise-local-key:v1:' + purpose.encode('ascii')
    entropy_buffer = ctypes.create_string_buffer(entropy_raw)
    source = Blob(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy = Blob(len(entropy_raw), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]; kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.POINTER(wintypes.LPWSTR) if decrypt else wintypes.LPCWSTR,
                         ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    try:
        # UI_FORBIDDEN only. Never use CRYPTPROTECT_LOCAL_MACHINE, which would
        # permit other users on the same host to unprotect this key.
        if not function(ctypes.byref(source), None if decrypt else 'Agent2 enterprise local key',
                        ctypes.byref(entropy), None, None, 1, ctypes.byref(output)):
            raise ServiceError(503, 'NODE_KEY_UNPROTECT_FAILED' if decrypt else 'NODE_KEY_PROTECT_FAILED')
        if not 0 < output.cbData <= 8192:
            raise ServiceError(503, 'NODE_KEY_BLOB_INVALID')
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if output.pbData:
            ctypes.memset(output.pbData, 0, output.cbData)
            kernel.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
        ctypes.memset(source_buffer, 0, ctypes.sizeof(source_buffer))
        ctypes.memset(entropy_buffer, 0, ctypes.sizeof(entropy_buffer))


def _json(raw):
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def load_key(path, *, purpose='state-wrapping', required_provider=None):
    if purpose not in PURPOSES:
        raise ServiceError(503, 'NODE_KEY_PURPOSE_INVALID')
    try:
        with open(path, 'rb') as stream:
            raw = stream.read(16385).strip()
    except OSError as exc:
        raise ServiceError(503, 'NODE_STATE_KEY_REQUIRED') from exc
    if len(raw) > 16384:
        raise ServiceError(503, 'NODE_KEY_FILE_LIMIT')
    if re.fullmatch(b'[a-f0-9]{64}', raw):
        if required_provider is not None and required_provider != 'legacy-hex':
            raise ServiceError(503, 'NODE_KEY_PROTECTION_REQUIRED')
        material = bytes.fromhex(raw.decode())
        return LocalKey(material, 'legacy-hex', purpose, key_id(material, purpose))
    try:
        value = _json(raw)
        if (not isinstance(value, dict) or set(value) != {'version', 'provider', 'purpose', 'key_id', 'protected'}
                or value['version'] != VERSION or value['provider'] != PROVIDER
                or value['purpose'] != purpose or required_provider not in (None, PROVIDER)
                or not isinstance(value['protected'], str) or len(value['protected']) > 12000):
            raise ValueError()
        protected = base64.b64decode(value['protected'], validate=True)
        private = _json(dpapi(protected, purpose, decrypt=True))
        if not isinstance(private, dict) or set(private) != {'version', 'purpose', 'material'} or private['version'] != VERSION or private['purpose'] != purpose:
            raise ValueError()
        material = base64.b64decode(private['material'], validate=True)
        if len(material) != 32 or not hmac.compare_digest(key_id(material, purpose), value['key_id']):
            raise ValueError()
        return LocalKey(material, PROVIDER, purpose, value['key_id'])
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError(503, 'NODE_KEY_FILE_INVALID') from exc


def protect_key(material, destination, *, purpose='state-wrapping'):
    if not isinstance(material, bytes) or len(material) != 32 or purpose not in PURPOSES:
        raise ServiceError(503, 'NODE_KEY_MATERIAL_INVALID')
    inner = canonical(dict(version=VERSION, purpose=purpose, material=base64.b64encode(material).decode()))
    protected = dpapi(inner, purpose)
    # Verify under the current user before publishing any new key file.
    if not hmac.compare_digest(dpapi(protected, purpose, decrypt=True), inner):
        raise ServiceError(503, 'NODE_KEY_ROUNDTRIP_FAILED')
    envelope = dict(version=VERSION, provider=PROVIDER, purpose=purpose, key_id=key_id(material, purpose),
                    protected=base64.b64encode(protected).decode())
    path = Path(destination).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.protected-key-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(envelope)); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic and never overwrite an existing key.
    finally:
        Path(temporary).unlink(missing_ok=True)
    return LocalKey(material, PROVIDER, purpose, envelope['key_id'])


def create_key(destination, *, purpose='state-wrapping'):
    return protect_key(secrets.token_bytes(32), destination, purpose=purpose)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('create', 'protect', 'inspect'))
    parser.add_argument('--purpose', choices=PURPOSES, default='state-wrapping')
    parser.add_argument('--input'); parser.add_argument('--output')
    args = parser.parse_args()
    try:
        if args.mode == 'create':
            if not args.output:
                raise ValueError()
            result = create_key(args.output, purpose=args.purpose)
        elif args.mode == 'protect':
            if not args.input or not args.output:
                raise ValueError()
            original = load_key(args.input, purpose=args.purpose)
            result = protect_key(original.material, args.output, purpose=args.purpose)
        else:
            if not args.input:
                raise ValueError()
            result = load_key(args.input, purpose=args.purpose)
        print(json.dumps(result.public_info(), ensure_ascii=False))
        return 0
    except (ServiceError, OSError, ValueError) as exc:
        print(getattr(exc, 'code', 'NODE_KEY_COMMAND_FAILED'))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
