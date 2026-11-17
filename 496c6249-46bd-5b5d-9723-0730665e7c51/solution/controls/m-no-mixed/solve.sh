#!/usr/bin/env bash
# Mutant M1 (one fault): the upstream fix, but only two StringDType operands take the
# sort path, so StringDType against fixed-width unicode keeps the comparison loop.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$here/apply.py" +reference.patch
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''    if (ar1.dtype.kind == "T" or ar2.dtype.kind == "T") and (
            ar1.dtype.kind in "TU" and ar2.dtype.kind in "TU"):
'''
new = '''    if ar1.dtype.kind == "T" and ar2.dtype.kind == "T":
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
