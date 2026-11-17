"""One measurement in a fresh interpreter, started as `python -I -B child.py ...`.

usage: child.py result <tree> <specs.json> [profile]   outcomes of many instances
       child.py oracle <base-tree> <specs.json>        the independent QR oracle
       child.py probe  <tree> <probe.json>             repeated calls in one process
       child.py timed  <tree> <spec.json> <core>       one timed first call

Prints one JSON line on stdout. The tree is put first on sys.path explicitly; -I
keeps the environment, the user site and the working directory out of it.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import threading
import time
import warnings
from pathlib import Path

HARNESS = Path(__file__).resolve().parent


def _import(tree: str):
    sys.path.insert(0, tree)
    sys.path.insert(1, str(HARNESS))
    import numpy as np  # noqa: F401
    import statsmodels
    from statsmodels.tsa.stattools import _stattools

    if not str(Path(statsmodels.__file__).resolve()).startswith(
        str(Path(tree).resolve())
    ):
        raise SystemExit(
            f"statsmodels imported from {statsmodels.__file__}, expected {tree}"
        )
    return _stattools


def _jsonable(res) -> dict:
    stat, pval, crit, lags, bpidx = res
    return {
        "stat": float(stat),
        "pvalue": float(pval),
        "crit": {str(k): float(v) for k, v in dict(crit).items()},
        "lags": int(lags),
        "bpidx": int(bpidx),
    }


def outcome(fn, x, kwargs) -> dict:
    """Return value, or exception type and message, plus every warning raised."""
    import numpy as np

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            out = {"ok": True, **_jsonable(fn(x, **kwargs))}
        except Exception as exc:  # boundary: the exception is the observed outcome
            out = {"ok": False, "exc_type": type(exc).__name__, "exc_msg": str(exc)}
    out["warnings"] = sorted({(w.category.__name__, str(w.message)) for w in caught})
    if out.get("ok") and not np.isfinite(out["stat"]):
        out["nonfinite_stat"] = True
    return out


def _base_profile(st, x, kwargs) -> dict | None:
    """The base loop's t-statistic of every period, to apply the near-tie rule."""
    import numpy as np

    from statsmodels.regression.linear_model import OLS

    za = st.ZivotAndrewsUnitRoot()
    nobs = x.shape[0]
    reg, trim, maxlag, autolag = (
        kwargs["regression"],
        kwargs["trim"],
        kwargs["maxlag"],
        kwargs["autolag"],
    )
    if autolag:
        lags = st.adfuller(
            x, maxlag=maxlag, regression="ct", autolag=autolag, result_object=False
        )[2]
    elif maxlag:
        lags = maxlag
    else:
        lags = int(12.0 * np.power(nobs / 100.0, 1 / 4.0))
    trimcnt = int(nobs * trim)
    cols = 5 if reg == "ct" else 4
    const = 1 / np.sqrt(nobs)
    trend = np.arange(1.0, nobs + 2) * (np.sqrt(3) / nobs ** (3 / 2))
    endog, exog = za._format_regression_data(x, nobs, const, trend, cols, lags)
    stats = []
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        for bp in range(trimcnt + 1, nobs - trimcnt + 1):
            exog = za._update_regression_exog(
                exog, reg, bp, nobs, const, trend, cols, lags
            )
            if bp == trimcnt + 1:
                stats.append(
                    OLS(endog[lags:], exog, hasconst=1).fit().tvalues[cols - 1]
                )
            else:
                stats.append(za._quick_ols(endog[lags:], exog)[cols - 1])
    s = np.sort(np.asarray(stats))
    if s.size < 2 or not np.all(np.isfinite(s[:2])):
        return None
    order = np.argsort(np.asarray(stats))
    return {
        "gap": float(abs(s[1] - s[0]) / abs(s[0])),
        "second_bpidx": int(order[1] + trimcnt + 1) - 1,
    }


def _ic_gap(st, x, kwargs) -> float | None:
    """Relative gap of the best and second-best information criteria of the lag search."""
    import numpy as np

    autolag = kwargs["autolag"]
    if autolag not in ("AIC", "BIC"):
        return None
    try:
        res = st.adfuller(
            x,
            maxlag=kwargs["maxlag"],
            regression="ct",
            autolag=autolag,
            store=True,
            regresults=True,
            result_object=False,
        )
        store = res[-1]
        values = sorted(
            float(getattr(r, autolag.lower())) for r in store.autolag_results.values()
        )
    except (
        Exception
    ):  # boundary: no tie information when the lag search cannot report it
        return None
    if len(values) < 2 or not np.isfinite(values[0]):
        return None
    return abs(values[1] - values[0]) / max(abs(values[0]), 1e-300)


def run_result(tree: str, specs_path: str, profile: bool) -> dict:
    st = _import(tree)
    import workloads

    out = {}
    for spec in json.loads(Path(specs_path).read_text()):
        x = workloads.make_series(spec)
        kwargs = workloads.za_kwargs(spec)
        res = outcome(st.zivot_andrews, x.copy(), kwargs)
        if profile and res.get("ok"):
            try:
                res["profile"] = _base_profile(st, x.copy(), kwargs)
            except Exception as exc:  # boundary: profile failure leaves no tie rule
                res["profile"] = None
                res["profile_error"] = f"{type(exc).__name__}: {exc}"[:200]
            res["ic_gap"] = _ic_gap(st, x.copy(), kwargs)
        out[spec["id"]] = res
    return {"results": out}


def run_oracle(base_tree: str, specs_path: str) -> dict:
    st = _import(base_tree)
    import numpy as np

    import oracle
    import workloads

    out = {}
    for spec in json.loads(Path(specs_path).read_text()):
        x = workloads.make_series(spec)
        try:
            with warnings.catch_warnings(), np.errstate(all="ignore"):
                warnings.simplefilter("ignore")
                out[spec["id"]] = oracle.oracle(x, base=st, **workloads.za_kwargs(spec))
        except Exception as exc:  # boundary: the oracle records what it cannot compute
            out[spec["id"]] = {
                "computed": False,
                "flags": ["oracle-error"],
                "error": f"{type(exc).__name__}: {exc}"[:300],
            }
    return {"results": out}


def run_probe(tree: str, probe_path: str) -> dict:
    """Calls in one process: A, B, then A's array overwritten in place with A2, then B again."""
    st = _import(tree)
    import workloads

    p = json.loads(Path(probe_path).read_text())
    a = workloads.make_series(p["a"])
    b = workloads.make_series(p["b"])
    a2 = workloads.make_series(p["a2"])
    ka, kb = workloads.za_kwargs(p["a"]), workloads.za_kwargs(p["b"])
    first_a = outcome(st.zivot_andrews, a, ka)
    first_b = outcome(st.zivot_andrews, b, kb)
    a[:] = a2
    second_a = outcome(st.zivot_andrews, a, ka)
    second_b = outcome(st.zivot_andrews, b.copy(), kb)
    return {"a": first_a, "b": first_b, "a2": second_a, "b_again": second_b}


def _task_count() -> int:
    try:
        return len(os.listdir("/proc/self/task"))
    except OSError:
        return -1


def run_timed(tree: str, spec_path: str, core: str) -> dict:
    os.sched_setaffinity(0, {int(core)})
    st = _import(tree)
    import workloads

    timed, warm = json.loads(Path(spec_path).read_text())
    started = {"threads": 0, "forks": 0}
    original_start = threading.Thread.start

    def counting_start(self, *args, **kwargs):
        started["threads"] += 1
        return original_start(self, *args, **kwargs)

    threading.Thread.start = counting_start
    os.register_at_fork(
        before=lambda: started.__setitem__("forks", started["forks"] + 1)
    )
    st.zivot_andrews(workloads.make_series(warm), **workloads.za_kwargs(warm))
    x = workloads.make_series(timed)
    kwargs = workloads.za_kwargs(timed)
    gc.collect()
    before_threads, before_forks, tasks_before = (
        started["threads"],
        started["forks"],
        _task_count(),
    )
    c0 = time.process_time()
    t0 = time.perf_counter()
    res = st.zivot_andrews(x, **kwargs)
    t1 = time.perf_counter()
    c1 = time.process_time()
    return {
        "seconds": t1 - t0,
        "cpu_seconds": c1 - c0,
        "threads_started": started["threads"] - before_threads,
        "forks": started["forks"] - before_forks,
        "tasks_before": tasks_before,
        "tasks_after": _task_count(),
        "affinity": sorted(os.sched_getaffinity(0)),
        "result": _jsonable(res),
    }


def main(argv: list[str]) -> None:
    kind, *rest = argv
    match kind:
        case "result":
            out = run_result(rest[0], rest[1], len(rest) > 2 and rest[2] == "profile")
        case "oracle":
            out = run_oracle(rest[0], rest[1])
        case "probe":
            out = run_probe(rest[0], rest[1])
        case "timed":
            out = run_timed(rest[0], rest[1], rest[2])
        case _:
            raise SystemExit(f"unknown kind {kind}")
    sys.stdout.write("\n" + json.dumps(out) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
