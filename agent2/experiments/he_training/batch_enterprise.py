"""Enterprise multi-batch training, isolated holdout and immutable label consent."""
from datetime import datetime, timezone
import hashlib
import hmac
import math
import secrets

from experiments.he_inference.key_manager import PROVIDER, load_key
from . import (
    EXECUTION_MODE_NATIVE,
    EXECUTION_MODE_VERIFIED,
    PROFILE,
    PROFILE_VERSION,
    TARGET,
    resolve_quantization_profile,
)
from . import batch_protocol as p
from .circuit import oracle
from .enterprise import Enterprise, verified_labels
from .protocol import TrainingError, atomic, canonical, fields, require, sha, sign, strict_json, verify


class BatchEnterprise(Enterprise):
    def bbase(self, dataset):
        prof_id = getattr(self, 'profile_spec', {}).get('profile_id', PROFILE)
        return dict(version=p.VERSION, profile=prof_id, target=TARGET, **self.meta, dataset_id=dataset['dataset_id'])

    def commitment(self, purpose, value):
        key = load_key(self.wrap_file, required_provider=PROVIDER).material
        return hmac.new(key, ('he-training-batch-' + purpose + '\x00').encode() + canonical(value), hashlib.sha256).hexdigest()

    def saved(self, name):
        body = verify(strict_json((self.root / name).read_bytes()), self.public_key)
        require(body['context'] == self.meta, 'BATCH_LOCAL_CONTEXT')
        return body

    def save_once(self, name, body):
        path = self.root / name
        if path.exists():
            require(self.saved(name) == body, 'BATCH_LOCAL_IMMUTABLE')
        else:
            atomic(path, canonical(sign(body, self.signing_key())))
        return body

    def prepare_batches(self, training, evaluation, *, simulated, provenance=None):
        self.guard('model.fit')
        require(type(simulated) is bool, 'SOURCE_MODE_REQUIRED')
        require(isinstance(training, list) and 2 <= len(training) <= 4 and isinstance(evaluation, list) and 1 <= len(evaluation) <= 4, 'BATCH_COUNT')
        require(provenance is not None or simulated is True, 'REAL_SOURCE_REQUIRES_SNAPSHOT_PLAN')
        seen = set()
        for batch in training + evaluation:
            fields(batch, {'x', 'row_ids'})
            require(
                isinstance(batch['row_ids'], list)
                and len(batch['row_ids']) == 4
                and all(isinstance(r, str) and 0 < len(r) <= 100 and r not in seen for r in batch['row_ids']),
                'TRAIN_EVALUATION_OVERLAP_OR_DUPLICATE',
            )
            require(len(set(batch['row_ids'])) == 4, 'BATCH_DUPLICATE_ROWS')
            seen.update(batch['row_ids'])
            require(
                isinstance(batch['x'], list)
                and len(batch['x']) == 4
                and all(isinstance(r, list) and len(r) == 2 and all(type(v) is int and -1 <= v <= 1 for v in r) for r in batch['x']),
                'FEATURE_DOMAIN',
            )
        content = dict(training=training, evaluation=evaluation, simulated=simulated, provenance=provenance)
        if (self.root / 'batch-source.json').exists():
            source = self.saved('batch-source.json')
            require(source['content'] == content, 'BATCH_DATASET_IMMUTABLE')
        else:
            source = self.save_once('batch-source.json', dict(context=self.meta, dataset_id='bds_' + secrets.token_hex(16), content=content))
        batches = []
        for i, batch in enumerate(training):
            name = f'batch-x-{i}.json'
            if (self.root / name).exists():
                cached = self.saved(name)
            else:
                encrypted = self.helper('encrypt-data', dict(x=batch['x']))
                cipher_only = {k: encrypted[k] for k in ('x_cipher', 'x_cipher_sha256')}
                cached = self.save_once(
                    name,
                    dict(context=self.meta, dataset_id=source['dataset_id'], index=i, input_sha256=sha(canonical(batch)), encrypted=cipher_only),
                )
            require(
                cached['dataset_id'] == source['dataset_id']
                and cached['index'] == i
                and cached['input_sha256'] == sha(canonical(batch)),
                'BATCH_ENCRYPTION_CACHE_MISMATCH',
            )
            cipher_fields = {k: cached['encrypted'][k] for k in ('x_cipher', 'x_cipher_sha256')}
            batches.append(dict(index=i, rows=4, features=2, **cipher_fields))
        body = dict(
            **self.bbase(source),
            batches=batches,
            batch_manifest_sha256=p.manifest(batches),
            training_commitment=self.commitment('training', dict(training=training, provenance=provenance)),
            evaluation_commitment=self.commitment('evaluation', dict(evaluation=evaluation, provenance=provenance)),
        )
        path = self.root / 'batch-upload.json'
        if path.exists():
            require(verify(strict_json(path.read_bytes()), self.public_key) == body, 'BATCH_UPLOAD_IMMUTABLE')
        else:
            atomic(path, canonical(sign(body, self.signing_key())))
        return source

    def prepare_snapshot_batches(self, store, request, *, expected_plan_sha256):
        self.guard('model.fit')
        from .batch_plan import prepare_batch_plan
        plan = prepare_batch_plan(store, self.scope, request, self.recheck)
        require(plan['status'] == 'ready', 'BATCH_SNAPSHOT_NOT_READY')
        require(plan['plan_sha256'] == expected_plan_sha256, 'BATCH_PREVIEW_STALE')
        parts = plan['parts']
        return self.prepare_batches(
            *[[dict(x=v['plan']['x'], row_ids=v['plan']['row_ids']) for v in parts[k]] for k in ('training', 'evaluation')],
            simulated=plan['simulated'],
            provenance=plan,
        )

    def upload_batches(self, url, worker_key):
        self.guard()
        source = self.saved('batch-source.json')
        packet = strict_json((self.root / 'batch-upload.json').read_bytes())
        body = verify(packet, self.public_key)
        receipt, signed = self.post(url, '/v2/datasets', packet, worker_key)
        expected = dict(
            **self.bbase(source),
            kind='batch_dataset_received',
            upload_sha256=sha(canonical(packet)),
            **{k: body[k] for k in ('batch_manifest_sha256', 'training_commitment', 'evaluation_commitment')},
            batch_count=len(body['batches']),
        )
        require(receipt == expected, 'BATCH_RECEIPT_MISMATCH')
        path = self.root / 'batch-receipt.json'
        if path.exists():
            require(strict_json(path.read_bytes()) == signed, 'BATCH_RECEIPT_CHANGED')
        else:
            atomic(path, canonical(signed))
        return signed

    def batch_review_templates(self):
        self.guard()
        source = self.saved('batch-source.json')
        receipt = strict_json((self.root / 'batch-receipt.json').read_bytes())
        return [
            dict(
                target=TARGET,
                revision=1,
                verification_mode='synthetic_expected' if source['content']['simulated'] else 'human_verified',
                tenant_id=self.scope.tenant_id,
                company_id=self.company,
                dataset_id=source['dataset_id'],
                receipt_sha256=sha(canonical(receipt)),
                rows=[dict(record_id=r, outcome=None, verified_by=self.scope.actor_id, verified_at=None, evidence_refs=[]) for r in batch['row_ids']],
            )
            for batch in source['content']['training']
        ]

    def confirm_batch_reviews(self, url, worker_key, reviews, *, epochs=1, initial_weights=None):
        self.guard('model.fit')
        source = self.saved('batch-source.json')
        receipt = strict_json((self.root / 'batch-receipt.json').read_bytes())
        require(source['content']['simulated'] is True, 'REAL_BATCH_LABELS_REQUIRE_LOCKED_PACKETS')
        require(isinstance(reviews, list) and len(reviews) == len(source['content']['training']), 'BATCH_LABEL_COUNT')
        labels = [
            verified_labels(
                review,
                batch['row_ids'],
                self.scope,
                simulated=source['content']['simulated'],
                dataset_id=source['dataset_id'],
                receipt_sha256=sha(canonical(receipt)),
                require_both_classes=False,
            )
            for batch, review in zip(source['content']['training'], reviews)
        ]
        return self._confirm_batches(url, worker_key, reviews, labels, epochs, initial_weights=initial_weights)

    def confirm_locked_batches(self, url, worker_key, label_store, locks, *, epochs=1):
        """Read prior attestations, not a fresh verification by the fitting actor."""
        self.guard('model.fit')
        source = self.saved('batch-source.json')
        plan = source['content']['provenance']
        require(plan is not None and isinstance(locks, list) and len(locks) == len(source['content']['training']), 'BATCH_LABEL_LOCKS_REQUIRED')
        reviews = []
        labels = []
        for pin, child, batch in zip(locks, plan['parts']['training'], source['content']['training']):
            fields(pin, {'packet_id', 'revision', 'lock_sha256'})
            exported = label_store.export(self.scope, pin['packet_id'], pin['revision'], pin['lock_sha256'], self.recheck)
            current = label_store.get(self.scope, pin['packet_id'], self.recheck)
            require(current['locked'] is True, 'LABEL_PACKET_NOT_LOCKED')
            require(current['revision'] == pin['revision'] and current['lock_sha256'] == pin['lock_sha256'], 'LABEL_PACKET_REVISION_STALE')
            require(exported['target'] == TARGET and exported['binding']['source_plan_sha256'] == child['plan']['plan_sha256'], 'BATCH_LABEL_SOURCE_MISMATCH')
            require(exported['binding']['simulated'] == source['content']['simulated'] and exported['binding']['feature_status'] == 'ready', 'BATCH_LABEL_MODE_FEATURE_MISMATCH')
            require(
                [r['record_id'] for r in exported['labels']] == batch['row_ids']
                and [r['revision'] for r in exported['labels']] == [r['revision'] for r in child['request']['rows']],
                'BATCH_LABEL_ROW_ORDER',
            )
            require(all(r['outcome'] in ('verified_fraud', 'verified_non_fraud') for r in exported['labels']), 'BATCH_LABELS_INCOMPLETE')
            reviews.append(exported)
            labels.append([int(r['outcome'] == 'verified_fraud') for r in exported['labels']])
        return self._confirm_batches(url, worker_key, reviews, labels, epochs)

    def _confirm_batches(self, url, worker_key, reviews, labels, epochs, *, initial_weights=None):
        self.guard('model.fit')
        source = self.saved('batch-source.json')
        count = len(source['content']['training'])
        require(type(epochs) is int and epochs >= 1 and count * epochs <= 4, 'BATCH_UPDATE_LIMIT')
        require(set(v for batch in labels for v in batch) == {0, 1}, 'BOTH_LABEL_CLASSES_REQUIRED')
        receipt = strict_json((self.root / 'batch-receipt.json').read_bytes())
        verify(receipt, worker_key)
        upload = verify(strict_json((self.root / 'batch-upload.json').read_bytes()), self.public_key)
        require(receipt['payload']['upload_sha256'] == sha((self.root / 'batch-upload.json').read_bytes()), 'BATCH_RECEIPT_MISMATCH')
        intent_body = dict(context=self.meta, dataset_id=source['dataset_id'], reviews=reviews, labels=labels, epochs=epochs)
        if initial_weights is not None:
            intent_body['initial_weights'] = [int(v) for v in initial_weights]
        intent = self.save_once('batch-verified-reviews.json', intent_body)
        batches = []
        initial = None
        for i, (review, y) in enumerate(zip(reviews, labels)):
            name = f'batch-y-{i}.json'
            commitment = self.commitment('review', dict(dataset_id=source['dataset_id'], index=i, review=review, y=y))
            if (self.root / name).exists():
                cached = self.saved(name)
            else:
                req = dict(y=y, initialize_weights=(i == 0))
                if i == 0 and initial_weights is not None:
                    req['initial_weights'] = [int(v) for v in initial_weights]
                encrypted = self.helper('encrypt-batch-labels', req)
                keep_keys = ('y_cipher', 'y_cipher_sha256') + (('weights_cipher', 'weights_cipher_sha256') if i == 0 else ())
                cipher_only = {k: encrypted[k] for k in keep_keys}
                cached = self.save_once(
                    name,
                    dict(context=self.meta, dataset_id=source['dataset_id'], index=i, review_commitment=commitment, encrypted=cipher_only),
                )
            require(
                cached['dataset_id'] == source['dataset_id']
                and cached['index'] == i
                and cached['review_commitment'] == commitment,
                'BATCH_LABEL_CACHE_MISMATCH',
            )
            enc = cached['encrypted']
            if i == 0:
                initial = {k: enc[k] for k in ('weights_cipher', 'weights_cipher_sha256')}
            batches.append(dict(
                index=i,
                label_revision=review['revision'],
                review_commitment=commitment,
                **{k: enc[k] for k in ('y_cipher', 'y_cipher_sha256')},
            ))
        path = self.root / 'batch-consent.json'
        body = dict(
            **self.bbase(source),
            consent_id='bc_' + sha(canonical(intent))[:32],
            receipt_sha256=sha(canonical(receipt)),
            **{k: upload[k] for k in ('batch_manifest_sha256', 'training_commitment', 'evaluation_commitment')},
            label_batches=batches,
            epochs=epochs,
            verification_mode='synthetic_expected' if source['content']['simulated'] else 'human_verified',
            **initial,
        )
        if path.exists():
            packet = strict_json(path.read_bytes())
            require(verify(packet, self.public_key) == body, 'BATCH_CONSENT_IMMUTABLE')
        else:
            packet = sign(body, self.signing_key())
            atomic(path, canonical(packet))
        result, signed = self.post(url, '/v2/confirm', packet, worker_key)
        self.check_batch_result(result, source, packet)
        atomic(self.root / 'batch-job.json', canonical(signed))
        return result

    def check_batch_result(self, result, source, consent):
        body = verify(consent, self.public_key)
        require(all(result[k] == v for k, v in self.bbase(source).items()), 'BATCH_RESULT_CONTEXT')
        require(
            result['job_id'] == 'btr_' + sha(canonical(consent))[:32]
            and result['consent_sha256'] == sha(canonical(consent)),
            'BATCH_RESULT_CONSENT',
        )
        require(
            all(result[k] == body[k] for k in ('batch_manifest_sha256', 'training_commitment', 'evaluation_commitment'))
            and result['total_updates'] == len(body['label_batches']) * body['epochs'],
            'BATCH_RESULT_BINDING',
        )

    def access_batches(self, url, worker_key, action):
        self.guard('model.fit' if action == 'run' else 'data.import')
        source = self.saved('batch-source.json')
        consent = strict_json((self.root / 'batch-consent.json').read_bytes())
        verify(consent, self.public_key)
        packet = sign(dict(**self.bbase(source), job_id='btr_' + sha(canonical(consent))[:32], action=action), self.signing_key())
        result, signed = self.post(url, '/v2/jobs', packet, worker_key)
        self.check_batch_result(result, source, consent)
        return result, signed

    def receive_batches(self, url, worker_key):
        self.guard()
        result, signed = self.access_batches(url, worker_key, 'result')
        require(result['status'] == 'completed' and result['completed_updates'] == result['total_updates'], 'BATCH_TRAINING_NOT_COMPLETED')
        source = self.saved('batch-source.json')
        intent = self.saved('batch-verified-reviews.json')
        consent = verify(strict_json((self.root / 'batch-consent.json').read_bytes()), self.public_key)
        require(intent['dataset_id'] == source['dataset_id'] and intent['epochs'] == consent['epochs'], 'BATCH_REVIEW_BINDING')
        prof_ver = getattr(self, 'profile_version', PROFILE_VERSION)
        weights = list(intent.get('initial_weights') or [0, 0, 0])
        for _ in range(consent['epochs']):
            for i, batch in enumerate(source['content']['training']):
                require(
                    self.commitment('review', dict(dataset_id=source['dataset_id'], index=i, review=intent['reviews'][i], y=intent['labels'][i]))
                    == consent['label_batches'][i]['review_commitment'],
                    'BATCH_REVIEW_TAMPERED',
                )
                weights = oracle(batch['x'], intent['labels'][i], weights, profile_version=prof_ver)
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
        require(actual['weights_code'] == weights, 'BATCH_DECRYPTED_PARITY_FAILED')
        prof_spec = resolve_quantization_profile(prof_ver)
        # Ensure coefficients/intercept reflect exact profile scale if caller used minimal test helper
        if 'profile_version' not in actual:
            w_scale = float(prof_spec['weight_scale'])
            b_scale = float(prof_spec['bias_scale'])
            actual = dict(
                actual,
                profile_version=prof_ver,
                weight_scale=prof_spec['weight_scale'],
                bias_scale=prof_spec['bias_scale'],
                probability_scale=prof_spec['probability_scale'],
                coefficients=[float(weights[0]) / w_scale, float(weights[1]) / w_scale],
                intercept=float(weights[2]) / b_scale,
            )
        exec_mode = actual.get('execution_mode', getattr(self, 'execution_mode', EXECUTION_MODE_VERIFIED))
        candidate = {
            **actual,
            **self.meta,
            'version': p.VERSION,
            'profile_version': prof_ver,
            'execution_mode': exec_mode,
            'native_fhe_executed': (exec_mode == EXECUTION_MODE_NATIVE),
            'dataset_id': source['dataset_id'],
            'job_id': result['job_id'],
            'consent_sha256': result['consent_sha256'],
            'model_cipher_sha256': result['model_cipher_sha256'],
            'training_commitment': consent['training_commitment'],
            'evaluation_commitment': consent['evaluation_commitment'],
            'training_rows': 4 * len(source['content']['training']),
            'evaluation_rows': 4 * len(source['content']['evaluation']),
            'completed_updates': result['completed_updates'],
            'validation': 'quantized_batch_oracle_exact',
            'operational_activation': False,
        }
        atomic(self.root / 'batch-candidate.json', canonical(sign(dict(context=self.meta, candidate=candidate), self.signing_key())))
        atomic(self.root / 'batch-model-result.json', canonical(signed))
        return candidate

    def evaluate_holdout(self, *, label_store=None, evaluation_locks=None):
        self.guard()
        require((self.root / 'batch-candidate.json').is_file(), 'BATCH_MODEL_NOT_RECEIVED')
        source = self.saved('batch-source.json')
        candidate = self.saved('batch-candidate.json')['candidate']
        require(
            candidate['dataset_id'] == source['dataset_id']
            and candidate['evaluation_commitment'] == self.commitment('evaluation', dict(evaluation=source['content']['evaluation'], provenance=source['content']['provenance'])),
            'EVALUATION_SOURCE_MISMATCH',
        )
        provenance = source['content']['provenance']
        verified_by_id = {}
        holdout_labels = None
        if evaluation_locks is not None:
            require(
                label_store is not None
                and provenance is not None
                and isinstance(evaluation_locks, list)
                and len(evaluation_locks) == len(source['content']['evaluation']),
                'BATCH_EVALUATION_LOCKS_REQUIRED',
            )
            lock_summaries = []
            for pin, child, batch in zip(evaluation_locks, provenance['parts']['evaluation'], source['content']['evaluation']):
                fields(pin, {'packet_id', 'revision', 'lock_sha256'})
                exported = label_store.export(self.scope, pin['packet_id'], pin['revision'], pin['lock_sha256'], self.recheck)
                current = label_store.get(self.scope, pin['packet_id'], self.recheck)
                require(current['locked'] is True, 'LABEL_PACKET_NOT_LOCKED')
                require(current['revision'] == pin['revision'] and current['lock_sha256'] == pin['lock_sha256'], 'LABEL_PACKET_REVISION_STALE')
                require(exported['target'] == TARGET and exported['binding']['source_plan_sha256'] == child['plan']['plan_sha256'], 'BATCH_EVALUATION_LABEL_SOURCE_MISMATCH')
                require(exported['binding']['simulated'] == source['content']['simulated'] and exported['binding']['feature_status'] == 'ready', 'BATCH_EVALUATION_LABEL_MODE_MISMATCH')
                require(
                    [r['record_id'] for r in exported['labels']] == batch['row_ids']
                    and [r['revision'] for r in exported['labels']] == [r['revision'] for r in child['request']['rows']],
                    'BATCH_EVALUATION_LABEL_ROW_ORDER',
                )
                for r in exported['labels']:
                    verified_by_id[r['record_id']] = r['outcome']
                lock_summaries.append(dict(packet_id=pin['packet_id'], revision=pin['revision'], lock_sha256=pin['lock_sha256']))
            outcomes = list(verified_by_id.values())
            holdout_labels = dict(
                verified=True,
                labels_used_for_fit=False,
                locks=lock_summaries,
                labelled_rows=sum(v in ('verified_fraud', 'verified_non_fraud') for v in outcomes),
                fraud_rows=sum(v == 'verified_fraud' for v in outcomes),
                non_fraud_rows=sum(v == 'verified_non_fraud' for v in outcomes),
                unlabelled_rows=sum(v is None for v in outcomes),
            )
        rows = []
        for batch_index, batch in enumerate(source['content']['evaluation']):
            for rid, x in zip(batch['row_ids'], batch['x']):
                z = sum(a * b for a, b in zip(x, candidate['coefficients'])) + candidate['intercept']
                row = dict(record_id=rid, batch_index=batch_index, score=1 / (1 + math.exp(-z)))
                if evaluation_locks is not None:
                    row['verified_outcome'] = verified_by_id.get(rid)
                rows.append(row)
        result = dict(
            dataset_id=source['dataset_id'],
            job_id=candidate['job_id'],
            profile_version=candidate.get('profile_version', PROFILE_VERSION),
            execution_mode=candidate.get('execution_mode', EXECUTION_MODE_VERIFIED),
            model_cipher_sha256=candidate['model_cipher_sha256'],
            candidate_sha256=sha(canonical(candidate)),
            plan_sha256=provenance['plan_sha256'] if provenance else None,
            snapshot_id=provenance['snapshot']['snapshot_id'] if provenance else None,
            evaluation_window=dict(
                start=provenance['request']['evaluation_start'],
                end=provenance['request']['evaluation_end'],
                as_of=provenance['request']['as_of'],
            ) if provenance else None,
            evaluation_commitment=candidate['evaluation_commitment'],
            evaluation_batches=len(source['content']['evaluation']),
            evaluation_rows=len(rows),
            rows=rows,
            holdout_labels=holdout_labels,
            uncalibrated=True,
            held_out_from_training=True,
            labels_used_for_fit=False,
            accuracy=None,
            fraud_verdicts=False,
            operational_queue_changed=False,
        )
        atomic(self.root / 'batch-evaluation.json', canonical(sign(dict(context=self.meta, evaluation=result), self.signing_key())))
        self.guard()
        return result

    def approve_batches(self, reason, *, expected_model_cipher_sha256=None, expected_plan_sha256=None, expected_evaluation_sha256=None):
        self.guard('model.fit')
        require('model.fit' in self.scope.permissions, 'MODEL_FIT_DENIED')
        require(isinstance(reason, str) and 10 <= len(reason.strip()) <= 1000, 'APPROVAL_REASON_REQUIRED')
        require((self.root / 'batch-candidate.json').is_file(), 'BATCH_MODEL_NOT_RECEIVED')
        require((self.root / 'batch-evaluation.json').is_file(), 'BATCH_HOLDOUT_EVALUATION_REQUIRED')
        source = self.saved('batch-source.json')
        candidate = self.saved('batch-candidate.json')['candidate']
        evaluation = self.saved('batch-evaluation.json')['evaluation']
        require(candidate['validation'] == 'quantized_batch_oracle_exact' and candidate['dataset_id'] == source['dataset_id'], 'BATCH_MODEL_NOT_VALIDATED')
        require(
            evaluation['dataset_id'] == source['dataset_id']
            and evaluation['model_cipher_sha256'] == candidate['model_cipher_sha256']
            and evaluation['evaluation_commitment'] == candidate['evaluation_commitment'],
            'BATCH_EVALUATION_BINDING_MISMATCH',
        )
        provenance = source['content']['provenance']
        plan_sha256 = provenance['plan_sha256'] if provenance else None
        evaluation_sha256 = sha(canonical(evaluation))
        candidate_sha256 = sha(canonical(candidate))
        if expected_model_cipher_sha256 is not None:
            require(expected_model_cipher_sha256 == candidate['model_cipher_sha256'], 'BATCH_APPROVAL_MODEL_MISMATCH')
        if expected_plan_sha256 is not None:
            require(expected_plan_sha256 == plan_sha256, 'BATCH_APPROVAL_PLAN_MISMATCH')
        if expected_evaluation_sha256 is not None:
            require(expected_evaluation_sha256 == evaluation_sha256, 'BATCH_APPROVAL_EVALUATION_MISMATCH')
        record = dict(
            version=p.VERSION,
            profile_version=candidate.get('profile_version', PROFILE_VERSION),
            execution_mode=candidate.get('execution_mode', EXECUTION_MODE_VERIFIED),
            target=TARGET,
            status='approved_for_shadow_evaluation',
            tenant_id=self.scope.tenant_id,
            company_id=self.company,
            dataset_id=source['dataset_id'],
            job_id=candidate['job_id'],
            consent_sha256=candidate['consent_sha256'],
            candidate_sha256=candidate_sha256,
            model_cipher_sha256=candidate['model_cipher_sha256'],
            plan_sha256=plan_sha256,
            evaluation_sha256=evaluation_sha256,
            training_commitment=candidate['training_commitment'],
            evaluation_commitment=candidate['evaluation_commitment'],
            actor_id=self.scope.actor_id,
            reason=reason.strip(),
            at=datetime.now(timezone.utc).isoformat(),
            shadow_only=True,
            operational_activation=False,
            active_model_replaced=False,
            operational_queue_changed=False,
        )
        path = self.root / 'batch-approval.json'
        if path.exists():
            existing = verify(strict_json(path.read_bytes()), self.public_key)
            require(
                existing['candidate_sha256'] == record['candidate_sha256']
                and existing['plan_sha256'] == record['plan_sha256']
                and existing['evaluation_sha256'] == record['evaluation_sha256'],
                'BATCH_APPROVAL_CONFLICT',
            )
            return strict_json(path.read_bytes())
        packet = sign(record, self.signing_key())
        atomic(path, canonical(packet))
        return packet

    def predict_batch_shadow(self, x, *, row_ids=None, mapping_fingerprint=None):
        self.guard()
        require('data.import' in self.scope.permissions, 'MODEL_READ_DENIED')
        require((self.root / 'batch-approval.json').is_file(), 'BATCH_MODEL_NOT_APPROVED')
        source = self.saved('batch-source.json')
        candidate = self.saved('batch-candidate.json')['candidate']
        approval = verify(strict_json((self.root / 'batch-approval.json').read_bytes()), self.public_key)
        require(
            approval['status'] == 'approved_for_shadow_evaluation'
            and approval['candidate_sha256'] == sha(canonical(candidate))
            and approval['model_cipher_sha256'] == candidate['model_cipher_sha256'],
            'BATCH_MODEL_NOT_APPROVED',
        )
        cand_prof = candidate.get('profile_version')
        node_prof = getattr(self, 'profile_version', None)
        if cand_prof is not None and node_prof is not None and cand_prof != node_prof:
            raise TrainingError('LEGACY_MODEL_PROFILE_MISMATCH')
        provenance = source['content']['provenance']
        if provenance is not None:
            require(approval['plan_sha256'] == provenance['plan_sha256'], 'BATCH_APPROVAL_PLAN_MISMATCH')
            require(mapping_fingerprint == provenance['mapping_fingerprint'], 'SNAPSHOT_FEATURE_MAPPING_REQUIRED')
        require(
            isinstance(x, list)
            and 1 <= len(x) <= 64
            and all(isinstance(row, list) and len(row) == 2 and all(type(v) is int and -1 <= v <= 1 for v in row) for row in x),
            'FEATURE_DOMAIN',
        )
        if row_ids is not None:
            require(
                isinstance(row_ids, list)
                and len(row_ids) == len(x)
                and all(isinstance(r, str) and 0 < len(r) <= 100 for r in row_ids),
                'SHADOW_ROW_IDS_INVALID',
            )
        scores = [
            1 / (1 + math.exp(-(sum(v * w for v, w in zip(row, candidate['coefficients'])) + candidate['intercept'])))
            for row in x
        ]
        rows = [dict(record_id=row_ids[i] if row_ids is not None else f'row_{i}', score=s) for i, s in enumerate(scores)]
        return dict(
            version=p.VERSION,
            profile_version=cand_prof or PROFILE_VERSION,
            execution_mode=candidate.get('execution_mode', EXECUTION_MODE_VERIFIED),
            target=TARGET,
            tenant_id=self.scope.tenant_id,
            company_id=self.company,
            dataset_id=source['dataset_id'],
            job_id=candidate['job_id'],
            model_cipher_sha256=candidate['model_cipher_sha256'],
            candidate_sha256=approval['candidate_sha256'],
            plan_sha256=approval['plan_sha256'],
            evaluation_sha256=approval['evaluation_sha256'],
            approved_by=approval['actor_id'],
            approved_at=approval['at'],
            scores=scores,
            rows=rows,
            uncalibrated=True,
            shadow_only=True,
            operational_activation=False,
            active_model_replaced=False,
            fraud_verdicts=False,
            operational_queue_changed=False,
        )

    def evaluate_shadow_holdout(self):
        self.guard()
        require((self.root / 'batch-approval.json').is_file(), 'BATCH_MODEL_NOT_APPROVED')
        source = self.saved('batch-source.json')
        provenance = source['content']['provenance']
        xs = [row for batch in source['content']['evaluation'] for row in batch['x']]
        rids = [rid for batch in source['content']['evaluation'] for rid in batch['row_ids']]
        res = self.predict_batch_shadow(xs, row_ids=rids, mapping_fingerprint=provenance['mapping_fingerprint'] if provenance else None)
        res.update(
            evaluation_commitment=self.commitment('evaluation', dict(evaluation=source['content']['evaluation'], provenance=provenance)),
            evaluation_rows=len(rids),
            held_out_from_training=True,
            labels_used_for_fit=False,
            accuracy=None,
        )
        return res
