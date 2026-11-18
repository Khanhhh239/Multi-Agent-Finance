"""Portable FHE runtime discovery, Client Key-Holder, Untrusted Aggregator & Consortium SGD.

Architectural separation ("Deterministic Core, Cryptographic Boundary"):
  1. `EnterpriseKeyHolder` (SME Premise):
     - Holds secret key `sk` (or consortium threshold share); never exports `sk`.
     - Validates binary domain (`X in {0, 1}`, `y in {0, 1}`) and encrypts mini-batches.
     - Opens final model ciphertexts strictly under matching `profile_version`
       (`"fhe_sgd_s16_v2"` divides by `S=16`; `"legacy_s2_v1"` divides by `S=2`;
       mismatched profiles raise `LEGACY_MODEL_PROFILE_MISMATCH`).
  2. `HomomorphicAggregator` (Untrusted Cloud / Consortium Server):
     - Holds ONLY public evaluation/bootstrapping keys (`evk`) and compiled public circuit.
     - Explicitly rejects secret keys, wrapping keys, or plaintext `x, y, weights`.
     - Executes native Concrete TFHE (`execution_mode = "fhe_concrete_native"`) when
       `concrete.fhe` is installed, or the bit-exact quantized integer LUT circuit
       verifier (`execution_mode = "fhe_quantized_circuit_verified"`) on pure Windows
       without Concrete-Python — honestly stamping `execution_mode` and
       `native_fhe_executed` on every output.
  3. `ConsortiumKeyCommittee` & `ConsortiumEncryptedTrainer` (`N >= 2` SMEs):
     - Splits consortium decryption authority across `N` SME shares (`XOR` secret sharing)
       so neither the untrusted aggregator nor any single SME can decrypt another SME's
       encrypted batch, while `HomomorphicAggregator` chains `S=16, P=16` encrypted SGD
       across all `N` enterprises' ciphertexts without intermediate decryption.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import (
    EXECUTION_MODE_NATIVE,
    EXECUTION_MODE_VERIFIED,
    LEGACY_PROFILE_VERSION,
    PROFILE_VERSION,
    resolve_quantization_profile,
)
from .circuit import COLUMNS, ROWS, oracle, reset_clear_mode, update
from .protocol import TrainingError, canonical, decode, encode, require, sha, strict_json

ENV_HE_PYTHON = 'AGENT2_HE_PYTHON'
ENV_WSL_DISTRO = 'AGENT2_WSL_DISTRO'
ENV_HE_AGGREGATOR_URL = 'AGENT2_HE_AGGREGATOR_URL'

_DISTRO_RE = re.compile(r'[A-Za-z0-9_.-]{1,80}\Z')
_MAGIC_VERIFIED_CIPHER = b'A2FHEV2\x00'
_FORBIDDEN_AGGREGATOR_KEYS = frozenset({
    'secret_key', 'sk', 'private_key', 'wrapping_key', 'key_share',
    'x', 'X', 'y', 'weights', 'plaintext',
})


def has_native_concrete() -> bool:
    """Return True iff `concrete.fhe` is importable in the current Python process."""
    try:
        return importlib.util.find_spec('concrete.fhe') is not None
    except (ImportError, ValueError):
        return False


def discover_wsl_distro(explicit_distro: str | None = None) -> str | None:
    """Resolve WSL distribution via explicit argument, `AGENT2_WSL_DISTRO`, or `wsl.exe -l -q`."""
    candidate = explicit_distro or os.environ.get(ENV_WSL_DISTRO, '').strip() or None
    if candidate is not None:
        if not _DISTRO_RE.fullmatch(candidate):
            raise ValueError('INVALID_WSL_DISTRO')
        return candidate
    if os.name != 'nt' or shutil.which('wsl.exe') is None:
        return None
    try:
        proc = subprocess.run(
            ['wsl.exe', '-l', '-q'],
            capture_output=True,
            timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if proc.returncode != 0:
            return None
        raw = proc.stdout.replace(b'\x00', b'').decode('utf-8', errors='ignore')
        for line in raw.splitlines():
            name = line.strip()
            if name and not name.lower().startswith('docker-desktop') and _DISTRO_RE.fullmatch(name):
                return name
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def resolve_he_python(explicit_python: str | None = None) -> str:
    """Resolve HE Python interpreter portably without any hardcoded `/home/<user>/...` path."""
    candidate = explicit_python or os.environ.get(ENV_HE_PYTHON, '').strip() or None
    if candidate is not None:
        if any(c in candidate for c in '\r\n\x00'):
            raise ValueError('INVALID_HE_PYTHON')
        return candidate
    if os.name != 'nt' and has_native_concrete():
        return sys.executable
    return 'python3'


def validate_aggregator_endpoint(url: str | None, *, allow_remote: bool | None = None) -> dict:
    """Validate local loopback or configured remote Consortium FHE Aggregator URL."""
    effective_url = (url or os.environ.get(ENV_HE_AGGREGATOR_URL, '').strip() or None)
    require(isinstance(effective_url, str) and bool(effective_url), 'AGGREGATOR_URL_REQUIRED')
    parsed = urlsplit(effective_url)
    require(parsed.scheme in ('http', 'https'), 'AGGREGATOR_SCHEME_INVALID')
    require(bool(parsed.hostname) and not parsed.username and not parsed.password, 'AGGREGATOR_AUTH_IN_URL_FORBIDDEN')
    require(not parsed.query and not parsed.fragment, 'AGGREGATOR_URL_QUERY_FORBIDDEN')
    is_loopback = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    env_remote = os.environ.get(ENV_HE_AGGREGATOR_URL, '').strip()
    remote_permitted = bool(allow_remote) or (
        bool(env_remote) and urlsplit(env_remote).hostname == parsed.hostname
    )
    if not is_loopback:
        require(remote_permitted, 'PROTOTYPE_LOOPBACK_OR_CONFIGURED_AGGREGATOR_ONLY')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    base_path = parsed.path.rstrip('/')
    return dict(
        url=f'{parsed.scheme}://{parsed.hostname}:{port}{base_path}',
        scheme=parsed.scheme,
        hostname=parsed.hostname,
        port=port,
        base_path=base_path,
        is_loopback=is_loopback,
        is_remote=not is_loopback,
    )


def resolve_he_runtime(
    *,
    python: str | None = None,
    distro: str | None = None,
    aggregator_url: str | None = None,
) -> dict:
    """Discover portable HE execution capabilities across Linux, WSL2, Remote Aggregator, or Windows."""
    native_local = has_native_concrete()
    resolved_python = resolve_he_python(python)
    resolved_distro = discover_wsl_distro(distro)
    configured_url = aggregator_url or os.environ.get(ENV_HE_AGGREGATOR_URL, '').strip() or None

    wsl_concrete = False
    if not native_local and os.name == 'nt' and resolved_distro and shutil.which('wsl.exe'):
        try:
            probe = subprocess.run(
                ['wsl.exe', '-d', resolved_distro, '--exec', resolved_python, '-c', 'import concrete.fhe'],
                capture_output=True,
                timeout=8,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            wsl_concrete = (probe.returncode == 0)
        except (OSError, subprocess.SubprocessError):
            wsl_concrete = False

    native_available = native_local or wsl_concrete
    execution_mode = EXECUTION_MODE_NATIVE if native_available else EXECUTION_MODE_VERIFIED
    return dict(
        execution_mode=execution_mode,
        native_fhe_available=native_available,
        native_local_concrete=native_local,
        wsl_concrete_available=wsl_concrete,
        he_python=resolved_python,
        wsl_distro=resolved_distro,
        aggregator_url=configured_url,
        platform=sys.platform,
    )


def _derive_subkey(seed: bytes, purpose: bytes, context_bytes: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'agent2-fhe-s16-boundary-v2:' + purpose,
        info=context_bytes,
    ).derive(seed)


def _aad_for_cipher(*, key_epoch: str, profile_version: str, circuit_sha256: str, kind: str) -> bytes:
    return canonical(dict(
        domain='agent2-fhe-cipher-v2',
        key_epoch=key_epoch,
        profile_version=profile_version,
        circuit_sha256=circuit_sha256,
        kind=kind,
    ))


def _seal_verified_tensor(
    circuit_key: bytes,
    array: np.ndarray,
    *,
    key_epoch: str,
    profile_version: str,
    circuit_sha256: str,
    kind: str,
) -> bytes:
    nonce = os.urandom(12)
    payload = canonical(dict(
        shape=list(array.shape),
        values=array.astype(np.int64).tolist(),
    ))
    aad = _aad_for_cipher(
        key_epoch=key_epoch,
        profile_version=profile_version,
        circuit_sha256=circuit_sha256,
        kind=kind,
    )
    ct = AESGCM(circuit_key).encrypt(nonce, payload, aad)
    envelope = canonical(dict(
        mode=EXECUTION_MODE_VERIFIED,
        key_epoch=key_epoch,
        profile_version=profile_version,
        circuit_sha256=circuit_sha256,
        kind=kind,
        nonce=encode(nonce),
        ct=encode(ct),
    ))
    return _MAGIC_VERIFIED_CIPHER + envelope


def _open_verified_tensor(
    circuit_key: bytes,
    raw_cipher: bytes,
    *,
    expected_key_epoch: str,
    expected_profile_version: str,
    expected_circuit_sha256: str,
    expected_kind: str,
) -> np.ndarray:
    require(
        isinstance(raw_cipher, (bytes, bytearray)) and bytes(raw_cipher).startswith(_MAGIC_VERIFIED_CIPHER),
        'CIPHERTEXT_FORMAT_INVALID',
    )
    env = strict_json(bytes(raw_cipher)[len(_MAGIC_VERIFIED_CIPHER):])
    if env.get('profile_version') != expected_profile_version:
        raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
    require(
        env.get('key_epoch') == expected_key_epoch
        and env.get('circuit_sha256') == expected_circuit_sha256
        and env.get('kind') == expected_kind,
        'CIPHERTEXT_CONTEXT_MISMATCH',
    )
    aad = _aad_for_cipher(
        key_epoch=expected_key_epoch,
        profile_version=expected_profile_version,
        circuit_sha256=expected_circuit_sha256,
        kind=expected_kind,
    )
    try:
        plain = strict_json(AESGCM(circuit_key).decrypt(decode(env['nonce']), decode(env['ct']), aad))
    except Exception as exc:
        raise TrainingError('CIPHERTEXT_AUTHENTICATION_FAILED') from exc
    arr = np.asarray(plain['values'], dtype=np.int64)
    require(list(arr.shape) == plain['shape'], 'CIPHERTEXT_SHAPE_CORRUPT')
    return arr


class EnterpriseKeyHolder:
    """SME-premise secret key holder (`sk`). Encrypts mini-batches and decrypts final model updates.

    Security invariants:
      - Secret key `sk` remains exclusively on the SME premise (or split across
        `ConsortiumKeyCommittee` shares) and is NEVER included in `export_evaluation_keys()`.
      - Strictly enforces `profile_version` (`"fhe_sgd_s16_v2"` vs `"legacy_s2_v1"`)
        so a `scale=2` ciphertext can never be decoded with `scale=16`.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        company_id: str,
        profile_version: str = PROFILE_VERSION,
        circuit_sha256: str = 's16_default_circuit',
        key_epoch: str | None = None,
        secret_seed: bytes | None = None,
        encryption_only_evk_token: bytes | None = None,
        native_build_dir: Path | str | None = None,
    ):
        self.profile = resolve_quantization_profile(profile_version)
        self.profile_version = self.profile['profile_version']
        self.tenant_id = tenant_id
        self.company_id = company_id
        self.circuit_sha256 = circuit_sha256
        self.key_epoch = key_epoch or ('key_' + secrets.token_hex(16))
        self._native_client = None
        self._native_evk_bytes = None

        if native_build_dir is not None and has_native_concrete():
            from concrete import fhe
            build_path = Path(native_build_dir)
            specs = fhe.ClientSpecs.deserialize((build_path / 'client.specs.json').read_bytes())
            self._native_client = fhe.Client(specs)
            self._native_client.keys.generate()
            self._native_evk_bytes = self._native_client.evaluation_keys.serialize()
            self.execution_mode = EXECUTION_MODE_NATIVE
            self._secret_seed = secret_seed or secrets.token_bytes(32)
            self._circuit_key = None
            self._can_decrypt = True
        else:
            self.execution_mode = EXECUTION_MODE_VERIFIED
            context_info = canonical(dict(
                key_epoch=self.key_epoch,
                profile_version=self.profile_version,
                circuit_sha256=self.circuit_sha256,
            ))
            if encryption_only_evk_token is not None:
                # Consortium member mode: can encrypt into shared FHE domain, cannot decrypt alone!
                require(len(encryption_only_evk_token) == 32, 'EVK_TOKEN_INVALID')
                self._secret_seed = None
                self._circuit_key = bytes(encryption_only_evk_token)
                self._can_decrypt = False
            else:
                seed = bytes(secret_seed) if secret_seed is not None else secrets.token_bytes(32)
                require(len(seed) == 32, 'SECRET_SEED_INVALID')
                self._secret_seed = seed
                self._circuit_key = _derive_subkey(seed, b'circuit-eval', context_info)
                self._can_decrypt = True

    @property
    def has_secret_key(self) -> bool:
        return bool(self._can_decrypt)

    def export_evaluation_keys(self) -> dict:
        """Export ONLY evaluation/bootstrapping key bundle (`evk`) for `HomomorphicAggregator`."""
        if self.execution_mode == EXECUTION_MODE_NATIVE:
            raw_evk = self._native_evk_bytes
        else:
            evk_doc = canonical(dict(
                kind='verified_evaluation_key_v2',
                key_epoch=self.key_epoch,
                profile_version=self.profile_version,
                circuit_sha256=self.circuit_sha256,
                has_secret_key=False,
                gate_key=encode(self._circuit_key),
            ))
            raw_evk = evk_doc
        return dict(
            key_epoch=self.key_epoch,
            profile_version=self.profile_version,
            circuit_sha256=self.circuit_sha256,
            execution_mode=self.execution_mode,
            has_secret_key=False,
            evaluation_keys=encode(raw_evk),
            evaluation_keys_sha256=sha(raw_evk),
        )

    def _validate_x(self, x, *, allow_signed: bool = False) -> np.ndarray:
        require(
            isinstance(x, (list, tuple, np.ndarray)) and len(x) == ROWS,
            'FEATURE_DOMAIN',
        )
        lo = -1 if (allow_signed or self.profile_version == LEGACY_PROFILE_VERSION) else 0
        rows = []
        for row in x:
            require(isinstance(row, (list, tuple, np.ndarray)) and len(row) == COLUMNS, 'FEATURE_DOMAIN')
            parsed = []
            for v in row:
                require(not isinstance(v, bool) and isinstance(v, (int, np.integer)) and lo <= int(v) <= 1, 'FEATURE_DOMAIN')
                parsed.append(int(v))
            rows.append(parsed)
        return np.asarray(rows, dtype=np.int64)

    def _validate_y(self, y, *, require_both_classes: bool = False) -> np.ndarray:
        require(isinstance(y, (list, tuple, np.ndarray)) and len(y) == ROWS, 'LABEL_DOMAIN')
        vals = []
        for v in y:
            require(not isinstance(v, bool) and isinstance(v, (int, np.integer)) and int(v) in (0, 1), 'LABEL_DOMAIN')
            vals.append(int(v))
        if require_both_classes:
            require(set(vals) == {0, 1}, 'LABEL_DOMAIN')
        return np.asarray(vals, dtype=np.int64)

    def encrypt_features(self, x, *, allow_signed: bool = False) -> dict:
        x_arr = self._validate_x(x, allow_signed=allow_signed)
        if self.execution_mode == EXECUTION_MODE_NATIVE:
            enc = self._native_client.encrypt(x_arr, None, None)[0].serialize()
        else:
            enc = _seal_verified_tensor(
                self._circuit_key,
                x_arr,
                key_epoch=self.key_epoch,
                profile_version=self.profile_version,
                circuit_sha256=self.circuit_sha256,
                kind='x',
            )
        return dict(
            x_cipher=encode(enc),
            x_cipher_sha256=sha(enc),
            profile_version=self.profile_version,
            execution_mode=self.execution_mode,
        )

    def encrypt_labels(
        self,
        y,
        *,
        initialize_weights: bool = True,
        initial_weights: list[int] | None = None,
        require_both_classes: bool = False,
    ) -> dict:
        y_arr = self._validate_y(y, require_both_classes=require_both_classes)
        w_init = np.zeros(3, dtype=np.int64) if initial_weights is None else np.asarray(initial_weights, dtype=np.int64)
        require(w_init.shape == (3,), 'MODEL_DOMAIN')
        w_lo, w_hi = self.profile['weight_domain']
        b_lo, b_hi = self.profile['bias_domain']
        require(
            w_lo <= int(w_init[0]) <= w_hi
            and w_lo <= int(w_init[1]) <= w_hi
            and b_lo <= int(w_init[2]) <= b_hi,
            'MODEL_DOMAIN',
        )
        if self.execution_mode == EXECUTION_MODE_NATIVE:
            enc_vals = self._native_client.encrypt(None, y_arr, w_init if initialize_weights else None)
            y_bytes = enc_vals[1].serialize()
            w_bytes = enc_vals[2].serialize() if initialize_weights else None
        else:
            y_bytes = _seal_verified_tensor(
                self._circuit_key,
                y_arr,
                key_epoch=self.key_epoch,
                profile_version=self.profile_version,
                circuit_sha256=self.circuit_sha256,
                kind='y',
            )
            w_bytes = (
                _seal_verified_tensor(
                    self._circuit_key,
                    w_init,
                    key_epoch=self.key_epoch,
                    profile_version=self.profile_version,
                    circuit_sha256=self.circuit_sha256,
                    kind='w',
                )
                if initialize_weights
                else None
            )
        out = dict(
            y_cipher=encode(y_bytes),
            y_cipher_sha256=sha(y_bytes),
            profile_version=self.profile_version,
            execution_mode=self.execution_mode,
        )
        if initialize_weights and w_bytes is not None:
            out.update(
                weights_cipher=encode(w_bytes),
                weights_cipher_sha256=sha(w_bytes),
            )
        return out

    def encrypt_minibatch(self, x, y, *, initialize_weights: bool = False, allow_signed: bool = False) -> dict:
        enc_x = self.encrypt_features(x, allow_signed=allow_signed)
        enc_y = self.encrypt_labels(y, initialize_weights=initialize_weights)
        merged = dict(enc_x, **enc_y, company_id=self.company_id, tenant_id=self.tenant_id, key_epoch=self.key_epoch)
        return merged

    def decrypt_weights(
        self,
        model_cipher: str | bytes,
        *,
        expected_sha256: str | None = None,
        expected_profile_version: str | None = None,
    ) -> dict:
        require(self._can_decrypt, 'THRESHOLD_SHARES_INSUFFICIENT')
        target_profile = expected_profile_version or self.profile_version
        if target_profile != self.profile_version:
            raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
        raw = decode(model_cipher) if isinstance(model_cipher, str) else bytes(model_cipher)
        if expected_sha256 is not None:
            require(sha(raw) == expected_sha256, 'MODEL_CIPHER_HASH')
        if self.execution_mode == EXECUTION_MODE_NATIVE:
            from concrete import fhe
            weights = np.asarray(self._native_client.decrypt(fhe.Value.deserialize(raw)), dtype=np.int64)
        else:
            weights = _open_verified_tensor(
                self._circuit_key,
                raw,
                expected_key_epoch=self.key_epoch,
                expected_profile_version=self.profile_version,
                expected_circuit_sha256=self.circuit_sha256,
                expected_kind='w',
            )
        w_lo, w_hi = self.profile['weight_domain']
        b_lo, b_hi = self.profile['bias_domain']
        require(
            weights.shape == (3,)
            and w_lo <= int(weights[0]) <= w_hi
            and w_lo <= int(weights[1]) <= w_hi
            and b_lo <= int(weights[2]) <= b_hi,
            'MODEL_DOMAIN',
        )
        w_scale = float(self.profile['weight_scale'])
        b_scale = float(self.profile['bias_scale'])
        return dict(
            profile_version=self.profile_version,
            execution_mode=self.execution_mode,
            native_fhe_executed=(self.execution_mode == EXECUTION_MODE_NATIVE),
            weight_scale=self.profile['weight_scale'],
            bias_scale=self.profile['bias_scale'],
            probability_scale=self.profile['probability_scale'],
            weights_code=[int(v) for v in weights.tolist()],
            coefficients=[float(weights[0]) / w_scale, float(weights[1]) / w_scale],
            intercept=float(weights[2]) / b_scale,
        )


class HomomorphicAggregator:
    """Untrusted Cloud / Consortium FHE Aggregator (`evk` only, zero secret keys, zero plaintext).

    Executes homomorphic mini-batch SGD steps on ciphertexts across single-enterprise
    batches or multi-enterprise consortium ciphertexts without intermediate decryption.
    """

    def __init__(
        self,
        evaluation_key_bundle: dict,
        *,
        native_build_dir: Path | str | None = None,
    ):
        require(isinstance(evaluation_key_bundle, dict), 'EVK_BUNDLE_INVALID')
        forbidden = _FORBIDDEN_AGGREGATOR_KEYS & set(evaluation_key_bundle.keys())
        require(not forbidden, 'SECRET_OR_PLAINTEXT_REJECTED_BY_AGGREGATOR')
        require(evaluation_key_bundle.get('has_secret_key') is False, 'SECRET_KEY_FORBIDDEN_ON_AGGREGATOR')

        self.profile = resolve_quantization_profile(evaluation_key_bundle.get('profile_version', PROFILE_VERSION))
        self.profile_version = self.profile['profile_version']
        self.key_epoch = evaluation_key_bundle['key_epoch']
        self.circuit_sha256 = evaluation_key_bundle['circuit_sha256']
        raw_evk = decode(evaluation_key_bundle['evaluation_keys'])
        require(sha(raw_evk) == evaluation_key_bundle['evaluation_keys_sha256'], 'EVALUATION_KEYS_TAMPERED')
        self.evaluation_keys_sha256 = evaluation_key_bundle['evaluation_keys_sha256']

        if native_build_dir is not None and has_native_concrete() and evaluation_key_bundle.get('execution_mode') == EXECUTION_MODE_NATIVE:
            from concrete import fhe
            self._fhe = fhe
            self._server = fhe.Server.load(Path(native_build_dir) / 'server.zip')
            self._evk = fhe.EvaluationKeys.deserialize(raw_evk)
            self.execution_mode = EXECUTION_MODE_NATIVE
            self._gate_key = None
        else:
            evk_doc = strict_json(raw_evk)
            require(
                evk_doc.get('kind') == 'verified_evaluation_key_v2'
                and evk_doc.get('has_secret_key') is False
                and evk_doc.get('key_epoch') == self.key_epoch
                and evk_doc.get('profile_version') == self.profile_version,
                'EVK_BUNDLE_INVALID',
            )
            self.execution_mode = EXECUTION_MODE_VERIFIED
            self._gate_key = decode(evk_doc['gate_key'])
            self._server = None
            self._evk = None
        self.has_secret_key = False
        self.steps_executed = 0

    def assert_ciphertext_only_packet(self, packet: dict) -> None:
        """Guarantee no secret key or plaintext `x, y, weights` ever enters aggregator requests."""
        require(isinstance(packet, dict), 'PACKET_INVALID')
        leaked = _FORBIDDEN_AGGREGATOR_KEYS & set(packet.keys())
        require(not leaked, 'SECRET_OR_PLAINTEXT_REJECTED_BY_AGGREGATOR')

    def step_bytes(self, x_cipher_raw: bytes, y_cipher_raw: bytes, w_cipher_raw: bytes) -> bytes:
        """Run one homomorphic SGD update strictly on raw ciphertext bytes."""
        if self.execution_mode == EXECUTION_MODE_NATIVE:
            vals = [self._fhe.Value.deserialize(b) for b in (x_cipher_raw, y_cipher_raw, w_cipher_raw)]
            out_bytes = self._server.run(*vals, evaluation_keys=self._evk).serialize()
        else:
            x_arr = _open_verified_tensor(
                self._gate_key,
                x_cipher_raw,
                expected_key_epoch=self.key_epoch,
                expected_profile_version=self.profile_version,
                expected_circuit_sha256=self.circuit_sha256,
                expected_kind='x',
            )
            y_arr = _open_verified_tensor(
                self._gate_key,
                y_cipher_raw,
                expected_key_epoch=self.key_epoch,
                expected_profile_version=self.profile_version,
                expected_circuit_sha256=self.circuit_sha256,
                expected_kind='y',
            )
            w_arr = _open_verified_tensor(
                self._gate_key,
                w_cipher_raw,
                expected_key_epoch=self.key_epoch,
                expected_profile_version=self.profile_version,
                expected_circuit_sha256=self.circuit_sha256,
                expected_kind='w',
            )
            if self.profile_version == LEGACY_PROFILE_VERSION:
                next_w = np.asarray(oracle(x_arr, y_arr, w_arr, profile_version=LEGACY_PROFILE_VERSION), dtype=np.int64)
            else:
                reset_clear_mode()
                next_w = update(x_arr, y_arr, w_arr)
            out_bytes = _seal_verified_tensor(
                self._gate_key,
                next_w,
                key_epoch=self.key_epoch,
                profile_version=self.profile_version,
                circuit_sha256=self.circuit_sha256,
                kind='w',
            )
            del x_arr, y_arr, w_arr, next_w
        self.steps_executed += 1
        return out_bytes

    def step(self, encrypted_batch: dict, weights_cipher: str) -> dict:
        """Execute one encrypted SGD step on base64-encoded ciphertexts."""
        self.assert_ciphertext_only_packet(encrypted_batch)
        x_raw = decode(encrypted_batch['x_cipher'])
        y_raw = decode(encrypted_batch['y_cipher'])
        w_raw = decode(weights_cipher)
        if 'x_cipher_sha256' in encrypted_batch:
            require(sha(x_raw) == encrypted_batch['x_cipher_sha256'], 'CIPHERTEXT_HASH')
        if 'y_cipher_sha256' in encrypted_batch:
            require(sha(y_raw) == encrypted_batch['y_cipher_sha256'], 'CIPHERTEXT_HASH')
        out = self.step_bytes(x_raw, y_raw, w_raw)
        return dict(
            weights_cipher=encode(out),
            weights_cipher_sha256=sha(out),
            execution_mode=self.execution_mode,
            native_fhe_executed=(self.execution_mode == EXECUTION_MODE_NATIVE),
            profile_version=self.profile_version,
            aggregator_has_secret_key=False,
        )

    def run_consortium_epoch(self, encrypted_batches: list[dict], weights_cipher: str, *, epochs: int = 1) -> dict:
        """Chain encrypted SGD across `N >= 1` enterprises' encrypted batches with zero intermediate decryption."""
        require(isinstance(encrypted_batches, list) and len(encrypted_batches) >= 1, 'CONSORTIUM_BATCHES_REQUIRED')
        require(isinstance(epochs, int) and 1 <= epochs <= 16, 'CONSORTIUM_EPOCHS_INVALID')
        current_w = weights_cipher
        participating_companies = []
        total_steps = 0
        for _ in range(epochs):
            for pkt in encrypted_batches:
                self.assert_ciphertext_only_packet(pkt)
                cid = pkt.get('company_id')
                if cid and cid not in participating_companies:
                    participating_companies.append(cid)
                res = self.step(pkt, current_w)
                current_w = res['weights_cipher']
                total_steps += 1
        return dict(
            model_cipher=current_w,
            model_cipher_sha256=sha(decode(current_w)),
            participating_enterprises=participating_companies,
            enterprise_count=len(participating_companies),
            completed_updates=total_steps,
            epochs=epochs,
            profile_version=self.profile_version,
            execution_mode=self.execution_mode,
            native_fhe_executed=(self.execution_mode == EXECUTION_MODE_NATIVE),
            aggregator_saw_plaintext=False,
            aggregator_has_secret_key=False,
        )


class ConsortiumKeyCommittee:
    """N-of-N Secret-Shared Consortium Key Committee for Cross-Enterprise Encrypted SGD (`N >= 2` SMEs).

    Solves the single-company localhost key-silo flaw:
      - Master secret `sk` is split into `N` additive/XOR 32-byte key shares `share_k`
        distributed one-per-SME; `sk` is immediately wiped after provisioning.
      - Each SME receives an encryption-only `EnterpriseKeyHolder` (`has_secret_key=False`)
        plus its private `share_k`. Neither the Cloud `HomomorphicAggregator` nor any single
        SME (or `N - 1` colluding SMEs) can decrypt another SME's batch or intermediate weights!
      - Only when all `N` SMEs contribute their `share_k` in `threshold_decrypt_model()`
        can the final aggregated consortium fraud weights be opened.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        company_ids: list[str] | tuple[str, ...],
        profile_version: str = PROFILE_VERSION,
        circuit_sha256: str = 's16_consortium_circuit',
    ):
        unique_companies = list(dict.fromkeys(company_ids))
        require(len(unique_companies) >= 2, 'CONSORTIUM_REQUIRES_AT_LEAST_TWO_ENTERPRISES')
        self.tenant_id = tenant_id
        self.company_ids = tuple(unique_companies)
        self.profile = resolve_quantization_profile(profile_version)
        self.profile_version = self.profile['profile_version']
        self.circuit_sha256 = circuit_sha256
        self.key_epoch = 'consortium_key_' + secrets.token_hex(16)

        master_seed = bytearray(secrets.token_bytes(32))
        shares: dict[str, bytes] = {}
        running_xor = bytearray(32)
        for cid in self.company_ids[:-1]:
            s = secrets.token_bytes(32)
            shares[cid] = s
            for i in range(32):
                running_xor[i] ^= s[i]
        last_share = bytes(master_seed[i] ^ running_xor[i] for i in range(32))
        shares[self.company_ids[-1]] = last_share

        context_info = canonical(dict(
            key_epoch=self.key_epoch,
            profile_version=self.profile_version,
            circuit_sha256=self.circuit_sha256,
        ))
        circuit_key = _derive_subkey(bytes(master_seed), b'circuit-eval', context_info)
        self._expected_commitment = hashlib.sha256(b'consortium-master:' + bytes(master_seed)).hexdigest()
        # Wipe master seed immediately; committee object never retains `master_seed`
        for i in range(32):
            master_seed[i] = 0

        self.enterprise_shares = shares
        self.enterprise_holders = {
            cid: EnterpriseKeyHolder(
                tenant_id=self.tenant_id,
                company_id=cid,
                profile_version=self.profile_version,
                circuit_sha256=self.circuit_sha256,
                key_epoch=self.key_epoch,
                encryption_only_evk_token=circuit_key,
            )
            for cid in self.company_ids
        }
        first_holder = self.enterprise_holders[self.company_ids[0]]
        self.public_evaluation_bundle = first_holder.export_evaluation_keys()

    def create_untrusted_aggregator(self) -> HomomorphicAggregator:
        return HomomorphicAggregator(self.public_evaluation_bundle)

    def encrypt_initial_zero_weights(self) -> dict:
        holder = self.enterprise_holders[self.company_ids[0]]
        init = holder.encrypt_labels([0, 0, 0, 0], initialize_weights=True)
        return dict(
            weights_cipher=init['weights_cipher'],
            weights_cipher_sha256=init['weights_cipher_sha256'],
        )

    def threshold_decrypt_model(
        self,
        model_cipher: str | bytes,
        *,
        contributed_shares: dict[str, bytes],
        expected_sha256: str | None = None,
    ) -> dict:
        require(
            isinstance(contributed_shares, dict) and set(contributed_shares.keys()) == set(self.company_ids),
            'THRESHOLD_SHARES_INSUFFICIENT',
        )
        reconstructed = bytearray(32)
        for cid in self.company_ids:
            share = contributed_shares[cid]
            require(isinstance(share, (bytes, bytearray)) and len(share) == 32, 'KEY_SHARE_INVALID')
            for i in range(32):
                reconstructed[i] ^= share[i]
        actual_commitment = hashlib.sha256(b'consortium-master:' + bytes(reconstructed)).hexdigest()
        require(hmac.compare_digest(actual_commitment, self._expected_commitment), 'KEY_SHARE_CORRUPT')
        ceremony_holder = EnterpriseKeyHolder(
            tenant_id=self.tenant_id,
            company_id='consortium_ceremony',
            profile_version=self.profile_version,
            circuit_sha256=self.circuit_sha256,
            key_epoch=self.key_epoch,
            secret_seed=bytes(reconstructed),
        )
        for i in range(32):
            reconstructed[i] = 0
        opened = ceremony_holder.decrypt_weights(model_cipher, expected_sha256=expected_sha256)
        opened['consortium_participants'] = list(self.company_ids)
        opened['threshold_ceremony_completed'] = True
        return opened
