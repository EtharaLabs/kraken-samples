#!/bin/bash
# Clone the target repo at base_commit; env creation happens later.
set -euo pipefail

git clone https://github.com/networkx/networkx.git /testbed
cd /testbed
git fetch --all --tags --quiet
git checkout 1515862e8ed0aa9f1894f28b780ba19e81e9454b

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
