"""Hidden, seed-randomized workload cases of the three timed families.

cases(family, seed, index) -> (kind, fingerprint, call)

`call()` runs one public scikit-learn entry point and returns a dict of plain arrays
and numbers (the fitted path or the fitted estimator's attributes). The fingerprint
is a digest of the generated inputs, so the harness can confirm every tree saw the
same problem. Problems are drawn from numpy's PCG64 generator, which is identical on
every build of the same numpy.

F1  dense solver: enet_path / lasso_path with precompute=False on tall dense X,
    ElasticNetCV / LassoCV with precompute=False on tall dense X.
F2  multi-task solver: MultiTaskElasticNetCV / MultiTaskLassoCV on sparse X, with
    and without an intercept, with and without sample weights.
F3  single-output sparse and Gram solvers: ElasticNetCV / LassoCV on sparse X, with
    and without an intercept, with and without sample weights; enet_path with a
    precomputed Gram matrix on tall dense X.
"""

from __future__ import annotations

import hashlib
import warnings

import numpy as np
from scipy import sparse

KINDS = {
    "F1": (
        "enet_path_dense",
        "enetcv_dense",
        "lasso_path_dense",
        "enetcv_dense",
        "enet_path_dense",
        "lassocv_dense",
        "enetcv_dense",
        "enet_path_dense",
    ),
    "F2": (
        "mtenetcv_sparse",
        "mtlassocv_sparse_noint_sw",
        "mtenetcv_sparse_sw",
        "mtenetcv_sparse_noint",
        "mtlassocv_sparse_sw",
        "mtenetcv_sparse_noint_sw",
        "mtenetcv_sparse",
        "mtlassocv_sparse_noint",
    ),
    "F3": (
        "enetcv_sparse",
        "lassocv_sparse_noint_sw",
        "enet_path_gram",
        "enetcv_sparse_noint",
        "lassocv_sparse_sw",
        "enetcv_sparse_noint_sw",
        "lassocv_sparse",
        "lassocv_sparse_noint",
    ),
}


def _rng(seed: int, family: str, index: int) -> np.random.Generator:
    return np.random.default_rng([seed, ord(family[1]), index])


def _problem(rng, n, p, *, tasks=1, density=None, noise=0.1):
    if density is None:
        X = rng.standard_normal((n, p))
    else:
        nnz_rows = rng.random((n, p)) < density
        rows, cols = np.nonzero(nnz_rows)
        vals = rng.standard_normal(rows.size) + rng.uniform(0.5, 1.5)
        X = sparse.csc_matrix((vals, (rows, cols)), shape=(n, p))
    k = max(2, int(p * rng.uniform(0.04, 0.12)))
    w = np.zeros((p, tasks))
    support = rng.choice(p, size=k, replace=False)
    w[support] = rng.standard_normal((k, tasks)) * rng.uniform(0.5, 3.0)
    y = np.asarray(X @ w) + noise * rng.standard_normal((n, tasks))
    y += rng.uniform(-2.0, 2.0, size=tasks)
    return X, (y[:, 0].copy() if tasks == 1 else y)


def _fingerprint(*arrays) -> str:
    h = hashlib.sha256()
    for a in arrays:
        if sparse.issparse(a):
            a = a.tocsc()
            for part in (a.data, a.indices, a.indptr):
                h.update(np.ascontiguousarray(part).tobytes())
        elif a is not None:
            h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def _path_out(res) -> dict:
    alphas, coefs, gaps, n_iters = res
    return {
        "alphas": np.asarray(alphas),
        "coef": np.asarray(coefs),
        "dual_gap": np.asarray(gaps),
        "n_iter": np.asarray(n_iters),
    }


def _cv_out(est) -> dict:
    return {
        "coef": np.asarray(est.coef_),
        "intercept": np.asarray(est.intercept_),
        "alpha": np.asarray(est.alpha_),
        "l1_ratio": np.asarray(getattr(est, "l1_ratio_", 1.0)),
        "mse_path": np.asarray(est.mse_path_),
        "dual_gap": np.asarray(est.dual_gap_),
        "n_iter": np.asarray(est.n_iter_),
    }


def cases(lm, family: str, seed: int, index: int):
    """lm is the sklearn.linear_model module of the tree under test."""
    rng = _rng(seed, family, index)
    kinds = KINDS[family]
    kind = kinds[index % len(kinds)]
    tol = float(rng.choice([1e-3, 2e-3, 5e-3]))
    n_alphas = int(rng.integers(60, 101))
    sw = None
    fit_intercept = "_noint" not in kind

    if kind in ("enet_path_dense", "lasso_path_dense"):
        X, y = _problem(
            rng, int(rng.integers(14000, 24000)), int(rng.integers(150, 320))
        )
        y = y - y.mean()
        X = np.asfortranarray(X - X.mean(axis=0))
        l1 = float(rng.uniform(0.5, 0.95))

        def call():
            if kind == "lasso_path_dense":
                res = lm.lasso_path(
                    X, y, alphas=n_alphas, tol=tol, precompute=False, return_n_iter=True
                )
            else:
                res = lm.enet_path(
                    X, y, l1_ratio=l1, alphas=n_alphas, tol=tol, precompute=False,
                    return_n_iter=True,
                )
            return _path_out(res)

    elif kind in ("enetcv_dense", "lassocv_dense"):
        X, y = _problem(
            rng, int(rng.integers(9000, 15000)), int(rng.integers(120, 260))
        )

        def call():
            if kind == "lassocv_dense":
                est = lm.LassoCV(alphas=n_alphas, cv=3, tol=tol, precompute=False)
            else:
                est = lm.ElasticNetCV(
                    l1_ratio=[0.5, 0.9],
                    alphas=n_alphas,
                    cv=3,
                    tol=tol,
                    precompute=False,
                )
            return _cv_out(est.fit(X, y))

    elif kind.startswith("mt"):
        n, p = int(rng.integers(2200, 3600)), int(rng.integers(600, 1000))
        X, y = _problem(
            rng,
            n,
            p,
            tasks=int(rng.integers(2, 4)),
            density=float(rng.uniform(0.15, 0.3)),
        )
        if kind.endswith("_sw"):
            sw = rng.uniform(0.3, 3.0, size=n)
        l1 = float(rng.uniform(0.5, 0.95))

        def call():
            if kind.startswith("mtlassocv"):
                est = lm.MultiTaskLassoCV(
                    alphas=n_alphas, cv=3, tol=tol, fit_intercept=fit_intercept
                )
            else:
                est = lm.MultiTaskElasticNetCV(
                    l1_ratio=l1,
                    alphas=n_alphas,
                    cv=3,
                    tol=tol,
                    fit_intercept=fit_intercept,
                )
            return _cv_out(est.fit(X, y, sample_weight=sw))

    elif kind.startswith(("enetcv_sparse", "lassocv_sparse")):
        n, p = int(rng.integers(4000, 8000)), int(rng.integers(1200, 2600))
        X, y = _problem(rng, n, p, density=float(rng.uniform(0.15, 0.3)))
        if kind.endswith("_sw"):
            sw = rng.uniform(0.3, 3.0, size=n)
        l1 = float(rng.uniform(0.5, 0.95))

        def call():
            if kind.startswith("lassocv"):
                est = lm.LassoCV(
                    alphas=n_alphas, cv=3, tol=tol, fit_intercept=fit_intercept
                )
            else:
                est = lm.ElasticNetCV(
                    l1_ratio=l1,
                    alphas=n_alphas,
                    cv=3,
                    tol=tol,
                    fit_intercept=fit_intercept,
                )
            return _cv_out(est.fit(X, y, sample_weight=sw))

    elif kind == "enet_path_gram":
        n, p = int(rng.integers(2500, 4000)), int(rng.integers(600, 1000))
        X, y = _problem(rng, n, p)
        y = y - y.mean()
        X = np.asfortranarray(X - X.mean(axis=0))
        gram = np.dot(X.T, X)
        Xy = np.dot(X.T, y)
        l1 = float(rng.uniform(0.5, 0.95))

        def call():
            res = lm.enet_path(
                X,
                y,
                l1_ratio=l1,
                precompute=gram,
                Xy=Xy,
                alphas=4 * n_alphas,
                tol=tol,
                return_n_iter=True,
            )
            return _path_out(res)

    else:  # pragma: no cover - KINDS is exhaustive
        raise ValueError(kind)

    fp = _fingerprint(X, y, sw) + f":{kind}:{tol}:{n_alphas}:{fit_intercept}"

    def quiet():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return call()

    return kind, fp, quiet
