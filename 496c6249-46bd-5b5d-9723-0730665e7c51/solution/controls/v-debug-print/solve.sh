#!/usr/bin/env bash
# Liveness control V2 (no fix): leaves a debugging print in _isin.
set -euo pipefail
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
old = '    # Check if one of the arrays may contain arbitrary objects\n'
assert t.count(old) == 1
p.write_text(t.replace(old, '    print("isin", ar1.dtype, ar2.dtype)\n' + old))
PY
