"""Instance classes and the equality relation of each class.

well      condition number below 1e5: the base commit is the reference, the
          statistic and p-value within rtol 1e-9 / atol 1e-12, the critical
          values exactly, the lag and break index exactly (near-tie rule).
near      condition number from 1e5 to 5e6 inclusive: the independent QR oracle is
          the reference for the statistic and break index, rtol 1e-6 (near-tie rule).
fallback  non-finite data, condition number above 5e6, near-span, all-zero or
          wrapping dummies, trim 0, or any base exception: a value matches the
          base commit or the oracle within rtol 1e-6; an exception matches the
          base commit's type and message; every warning raised matches one the base
          commit raises, by category and message (never by source location).
"""

from __future__ import annotations

import math

WELL_RTOL, WELL_ATOL = 1e-9, 1e-12
NEAR_RTOL, NEAR_ATOL = 1e-6, 1e-12
NEAR_LO, NEAR_HI = 1e5, 5e6


def classify(spec: dict, base: dict, orc: dict) -> str:
    if (
        spec["intended"] == "fallback"
        or not base.get("ok")
        or base.get("nonfinite_stat")
        or not orc.get("computed")
        or orc.get("flags")
        or orc.get("cond_max", math.inf) > NEAR_HI
    ):
        return "fallback"
    return "near" if orc["cond_max"] >= NEAR_LO else "well"


def _close(a: float, b: float, rtol: float, atol: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= atol + rtol * abs(b)


def _rel(a: float, b: float) -> float:
    if math.isnan(a) or math.isnan(b):
        return 0.0 if (math.isnan(a) and math.isnan(b)) else math.inf
    return abs(a - b) / max(abs(b), 1e-300)


def _bpidx_ok(
    got: int, ref: int, gap: float | None, second: int | None, rtol: float
) -> bool:
    if got == ref:
        return True
    return gap is not None and gap < rtol and second is not None and got == second


def _lags_ok(sub: dict, base: dict) -> bool:
    if sub["lags"] == base["lags"]:
        return True
    gap = base.get("ic_gap")
    return gap is not None and gap < WELL_RTOL


def _against(sub: dict, ref: dict, rtol: float, atol: float, gap, second) -> list[str]:
    bad = []
    if not _close(sub["stat"], ref["stat"], rtol, atol):
        bad.append(f"statistic {sub['stat']!r} vs {ref['stat']!r}")
    if not _close(sub["pvalue"], ref["pvalue"], rtol, atol):
        bad.append(f"p-value {sub['pvalue']!r} vs {ref['pvalue']!r}")
    if not _bpidx_ok(sub["bpidx"], ref["bpidx"], gap, second, rtol):
        bad.append(f"break index {sub['bpidx']} vs {ref['bpidx']}")
    return bad


def _common(sub: dict, base: dict) -> list[str]:
    bad = []
    if sub["crit"] != base["crit"]:
        bad.append(f"critical values {sub['crit']} vs {base['crit']}")
    if not _lags_ok(sub, base):
        bad.append(f"lags {sub['lags']} vs {base['lags']}")
    return bad


def _exception(sub: dict, base: dict) -> list[str]:
    if sub.get("ok"):
        return [
            f"returned a value where the base raised {base['exc_type']}: {base['exc_msg'][:120]}"
        ]
    if (sub["exc_type"], sub["exc_msg"]) != (base["exc_type"], base["exc_msg"]):
        return [
            f"raised {sub['exc_type']}: {sub['exc_msg'][:120]!r}; base raised "
            f"{base['exc_type']}: {base['exc_msg'][:120]!r}"
        ]
    return []


def judge(cls: str, sub: dict, base: dict, orc: dict) -> list[str]:
    """Reasons the submission's outcome is wrong; empty when it matches."""
    if not base.get("ok"):
        return _exception(sub, base)
    if not sub.get("ok"):
        return [
            f"raised {sub.get('exc_type')}: {sub.get('exc_msg', '')[:160]!r} where the base returned"
        ]
    profile = base.get("profile") or {}
    match cls:
        case "well":
            return _common(sub, base) + _against(
                sub,
                base,
                WELL_RTOL,
                WELL_ATOL,
                profile.get("gap"),
                profile.get("second_bpidx"),
            )
        case "near":
            return _common(sub, base) + _against(
                sub, orc, NEAR_RTOL, NEAR_ATOL, orc.get("gap"), orc.get("second_bpidx")
            )
        case "fallback":
            bad = _common(sub, base)
            extra = sorted({tuple(w) for w in sub["warnings"]} - {tuple(w) for w in base["warnings"]})
            if extra:
                bad.append(f"warnings the base does not raise: {extra[:4]}")
            vs_base = _against(
                sub,
                base,
                NEAR_RTOL,
                NEAR_ATOL,
                profile.get("gap"),
                profile.get("second_bpidx"),
            )
            if vs_base and orc.get("computed"):
                vs_orc = _against(
                    sub,
                    orc,
                    NEAR_RTOL,
                    NEAR_ATOL,
                    orc.get("gap"),
                    orc.get("second_bpidx"),
                )
                if vs_orc:
                    bad += [
                        f"neither base ({'; '.join(vs_base)}) nor oracle ({'; '.join(vs_orc)})"
                    ]
            elif vs_base:
                bad += vs_base
            return bad
        case _:
            raise ValueError(cls)


def errors(sub: dict, base: dict, orc: dict) -> dict:
    """Relative statistic error against the base and the oracle, for the margin table."""
    out = {}
    if sub.get("ok") and base.get("ok"):
        out["vs_base"] = _rel(sub["stat"], base["stat"])
        out["pvalue_vs_base"] = _rel(sub["pvalue"], base["pvalue"])
    if sub.get("ok") and orc.get("computed"):
        out["vs_oracle"] = _rel(sub["stat"], orc["stat"])
    return out
