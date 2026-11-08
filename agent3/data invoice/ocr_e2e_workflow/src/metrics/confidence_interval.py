from __future__ import annotations

import random
from typing import Iterable


def bootstrap_mean_ci(
    values: Iterable[float], samples: int = 1000, confidence: float = 0.95, seed: int = 20260922
) -> dict[str, float | None]:
    data = list(values)
    if not data:
        return {"mean": None, "lower": None, "upper": None}
    generator = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = [data[generator.randrange(len(data))] for _ in data]
        means.append(sum(draw) / len(draw))
    means.sort()
    alpha = (1 - confidence) / 2
    lower = means[int(alpha * (len(means) - 1))]
    upper = means[int((1 - alpha) * (len(means) - 1))]
    return {"mean": sum(data) / len(data), "lower": lower, "upper": upper}

