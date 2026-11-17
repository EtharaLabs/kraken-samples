#!/usr/bin/env bash
# Negative control N5 (known-wrong, build): the upstream fix plus a C syntax error in
# the StringDType source, so the meson build fails.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$here/apply.py" +reference.patch
printf '\nstatic int stringdtype_broken = ;\n' >> /app/numpy/numpy/_core/src/multiarray/stringdtype/dtype.c
