"""Compile a public fixed `S=16, P=16` training program, without customer data or keys."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np

from . import (
    EXECUTION_MODE_NATIVE,
    EXECUTION_MODE_VERIFIED,
    PROFILE,
    PROFILE_VERSION,
    TARGET,
    VERSION,
    resolve_quantization_profile,
)
from . import circuit as c
from .runtime import has_native_concrete


def _manifest_dict(output: Path, prof: dict, *, started: float, execution_mode: str, concrete_version: str | None) -> dict:
    return dict(
        version=VERSION,
        profile=prof['profile_id'],
        profile_version=prof['profile_version'],
        target=TARGET,
        rows=c.ROWS,
        features=c.COLUMNS,
        feature_scale=prof['feature_scale'],
        weight_scale=prof['weight_scale'],
        bias_scale=prof['bias_scale'],
        probability_scale=prof['probability_scale'],
        input_domain=prof['input_domain'],
        weight_domain=prof['weight_domain'],
        bias_domain=prof['bias_domain'],
        logit_domain=prof['logit_domain'],
        gradient_sum_domain=prof['gradient_sum_domain'],
        learning_rate=prof['learning_rate'],
        effective_float_learning_rate=prof['effective_float_learning_rate'],
        rounding=prof['rounding'],
        lut_sizes=prof['lut_sizes'],
        batch_size=prof['batch_size'],
        max_steps=4,
        all_inputs_encrypted=True,
        composable=True,
        secret_keys_in_bundle=False,
        execution_mode=execution_mode,
        native_fhe_compiled=(execution_mode == EXECUTION_MODE_NATIVE),
        concrete_version=concrete_version,
        seconds=time.monotonic() - started,
        source_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
        files={
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ('server.zip', 'client.specs.json')
        },
    )


def build_verified_bundle(output: Path | str, *, profile_version: str = PROFILE_VERSION) -> dict:
    """Build bit-exact verified integer circuit bundle when Concrete-Python is absent (pure Windows)."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    prof = resolve_quantization_profile(profile_version)
    started = time.monotonic()
    c.reset_clear_mode()
    values = c.samples(prof['profile_version'])
    expected = [c.oracle(*v, profile_version=prof['profile_version']) for v in values]
    if prof['profile_version'] == PROFILE_VERSION:
        for v, wanted in zip(values, expected):
            if not np.array_equal(c.update(*v), wanted):
                raise ValueError('verified integer LUT circuit differs from scalar oracle')

    circuit_spec = dict(
        bundle_format='agent2-verified-fhe-circuit/2.0',
        execution_mode=EXECUTION_MODE_VERIFIED,
        native_fhe_compiled=False,
        profile_version=prof['profile_version'],
        source_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
        lut_sizes=prof['lut_sizes'],
    )
    client_specs = dict(
        client_specs_format='agent2-verified-client-specs/2.0',
        execution_mode=EXECUTION_MODE_VERIFIED,
        profile_version=prof['profile_version'],
        inputs=['x:(4,2):encrypted', 'y:(4,):encrypted', 'weights:(3,):encrypted'],
        outputs=['weights_next:(3,):encrypted'],
    )
    (output / 'server.zip').write_text(json.dumps(circuit_spec, sort_keys=True) + '\n', encoding='utf-8')
    (output / 'client.specs.json').write_text(json.dumps(client_specs, sort_keys=True) + '\n', encoding='utf-8')
    manifest = _manifest_dict(
        output,
        prof,
        started=started,
        execution_mode=EXECUTION_MODE_VERIFIED,
        concrete_version=None,
    )
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def build(output: Path | str, *, allow_verified_fallback: bool = False):
    output = Path(output)
    if not has_native_concrete():
        if allow_verified_fallback:
            manifest = build_verified_bundle(output, profile_version=PROFILE_VERSION)
            print(json.dumps(dict(
                status='compiled_verified_circuit',
                execution_mode=EXECUTION_MODE_VERIFIED,
                seconds=manifest['seconds'],
            )), flush=True)
            return manifest
        raise RuntimeError(
            'Concrete-Python (`concrete.fhe`) is not installed in this Python runtime; '
            'pass allow_verified_fallback=True for verified quantized circuit bundle on Windows.'
        )

    import concrete
    from concrete import fhe

    output.mkdir(parents=True, exist_ok=False)
    prof = resolve_quantization_profile(PROFILE_VERSION)
    values = c.samples(PROFILE_VERSION)
    expected = [c.oracle(*v, profile_version=PROFILE_VERSION) for v in values]
    started = time.monotonic()
    c.configure_fhe()
    try:
        compiled = fhe.Compiler(
            c.update,
            {'x': 'encrypted', 'y': 'encrypted', 'weights': 'encrypted'},
        ).compile(values, global_p_error=1e-9, composable=True)
        for v, wanted in zip(values, expected):
            if not np.array_equal(compiled.simulate(*v), wanted):
                raise ValueError('training simulation differs from scalar oracle')
        compiled.server.save(output / 'server.zip')
        specs = compiled.client.specs.serialize()
        (output / 'client.specs.json').write_bytes(specs if isinstance(specs, bytes) else specs.encode())
    finally:
        c.reset_clear_mode()

    manifest = _manifest_dict(
        output,
        prof,
        started=started,
        execution_mode=EXECUTION_MODE_NATIVE,
        concrete_version=getattr(concrete, '__version__', '2.11.0'),
    )
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(
        status='compiled',
        execution_mode=EXECUTION_MODE_NATIVE,
        seconds=manifest['seconds'],
        simulation_cases=len(values),
    )), flush=True)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-verified-fallback', action='store_true')
    a = p.parse_args()
    build(a.output, allow_verified_fallback=a.allow_verified_fallback)
