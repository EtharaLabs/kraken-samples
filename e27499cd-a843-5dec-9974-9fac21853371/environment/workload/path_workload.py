"""Time regularization-path fits of scikit-learn's coordinate descent solvers.

usage: python /app/workload/path_workload.py

Builds a few synthetic problems from one fixed seed, fits a path or a
cross-validated estimator on each, and prints the wall-clock seconds and a short
digest of the fitted coefficients.
"""

import hashlib
import time

import numpy as np

from sklearn.linear_model import LassoCV, MultiTaskElasticNetCV, enet_path

SEED = 20260729


def digest(a):
    return hashlib.sha256(np.round(np.asarray(a), 8).tobytes()).hexdigest()[:12]


def problem(rng, n_samples, n_features, n_tasks=1):
    X = rng.standard_normal((n_samples, n_features))
    w = np.zeros((n_features, n_tasks))
    w[: n_features // 10] = rng.standard_normal((n_features // 10, n_tasks))
    y = X @ w + 0.1 * rng.standard_normal((n_samples, n_tasks))
    return X, (y[:, 0] if n_tasks == 1 else y)


def timed(label, fn):
    t0 = time.perf_counter()
    coef = fn()
    print(f"{label:<44s} {time.perf_counter() - t0:8.3f} s  {digest(coef)}")


def main():
    rng = np.random.default_rng(SEED)
    X, y = problem(rng, 20000, 300)
    X = np.asfortranarray(X - X.mean(axis=0))
    y = y - y.mean()
    timed(
        "enet_path, dense X, precompute=False",
        lambda: enet_path(X, y, l1_ratio=0.8, alphas=100, tol=1e-3, precompute=False)[1],
    )
    Xc, yc = problem(rng, 12000, 200)
    timed(
        "LassoCV, dense X, precompute=False",
        lambda: LassoCV(alphas=100, cv=3, tol=1e-3, precompute=False).fit(Xc, yc).coef_,
    )
    Xg, yg = problem(rng, 1500, 2500)
    Xg = np.asfortranarray(Xg - Xg.mean(axis=0))
    yg = yg - yg.mean()
    gram, Xy = Xg.T @ Xg, Xg.T @ yg
    timed(
        "enet_path, precomputed Gram",
        lambda: enet_path(Xg, yg, precompute=gram, Xy=Xy, alphas=300, tol=1e-3)[1],
    )
    Xm, Ym = problem(rng, 4000, 300, n_tasks=3)
    timed(
        "MultiTaskElasticNetCV, dense X",
        lambda: MultiTaskElasticNetCV(alphas=100, cv=3, tol=1e-3).fit(Xm, Ym).coef_,
    )


if __name__ == "__main__":
    main()
