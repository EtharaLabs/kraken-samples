#!/bin/bash
# Clone the target repo at base_commit; env creation happens later.
set -euo pipefail

git clone https://github.com/pallets/jinja.git /testbed
cd /testbed
git fetch --all --tags --quiet
git checkout 99b6fc7f37449f009b5c114b8159ccd4d10c1167

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
