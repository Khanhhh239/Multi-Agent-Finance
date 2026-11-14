"""Enterprise-only fit, private keys, feature preparation and result opening."""
import time
import uuid

import numpy as np
import tenseal as ts
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sme_fraud.unsupervised_statistics import ShrunkMahalanobis
from .protocol import (ABS_TOLERANCE, BINDING, CONTRACT, MAX_CIPHER, MAX_NORMALIZED,
                       MAX_ROWS, MAX_WEIGHT, PAIRS, PROFILE, VERSION, b64, canonical,
                       identifier, public_hex, require, sha, sign, unb64, verify)


def numeric_pair(values, maximum_rows=None):
    require(isinstance(values, (list, np.ndarray)), 'INPUT_TYPE')
    # Missing values and booleans must not become 0/1 or an imputation.
    rows = values.tolist() if isinstance(values, np.ndarray) else list(values)
    require(rows and (maximum_rows is None or len(rows) <= maximum_rows), 'ROW_LIMIT')
    from .protocol import finite
    require(all(isinstance(r, (list, tuple, np.ndarray)) and len(r) == 2
                and all(finite(v) for v in r) for r in rows), 'HE_INPUT_UNAVAILABLE')
    return np.asarray(rows, dtype=float)


class EnterpriseSession:
    """Experimental session; fitting and loading are explicitly separate paths."""
    def __init__(self, tenant, company, history, *, history_end, evaluation_start):
        require(identifier(tenant) and identifier(company), 'INVALID_IDENTIFIER')
        require(type(history_end) is int and type(evaluation_start) is int
                and history_end < evaluation_start, 'TRAIN_EVALUATION_OVERLAP')
        x = numeric_pair(history)
        require(len(x) >= 20, 'HISTORY_TOO_SHORT')
        self.model = ShrunkMahalanobis().fit(x)
        self.evaluation_start = evaluation_start
        self._initialize_crypto(tenant, company)

    @classmethod
    def from_fitted_model(cls, tenant, company, model, *, evaluation_start):
        """Trusted local registry adapter only; this path never calls fit."""
        require(identifier(tenant) and identifier(company), 'INVALID_IDENTIFIER')
        require(type(evaluation_start) is int, 'INVALID_EVALUATION_START')
        require(type(model) is ShrunkMahalanobis, 'HE_MODEL_UNSUPPORTED')
        try:
            require(model.mean_.shape == model.std_.shape == model.cov_.location_.shape == (2,), 'HE_MODEL_SHAPE')
            require(model.cov_.precision_.shape == (2, 2), 'HE_MODEL_SHAPE')
            require(all(np.isfinite(a).all() for a in (model.mean_, model.std_, model.cov_.location_, model.cov_.precision_))
                    and (model.std_ > 0).all(), 'HE_MODEL_NUMERIC')
            require(np.allclose(model.cov_.precision_, model.cov_.precision_.T, atol=1e-12, rtol=1e-12)
                    and np.linalg.eigvalsh(model.cov_.precision_).min() >= -1e-12, 'HE_MODEL_NUMERIC')
        except AttributeError as exc:
            from .protocol import HEUnavailable
            raise HEUnavailable('HE_MODEL_SHAPE') from exc
        instance = cls.__new__(cls)
        instance.model = model
        instance.evaluation_start = evaluation_start
        instance._initialize_crypto(tenant, company)
        return instance

    def _initialize_crypto(self, tenant, company):
        precision = self.model.cov_.precision_
        self.weights = [float(precision[i, j]) * (1 if i == j else 2) for i, j in PAIRS]
        require(all(np.isfinite(w) and abs(w) <= MAX_WEIGHT for w in self.weights), 'MODEL_OUT_OF_DOMAIN')
        self.context = ts.context(ts.SCHEME_TYPE.CKKS, poly_modulus_degree=8192,
                                  coeff_mod_bit_sizes=[60, 40, 40, 60], n_threads=1)
        self.context.global_scale = 2 ** 40
        self.signer = Ed25519PrivateKey.generate()
        self.public_context = self.context.serialize(save_secret_key=False, save_galois_keys=False)
        self.binding = dict(version=VERSION, profile=PROFILE, contract=CONTRACT,
                            tenant_id=tenant, company_id=company,
                            session_id='ses_' + uuid.uuid4().hex,
                            model_id='mdl_' + uuid.uuid4().hex, key_epoch='key_' + uuid.uuid4().hex,
                            context_sha256=sha(self.public_context))
        self.pending = {}

    def prepare(self, values, worker_verify_key, *, event_times, now=None):
        x = numeric_pair(values, MAX_ROWS)
        require(len(event_times) == len(x) and all(type(t) is int and t >= self.evaluation_start for t in event_times), 'BEFORE_EVALUATION')
        centered = (x - self.model.mean_) / self.model.std_ - self.model.cov_.location_
        require(np.isfinite(centered).all() and np.max(np.abs(centered)) <= MAX_NORMALIZED, 'INPUT_OUT_OF_DOMAIN')
        n = len(x)
        weights = [ts.ckks_vector(self.context, [v] * n).serialize() for v in self.weights]
        clock = int(time.time()) if now is None else now
        p = dict(self.binding, nonce='req_' + uuid.uuid4().hex, created_at=clock, expires_at=clock + 300,
                 row_handles=['row_' + uuid.uuid4().hex for _ in range(n)], context=b64(self.public_context),
                 columns=[b64(ts.ckks_vector(self.context, centered[:, i].tolist()).serialize()) for i in range(2)],
                 quadratic=[b64(v) for v in weights])
        packet = sign(p, self.signer)
        policy = dict(self.binding, enabled=True, client_verify_key=public_hex(self.signer),
                      quadratic_sha256=[sha(v) for v in weights])
        self.pending[p['nonce']] = dict(request=packet, worker_verify_key=worker_verify_key)
        return packet, policy

    def open(self, response, nonce):
        require(nonce in self.pending, 'RESULT_NOT_PENDING')
        pending = self.pending[nonce]
        p = verify(response, pending['worker_verify_key'])
        expected = set(BINDING) | {'nonce', 'row_handles', 'request_sha256', 'ciphertext', 'worker'}
        require(set(p) == expected, 'RESULT_FIELDS')
        request = pending['request']
        require(all(p[k] == request['payload'][k] for k in BINDING + ('nonce', 'row_handles'))
                and p['request_sha256'] == sha(canonical(request)), 'RESULT_BINDING')
        require(p['worker'] == dict(has_decryption_key=False, enterprise_imported=False, sklearn_imported=False), 'WORKER_BOUNDARY')
        vector = ts.ckks_vector_from(self.context, unb64(p['ciphertext'], MAX_CIPHER))
        require(vector.size() == len(p['row_handles']), 'RESULT_LAYOUT')
        scores = vector.decrypt()
        require(len(scores) == len(p['row_handles']) and all(np.isfinite(v) and -ABS_TOLERANCE <= v <= 20000 for v in scores), 'RESULT_OUT_OF_DOMAIN')
        del self.pending[nonce]
        return scores

    def clear_circuit(self, values):
        x = numeric_pair(values)
        z = (x - self.model.mean_) / self.model.std_ - self.model.cov_.location_
        return np.asarray([sum(w * row[i] * row[j] for (i, j), w in zip(PAIRS, self.weights)) for row in z])
