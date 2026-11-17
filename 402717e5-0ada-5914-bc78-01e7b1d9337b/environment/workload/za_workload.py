"""Visible workload: one Zivot-Andrews test on a long series with a level break.

Run it with:  python /app/workload/za_workload.py

It builds a seeded random walk with drift and one level shift, calls
statsmodels.tsa.stattools.zivot_andrews once in this fresh interpreter, and
reports how long the call took together with everything the call returned.
The returned values must not change when the library gets faster.
"""

import time

import numpy as np

from statsmodels.tsa.stattools import zivot_andrews

NOBS = 3000
SEED = 20261103


def series():
    rng = np.random.default_rng(SEED)
    t = np.arange(NOBS)
    return np.cumsum(rng.standard_normal(NOBS)) + 0.05 * t + 12.0 * (t >= 1900)


def main():
    x = series()
    start = time.perf_counter()
    stat, pvalue, crit, lags, bpidx = zivot_andrews(x, regression="c", autolag=None)
    elapsed = time.perf_counter() - start
    print(f"nobs={NOBS} lags={lags} break_index={bpidx} seconds={elapsed:.3f}")
    print(f"statistic={stat!r} pvalue={pvalue!r}")
    print(f"critical_values={crit}")


if __name__ == "__main__":
    main()
