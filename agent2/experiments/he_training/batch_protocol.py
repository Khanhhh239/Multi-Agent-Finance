"""Versioned multi-batch envelope; old single-batch protocol stays unchanged."""
from . import PROFILE, SUPPORTED_PROFILES, TARGET
from .protocol import TrainingError, fields, require, ID, sha, canonical

VERSION = 'encrypted-batch-training/0.1.0'
MAX_BATCHES = 4
BASE = {'version', 'profile', 'target', 'tenant_id', 'company_id', 'key_epoch', 'dataset_id', 'build_sha256'}
UPLOAD = BASE | {'batches', 'batch_manifest_sha256', 'training_commitment', 'evaluation_commitment'}
CONSENT = BASE | {
    'consent_id', 'receipt_sha256', 'batch_manifest_sha256', 'label_batches',
    'weights_cipher', 'weights_cipher_sha256', 'epochs', 'verification_mode',
    'training_commitment', 'evaluation_commitment',
}
ACCESS = BASE | {'action', 'job_id'}


def common(body, *, expected_profile=PROFILE):
    if body.get('profile') in SUPPORTED_PROFILES and body.get('profile') != expected_profile:
        raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
    require(
        body['version'] == VERSION and body['profile'] == expected_profile and body['target'] == TARGET,
        'BATCH_CONTRACT_MISMATCH',
    )
    for name in ('tenant_id', 'company_id', 'key_epoch', 'dataset_id'):
        require(isinstance(body[name], str) and ID.fullmatch(body[name]), 'IDENTITY_INVALID')


def hash_field(value):
    import re
    require(isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value), 'BATCH_HASH_INVALID')


def manifest(batches):
    return sha(canonical([
        dict(index=b['index'], rows=b['rows'], features=b['features'], x_cipher_sha256=b['x_cipher_sha256'])
        for b in batches
    ]))
