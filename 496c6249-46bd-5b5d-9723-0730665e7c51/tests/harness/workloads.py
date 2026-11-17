"""Hidden instances, generated from a verify-time seed with the standard-library RNG.

Nothing here depends on the numpy under test: instances are plain Python data plus
dtype descriptors, and child.py turns them into arrays with whichever build it runs.
"""

from __future__ import annotations

import random
from typing import Any

LETTERS = "abcdefghijklmnopqrstuvwxyz"
WIDE = "\u00e9\u00df\u00f8\u00f1\u4e2d\u6587\u5b57\u03bb\u03a9\u0436\U0001f642"


class _Sentinel:
    """An arbitrary missing-value object; one instance per process."""

    def __repr__(self) -> str:
        return "<sentinel>"


SENTINEL = _Sentinel()
# The "no missing value" kind: a plain StringDType without na_object.
NO_NA = "absent"
NA_KINDS = (NO_NA, "none", "nan", "str_na", "str_empty", "object", "pd_na")
TIMED_CLASSES = ("plain", "none", "nan", "str_na", "object", "mixed")
TIMED_NA = {
    "plain": "absent",
    "none": "none",
    "nan": "nan",
    "str_na": "str_na",
    "object": "object",
    "mixed": "none",
}


def na_value(kind: str) -> Any:
    match kind:
        case "none":
            return None
        case "nan":
            return float("nan")
        case "str_na":
            return "NA"
        case "str_empty":
            return ""
        case "object":
            return SENTINEL
        case "pd_na":
            from numpy._core.tests._natype import pd_NA

            return pd_NA
        case _:
            raise ValueError(kind)


def word(rng: random.Random, wide_share: float = 0.2, nul_share: float = 0.02) -> str:
    """A string of 0 to 12 or 16 to 48 characters, sometimes non-ASCII or NUL-terminated.

    Fixed-width unicode drops trailing NUL characters, so instances that mix in a
    fixed-width operand draw with nul_share 0: there the stripped and unstripped
    spellings would be two different strings in one operand and one in the other.
    """
    length = rng.randint(16, 48) if rng.random() < 0.3 else rng.randint(0, 12)
    chars = LETTERS + (WIDE if rng.random() < wide_share else "")
    text = "".join(rng.choice(chars) for _ in range(length))
    return text + "\x00" if rng.random() < nul_share else text


def draw(
    rng: random.Random, n: int, pool: list[str], kind: str, share: float
) -> list[Any]:
    if kind == NO_NA or share <= 0.0:
        return [rng.choice(pool) for _ in range(n)]
    na = na_value(kind)
    return [na if rng.random() < share else rng.choice(pool) for _ in range(n)]


def _key(value: Any) -> tuple[str, str]:
    return ("s", value) if isinstance(value, str) else ("na", "")


def unique(values: list[Any]) -> list[Any]:
    seen: set[tuple[str, str]] = set()
    out = []
    for value in values:
        if _key(value) not in seen:
            seen.add(_key(value))
            out.append(value)
    return out


def _case(op: str, left: tuple, right: tuple | None, **kwargs: Any) -> dict:
    return {"op": op, "left": left, "right": right, "kwargs": kwargs}


def _isin_family(rng: random.Random, kind: str) -> list[dict]:
    pool = [word(rng) for _ in range(rng.randint(150, 400))] + [""]
    share = 0.15 if kind != NO_NA else 0.0
    a = draw(rng, rng.randint(300, 900), pool, kind, share)
    b = draw(rng, rng.randint(200, 700), pool, kind, share)
    t = ("T", kind)
    rows, cols = 17, rng.randint(5, 17)
    cases = [
        _case("isin", (t, a), (t, b)),
        _case("isin", (t, a), (t, b), invert=True),
        _case("isin", (t, a), (t, b), kind="sort"),
        _case("isin", (t, a), (t, b), kind="sort", invert=True),
        _case("isin", (t, a), (t, b[:5])),
        _case("isin", (t, unique(a)), (t, unique(b)), assume_unique=True),
        _case("isin", (t, unique(a)), (t, unique(b)), assume_unique=True, invert=True),
        _case("isin", (t, a), (t, [])),
        _case("isin", (t, []), (t, b)),
        _case("isin", (t, a[:1]), (t, b)),
        _case("isin", (t, a), (t, b[:1])),
        _case("isin", (t, a[: rows * cols], (rows, cols)), (t, b)),
        _case("isin", (t, a[: rows * cols], (rows, cols)), (t, b), invert=True),
        _case("setdiff1d", (t, a), (t, b)),
        _case("intersect1d", (t, a), (t, b)),
        _case("union1d", (t, a), (t, b)),
        _case("setxor1d", (t, a), (t, b)),
        _case("unique", (t, a), None),
    ]
    if kind != NO_NA:
        na = na_value(kind)
        clean_a = [v for v in a if isinstance(v, str)]
        clean_b = [v for v in b if isinstance(v, str)]
        cases += [
            _case("isin", (t, [na] * 40), (t, [na] * 40)),
            _case("isin", (t, [na] * 40), (t, [na] * 40), invert=True),
            _case("isin", (t, a), (t, clean_b)),
            _case("isin", (t, clean_a), (t, b)),
            _case("isin", (t, a), (t, clean_b), invert=True),
            _case("setdiff1d", (t, a), (t, clean_b)),
        ]
    return cases


def _mixed(rng: random.Random) -> list[dict]:
    pool = [word(rng, wide_share=0.3, nul_share=0.0) for _ in range(rng.randint(150, 400))]
    cases: list[dict] = []
    for kind in ("absent", "none", "nan", "str_na"):
        a = draw(
            rng, rng.randint(300, 900), pool, kind, 0.15 if kind != NO_NA else 0.0
        )
        u = [rng.choice(pool) for _ in range(rng.randint(200, 700))]
        t = ("T", kind)
        cases += [
            _case("isin", (t, a), (("U",), u)),
            _case("isin", (("U",), u), (t, a)),
            _case("isin", (t, a), (("U",), u), invert=True),
            _case("isin", (("U",), u), (t, a), kind="sort"),
            _case("setdiff1d", (t, a), (("U",), u)),
        ]
    return cases


def _incompatible(rng: random.Random) -> list[dict]:
    pool = [word(rng) for _ in range(rng.randint(150, 400))]
    pairs = (
        ("none", "nan"),
        ("nan", "none"),
        ("none", "str_na"),
        ("str_na", "object"),
        ("pd_na", "none"),
        ("str_empty", "str_na"),
        ("absent", "none"),
        ("object", "nan"),
    )
    cases: list[dict] = []
    for left, right in pairs:
        a = draw(rng, rng.randint(300, 900), pool, left, 0.1)
        b = draw(rng, rng.randint(200, 700), pool, right, 0.1)
        cases += [
            _case("isin", (("T", left), a), (("T", right), b)),
            _case("isin", (("T", left), a), (("T", right), b), invert=True),
            _case("setdiff1d", (("T", left), a), (("T", right), b)),
        ]
    a = draw(rng, 500, pool, "none", 0.1)
    cases.append(_case("isin", (("T", "none"), a), (("O",), list(pool[:300]))))
    return cases


def correctness_cases(seed: int) -> list[dict]:
    rng = random.Random(seed)
    cases: list[dict] = []
    for kind in NA_KINDS:
        cases += _isin_family(rng, kind)
    return cases + _mixed(rng) + _incompatible(rng)


def timed_case(name: str, n_left: int, n_right: int, seed: int) -> dict:
    rng = random.Random(seed)
    kind = TIMED_NA[name]
    nul_share = 0.0 if name == "mixed" else 0.02
    pool = [word(rng, nul_share=nul_share) for _ in range(max(64, n_left // 4))]
    share = 0.0 if kind == NO_NA else 0.1
    left = (("T", kind), draw(rng, n_left, pool, kind, share))
    if name == "mixed":
        right = (("U",), [rng.choice(pool) for _ in range(n_right)])
    else:
        right = (("T", kind), draw(rng, n_right, pool, kind, share))
    return _case("isin", left, right)
