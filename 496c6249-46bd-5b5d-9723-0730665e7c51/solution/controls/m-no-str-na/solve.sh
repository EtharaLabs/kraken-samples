#!/usr/bin/env bash
# Mutant M3 (one fault): the upstream fix, but a string missing value keeps the
# comparison loop.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$here/apply.py" +reference.patch
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''            string_dtype = np.result_type(ar1, ar2)
'''
new = '''            string_dtype = np.result_type(ar1, ar2)
            if string_dtype._has_string_na:
                string_dtype = None
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
