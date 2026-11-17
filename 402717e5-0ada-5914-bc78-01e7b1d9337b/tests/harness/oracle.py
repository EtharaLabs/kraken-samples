"""Independent per-period oracle for the Zivot-Andrews break regressions.

Every candidate break period gets its own design matrix, built from the model
definition, and its own column-pivoted QR decomposition (scipy.linalg.qr with
pivoting). The t-statistic of the lagged level comes from the triangular factor,
never from a cross-product inverse, so the oracle keeps its digits on
near-collinear designs where an X'X inverse loses about cond**2 * eps.

The oracle shares no solver code with any statsmodels tree. It uses the base
tree only for what the patch may not change and the oracle does not grade: the
argument validation, the adfuller lag selection and the critical value table.
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import qr, solve_triangular, svdvals

EPS = np.finfo(float).eps


def _lags_of(x, nobs, maxlag, autolag, adfuller):
    if autolag:
        return adfuller(
            x, maxlag=maxlag, regression="ct", autolag=autolag, result_object=False
        )[2]
    if maxlag:
        return maxlag
    return int(12.0 * np.power(nobs / 100.0, 1 / 4.0))


def _base_design(x, nobs, lags, cols):
    """endog and the period-independent columns, from the model definition."""
    dy = np.diff(x)
    dy = dy / np.sqrt(dy @ dy)
    level = x / np.sqrt(x @ x)
    nreg = nobs - 1 - lags
    exog = np.zeros((nreg, cols + lags))
    exog[:, 0] = 1 / np.sqrt(nobs)
    exog[:, cols - 1] = level[lags : nobs - 1]
    for j in range(1, lags + 1):
        exog[:, cols + j - 1] = dy[lags - j : lags - j + nreg]
    return dy[lags:], exog


def _set_dummies(exog, regression, period, nobs, const, trend, lags):
    """The break columns of one period, with the slicing of the model definition."""
    cutoff = period - (lags + 1)
    if regression != "t":
        exog[:cutoff, 1] = 0
        exog[cutoff:, 1] = const
        exog[:, 2] = trend[(lags + 2) : (nobs + 1)]
        if regression == "ct":
            exog[:cutoff, 3] = 0
            exog[cutoff:, 3] = trend[1 : (nobs - period + 1)]
    else:
        exog[:, 1] = trend[(lags + 2) : (nobs + 1)]
        exog[: (cutoff - 1), 2] = 0
        exog[(cutoff - 1) :, 2] = trend[0 : (nobs - period + 1)]


def _qr_tvalue(y, exog, col):
    """t-statistic of column ``col`` and the condition number, by pivoted QR."""
    n, k = exog.shape
    q, r, piv = qr(exog, mode="economic", pivoting=True)
    diag = np.abs(np.diag(r))
    rank = int(np.sum(diag > max(n, k) * EPS * diag[0]))
    sv = svdvals(r)
    cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")
    if rank < k:
        return float("nan"), cond, rank
    coef_p = solve_triangular(r, q.T @ y)
    coef = np.empty(k)
    coef[piv] = coef_p
    resid = y - exog @ coef
    sigma2 = (resid @ resid) / (n - k)
    rinv = solve_triangular(r, np.eye(k))
    pos = int(np.flatnonzero(piv == col)[0])
    var = sigma2 * (rinv[pos] @ rinv[pos])
    return float(coef[col] / np.sqrt(var)), cond, rank


def oracle(x, *, trim, maxlag, regression, autolag, base) -> dict:
    """The oracle's zivot_andrews outcome; ``base`` is the base tree's stattools module."""
    za = base.ZivotAndrewsUnitRoot()
    x = np.asarray(x, dtype=float)
    nobs = x.shape[0]
    flags = []
    if not np.all(np.isfinite(x)):
        flags.append("nonfinite")
        return {"computed": False, "flags": flags}
    lags = _lags_of(x, nobs, maxlag, autolag and autolag.lower(), base.adfuller)
    trimcnt = int(nobs * trim)
    start, end = trimcnt, nobs - trimcnt
    cols = 5 if regression == "ct" else 4
    const = 1 / np.sqrt(nobs)
    trend = np.arange(1.0, nobs + 2) * (np.sqrt(3) / nobs ** (3 / 2))
    y, exog = _base_design(x, nobs, lags, cols)
    nreg = exog.shape[0]
    first = start + 1 - (lags + 1) - (1 if regression == "t" else 0)
    last = end - (lags + 1) - (1 if regression == "t" else 0)
    if trim == 0 or first <= 0 or last >= nreg:
        flags.append("zero-or-wrapping-dummy")
    stats = np.full(end + 1, np.inf)
    cond_max, min_rank = 0.0, exog.shape[1]
    for bp in range(start + 1, end + 1):
        try:
            _set_dummies(exog, regression, bp, nobs, const, trend, lags)
        except ValueError:
            flags.append("dummy-shape")
            return {"computed": False, "flags": flags, "lags": int(lags)}
        t, cond, rank = _qr_tvalue(y, exog, cols - 1)
        cond_max, min_rank = max(cond_max, cond), min(min_rank, rank)
        stats[bp] = t
    if min_rank < exog.shape[1]:
        flags.append("rank-deficient")
    if cond_max > 1e8:
        flags.append("cond-above-1e8")
    finite = stats[np.isfinite(stats)]
    if finite.size == 0:
        return {
            "computed": False,
            "flags": flags,
            "lags": int(lags),
            "cond_max": cond_max,
        }
    stat = float(np.min(stats))
    bpidx = int(np.argmin(stats)) - 1
    ordered = np.sort(finite)
    gap = (
        float(abs(ordered[1] - ordered[0]) / abs(ordered[0]))
        if ordered.size > 1
        else float("inf")
    )
    pval, crit = za._za_crit(stat, regression)
    return {
        "computed": True,
        "flags": flags,
        "stat": stat,
        "pvalue": float(pval),
        "crit": {k: float(v) for k, v in crit.items()},
        "lags": int(lags),
        "bpidx": bpidx,
        "gap": gap,
        "cond_max": cond_max,
        "second_bpidx": int(np.argsort(stats)[1]) - 1 if ordered.size > 1 else None,
    }
