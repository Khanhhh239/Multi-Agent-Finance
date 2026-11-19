"""Named streams; shape changes in one component cannot consume another's RNG."""
from __future__ import annotations

import hashlib
import numpy as np


def seed_for(seed, case, stream):
    digest = hashlib.sha256(f"{case}:{stream}".encode()).digest()
    words = np.frombuffer(digest, dtype="<u4").tolist()
    return int(np.random.SeedSequence([int(seed), *words]).generate_state(1, dtype=np.uint64)[0])


def generator(seed, case, stream):
    return np.random.default_rng(seed_for(seed, case, stream))
