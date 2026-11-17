#!/usr/bin/env bash
# Control P1 (score below 0.40): the Opus 5.5 author-side probe patch of 2026-11-04, a pure-Python tolist and set fast path in _isin.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$here/apply.py" +controls/probe-patch/probe.patch
ninja -C /app/numpy/build
