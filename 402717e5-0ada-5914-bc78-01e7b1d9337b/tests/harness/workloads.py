"""Seeded series and instance plans for the hidden Zivot-Andrews workloads.

Every series comes from numpy.random.Generator(PCG64(seed)). The verifier draws
the master seed and every instance seed at verify time from the operating
system's random source and logs them, so no hidden input exists before a run.
"""

from __future__ import annotations

import math

import numpy as np

AUTOLAGS = (None, "AIC", "BIC", "t-stat")
REGRESSIONS = ("c", "t", "ct")
TRIMS = (0.05, 0.15, 1 / 3)
WELL_KINDS = (
    "random_walk",
    "ar",
    "trend_break",
    "white_noise",
    "level_break",
    "narrow_break",
)


def _rng(seed: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def make_series(spec: dict) -> np.ndarray:
    """The series of one instance, a pure function of the spec."""
    kind, n = spec["kind"], int(spec["nobs"])
    p = spec.get("params", {})
    rng = _rng(int(spec["seed"]))
    t = np.arange(n, dtype=float)
    e = rng.standard_normal(n)
    match kind:
        case "random_walk":
            return np.cumsum(e)
        case "white_noise":
            return e
        case "ar":
            x = np.zeros(n)
            for i in range(1, n):
                x[i] = 0.8 * x[i - 1] + e[i]
            return 50.0 + x
        case "trend_break":
            return 0.1 * t + 0.4 * np.maximum(t - p["b"], 0) + np.cumsum(e)
        case "level_break":
            return np.cumsum(e) + 0.3 * t + p["a"] * (t >= p["b"])
        case "narrow_break":
            # a stationary series with one large level shift: the t-statistic of the
            # lagged level is sharply lower at the true break than one period away
            x = np.zeros(n)
            for i in range(1, n):
                x[i] = p["phi"] * x[i - 1] + e[i]
            return x + p["a"] * (t >= p["b"])
        case "near_trend":
            return 1.0 + 0.5 * t + p["delta"] * e
        case "nonfinite":
            x = np.cumsum(e)
            x[p["at"]] = np.nan if p["value"] == "nan" else np.inf
            return x
        case "linear":
            return np.arange(float(n))
        case "periodic":
            return np.cumsum(np.tile([1.0, -1.0, 2.0], math.ceil(n / 3))[:n])
        case "geometric":
            return 0.5 ** (np.arange(float(n)) / 10)
        case "level_collinear":
            return t + 5.0 * (t >= p["b"])
        case _:
            raise ValueError(f"unknown series kind {kind}")

def _near_trend_cond(nobs: int, seed: int, delta: float, regression: str, lags: int, trim: float) -> float:
    """Largest condition number of the break-period designs at three periods."""
    import oracle

    x = make_series({"kind": "near_trend", "nobs": nobs, "seed": seed, "params": {"delta": delta}})
    cols = 5 if regression == "ct" else 4
    const = 1 / np.sqrt(nobs)
    trend = np.arange(1.0, nobs + 2) * (np.sqrt(3) / nobs ** (3 / 2))
    y, exog = oracle._base_design(x, nobs, lags, cols)
    lo, hi = int(nobs * trim) + 1, nobs - int(nobs * trim)
    worst = 0.0
    for period in (lo, (lo + hi) // 2, hi):
        oracle._set_dummies(exog, regression, period, nobs, const, trend, lags)
        worst = max(worst, oracle._qr_tvalue(y, exog, cols - 1)[1])
    return worst


def tune_delta(nobs: int, seed: int, regression: str, lags: int, trim: float, target: float) -> float:
    """The noise scale that puts a near-trend design at the target condition number."""
    delta = 1.8 * nobs / target  # the condition number is about 1.8 * nobs / delta
    for _ in range(3):
        delta *= _near_trend_cond(nobs, seed, delta, regression, lags, trim) / target
    return float(delta)


def za_kwargs(spec: dict) -> dict:
    return {
        "trim": spec["trim"],
        "maxlag": spec["maxlag"],
        "regression": spec["regression"],
        "autolag": spec["autolag"],
    }


def _draw_nobs(rng: np.random.Generator, lo: int, hi: int, avoid: int) -> int:
    while True:
        n = int(round(math.exp(rng.uniform(math.log(lo), math.log(hi)))))
        if n != avoid:
            return n


def _seed(rng: np.random.Generator, avoid: int) -> int:
    while True:
        s = int(rng.integers(1, 2**31 - 1))
        if s != avoid:
            return s


def correctness_plan(master_seed: int, visible: dict, plan: dict) -> list[dict]:
    """The hidden correctness instances, one dict per instance."""
    rng = _rng(master_seed)
    vn, vs = int(visible["nobs"]), int(visible["seed"])
    specs: list[dict] = []

    def add(
        kind, nobs, regression, autolag, trim, maxlag, params=None, intended="well"
    ):
        seed = _seed(rng, vs)
        params = dict(params or {})
        if "cond_target" in params:
            params["delta"] = tune_delta(int(nobs), seed, regression, maxlag, trim, params["cond_target"])
        specs.append(
            {
                "id": f"{intended[:2]}{len(specs):02d}",
                "intended": intended,
                "kind": kind,
                "nobs": int(nobs),
                "seed": seed,
                "regression": regression,
                "autolag": autolag,
                "trim": trim,
                "maxlag": maxlag,
                "params": params,
            }
        )

    # well-conditioned: every regression x autolag pair, twice, across kinds and trims
    combos = [(r, a) for r in REGRESSIONS for a in AUTOLAGS] * plan["well_repeats"]
    for i, (reg, al) in enumerate(combos):
        kind = WELL_KINDS[i % len(WELL_KINDS)]
        trim = TRIMS[i % len(TRIMS)]
        n = _draw_nobs(rng, plan["nobs_min"], plan["nobs_max"], vn)
        maxlag = None if i % 4 else int(rng.integers(1, 9))
        params = {}
        if kind in ("trend_break", "level_break", "narrow_break"):
            lo, hi = int(n * max(trim, 0.15)) + 2, int(n * (1 - max(trim, 0.15))) - 2
            params["b"] = int(rng.integers(lo, hi))
            params["a"] = float(rng.uniform(6.0, 12.0))
            params["phi"] = float(rng.uniform(0.0, 0.5))
        add(kind, n, reg, al, trim, maxlag, params)
    # planted narrow minimum breaks, the argmin must be exact
    for i in range(plan["narrow"]):
        reg = ("c", "ct")[i % 2]
        n = _draw_nobs(rng, 400, plan["nobs_max"], vn)
        b = int(rng.integers(int(n * 0.2), int(n * 0.8)))
        params = {
            "b": b,
            "a": float(rng.uniform(8.0, 14.0)),
            "phi": float(rng.uniform(0.0, 0.4)),
        }
        add("narrow_break", n, reg, (None, "AIC", "BIC")[i % 3], 0.15, None, params, "narrow")
    # near-collinear: the lagged level is almost a linear trend; one target condition
    # number per equal-width stratum of log10 cond, so the instances span the whole band
    lo_c, hi_c = plan["near_log10_cond"]
    width = (hi_c - lo_c) / plan["near_collinear"]
    for i in range(plan["near_collinear"]):
        reg = REGRESSIONS[i % 3]
        n = _draw_nobs(rng, 150, 1200, vn)
        target = 10 ** (lo_c + width * (i + float(rng.uniform())))
        add("near_trend", n, reg, None, 0.15, int(rng.integers(1, 4)), {"cond_target": target}, "near")
    # fallback: non-finite data, singular or near-span designs, zero or wrapping dummies
    fb = [
        ("nonfinite", 100, "c", None, 0.15, 2, {"at": 50, "value": "nan"}),
        ("nonfinite", 120, "ct", None, 0.15, 3, {"at": 70, "value": "inf"}),
        ("linear", 100, "c", None, 0.15, 3, {}),
        ("periodic", 120, "t", None, 0.15, 3, {}),
        ("geometric", 120, "ct", None, 0.15, 3, {}),
        ("level_collinear", 100, "c", None, 0.15, 1, {"b": 50}),
        ("level_collinear", 100, "ct", None, 0.15, 1, {"b": 50}),
        ("random_walk", 100, "c", None, 0.05, 5, {}),
        ("random_walk", 100, "t", None, 0.05, 4, {}),
        ("random_walk", 100, "ct", None, 0.0, 0, {}),
        ("random_walk", 100, "c", None, 0.05, 8, {}),
        ("random_walk", 100, "t", None, 0.0, 2, {}),
        # condition number above 1e8 but below 1e9, far past the 5e6 fallback bound, where
        # every backward-stable fit still agrees with the oracle to about 1e-7 while the
        # X'X inverse has lost every digit
        ("near_trend", 300, "ct", None, 0.15, 2, {"cond_target": 3e8}),
        ("near_trend", 400, "c", None, 0.15, 2, {"cond_target": 6e8}),
        ("random_walk", 200, "c", "AIC", 0.34, None, {}),
    ]
    for kind, n, reg, al, trim, maxlag, params in fb:
        add(kind, n, reg, al, trim, maxlag, params, "fallback")
    return specs


def timed_specs(
    master_seed: int, rep: int, workloads: list[dict], visible: dict
) -> list[tuple[dict, dict]]:
    """(timed spec, warm-up spec) per timed workload for one repetition.

    Each repetition draws fresh series; the warm-up series is a different, shorter
    series with the same options, so the timed call is the first on its data.
    """
    rng = _rng(master_seed + 7919 * (rep + 1))
    vs = int(visible["seed"])
    out = []
    for w in workloads:
        n = int(w["nobs"])
        b = int(rng.integers(int(n * 0.3), int(n * 0.7)))
        timed = {
            "id": w["id"],
            "kind": "level_break",
            "nobs": n,
            "seed": _seed(rng, vs),
            "regression": w["regression"],
            "autolag": w["autolag"],
            "trim": float(w.get("trim", 0.15)),
            "maxlag": None,
            "params": {"a": float(rng.uniform(8.0, 12.0)), "b": b},
        }
        wn = int(rng.integers(300, 600))
        warm = dict(
            timed,
            id=w["id"] + "-warm",
            nobs=wn,
            seed=_seed(rng, vs),
            params={"a": 10.0, "b": wn // 2},
            # A short warm-up at a small trim makes the earliest break dummy span every
            # lag-trimmed row, so base and reference raise their rank error; the warm-up
            # only exercises the code path, so it keeps the default trim.
            trim=0.15,
        )
        out.append((timed, warm))
    return out
