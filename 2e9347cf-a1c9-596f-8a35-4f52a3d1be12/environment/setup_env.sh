#!/bin/bash
# Create conda testbed env, install repo, snapshot as harbor-base.
set -euo pipefail

source /opt/miniconda3/etc/profile.d/conda.sh
cd /testbed

conda create -n testbed python=3.10 -y
conda activate testbed
python -m pip install --upgrade pip setuptools wheel

# --- install_cmd ---
pip install -e . && pip install pytest markupsafe

# --- pip_packages ---
pip install pytest markupsafe

# Ensure pytest tooling is present regardless of dataset spec
pip install pytest pytest-xdist coverage unidiff

pip freeze > /testbed/.dep-manifest.txt

# Snapshot canonical post-install commit so agent diffs & reset --hard are symmetric.
git add -A
git -c user.email='harbor@local' -c user.name='harbor' commit --allow-empty -m 'harbor: post-install snapshot' >/dev/null
git tag harbor-base
