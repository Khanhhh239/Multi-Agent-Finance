"""Encrypted logistic-regression training with CKKS (TenSEAL): the station sees labels, never transaction features.

Protocol (one company, one epoch):
  1. The company encrypts each feature column (one CKKS vector per feature over its rows) under its own secret key and
     sends the station the ciphertexts, its public context (relinearisation + Galois keys, no secret key) and the labels.
  2. The station holds plaintext weights w, b and computes homomorphically
        z = b + sum_j w_j * Enc(col_j)          (encrypted score per row)
        r = sigmoid3(z) - y                       (degree-3 sigmoid approximation, labels are plaintext)
        g_j = sum_i Enc(col_j)_i * r_i,  g_b = sum_i r_i
  3. Only the company can decrypt; it returns the aggregated gradient (d+1 numbers for all its rows together).
  4. The station averages gradients over companies and updates w, b. Validation scores are decrypted the same way.
The station never holds a secret key and never sees per-row features. A company sees only its own aggregate gradient.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import tenseal as ts

POLY_DEGREE = 16384
COEFF_BITS = [60, 40, 40, 40, 40, 40, 60]
SCALE = 2 ** 40
SIGMOID3 = [0.5, 0.197, 0.0, -0.004]  # sigmoid(z) on |z| <= 5 (Kim et al., iDASH 2017)
MAX_ROWS = POLY_DEGREE // 2


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'))


class CompanyNode:
    """Company-side key holder: generates and keeps the CKKS secret key, encrypts, decrypts aggregates only."""

    def __init__(self, root, company: str):
        self.dir = Path(root) / company
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.company = company
        self.secret_file = self.dir / 'ckks-secret.ctx'
        if os.name != 'nt':
            # The secret key must stay owner-only on a shared Linux host (mkdir's mode is reduced by umask).
            os.chmod(self.dir, 0o700)
            if self.secret_file.is_file():
                os.chmod(self.secret_file, 0o600)
        if self.secret_file.is_file():
            self.ctx = ts.context_from(self.secret_file.read_bytes())
        else:
            ctx = ts.context(ts.SCHEME_TYPE.CKKS, POLY_DEGREE, coeff_mod_bit_sizes=COEFF_BITS)
            ctx.global_scale = SCALE
            ctx.generate_galois_keys()
            ctx.generate_relin_keys()
            temporary = self.dir / '.ckks-secret.ctx.tmp'
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_BINARY', 0), 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(ctx.serialize(save_secret_key=True))
            os.replace(temporary, self.secret_file)
            self.ctx = ctx

    def public_context(self) -> bytes:
        return self.ctx.serialize(save_secret_key=False)

    def encrypt_columns(self, rows, features) -> list[str]:
        if not rows or len(rows) > MAX_ROWS:
            raise ValueError('CKKS_ROW_LIMIT')
        return [_b64(ts.ckks_vector(self.ctx, [float(r['x'][j]) for r in rows]).serialize()) for j in range(len(features))]

    def decrypt_aggregate(self, ciphertexts: list[str], expected: int) -> list[float]:
        """Decrypt only short aggregates (a gradient of d+1 sums, or the scores of the company's own validation rows)."""
        if len(ciphertexts) > expected:
            raise ValueError('DECRYPT_REQUEST_TOO_LARGE')
        out = []
        for c in ciphertexts:
            vec = ts.ckks_vector_from(self.ctx, _unb64(c))
            out.extend(vec.decrypt())
        return out


def package(node: CompanyNode, train, holdout, features) -> dict:
    """What the company sends to the station: public context, encrypted columns, plaintext labels."""
    return dict(company_id=node.company, features=list(features), public_context=_b64(node.public_context()),
                train_cols=node.encrypt_columns(train, features), train_y=[int(r['y']) for r in train],
                holdout_cols=node.encrypt_columns(holdout, features), holdout_y=[int(r['y']) for r in holdout])


class StationView:
    """Station-side computation on one company's ciphertexts (public context only)."""

    def __init__(self, pkg: dict):
        self.pkg = pkg
        self.ctx = ts.context_from(_unb64(pkg['public_context']))
        if self.ctx.is_private():
            raise ValueError('STATION_RECEIVED_SECRET_KEY')
        self.train = [ts.ckks_vector_from(self.ctx, _unb64(c)) for c in pkg['train_cols']]
        self.holdout = [ts.ckks_vector_from(self.ctx, _unb64(c)) for c in pkg['holdout_cols']]

    @staticmethod
    def _score(cols, w, b):
        z = cols[0] * float(w[0])
        for j in range(1, len(cols)):
            z = z + cols[j] * float(w[j])
        return z + float(b)

    def gradient(self, w, b) -> list[str]:
        z = self._score(self.train, w, b)
        r = z.polyval(SIGMOID3) - [float(y) for y in self.pkg['train_y']]
        grads = [(col * r).sum() for col in self.train] + [r.sum()]
        return [_b64(g.serialize()) for g in grads]

    def holdout_scores(self, w, b) -> list[str]:
        return [_b64(self._score(self.holdout, w, b).serialize())]


def dumps(pkg: dict) -> str:
    return json.dumps(pkg)
