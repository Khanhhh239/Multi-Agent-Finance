"""One quantized binary logistic SGD update, all arguments encrypted (`S=16, P=16`).

Four rows (`B=4`), two binary indicator features (`X in {0, 1}`), binary labels
(`y in {0, 1}`), and three encrypted integer parameters (`W in [-16, 16]^2`,
`B in [-32, 32]`).

Exact fixed-point circuit equations (`profile_version = "fhe_sgd_s16_v2"`):
  - Linear score: `z_i = w0 * x_{i,0} + w1 * x_{i,1} + b` in `[-64, 64]`
  - Public quantized sigmoid LUT (`129` entries, 7-bit TFHE PBS compatible):
    `p_hat(z) = clip(round_half_away(16 / (1 + exp(-z / 16))), 0, 16)`
    with `p_hat(0) = 8`
  - Per-sample prediction residual: `e_i = p_hat(z_i) - 16 * y_i` in `[-16, 16]`
  - Mini-batch gradient accumulators:
    `G_w[j] = sum_{i=0..3} e_i * x_{i,j}` in `[-64, 64]`
    `G_b    = sum_{i=0..3} e_i`           in `[-64, 64]`
  - Exact integer division-by-4 LUT (`129` entries, half-away-from-zero):
    `delta_W[j] = round_div4(G_w[j])`, `delta_B = round_div4(G_b)` in `[-16, 16]`
    (since `S * lr / (B_batch * P) = 16 * 1 / (4 * 16) = 1 / 4`)
  - Bounded state update (`65` and `97` entry clip LUTs):
    `W_new[j] = clip(W[j] - delta_W[j], -16, 16)` (`W_pre in [-32, 32]`)
    `B_new    = clip(B    - delta_B,    -32, 32)` (`B_pre in [-48, 48]`)

Legacy `scale=2` (`profile_version = "legacy_s2_v1"`) is preserved explicitly in
`oracle(..., profile_version="legacy_s2_v1")` for backward-compatibility checks
and regression proofs without ever mixing scales silently.
"""
import math
import numpy as np

from . import LEGACY_PROFILE_VERSION, PROFILE_VERSION, resolve_quantization_profile

ROWS, COLUMNS = 4, 2
S_WEIGHT = 16
S_BIAS = 16
P_PROBABILITY = 16
LEARNING_RATE = 1
BATCH_SIZE = 4

W_MIN, W_MAX = -16, 16
B_MIN, B_MAX = -32, 32
Z_MIN, Z_MAX = -64, 64
G_MIN, G_MAX = -64, 64
W_PRE_MIN, W_PRE_MAX = -32, 32
B_PRE_MIN, B_PRE_MAX = -48, 48


def round_half_away_from_zero(value: float) -> int:
    """Deterministic half-away-from-zero rounding (avoids banker's round-to-even dead zone at +-0.5)."""
    v = float(value)
    if v >= 0.0:
        return int(math.floor(v + 0.5))
    return -int(math.floor(-v + 0.5))


def round_div4(numerator: int) -> int:
    """Exact integer `round_half_away_from_zero(numerator / 4)` without float drift."""
    v = int(numerator)
    return (v + 2) // 4 if v >= 0 else -((-v + 2) // 4)


def quantized_sigmoid_s16(z: int) -> int:
    """Quantized sigmoid `clip(round_half_away(16 / (1 + exp(-z / 16))), 0, 16)`."""
    prob = float(P_PROBABILITY) / (1.0 + math.exp(-int(z) / float(S_WEIGHT)))
    return max(0, min(P_PROBABILITY, round_half_away_from_zero(prob)))


SIGMOID_TABLE = [quantized_sigmoid_s16(i - 64) for i in range(129)]
ROUND4_TABLE = [round_div4(i - 64) for i in range(129)]
CLIP_W_TABLE = [max(W_MIN, min(W_MAX, i - 32)) for i in range(65)]
CLIP_B_TABLE = [max(B_MIN, min(B_MAX, i - 48)) for i in range(97)]

_SIGMOID_NP = np.asarray(SIGMOID_TABLE, dtype=np.int64)
_ROUND4_NP = np.asarray(ROUND4_TABLE, dtype=np.int64)
_CLIP_W_NP = np.asarray(CLIP_W_TABLE, dtype=np.int64)
_CLIP_B_NP = np.asarray(CLIP_B_TABLE, dtype=np.int64)

ARRAY = None
SIGMOID = None
ROUND_W = None
ROUND_B = None
CLIP_W = None
CLIP_B = None


def reset_clear_mode():
    """Bind circuit primitives to exact integer LUT tables in clear NumPy mode."""
    global ARRAY, SIGMOID, ROUND_W, ROUND_B, CLIP_W, CLIP_B
    ARRAY = lambda vals: np.asarray(vals, dtype=np.int64)
    SIGMOID = lambda z: _SIGMOID_NP[np.asarray(z, dtype=np.int64) + 64]
    ROUND_W = lambda g: _ROUND4_NP[np.asarray(g, dtype=np.int64) + 64]
    ROUND_B = lambda g: _ROUND4_NP[np.asarray(g, dtype=np.int64) + 64]
    CLIP_W = lambda w: _CLIP_W_NP[np.asarray(w, dtype=np.int64) + 32]
    CLIP_B = lambda b: _CLIP_B_NP[np.asarray(b, dtype=np.int64) + 48]


reset_clear_mode()


def update(x, y, weights):
    """Execute one quantized FHE-compatible mini-batch SGD step (`S=16, P=16`)."""
    x_arr = np.asarray(x) if ARRAY is not None and not hasattr(weights, 'tracing') else x
    z = np.sum(x * weights[:2], axis=1) + weights[2]
    error = SIGMOID(z) - P_PROBABILITY * y
    gradient = ROUND_W(np.sum(error.reshape((ROWS, 1)) * x, axis=0))
    bias_gradient = ROUND_B(np.sum(error))
    return ARRAY([
        CLIP_W(weights[0] - gradient[0]),
        CLIP_W(weights[1] - gradient[1]),
        CLIP_B(weights[2] - bias_gradient),
    ])


def _legacy_s2_oracle(x, y, weights) -> list[int]:
    """Legacy `S=2, P=4` round-to-even scalar equation preserved strictly for v1 comparison/compat."""
    errors = []
    for i in range(ROWS):
        linear = sum(int(x[i][j]) * int(weights[j]) for j in range(COLUMNS)) + int(weights[2])
        probability = int(round(4.0 / (1.0 + math.exp(-linear / 2.0))))
        errors.append(probability - 4 * int(y[i]))
    next_w = [
        max(-2, min(2, int(weights[j]) - round(sum(errors[i] * int(x[i][j]) for i in range(ROWS)) / 8.0)))
        for j in range(COLUMNS)
    ]
    next_b = max(-4, min(4, int(weights[2]) - round(sum(errors) / 8.0)))
    return next_w + [next_b]


def oracle(x, y, weights, *, profile_version: str = PROFILE_VERSION) -> list[int]:
    """Independent scalar integer specification for `fhe_sgd_s16_v2` (and `legacy_s2_v1`)."""
    prof = resolve_quantization_profile(profile_version)
    if prof['profile_version'] == LEGACY_PROFILE_VERSION:
        return _legacy_s2_oracle(x, y, weights)

    w0, w1, b = int(weights[0]), int(weights[1]), int(weights[2])
    if not (W_MIN <= w0 <= W_MAX and W_MIN <= w1 <= W_MAX and B_MIN <= b <= B_MAX):
        raise ValueError(f'WEIGHT_STATE_OUT_OF_DOMAIN:{[w0, w1, b]}')
    errors = []
    for i in range(ROWS):
        xi0, xi1 = int(x[i][0]), int(x[i][1])
        yi = int(y[i])
        if xi0 not in (-1, 0, 1) or xi1 not in (-1, 0, 1):
            raise ValueError(f'FEATURE_OUT_OF_DOMAIN:{[xi0, xi1]}')
        if yi not in (0, 1):
            raise ValueError(f'LABEL_OUT_OF_DOMAIN:{yi}')
        linear = w0 * xi0 + w1 * xi1 + b
        p_code = quantized_sigmoid_s16(linear)
        errors.append(p_code - P_PROBABILITY * yi)

    gw0 = sum(errors[i] * int(x[i][0]) for i in range(ROWS))
    gw1 = sum(errors[i] * int(x[i][1]) for i in range(ROWS))
    gb = sum(errors)

    dw0 = round_div4(gw0)
    dw1 = round_div4(gw1)
    db = round_div4(gb)

    return [
        max(W_MIN, min(W_MAX, w0 - dw0)),
        max(W_MIN, min(W_MAX, w1 - dw1)),
        max(B_MIN, min(B_MAX, b - db)),
    ]


def inspect_intermediate_bounds(x, y, weights) -> dict:
    """Return exact intermediate values before LUTs/clipping to verify zero silent overflow."""
    w0, w1, b = int(weights[0]), int(weights[1]), int(weights[2])
    z_vals = [w0 * int(x[i][0]) + w1 * int(x[i][1]) + b for i in range(ROWS)]
    p_vals = [quantized_sigmoid_s16(z) for z in z_vals]
    e_vals = [p_vals[i] - P_PROBABILITY * int(y[i]) for i in range(ROWS)]
    gw = [sum(e_vals[i] * int(x[i][j]) for i in range(ROWS)) for j in range(COLUMNS)]
    gb = sum(e_vals)
    dw = [round_div4(g) for g in gw]
    db = round_div4(gb)
    w_pre = [w0 - dw[0], w1 - dw[1]]
    b_pre = b - db
    w_out = [max(W_MIN, min(W_MAX, v)) for v in w_pre]
    b_out = max(B_MIN, min(B_MAX, b_pre))
    in_bounds = (
        all(Z_MIN <= z <= Z_MAX for z in z_vals)
        and all(0 <= z + 64 < len(SIGMOID_TABLE) for z in z_vals)
        and all(G_MIN <= g <= G_MAX for g in (*gw, gb))
        and all(0 <= g + 64 < len(ROUND4_TABLE) for g in (*gw, gb))
        and all(W_PRE_MIN <= v <= W_PRE_MAX for v in w_pre)
        and all(0 <= v + 32 < len(CLIP_W_TABLE) for v in w_pre)
        and (B_PRE_MIN <= b_pre <= B_PRE_MAX)
        and (0 <= b_pre + 48 < len(CLIP_B_TABLE))
    )
    return dict(
        z=z_vals,
        p_code=p_vals,
        e_code=e_vals,
        g_w=gw,
        g_b=gb,
        delta_w=dw,
        delta_b=db,
        w_pre_clip=w_pre,
        b_pre_clip=b_pre,
        weights_out=[w_out[0], w_out[1], b_out],
        lut_indices_valid=in_bounds,
    )


def float_logistic_sgd_step(x, y, weights_float, *, learning_rate: float = 1.0, clip: bool = True) -> list[float]:
    """Floating-point logistic SGD reference with matching initialization, LR, and domain bounds."""
    w0, w1, b = float(weights_float[0]), float(weights_float[1]), float(weights_float[2])
    errs = []
    for i in range(ROWS):
        z = w0 * float(x[i][0]) + w1 * float(x[i][1]) + b
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        errs.append(p - float(y[i]))
    gw0 = sum(errs[i] * float(x[i][0]) for i in range(ROWS)) / float(ROWS)
    gw1 = sum(errs[i] * float(x[i][1]) for i in range(ROWS)) / float(ROWS)
    gb = sum(errs) / float(ROWS)
    nw0 = w0 - learning_rate * gw0
    nw1 = w1 - learning_rate * gw1
    nb = b - learning_rate * gb
    if clip:
        nw0 = max(-1.0, min(1.0, nw0))
        nw1 = max(-1.0, min(1.0, nw1))
        nb = max(-2.0, min(2.0, nb))
    return [nw0, nw1, nb]


def configure_fhe():
    """Bind 7-bit TFHE LookupTables (`<= 129` entries each) for Concrete-Python compilation."""
    from concrete import fhe
    global ARRAY, SIGMOID, ROUND_W, ROUND_B, CLIP_W, CLIP_B
    ARRAY = fhe.array
    sigmoid = fhe.LookupTable(SIGMOID_TABLE)
    rw = fhe.LookupTable(ROUND4_TABLE)
    rb = fhe.LookupTable(ROUND4_TABLE)
    cw = fhe.LookupTable(CLIP_W_TABLE)
    cb = fhe.LookupTable(CLIP_B_TABLE)
    SIGMOID = lambda z: sigmoid[z + 64]
    ROUND_W = lambda z: rw[z + 64]
    ROUND_B = lambda z: rb[z + 64]
    CLIP_W = lambda z: cw[z + 32]
    CLIP_B = lambda z: cb[z + 48]


def samples(profile_version: str = PROFILE_VERSION):
    """Representative calibration inputset spanning binary `{0, 1}` features and state extrema."""
    prof = resolve_quantization_profile(profile_version)
    rng = np.random.default_rng(20261115)
    values = []
    if prof['profile_version'] == LEGACY_PROFILE_VERSION:
        for _ in range(128):
            values.append((
                rng.integers(-1, 2, (ROWS, COLUMNS)),
                rng.integers(0, 2, ROWS),
                np.array([*rng.integers(-2, 3, 2), rng.integers(-4, 5)], dtype=np.int64),
            ))
        for a in (-1, 1):
            for label in (0, 1):
                for w in (-2, 2):
                    for b in (-4, 4):
                        values.append((np.full((ROWS, COLUMNS), a, dtype=np.int64), np.full(ROWS, label, dtype=np.int64), np.array([w, w, b], dtype=np.int64)))
        return values

    for _ in range(192):
        values.append((
            rng.integers(0, 2, (ROWS, COLUMNS), dtype=np.int64),
            rng.integers(0, 2, ROWS, dtype=np.int64),
            np.array([*rng.integers(W_MIN, W_MAX + 1, 2), rng.integers(B_MIN, B_MAX + 1)], dtype=np.int64),
        ))
    # Explicit binary boundary corners to guarantee full bit-width allocation in Concrete-Python
    for x0 in (0, 1):
        for x1 in (0, 1):
            x_mat = np.tile(np.array([[x0, x1]], dtype=np.int64), (ROWS, 1))
            for label in (0, 1):
                y_vec = np.full(ROWS, label, dtype=np.int64)
                for w0 in (W_MIN, 0, W_MAX):
                    for w1 in (W_MIN, 0, W_MAX):
                        for b in (B_MIN, 0, B_MAX):
                            values.append((x_mat.copy(), y_vec.copy(), np.array([w0, w1, b], dtype=np.int64)))
    return values
