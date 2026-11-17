#!/usr/bin/env bash
# Oracle: apply the reference library change (reference.patch: the upstream fix plus an authored C
# hash path for StringDType membership, exact context) to /app/numpy
# and recompile the editable build in place.
set -euo pipefail
python3 "$(dirname "$0")/apply.py" +reference.patch
ninja -C /app/numpy/build
