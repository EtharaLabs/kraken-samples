#!/usr/bin/env bash
# Liveness control V1 (no fix): adds a file outside numpy/, which the overlay ignores.
set -euo pipefail
mkdir -p /app/numpy/tools
printf '# isin timing notes\n' > /app/numpy/tools/isin_notes.py
