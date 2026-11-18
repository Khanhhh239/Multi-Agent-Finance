"""Enterprise-only crypto helper (`S=16, P=16` default; `legacy_s2_v1` recognized).

Supports native Concrete TFHE (`fhe_concrete_native`) when `concrete.fhe` is
present and the build is native, and portable `EnterpriseKeyHolder` verified
circuit sealing (`fhe_quantized_circuit_verified`) on pure Windows without WSL.
Wrapping key arrives strictly via stdin, never argv.
"""
import argparse
import json
from pathlib import Path
import secrets
import sys
import numpy as np

from experiments.he4.vault import open_private, seal
from . import EXECUTION_MODE_NATIVE, EXECUTION_MODE_VERIFIED, resolve_quantization_profile
from .protocol import atomic, canonical, decode, encode, require, sha, strict_json
from .runtime import EnterpriseKeyHolder, has_native_concrete


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['provision', 'encrypt-data', 'encrypt-labels', 'encrypt-batch-labels', 'open-model'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()

    request = strict_json(sys.stdin.buffer.read(24 * 1024 * 1024 + 1))
    key = decode(request.pop('wrapping_key'))
    require(len(key) == 32, 'WRAPPING_KEY')
    binding = request['binding']
    manifest = json.loads((a.build / 'manifest.json').read_bytes())
    require(manifest['files']['server.zip'] == binding['build_sha256'], 'BUILD_BINDING')
    for name, digest in manifest['files'].items():
        require(sha((a.build / name).read_bytes()) == digest, 'BUILD_TAMPERED')

    prof = resolve_quantization_profile(manifest)
    profile_version = prof['profile_version']
    use_native = (
        manifest.get('execution_mode', EXECUTION_MODE_NATIVE) == EXECUTION_MODE_NATIVE
        and has_native_concrete()
    )

    a.root.mkdir(parents=True, exist_ok=True)
    private = a.root / 'context.sealed'
    public = a.root / 'evaluation.keys'

    if use_native:
        from concrete import fhe
        client = fhe.Client(fhe.ClientSpecs.deserialize((a.build / 'client.specs.json').read_bytes()))
        if a.action == 'provision':
            require(not private.exists() and not public.exists(), 'CONTEXT_ALREADY_EXISTS')
            client.keys.generate()
            seal(private, key, binding, client.keys.serialize())
            atomic(public, client.evaluation_keys.serialize())
            result = dict(
                binding=binding,
                profile_version=profile_version,
                execution_mode=EXECUTION_MODE_NATIVE,
                native_fhe_executed=True,
                evaluation_keys_sha256=sha(public.read_bytes()),
                private_keys_persisted='AES-GCM wrapped by enterprise DPAPI key',
            )
        else:
            raw = open_private(private, key, binding)
            client.keys = fhe.Keys.deserialize(raw)
            del raw
            if a.action == 'encrypt-data':
                x = np.asarray(request['x'])
                require(
                    x.shape == (4, 2) and np.issubdtype(x.dtype, np.integer) and np.all((-1 <= x) & (x <= 1)),
                    'FEATURE_DOMAIN',
                )
                values = client.encrypt(x.astype(np.int64), None, None)
                ser = values[0].serialize()
                result = dict(
                    x_cipher=encode(ser),
                    x_cipher_sha256=sha(ser),
                    profile_version=profile_version,
                    execution_mode=EXECUTION_MODE_NATIVE,
                )
            elif a.action in ('encrypt-labels', 'encrypt-batch-labels'):
                y = np.asarray(request['y'])
                require(y.shape == (4,) and np.issubdtype(y.dtype, np.integer) and set(y.tolist()) <= {0, 1}, 'LABEL_DOMAIN')
                initialize = (a.action == 'encrypt-labels') or (request.get('initialize_weights') is True)
                if a.action == 'encrypt-labels':
                    require(set(y.tolist()) == {0, 1}, 'LABEL_DOMAIN')
                else:
                    require(type(request.get('initialize_weights')) is bool, 'INITIAL_WEIGHTS_FLAG')
                values = client.encrypt(None, y.astype(np.int64), np.zeros(3, dtype=np.int64) if initialize else None)
                y_ser = values[1].serialize()
                result = dict(
                    y_cipher=encode(y_ser),
                    y_cipher_sha256=sha(y_ser),
                    profile_version=profile_version,
                    execution_mode=EXECUTION_MODE_NATIVE,
                )
                if initialize:
                    w_ser = values[2].serialize()
                    result.update(weights_cipher=encode(w_ser), weights_cipher_sha256=sha(w_ser))
            else:
                expected_prof = request.get('expected_profile_version')
                if expected_prof is not None and expected_prof != profile_version:
                    require(False, 'LEGACY_MODEL_PROFILE_MISMATCH')
                raw_cipher = decode(request['model_cipher'])
                require(sha(raw_cipher) == request['model_cipher_sha256'], 'MODEL_CIPHER_HASH')
                weights = np.asarray(client.decrypt(fhe.Value.deserialize(raw_cipher)), dtype=np.int64)
                w_lo, w_hi = prof['weight_domain']
                b_lo, b_hi = prof['bias_domain']
                require(
                    weights.shape == (3,)
                    and np.all((w_lo <= weights[:2]) & (weights[:2] <= w_hi))
                    and (b_lo <= int(weights[2]) <= b_hi),
                    'MODEL_DOMAIN',
                )
                w_scale = float(prof['weight_scale'])
                b_scale = float(prof['bias_scale'])
                result = dict(
                    profile_version=profile_version,
                    execution_mode=EXECUTION_MODE_NATIVE,
                    native_fhe_executed=True,
                    weight_scale=prof['weight_scale'],
                    bias_scale=prof['bias_scale'],
                    probability_scale=prof['probability_scale'],
                    weights_code=weights.tolist(),
                    coefficients=(weights[:2] / w_scale).tolist(),
                    intercept=float(weights[2] / b_scale),
                )
    else:
        # Pure-Windows portable verified-circuit path via EnterpriseKeyHolder (never lies about native FHE)
        circuit_sha = manifest['files']['server.zip']
        if a.action == 'provision':
            require(not private.exists() and not public.exists(), 'CONTEXT_ALREADY_EXISTS')
            seed = secrets.token_bytes(32)
            holder = EnterpriseKeyHolder(
                tenant_id=binding['tenant_id'],
                company_id=binding['company_id'],
                profile_version=profile_version,
                circuit_sha256=circuit_sha,
                key_epoch=binding['key_epoch'],
                secret_seed=seed,
            )
            evk_bundle = holder.export_evaluation_keys()
            seal(private, key, binding, canonical(dict(
                seed=encode(seed),
                profile_version=profile_version,
                execution_mode=EXECUTION_MODE_VERIFIED,
            )))
            atomic(public, canonical(evk_bundle))
            result = dict(
                binding=binding,
                profile_version=profile_version,
                execution_mode=EXECUTION_MODE_VERIFIED,
                native_fhe_executed=False,
                evaluation_keys_sha256=sha(public.read_bytes()),
                private_keys_persisted='AES-GCM wrapped by enterprise DPAPI key',
            )
        else:
            opened_priv = strict_json(open_private(private, key, binding))
            require(opened_priv.get('profile_version') == profile_version, 'LEGACY_MODEL_PROFILE_MISMATCH')
            holder = EnterpriseKeyHolder(
                tenant_id=binding['tenant_id'],
                company_id=binding['company_id'],
                profile_version=profile_version,
                circuit_sha256=circuit_sha,
                key_epoch=binding['key_epoch'],
                secret_seed=decode(opened_priv['seed']),
            )
            if a.action == 'encrypt-data':
                result = holder.encrypt_features(request['x'], allow_signed=True)
            elif a.action in ('encrypt-labels', 'encrypt-batch-labels'):
                initialize = (a.action == 'encrypt-labels') or (request.get('initialize_weights') is True)
                if a.action != 'encrypt-labels':
                    require(type(request.get('initialize_weights')) is bool, 'INITIAL_WEIGHTS_FLAG')
                result = holder.encrypt_labels(
                    request['y'],
                    initialize_weights=initialize,
                    require_both_classes=(a.action == 'encrypt-labels'),
                )
            else:
                result = holder.decrypt_weights(
                    request['model_cipher'],
                    expected_sha256=request['model_cipher_sha256'],
                    expected_profile_version=request.get('expected_profile_version', profile_version),
                )

    atomic(a.output, canonical(result))
    print(json.dumps(dict(status='ok', action=a.action, execution_mode=result.get('execution_mode'))), flush=True)


if __name__ == '__main__':
    main()
