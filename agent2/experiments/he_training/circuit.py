"""One quantized binary logistic SGD update, all arguments encrypted.

Four rows, two fixed-point features, three encrypted parameters. Probability
uses a public sigmoid LUT, not a lookup of labels or fitted weights. The worker
feeds encrypted output weights back into this circuit; no decrypt between steps.
This is a bounded research model, not Concrete ML's SGDClassifier adapter.
"""
import math
import numpy as np

ROWS, COLUMNS = 4, 2
ARRAY = np.array
SIGMOID = lambda z: np.array([round(4 / (1 + math.exp(-int(v) / 2))) for v in z], dtype=np.int64)
ROUND_W = lambda z: np.rint(z / 8).astype(np.int64)
ROUND_B = lambda z: np.rint(z / 8).astype(np.int64)
CLIP_W = lambda z: np.clip(z, -2, 2)
CLIP_B = lambda z: np.clip(z, -4, 4)


def update(x, y, weights):
    z = np.sum(x * weights[:2], axis=1) + weights[2]
    error = SIGMOID(z) - 4 * y
    gradient = ROUND_W(np.sum(error.reshape((ROWS, 1)) * x, axis=0))
    bias_gradient = ROUND_B(np.sum(error))
    return ARRAY([CLIP_W(weights[0] - gradient[0]), CLIP_W(weights[1] - gradient[1]), CLIP_B(weights[2] - bias_gradient)])


def oracle(x, y, weights):
    """Scalar reference equation, independent of the vectorized circuit path."""
    errors = []
    for i in range(ROWS):
        linear = sum(int(x[i][j]) * int(weights[j]) for j in range(COLUMNS)) + int(weights[2])
        probability = int(round(4.0 / (1.0 + math.exp(-linear / 2.0))))
        errors.append(probability - 4 * int(y[i]))
    return [max(-2, min(2, int(weights[j]) - round(sum(errors[i] * int(x[i][j]) for i in range(ROWS)) / 8.0))) for j in range(COLUMNS)] + [max(-4, min(4, int(weights[2]) - round(sum(errors) / 8.0)))]


def configure_fhe():
    from concrete import fhe
    global ARRAY, SIGMOID, ROUND_W, ROUND_B, CLIP_W, CLIP_B
    ARRAY = fhe.array
    sigmoid = fhe.LookupTable([round(4 / (1 + math.exp(-(i - 16) / 2))) for i in range(32)])
    rw = fhe.LookupTable([round((i - 32) / 8) for i in range(64)])
    rb = fhe.LookupTable([round((i - 32) / 8) for i in range(64)])
    cw = fhe.LookupTable([max(-2, min(2, i - 8)) for i in range(16)])
    cb = fhe.LookupTable([max(-4, min(4, i - 8)) for i in range(16)])
    SIGMOID = lambda z: sigmoid[z + 16]
    ROUND_W = lambda z: rw[z + 32]
    ROUND_B = lambda z: rb[z + 32]
    CLIP_W = lambda z: cw[z + 8]
    CLIP_B = lambda z: cb[z + 8]


def samples():
    rng = np.random.default_rng(20261115)
    values = []
    for _ in range(128):
        values.append((rng.integers(-1, 2, (ROWS, COLUMNS)), rng.integers(0, 2, ROWS), np.array([*rng.integers(-2, 3, 2), rng.integers(-4, 5)])))
    for a in (-1, 1):
        for label in (0, 1):
            for w in (-2, 2):
                for b in (-4, 4):
                    values.append((np.full((ROWS, COLUMNS), a), np.full(ROWS, label), np.array([w, w, b])))
    return values
