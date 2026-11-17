#!/usr/bin/env bash
# Oracle: apply solution/reference.patch, the upstream fix of statsmodels pull
# request 10602 restricted to its two source files, to /app/statsmodels with exact
# context. The sandbox has no git or patch binary, so solution/apply.py applies it.
set -euo pipefail
python3 "$(dirname "$0")/apply.py" +reference.patch
