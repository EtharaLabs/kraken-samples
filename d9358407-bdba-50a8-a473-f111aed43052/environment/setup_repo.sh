#!/bin/bash
# Clone the target repo at base_commit; env creation happens later.
set -euo pipefail

git clone https://github.com/networkx/networkx.git /testbed
cd /testbed
git fetch --all --tags --quiet
git checkout 05809740ff46c1bd03998bcef1d7686444048371

# Keep local build artifacts out of git so agent diffs stay clean.
cat >> /testbed/.git/info/exclude <<'EOF'
.dep-manifest.txt
*.egg-info/
__pycache__/
*.pyc
build/
dist/
.pytest_cache/
EOF
