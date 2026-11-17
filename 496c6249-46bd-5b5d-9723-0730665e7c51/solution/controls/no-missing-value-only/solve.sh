#!/usr/bin/env bash
# Negative control N3 (partial): only string operands without any missing-value
# sentinel take the sort path; every array with an na_object keeps the comparison loop.
set -euo pipefail
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''    contains_object = ar1.dtype.hasobject or ar2.dtype.hasobject
'''
new = '''    plain_strings = all(
        ar.dtype.kind in "TU" and not hasattr(ar.dtype, "na_object")
        for ar in (ar1, ar2))
    contains_object = (
        ar1.dtype.hasobject or ar2.dtype.hasobject) and not plain_strings
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
