"""Genuine Concrete FHE circuit for rule C3 (Duyệt dưới 60 giây ở cấp thẩm quyền cao).

All C3 arithmetic/policy predicates execute on encrypted ciphertexts:
- 64-bit signed epoch microseconds subtraction (`approved_us - created_us`)
- `0 <= dt_us < 60_000_000`
- Authority matrix band matching `min_amount_vnd <= amount_vnd <= max_amount_vnd`
  across up to 4 metadata-eligible authority candidates
- Specificity tie-breaking & `ambiguous_authority` detection across matching bands
- Legacy fallback `amount_vnd >= high_approval_vnd` when uncovered

Zero plaintext comparison on `amount_vnd` or timestamps happens before encryption.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np

C3_WORD_DIGITS = 16
RADIX = 16
MAX_AUTHORITIES = 4
MIN_DT_US = 0
LIMIT_DT_US = 60_000_000
EPOCHS_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)
MICROSECOND = timedelta(microseconds=1)
INT64_MIN = -(2**63)
INT64_MAX = (2**63) - 1

ARRAY = np.array  # compiler sets to concrete.fhe.array


def encode_word64(value: int) -> np.ndarray:
    """Encode signed int64 into 16 little-endian base-16 nibbles."""
    if type(value) is not int or not INT64_MIN <= value <= INT64_MAX:
        raise ValueError('value must fit signed int64')
    unsigned = value % (1 << 64)
    return np.array([(unsigned >> (4 * i)) & 15 for i in range(C3_WORD_DIGITS)], dtype=np.int64)


def decode_word64(word) -> int:
    """Decode 16 little-endian base-16 nibbles back into signed int64."""
    values = np.asarray(word, dtype=np.int64)
    if values.shape != (C3_WORD_DIGITS,) or np.any(values < 0) or np.any(values >= RADIX):
        raise ValueError('invalid 64-bit nibble word')
    unsigned = sum(int(v) << (4 * i) for i, v in enumerate(values))
    return unsigned - (1 << 64) if unsigned & (1 << 63) else unsigned


def timestamp_to_epoch_us(value: str) -> int:
    """Parse ISO timestamp to exact integer microseconds since Unix epoch UTC."""
    if not isinstance(value, str) or not value:
        raise ValueError('missing ISO timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=7)))
    delta = dt.astimezone(timezone.utc) - EPOCHS_UTC
    us = delta // MICROSECOND
    if not INT64_MIN <= us <= INT64_MAX:
        raise ValueError('timestamp outside int64 microseconds range')
    return int(us)


def subtract_word64(a, b):
    """Compute signed/unsigned 64-bit little-endian base-16 difference (a - b mod 2^64)."""
    out = []
    carry = 1
    for i in range(C3_WORD_DIGITS):
        total = a[i] + (RADIX - 1 - b[i]) + carry
        out.append(total % RADIX)
        carry = total // RADIX
    return ARRAY(out)


def unsigned_gt64(a, b):
    """Return 1 iff unsigned 64-bit base-16 a > b via unsigned complement carry."""
    carry = 0
    for i in range(C3_WORD_DIGITS):
        total = a[i] + (RADIX - 1 - b[i]) + carry
        carry = total // RADIX
    return carry


def signed_gt64(a, b):
    sa = a[C3_WORD_DIGITS - 1] // 8
    sb = b[C3_WORD_DIGITS - 1] // 8
    ugt = unsigned_gt64(a, b)
    same = (sa + sb) != 1
    return (same * ugt + (sa < sb)) > 0


def _max2(a, b):
    ge = (a - b) >= 0
    return ge * a + (1 - ge) * b


def c3(
    created_us,
    approved_us,
    amount,
    high_threshold,
    mode_legacy,
    rule_min,
    rule_max,
    rule_rank,
    rule_is_high,
    rule_outcome,
):
    """Encrypted C3 evaluation circuit: zero plaintext decisions on time/amount."""
    zero = np.zeros(C3_WORD_DIGITS, dtype=np.int64)
    sixty_s_us = encode_word64(LIMIT_DT_US)

    dt_us = subtract_word64(approved_us, created_us)
    # 0 <= dt_us < 60_000_000
    non_negative = 1 - signed_gt64(zero, dt_us)
    under_limit = signed_gt64(sixty_s_us, dt_us)
    fast_60s = (non_negative * under_limit) > 0

    eff_ranks = []
    for i in range(MAX_AUTHORITIES):
        ge_min = 1 - signed_gt64(rule_min[i], amount)
        le_max = 1 - signed_gt64(amount, rule_max[i])
        in_range = (rule_rank[i] > 0) * ge_min * le_max
        eff_ranks.append(in_range * rule_rank[i])

    best_rank = _max2(_max2(eff_ranks[0], eff_ranks[1]), _max2(eff_ranks[2], eff_ranks[3]))
    has_best = best_rank > 0

    selected = []
    high_votes = 0
    for i in range(MAX_AUTHORITIES):
        sel_i = has_best * (eff_ranks[i] == best_rank)
        selected.append(sel_i)
        high_votes = high_votes + sel_i * rule_is_high[i]

    conflicts = 0
    for i in range(MAX_AUTHORITIES):
        for j in range(i + 1, MAX_AUTHORITIES):
            conflicts = conflicts + selected[i] * selected[j] * ((rule_outcome[i] - rule_outcome[j]) != 0)
    ambiguous = (conflicts > 0)

    any_high = high_votes > 0
    explicit_high = (has_best * (1 - ambiguous) * any_high) > 0
    legacy_high = (1 - signed_gt64(high_threshold, amount)) > 0

    use_legacy = mode_legacy == 1
    authority_trigger = use_legacy * legacy_high + (1 - use_legacy) * explicit_high
    matched = (fast_60s * authority_trigger) > 0

    result = [matched, fast_60s, explicit_high, ambiguous, has_best, legacy_high]
    for i in range(C3_WORD_DIGITS):
        result.append(dt_us[i])
    return ARRAY(result)


def decode_c3(output) -> dict:
    values = np.asarray(output, dtype=np.int64)
    if values.shape != (6 + C3_WORD_DIGITS,) or any(v not in (0, 1) for v in values[:6]):
        raise ValueError('invalid C3 encrypted output shape')
    return dict(
        matched=bool(values[0]),
        fast_60s=bool(values[1]),
        explicit_high=bool(values[2]),
        ambiguous_authority=bool(values[3]),
        has_matching_authority=bool(values[4]),
        legacy_high=bool(values[5]),
        approval_delta_us=decode_word64(values[6:]),
    )


def samples() -> list[tuple]:
    """Full-domain randomized + boundary inputset for Concrete bit-width inference."""
    rng = np.random.default_rng(20261114)
    rows = []
    for _ in range(36):
        created = rng.integers(0, 16, C3_WORD_DIGITS, dtype=np.int64)
        approved = rng.integers(0, 16, C3_WORD_DIGITS, dtype=np.int64)
        amount = rng.integers(0, 16, C3_WORD_DIGITS, dtype=np.int64)
        high_thr = rng.integers(0, 16, C3_WORD_DIGITS, dtype=np.int64)
        mode_leg = int(rng.integers(0, 2))
        rmin = rng.integers(0, 16, (MAX_AUTHORITIES, C3_WORD_DIGITS), dtype=np.int64)
        rmax = rng.integers(0, 16, (MAX_AUTHORITIES, C3_WORD_DIGITS), dtype=np.int64)
        rrank = rng.integers(0, 5, MAX_AUTHORITIES, dtype=np.int64)
        rhigh = rng.integers(0, 2, MAX_AUTHORITIES, dtype=np.int64)
        rout = rng.integers(0, 9, MAX_AUTHORITIES, dtype=np.int64)
        rows.append((created, approved, amount, high_thr, mode_leg, rmin, rmax, rrank, rhigh, rout))

    for nibble in (0, 15):
        for flag in (0, 1):
            rows.append(
                (
                    np.full(C3_WORD_DIGITS, nibble, dtype=np.int64),
                    np.full(C3_WORD_DIGITS, nibble, dtype=np.int64),
                    np.full(C3_WORD_DIGITS, nibble, dtype=np.int64),
                    np.full(C3_WORD_DIGITS, nibble, dtype=np.int64),
                    flag,
                    np.full((MAX_AUTHORITIES, C3_WORD_DIGITS), nibble, dtype=np.int64),
                    np.full((MAX_AUTHORITIES, C3_WORD_DIGITS), nibble, dtype=np.int64),
                    np.full(MAX_AUTHORITIES, 4 if flag else 0, dtype=np.int64),
                    np.full(MAX_AUTHORITIES, flag, dtype=np.int64),
                    np.full(MAX_AUTHORITIES, 8 if flag else 1, dtype=np.int64),
                )
            )
    # Also ensure mixed rank/outcome combinations appear
    rows.append(
        (
            encode_word64(1_700_000_000_000_000),
            encode_word64(1_700_000_020_000_000),
            encode_word64(60_000_000),
            encode_word64(50_000_000),
            0,
            np.array([encode_word64(0), encode_word64(50_000_000), encode_word64(10_000_000), encode_word64(0)]),
            np.array([encode_word64(100_000_000), encode_word64(200_000_000), encode_word64(80_000_000), encode_word64(0)]),
            np.array([1, 2, 2, 0], dtype=np.int64),
            np.array([0, 1, 0, 0], dtype=np.int64),
            np.array([1, 5, 3, 0], dtype=np.int64),
        )
    )
    return rows


def reference_checks() -> list[tuple]:
    t0 = 1_755_000_000_000_000
    return [
        # 1. Explicit high authority + 20s -> matched=True
        (
            encode_word64(t0),
            encode_word64(t0 + 20_000_000),
            encode_word64(60_000_000),
            encode_word64(50_000_000),
            0,
            np.array([encode_word64(0), encode_word64(0), encode_word64(0), encode_word64(0)]),
            np.array([encode_word64(1_000_000_000), encode_word64(0), encode_word64(0), encode_word64(0)]),
            np.array([1, 0, 0, 0], dtype=np.int64),
            np.array([1, 0, 0, 0], dtype=np.int64),
            np.array([5, 0, 0, 0], dtype=np.int64),
        ),
        # 2. Boundary 60s exact -> matched=False
        (
            encode_word64(t0),
            encode_word64(t0 + 60_000_000),
            encode_word64(60_000_000),
            encode_word64(50_000_000),
            1,
            np.zeros((MAX_AUTHORITIES, C3_WORD_DIGITS), dtype=np.int64),
            np.zeros((MAX_AUTHORITIES, C3_WORD_DIGITS), dtype=np.int64),
            np.zeros(MAX_AUTHORITIES, dtype=np.int64),
            np.zeros(MAX_AUTHORITIES, dtype=np.int64),
            np.zeros(MAX_AUTHORITIES, dtype=np.int64),
        ),
    ]


def build(output: Path):
    global ARRAY
    from concrete import fhe

    output = Path(output)
    if output.exists():
        raise ValueError('use a new immutable build directory')
    output.mkdir(parents=True)

    started = time.monotonic()
    ARRAY = fhe.array
    fields = [
        'created_us',
        'approved_us',
        'amount',
        'high_threshold',
        'mode_legacy',
        'rule_min',
        'rule_max',
        'rule_rank',
        'rule_is_high',
        'rule_outcome',
    ]
    compiler = fhe.Compiler(c3, {name: 'encrypted' for name in fields})
    circuit = compiler.compile(samples(), global_p_error=1e-9)

    for values in reference_checks():
        ARRAY = np.array
        expected = c3(*values)
        ARRAY = fhe.array
        actual = circuit.simulate(*values)
        if not np.array_equal(actual, expected):
            raise ValueError('compiled C3 circuit differs from reference')

    circuit.server.save(output / 'server.zip')
    specs = circuit.client.specs.serialize()
    (output / 'client.specs.json').write_bytes(specs if isinstance(specs, bytes) else specs.encode('utf-8'))
    manifest = dict(
        version='he4-circuit-build/0.1.0',
        profile='c3',
        concrete_version='2.11.0',
        seconds=time.monotonic() - started,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        files={item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in output.iterdir() if item.is_file()},
        scope=dict(
            word_digits=C3_WORD_DIGITS,
            epoch_precision='microseconds_signed_int64',
            amount_domain='signed_int64',
            max_authorities=MAX_AUTHORITIES,
            fast_seconds_exclusive=60,
        ),
        all_inputs_encrypted=True,
        contains_secret_keys=False,
    )
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output)

