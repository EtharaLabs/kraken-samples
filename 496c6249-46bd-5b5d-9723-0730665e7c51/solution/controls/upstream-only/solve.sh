#!/usr/bin/env bash
# Control U1 (score below the reference): the upstream fix 7643e77e alone, an earlier version of the reference.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$here/apply.py" +controls/upstream-only/upstream.patch
ninja -C /app/numpy/build
