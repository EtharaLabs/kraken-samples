#!/usr/bin/env bash
# Reference solution: apply the fast reference implementation (solution/reference.patch,
# library source only: sklearn/linear_model/_cd_fast.pyx and
# sklearn/linear_model/_coordinate_descent.py, the same change the verifier times as
# T_ref) to the working tree at /app/scikit-learn. The sandbox has no git or patch binary,
# so solution/apply.py applies the unified diff with exact context. The verifier rebuilds
# the tree itself. No network is used.
set -euo pipefail
python3 "$(dirname "$0")/apply.py" +reference.patch
