#!/usr/bin/env bash
# Liveness control V6 (no fix): adds a keyword to setdiff1d's public signature (red line RL5).
set -euo pipefail
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import re, sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
new, n = re.subn(r'def setdiff1d\(([^)]*)\):', r'def setdiff1d(\1, *, _fast=False):', t)
assert n == 1
p.write_text(new)
PY
