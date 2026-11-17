"""One measurement in a fresh interpreter against one numpy build.

usage: child.py <site> api
       child.py <site> correct <seed>
       child.py <site> time <class> <n_left> <n_right> <seed>

<site> is the directory holding the numpy package under test. Prints one JSON
line on stdout. In `time` mode only the first np.isin call is timed.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import sys
import time
from typing import Any

ABSENT = "<absent>"


def _canon(value: Any) -> list:
    if isinstance(value, str):
        return ["s", value]
    if isinstance(value, float) and value != value:
        return ["nan"]
    return ["na", type(value).__name__]


def _dtype(np: Any, desc: tuple) -> Any:
    from numpy.dtypes import StringDType

    import workloads

    match desc[0]:
        case "T":
            kind = desc[1]
            return (
                StringDType()
                if kind == workloads.NO_NA
                else StringDType(na_object=workloads.na_value(kind))
            )
        case "U":
            return np.dtype("U")
        case "O":
            return np.dtype(object)
        case other:
            raise ValueError(other)


def _array(np: Any, spec: tuple) -> Any:
    desc, values, *shape = spec
    arr = np.array(values, dtype=_dtype(np, tuple(desc)))
    return arr.reshape(tuple(shape[0])) if shape else arr


def _dtype_key(dtype: Any) -> list:
    if dtype.kind == "T":
        return ["T", _canon(getattr(dtype, "na_object", ABSENT))]
    return [dtype.kind]


def _result(np: Any, value: Any) -> list:
    if isinstance(value, tuple):
        return ["tuple", [_result(np, v) for v in value]]
    arr = np.asarray(value)
    if arr.dtype == np.bool_:
        return ["bool", list(arr.shape), hashlib.sha256(arr.tobytes()).hexdigest()]
    return [
        "arr",
        _dtype_key(arr.dtype),
        list(arr.shape),
        [_canon(v) for v in arr.ravel().tolist()],
    ]


def _run_case(np: Any, case: dict) -> list:
    try:
        left = _array(np, tuple(case["left"]))
        func = getattr(np, case["op"])
        if case["right"] is None:
            out = func(left, **case["kwargs"])
        else:
            out = func(left, _array(np, tuple(case["right"])), **case["kwargs"])
        return _result(np, out)
    except (
        Exception
    ) as exc:  # boundary: the base build's exception class is part of its semantics
        return ["raise", type(exc).__name__]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _api(np: Any) -> dict:
    from numpy.dtypes import StringDType

    names = (
        "isin",
        "setdiff1d",
        "intersect1d",
        "union1d",
        "setxor1d",
        "unique",
        "unique_values",
        "unique_inverse",
        "unique_counts",
        "unique_all",
        "ediff1d",
    )
    out: dict[str, Any] = {
        name: str(inspect.signature(getattr(np, name))) for name in names
    }
    out["has_in1d"] = hasattr(np, "in1d")
    out["arraysetops_all"] = sorted(importlib.import_module("numpy.lib._arraysetops_impl").__all__)
    out["stringdtype_public"] = sorted(
        a for a in dir(StringDType(na_object=None)) if not a.startswith("_")
    )
    return out


def main(argv: list[str]) -> None:
    site, mode, *rest = argv
    sys.path.insert(0, site)
    import numpy as np

    if not np.__file__.startswith(site):
        raise SystemExit(f"numpy imported from {np.__file__}, expected {site}")
    import workloads

    match mode:
        case "api":
            detail = _api(np)
            print(json.dumps({"digest": _digest(detail), "detail": detail}))
        case "correct":
            results = [
                _run_case(np, case)
                for case in workloads.correctness_cases(int(rest[0]))
            ]
            print(
                json.dumps(
                    {
                        "digest": _digest(results),
                        "cases": [_digest(r) for r in results],
                        "raised": [i for i, r in enumerate(results) if r[0] == "raise"],
                    }
                )
            )
        case "time":
            case = workloads.timed_case(
                rest[0], int(rest[1]), int(rest[2]), int(rest[3])
            )
            left, right = (
                _array(np, tuple(case["left"])),
                _array(np, tuple(case["right"])),
            )
            start = time.perf_counter()
            mask = np.isin(left, right)
            seconds = time.perf_counter() - start
            print(
                json.dumps({"seconds": seconds, "digest": _digest(_result(np, mask))})
            )
        case other:
            raise SystemExit(f"unknown mode {other}")


if __name__ == "__main__":
    main(sys.argv[1:])
