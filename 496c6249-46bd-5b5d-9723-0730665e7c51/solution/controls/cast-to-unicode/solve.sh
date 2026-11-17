#!/usr/bin/env bash
# Negative control N2 (known-wrong, correctness): cast StringDType operands to
# fixed-width unicode so the sort path applies. A NaN-like missing value becomes the
# string "nan" and matches itself, other sentinels become their str(), and trailing
# NUL characters are stripped, so results change.
set -euo pipefail
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''    # Check if one of the arrays may contain arbitrary objects
    contains_object = ar1.dtype.hasobject or ar2.dtype.hasobject
'''
new = '''    if "T" in (ar1.dtype.kind, ar2.dtype.kind) and {ar1.dtype.kind, ar2.dtype.kind} <= {"T", "U"}:
        ar1 = ar1.astype(np.str_)
        ar2 = ar2.astype(np.str_)
''' + old
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
