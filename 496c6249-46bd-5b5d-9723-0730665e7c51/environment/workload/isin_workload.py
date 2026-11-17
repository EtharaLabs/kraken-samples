"""Visible workload: membership tests on variable-width string arrays.

Run it from outside the source checkout, for example:

    cd /app && python /app/workload/isin_workload.py

For each missing-value setting it builds two fixed, seeded arrays of
variable-width strings (some of them missing), times one call of np.isin in
this process, and prints a digest of the boolean result. The digest must not
change when the library gets faster.
"""

import hashlib
import random
import time

import numpy as np
from numpy.dtypes import StringDType

SEED = 20260731
N_LEFT = 13579
N_RIGHT = 2468
SETTINGS = (
    ("no missing value", {}),
    ("na_object=None", {"na_object": None}),
    ("na_object=nan", {"na_object": float("nan")}),
)


def words(rng, count):
    letters = "abcdefghijklmnopqrstuvwxyz"
    pool = [
        "".join(rng.choice(letters) for _ in range(rng.randint(1, 24)))
        for _ in range(count // 2)
    ]
    return [rng.choice(pool) for _ in range(count)]


def build(rng, count, kwargs):
    values = words(rng, count)
    if kwargs:
        values = [kwargs["na_object"] if rng.random() < 0.1 else v for v in values]
    return np.array(values, dtype=StringDType(**kwargs))


def main():
    for label, kwargs in SETTINGS:
        rng = random.Random(SEED)
        left = build(rng, N_LEFT, kwargs)
        right = build(rng, N_RIGHT, kwargs)
        start = time.perf_counter()
        mask = np.isin(left, right)
        elapsed = time.perf_counter() - start
        digest = hashlib.sha256(mask.tobytes()).hexdigest()[:16]
        print(
            f"{label:18s} isin_seconds={elapsed:.3f} matches={int(mask.sum())} digest={digest}"
        )


if __name__ == "__main__":
    main()
