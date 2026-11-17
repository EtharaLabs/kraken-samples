"""Equivalence of two output dumps (child.py) without importing Cirq.

Circuits: same moment count; in each moment the same qubit-bearing operations (same
qubits, kind and tags), each unitary equal to the other up to a global phase within
ATOL, non-unitary operations equal by repr, circuit operations equal in repetitions
and recursively in body, and the product of the moment's global-phase operations
equal within ATOL (so several phases may be combined into one). Matrices: equal
within ATOL, phase included.
"""

from __future__ import annotations

import cmath

ATOL = 1e-7


def _c(v: list[float]) -> complex:
    return complex(v[0], v[1])


def _phase_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    x, y = [_c(v) for v in a], [_c(v) for v in b]
    inner = sum(p.conjugate() * q for p, q in zip(x, y))
    if abs(inner) < 1e-12:
        return False
    phase = inner / abs(inner)
    return all(abs(p * phase - q) <= ATOL for p, q in zip(x, y))


def _exact_equal(a: list, b: list) -> bool:
    return len(a) == len(b) and all(abs(_c(p) - _c(q)) <= ATOL for p, q in zip(a, b))


def _moment_diff(ma: list, mb: list, where: str) -> str | None:
    pa = cmath.exp(0)
    pb = cmath.exp(0)
    keyed_a, keyed_b = {}, {}
    for rec in ma:
        if rec["k"] == "g":
            pa *= _c(rec["v"])
        else:
            keyed_a[tuple(rec["q"])] = rec
    for rec in mb:
        if rec["k"] == "g":
            pb *= _c(rec["v"])
        else:
            keyed_b[tuple(rec["q"])] = rec
    if abs(pa - pb) > ATOL:
        return f"{where}: global phase {pa} != {pb}"
    if keyed_a.keys() != keyed_b.keys():
        return f"{where}: operation qubits differ"
    for key, ra in keyed_a.items():
        rb = keyed_b[key]
        if ra["k"] != rb["k"] or ra["t"] != rb["t"]:
            return f"{where}{list(key)}: kind or tags differ"
        if ra["k"] == "u" and not _phase_equal(ra["v"], rb["v"]):
            return f"{where}{list(key)}: unitary differs"
        if ra["k"] == "o" and ra["v"] != rb["v"]:
            return f"{where}{list(key)}: operation differs"
        if ra["k"] == "c":
            if ra["rep"] != rb["rep"]:
                return f"{where}{list(key)}: repetitions differ"
            d = circuit_diff(ra["c"], rb["c"], f"{where}{list(key)}/")
            if d:
                return d
    return None


def circuit_diff(a: list, b: list, where: str = "") -> str | None:
    if len(a) != len(b):
        return f"{where}moment count {len(a)} != {len(b)}"
    for i, (ma, mb) in enumerate(zip(a, b)):
        d = _moment_diff(ma, mb, f"{where}m{i}")
        if d:
            return d
    return None


def output_diff(a: dict, b: dict) -> str | None:
    """None when equivalent, else a short reason."""
    if a.get("kind") != b.get("kind"):
        return "result kind differs"
    if a["kind"] == "matrices":
        if len(a["v"]) != len(b["v"]):
            return "matrix count differs"
        for i, (x, y) in enumerate(zip(a["v"], b["v"])):
            if not _exact_equal(x, y):
                return f"matrix {i} differs"
        return None
    if a.get("type") != b.get("type"):
        return "result type differs"
    return circuit_diff(a["v"], b["v"])
