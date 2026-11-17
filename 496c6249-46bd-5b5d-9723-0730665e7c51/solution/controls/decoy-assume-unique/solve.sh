#!/usr/bin/env bash
# Negative control N4 (decoy): the sort path for string operands without a missing
# value only when assume_unique=True (setdiff1d's internal call). No timed call passes
# assume_unique, so nothing timed gets faster.
set -euo pipefail
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''    contains_object = ar1.dtype.hasobject or ar2.dtype.hasobject
'''
new = '''    unique_strings = assume_unique and all(
        ar.dtype.kind in "TU" and not hasattr(ar.dtype, "na_object")
        for ar in (ar1, ar2))
    contains_object = (
        ar1.dtype.hasobject or ar2.dtype.hasobject) and not unique_strings
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
