"""Equivalence of two output dumps (child.py) without importing scikit-learn.

Every output field must be present in both dumps with the same shape. Integer fields
(numbers of iterations) must be equal. The selected regularization (`alpha`,
`l1_ratio`) and the alpha grid (`alphas`) must be equal within a relative 1e-9.
Every other float field (coefficients, intercepts, dual gaps, cross-validation error
paths) must satisfy max|a - b| <= RTOL * max(max|a|, 1e-12) with RTOL = 1e-6.
"""

from __future__ import annotations

RTOL = 1e-6
TIGHT = 1e-9
TIGHT_FIELDS = ("alpha", "l1_ratio", "alphas")


def _field_diff(name: str, a: dict, b: dict) -> str | None:
    if a["dtype"] != b["dtype"] or a["shape"] != b["shape"]:
        return f"{name}: dtype or shape differs"
    va, vb = a["v"], b["v"]
    if a["dtype"] == "int":
        return None if va == vb else f"{name}: integer values differ"
    if any(x != x for x in vb):
        return f"{name}: NaN in output"
    scale = max([abs(x) for x in va] + [1e-12])
    rtol = TIGHT if name in TIGHT_FIELDS else RTOL
    worst = max((abs(x - y) for x, y in zip(va, vb)), default=0.0)
    if worst > rtol * scale:
        return f"{name}: max abs difference {worst:.3e} exceeds {rtol:g} x {scale:.3e}"
    return None


def output_diff(a: dict, b: dict) -> str | None:
    """None when equivalent, else a short reason."""
    if set(a) != set(b):
        return "output fields differ"
    for name in sorted(a):
        d = _field_diff(name, a[name], b[name])
        if d:
            return d
    return None
