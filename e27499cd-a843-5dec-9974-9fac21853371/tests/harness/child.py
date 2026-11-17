"""One family run in a fresh interpreter, against one scikit-learn build.

usage: child.py <site> <family> <seed> <count>
       child.py <site> api

Imports scikit-learn from <site>, warms every entry point of the timed families once
on a tiny problem, then builds `count` hidden cases of the family from the seed,
times each entry-point call once, and prints one JSON line with the timings, a digest
of each input and a plain-data dump of each output. The `api` form prints the call
signatures of sklearn.linear_model's public functions and estimator methods instead.
"""

from __future__ import annotations

import inspect
import json
import sys
import time


def _plain(value):
    import numpy as np

    a = np.asarray(value)
    if a.dtype.kind in "iub":
        return {"dtype": "int", "shape": list(a.shape), "v": a.ravel().tolist()}
    return {
        "dtype": "float",
        "shape": list(a.shape),
        "v": a.astype(float).ravel().tolist(),
    }


def _warm(lm) -> None:
    import warnings

    import numpy as np
    from scipy import sparse

    rng = np.random.default_rng(0)
    X = rng.standard_normal((60, 8))
    y = X[:, 0] + 0.1 * rng.standard_normal(60)
    Y = np.c_[y, X[:, 1]]
    Xs = sparse.csc_matrix(np.where(rng.random((60, 8)) < 0.3, X, 0.0))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lm.enet_path(np.asfortranarray(X), y, alphas=3, precompute=False)
        lm.lasso_path(np.asfortranarray(X), y, alphas=3, precompute=False)
        lm.enet_path(X, y, precompute=X.T @ X, Xy=X.T @ y, alphas=3)
        lm.ElasticNetCV(alphas=3, cv=2, precompute=False).fit(X, y)
        lm.LassoCV(alphas=3, cv=2, precompute=False).fit(X, y)
        lm.ElasticNetCV(alphas=3, cv=2).fit(Xs, y, sample_weight=np.ones(60))
        lm.LassoCV(alphas=3, cv=2).fit(Xs, y)
        lm.MultiTaskElasticNetCV(alphas=3, cv=2).fit(Xs, Y)
        lm.MultiTaskLassoCV(alphas=3, cv=2).fit(Xs, Y, sample_weight=np.ones(60))


def _api(lm) -> dict:
    out = {}
    for name in sorted(getattr(lm, "__all__", dir(lm))):
        obj = getattr(lm, name, None)
        if inspect.isclass(obj):
            for meth in ("__init__", "fit", "path", "predict", "score"):
                fn = obj.__dict__.get(meth) or getattr(obj, meth, None)
                if callable(fn):
                    try:
                        out[f"{name}.{meth}"] = str(inspect.signature(fn))
                    except (TypeError, ValueError):
                        out[f"{name}.{meth}"] = "?"
        elif callable(obj):
            try:
                out[name] = str(inspect.signature(obj))
            except (TypeError, ValueError):
                out[name] = "?"
    return out


def main(argv: list[str]) -> None:
    site = argv[0]
    sys.path.insert(0, site)
    import sklearn
    import sklearn.linear_model as lm

    if not sklearn.__file__.startswith(site):
        raise SystemExit(f"sklearn imported from {sklearn.__file__}, expected {site}")
    if argv[1:] == ["api"]:
        print(json.dumps({"api": _api(lm)}, sort_keys=True))
        return

    import workloads

    family, seed, count = argv[1], int(argv[2]), int(argv[3])
    _warm(lm)
    records = []
    for index in range(count):
        kind, fingerprint, call = workloads.cases(lm, family, seed, index)
        t0 = time.perf_counter()
        out = call()
        dt = time.perf_counter() - t0
        records.append(
            {
                "kind": kind,
                "seconds": dt,
                "input": fingerprint,
                "output": {k: _plain(v) for k, v in out.items()},
            }
        )
    print(json.dumps({"family": family, "seed": seed, "records": records}))


if __name__ == "__main__":
    main(sys.argv[1:])
