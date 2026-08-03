#!/bin/bash
# Oracle solution: apply the reference patch that produced the target speedup.
set -euo pipefail

source /opt/miniconda3/etc/profile.d/conda.sh
conda activate testbed
cd /testbed
git reset --hard harbor-base
git clean -fdx -e .venv -e "*.egg-info"

if [ -s /solution/patch.diff ]; then
    if git apply --verbose /solution/patch.diff; then
        echo ">>>>> Applied oracle patch"
    elif git apply --verbose --ignore-space-change /solution/patch.diff; then
        echo ">>>>> Applied oracle patch (ignoring whitespace)"
    else
        echo ">>>>> Oracle patch failed to apply" >&2
        exit 1
    fi
else
    echo "Oracle patch is empty; nothing to do."
fi

pip install -e .
echo "Oracle solution complete."
