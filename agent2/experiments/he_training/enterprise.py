"""Enterprise workflow: upload -> verified labels/consent -> encrypted fit -> approval.

Secret keys (`sk`) remain DPAPI-protected at the enterprise via `EnterpriseKeyHolder`.
Labels/source records and decrypted models never enter cloud/aggregator requests.
Runtime discovery is portable via `AGENT2_HE_PYTHON`, `AGENT2_WSL_DISTRO`, and
`AGENT2_HE_AGGREGATOR_URL` with zero hardcoded user paths or WSL distro names.
"""
from datetime import datetime, timezone
import http.client
import hashlib
import hmac
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from experiments.he_inference.key_manager import PROVIDER, create_key, load_key
from experiments.he4.windows_bridge import linux_path
from . import (
    EXECUTION_MODE_NATIVE,
    EXECUTION_MODE_VERIFIED,
    PROFILE,
    PROFILE_VERSION,
    TARGET,
    VERSION,
    resolve_quantization_profile,
)
from .circuit import oracle
from .protocol import (
    MAX_PACKET,
    TrainingError,
    atomic,
    canonical,
    encode,
    fields,
    require,
    sha,
    sign,
    strict_json,
    verify,
)
from .runtime import resolve_he_runtime, validate_aggregator_endpoint


def verified_labels(review, row_ids, scope, *, simulated, dataset_id, receipt_sha256, now=None, require_both_classes=True):
    require('evidence.verify' in scope.permissions, 'LABEL_VERIFICATION_DENIED')
    fields(review, {'target', 'revision', 'verification_mode', 'rows', 'tenant_id', 'company_id', 'dataset_id', 'receipt_sha256'})
    require(
        review['tenant_id'] == scope.tenant_id
        and review['company_id'] == next(iter(scope.company_ids))
        and review['dataset_id'] == dataset_id
        and review['receipt_sha256'] == receipt_sha256,
        'LABEL_DATASET_BINDING',
    )
    require(review['target'] == TARGET, 'LABEL_TARGET_MISMATCH')
    mode = 'synthetic_expected' if simulated else 'human_verified'
    require(review['verification_mode'] == mode, 'LABEL_VERIFICATION_MODE')
    require(type(review['revision']) is int and review['revision'] >= 1, 'LABEL_REVISION_INVALID')
    require(isinstance(review['rows'], list) and len(review['rows']) == len(row_ids), 'LABELS_INCOMPLETE')
    rows = {}
    now = now or datetime.now(timezone.utc)
    for entry in review['rows']:
        fields(entry, {'record_id', 'outcome', 'verified_by', 'verified_at', 'evidence_refs'})
        require(entry['record_id'] in row_ids and entry['record_id'] not in rows, 'LABEL_ROW_BINDING')
        require(entry['outcome'] in ('verified_fraud', 'verified_non_fraud'), 'LABEL_NOT_VERIFIED')
        require(entry['verified_by'] == scope.actor_id, 'LABEL_REVIEWER_MISMATCH')
        require(
            isinstance(entry['evidence_refs'], list)
            and entry['evidence_refs']
            and all(isinstance(s, str) and 0 < len(s) <= 200 for s in entry['evidence_refs']),
            'LABEL_EVIDENCE_REQUIRED',
        )
        try:
            at = datetime.fromisoformat(entry['verified_at'])
        except (ValueError, TypeError):
            raise ValueError('LABEL_TIME_INVALID')
        require(at.tzinfo is not None and at <= now, 'LABEL_TIME_INVALID')
        rows[entry['record_id']] = 1 if entry['outcome'] == 'verified_fraud' else 0
    result = [rows[r] for r in row_ids]
    if require_both_classes:
        require(set(result) == {0, 1}, 'BOTH_LABEL_CLASSES_REQUIRED')
    return result


class Enterprise:
    def __init__(self, root, build, scope, *, python=None, distro=None, recheck=None):
        require(len(scope.company_ids) == 1 and 'data.import' in scope.permissions, 'COMPANY_SCOPE_REQUIRED')
        self.root = Path(root).resolve()
        self.build = Path(build).resolve()
        self.scope = scope
        self.company = next(iter(scope.company_ids))
        self.python = python
        self.distro = distro
        self.recheck = recheck
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700 if os.name != 'nt' else 0o777)
        manifest = strict_json((self.build / 'manifest.json').read_bytes())
        self.manifest = manifest
        self.profile_spec = resolve_quantization_profile(manifest)
        self.profile_version = self.profile_spec['profile_version']
        self.execution_mode = manifest.get('execution_mode', EXECUTION_MODE_NATIVE)
        self.build_sha = manifest['files']['server.zip']
        self.wrap_file = self.root / 'wrapping.dpapi.json'
        self.sign_file = self.root / 'node-signing.dpapi.json'
        self.meta_file = self.root / 'enterprise.json'
        if self.meta_file.exists():
            self.meta = strict_json(self.meta_file.read_bytes())
            saved_prof = self.meta.get('profile_version')
            if saved_prof is not None and saved_prof != self.profile_version:
                raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
            require(
                self.meta['tenant_id'] == scope.tenant_id
                and self.meta['company_id'] == self.company
                and self.meta['build_sha256'] == self.build_sha,
                'ENTERPRISE_CONTEXT_MISMATCH',
            )
            load_key(self.wrap_file, required_provider=PROVIDER)
            load_key(self.sign_file, purpose='node-signing', required_provider=PROVIDER)
        else:
            require('model.fit' in scope.permissions, 'MODEL_FIT_DENIED')
            require(not self.wrap_file.exists() and not self.sign_file.exists(), 'PARTIAL_CONTEXT')
            create_key(self.wrap_file)
            create_key(self.sign_file, purpose='node-signing')
            self.meta = dict(
                tenant_id=scope.tenant_id,
                company_id=self.company,
                key_epoch='key_' + secrets.token_hex(16),
                build_sha256=self.build_sha,
            )
            atomic(self.meta_file, canonical(self.meta))
            self.helper('provision', {})

    @property
    def public_key(self):
        return self.signing_key().public_key().public_bytes_raw().hex()

    def guard(self, permission='data.import'):
        current = self.recheck() if self.recheck else self.scope
        require(current == self.scope, 'AUTH_CONTEXT_CHANGED')
        require(permission in current.permissions, 'PERMISSION_DENIED')

    def signing_key(self):
        return Ed25519PrivateKey.from_private_bytes(load_key(self.sign_file, purpose='node-signing', required_provider=PROVIDER).material)

    def helper(self, action, values):
        self.guard()
        key = load_key(self.wrap_file, required_provider=PROVIDER).material
        output = self.root / ('helper-' + secrets.token_hex(8) + '.json')
        request = dict(wrapping_key=encode(key), binding=self.meta, **values)

        rt = resolve_he_runtime(python=self.python, distro=self.distro)
        agent2_root = Path(__file__).resolve().parents[2]
        use_wsl = (
            os.name == 'nt'
            and not rt['native_local_concrete']
            and rt['wsl_concrete_available']
            and self.manifest.get('execution_mode', EXECUTION_MODE_NATIVE) == EXECUTION_MODE_NATIVE
        )
        if use_wsl:
            command = [
                'wsl.exe', '-d', rt['wsl_distro'],
                '--cd', linux_path(agent2_root),
                '--exec', rt['he_python'], '-m', 'experiments.he_training.helper',
                action,
                '--root', linux_path(self.root / 'crypto'),
                '--build', linux_path(self.build),
                '--output', linux_path(output),
            ]
            env = None
        else:
            local_py = rt['he_python'] if (os.name != 'nt' and rt['native_local_concrete']) else sys.executable
            command = [
                local_py, '-m', 'experiments.he_training.helper',
                action,
                '--root', str(self.root / 'crypto'),
                '--build', str(self.build),
                '--output', str(output),
            ]
            env = dict(os.environ)
            py_paths = [str(agent2_root), str(agent2_root.parent)]
            if env.get('PYTHONPATH'):
                py_paths.append(env['PYTHONPATH'])
            env['PYTHONPATH'] = os.pathsep.join(py_paths)

        result = subprocess.run(
            command,
            input=canonical(request),
            capture_output=True,
            env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            timeout=600,
        )
        if result.returncode != 0:
            atomic(self.root / 'private-helper-error.log', result.stderr)
        require(result.returncode == 0, 'ENTERPRISE_CRYPTO_HELPER_FAILED')
        self.guard()
        value = strict_json(output.read_bytes())
        output.unlink()
        if value.get('execution_mode'):
            self.execution_mode = value['execution_mode']
        return value

    def base(self, dataset):
        prof_id = getattr(self, 'profile_spec', {}).get('profile_id', PROFILE)
        return dict(version=VERSION, profile=prof_id, target=TARGET, **self.meta, dataset_id=dataset['dataset_id'])

    def dataset(self):
        value = strict_json((self.root / 'dataset.json').read_bytes())
        saved = verify(strict_json((self.root / 'dataset-auth.json').read_bytes()), self.public_key)
        require(
            saved == dict(
                **self.meta,
                dataset_sha256=sha(canonical(value)),
                upload_sha256=sha((self.root / 'upload.json').read_bytes()),
            ),
            'LOCAL_DATASET_TAMPERED',
        )
        return value

    def review_commitment(self, review, dataset):
        return hmac.new(
            load_key(self.wrap_file, required_provider=PROVIDER).material,
            b'he-training-label-review-v1\x00' + canonical(dict(review=review, dataset_id=dataset['dataset_id'])),
            hashlib.sha256,
        ).hexdigest()

    def review_template(self):
        self.guard()
        dataset = self.dataset()
        receipt = strict_json((self.root / 'receipt.json').read_bytes())
        return dict(
            target=TARGET,
            tenant_id=self.scope.tenant_id,
            company_id=self.company,
            dataset_id=dataset['dataset_id'],
            receipt_sha256=sha(canonical(receipt)),
            revision=1,
            verification_mode='synthetic_expected' if dataset['simulated'] else 'human_verified',
            rows=[
                dict(record_id=r, outcome=None, verified_by=self.scope.actor_id, verified_at=None, evidence_refs=[])
                for r in dataset['row_ids']
            ],
        )

    def prepare(self, x, row_ids, *, simulated, provenance=None):
        self.guard()
        require(type(simulated) is bool, 'SOURCE_MODE_REQUIRED')
        require(
            isinstance(row_ids, list)
            and len(row_ids) == 4
            and len(set(row_ids)) == 4
            and all(isinstance(r, str) and 0 < len(r) <= 100 for r in row_ids),
            'DATA_ROWS',
        )
        require(
            isinstance(x, list)
            and len(x) == 4
            and all(isinstance(row, list) and len(row) == 2 and all(type(v) is int and -1 <= v <= 1 for v in row) for row in x),
            'FEATURE_DOMAIN',
        )
        path = self.root / 'dataset.json'
        if path.exists():
            dataset = self.dataset()
            require(
                dataset['x'] == x
                and dataset['row_ids'] == row_ids
                and dataset['simulated'] == simulated
                and dataset.get('provenance') == provenance,
                'DATASET_IMMUTABLE',
            )
            return dataset
        encrypted = self.helper('encrypt-data', dict(x=x))
        cipher_fields = {k: encrypted[k] for k in ('x_cipher', 'x_cipher_sha256')}
        dataset = dict(dataset_id='ds_' + secrets.token_hex(16), row_ids=row_ids, x=x, simulated=simulated)
        if provenance is not None:
            dataset['provenance'] = strict_json(canonical(provenance))
        packet = sign(dict(**self.base(dataset), **cipher_fields, rows=4, features=2), self.signing_key())
        atomic(self.root / 'upload.json', canonical(packet))
        atomic(path, canonical(dataset))
        atomic(
            self.root / 'dataset-auth.json',
            canonical(sign(dict(**self.meta, dataset_sha256=sha(canonical(dataset)), upload_sha256=sha(canonical(packet))), self.signing_key())),
        )
        return dataset

    def prepare_snapshot(self, store, request, *, expected_plan_sha256):
        self.guard('model.fit')
        from .snapshot_adapter import prepare_snapshot_training
        plan = prepare_snapshot_training(store, self.scope, request, self.recheck)
        require(plan['status'] == 'ready', 'SNAPSHOT_TRAINING_NOT_READY')
        require(plan['plan_sha256'] == expected_plan_sha256, 'TRAINING_PREVIEW_STALE')
        return self.prepare(plan['x'], plan['row_ids'], simulated=plan['simulated'], provenance=plan)

    def post(self, url, path, packet, worker_key):
        self.guard()
        ep = validate_aggregator_endpoint(url)
        conn_cls = http.client.HTTPSConnection if ep['scheme'] == 'https' else http.client.HTTPConnection
        c = conn_cls(ep['hostname'], ep['port'], timeout=600)
        try:
            full_path = ep['base_path'] + path
            c.request('POST', full_path, canonical(packet), {'Content-Type': 'application/json'})
            r = c.getresponse()
            raw = r.read(MAX_PACKET + 1)
            body = strict_json(raw)
            require(r.status == 200, body.get('error', 'WORKER_ERROR'))
            self.guard()
            return verify(body, worker_key), body
        finally:
            c.close()

    def upload(self, url, worker_key):
        dataset = self.dataset()
        request = strict_json((self.root / 'upload.json').read_bytes())
        receipt, packet = self.post(url, '/v1/datasets', request, worker_key)
        prof_id = getattr(self, 'profile_spec', {}).get('profile_id', PROFILE)
        require(
            receipt == dict(
                version=VERSION,
                kind='dataset_received',
                tenant_id=self.scope.tenant_id,
                company_id=self.company,
                dataset_id=dataset['dataset_id'],
                key_epoch=self.meta['key_epoch'],
                build_sha256=self.build_sha,
                profile=prof_id,
                target=TARGET,
                x_cipher_sha256=request['payload']['x_cipher_sha256'],
                upload_sha256=sha(canonical(request)),
            ),
            'UPLOAD_RECEIPT_MISMATCH',
        )
        atomic(self.root / 'receipt.json', canonical(packet))
        return packet

    def confirm(self, url, worker_key, review, *, steps=2):
        self.guard('model.fit')
        require('model.fit' in self.scope.permissions, 'MODEL_FIT_DENIED')
        require(type(steps) is int and 1 <= steps <= 4, 'STEPS_INVALID')
        dataset = self.dataset()
        require((self.root / 'receipt.json').is_file(), 'UPLOAD_RECEIPT_REQUIRED')
        receipt = strict_json((self.root / 'receipt.json').read_bytes())
        verify(receipt, worker_key)
        y = verified_labels(
            review,
            dataset['row_ids'],
            self.scope,
            simulated=dataset['simulated'],
            dataset_id=dataset['dataset_id'],
            receipt_sha256=sha(canonical(receipt)),
        )
        commitment = self.review_commitment(review, dataset)
        path = self.root / 'consent.json'
        if path.exists():
            packet = strict_json(path.read_bytes())
            require(
                packet['payload']['label_review_commitment'] == commitment and packet['payload']['steps'] == steps,
                'CONSENT_IMMUTABLE',
            )
        else:
            encrypted = self.helper('encrypt-labels', dict(y=y))
            cipher_fields = {k: encrypted[k] for k in ('y_cipher', 'y_cipher_sha256', 'weights_cipher', 'weights_cipher_sha256')}
            packet = sign(
                dict(
                    **self.base(dataset),
                    consent_id='consent_' + secrets.token_hex(16),
                    receipt_sha256=sha(canonical(receipt)),
                    label_revision=review['revision'],
                    label_review_commitment=commitment,
                    steps=steps,
                    verification_mode=review['verification_mode'],
                    **cipher_fields,
                ),
                self.signing_key(),
            )
            atomic(self.root / 'verified-labels.json', canonical(review))
            atomic(path, canonical(packet))
        result, signed = self.post(url, '/v1/confirm', packet, worker_key)
        self.check_result(result, packet, dataset)
        atomic(self.root / 'job.json', canonical(signed))
        return result

    def check_result(self, result, consent, dataset):
        require(all(result[k] == v for k, v in self.base(dataset).items()), 'RESULT_CONTEXT_MISMATCH')
        digest = sha(canonical(consent))
        require(result['job_id'] == 'trn_' + digest[:32] and result['consent_sha256'] == digest, 'RESULT_CONSENT_MISMATCH')

    def access(self, url, worker_key, action):
        self.guard('model.fit' if action == 'run' else 'data.import')
        dataset = self.dataset()
        consent = strict_json((self.root / 'consent.json').read_bytes())
        job = 'trn_' + sha(canonical(consent))[:32]
        request = sign(dict(**self.base(dataset), job_id=job, action=action), self.signing_key())
        result, packet = self.post(url, '/v1/jobs', request, worker_key)
        self.check_result(result, consent, dataset)
        return result, packet

    def receive(self, url, worker_key):
        self.guard()
        result, packet = self.access(url, worker_key, 'result')
        consent = strict_json((self.root / 'consent.json').read_bytes())
        require(result['status'] == 'completed' and result['completed_steps'] == consent['payload']['steps'], 'TRAINING_NOT_COMPLETED')
        prof_ver = getattr(self, 'profile_version', PROFILE_VERSION)
        actual = self.helper(
            'open-model',
            dict(
                model_cipher=result['model_cipher'],
                model_cipher_sha256=result['model_cipher_sha256'],
                expected_profile_version=prof_ver,
            ),
        )
        if actual.get('profile_version') not in (None, prof_ver):
            raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
        dataset = self.dataset()
        review = strict_json((self.root / 'verified-labels.json').read_bytes())
        require(
            self.review_commitment(review, dataset) == consent['payload']['label_review_commitment']
            and review['revision'] == consent['payload']['label_revision'],
            'SAVED_REVIEW_TAMPERED',
        )
        labels = {r['record_id']: r['outcome'] == 'verified_fraud' for r in review['rows']}
        y = [int(labels[r]) for r in dataset['row_ids']]
        weights = [0, 0, 0]
        for _ in range(consent['payload']['steps']):
            weights = oracle(dataset['x'], y, weights, profile_version=prof_ver)
        require(actual['weights_code'] == weights, 'DECRYPTED_TRAINING_PARITY_FAILED')
        prof_id = getattr(self, 'profile_spec', {}).get('profile_id', PROFILE)
        exec_mode = actual.get('execution_mode', getattr(self, 'execution_mode', EXECUTION_MODE_VERIFIED))
        candidate = {
            **actual,
            **self.meta,
            'version': VERSION,
            'profile': prof_id,
            'profile_version': prof_ver,
            'execution_mode': exec_mode,
            'native_fhe_executed': (exec_mode == EXECUTION_MODE_NATIVE),
            'target': TARGET,
            'dataset_id': dataset['dataset_id'],
            'job_id': result['job_id'],
            'consent_sha256': result['consent_sha256'],
            'label_revision': review['revision'],
            'verification_mode': review['verification_mode'],
            'steps': result['completed_steps'],
            'model_cipher_sha256': result['model_cipher_sha256'],
            'validation': 'quantized_training_parity_passed',
            'operational_activation': False,
        }
        if dataset.get('provenance') is not None:
            candidate['training_provenance'] = dataset['provenance']
        atomic(self.root / 'candidate.json', canonical(sign(candidate, self.signing_key())))
        atomic(self.root / 'model-result.json', canonical(packet))
        return candidate

    def approve(self, reason):
        self.guard('model.fit')
        require('model.fit' in self.scope.permissions, 'MODEL_FIT_DENIED')
        require(isinstance(reason, str) and 10 <= len(reason.strip()) <= 1000, 'APPROVAL_REASON_REQUIRED')
        require((self.root / 'candidate.json').is_file(), 'MODEL_NOT_VALIDATED')
        candidate = verify(strict_json((self.root / 'candidate.json').read_bytes()), self.public_key)
        require(candidate['validation'] == 'quantized_training_parity_passed', 'MODEL_NOT_VALIDATED')
        require(all(candidate[k] == v for k, v in self.meta.items()), 'MODEL_CONTEXT_MISMATCH')
        record = dict(
            status='approved_for_shadow_evaluation',
            candidate_sha256=sha(canonical(candidate)),
            actor_id=self.scope.actor_id,
            reason=reason,
            at=datetime.now(timezone.utc).isoformat(),
            operational_activation=False,
        )
        path = self.root / 'approval.json'
        if path.exists():
            require(strict_json(path.read_bytes())['payload']['candidate_sha256'] == record['candidate_sha256'], 'APPROVAL_CONFLICT')
            return strict_json(path.read_bytes())
        packet = sign(record, self.signing_key())
        atomic(path, canonical(packet))
        return packet

    def predict_shadow(self, x, *, mapping_fingerprint=None):
        self.guard()
        require('data.import' in self.scope.permissions, 'MODEL_READ_DENIED')
        require((self.root / 'approval.json').is_file(), 'MODEL_NOT_APPROVED')
        candidate = verify(strict_json((self.root / 'candidate.json').read_bytes()), self.public_key)
        approval = verify(strict_json((self.root / 'approval.json').read_bytes()), self.public_key)
        require(
            approval['candidate_sha256'] == sha(canonical(candidate))
            and approval['status'] == 'approved_for_shadow_evaluation',
            'MODEL_NOT_APPROVED',
        )
        require(all(candidate[k] == v for k, v in self.meta.items()), 'MODEL_CONTEXT_MISMATCH')
        cand_prof = candidate.get('profile_version')
        node_prof = getattr(self, 'profile_version', None)
        if cand_prof is not None and node_prof is not None and cand_prof != node_prof:
            raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
        if candidate.get('training_provenance') is not None:
            require(mapping_fingerprint == candidate['training_provenance']['mapping']['fingerprint'], 'SNAPSHOT_FEATURE_MAPPING_REQUIRED')
        require(
            isinstance(x, list)
            and all(isinstance(row, list) and len(row) == 2 and all(type(v) is int and -1 <= v <= 1 for v in row) for row in x),
            'FEATURE_DOMAIN',
        )
        scores = [
            1 / (1 + math.exp(-(sum(v * w for v, w in zip(row, candidate['coefficients'])) + candidate['intercept'])))
            for row in x
        ]
        return dict(
            target=TARGET,
            profile_version=cand_prof or PROFILE_VERSION,
            execution_mode=candidate.get('execution_mode', EXECUTION_MODE_VERIFIED),
            scores=scores,
            uncalibrated=True,
            shadow_only=True,
            fraud_verdicts=False,
            operational_queue_changed=False,
        )
